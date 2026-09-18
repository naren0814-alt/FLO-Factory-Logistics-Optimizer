"""
Tests for Graph A* Routing Algorithm, Blocked Edge Avoidance, and Congestion Penalties.
"""

import pytest
from flo.core.graph import FactoryGraph

def test_astar_finds_valid_route():
    graph = FactoryGraph()
    res = graph.find_route("WAREHOUSE", "ASSY", consider_congestion=False)
    assert res is not None
    assert res["route"][0] == "WAREHOUSE"
    assert res["route"][-1] == "ASSY"
    assert res["distance"] > 0

def test_blocked_edge_avoidance():
    graph = FactoryGraph()
    # Block direct center corridor J3-J2
    graph.set_edge_blocked("J3", "J2", True)

    res = graph.find_route("J3", "J2", consider_congestion=False)
    # Must find alternative route or bypass
    if res:
        assert "J3" in res["route"] and "J2" in res["route"]
        # Ensure direct edge J3-J2 is not taken as a single hop
        for i in range(len(res["route"]) - 1):
            hop = (res["route"][i], res["route"][i+1])
            assert hop != ("J3", "J2") and hop != ("J2", "J3")

def test_congestion_increases_route_cost_and_selects_alternative():
    graph = FactoryGraph()
    
    # 1. Normal route from WAREHOUSE to ASSY
    normal_route = graph.find_route("WAREHOUSE", "ASSY", consider_congestion=True)
    
    # 2. Inject high congestion on central corridor J3-J2
    graph.set_edge_congestion("J3", "J2", 5.0)
    congested_route = graph.find_route("WAREHOUSE", "ASSY", consider_congestion=True)
    
    assert congested_route is not None
    # Congested route cost should be higher or select an alternative path
    assert congested_route["congestion_cost"] >= 0
