import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { CROPS } from "../data/crops";
import { decay, eaFromQ10, kRef, Q_MIN, rate, sellableFraction } from "./arrhenius";
import { buildGraph } from "./graph";
import { dijkstra, pathTo } from "./router";
import { Sim } from "./sim";

describe("arrhenius", () => {
  it("reaches Q_MIN at the reference shelf life and temperature", () => {
    for (const c of Object.values(CROPS)) {
      const k = rate(c, c.refTempC, c.rhOpt, eaFromQ10(2.5));
      expect(k).toBeCloseTo(kRef(c), 12);
      expect(decay(1, k, c.refLifeH)).toBeCloseTo(Q_MIN, 9);
    }
  });

  it("multiplies k by ~Q10 for +10 °C around 20 °C", () => {
    const c = CROPS.tomato;
    for (const q10 of [2, 2.5, 3]) {
      const ea = eaFromQ10(q10);
      expect(rate(c, 30, c.rhOpt, ea) / rate(c, 20, c.rhOpt, ea)).toBeCloseTo(q10, 6);
    }
  });

  it("sellable fraction falls monotonically with quality", () => {
    const c = CROPS.tomato;
    let prev = 1.01;
    for (let q = 0.95; q > 0.4; q -= 0.05) {
      const s = sellableFraction(c, q);
      expect(s).toBeLessThanOrEqual(prev);
      prev = s;
    }
    expect(sellableFraction(c, Q_MIN)).toBeCloseTo(0.5, 6);
  });
});

describe("router", () => {
  it("matches brute force on a small graph", () => {
    // 0-1 (1), 1-3 (1), 0-2 (1), 2-3 (5), 0-3 (4)
    const g = buildGraph({
      nodes: [0, 0, 1, 0, 0, 1, 1, 1],
      edges: [0, 1, 1000, 0, 1, 3, 1000, 0, 0, 2, 1000, 0, 2, 3, 5000, 0, 0, 3, 4000, 0],
      geoms: [[0, 0, 1, 0], [1, 0, 1, 1], [0, 0, 0, 1], [0, 1, 1, 1], [0, 0, 1, 1]],
      classes: ["motorway"], attribution: "",
    });
    const tree = dijkstra(g, 0, g.lenKm);
    expect(tree.dist[3]).toBeCloseTo(2, 6);
    expect(pathTo(g, tree, 3)!.map((s) => s.e)).toEqual([0, 1]);
    expect(pathTo(g, dijkstra(g, 3, g.lenKm), 0)!.map((s) => [s.e, s.fwd])).toEqual([[1, false], [0, false]]);
  });
});

describe("simulation on the Nagpur graph", () => {
  const g = buildGraph(JSON.parse(readFileSync(new URL("../../public/graph.json", import.meta.url), "utf8")));
  const run = (setup: (s: Sim) => void, midTrip?: (s: Sim) => void) => {
    const s = new Sim(g);
    setup(s);
    for (let i = 0; i < 400 && !s.trucks.every((t) => t.done); i++) {
      s.step(0.05);
      if (i === 6 && midTrip) midTrip(s);
    }
    return s;
  };
  const summary = (s: Sim) => s.trucks.map((t) => `${t.id}:${t.buyer}:${Math.round(t.done!.sellFrac * 100)}%:${t.done!.hours.toFixed(1)}h`).join("  ");

  it("delivers all six trucks in calm weather", () => {
    const s = run(() => {});
    expect(s.trucks.every((t) => t.done)).toBe(true);
    console.log("calm     ", summary(s), s.kpis().foodSavedKg.toFixed(0));
  });

  it("heatwave mid-trip makes the smart policy save food", () => {
    const s = run(() => {}, (x) => x.setEnv({ ambientC: 46, rh: 30 }));
    const k = s.kpis();
    console.log("heatwave ", summary(s), k.foodSavedKg.toFixed(0), k.reroutes);
    expect(k.foodSavedKg).toBeGreaterThan(0);
  });

  it("flood on NH-44 at Jamtha reroutes", () => {
    const s = run(() => {}, (x) => x.setEnv({ rain: 0.6, cells: [{ id: 1, kind: "storm", lon: 79.02, lat: 21.04, radiusKm: 10 }] }));
    const k = s.kpis();
    console.log("flood    ", summary(s), k.foodSavedKg.toFixed(0), k.reroutes, s.events.filter((e) => e.kind === "reroute").map((e) => e.text));
    expect(k.reroutes).toBeGreaterThan(0);
  });
});
