"""Hourly discrete-time simulation engine (project brief §7, deck S5/S8).

Per tick t (UTC hour): dispatch due lots → policy decisions for lots in transit → move trucks along time-varying
edges (congestion multipliers, disruptions) → age every active lot with the replayed temperature where it is →
spoilage (HEAT_ROT) and handling damage (CRUSHED) → arrivals at sinks → market trade during the morning window →
at window close, unsold lots may be redirected (proposed policy only) or expire → mass balance asserted.

Mass balance (every tick): injected = sold + donated + processed + wasted + in_market + in_transit.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
from scipy.sparse.csgraph import dijkstra

from app.core.config import commodities_config, thresholds
from app.domain.decay import CommodityProfile, DecayModel
from app.simulation.network import BusinessNode, Network
from app.simulation.policies import Decision, RoutingPolicy
from app.simulation.scenario import Lot, Scenario, ist_hour, sim_config


def day_ist(tick: float) -> int:
    return int(math.floor((tick + 5.5) / 24))


@dataclass
class LotState:
    lot: Lot
    qty: float
    age: float
    status: str = "pending"            # pending | transit | market | done
    dest: str | None = None
    path_edges: list[int] = field(default_factory=list)
    pos: int = 0
    cur_edge: int | None = None
    edge_left_s: float = 0.0
    edge_total_s: float = 0.0
    cur_node: int = -1
    origin_access_left_s: float = 0.0
    final_access_left_s: float = 0.0
    pending_route: tuple[str, list[int]] | None = None
    km: float = 0.0
    transit_s: float = 0.0
    arrival_tick: int | None = None
    sale_day: int | None = None
    sold: float = 0.0
    donated: float = 0.0
    processed: float = 0.0
    wasted: dict[str, float] = field(default_factory=lambda: {"HEAT_ROT": 0.0, "CRUSHED": 0.0, "UNSOLD": 0.0})
    reroutes: int = 0
    redirects: int = 0
    final_sink: str | None = None
    q_at_sink: float | None = None

    @property
    def wasted_total(self) -> float:
        return sum(self.wasted.values())


class TickContext:
    """What a policy may see at tick t: current (not future) travel times, temperature and market state."""

    def __init__(self, eng: Engine, t: int):
        self.eng, self.t = eng, t
        self._w: np.ndarray | None = None
        self._rev: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        self._csr_t = None
        self.saleable_min = eng.saleable_min
        self.processing_min = eng.processing_min

    @property
    def weights(self) -> np.ndarray:
        if self._w is None:
            self._w = self.eng.scen.weights(self.eng.net, self.t)
        return self._w

    def _reverse(self, sink_id: str) -> tuple[np.ndarray, np.ndarray]:
        if sink_id not in self._rev:
            g = self.eng.net.business[sink_id].gidx
            key = (self.t, sink_id)
            cached = self.eng.rev_cache.get(key)
            if cached is None:
                if self._csr_t is None:
                    self._csr_t = self.eng.net.csr(self.weights).T.tocsr()
                d, p = dijkstra(self._csr_t, directed=True, indices=g, return_predecessors=True)
                cached = (d, p)
                self.eng.rev_cache = {k: v for k, v in self.eng.rev_cache.items() if k[0] == self.t}
                self.eng.rev_cache[key] = cached
            self._rev[sink_id] = cached
        return self._rev[sink_id]

    def static_path(self, src: int, dest_id: str) -> tuple[list[int], float]:
        return self.eng.static_path(src, dest_id)

    def candidate_sinks(self, commodity: str) -> list[BusinessNode]:
        e = self.eng
        today = day_ist(self.t)
        mk = [m for m in e.markets if e.forecast(m.node_id, commodity, today) > 0 or e.forecast(m.node_id, commodity, today + 1) > 0]
        return mk + e.ngos + e.processors

    def sink_kind(self, node_id: str) -> str:
        return self.eng.kind[node_id]

    def route_now(self, ls: LotState, sink_id: str) -> tuple[float, list[int] | None]:
        e = self.eng
        if ls.cur_edge is not None and ls.edge_left_s > 0:
            src, offset = int(e.net.ev[ls.cur_edge]), ls.edge_left_s
        else:
            src, offset = ls.cur_node, 0.0
        d, succ = self._reverse(sink_id)
        if not np.isfinite(d[src]) or d[src] >= 1e8:
            return math.inf, None
        path = [src]
        target = e.net.business[sink_id].gidx
        while path[-1] != target:
            nxt = int(succ[path[-1]])
            if nxt < 0:
                return math.inf, None
            path.append(nxt)
        return float(d[src]) + offset + ls.origin_access_left_s + e.net.business[sink_id].access_s, path

    def predict_arrival(self, ls: LotState, hours: float, diurnal: bool = False) -> tuple[float, float, float, float]:
        """Predicted (quality, qty, temp_now, accel_now) after `hours`. Default: current temperature persists
        (pre-registered). `diurnal=True` (exploratory): hour k ahead uses the temperature observed 24 h earlier at
        the same hour and place, which is information a dispatcher has."""
        e = self.eng
        m = e.models[ls.lot.commodity]
        node = ls.cur_node if ls.cur_node >= 0 else e.net.business[ls.lot.origin].gidx
        dist = int(e.net.node_district[node])
        off = e.truck_offset if ls.status != "market" else 0.0
        temp = e.scen.temp(dist, self.t) + off
        acc = m.accel(temp)
        h = max(hours, 0.0)
        if diurnal and h > 0:
            whole = int(h)
            a1 = ls.age + sum(m.accel(e.scen.temp(dist, self.t - 24 + k) + off) for k in range(whole))
            a1 += (h - whole) * m.accel(e.scen.temp(dist, self.t - 24 + whole) + off)
        else:
            a1 = ls.age + acc * h
        f0, f1 = m.spoiled_fraction(ls.age), m.spoiled_fraction(a1)
        return 1.0 - f1, ls.qty * (1 - f1) / max(1e-9, 1 - f0), temp, acc

    def sale_day(self, eta_h: float) -> tuple[int, float]:
        e = self.eng
        ta = self.t + eta_h
        h = (ta + 5.5) % 24
        d = day_ist(ta)
        if e.win_start <= h < e.win_end:
            return d, 0.0
        if h < e.win_start:
            return d, e.win_start - h
        return d + 1, 24 - h + e.win_start

    def market_room(self, m: str, ls: LotState, day: int) -> float:
        e = self.eng
        c = ls.lot.commodity
        committed = sum(o.qty for o in e.active if o is not ls and o.dest == m and o.lot.commodity == c and o.sale_day == day)
        return max(0.0, e.forecast(m, c, day) - e.sold_mcd[(m, c, day)] - committed)

    def ngo_room(self, n: str, eta_h: float) -> float:
        e = self.eng
        d = day_ist(self.t + eta_h)
        committed = sum(o.qty for o in e.active if o.dest == n and o.status == "transit")
        return max(0.0, e.ngo_cap - e.donated_nd[(n, d)] - committed)


@dataclass
class RunResult:
    season: str
    seed: int
    policy: str
    metrics: dict
    per_commodity: dict
    lots: list[dict]
    events: list[dict]
    balance: list[dict]
    replay: list[list] | None
    notes: list[str]


class Engine:
    def __init__(self, net: Network, scen: Scenario, policy: RoutingPolicy, *, decay_mode: str = "fao_table1",
                 q10: float = 2.5, truck_offset: float | None = None, record_replay: bool = False):
        cfg = sim_config()
        th = thresholds().quality
        self.net, self.scen, self.policy = net, scen, policy
        self.saleable_min, self.processing_min = th.saleable_min, th.processing_min
        self.truck_offset = cfg["decay"]["truck_temp_offset_c"]["value"] if truck_offset is None else truck_offset
        sigma = cfg["decay"]["unit_variation_sigma"]["value"]
        self.models = {c: DecayModel(CommodityProfile.load(c), decay_mode, q10, sigma) for c in commodities_config().commodities}
        self.win_start = cfg["market"]["trade_window_ist"]["start"]
        self.win_end = cfg["market"]["trade_window_ist"]["end"]
        self.max_wait_h = 24 * cfg["market"]["max_wait_days"]["value"]
        self.ngo_cap = cfg["sinks"]["ngo_capacity_kg_day"]["value"]
        self.markets = sorted(net.by_type("ReceivingMarket"), key=lambda b: b.node_id)
        self.ngos = sorted(net.by_type("NGOSink"), key=lambda b: b.node_id)
        self.processors = sorted(net.by_type("ProcessingSink"), key=lambda b: b.node_id)
        self.kind = {b.node_id: "market" for b in self.markets} | {b.node_id: "ngo" for b in self.ngos} | \
            {b.node_id: "processing" for b in self.processors}
        self.static_cache: dict[tuple[int, str], tuple[list[int], float]] = {}
        self.rev_cache: dict = {}
        self.record_replay = record_replay
        self.sold_mcd: dict = defaultdict(float)
        self.donated_nd: dict = defaultdict(float)
        self.active: list[LotState] = []
        self.done: list[LotState] = []
        self.events: list[dict] = []
        self.balance: list[dict] = []
        self.replay: list[list] = []
        self.injected = 0.0
        self.unmet: dict = {}
        self.q_kg_at_sink = 0.0
        self.kg_at_sink = 0.0
        self._ff_csr = None
        self._hist = self._history()

    # ------------------------------------------------------------------ helpers
    def _history(self) -> dict:
        h: dict = defaultdict(dict)
        for (m, c, d), q in self.scen.demand.items():
            h[(m, c)][d] = q
        return h

    def forecast(self, m: str, c: str, day: int) -> float:
        """Persistence forecast the dispatcher could know: mean of the last 3 reported days strictly before `day`
        (the same Agmarknet series a crowd meter would show). Not the realised demand."""
        past = [q for d, q in sorted(self._hist.get((m, c), {}).items()) if d < day][-3:]
        return float(np.mean(past)) if past else 0.0

    def demand(self, m: str, c: str, day: int) -> float:
        return self.scen.demand.get((m, c, day), 0.0)

    def static_path(self, src: int, dest_id: str) -> tuple[list[int], float]:
        key = (src, dest_id)
        if key not in self.static_cache:
            if self._ff_csr is None:
                self._ff_csr = self.net.csr(self.net.ff_s)
            d, p = dijkstra(self._ff_csr, directed=True, indices=src, return_predecessors=True)
            for b in self.net.business.values():
                path = Network.path_from(p, src, b.gidx)
                if path:
                    self.static_cache[(src, b.node_id)] = (path, (float(d[b.gidx]) + b.access_s) / 3600)
        return self.static_cache[key]

    def _log(self, t: int, ls: LotState, event: str, **kw) -> None:
        self.events.append({"tick": t, "lot_id": ls.lot.lot_id, "commodity": ls.lot.commodity, "event": event,
                            "qty_kg": round(ls.qty, 3), "quality": round(1 - self.models[ls.lot.commodity].spoiled_fraction(ls.age), 4),
                            **kw})

    def quality(self, ls: LotState) -> float:
        return 1.0 - self.models[ls.lot.commodity].spoiled_fraction(ls.age)

    def _apply(self, t: int, ls: LotState, d: Decision, at_dispatch: bool) -> None:
        if d.action == "STAY":
            return
        changed = d.dest != ls.dest
        if d.action == "REROUTE" or (d.action == "ROUTE" and ls.dest is not None and changed):
            ls.reroutes += 1
        if d.action == "REDIRECT":
            ls.redirects += 1
        edges = self.net.path_edges(d.path)
        if ls.cur_edge is not None and ls.edge_left_s > 0:
            ls.pending_route = (d.dest, edges)
        else:
            ls.path_edges, ls.pos = edges, 0
            ls.cur_edge = None
        ls.dest = d.dest
        ls.final_access_left_s = self.net.business[d.dest].access_s
        if self.kind[d.dest] == "market":
            ls.sale_day = TickContext(self, t).sale_day(d.eta_h)[0]
        else:
            ls.sale_day = None
        self._log(t, ls, "DECISION", action=d.action, at_dispatch=at_dispatch, planned=ls.lot.planned_dest,
                  dest=d.dest, eta_h=round(d.eta_h, 2), reasons=" | ".join(d.reasons), expected=str(d.expected))

    # ------------------------------------------------------------------ physics
    def _age(self, t: int, ls: LotState) -> None:
        m = self.models[ls.lot.commodity]
        temp = self.scen.temp(int(self.net.node_district[ls.cur_node]), t) + (self.truck_offset if ls.status == "transit" else 0.0)
        a1 = ls.age + m.accel(temp)
        f0, f1 = m.spoiled_fraction(ls.age), m.spoiled_fraction(a1)
        spoil = ls.qty * (f1 - f0) / max(1e-12, 1 - f0)
        spoil = min(spoil, ls.qty)
        ls.qty -= spoil
        ls.wasted["HEAT_ROT"] += spoil
        ls.age = a1

    def _move(self, t: int, ls: LotState) -> None:
        budget = 3600.0
        net = self.net
        while budget > 1e-9 and ls.status == "transit":
            if ls.origin_access_left_s > 0:
                use = min(budget, ls.origin_access_left_s)
                ls.origin_access_left_s -= use
                budget -= use
                ls.transit_s += use
                continue
            if ls.cur_edge is None or ls.edge_left_s <= 0:
                if ls.cur_edge is not None:                      # finished an edge
                    ls.cur_node = int(net.ev[ls.cur_edge])
                    ls.cur_edge = None
                    if ls.pending_route is not None:
                        ls.dest, ls.path_edges = ls.pending_route
                        ls.pos, ls.pending_route = 0, None
                if ls.pos >= len(ls.path_edges):
                    if ls.final_access_left_s > 0:
                        use = min(budget, ls.final_access_left_s)
                        ls.final_access_left_s -= use
                        budget -= use
                        ls.transit_s += use
                        continue
                    self._arrive(t, ls)
                    return
                e = ls.path_edges[ls.pos]
                if self.scen.disrupted(e, t):                    # road closed now: wait (and age) where we are
                    ls.transit_s += budget
                    return
                ls.cur_edge = e
                ls.pos += 1
                ls.edge_left_s = float(net.ff_s[e] * self.scen.class_hour_mult[net.cls[e], min(t, self.scen.ticks - 1)]
                                       * self.scen.edge_factor[e])
                ls.edge_total_s = ls.edge_left_s
            use = min(budget, ls.edge_left_s)
            frac = use / ls.edge_total_s if ls.edge_total_s > 0 else 1.0
            km = float(net.length_m[ls.cur_edge]) * frac / 1000.0
            ls.km += km
            crush = min(ls.qty, ls.qty * self.models[ls.lot.commodity].profile.handling_per_100km * km / 100.0)
            ls.qty -= crush
            ls.wasted["CRUSHED"] += crush
            ls.edge_left_s -= use
            ls.transit_s += use
            budget -= use

    def _finish(self, t: int, ls: LotState, sink: str) -> None:
        ls.status, ls.final_sink = "done", sink
        self.active.remove(ls)
        self.done.append(ls)
        self._log(t, ls, "DONE", dest=sink, sold=round(ls.sold, 3), donated=round(ls.donated, 3),
                  processed=round(ls.processed, 3), wasted=round(ls.wasted_total, 3))

    def _dispose(self, ls: LotState, kind: str, kg: float) -> None:
        q = self.quality(ls)
        kg = min(kg, ls.qty)
        ls.qty -= kg
        if kind == "sold":
            ls.sold += kg
        elif kind == "donated":
            ls.donated += kg
        elif kind == "processed":
            ls.processed += kg
        if kg > 0:
            self.q_kg_at_sink += q * kg
            self.kg_at_sink += kg
            ls.q_at_sink = q

    def _arrive(self, t: int, ls: LotState) -> None:
        dest = ls.dest
        assert dest is not None, "a lot in transit always has a destination"
        ls.cur_node = self.net.business[dest].gidx
        ls.arrival_tick = t
        k = self.kind[dest]
        q = self.quality(ls)
        self._log(t, ls, "ARRIVE", dest=ls.dest, kind=k)
        if k == "market":
            ls.status = "market"
            return
        if k == "ngo":
            d = day_ist(t)
            if q >= self.saleable_min:
                give = min(ls.qty, max(0.0, self.ngo_cap - self.donated_nd[(ls.dest, d)]))
                self.donated_nd[(ls.dest, d)] += give
                self._dispose(ls, "donated", give)
            ls.wasted["UNSOLD"] += ls.qty
            ls.qty = 0.0
        else:  # processing
            if q >= self.processing_min:
                self._dispose(ls, "processed", ls.qty)
            ls.wasted["HEAT_ROT"] += ls.qty
            ls.qty = 0.0
        self._finish(t, ls, dest)

    def _trade(self, t: int) -> None:
        h = ist_hour(t)
        d = day_ist(t)
        if self.win_start <= h < self.win_end:
            for m in self.markets:
                queue = sorted((ls for ls in self.active if ls.status == "market" and ls.dest == m.node_id),
                               key=lambda x: (x.arrival_tick, x.lot.lot_id))
                for ls in queue:
                    c = ls.lot.commodity
                    room = self.demand(m.node_id, c, d) - self.sold_mcd[(m.node_id, c, d)]
                    if room <= 0 or self.quality(ls) < self.saleable_min:
                        continue
                    kg = min(ls.qty, room)
                    self.sold_mcd[(m.node_id, c, d)] += kg
                    self._dispose(ls, "sold", kg)
                    self._log(t, ls, "SOLD", dest=m.node_id, kg=round(kg, 3))
                    if ls.qty <= 1e-9:
                        self._finish(t, ls, m.node_id)
        if h == self.win_end:                                       # window just closed
            for m in self.markets:
                for c in commodities_config().commodities:
                    dem = self.demand(m.node_id, c, d)
                    if dem > 0 and 1 <= d < self.scen.days:
                        self.unmet[(m.node_id, c, d)] = max(0.0, dem - self.sold_mcd[(m.node_id, c, d)])
            ctx = TickContext(self, t)
            for ls in [x for x in self.active if x.status == "market"]:
                expired = t - (ls.arrival_tick or t) >= self.max_wait_h or self.quality(ls) < self.processing_min
                dec = None if expired else self.policy.unsold_after_window(ls, ctx)
                if dec is not None and dec.dest != ls.dest:
                    ls.status = "transit"
                    ls.cur_edge, ls.edge_left_s = None, 0.0
                    self._apply(t, ls, dec, at_dispatch=False)
                elif expired:
                    reason = "UNSOLD" if self.quality(ls) >= self.saleable_min else "HEAT_ROT"
                    ls.wasted[reason] += ls.qty
                    ls.qty = 0.0
                    self._finish(t, ls, ls.dest or "")

    # ------------------------------------------------------------------ main loop
    def run(self) -> RunResult:
        by_tick: dict[int, list[Lot]] = defaultdict(list)
        for lot in self.scen.lots:
            by_tick[lot.dispatch_tick].append(lot)
        for t in range(self.scen.ticks):
            ctx = TickContext(self, t)
            for lot in sorted(by_tick.get(t, []), key=lambda x: x.lot_id):
                origin = self.net.business[lot.origin]
                m = self.models[lot.commodity]
                age = 0.0                                          # harvest → dispatch ageing at origin temperatures
                for h in range(lot.harvest_lead_h):
                    age += m.accel(self.scen.temp(int(self.net.node_district[origin.gidx]), t - lot.harvest_lead_h + h))
                ls = LotState(lot, lot.qty_kg, age, status="transit", cur_node=origin.gidx,
                              origin_access_left_s=origin.access_s)
                self.injected += lot.qty_kg
                self.active.append(ls)
                self._log(t, ls, "DISPATCH", dest=lot.planned_dest, origin=lot.origin)
                self._apply(t, ls, self.policy.on_dispatch(ls, ctx), at_dispatch=True)
            for ls in [x for x in self.active if x.status == "transit"]:
                if ls.dest is not None and ls.lot.dispatch_tick != t:
                    dec = self.policy.in_transit(ls, ctx)
                    if dec is not None and dec.dest != ls.dest:
                        self._apply(t, ls, dec, at_dispatch=False)
            for ls in [x for x in self.active if x.status == "transit"]:
                self._move(t, ls)
            for ls in [x for x in self.active if x.status in ("transit", "market")]:
                self._age(t, ls)
                if ls.qty <= 1e-9:
                    ls.qty = 0.0
                    self._finish(t, ls, ls.dest or "spoiled")
            self._trade(t)
            self._check_balance(t)
            if self.record_replay:
                self.replay.append([t] + [[ls.lot.lot_id, round(float(self.net.y[ls.cur_node]), 5),
                                           round(float(self.net.x[ls.cur_node]), 5), ls.status, ls.dest, ls.lot.commodity,
                                           round(self.quality(ls), 3)] for ls in self.active])
        return self._result()

    def _check_balance(self, t: int) -> None:
        allls = self.active + self.done
        sold = sum(x.sold for x in allls)
        don = sum(x.donated for x in allls)
        proc = sum(x.processed for x in allls)
        waste = sum(x.wasted_total for x in allls)
        in_market = sum(x.qty for x in self.active if x.status == "market")
        in_transit = sum(x.qty for x in self.active if x.status == "transit")
        err = self.injected - (sold + don + proc + waste + in_market + in_transit)
        row = {"tick": t, "injected": self.injected, "sold": sold, "donated": don, "processed": proc, "wasted": waste,
               "in_market": in_market, "in_transit": in_transit, "error_kg": err}
        self.balance.append(row)
        if abs(err) > 1e-6 * max(1.0, self.injected):
            raise AssertionError(f"mass balance broken at tick {t}: {row}")
        if any(x.qty < -1e-9 for x in allls):
            raise AssertionError(f"negative quantity at tick {t}")

    def _result(self) -> RunResult:
        allls = self.done + self.active
        inj = self.injected
        demand_total = sum(q for (m, c, d), q in self.scen.demand.items() if 1 <= d < self.scen.days)
        unmet_total = sum(self.unmet.values())
        waste = sum(x.wasted_total for x in allls)
        metrics = {
            "injected_kg": inj, "sold_kg": sum(x.sold for x in allls), "donated_kg": sum(x.donated for x in allls),
            "processed_kg": sum(x.processed for x in allls), "wasted_kg": waste,
            "wasted_heat_kg": sum(x.wasted["HEAT_ROT"] for x in allls), "wasted_crushed_kg": sum(x.wasted["CRUSHED"] for x in allls),
            "wasted_unsold_kg": sum(x.wasted["UNSOLD"] for x in allls),
            "unresolved_kg": sum(x.qty for x in self.active),
            "wastage_rate": waste / inj if inj else float("nan"),
            "demand_kg": demand_total, "unmet_demand_kg": unmet_total,
            "unmet_demand_rate": unmet_total / demand_total if demand_total else float("nan"),
            "mean_quality_at_sink": self.q_kg_at_sink / self.kg_at_sink if self.kg_at_sink else float("nan"),
            "mean_travel_h_per_lot": float(np.mean([x.transit_s / 3600 for x in allls])) if allls else float("nan"),
            "total_km": sum(x.km for x in allls),
            "reroute_count": sum(x.reroutes for x in allls), "redirect_count": sum(x.redirects for x in allls),
            "lots": len(allls), "max_abs_balance_error_kg": max(abs(b["error_kg"]) for b in self.balance) if self.balance else 0.0,
        }
        per_c: dict = {}
        for c in commodities_config().commodities:
            xs = [x for x in allls if x.lot.commodity == c]
            i = sum(x.lot.qty_kg for x in xs)
            w = sum(x.wasted_total for x in xs)
            per_c[c] = {"injected_kg": i, "wasted_kg": w, "wastage_rate": w / i if i else None, "lots": len(xs)}
        lots = [{"lot_id": x.lot.lot_id, "commodity": x.lot.commodity, "origin": x.lot.origin, "planned_dest": x.lot.planned_dest,
                 "final_sink": x.final_sink or x.dest, "status": x.status, "qty_initial_kg": x.lot.qty_kg, "sold_kg": x.sold,
                 "donated_kg": x.donated, "processed_kg": x.processed, "wasted_heat_kg": x.wasted["HEAT_ROT"],
                 "wasted_crushed_kg": x.wasted["CRUSHED"], "wasted_unsold_kg": x.wasted["UNSOLD"], "remaining_kg": x.qty,
                 "km": x.km, "transit_h": x.transit_s / 3600, "reroutes": x.reroutes, "redirects": x.redirects,
                 "q_at_sink": x.q_at_sink} for x in sorted(allls, key=lambda z: z.lot.lot_id)]
        return RunResult(self.scen.season, self.scen.seed, self.policy.name, metrics, per_c, lots, self.events,
                         self.balance, self.replay if self.record_replay else None, self.scen.notes + self.net.notes)
