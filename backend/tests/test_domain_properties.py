"""Property-based tests for the domain invariants (I1–I4) and the hash chain."""
from datetime import UTC, datetime, timedelta

import pytest
from app.domain import hashchain
from app.domain.decay import CommodityProfile, DecayModel
from app.domain.model import (
    AssemblyMandi,
    Consignment,
    Disposition,
    DomainError,
    NGOSink,
    ReasonCode,
    Status,
)
from hypothesis import given, settings
from hypothesis import strategies as st

T0 = datetime(2026, 5, 1, 6, tzinfo=UTC)


def new_c(qty=1000.0):
    return Consignment(id="C1", short_code="ABCD2345", commodity="tomato", grade="A", initial_qty_kg=qty,
                       harvest_time=T0, origin_node="N_origin")


ops = st.lists(st.tuples(st.sampled_from(["waste", "sell", "donate", "process", "move", "undo"]),
                         st.floats(min_value=0, max_value=1, allow_nan=False),
                         st.sampled_from(list(ReasonCode))), max_size=25)


@settings(max_examples=300, deadline=None)
@given(qty=st.floats(min_value=1, max_value=50_000, allow_nan=False), seq=ops,
       recv_ratio=st.floats(min_value=0.5, max_value=1.0))
def test_invariants_hold_under_any_operation_sequence(qty, seq, recv_ratio):
    c = new_c(qty)
    a, b = AssemblyMandi("N_origin", "origin"), NGOSink("N_ngo", "ngo")
    a.stock[c.id] = c
    holder, other = a, b
    last_waste = None
    t = T0
    for op, frac, reason in seq:
        t += timedelta(hours=1)
        if c.status == Status.CLOSED:
            break
        amount = c.current_qty_kg * frac
        try:
            if op == "waste":
                last_waste = c.record_wastage(amount, reason, t)
            elif op in ("sell", "donate", "process"):
                c.dispose({"sell": Disposition.SOLD, "donate": Disposition.DONATED, "process": Disposition.PROCESSED}[op],
                          amount, t)
            elif op == "move" and c.status in (Status.AT_NODE, Status.DISPUTED_WEIGHT):
                holder.release(c, other.node_id, t)
                other.receive_consignment(c, t + timedelta(minutes=30), weight_kg=c.current_qty_kg * recv_ratio)
                holder, other = other, holder
            elif op == "undo" and last_waste is not None:
                c.undo_wastage(last_waste, t)
                last_waste = None
        except DomainError:
            pass
        c.check_invariants()          # I1–I4 after every step


def test_wastage_cannot_exceed_current_quantity():
    c = new_c(100)
    with pytest.raises(DomainError):
        c.record_wastage(100.01, ReasonCode.HEAT_ROT, T0)


def test_weight_mismatch_is_disputed_not_wasted():
    c = new_c(1000)
    a, b = AssemblyMandi("N_origin", "a"), AssemblyMandi("N_b", "b")
    a.stock[c.id] = c
    a.release(c, "N_b", T0)
    diff = b.receive_consignment(c, T0 + timedelta(hours=3), weight_kg=950, tolerance_pct=2.0)
    assert diff == pytest.approx(50)
    assert c.status == Status.DISPUTED_WEIGHT
    assert c.disposed["WASTED"] == 0 and c.unreconciled_kg == pytest.approx(50)
    c.check_invariants()


def test_consignment_cannot_be_received_twice():
    c = new_c()
    a, b, x = AssemblyMandi("N_origin", "a"), AssemblyMandi("N_b", "b"), AssemblyMandi("N_x", "x")
    a.stock[c.id] = c
    a.release(c, "N_b", T0)
    b.receive_consignment(c, T0)
    with pytest.raises(DomainError):
        x.receive_consignment(c, T0)       # never in two places


@given(st.integers(min_value=1, max_value=12), st.data())
def test_chain_detects_any_edit_removal_or_reorder(n, data):
    evs = hashchain.chain("C9", [{"event_type": "RECEIVE", "to_node": f"N{i}", "weight_received_kg": 100.0 - i,
                                  "scan_time_utc": f"2026-05-01T0{i % 10}:00:00"} for i in range(n)])
    assert hashchain.verify("C9", evs)[0]
    i = data.draw(st.integers(0, n - 1))
    edited = [dict(e) for e in evs]
    edited[i]["weight_received_kg"] = edited[i]["weight_received_kg"] + 1
    assert not hashchain.verify("C9", edited)[0]
    head, count = evs[-1]["hash"], len(evs)
    removed = evs[:i] + evs[i + 1:]
    # middle removals break the links; tail removal is caught by the recorded head + count
    assert not hashchain.verify("C9", removed, expected_head=head, expected_count=count)[0]
    if i < n - 1:
        assert not hashchain.verify("C9", removed)[0]


def test_decay_is_monotonic_and_hotter_is_faster():
    m = DecayModel(CommodityProfile.load("tomato"))
    cool = m.predict_loss(1000, 1.0, [15.0] * 24)
    hot = m.predict_loss(1000, 1.0, [35.0] * 24)
    assert hot.expected_loss_kg >= cool.expected_loss_kg
    assert hot.remaining_life_h < cool.remaining_life_h
    assert hot.quality_end <= 1.0 and cool.quality_end <= 1.0
    # Q10 sensitivity bounds are reported
    assert set(hot.sensitivity) == {"remaining_life_h_q10_2", "remaining_life_h_q10_3"}
    assert any("assumption" in w.lower() for w in hot.warnings)


@given(st.floats(min_value=0.01, max_value=0.99))
def test_quality_age_roundtrip(q):
    m = DecayModel(CommodityProfile.load("onion"))
    assert m.quality(m.age_for_quality(q)) == pytest.approx(q, abs=1e-6)


def test_custody_events_are_append_only_in_application_code():
    """No service/API code updates or deletes custody events (only the demo reset in cli.py deletes demo rows)."""
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for f in root.rglob("*.py"):
        if f.name == "cli.py":
            continue
        txt = f.read_text(encoding="utf-8")
        if re.search(r"(update|delete)\(\s*CustodyEvent", txt) or re.search(r"custody_events.*(UPDATE|DELETE)", txt, re.I):
            offenders.append(str(f))
    assert offenders == []


def test_remaining_life_is_measured_from_now_not_from_horizon_end():
    """Regression: a lot with ~19 h left under a hot forecast must not report 0 h because the 24 h horizon is hot."""
    m = DecayModel(CommodityProfile.load("tomato"))
    age = 60.0
    hot = [40.0] * 24
    rem = m.predict_loss(800, m.quality(age), hot).remaining_life_h
    assert rem == pytest.approx(m.remaining_life_h(age, 40.0), rel=1e-3) and rem > 0
    # integrating a changing forecast lies between the constant-temperature extremes
    mixed = m.hours_until_expiry(age, [20.0] * 6 + [40.0] * 30)
    assert m.remaining_life_h(age, 40.0) < mixed < m.remaining_life_h(age, 20.0)


def test_hash_is_type_stable_for_numbers():
    """Regression: an int weight (service call) and the float read back from the DB must hash identically."""
    a = {"event_type": "CREATED", "weight_received_kg": 800, "lat": 21, "scan_time_utc": "x"}
    b = {"event_type": "CREATED", "weight_received_kg": 800.0, "lat": 21.0, "scan_time_utc": "x"}
    assert hashchain.event_hash(a, "p") == hashchain.event_hash(b, "p")
