"""M3 shelf-life, M4 crowd meter, M5 rescue, M6 matching, notifications, M7 advisor + Simulation Lab endpoints."""
from __future__ import annotations

import json
from datetime import date, datetime

import pandas as pd
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.clock import is_demo_clock, now
from app.core.config import ROOT, app_config, commodities_config
from app.core.db import get_db
from app.core.provenance import Provenance
from app.core.security import ANY_ROLE, Role, require
from app.models.orm import (
    Consignment,
    NgoProfile,
    Node,
    Notification,
    RescueBroadcast,
    RescueOffer,
    User,
)
from app.services import advisor, crowd, custody, rescue, shelf_life
from app.services.custody import ServiceError

router = APIRouter(prefix="/api/v1")
SIM = ROOT / "reports" / "sim"


@router.get("/clock", tags=["meta"])
def clock() -> dict:
    t = now()
    return {"now_utc": t.isoformat(timespec="seconds"), "demo_clock": is_demo_clock(),
            "note": "Demo clock inside the weather replay window (temperatures are replayed real data)" if is_demo_clock()
            else "Real clock"}


# ---------------------------------------------------------------- M3 shelf life
@router.get("/storage/{node_id}/batches", tags=["M3 shelf life"])
def batches(node_id: str, user: User = Depends(require(*ANY_ROLE)), db: Session = Depends(get_db)) -> dict:
    n = db.get(Node, node_id)
    if n is None:
        raise ServiceError(404, "Location not found", "not_found")
    lots = list(db.scalars(select(Consignment).where(Consignment.at_node_id == node_id,
                                                     Consignment.status.in_(["AT_NODE", "DISPUTED_WEIGHT"]))))
    preds = shelf_life.fefo([shelf_life.predict_for_consignment(c, n) for c in lots])
    for p, c in zip(preds, sorted(lots, key=lambda c: next(i for i, q in enumerate(preds) if q["consignment_id"] == c.id)),
                    strict=True):
        p["provenance"] = c.provenance
    tl = app_config()
    return {"node": {"node_id": n.node_id, "name": n.name, "provenance": n.provenance}, "order": "FEFO (first expiring first out)",
            "batches": preds, "thresholds_note": "Red < 24 h, Yellow 24–72 h, Green ≥ 72 h (ASSUMPTION: confirm with operators)",
            "clock": clock(), "demo_mode": tl.runtime.demo_mode}


@router.get("/consignments/{cid}/shelf-life", tags=["M3 shelf life"])
def consignment_shelf_life(cid: str, horizon_h: int = Query(24, ge=1, le=168), _: User = Depends(require(*ANY_ROLE)),
                           db: Session = Depends(get_db)) -> dict:
    c = db.get(Consignment, cid)
    if c is None:
        raise ServiceError(404, "Consignment not found", "not_found")
    node = db.get(Node, c.at_node_id or c.in_transit_to or c.origin_node_id)
    return shelf_life.predict_for_consignment(c, node, horizon_h)


# ---------------------------------------------------------------- M4 crowd meter
@router.get("/crowd", tags=["M4 crowd meter"])
def crowd_meter(commodity: str, on: date | None = None, origin_node_id: str | None = None,
                _: User = Depends(require(*ANY_ROLE)), db: Session = Depends(get_db)) -> dict:
    if commodity not in commodities_config().commodities:
        raise ServiceError(422, "Unknown commodity", "bad_commodity")
    on = on or now().date()
    markets = list(db.scalars(select(Node).where(Node.node_type.in_(["ReceivingMarket", "AssemblyMandi"]))))
    rows = []
    for m in markets:
        r = crowd.meter(m.name, commodity, on)
        if r["status"] == "NO_DATA":
            continue
        rt = rescue.road_time_h(origin_node_id, m.node_id) if origin_node_id else None
        rows.append({**r, "node_id": m.node_id, "lat": m.lat, "lon": m.lon, "routable": not m.needs_review or m.review_status in ("accept", "move"),
                     "road_time_h": round(rt, 2) if rt is not None else None})
    radius = app_config().crowd_meter.alternate_radius_h
    for r in rows:
        if r["status"] in ("GLUT_WARNING", "BUSY"):
            alts = [x for x in rows if x["node_id"] != r["node_id"] and x.get("ratio") is not None
                    and x["ratio"] < (r.get("ratio") or 0) and x["status"] in ("NORMAL", "BUSY")]
            for a in alts:
                a_rt = rescue.road_time_h(r["node_id"], a["node_id"])
                a["_from"] = a_rt
            r["alternates"] = [{"node_id": a["node_id"], "market": a["market"], "ratio": a["ratio"],
                                "road_time_h_from_this_market": round(a["_from"], 2)}
                               for a in sorted(alts, key=lambda x: x["ratio"]) if a.get("_from") is not None and a["_from"] <= radius][:3]
    for r in rows:
        r.pop("_from", None)
    return {"commodity": commodity, "date": on.isoformat(), "definition": crowd.DEFINITION.format(n=app_config().crowd_meter.trailing_days),
            "markets": sorted(rows, key=lambda r: (-(r.get("ratio") or 0), r["market"])),
            "markets_without_data": len(markets) - len(rows),
            "note": "Only markets that report arrivals to Agmarknet appear. Alternates are limited to markets with data within "
                    f"{radius:g} h road time (free-flow model)."}


# ---------------------------------------------------------------- M5 rescue + M6 matching
class BroadcastIn(BaseModel):
    consignment_id: str
    trigger: str = Field(pattern="^(YELLOW|RED|UNSOLD)$")


class NgoProfileIn(BaseModel):
    accepted_commodities: list[str]
    daily_capacity_kg: float = Field(gt=0, le=100_000)
    pickup_start_ist: int = Field(8, ge=0, le=23)
    pickup_end_ist: int = Field(18, ge=1, le=24)
    can_collect: bool = True


@router.put("/ngo/profile", tags=["M5 rescue"])
def put_profile(body: NgoProfileIn, user: User = Depends(require(Role.NGO)), db: Session = Depends(get_db)) -> dict:
    if not user.home_node_id:
        raise ServiceError(422, "Set your organisation's location first", "no_node")
    bad = set(body.accepted_commodities) - set(commodities_config().commodities)
    if bad:
        raise ServiceError(422, f"Unknown commodities {sorted(bad)}", "bad_commodity")
    p = db.get(NgoProfile, user.home_node_id) or NgoProfile(node_id=user.home_node_id)
    p.user_id, p.accepted_commodities = user.id, ",".join(sorted(body.accepted_commodities))
    p.daily_capacity_kg, p.pickup_start_ist, p.pickup_end_ist, p.can_collect = (body.daily_capacity_kg, body.pickup_start_ist,
                                                                              body.pickup_end_ist, body.can_collect)
    p.provenance = user.provenance if user.provenance == Provenance.SYNTHETIC_DEMO else Provenance.USER_ENTERED
    p.updated_at = now()
    db.add(p)
    custody.audit(db, user, "ngo.profile", "node", user.home_node_id, body.model_dump())
    db.commit()
    return {"node_id": p.node_id, "accepted_commodities": p.accepted_commodities.split(","), "daily_capacity_kg": p.daily_capacity_kg,
            "pickup_start_ist": p.pickup_start_ist, "pickup_end_ist": p.pickup_end_ist, "provenance": p.provenance}


@router.get("/rescue/matches/{cid}", tags=["M6 matching"])
def matches(cid: str, user: User = Depends(require(Role.SUPERVISOR, Role.WAREHOUSE, Role.DISPATCHER)),
            db: Session = Depends(get_db)) -> dict:
    c = db.get(Consignment, cid)
    if c is None or c.at_node_id is None:
        raise ServiceError(404, "Lot not found at a location", "not_found")
    pred = shelf_life.predict_for_consignment(c, db.get(Node, c.at_node_id))
    return {"consignment_id": cid, "safe_window_h": pred["safe_window_h"], "light": pred["light"],
            "matches": rescue.ranked_ngos(db, c, c.at_node_id, pred["safe_window_h"]),
            "score_formula": "Σ weight × component; components: road time (1 − t / max), life margin after travel + pickup wait, "
                             "capacity fit (capacity left ÷ lot size). Weights: ASSUMPTION A13.",
            "disclaimer": shelf_life.SAFETY_DISCLAIMER}


@router.post("/rescue/broadcasts", status_code=201, tags=["M5 rescue"])
def create_broadcast(body: BroadcastIn, user: User = Depends(require(Role.SUPERVISOR, Role.WAREHOUSE, Role.DISPATCHER)),
                     db: Session = Depends(get_db)) -> dict:
    c = db.get(Consignment, body.consignment_id)
    if c is None:
        raise ServiceError(404, "Consignment not found", "not_found")
    b = rescue.broadcast(db, user, c, body.trigger)
    return _broadcast_out(db, b)


def _broadcast_out(db: Session, b: RescueBroadcast) -> dict:
    offers = list(db.scalars(select(RescueOffer).where(RescueOffer.broadcast_id == b.id).order_by(RescueOffer.rank)))
    names = {n.node_id: n.name for n in db.scalars(select(Node).where(Node.node_id.in_([o.ngo_node_id for o in offers])))}
    return {"id": b.id, "consignment_id": b.consignment_id, "status": b.status, "wave": b.wave, "trigger": b.trigger,
            "qty_kg": b.qty_kg, "safety_note": b.safety_note, "provenance": b.provenance,
            "offers": [{"id": o.id, "ngo_node_id": o.ngo_node_id, "ngo_name": names.get(o.ngo_node_id), "rank": o.rank,
                        "status": o.status, "road_time_h": o.road_time_h, "safe_window_h": o.safe_window_h, "score": o.score,
                        "score_breakdown": json.loads(o.score_breakdown or "{}"),
                        "offer_expires_at": o.offer_expires_at, "claim_expires_at": o.claim_expires_at} for o in offers]}


@router.get("/rescue/broadcasts", tags=["M5 rescue"])
def list_broadcasts(user: User = Depends(require(*ANY_ROLE)), db: Session = Depends(get_db)) -> list[dict]:
    rescue.expire_due(db)
    q = select(RescueBroadcast).order_by(RescueBroadcast.created_at.desc()).limit(50)
    if user.role not in (Role.ADMIN,):
        q = q.where(or_(RescueBroadcast.from_node_id == user.home_node_id, RescueBroadcast.created_by == user.id))
    return [_broadcast_out(db, b) for b in db.scalars(q)]


@router.get("/rescue/offers", tags=["M5 rescue"])
def my_offers(user: User = Depends(require(Role.NGO)), db: Session = Depends(get_db)) -> list[dict]:
    rescue.expire_due(db)
    rows = db.scalars(select(RescueOffer).where(RescueOffer.ngo_node_id == user.home_node_id,
                                                RescueOffer.status.in_(["OFFERED", "CLAIMED"])).order_by(RescueOffer.offered_at.desc()))
    out = []
    for o in rows:
        c = db.get(Consignment, o.consignment_id)
        frm = db.get(Node, c.at_node_id) if c and c.at_node_id else None
        out.append({"id": o.id, "status": o.status, "commodity": c.commodity if c else None, "qty_kg": o.qty_kg,
                    "from_name": frm.name if frm else None, "from_node_id": frm.node_id if frm else None,
                    "road_time_h": o.road_time_h, "safe_window_h": o.safe_window_h, "offer_expires_at": o.offer_expires_at,
                    "claim_expires_at": o.claim_expires_at, "score": o.score, "trigger": o.trigger,
                    "short_code": c.short_code if c else None, "disclaimer": shelf_life.SAFETY_DISCLAIMER,
                    "provenance": c.provenance if c else None})
    return out


@router.post("/rescue/offers/{offer_id}/claim", tags=["M5 rescue"])
def claim(offer_id: str, user: User = Depends(require(Role.NGO)), db: Session = Depends(get_db)) -> dict:
    o = rescue.claim(db, user, offer_id)
    return {"id": o.id, "status": o.status, "claim_expires_at": o.claim_expires_at,
            "next_step": "Collect the lot and confirm the handover (scan its QR) before the timer ends."}


@router.post("/consignments/{cid}/sold", tags=["M1 traceability"])
def sold(cid: str, kg: float = Query(gt=0), user: User = Depends(require(Role.SUPERVISOR, Role.DISPATCHER, Role.WAREHOUSE)),
         db: Session = Depends(get_db)) -> dict:
    c = db.get(Consignment, cid)
    if c is None:
        raise ServiceError(404, "Consignment not found", "not_found")
    c = custody.record_sale(db, user, c, kg)
    return {"id": c.id, "status": c.status, "sold_kg": c.sold_kg, "current_qty_kg": c.current_qty_kg}


@router.get("/notifications", tags=["notifications"])
def notifications(user: User = Depends(require(*ANY_ROLE)), db: Session = Depends(get_db)) -> list[dict]:
    rescue.expire_due(db)
    q = select(Notification).where(or_(Notification.user_id == user.id, Notification.node_id == user.home_node_id))
    return [{"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "ref": n.ref, "created_at": n.created_at,
             "read": n.read_at is not None} for n in db.scalars(q.order_by(Notification.id.desc()).limit(50))]


@router.get("/stats/dispositions", tags=["M5 rescue"])
def dispositions(user: User = Depends(require(*ANY_ROLE)), db: Session = Depends(get_db)) -> dict:
    """WASTED vs DONATED vs SOLD vs PROCESSED, split by provenance (demo data never mixed with real)."""
    out: dict[str, dict] = {}
    for c in db.scalars(select(Consignment)):
        d = out.setdefault(c.provenance, {"lots": 0, "injected_kg": 0.0, "sold_kg": 0.0, "donated_kg": 0.0, "processed_kg": 0.0,
                                          "wasted_kg": 0.0, "unreconciled_kg": 0.0, "in_stock_kg": 0.0})
        d["lots"] += 1
        d["injected_kg"] += c.initial_qty_kg
        d["sold_kg"] += c.sold_kg
        d["donated_kg"] += c.donated_kg
        d["processed_kg"] += c.processed_kg
        d["wasted_kg"] += c.wasted_kg
        d["unreconciled_kg"] += c.unreconciled_kg
        d["in_stock_kg"] += c.current_qty_kg
    for d in out.values():
        d["logged_wastage_rate"] = d["wasted_kg"] / d["injected_kg"] if d["injected_kg"] else None
    return {"by_provenance": out, "note": "Logged in the app (operations layer). Not a simulation output. "
                                          "SYNTHETIC_DEMO rows are demo data and must not be read as real loss."}


# ---------------------------------------------------------------- M7 advisor
class AdvisorIn(BaseModel):
    origin_node_id: str
    commodity: str
    qty_kg: float = Field(gt=0, le=50_000)
    harvest_time: datetime
    planned_dest_id: str | None = None


@router.post("/advisor/compare", tags=["M7 advisor"])
def advisor_compare(body: AdvisorIn, _: User = Depends(require(Role.DISPATCHER, Role.SUPERVISOR)),
                    db: Session = Depends(get_db)) -> dict:
    return advisor.compare(db, origin_node_id=body.origin_node_id, commodity=body.commodity, qty_kg=body.qty_kg,
                           harvest_time=body.harvest_time.replace(tzinfo=None), planned_dest_id=body.planned_dest_id)


# ---------------------------------------------------------------- Simulation Lab
def _read_set(name: str) -> dict | None:
    d = SIM / name
    if not (d / "summary.json").exists():
        return None
    runs = pd.read_csv(d / "runs.csv")
    keep = ["variant", "season", "seed", "policy", "wastage_rate", "unmet_demand_rate", "mean_quality_at_sink", "injected_kg",
            "sold_kg", "donated_kg", "processed_kg", "wasted_kg", "wasted_heat_kg", "wasted_crushed_kg", "wasted_unsold_kg",
            "mean_travel_h_per_lot", "total_km", "reroute_count", "redirect_count", "events_sha256", "per_commodity"]
    return {"summary": json.loads((d / "summary.json").read_text(encoding="utf-8")),
            "paired": json.loads(pd.read_csv(d / "paired.csv").to_json(orient="records")),
            "runs": json.loads(runs[[k for k in keep if k in runs.columns]].to_json(orient="records"))}


@router.get("/sim/results", tags=["M7 simulation lab"])
def sim_results(_: User = Depends(require(Role.ADMIN, Role.DISPATCHER))) -> dict:
    out = {k: _read_set(k) for k in ("primary", "sensitivity", "exploratory")}
    replays = sorted(p.name for p in SIM.glob("replay__*.json")) if SIM.exists() else []
    return {**out, "replays": replays, "label": "Simulation output, not field-validated",
            "config": {"experiments": "config/experiments.yaml", "simulation": "config/simulation.yaml"},
            "report": "/reports/simulation_report.html" if (ROOT / "reports" / "simulation_report.html").exists() else None}


@router.get("/sim/replay/{name}", tags=["M7 simulation lab"])
def sim_replay(name: str, _: User = Depends(require(Role.ADMIN, Role.DISPATCHER))) -> dict:
    p = (SIM / name).resolve()
    if SIM.resolve() not in p.parents or not p.name.startswith("replay__") or not p.exists():
        raise ServiceError(404, "Replay not found", "not_found")
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- live simulation stream (dashboard)
@router.get("/sim/live", tags=["M7 simulation lab"])
def sim_live(start: date = Query(date(2026, 5, 1)), days: int = Query(3, ge=2, le=7), seed: int = Query(1, ge=0, le=10_000),
             pace_ms: int = Query(60, ge=0, le=1000), _: User = Depends(require(Role.ADMIN, Role.DISPATCHER))):
    """Server-sent events: both policies advance tick by tick on the *same* scenario; each event carries cumulative
    metrics and truck positions. A live exploratory run, not the pre-registered experiment."""
    import time

    from fastapi.responses import StreamingResponse

    from app.simulation.engine import Engine
    from app.simulation.network import load_network
    from app.simulation.policies import make_policy
    from app.simulation.scenario import build_scenario

    try:
        lo, hi = date(2025, 11, 9), date(2026, 10, 18) - pd.Timedelta(days=days + 3)
        if not (lo <= start <= hi):
            raise ServiceError(422, f"Start must be between {lo} and {hi} (weather + arrivals coverage)", "bad_window")
    except TypeError:
        raise ServiceError(422, "Bad start date", "bad_window") from None
    net = load_network()

    def gen():
        sc = build_scenario(net, "live", start.isoformat(), days, seed, list(commodities_config().commodities))
        engines = {"baseline": Engine(net, sc, make_policy("StaticShortestPath")),
                   "proposed": Engine(net, sc, make_policy("QualityAwareDynamic"))}
        head = {"type": "start", "start": start.isoformat(), "days": days, "seed": seed, "lots": len(sc.lots),
                "ticks": sc.ticks, "label": "Live exploratory simulation: SYNTHETIC lots on real roads, weather and market "
                "volumes. Not the pre-registered experiment. Not field-validated.", "notes": sc.notes}
        yield f"data: {json.dumps(head)}\n\n"
        for t in range(sc.ticks):
            payload = {"type": "tick", "tick": t, "time_utc": (pd.Timestamp(start) + pd.Timedelta(hours=t)).isoformat()}
            for k, e in engines.items():
                e.step(t)
                payload[k] = e.snapshot(t)
                payload[k + "_trucks"] = [[round(float(net.y[ls.cur_node]), 4), round(float(net.x[ls.cur_node]), 4),
                                           ls.lot.commodity, round(e.quality(ls), 2)]
                                          for ls in e.active if ls.status == "transit"][:300]
            yield f"data: {json.dumps(payload, default=float)}\n\n"
            if pace_ms:
                time.sleep(pace_ms / 1000)
        yield f"data: {json.dumps({'type': 'end', **{k: e._result().metrics for k, e in engines.items()}}, default=float)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
