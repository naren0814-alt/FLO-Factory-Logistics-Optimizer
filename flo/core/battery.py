"""
FLO Core Battery — Mission energy estimation & battery feasibility analyzer.
"""

from typing import Dict, Optional, Tuple
from flo.core.models import AGVModel, TaskModel
from flo.core.graph import FactoryGraph
from config.settings import BATTERY_DRAIN_RATE, LOADED_DRAIN_MULTIPLIER, SAFETY_RESERVE_PCT, LOW_BATTERY_THRESHOLD

class BatteryManager:
    def __init__(self, graph: FactoryGraph):
        self.graph = graph

    def estimate_mission_energy(
        self,
        agv: AGVModel,
        task: TaskModel,
        route_to_pickup: Dict,
        route_to_dest: Dict
    ) -> float:
        """
        Calculates total predicted battery drain for the full mission:
        Current location -> Pickup -> Destination
        """
        dist_pickup = route_to_pickup.get("distance", 0.0)
        dist_dest = route_to_dest.get("distance", 0.0)
        
        # Energy to reach pickup (unloaded)
        energy_pickup = dist_pickup * BATTERY_DRAIN_RATE * 0.1
        
        # Energy from pickup to destination (loaded with task weight)
        load_factor = 1.0 + (task.weight / agv.payload_capacity) * (LOADED_DRAIN_MULTIPLIER - 1.0)
        energy_dest = dist_dest * BATTERY_DRAIN_RATE * 0.1 * load_factor
        
        # Congestion factor penalty
        congestion_penalty = 1.0 + 0.15 * (route_to_pickup.get("congestion_cost", 0.0) + route_to_dest.get("congestion_cost", 0.0))
        
        total_mission_energy = (energy_pickup + energy_dest) * congestion_penalty
        return total_mission_energy

    def is_battery_feasible(
        self,
        agv: AGVModel,
        task: TaskModel,
        route_to_pickup: Dict,
        route_to_dest: Dict
    ) -> Tuple[bool, float, str]:
        """
        Evaluates hard battery feasibility for a candidate AGV & task mission.
        Must retain at least SAFETY_RESERVE_PCT remaining battery after completion.
        """
        estimated_energy = self.estimate_mission_energy(agv, task, route_to_pickup, route_to_dest)
        total_required = estimated_energy + SAFETY_RESERVE_PCT

        if agv.battery < total_required:
            reason = f"Insufficient battery ({agv.battery:.1f}% available < {total_required:.1f}% required for mission + safety reserve)"
            return False, estimated_energy, reason

        return True, estimated_energy, f"Feasible ({agv.battery:.1f}% available >= {total_required:.1f}% required)"

    def find_nearest_charger(self, current_node: str) -> Optional[Tuple[str, Dict]]:
        """Finds nearest charging station node and route to it."""
        chargers = ["CHARGER1", "CHARGER2"]
        best_charger = None
        best_route = None
        min_dist = float('inf')

        for charger_id in chargers:
            route_data = self.graph.find_route(current_node, charger_id, consider_congestion=False)
            if route_data and route_data["distance"] < min_dist:
                min_dist = route_data["distance"]
                best_charger = charger_id
                best_route = route_data

        if best_charger and best_route:
            return best_charger, best_route
        return None

    def check_active_agv_battery_risk(self, agv: AGVModel) -> bool:
        """
        Checks if an active AGV currently performing a task is in danger of running out of battery
        before completing its task or reaching a charger.
        """
        if agv.charging or agv.status in ["CHARGING", "FAILED"]:
            return False

        # Low battery threshold check
        if agv.battery <= LOW_BATTERY_THRESHOLD:
            return True

        return False
