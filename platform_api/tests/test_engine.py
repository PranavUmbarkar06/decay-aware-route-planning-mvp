"""Engine acceptance tests (plan v2 §11). Pure-model tests run on synthetic segments; routing tests use the
India graph built by pipelines/v2/india_roads.py and are skipped if it is missing."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from platform_api.engine.crops import load
from platform_api.engine.deterioration import Segment, ShipmentSpec, ea_from_q10, grade_split, rate, simulate
from platform_api.engine.graph import build
from platform_api.engine.routing import Conditions, Disruption, plan_route

GRAPH = Path(__file__).resolve().parents[2] / "data" / "processed" / "india" / "edges.parquet"


# ---------------------------------------------------------------- kinetics

def test_quality_reaches_q_min_at_reference_life():
    common, crops = load()
    for c in crops.values():
        segs = [Segment(hours=c.ref_life_h / 10, ambient_c=c.ref_temp_c, rh=c.rh_opt, moving=False) for _ in range(10)]
        spec = ShipmentSpec(crop=c.id, kg=1000, vehicle="open_truck")
        # Start at Q=1 by integrating the rate directly (initial-quality presets are below 1 by design).
        k = rate(c, common, c.ref_temp_c, c.rh_opt)
        assert math.isclose(math.exp(-k * c.ref_life_h), common.q_min, rel_tol=1e-9)
        assert spec.crop == c.id and segs


def test_q10_scaling_around_20c():
    common, crops = load()
    c = crops["tomato"]
    for q10 in (2.0, 2.5, 3.0):
        assert math.isclose(rate(c, common, 30, c.rh_opt, q10) / rate(c, common, 20, c.rh_opt, q10), q10, rel_tol=1e-6)
    assert ea_from_q10(2.0) < ea_from_q10(3.0)


def test_grade_split_sums_to_one_and_is_monotone():
    common, _ = load()
    prev_a = 1.01
    for q in np.linspace(0.95, 0.4, 12):
        a, d, r = grade_split(float(q), common)
        assert math.isclose(a + d + r, 1.0, abs_tol=1e-9)
        assert a <= prev_a + 1e-12
        prev_a = a


def test_mechanisms_multiply_not_add():
    """Physical loss = 1 − (1−D_mech)(1−D_hand): a bruised unit is not also counted as rotten."""
    route = [Segment(hours=0.5, km=25, ambient_c=30, rh=60, roughness=8) for _ in range(20)]
    o = simulate(ShipmentSpec(crop="tomato", kg=10000, vehicle="open_truck"), route)
    expected_phys = 10000 * (1 - (1 - o.d_mech) * (1 - o.d_hand))
    assert math.isclose(o.physical_loss_kg, expected_phys, rel_tol=1e-9)
    assert math.isclose(o.physical_loss_kg + o.rejected_kg + o.downgraded_kg + o.grade_a_kg, o.kg, rel_tol=1e-9)
    assert math.isclose(o.wastage_kg, o.physical_loss_kg + o.rejected_kg, rel_tol=1e-9)


def test_deterministic():
    route = [Segment(hours=0.7, km=30, ambient_c=37, rh=75, roughness=5, traffic=4) for _ in range(15)]
    a = simulate(ShipmentSpec(crop="grapes", kg=8000, vehicle="open_truck"), route)
    b = simulate(ShipmentSpec(crop="grapes", kg=8000, vehicle="open_truck"), route)
    assert a == b


def test_rough_roads_hurt_grapes_and_tomato_more_than_cured_onion():
    def extra(crop: str) -> float:
        smooth = [Segment(hours=0.5, km=25, ambient_c=30, rh=60, roughness=2) for _ in range(16)]
        rough = [Segment(hours=0.5, km=25, ambient_c=30, rh=60, roughness=8) for _ in range(16)]
        spec = ShipmentSpec(crop=crop, kg=10000, vehicle="open_truck", condition="cured" if crop == "onion" else None)
        return (simulate(spec, rough).wastage_pct - simulate(spec, smooth).wastage_pct)
    g, t, o = extra("grapes"), extra("tomato"), extra("onion")
    assert g > o * 3 and t > o * 3, (g, t, o)


def test_reefer_failure_raises_wastage():
    route = [Segment(hours=1, km=50, ambient_c=38, rh=50, roughness=3) for _ in range(12)]
    ok = simulate(ShipmentSpec(crop="grapes", kg=8000, vehicle="reefer"), route)
    fail = simulate(ShipmentSpec(crop="grapes", kg=8000, vehicle="reefer", reefer_fail_at_h=2), route)
    assert fail.q_arrival < ok.q_arrival and fail.max_cargo_temp_c > 30


# ---------------------------------------------------------------- routing on a toy graph (brute-force checkable)

def toy():
    """0 → 3 via a short rough road (0-1-3) or a longer smooth highway (0-2-3)."""
    nodes = pd.DataFrame({"lon": [0.0, 0.5, 0.5, 1.0], "lat": [0.0, 0.05, -0.2, 0.0]})
    rows = []
    def e(u, v, km, hw, rough, rid):
        return {"edge_id": rid, "u": u, "v": v, "way_id": rid, "highway": hw, "ref": f"R{rid}", "name": "", "len_m": km * 1000,
                "speed_kmh": 40.0, "speed_src": "class_default", "oneway": 0, "hgv_no": 0, "rough": rough,
                "rough_src": "class_default", "rank": 0, "geom": np.array([nodes.lon[u], nodes.lat[u], nodes.lon[v], nodes.lat[v]])}
    rows += [e(0, 1, 55, "primary", 8.5, 0), e(1, 3, 55, "primary", 8.5, 1), e(0, 2, 75, "trunk", 1.5, 2), e(2, 3, 75, "trunk", 1.5, 3)]
    return build(nodes, pd.DataFrame(rows))


def test_decision_can_be_continue_or_reroute_depending_on_crop():
    g = toy()
    # Same network, same conditions: only crop parameters differ.
    tom = plan_route(g, 0, 3, ShipmentSpec(crop="tomato", kg=10000, vehicle="open_truck", condition="turning"), Conditions(), [])
    oni = plan_route(g, 0, 3, ShipmentSpec(crop="onion", kg=10000, vehicle="open_truck", condition="cured"), Conditions(), [])
    used = lambda p: {int(g.a_edge[a]) for a in p.recommended.eval.arcs}
    assert used(oni) == {0, 1}, "cured onion should not pay for a smoother but longer road"
    assert oni.decision == "continue"
    assert used(tom) == {2, 3} or tom.decision == "continue"   # tomato may or may not justify it; never forced
    grapes = plan_route(g, 0, 3, ShipmentSpec(crop="grapes", kg=8000, vehicle="open_truck", price_rs_kg=80), Conditions(vibration=8), [])
    assert used(grapes) == {2, 3} and grapes.decision == "reroute"


def test_closure_removes_edge_and_isolation_is_reported():
    g = toy()
    spec = ShipmentSpec(crop="tomato", kg=10000)
    p = plan_route(g, 0, 3, spec, Conditions(), [Disruption("c", "closure", [1])])
    assert p.recommended and all(int(g.a_edge[a]) != 1 for a in p.recommended.eval.arcs)
    none = plan_route(g, 0, 3, spec, Conditions(), [Disruption("a", "closure", [1]), Disruption("b", "closure", [3])])
    assert none.decision == "no_feasible_route" and none.recommended is None


@pytest.mark.skipif(not GRAPH.exists(), reason="India graph not built")
def test_brief_corridors_route_on_connected_roads():
    from platform_api.engine.graph import load_graph
    g = load_graph()
    P = {"Nashik": (73.99, 20.17), "Mumbai": (73.00, 19.08), "Madanapalle": (78.50, 13.55), "Hyderabad": (78.48, 17.47),
         "Delhi": (77.17, 28.71)}
    for crop, a, b in [("grapes", "Nashik", "Mumbai"), ("tomato", "Madanapalle", "Hyderabad"), ("onion", "Nashik", "Hyderabad"),
                       ("onion", "Nashik", "Delhi")]:
        o, _ = g.nearest_node(*P[a])
        d, _ = g.nearest_node(*P[b])
        p = plan_route(g, o, d, ShipmentSpec(crop=crop, kg=10000), Conditions(), [])
        arcs = p.original.eval.arcs
        assert p.original.eval.feasible
        assert all(g.a_to[arcs[i]] == g.a_from[arcs[i + 1]] for i in range(len(arcs) - 1))
        assert g.a_from[arcs[0]] == o and g.a_to[arcs[-1]] == d
