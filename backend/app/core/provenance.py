"""Provenance tags (honesty contract §1.2). Every datum that reaches the UI or a metric carries one."""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Provenance(StrEnum):
    REAL_FETCHED = "REAL_FETCHED"      # downloaded from a named source (url, timestamp, licence, checksum)
    REAL_DERIVED = "REAL_DERIVED"      # computed from REAL_FETCHED by documented code
    USER_ENTERED = "USER_ENTERED"      # typed/scanned by a user in the app
    ASSUMPTION = "ASSUMPTION"          # a parameter we chose (rationale + needs-validation flag)
    SYNTHETIC_DEMO = "SYNTHETIC_DEMO"  # seeded generator output, demonstration only


DEMO_BADGE_REQUIRED = {Provenance.SYNTHETIC_DEMO}


class Tagged(BaseModel):
    """A value with its provenance, for API payloads that mix sources."""

    model_config = ConfigDict(frozen=True)
    value: float | int | str | None
    provenance: Provenance
    source: str | None = None
    note: str | None = None


def weakest(*tags: Provenance) -> Provenance:
    """Provenance of a value computed from several inputs = the least real input.

    Order (most → least real): REAL_FETCHED, REAL_DERIVED, USER_ENTERED, ASSUMPTION, SYNTHETIC_DEMO.
    A computation over any REAL input yields at best REAL_DERIVED.
    """
    order = [Provenance.REAL_FETCHED, Provenance.REAL_DERIVED, Provenance.USER_ENTERED,
             Provenance.ASSUMPTION, Provenance.SYNTHETIC_DEMO]
    worst = max(tags, key=order.index) if tags else Provenance.ASSUMPTION
    return Provenance.REAL_DERIVED if worst == Provenance.REAL_FETCHED else worst
