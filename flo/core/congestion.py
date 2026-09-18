"""
FLO Core Congestion — Edge congestion tracking & scenario modifier.
"""

from typing import Dict, List
from flo.core.graph import FactoryGraph
from flo.core.models import AGVModel

class CongestionManager:
    def __init__(self, graph: FactoryGraph):
        self.graph = graph

    def update_live_congestion(self, agvs: List[AGVModel]):
        """
        Recalculates edge occupancy based on current positions of active AGVs.
        """
        # Reset current edge occupancy
        occupancy_map: Dict[str, int] = {}

        for agv in agvs:
            if len(agv.current_route) > 1 and agv.route_index < len(agv.current_route) - 1:
                u = agv.current_route[agv.route_index]
                v = agv.current_route[agv.route_index + 1]
                edge_id_1 = f"{u}_{v}"
                edge_id_2 = f"{v}_{u}"
                occupancy_map[edge_id_1] = occupancy_map.get(edge_id_1, 0) + 1
                occupancy_map[edge_id_2] = occupancy_map.get(edge_id_2, 0) + 1

        for edge_id, edge in self.graph.edges.items():
            cnt = occupancy_map.get(edge_id, 0)
            self.graph.update_edge_occupancy(edge_id, cnt)

    def inject_congestion_scenario(self, src: str = "J3", dst: str = "J2", level: float = 3.0):
        """Sets high congestion multiplier on key corridor J3-J2."""
        self.graph.set_edge_congestion(src, dst, level)

    def clear_congestion_scenario(self, src: str = "J3", dst: str = "J2"):
        """Clears high congestion multiplier on corridor J3-J2."""
        self.graph.set_edge_congestion(src, dst, 0.0)

    def set_route_blocked(self, src: str = "J3", dst: str = "J2", blocked: bool = True):
        """Blocks or unblocks corridor J3-J2."""
        self.graph.set_edge_blocked(src, dst, blocked)
