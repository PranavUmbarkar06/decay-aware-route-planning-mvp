"""M1 Traceability + QR handshake (service layer).

State changes run in one DB transaction each; concurrent changes to the same consignment are serialised by
the optimistic `version` column (SQLAlchemy raises StaleDataError → HTTP 409) and by conditional UPDATEs on
handovers (`WHERE status='PENDING'`, rowcount must be 1), which works identically on SQLite and Postgres.
"""
from __future__ import annotations

import base64
import io
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import cast

import qrcode
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.core.clock import now as utcnow
from app.core.config import app_config, commodities_config
from app.core.provenance import Provenance
from app.core.security import Role, request_id_var
from app.domain import hashchain
from app.domain import pin as pinlib
from app.models.orm import AuditLog, Consignment, CustodyEvent, Handover, Node, QualityEvent, User

CONDITIONS = ("GOOD", "MINOR_DAMAGE", "MAJOR_DAMAGE", "WET", "OVERRIPE")


class ServiceError(Exception):
    def __init__(self, status: int, message: str, code: str = "error"):
        super().__init__(message)
        self.status, self.message, self.code = status, message, code


def audit(db: Session, actor: User | None, action: str, entity: str, entity_id: str, detail: dict | None = None) -> None:
    db.add(AuditLog(at_utc=utcnow(), actor_id=actor.id if actor else None, request_id=request_id_var.get(),
                    action=action, entity=entity, entity_id=entity_id,
                    detail=json.dumps(detail, default=str, ensure_ascii=False) if detail else None))


def _append_event(db: Session, c: Consignment, ev: dict, *, scan_time: datetime | None, client_event_id: str | None,
                  provenance: str = Provenance.USER_ENTERED) -> CustodyEvent:
    if client_event_id:
        dup = db.scalar(select(CustodyEvent).where(CustodyEvent.client_event_id == client_event_id))
        if dup is not None:
            raise ServiceError(409, "This scan was already synced", "duplicate_event")
    st = (scan_time or utcnow()).replace(microsecond=0).isoformat()
    payload = {**ev, "consignment_id": c.id, "seq": c.chain_count, "scan_time_utc": st}
    h = hashchain.event_hash(payload, c.chain_head)
    row = CustodyEvent(consignment_id=c.id, seq=c.chain_count, event_type=ev["event_type"],
                       from_node=ev.get("from_node"), to_node=ev.get("to_node"), actor_release=ev.get("actor_release"),
                       actor_receive=ev.get("actor_receive"), weight_released_kg=ev.get("weight_released_kg"),
                       weight_received_kg=ev.get("weight_received_kg"), condition_released=ev.get("condition_released"),
                       condition_received=ev.get("condition_received"), scan_time_utc=st, sync_time_utc=utcnow(),
                       lat=ev.get("lat"), lon=ev.get("lon"), note=ev.get("note"), client_event_id=client_event_id,
                       prev_hash=c.chain_head, hash=h, provenance=provenance)
    db.add(row)
    c.chain_head, c.chain_count = h, c.chain_count + 1
    return row


def _qr_png_data_uri(text: str) -> str:
    img = qrcode.make(text, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@dataclass
class Created:
    consignment: Consignment
    pin: str                     # shown once, never stored in clear
    qr_payload: str
    qr_png: str


def create_consignment(db: Session, user: User, *, commodity: str, grade: str, qty_kg: float, harvest_time: datetime,
                       origin_node_id: str, client_event_id: str | None = None, provenance: str = Provenance.USER_ENTERED) -> Created:
    if commodity not in commodities_config().commodities:
        raise ServiceError(422, f"Unknown commodity '{commodity}'", "bad_commodity")
    if qty_kg <= 0:
        raise ServiceError(422, "Quantity must be more than 0 kg", "bad_qty")
    node = db.get(Node, origin_node_id)
    if node is None:
        raise ServiceError(404, "Origin location not found", "bad_node")
    if harvest_time > utcnow():
        raise ServiceError(422, "Harvest time cannot be in the future", "bad_time")
    cfg = app_config().pin
    for _ in range(5):
        code = pinlib.new_short_code()
        if db.scalar(select(Consignment.id).where(Consignment.short_code == code)) is None:
            break
    else:  # pragma: no cover - 32^8 space
        raise ServiceError(500, "Could not allocate a short code")
    pin = pinlib.new_pin(cfg.digits)
    cid = str(uuid.uuid4())
    c = Consignment(id=cid, short_code=code, pin_hash=pinlib.hash_pin(pin, code), pin_issued_at=utcnow(),
                    commodity=commodity, grade=grade, initial_qty_kg=qty_kg, current_qty_kg=qty_kg, quality_score=1.0,
                    harvest_time=harvest_time, origin_node_id=origin_node_id, at_node_id=origin_node_id,
                    status="AT_NODE", chain_head=hashchain.genesis_hash(cid), chain_count=0, created_by=user.id,
                    created_at=utcnow(), provenance=provenance)
    db.add(c)
    db.flush()
    _append_event(db, c, {"event_type": "CREATED", "to_node": origin_node_id, "actor_receive": user.id,
                          "weight_received_kg": qty_kg, "lat": node.lat, "lon": node.lon},
                  scan_time=harvest_time, client_event_id=client_event_id, provenance=provenance)
    db.add(QualityEvent(consignment_id=cid, timestamp=utcnow(), qty_kg=qty_kg, quality=1.0, event_type="CREATED",
                        amount_kg=0.0, actor_id=user.id, provenance=provenance))
    audit(db, user, "consignment.create", "consignment", cid, {"commodity": commodity, "qty_kg": qty_kg, "origin": origin_node_id})
    db.commit()
    payload = f"PHL1:{code}"     # the QR carries only the short code; the PIN is never in the QR
    return Created(c, pin, payload, _qr_png_data_uri(payload))


def find_by_code(db: Session, short_code: str) -> Consignment:
    c = db.scalar(select(Consignment).where(Consignment.short_code == pinlib.normalize_short_code(short_code)))
    if c is None:
        raise ServiceError(404, "No consignment with this code", "not_found")
    return c


def verify_pin(db: Session, short_code: str, pin: str) -> Consignment:
    c = find_by_code(db, short_code)
    cfg = app_config().pin
    st = pinlib.PinState(c.pin_hash, c.pin_issued_at, c.pin_failures, c.pin_locked_until)
    res = pinlib.verify_pin(pin, c.short_code, st, utcnow(), max_failures=cfg.max_failures, lockout_s=cfg.lockout_s,
                            ttl_h=cfg.ttl_h)
    c.pin_failures, c.pin_locked_until = res.state.failures, res.state.locked_until
    audit(db, None, f"pin.{res.reason.lower()}", "consignment", c.id)
    db.commit()
    if not res.ok:
        msg = {"WRONG_PIN": "Wrong PIN", "LOCKED": "Too many wrong PINs. This PIN is locked for a while; scan the QR instead.",
               "EXPIRED": "This PIN has expired; scan the QR instead."}[res.reason]
        raise ServiceError(403 if res.reason != "WRONG_PIN" else 401, msg, res.reason.lower())
    return c


def _user_can_act_at(user: User, node_id: str) -> bool:
    return user.role == Role.ADMIN or user.home_node_id == node_id


def start_handover(db: Session, user: User, c: Consignment, *, to_node_id: str, weight_kg: float, condition: str,
                   scan_time: datetime | None = None, client_event_id: str | None = None) -> Handover:
    """Releaser side. Calls the equivalent of `Node.release(c)`."""
    if c.status not in ("AT_NODE", "DISPUTED_WEIGHT"):
        raise ServiceError(409, f"Consignment is {c.status}, it cannot be released now", "bad_state")
    if not _user_can_act_at(user, c.at_node_id or ""):
        raise ServiceError(403, "You can only release lots held at your own location", "not_holder")
    if condition not in CONDITIONS:
        raise ServiceError(422, f"Condition must be one of {CONDITIONS}", "bad_condition")
    if weight_kg <= 0 or weight_kg > c.current_qty_kg * 1.5:
        raise ServiceError(422, "Declared weight is not plausible for this lot", "bad_weight")
    dest = db.get(Node, to_node_id)
    if dest is None or to_node_id == c.at_node_id:
        raise ServiceError(422, "Choose a different, known destination", "bad_node")
    if dest.review_status == "reject":
        raise ServiceError(422, "That location was rejected in review", "bad_node")
    h = Handover(id=str(uuid.uuid4()), consignment_id=c.id, from_node=c.at_node_id, to_node=to_node_id,
                 releaser_id=user.id, weight_released_kg=weight_kg, condition_released=condition, status="PENDING",
                 created_at=utcnow())
    db.add(h)
    src = db.get(Node, c.at_node_id)
    _append_event(db, c, {"event_type": "RELEASE", "from_node": c.at_node_id, "to_node": to_node_id,
                          "actor_release": user.id, "weight_released_kg": weight_kg, "condition_released": condition,
                          "lat": src.lat if src else None, "lon": src.lon if src else None},
                  scan_time=scan_time, client_event_id=client_event_id, provenance=c.provenance)
    c.status, c.at_node_id, c.in_transit_to = "IN_TRANSIT", None, to_node_id
    if c.dispatch_time is None:
        c.dispatch_time = scan_time or utcnow()
    audit(db, user, "handover.start", "handover", h.id, {"to": to_node_id, "weight_kg": weight_kg})
    db.commit()
    return h


def confirm_handover(db: Session, user: User, handover_id: str, *, weight_kg: float, condition: str,
                     scan_time: datetime | None = None, client_event_id: str | None = None) -> Handover:
    """Receiver side. Calls the equivalent of `Node.receive_consignment(c)`. Atomic: exactly one confirmation wins."""
    h = db.get(Handover, handover_id)
    if h is None:
        raise ServiceError(404, "Handover not found", "not_found")
    if not _user_can_act_at(user, h.to_node):
        raise ServiceError(403, "Only someone at the receiving location can confirm", "not_receiver")
    if user.id == h.releaser_id and user.role != Role.ADMIN:
        raise ServiceError(403, "The releaser cannot also confirm receipt", "same_party")
    if condition not in CONDITIONS:
        raise ServiceError(422, f"Condition must be one of {CONDITIONS}", "bad_condition")
    if weight_kg < 0:
        raise ServiceError(422, "Weight cannot be negative", "bad_weight")
    c = db.get(Consignment, h.consignment_id)
    assert c is not None
    if weight_kg > c.current_qty_kg * 1.05:
        raise ServiceError(422, "Received weight is more than was sent; please re-weigh", "bad_weight")
    tol = app_config().handover.weight_tolerance_pct
    diff = h.weight_released_kg - weight_kg
    disputed = abs(diff) > h.weight_released_kg * tol / 100
    new_status = "DISPUTED_WEIGHT" if disputed else "COMPLETED"
    stmt = (update(Handover).where(Handover.id == h.id, Handover.status == "PENDING")
            .values(status=new_status, receiver_id=user.id, weight_received_kg=weight_kg,
                    condition_received=condition, difference_kg=diff, completed_at=utcnow()))
    won = cast(CursorResult, db.execute(stmt))
    if won.rowcount != 1:
        db.rollback()
        raise ServiceError(409, "This handover was already confirmed", "already_confirmed")
    dst = db.get(Node, h.to_node)
    _append_event(db, c, {"event_type": "RECEIVE_DISPUTED" if disputed else "RECEIVE", "to_node": h.to_node,
                          "actor_receive": user.id, "weight_received_kg": weight_kg, "condition_received": condition,
                          "lat": dst.lat if dst else None, "lon": dst.lon if dst else None,
                          "note": f"difference {diff:.2f} kg vs declared" if disputed else None},
                  scan_time=scan_time, client_event_id=client_event_id, provenance=c.provenance)
    # The weight difference is surfaced as unreconciled, never auto-booked as wastage.
    shrink = c.current_qty_kg - weight_kg
    c.current_qty_kg = weight_kg
    c.unreconciled_kg += shrink
    c.status, c.at_node_id, c.in_transit_to = ("DISPUTED_WEIGHT" if disputed else "AT_NODE"), h.to_node, None
    db.add(QualityEvent(consignment_id=c.id, timestamp=utcnow(), qty_kg=c.current_qty_kg, quality=c.quality_score,
                        event_type="HANDOVER", reason_code=None, amount_kg=0.0, actor_id=user.id,
                        provenance=Provenance.USER_ENTERED))
    # Receipt at a sink is a disposition: NGO → DONATED (never wastage), processing unit → PROCESSED.
    if dst is not None and dst.node_type in ("NGOSink", "ProcessingSink") and not disputed:
        kind = "DONATED" if dst.node_type == "NGOSink" else "PROCESSED"
        _close_as(db, user, c, kind)
        if kind == "DONATED":
            from app.services import rescue
            rescue.on_received_by_ngo(db, c, dst.node_id, h.id)
    audit(db, user, "handover.confirm", "handover", h.id, {"status": new_status, "difference_kg": diff})
    db.commit()
    db.refresh(h)
    return h


def _close_as(db: Session, user: User, c: Consignment, kind: str, kg: float | None = None) -> None:
    kg = c.current_qty_kg if kg is None else kg
    if kg > c.current_qty_kg + 1e-9 or kg <= 0:
        raise ServiceError(422, "Quantity must be between 0 and what is left in the lot", "bad_qty")
    c.current_qty_kg -= kg
    if kind == "DONATED":
        c.donated_kg += kg
    elif kind == "PROCESSED":
        c.processed_kg += kg
    elif kind == "SOLD":
        c.sold_kg += kg
    db.add(QualityEvent(consignment_id=c.id, timestamp=utcnow(), qty_kg=c.current_qty_kg, quality=c.quality_score,
                        event_type="DISPOSITION", reason_code=kind, amount_kg=kg, actor_id=user.id,
                        provenance=Provenance.USER_ENTERED))
    if c.current_qty_kg <= 1e-9:
        c.current_qty_kg = 0.0
        c.status, c.at_node_id, c.in_transit_to = "CLOSED", None, None


def record_sale(db: Session, user: User, c: Consignment, kg: float) -> Consignment:
    """Lot (or part of it) sold at the market where it sits."""
    if c.status not in ("AT_NODE", "DISPUTED_WEIGHT"):
        raise ServiceError(409, "Only lots at a location can be sold", "bad_state")
    if user.role != Role.ADMIN and user.home_node_id != c.at_node_id:
        raise ServiceError(403, "Only someone at this location can record a sale", "not_holder")
    _close_as(db, user, c, "SOLD", kg)
    audit(db, user, "consignment.sold", "consignment", c.id, {"kg": kg})
    db.commit()
    return c


def transit_scan(db: Session, user: User, c: Consignment, *, lat: float | None, lon: float | None,
                 scan_time: datetime | None = None, client_event_id: str | None = None) -> CustodyEvent:
    """Transporter scan-only event: proves the lot was sighted; no weight, no custody change."""
    if c.status != "IN_TRANSIT":
        raise ServiceError(409, "Only lots in transit can be scanned by the driver", "bad_state")
    ev = _append_event(db, c, {"event_type": "TRANSIT_SCAN", "to_node": c.in_transit_to, "actor_release": user.id,
                               "lat": lat, "lon": lon}, scan_time=scan_time, client_event_id=client_event_id)
    audit(db, user, "custody.transit_scan", "consignment", c.id)
    db.commit()
    return ev


def verify_chain(db: Session, c: Consignment) -> dict:
    evs = list(db.scalars(select(CustodyEvent).where(CustodyEvent.consignment_id == c.id).order_by(CustodyEvent.seq)))
    rows = [{k: getattr(e, k) for k in (*hashchain.HASHED_FIELDS, "prev_hash", "hash")} for e in evs]
    ok, bad, why = hashchain.verify(c.id, rows, expected_head=c.chain_head, expected_count=c.chain_count)
    return {"ok": ok, "first_bad_seq": bad, "reason": why, "events": len(rows)}


def mass_balance(c: Consignment) -> dict:
    accounted = c.current_qty_kg + c.sold_kg + c.donated_kg + c.processed_kg + c.wasted_kg + c.unreconciled_kg
    return {"initial_kg": c.initial_qty_kg, "current_kg": c.current_qty_kg, "sold_kg": c.sold_kg,
            "donated_kg": c.donated_kg, "processed_kg": c.processed_kg, "wasted_kg": c.wasted_kg,
            "unreconciled_kg": c.unreconciled_kg, "error_kg": round(c.initial_qty_kg - accounted, 6),
            "holds": abs(c.initial_qty_kg - accounted) <= 1e-6 * max(1.0, c.initial_qty_kg)}


def timeline(db: Session, c: Consignment) -> dict:
    """Origin → path → destination built only from actual scan events (no inferred hops)."""
    evs = list(db.scalars(select(CustodyEvent).where(CustodyEvent.consignment_id == c.id).order_by(CustodyEvent.seq)))
    node_ids = {e.from_node for e in evs} | {e.to_node for e in evs} - {None}
    nodes = {n.node_id: n for n in db.scalars(select(Node).where(Node.node_id.in_(node_ids)))} if node_ids else {}
    items, path = [], []
    for e in evs:
        items.append({"seq": e.seq, "event_type": e.event_type, "from_node": e.from_node, "to_node": e.to_node,
                      "from_name": nodes[e.from_node].name if e.from_node in nodes else None,
                      "to_name": nodes[e.to_node].name if e.to_node in nodes else None,
                      "weight_released_kg": e.weight_released_kg, "weight_received_kg": e.weight_received_kg,
                      "condition_released": e.condition_released, "condition_received": e.condition_received,
                      "scan_time_utc": e.scan_time_utc, "sync_time_utc": e.sync_time_utc.isoformat(),
                      "lat": e.lat, "lon": e.lon, "note": e.note, "hash": e.hash[:12], "provenance": e.provenance})
        if e.lat is not None and e.lon is not None:
            path.append({"lat": e.lat, "lon": e.lon, "seq": e.seq, "event_type": e.event_type, "inferred": False})
    return {"events": items, "path": path, "chain": verify_chain(db, c), "mass_balance": mass_balance(c)}
