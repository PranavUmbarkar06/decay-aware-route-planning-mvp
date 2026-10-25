"""M1 (traceability + QR handshake) and M2 (wastage logger) through the HTTP API."""
import threading
from datetime import timedelta

import pytest
from sqlalchemy import text


def _clock_now():
    from app.core.clock import now
    return now()


PH = {"farmer": "+910000000001", "supervisor": "+910000000002", "warehouse": "+910000000003",
      "dispatcher": "+910000000004", "ngo": "+910000000005", "driver": "+910000000006", "admin": "+910000000007"}


def _now_minus(h):
    from app.core.clock import now
    return (now() - timedelta(hours=h)).isoformat()


@pytest.fixture(scope="module")
def flow(client):
    """Farmer creates a lot and hands it to the supervisor's mandi."""
    from app.core.ratelimit import limiter

    def tok(phone):
        limiter.reset()
        ch = client.post("/api/v1/auth/otp/request", json={"phone": phone}).json()
        r = client.post("/api/v1/auth/otp/verify", json={"challenge_id": ch["challenge_id"], "code": ch["dev_otp"]}).json()
        return {"Authorization": f"Bearer {r['token']}"}, r["user"]

    H = {k: tok(v) for k, v in PH.items()}
    farmer_h, farmer = H["farmer"]
    r = client.post("/api/v1/consignments", headers=farmer_h, json={
        "commodity": "tomato", "grade": "A", "qty_kg": 1000, "harvest_time": _now_minus(6),
        "origin_node_id": farmer["home_node_id"]})
    assert r.status_code == 201, r.text
    return {"H": H, "created": r.json()}


def test_create_returns_qr_and_pin_once(client, flow):
    c = flow["created"]
    assert c["qr_payload"] == f"PHL1:{c['consignment']['short_code']}" and c["qr_png"].startswith("data:image/png")
    assert len(c["pin"]) == 4 and c["pin"] not in c["qr_payload"]
    got = client.get(f"/api/v1/consignments/{c['consignment']['id']}", headers=flow["H"]["admin"][0]).json()
    assert "pin" not in got and "pin_hash" not in got


def test_two_party_handover_and_timeline(client, flow):
    H, cid = flow["H"], flow["created"]["consignment"]["id"]
    sup_h, sup = H["supervisor"]
    r = client.post(f"/api/v1/consignments/{cid}/handovers", headers=H["farmer"][0],
                    json={"to_node_id": sup["home_node_id"], "weight_kg": 1000, "condition": "GOOD"})
    assert r.status_code == 201, r.text
    hid = r.json()["id"]
    # the releaser cannot confirm their own handover; a non-receiver cannot either
    assert client.post(f"/api/v1/handovers/{hid}/confirm", headers=H["warehouse"][0],
                       json={"weight_kg": 1000, "condition": "GOOD"}).status_code == 403
    r = client.post(f"/api/v1/handovers/{hid}/confirm", headers=sup_h, json={"weight_kg": 990, "condition": "GOOD"})
    assert r.status_code == 200 and r.json()["status"] == "COMPLETED"           # 1% < 2% tolerance
    r = client.post(f"/api/v1/handovers/{hid}/confirm", headers=sup_h, json={"weight_kg": 990, "condition": "GOOD"})
    assert r.status_code == 409                                                  # single winner
    t = client.get(f"/api/v1/consignments/{cid}/timeline", headers=H["admin"][0]).json()
    assert [e["event_type"] for e in t["events"]] == ["CREATED", "RELEASE", "RECEIVE"]
    assert t["chain"]["ok"] and t["mass_balance"]["holds"]
    assert all(not p["inferred"] for p in t["path"])


def test_wastage_slider_guards_and_undo(client, flow):
    H, cid = flow["H"], flow["created"]["consignment"]["id"]
    sup_h = H["supervisor"][0]
    assert client.post(f"/api/v1/consignments/{cid}/wastage", headers=sup_h,
                       json={"amount_kg": 1e6, "reason_code": "HEAT_ROT"}).status_code == 422
    assert client.post(f"/api/v1/consignments/{cid}/wastage", headers=sup_h,
                       json={"amount_kg": 5, "reason_code": "MOLDY"}).status_code == 422
    assert client.post(f"/api/v1/consignments/{cid}/wastage", headers=H["farmer"][0],
                       json={"amount_kg": 5, "reason_code": "WET"}).status_code == 403
    r = client.post(f"/api/v1/consignments/{cid}/wastage", headers=sup_h, json={"amount_kg": 40, "reason_code": "HEAT_ROT"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["consignment"]["wasted_kg"] == 40 and body["consignment"]["current_qty_kg"] == 950
    r = client.post(f"/api/v1/wastage/{body['event']['id']}/undo", headers=sup_h)
    assert r.status_code == 200 and r.json()["event_type"] == "UNDO"
    assert client.post(f"/api/v1/wastage/{body['event']['id']}/undo", headers=sup_h).status_code == 409
    c = client.get(f"/api/v1/consignments/{cid}", headers=sup_h).json()
    assert c["wasted_kg"] == 0 and c["current_qty_kg"] == 990
    hist = client.get(f"/api/v1/consignments/{cid}/quality-history", headers=sup_h).json()
    assert [h["event_type"] for h in hist][-2:] == ["WASTAGE", "UNDO"] and hist[-2]["undone_at"]


def test_weight_mismatch_is_disputed_not_booked_as_waste(client, flow):
    H, cid = flow["H"], flow["created"]["consignment"]["id"]
    wh_h, wh = H["warehouse"]
    r = client.post(f"/api/v1/consignments/{cid}/handovers", headers=H["supervisor"][0],
                    json={"to_node_id": wh["home_node_id"], "weight_kg": 990, "condition": "GOOD"})
    hid = r.json()["id"]
    # driver scan while in transit (scan-only role), with an offline scan time preserved
    scan_t = _now_minus(1)
    r = client.post(f"/api/v1/consignments/{cid}/scan", headers=H["driver"][0], json={"lat": 21.1, "lon": 79.1, "scan_time": scan_t})
    assert r.status_code == 201 and r.json()["scan_time_utc"][:16] == scan_t[:16]
    r = client.post(f"/api/v1/handovers/{hid}/confirm", headers=wh_h, json={"weight_kg": 900, "condition": "MINOR_DAMAGE"})
    assert r.json()["status"] == "DISPUTED_WEIGHT" and r.json()["difference_kg"] == pytest.approx(90)
    c = client.get(f"/api/v1/consignments/{cid}", headers=wh_h).json()
    assert c["status"] == "DISPUTED_WEIGHT" and c["wasted_kg"] == 0 and c["unreconciled_kg"] == pytest.approx(100)
    v = client.get(f"/api/v1/consignments/{cid}/verify", headers=wh_h).json()
    assert v["chain"]["ok"] and v["mass_balance"]["holds"]


def test_tampering_is_detected(client, flow, app_db):
    cid = flow["created"]["consignment"]["id"]
    with app_db.begin() as conn:
        conn.execute(text("UPDATE custody_events SET weight_received_kg = 1200 WHERE consignment_id=:c AND seq=0"), {"c": cid})
    v = client.get(f"/api/v1/consignments/{cid}/verify", headers=flow["H"]["admin"][0]).json()
    assert not v["chain"]["ok"] and v["chain"]["first_bad_seq"] == 0
    with app_db.begin() as conn:
        conn.execute(text("UPDATE custody_events SET weight_received_kg = 1000 WHERE consignment_id=:c AND seq=0"), {"c": cid})
        last = conn.execute(text("SELECT MAX(seq) FROM custody_events WHERE consignment_id=:c"), {"c": cid}).scalar()
    assert client.get(f"/api/v1/consignments/{cid}/verify", headers=flow["H"]["admin"][0]).json()["chain"]["ok"]
    with app_db.begin() as conn:   # delete the tail event: caught by the recorded head/count
        conn.execute(text("DELETE FROM custody_events WHERE consignment_id=:c AND seq=:s"), {"c": cid, "s": last})
    assert not client.get(f"/api/v1/consignments/{cid}/verify", headers=flow["H"]["admin"][0]).json()["chain"]["ok"]


def test_pin_lockout_and_manual_lookup(client, login):
    h = login(PH["farmer"])
    r = client.post("/api/v1/consignments", headers=h, json={"commodity": "onion", "qty_kg": 500, "harvest_time": _now_minus(2),
                                                             "origin_node_id": h.user["home_node_id"]}).json()
    code, pin = r["consignment"]["short_code"], r["pin"]
    ok = client.post("/api/v1/consignments/pin-lookup", headers=h, json={"short_code": code.lower(), "pin": pin})
    assert ok.status_code == 200 and ok.json()["short_code"] == code
    wrong = f"{(int(pin) + 1) % 10000:04d}"
    codes = [client.post("/api/v1/consignments/pin-lookup", headers=h, json={"short_code": code, "pin": wrong}).status_code
             for _ in range(5)]
    assert codes[:4] == [401] * 4 and codes[4] == 403          # 5th failure locks
    assert client.post("/api/v1/consignments/pin-lookup", headers=h, json={"short_code": code, "pin": pin}).status_code == 403


def test_offline_sync_is_idempotent_and_keeps_scan_time(client, login):
    f = login(PH["farmer"])
    sup = login(PH["supervisor"])
    c = client.post("/api/v1/consignments", headers=f, json={"commodity": "orange", "qty_kg": 300, "harvest_time": _now_minus(30),
                                                             "origin_node_id": f.user["home_node_id"]}).json()["consignment"]
    offline_t = _now_minus(20)
    ops = [{"op": "handover_start", "client_event_id": "dev1-0001", "consignment_id": c["id"],
            "payload": {"to_node_id": sup.user["home_node_id"], "weight_kg": 300, "condition": "GOOD", "scan_time": offline_t}}]
    first = client.post("/api/v1/sync", headers=f, json=ops).json()
    again = client.post("/api/v1/sync", headers=f, json=ops).json()
    assert first[0]["ok"] and again[0]["ok"] and again[0]["message"] == "already synced"
    t = client.get(f"/api/v1/consignments/{c['id']}/timeline", headers=f).json()
    rel = [e for e in t["events"] if e["event_type"] == "RELEASE"]
    assert len(rel) == 1 and rel[0]["scan_time_utc"][:16] == offline_t[:16] and rel[0]["sync_time_utc"] > rel[0]["scan_time_utc"]


def test_concurrent_confirmations_have_exactly_one_winner(app_db):
    from app.core import db as dbmod
    from app.models.orm import Node, User
    from app.services import custody
    from app.services.custody import ServiceError

    with dbmod.session() as s:
        farmer = s.query(User).filter_by(phone=PH["farmer"]).one()
        sup = s.query(User).filter_by(phone=PH["supervisor"]).one()
        made = custody.create_consignment(s, farmer, commodity="tomato", grade="A", qty_kg=200,
                                          harvest_time=_clock_now() - timedelta(hours=1),
                                          origin_node_id=farmer.home_node_id)
        h = custody.start_handover(s, farmer, made.consignment, to_node_id=sup.home_node_id, weight_kg=200, condition="GOOD")
        hid, sup_id = h.id, sup.id
        assert s.get(Node, sup.home_node_id) is not None
    results = []

    def confirm():
        with dbmod.session() as s:
            u = s.get(User, sup_id)
            try:
                custody.confirm_handover(s, u, hid, weight_kg=200, condition="GOOD")
                results.append("won")
            except ServiceError as e:
                results.append(e.code)
            except Exception as e:  # noqa: BLE001 - e.g. StaleDataError / locked db counts as a loss
                results.append(type(e).__name__)

    threads = [threading.Thread(target=confirm) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("won") == 1, results
