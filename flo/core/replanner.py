"""
FLO Core Replanner — Dynamic event-driven fleet replanning engine.
"""

from typing import List, Dict, Tuple, Optional
from flo.core.models import (
    AGVModel, TaskModel, AGVStatus, TaskStatus, EventLog
)
from flo.core.graph import FactoryGraph
from flo.core.battery import BatteryManager
from flo.core.assignment import AssignmentEngine

class Replanner:
    def __init__(self, graph: FactoryGraph, battery_mgr: BatteryManager, assignment_engine: AssignmentEngine):
        self.graph = graph
        self.battery_mgr = battery_mgr
        self.assignment_engine = assignment_engine

    def handle_route_change_event(
        self,
        agvs: List[AGVModel],
        tasks: Dict[str, TaskModel]
    ) -> Tuple[List[Dict], List[EventLog]]:
        """
        Triggered when route congestion increases or route is blocked.
        Re-plans routes for active AGVs if a faster/cheaper route exists.
        If a route is completely blocked and no alternative exists, releases task to WAITING.
        """
        commands = []
        events = []

        for agv in agvs:
            if agv.status in [AGVStatus.MOVING_TO_PICKUP, AGVStatus.MOVING_TO_DESTINATION] and agv.current_route:
                # Get remaining destination
                dest_node = agv.current_route[-1]
                curr_node = agv.current_node

                if curr_node != dest_node:
                    new_route_data = self.graph.find_route(curr_node, dest_node, consider_congestion=True)
                    if new_route_data:
                        new_route = new_route_data["route"]
                        # Compare if route changed significantly or old route was blocked
                        if new_route != agv.current_route[agv.route_index:]:
                            agv.current_route = agv.current_route[:agv.route_index] + new_route
                            agv.route_index = min(agv.route_index, len(agv.current_route) - 1)

                            cmd = {
                                "command": "reroute_agv",
                                "agv_id": agv.id,
                                "new_route": agv.current_route
                            }
                            commands.append(cmd)

                            evt = EventLog(
                                id=f"evt_{len(events)+1}",
                                timestamp="NOW",
                                level="WARNING",
                                message=f"AGV {agv.id} dynamically rerouted to bypass congestion/blockage via {' -> '.join(new_route)}",
                                category="REPLAN"
                            )
                            events.append(evt)
                    else:
                        # No unblocked route exists! Release task to WAITING
                        if agv.current_task_id and agv.current_task_id in tasks:
                            task = tasks[agv.current_task_id]
                            task.status = TaskStatus.WAITING
                            task.assigned_agv_id = None
                            t_id = agv.current_task_id
                            agv.current_task_id = None
                            agv.current_route = []
                            agv.route_index = 0
                            agv.status = AGVStatus.AVAILABLE

                            commands.append({"command": "release_task", "task_id": t_id, "agv_id": agv.id})
                            events.append(EventLog(
                                id=f"evt_block_{len(events)+1}",
                                timestamp="NOW",
                                level="WARNING",
                                message=f"Task {t_id} placed in WAITING: No currently feasible route available for AGV {agv.id}",
                                category="CONGESTION"
                            ))

        return commands, events

    def handle_agv_failure_event(
        self,
        failed_agv_id: str,
        agvs: List[AGVModel],
        tasks: Dict[str, TaskModel]
    ) -> Tuple[List[Dict], List[EventLog]]:
        """
        Triggered when an AGV fails (`[ FAIL AGV ]`).
        Re-queues task, releases reservations, and assigns to next best feasible AGV.
        """
        commands = []
        events = []

        # Find failed AGV
        failed_agv = next((a for a in agvs if a.id == failed_agv_id), None)
        if not failed_agv:
            return commands, events

        failed_agv.status = AGVStatus.FAILED
        failed_agv.charging = False

        evt1 = EventLog(
            id=f"evt_fail_1",
            timestamp="NOW",
            level="ERROR",
            message=f"CRITICAL: AGV {failed_agv.id} HAS FAILED! Re-evaluating fleet tasks...",
            category="FAILURE"
        )
        events.append(evt1)

        # Requeue active task if present
        if failed_agv.current_task_id and failed_agv.current_task_id in tasks:
            task = tasks[failed_agv.current_task_id]
            stale_task_id = task.task_id

            task.status = TaskStatus.REASSIGNING
            task.assigned_agv_id = None
            failed_agv.current_task_id = None
            failed_agv.current_route = []
            failed_agv.route_index = 0

            # Signal simulator to release task
            commands.append({"command": "release_task", "task_id": stale_task_id, "agv_id": failed_agv_id})

            events.append(EventLog(
                id=f"evt_rel_{stale_task_id}",
                timestamp="NOW",
                level="WARNING",
                message=f"Task {stale_task_id} released from failed AGV {failed_agv_id} -> entering REASSIGNMENT",
                category="FAILURE"
            ))

            # Attempt reassignment with remaining operational AGVs
            remaining_agvs = [a for a in agvs if a.id != failed_agv.id and a.status != AGVStatus.FAILED]
            new_agv, explanation, route_data = self.assignment_engine.assign_best_agv(
                task, remaining_agvs, allow_reassignment=True
            )

            if new_agv and route_data:
                task.status = TaskStatus.ASSIGNED
                task.assigned_agv_id = new_agv.id
                new_agv.current_task_id = task.task_id
                new_agv.current_route = route_data["route"]
                new_agv.route_index = 0
                new_agv.status = AGVStatus.MOVING_TO_PICKUP

                commands.append({
                    "command": "assign_task",
                    "agv_id": new_agv.id,
                    "task_id": task.task_id,
                    "route": route_data["route"],
                    "pickup": task.pickup,
                    "destination": task.destination
                })

                evt2 = EventLog(
                    id=f"evt_fail_2",
                    timestamp="NOW",
                    level="SUCCESS",
                    message=f"Task {task.task_id} successfully reassigned from failed {failed_agv_id} to {new_agv.id}",
                    category="REPLAN"
                )
                events.append(evt2)
            else:
                task.status = TaskStatus.WAITING
                evt2 = EventLog(
                    id=f"evt_fail_2",
                    timestamp="NOW",
                    level="WARNING",
                    message=f"Task {task.task_id} requeued to WAITING — no other feasible AGV currently available",
                    category="TASK"
                )
                events.append(evt2)

        return commands, events

    def handle_low_battery_risk(
        self,
        agv: AGVModel,
        tasks: Dict[str, TaskModel]
    ) -> Tuple[List[Dict], List[EventLog]]:
        """
        Diverts low-battery AGV to nearest charger.
        If AGV has an assigned task it cannot finish, releases task to WAITING/REASSIGNMENT.
        """
        commands = []
        events = []

        if agv.charging or agv.status in [AGVStatus.CHARGING, AGVStatus.FAILED]:
            return commands, events

        charger_info = self.battery_mgr.find_nearest_charger(agv.current_node)
        if charger_info:
            charger_id, route_data = charger_info
            
            # If AGV has an assigned task and is not carrying material or battery critically low, release task
            if agv.current_task_id and agv.current_task_id in tasks:
                task = tasks[agv.current_task_id]
                if not agv.carrying_material or agv.battery < 15.0:
                    t_id = task.task_id
                    task.status = TaskStatus.WAITING
                    task.assigned_agv_id = None
                    agv.current_task_id = None
                    commands.append({"command": "release_task", "task_id": t_id, "agv_id": agv.id})
                    events.append(EventLog(
                        id=f"evt_bat_rel_{t_id}",
                        timestamp="NOW",
                        level="WARNING",
                        message=f"Task {t_id} released from low-battery AGV {agv.id} -> requeued to WAITING",
                        category="BATTERY"
                    ))

            agv.status = AGVStatus.LOW_BATTERY
            agv.target_charger = charger_id
            agv.current_route = route_data["route"]
            agv.route_index = 0

            commands.append({
                "command": "send_to_charge",
                "agv_id": agv.id,
                "charger_id": charger_id,
                "route": route_data["route"]
            })

            events.append(EventLog(
                id=f"evt_bat_1",
                timestamp="NOW",
                level="WARNING",
                message=f"AGV {agv.id} battery low ({agv.battery:.1f}%) — Diverting to {charger_id}",
                category="BATTERY"
            ))

        return commands, events
