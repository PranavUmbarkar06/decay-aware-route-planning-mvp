"""M5 NGO rescue broadcast with claim timer, and M6 redistribution matching.

Flow: a lot turns YELLOW/RED (M3) or is logged UNSOLD (M2) → broadcast to a wave of the nearest eligible NGOs → the
first claim wins atomically (conditional UPDATE on the broadcast row) and starts the claim timer → pickup is an M1
handover with the NGO as receiver, booked as DONATED (not wastage). Unclaimed offers and expired claims cascade to
the next wave. Every transition is audited and notified in-app.

Food-safety note: the "safe window" shown is the model's remaining life × a conservative margin (ASSUMPTION A12);
it is not a certification (COMPLIANCE_TODO.md).
"""
from __future__ import annotations

import json
import uuid
from datetime import timedelta
from functools import lru_cache
from typing import cast

import pandas as pd
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.config import ROOT, app_config
from app.core.provenance import Provenance
from app.core.security import Role
from app.models.orm import Consignment, NgoProfile, Node, Notification, RescueBroadcast, RescueOffer, User
from app.services import shelf_life
from app.services.custody import ServiceError, audit

SAFETY_NOTE = ("Safe window = model estimate × {m:.0%} margin, not a food-safety certification. Inspect before use. "
               "Food-donation rules and liability need review by a qualified person (COMPLIANCE_TODO.md).")


@lru_cache
def _od() -> pd.DataFrame:
    p = ROOT / "data" / "cache" / "od_matrix.parquet"
    if not p.exists():
        return pd.DataFrame(columns=["origin", "dest", "time_s", "dist_m"]).set_index(["origin", "dest"])
    return pd.read_parquet(p).set_index(["origin", "dest"])


def road_time_h(a: str, b: str) -> float | None:
    """Free-flow road time between two routable nodes from the precomputed OD matrix (REAL_DERIVED)."""
    if a == b:
        return 0.0
    try:
        return float(_od().loc[(a, b), "time_s"]) / 3600.0
    except KeyError:
        return None


ESTIMATE_DETOUR, ESTIMATE_KMH = 1.3, 35.0   # ASSUMPTION A8-style straight-line estimate, only when no routed time exists


def travel_time_h(db: Session, a: str, b: str) -> tuple[float | None, str]:
    """Routed OD time when available; otherwise a labelled straight-line estimate (never shown as routed)."""
    rt = road_time_h(a, b)
    if rt is not None:
        return rt, "routed (OD matrix, free-flow)"
    na, nb = db.get(Node, a), db.get(Node, b)
    if na is None or nb is None or na.lat is None or na.lon is None or nb.lat is None or nb.lon is None:
        return None, "unavailable"
    import math
    la1, lo1, la2, lo2 = (math.radians(v) for v in (na.lat, na.lon, nb.lat, nb.lon))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    km = 2 * 6371.0088 * math.asin(math.sqrt(h))
    return km * ESTIMATE_DETOUR / ESTIMATE_KMH, "estimated (straight line × 1.3 at 35 km/h, ASSUMPTION)"


def _notify(db: Session, *, node_id: str | None = None, user_id: str | None = None, kind: str, title: str, body: str,
            ref: str | None = None) -> None:
    db.add(Notification(user_id=user_id, node_id=node_id, kind=kind, title=title, body=body, ref=ref, created_at=now()))


def donated_today(db: Session, ngo_node: str) -> float:
    start = now().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = db.scalars(select(RescueOffer).where(RescueOffer.ngo_node_id == ngo_node,
                                                RescueOffer.status.in_(["CLAIMED", "COMPLETED"]),
                                                RescueOffer.claimed_at >= start))
    return sum(r.qty_kg for r in rows)


def score_match(db: Session, profile: NgoProfile, c: Consignment, from_node: str, safe_window_h: float) -> dict | None:
    """M6 score with breakdown: road time, life margin vs pickup, capacity fit (weights: config.matching, ASSUMPTION A13)."""
    if c.commodity not in profile.accepted_commodities.split(","):
        return None
    rt, rt_method = travel_time_h(db, from_node, profile.node_id)
    max_rt = app_config().rescue.max_road_time_h
    if rt is None or rt > max_rt:
        return None
    w = app_config().matching.weights
    ist_h = (now() + timedelta(hours=5.5)).hour
    wait_h = 0.0 if profile.pickup_start_ist <= ist_h < profile.pickup_end_ist else (profile.pickup_start_ist - ist_h) % 24
    margin_h = safe_window_h - (rt + wait_h)
    cap_left = max(0.0, profile.daily_capacity_kg - donated_today(db, profile.node_id))
    if margin_h <= 0 or cap_left <= 0:
        return None
    parts = {"road_time": 1 - rt / max_rt, "life_margin": min(1.0, margin_h / max(safe_window_h, 1e-6)),
             "capacity_fit": min(1.0, cap_left / max(c.current_qty_kg, 1e-6))}
    total = sum(w[k] * v for k, v in parts.items())
    return {"ngo_node_id": profile.node_id, "score": round(total, 4),
            "breakdown": {k: {"value": round(v, 3), "weight": w[k], "contribution": round(w[k] * v, 3)} for k, v in parts.items()},
            "road_time_h": round(rt, 2), "road_time_method": rt_method, "pickup_wait_h": round(wait_h, 1), "life_margin_h": round(margin_h, 1),
            "capacity_left_kg": round(cap_left, 1), "weights_status": "ASSUMPTION A13"}


def ranked_ngos(db: Session, c: Consignment, from_node: str, safe_window_h: float) -> list[dict]:
    out = []
    for p in db.scalars(select(NgoProfile).order_by(NgoProfile.node_id)):
        n = db.get(Node, p.node_id)
        if n is None or n.review_status == "reject":
            continue
        s = score_match(db, p, c, from_node, safe_window_h)
        if s:
            s["name"], s["provenance"] = n.name, n.provenance
            out.append(s)
    return sorted(out, key=lambda s: (-s["score"], s["road_time_h"], s["ngo_node_id"]))


def broadcast(db: Session, user: User, c: Consignment, trigger: str, *, ranked: list[dict] | None = None) -> RescueBroadcast:
    if c.status != "AT_NODE" or c.at_node_id is None:
        raise ServiceError(409, "Only lots sitting at a location can be offered", "bad_state")
    if user.role != Role.ADMIN and user.home_node_id != c.at_node_id:
        raise ServiceError(403, "Only the holder can offer this lot", "not_holder")
    if db.scalar(select(RescueBroadcast.id).where(RescueBroadcast.consignment_id == c.id,
                                                  RescueBroadcast.status.in_(["OPEN", "CLAIMED"]))):
        raise ServiceError(409, "This lot already has an active rescue offer", "already_open")
    node = db.get(Node, c.at_node_id)
    pred = shelf_life.predict_for_consignment(c, node)
    if trigger in ("YELLOW", "RED") and pred["light"] == "GREEN":
        raise ServiceError(409, "This lot is still green; rescue offers start at yellow or red", "too_fresh")
    safe = pred["safe_window_h"]
    ranked = ranked if ranked is not None else ranked_ngos(db, c, c.at_node_id, safe)
    b = RescueBroadcast(id=str(uuid.uuid4()), consignment_id=c.id, from_node_id=c.at_node_id, trigger=trigger,
                        qty_kg=c.current_qty_kg, status="OPEN" if ranked else "EXHAUSTED", wave=0, created_by=user.id,
                        created_at=now(), safety_note=SAFETY_NOTE.format(m=app_config().rescue.safety_margin_frac),
                        provenance=Provenance.USER_ENTERED)
    db.add(b)
    wave = app_config().rescue.wave_size
    ttl = timedelta(seconds=app_config().rescue.offer_ttl_s)
    for i, r in enumerate(ranked):
        o = RescueOffer(id=str(uuid.uuid4()), broadcast_id=b.id, consignment_id=c.id, ngo_node_id=r["ngo_node_id"], rank=i,
                        qty_kg=c.current_qty_kg, trigger=trigger, road_time_h=r["road_time_h"], safe_window_h=safe,
                        score=r["score"], score_breakdown=json.dumps(r["breakdown"]),
                        status="OFFERED" if i < wave else "QUEUED", offered_at=now(), offer_expires_at=now() + ttl,
                        provenance=Provenance.USER_ENTERED)
        db.add(o)
        if i < wave:
            _notify(db, node_id=r["ngo_node_id"], kind="rescue.offer",
                    title=f"{c.current_qty_kg:.0f} kg {c.commodity} available",
                    body=f"{r['road_time_h']:.1f} h away · safe window ~{safe:.0f} h. {b.safety_note}", ref=o.id)
    audit(db, user, "rescue.broadcast", "consignment", c.id, {"trigger": trigger, "candidates": len(ranked), "safe_window_h": safe})
    db.commit()
    return b


def expire_due(db: Session) -> int:
    """Expire unclaimed offers and lapsed claims; cascade to the next wave. Safe to call often (idempotent)."""
    t = now()
    changed = 0
    wave = app_config().rescue.wave_size
    ttl = timedelta(seconds=app_config().rescue.offer_ttl_s)
    for b in db.scalars(select(RescueBroadcast).where(RescueBroadcast.status.in_(["OPEN", "CLAIMED"]))).all():
        offers = list(db.scalars(select(RescueOffer).where(RescueOffer.broadcast_id == b.id).order_by(RescueOffer.rank)))
        if b.status == "CLAIMED":
            o = next((x for x in offers if x.id == b.claimed_offer_id), None)
            if o and o.status == "CLAIMED" and o.claim_expires_at and o.claim_expires_at < t:
                o.status = "CLAIM_EXPIRED"
                b.status, b.claimed_offer_id = "OPEN", None
                audit(db, None, "rescue.claim_expired", "rescue_offer", o.id)
                _notify(db, node_id=o.ngo_node_id, kind="rescue.claim_expired", title="Claim timer ran out",
                        body="The lot was offered to the next NGO.", ref=o.id)
                changed += 1
            else:
                continue
        for o in offers:
            if o.status == "OFFERED" and o.offer_expires_at < t:
                o.status = "EXPIRED"
                changed += 1
        if not any(o.status == "OFFERED" for o in offers):
            queued = [o for o in offers if o.status == "QUEUED"][:wave]
            if queued:
                b.wave += 1
                for o in queued:
                    o.status, o.offered_at, o.offer_expires_at = "OFFERED", t, t + ttl
                    _notify(db, node_id=o.ngo_node_id, kind="rescue.offer", title=f"{o.qty_kg:.0f} kg available (re-offered)",
                            body=b.safety_note, ref=o.id)
                audit(db, None, "rescue.cascade", "rescue_broadcast", b.id, {"wave": b.wave})
            elif b.status == "OPEN":
                b.status = "EXHAUSTED"
                audit(db, None, "rescue.exhausted", "rescue_broadcast", b.id)
                _notify(db, node_id=b.from_node_id, kind="rescue.exhausted", title="No NGO claimed the lot",
                        body="Consider processing or another outlet.", ref=b.id)
    if changed:
        db.commit()
    return changed


def claim(db: Session, user: User, offer_id: str) -> RescueOffer:
    expire_due(db)
    o = db.get(RescueOffer, offer_id)
    if o is None:
        raise ServiceError(404, "Offer not found", "not_found")
    if user.role != Role.ADMIN and (user.role != Role.NGO or user.home_node_id != o.ngo_node_id):
        raise ServiceError(403, "This offer was sent to a different NGO", "not_recipient")
    if o.status != "OFFERED":
        raise ServiceError(409, f"Offer is {o.status.lower()}", "not_open")
    t = now()
    won = cast(CursorResult, db.execute(update(RescueBroadcast)
                                         .where(RescueBroadcast.id == o.broadcast_id, RescueBroadcast.status == "OPEN")
                                         .values(status="CLAIMED", claimed_offer_id=o.id)))
    if won.rowcount != 1:
        db.rollback()
        raise ServiceError(409, "Another NGO claimed this lot first", "already_claimed")
    o.status, o.claimed_by, o.claimed_at = "CLAIMED", user.id, t
    o.claim_expires_at = t + timedelta(seconds=app_config().rescue.claim_timer_s)
    for other in db.scalars(select(RescueOffer).where(RescueOffer.broadcast_id == o.broadcast_id, RescueOffer.id != o.id,
                                                      RescueOffer.status == "OFFERED")):
        other.status = "TAKEN_BY_OTHER"
    b = db.get(RescueBroadcast, o.broadcast_id)
    _notify(db, node_id=b.from_node_id if b else None, kind="rescue.claimed", title="An NGO claimed your lot",
            body=f"Pickup within {app_config().rescue.claim_timer_s // 3600} h.", ref=o.id)
    audit(db, user, "rescue.claim", "rescue_offer", o.id)
    db.commit()
    return o


def on_received_by_ngo(db: Session, c: Consignment, ngo_node: str, handover_id: str) -> None:
    """Called inside the handover confirmation when the receiver is an NGO node: completes the claim."""
    b = db.scalar(select(RescueBroadcast).where(RescueBroadcast.consignment_id == c.id, RescueBroadcast.status == "CLAIMED"))
    if b is None:
        return
    o = db.get(RescueOffer, b.claimed_offer_id) if b.claimed_offer_id else None
    if o is not None and o.ngo_node_id == ngo_node:
        o.status, o.completed_at, o.handover_id = "COMPLETED", now(), handover_id
        b.status = "COMPLETED"
