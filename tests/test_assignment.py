"""
Tests for Two-Stage Assignment Engine, Feasibility Filters, and Payload Limits.
"""

import pytest
from flo.core.graph import FactoryGraph
from flo.core.battery import BatteryManager
from flo.core.assignment import AssignmentEngine
from flo.core.models import AGVModel, TaskModel, AGVStatus, TaskPriority, TaskStatus

def test_payload_capacity_filter():
    graph = FactoryGraph()
    bat_mgr = BatteryManager(graph)
    assign_engine = AssignmentEngine(graph, bat_mgr)

    # Task requires 60kg payload
    heavy_task = TaskModel(
        task_id="T_HEAVY", pickup="WAREHOUSE", destination="ASSY",
        weight=60.0, priority=TaskPriority.NORMAL
    )

    # AGV 1 has 30kg capacity, AGV 2 has 70kg capacity
    agv1 = AGVModel(id="AGV01", name="Light", current_node="WAREHOUSE", x=100, y=100, payload_capacity=30.0)
    agv2 = AGVModel(id="AGV02", name="Heavy", current_node="WAREHOUSE", x=100, y=100, payload_capacity=70.0)

    best_agv, explanation, route_data = assign_engine.assign_best_agv(heavy_task, [agv1, agv2])

    assert best_agv is not None
    assert best_agv.id == "AGV02"
    assert "Insufficient payload capacity" in explanation.evaluations[0].reason

def test_urgent_task_priority_scoring():
    graph = FactoryGraph()
    bat_mgr = BatteryManager(graph)
    assign_engine = AssignmentEngine(graph, bat_mgr)

    urgent_task = TaskModel(
        task_id="T_URGENT", pickup="WAREHOUSE", destination="ASSY",
        weight=10.0, priority=TaskPriority.URGENT
    )

    agv = AGVModel(id="AGV01", name="Test", current_node="WAREHOUSE", x=100, y=100)
    
    route_pickup = graph.find_route("WAREHOUSE", "WAREHOUSE", consider_congestion=False)
    route_dest = graph.find_route("WAREHOUSE", "ASSY", consider_congestion=False)
    
    is_feasible, result, _, _ = assign_engine.feasibility_checker.evaluate_agv(agv, urgent_task)
    score = assign_engine.calculate_score(agv, urgent_task, route_pickup, route_dest, result)
    
    normal_task = TaskModel(
        task_id="T_NORMAL", pickup="WAREHOUSE", destination="ASSY",
        weight=10.0, priority=TaskPriority.NORMAL
    )
    is_feasible_n, result_n, _, _ = assign_engine.feasibility_checker.evaluate_agv(agv, normal_task)
    normal_score = assign_engine.calculate_score(agv, normal_task, route_pickup, route_dest, result_n)

    # Urgent task score must be strictly lower (more prioritized) than normal task score
    assert score < normal_score
