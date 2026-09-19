"""
Production Single-Service Deployment End-to-End Verification Test.
Tests launching `main:app` on port 10000 (simulating Render $PORT & 0.0.0.0 binding)
and verifies complete lifecycle, scenario triggering, task creation, AGV movement, and completion.
"""

import subprocess
import time
import httpx
import sys
import os

def kill_existing_servers():
    """Kills any processes bound to port 10000."""
    try:
        if os.name == 'nt':
            cmd = 'powershell -Command "Get-NetTCPConnection -LocalPort 10000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess"'
            output = subprocess.check_output(cmd, shell=True, text=True)
            pids = set(output.strip().split())
            for pid_str in pids:
                if pid_str and pid_str.isdigit():
                    pid = int(pid_str)
                    if pid > 0:
                        subprocess.run(f"taskkill /f /pid {pid}", shell=True, capture_output=True)
            time.sleep(1.0)
    except Exception:
        pass

def test_production_deployment():
    print("====================================================")
    print("  PRODUCTION SINGLE-SERVICE DEPLOYMENT TEST (PORT 10000)")
    print("====================================================")

    kill_existing_servers()

    # Launch main.py on PORT=10000
    env = os.environ.copy()
    env["PORT"] = "10000"
    env["HOST"] = "0.0.0.0"

    print("[INIT] Starting production app: uvicorn main:app --host 0.0.0.0 --port 10000...")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"], cwd="c:/Users/coolr/Documents/FLO", env=env)

    try:
        time.sleep(3.5)

        with httpx.Client(timeout=5.0) as client:
            # 1. Verify HTML & Static files
            print("[TEST 1] Verifying Static files & HTML views...")
            r_gui = client.get("http://127.0.0.1:10000/")
            assert r_gui.status_code == 200 and "FLO — Factory Logistics Optimizer" in r_gui.text
            print(" -> GUI (index.html): PASS")

            r_core = client.get("http://127.0.0.1:10000/core_view")
            assert r_core.status_code == 200 and "FLO Core Engine" in r_core.text
            print(" -> Core View: PASS")

            r_js = client.get("http://127.0.0.1:10000/static/app.js")
            assert r_js.status_code == 200
            print(" -> Static app.js: PASS")

            # 2. Verify State endpoints
            print("[TEST 2] Verifying API State endpoints...")
            r_sim_state = client.get("http://127.0.0.1:10000/api/simulator_state")
            assert r_sim_state.status_code == 200
            sim_data = r_sim_state.json()
            assert "agvs" in sim_data and "tasks" in sim_data
            print(" -> /api/simulator_state: PASS")

            r_flo_state = client.get("http://127.0.0.1:10000/api/state")
            assert r_flo_state.status_code == 200
            flo_data = r_flo_state.json()
            assert "agvs" in flo_data and "tasks" in flo_data
            print(" -> /api/state: PASS")

            # 3. Create Task via production endpoint
            print("[TEST 3] Creating new task via /api/task/create...")
            r_create = client.post("http://127.0.0.1:10000/api/task/create", json={
                "pickup": "WAREHOUSE",
                "destination": "M1",
                "priority": "URGENT",
                "weight": 20.0,
                "deadline_seconds": 300.0
            })
            assert r_create.status_code == 200
            t_data = r_create.json()
            task_id = t_data["task"]["task_id"]
            print(f" -> Task created: {task_id}")

            # 4. Trigger Scenarios
            print("[TEST 4] Testing Multi-Scenario Triggers...")
            r_cong = client.post("http://127.0.0.1:10000/api/scenario/add_congestion", json={"src": "J3", "dst": "J2"})
            assert r_cong.status_code == 200
            print(" -> Congestion: PASS")

            r_bat = client.post("http://127.0.0.1:10000/api/scenario/low_battery_test", json={"agv_id": "AGV01", "battery_val": 12.0})
            assert r_bat.status_code == 200
            print(" -> Low Battery: PASS")

            r_fail = client.post("http://127.0.0.1:10000/api/scenario/fail_agv", json={"agv_id": "AGV03"})
            assert r_fail.status_code == 200
            print(" -> AGV Failure: PASS")

            # 5. Monitor AGV assignment, movement, and completion
            print(f"[TEST 5] Tracking Task {task_id} lifecycle to completion...")
            completed = False
            for tick in range(250):
                time.sleep(0.5)
                st = client.get("http://127.0.0.1:10000/api/simulator_state").json()
                t_obj = next((t for t in st["tasks"] if t["task_id"] == task_id), None)
                if t_obj:
                    status = t_obj["status"]
                    assigned_agv = t_obj.get("assigned_agv_id")
                    if tick % 10 == 0:
                        print(f" Tick {tick+1:02d}: Task {task_id} status = [{status}] | AGV = [{assigned_agv}]")
                    if status == "COMPLETED":
                        completed = True
                        print(f" -> Task {task_id} reached COMPLETED status cleanly!")
                        break

            assert completed, f"Task {task_id} failed to complete within test window"

            print("\n====================================================")
            print(" ALL PRODUCTION DEPLOYMENT CHECKS PASSED SUCCESSFULLY!")
            print("====================================================")

    finally:
        try:
            proc.terminate()
        except Exception:
            pass

if __name__ == "__main__":
    test_production_deployment()
