"""Dispatcher decision support (plan v2 §5b). The system never reroutes by itself: it works out whether a decision
is needed, where the truck can still divert, the point of no return (PNR), and the deadline by which a human must
approve so that the driver can be told and turn safely.

    t_deadline = t_PNR(pessimistic ETA) − (communication + acknowledgement + manoeuvre buffers)
    t_alert    = t_deadline − (review time + queue wait)
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Literal

import numpy as np

from .deterioration import ShipmentSpec, StartState
from .graph import RoadGraph
from .routing import (Conditions, Disruption, arc_weights, combine, corridor_arcs, edge_state, effect_of, evaluate,
                      shortest, traffic_mult, _marginals)
from .crops import load

Tier = Literal["CRITICAL", "HIGH", "ADVISORY", "MONITOR", "EXPIRED", "NONE"]


@dataclass
class Buffers:   # minutes; ASSUMPTION until calibrated from the decision log
    communication: float = 3.0
    acknowledgement: float = 5.0
    manoeuvre: float = 2.0
    review: float = 4.0
    eta_uncertainty: float = 0.15   # ± fraction of remaining time

    @property
    def driver_h(self) -> float:
        return (self.communication + self.acknowledgement + self.manoeuvre) / 60


@dataclass
class DiversionOption:
    node: int
    route_index: int          # index into the current route's arcs where the truck leaves it
    km_ahead: float
    eta_h: float              # expected
    eta_lo_h: float           # pessimistic (earliest) arrival at the junction
    deadline_h: float
    net_value_rs: float
    benefit_rs: float
    distance_km: float
    wastage_kg: float
    saleable_kg: float
    arcs: list[int] = field(default_factory=list)
    reachable: bool = True
    label: str = ""


@dataclass
class DecisionWindow:
    needed: bool
    tier: Tier
    reason: str
    now_h: float
    stay_feasible: bool
    stay_net_rs: float
    stay_wastage_kg: float
    options: list[DiversionOption]
    pnr: DiversionOption | None
    deadline_h: float | None
    alert_at_h: float | None
    recommended_decision_h: float | None
    slack_min: float | None
    wait_and_see: bool
    benefit_curve: list[tuple[float, float]]   # (minutes from now until the junction, benefit ₹)
    affecting: list[str]


def tier_for(slack_min: float, buf: Buffers) -> Tier:
    if slack_min < 0:
        return "EXPIRED"
    if slack_min < buf.review:
        return "CRITICAL"
    if slack_min < 15:
        return "HIGH"
    if slack_min < 60:
        return "ADVISORY"
    return "MONITOR"


def arrival_times(g: RoadGraph, arcs: list[int], cond: Conditions, disruptions: list[Disruption], t0: float,
                  first_progress: float = 0.0) -> np.ndarray:
    """Expected time at the START of each arc (and the end of the last), time-aware disruptions, no blocking waits."""
    by_edge: dict[int, list[Disruption]] = {}
    for d in disruptions:
        for e in d.edges:
            by_edge.setdefault(int(e), []).append(d)
    tm = traffic_mult(cond.traffic)
    t = t0
    out = np.empty(len(arcs) + 1)
    for i, a in enumerate(arcs):
        out[i] = t
        e = int(g.a_edge[a])
        ef = combine([effect_of(d) for d in by_edge.get(e, []) if d.active(t) and not effect_of(d).blocked])
        L = float(g.len_km[e]) * (1 - first_progress if i == 0 else 1)
        t += L / max(1.0, float(g.speed[e]) * tm * ef.speed_mult)
    out[-1] = t
    return out


def decision_window(g: RoadGraph, route: list[int], pos: int, start: StartState, d_node: int, spec: ShipmentSpec,
                    cond: Conditions, disruptions: list[Disruption], *, now_h: float | None = None,
                    buffers: Buffers | None = None, margin_rs: float | None = None, progress: float = 0.0,
                    max_exact: int = 10) -> DecisionWindow:
    """`route[pos]` is the arc the truck is on (fraction `progress` done). Times are hours after dispatch."""
    buf = buffers or Buffers()
    now = start.t_h if now_h is None else now_h
    ahead = route[pos:]
    times = arrival_times(g, ahead, cond, disruptions, now, progress)
    remaining = times[-1] - now
    lo = now + (times - now) * (1 - buf.eta_uncertainty)
    hi = now + (times - now) * (1 + buf.eta_uncertainty)

    # 1. Relevance: which disruptions overlap the truck's ETA window at their edges?
    idx_of_edge: dict[int, int] = {}
    for i, a in enumerate(ahead):
        idx_of_edge.setdefault(int(g.a_edge[a]), i)
    affecting = []
    for d in disruptions:
        hits = [idx_of_edge[e] for e in d.edges if e in idx_of_edge]
        if not hits:
            continue
        i = min(hits)
        if d.overlaps(lo[i], hi[max(hits) + 1]):
            affecting.append(d.id)
    common, crops = load()
    price = spec.price_rs_kg if spec.price_rs_kg is not None else crops[spec.crop].default_price
    margin = margin_rs if margin_rs is not None else max(500.0, 0.01 * spec.kg * price)

    stay = evaluate(g, ahead, spec, cond, disruptions, start)
    stay_net = stay.net_value_rs if stay.feasible else -math.inf
    stay_waste = stay.outcome.wastage_kg if stay.feasible and stay.outcome else math.nan
    empty = DecisionWindow(False, "NONE", "", now, stay.feasible, stay_net, stay_waste, [], None, None, None, None,
                           None, False, [], affecting)
    if not affecting:
        empty.reason = ("No disruption overlaps this truck's expected time window on its route; monitoring only."
                        if disruptions else "No disruptions on the route.")
        return empty

    # 2. Diversion points via one reverse Dijkstra from the destination (cost-to-go for every node).
    o_node = int(g.a_from[ahead[0]])
    arcs_c = corridor_arcs(g, o_node, d_node)
    horizon = (now, now + max(remaining, 1) * 1.5 + 6)
    st = edge_state(g, cond, disruptions, horizon)
    lam, mu = _marginals(spec, stay if stay.feasible else None)
    w = arc_weights(g, arcs_c, st, spec, cond, lam, mu, True)
    ctg, pred_rev, _ = shortest(g, arcs_c, w, d_node, reverse=True)
    pos_c = {int(a): i for i, a in enumerate(arcs_c)}
    out_arcs: dict[int, list[int]] = {}
    for a in arcs_c:
        out_arcs.setdefault(int(g.a_from[a]), []).append(int(a))
    w_route = np.array([w[pos_c[int(a)]] if int(a) in pos_c else np.inf for a in ahead])
    stay_suffix = np.concatenate([np.cumsum(w_route[::-1])[::-1], [0.0]])

    screened: list[tuple[int, int, float]] = []   # (route index i, first arc, screen benefit)
    for i in range(1, len(ahead)):                # node at the start of ahead[i]; i=0 is mid-arc
        node = int(g.a_from[ahead[i]])
        best_a, best_c = -1, math.inf
        for a in out_arcs.get(node, []):
            if a == int(ahead[i]):
                continue
            c = w[pos_c[a]] + ctg[int(g.a_to[a])]
            if c < best_c:
                best_a, best_c = a, c
        if best_a >= 0 and math.isfinite(best_c):
            screened.append((i, best_a, stay_suffix[i] - best_c))

    def follow(first_arc: int) -> list[int] | None:
        path = [first_arc]
        v = int(g.a_to[first_arc])
        guard = 0
        while v != d_node and guard < 200000:
            nxt = int(pred_rev[v])
            if nxt < 0:
                return None
            cands = [a for a in out_arcs.get(v, []) if int(g.a_to[a]) == nxt]
            if not cands:
                return None
            a = min(cands, key=lambda x: w[pos_c[x]])
            path.append(a)
            v = nxt
            guard += 1
        return path

    positive = [s for s in screened if s[2] > 0]
    pick: list[tuple[int, int, float]] = []
    if positive:
        tail = positive[-max_exact // 2:]
        step = max(1, len(positive) // max(1, max_exact - len(tail)))
        pick = sorted({s[0]: s for s in positive[::step] + tail}.values())
    options: list[DiversionOption] = []
    km_cum = np.concatenate([[0.0], np.cumsum([g.len_km[int(g.a_edge[a])] for a in ahead])])
    for i, first, _ in pick:
        tail_path = follow(first)
        if not tail_path:
            continue
        path = list(ahead[:i]) + tail_path
        ev = evaluate(g, path, spec, cond, disruptions, start)
        if not ev.feasible or ev.outcome is None:
            continue
        benefit = ev.net_value_rs - stay_net if stay.feasible else math.inf
        deadline = lo[i] - buf.driver_h
        options.append(DiversionOption(
            node=int(g.a_from[ahead[i]]), route_index=pos + i, km_ahead=float(km_cum[i] - km_cum[0] * 0), eta_h=float(times[i]),
            eta_lo_h=float(lo[i]), deadline_h=float(deadline), net_value_rs=ev.net_value_rs,
            benefit_rs=benefit, distance_km=ev.distance_km, wastage_kg=ev.outcome.wastage_kg,
            saleable_kg=ev.outcome.saleable_kg, arcs=path, reachable=bool(deadline >= now),
            label=_junction_label(g, ahead, i)))
    good = [op for op in options if op.benefit_rs > margin]
    curve = [(round((op.eta_h - now) * 60, 1), round(op.benefit_rs if math.isfinite(op.benefit_rs) else op.net_value_rs, 0))
             for op in options]
    if not good:
        empty.reason = (f"A disruption affects the route, but no diversion beats staying by more than the "
                        f"₹{margin:,.0f} margin. Recommend continuing; keep monitoring.")
        empty.benefit_curve = curve
        empty.options = options
        return empty

    pnr = good[-1]
    deadline = pnr.deadline_h
    alert_at = deadline - buf.review / 60
    slack_min = (deadline - now) * 60
    reachable = [op for op in good if op.reachable]
    unconfirmed = any(not d.confirmed for d in disruptions if d.id in affecting)
    far = all(d.start_h - now > 2 for d in disruptions if d.id in affecting)
    wait_and_see = (unconfirmed or far) and slack_min > buf.review
    tier = tier_for(slack_min, buf)
    if tier == "EXPIRED":
        reason = ("The point of no return has been passed for the best diversion. "
                  + ("Still-reachable options are listed." if reachable else "No diversion is still reachable; continue and re-plan from the next junction."))
    else:
        best = max(good, key=lambda x: x.benefit_rs)
        reason = (f"Diverting saves up to ₹{best.benefit_rs:,.0f} net ({stay_waste - best.wastage_kg:,.0f} kg less wastage) "
                  if stay.feasible else "The current route is blocked; diversion is required. ")
        reason += f"Last safe diversion: {pnr.label}, {pnr.km_ahead:.0f} km ahead."
    return DecisionWindow(
        needed=True, tier=tier, reason=reason, now_h=now, stay_feasible=stay.feasible, stay_net_rs=stay_net,
        stay_wastage_kg=stay_waste, options=good if tier != "EXPIRED" else reachable, pnr=pnr,
        deadline_h=deadline, alert_at_h=alert_at,
        recommended_decision_h=max(now, alert_at) if wait_and_see else now,
        slack_min=slack_min, wait_and_see=wait_and_see, benefit_curve=curve, affecting=affecting)


def _junction_label(g: RoadGraph, arcs: list[int], i: int) -> str:
    a_prev, a_next = int(g.a_edge[arcs[i - 1]]), int(g.a_edge[arcs[i]])
    names = [g.ref[a_prev] or g.name[a_prev], g.ref[a_next] or g.name[a_next]]
    names = [n for n in names if n]
    return " / ".join(dict.fromkeys(names)) + " junction" if names else f"junction {int(g.a_from[arcs[i]])}"


def window_dict(w: DecisionWindow) -> dict:
    def op(o: DiversionOption | None):
        if o is None:
            return None
        d = asdict(o)
        d.pop("arcs")
        for k, v in d.items():
            if isinstance(v, float) and not math.isfinite(v):
                d[k] = None
        return d
    out = asdict(w)
    out["options"] = [op(o) for o in w.options]
    out["pnr"] = op(w.pnr)
    for k in ("stay_net_rs", "stay_wastage_kg"):
        if isinstance(out[k], float) and not math.isfinite(out[k]):
            out[k] = None
    return out
