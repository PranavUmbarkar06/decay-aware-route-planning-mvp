"""M7 Dispatcher route advisor (deck S6 journey: enter load → assess conditions → compare routes → alert → choose).

Compares the static free-flow shortest path to the planned market (baseline) with a quality-aware recommendation over
all markets with recent Agmarknet data plus NGO/processing sinks. Inputs at the business clock time:
- temperature: Open-Meteo replay at the origin district (REAL_FETCHED; ASSUMPTION fallback outside the window)
- congestion: MODELLED peak-hour profile (ASSUMPTION A9), never observed traffic; no disruptions are known
- market room: crowd-meter trailing median (REAL_DERIVED proxy), no knowledge of other dispatchers' loads
The system recommends; the dispatcher decides. Nothing is executed automatically.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.config import thresholds
from app.domain.decay import CommodityProfile, DecayModel
from app.models.orm import Node
from app.services import crowd, shelf_life
from app.services.custody import ServiceError
from app.simulation.network import Network, load_network
from app.simulation.policies import VALUE_WEIGHT
from app.simulation.scenario import sim_config


def _weights(net: Network, at: datetime) -> np.ndarray:
    tr = sim_config()["traffic"]
    h = (at + timedelta(hours=5, minutes=30)).hour
    peak = tr["peak_extra"]["value"] if any(a <= h < b for a, b in tr["peak_hours_ist"]) else 0.0
    return net.ff_s * (1.0 + peak)


def _geometry(net: Network, path: list[int]) -> list[list[float]]:
    pts = [[round(float(net.y[i]), 5), round(float(net.x[i]), 5)] for i in path]
    return pts if len(pts) <= 400 else pts[:: max(1, len(pts) // 400)] + [pts[-1]]


def _km(net: Network, path: list[int]) -> float:
    return sum(float(net.length_m[net.edge_index[(a, b)]]) for a, b in zip(path[:-1], path[1:], strict=True)) / 1000


def compare(db: Session, *, origin_node_id: str, commodity: str, qty_kg: float, harvest_time: datetime,
            planned_dest_id: str | None = None, dispatch_time: datetime | None = None) -> dict:
    net = load_network()
    if origin_node_id not in net.business:
        raise ServiceError(422, "This origin is not routable yet (it may be awaiting location review)", "not_routable")
    t0 = dispatch_time or now()
    origin = net.business[origin_node_id]
    model = DecayModel(CommodityProfile.load(commodity))
    on_node = db.get(Node, origin_node_id)
    hist_h = max(0, int((t0 - harvest_time).total_seconds() // 3600))
    temps_hist, prov_hist = shelf_life.temperatures(on_node.district if on_node else None, harvest_time, hist_h)
    age0 = model.age_after(0.0, temps_hist) if temps_hist else 0.0
    temps_next, prov_next = shelf_life.temperatures(origin.district, t0, 24)
    th = thresholds().quality
    today = t0.date()

    markets = [b for b in net.by_type("ReceivingMarket")]
    if planned_dest_id is None:
        with_data = [m for m in markets if (crowd.forecast_demand(m.name, commodity, today).qty_kg or 0) > 0]
        pool = with_data or markets
        d_ff, _ = net.sssp(net.ff_s, origin.gidx)
        planned_dest_id = min(pool, key=lambda m: d_ff[m.gidx]).node_id
    if planned_dest_id not in net.business:
        raise ServiceError(422, "Planned destination is not routable", "not_routable")

    d_ff, p_ff = net.sssp(net.ff_s, origin.gidx)
    w = _weights(net, t0)
    d_now, p_now = net.sssp(w, origin.gidx)

    def option(dest_id: str, dist: np.ndarray, pred: np.ndarray, kind: str) -> dict | None:
        b = net.business[dest_id]
        path = Network.path_from(pred, origin.gidx, b.gidx)
        if not path:
            return None
        eta_h = (float(dist[b.gidx]) + origin.access_s + b.access_s) / 3600
        k = int(np.ceil(eta_h))
        a_arr = model.age_after(age0, temps_next[:k] or [temps_next[0]])
        q_arr = model.quality(a_arr)
        f0 = model.spoiled_fraction(age0)
        qty_arr = qty_kg * (1 - model.spoiled_fraction(a_arr)) / max(1e-9, 1 - f0)
        bounds = {}
        for q10 in (2.0, 3.0):
            alt = DecayModel(model.profile, "q10", q10)
            bounds[f"q10_{q10:g}"] = round(alt.quality(alt.age_after(alt.age_for_quality(max(min(model.quality(age0), 0.999), 0.001)),
                                                                     temps_next[:k] or [temps_next[0]])), 3)
        out = {"dest": dest_id, "dest_name": b.name, "kind": kind, "eta_h": round(eta_h, 2), "km": round(_km(net, path), 1),
               "quality_at_arrival": round(q_arr, 3), "quality_bounds": bounds, "qty_at_arrival_kg": round(qty_arr, 1),
               "geometry": _geometry(net, path), "provenance": b.provenance}
        if kind == "market":
            fc = crowd.forecast_demand(b.name, commodity, today)
            meter = crowd.meter(b.name, commodity, today)
            room = fc.qty_kg or 0.0
            sale_ok = q_arr >= th.saleable_min
            out.update({"crowd": meter, "forecast_kg": fc.qty_kg,
                        "value_kg": VALUE_WEIGHT["market"] * (min(qty_arr, room) if sale_ok else 0.0)})
        elif kind == "ngo":
            out["value_kg"] = VALUE_WEIGHT["ngo"] * (qty_arr if q_arr >= th.saleable_min else 0.0)
        else:
            out["value_kg"] = VALUE_WEIGHT["processing"] * (qty_arr if q_arr >= th.processing_min else 0.0)
        return out

    baseline = option(planned_dest_id, d_ff, p_ff, "market")
    opts = [o for o in (option(m.node_id, d_now, p_now, "market") for m in markets) if o]
    opts += [o for o in (option(n.node_id, d_now, p_now, "ngo") for n in net.by_type("NGOSink")) if o]
    opts += [o for o in (option(n.node_id, d_now, p_now, "processing") for n in net.by_type("ProcessingSink")) if o]
    if not opts or baseline is None:
        raise ServiceError(422, "No reachable destination", "no_route")
    best = max(opts, key=lambda o: (o["value_kg"], -o["eta_h"]))
    planned_now = next(o for o in opts if o["dest"] == planned_dest_id)
    margin = sim_config()["policies"]["QualityAwareDynamic"]["reroute_margin"]["value"]
    if best["dest"] == planned_dest_id or best["value_kg"] <= planned_now["value_kg"] * (1 + margin):
        action, rec = "ROUTE", planned_now
    else:
        action, rec = ("REROUTE" if best["kind"] == "market" else "REDIRECT"), best
    temp_now = temps_next[0]
    accel = model.accel(temp_now)
    reasons = [f"Produce is {hist_h} h from harvest; model quality now {model.quality(age0):.2f}.",
               f"Temperature at origin now {temp_now:.0f} °C: ageing {accel:.1f}× the reference rate ({prov_next}).",
               f"Planned market {planned_now['dest_name']}: ETA {planned_now['eta_h']:.1f} h, quality on arrival "
               f"{planned_now['quality_at_arrival']:.2f}, crowd meter: {planned_now.get('crowd', {}).get('label', 'n/a')}."]
    if action != "ROUTE":
        reasons.append(f"Recommended {rec['dest_name']} ({rec['kind']}): ETA {rec['eta_h']:.1f} h, quality on arrival "
                       f"{rec['quality_at_arrival']:.2f}, expected useful kg ~{rec['value_kg']:.0f} vs ~{planned_now['value_kg']:.0f}.")
    alerts = []
    if planned_now["quality_at_arrival"] < th.saleable_min:
        alerts.append("Planned market: predicted quality on arrival is below the saleable threshold.")
    if planned_now.get("crowd", {}).get("status") == "GLUT_WARNING":
        alerts.append("Planned market shows a glut warning on the crowd meter.")
    if planned_now["eta_h"] > baseline["eta_h"] * 1.2:
        alerts.append("Modelled peak-hour congestion adds more than 20% to the free-flow time.")
    return {
        "action": action, "recommended": rec, "baseline": baseline, "planned_with_current_conditions": planned_now,
        "alternatives": sorted(opts, key=lambda o: -o["value_kg"])[:5], "reasons": reasons, "alerts": alerts,
        "inputs": {"dispatch_time_utc": t0.isoformat(), "ist_hour": (t0 + timedelta(hours=5, minutes=30)).hour,
                   "temperature_provenance": str(prov_next), "temperature_history_provenance": str(prov_hist),
                   "congestion": "MODELLED peak-hour profile (ASSUMPTION A9), not observed traffic; no disruption data",
                   "market_room": "crowd-meter trailing median (REAL_DERIVED proxy); other dispatchers' loads unknown",
                   "value_weights": {**VALUE_WEIGHT, "status": "ASSUMPTION A29"}},
        "uncertainty": "Quality bounds use constant Q10 = 2 and 3 (FAO 152 range). Reference lives are extrapolated from "
                       "cold storage (ASSUMPTIONS A2, A3).",
        "guardrail": "Recommendation only. The dispatcher decides; nothing is executed automatically.",
        "label": "Model output, not field-validated",
    }
