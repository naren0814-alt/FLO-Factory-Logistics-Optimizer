"""
Tests for Battery Feasibility, Energy Prediction, and Low Battery Rejection.
"""

import pytest
from flo.core.graph import FactoryGraph
from flo.core.battery import BatteryManager
from flo.core.assignment import AssignmentEngine
from flo.core.models import AGVModel, TaskModel, TaskPriority

def test_low_battery_agv_rejection():
    graph = FactoryGraph()
    bat_mgr = BatteryManager(graph)
    assign_engine = AssignmentEngine(graph, bat_mgr)

    task = TaskModel(task_id="T1", pickup="WAREHOUSE", destination="DISPATCH", weight=20.0)

    # AGV 1 is right at WAREHOUSE but only has 10% battery (infeasible)
    agv_low = AGVModel(id="AGV_LOW", name="Low Battery", current_node="WAREHOUSE", x=100, y=100, battery=10.0)
    
    # AGV 2 is farther away at J2 but has 80% battery (feasible)
    agv_ok = AGVModel(id="AGV_OK", name="Full Battery", current_node="J2", x=450, y=100, battery=80.0)

    best_agv, explanation, route_data = assign_engine.assign_best_agv(task, [agv_low, agv_ok])

    assert best_agv is not None
    assert best_agv.id == "AGV_OK"
    assert "Insufficient battery" in explanation.evaluations[0].reason
