import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, streamEvents } from "../../lib/api";
import { useSession } from "../../lib/session";
import { hours, pct, weight } from "../../lib/format";
import { MapView, type MapDot } from "../../components/MapView";
import { Button, Card, ErrorBox, Field, HowCalculated, inputCls, Loading, PageTitle, ProvenanceBadge, Stat } from "../../components/ui";
import { DotPlot, LineChart } from "./Charts";
import { useNodes } from "../lots/Lots";

const SIM_LABEL = "Simulation output, not field-validated";

// ---------------------------------------------------------------- M7 Route advisor
export function Advisor() {
  const { t } = useTranslation();
  const { user, meta, serverNow } = useSession();
  const origins = useNodes("AssemblyMandi,ReceivingMarket");
  const markets = useNodes("ReceivingMarket");
  const [form, setForm] = useState({ origin_node_id: user?.home_node_id ?? "", commodity: "tomato", qty_kg: "3000", harvest_h_ago: "20", planned_dest_id: "" });
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function compare(e: React.FormEvent) {
    e.preventDefault(); setErr(null); setBusy(true);
    try {
      setRes(await api("/advisor/compare", { body: {
        origin_node_id: form.origin_node_id, commodity: form.commodity, qty_kg: Number(form.qty_kg),
        harvest_time: new Date(serverNow() - Number(form.harvest_h_ago) * 3600e3).toISOString(), planned_dest_id: form.planned_dest_id || null } }));
    } catch (e2) { setErr(e2); setRes(null); } finally { setBusy(false); }
  }
  const lines = res ? [
    { id: "b", coords: res.baseline.geometry, color: "series-1" as const, width: 5 },
    { id: "r", coords: res.recommended.geometry, color: "series-2" as const, width: 4 },
  ] : [];
  return (
    <>
      <PageTitle sub="Compare the usual route with a quality-aware option. The app recommends; you decide.">{t("advisor.title")}</PageTitle>
      <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
        <Card>
          <form className="space-y-3" onSubmit={compare}>
            <Field label="From">{(id) => <select id={id} className={inputCls} required value={form.origin_node_id} onChange={(e) => setForm({ ...form, origin_node_id: e.target.value })}>
              <option value="" disabled>Select…</option>{origins.map((n) => <option key={n.node_id} value={n.node_id}>{n.name}</option>)}</select>}</Field>
            <Field label={t("lot.commodity")}>{(id) => <select id={id} className={inputCls} value={form.commodity} onChange={(e) => setForm({ ...form, commodity: e.target.value })}>
              {Object.entries(meta?.commodities ?? {}).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>}</Field>
            <Field label={t("lot.qty")}>{(id) => <input id={id} className={inputCls} type="number" min={1} value={form.qty_kg} onChange={(e) => setForm({ ...form, qty_kg: e.target.value })} />}</Field>
            <Field label="Hours since harvest">{(id) => <input id={id} className={inputCls} type="number" min={0} max={240} value={form.harvest_h_ago} onChange={(e) => setForm({ ...form, harvest_h_ago: e.target.value })} />}</Field>
            <Field label="Planned market (optional)">{(id) => <select id={id} className={inputCls} value={form.planned_dest_id} onChange={(e) => setForm({ ...form, planned_dest_id: e.target.value })}>
              <option value="">Nearest market with data</option>{markets.map((n) => <option key={n.node_id} value={n.node_id}>{n.name}</option>)}</select>}</Field>
            <Button type="submit" busy={busy} className="w-full">{t("advisor.compare")}</Button>
          </form>
        </Card>
        <div className="space-y-3">
          {err ? <ErrorBox error={err} /> : null}
          <MapView height={340} lines={lines} />
          {res ? (
            <>
              <div className={`rounded-xl p-3 font-semibold ${res.action === "ROUTE" ? "bg-good-soft text-good" : "bg-warn-soft text-warn"}`} data-testid="advisor-action">
                Recommendation: {res.action === "ROUTE" ? "keep the planned market" : res.action === "REROUTE" ? `reroute to ${res.recommended.dest_name}` : `redirect to ${res.recommended.dest_name} (${res.recommended.kind})`}
              </div>
              {res.alerts.map((a: string) => <p key={a} className="rounded-lg bg-bad-soft p-2 text-sm text-bad">⚠ {a}</p>)}
              <div className="grid gap-3 sm:grid-cols-2">
                {[["Usual route (static, free-flow)", res.baseline, "series-1"], ["Suggested", res.recommended, "series-2"]].map(([label, o, c]: any) => (
                  <div key={label} className="card border-l-4 p-3" style={{ borderLeftColor: `var(--${c})` }}>
                    <b>{label}</b><div className="text-sm">{o.dest_name} · {hours(o.eta_h)} · {o.km} km</div>
                    <div className="text-sm">Quality on arrival {o.quality_at_arrival} (Q10 2–3: {o.quality_bounds.q10_2}–{o.quality_bounds.q10_3}) · ~{weight(o.qty_at_arrival_kg)} left</div>
                    {o.crowd ? <div className="text-xs text-muted">Crowd: {o.crowd.label}</div> : null}
                  </div>
                ))}
              </div>
              <Card title="Why">
                <ul className="list-disc space-y-1 pl-5 text-sm">{res.reasons.map((r: string) => <li key={r}>{r}</li>)}</ul>
                <HowCalculated>
                  <ul className="list-disc pl-5">{Object.entries(res.inputs).map(([k, v]) => <li key={k}><b>{k}</b>: {typeof v === "object" ? JSON.stringify(v) : String(v)}</li>)}</ul>
                  <p className="mt-2">{res.uncertainty}</p>
                </HowCalculated>
                <p className="mt-2 text-sm font-semibold">{res.guardrail}</p>
                <p className="text-xs text-muted">{res.label}. In simulation, this kind of policy cut waste in hot seasons but raised unmet demand (see Simulation lab).</p>
              </Card>
            </>
          ) : null}
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------- Simulation Lab
export function Lab() {
  const [tab, setTab] = useState<"results" | "replay" | "live">("results");
  return (
    <>
      <PageTitle sub={<>Baseline (static shortest path) vs proposed (quality-aware dynamic), same inputs, only the policy differs. <b>{SIM_LABEL}.</b></>}>Simulation lab</PageTitle>
      <div role="tablist" className="mb-4 flex gap-2 overflow-x-auto">
        {([["results", "Pre-registered results"], ["replay", "Replay on map"], ["live", "Live run"]] as const).map(([k, l]) => (
          <Button key={k} role="tab" aria-selected={tab === k} variant={tab === k ? "primary" : "secondary"} onClick={() => setTab(k)}>{l}</Button>
        ))}
      </div>
      {tab === "results" ? <Results /> : tab === "replay" ? <Replay /> : <Live />}
    </>
  );
}

function Results() {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  const [table, setTable] = useState(false);
  useEffect(() => { api("/sim/results").then(setData).catch(setErr); }, []);
  if (err) return <ErrorBox error={err} />;
  if (!data) return <Loading />;
  if (!data.primary) return <p>No results yet. Run <code>python tasks.py experiments</code>.</p>;
  const runs = data.primary.runs as any[];
  const seasons = [...new Set(runs.map((r) => r.season))];
  const groups = (m: string) => seasons.map((s) => ({ label: s[0].toUpperCase() + s.slice(1),
    baseline: runs.filter((r) => r.season === s && r.policy === "StaticShortestPath").map((r) => r[m]),
    proposed: runs.filter((r) => r.season === s && r.policy !== "StaticShortestPath").map((r) => r[m]) }));
  const paired = (data.primary.paired as any[]).filter((p) => ["wastage_rate", "unmet_demand_rate"].includes(p.metric));
  return (
    <div className="space-y-4">
      <Card title="Verdict (pre-registered decision rule)">
        <ul className="space-y-1">
          {data.primary.summary.verdicts.map((v: any) => (
            <li key={v.season} className={v.beats_baseline ? "text-good" : "text-bad"}>
              <b className="capitalize">{v.season}</b>: proposed {v.beats_baseline ? "beats" : "does not beat"} the baseline on both primary metrics
              {v.n_failures ? ` · worse on a primary metric in ${v.n_failures} of ${data.primary.summary.seeds.length} seeds` : ""}
            </li>
          ))}
        </ul>
        <p className="mt-2 text-sm text-muted">Registered {data.primary.summary.preregistration_commit}. Rule: the 95% paired bootstrap CI must be below 0 for both wastage rate and unmet-demand rate.</p>
      </Card>
      <Card><DotPlot title="Wastage rate per seed (dots) and mean (bar)" groups={groups("wastage_rate")} /></Card>
      <Card><DotPlot title="Unmet-demand rate per seed (dots) and mean (bar)" groups={groups("unmet_demand_rate")} /></Card>
      <Card title="Numbers" action={<Button variant="secondary" onClick={() => setTable(!table)}>{table ? "Hide table" : "Show table"}</Button>}>
        {table ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead><tr><th>Season</th><th>Metric</th><th>Baseline</th><th>Proposed</th><th>Diff [95% CI]</th></tr></thead>
              <tbody>{paired.map((p) => (
                <tr key={p.season + p.metric} className="border-t border-line"><td>{p.season}</td><td>{p.metric}</td><td>{pct(p.baseline_mean)}</td><td>{pct(p.proposed_mean)}</td>
                  <td>{(p.mean_diff * 100).toFixed(2)} pp [{(p.ci95_lo * 100).toFixed(2)}, {(p.ci95_hi * 100).toFixed(2)}]</td></tr>
              ))}</tbody>
            </table>
          </div>
        ) : <p className="text-sm text-muted">Means, spreads and confidence intervals for every pre-registered metric, plus sensitivity and exploratory runs, are in the full report.</p>}
        {data.report ? <a className="mt-2 inline-block font-semibold text-brand underline" href={data.report} target="_blank" rel="noreferrer">Open the full simulation report</a> : null}
      </Card>
      <Card title="What this means">
        <p className="text-sm">In this model the quality-aware policy wastes less produce in summer and monsoon, but sends much of it to processing,
          so markets get less and unmet demand rises. In winter it is worse on both. Sensitivity runs (Q10 2 and 3, hotter trucks, oversupply) and
          post-hoc variants show the same trade-off. Tomato losses in the model are about 7 times the national market-level figure, so absolute
          levels are uncertain; the decay parameters need field data.</p>
      </Card>
    </div>
  );
}

function Replay() {
  const [policy, setPolicy] = useState<"StaticShortestPath" | "QualityAwareDynamic">("QualityAwareDynamic");
  const [data, setData] = useState<Record<string, any>>({});
  const [tick, setTick] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  useEffect(() => {
    for (const p of ["StaticShortestPath", "QualityAwareDynamic"]) {
      api(`/sim/replay/replay__summer__101__${p}.json`).then((d) => setData((x) => ({ ...x, [p]: d }))).catch(setErr);
    }
  }, []);
  const cur = data[policy];
  const n = cur?.ticks.length ?? 0;
  useEffect(() => {
    if (!playing || !n) return;
    const i = setInterval(() => setTick((t) => (t + 1) % n), 250);
    return () => clearInterval(i);
  }, [playing, n]);
  if (err) return <ErrorBox error={err} />;
  if (!cur) return <Loading />;
  const row = cur.ticks[Math.min(tick, n - 1)];
  const dots: MapDot[] = row.slice(1).filter((x: any) => x[3] === "transit").map((x: any) => ({ lat: x[1], lon: x[2], color: policy === "StaticShortestPath" ? "series-1" : "series-2" }));
  const atMarket = row.slice(1).filter((x: any) => x[3] === "market").length;
  return (
    <div className="space-y-3">
      <p className="text-sm">Registered run: summer 2026, seed 101. <ProvenanceBadge p="SYNTHETIC_DEMO" /> lots on real roads and weather. {SIM_LABEL}.</p>
      <div className="flex flex-wrap gap-2">
        <Button variant={policy === "StaticShortestPath" ? "primary" : "secondary"} onClick={() => setPolicy("StaticShortestPath")}>Baseline</Button>
        <Button variant={policy === "QualityAwareDynamic" ? "primary" : "secondary"} onClick={() => setPolicy("QualityAwareDynamic")}>Proposed</Button>
        <Button variant="secondary" onClick={() => setPlaying(!playing)}>{playing ? "⏸ Pause" : "▶ Play"}</Button>
      </div>
      <MapView height={380} dots={dots} showRoads />
      <label className="block text-sm font-semibold" htmlFor="scrub">Time: hour {tick} of {n - 1} ({dots.length} trucks moving, {atMarket} lots waiting at markets)</label>
      <input id="scrub" type="range" className="big" min={0} max={n - 1} value={tick} onChange={(e) => setTick(+e.target.value)} />
    </div>
  );
}

function Live() {
  const { serverNow } = useSession();
  const [start, setStart] = useState("2026-05-01");
  const [days, setDays] = useState("3");
  const [seed, setSeed] = useState("7");
  const [head, setHead] = useState<any>(null);
  const [ticks, setTicks] = useState<any[]>([]);
  const [end, setEnd] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  const [running, setRunning] = useState(false);
  const abort = useRef<AbortController | null>(null);
  useEffect(() => () => abort.current?.abort(), []);
  async function go() {
    abort.current?.abort();
    const ac = new AbortController();
    abort.current = ac;
    setHead(null); setTicks([]); setEnd(null); setErr(null); setRunning(true);
    try {
      await streamEvents(`/sim/live?start=${start}&days=${days}&seed=${seed}&pace_ms=40`, (e) => {
        if (e.type === "start") setHead(e);
        else if (e.type === "tick") setTicks((t) => [...t, e]);
        else if (e.type === "end") setEnd(e);
      }, ac.signal);
    } catch (e) { if ((e as Error).name !== "AbortError") setErr(e); } finally { setRunning(false); }
  }
  const last = ticks[ticks.length - 1];
  const series = useMemo(() => [
    { key: "b", label: "Baseline: static", color: "series-1" as const, points: ticks.map((t) => ({ x: t.tick, y: t.baseline.wastage_rate })) },
    { key: "p", label: "Proposed: quality-aware", color: "series-2" as const, points: ticks.map((t) => ({ x: t.tick, y: t.proposed.wastage_rate })) },
  ], [ticks]);
  const unmet = useMemo(() => [
    { key: "b", label: "Baseline: static", color: "series-1" as const, points: ticks.map((t) => ({ x: t.tick, y: t.baseline.unmet_demand_rate })) },
    { key: "p", label: "Proposed: quality-aware", color: "series-2" as const, points: ticks.map((t) => ({ x: t.tick, y: t.proposed.unmet_demand_rate })) },
  ], [ticks]);
  const dots: MapDot[] = last ? [
    ...last.baseline_trucks.map((x: any) => ({ lat: x[0], lon: x[1], color: "series-1" as const })),
    ...last.proposed_trucks.map((x: any) => ({ lat: x[0], lon: x[1], color: "series-2" as const })),
  ] : [];
  void serverNow;
  return (
    <div className="space-y-3">
      <Card>
        <form className="grid gap-3 sm:grid-cols-4" onSubmit={(e) => { e.preventDefault(); void go(); }}>
          <Field label="Start (UTC date)">{(id) => <input id={id} className={inputCls} type="date" min="2025-11-09" max="2026-10-08" value={start} onChange={(e) => setStart(e.target.value)} />}</Field>
          <Field label="Days (2–7)">{(id) => <input id={id} className={inputCls} type="number" min={2} max={7} value={days} onChange={(e) => setDays(e.target.value)} />}</Field>
          <Field label="Seed">{(id) => <input id={id} className={inputCls} type="number" min={0} value={seed} onChange={(e) => setSeed(e.target.value)} />}</Field>
          <div className="flex items-end gap-2">
            <Button type="submit" busy={running} className="w-full" data-testid="live-start">▶ Run live</Button>
            {running ? <Button type="button" variant="secondary" onClick={() => abort.current?.abort()}>Stop</Button> : null}
          </div>
        </form>
        <p className="mt-2 text-xs text-muted">{head?.label ?? "Both policies advance hour by hour on identical inputs. This is a live exploratory run, separate from the pre-registered experiment."}</p>
      </Card>
      {err ? <ErrorBox error={err} /> : null}
      {last ? (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" aria-live="polite">
            <Stat label="Wastage so far: baseline" value={pct(last.baseline.wastage_rate)} sub={weight(last.baseline.wasted_kg)} />
            <Stat label="Wastage so far: proposed" value={pct(last.proposed.wastage_rate)} sub={weight(last.proposed.wasted_kg)} />
            <Stat label="Unmet demand: baseline" value={pct(last.baseline.unmet_demand_rate)} />
            <Stat label="Unmet demand: proposed" value={pct(last.proposed.unmet_demand_rate)} sub={`${last.proposed.reroutes} reroutes · ${last.proposed.redirects} redirects`} />
          </div>
          <Card><LineChart title="Cumulative wastage rate (wasted ÷ dispatched)" series={series} xLabel="hour" /></Card>
          <Card><LineChart title="Unmet-demand rate (closed market days)" series={unmet} xLabel="hour" /></Card>
          <MapView height={340} dots={dots} showRoads />
          <p className="text-xs text-muted">Hour {last.tick} of {head?.ticks}. Blue = baseline trucks, orange = proposed trucks. Mass balance error this hour: {Math.abs(last.baseline.balance_error_kg).toExponential(1)} / {Math.abs(last.proposed.balance_error_kg).toExponential(1)} kg. {SIM_LABEL}.</p>
        </>
      ) : running ? <Loading /> : null}
      {end ? (
        <Card title="Final (this live run)">
          <table className="w-full text-left text-sm"><thead><tr><th>Metric</th><th>Baseline</th><th>Proposed</th></tr></thead><tbody>
            {["wastage_rate", "unmet_demand_rate", "mean_quality_at_sink"].map((k) => <tr key={k} className="border-t border-line"><td>{k}</td><td>{pct(end.baseline[k])}</td><td>{pct(end.proposed[k])}</td></tr>)}
            {["sold_kg", "donated_kg", "processed_kg", "wasted_kg"].map((k) => <tr key={k} className="border-t border-line"><td>{k}</td><td>{weight(end.baseline[k])}</td><td>{weight(end.proposed[k])}</td></tr>)}
          </tbody></table>
        </Card>
      ) : null}
    </div>
  );
}
