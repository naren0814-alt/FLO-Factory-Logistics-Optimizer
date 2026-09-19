"""
Factory Simulator — Physical AGV Simulation & Movement Physics Engine.
Handles precise waypoint tracking, arrival detection, and state machine transitions.
"""

import math
from typing import Dict, List, Optional
from flo.core.models import AGVModel, AGVStatus, TaskModel, TaskStatus
from flo.core.graph import get_default_factory_nodes
from config.settings import DEFAULT_AGV_SPEED, BATTERY_DRAIN_RATE, LOADED_DRAIN_MULTIPLIER, CHARGING_RATE

# Arrival detection tolerance threshold in spatial units
ARRIVAL_THRESHOLD = 4.0

class AGVSimulator:
    def __init__(self):
        self.nodes = get_default_factory_nodes()
        self.agvs: Dict[str, AGVModel] = self._create_initial_agvs()

    def _create_initial_agvs(self) -> Dict[str, AGVModel]:
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

    def tick(self, tasks: Dict[str, TaskModel]):
        """
        Advances physical AGV position and handles arrival milestone transitions.
        Executes exactly once per tick.
        """
        for agv in self.agvs.values():
            if agv.status == AGVStatus.FAILED:
                continue

            # 1. Charging Physics
            if agv.charging or agv.status == AGVStatus.CHARGING:
                agv.battery = min(100.0, agv.battery + CHARGING_RATE)
                if agv.battery >= 90.0:
                    agv.charging = False
                    agv.target_charger = None
                    agv.status = AGVStatus.AVAILABLE
                continue

            # 2. Movement along route
            if agv.current_route and agv.route_index < len(agv.current_route):
                target_node_id = agv.current_route[agv.route_index]
                target_node = self.nodes.get(target_node_id)

                if target_node:
                    dx = target_node.x - agv.x
                    dy = target_node.y - agv.y
                    dist_to_target = math.hypot(dx, dy)

                    step = agv.speed * 8.0  # Movement step per tick (~12 units)

                    if dist_to_target <= step or dist_to_target <= ARRIVAL_THRESHOLD:
                        # Snap position to node waypoint
                        agv.x = target_node.x
                        agv.y = target_node.y
                        agv.current_node = target_node_id

                        # Handle waypoint milestone arrival
                        self._process_waypoint_arrival(agv, tasks, target_node_id)
                    else:
                        # Interpolate movement
                        agv.x += (dx / dist_to_target) * step
                        agv.y += (dy / dist_to_target) * step

                        # Deplete battery
                        drain = step * BATTERY_DRAIN_RATE * 0.05
                        if agv.carrying_material:
                            drain *= LOADED_DRAIN_MULTIPLIER
                        agv.battery = max(0.0, agv.battery - drain)

    def _process_waypoint_arrival(self, agv: AGVModel, tasks: Dict[str, TaskModel], node_id: str):
        """Processes milestone state transitions upon reaching a node waypoint."""

        # Charger arrival
        if agv.target_charger and node_id == agv.target_charger:
            agv.status = AGVStatus.CHARGING
            agv.charging = True
            agv.current_route = []
            agv.route_index = 0
            return

        task = tasks.get(agv.current_task_id) if agv.current_task_id else None

        if task:
            # A) PICKUP ARRIVAL: AGV reached pickup node while MOVING_TO_PICKUP
            if node_id == task.pickup and (agv.status == AGVStatus.MOVING_TO_PICKUP or not agv.carrying_material):
                print(f"[FACTORY] {agv.id} reached {task.pickup}")
                print(f"[FACTORY] {agv.id} status = MOVING_TO_DESTINATION")
                print(f"[FACTORY] {agv.id} target = {task.destination}")
                agv.carrying_material = True
                agv.status = AGVStatus.MOVING_TO_DESTINATION
                task.status = TaskStatus.IN_TRANSIT
                agv.route_index += 1

            # B) DESTINATION ARRIVAL: AGV reached final destination node
            elif node_id == task.destination and (agv.status == AGVStatus.MOVING_TO_DESTINATION or agv.carrying_material):
                print(f"[FACTORY] {agv.id} reached {task.destination}")
                print(f"[FACTORY] {task.task_id} COMPLETED")
                print(f"[FACTORY] {agv.id} status = AVAILABLE")
                task.status = TaskStatus.COMPLETED
                agv.carrying_material = False
                agv.status = AGVStatus.AVAILABLE
                agv.current_task_id = None
                agv.current_route = []
                agv.route_index = 0

            else:
                # Intermediate corridor waypoint
                agv.route_index += 1

                # Check if reached end of route list
                if agv.route_index >= len(agv.current_route):
                    if agv.carrying_material and node_id == task.destination:
                        print(f"[FACTORY] {agv.id} reached {task.destination}")
                        print(f"[FACTORY] {task.task_id} COMPLETED")
                        print(f"[FACTORY] {agv.id} status = AVAILABLE")
                        task.status = TaskStatus.COMPLETED
                        agv.carrying_material = False
                        agv.status = AGVStatus.AVAILABLE
                        agv.current_task_id = None
                        agv.current_route = []
                        agv.route_index = 0
                    else:
                        agv.route_index = len(agv.current_route) - 1
        else:
            # No active task attached
            agv.route_index += 1
            if agv.route_index >= len(agv.current_route):
                agv.status = AGVStatus.AVAILABLE
                agv.current_route = []
                agv.route_index = 0
