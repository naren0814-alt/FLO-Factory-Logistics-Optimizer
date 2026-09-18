"""
FLO Core Graph — Factory layout graph topology & dynamic A* routing algorithm.
"""

import math
import heapq
from typing import Dict, List, Optional, Tuple
from flo.core.models import NodeModel, EdgeModel
from config.settings import CONGESTION_PENALTY_FACTOR, BATTERY_DRAIN_RATE, DEFAULT_AGV_SPEED, LOADED_DRAIN_MULTIPLIER

def get_default_factory_nodes() -> Dict[str, NodeModel]:
    nodes = [
        NodeModel(id="WAREHOUSE", name="Raw Material Warehouse", x=100.0, y=100.0, node_type="warehouse"),
        NodeModel(id="J1", name="Junction 1", x=250.0, y=100.0, node_type="junction"),
        NodeModel(id="M1", name="Machine 1", x=250.0, y=250.0, node_type="machine"),
        NodeModel(id="M2", name="Machine 2", x=450.0, y=250.0, node_type="machine"),
        NodeModel(id="J2", name="North Junction", x=450.0, y=100.0, node_type="junction"),
        NodeModel(id="J3", name="Central Corridor Junction", x=350.0, y=180.0, node_type="junction"),
        NodeModel(id="J4", name="South Bypass Junction", x=350.0, y=320.0, node_type="junction"),
        NodeModel(id="J5", name="Assembly Junction", x=550.0, y=250.0, node_type="junction"),
        NodeModel(id="ASSY", name="Assembly Station", x=550.0, y=380.0, node_type="assembly"),
        NodeModel(id="DISPATCH", name="Dispatch / Finished Goods", x=700.0, y=380.0, node_type="dispatch"),
        NodeModel(id="CHARGER1", name="Charging Station 1", x=100.0, y=380.0, node_type="charging"),
        NodeModel(id="CHARGER2", name="Charging Station 2", x=700.0, y=100.0, node_type="charging"),
    ]
    return {n.id: n for n in nodes}

def get_default_factory_edges() -> Dict[str, EdgeModel]:
    # Edge definitions (bidirectional created below)
    raw_edges = [
        ("WAREHOUSE", "J1", 150.0, 2),
        ("WAREHOUSE", "CHARGER1", 280.0, 3),
        ("J1", "J2", 200.0, 2),  # Direct Top Corridor Bridge J1 <-> J2
        ("J1", "M1", 150.0, 2),
        ("J1", "J3", 130.0, 1),  # Narrow corridor entrance
        ("J1", "CHARGER1", 280.0, 2),
        ("M1", "J3", 120.0, 2),
        ("M1", "J4", 120.0, 2),  # South bypass path
        ("J3", "J2", 130.0, 1),  # Central main corridor (narrow, capacity 1)
        ("J3", "M2", 120.0, 2),
        ("J3", "J5", 210.0, 2),
        ("M2", "J2", 150.0, 2),
        ("M2", "J4", 120.0, 2),
        ("M2", "J5", 120.0, 2),
        ("J4", "ASSY", 210.0, 3), # Alternative south bypass to Assembly
        ("J2", "J5", 180.0, 2),
        ("J2", "CHARGER2", 250.0, 2),
        ("J5", "ASSY", 130.0, 2),
        ("ASSY", "DISPATCH", 150.0, 2),
        ("CHARGER2", "DISPATCH", 280.0, 2),
    ]

    edges = {}
    for src, dst, dist, cap in raw_edges:
        # Create forward edge
        edge_id_1 = f"{src}_{dst}"
        edges[edge_id_1] = EdgeModel(
            id=edge_id_1, source=src, destination=dst,
            distance=dist, travel_time=dist / 50.0, capacity=cap
        )
        # Create reverse edge
        edge_id_2 = f"{dst}_{src}"
        edges[edge_id_2] = EdgeModel(
            id=edge_id_2, source=dst, destination=src,
            distance=dist, travel_time=dist / 50.0, capacity=cap
        )
    return edges

class FactoryGraph:
    def __init__(self, nodes: Optional[Dict[str, NodeModel]] = None, edges: Optional[Dict[str, EdgeModel]] = None):
        self.nodes = nodes or get_default_factory_nodes()
        self.edges = edges or get_default_factory_edges()

    def update_edge_occupancy(self, edge_id: str, occupied_count: int):
        if edge_id in self.edges:
            edge = self.edges[edge_id]
            edge.occupied_count = max(0, occupied_count)
            # Calculate congestion ratio
            if edge.capacity > 0:
                # Congestion ramps up non-linearly if occupied > capacity
                ratio = edge.occupied_count / float(edge.capacity)
                edge.congestion = max(0.0, ratio - 0.5)
            else:
                edge.congestion = 0.0

    def set_edge_blocked(self, src: str, dst: str, blocked: bool):
        edge_id_1 = f"{src}_{dst}"
        edge_id_2 = f"{dst}_{src}"
        if edge_id_1 in self.edges:
            self.edges[edge_id_1].blocked = blocked
        if edge_id_2 in self.edges:
            self.edges[edge_id_2].blocked = blocked

    def set_edge_congestion(self, src: str, dst: str, congestion_level: float):
        edge_id_1 = f"{src}_{dst}"
        edge_id_2 = f"{dst}_{src}"
        if edge_id_1 in self.edges:
            self.edges[edge_id_1].congestion = max(0.0, congestion_level)
        if edge_id_2 in self.edges:
            self.edges[edge_id_2].congestion = max(0.0, congestion_level)

    def get_neighbors(self, node_id: str) -> List[Tuple[str, EdgeModel]]:
        neighbors = []
        for edge in self.edges.values():
            if edge.source == node_id and not edge.blocked:
                neighbors.append((edge.destination, edge))
        return neighbors

    def calculate_edge_cost(self, edge: EdgeModel, consider_congestion: bool = True) -> float:
        if edge.blocked:
            return float('inf')
        base_cost = edge.distance
        if consider_congestion:
            # Dynamic cost multiplier based on congestion
            congestion_factor = 1.0 + (CONGESTION_PENALTY_FACTOR * edge.congestion)
            return base_cost * congestion_factor
        return base_cost

    def heuristic(self, node_a: str, node_b: str) -> float:
        """Euclidean distance heuristic for A*"""
        nA = self.nodes.get(node_a)
        nB = self.nodes.get(node_b)
        if not nA or not nB:
            return 0.0
        return math.hypot(nA.x - nB.x, nA.y - nB.y)

    def find_route(self, start_node: str, end_node: str, consider_congestion: bool = True) -> Optional[Dict]:
        """
        A* algorithm for shortest path with dynamic congestion weighting.
        Returns dict with route_nodes, distance, estimated_travel_time, estimated_energy, congestion_cost.
        """
        if start_node not in self.nodes or end_node not in self.nodes:
            return None

        if start_node == end_node:
            return {
                "route": [start_node],
                "distance": 0.0,
                "estimated_travel_time": 0.0,
                "estimated_energy": 0.0,
                "congestion_cost": 0.0
            }

        # Priority Queue: (f_score, current_node)
        open_set: List[Tuple[float, str]] = []
        heapq.heappush(open_set, (0.0, start_node))

        came_from: Dict[str, str] = {}
        edge_used: Dict[str, EdgeModel] = {}

        g_score: Dict[str, float] = {node: float('inf') for node in self.nodes}
        g_score[start_node] = 0.0

        f_score: Dict[str, float] = {node: float('inf') for node in self.nodes}
        f_score[start_node] = self.heuristic(start_node, end_node)

        while open_set:
            _, current = heapq.heappop(open_set)

            if current == end_node:
                # Reconstruct path
                path = [current]
                total_distance = 0.0
                total_congestion_cost = 0.0

                curr = current
                while curr in came_from:
                    edge = edge_used[curr]
                    total_distance += edge.distance
                    total_congestion_cost += self.calculate_edge_cost(edge, consider_congestion) - edge.distance
                    curr = came_from[curr]
                    path.append(curr)

                path.reverse()
                est_time = total_distance / (DEFAULT_AGV_SPEED * 10.0) # Normalized speed units
                est_energy = total_distance * BATTERY_DRAIN_RATE * 0.1

                return {
                    "route": path,
                    "distance": total_distance,
                    "estimated_travel_time": est_time,
                    "estimated_energy": est_energy,
                    "congestion_cost": total_congestion_cost
                }

            for neighbor, edge in self.get_neighbors(current):
                edge_cost = self.calculate_edge_cost(edge, consider_congestion)
                if edge_cost == float('inf'):
                    continue

                tentative_g = g_score[current] + edge_cost

                if tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    edge_used[neighbor] = edge
                    g_score[neighbor] = tentative_g
                    f_score[neighbor] = tentative_g + self.heuristic(neighbor, end_node)
                    heapq.heappush(open_set, (f_score[neighbor], neighbor))

        return None  # No valid route found
