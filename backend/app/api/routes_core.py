"""Auth, profile, nodes, consignments (M1) and wastage (M2) endpoints. Every endpoint declares its roles."""
from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api import schemas as s
from app.core.config import app_config, commodities_config, division_bounds
from app.core.db import get_db
from app.core.ratelimit import enforce
from app.core.security import (
    ANY_ROLE,
    ROLE_DESCRIPTIONS,
    Role,
    current_user,
    hash_otp,
    issue_token,
    new_otp,
    otp_sender,
    require,
    utcnow,
)
from app.models.orm import AuditLog, Consignment, Handover, Node, OtpChallenge, QualityEvent, User
from app.services import custody, wastage
from app.services.custody import ServiceError

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------- meta
@router.get("/meta", tags=["meta"])
def meta() -> dict:
    cfg = app_config()
    return {"product_name": cfg.product_name, "version": cfg.version, "demo_mode": cfg.runtime.demo_mode,
            "auth_mode": cfg.auth.mode, "logo_path": cfg.logo_path,
            "map": {"tile_url": cfg.map.tile_url, "attribution": cfg.map.attribution,
                    "bounds": division_bounds(), "bounds_provenance": "REAL_DERIVED (OSM district polygons)"},
            "attributions": ["Road data © OpenStreetMap contributors (ODbL)", "Weather data by Open-Meteo.com (CC BY 4.0)",
                             "Market master list and arrivals: Agmarknet 2.0 (DMI, MoA&FW)"],
            "commodities": {k: c.label for k, c in commodities_config().commodities.items()},
            "provenance_legend": {
                "REAL_FETCHED": "Downloaded from a named source", "REAL_DERIVED": "Computed from real data",
                "USER_ENTERED": "Entered or scanned by a user", "ASSUMPTION": "A parameter we chose (needs validation)",
                "SYNTHETIC_DEMO": "Made-up demo data"},
            "units": cfg.units.display_options}


@router.get("/demo/personas", tags=["meta"])
def demo_personas(db: Session = Depends(get_db)) -> list[dict]:
    """Demo mode only: the fictional demo personas (SYNTHETIC_DEMO) and their home locations."""
    if not app_config().runtime.demo_mode:
        raise ServiceError(404, "Not available outside demo mode", "not_found")
    rows = db.scalars(select(User).where(User.provenance == "SYNTHETIC_DEMO").order_by(User.phone))
    return [{"phone": u.phone, "name": u.name, "role": u.role, "home_node_id": u.home_node_id, "provenance": u.provenance}
            for u in rows]


@router.get("/roles", tags=["meta"])
def roles() -> list[dict]:
    return [{"role": r.value, "description": d} for r, d in ROLE_DESCRIPTIONS.items() if r != Role.ADMIN]


# ---------------------------------------------------------------- auth
@router.post("/auth/otp/request", response_model=s.OtpRequested, tags=["auth"])
def otp_request(body: s.OtpRequest, request: Request, db: Session = Depends(get_db)) -> s.OtpRequested:
    enforce(request, "otp_request", app_config().auth.otp_requests_per_min)
    code = new_otp()
    ch = OtpChallenge(id=str(uuid.uuid4()), phone=body.phone, code_hash=hash_otp(body.phone, code),
                      expires_at=utcnow() + timedelta(seconds=app_config().auth.otp_ttl_s))
    db.add(ch)
    db.commit()
    sent = otp_sender().send(body.phone, code)
    return s.OtpRequested(challenge_id=ch.id, expires_in_s=app_config().auth.otp_ttl_s, delivery=sent["delivery"],
                          dev_otp=sent.get("dev_otp"))


@router.post("/auth/otp/verify", response_model=s.TokenOut, tags=["auth"])
def otp_verify(body: s.OtpVerify, request: Request, db: Session = Depends(get_db)) -> s.TokenOut:
    enforce(request, "otp_verify", 10)
    ch = db.get(OtpChallenge, body.challenge_id)
    if ch is None or ch.used or ch.expires_at < utcnow():
        raise ServiceError(401, "This code has expired. Ask for a new one.", "otp_expired")
    if ch.attempts >= app_config().auth.otp_max_attempts:
        raise ServiceError(429, "Too many wrong codes. Ask for a new one.", "otp_locked")
    if hash_otp(ch.phone, body.code) != ch.code_hash:
        ch.attempts += 1
        db.commit()
        raise ServiceError(401, "Wrong code", "otp_wrong")
    ch.used = True
    user = db.scalar(select(User).where(User.phone == ch.phone))
    if user is None:
        p = body.profile
        if p is None:
            db.rollback()
            raise ServiceError(409, "New number: complete your profile first", "needs_profile")
        if not p.consent:
            raise ServiceError(422, "Please accept the data-use notice to continue", "no_consent")
        if p.role not in {r.value for r in Role} or p.role == Role.ADMIN:
            raise ServiceError(422, "Choose one of the listed roles", "bad_role")
        if p.home_node_id and db.get(Node, p.home_node_id) is None:
            raise ServiceError(422, "Unknown location", "bad_node")
        user = User(id=str(uuid.uuid4()), phone=ch.phone, role=p.role, name=p.name, language=p.language,
                    district=p.district, home_node_id=p.home_node_id, commodity_interests=",".join(p.commodity_interests),
                    consent_at=utcnow(), created_at=utcnow(), provenance="USER_ENTERED")
        db.add(user)
        custody.audit(db, user, "user.register", "user", user.id, {"role": p.role})
    elif user.consent_at is None:                     # invited by an admin: must accept the data notice once
        if body.profile is None or not body.profile.consent:
            db.rollback()
            raise ServiceError(409, "Please accept the data-use notice to continue", "needs_consent")
        user.consent_at = utcnow()
    custody.audit(db, user, "auth.login", "user", user.id)
    db.commit()
    return s.TokenOut(token=issue_token(user), user=s.UserOut.model_validate(user), auth_mode=app_config().auth.mode)


@router.get("/me", response_model=s.UserOut, tags=["auth"])
def me(user: User = Depends(current_user)) -> User:
    return user


# ---------------------------------------------------------------- nodes
@router.get("/nodes", response_model=list[s.NodeOut], tags=["nodes"])
def list_nodes(type: str | None = None, district: str | None = None, include_review: bool = False,
               _: User = Depends(require(*ANY_ROLE)), db: Session = Depends(get_db)) -> list[Node]:
    q = select(Node)
    if type:
        q = q.where(Node.node_type.in_(type.split(",")))
    if district:
        q = q.where(Node.district == district)
    if not include_review:
        q = q.where(or_(Node.needs_review.is_(False), Node.review_status.in_(["accept", "move"])))
    q = q.where(or_(Node.review_status.is_(None), Node.review_status != "reject"))
    return list(db.scalars(q.order_by(Node.node_type, Node.name)))


@router.get("/public/places", tags=["nodes"])
def public_places(type: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    """Unauthenticated reference list for onboarding (pick your location): public names/types/districts only."""
    q = select(Node).where(or_(Node.review_status.is_(None), Node.review_status != "reject"))
    if type:
        q = q.where(Node.node_type.in_(type.split(",")))
    return [{"node_id": n.node_id, "name": n.name, "node_type": n.node_type, "district": n.district,
             "provenance": n.provenance, "needs_review": n.needs_review} for n in db.scalars(q.order_by(Node.district, Node.name))]


@router.post("/feedback", status_code=201, tags=["meta"])
def feedback(body: dict, request: Request, user: User = Depends(require(*ANY_ROLE)), db: Session = Depends(get_db)) -> dict:
    """'Report a problem': stored in the audit log for the team. Never sent anywhere else."""
    enforce(request, "feedback", 10)
    text = str(body.get("message", ""))[:2000]
    if not text.strip():
        raise ServiceError(422, "Please describe the problem", "empty")
    custody.audit(db, user, "feedback.report", "page", str(body.get("page", ""))[:200], {"message": text})
    db.commit()
    return {"ok": True}


@router.get("/nodes/{node_id}", response_model=s.NodeOut, tags=["nodes"])
def get_node(node_id: str, _: User = Depends(require(*ANY_ROLE)), db: Session = Depends(get_db)) -> Node:
    n = db.get(Node, node_id)
    if n is None:
        raise ServiceError(404, "Location not found", "not_found")
    return n


# ---------------------------------------------------------------- consignments (M1)
def _get_c(db: Session, cid: str) -> Consignment:
    c = db.get(Consignment, cid)
    if c is None:
        raise ServiceError(404, "Consignment not found", "not_found")
    return c


@router.post("/consignments", response_model=s.ConsignmentCreated, status_code=201, tags=["M1 traceability"])
def create(body: s.ConsignmentCreate,
           user: User = Depends(require(Role.FARMER, Role.SUPERVISOR, Role.WAREHOUSE, Role.DISPATCHER)),
           db: Session = Depends(get_db)) -> s.ConsignmentCreated:
    r = custody.create_consignment(db, user, commodity=body.commodity, grade=body.grade, qty_kg=body.qty_kg,
                                   harvest_time=body.harvest_time.replace(tzinfo=None), origin_node_id=body.origin_node_id,
                                   client_event_id=body.client_event_id,
                                   # demo personas create demo data: it must carry the DEMO badge everywhere
                                   provenance="SYNTHETIC_DEMO" if user.provenance == "SYNTHETIC_DEMO" else "USER_ENTERED")
    return s.ConsignmentCreated(consignment=s.ConsignmentOut.model_validate(r.consignment), pin=r.pin,
                                qr_payload=r.qr_payload, qr_png=r.qr_png)


@router.get("/consignments", response_model=list[s.ConsignmentOut], tags=["M1 traceability"])
def list_consignments(status: str | None = None, limit: int = Query(100, le=500),
                      user: User = Depends(require(*ANY_ROLE)), db: Session = Depends(get_db)) -> list[Consignment]:
    q = select(Consignment)
    if user.role != Role.ADMIN:
        q = q.where(or_(Consignment.created_by == user.id, Consignment.at_node_id == user.home_node_id,
                        Consignment.in_transit_to == user.home_node_id))
    if status:
        q = q.where(Consignment.status == status)
    return list(db.scalars(q.order_by(Consignment.created_at.desc()).limit(limit)))


@router.get("/consignments/by-code/{short_code}", response_model=s.ConsignmentOut, tags=["M1 traceability"])
def by_code(short_code: str, _: User = Depends(require(*ANY_ROLE)), db: Session = Depends(get_db)) -> Consignment:
    return custody.find_by_code(db, short_code)


@router.post("/consignments/pin-lookup", response_model=s.ConsignmentOut, tags=["M1 traceability"])
def pin_lookup(body: s.PinLookup, request: Request, _: User = Depends(require(*ANY_ROLE)),
               db: Session = Depends(get_db)) -> Consignment:
    """Manual fallback when the QR cannot be scanned: short code + PIN (rate-limited, lockout, expiry)."""
    enforce(request, "pin", app_config().pin.rate_limit_per_min)
    return custody.verify_pin(db, body.short_code, body.pin)


@router.get("/consignments/{cid}", response_model=s.ConsignmentOut, tags=["M1 traceability"])
def get_c(cid: str, _: User = Depends(require(*ANY_ROLE)), db: Session = Depends(get_db)) -> Consignment:
    return _get_c(db, cid)


@router.get("/consignments/{cid}/timeline", tags=["M1 traceability"])
def get_timeline(cid: str, _: User = Depends(require(*ANY_ROLE)), db: Session = Depends(get_db)) -> dict:
    return custody.timeline(db, _get_c(db, cid))


@router.get("/consignments/{cid}/verify", tags=["M1 traceability"])
def verify(cid: str, _: User = Depends(require(*ANY_ROLE)), db: Session = Depends(get_db)) -> dict:
    c = _get_c(db, cid)
    return {"chain": custody.verify_chain(db, c), "mass_balance": custody.mass_balance(c)}


@router.post("/consignments/{cid}/handovers", response_model=s.HandoverOut, status_code=201, tags=["M1 traceability"])
def handover_start(cid: str, body: s.HandoverStart,
                   user: User = Depends(require(Role.FARMER, Role.SUPERVISOR, Role.WAREHOUSE, Role.DISPATCHER)),
                   db: Session = Depends(get_db)) -> Handover:
    return custody.start_handover(db, user, _get_c(db, cid), to_node_id=body.to_node_id, weight_kg=body.weight_kg,
                                  condition=body.condition,
                                  scan_time=body.scan_time.replace(tzinfo=None) if body.scan_time else None,
                                  client_event_id=body.client_event_id)


@router.get("/handovers", response_model=list[s.HandoverOut], tags=["M1 traceability"])
def pending_handovers(user: User = Depends(require(*ANY_ROLE)), db: Session = Depends(get_db)) -> list[Handover]:
    q = select(Handover).where(Handover.status == "PENDING")
    if user.role != Role.ADMIN:
        q = q.where(or_(Handover.to_node == user.home_node_id, Handover.releaser_id == user.id))
    return list(db.scalars(q.order_by(Handover.created_at.desc())))


@router.post("/handovers/{hid}/confirm", response_model=s.HandoverOut, tags=["M1 traceability"])
def handover_confirm(hid: str, body: s.HandoverConfirm,
                     user: User = Depends(require(Role.SUPERVISOR, Role.WAREHOUSE, Role.DISPATCHER, Role.NGO)),
                     db: Session = Depends(get_db)) -> Handover:
    return custody.confirm_handover(db, user, hid, weight_kg=body.weight_kg, condition=body.condition,
                                    scan_time=body.scan_time.replace(tzinfo=None) if body.scan_time else None,
                                    client_event_id=body.client_event_id)


@router.post("/consignments/{cid}/scan", status_code=201, tags=["M1 traceability"])
def scan(cid: str, body: s.TransitScan, user: User = Depends(require(Role.TRANSPORTER)),
         db: Session = Depends(get_db)) -> dict:
    ev = custody.transit_scan(db, user, _get_c(db, cid), lat=body.lat, lon=body.lon,
                              scan_time=body.scan_time.replace(tzinfo=None) if body.scan_time else None,
                              client_event_id=body.client_event_id)
    return {"seq": ev.seq, "hash": ev.hash[:12], "scan_time_utc": ev.scan_time_utc, "sync_time_utc": ev.sync_time_utc}


# ---------------------------------------------------------------- wastage (M2)
@router.get("/wastage/reasons", tags=["M2 wastage"])
def reasons(_: User = Depends(require(*ANY_ROLE))) -> list[dict]:
    return [{"code": k, "label": v, "simulation_driver": wastage.SIMULATION_DRIVER[k],
             "logged_only": wastage.SIMULATION_DRIVER[k] is None} for k, v in wastage.REASON_LABELS["en"].items()]


@router.post("/consignments/{cid}/wastage", response_model=s.WastageRecorded, status_code=201, tags=["M2 wastage"])
def log_wastage(cid: str, body: s.WastageIn, user: User = Depends(require(Role.SUPERVISOR, Role.WAREHOUSE)),
                db: Session = Depends(get_db)) -> s.WastageRecorded:
    c = _get_c(db, cid)
    e = wastage.record_wastage(db, user, c, amount_kg=body.amount_kg, reason=body.reason_code,
                               client_event_id=body.client_event_id)
    return s.WastageRecorded(event=s.QualityEventOut.model_validate(e), consignment=s.ConsignmentOut.model_validate(c),
                             undo_deadline=e.timestamp + timedelta(seconds=app_config().wastage.undo_window_s))


@router.post("/wastage/{event_id}/undo", response_model=s.QualityEventOut, tags=["M2 wastage"])
def undo(event_id: int, user: User = Depends(require(Role.SUPERVISOR, Role.WAREHOUSE)),
         db: Session = Depends(get_db)) -> QualityEvent:
    return wastage.undo_wastage(db, user, event_id)


@router.get("/consignments/{cid}/quality-history", response_model=list[s.QualityEventOut], tags=["M2 wastage"])
def quality_history(cid: str, _: User = Depends(require(*ANY_ROLE)), db: Session = Depends(get_db)) -> list[QualityEvent]:
    return list(db.scalars(select(QualityEvent).where(QualityEvent.consignment_id == cid).order_by(QualityEvent.id)))


# ---------------------------------------------------------------- offline sync
@router.post("/sync", response_model=list[s.SyncResult], tags=["offline"])
def sync(ops: list[s.SyncOp], user: User = Depends(require(*ANY_ROLE)), db: Session = Depends(get_db)) -> list[s.SyncResult]:
    """Replays a device's offline queue in order. Real scan timestamps come in the payload (`scan_time`);
    the server records its own sync time separately. Replays are idempotent via `client_event_id`."""
    out = []
    for op in ops:
        if _already_applied(db, op.client_event_id):
            out.append(s.SyncResult(client_event_id=op.client_event_id, ok=True, status=200, message="already synced"))
            continue
        try:
            p = {**op.payload, "client_event_id": op.client_event_id}
            if op.op == "handover_start":
                hs = s.HandoverStart(**p)
                handover_start(op.consignment_id or "", hs, user=_check_role(user, Role.FARMER, Role.SUPERVISOR, Role.WAREHOUSE, Role.DISPATCHER), db=db)
            elif op.op == "handover_confirm":
                hc = s.HandoverConfirm(**p)
                handover_confirm(op.handover_id or "", hc, user=_check_role(user, Role.SUPERVISOR, Role.WAREHOUSE, Role.DISPATCHER, Role.NGO), db=db)
            elif op.op == "transit_scan":
                scan(op.consignment_id or "", s.TransitScan(**p), user=_check_role(user, Role.TRANSPORTER), db=db)
            elif op.op == "wastage":
                log_wastage(op.consignment_id or "", s.WastageIn(**p), user=_check_role(user, Role.SUPERVISOR, Role.WAREHOUSE), db=db)
            out.append(s.SyncResult(client_event_id=op.client_event_id, ok=True, status=200, message="synced"))
        except ServiceError as e:
            db.rollback()
            ok = e.code == "duplicate_event"          # already applied on an earlier sync → fine
            out.append(s.SyncResult(client_event_id=op.client_event_id, ok=ok, status=e.status,
                                    message="already synced" if ok else e.message))
        except Exception as e:  # noqa: BLE001 - report per op, keep going
            db.rollback()
            out.append(s.SyncResult(client_event_id=op.client_event_id, ok=False, status=422, message=str(e)[:200]))
    return out


def _already_applied(db: Session, client_event_id: str) -> bool:
    """Idempotency is checked before any state validation, so a replay never fails on 'wrong state'."""
    from app.models.orm import CustodyEvent
    return (db.scalar(select(CustodyEvent.id).where(CustodyEvent.client_event_id == client_event_id)) is not None
            or db.scalar(select(QualityEvent.id).where(QualityEvent.client_event_id == client_event_id)) is not None)


def _check_role(user: User, *roles: Role) -> User:
    if user.role != Role.ADMIN and user.role not in {r.value for r in roles}:
        raise ServiceError(403, f"Role {user.role} cannot do this", "forbidden")
    return user


# ---------------------------------------------------------------- admin
@router.get("/admin/audit", tags=["admin"])
def audit_log(limit: int = Query(200, le=2000), _: User = Depends(require(Role.ADMIN)), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))
    return [{"id": r.id, "at_utc": r.at_utc, "actor_id": r.actor_id, "request_id": r.request_id, "action": r.action,
             "entity": r.entity, "entity_id": r.entity_id, "detail": r.detail} for r in rows]
