"""
Targeted Single Task Lifecycle Test.
Verifies the complete end-to-end task execution for 1 new task (WAREHOUSE -> DISPATCH).
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

def test_basic_task_lifecycle():
    print("====================================================")
    print("    TESTING BASIC TASK EXECUTION (SINGLE TASK)")
    print("====================================================")

    # 1. Kill leftover server processes
    kill_existing_servers()

    # 2. Launch fresh Core & Simulator with updated code
    print("[INIT] Launching fresh Session 1 (Core) and Session 2 (Simulator)...")
    core_proc = subprocess.Popen([sys.executable, "-m", "flo.api.server"], cwd="c:/Users/coolr/Documents/FLO")
    fact_proc = subprocess.Popen([sys.executable, "-m", "factory.api"], cwd="c:/Users/coolr/Documents/FLO")

    try:
        time.sleep(3.5)

        with httpx.Client(timeout=5.0) as client:
            # 3. Create 1 New Task: WAREHOUSE -> DISPATCH
            print("\n[STEP 1] Creating New Task: WAREHOUSE -> DISPATCH...")
            res_create = client.post("http://127.0.0.1:8001/api/task/create", json={
                "pickup": "WAREHOUSE",
                "destination": "DISPATCH",
                "priority": "NORMAL",
                "weight": 20.0,
                "deadline_seconds": 300.0
            })
            assert res_create.status_code == 200, f"Task creation API failed with status {res_create.status_code}"
            task_info = res_create.json()["task"]
            task_id = task_info["task_id"]
            print(f" -> Task Created Successfully: {task_id}")

            # 4. Wait and monitor execution progression over 35 seconds
            print("\n[STEP 2] Monitoring Task & AGV Execution Progress...")
            for i in range(70):
                time.sleep(0.5)
                sim_state = client.get("http://127.0.0.1:8001/api/simulator_state").json()
                
                # Check task status
                t_obj = next((t for t in sim_state["tasks"] if t["task_id"] == task_id), None)
                if t_obj:
                    agv_id = t_obj.get("assigned_agv_id")
                    agv_obj = next((a for a in sim_state["agvs"] if a["id"] == agv_id), None) if agv_id else None
                    agv_status = agv_obj["status"] if agv_obj else "UNASSIGNED"
                    
                    print(f" Tick {i+1:02d}: Task {task_id} Status: [{t_obj['status']}] | Assigned AGV: [{agv_id}] | AGV Status: [{agv_status}]")
                    
                    if t_obj["status"] == "COMPLETED" and agv_status == "AVAILABLE":
                        print("\n====================================================")
                        print(" SUCCESS: Task Completed & AGV returned to AVAILABLE!")
                        print("====================================================")
                        return

            raise AssertionError(f"Task {task_id} failed to reach COMPLETED state within 35 seconds")

    finally:
        try:
            core_proc.terminate()
            fact_proc.terminate()
        except Exception:
            pass

if __name__ == "__main__":
    test_basic_task_lifecycle()
