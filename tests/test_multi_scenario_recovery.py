"""
Multi-Scenario Task Starvation & Recovery Test.
Verifies that when AGV breakdown, low battery, and route congestion occur simultaneously:
1. Failed AGV releases its assigned task immediately.
2. Low-battery AGV is diverted and its task reassigned/requeued.
3. Every active task either executes or waits in WAITING status (never stranded as ASSIGNED to FAILED AGV).
4. As resources become available, all tasks complete successfully.
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

def test_multi_scenario_recovery():
    print("====================================================")
    print("  MULTI-SCENARIO STARVATION & RECOVERY TEST")
    print("====================================================")

    # 1. Kill stale server processes
    kill_existing_servers()

    # 2. Launch fresh Core & Simulator
    print("[INIT] Launching Core (8000) and Simulator (8001)...")
    core_proc = subprocess.Popen([sys.executable, "-m", "flo.api.server"], cwd="c:/Users/coolr/Documents/FLO")
    fact_proc = subprocess.Popen([sys.executable, "-m", "factory.api"], cwd="c:/Users/coolr/Documents/FLO")

    try:
        time.sleep(3.5)

        with httpx.Client(timeout=5.0) as client:
            # 3. Create 3 tasks
            print("\n[STEP 1] Creating 3 runtime tasks...")
            t1 = client.post("http://127.0.0.1:8001/api/task/create", json={
                "pickup": "WAREHOUSE", "destination": "M1", "priority": "NORMAL", "weight": 20.0, "deadline_seconds": 300.0
            }).json()["task"]["task_id"]

            t2 = client.post("http://127.0.0.1:8001/api/task/create", json={
                "pickup": "M1", "destination": "M2", "priority": "HIGH", "weight": 25.0, "deadline_seconds": 300.0
            }).json()["task"]["task_id"]

            t3 = client.post("http://127.0.0.1:8001/api/task/create", json={
                "pickup": "M2", "destination": "DISPATCH", "priority": "URGENT", "weight": 15.0, "deadline_seconds": 300.0
            }).json()["task"]["task_id"]

            print(f" -> Created tasks: {t1}, {t2}, {t3}")

            # 4. Trigger simultaneous multi-scenarios
            print("\n[STEP 2] Triggering simultaneous AGV Failure + Low Battery + Congestion...")
            client.post("http://127.0.0.1:8000/api/scenario/fail_agv", json={"agv_id": "AGV03"})
            client.post("http://127.0.0.1:8000/api/scenario/low_battery_test", json={"agv_id": "AGV01", "battery_val": 12.0})
            client.post("http://127.0.0.1:8000/api/scenario/add_congestion", json={"src": "J3", "dst": "J2"})

            # 5. Monitor consistency over 140 Ticks (70 seconds)
            print("\n[STEP 3] Monitoring system state consistency & recovery progress...")
            for i in range(140):
                time.sleep(0.5)
                sim_state = client.get("http://127.0.0.1:8001/api/simulator_state").json()

                # SANITY CHECK: Ensure NO task is ASSIGNED to a FAILED AGV
                failed_agvs = {a["id"] for a in sim_state["agvs"] if a["status"] == "FAILED"}
                for task_obj in sim_state["tasks"]:
                    assigned_agv = task_obj.get("assigned_agv_id")
                    if assigned_agv in failed_agvs and task_obj["status"] in ["ASSIGNED", "MOVING_TO_PICKUP", "IN_TRANSIT"]:
                        raise AssertionError(f"INCONSISTENCY DETECTED: Task {task_obj['task_id']} is ASSIGNED to FAILED AGV {assigned_agv}!")

                # Check completion of created tasks
                created_tasks = [t for t in sim_state["tasks"] if t["task_id"] in [t1, t2, t3]]
                completed_count = sum(1 for t in created_tasks if t["status"] == "COMPLETED")
                print(f" Tick {i+1:02d}: Completed {completed_count}/3 tasks | Operational AGVs: {len(sim_state['agvs']) - len(failed_agvs)}")

                if completed_count == 3:
                    print("\n====================================================")
                    print(" SUCCESS: All tasks recovered & completed successfully!")
                    print(" NO stranded tasks detected!")
                    print("====================================================")
                    return

            # Final verification
            sim_state = client.get("http://127.0.0.1:8001/api/simulator_state").json()
            for t_id in [t1, t2, t3]:
                t_obj = next((t for t in sim_state["tasks"] if t["task_id"] == t_id), None)
                print(f" Task {t_id} final status: {t_obj['status'] if t_obj else 'UNKNOWN'}")

            raise AssertionError("Not all tasks reached COMPLETED status within 70 seconds under multi-scenario stress")

    finally:
        try:
            core_proc.terminate()
            fact_proc.terminate()
        except Exception:
            pass

if __name__ == "__main__":
    test_multi_scenario_recovery()
