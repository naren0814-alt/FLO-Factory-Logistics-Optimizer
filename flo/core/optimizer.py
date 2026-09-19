"""
FLO Core Optimizer — Master Optimization Engine & Central Decision Coordinator.
"""

from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from flo.core.models import (
    AGVModel, TaskModel, NodeModel, EdgeModel,
    AGVStatus, TaskStatus, TaskPriority, DecisionExplanation,
    EventLog, SystemMetrics, BaselineComparison
)
from flo.core.graph import FactoryGraph
from flo.core.battery import BatteryManager
from flo.core.feasibility import FeasibilityChecker
from flo.core.assignment import AssignmentEngine
from flo.core.congestion import CongestionManager
from flo.core.replanner import Replanner
from flo.core.baseline import BaselineOptimizer
from flo.core.metrics import MetricsCollector
from flo.core.coordination import FleetCoordinationEngine

class FLOOptimizer:
    def __init__(self):
        self.graph = FactoryGraph()
        self.battery_mgr = BatteryManager(self.graph)
        self.assignment_engine = AssignmentEngine(self.graph, self.battery_mgr)
        self.congestion_mgr = CongestionManager(self.graph)
        self.replanner = Replanner(self.graph, self.battery_mgr, self.assignment_engine)
        self.coordination_engine = FleetCoordinationEngine()
        self.baseline_opt = BaselineOptimizer(self.graph)
        self.metrics_collector = MetricsCollector()

        self.agvs: Dict[str, AGVModel] = self._create_default_agvs()
        self.tasks: Dict[str, TaskModel] = self._create_default_tasks()
        self.events: List[EventLog] = []
        self.decisions: List[DecisionExplanation] = []
        self.last_decision: Optional[DecisionExplanation] = None
        self.pending_commands: List[Dict] = []
        self.warned_low_battery_agvs: Set[str] = set()

    def _create_default_agvs(self) -> Dict[str, AGVModel]:
        agv_data = [
            ("AGV01", "AGV 1 (Heavy Duty)", "WAREHOUSE", 100.0, 100.0, 88.0, 60.0, 1.6),
            ("AGV02", "AGV 2 (Standard)", "J1", 250.0, 100.0, 75.0, 45.0, 1.5),
            ("AGV03", "AGV 3 (Express)", "M1", 250.0, 250.0, 92.0, 50.0, 1.7),
            ("AGV04", "AGV 4 (Standard)", "CHARGER1", 100.0, 380.0, 18.0, 40.0, 1.4),
            ("AGV05", "AGV 5 (Heavy Duty)", "DISPATCH", 700.0, 380.0, 80.0, 55.0, 1.5),
        ]
        agvs = {}
        for aid, name, node, x, y, bat, cap, spd in agv_data:
            agvs[aid] = AGVModel(
                id=aid, name=name, current_node=node,
                x=x, y=y, battery=bat, payload_capacity=cap,
                speed=spd, status=AGVStatus.AVAILABLE
            )
        return agvs

    def _create_default_tasks(self) -> Dict[str, TaskModel]:
        raw_tasks = [
            ("T001", "WAREHOUSE", "M1", TaskPriority.NORMAL, 15.0, 300.0),
            ("T002", "WAREHOUSE", "M2", TaskPriority.NORMAL, 20.0, 300.0),
            ("T003", "M1", "ASSY", TaskPriority.HIGH, 25.0, 240.0),
            ("T004", "M2", "ASSY", TaskPriority.NORMAL, 20.0, 300.0),
            ("T005", "ASSY", "DISPATCH", TaskPriority.NORMAL, 35.0, 180.0),
        ]
        tasks = {}
        for tid, pickup, dest, prio, weight, deadline in raw_tasks:
            tasks[tid] = TaskModel(
                task_id=tid, pickup=pickup, destination=dest,
                priority=prio, weight=weight, deadline_seconds=deadline,
                status=TaskStatus.WAITING
            )
        return tasks

    def add_event(self, level: str, message: str, category: str):
        evt = EventLog(
            id=f"evt_{len(self.events)+1}",
            timestamp=datetime.now().strftime("%H:%M:%S"),
            level=level,
            message=message,
            category=category
        )
        self.events.insert(0, evt)  # Newest first
        if len(self.events) > 50:
            self.events.pop()

    def recover_task(self, task: TaskModel, reason: str = "AGV Failure/Stale State"):
        """Centralized task recovery mechanism to release stranded assignments."""
        old_agv_id = task.assigned_agv_id
        task.status = TaskStatus.WAITING
        task.assigned_agv_id = None

        if old_agv_id and old_agv_id in self.agvs:
            agv = self.agvs[old_agv_id]
            if agv.current_task_id == task.task_id:
                agv.current_task_id = None
                agv.current_route = []
                agv.route_index = 0
                if agv.status not in [AGVStatus.FAILED, AGVStatus.LOW_BATTERY, AGVStatus.CHARGING]:
                    agv.status = AGVStatus.AVAILABLE

        cmd = {"command": "release_task", "task_id": task.task_id, "agv_id": old_agv_id}
        if cmd not in self.pending_commands:
            self.pending_commands.append(cmd)

        self.add_event(
            "WARNING",
            f"RECOVERY: Task {task.task_id} released from {old_agv_id or 'unknown'} -> Requeued to WAITING ({reason})",
            "TASK"
        )

    def run_safety_audit(self):
        """
        Lightweight two-way consistency check:
        1. Ensures no task remains ASSIGNED to a FAILED, low-battery, or mismatched AGV.
        2. Ensures no FAILED AGV owns an active task.
        """
        # Audit Tasks
        for task in list(self.tasks.values()):
            if task.status in [TaskStatus.ASSIGNED, TaskStatus.MOVING_TO_PICKUP, TaskStatus.IN_TRANSIT]:
                if not task.assigned_agv_id or task.assigned_agv_id not in self.agvs:
                    self.recover_task(task, "Assigned AGV missing")
                else:
                    agv = self.agvs[task.assigned_agv_id]
                    if agv.status == AGVStatus.FAILED:
                        self.recover_task(task, "Assigned AGV is FAILED")
                    elif agv.status in [AGVStatus.LOW_BATTERY, AGVStatus.CHARGING] and not agv.carrying_material:
                        self.recover_task(task, "AGV diverting to charger without material")
                    elif agv.current_task_id and agv.current_task_id != task.task_id:
                        self.recover_task(task, f"AGV current_task_id mismatch ({agv.current_task_id} != {task.task_id})")

        # Audit AGVs
        for agv in list(self.agvs.values()):
            if agv.status == AGVStatus.FAILED and agv.current_task_id:
                t_id = agv.current_task_id
                agv.current_task_id = None
                agv.current_route = []
                agv.route_index = 0
                if t_id in self.tasks:
                    self.recover_task(self.tasks[t_id], "AGV in FAILED status")

    def sync_factory_state(self, agv_list: List[Dict], task_list: List[Dict], edge_list: Optional[List[Dict]] = None):
        """Synchronizes live state from Factory Simulator into FLO Core Engine."""
        for a_data in agv_list:
            agv_id = a_data["id"]
            if agv_id not in self.agvs:
                self.agvs[agv_id] = AGVModel(**a_data)
            else:
                agv = self.agvs[agv_id]
                agv.current_node = a_data.get("current_node", agv.current_node)
                agv.x = a_data.get("x", agv.x)
                agv.y = a_data.get("y", agv.y)
                new_status = AGVStatus(a_data.get("status", agv.status.value))
                if agv.status == AGVStatus.FAILED and new_status != AGVStatus.FAILED:
                    pass  # Retain FAILED status in Core until explicitly recovered
                else:
                    agv.status = new_status

                agv.carrying_material = a_data.get("carrying_material", agv.carrying_material)
                agv.charging = a_data.get("charging", agv.charging)

                # Reset warned state when AGV finishes charging
                if agv.battery >= 85.0 and agv_id in self.warned_low_battery_agvs:
                    self.warned_low_battery_agvs.remove(agv_id)

        for t_data in task_list:
            t_id = t_data["task_id"]
            if t_id not in self.tasks:
                self.tasks[t_id] = TaskModel(**t_data)
            else:
                task = self.tasks[t_id]
                prev_status = task.status
                sim_status = TaskStatus(t_data.get("status", task.status.value))
                sim_agv_id = t_data.get("assigned_agv_id", task.assigned_agv_id)

                # Prevent simulator from overwriting a recovered WAITING task back to FAILED AGV
                if sim_agv_id and sim_agv_id in self.agvs and self.agvs[sim_agv_id].status == AGVStatus.FAILED:
                    task.status = TaskStatus.WAITING
                    task.assigned_agv_id = None
                else:
                    task.status = sim_status
                    task.assigned_agv_id = sim_agv_id

                # Record task completion once
                if task.status == TaskStatus.COMPLETED and task.actual_completion_time is None:
                    task.actual_completion_time = datetime.now().timestamp()
                    print(f"[CORE] Completion recorded for {task.task_id}")
                    if task.assigned_agv_id:
                        print(f"[CORE] Reservation released for AGV {task.assigned_agv_id}")
                        if task.assigned_agv_id in self.agvs:
                            c_agv = self.agvs[task.assigned_agv_id]
                            if c_agv.current_task_id == task.task_id:
                                c_agv.current_task_id = None
                                c_agv.status = AGVStatus.AVAILABLE
                                c_agv.current_route = []
                                c_agv.route_index = 0

                    self.metrics_collector.record_task_completed(
                        delivery_time=task.actual_completion_time - task.creation_time if task.creation_time > 0 else 45.0,
                        distance=300.0,
                        energy=5.0
                    )
                    self.add_event("SUCCESS", f"TASK COMPLETED: {task.task_id} ({task.pickup} -> {task.destination})", "TASK")

        # Run Safety Audit to catch any state discrepancies
        self.run_safety_audit()

        # Update edge congestion
        self.congestion_mgr.update_live_congestion(list(self.agvs.values()))
        
        # Check active AGVs for low battery risk ONCE per transition
        for agv in self.agvs.values():
            if self.battery_mgr.check_active_agv_battery_risk(agv) and agv.status not in [AGVStatus.LOW_BATTERY, AGVStatus.CHARGING]:
                if agv.id not in self.warned_low_battery_agvs:
                    self.warned_low_battery_agvs.add(agv.id)
                    cmds, evts = self.replanner.handle_low_battery_risk(agv, self.tasks)
                    self.pending_commands.extend(cmds)
                    self.add_event("WARNING", f"AGV {agv.id} low battery detected ({agv.battery:.1f}%) — initiating charging divert", "BATTERY")
                    self.metrics_collector.record_battery_intervention()

            # Auto-charge idle AVAILABLE AGVs with low battery (< 40%)
            elif agv.status == AGVStatus.AVAILABLE and agv.battery < 40.0 and not agv.charging:
                if agv.id not in self.warned_low_battery_agvs:
                    self.warned_low_battery_agvs.add(agv.id)
                    cmds, evts = self.replanner.handle_low_battery_risk(agv, self.tasks)
                    self.pending_commands.extend(cmds)
                    self.add_event("INFO", f"AGV {agv.id} idle with medium-low battery ({agv.battery:.1f}%) — sending to recharge", "BATTERY")

    def process_optimization_cycle(self) -> List[Dict]:
        """
        Main Optimization Loop:
        1. Runs safety audit for consistency.
        2. Evaluates pending tasks.
        3. Assigns best feasible AGV using Stage 1 & Stage 2 optimization.
        4. Evaluates multi-AGV spatial-temporal zone coordination.
        5. Returns command list to execute in Factory Simulator.
        """
        commands = list(self.pending_commands)
        self.pending_commands.clear()

        # Run Safety Audit to clean up any orphaned or stale assignments
        self.run_safety_audit()

        # Find pending tasks (WAITING or REASSIGNING)
        pending_tasks = [t for t in self.tasks.values() if t.status in [TaskStatus.WAITING, TaskStatus.REASSIGNING]]
        priority_order = {TaskPriority.URGENT: 0, TaskPriority.HIGH: 1, TaskPriority.NORMAL: 2, TaskPriority.LOW: 3}
        pending_tasks.sort(key=lambda x: (priority_order.get(x.priority, 99), x.creation_time))

        self.metrics_collector.update_pending_count(len(pending_tasks))

        for task in pending_tasks:
            # Refresh live list of available/operational AGVs
            operational_agvs = [a for a in self.agvs.values() if a.status != AGVStatus.FAILED]
            best_agv, explanation, route_data = self.assignment_engine.assign_best_agv(task, operational_agvs)

            self.last_decision = explanation
            self.decisions.insert(0, explanation)
            if len(self.decisions) > 20:
                self.decisions.pop()

            if best_agv and route_data:
                # Update task state
                task.status = TaskStatus.ASSIGNED
                task.assigned_agv_id = best_agv.id
                task.estimated_completion_time = route_data["estimated_travel_time"]

                # Update AGV state
                best_agv.current_task_id = task.task_id
                best_agv.current_route = route_data["route"]
                best_agv.route_index = 0
                best_agv.status = AGVStatus.MOVING_TO_PICKUP
                best_agv.target_charger = None
                best_agv.charging = False

                cmd = {
                    "command": "assign_task",
                    "agv_id": best_agv.id,
                    "task_id": task.task_id,
                    "route": route_data["route"],
                    "pickup": task.pickup,
                    "destination": task.destination
                }
                commands.append(cmd)

                self.add_event(
                    "SUCCESS",
                    f"Assigned Task {task.task_id} [{task.priority.value}] to AGV {best_agv.id} (Est. Time: {route_data['estimated_travel_time']:.1f}s)",
                    "TASK"
                )

        # Run Multi-AGV Fleet Spatial-Temporal Zone Interlocking & Coordination
        coord_cmds, coord_evts = self.coordination_engine.evaluate_fleet_coordination(
            list(self.agvs.values()), self.tasks
        )
        commands.extend(coord_cmds)
        for e in coord_evts:
            self.events.insert(0, e)

        return commands

    def trigger_scenario_add_congestion(self, src: str = "J3", dst: str = "J2") -> List[Dict]:
        """Injects heavy congestion on specified corridor and reroutes affected AGVs."""
        self.congestion_mgr.inject_congestion_scenario(src, dst, level=3.5)
        self.add_event("WARNING", f"SCENARIO: Congestion spike injected on Corridor {src} ↔ {dst}", "CONGESTION")
        self.metrics_collector.record_reroute()
        
        cmds, evts = self.replanner.handle_route_change_event(list(self.agvs.values()), self.tasks)
        for e in evts:
            self.events.insert(0, e)
        self.pending_commands.extend(cmds)
        opt_cmds = self.process_optimization_cycle()
        return opt_cmds

    def trigger_scenario_remove_congestion(self, src: str = "J3", dst: str = "J2") -> List[Dict]:
        """Clears congestion on specified corridor."""
        self.congestion_mgr.clear_congestion_scenario(src, dst)
        self.add_event("INFO", f"SCENARIO: Congestion cleared on Corridor {src} ↔ {dst}", "CONGESTION")
        cmds, evts = self.replanner.handle_route_change_event(list(self.agvs.values()), self.tasks)
        for e in evts:
            self.events.insert(0, e)
        self.pending_commands.extend(cmds)
        opt_cmds = self.process_optimization_cycle()
        return opt_cmds

    def trigger_scenario_block_route(self, src: str = "J3", dst: str = "J2") -> List[Dict]:
        """Blocks specified corridor completely and forces dynamic rerouting."""
        self.congestion_mgr.set_route_blocked(src, dst, True)
        self.add_event("ERROR", f"SCENARIO: Corridor {src} ↔ {dst} IS BLOCKED!", "CONGESTION")
        self.metrics_collector.record_reroute()

        cmds, evts = self.replanner.handle_route_change_event(list(self.agvs.values()), self.tasks)
        for e in evts:
            self.events.insert(0, e)
        self.pending_commands.extend(cmds)
        opt_cmds = self.process_optimization_cycle()
        return opt_cmds

    def trigger_scenario_unblock_route(self, src: str = "J3", dst: str = "J2") -> List[Dict]:
        """Unblocks specified corridor."""
        self.congestion_mgr.set_route_blocked(src, dst, False)
        self.add_event("INFO", f"SCENARIO: Corridor {src} ↔ {dst} UNBLOCKED", "CONGESTION")
        cmds, evts = self.replanner.handle_route_change_event(list(self.agvs.values()), self.tasks)
        for e in evts:
            self.events.insert(0, e)
        self.pending_commands.extend(cmds)
        opt_cmds = self.process_optimization_cycle()
        return opt_cmds

    def trigger_scenario_low_battery_test(self, agv_id: str = "AGV01", battery_val: float = 12.0) -> List[Dict]:
        """Drains battery of specified AGV to target % to demonstrate feasibility rejection & charging divert."""
        if agv_id in self.agvs:
            agv = self.agvs[agv_id]
            agv.battery = battery_val
            if agv_id in self.warned_low_battery_agvs:
                self.warned_low_battery_agvs.remove(agv_id)

            self.add_event("WARNING", f"SCENARIO: AGV {agv_id} battery artificially dropped to {battery_val:.1f}%", "BATTERY")

            # Trigger charger divert if active
            cmds, evts = self.replanner.handle_low_battery_risk(agv, self.tasks)
            cmds.insert(0, {"command": "set_battery", "agv_id": agv_id, "battery": battery_val})
            for e in evts:
                self.events.insert(0, e)
            self.pending_commands.extend(cmds)
            opt_cmds = self.process_optimization_cycle()
            return opt_cmds
        return []

    def trigger_scenario_fail_agv(self, agv_id: str = "AGV01") -> List[Dict]:
        """Simulates complete breakdown of specified AGV and requeues/reassigns active task."""
        cmds, evts = self.replanner.handle_agv_failure_event(agv_id, list(self.agvs.values()), self.tasks)
        cmds.insert(0, {"command": "set_status", "agv_id": agv_id, "status": "FAILED"})
        for e in evts:
            self.events.insert(0, e)
        self.pending_commands.extend(cmds)
        opt_cmds = self.process_optimization_cycle()
        return opt_cmds

    def trigger_scenario_recover_agv(self, agv_id: str = "AGV01") -> List[Dict]:
        """Repairs a failed AGV and restores it to operational AVAILABLE state."""
        if agv_id in self.agvs:
            agv = self.agvs[agv_id]
            agv.status = AGVStatus.AVAILABLE
            agv.battery = max(agv.battery, 80.0)
            cmd = {"command": "set_status", "agv_id": agv_id, "status": "AVAILABLE"}
            self.add_event("SUCCESS", f"RECOVERY: AGV {agv_id} repaired and restored to AVAILABLE fleet", "TASK")
            self.pending_commands.append(cmd)
            opt_cmds = self.process_optimization_cycle()
            return opt_cmds
        return []

    def create_new_task(
        self,
        pickup: str,
        destination: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        weight: float = 10.0,
        deadline_seconds: float = 300.0
    ) -> TaskModel:
        """Creates a new runtime task, enqueues it, and triggers optimization."""
        task_id = f"T{len(self.tasks)+1:03d}"
        task = TaskModel(
            task_id=task_id,
            pickup=pickup,
            destination=destination,
            priority=priority,
            weight=weight,
            deadline_seconds=deadline_seconds,
            creation_time=datetime.now().timestamp(),
            status=TaskStatus.WAITING
        )
        self.tasks[task_id] = task

        print(f"[CORE] Task created: {task_id}")
        print(f"[CORE] Task queued: {task_id}")

        self.add_event("INFO", f"New Task Created: {task_id} ({pickup} → {destination}, [{priority.value}])", "TASK")

        # Push create_task command so Factory Simulator registers it immediately
        self.pending_commands.append({"command": "create_task", "task": task.model_dump()})

        # Run optimization and collect assignment commands
        cmds = self.process_optimization_cycle()
        self.pending_commands.extend(cmds)

        return task
