"""
FLO Core Models — Data structures for Graph, AGVs, Tasks, Events, and Decisions.
"""

from enum import Enum
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

class AGVStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    MOVING_TO_PICKUP = "MOVING_TO_PICKUP"
    LOADING = "LOADING"
    MOVING_TO_DESTINATION = "MOVING_TO_DESTINATION"
    UNLOADING = "UNLOADING"
    CHARGING = "CHARGING"
    LOW_BATTERY = "LOW_BATTERY"
    WAITING = "WAITING"
    FAILED = "FAILED"

class TaskPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"

class TaskStatus(str, Enum):
    WAITING = "WAITING"
    ASSIGNED = "ASSIGNED"
    MOVING_TO_PICKUP = "MOVING_TO_PICKUP"
    LOADING = "LOADING"
    IN_TRANSIT = "IN_TRANSIT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REASSIGNING = "REASSIGNING"

class NodeModel(BaseModel):
    id: str
    name: str
    x: float
    y: float
    node_type: str  # warehouse, machine, assembly, dispatch, charging, junction

class EdgeModel(BaseModel):
    id: str
    source: str
    destination: str
    distance: float
    travel_time: float
    capacity: int = 2
    occupied_count: int = 0
    congestion: float = 0.0
    blocked: bool = False

class AGVModel(BaseModel):
    id: str
    name: str
    current_node: str
    x: float
    y: float
    battery: float = 100.0  # percentage
    battery_capacity: float = 100.0
    payload_capacity: float = 50.0  # kg
    speed: float = 1.5
    status: AGVStatus = AGVStatus.AVAILABLE
    current_task_id: Optional[str] = None
    current_route: List[str] = Field(default_factory=list)
    route_index: int = 0
    carrying_material: bool = False
    charging: bool = False
    target_charger: Optional[str] = None
    saved_task_id: Optional[str] = None  # Task to resume after charging

class TaskModel(BaseModel):
    task_id: str
    pickup: str
    destination: str
    priority: TaskPriority = TaskPriority.NORMAL
    weight: float = 10.0  # kg
    deadline_seconds: float = 300.0  # seconds from creation
    creation_time: float = 0.0
    status: TaskStatus = TaskStatus.WAITING
    assigned_agv_id: Optional[str] = None
    estimated_completion_time: Optional[float] = None
    actual_completion_time: Optional[float] = None

class FeasibilityResult(BaseModel):
    agv_id: str
    feasible: bool
    reason: str
    required_energy: float
    available_battery: float
    estimated_time: float
    distance: float

class DecisionExplanation(BaseModel):
    task_id: str
    assigned_agv_id: Optional[str]
    timestamp: str
    evaluations: List[FeasibilityResult]
    reasoning: str
    selected_route: List[str]
    algorithm_used: str = "FLO_MULTI_FACTOR"

class EventLog(BaseModel):
    id: str
    timestamp: str
    level: str  # INFO, WARNING, ERROR, SUCCESS
    message: str
    category: str  # CONGESTION, BATTERY, TASK, FAILURE, REPLAN

class SystemMetrics(BaseModel):
    completed_tasks: int = 0
    pending_tasks: int = 0
    total_distance_traveled: float = 0.0
    total_energy_consumed: float = 0.0
    avg_delivery_time: float = 0.0
    replans_triggered: int = 0
    congestion_reroutes: int = 0
    battery_interventions: int = 0
    failed_tasks: int = 0
    agv_utilization_pct: float = 0.0
    flo_efficiency_gain_pct: float = 0.0  # Measured comparison against baseline

class BaselineComparison(BaseModel):
    baseline_delivery_time: float = 0.0
    flo_delivery_time: float = 0.0
    baseline_energy: float = 0.0
    flo_energy: float = 0.0
    baseline_reroutes: int = 0
    flo_reroutes: int = 0
