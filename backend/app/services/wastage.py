"""M2 1-Tap Visual Wastage Logger (service layer).

`record_wastage(amount, reason)` appends a standardised entry to the consignment's quality history.
Guards: amount ≤ current quantity; reason is one of the four enum codes; the entry can be undone within
`wastage.undo_window_s` (soft: the original row is marked `undone_at` and a compensating UNDO row is added).
WET and UNSOLD are logged-only reasons with no simulation driver (ASSUMPTIONS.md). UNSOLD additionally flags the
lot for M5 rescue / redirection.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now as utcnow
from app.core.config import app_config
from app.core.provenance import Provenance
from app.core.security import Role
from app.domain.model import ReasonCode
from app.models.orm import Consignment, QualityEvent, User
from app.services.custody import ServiceError, audit

REASON_LABELS = {  # display labels; icons are in the frontend and always shown with text
    "en": {"HEAT_ROT": "Heat / rotted", "CRUSHED": "Crushed in transit", "WET": "Wet / moisture", "UNSOLD": "Unsold at market"},
}
SIMULATION_DRIVER = {"HEAT_ROT": "temperature × time (decay model)", "CRUSHED": "handling distance (ASSUMPTION A6)",
                     "WET": None, "UNSOLD": None}


def record_wastage(db: Session, user: User, c: Consignment, *, amount_kg: float, reason: str,
                   client_event_id: str | None = None) -> QualityEvent:
    try:
        reason = ReasonCode(reason).value
    except ValueError:
        raise ServiceError(422, f"Reason must be one of {[r.value for r in ReasonCode]}", "bad_reason") from None
    if c.status in ("CLOSED", "IN_TRANSIT"):
        raise ServiceError(409, f"Cannot log wastage while the lot is {c.status.lower().replace('_', ' ')}", "bad_state")
    if user.role not in (Role.ADMIN, Role.SUPERVISOR, Role.WAREHOUSE) or (
            user.role != Role.ADMIN and user.home_node_id != c.at_node_id):
        raise ServiceError(403, "Only the supervisor or warehouse holding this lot can log wastage", "not_holder")
    if amount_kg <= 0:
        raise ServiceError(422, "Move the slider above 0 kg", "bad_amount")
    if amount_kg > c.current_qty_kg + 1e-9:
        raise ServiceError(422, f"Cannot log more than the {c.current_qty_kg:.1f} kg in this lot", "exceeds_current")
    if client_event_id and db.scalar(select(QualityEvent.id).where(QualityEvent.client_event_id == client_event_id)):
        raise ServiceError(409, "Already recorded", "duplicate_event")
    c.current_qty_kg -= amount_kg
    c.wasted_kg += amount_kg
    e = QualityEvent(consignment_id=c.id, timestamp=utcnow(), qty_kg=c.current_qty_kg, quality=c.quality_score,
                     event_type="WASTAGE", reason_code=reason, amount_kg=amount_kg, actor_id=user.id,
                     client_event_id=client_event_id,
                     provenance=Provenance.SYNTHETIC_DEMO if c.provenance == Provenance.SYNTHETIC_DEMO else Provenance.USER_ENTERED)
    db.add(e)
    audit(db, user, "wastage.record", "consignment", c.id, {"amount_kg": amount_kg, "reason": reason})
    db.commit()
    return e


def undo_wastage(db: Session, user: User, event_id: int) -> QualityEvent:
    e = db.get(QualityEvent, event_id)
    if e is None or e.event_type != "WASTAGE":
        raise ServiceError(404, "Wastage entry not found", "not_found")
    if e.undone_at is not None:
        raise ServiceError(409, "Already undone", "already_undone")
    if e.actor_id != user.id and user.role != Role.ADMIN:
        raise ServiceError(403, "Only the person who logged it can undo", "not_owner")
    window = timedelta(seconds=app_config().wastage.undo_window_s)
    if utcnow() - e.timestamp > window:
        raise ServiceError(409, "The undo window has passed; log a correction instead", "undo_expired")
    c = db.get(Consignment, e.consignment_id)
    assert c is not None
    c.current_qty_kg += e.amount_kg
    c.wasted_kg -= e.amount_kg
    e.undone_at = utcnow()
    u = QualityEvent(consignment_id=c.id, timestamp=utcnow(), qty_kg=c.current_qty_kg, quality=c.quality_score,
                     event_type="UNDO", reason_code=e.reason_code, amount_kg=-e.amount_kg, actor_id=user.id,
                     undo_of=e.id, provenance=Provenance.USER_ENTERED)
    db.add(u)
    audit(db, user, "wastage.undo", "consignment", c.id, {"event_id": e.id, "amount_kg": e.amount_kg})
    db.commit()
    return u
