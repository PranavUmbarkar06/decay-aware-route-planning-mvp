"""Explainable parametric decay model (ADR-018), shared by M3 (shelf-life traffic light) and the simulation.

Physiological age. A lot accumulates "reference hours" a: one hour at temperature T adds v(T)/v(T_ref)
reference hours, where v is the relative deterioration velocity from FAO AGS Bulletin 152 Table 1
(log-linear interpolation, held flat outside 0–40 °C), or Q10^((T−T_ref)/10) in q10 mode (sensitivity runs).

Within-lot variation (ASSUMPTION A17). Units in a lot do not all fail at once: unit life is lognormal
around the commodity's reference life L_ref with shape σ (`spread_sigma`). The fraction of units spoiled
at age a is F(a) = Φ(ln(a / L_ref) / σ). At a = L_ref half the units are past their life.

Outputs:
- quality score q = 1 − F(a), the saleable fraction (0–1)
- remaining life (h at the current temperature) until F reaches `traffic_quantile` (default 0.5)
- expected loss over a horizon = current qty × (F(a_end) − F(a_now)) / (1 − F(a_now))

Every prediction carries a provenance summary and the extrapolation warning (ASSUMPTIONS A2, A3, A17).
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
import pandas as pd

from app.core.config import ROOT, commodities_config
from app.core.provenance import Provenance

EXTRAPOLATION_WARNING = ("Reference shelf lives are for cold/optimal storage; extrapolating them to ambient "
                         "transit temperatures uses FAO's generic curve and is an assumption, not a field measurement.")
SPREAD_SIGMA_DEFAULT = 0.25   # ASSUMPTION A17: lognormal shape of unit-to-unit life variation; needs validation


@lru_cache
def fao_table() -> tuple[np.ndarray, np.ndarray]:
    cfg = commodities_config().temperature_model
    t = pd.read_csv(ROOT / cfg.table_csv)
    return t["temp_c"].to_numpy(float), t["relative_velocity"].to_numpy(float)


def rel_velocity(temp_c: float | np.ndarray, mode: str = "fao_table1", q10: float = 2.5, ref_c: float = 0.0):
    """Relative deterioration velocity (dimensionless; 1.0 at 0 °C in FAO mode)."""
    lo, hi = commodities_config().temperature_model.clamp_c
    tc = np.clip(np.asarray(temp_c, dtype=float), lo, hi)
    if mode == "q10":
        return q10 ** ((tc - ref_c) / 10.0)
    xs, vs = fao_table()
    return np.exp(np.interp(tc, xs, np.log(vs)))


def _phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _phi_inv(p: float) -> float:
    # Acklam-free: bisection is exact enough for p in (1e-9, 1-1e-9) and keeps dependencies minimal
    lo, hi = -10.0, 10.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if _phi(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


@dataclass(frozen=True)
class CommodityProfile:
    key: str
    life_ref_h: float
    ref_temp_c: float
    status: str
    source: str | None
    handling_per_100km: float
    warnings: tuple[str, ...]

    @classmethod
    def load(cls, key: str) -> CommodityProfile:
        cc = commodities_config()
        c = cc.commodities[key]
        warn = [EXTRAPOLATION_WARNING]
        if c.base_shelf_life_h.status == "MISSING" or c.base_shelf_life_h.value is None:
            life, ref = cc.missing_placeholder.base_shelf_life_h, cc.missing_placeholder.ref_temp_c
            warn.append(cc.missing_placeholder.warning)
            status, source = "ASSUMPTION", None
        else:
            life, ref = float(c.base_shelf_life_h.value), float(c.base_shelf_life_h.ref_temp_c or 0.0)
            status, source = c.base_shelf_life_h.status, c.base_shelf_life_h.source
            if c.base_shelf_life_h.note:
                warn.append(c.base_shelf_life_h.note)
        return cls(key, life, ref, status, source, float(c.handling_damage_per_100km.value or 0.0), tuple(warn))


@dataclass
class Driver:
    name: str
    value: float
    unit: str
    provenance: str
    explanation: str


@dataclass
class LossPrediction:
    expected_loss_kg: float
    remaining_life_h: float
    quality_now: float
    quality_end: float
    drivers: list[Driver]
    inputs_provenance: dict[str, str]
    warnings: list[str] = field(default_factory=list)
    sensitivity: dict[str, float] = field(default_factory=dict)   # remaining life under Q10=2 / Q10=3


@dataclass
class DecayModel:
    profile: CommodityProfile
    mode: str = "fao_table1"
    q10: float = 2.5
    sigma: float = SPREAD_SIGMA_DEFAULT
    traffic_quantile: float = 0.5

    # ---- age <-> quality
    def _v(self, t_c):
        return rel_velocity(t_c, self.mode, self.q10, self.profile.ref_temp_c)

    def accel(self, temp_c: float) -> float:
        """How many reference hours one hour at temp_c consumes."""
        return float(self._v(temp_c) / self._v(self.profile.ref_temp_c))

    def spoiled_fraction(self, age_ref_h: float) -> float:
        if age_ref_h <= 0:
            return 0.0
        return _phi(math.log(age_ref_h / self.profile.life_ref_h) / self.sigma)

    def quality(self, age_ref_h: float) -> float:
        return 1.0 - self.spoiled_fraction(age_ref_h)

    def age_for_quality(self, q: float) -> float:
        q = min(max(q, 1e-9), 1 - 1e-9)
        return self.profile.life_ref_h * math.exp(self.sigma * _phi_inv(1.0 - q))

    def age_after(self, age_ref_h: float, temps_c: Sequence[float], dt_h: float = 1.0) -> float:
        return age_ref_h + float(np.sum(self._v(np.asarray(temps_c, float)))) * dt_h / float(self._v(self.profile.ref_temp_c))

    def remaining_life_h(self, age_ref_h: float, temp_c: float) -> float:
        target = self.profile.life_ref_h * math.exp(self.sigma * _phi_inv(self.traffic_quantile))
        return max(0.0, (target - age_ref_h) / self.accel(temp_c))

    # ---- §6 TransitStorageNode.predict_loss
    def predict_loss(self, qty_kg: float, quality_now: float, temps_c: Sequence[float], *, dt_h: float = 1.0,
                     temp_provenance: str = Provenance.REAL_FETCHED, distance_km: float = 0.0) -> LossPrediction:
        a0 = self.age_for_quality(quality_now) if quality_now < 1 else 0.0
        a1 = self.age_after(a0, temps_c, dt_h)
        f0, f1 = self.spoiled_fraction(a0), self.spoiled_fraction(a1)
        heat_loss = qty_kg * (f1 - f0) / max(1e-9, 1 - f0)
        handling = qty_kg * self.profile.handling_per_100km * distance_km / 100.0
        temp_last = float(temps_c[-1]) if len(temps_c) else self.profile.ref_temp_c
        mean_t = float(np.mean(temps_c)) if len(temps_c) else self.profile.ref_temp_c
        rem = self.remaining_life_h(a1, temp_last)
        sens = {}
        for q in (2.0, 3.0):
            alt = DecayModel(self.profile, "q10", q, self.sigma, self.traffic_quantile)
            sens[f"remaining_life_h_q10_{q:g}"] = round(alt.remaining_life_h(alt.age_after(a0, temps_c, dt_h), temp_last), 1)
        drivers = [
            Driver("temperature", round(mean_t, 1), "°C mean over horizon", str(temp_provenance),
                   f"At {mean_t:.0f} °C produce ages {self.accel(mean_t):.1f}× faster than at the reference "
                   f"{self.profile.ref_temp_c:g} °C (FAO 152 Table 1)."),
            Driver("elapsed_time", round(len(temps_c) * dt_h, 1), "h", Provenance.USER_ENTERED,
                   "Hours covered by this prediction."),
            Driver("quality_now", round(quality_now, 3), "fraction saleable", Provenance.REAL_DERIVED,
                   "Current quality score from the lot's history."),
            Driver("reference_life", self.profile.life_ref_h, f"h at {self.profile.ref_temp_c:g} °C",
                   Provenance.REAL_FETCHED if self.profile.status == "SOURCED" else Provenance.ASSUMPTION,
                   self.profile.source or "placeholder (MISSING)"),
            Driver("unit_variation_sigma", self.sigma, "lognormal σ", Provenance.ASSUMPTION,
                   "Spread of unit-to-unit shelf life inside a lot (ASSUMPTION A17)."),
        ]
        if distance_km:
            drivers.append(Driver("handling", round(distance_km, 1), "km", Provenance.ASSUMPTION,
                                  f"{self.profile.handling_per_100km:.1%} crushed per 100 km (ASSUMPTION A6)."))
        return LossPrediction(
            expected_loss_kg=round(heat_loss + handling, 3), remaining_life_h=round(rem, 1),
            quality_now=round(quality_now, 4), quality_end=round(1 - f1, 4), drivers=drivers,
            inputs_provenance={"temperature": str(temp_provenance),
                               "reference_life": "REAL_FETCHED" if self.profile.status == "SOURCED" else "ASSUMPTION",
                               "temperature_curve": "REAL_FETCHED (FAO 152 Table 1)",
                               "unit_variation": "ASSUMPTION", "handling": "ASSUMPTION"},
            warnings=list(self.profile.warnings), sensitivity=sens)
