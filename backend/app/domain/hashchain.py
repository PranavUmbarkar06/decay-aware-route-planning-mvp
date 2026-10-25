"""Tamper-evident custody log (ADR-012): append-only, each event stores the SHA-256 of the previous one.

Not a blockchain: there is no distributed consensus. Anyone holding the event list can recompute the
chain and detect an edited, removed or reordered event.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

HASHED_FIELDS = ("consignment_id", "seq", "event_type", "from_node", "to_node", "actor_release", "actor_receive",
                 "weight_released_kg", "weight_received_kg", "condition_released", "condition_received",
                 "scan_time_utc", "lat", "lon", "note")


def genesis_hash(consignment_id: str) -> str:
    return hashlib.sha256(f"genesis:{consignment_id}".encode()).hexdigest()


def _canonical(event: Mapping[str, Any]) -> str:
    payload = {k: event.get(k) for k in HASHED_FIELDS}
    for k, v in payload.items():   # floats are hashed at fixed precision so DB round-trips do not break the chain
        if isinstance(v, float):
            payload[k] = f"{v:.6f}"
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def event_hash(event: Mapping[str, Any], prev_hash: str) -> str:
    return hashlib.sha256((prev_hash + "|" + _canonical(event)).encode("utf-8")).hexdigest()


def chain(consignment_id: str, events: Iterable[dict]) -> list[dict]:
    """Return events with seq, prev_hash and hash filled in (used when building fixtures/simulations)."""
    out, prev = [], genesis_hash(consignment_id)
    for i, e in enumerate(events):
        e = {**e, "consignment_id": consignment_id, "seq": i}
        e["prev_hash"] = prev
        e["hash"] = event_hash(e, prev)
        prev = e["hash"]
        out.append(e)
    return out


def verify(consignment_id: str, events: Sequence[Mapping[str, Any]], expected_head: str | None = None,
           expected_count: int | None = None) -> tuple[bool, int | None, str]:
    """(ok, first_bad_seq, reason). Events must be ordered by seq.

    A chain alone cannot detect removal of its *last* events (tail truncation). The consignment record
    therefore stores the head hash and event count; pass them as `expected_head` / `expected_count`.
    """
    if expected_count is not None and len(events) != expected_count:
        return False, min(len(events), expected_count), (
            f"event count {len(events)} ≠ recorded {expected_count} (events removed or added)")
    if expected_head is not None and (events[-1]["hash"] if events else None) != expected_head:
        return False, len(events) - 1, "last event hash ≠ recorded head hash (tail truncated or replaced)"
    prev = genesis_hash(consignment_id)
    for i, e in enumerate(events):
        if e.get("seq") != i:
            return False, i, f"sequence gap or reorder at position {i} (seq={e.get('seq')})"
        if e.get("prev_hash") != prev:
            return False, i, "prev_hash does not match the previous event's hash (event removed or reordered)"
        if event_hash(e, prev) != e.get("hash"):
            return False, i, "event content does not match its hash (event edited)"
        prev = e["hash"]
    return True, None, "chain verifies end to end"
