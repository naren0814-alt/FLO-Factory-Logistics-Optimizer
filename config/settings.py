"""
FLO - Factory Logistics Optimizer Settings & Configuration
Centralized parameters for simulation, routing, scoring, and ports.
"""

import os

# Server Ports & Production Settings
PORT = int(os.getenv("PORT", "8000"))
CORE_PORT = int(os.getenv("CORE_PORT", "8000"))
FACTORY_PORT = int(os.getenv("FACTORY_PORT", "8001"))

# Environment-configurable URLs (fallback to localhost ports for local dev)
if "PORT" in os.environ:
    DEFAULT_CORE_URL = f"http://127.0.0.1:{PORT}"
    DEFAULT_FACTORY_URL = f"http://127.0.0.1:{PORT}"
else:
    DEFAULT_CORE_URL = f"http://127.0.0.1:{CORE_PORT}"
    DEFAULT_FACTORY_URL = f"http://127.0.0.1:{FACTORY_PORT}"

CORE_URL = os.getenv("CORE_URL", DEFAULT_CORE_URL)
FACTORY_URL = os.getenv("FACTORY_URL", DEFAULT_FACTORY_URL)

# Scoring Weights (Stage 2 Multi-Factor Score)
# Lower score = better candidate
TIME_WEIGHT = 2.0
DISTANCE_WEIGHT = 1.0
CONGESTION_WEIGHT = 3.0
ENERGY_WEIGHT = 1.5
PRIORITY_WEIGHT = 5.0
DEADLINE_WEIGHT = 4.0
LATENESS_WEIGHT = 10.0

# AGV Physical Properties
DEFAULT_AGV_SPEED = 1.5           # Grid units per simulation tick
DEFAULT_BATTERY_CAPACITY = 100.0  # Percentage
BATTERY_DRAIN_RATE = 0.25         # % lost per unit distance moved
LOADED_DRAIN_MULTIPLIER = 1.4     # Extra battery drain when carrying payload
CHARGING_RATE = 2.5               # % battery gained per tick while charging
SAFETY_RESERVE_PCT = 15.0         # Minimum safety reserve required after task completion (%)
LOW_BATTERY_THRESHOLD = 25.0      # % at which AGV considers auto-charging

# Congestion Parameters
CONGESTION_PENALTY_FACTOR = 2.5   # Multiplier for occupied edge cost in routing

# Simulation Tick
SIMULATION_TICK_MS = 200          # 5 updates per second
