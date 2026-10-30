"""One routing + optimisation engine for every crop (plan v2 §5).

Crop identity never appears in a routing rule: crops differ only through the cost weights produced by their
deterioration parameters (config/crops_v2.yaml).

  arc cost (₹) = c_km·km + c_h·h                                transport
               + λ · k(T,RH) · h                                physiological decay (marginal ₹ per unit −ln Q)
               + μ · (r/10)² · km                               vibration damage (marginal ₹ per unit dose)
  λ and μ are linearised at the expected arrival state of a reference route (the "λ trick" of the v1 prototype).

Candidates: the planned (original) route, fastest under current conditions, crop-optimal, and penalty-method
alternatives. Every candidate is then simulated exactly (time-aware disruptions) and compared on net value.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Literal

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

from .crops import load
from .deterioration import Outcome, Segment, ShipmentSpec, StartState, grade_split, initial_quality, rate, simulate
from .graph import HIGHWAYS, RoadGraph, hav_km

DisruptionType = Literal["closure", "partial_blockage", "congestion", "reduced_speed", "construction",
                         "accident", "poor_road", "vehicle_restriction"]
DECISION_MARGIN_RS = 500.0
DECISION_MARGIN_FRAC = 0.01


@dataclass
class Conditions:
    ambient_c: float = 32.0
    rh: float = 60.0
    traffic: float = 2.0          # 0–10, network-wide
    extra_delay_h: float = 0.0    # additional unplanned stoppage (e.g. checkpost, queue)
    road_quality: float = 10.0    # 10 = as mapped; lower worsens every road
    vibration: float = 5.0        # 5 = as modelled; scales vibration dose ×(vibration/5)


@dataclass
class Disruption:
    id: str
    type: DisruptionType
    edges: list[int]
    severity: float = 5.0         # 0–10
    start_h: float = 0.0          # hours after dispatch
    end_h: float | None = None    # None = until further notice
    heavy_only: bool = True
    alt_access: bool = False
    confirmed: bool = True

    def active(self, t_h: float) -> bool:
        return t_h >= self.start_h and (self.end_h is None or t_h < self.end_h)

    def overlaps(self, t0: float, t1: float) -> bool:
        return self.start_h < t1 and (self.end_h is None or self.end_h > t0)


@dataclass
class Effect:
    blocked: bool = False
    speed_mult: float = 1.0
    delay_h: float = 0.0
    rough_add: float = 0.0
    rough_min: float = 0.0
    heat: float = 0.0             # extra traffic-severity points → idling heat


def effect_of(d: Disruption) -> Effect:
    s = max(0.0, min(10.0, d.severity))
    t = d.type
    if t == "closure":
        return Effect(speed_mult=0.5, delay_h=0.3 + 0.05 * s) if d.alt_access else Effect(blocked=True)
    if t == "vehicle_restriction":
        return Effect(blocked=True) if d.heavy_only else Effect()
    if t == "accident":
        if s >= 7 and not d.alt_access:
            return Effect(blocked=True)
        return Effect(speed_mult=max(0.15, 1 - 0.08 * s), delay_h=0.1 * s, heat=s / 2)
    if t == "partial_blockage":
        return Effect(speed_mult=max(0.2, 1 - 0.07 * s), delay_h=0.05 * s, heat=s / 2)
    if t == "congestion":
        return Effect(speed_mult=1 / (1 + 0.3 * s), heat=s)
    if t == "reduced_speed":
        return Effect(speed_mult=max(0.2, 1 - 0.06 * s))
    if t == "construction":
        return Effect(speed_mult=max(0.3, 1 - 0.05 * s), rough_add=0.5 * s, heat=s / 3)
    if t == "poor_road":
        return Effect(rough_min=s, speed_mult=max(0.4, 1 - 0.03 * s))
    return Effect()


def combine(effects: list[Effect]) -> Effect:
    out = Effect()
    for e in effects:
        out.blocked |= e.blocked
        out.speed_mult *= e.speed_mult
        out.delay_h += e.delay_h
        out.rough_add += e.rough_add
        out.rough_min = max(out.rough_min, e.rough_min)
        out.heat += e.heat
    return out


def traffic_mult(traffic: float) -> float:
    return 1 / (1 + 0.06 * max(0.0, traffic))


# ---------------------------------------------------------------- static arc state (for Dijkstra)

@dataclass
class ArcState:
    hours: np.ndarray       # per edge traversal time incl. disruption delays
    rough: np.ndarray       # per edge effective roughness
    heat: np.ndarray        # per edge extra traffic points
    blocked: np.ndarray     # per edge bool


def edge_state(g: RoadGraph, cond: Conditions, disruptions: list[Disruption], horizon: tuple[float, float] | None) -> ArcState:
    m = len(g.len_km)
    speed = g.speed * traffic_mult(cond.traffic)
    rough = np.minimum(10.0, g.rough + (10 - cond.road_quality) * 0.5)
    delay = np.zeros(m)
    heat = np.full(m, cond.traffic, dtype=float)
    blocked = np.zeros(m, dtype=bool)
    for d in disruptions:
        if horizon is not None and not d.overlaps(*horizon):
            continue
        ef = effect_of(d)
        idx = np.asarray(d.edges, dtype=np.int64)
        if ef.blocked:
            blocked[idx] = True
            continue
        speed[idx] *= ef.speed_mult
        delay[idx] += ef.delay_h / max(1, len(idx))   # one stoppage per disrupted stretch, spread across its edges
        rough[idx] = np.minimum(10.0, np.maximum(rough[idx] + ef.rough_add, ef.rough_min))
        heat[idx] += ef.heat
    return ArcState(hours=g.len_km / np.maximum(speed, 1.0) + delay, rough=rough, heat=heat, blocked=blocked)


# ---------------------------------------------------------------- corridor-pruned Dijkstra

@dataclass
class Corridor:
    arcs: np.ndarray        # indices into g.a_* of arcs inside the corridor
    keys: np.ndarray        # sorted unique (from*n + to) of the deduped arcs
    best_arc: np.ndarray    # arc index for each key (filled per weight vector)


def corridor_arcs(g: RoadGraph, o: int, d: int, factor: float | None = None, pad_km: float = 60.0) -> np.ndarray:
    direct = float(hav_km(g.lon[o], g.lat[o], g.lon[d], g.lat[d]))
    if factor is None:   # long trips need proportionally less room for detours
        factor = 1.5 if direct < 300 else (1.35 if direct < 800 else 1.25)
    budget = factor * direct + pad_km
    node_ok = (hav_km(g.lon[o], g.lat[o], g.lon, g.lat) + hav_km(g.lon[d], g.lat[d], g.lon, g.lat)) <= budget
    return np.nonzero(node_ok[g.a_from] & node_ok[g.a_to])[0]


def shortest(g: RoadGraph, arcs: np.ndarray, w_arc: np.ndarray, src: int, dst: int | None = None,
             reverse: bool = False) -> tuple[np.ndarray, np.ndarray, dict[tuple[int, int], int]]:
    """Dijkstra over `arcs` with weights `w_arc` (one per arc in `arcs`). Returns dist, predecessors and the
    (from, to) → arc map used to reconstruct arc paths (parallel arcs: cheapest wins)."""
    ok = np.isfinite(w_arc)
    arcs, w = arcs[ok], np.maximum(w_arc[ok], 1e-9)
    fr, to = g.a_from[arcs], g.a_to[arcs]
    if reverse:
        fr, to = to, fr
    order = np.lexsort((w, to, fr))
    fr, to, w, arcs = fr[order], to[order], w[order], arcs[order]
    first = np.ones(len(fr), dtype=bool)
    first[1:] = (fr[1:] != fr[:-1]) | (to[1:] != to[:-1])
    fr, to, w, arcs = fr[first], to[first], w[first], arcs[first]
    mat = csr_matrix((w, (fr, to)), shape=(g.n, g.n))
    dist, pred = dijkstra(mat, directed=True, indices=src, return_predecessors=True,
                          limit=np.inf if dst is None else np.inf)
    amap = dict(zip(zip(fr.tolist(), to.tolist()), arcs.tolist())) if dst is not None else {}
    return dist, pred, amap


def arc_path(pred: np.ndarray, amap: dict[tuple[int, int], int], src: int, dst: int) -> list[int] | None:
    if dst != src and pred[dst] < 0:
        return None
    out = []
    v = dst
    while v != src:
        u = int(pred[v])
        out.append(amap[(u, v)])
        v = u
    return out[::-1]


# ---------------------------------------------------------------- exact, time-aware evaluation

@dataclass
class RouteEval:
    feasible: bool
    reason: str
    outcome: Outcome | None
    arcs: list[int]
    distance_km: float
    drive_h: float
    free_flow_h: float
    wait_h: float
    delay_h: float
    road_quality: float            # 0–10, higher is better (km-weighted)
    vibration_risk_pct: float
    transport_cost_rs: float
    net_value_rs: float
    segments: list[dict] = field(default_factory=list)   # coloured stretches for the map


def _vehicle(spec: ShipmentSpec) -> dict:
    common, crops = load()
    return common.vehicles[spec.vehicle or crops[spec.crop].default_vehicle]


def evaluate(g: RoadGraph, arcs: list[int], spec: ShipmentSpec, cond: Conditions, disruptions: list[Disruption],
             start: StartState | None = None, include_wait: bool = True) -> RouteEval:
    t = start.t_h if start else 0.0
    by_edge: dict[int, list[Disruption]] = {}
    for d in disruptions:
        for e in d.edges:
            by_edge.setdefault(int(e), []).append(d)
    tm = traffic_mult(cond.traffic)
    vib_scale = max(0.0, cond.vibration) / 5
    segs: list[Segment] = []
    marks: list[dict] = []
    drive = free = wait = km = rough_km = 0.0
    extra_left = cond.extra_delay_h
    half_km = sum(float(g.len_km[g.a_edge[a]]) for a in arcs) / 2
    # Undisrupted arcs are merged into ≤30-minute segments; roughness is combined as RMS so the vibration dose
    # Σ(r/10)²·km is unchanged.
    acc = {"h": 0.0, "km": 0.0, "r2km": 0.0, "traffic": 0.0}

    def flush() -> None:
        if acc["h"] > 0:
            r = math.sqrt(acc["r2km"] / acc["km"]) if acc["km"] > 0 else 0.0
            segs.append(Segment(hours=acc["h"], km=acc["km"], ambient_c=cond.ambient_c, rh=cond.rh, roughness=r,
                                traffic=acc["traffic"]))
        acc.update(h=0.0, km=0.0, r2km=0.0, traffic=0.0)

    for a in arcs:
        e = int(g.a_edge[a])
        L = float(g.len_km[e])
        active = [d for d in by_edge.get(e, []) if d.active(t)]
        ef = combine([effect_of(d) for d in active])
        if ef.blocked:
            ends = [d.end_h for d in active if effect_of(d).blocked]
            if any(x is None for x in ends):
                return RouteEval(False, f"Blocked at {g.ref[e] or g.name[e] or HIGHWAYS[g.hw[e]]} (edge {e}) with no reopening time",
                                 None, arcs, 0, 0, 0, 0, 0, 0, 0, 0, -math.inf)
            hold = max(ends) - t
            wait += hold
            flush()
            segs.append(Segment(hours=hold, ambient_c=cond.ambient_c, rh=cond.rh, traffic=cond.traffic, moving=False))
            t += hold
            marks.append({"edge": e, "kind": "blocked_wait", "hours": round(hold, 2)})
            ef = combine([effect_of(d) for d in by_edge.get(e, []) if d.active(t)])
        v = max(1.0, float(g.speed[e]) * tm * ef.speed_mult)
        h = L / v + ef.delay_h / max(1, len(active[0].edges) if active else 1)
        r = min(10.0, max(float(g.rough[e]) + (10 - cond.road_quality) * 0.5 + ef.rough_add, ef.rough_min))
        r_vib = min(10.0, r * math.sqrt(vib_scale))
        if active:
            flush()
            segs.append(Segment(hours=h, km=L, ambient_c=cond.ambient_c, rh=cond.rh, roughness=r_vib,
                                traffic=cond.traffic + ef.heat))
        else:
            acc["h"] += h
            acc["km"] += L
            acc["r2km"] += r_vib ** 2 * L
            acc["traffic"] = cond.traffic
            if acc["h"] >= 0.5:
                flush()
        if active:
            kind = "blocked" if any(effect_of(d).blocked for d in active) else (
                "poor" if ef.rough_min or ef.rough_add else "congested")
            marks.append({"edge": e, "kind": kind})
        elif r >= 7:
            marks.append({"edge": e, "kind": "poor"})
        drive += h
        free += L / float(g.speed[e])
        km += L
        rough_km += r * L
        t += h
        if extra_left > 0 and km >= half_km:
            flush()
            segs.append(Segment(hours=extra_left, ambient_c=cond.ambient_c, rh=cond.rh, traffic=cond.traffic, moving=False))
            wait += extra_left
            t += extra_left
            extra_left = 0.0
    flush()
    out = simulate(spec, segs, start=start, include_wait=include_wait)
    veh = _vehicle(spec)
    moving_h = drive
    cost = (km * veh["rs_per_km"]) + (moving_h + wait) * veh["rs_per_h"]
    return RouteEval(
        feasible=True, reason="", outcome=out, arcs=arcs, distance_km=km, drive_h=drive, free_flow_h=free,
        wait_h=wait + (spec.market_wait_h if include_wait else 0), delay_h=max(0.0, drive + wait - free),
        road_quality=10 - (rough_km / km if km else 0), vibration_risk_pct=100 * out.d_mech,
        transport_cost_rs=cost, net_value_rs=out.revenue_rs - cost, segments=marks,
    )


# ---------------------------------------------------------------- optimisation

@dataclass
class Candidate:
    id: str
    label: str
    eval: RouteEval


@dataclass
class Plan:
    feasible: bool
    original: Candidate | None
    candidates: list[Candidate]
    recommended: Candidate | None
    decision: Literal["reroute", "continue", "no_feasible_route", "original_blocked"]
    explanation: list[str]
    margin_rs: float


def _marginals(spec: ShipmentSpec, ref: RouteEval | None) -> tuple[float, float]:
    """λ (₹ per unit −ln Q) and μ (₹ per unit vibration dose) at the reference route's arrival state."""
    common, crops = load()
    crop = crops[spec.crop]
    price = spec.price_rs_kg if spec.price_rs_kg is not None else crop.default_price
    value = spec.kg * price
    if ref is None or ref.outcome is None:
        q = initial_quality(spec) * 0.9
        dose = 0.0
    else:
        q, dose = ref.outcome.q_arrival, ref.outcome.vib_dose

    def val(qq: float) -> float:
        a, d, _ = grade_split(qq, common)
        return a + d * common.downgrade_price_factor

    eps = 0.02
    lam = value * max(0.0, val(q) - val(q * math.exp(-eps))) / eps
    pack = common.packaging_factor[spec.packaging or crop.default_packaging] * common.loading_factor[spec.loading]
    mu = value * crop.beta_vib * pack * math.exp(-crop.beta_vib * pack * dose)
    return max(lam, value * 0.02), mu


def arc_weights(g: RoadGraph, arcs: np.ndarray, st: ArcState, spec: ShipmentSpec, cond: Conditions,
                lam: float, mu: float, crop_aware: bool) -> np.ndarray:
    e = g.a_edge[arcs]
    h = st.hours[e]
    veh = _vehicle(spec)
    w = veh["rs_per_km"] * g.len_km[e] + veh["rs_per_h"] * h
    if crop_aware:
        common, crops = load()
        crop = crops[spec.crop]
        if veh["refrigerated"] and spec.refrigeration_ok and spec.reefer_fail_at_h is None:
            k = np.full(len(e), rate(crop, common, crop.reefer_set_c, crop.rh_opt, spec.q10))
        else:
            # daily-mean solar load; idling heat from traffic points on the edge
            tc = cond.ambient_c + common.solar_load_c * 0.4 + common.idle_heat_per_traffic_c * st.heat[e]
            rh = min(100.0, cond.rh + (1 - veh["ventilation"]) * common.closed_body_rh_rise)
            grid = np.arange(-2, 56)
            kk = np.array([rate(crop, common, float(x), rh, spec.q10) for x in grid])
            k = np.interp(tc, grid, kk)
        k = k / crop.condition_life_factor.get(spec.condition or crop.default_condition, 1.0)
        vib = max(0.0, cond.vibration) / 5
        w = w + lam * k * h + mu * vib * (st.rough[e] / 10) ** 2 * g.len_km[e]
    w = np.where(st.blocked[e], np.inf, w)
    return w


def _overlap(g: RoadGraph, a: list[int], b: list[int]) -> float:
    ea, eb = {int(g.a_edge[x]) for x in a}, {int(g.a_edge[x]) for x in b}
    la = sum(g.len_km[list(ea)]) or 1
    return float(sum(g.len_km[list(ea & eb)]) / la)


def plan_route(g: RoadGraph, o: int, d: int, spec: ShipmentSpec, cond: Conditions, disruptions: list[Disruption],
               *, original_arcs: list[int] | None = None, start: StartState | None = None, n_alt: int = 3) -> Plan:
    arcs = corridor_arcs(g, o, d)
    nominal = edge_state(g, cond, [], None)
    # Original = the route a dispatcher plans at dispatch: fastest on the network without the disruptions.
    if original_arcs is None:
        dist, pred, amap = shortest(g, arcs, arc_weights(g, arcs, nominal, spec, cond, 0, 0, False), o, d)
        original_arcs = arc_path(pred, amap, o, d)
    candidates: list[Candidate] = []
    original = None
    if original_arcs is not None:
        ev = evaluate(g, original_arcs, spec, cond, disruptions, start)
        original = Candidate("original", "Original (planned fastest)", ev)
        candidates.append(original)
    horizon_end = (original.eval.drive_h + original.eval.wait_h if original and original.eval.feasible else 48) * 1.5 + 6
    t0 = start.t_h if start else 0.0
    st = edge_state(g, cond, disruptions, (t0, t0 + horizon_end))

    def add(cid: str, label: str, path: list[int] | None) -> list[int] | None:
        if not path:
            return None
        if any(_overlap(g, path, c.eval.arcs) > 0.97 and _overlap(g, c.eval.arcs, path) > 0.97 for c in candidates):
            return path
        candidates.append(Candidate(cid, label, evaluate(g, path, spec, cond, disruptions, start)))
        return path

    w_fast = arc_weights(g, arcs, st, spec, cond, 0, 0, False)
    _, pred, amap = shortest(g, arcs, w_fast, o, d)
    fastest = add("fastest_now", "Fastest under current conditions", arc_path(pred, amap, o, d))

    ref = original.eval if original and original.eval.feasible else (candidates[-1].eval if candidates else None)
    lam, mu = _marginals(spec, ref)
    best_path = None
    for _ in range(2):   # re-linearise once at the crop-optimal route's own arrival state
        w = arc_weights(g, arcs, st, spec, cond, lam, mu, True)
        _, pred, amap = shortest(g, arcs, w, o, d)
        best_path = arc_path(pred, amap, o, d)
        if not best_path:
            break
        ev = evaluate(g, best_path, spec, cond, disruptions, start)
        lam, mu = _marginals(spec, ev)
    add("crop_optimal", "Crop-aware optimum", best_path)

    # Penalty-method alternatives around the crop-aware optimum.
    if best_path:
        w = arc_weights(g, arcs, st, spec, cond, lam, mu, True)
        pos = {int(a): i for i, a in enumerate(arcs)}
        used = list(best_path) + (fastest or [])
        for k in range(n_alt):
            for a in used:
                i = pos.get(int(a))
                if i is not None:
                    w[i] *= 1.4
            _, pred, amap = shortest(g, arcs, w, o, d)
            p = arc_path(pred, amap, o, d)
            if not p:
                break
            if all(_overlap(g, p, c.eval.arcs) < 0.8 for c in candidates):
                add(f"alt_{k + 1}", f"Alternative {k + 1}", p)
            used = p

    return decide(original, candidates, spec)


def decision_margin(spec: ShipmentSpec) -> float:
    _, crops = load()
    price = spec.price_rs_kg if spec.price_rs_kg is not None else crops[spec.crop].default_price
    return max(DECISION_MARGIN_RS, DECISION_MARGIN_FRAC * spec.kg * price)


def decide(original: Candidate | None, candidates: list[Candidate], spec: ShipmentSpec) -> Plan:
    """Recommend only an economically justified change; say so explicitly when nothing is feasible."""
    feasible = [c for c in candidates if c.eval.feasible]
    margin = decision_margin(spec)
    if not feasible:
        return Plan(False, original, candidates, None, "no_feasible_route",
                    ["No feasible route exists between origin and destination under the current disruptions."], margin)
    best = max(feasible, key=lambda c: c.eval.net_value_rs)
    expl: list[str] = []
    if original is None or not original.eval.feasible:
        reason = original.eval.reason if original else "no planned route"
        expl.append(f"The original route is not usable: {reason}.")
        expl += _why(best, original)
        return Plan(True, original, candidates, best, "original_blocked", expl, margin)
    gain = best.eval.net_value_rs - original.eval.net_value_rs
    if best is original or gain <= margin:
        expl.append(f"Continue on the original route: the best alternative improves net value by ₹{gain:,.0f}, "
                    f"below the ₹{margin:,.0f} decision margin, so a detour is not justified.")
        return Plan(True, original, candidates, original, "continue", expl, margin)
    expl += _why(best, original)
    return Plan(True, original, candidates, best, "reroute", expl, margin)


def _why(best: Candidate, orig: Candidate | None) -> list[str]:
    b = best.eval
    if orig is None or not orig.eval.feasible:
        return [f"Recommended: {best.label}, {b.distance_km:.0f} km, net value ₹{b.net_value_rs:,.0f}."]
    o = orig.eval
    ob, bb = o.outcome, b.outcome
    lines = [f"Switch to {best.label}: net value +₹{b.net_value_rs - o.net_value_rs:,.0f} after "
             f"{b.distance_km - o.distance_km:+.0f} km and {b.transport_cost_rs - o.transport_cost_rs:+,.0f} ₹ transport cost."]
    if ob and bb:
        lines.append(f"Projected wastage {ob.wastage_kg:,.0f} kg → {bb.wastage_kg:,.0f} kg; saleable {ob.saleable_kg:,.0f} → {bb.saleable_kg:,.0f} kg.")
        drivers = []
        if bb.heat_degree_h < ob.heat_degree_h * 0.9:
            drivers.append(f"less heat exposure ({ob.heat_degree_h:.0f} → {bb.heat_degree_h:.0f} °C·h)")
        if b.vibration_risk_pct < o.vibration_risk_pct * 0.9:
            drivers.append(f"smoother roads (vibration damage {o.vibration_risk_pct:.1f}% → {b.vibration_risk_pct:.1f}%)")
        if b.drive_h + b.wait_h < o.drive_h + o.wait_h - 0.1:
            drivers.append(f"shorter time on the road ({o.drive_h + o.wait_h:.1f} h → {b.drive_h + b.wait_h:.1f} h)")
        if drivers:
            lines.append("Driven by " + ", ".join(drivers) + ".")
    return lines


def route_coords(g: RoadGraph, arcs: list[int]) -> list[list[float]]:
    out: list[list[float]] = []
    for a in arcs:
        pts = g.edge_coords(int(g.a_edge[a]), bool(g.a_fwd[a]))
        out.extend(pts if not out else pts[1:])
    return out


def eval_summary(ev: RouteEval, spec: ShipmentSpec, dispatch_hour: float) -> dict:
    o = ev.outcome
    if not ev.feasible or o is None:
        return {"feasible": False, "reason": ev.reason}
    total_h = o.hours
    arr = (dispatch_hour + total_h)
    return {
        "feasible": True,
        "distance_km": round(ev.distance_km, 1),
        "travel_h": round(ev.drive_h, 2),
        "delay_h": round(ev.delay_h, 2),
        "wait_h": round(ev.wait_h, 2),
        "road_quality": round(ev.road_quality, 1),
        "vibration_risk_pct": round(ev.vibration_risk_pct, 2),
        "mean_cargo_temp_c": round(o.mean_cargo_temp_c, 1),
        "max_cargo_temp_c": round(o.max_cargo_temp_c, 1),
        "heat_degree_h": round(o.heat_degree_h, 0),
        "q_arrival": round(o.q_arrival, 4),
        "kg": round(o.kg),
        "physical_loss_kg": round(o.physical_loss_kg, 1),
        "rejected_kg": round(o.rejected_kg, 1),
        "downgraded_kg": round(o.downgraded_kg, 1),
        "grade_a_kg": round(o.grade_a_kg, 1),
        "wastage_kg": round(o.wastage_kg, 1),
        "wastage_pct": round(o.wastage_pct, 2),
        "saleable_kg": round(o.saleable_kg, 1),
        "revenue_rs": round(o.revenue_rs),
        "transport_cost_rs": round(ev.transport_cost_rs),
        "net_value_rs": round(ev.net_value_rs),
        "total_h": round(total_h, 2),
        "arrival_day": int(arr // 24),
        "arrival_clock": f"{int(arr % 24):02d}:{int((arr % 1) * 60):02d}",
        "profile": [[round(t, 2), round(q, 4)] for t, q in o.profile[:: max(1, len(o.profile) // 60)]],
    }
