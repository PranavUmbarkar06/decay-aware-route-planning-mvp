"""M4 Mandi crowd meter (glut warning).

Definition shown to users, verbatim: "Today's reported arrivals vs the trailing 14-day median of reported arrivals
for this commodity at this market (Agmarknet)". It is NOT "% of capacity": no verifiable mandi capacity source was
found (DATA_GAPS: mandi capacity MISSING), so capacity is never shown.

`ConsumerNode.forecast_demand(date)` → trailing-median forecast; `compute_gap(supply, demand)` → surplus/shortfall.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

import pandas as pd

from app.core.config import ROOT, app_config
from app.core.provenance import Provenance

DEFINITION = ("Today's reported arrivals vs the trailing {n}-day median of reported arrivals for this commodity at this "
              "market (Agmarknet). Not a share of capacity: mandi capacity data is unavailable.")


@lru_cache
def arrivals() -> pd.DataFrame:
    p = ROOT / "data" / "processed" / "agmarknet_arrivals_daily.csv"
    d = pd.read_csv(p) if p.exists() else pd.DataFrame(columns=["arrival_date", "market_name_clean", "commodity", "arrival_kg"])
    d["arrival_date"] = pd.to_datetime(d["arrival_date"]).dt.date
    return d


@dataclass
class DemandForecast:
    qty_kg: float | None
    method: str
    provenance: str
    uncertainty: dict
    n_days: int


def forecast_demand(market: str, commodity: str, on: date, trailing_days: int | None = None) -> DemandForecast:
    """ConsumerNode.forecast_demand(date). Demand proxy = reported arrivals (what the market absorbed)."""
    n = trailing_days or app_config().crowd_meter.trailing_days
    d = arrivals()
    s = d[(d["market_name_clean"] == market) & (d["commodity"] == commodity) & (d["arrival_date"] < on)
          & (d["arrival_date"] >= on - timedelta(days=n))]["arrival_kg"]
    if s.empty:
        return DemandForecast(None, f"trailing {n}-day median of reported arrivals", Provenance.REAL_DERIVED,
                              {"note": "no reported arrivals in the window"}, 0)
    return DemandForecast(float(s.median()), f"trailing {n}-day median of reported arrivals (proxy for demand)",
                          Provenance.REAL_DERIVED, {"p25_kg": float(s.quantile(0.25)), "p75_kg": float(s.quantile(0.75))},
                          int(s.size))


def compute_gap(supply_kg: float, demand: DemandForecast) -> dict:
    if demand.qty_kg is None:
        return {"gap_kg": None, "status": "NO_DATA"}
    gap = supply_kg - demand.qty_kg
    return {"gap_kg": gap, "status": "SURPLUS" if gap > 0 else "SHORTFALL", "provenance": Provenance.REAL_DERIVED}


def meter(market: str, commodity: str, on: date) -> dict:
    cfg = app_config().crowd_meter
    d = arrivals()
    sub = d[(d["market_name_clean"] == market) & (d["commodity"] == commodity) & (d["arrival_date"] <= on)]
    last = sub["arrival_date"].max() if len(sub) else None
    base = {"market": market, "commodity": commodity, "date": on.isoformat(), "definition": DEFINITION.format(n=cfg.trailing_days),
            "last_reported": last.isoformat() if last else None, "provenance": Provenance.REAL_DERIVED,
            "source": "Agmarknet 2.0 Daily Price and Arrival Report (owner exports)"}
    if last is None:
        return {**base, "status": "NO_DATA", "label": "No data"}
    if (on - last).days > cfg.stale_after_days:
        return {**base, "status": "STALE", "label": f"No recent data (last reported {last:%d %b %Y})"}
    today = float(sub[sub["arrival_date"] == last]["arrival_kg"].sum())
    fc = forecast_demand(market, commodity, last)
    if fc.qty_kg is None or fc.qty_kg <= 0:
        return {**base, "status": "NO_BASELINE", "label": "Not enough history", "today_kg": today}
    ratio = today / fc.qty_kg
    status = "GLUT_WARNING" if ratio >= cfg.warn_ratio else ("BUSY" if ratio >= 1.0 else "NORMAL")
    return {**base, "status": status, "ratio": round(ratio, 2), "today_kg": today, "trailing_median_kg": fc.qty_kg,
            "trailing_days_with_data": fc.n_days, "warn_ratio": cfg.warn_ratio,
            "warn_ratio_status": "ASSUMPTION: needs validation", "uncertainty": fc.uncertainty,
            "label": f"{ratio:.0%} of its usual {cfg.trailing_days}-day median"}
