"""
Factory Simulator API Server — FastAPI Server for Session 2 (Physical Factory Simulator & GUI).
Runs on Port 8001.
"""

import asyncio
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import os

from factory.simulator import FactorySimulatorEngine
from factory.task_generator import get_initial_tasks
from config.settings import FACTORY_PORT

simulator = FactorySimulatorEngine()
sync_task = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup background sync loop
    global sync_task
    sync_task = asyncio.create_task(simulator.sync_with_core_loop())
    yield
    # Shutdown
    if sync_task:
        sync_task.cancel()

app = FastAPI(
    title="FLO — Factory Simulator (Physical Session 2)",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_dir = os.path.join(os.getcwd(), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/api/simulator_state")
def get_simulator_state():
    return simulator.get_state()

@app.post("/api/control/pause")
def pause_simulator():
    simulator.running = False
    return {"status": "PAUSED"}

@app.post("/api/control/resume")
def resume_simulator():
    simulator.running = True
    return {"status": "RUNNING"}

@app.post("/api/control/reset")
def reset_simulator():
    simulator.agv_sim = simulator.agv_sim.__class__()
    simulator.tasks = get_initial_tasks()
    simulator.running = True
    return {"status": "RESET"}

@app.get("/", response_class=HTMLResponse)
def get_factory_gui():
    path = os.path.join("frontend", "index.html")
    if os.path.exists(path):
        return FileResponse(path)
    return HTMLResponse("<h1>FLO Factory Simulator GUI</h1>")

if __name__ == "__main__":
    uvicorn.run("factory.api:app", host="127.0.0.1", port=FACTORY_PORT, reload=False)
