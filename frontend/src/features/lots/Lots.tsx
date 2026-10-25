import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, ApiError } from "../../lib/api";
import { enqueue, newEventId } from "../../lib/offline";
import { useSession } from "../../lib/session";
import { hours, ist, weight } from "../../lib/format";
import { QRScanner } from "../../components/QRScanner";
import { MapView } from "../../components/MapView";
import { Button, Card, Empty, ErrorBox, Field, HowCalculated, inputCls, Loading, PageTitle, ProvenanceBadge, TrafficLight } from "../../components/ui";

export type Lot = { id: string; short_code: string; commodity: string; grade: string; initial_qty_kg: number; current_qty_kg: number;
  sold_kg: number; donated_kg: number; processed_kg: number; wasted_kg: number; unreconciled_kg: number; quality_score: number;
  harvest_time: string; dispatch_time: string | null; origin_node_id: string; at_node_id: string | null; in_transit_to: string | null;
  status: string; chain_count: number; provenance: string };
type Node = { node_id: string; node_type: string; name: string; lat: number | null; lon: number | null; district: string | null; provenance: string; needs_review: boolean };

export function useNodes(type?: string) {
  const [nodes, setNodes] = useState<Node[]>([]);
  useEffect(() => { void api<Node[]>(`/nodes${type ? `?type=${type}` : ""}`).then(setNodes).catch(() => setNodes([])); }, [type]);
  return nodes;
}

function useUnitTick() {
  const [, set] = useState(0);
  useEffect(() => { const f = () => set((x) => x + 1); window.addEventListener("phl-unit", f); return () => window.removeEventListener("phl-unit", f); }, []);
}

const STATUS_LABEL: Record<string, string> = { AT_NODE: "At location", IN_TRANSIT: "In transit", DISPUTED_WEIGHT: "Weight disputed", CLOSED: "Closed" };

export function LotList() {
  const { t } = useTranslation();
  useUnitTick();
  const [lots, setLots] = useState<Lot[] | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const load = useCallback(() => { setErr(null); api<Lot[]>("/consignments").then(setLots).catch(setErr); }, []);
  useEffect(load, [load]);
  return (
    <>
      <PageTitle sub="Lots you created or that are at or heading to your location">{t("nav.lots")}</PageTitle>
      {err ? <ErrorBox error={err} retry={load} /> : null}
      {!lots ? <Loading /> : lots.length === 0 ? (
        <Empty title={t("empty.lots")} action={<Link to="/lots/new"><Button>{t("lot.create")}</Button></Link>} />
      ) : (
        <ul className="space-y-2">
          {lots.map((l) => (
            <li key={l.id}>
              <Link to={`/lots/${l.id}`} className="card tap flex items-center justify-between gap-3 p-3">
                <span>
                  <span className="font-semibold capitalize">{l.commodity}</span> <span className="font-mono text-sm text-muted">{l.short_code}</span>
                  <span className="block text-sm text-muted">{weight(l.current_qty_kg)} · {STATUS_LABEL[l.status] ?? l.status}</span>
                </span>
                <ProvenanceBadge p={l.provenance} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export function NewLot() {
  const { t } = useTranslation();
  const { user, meta, serverNow } = useSession();
  const nodes = useNodes();
  const [form, setForm] = useState({ commodity: "tomato", grade: "A", qty_kg: "", harvest_time: "", origin_node_id: user?.home_node_id ?? "" });
  const [made, setMade] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const d = new Date(serverNow() - 6 * 3600e3 + 5.5 * 3600e3);
    setForm((f) => ({ ...f, harvest_time: f.harvest_time || d.toISOString().slice(0, 16) }));
  }, [serverNow]);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setErr(null); setBusy(true);
    try {
      // the picker shows IST; convert back to UTC
      const utc = new Date(new Date(`${form.harvest_time}:00Z`).getTime() - 5.5 * 3600e3).toISOString();
      setMade(await api("/consignments", { body: { ...form, qty_kg: Number(form.qty_kg), harvest_time: utc, client_event_id: newEventId() } }));
    } catch (e) { setErr(e); } finally { setBusy(false); }
  }
  if (made) {
    const c: Lot = made.consignment;
    return (
      <Card title={t("lot.created")} action={<ProvenanceBadge p={c.provenance} />}>
        <div className="flex flex-col items-center gap-3 text-center print:break-inside-avoid" data-testid="lot-label">
          <img src={made.qr_png} alt={`QR code for lot ${c.short_code}`} className="size-56 rounded-lg bg-white p-2" />
          <div className="font-mono text-2xl tracking-widest">{c.short_code}</div>
          <div className="rounded-xl bg-warn-soft px-4 py-2 text-warn">
            PIN <b className="font-mono text-2xl tracking-widest" data-testid="lot-pin">{made.pin}</b>
            <div className="text-sm">{t("lot.pinOnce")}</div>
          </div>
          <div className="text-sm text-muted"><span className="capitalize">{c.commodity}</span> · {weight(c.initial_qty_kg)} · harvested {ist(c.harvest_time)}</div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => window.print()}>🖨 {t("lot.print")}</Button>
          <Link to={`/lots/${c.id}`}><Button>Open lot</Button></Link>
        </div>
      </Card>
    );
  }
  return (
    <>
      <PageTitle>{t("lot.create")}</PageTitle>
      <Card>
        <form className="space-y-4" onSubmit={submit}>
          {err ? <ErrorBox error={err} /> : null}
          <fieldset>
            <legend className="mb-2 font-semibold">{t("lot.commodity")}</legend>
            <div className="grid grid-cols-3 gap-2">
              {Object.entries(meta?.commodities ?? {}).map(([k, label]) => (
                <button type="button" key={k} onClick={() => setForm({ ...form, commodity: k })} aria-pressed={form.commodity === k}
                  className={`tap rounded-xl border p-2 text-center font-semibold ${form.commodity === k ? "border-brand bg-brand-soft text-brand" : "border-line"}`}>
                  <span className="block text-2xl" aria-hidden>{k === "tomato" ? "🍅" : k === "onion" ? "🧅" : "🍊"}</span>{label}
                </button>
              ))}
            </div>
          </fieldset>
          <Field label={t("lot.qty")}>{(id) => <input id={id} className={inputCls} inputMode="decimal" type="number" min={1} max={100000} step="any" required value={form.qty_kg} onChange={(e) => setForm({ ...form, qty_kg: e.target.value })} />}</Field>
          <Field label={t("lot.grade")}>{(id) => <select id={id} className={inputCls} value={form.grade} onChange={(e) => setForm({ ...form, grade: e.target.value })}><option>A</option><option>B</option><option>C</option></select>}</Field>
          <Field label={`${t("lot.harvest")} (IST)`}>{(id) => <input id={id} className={inputCls} type="datetime-local" required value={form.harvest_time} onChange={(e) => setForm({ ...form, harvest_time: e.target.value })} />}</Field>
          <Field label={t("lot.origin")}>
            {(id) => <select id={id} className={inputCls} required value={form.origin_node_id} onChange={(e) => setForm({ ...form, origin_node_id: e.target.value })}>
              <option value="" disabled>Select…</option>
              {nodes.map((n) => <option key={n.node_id} value={n.node_id}>{n.name} · {n.node_type}{n.provenance === "SYNTHETIC_DEMO" ? " (DEMO)" : ""}</option>)}
            </select>}
          </Field>
          <Button type="submit" busy={busy} className="w-full">{t("lot.create")}</Button>
        </form>
      </Card>
    </>
  );
}

export function Scan() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const [err, setErr] = useState<unknown>(null);
  async function byCode(code: string) {
    try { const c = await api<Lot>(`/consignments/by-code/${encodeURIComponent(code)}`); nav(`/lots/${c.id}`); } catch (e) { setErr(e); }
  }
  async function manual(code: string, pin: string) {
    try { const c = await api<Lot>("/consignments/pin-lookup", { body: { short_code: code, pin } }); nav(`/lots/${c.id}`); } catch (e) { setErr(e); }
  }
  return (
    <>
      <PageTitle sub="Scan the QR label. If the camera is not available, type the code and PIN.">{t("scan.title")}</PageTitle>
      {err ? <div className="mb-3"><ErrorBox error={err} /></div> : null}
      <Card><QRScanner onCode={byCode} onManual={manual} /></Card>
    </>
  );
}

export function LotDetail() {
  const { id } = useParams();
  const { t } = useTranslation();
  useUnitTick();
  const { user, toast, online, serverNow } = useSession();
  const [lot, setLot] = useState<Lot | null>(null);
  const [tl, setTl] = useState<any>(null);
  const [sl, setSl] = useState<any>(null);
  const [handovers, setHandovers] = useState<any[]>([]);
  const [err, setErr] = useState<unknown>(null);
  const load = useCallback(async () => {
    setErr(null);
    try {
      const l = await api<Lot>(`/consignments/${id}`);
      setLot(l);
      setTl(await api(`/consignments/${id}/timeline`));
      if (l.status !== "CLOSED") setSl(await api(`/consignments/${id}/shelf-life`).catch(() => null));
      setHandovers((await api<any[]>("/handovers")).filter((h) => h.consignment_id === id));
    } catch (e) { setErr(e); }
  }, [id]);
  useEffect(() => { void load(); }, [load]);
  if (err) return <ErrorBox error={err} retry={load} />;
  if (!lot || !tl) return <Loading rows={4} />;
  const holder = user?.home_node_id && lot.at_node_id === user.home_node_id;
  const receiving = handovers.find((h) => h.to_node === user?.home_node_id);
  return (
    <div className="space-y-4">
      <PageTitle sub={<span className="font-mono">{lot.short_code}</span>}>
        <span className="capitalize">{lot.commodity}</span> · {weight(lot.current_qty_kg)} <ProvenanceBadge p={lot.provenance} className="align-middle" />
      </PageTitle>
      {lot.status === "DISPUTED_WEIGHT" ? <p className="rounded-xl bg-warn-soft p-3 text-warn" role="alert">⚠ {t("handover.disputed")} ({weight(lot.unreconciled_kg)})</p> : null}
      {sl ? (
        <Card title="Shelf life" action={<TrafficLight light={sl.light} hours={sl.remaining_life_h} />}>
          <p>{sl.explanation.why}</p>
          <ShelfExplain sl={sl} />
        </Card>
      ) : null}
      <div className="grid gap-4 md:grid-cols-2">
        {holder && lot.status !== "CLOSED" ? <HandoverForm lot={lot} onDone={load} /> : null}
        {receiving ? <ConfirmForm h={receiving} onDone={load} /> : null}
        {holder && ["SUPERVISOR", "WAREHOUSE", "ADMIN"].includes(user?.role ?? "") && lot.status !== "IN_TRANSIT" && lot.current_qty_kg > 0 ? (
          <WastageLogger lot={lot} onDone={load} />
        ) : null}
        {user?.role === "TRANSPORTER" && lot.status === "IN_TRANSIT" ? (
          <Card title="Driver scan">
            <Button onClick={async () => {
              const payload = { scan_time: new Date(serverNow()).toISOString(), client_event_id: newEventId() };
              if (!online) { await enqueue({ op: "transit_scan", consignment_id: lot.id, client_event_id: payload.client_event_id, payload, label: `scan ${lot.short_code}` }); toast("Saved offline. Will sync later."); return; }
              try { await api(`/consignments/${lot.id}/scan`, { body: payload }); toast("Scan recorded", { tone: "good" }); void load(); } catch (e) { toast((e as Error).message, { tone: "bad" }); }
            }}>📍 Record sighting</Button>
          </Card>
        ) : null}
      </div>
      <Card title="Journey" action={<span className={`text-sm font-semibold ${tl.chain.ok ? "text-good" : "text-bad"}`}>{tl.chain.ok ? "✔ Tamper-evident log verifies" : "✖ Log does not verify"}</span>}>
        {tl.path.length ? <MapView height={260} lines={[{ id: "path", coords: tl.path.map((p: any) => [p.lat, p.lon]), color: "brand" }]}
          points={tl.path.map((p: any, i: number) => ({ id: String(i), lat: p.lat, lon: p.lon, label: p.event_type, kind: "ReceivingMarket" }))} /> : null}
        <p className="mt-2 text-xs text-muted">Path drawn only from actual scans; no hops are inferred.</p>
        <ol className="mt-3 space-y-2">
          {tl.events.map((e: any) => (
            <li key={e.seq} className="rounded-xl border border-line p-3 text-sm">
              <div className="flex justify-between gap-2"><b>{e.event_type.replace("_", " ")}</b><span className="text-muted">{ist(e.scan_time_utc)}</span></div>
              <div>{e.from_name ? `${e.from_name} → ` : ""}{e.to_name ?? ""}</div>
              <div className="text-muted">
                {e.weight_released_kg != null ? `sent ${weight(e.weight_released_kg)} ` : ""}{e.weight_received_kg != null ? `received ${weight(e.weight_received_kg)} ` : ""}
                {e.condition_released ?? e.condition_received ?? ""} {e.note ?? ""}
              </div>
              <div className="font-mono text-xs text-muted">#{e.hash} · synced {ist(e.sync_time_utc)}</div>
            </li>
          ))}
        </ol>
      </Card>
      <Card title="Where the produce went">
        <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
          {[["In this lot", lot.current_qty_kg], ["Sold", lot.sold_kg], ["Donated", lot.donated_kg], ["Processed", lot.processed_kg], ["Wasted", lot.wasted_kg], ["Disputed (not waste)", lot.unreconciled_kg]].map(([k, v]) => (
            <div key={k as string} className="rounded-lg bg-surface-3 p-2"><dt className="text-muted">{k}</dt><dd className="font-semibold tabular-nums">{weight(v as number)}</dd></div>
          ))}
        </dl>
        <p className="mt-2 text-xs text-muted">Mass balance {tl.mass_balance.holds ? "holds" : "does NOT hold"}: started with {weight(lot.initial_qty_kg)}.</p>
      </Card>
    </div>
  );
}

function ShelfExplain({ sl }: { sl: any }) {
  const ex = sl.explanation;
  return (
    <HowCalculated title="Why this colour">
      <p className="mb-2">{ex.why}</p>
      <h3 className="mt-3 font-semibold">Inputs</h3>
      <ul className="list-disc pl-5">
        <li>Hours since harvest: {ex.inputs.elapsed_since_harvest_h}</li>
        <li>Mean temperature so far: {ex.inputs.temperature_history.mean_c ?? "–"} °C <ProvenanceBadge p={ex.inputs.temperature_history.provenance} /></li>
        <li>Mean temperature next {sl.horizon_h} h: {ex.inputs.temperature_next.mean_c ?? "–"} °C <ProvenanceBadge p={ex.inputs.temperature_next.provenance} /></li>
        <li>Quality score now: {ex.inputs.quality_score}</li>
      </ul>
      <h3 className="mt-3 font-semibold">Parameters</h3>
      <ul className="list-disc pl-5">
        <li>Reference life: {ex.parameters.reference_life_h} h at {ex.parameters.reference_temp_c} °C. Source: {ex.parameters.reference_source}</li>
        <li>Temperature curve: {ex.parameters.temperature_curve}</li>
        <li>Spread between units in a lot: σ = {ex.parameters.unit_variation_sigma} <ProvenanceBadge p="ASSUMPTION" /></li>
        <li>Range with Q10 = 2 / 3: {hours(sl.sensitivity.remaining_life_h_q10_2)} / {hours(sl.sensitivity.remaining_life_h_q10_3)}</li>
        <li>Thresholds: {ex.thresholds.status}</li>
      </ul>
      <h3 className="mt-3 font-semibold">Warnings</h3>
      <ul className="list-disc pl-5">{ex.warnings.map((w: string) => <li key={w}>{w}</li>)}</ul>
      <p className="mt-3 rounded-lg bg-warn-soft p-2 text-warn">{ex.disclaimer}</p>
    </HowCalculated>
  );
}

const CONDITIONS = ["GOOD", "MINOR_DAMAGE", "MAJOR_DAMAGE", "WET", "OVERRIPE"];

function HandoverForm({ lot, onDone }: { lot: Lot; onDone: () => void }) {
  const { t } = useTranslation();
  const { toast, online, serverNow } = useSession();
  const nodes = useNodes();
  const [to, setTo] = useState("");
  const [kg, setKg] = useState(String(Math.round(lot.current_qty_kg)));
  const [cond, setCond] = useState("GOOD");
  const [busy, setBusy] = useState(false);
  async function send(e: React.FormEvent) {
    e.preventDefault(); setBusy(true);
    const payload = { to_node_id: to, weight_kg: Number(kg), condition: cond, scan_time: new Date(serverNow()).toISOString(), client_event_id: newEventId() };
    try {
      if (!online) throw new ApiError(0, "offline", "offline");
      await api(`/consignments/${lot.id}/handovers`, { body: payload });
      toast("Handed over. The receiver must confirm.", { tone: "good" });
      onDone();
    } catch (err) {
      if (err instanceof ApiError && err.code === "offline") {
        await enqueue({ op: "handover_start", consignment_id: lot.id, client_event_id: payload.client_event_id, payload, label: `handover ${lot.short_code}` });
        toast("Saved offline with the real scan time. It will sync when you are back online.");
      } else toast((err as Error).message, { tone: "bad" });
    } finally { setBusy(false); }
  }
  return (
    <Card title={t("handover.send")}>
      <form className="space-y-3" onSubmit={send}>
        <Field label={t("handover.to")}>{(id) => <select id={id} className={inputCls} required value={to} onChange={(e) => setTo(e.target.value)}>
          <option value="" disabled>Select…</option>
          {nodes.filter((n) => n.node_id !== lot.at_node_id).map((n) => <option key={n.node_id} value={n.node_id}>{n.name} · {n.node_type}{n.provenance === "SYNTHETIC_DEMO" ? " (DEMO)" : ""}</option>)}
        </select>}</Field>
        <Field label={t("handover.weight")}>{(id) => <input id={id} className={inputCls} type="number" inputMode="decimal" min={0.1} step="any" required value={kg} onChange={(e) => setKg(e.target.value)} />}</Field>
        <Field label={t("handover.condition")}>{(id) => <select id={id} className={inputCls} value={cond} onChange={(e) => setCond(e.target.value)}>{CONDITIONS.map((c) => <option key={c} value={c}>{t(`cond.${c}`)}</option>)}</select>}</Field>
        <Button type="submit" busy={busy} className="w-full">{t("handover.send")}</Button>
      </form>
    </Card>
  );
}

function ConfirmForm({ h, onDone }: { h: any; onDone: () => void }) {
  const { t } = useTranslation();
  const { toast, online, serverNow } = useSession();
  const [kg, setKg] = useState(String(h.weight_released_kg));
  const [cond, setCond] = useState("GOOD");
  const [busy, setBusy] = useState(false);
  async function confirm(e: React.FormEvent) {
    e.preventDefault(); setBusy(true);
    const payload = { weight_kg: Number(kg), condition: cond, scan_time: new Date(serverNow()).toISOString(), client_event_id: newEventId() };
    try {
      if (!online) throw new ApiError(0, "offline", "offline");
      const r = await api(`/handovers/${h.id}/confirm`, { body: payload });
      toast(r.status === "DISPUTED_WEIGHT" ? t("handover.disputed") : "Receipt confirmed", { tone: r.status === "DISPUTED_WEIGHT" ? "bad" : "good" });
      onDone();
    } catch (err) {
      if (err instanceof ApiError && err.code === "offline") {
        await enqueue({ op: "handover_confirm", handover_id: h.id, client_event_id: payload.client_event_id, payload, label: "confirm receipt" });
        toast("Saved offline. It will sync later.");
      } else toast((err as Error).message, { tone: "bad" });
    } finally { setBusy(false); }
  }
  return (
    <Card title={t("handover.receive")}>
      <p className="mb-3 text-sm">Sender declared <b>{weight(h.weight_released_kg)}</b>, condition {t(`cond.${h.condition_released}`)}. Weigh it and check it.</p>
      <form className="space-y-3" onSubmit={confirm}>
        <Field label={t("handover.weight")}>{(id) => <input id={id} className={inputCls} type="number" inputMode="decimal" min={0} step="any" required value={kg} onChange={(e) => setKg(e.target.value)} />}</Field>
        <Field label={t("handover.condition")}>{(id) => <select id={id} className={inputCls} value={cond} onChange={(e) => setCond(e.target.value)}>{CONDITIONS.map((c) => <option key={c} value={c}>{t(`cond.${c}`)}</option>)}</select>}</Field>
        <Button type="submit" busy={busy} className="w-full">{t("handover.receive")}</Button>
      </form>
    </Card>
  );
}

const REASONS: { code: string; icon: string }[] = [
  { code: "HEAT_ROT", icon: "☀️" }, { code: "CRUSHED", icon: "📦" }, { code: "WET", icon: "🌧️" }, { code: "UNSOLD", icon: "📉" },
];

export function WastageLogger({ lot, onDone }: { lot: Lot; onDone: () => void }) {
  const { t } = useTranslation();
  const { toast, online } = useSession();
  const max = Math.floor(lot.current_qty_kg);
  const [kg, setKg] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  async function log(reason: string) {
    if (kg <= 0) return;
    setBusy(reason);
    const payload = { amount_kg: kg, reason_code: reason, client_event_id: newEventId() };
    try {
      if (!online) throw new ApiError(0, "offline", "offline");
      const r = await api(`/consignments/${lot.id}/wastage`, { body: payload });
      setKg(0);
      onDone();
      toast(t("waste.saved", { kg: weight(payload.amount_kg), reason: t(`waste.${reason}`) }), {
        tone: "good",
        undo: async () => { try { await api(`/wastage/${r.event.id}/undo`, { method: "POST" }); toast("Undone"); onDone(); } catch (e) { toast((e as Error).message, { tone: "bad" }); } },
      });
    } catch (err) {
      if (err instanceof ApiError && err.code === "offline") {
        await enqueue({ op: "wastage", consignment_id: lot.id, client_event_id: payload.client_event_id, payload, label: `wastage ${kg} kg` });
        toast("Saved offline. It will sync later.");
        setKg(0);
      } else toast((err as Error).message, { tone: "bad" });
    } finally { setBusy(null); }
  }
  return (
    <Card title={t("waste.title")}>
      <label htmlFor="waste-slider" className="font-semibold">{t("waste.howMuch")}</label>
      <input id="waste-slider" type="range" className="big my-3" min={0} max={max} step={Math.max(1, Math.round(max / 100))}
        value={kg} onChange={(e) => setKg(Math.min(max, Number(e.target.value)))} aria-valuetext={`${kg} kg`} />
      <div className="mb-3 flex items-center justify-between">
        <span className="text-3xl font-bold tabular-nums" data-testid="waste-kg">{kg} kg</span>
        <span className="text-sm text-muted">max {weight(max)}</span>
      </div>
      <p className="mb-2 font-semibold">{t("waste.why")}</p>
      <div className="grid grid-cols-2 gap-2">
        {REASONS.map((r) => (
          <Button key={r.code} variant="secondary" disabled={kg <= 0} busy={busy === r.code} className="h-24 flex-col text-base"
            onClick={() => void log(r.code)} data-reason={r.code}>
            <span className="text-3xl" aria-hidden>{r.icon}</span>{t(`waste.${r.code}`)}
          </Button>
        ))}
      </div>
      <p className="mt-2 text-xs text-muted">Wet and Unsold are recorded only; the shelf-life model does not use them yet. Unsold lots can be offered to NGOs.</p>
    </Card>
  );
}
