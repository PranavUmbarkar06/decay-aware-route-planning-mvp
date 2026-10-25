"""Scenario = every exogenous input of one (season, seed) run, generated once and shared by both policies.

Ticks are UTC hours from the season start (00:00 UTC). IST hour-of-day = floor(UTC hour + 5.5) mod 24.
Day index d covers ticks [24d, 24d+24).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd
import yaml

from app.core.config import ROOT
from app.simulation.network import CLASS_ORDER, Network

PROCESSED = ROOT / "data" / "processed"
SIM_CFG = ROOT / "config" / "simulation.yaml"


@lru_cache
def sim_config() -> dict:
    return yaml.safe_load(SIM_CFG.read_text(encoding="utf-8"))


def file_sha(p) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


HISTORY_DAYS = 14


def ist_hour(tick: int) -> int:
    return int((tick + 5.5) % 24)


@dataclass(frozen=True)
class Lot:
    lot_id: str
    commodity: str
    qty_kg: float
    origin: str
    planned_dest: str
    dispatch_tick: int
    market_day: int
    harvest_lead_h: int


@dataclass
class Scenario:
    season: str
    seed: int
    start: date
    days: int
    ticks: int
    pre_ticks: int                                   # weather hours available before tick 0 (harvest ageing)
    temps: np.ndarray                                # [district, pre_ticks + ticks]
    lots: list[Lot]
    demand: dict[tuple[str, str, int], float]        # (market node_id, commodity, day) → kg   REAL_DERIVED
    class_hour_mult: np.ndarray                      # [class, tick]                          ASSUMPTION
    edge_factor: np.ndarray                          # [edge]                                 ASSUMPTION
    disruptions: dict[int, list[tuple[int, int]]]    # edge → [(start_tick, end_tick)]         ASSUMPTION
    params: dict
    notes: list[str] = field(default_factory=list)

    def temp(self, district_idx: int, tick: int) -> float:
        return float(self.temps[district_idx, self.pre_ticks + min(tick, self.ticks - 1)])

    def disrupted(self, edge: int, tick: int) -> bool:
        return any(s <= tick < e for s, e in self.disruptions.get(edge, ()))

    def weights(self, net: Network, tick: int) -> np.ndarray:
        w = net.ff_s * self.class_hour_mult[net.cls, min(tick, self.ticks - 1)] * self.edge_factor
        for e, spans in self.disruptions.items():
            if any(s <= tick < en for s, en in spans):
                w[e] = 1e9
        return w


def _weather(start: date, days: int, pre_h: int, districts: list[str]) -> np.ndarray:
    w = pd.read_csv(PROCESSED / "weather_hourly.csv", usecols=["district", "time_utc", "temperature_2m"])
    w["time_utc"] = pd.to_datetime(w["time_utc"])
    t0 = datetime(start.year, start.month, start.day) - timedelta(hours=pre_h)
    idx = pd.date_range(t0, periods=pre_h + days * 24 + 96, freq="h")
    out = np.empty((len(districts), len(idx)))
    for i, d in enumerate(districts):
        s = w[w["district"] == d].set_index("time_utc")["temperature_2m"].reindex(idx)
        if s.isna().any():
            missing = int(s.isna().sum())
            if missing > len(s) * 0.05:
                raise RuntimeError(f"weather replay missing {missing} hours for {d} in {idx[0]}..{idx[-1]}")
            s = s.interpolate(limit_direction="both")   # only tiny gaps; recorded in notes by caller
        out[i] = s.to_numpy()
    return out


def _demand(net: Network, start: date, days: int, commodities: list[str]) -> tuple[dict, list[str]]:
    d = pd.read_csv(PROCESSED / "agmarknet_arrivals_daily.csv")
    names = {b.name: b.node_id for b in net.by_type("ReceivingMarket")}
    notes = []
    excluded = sorted(set(d[d["in_pilot_commodity"]]["market_name_clean"]) - set(names))
    if excluded:
        notes.append(f"markets with arrivals but not routable (under review) → their demand is excluded: {excluded}")
    out: dict[tuple[str, str, int], float] = {}
    # Days before the window (k < 0) are history: visible to forecasts (as on a crowd meter), never counted as
    # demand to satisfy and never used to generate supply.
    for k in range(-HISTORY_DAYS, days):
        day = (start + timedelta(days=k)).isoformat()
        sub = d[(d["arrival_date"] == day) & d["commodity"].isin(commodities) & d["market_name_clean"].isin(names)]
        for r in sub.itertuples(index=False):
            if r.arrival_kg and r.arrival_kg > 0:
                out[(names[r.market_name_clean], r.commodity, k)] = float(r.arrival_kg)
    return out, notes


def build_scenario(net: Network, season: str, start: str, days: int, seed: int, commodities: list[str],
                   overrides: dict | None = None) -> Scenario:
    cfg = sim_config()
    ov = overrides or {}
    rng = np.random.default_rng(seed)
    st = date.fromisoformat(start)
    pre_h = 48
    flush_h = 72
    ticks = days * 24 + flush_h
    temps = _weather(st, days, pre_h, net.districts)
    demand, notes = _demand(net, st, days, commodities)

    sp = cfg["supply"]
    ratio = ov.get("supply_ratio", sp["supply_ratio"]["value"])
    ls = sp["lot_size_kg"]
    origins = sorted(b.node_id for b in net.by_type(cfg["network"]["origins"]))
    lots: list[Lot] = []
    for k in range(1, days):                                    # day 0 is warm-up (lots for day 1 leave on day 0)
        for c in commodities:
            mk = sorted((m, q) for (m, cc, dd), q in demand.items() if cc == c and dd == k)
            total = ratio * sum(q for _, q in mk)
            if total <= 0:
                continue
            shares = np.array([q for _, q in mk]) / sum(q for _, q in mk)
            if ov.get("plan_from_forecast"):
                # Exploratory variant (post-hoc): plans follow what a dispatcher could know (mean of the previous
                # 3 reported days), not the realised arrivals of the day. Supply volume is unchanged.
                fc = []
                for m, _ in mk:
                    past = [q for (mm, cc, dd), q in sorted(demand.items(), key=lambda kv: kv[0][2])
                            if mm == m and cc == c and dd < k][-3:]
                    fc.append(float(np.mean(past)) if past else 0.0)
                if sum(fc) > 0:
                    shares = np.array(fc) / sum(fc)
            remaining, n = total, 0
            while remaining > 1e-6:
                size = float(np.clip(rng.lognormal(np.log(ls["median"]), ls["sigma"]), ls["min"], ls["max"]))
                if remaining - size < ls["min"]:
                    size = remaining
                remaining -= size
                dest = mk[int(rng.choice(len(mk), p=shares))][0]
                origin = origins[int(rng.integers(len(origins)))]
                hour = int(rng.integers(sp["dispatch_hour_ist"]["min"], sp["dispatch_hour_ist"]["max"] + 1))
                tick = 24 * (k - 1) + int(np.floor(hour - 5.5)) % 24
                lead = int(rng.integers(sp["harvest_to_dispatch_h"]["min"], sp["harvest_to_dispatch_h"]["max"] + 1))
                lots.append(Lot(f"{season[:1].upper()}{seed}-{c[:2]}-{k:02d}-{n:03d}", c, round(size, 3), origin, dest,
                                tick, k, lead))
                n += 1

    tr = cfg["traffic"]
    n_cls = len(CLASS_ORDER)
    peak = np.zeros(ticks)
    for t in range(ticks):
        h = ist_hour(t)
        if any(a <= h < b for a, b in tr["peak_hours_ist"]):
            peak[t] = tr["peak_extra"]["value"]
    noise = rng.lognormal(0.0, tr["class_hour_noise_sigma"]["value"], size=(n_cls, ticks))
    class_hour_mult = (1.0 + peak)[None, :] * noise
    edge_factor = rng.lognormal(0.0, tr["edge_factor_sigma"]["value"], size=len(net.ff_s))
    disruptions: dict[int, list[tuple[int, int]]] = {}
    rate = tr["disruption_rate_per_edge_day"]["value"]
    dmin, dmax = tr["disruption_duration_h"]["min"], tr["disruption_duration_h"]["max"]
    for day in range(days + flush_h // 24):
        k = rng.poisson(rate * len(net.ff_s))
        for e in rng.choice(len(net.ff_s), size=k, replace=False):
            s0 = 24 * day + int(rng.integers(24))
            disruptions.setdefault(int(e), []).append((s0, s0 + int(rng.integers(dmin, dmax + 1))))
    params = {"supply_ratio": ratio, "simulation_yaml_sha256": file_sha(SIM_CFG),
              "edges_csv_sha256": file_sha(PROCESSED / "edges.csv"), "nodes_csv_sha256": file_sha(PROCESSED / "nodes.csv"),
              "arrivals_sha256": file_sha(PROCESSED / "agmarknet_arrivals_daily.csv"), **ov}
    notes.append(f"{len(lots)} lots; demand market-days: {len({(m, d) for (m, _, d) in demand})}; "
                 f"disrupted edges: {len(disruptions)}")
    return Scenario(season, seed, st, days, ticks, pre_h, temps, lots, demand, class_hour_mult, edge_factor, disruptions,
                    params, notes)
