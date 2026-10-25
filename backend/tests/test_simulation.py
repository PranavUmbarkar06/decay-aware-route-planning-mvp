"""Simulation checks (deck S8 validation checkpoints). Engineering runs use seed 1 on a short March window, which is
outside the pre-registered seeds and seasons, so tests never touch the registered experiment."""
import hashlib

import pandas as pd
import pytest
from app.simulation.engine import Engine
from app.simulation.network import load_network
from app.simulation.policies import make_policy
from app.simulation.scenario import build_scenario

DEV = dict(season="dev", start="2026-03-02", days=3, seed=1, commodities=["tomato", "orange", "onion"])


@pytest.fixture(scope="module")
def net():
    return load_network()


def _events_sha(r) -> str:
    return hashlib.sha256(pd.DataFrame(r.events).to_csv(index=False).encode()).hexdigest()


def test_baseline_is_reproducible_bit_for_bit(net):
    shas, metrics = [], []
    for _ in range(2):
        sc = build_scenario(net, **DEV)                      # rebuilt from the seed each time
        r = Engine(net, sc, make_policy("StaticShortestPath")).run()
        shas.append(_events_sha(r))
        metrics.append(r.metrics)
    assert shas[0] == shas[1]
    assert metrics[0] == metrics[1]


def test_proposed_is_deterministic_too(net):
    a = Engine(net, build_scenario(net, **DEV), make_policy("QualityAwareDynamic")).run()
    b = Engine(net, build_scenario(net, **DEV), make_policy("QualityAwareDynamic")).run()
    assert _events_sha(a) == _events_sha(b)


@pytest.mark.parametrize("policy", ["StaticShortestPath", "QualityAwareDynamic"])
def test_mass_balance_holds_every_tick(net, policy):
    r = Engine(net, build_scenario(net, **DEV), make_policy(policy)).run()
    bal = pd.DataFrame(r.balance)
    assert len(bal) == build_scenario(net, **DEV).ticks
    assert bal["error_kg"].abs().max() < 1e-6 * max(1.0, bal["injected"].max())
    assert (bal[["sold", "donated", "processed", "wasted", "in_market", "in_transit"]] >= -1e-9).all().all()
    m = r.metrics
    assert m["wastage_rate"] == pytest.approx(m["wasted_kg"] / m["injected_kg"])


def test_the_only_difference_between_paired_runs_is_the_policy(net):
    a, b = build_scenario(net, **DEV), build_scenario(net, **DEV)
    assert a.lots == b.lots and a.demand == b.demand and a.disruptions == b.disruptions
    assert (a.class_hour_mult == b.class_hour_mult).all() and (a.edge_factor == b.edge_factor).all()
    assert (a.temps == b.temps).all()
    ra = Engine(net, a, make_policy("StaticShortestPath")).run()
    rb = Engine(net, b, make_policy("QualityAwareDynamic")).run()
    assert ra.metrics["injected_kg"] == rb.metrics["injected_kg"]


def test_baseline_never_reroutes_or_redirects(net):
    r = Engine(net, build_scenario(net, **DEV), make_policy("StaticShortestPath")).run()
    assert r.metrics["reroute_count"] == 0 and r.metrics["redirect_count"] == 0


def test_decisions_carry_reasons(net):
    r = Engine(net, build_scenario(net, **DEV), make_policy("QualityAwareDynamic")).run()
    dec = [e for e in r.events if e["event"] == "DECISION"]
    assert dec and all(e["reasons"] for e in dec)


def test_no_isolated_or_demo_nodes_in_experiments(net):
    assert all(b.provenance != "SYNTHETIC_DEMO" for b in net.business.values())
    assert net.n > 0 and len(net.eu) > 0
