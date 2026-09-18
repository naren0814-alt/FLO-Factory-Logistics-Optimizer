"""
Tests for AGV Failure Recovery, Task Requeuing, and Dynamic Rerouting.
"""

import pytest
from flo.core.optimizer import FLOOptimizer
from flo.core.models import AGVStatus, TaskStatus

def test_agv_failure_reassigns_active_task():
    opt = FLOOptimizer()
    
    # Setup state
    agv1 = opt.agvs["AGV01"]
    agv2 = opt.agvs["AGV02"]
    task = opt.tasks["T001"]

    # Assign task to AGV01 initially
    opt.process_optimization_cycle()
    assert task.assigned_agv_id is not None
    assigned_agv_id = task.assigned_agv_id

    # Fail the assigned AGV
    opt.trigger_scenario_fail_agv(assigned_agv_id)

    # Check failed AGV state
    assert opt.agvs[assigned_agv_id].status == AGVStatus.FAILED

    # Task should be reassigned to another available operational AGV
    assert task.assigned_agv_id != assigned_agv_id
    assert task.status in [TaskStatus.ASSIGNED, TaskStatus.MOVING_TO_PICKUP]
