"""
FLO Core Coordination — Priority Spatial-Temporal Zone Interlocking & Collision Prevention Engine.
Coordinates multi-AGV movement at junctions and narrow corridors to prevent deadlocks and overlays.
"""

from typing import Dict, List, Optional, Tuple
from flo.core.models import AGVModel, TaskModel, AGVStatus, TaskPriority, EventLog

class ZoneReservation:
    def __init__(self, node_id: str, agv_id: str, priority_val: int, eta: float):
        self.node_id = node_id
        self.agv_id = agv_id
        self.priority_val = priority_val
        self.eta = eta

class FleetCoordinationEngine:
    def __init__(self):
        # Active node reservations: node_id -> ZoneReservation
        self.active_reservations: Dict[str, ZoneReservation] = {}
        # AGVs currently yielding at approach nodes: agv_id -> waiting_at_node
        self.yielding_agvs: Dict[str, str] = {}

    def evaluate_fleet_coordination(
        self,
        agvs: List[AGVModel],
        tasks: Dict[str, TaskModel]
    ) -> Tuple[List[Dict], List[EventLog]]:
        """
        Evaluates Spatial-Temporal Zone Interlocking for all moving AGVs.
        Detects junction conflicts and assigns Right-of-Way based on Task Priority and ETA.
        """
        commands = []
        events = []

        # 1. Clear expired reservations
        self.active_reservations.clear()

        # Priority values for ranking right-of-way
        prio_ranks = {TaskPriority.URGENT: 4, TaskPriority.HIGH: 3, TaskPriority.NORMAL: 2, TaskPriority.LOW: 1}

        # 2. Build forward reservations for next 2 waypoint nodes for each moving AGV
        for agv in agvs:
            if agv.status == AGVStatus.FAILED:
                continue

            if agv.current_route and agv.route_index < len(agv.current_route) - 1:
                # Next node AGV is entering
                next_node = agv.current_route[agv.route_index + 1]
                
                # Determine task priority
                prio_val = 2
                if agv.current_task_id and agv.current_task_id in tasks:
                    prio_val = prio_ranks.get(tasks[agv.current_task_id].priority, 2)

                eta = agv.route_index * 2.0  # Estimated ETA to node

                if next_node in self.active_reservations:
                    existing_res = self.active_reservations[next_node]
                    
                    # CONFLICT DETECTED at next_node!
                    if existing_res.agv_id != agv.id:
                        # Compare Right-of-Way: Higher priority wins; if equal, earlier ETA wins
                        if (prio_val < existing_res.priority_val) or (prio_val == existing_res.priority_val and eta > existing_res.eta):
                            # Current AGV must YIELD to existing_res.agv_id
                            if agv.id not in self.yielding_agvs:
                                self.yielding_agvs[agv.id] = agv.current_node
                                events.append(EventLog(
                                    id=f"evt_coord_{len(events)+1}",
                                    timestamp="NOW",
                                    level="WARNING",
                                    message=f"COORDINATION: {agv.id} yielding at {agv.current_node} — Granting Junction {next_node} Right-of-Way to higher-priority {existing_res.agv_id}",
                                    category="REPLAN"
                                ))
                                commands.append({
                                    "command": "hold_agv",
                                    "agv_id": agv.id,
                                    "reason": f"Yielding junction {next_node} to {existing_res.agv_id}"
                                })
                        else:
                            # Existing AGV must YIELD to current AGV
                            yield_agv_id = existing_res.agv_id
                            if yield_agv_id not in self.yielding_agvs:
                                self.yielding_agvs[yield_agv_id] = next_node
                                events.append(EventLog(
                                    id=f"evt_coord_{len(events)+1}",
                                    timestamp="NOW",
                                    level="WARNING",
                                    message=f"COORDINATION: {yield_agv_id} yielding at junction {next_node} — Granting Right-of-Way to {agv.id}",
                                    category="REPLAN"
                                ))
                                commands.append({
                                    "command": "hold_agv",
                                    "agv_id": yield_agv_id,
                                    "reason": f"Yielding junction {next_node} to {agv.id}"
                                })
                                # Replace reservation
                                self.active_reservations[next_node] = ZoneReservation(next_node, agv.id, prio_val, eta)
                else:
                    # Grant reservation token to AGV
                    self.active_reservations[next_node] = ZoneReservation(next_node, agv.id, prio_val, eta)
                    if agv.id in self.yielding_agvs:
                        del self.yielding_agvs[agv.id]

        return commands, events
