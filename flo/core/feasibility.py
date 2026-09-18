"""
FLO Core Feasibility — Stage 1 Hard Feasibility Filter for AGV-Task matching.
"""

from typing import List, Tuple, Dict, Optional
from flo.core.models import AGVModel, TaskModel, AGVStatus, FeasibilityResult
from flo.core.graph import FactoryGraph
from flo.core.battery import BatteryManager

class FeasibilityChecker:
    def __init__(self, graph: FactoryGraph, battery_mgr: BatteryManager):
        self.graph = graph
        self.battery_mgr = battery_mgr

    def evaluate_agv(
        self,
        agv: AGVModel,
        task: TaskModel,
        allow_reassignment: bool = False
    ) -> Tuple[bool, FeasibilityResult, Optional[Dict], Optional[Dict]]:
        """
        Evaluates Stage 1 Hard Feasibility for a single AGV against a given Task.
        Returns (is_feasible, FeasibilityResult, route_to_pickup, route_to_dest).
        """
        # 1. Status Check
        if agv.status == AGVStatus.FAILED:
            res = FeasibilityResult(
                agv_id=agv.id, feasible=False,
                reason="AGV is in FAILED state",
                required_energy=0.0, available_battery=agv.battery,
                estimated_time=0.0, distance=0.0
            )
            return False, res, None, None

        if not allow_reassignment and agv.status not in [AGVStatus.AVAILABLE, AGVStatus.WAITING]:
            res = FeasibilityResult(
                agv_id=agv.id, feasible=False,
                reason=f"AGV is currently occupied ({agv.status.value})",
                required_energy=0.0, available_battery=agv.battery,
                estimated_time=0.0, distance=0.0
            )
            return False, res, None, None

        # 2. Payload Capacity Check
        if agv.payload_capacity < task.weight:
            res = FeasibilityResult(
                agv_id=agv.id, feasible=False,
                reason=f"Insufficient payload capacity ({agv.payload_capacity}kg < {task.weight}kg task weight)",
                required_energy=0.0, available_battery=agv.battery,
                estimated_time=0.0, distance=0.0
            )
            return False, res, None, None

        # 3. Routing Check
        route_pickup = self.graph.find_route(agv.current_node, task.pickup, consider_congestion=True)
        if not route_pickup:
            res = FeasibilityResult(
                agv_id=agv.id, feasible=False,
                reason=f"No unblocked route available from AGV node ({agv.current_node}) to pickup ({task.pickup})",
                required_energy=0.0, available_battery=agv.battery,
                estimated_time=0.0, distance=0.0
            )
            return False, res, None, None

        route_dest = self.graph.find_route(task.pickup, task.destination, consider_congestion=True)
        if not route_dest:
            res = FeasibilityResult(
                agv_id=agv.id, feasible=False,
                reason=f"No unblocked route available from pickup ({task.pickup}) to destination ({task.destination})",
                required_energy=0.0, available_battery=agv.battery,
                estimated_time=0.0, distance=0.0
            )
            return False, res, None, None

        # 4. Battery Feasibility Check
        bat_feasible, req_energy, bat_reason = self.battery_mgr.is_battery_feasible(
            agv, task, route_pickup, route_dest
        )
        total_dist = route_pickup["distance"] + route_dest["distance"]
        total_time = route_pickup["estimated_travel_time"] + route_dest["estimated_travel_time"]

        if not bat_feasible:
            res = FeasibilityResult(
                agv_id=agv.id, feasible=False,
                reason=bat_reason,
                required_energy=req_energy, available_battery=agv.battery,
                estimated_time=total_time, distance=total_dist
            )
            return False, res, route_pickup, route_dest

        # 5. Deadline Check
        if task.deadline_seconds > 0 and total_time > task.deadline_seconds:
            res = FeasibilityResult(
                agv_id=agv.id, feasible=False,
                reason=f"Impossible deadline ({total_time:.1f}s travel time > {task.deadline_seconds:.1f}s deadline)",
                required_energy=req_energy, available_battery=agv.battery,
                estimated_time=total_time, distance=total_dist
            )
            return False, res, route_pickup, route_dest

        # Passed all Stage 1 Filters
        res = FeasibilityResult(
            agv_id=agv.id, feasible=True,
            reason=f"FEASIBLE (Battery: {agv.battery:.1f}%, Est Time: {total_time:.1f}s)",
            required_energy=req_energy, available_battery=agv.battery,
            estimated_time=total_time, distance=total_dist
        )
        return True, res, route_pickup, route_dest
