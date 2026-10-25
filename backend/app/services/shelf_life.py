"""M3 Shelf-life countdown: traffic light + FEFO, powered by the explainable decay model (ADR-018).

`TransitStorageNode.predict_loss(consignment, duration)` is implemented by `predict_for_consignment`: it ages the lot
from its harvest time to "now" with the temperatures where it was (district of its current node), then projects the
next `duration` hours. Temperatures are the Open-Meteo replay (REAL_FETCHED) when "now" falls inside the replay window;
otherwise the district's monthly mean from the replay (ASSUMPTION, flagged). Never a food-safety certification.
"""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache

import pandas as pd

from app.core.clock import now
from app.core.config import ROOT, app_config, thresholds
from app.core.provenance import Provenance
from app.domain.decay import CommodityProfile, DecayModel
from app.models.orm import Consignment, Node

SAFETY_DISCLAIMER = ("Model estimate with a conservative margin, not a food-safety certification. Check the produce "
                     "before eating or donating it.")


@lru_cache
def _weather() -> pd.DataFrame:
    w = pd.read_csv(ROOT / "data" / "processed" / "weather_hourly.csv", usecols=["district", "time_utc", "temperature_2m"])
    w["time_utc"] = pd.to_datetime(w["time_utc"])
    return w.set_index(["district", "time_utc"]).sort_index()


@lru_cache
def _monthly_mean() -> dict[tuple[str, int], float]:
    w = _weather().reset_index()
    w["m"] = w["time_utc"].dt.month
    return w.groupby(["district", "m"])["temperature_2m"].mean().to_dict()


@lru_cache
def _month_mean_all() -> dict[int, float]:
    w = _weather().reset_index()
    return w.groupby(w["time_utc"].dt.month)["temperature_2m"].mean().to_dict()


@lru_cache
def _overall_mean() -> float:
    return float(_weather()["temperature_2m"].mean())


def temperatures(district: str | None, start: datetime, hours: int) -> tuple[list[float], str]:
    """Hourly temperatures and their provenance for [start, start + hours)."""
    district = district or "Nagpur"
    w = _weather()
    idx = pd.date_range(start.replace(minute=0, second=0, microsecond=0), periods=max(hours, 0), freq="h")
    try:
        s = w.loc[district]["temperature_2m"].reindex(idx)
    except KeyError:
        s = pd.Series(index=idx, dtype=float)
    prov = Provenance.REAL_FETCHED
    if s.isna().any():
        mm = _monthly_mean()
        fill = pd.Series([mm.get((district, t.month), _month_mean_all().get(t.month, _overall_mean())) for t in idx], index=idx)
        prov = Provenance.ASSUMPTION if s.isna().all() else Provenance.REAL_DERIVED
        s = s.fillna(fill)
    return s.tolist(), prov


def traffic_light(remaining_h: float) -> str:
    tl = thresholds().traffic_light
    if remaining_h < tl.red_below_h:
        return "RED"
    if remaining_h < tl.green_at_or_above_h:
        return "YELLOW"
    return "GREEN"


def predict_for_consignment(c: Consignment, node: Node | None, horizon_h: int = 24, at: datetime | None = None) -> dict:
    at = at or now()
    model = DecayModel(CommodityProfile.load(c.commodity))
    hist_h = max(0, int((at - c.harvest_time).total_seconds() // 3600))
    temps_hist, prov_hist = temperatures(node.district if node else None, c.harvest_time, hist_h)
    age = model.age_after(0.0, temps_hist) if temps_hist else 0.0
    q_model = model.quality(age)
    temps_next, prov_next = temperatures(node.district if node else None, at, horizon_h)
    pred = model.predict_loss(c.current_qty_kg, q_model, temps_next or [25.0], temp_provenance=prov_next)
    tl = thresholds().traffic_light
    light = traffic_light(pred.remaining_life_h)
    margin = app_config().rescue.safety_margin_frac
    return {
        "consignment_id": c.id, "short_code": c.short_code, "commodity": c.commodity, "qty_kg": round(c.current_qty_kg, 1),
        "hours_since_harvest": hist_h, "quality_model": round(q_model, 3), "light": light,
        "remaining_life_h": pred.remaining_life_h, "safe_window_h": round(pred.remaining_life_h * margin, 1),
        "expected_loss_next_h_kg": pred.expected_loss_kg, "horizon_h": horizon_h,
        "sensitivity": pred.sensitivity,
        "explanation": {
            "why": f"{light}: about {pred.remaining_life_h:.0f} h of saleable life left "
                   f"(red < {tl.red_below_h:g} h, yellow < {tl.green_at_or_above_h:g} h, green ≥ {tl.green_at_or_above_h:g} h).",
            "inputs": {"temperature_history": {"hours": hist_h, "mean_c": round(sum(temps_hist) / len(temps_hist), 1) if temps_hist else None,
                                               "provenance": str(prov_hist)},
                       "temperature_next": {"mean_c": round(sum(temps_next) / len(temps_next), 1) if temps_next else None,
                                            "provenance": str(prov_next)},
                       "elapsed_since_harvest_h": hist_h, "quality_score": round(q_model, 3)},
            "drivers": [d.__dict__ for d in pred.drivers],
            "parameters": {"reference_life_h": model.profile.life_ref_h, "reference_temp_c": model.profile.ref_temp_c,
                           "reference_source": model.profile.source, "unit_variation_sigma": model.sigma,
                           "temperature_curve": "FAO AGS Bulletin 152 Table 1"},
            "provenance": pred.inputs_provenance,
            "thresholds": {"red_below_h": tl.red_below_h, "green_at_or_above_h": tl.green_at_or_above_h,
                           "status": "ASSUMPTION: needs confirmation with operators"},
            "warnings": pred.warnings,
            "disclaimer": SAFETY_DISCLAIMER,
        },
    }


def fefo(predictions: list[dict]) -> list[dict]:
    """First-expiring-first-out dispatch order."""
    return sorted(predictions, key=lambda p: (p["remaining_life_h"], -p["qty_kg"], p["short_code"]))

