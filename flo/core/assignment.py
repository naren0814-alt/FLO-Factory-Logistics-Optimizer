"""
FLO Core Assignment — Stage 2 Multi-Factor Score Optimization & Decision Reasoning.
"""

from datetime import datetime
from typing import List, Dict, Optional, Tuple
from flo.core.models import (
    AGVModel, TaskModel, TaskPriority, DecisionExplanation,
    FeasibilityResult
)
from flo.core.graph import FactoryGraph
from flo.core.battery import BatteryManager
from flo.core.feasibility import FeasibilityChecker
from config.settings import (
    TIME_WEIGHT, DISTANCE_WEIGHT, CONGESTION_WEIGHT,
    ENERGY_WEIGHT, PRIORITY_WEIGHT
)

class AssignmentEngine:
    def __init__(self, graph: FactoryGraph, battery_mgr: BatteryManager):
        self.graph = graph
        self.battery_mgr = battery_mgr
        self.feasibility_checker = FeasibilityChecker(graph, battery_mgr)

    def calculate_score(
        self,
        agv: AGVModel,
        task: TaskModel,
        route_pickup: Dict,
        route_dest: Dict,
        feasibility: FeasibilityResult
    ) -> float:
        """
        Calculates Stage 2 Multi-Factor Score for a feasible AGV.
        Lower score = more optimal candidate.
        """
        total_time = route_pickup["estimated_travel_time"] + route_dest["estimated_travel_time"]
        total_dist = route_pickup["distance"] + route_dest["distance"]
        total_congestion = route_pickup.get("congestion_cost", 0.0) + route_dest.get("congestion_cost", 0.0)
        req_energy = feasibility.required_energy

        priority_bonus = 0.0
        if task.priority == TaskPriority.LOW:
            priority_bonus = 0.0
        elif task.priority == TaskPriority.NORMAL:
            priority_bonus = 10.0
        elif task.priority == TaskPriority.HIGH:
            priority_bonus = 35.0
        elif task.priority == TaskPriority.URGENT:
            priority_bonus = 80.0

        score = (
            (TIME_WEIGHT * total_time) +
            (DISTANCE_WEIGHT * total_dist) +
            (CONGESTION_WEIGHT * total_congestion) +
            (ENERGY_WEIGHT * req_energy) -
            (PRIORITY_WEIGHT * priority_bonus)
        )
        return score

    def assign_best_agv(
        self,
        task: TaskModel,
        agvs: List[AGVModel],
        allow_reassignment: bool = False
    ) -> Tuple[Optional[AGVModel], DecisionExplanation, Optional[Dict]]:
        """
        Evaluates all AGVs through Stage 1 & Stage 2 optimization.
        Returns (best_agv, decision_explanation, combined_route_data).
        """
        evaluations: List[FeasibilityResult] = []
        best_agv: Optional[AGVModel] = None
        best_score = float('inf')
        best_route_data: Optional[Dict] = None

        for agv in agvs:
            is_feasible, result, route_pickup, route_dest = self.feasibility_checker.evaluate_agv(
                agv, task, allow_reassignment=allow_reassignment
            )
            evaluations.append(result)

            if is_feasible and route_pickup and route_dest:
                score = self.calculate_score(agv, task, route_pickup, route_dest, result)
                if score < best_score:
                    best_score = score
                    best_agv = agv

                    # Combine route: agv.current_node -> pickup -> destination
                    combined_nodes = route_pickup["route"][:-1] + route_dest["route"]
                    best_route_data = {
                        "route": combined_nodes,
                        "distance": route_pickup["distance"] + route_dest["distance"],
                        "estimated_travel_time": route_pickup["estimated_travel_time"] + route_dest["estimated_travel_time"],
                        "estimated_energy": result.required_energy,
                        "pickup_node": task.pickup,
                        "dest_node": task.destination
                    }

        # Build Decision Explanation
        timestamp_str = datetime.now().strftime("%H:%M:%S")
        if best_agv and best_route_data:
            reasons = [f"Selected {best_agv.id} (Score: {best_score:.1f})"]
            for ev in evaluations:
                if ev.agv_id != best_agv.id:
                    reasons.append(f"{ev.agv_id} rejected: {ev.reason}")

            explanation = DecisionExplanation(
                task_id=task.task_id,
                assigned_agv_id=best_agv.id,
                timestamp=timestamp_str,
                evaluations=evaluations,
                reasoning=" | ".join(reasons),
                selected_route=best_route_data["route"]
            )
            return best_agv, explanation, best_route_data
        else:
            reasons = [f"{ev.agv_id} rejected: {ev.reason}" for ev in evaluations]
            explanation = DecisionExplanation(
                task_id=task.task_id,
                assigned_agv_id=None,
                timestamp=timestamp_str,
                evaluations=evaluations,
                reasoning="No feasible AGV found. " + " | ".join(reasons),
                selected_route=[]
            )
            return None, explanation, None
