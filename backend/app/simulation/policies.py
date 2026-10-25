"""Routing policies (deck S5). Both implement `RoutingPolicy`; the engine is identical for both, so the policy is the
only difference between paired runs.

Decision outputs: ROUTE (path & ETA), REROUTE (alternate market), REDIRECT (processing / NGO sink). Every decision
carries human-readable reasons and the numbers behind them (explainability; humans decide in the real product).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.simulation.engine import LotState, TickContext

VALUE_WEIGHT = {"market": 1.0, "ngo": 0.9, "processing": 0.6}   # ASSUMPTION A29: relative value of each outcome


@dataclass
class Decision:
    action: str                    # ROUTE | REROUTE | REDIRECT | STAY
    dest: str
    path: list[int]
    eta_h: float
    reasons: list[str] = field(default_factory=list)
    expected: dict = field(default_factory=dict)


class RoutingPolicy(Protocol):
    name: str

    def on_dispatch(self, ls: LotState, ctx: TickContext) -> Decision: ...

    def in_transit(self, ls: LotState, ctx: TickContext) -> Decision | None: ...

    def unsold_after_window(self, ls: LotState, ctx: TickContext) -> Decision | None: ...


class StaticShortestPath:
    """Baseline: go to the planned market on the static free-flow shortest path. Never reroutes or redirects."""
    name = "StaticShortestPath"

    def on_dispatch(self, ls: LotState, ctx: TickContext) -> Decision:
        path, eta = ctx.static_path(ls.cur_node, ls.lot.planned_dest)
        return Decision("ROUTE", ls.lot.planned_dest, path, eta, ["static free-flow shortest path to the planned market"])

    def in_transit(self, ls: LotState, ctx: TickContext) -> Decision | None:
        return None

    def unsold_after_window(self, ls: LotState, ctx: TickContext) -> Decision | None:
        return None


class QualityAwareDynamic:
    """Proposed: evaluates every market and redirect sink with *current* travel times (congestion, disruptions),
    *current* temperature, the lot's quality, and how much has already been sold/committed at each market today.
    Switches only if the expected value improves by more than `margin` (no flapping)."""
    name = "QualityAwareDynamic"

    def __init__(self, margin: float = 0.10, diurnal: bool = False):
        self.margin = margin
        self.diurnal = diurnal          # exploratory variant (post-hoc): forecast temperature from yesterday's same hours
        if diurnal:
            self.name = "QualityAwareDynamic+diurnal"

    def _options(self, ls: LotState, ctx: TickContext) -> list[dict]:
        opts = []
        for sink in ctx.candidate_sinks(ls.lot.commodity):
            dist, path = ctx.route_now(ls, sink.node_id)
            if path is None:
                continue
            eta_h = dist / 3600.0
            q_arr, qty_arr, temp_now, accel = ctx.predict_arrival(ls, eta_h, self.diurnal)
            kind = ctx.sink_kind(sink.node_id)
            if kind == "market":
                sale_day, wait_h = ctx.sale_day(eta_h)
                q_sale, qty_sale, _, _ = ctx.predict_arrival(ls, eta_h + wait_h, self.diurnal)
                room = ctx.market_room(sink.node_id, ls, sale_day)
                ok = q_sale >= ctx.saleable_min
                value = VALUE_WEIGHT["market"] * (min(qty_sale, room) if ok else 0.0)
                why = (f"{sink.name}: arrive in {eta_h:.1f} h, quality at sale {q_sale:.2f}, "
                       f"room for ~{room / 1000:.1f} t (forecast demand minus sold and in-flight)")
            elif kind == "ngo":
                cap = ctx.ngo_room(sink.node_id, eta_h)
                ok = q_arr >= ctx.saleable_min and cap > 0
                value = VALUE_WEIGHT["ngo"] * (min(qty_arr, cap) if ok else 0.0)
                why = f"{sink.name} (NGO): arrive in {eta_h:.1f} h, quality {q_arr:.2f}, capacity left {cap / 1000:.1f} t"
            else:
                ok = q_arr >= ctx.processing_min
                value = VALUE_WEIGHT["processing"] * (qty_arr if ok else 0.0)
                why = f"{sink.name} (processing): arrive in {eta_h:.1f} h, quality {q_arr:.2f}"
            opts.append({"dest": sink.node_id, "kind": kind, "path": path, "eta_h": eta_h, "value": value,
                         "q_arr": q_arr, "temp_now": temp_now, "accel": accel, "why": why})
        return opts

    def _choose(self, ls: LotState, ctx: TickContext, current: str | None) -> Decision | None:
        opts = self._options(ls, ctx)
        if not opts:
            return None
        best = max(opts, key=lambda o: (o["value"], -o["eta_h"]))
        cur = next((o for o in opts if o["dest"] == current), None)
        heat = f"Temperature now {best['temp_now']:.0f} °C: produce ages {best['accel']:.1f}× the reference rate"
        if cur is not None and (best["dest"] == current or best["value"] <= cur["value"] * (1 + self.margin)
                                or best["value"] - cur["value"] < 1.0):
            return Decision("STAY", current or best["dest"], cur["path"], cur["eta_h"], [cur["why"], heat],
                            {"value": cur["value"]})
        action = "REDIRECT" if best["kind"] != "market" else ("ROUTE" if current is None else "REROUTE")
        reasons = [best["why"], heat]
        if cur is not None:
            reasons.insert(0, f"Current plan ({cur['why']}) is worth ~{cur['value'] / 1000:.1f} t; "
                              f"best option is worth ~{best['value'] / 1000:.1f} t")
        return Decision(action, best["dest"], best["path"], best["eta_h"], reasons,
                        {"value": best["value"], "q_arr": best["q_arr"],
                         "alternatives": sorted(((o["dest"], round(o["value"])) for o in opts), key=lambda x: -x[1])[:4]})

    def on_dispatch(self, ls: LotState, ctx: TickContext) -> Decision:
        d = self._choose(ls, ctx, ls.lot.planned_dest)
        if d is None:                                          # nothing reachable: fall back to the plan
            path, eta = ctx.static_path(ls.cur_node, ls.lot.planned_dest)
            return Decision("ROUTE", ls.lot.planned_dest, path, eta, ["no evaluable option; planned market"])
        if d.action == "STAY":
            d.action = "ROUTE"
        return d

    def in_transit(self, ls: LotState, ctx: TickContext) -> Decision | None:
        d = self._choose(ls, ctx, ls.dest)
        return d

    def unsold_after_window(self, ls: LotState, ctx: TickContext) -> Decision | None:
        d = self._choose(ls, ctx, ls.dest)
        if d is None or d.action == "STAY":
            return None
        return d


def make_policy(name: str, **kw) -> RoutingPolicy:
    if name == "StaticShortestPath":
        return StaticShortestPath()
    if name == "QualityAwareDynamic":
        return QualityAwareDynamic(**kw)
    raise ValueError(name)
