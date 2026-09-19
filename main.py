"""
FLO Production Master Application — Single-Service Unified Deployment Entry Point.
Combines FLO Optimization Engine (Core) and Factory Simulator into a single HTTP server.
"""

import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse

from flo.api.server import app as core_app
from factory.api import app as factory_app, lifespan as factory_lifespan

# 1. Initialize master production FastAPI application
app = FastAPI(
    title="FLO — Factory Logistics Optimizer (Production)",
    version="1.0.0",
    lifespan=factory_lifespan
)

# 2. CORS Middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Static Files Mounting
frontend_dir = os.path.join(os.getcwd(), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

# 4. Route Merging
registered_keys = set()

# Register Factory routes first (excluding static mounts and root redirects)
for route in factory_app.routes:
    if hasattr(route, "path") and route.path not in ["/", "/static"]:
        route_key = (route.path, tuple(sorted(getattr(route, "methods", []))))
        app.routes.append(route)
        registered_keys.add(route_key)

# Register Core routes (avoiding duplicate route keys)
for route in core_app.routes:
    if hasattr(route, "path") and route.path not in ["/core_view"]:
        route_key = (route.path, tuple(sorted(getattr(route, "methods", []))))
        if route_key not in registered_keys:
            app.routes.append(route)
            registered_keys.add(route_key)

# 5. HTML Views
@app.get("/", response_class=HTMLResponse)
def get_factory_gui():
    path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(path):
        return FileResponse(path)
    return HTMLResponse("<h1>FLO Factory Simulator GUI</h1>")

@app.get("/core_view", response_class=HTMLResponse)
def get_core_view():
    path = os.path.join(frontend_dir, "core_view.html")
    if os.path.exists(path):
        return FileResponse(path)
    return HTMLResponse("<h1>FLO Core View Page</h1>")

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=False)
