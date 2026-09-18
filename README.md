# FLO — Factory Logistics Optimizer

> **Problem SI-04**: Autonomous Factory Material Flow Optimization  
> **Hackathon Prototype**

![FLO Architecture](https://img.shields.io/badge/Architecture-Dual--Session%20REST-blue)
![Python](https://img.shields.io/badge/Backend-Python%20%7C%20FastAPI-green)
![Frontend](https://img.shields.io/badge/Frontend-HTML5%20Canvas%202D-orange)
![Tests](https://img.shields.io/badge/Tests-100%25%20Passing-brightgreen)

---

## 💡 Core Idea

> *"Existing fleet managers control robot fleets. FLO continuously optimizes how the entire fleet should respond to changing factory conditions."*

FLO is an adaptive material flow optimization and decision engine for smart manufacturing environments. FLO evaluates changing factory conditions—AGV battery feasibility, corridor congestion, task deadlines/priorities, and equipment breakdowns—and dynamically decides how the AGV fleet should move materials efficiently.

---

## 🏗️ Architecture: Two Running Sessions

FLO operates as **two independent running sessions** communicating through a lightweight local REST API:

```
┌─────────────────────────────────────────────────────────┐         ┌──────────────────────────────────────────────────────────┐
│  SESSION 1 — FLO CORE SYSTEM                            │         │  SESSION 2 — FACTORY SIMULATOR                           │
│  (Port 8000)                                            │         │  (Port 8001)                                             │
│                                                         │         │                                                          │
│  - Graph Routing Engine (Dynamic Congestion A*)         │  State  │  - 2D Canvas Industrial Factory Floor Physics            │
│  - Spatial-Temporal Zone Interlocking Coordination      │ <─────  │  - AGV Position Interpolation & Battery Drain            │
│  - Stage 1 Hard Battery & Payload Feasibility Filter    │  Cmds   │  - Interactive Test Scenario Selection Modals            │
│  - Stage 2 Multi-Factor Weighted Scoring Engine         │ ──────> │  - Live Event Log & Real-Time KPI Visualizer             │
│  - Event-Driven Dynamic Replanner & Auto-Charger        │         │  - Interactive Factory GUI (http://localhost:8001)       │
│  - Session 1 Engine Dashboard (http://localhost:8000)   │         │                                                          │
└─────────────────────────────────────────────────────────┘         └──────────────────────────────────────────────────────────┘
```

---

## ⚡ Key Features & Optimization Capabilities

### 1. Dynamic Congestion-Aware A* Routing
FLO computes optimal paths across the factory graph taking edge distance, capacities, and real-time corridor congestion into account:

$$\text{cost} = \text{distance} \times \left(1.0 + \text{CONGESTION\_WEIGHT} \times \frac{\text{occupied\_count}}{\max(\text{capacity}, 1)}\right)$$

If a main corridor (e.g., `J3 ↔ J2`) becomes heavily congested or blocked, FLO automatically reroutes AGVs onto faster bypass corridors (such as the top highway `J1 ↔ J2` or south bypass `J4`).

### 2. Two-Stage Task Assignment Engine
- **Stage 1 — Hard Feasibility Filter**: Rejects AGVs if status is `FAILED` or occupied, payload capacity < task weight, no unblocked path exists, battery is insufficient for the mission + safety reserve, or task deadline is unachievable.
- **Stage 2 — Multi-Factor Score Optimization**: Computes a deterministic score for all feasible AGVs based on travel time, distance, congestion penalties, energy consumption, and priority weighting (`LOW`, `NORMAL`, `HIGH`, `URGENT`).

### 3. Battery Feasibility & Automatic Charging Divert
- **Mission Energy Prediction**: Calculates total energy required for the entire mission (`Current Location → Pickup → Destination + 15% Safety Reserve`). Low-battery AGVs are rejected during assignment even if physically closest.
- **Automatic Charging Divert**: If an active AGV's battery drops below safe threshold mid-mission, FLO diverts it to the nearest Charger (`CHARGER1`/`CHARGER2`), recharges it to 90%, and resumes its assigned task.

### 4. Priority Spatial-Temporal Zone Coordination (`flo/core/coordination.py`)
Prevents deadlocks, collisions, and overlaying at junctions and narrow corridors. When two AGVs approach the same junction, FLO compares Task Priority (`URGENT` > `HIGH` > `NORMAL` > `LOW`) and ETA:
- Grants **Right-of-Way** to the higher-priority task.
- Instructs the lower-priority AGV to safely yield (`COORDINATION: AGV02 yielding at Junction J3`) until the intersection clears.

---

## 📁 Project Structure

```
FLO/
├── config/
│   └── settings.py               # Centralized parameters, weights, drain rates, ports
├── flo/
│   ├── core/
│   │   ├── models.py             # AGV, Task, Graph, Event, Decision data models
│   │   ├── graph.py              # Factory layout topology & dynamic A* routing
│   │   ├── battery.py            # Mission energy prediction & battery feasibility
│   │   ├── feasibility.py        # Stage 1 Hard Feasibility Filter
│   │   ├── assignment.py         # Stage 2 Multi-Factor Weighted Scoring Engine
│   │   ├── congestion.py         # Real-time edge occupancy tracking & corridor modifiers
│   │   ├── coordination.py       # Priority Spatial-Temporal Zone Interlocking Coordination
│   │   ├── replanner.py          # Dynamic event replanner & auto-charger divert
│   │   ├── baseline.py           # Naive baseline optimizer (Nearest + Shortest distance)
│   │   ├── metrics.py            # KPI collector & FLO vs Baseline comparison analytics
│   │   └── optimizer.py          # Master FLO Core Optimizer Loop
│   └── api/
│       └── server.py             # Session 1 FastAPI Application (Port 8000)
├── factory/
│   ├── agv_simulation.py        # Physical AGV physics, waypoints, and battery depletion
│   ├── task_generator.py        # Initial tasks & task helper functions
│   ├── simulator.py              # Physical simulator tick loop & state sync
│   └── api.py                    # Session 2 FastAPI Application (Port 8001)
├── frontend/
│   ├── index.html                # Interactive 2D Canvas Factory Floor GUI (Session 2)
│   ├── core_view.html            # FLO Core Engine Decision Dashboard (Session 1)
│   ├── style.css                 # Clean modern industrial stylesheet
│   └── app.js                    # HTML5 Canvas 2D renderer & live API polling controller
├── tests/
│   ├── test_routing.py           # Unit tests for A*, congestion, blocked paths
│   ├── test_assignment.py        # Unit tests for feasibility filters & priority scoring
│   ├── test_battery.py           # Unit tests for battery feasibility & low-battery rejection
│   ├── test_replanning.py        # Unit tests for AGV breakdown task reassignment
│   └── acceptance_test.py        # Full 22-step end-to-end acceptance sequence test
├── run_core.bat                  # Session 1 launcher script
├── run_factory.bat               # Session 2 launcher script
└── run_all.bat                   # Master launcher script for both sessions
```

---

## 🚀 Quick Start Guide (Windows)

### Prerequisites
- Python 3.10+
- Installed dependencies: `fastapi`, `uvicorn`, `pydantic`, `httpx`, `pytest`
  ```cmd
  pip install fastapi uvicorn pydantic httpx pytest
  ```

### Launching the System

#### Option 1: Master Launcher (Recommended)
Double-click or execute in command prompt:
```cmd
run_all.bat
```
This launches **Session 1 (FLO Core)** on `http://127.0.0.1:8000` and **Session 2 (Factory Simulator)** on `http://127.0.0.1:8001`, and opens the interactive Factory GUI in your browser.

#### Option 2: Separate Session Launchers
- **Session 1 — FLO Core Engine**:
  ```cmd
  run_core.bat
  ```
  Core Dashboard: `http://127.0.0.1:8000/core_view`
- **Session 2 — Factory Simulator**:
  ```cmd
  run_factory.bat
  ```
  Factory GUI: `http://127.0.0.1:8001`

---

## 🧪 Testing & Verification

### Run Unit Tests
```cmd
python -m pytest tests/
```
Output: `7 passed in 0.16s (100% Pass Rate)`

### Run Full System Acceptance Test
```cmd
python tests/acceptance_test.py
```
Output: `Acceptance test completed successfully with 100% PASS rate (22/22 steps passed)`

---

## 🎮 Interactive Test Scenarios (Demo Panel)

The Factory GUI includes interactive scenario injectors to demonstrate FLO's dynamic adaptation:

- **`+ New Task`**: Opens a modal form to submit a custom task (pickup, destination, priority, weight). FLO immediately evaluates and assigns an optimal AGV.
- **`⚡ Urgent Task`**: Instantly creates an `URGENT` priority task (`WAREHOUSE → ASSY`). FLO re-evaluates the fleet and prioritizes it.
- **`⚠️ Route Congestion`**: Opens a modal to select WHICH corridor (`J3 ↔ J2`, `J1 ↔ J2`, `J1 ↔ M1`, `M1 ↔ J4`, `J5 ↔ ASSY`, `ASSY ↔ DISPATCH`) to congest or clear. FLO recalculates dynamic route costs and reroutes affected AGVs.
- **`🛑 Block Route`**: Opens a modal to select WHICH corridor to block completely. FLO automatically reroutes AGVs onto unblocked bypasses.
- **`🪫 Low Battery`**: Opens a modal to select WHICH AGV (`AGV01`–`AGV05`) to drain and set battery level. Unsafe AGVs are rejected for new missions and diverted to charging stations.
- **`💥 AGV Breakdown & Recovery`**: Opens a modal to fail or repair an AGV. When an active AGV breaks down, its task is requeued and reassigned to another operational AGV without interrupting factory operation.
