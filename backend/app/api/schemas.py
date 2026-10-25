"""Request/response models (pydantic). Responses that carry data shown in the UI include `provenance`."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiError(BaseModel):
    status: int
    code: str
    message: str


class OtpRequest(BaseModel):
    phone: str = Field(pattern=r"^\+?\d{10,15}$", examples=["+910000000001"])


class OtpRequested(BaseModel):
    challenge_id: str
    expires_in_s: int
    delivery: str
    dev_otp: str | None = Field(None, description="Only present in dev_stub mode (DEV AUTH)")


class Profile(BaseModel):
    role: str
    name: str | None = Field(None, max_length=120)
    language: Literal["en", "hi", "mr"] = "en"
    district: str | None = None
    home_node_id: str | None = None
    commodity_interests: list[str] = []
    consent: bool = Field(description="User accepted the data-use consent screen")


class OtpVerify(BaseModel):
    challenge_id: str
    code: str = Field(pattern=r"^\d{6}$")
    profile: Profile | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    phone: str
    role: str
    name: str | None
    language: str
    district: str | None
    home_node_id: str | None
    provenance: str


class TokenOut(BaseModel):
    token: str
    user: UserOut
    auth_mode: str


class NodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    node_id: str
    node_type: str
    name: str
    lat: float | None
    lon: float | None
    district: str | None
    geocode_method: str | None
    geocode_confidence: float | None
    snap_distance_m: float | None
    capacity_kg: float | None
    capacity_source: str | None
    provenance: str
    needs_review: bool
    review_status: str | None
    notes: str | None


class ConsignmentCreate(BaseModel):
    commodity: str
    grade: str = Field("A", max_length=20)
    qty_kg: float = Field(gt=0, le=100_000)
    harvest_time: datetime
    origin_node_id: str
    client_event_id: str | None = Field(None, max_length=64)


class ConsignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    short_code: str
    commodity: str
    grade: str
    initial_qty_kg: float
    current_qty_kg: float
    sold_kg: float
    donated_kg: float
    processed_kg: float
    wasted_kg: float
    unreconciled_kg: float
    quality_score: float
    harvest_time: datetime
    dispatch_time: datetime | None
    origin_node_id: str
    at_node_id: str | None
    in_transit_to: str | None
    status: str
    chain_count: int
    provenance: str


class ConsignmentCreated(BaseModel):
    consignment: ConsignmentOut
    pin: str = Field(description="Shown once. Not stored in clear; write it on the label.")
    qr_payload: str
    qr_png: str


class PinLookup(BaseModel):
    short_code: str = Field(min_length=6, max_length=14)
    pin: str = Field(pattern=r"^\d{4,8}$")


class HandoverStart(BaseModel):
    to_node_id: str
    weight_kg: float = Field(gt=0)
    condition: str
    scan_time: datetime | None = None
    client_event_id: str | None = Field(None, max_length=64)


class HandoverConfirm(BaseModel):
    weight_kg: float = Field(ge=0)
    condition: str
    scan_time: datetime | None = None
    client_event_id: str | None = Field(None, max_length=64)


class HandoverOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    consignment_id: str
    from_node: str
    to_node: str
    weight_released_kg: float
    weight_received_kg: float | None
    condition_released: str
    condition_received: str | None
    status: str
    difference_kg: float | None
    created_at: datetime
    completed_at: datetime | None


class TransitScan(BaseModel):
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    scan_time: datetime | None = None
    client_event_id: str | None = Field(None, max_length=64)


class WastageIn(BaseModel):
    amount_kg: float = Field(gt=0)
    reason_code: Literal["HEAT_ROT", "CRUSHED", "WET", "UNSOLD"]
    client_event_id: str | None = Field(None, max_length=64)


class QualityEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    consignment_id: str
    timestamp: datetime
    qty_kg: float
    quality: float
    event_type: str
    reason_code: str | None
    amount_kg: float
    undone_at: datetime | None
    undo_of: int | None
    provenance: str


class WastageRecorded(BaseModel):
    event: QualityEventOut
    consignment: ConsignmentOut
    undo_deadline: datetime


class SyncOp(BaseModel):
    """One queued offline action. `client_event_id` makes replays idempotent."""
    op: Literal["handover_start", "handover_confirm", "transit_scan", "wastage"]
    client_event_id: str = Field(max_length=64)
    consignment_id: str | None = None
    handover_id: str | None = None
    payload: dict


class SyncResult(BaseModel):
    client_event_id: str
    ok: bool
    status: int
    message: str
