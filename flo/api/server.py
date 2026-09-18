"""
FLO Core API Server — FastAPI Server for Session 1 (FLO Optimization Engine).
Runs on Port 8000.
"""

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict, List, Optional
import os

from flo.core.optimizer import FLOOptimizer
from flo.core.models import TaskPriority, AGVStatus
from config.settings import CORE_PORT

app = FastAPI(title="FLO — Factory Logistics Optimizer (Core Session 1)", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

optimizer = FLOOptimizer()

class TaskCreateRequest(BaseModel):
    pickup: str
    destination: str
    priority: TaskPriority = TaskPriority.NORMAL
    weight: float = 10.0
    deadline_seconds: float = 300.0

class ScenarioRequest(BaseModel):
    src: str = "J3"
    dst: str = "J2"
    agv_id: str = "AGV01"
    battery: float = 12.0

@app.get("/api/state")
def get_flo_state():
    """Returns complete state, active graph, latest decision reasoning, events, and metrics."""
    return {
        "nodes": [n.model_dump() for n in optimizer.graph.nodes.values()],
        "edges": [e.model_dump() for e in optimizer.graph.edges.values()],
        "agvs": [a.model_dump() for a in optimizer.agvs.values()],
        "tasks": [t.model_dump() for t in optimizer.tasks.values()],
        "events": [e.model_dump() for e in optimizer.events],
        "decisions": [d.model_dump() for d in optimizer.decisions],
        "last_decision": optimizer.last_decision.model_dump() if optimizer.last_decision else None,
        "metrics": optimizer.metrics_collector.metrics.model_dump(),
        "baseline": optimizer.metrics_collector.baseline_stats.model_dump()
    }

@app.post("/api/sync_state")
def sync_factory_state(payload: Dict):
    """
    Receives factory state updates from Factory Simulator (Session 2).
    Evaluates pending tasks, battery feasibility, dynamic routing, and returns commands.
    """
    agv_list = payload.get("agvs", [])
    task_list = payload.get("tasks", [])
    
    optimizer.sync_factory_state(agv_list, task_list)
    commands = optimizer.process_optimization_cycle()
    
    return {
        "status": "OK",
        "commands": commands
    }

@app.post("/api/task/create")
def create_task(req: TaskCreateRequest):
    task = optimizer.create_new_task(
        pickup=req.pickup,
        destination=req.destination,
        priority=req.priority,
        weight=req.weight,
        deadline_seconds=req.deadline_seconds
    )
    return {"status": "SUCCESS", "task": task.model_dump()}

@app.post("/api/scenario/add_congestion")
def scenario_add_congestion(req: ScenarioRequest):
    cmds = optimizer.trigger_scenario_add_congestion(req.src, req.dst)
    return {"status": "SUCCESS", "message": f"Congestion added to {req.src}-{req.dst}", "commands": cmds}

@app.post("/api/scenario/remove_congestion")
def scenario_remove_congestion(req: ScenarioRequest):
    cmds = optimizer.trigger_scenario_remove_congestion(req.src, req.dst)
    return {"status": "SUCCESS", "message": f"Congestion removed from {req.src}-{req.dst}", "commands": cmds}

@app.post("/api/scenario/block_route")
def scenario_block_route(req: ScenarioRequest):
    cmds = optimizer.trigger_scenario_block_route(req.src, req.dst)
    return {"status": "SUCCESS", "message": f"Route {req.src}-{req.dst} blocked", "commands": cmds}

@app.post("/api/scenario/unblock_route")
def scenario_unblock_route(req: ScenarioRequest):
    cmds = optimizer.trigger_scenario_unblock_route(req.src, req.dst)
    return {"status": "SUCCESS", "message": f"Route {req.src}-{req.dst} unblocked", "commands": cmds}

@app.post("/api/scenario/low_battery_test")
def scenario_low_battery_test(req: ScenarioRequest):
    agv_id = req.agv_id or "AGV01"
    cmds = optimizer.trigger_scenario_low_battery_test(agv_id, req.battery)
    return {"status": "SUCCESS", "message": f"Low battery ({req.battery:.1f}%) triggered for {agv_id}", "commands": cmds}

@app.post("/api/scenario/fail_agv")
def scenario_fail_agv(req: ScenarioRequest):
    agv_id = req.agv_id or "AGV01"
    cmds = optimizer.trigger_scenario_fail_agv(agv_id)
    return {"status": "SUCCESS", "message": f"AGV {agv_id} marked as FAILED", "commands": cmds}

@app.post("/api/scenario/recover_agv")
def scenario_recover_agv(req: ScenarioRequest):
    agv_id = req.agv_id or "AGV01"
    cmds = optimizer.trigger_scenario_recover_agv(agv_id)
    return {"status": "SUCCESS", "message": f"AGV {agv_id} recovered and returned to fleet", "commands": cmds}

@app.get("/core_view", response_class=HTMLResponse)
def get_core_view_page():
    path = os.path.join("frontend", "core_view.html")
    if os.path.exists(path):
        return FileResponse(path)
    return HTMLResponse("<h1>FLO Core View Page</h1>")

if __name__ == "__main__":
    uvicorn.run("flo.api.server:app", host="127.0.0.1", port=CORE_PORT, reload=False)
