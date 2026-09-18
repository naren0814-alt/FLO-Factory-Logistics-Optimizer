"""
Factory Simulator Engine — Master state coordinator & physics loop runner.
"""

import asyncio
import httpx
import logging
from typing import Dict, List, Optional
from flo.core.models import AGVModel, TaskModel, AGVStatus, TaskStatus
from factory.agv_simulation import AGVSimulator
from factory.task_generator import get_initial_tasks
from config.settings import CORE_URL, SIMULATION_TICK_MS

logger = logging.getLogger("FactorySimulator")

class FactorySimulatorEngine:
    def __init__(self):
        self.agv_sim = AGVSimulator()
        self.tasks: Dict[str, TaskModel] = get_initial_tasks()
        self.running: bool = True
        self.tick_count: int = 0

    def get_state(self) -> Dict:
        """Returns full current state of the simulated factory."""
        return {
            "agvs": [agv.model_dump() for agv in self.agv_sim.agvs.values()],
            "tasks": [task.model_dump() for task in self.tasks.values()],
            "tick": self.tick_count,
            "running": self.running
        }

    def execute_command(self, cmd: Dict):
        """Applies an optimization command from FLO Core to the physical simulator."""
        command_type = cmd.get("command")
        agv_id = cmd.get("agv_id")

        if agv_id not in self.agv_sim.agvs:
            return

        agv = self.agv_sim.agvs[agv_id]

        if command_type == "assign_task":
            task_id = cmd.get("task_id")
            route = cmd.get("route", [])
            agv.current_task_id = task_id
            agv.current_route = route
            agv.route_index = 0
            agv.status = AGVStatus.MOVING_TO_PICKUP

            if task_id in self.tasks:
                self.tasks[task_id].status = TaskStatus.ASSIGNED
                self.tasks[task_id].assigned_agv_id = agv.id

        elif command_type in ["reroute_agv", "set_route"]:
            new_route = cmd.get("new_route", cmd.get("route", []))
            agv.current_route = new_route
            agv.route_index = 0

        elif command_type == "send_to_charge":
            charger_id = cmd.get("charger_id")
            route = cmd.get("route", [])
            agv.target_charger = charger_id
            agv.current_route = route
            agv.route_index = 0
            agv.status = AGVStatus.LOW_BATTERY

        elif command_type == "set_battery":
            battery_val = cmd.get("battery", 12.0)
            agv.battery = battery_val

        elif command_type == "set_status":
            status_val = cmd.get("status", AGVStatus.AVAILABLE.value)
            agv.status = AGVStatus(status_val)

        elif command_type == "hold_agv":
            # Hold AGV position for 1 tick to yield right-of-way at junction
            pass

    def tick(self):
        """Runs 1 physics tick."""
        if not self.running:
            return

        self.tick_count += 1
        self.agv_sim.tick(self.tasks)

    async def sync_with_core_loop(self):
        """Background loop pushing state to FLO Core and retrieving decisions."""
        async with httpx.AsyncClient(timeout=2.0) as client:
            while True:
                try:
                    if self.running:
                        self.tick()
                        state = self.get_state()
                        # Sync state to FLO Core
                        resp = await client.post(f"{CORE_URL}/api/sync_state", json=state)
                        if resp.status_code == 200:
                            data = resp.json()
                            commands = data.get("commands", [])
                            for cmd in commands:
                                self.execute_command(cmd)
                except Exception as e:
                    # Core might be starting up
                    pass

                await asyncio.sleep(SIMULATION_TICK_MS / 1000.0)
