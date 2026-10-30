"""Dispatcher decision-support tests (plan v2 §5b, §11)."""
from __future__ import annotations

import math
import sqlite3

import numpy as np
import pandas as pd
import pytest

from platform_api import alerts as book
from platform_api.engine.decision import Buffers, decision_window, tier_for
from platform_api.engine.deterioration import ShipmentSpec, StartState
from platform_api.engine.graph import build
from platform_api.engine.routing import Conditions, Disruption, evaluate, plan_route
from platform_api.store import SCHEMA


def ladder():
    """A main road 0-1-2-3-4-5 with a parallel bypass reachable from nodes 1, 2 and 3 (via 6, 7, 8) to 5."""
    xs = [0, 1, 2, 3, 4, 5, 1.5, 2.5, 3.5]
    ys = [0, 0, 0, 0, 0, 0, 0.3, 0.3, 0.3]
    nodes = pd.DataFrame({"lon": [x * 0.3 for x in xs], "lat": [y * 0.3 for y in ys]})
    rows = []
    def e(i, u, v, km):
        return {"edge_id": i, "u": u, "v": v, "way_id": i, "highway": "trunk", "ref": f"NH{i}", "name": "", "len_m": km * 1000,
                "speed_kmh": 45.0, "speed_src": "class_default", "oneway": 0, "hgv_no": 0, "rough": 3.0,
                "rough_src": "class_default", "rank": 0,
                "geom": np.array([nodes.lon[u], nodes.lat[u], nodes.lon[v], nodes.lat[v]])}
    main = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)]
    for i, (u, v) in enumerate(main):
        rows.append(e(i, u, v, 30))
    side = [(1, 6, 25), (6, 7, 30), (2, 7, 25), (7, 8, 30), (3, 8, 25), (8, 5, 50)]
    for j, (u, v, km) in enumerate(side):
        rows.append(e(10 + j, u, v, km))
    return build(nodes, pd.DataFrame(rows))


@pytest.fixture
def g():
    return ladder()


@pytest.fixture
def route(g):
    p = plan_route(g, 0, 5, ShipmentSpec(crop="tomato", kg=10000), Conditions(), [])
    return p.original.eval.arcs


SPEC = ShipmentSpec(crop="tomato", kg=10000, vehicle="open_truck")


def test_no_alert_when_truck_clears_before_disruption(g, route):
    d = [Disruption("late", "closure", [4], start_h=40)]
    w = decision_window(g, route, 0, StartState(), 5, SPEC, Conditions(), d)
    assert not w.needed and w.tier == "NONE"


def test_closure_needs_decision_with_deadline_before_pnr(g, route):
    buf = Buffers()
    w = decision_window(g, route, 0, StartState(), 5, SPEC, Conditions(), [Disruption("c", "closure", [4])], buffers=buf)
    assert w.needed and not w.stay_feasible
    assert math.isclose(w.deadline_h, w.pnr.eta_lo_h - buf.driver_h, rel_tol=1e-9)
    assert math.isclose(w.alert_at_h, w.deadline_h - buf.review / 60, rel_tol=1e-9)
    # PNR is the last junction before the closure (node 4): the roads are two-way, so the truck can still turn
    # back there to the bypass at node 3. Diverting earlier is cheaper, which the benefit curve shows.
    assert w.pnr.node == 4
    by_node = {o.node: o for o in w.options}
    assert by_node[3].net_value_rs > by_node[4].net_value_rs


def test_pnr_matches_brute_force(g, route):
    dis = [Disruption("c", "closure", [4])]
    w = decision_window(g, route, 0, StartState(), 5, SPEC, Conditions(), dis, max_exact=50)
    # brute force: for every junction ahead, is there any feasible way to 5 avoiding edge 4 from there?
    feasible_nodes = []
    for i in range(1, len(route)):
        node = int(g.a_from[route[i]])
        p = plan_route(g, node, 5, SPEC, Conditions(), dis)
        if p.recommended is not None and p.recommended.eval.feasible:
            feasible_nodes.append(node)
    assert w.pnr.node == feasible_nodes[-1]


def test_options_expire_as_truck_advances_and_tier_tightens(g, route):
    dis = [Disruption("c", "closure", [4])]
    w0 = decision_window(g, route, 0, StartState(), 5, SPEC, Conditions(), dis)
    pos = 2   # truck now starting edge 2-3: junctions 1 and 2 are behind it
    ev = evaluate(g, route[:pos], SPEC, Conditions(), [], include_wait=False)
    st = StartState(t_h=ev.outcome.hours, neg_ln_q=-math.log(ev.outcome.q_arrival), km=ev.distance_km)
    w2 = decision_window(g, route, pos, st, 5, SPEC, Conditions(), dis)
    nodes0 = {o.node for o in w0.options}
    nodes2 = {o.node for o in w2.options}
    assert {1, 2} & nodes0 and not ({1, 2} & nodes2)
    assert w2.slack_min < w0.slack_min


def test_tiers():
    b = Buffers(review=4)
    assert tier_for(-1, b) == "EXPIRED" and tier_for(3, b) == "CRITICAL" and tier_for(10, b) == "HIGH"
    assert tier_for(40, b) == "ADVISORY" and tier_for(120, b) == "MONITOR"


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def test_queue_is_edf_with_workload_warning_and_hysteresis(g, route):
    c = _db()
    dis = [Disruption("c", "closure", [4])]
    w = decision_window(g, route, 0, StartState(), 5, SPEC, Conditions(), dis)
    a1 = book.upsert(c, "A", w, 0.0, [o.arcs for o in w.options])
    # second shipment with an earlier deadline
    w_b = decision_window(g, route, 0, StartState(), 5, SPEC, Conditions(), dis)
    w_b.deadline_h = w.deadline_h - 0.5
    book.upsert(c, "B", w_b, 0.0, [o.arcs for o in w_b.options])
    q = book.queue(c, 0.0, Buffers(review=4))
    assert [a["shipment_id"] for a in q["alerts"]] == ["B", "A"]
    q_slow = book.queue(c, 0.0, Buffers(review=60 * w.deadline_h))
    assert q_slow["at_risk"] and q_slow["warning"]
    # same window again: no duplicate alert, no re-alert event
    n_events = c.execute("SELECT COUNT(*) FROM alert_events").fetchone()[0]
    book.upsert(c, "A", w, 0.01, [o.arcs for o in w.options])
    assert c.execute("SELECT COUNT(*) FROM alerts WHERE shipment_id='A'").fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM alert_events").fetchone()[0] == n_events
    assert a1["state"] == "ALERTED"


def test_no_reroute_without_approval_and_ack(g, route):
    c = _db()
    w = decision_window(g, route, 0, StartState(), 5, SPEC, Conditions(), [Disruption("c", "closure", [4])])
    a = book.upsert(c, "A", w, 0.0, [o.arcs for o in w.options])
    with pytest.raises(ValueError):
        book.act(c, a["id"], "execute", 0.1, "test")          # cannot execute an unapproved alert
    with pytest.raises(ValueError):
        book.act(c, a["id"], "send", 0.1, "test")             # cannot send before approval
    assert not book.AUTO_APPROVE_ON_TIMEOUT
    book.act(c, a["id"], "approve", 0.1, "test")
    book.act(c, a["id"], "send", 0.12, "test")
    r = book.act(c, a["id"], "acknowledge", 0.2, "test")
    assert r["state"] == "ACKNOWLEDGED"


def test_unanswered_alert_expires_and_truck_keeps_route(g, route):
    c = _db()
    w = decision_window(g, route, 0, StartState(), 5, SPEC, Conditions(), [Disruption("c", "closure", [4])])
    a = book.upsert(c, "A", w, 0.0, [o.arcs for o in w.options])
    q = book.queue(c, w.deadline_h + 0.01, Buffers())
    assert not q["alerts"]
    assert c.execute("SELECT state FROM alerts WHERE id=?", (a["id"],)).fetchone()[0] == "EXPIRED"
    with pytest.raises(ValueError):
        book.act(c, a["id"], "approve", w.deadline_h + 0.02, "test")


def test_past_deadline_offers_only_reachable_options(g, route):
    dis = [Disruption("c", "closure", [4])]
    w0 = decision_window(g, route, 0, StartState(), 5, SPEC, Conditions(), dis)
    late = w0.options[0].deadline_h + 0.01     # first junction's window has closed, PNR's has not
    w = decision_window(g, route, 0, StartState(t_h=0), 5, SPEC, Conditions(), dis, now_h=late)
    assert all(o.deadline_h >= late for o in w.options if o.reachable)
