"""Domain model (project brief §6). Pure Python, no database: shared by the simulation engine and by the
service layer's invariant checks. The service layer persists the same state transitions via SQLAlchemy.

Invariants (property-tested in tests/test_domain_properties.py):
  I1 mass balance: initial = current + sold + donated + processed + wasted + unreconciled   (per consignment)
  I2 quantities never negative
  I3 custody chain hash verifies end to end
  I4 a consignment is never in two places: exactly one of (at_node, in_transit_to) is set, or it is CLOSED
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.core.provenance import Provenance
from app.domain import hashchain

EPS = 1e-6


class ReasonCode(StrEnum):
    HEAT_ROT = "HEAT_ROT"
    CRUSHED = "CRUSHED"
    WET = "WET"
    UNSOLD = "UNSOLD"


# Reasons the decay model can generate. WET and UNSOLD are logged-only (ASSUMPTIONS.md).
SIMULATION_DRIVEN_REASONS = {ReasonCode.HEAT_ROT, ReasonCode.CRUSHED}


class Disposition(StrEnum):
    SOLD = "SOLD"
    DONATED = "DONATED"
    PROCESSED = "PROCESSED"
    WASTED = "WASTED"


class Status(StrEnum):
    AT_NODE = "AT_NODE"
    IN_TRANSIT = "IN_TRANSIT"
    DISPUTED_WEIGHT = "DISPUTED_WEIGHT"
    CLOSED = "CLOSED"


class DomainError(ValueError):
    pass


@dataclass
class QualityEntry:
    timestamp: datetime
    qty_kg: float
    quality: float
    event_type: str             # CREATED | WASTAGE | DECAY | HANDOVER | DISPOSITION | UNDO
    reason_code: str | None
    amount_kg: float
    provenance: Provenance


@dataclass
class Consignment:
    id: str
    short_code: str
    commodity: str
    grade: str
    initial_qty_kg: float
    harvest_time: datetime
    origin_node: str
    quality_score: float = 1.0
    dispatch_time: datetime | None = None
    pin_hash: str | None = None
    provenance: Provenance = Provenance.USER_ENTERED
    current_qty_kg: float = field(init=False)
    at_node: str | None = field(init=False)
    in_transit_to: str | None = None
    status: Status = Status.AT_NODE
    disposed: dict[str, float] = field(default_factory=lambda: {d.value: 0.0 for d in Disposition})
    unreconciled_kg: float = 0.0          # disputed handover differences: surfaced, never booked as waste
    custody_chain: list[dict] = field(default_factory=list)
    chain_head: str | None = None         # recorded head hash + count detect tail truncation
    chain_count: int = 0
    quality_history: list[QualityEntry] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.initial_qty_kg <= 0:
            raise DomainError("initial quantity must be positive")
        if not 0 <= self.quality_score <= 1:
            raise DomainError("quality must be in [0, 1]")
        self.current_qty_kg = self.initial_qty_kg
        self.at_node = self.origin_node
        self._log_quality(self.harvest_time, "CREATED", None, 0.0)
        self._append_custody({"event_type": "CREATED", "from_node": None, "to_node": self.origin_node,
                              "weight_received_kg": self.initial_qty_kg, "scan_time_utc": self.harvest_time.isoformat()})

    # ------------------------------------------------------------ bookkeeping
    def _log_quality(self, t: datetime, event_type: str, reason: str | None, amount: float,
                     provenance: Provenance | None = None) -> None:
        self.quality_history.append(QualityEntry(t, self.current_qty_kg, self.quality_score, event_type, reason,
                                                 amount, provenance or self.provenance))

    def _append_custody(self, ev: dict) -> None:
        prev = self.custody_chain[-1]["hash"] if self.custody_chain else hashchain.genesis_hash(self.id)
        e = {**ev, "consignment_id": self.id, "seq": len(self.custody_chain), "prev_hash": prev}
        e["hash"] = hashchain.event_hash(e, prev)
        self.custody_chain.append(e)
        self.chain_head, self.chain_count = e["hash"], len(self.custody_chain)

    def _remove(self, amount: float) -> None:
        if amount < -EPS:
            raise DomainError("amount must be non-negative")
        if amount > self.current_qty_kg + EPS:
            raise DomainError(f"amount {amount:.2f} kg exceeds current quantity {self.current_qty_kg:.2f} kg")
        self.current_qty_kg = max(0.0, self.current_qty_kg - amount)

    # ------------------------------------------------------------ §6 operations
    def record_wastage(self, amount: float, reason: ReasonCode | str, t: datetime,
                       provenance: Provenance | None = None) -> QualityEntry:
        reason = ReasonCode(reason)
        if self.status == Status.CLOSED:
            raise DomainError("consignment is closed")
        self._remove(amount)
        self.disposed[Disposition.WASTED] += amount
        self._log_quality(t, "WASTAGE", reason.value, amount, provenance)
        return self.quality_history[-1]

    def undo_wastage(self, entry: QualityEntry, t: datetime) -> None:
        """Soft undo: re-credits the quantity and appends an UNDO entry; nothing is deleted."""
        if entry.event_type != "WASTAGE":
            raise DomainError("only wastage entries can be undone")
        self.disposed[Disposition.WASTED] -= entry.amount_kg
        self.current_qty_kg += entry.amount_kg
        self._log_quality(t, "UNDO", entry.reason_code, -entry.amount_kg)

    def dispose(self, kind: Disposition | str, amount: float, t: datetime, at_node: str | None = None) -> None:
        kind = Disposition(kind)
        if kind == Disposition.WASTED:
            raise DomainError("use record_wastage for waste")
        self._remove(amount)
        self.disposed[kind] += amount
        self._log_quality(t, "DISPOSITION", kind.value, amount)
        if self.current_qty_kg <= EPS:
            self.close(t)

    def close(self, t: datetime) -> None:
        self.status = Status.CLOSED
        self.at_node = None
        self.in_transit_to = None

    def apply_decay(self, new_quality: float, t: datetime) -> None:
        if not 0 <= new_quality <= 1:
            raise DomainError("quality must be in [0, 1]")
        self.quality_score = min(self.quality_score, new_quality)   # quality never improves
        self._log_quality(t, "DECAY", None, 0.0)

    # ------------------------------------------------------------ invariants
    def mass_balance_error(self) -> float:
        return self.initial_qty_kg - (self.current_qty_kg + sum(self.disposed.values()) + self.unreconciled_kg)

    def check_invariants(self) -> None:
        if abs(self.mass_balance_error()) > 1e-6 * max(1.0, self.initial_qty_kg):
            raise AssertionError(f"I1 mass balance broken by {self.mass_balance_error():.6f} kg")
        if self.current_qty_kg < -EPS or any(v < -EPS for v in self.disposed.values()):
            raise AssertionError("I2 negative quantity")
        ok, _, why = hashchain.verify(self.id, self.custody_chain, expected_head=self.chain_head,
                                      expected_count=self.chain_count)
        if not ok:
            raise AssertionError(f"I3 custody chain: {why}")
        places = (self.at_node is not None) + (self.in_transit_to is not None)
        if self.status == Status.CLOSED and places != 0:
            raise AssertionError("I4 closed consignment still located")
        if self.status != Status.CLOSED and places != 1:
            raise AssertionError(f"I4 consignment in {places} places")


@dataclass
class Node:
    """Base node. Holds consignments by id; `receive_consignment` / `release` move custody."""
    node_id: str
    name: str
    node_type: str = "Node"
    provenance: Provenance = Provenance.REAL_DERIVED
    capacity_kg: float | None = None
    stock: dict[str, Consignment] = field(default_factory=dict)

    def stock_kg(self) -> float:
        return sum(c.current_qty_kg for c in self.stock.values())

    def release(self, c: Consignment, to_node: str, t: datetime, *, weight_kg: float | None = None,
                condition: str | None = None, actor: str | None = None) -> None:
        if c.id not in self.stock or c.at_node != self.node_id:
            raise DomainError(f"{c.id} is not held at {self.node_id}")
        del self.stock[c.id]
        c.at_node, c.in_transit_to, c.status = None, to_node, Status.IN_TRANSIT
        if c.dispatch_time is None:
            c.dispatch_time = t
        c._append_custody({"event_type": "RELEASE", "from_node": self.node_id, "to_node": to_node,
                           "actor_release": actor, "weight_released_kg": weight_kg if weight_kg is not None else c.current_qty_kg,
                           "condition_released": condition, "scan_time_utc": t.isoformat()})

    def receive_consignment(self, c: Consignment, t: datetime, *, weight_kg: float | None = None,
                            condition: str | None = None, actor: str | None = None,
                            tolerance_pct: float = 2.0) -> float:
        """Returns the weight difference (released − received). Beyond tolerance → DISPUTED_WEIGHT and the
        difference moves to `unreconciled_kg` (never auto-booked as wastage)."""
        if c.status != Status.IN_TRANSIT or c.in_transit_to != self.node_id:
            raise DomainError(f"{c.id} is not in transit to {self.node_id}")
        if self.capacity_kg is not None and self.stock_kg() + c.current_qty_kg > self.capacity_kg + EPS:
            raise DomainError(f"{self.node_id} capacity exceeded")
        received = c.current_qty_kg if weight_kg is None else weight_kg
        diff = c.current_qty_kg - received
        disputed = abs(diff) > c.current_qty_kg * tolerance_pct / 100
        if disputed:
            c.current_qty_kg = received
            c.unreconciled_kg += diff
            c.status = Status.DISPUTED_WEIGHT
        else:
            c.status = Status.AT_NODE
        c.at_node, c.in_transit_to = self.node_id, None
        self.stock[c.id] = c
        c._append_custody({"event_type": "RECEIVE_DISPUTED" if disputed else "RECEIVE", "from_node": None,
                           "to_node": self.node_id, "actor_receive": actor, "weight_received_kg": received,
                           "condition_received": condition, "scan_time_utc": t.isoformat()})
        c._log_quality(t, "HANDOVER", None, 0.0)
        return diff


class FarmGatherPoint(Node):
    pass


class AssemblyMandi(Node):
    pass


class NGOSink(Node):
    pass


class ProcessingSink(Node):
    pass
