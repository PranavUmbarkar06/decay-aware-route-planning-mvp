"""India-wide batch simulation (plan v2 §8.5). SIMULATED: every aggregate is summed from individual shipments.

Corridors come from HISTORICAL Agmarknet arrivals (high-volume production markets → large terminal markets).
Shipment sizes, weather, traffic and disruptions are SYNTHETIC, drawn from a seeded generator, so identical
inputs give identical outputs.

Per corridor the engine generates a candidate route pool once (planned route + crop-aware alternatives), then for
each shipment:
  baseline  = the planned route, driven as planned whatever happens (no rerouting)
  optimised = the same decide() rule as the live system, applied to the pool under that shipment's conditions
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .crops import load
from .deterioration import ShipmentSpec
from .graph import RoadGraph, hav_km
from .routing import (Candidate, Conditions, Disruption, arc_path, arc_weights, corridor_arcs, decide, edge_state, effect_of,
                      evaluate, plan_route, route_coords, shortest)

DISRUPTION_TYPES = ["congestion", "partial_blockage", "poor_road", "construction", "accident", "closure", "reduced_speed"]
DISRUPTION_P = [0.30, 0.15, 0.15, 0.12, 0.10, 0.08, 0.10]   # ASSUMPTION
GOOD_GEOCODE = ("osm_place_exact", "osm_place_fuzzy", "manual_override")
# Terminal (consumption) markets: the main yards of large cities. A market qualifies when its district is a metro
# district AND its name contains the city (so rural yards in the same district are excluded).
METRO = {"Delhi": "", "Mumbai": "mumbai", "Bengaluru": "bengaluru", "Hyderabad": "", "Kolkata": "", "Ahmedabad": "ahmedabad",
         "Pune": "pune", "Jaipur": "jaipur", "Lucknow": "lucknow", "Indore": "indore", "Nagpur": "nagpur", "Surat": "surat",
         "Bhopal": "bhopal", "Kanpur": "kanpur"}


def corridors(m: pd.DataFrame, crop: str, n: int, states: list[str] | None) -> list[tuple[pd.Series, pd.Series]]:
    col = f"{crop}_t"
    mk = m[(m[col].fillna(0) > 0) & m.geocode_method.isin(GOOD_GEOCODE)].copy()
    origins = mk if not states else mk[mk.state.isin(states)]
    origins = origins.sort_values(col, ascending=False)
    is_metro = mk.apply(lambda r: r.district in METRO and METRO[r.district] in r.market.lower(), axis=1)
    terminals = mk[is_metro].sort_values(col, ascending=False)
    origins = origins[~origins.market_id.isin(terminals.market_id)]
    out, used = [], set()
    for _, o in origins.iterrows():
        if len(out) >= n:
            break
        if o.market_id in used:
            continue
        d_km = hav_km(o.lon, o.lat, terminals.lon.values, terminals.lat.values)
        ok = terminals[(d_km > 120) & (d_km < 1500)]
        if ok.empty:
            continue
        # prefer the biggest terminal, tie-broken by distance (deterministic)
        dist = hav_km(o.lon, o.lat, ok.lon.values, ok.lat.values)
        score = ok[col].values / (1 + dist / 400)
        dst = ok.iloc[int(np.argmax(score))]
        used.add(o.market_id)
        out.append((o, dst))
    return out


def reactive_detour(g: RoadGraph, arcs: list[int], d_node: int, spec: ShipmentSpec, cond: Conditions,
                    dis: list[Disruption]) -> list[int] | None:
    """Status-quo behaviour at a closure: drive the planned route up to the blocked road, then take the fastest
    way round from there (decided on the spot, no crop awareness)."""
    blocked = {e for d in dis if effect_of(d).blocked for e in d.edges}
    i = next((k for k, a in enumerate(arcs) if int(g.a_edge[a]) in blocked), None)
    if i is None:
        return None
    node = int(g.a_from[arcs[i]])
    ca = corridor_arcs(g, node, d_node)
    st = edge_state(g, cond, dis, None)
    _, pred, amap = shortest(g, ca, arc_weights(g, ca, st, spec, cond, 0, 0, False), node, d_node)
    tail = arc_path(pred, amap, node, d_node)
    return list(arcs[:i]) + tail if tail else None


def run_batch(g: RoadGraph, m: pd.DataFrame, p: dict) -> dict:
    key = (tuple(p["crops"]), tuple(p["states"] or []), p["shipments_per_corridor"], p["corridors_per_crop"], p["days"], p["seed"])
    if key not in _CACHE:
        if len(_CACHE) > 16:
            _CACHE.clear()
        _CACHE[key] = _run(g, m, key)
    return _CACHE[key]


_CACHE: dict[tuple, dict] = {}


def _run(g: RoadGraph, m: pd.DataFrame, key: tuple) -> dict:
    crops, states, n_ship, n_corr, days, seed = key
    _, crops_cfg = load()
    rng = np.random.default_rng(seed)
    ships, routes = [], []
    for crop in crops:
        for o, d in corridors(m, crop, n_corr, list(states) or None):
            on, _ = g.nearest_node(float(o.lon), float(o.lat))
            dn, _ = g.nearest_node(float(d.lon), float(d.lat))
            if on == dn:
                continue
            price = (d.get(f"{crop}_price_rs_q") or 0) / 100 or None
            long_haul = float(hav_km(o.lon, o.lat, d.lon, d.lat)) > 450
            cond_key = crops_cfg[crop].raw.get("long_haul_condition") if long_haul else None
            spec0 = ShipmentSpec(crop=crop, kg=10000, price_rs_kg=price, condition=cond_key)
            plan = plan_route(g, on, dn, spec0, Conditions(), [], n_alt=2)
            if not plan.original or not plan.original.eval.feasible:
                continue
            pool = [c for c in plan.candidates if c.eval.feasible]
            orig_arcs = plan.original.eval.arcs
            rid = f"{crop}:{o.market_id}>{d.market_id}"
            routes.append({"route_id": rid, "crop": crop, "origin": o.market, "origin_state": o.state,
                           "destination": d.market, "destination_state": d.state,
                           "distance_km": round(plan.original.eval.distance_km),
                           "coords": [[round(x, 3), round(y, 3)] for x, y in route_coords(g, orig_arcs)[::25]]})
            for i in range(n_ship):
                day = int(rng.integers(0, days))
                kg = float(np.clip(rng.lognormal(math.log(9000), 0.35), 3000, 20000))
                cond = Conditions(ambient_c=float(rng.uniform(24, 42)), rh=float(rng.uniform(35, 90)),
                                  traffic=float(rng.uniform(1, 6)), road_quality=float(rng.uniform(7, 10)))
                dis: list[Disruption] = []
                if rng.random() < 0.55:   # ASSUMPTION: share of trips meeting a disruption
                    typ = str(rng.choice(DISRUPTION_TYPES, p=DISRUPTION_P))
                    frac = float(rng.uniform(0.2, 0.7))
                    stretch_km = float(rng.uniform(5, 40))
                    idx = int(len(orig_arcs) * frac)
                    edges, tot = [], 0.0
                    while idx < len(orig_arcs) and tot < stretch_km:
                        e = int(g.a_edge[orig_arcs[idx]])
                        edges.append(e)
                        tot += float(g.len_km[e])
                        idx += 1
                    end = float(rng.uniform(4, 24)) if typ == "closure" and rng.random() < 0.6 else None
                    dis.append(Disruption(f"b{i}", typ, edges, severity=float(rng.uniform(3, 9)), end_h=end))
                spec = ShipmentSpec(crop=crop, kg=kg, price_rs_kg=price, condition=cond_key, dispatch_hour=float(rng.uniform(0, 24)))
                cands = [Candidate(c.id, c.label, evaluate(g, c.eval.arcs, spec, cond, dis)) for c in pool]
                orig = next(c for c in cands if c.id == "original")
                plan_i = decide(orig, cands, spec)
                base = orig.eval
                if not base.feasible:   # status quo detours reactively at the closure
                    late = reactive_detour(g, orig_arcs, dn, spec, cond, dis)
                    if late:
                        base = evaluate(g, late, spec, cond, dis)
                chosen = plan_i.recommended.eval if plan_i.recommended else None
                if not base.feasible and chosen is None:
                    continue
                b_out = base.outcome if base.feasible else None
                c_out = chosen.outcome if chosen and chosen.feasible else b_out
                # No way round at all: the baseline load is held at the closure and counted as lost.
                b_waste = b_out.wastage_kg if b_out else kg
                b_sale = b_out.saleable_kg if b_out else 0.0
                ships.append({
                    "route_id": rid, "crop": crop, "origin_state": o.state, "day": day, "kg": kg,
                    "disrupted": bool(dis), "disruption": dis[0].type if dis else None, "decision": plan_i.decision,
                    "base_wastage_kg": b_waste, "opt_wastage_kg": c_out.wastage_kg if c_out else kg,
                    "base_saleable_kg": b_sale, "opt_saleable_kg": c_out.saleable_kg if c_out else 0.0,
                    "base_phys_kg": b_out.physical_loss_kg if b_out else 0.0, "opt_phys_kg": c_out.physical_loss_kg if c_out else 0.0,
                    "base_down_kg": b_out.downgraded_kg if b_out else 0.0, "opt_down_kg": c_out.downgraded_kg if c_out else 0.0,
                    "base_net_rs": base.net_value_rs if base.feasible else 0.0,   # cargo lost, no sale
                    "opt_net_rs": chosen.net_value_rs if chosen and chosen.feasible else (base.net_value_rs if base.feasible else 0.0),
                })
    df = pd.DataFrame(ships)
    if df.empty:
        return {"label": "SIMULATED", "shipments": 0, "routes": routes}

    def summ(g_: pd.DataFrame) -> dict:
        b, o, kg = g_.base_wastage_kg.sum(), g_.opt_wastage_kg.sum(), g_.kg.sum()
        b, o, kg = float(b), float(o), float(kg)
        return {"shipments": int(len(g_)), "kg": round(kg), "base_wastage_kg": round(b), "opt_wastage_kg": round(o),
                "saved_kg": round(b - o), "reduction_pct": round(100 * (b - o) / b, 1) if b > 0 else 0.0,
                "base_wastage_pct": round(100 * b / kg, 2), "opt_wastage_pct": round(100 * o / kg, 2),
                "base_saleable_kg": round(float(g_.base_saleable_kg.sum())), "opt_saleable_kg": round(float(g_.opt_saleable_kg.sum())),
                "net_benefit_rs": round(float(g_.opt_net_rs.sum() - g_.base_net_rs.sum())),
                "rerouted": int((g_.decision.isin(["reroute", "original_blocked"])).sum())}

    total = summ(df)
    total.update({
        "base_phys_kg": round(float(df.base_phys_kg.sum())), "opt_phys_kg": round(float(df.opt_phys_kg.sum())),
        "base_down_kg": round(float(df.base_down_kg.sum())), "opt_down_kg": round(float(df.opt_down_kg.sum())),
        "base_rejected_kg": round(float(df.base_wastage_kg.sum() - df.base_phys_kg.sum())),
        "opt_rejected_kg": round(float(df.opt_wastage_kg.sum() - df.opt_phys_kg.sum())),
    })
    by_route = []
    for rid, gr in df.groupby("route_id"):
        r = next(x for x in routes if x["route_id"] == rid)
        by_route.append({**{k: v for k, v in r.items() if k != "coords"}, **summ(gr)})
    by_route.sort(key=lambda r: -r["base_wastage_pct"])
    improved = sorted(by_route, key=lambda r: -r["saved_kg"])
    return {
        "label": "SIMULATED",
        "note": "Synthetic shipments on real mapped corridors; NOT observed reductions in wastage.",
        "params": {"crops": list(crops), "states": list(states), "shipments_per_corridor": n_ship,
                   "corridors_per_crop": n_corr, "days": days, "seed": seed},
        "total": total,
        "by_crop": [{"crop": c, **summ(gr)} for c, gr in df.groupby("crop")],
        "by_state": [{"state": s, **summ(gr)} for s, gr in df.groupby("origin_state")],
        "by_disruption": [{"disruption": s, **summ(gr)} for s, gr in df.fillna({"disruption": "none"}).groupby("disruption")],
        "by_route": by_route,
        "highest_risk": by_route[:5],
        "most_improved": improved[:5],
        "routes": routes,
    }

