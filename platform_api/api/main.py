"""FastAPI service for the India crop-aware routing platform (plan v2 §4).

    .venv/Scripts/python.exe -m uvicorn platform_api.api.main:app --port 8010
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
import shapely
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import alerts as alertbook
from ..engine import crops as crops_mod
from ..engine.decision import Buffers, decision_window
from ..engine.deterioration import ShipmentSpec, StartState
from ..engine.graph import RoadGraph, load_graph
from ..engine.routing import (Candidate, Conditions, Disruption, decide, effect_of, eval_summary, evaluate,
                              plan_route, route_coords)
from ..engine.decision import arrival_times
from ..store import conn, row_dict

ROOT = Path(__file__).resolve().parents[2]
INDIA = ROOT / "data" / "processed" / "india"

app = FastAPI(title="Crop-aware routing platform", version="2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------- schemas

class Point(BaseModel):
    lon: float | None = None
    lat: float | None = None
    market_id: str | None = None


class ShipmentIn(BaseModel):
    shipment_id: str = "SHP-DEMO"
    crop: Literal["grapes", "tomato", "onion"]
    kg: float = 10000
    condition: str | None = None
    packaging: str | None = None
    loading: str = "proper"
    vehicle: str | None = None
    refrigeration_ok: bool = True
    reefer_fail_at_h: float | None = None
    handling_events: int = 2
    pre_dispatch_h: float = 0.0
    market_wait_h: float = 0.0
    dispatch_hour: float = 6.0
    price_rs_kg: float | None = None
    q10: float | None = None
    breakdown_h: float = 0.0

    def spec(self) -> ShipmentSpec:
        d = self.model_dump()
        d.pop("shipment_id")
        return ShipmentSpec(**d)


class ConditionsIn(BaseModel):
    ambient_c: float = 32
    rh: float = 60
    traffic: float = 2
    extra_delay_h: float = 0
    road_quality: float = 10
    vibration: float = 5

    def obj(self) -> Conditions:
        return Conditions(**self.model_dump())


class DisruptionIn(BaseModel):
    id: str
    type: Literal["closure", "partial_blockage", "congestion", "reduced_speed", "construction", "accident",
                  "poor_road", "vehicle_restriction"]
    edges: list[int]
    severity: float = 5
    start_h: float = 0
    end_h: float | None = None
    heavy_only: bool = True
    alt_access: bool = False
    confirmed: bool = True

    def obj(self) -> Disruption:
        return Disruption(**self.model_dump())


class OptimiseIn(BaseModel):
    shipment: ShipmentIn
    origin: Point
    destination: Point
    conditions: ConditionsIn = Field(default_factory=ConditionsIn)
    disruptions: list[DisruptionIn] = []
    original_arcs: list[int] | None = None


class EvaluateIn(BaseModel):
    shipment: ShipmentIn
    conditions: ConditionsIn = Field(default_factory=ConditionsIn)
    disruptions: list[DisruptionIn] = []
    candidates: list[dict]          # {id, label, arcs}
    original_id: str = "original"


class TruckIn(BaseModel):
    shipment: ShipmentIn
    route_arcs: list[int]
    pos: int = 0
    progress: float = 0.0
    destination_node: int


class AlertsEvalIn(BaseModel):
    trucks: list[TruckIn]
    conditions: ConditionsIn = Field(default_factory=ConditionsIn)
    disruptions: list[DisruptionIn] = []
    now_h: float
    buffers: dict | None = None


class AlertActionIn(BaseModel):
    action: Literal["review", "approve", "modify", "reject", "snooze", "send", "acknowledge", "execute"]
    now_h: float
    actor: str = "dispatcher"
    option: int | None = None
    until_h: float | None = None
    note: str | None = None
    dest_name: str = "destination"


# ---------------------------------------------------------------- data

@lru_cache(maxsize=1)
def G() -> RoadGraph:
    return load_graph()


@lru_cache(maxsize=1)
def markets() -> pd.DataFrame:
    p = INDIA / "markets.parquet"
    if not p.exists():
        return pd.DataFrame(columns=["market_id", "market", "state", "district", "lon", "lat"])
    m = pd.read_parquet(p)
    return m[m.lon.notna()].reset_index(drop=True)


@lru_cache(maxsize=1)
def arrivals() -> pd.DataFrame:
    return pd.read_parquet(INDIA / "arrivals_daily.parquet")


def resolve(p: Point) -> dict:
    g = G()
    if p.market_id:
        m = markets()
        row = m[m.market_id == p.market_id]
        if row.empty:
            raise HTTPException(404, f"market {p.market_id} not found")
        r = row.iloc[0]
        lon, lat, label = float(r.lon), float(r.lat), f"{r.market}, {r.district}"
        meta = {"market_id": p.market_id, "geocode_method": r.geocode_method, "geocode_confidence": float(r.geocode_confidence)}
    elif p.lon is not None and p.lat is not None:
        lon, lat, label, meta = p.lon, p.lat, f"{p.lat:.4f}, {p.lon:.4f}", {}
    else:
        raise HTTPException(422, "origin/destination needs market_id or lon/lat")
    node, km = g.nearest_node(lon, lat)
    return {"node": node, "lon": float(g.lon[node]), "lat": float(g.lat[node]), "input_lon": lon, "input_lat": lat,
            "snap_km": round(km, 2), "label": label, "access_leg": km > 2, **meta}


def simplify_coords(coords: list[list[float]], tol: float = 0.0004) -> list[list[float]]:
    if len(coords) < 3:
        return coords
    ls = shapely.simplify(shapely.linestrings(coords), tol)
    return [[round(x, 5), round(y, 5)] for x, y in shapely.get_coordinates(ls)]


def marks_geo(g: RoadGraph, marks: list[dict]) -> list[dict]:
    out = []
    for m in marks:
        out.append({"kind": m["kind"], "edge": m["edge"], "coords": g.edge_coords(m["edge"]), **({"hours": m["hours"]} if "hours" in m else {})})
    return out


def cand_json(g: RoadGraph, c: Candidate, spec: ShipmentSpec, dispatch_hour: float) -> dict:
    ev = c.eval
    return {"id": c.id, "label": c.label, "feasible": ev.feasible, "reason": ev.reason, "arcs": [int(a) for a in ev.arcs],
            "edges": [int(g.a_edge[a]) for a in ev.arcs], "edge_km": [round(float(g.len_km[g.a_edge[a]]), 3) for a in ev.arcs],
            "coords": simplify_coords(route_coords(g, ev.arcs)) if ev.feasible else [],
            "metrics": eval_summary(ev, spec, dispatch_hour), "marks": marks_geo(g, ev.segments) if ev.feasible else []}


def plan_json(g: RoadGraph, plan, spec: ShipmentSpec, dispatch_hour: float) -> dict:
    cands = [cand_json(g, c, spec, dispatch_hour) for c in plan.candidates]
    out = {"decision": plan.decision, "explanation": plan.explanation, "margin_rs": round(plan.margin_rs),
           "original_id": plan.original.id if plan.original else None,
           "recommended_id": plan.recommended.id if plan.recommended else None, "candidates": cands}
    if plan.original and plan.recommended and plan.original.eval.feasible and plan.recommended.eval.feasible:
        o, r = plan.original.eval, plan.recommended.eval
        saved = o.outcome.wastage_kg - r.outcome.wastage_kg
        extra_cost = r.transport_cost_rs - o.transport_cost_rs
        out["economics"] = {
            "extra_km": round(r.distance_km - o.distance_km, 1),
            "extra_transport_rs": round(extra_cost),
            "extra_fuel_l": round((r.distance_km - o.distance_km) / 3.0, 1),   # ASSUMPTION: ~3 km/L laden
            "produce_value_protected_rs": round(r.outcome.revenue_rs - o.outcome.revenue_rs),
            "net_benefit_rs": round(r.net_value_rs - o.net_value_rs),
            "kg_saved": round(saved, 1),
            "cost_per_kg_saved_rs": round(extra_cost / saved, 2) if saved > 0.5 else None,
        }
    return out


# ---------------------------------------------------------------- endpoints

@app.get("/api/health")
def health() -> dict:
    stats = INDIA / "graph_stats.json"
    return {"ok": True, "graph": __import__("json").loads(stats.read_text()) if stats.exists() else None}


@app.get("/api/crops")
def crops() -> dict:
    return crops_mod.raw_config()


@app.get("/api/meta")
def meta() -> dict:
    import json
    out: dict[str, Any] = {}
    for name in ("graph_stats.json", "markets_report.json", "render/tiles_report.json"):
        p = INDIA / name
        out[name.split("/")[-1].replace(".json", "")] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    out["labels"] = {
        "MAPPED ROAD (OSM)": "Road geometry and class from OpenStreetMap (ODbL), Geofabrik extract",
        "HISTORICAL (Agmarknet)": "Daily arrivals and modal prices, Nov 2025 – Oct 2026; arrivals are not demand",
        "SIMULATED": "Traffic, disruptions and shipment outcomes produced by this model",
        "ASSUMPTION": "Illustrative coefficient awaiting calibration",
    }
    return out


@app.get("/api/states")
def states() -> list[dict]:
    m = markets()
    g = m.groupby("state").agg(markets=("market_id", "size")).reset_index()
    return g.sort_values("state").to_dict("records")


@app.get("/api/districts")
def districts(state: str) -> list[dict]:
    m = markets()
    g = m[m.state == state].groupby("district").agg(markets=("market_id", "size")).reset_index()
    return g.sort_values("district").to_dict("records")


@app.get("/api/places")
def places(q: str = "", state: str | None = None, district: str | None = None, crop: str | None = None, limit: int = 30) -> list[dict]:
    m = markets()
    if state:
        m = m[m.state == state]
    if district:
        m = m[m.district == district]
    if crop:
        m = m[m[f"{crop}_t"].fillna(0) > 0]
    if q:
        ql = q.lower()
        m = m[m.market.str.lower().str.contains(ql, regex=False) | m.district.str.lower().str.contains(ql, regex=False)]
    vol = sum(m[f"{c}_t"].fillna(0) for c in ("tomato", "onion", "grapes"))
    m = m.assign(volume_t=vol).sort_values("volume_t", ascending=False).head(limit)
    cols = ["market_id", "market", "district", "state", "lon", "lat", "geocode_method", "geocode_confidence", "volume_t",
            "tomato_t", "onion_t", "grapes_t", "tomato_price_rs_q", "onion_price_rs_q", "grapes_price_rs_q"]
    return m[cols].replace({np.nan: None}).to_dict("records")


# Demo corridors from the brief, pinned to named Agmarknet markets (state, exact market name).
# Grapes: Nashik grape is mostly sold outside APMC yards, so the origin is the Pimpalgaon Baswant hub (Niphad).
PRESET_MARKETS = {
    "grapes": [("Maharashtra", "APMC Pimpalgaon Baswant"), ("Maharashtra", "Mumbai- Fruit Market"),
               [(("Maharashtra", "APMC Pimpalgaon Baswant"), ("NCT of Delhi", "APMC Azadpur"))]],
    "tomato": [("Andhra Pradesh", "Madanapalli APMC"), ("Telangana", "Bowenpally APMC"),
               [(("Karnataka", "Kolar APMC"), ("NCT of Delhi", "APMC Azadpur"))]],
    "onion": [("Maharashtra", "APMC Lasalgaon"), ("Telangana", "Gudimalkapur APMC"),
              [(("Maharashtra", "APMC Lasalgaon"), ("NCT of Delhi", "APMC Azadpur"))]],
}


def _market(state: str, name: str) -> dict:
    m = markets()
    hit = m[(m.state == state) & (m.market.str.strip() == name)]
    if hit.empty:
        raise HTTPException(500, f"preset market not found: {name}, {state}")
    r = hit.iloc[0]
    return {"market_id": r.market_id, "market": r.market.strip(), "district": r.district, "state": r.state,
            "lon": float(r.lon), "lat": float(r.lat), "geocode_method": r.geocode_method,
            "tomato_price_rs_q": None if pd.isna(r.tomato_price_rs_q) else float(r.tomato_price_rs_q),
            "onion_price_rs_q": None if pd.isna(r.onion_price_rs_q) else float(r.onion_price_rs_q),
            "grapes_price_rs_q": None if pd.isna(r.grapes_price_rs_q) else float(r.grapes_price_rs_q)}


@app.get("/api/presets")
def presets() -> dict:
    return {crop: {"origin": _market(*o), "destination": _market(*d),
                   "research": [{"origin": _market(*ro), "destination": _market(*rd)} for ro, rd in research]}
            for crop, (o, d, research) in PRESET_MARKETS.items()}


@app.post("/api/optimise")
def optimise(req: OptimiseIn) -> dict:
    g = G()
    o, d = resolve(req.origin), resolve(req.destination)
    spec = req.shipment.spec()
    plan = plan_route(g, o["node"], d["node"], spec, req.conditions.obj(), [x.obj() for x in req.disruptions],
                      original_arcs=req.original_arcs)
    out = plan_json(g, plan, spec, req.shipment.dispatch_hour)
    out["origin"], out["destination"] = o, d
    return out


@app.post("/api/evaluate")
def evaluate_routes(req: EvaluateIn) -> dict:
    """Re-score existing candidate routes under new conditions without re-routing (fast path for sliders)."""
    g = G()
    spec = req.shipment.spec()
    cond, dis = req.conditions.obj(), [x.obj() for x in req.disruptions]
    cands = [Candidate(c["id"], c.get("label", c["id"]), evaluate(g, [int(a) for a in c["arcs"]], spec, cond, dis))
             for c in req.candidates]
    original = next((c for c in cands if c.id == req.original_id), None)
    plan = decide(original, cands, spec)
    out = plan_json(g, plan, spec, req.shipment.dispatch_hour)
    for c in out["candidates"]:
        c.pop("coords")   # client already has geometry
    return out


@app.get("/api/edge-at")
def edge_at(lon: float, lat: float, max_km: float = 3.0) -> dict:
    g = G()
    e, km = g.nearest_edge(lon, lat)
    if km > max_km:
        raise HTTPException(404, f"no mapped road within {max_km} km")
    info = g.edge_info(e)
    info["snap_km"] = round(km, 3)
    way = g.way_edges(int(g.way_id[e]))
    info["way_edges"] = [int(x) for x in way]
    info["way_coords"] = [g.edge_coords(int(x)) for x in way]
    info["way_len_km"] = round(float(g.len_km[way].sum()), 2)
    return info


@app.get("/api/edges")
def edges_geo(ids: str) -> list[dict]:
    g = G()
    return [{"edge": int(i), "coords": g.edge_coords(int(i))} for i in ids.split(",") if i.strip()]


@lru_cache(maxsize=1)
def edge_mids() -> tuple[np.ndarray, np.ndarray]:
    g = G()
    npts = np.diff(g.g_off) // 2
    i = g.g_off[:-1] + (npts // 2) * 2
    return g.g_flat[i], g.g_flat[i + 1]


@app.get("/api/roads/viewport")
def roads_viewport(west: float, south: float, east: float, north: float, near: str | None = None,
                   buffer_km: float = 5, limit: int = 5000) -> dict:
    """Detail roads near the selected route (z≥11 only, called debounced by the map)."""
    g = G()
    mx, my = edge_mids()
    sel =np.nonzero((mx >= west) & (mx <= east) & (my >= south) & (my <= north))[0]
    if near:
        route = [int(a) for a in near.split(",") if a]
        pts = np.array([c for a in route for c in g.edge_coords(int(g.a_edge[a]))])
        if len(pts):
            from scipy.spatial import cKDTree
            t = cKDTree(pts)
            d, _ = t.query(np.column_stack([mx[sel], my[sel]]))
            sel = sel[d * 111 <= buffer_km]
    sel = sel[:limit]
    feats = [{"type": "Feature", "properties": {"edge_id": int(e), "rank": int(g.rank[e]), "rough": float(g.rough[e])},
              "geometry": {"type": "LineString", "coordinates": g.edge_coords(int(e))}} for e in sel]
    return {"type": "FeatureCollection", "features": feats, "truncated": len(sel) >= limit}


def _start_state(g: RoadGraph, t: TruckIn, cond: Conditions, dis: list[Disruption]) -> StartState:
    spec = t.shipment.spec()
    if t.pos <= 0 and t.progress <= 0:
        ev = evaluate(g, [], spec, cond, dis, include_wait=False) if spec.pre_dispatch_h else None
        if ev and ev.outcome:
            return StartState(t_h=ev.outcome.hours, neg_ln_q=-math.log(ev.outcome.q_arrival))
        return StartState()
    # The truck has already driven this part: a closure there can no longer stop it.
    passable = [d for d in dis if not effect_of(d).blocked]
    ev = evaluate(g, t.route_arcs[:t.pos], spec, cond, passable, include_wait=False)
    o = ev.outcome
    return StartState(t_h=o.hours, neg_ln_q=-math.log(max(1e-9, o.q_arrival)), km=ev.distance_km, dose=o.vib_dose)


@app.post("/api/route/timeline")
def timeline(t: TruckIn, now_h: float = 0.0, ambient_c: float = 32, traffic: float = 2) -> dict:
    """Full-resolution geometry with per-arc expected times, for animating the truck."""
    g = G()
    cond = Conditions(ambient_c=ambient_c, traffic=traffic)
    times = arrival_times(g, t.route_arcs, cond, [], now_h)
    coords, idx = [], []
    for a in t.route_arcs:
        pts = g.edge_coords(int(g.a_edge[a]), bool(g.a_fwd[a]))
        idx.append(max(0, len(coords) - 1) if coords else 0)
        coords.extend(pts if not coords else pts[1:])
    return {"coords": [[round(x, 5), round(y, 5)] for x, y in coords], "arc_coord_idx": idx,
            "arc_t": [round(float(x), 4) for x in times], "edges": [int(g.a_edge[a]) for a in t.route_arcs]}


@app.post("/api/alerts/evaluate")
def alerts_evaluate(req: AlertsEvalIn) -> dict:
    g = G()
    cond, dis = req.conditions.obj(), [x.obj() for x in req.disruptions]
    buf = Buffers(**(req.buffers or {}))
    windows = {}
    with conn() as c:
        for t in req.trucks:
            spec = t.shipment.spec()
            st = _start_state(g, t, cond, dis)
            st.t_h = req.now_h
            w = decision_window(g, t.route_arcs, t.pos, st, t.destination_node, spec, cond, dis,
                                now_h=req.now_h, buffers=buf, progress=t.progress)
            opt_arcs = [[int(a) for a in o.arcs] for o in w.options]
            row = alertbook.upsert(c, t.shipment.shipment_id, w, req.now_h, opt_arcs)
            from ..engine.decision import window_dict
            windows[t.shipment.shipment_id] = {"window": window_dict(w), "alert_id": row["id"] if row else None}
        q = alertbook.queue(c, req.now_h, buf)
    return {"windows": windows, "queue": q}


@app.get("/api/alerts")
def alerts_list(now_h: float, review_min: float = 4.0) -> dict:
    with conn() as c:
        return alertbook.queue(c, now_h, Buffers(review=review_min))


@app.get("/api/alerts/{aid}/events")
def alert_events(aid: str) -> list[dict]:
    with conn() as c:
        return [row_dict(r) for r in c.execute("SELECT * FROM alert_events WHERE alert_id=? ORDER BY id", (aid,))]


@app.patch("/api/alerts/{aid}")
def alert_act(aid: str, req: AlertActionIn) -> dict:
    with conn() as c:
        try:
            row = alertbook.act(c, aid, req.action, req.now_h, req.actor, option=req.option, until_h=req.until_h, note=req.note)
        except KeyError:
            raise HTTPException(404, "alert not found")
        except ValueError as ex:
            c.commit()
            raise HTTPException(409, str(ex))
        out: dict[str, Any] = {"alert": row}
        if req.action == "send":
            out["messages"] = alertbook.driver_messages(row["payload"], row.get("chosen_option") or 0, req.dest_name)
        if req.action in ("acknowledge", "execute"):
            opts = row["payload"].get("option_arcs") or []
            i = row.get("chosen_option") or 0
            out["new_route_arcs"] = opts[i] if i < len(opts) else None
        return out


@app.delete("/api/alerts")
def alerts_reset() -> dict:
    with conn() as c:
        c.execute("DELETE FROM alerts")
        c.execute("DELETE FROM alert_events")
    return {"ok": True}


@app.get("/api/decision-log")
def decision_log(limit: int = 200) -> list[dict]:
    with conn() as c:
        return [row_dict(r) for r in c.execute(
            "SELECT e.*, a.shipment_id FROM alert_events e LEFT JOIN alerts a ON a.id=e.alert_id ORDER BY e.id DESC LIMIT ?", (limit,))]


# ---------------------------------------------------------------- markets / arrivals (HISTORICAL)

@app.get("/api/markets/{market_id}/arrivals")
def market_arrivals(market_id: str, crop: str) -> dict:
    a = arrivals()
    s = a[(a.market_id == market_id) & (a.crop == crop)].sort_values("date")
    if s.empty:
        return {"market_id": market_id, "crop": crop, "series": [], "label": "HISTORICAL (Agmarknet)"}
    s = s.set_index("date")
    med30 = s.arrival_t.rolling("30D", min_periods=5).median()
    last = s.iloc[-1]
    load_idx = float(last.arrival_t / med30.iloc[-1]) if med30.iloc[-1] else None
    return {
        "market_id": market_id, "crop": crop, "label": "HISTORICAL (Agmarknet)",
        "series": [{"date": d.strftime("%Y-%m-%d"), "arrival_t": round(float(r.arrival_t), 2), "modal_rs_q": float(r.modal_rs_q)}
                   for d, r in s.iterrows()],
        "latest": {"date": s.index[-1].strftime("%Y-%m-%d"), "arrival_t": float(last.arrival_t), "modal_rs_q": float(last.modal_rs_q)},
        "load_index": round(load_idx, 2) if load_idx else None,
        "load_index_note": "latest arrivals ÷ trailing 30-day median arrivals at this market. Indicates supply pressure, NOT demand.",
    }


@app.get("/api/markets/summary")
def markets_summary(crop: str, state: str | None = None) -> dict:
    m = markets()
    if state:
        m = m[m.state == state]
    col = f"{crop}_t"
    m = m[m[col].fillna(0) > 0]
    by_state = m.groupby("state")[col].sum().sort_values(ascending=False)
    top = m.sort_values(col, ascending=False).head(15)
    return {"label": "HISTORICAL (Agmarknet)", "crop": crop,
            "by_state": [{"state": s, "arrival_t": round(float(v))} for s, v in by_state.items()],
            "top_markets": top[["market_id", "market", "district", "state", col, f"{crop}_price_rs_q", "lon", "lat", "geocode_method"]]
                .rename(columns={col: "arrival_t", f"{crop}_price_rs_q": "median_modal_rs_q"}).replace({np.nan: None}).to_dict("records"),
            "markets": m[["market_id", "market", "lon", "lat", col, "geocode_method"]].rename(columns={col: "arrival_t"})
                .replace({np.nan: None}).to_dict("records")}


# ---------------------------------------------------------------- crop sensitivity (same engine)

@app.get("/api/sensitivity")
def sensitivity(hours: float = 24, km: float = 600) -> dict:
    """Wastage after a fixed trip for each crop while one variable sweeps; everything else at defaults."""
    from ..engine.deterioration import Segment, simulate
    out: dict[str, Any] = {"hours": hours, "km": km, "series": {}}
    _, crops_ = crops_mod.load()
    sweeps = {"temperature": [float(x) for x in range(10, 51, 5)], "humidity": [float(x) for x in range(30, 101, 10)],
              "roughness": [float(x) for x in range(0, 11)]}
    for var, xs in sweeps.items():
        out["series"][var] = []
        for x in xs:
            row: dict[str, Any] = {"x": x}
            for cid in crops_:
                seg_n = max(1, int(hours))
                segs = [Segment(hours=hours / seg_n, km=km / seg_n,
                                ambient_c=x if var == "temperature" else 32.0, rh=x if var == "humidity" else 60.0,
                                roughness=x if var == "roughness" else 3.0) for _ in range(seg_n)]
                o = simulate(ShipmentSpec(crop=cid, kg=1000, vehicle="open_truck"), segs)
                row[cid] = round(o.wastage_pct + 100 * o.downgraded_kg / o.kg * 0.5, 2)
            out["series"][var].append(row)
    out["note"] = "Open truck, default packaging and condition. Value lost % = wastage + half of downgraded share."
    return out


@app.on_event("startup")
def warm() -> None:
    import threading

    def go() -> None:
        g = G()
        g.nearest_edge(78.0, 21.0)   # build the click index
        markets()
        edge_mids()
    threading.Thread(target=go, daemon=True).start()


# ---------------------------------------------------------------- outcomes

@app.post("/api/outcomes")
def outcome_add(payload: dict) -> dict:
    import json
    with conn() as c:
        c.execute("INSERT INTO outcomes(shipment_id, crop, recorded_utc, payload) VALUES (?,?,datetime('now'),?)",
                  (payload.get("shipment_id"), payload.get("crop"), json.dumps(payload)))
    return {"ok": True}


@app.get("/api/outcomes")
def outcome_list() -> list[dict]:
    with conn() as c:
        return [row_dict(r) for r in c.execute("SELECT * FROM outcomes ORDER BY id DESC")]


# ---------------------------------------------------------------- batch simulation (SIMULATED)

class BatchIn(BaseModel):
    crops: list[str] = ["grapes", "tomato", "onion"]
    states: list[str] | None = None
    shipments_per_corridor: int = 12
    corridors_per_crop: int = 8
    days: int = 30
    seed: int = 7


@app.post("/api/batch")
def batch(req: BatchIn) -> dict:
    from ..engine.batch import run_batch
    return run_batch(G(), markets(), req.model_dump())


# ---------------------------------------------------------------- tiles (render-only artefact)

@app.get("/tiles/roads.pmtiles")
def tiles() -> FileResponse:
    p = INDIA / "render" / "roads.pmtiles"
    if not p.exists():
        raise HTTPException(404, "tiles not built: python -m pipelines.v2.render_tiles")
    return FileResponse(p, media_type="application/octet-stream")


@app.get("/geo/{name}")
def geo(name: Literal["states", "districts"]) -> FileResponse:
    return FileResponse(INDIA / f"{name}.geojson", media_type="application/geo+json")
