"""
FLO Core Baseline — Naive Baseline Algorithm (Nearest Available AGV + Shortest Distance Route).
"""

from typing import List, Dict, Optional, Tuple
from flo.core.models import AGVModel, TaskModel, AGVStatus
from flo.core.graph import FactoryGraph

class BaselineOptimizer:
    def __init__(self, graph: FactoryGraph):
        self.graph = graph

    def assign_task_baseline(
        self,
        task: TaskModel,
        agvs: List[AGVModel]
    ) -> Tuple[Optional[AGVModel], Optional[Dict]]:
        """
        Naive Baseline Strategy:
        Picks nearest available AGV using unweighted shortest distance, ignoring battery feasibility and congestion.
        """
        best_agv = None
        min_dist = float('inf')
        best_route_data = None

        for agv in agvs:
            if agv.status in [AGVStatus.AVAILABLE, AGVStatus.WAITING]:
                route_pickup = self.graph.find_route(agv.current_node, task.pickup, consider_congestion=False)
                route_dest = self.graph.find_route(task.pickup, task.destination, consider_congestion=False)

                if route_pickup and route_dest:
                    tot_dist = route_pickup["distance"] + route_dest["distance"]
                    if tot_dist < min_dist:
                        min_dist = tot_dist
                        best_agv = agv
                        best_route_data = {
                            "route": route_pickup["route"][:-1] + route_dest["route"],
                            "distance": tot_dist,
                            "estimated_travel_time": tot_dist / 15.0,
                            "estimated_energy": tot_dist * 0.025
                        }

        return best_agv, best_route_data
