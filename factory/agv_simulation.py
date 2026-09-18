"""
Factory Simulator — Physical AGV Simulation & Physics Engine.
"""

import math
from typing import Dict, List, Optional
from flo.core.models import AGVModel, AGVStatus, TaskModel, TaskStatus
from flo.core.graph import get_default_factory_nodes
from config.settings import DEFAULT_AGV_SPEED, BATTERY_DRAIN_RATE, LOADED_DRAIN_MULTIPLIER, CHARGING_RATE

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
        Advances the physical simulation by 1 tick (200ms).
        Updates position, battery drain/recharge, and task progression.
        """
        for agv in self.agvs.values():
            if agv.status == AGVStatus.FAILED:
                continue

            # 1. Charging state physics
            if agv.charging or agv.status == AGVStatus.CHARGING:
                agv.battery = min(100.0, agv.battery + CHARGING_RATE)
                if agv.battery >= 90.0:
                    agv.charging = False
                    agv.target_charger = None
                    if agv.saved_task_id and agv.saved_task_id in tasks:
                        agv.status = AGVStatus.MOVING_TO_PICKUP
                        # Resuming task will be routed by FLO Core
                    else:
                        agv.status = AGVStatus.AVAILABLE
                continue

            # 2. Movement along active route
            if agv.current_route and agv.route_index < len(agv.current_route):
                target_node_id = agv.current_route[agv.route_index]
                target_node = self.nodes.get(target_node_id)

                if target_node:
                    dx = target_node.x - agv.x
                    dy = target_node.y - agv.y
                    dist_to_target = math.hypot(dx, dy)

                    step = agv.speed * 8.0  # Physical step size per tick

                    if dist_to_target <= step:
                        # Reached node waypoint
                        agv.x = target_node.x
                        agv.y = target_node.y
                        agv.current_node = target_node_id
                        agv.route_index += 1

                        # If reached end of route
                        if agv.route_index >= len(agv.current_route):
                            self._handle_route_completion(agv, tasks)
                    else:
                        # Move fraction towards target
                        move_x = (dx / dist_to_target) * step
                        move_y = (dy / dist_to_target) * step
                        agv.x += move_x
                        agv.y += move_y

                        # Drain battery
                        drain = step * BATTERY_DRAIN_RATE * 0.05
                        if agv.carrying_material:
                            drain *= LOADED_DRAIN_MULTIPLIER
                        agv.battery = max(0.0, agv.battery - drain)

    def _handle_route_completion(self, agv: AGVModel, tasks: Dict[str, TaskModel]):
        """Callback when an AGV reaches the final node in its assigned route."""
        if agv.target_charger and agv.current_node == agv.target_charger:
            # Reached charging station
            agv.status = AGVStatus.CHARGING
            agv.charging = True
            return

        if agv.current_task_id and agv.current_task_id in tasks:
            task = tasks[agv.current_task_id]

            if agv.status == AGVStatus.MOVING_TO_PICKUP or agv.current_node == task.pickup:
                # Arrived at Pickup! Pick up cargo and head to destination
                agv.carrying_material = True
                task.status = TaskStatus.IN_TRANSIT
                agv.status = AGVStatus.MOVING_TO_DESTINATION

                # Calculate remaining route to destination
                pickup_idx = agv.current_route.index(task.pickup) if task.pickup in agv.current_route else 0
                dest_idx = agv.current_route.index(task.destination) if task.destination in agv.current_route else len(agv.current_route) - 1
                if pickup_idx < dest_idx:
                    agv.route_index = pickup_idx + 1

            elif agv.current_node == task.destination:
                # Arrived at Destination! Complete task
                agv.carrying_material = False
                task.status = TaskStatus.COMPLETED
                agv.status = AGVStatus.AVAILABLE
                agv.current_task_id = None
                agv.current_route = []
                agv.route_index = 0
