"""
FLO Core Optimizer — Master Optimization Engine & Central Decision Coordinator.
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple
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

class FLOOptimizer:
    def __init__(self):
        self.graph = FactoryGraph()
        self.battery_mgr = BatteryManager(self.graph)
        self.assignment_engine = AssignmentEngine(self.graph, self.battery_mgr)
        self.congestion_mgr = CongestionManager(self.graph)
        self.replanner = Replanner(self.graph, self.battery_mgr, self.assignment_engine)
        self.baseline_opt = BaselineOptimizer(self.graph)
        self.metrics_collector = MetricsCollector()

        self.agvs: Dict[str, AGVModel] = self._create_default_agvs()
        self.tasks: Dict[str, TaskModel] = self._create_default_tasks()
        self.events: List[EventLog] = []
        self.decisions: List[DecisionExplanation] = []
        self.last_decision: Optional[DecisionExplanation] = None
        self.pending_commands: List[Dict] = []

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
            ("T005", "ASSY", "DISPATCH", TaskPriority.URGENT, 35.0, 180.0),
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
                agv.battery = a_data.get("battery", agv.battery)
                agv.status = AGVStatus(a_data.get("status", agv.status.value))
                agv.carrying_material = a_data.get("carrying_material", agv.carrying_material)
                agv.charging = a_data.get("charging", agv.charging)

        for t_data in task_list:
            t_id = t_data["task_id"]
            if t_id not in self.tasks:
                self.tasks[t_id] = TaskModel(**t_data)
            else:
                task = self.tasks[t_id]
                task.status = TaskStatus(t_data.get("status", task.status.value))
                task.assigned_agv_id = t_data.get("assigned_agv_id", task.assigned_agv_id)

        # Update edge congestion
        self.congestion_mgr.update_live_congestion(list(self.agvs.values()))
        
        # Check active AGVs for low battery risk
        for agv in self.agvs.values():
            if self.battery_mgr.check_active_agv_battery_risk(agv) and agv.status not in [AGVStatus.LOW_BATTERY, AGVStatus.CHARGING]:
                self.replanner.handle_low_battery_risk(agv, self.tasks)
                self.add_event("WARNING", f"AGV {agv.id} low battery detected ({agv.battery:.1f}%) — initiating charging divert", "BATTERY")
                self.metrics_collector.record_battery_intervention()

    def process_optimization_cycle(self) -> List[Dict]:
        """
        Main Optimization Loop:
        1. Evaluates pending tasks.
        2. Assigns best feasible AGV using Stage 1 & Stage 2 optimization.
        3. Returns command list to execute in Factory Simulator.
        """
        commands = list(self.pending_commands)
        self.pending_commands.clear()

        # Find pending tasks
        pending_tasks = [t for t in self.tasks.values() if t.status == TaskStatus.WAITING]
        # Sort pending by priority (URGENT > HIGH > NORMAL > LOW)
        priority_order = {TaskPriority.URGENT: 0, TaskPriority.HIGH: 1, TaskPriority.NORMAL: 2, TaskPriority.LOW: 3}
        pending_tasks.sort(key=lambda x: priority_order.get(x.priority, 99))

        self.metrics_collector.update_pending_count(len(pending_tasks))

        agv_list = list(self.agvs.values())

        for task in pending_tasks:
            best_agv, explanation, route_data = self.assignment_engine.assign_best_agv(task, agv_list)

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
            else:
                self.add_event(
                    "WARNING",
                    f"Task {task.task_id} [{task.priority.value}] could not be assigned: No feasible AGV available",
                    "TASK"
                )

        return commands

    def trigger_scenario_add_congestion(self, src: str = "J3", dst: str = "J2") -> List[Dict]:
        """Injects heavy congestion on central corridor J3-J2 and reroutes affected AGVs."""
        self.congestion_mgr.inject_congestion_scenario(src, dst, level=3.5)
        self.add_event("WARNING", f"SCENARIO: Congestion spike injected on Corridor {src}-{dst}", "CONGESTION")
        self.metrics_collector.record_reroute()
        
        cmds, evts = self.replanner.handle_route_change_event(list(self.agvs.values()), self.tasks)
        for e in evts:
            self.events.insert(0, e)
        self.pending_commands.extend(cmds)
        return cmds

    def trigger_scenario_remove_congestion(self, src: str = "J3", dst: str = "J2") -> List[Dict]:
        """Clears congestion on central corridor J3-J2."""
        self.congestion_mgr.clear_congestion_scenario(src, dst)
        self.add_event("INFO", f"SCENARIO: Congestion cleared on Corridor {src}-{dst}", "CONGESTION")
        cmds, evts = self.replanner.handle_route_change_event(list(self.agvs.values()), self.tasks)
        for e in evts:
            self.events.insert(0, e)
        self.pending_commands.extend(cmds)
        return cmds

    def trigger_scenario_block_route(self, src: str = "J3", dst: str = "J2") -> List[Dict]:
        """Blocks corridor J3-J2 completely and forces dynamic rerouting."""
        self.congestion_mgr.set_route_blocked(src, dst, True)
        self.add_event("ERROR", f"SCENARIO: Corridor {src}-{dst} IS BLOCKED!", "CONGESTION")
        self.metrics_collector.record_reroute()

        cmds, evts = self.replanner.handle_route_change_event(list(self.agvs.values()), self.tasks)
        for e in evts:
            self.events.insert(0, e)
        self.pending_commands.extend(cmds)
        return cmds

    def trigger_scenario_unblock_route(self, src: str = "J3", dst: str = "J2") -> List[Dict]:
        """Unblocks corridor J3-J2."""
        self.congestion_mgr.set_route_blocked(src, dst, False)
        self.add_event("INFO", f"SCENARIO: Corridor {src}-{dst} UNBLOCKED", "CONGESTION")
        cmds, evts = self.replanner.handle_route_change_event(list(self.agvs.values()), self.tasks)
        for e in evts:
            self.events.insert(0, e)
        self.pending_commands.extend(cmds)
        return cmds

    def trigger_scenario_low_battery_test(self, agv_id: str = "AGV01") -> List[Dict]:
        """Drains battery of specified AGV to 12% to demonstrate feasibility rejection & charging divert."""
        if agv_id in self.agvs:
            agv = self.agvs[agv_id]
            agv.battery = 12.0
            self.add_event("WARNING", f"SCENARIO: AGV {agv_id} battery artificially dropped to 12.0%", "BATTERY")

            # Trigger charger divert if active
            cmds, evts = self.replanner.handle_low_battery_risk(agv, self.tasks)
            cmds.insert(0, {"command": "set_battery", "agv_id": agv_id, "battery": 12.0})
            for e in evts:
                self.events.insert(0, e)
            self.pending_commands.extend(cmds)
            return cmds
        return []

    def trigger_scenario_fail_agv(self, agv_id: str = "AGV01") -> List[Dict]:
        """Simulates complete breakdown of specified AGV and requeues/reassigns active task."""
        cmds, evts = self.replanner.handle_agv_failure_event(agv_id, list(self.agvs.values()), self.tasks)
        cmds.insert(0, {"command": "set_status", "agv_id": agv_id, "status": "FAILED"})
        for e in evts:
            self.events.insert(0, e)
        self.pending_commands.extend(cmds)
        return cmds

    def create_new_task(
        self,
        pickup: str,
        destination: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        weight: float = 10.0,
        deadline_seconds: float = 300.0
    ) -> TaskModel:
        """Creates a new runtime task and triggers an immediate optimization cycle."""
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
        self.add_event("INFO", f"New Task Created: {task_id} ({pickup} -> {destination}, [{priority.value}])", "TASK")

        # Run optimization immediately for new task
        self.process_optimization_cycle()
        return task
