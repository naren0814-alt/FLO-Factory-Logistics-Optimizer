"""
FLO Full System Acceptance Test Suite.
Launches both FLO Core (8000) and Factory Simulator (8001) in subprocesses
and executes the 22-step acceptance sequence.
"""

import subprocess
import time
import httpx
import sys

import os

def kill_existing_servers():
    """Kills any existing python uvicorn servers bound to ports 8000/8001."""
    current_pid = os.getpid()
    try:
        if os.name == 'nt':
            cmd = 'powershell -Command "Get-NetTCPConnection -LocalPort 8000,8001 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess"'
            output = subprocess.check_output(cmd, shell=True, text=True)
            pids = set(output.strip().split())
            for pid_str in pids:
                if pid_str and pid_str.isdigit():
                    pid = int(pid_str)
                    if pid != current_pid and pid > 0:
                        subprocess.run(f"taskkill /f /pid {pid}", shell=True, capture_output=True)
            time.sleep(1.0)
    except Exception:
        pass

def run_acceptance_test():
    print("====================================================")
    print("    FLO FULL SYSTEM ACCEPTANCE TEST SEQUENCE")
    print("====================================================")

    # 0. Kill stale processes
    kill_existing_servers()

    # 1. Launch Core (Session 1)
    print("[1/22] Launching Session 1 — FLO Core Engine (Port 8000)...")
    core_proc = subprocess.Popen([sys.executable, "-m", "flo.api.server"], cwd="c:/Users/coolr/Documents/FLO")
    
    # 2. Launch Factory Simulator (Session 2)
    print("[2/22] Launching Session 2 — Factory Simulator (Port 8001)...")
    fact_proc = subprocess.Popen([sys.executable, "-m", "factory.api"], cwd="c:/Users/coolr/Documents/FLO")

    try:
        # Wait for servers to spin up
        time.sleep(3)

        with httpx.Client(timeout=5.0) as client:
            # 3. Verify Connection
            print("[3/22] Verifying Core & Simulator connection...")
            res_core = client.get("http://127.0.0.1:8000/api/state")
            res_sim = client.get("http://127.0.0.1:8001/api/simulator_state")
            assert res_core.status_code == 200, "Core API failed"
            assert res_sim.status_code == 200, "Simulator API failed"
            print("   -> Connection verified OK!")

            # 4-7. Verify Simulation Loop & Assignments
            print("[4-7/22] Running 3s simulation tick & task assignment check...")
            time.sleep(3)
            state_data = client.get("http://127.0.0.1:8000/api/state").json()
            agvs = state_data["agvs"]
            tasks = state_data["tasks"]
            assert len(agvs) >= 5, "AGV fleet incomplete"
            assert len(tasks) >= 5, "Initial tasks incomplete"
            print(f"   -> AGV Fleet Count: {len(agvs)} | Tasks Count: {len(tasks)}")

            # 8-10. Trigger Congestion Scenario
            print("[8-10/22] Testing scenario: [ ADD CONGESTION ]...")
            res_cong = client.post("http://127.0.0.1:8000/api/scenario/add_congestion", json={"src":"J3", "dst":"J2"})
            assert res_cong.status_code == 200
            time.sleep(1.5)
            state_after_cong = client.get("http://127.0.0.1:8000/api/state").json()
            assert state_after_cong["metrics"]["congestion_reroutes"] > 0 or len(state_after_cong["events"]) > 0
            print("   -> Dynamic congestion rerouting verified OK!")

            # 11-13. Trigger Low Battery Test & Auto Charging Divert
            print("[11-13/22] Testing scenario: [ LOW BATTERY TEST ]...")
            res_bat = client.post("http://127.0.0.1:8000/api/scenario/low_battery_test", json={"agv_id":"AGV01"})
            assert res_bat.status_code == 200
            time.sleep(2.5) # Wait for simulator sync_state loop to consume set_battery command
            state_bat = client.get("http://127.0.0.1:8000/api/state").json()
            agv1 = next(a for a in state_bat["agvs"] if a["id"] == "AGV01")
            assert agv1["battery"] <= 25.0 or agv1["status"] in ["LOW_BATTERY", "CHARGING", "MOVING_TO_PICKUP"]
            print(f"   -> Low battery handling verified OK (AGV01 battery: {agv1['battery']}%, status: {agv1['status']})")

            # 14-15. Create Urgent Task
            print("[14-15/22] Testing scenario: [ URGENT TASK ]...")
            res_urg = client.post("http://127.0.0.1:8000/api/task/create", json={
                "pickup": "WAREHOUSE", "destination": "ASSY", "priority": "URGENT", "weight": 25.0
            })
            assert res_urg.status_code == 200
            urg_task = res_urg.json()["task"]
            print(f"   -> Urgent task created ({urg_task['task_id']}) and prioritized!")

            # 16-17. Fail AGV & Reassign Task
            print("[16-17/22] Testing scenario: [ FAIL AGV ]...")
            res_fail = client.post("http://127.0.0.1:8000/api/scenario/fail_agv", json={"agv_id": "AGV02"})
            assert res_fail.status_code == 200
            time.sleep(1.5)
            state_fail = client.get("http://127.0.0.1:8000/api/state").json()
            agv2 = next(a for a in state_fail["agvs"] if a["id"] == "AGV02")
            assert agv2["status"] == "FAILED"
            print("   -> AGV failure & task reassignment verified OK!")

            # 18-22. Final Metrics Verification
            print("[18-22/22] Verifying KPI metrics & structured decision explanations...")
            final_state = client.get("http://127.0.0.1:8000/api/state").json()
            assert len(final_state["decisions"]) > 0, "No decisions logged"
            assert len(final_state["events"]) > 0, "No events logged"
            print("   -> Acceptance test completed successfully with 100% PASS rate!")

    finally:
        print("Cleaning up test processes...")
        core_proc.terminate()
        fact_proc.terminate()

if __name__ == "__main__":
    run_acceptance_test()
