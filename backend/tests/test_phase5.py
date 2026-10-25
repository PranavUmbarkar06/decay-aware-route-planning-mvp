"""Phase 5: M3 thresholds + explanations, M4 crowd meter definition, M5 atomic claim + cascade + DONATED booking,
M6 score breakdown, M7 advisor (recommend only). Test NGOs are fictional nodes created only in the test database."""
import threading
from datetime import date, timedelta

import pytest
from app.core import db as dbmod
from app.models.orm import Consignment, NgoProfile, Node, RescueBroadcast, RescueOffer, User

PH = {"farmer": "+910000000001", "supervisor": "+910000000002", "warehouse": "+910000000003", "dispatcher": "+910000000004",
      "ngo": "+910000000005", "admin": "+910000000007"}


# ---------------------------------------------------------------- M3
@pytest.mark.parametrize("hours,light", [(0, "RED"), (23.9, "RED"), (24, "YELLOW"), (71.9, "YELLOW"), (72, "GREEN"), (500, "GREEN")])
def test_traffic_light_bands_have_no_gaps(hours, light):
    from app.services.shelf_life import traffic_light
    assert traffic_light(hours) == light


@pytest.fixture(scope="module")
def world(client, app_db):
    """Two fictional test NGOs near the supervisor, with profiles; a supervisor-held tomato lot."""
    from app.core.clock import now
    from app.core.ratelimit import limiter
    from app.services import custody

    with dbmod.session() as s:
        sup = s.query(User).filter_by(phone=PH["supervisor"]).one()
        home = s.get(Node, sup.home_node_id)
        ngo_ids = []
        for i, dlat in enumerate((0.05, 0.08)):
            nid = f"NTESTNGO{i}"
            s.add(Node(node_id=nid, node_type="NGOSink", name=f"Test NGO {i} DEMO", lat=home.lat + dlat, lon=home.lon,
                       district=home.district, provenance="SYNTHETIC_DEMO", source_manifest_id="test", needs_review=False))
            s.add(User(id=f"test-ngo-{i}", phone=f"+91000000008{i}", role="NGO", name=f"Test NGO user {i}", language="en",
                       home_node_id=nid, created_at=now(), provenance="SYNTHETIC_DEMO"))
            s.flush()
            s.add(NgoProfile(node_id=nid, user_id=f"test-ngo-{i}", accepted_commodities="onion,orange,tomato",
                             daily_capacity_kg=5000, pickup_start_ist=0, pickup_end_ist=24, can_collect=True,
                             provenance="SYNTHETIC_DEMO", updated_at=now()))
            ngo_ids.append(nid)
        s.commit()
        made = custody.create_consignment(s, sup, commodity="tomato", grade="B", qty_kg=800,
                                          harvest_time=now() - timedelta(hours=12), origin_node_id=sup.home_node_id)
        cid = made.consignment.id

    def tok(phone):
        limiter.reset()
        ch = client.post("/api/v1/auth/otp/request", json={"phone": phone}).json()
        return {"Authorization": "Bearer " + client.post("/api/v1/auth/otp/verify", json={"challenge_id": ch["challenge_id"],
                                                                                           "code": ch["dev_otp"]}).json()["token"]}
    return {"cid": cid, "ngos": ngo_ids, "sup": tok(PH["supervisor"]), "ngo0": tok("+910000000080"),
            "ngo1": tok("+910000000081"), "admin": tok(PH["admin"]), "disp": tok(PH["dispatcher"])}


def test_shelf_life_has_full_explanation(client, world):
    r = client.get(f"/api/v1/consignments/{world['cid']}/shelf-life", headers=world["sup"]).json()
    assert r["light"] in ("RED", "YELLOW", "GREEN")
    ex = r["explanation"]
    assert {"why", "inputs", "drivers", "parameters", "provenance", "thresholds", "warnings", "disclaimer"} <= set(ex)
    assert ex["inputs"]["temperature_history"]["provenance"] in ("REAL_FETCHED", "REAL_DERIVED", "ASSUMPTION")
    assert "not a food-safety certification" in ex["disclaimer"]
    assert r["safe_window_h"] <= r["remaining_life_h"]


def test_storage_view_is_fefo(client, world):
    from app.services import shelf_life
    node = client.get("/api/v1/me", headers=world["sup"]).json()["home_node_id"]
    r = client.get(f"/api/v1/storage/{node}/batches", headers=world["sup"]).json()
    lives = [b["remaining_life_h"] for b in r["batches"]]
    assert lives == sorted(lives) and r["order"].startswith("FEFO")
    assert shelf_life.fefo([{"remaining_life_h": 5, "qty_kg": 1, "short_code": "B"},
                            {"remaining_life_h": 2, "qty_kg": 1, "short_code": "A"}])[0]["short_code"] == "A"


# ---------------------------------------------------------------- M4
def test_crowd_meter_definition_and_states():
    from app.services import crowd
    m = crowd.meter("APMC Nagpur", "tomato", date(2026, 5, 4))
    assert "trailing" in m["definition"] and "Not a share of capacity" in m["definition"]
    assert m["status"] in ("NORMAL", "BUSY", "GLUT_WARNING", "STALE", "NO_BASELINE")
    assert crowd.meter("APMC Narkhed", "tomato", date(2026, 5, 4))["status"] == "NO_DATA"
    assert crowd.meter("APMC Nagpur", "tomato", date(2027, 1, 1))["status"] == "STALE"
    fc = crowd.forecast_demand("APMC Nagpur", "tomato", date(2026, 5, 4))
    assert fc.qty_kg and fc.provenance == "REAL_DERIVED"
    assert crowd.compute_gap(fc.qty_kg + 100, fc)["status"] == "SURPLUS"


def test_crowd_endpoint_never_shows_capacity(client, world):
    r = client.get("/api/v1/crowd", params={"commodity": "tomato", "on": "2026-05-04"}, headers=world["sup"]).json()
    assert r["markets"] and all("capacity" not in k for m in r["markets"] for k in m)


# ---------------------------------------------------------------- M6 + M5
def test_match_scores_have_breakdown(client, world):
    r = client.get(f"/api/v1/rescue/matches/{world['cid']}", headers=world["sup"]).json()
    assert r["matches"], r
    m = r["matches"][0]
    assert set(m["breakdown"]) == {"road_time", "life_margin", "capacity_fit"}
    assert abs(sum(v["contribution"] for v in m["breakdown"].values()) - m["score"]) < 1e-3


def test_two_ngos_claim_simultaneously_exactly_one_wins(client, world):
    r = client.post("/api/v1/rescue/broadcasts", headers=world["sup"], json={"consignment_id": world["cid"], "trigger": "UNSOLD"})
    assert r.status_code == 201, r.text
    b = r.json()
    offered = [o for o in b["offers"] if o["status"] == "OFFERED" and o["ngo_node_id"] in world["ngos"]]
    assert len(offered) == 2
    from app.services import rescue
    from app.services.custody import ServiceError
    results = []

    def go(user_id, offer_id):
        with dbmod.session() as s:
            try:
                rescue.claim(s, s.get(User, user_id), offer_id)
                results.append("won")
            except ServiceError as e:
                results.append(e.code)
    users = {o["ngo_node_id"]: f"test-ngo-{world['ngos'].index(o['ngo_node_id'])}" for o in offered}
    ts = [threading.Thread(target=go, args=(users[o["ngo_node_id"]], o["id"])) for o in offered]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert results.count("won") == 1, results
    with dbmod.session() as s:
        assert s.get(RescueBroadcast, b["id"]).status == "CLAIMED"
    world["broadcast"] = b["id"]


def test_claim_expiry_cascades_and_is_logged(world, monkeypatch):
    from app.services import rescue
    with dbmod.session() as s:
        b = s.get(RescueBroadcast, world["broadcast"])
        claimed = s.get(RescueOffer, b.claimed_offer_id)
        later = claimed.claim_expires_at + timedelta(minutes=1)
    monkeypatch.setattr(rescue, "now", lambda: later)
    with dbmod.session() as s:
        rescue.expire_due(s)
        b = s.get(RescueBroadcast, world["broadcast"])
        offers = {o.id: o.status for o in s.query(RescueOffer).filter_by(broadcast_id=b.id)}
        assert offers[claimed.id] == "CLAIM_EXPIRED"
        assert b.status in ("OPEN", "EXHAUSTED")
        from app.models.orm import AuditLog
        assert s.query(AuditLog).filter_by(action="rescue.claim_expired", entity_id=claimed.id).count() == 1


def test_pickup_handshake_books_donated_not_wasted(client, world):
    # fresh broadcast on the same lot → claim → handover to the NGO → DONATED
    with dbmod.session() as s:
        for b in s.query(RescueBroadcast).filter_by(consignment_id=world["cid"]):
            b.status = "CANCELLED"
        s.commit()
    b = client.post("/api/v1/rescue/broadcasts", headers=world["sup"], json={"consignment_id": world["cid"], "trigger": "UNSOLD"}).json()
    offer = next(o for o in b["offers"] if o["ngo_node_id"] == world["ngos"][0] and o["status"] == "OFFERED")
    assert client.post(f"/api/v1/rescue/offers/{offer['id']}/claim", headers=world["ngo1"]).status_code == 403  # not theirs
    r = client.post(f"/api/v1/rescue/offers/{offer['id']}/claim", headers=world["ngo0"])
    assert r.status_code == 200 and r.json()["status"] == "CLAIMED"
    c = client.get(f"/api/v1/consignments/{world['cid']}", headers=world["sup"]).json()
    h = client.post(f"/api/v1/consignments/{world['cid']}/handovers", headers=world["sup"],
                    json={"to_node_id": world["ngos"][0], "weight_kg": c["current_qty_kg"], "condition": "MINOR_DAMAGE"}).json()
    r = client.post(f"/api/v1/handovers/{h['id']}/confirm", headers=world["ngo0"], json={"weight_kg": c["current_qty_kg"], "condition": "MINOR_DAMAGE"})
    assert r.status_code == 200, r.text
    c2 = client.get(f"/api/v1/consignments/{world['cid']}", headers=world["sup"]).json()
    assert c2["status"] == "CLOSED" and c2["donated_kg"] == pytest.approx(c["current_qty_kg"]) and c2["wasted_kg"] == 0
    v = client.get(f"/api/v1/consignments/{world['cid']}/verify", headers=world["sup"]).json()
    assert v["mass_balance"]["holds"], v
    assert v["chain"]["ok"], v
    with dbmod.session() as s:
        assert s.get(RescueBroadcast, b["id"]).status == "COMPLETED"
        assert s.get(Consignment, world["cid"]).at_node_id is None
    stats = client.get("/api/v1/stats/dispositions", headers=world["admin"]).json()
    assert "SYNTHETIC_DEMO" in stats["by_provenance"] or "USER_ENTERED" in stats["by_provenance"]


def test_green_lot_cannot_be_broadcast_as_yellow(client, world, login):
    from app.core.clock import now
    f = login(PH["supervisor"])
    c = client.post("/api/v1/consignments", headers=f, json={"commodity": "onion", "qty_kg": 300,
                                                             "harvest_time": (now() - timedelta(hours=2)).isoformat(),
                                                             "origin_node_id": f.user["home_node_id"]}).json()["consignment"]
    r = client.post("/api/v1/rescue/broadcasts", headers=f, json={"consignment_id": c["id"], "trigger": "YELLOW"})
    assert r.status_code == 409 and r.json()["code"] == "too_fresh"


# ---------------------------------------------------------------- M7
def test_advisor_recommends_without_executing(client, world):
    from app.core.clock import now
    with dbmod.session() as s:
        disp = s.query(User).filter_by(phone=PH["dispatcher"]).one()
        before = s.query(Consignment).count()
    r = client.post("/api/v1/advisor/compare", headers=world["disp"],
                    json={"origin_node_id": disp.home_node_id, "commodity": "tomato", "qty_kg": 3000,
                          "harvest_time": (now() - timedelta(hours=20)).isoformat()})
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["action"] in ("ROUTE", "REROUTE", "REDIRECT")
    assert a["baseline"]["geometry"] and a["recommended"]["geometry"] and a["reasons"]
    assert "not observed traffic" in a["inputs"]["congestion"] and a["label"].startswith("Model output")
    assert set(a["recommended"]["quality_bounds"]) == {"q10_2", "q10_3"}
    with dbmod.session() as s:
        assert s.query(Consignment).count() == before


def test_live_stream_emits_ticks_for_both_policies(client, world):
    import json as _json
    with client.stream("GET", "/api/v1/sim/live", params={"start": "2026-03-02", "days": 2, "seed": 1, "pace_ms": 0},
                       headers=world["admin"]) as r:
        assert r.status_code == 200
        events = [_json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
    assert events[0]["type"] == "start" and "Not the pre-registered experiment" in events[0]["label"]
    ticks = [e for e in events if e["type"] == "tick"]
    assert len(ticks) == events[0]["ticks"]
    assert all(abs(e["baseline"]["balance_error_kg"]) < 1e-3 and abs(e["proposed"]["balance_error_kg"]) < 1e-3 for e in ticks)
    assert ticks[-1]["baseline"]["injected_kg"] == ticks[-1]["proposed"]["injected_kg"]   # identical inputs
    assert events[-1]["type"] == "end"
    assert client.get("/api/v1/sim/live", headers=world["sup"]).status_code == 403
