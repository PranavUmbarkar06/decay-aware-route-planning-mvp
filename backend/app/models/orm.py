"""SQLAlchemy models. Timestamps are stored in UTC (naive UTC datetimes); the UI shows IST.

Every row that can reach the UI carries `provenance`. Custody events are append-only (no UPDATE/DELETE in the
service layer; enforced by tests) and hash-chained; the consignment row holds the chain head + count.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(20))
    name: Mapped[str | None] = mapped_column(String(120))
    language: Mapped[str] = mapped_column(String(5), default="en")
    district: Mapped[str | None] = mapped_column(String(60))
    home_node_id: Mapped[str | None] = mapped_column(ForeignKey("nodes.node_id"))
    commodity_interests: Mapped[str | None] = mapped_column(String(200))
    consent_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    provenance: Mapped[str] = mapped_column(String(20), default="USER_ENTERED")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class OtpChallenge(Base):
    __tablename__ = "otp_challenges"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    code_hash: Mapped[str] = mapped_column(String(200))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class Node(Base):
    __tablename__ = "nodes"
    node_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    node_type: Mapped[str] = mapped_column(String(30), index=True)
    name: Mapped[str] = mapped_column(String(200))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    district: Mapped[str | None] = mapped_column(String(60))
    snapped_graph_node: Mapped[str | None] = mapped_column(String(30))
    snap_distance_m: Mapped[float | None] = mapped_column(Float)
    geocode_method: Mapped[str | None] = mapped_column(String(40))
    geocode_confidence: Mapped[float | None] = mapped_column(Float)
    capacity_kg: Mapped[float | None] = mapped_column(Float)
    capacity_source: Mapped[str | None] = mapped_column(String(80))
    provenance: Mapped[str] = mapped_column(String(20))
    source_manifest_id: Mapped[str | None] = mapped_column(String(200))
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_status: Mapped[str | None] = mapped_column(String(20))       # None | accept | move | reject (USER_ENTERED)
    notes: Mapped[str | None] = mapped_column(Text)
    agmarknet_market_name: Mapped[str | None] = mapped_column(String(200))


class Consignment(Base):
    __tablename__ = "consignments"
    __table_args__ = (
        CheckConstraint("current_qty_kg >= 0", name="ck_current_nonneg"),
        CheckConstraint("initial_qty_kg > 0", name="ck_initial_pos"),
        CheckConstraint("quality_score >= 0 AND quality_score <= 1", name="ck_quality_range"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    short_code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    pin_hash: Mapped[str] = mapped_column(String(200))
    pin_issued_at: Mapped[datetime] = mapped_column(DateTime)
    pin_failures: Mapped[int] = mapped_column(Integer, default=0)
    pin_locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    commodity: Mapped[str] = mapped_column(String(20))
    grade: Mapped[str] = mapped_column(String(20))
    initial_qty_kg: Mapped[float] = mapped_column(Float)
    current_qty_kg: Mapped[float] = mapped_column(Float)
    sold_kg: Mapped[float] = mapped_column(Float, default=0.0)
    donated_kg: Mapped[float] = mapped_column(Float, default=0.0)
    processed_kg: Mapped[float] = mapped_column(Float, default=0.0)
    wasted_kg: Mapped[float] = mapped_column(Float, default=0.0)
    unreconciled_kg: Mapped[float] = mapped_column(Float, default=0.0)
    quality_score: Mapped[float] = mapped_column(Float, default=1.0)
    harvest_time: Mapped[datetime] = mapped_column(DateTime)
    dispatch_time: Mapped[datetime | None] = mapped_column(DateTime)
    origin_node_id: Mapped[str] = mapped_column(ForeignKey("nodes.node_id"))
    at_node_id: Mapped[str | None] = mapped_column(ForeignKey("nodes.node_id"))
    in_transit_to: Mapped[str | None] = mapped_column(ForeignKey("nodes.node_id"))
    status: Mapped[str] = mapped_column(String(20), index=True)
    chain_head: Mapped[str] = mapped_column(String(64))
    chain_count: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)          # optimistic concurrency
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    provenance: Mapped[str] = mapped_column(String(20))

    __mapper_args__ = {"version_id_col": version}

    events: Mapped[list[CustodyEvent]] = relationship(order_by="CustodyEvent.seq", back_populates="consignment")


class CustodyEvent(Base):
    """Append-only. `scan_time_utc` = when the scan happened on the device (may be offline);
    `sync_time_utc` = when the server received it."""
    __tablename__ = "custody_events"
    __table_args__ = (UniqueConstraint("consignment_id", "seq"), UniqueConstraint("client_event_id"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    consignment_id: Mapped[str] = mapped_column(ForeignKey("consignments.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(30))
    from_node: Mapped[str | None] = mapped_column(String(20))
    to_node: Mapped[str | None] = mapped_column(String(20))
    actor_release: Mapped[str | None] = mapped_column(String(36))
    actor_receive: Mapped[str | None] = mapped_column(String(36))
    weight_released_kg: Mapped[float | None] = mapped_column(Float)
    weight_received_kg: Mapped[float | None] = mapped_column(Float)
    condition_released: Mapped[str | None] = mapped_column(String(30))
    condition_received: Mapped[str | None] = mapped_column(String(30))
    scan_time_utc: Mapped[str] = mapped_column(String(32))
    sync_time_utc: Mapped[datetime] = mapped_column(DateTime)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(String(300))
    client_event_id: Mapped[str | None] = mapped_column(String(64))
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
    provenance: Mapped[str] = mapped_column(String(20))
    consignment: Mapped[Consignment] = relationship(back_populates="events")


class Handover(Base):
    """Two-party confirmation: releaser declares weight+condition, receiver confirms."""
    __tablename__ = "handovers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    consignment_id: Mapped[str] = mapped_column(ForeignKey("consignments.id"), index=True)
    from_node: Mapped[str] = mapped_column(ForeignKey("nodes.node_id"))
    to_node: Mapped[str] = mapped_column(ForeignKey("nodes.node_id"))
    releaser_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    receiver_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    weight_released_kg: Mapped[float] = mapped_column(Float)
    weight_received_kg: Mapped[float | None] = mapped_column(Float)
    condition_released: Mapped[str] = mapped_column(String(30))
    condition_received: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), index=True)       # PENDING | COMPLETED | DISPUTED_WEIGHT | CANCELLED
    difference_kg: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class QualityEvent(Base):
    """Consignment.quality_history. Wastage entries can be undone within a window (soft: `undone_at` +
    a compensating UNDO row); nothing is deleted."""
    __tablename__ = "quality_events"
    __table_args__ = (UniqueConstraint("client_event_id"), Index("ix_qe_cons_time", "consignment_id", "timestamp"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    consignment_id: Mapped[str] = mapped_column(ForeignKey("consignments.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime)
    qty_kg: Mapped[float] = mapped_column(Float)
    quality: Mapped[float] = mapped_column(Float)
    event_type: Mapped[str] = mapped_column(String(20))    # CREATED | WASTAGE | UNDO | DECAY | HANDOVER | DISPOSITION
    reason_code: Mapped[str | None] = mapped_column(String(20))
    amount_kg: Mapped[float] = mapped_column(Float, default=0.0)
    actor_id: Mapped[str | None] = mapped_column(String(36))
    undone_at: Mapped[datetime | None] = mapped_column(DateTime)
    undo_of: Mapped[int | None] = mapped_column(ForeignKey("quality_events.id"))
    client_event_id: Mapped[str | None] = mapped_column(String(64))
    provenance: Mapped[str] = mapped_column(String(20))


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at_utc: Mapped[datetime] = mapped_column(DateTime, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(36))
    request_id: Mapped[str | None] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text)
