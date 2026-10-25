import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../../lib/api";
import { useSession } from "../../lib/session";
import { countdown, hours, weight } from "../../lib/format";
import { MapView } from "../../components/MapView";
import { Button, Card, Empty, ErrorBox, Field, HowCalculated, inputCls, Loading, PageTitle, ProvenanceBadge, TrafficLight } from "../../components/ui";

// ---------------------------------------------------------------- M3 storage
export function Storage() {
  const { t } = useTranslation();
  const { user } = useSession();
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  const load = useCallback(() => {
    if (!user?.home_node_id) return;
    setErr(null);
    api(`/storage/${user.home_node_id}/batches`).then(setData).catch(setErr);
  }, [user]);
  useEffect(load, [load]);
  if (!user?.home_node_id) return <Empty title="No location on your profile">Storage needs a home location.</Empty>;
  return (
    <>
      <PageTitle sub={data ? `${data.node.name} · ${data.order}` : undefined}>{t("storage.title")}</PageTitle>
      {err ? <ErrorBox error={err} retry={load} /> : null}
      {!data ? <Loading /> : data.batches.length === 0 ? <Empty title="No lots stored here right now." /> : (
        <ol className="space-y-2" aria-label="Dispatch order, first expiring first">
          {data.batches.map((b: any, i: number) => (
            <li key={b.consignment_id} className="card p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Link to={`/lots/${b.consignment_id}`} className="font-semibold">
                  <span className="mr-2 inline-flex size-7 items-center justify-center rounded-full bg-surface-3 text-sm" aria-label={`Position ${i + 1}`}>{i + 1}</span>
                  <span className="capitalize">{b.commodity}</span> <span className="font-mono text-sm text-muted">{b.short_code}</span>
                </Link>
                <TrafficLight light={b.light} hours={b.remaining_life_h} />
              </div>
              <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-sm text-muted">
                <span>{weight(b.qty_kg)} · {b.hours_since_harvest} h since harvest · expected loss next {b.horizon_h} h: {weight(b.expected_loss_next_h_kg)}</span>
                <ProvenanceBadge p={b.provenance} />
              </div>
              <HowCalculated title="Why this colour">
                <p>{b.explanation.why}</p>
                <ul className="mt-2 list-disc pl-5">
                  <li>Temperature so far {b.explanation.inputs.temperature_history.mean_c} °C ({b.explanation.inputs.temperature_history.provenance}); next {b.explanation.inputs.temperature_next.mean_c} °C ({b.explanation.inputs.temperature_next.provenance})</li>
                  <li>Reference life {b.explanation.parameters.reference_life_h} h at {b.explanation.parameters.reference_temp_c} °C: {b.explanation.parameters.reference_source}</li>
                  <li>Range under Q10 2/3: {hours(b.sensitivity.remaining_life_h_q10_2)} / {hours(b.sensitivity.remaining_life_h_q10_3)}</li>
                  {b.explanation.warnings.map((w: string) => <li key={w}>{w}</li>)}
                </ul>
                <p className="mt-2 text-warn">{b.explanation.disclaimer}</p>
              </HowCalculated>
            </li>
          ))}
        </ol>
      )}
      <p className="mt-3 text-sm text-muted">{data?.thresholds_note}</p>
    </>
  );
}

// ---------------------------------------------------------------- M4 crowd meter
const CROWD_STYLE: Record<string, string> = {
  GLUT_WARNING: "bg-bad-soft text-bad", BUSY: "bg-warn-soft text-warn", NORMAL: "bg-good-soft text-good",
  STALE: "bg-surface-3 text-muted", NO_BASELINE: "bg-surface-3 text-muted",
};
const CROWD_ICON: Record<string, string> = { GLUT_WARNING: "▲▲", BUSY: "▲", NORMAL: "●", STALE: "○", NO_BASELINE: "○" };

export function Crowd() {
  const { t } = useTranslation();
  const { meta, user, serverNow } = useSession();
  const [commodity, setCommodity] = useState("tomato");
  const [on, setOn] = useState(() => new Date(serverNow() + 5.5 * 3600e3).toISOString().slice(0, 10));
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  useEffect(() => {
    setData(null); setErr(null);
    const q = new URLSearchParams({ commodity, on, ...(user?.home_node_id ? { origin_node_id: user.home_node_id } : {}) });
    api(`/crowd?${q}`).then(setData).catch(setErr);
  }, [commodity, on, user]);
  return (
    <>
      <PageTitle sub={data?.definition}>{t("crowd.title")}</PageTitle>
      <div className="mb-3 flex flex-wrap gap-2">
        {Object.entries(meta?.commodities ?? {}).map(([k, l]) => (
          <Button key={k} variant={commodity === k ? "primary" : "secondary"} onClick={() => setCommodity(k)}>{l}</Button>
        ))}
        <input type="date" className={`${inputCls} w-auto`} value={on} onChange={(e) => setOn(e.target.value)} aria-label="Date" min="2025-11-07" max="2026-10-25" />
      </div>
      {err ? <ErrorBox error={err} /> : null}
      {!data ? <Loading /> : (
        <>
          <MapView height={300} points={data.markets.filter((m: any) => m.lat).map((m: any) => ({ id: m.node_id, lat: m.lat, lon: m.lon, label: `${m.market}: ${m.label}`, kind: "ReceivingMarket", provenance: m.provenance }))} />
          {data.markets.length === 0 ? <Empty title="No market reported arrivals for this produce." >Data unavailable: shown as no data, never guessed.</Empty> : (
            <ul className="mt-3 space-y-2">
              {data.markets.map((m: any) => (
                <li key={m.node_id} className="card p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <b>{m.market}</b>
                    <span className={`rounded-lg px-2 py-1 text-sm font-semibold ${CROWD_STYLE[m.status] ?? ""}`}>
                      <span aria-hidden>{CROWD_ICON[m.status]} </span>{m.status === "GLUT_WARNING" ? "Glut warning" : m.status === "BUSY" ? "Busy" : m.status === "NORMAL" ? "Normal" : "No recent data"}
                    </span>
                  </div>
                  <p className="text-sm">{m.label}{m.today_kg != null ? ` · today ${weight(m.today_kg)} vs usual ${weight(m.trailing_median_kg)}` : ""}</p>
                  <p className="text-xs text-muted">Last reported {m.last_reported ?? "never"} · {m.road_time_h != null ? `${hours(m.road_time_h)} from you (free-flow model)` : "road time unknown"}{!m.routable ? " · location under review" : ""}</p>
                  {m.alternates?.length ? (
                    <p className="mt-1 text-sm">Less crowded nearby: {m.alternates.map((a: any) => `${a.market} (${Math.round(a.ratio * 100)}% of usual, ${hours(a.road_time_h_from_this_market)} away)`).join(" · ")}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-sm text-muted">{data.note} {data.markets_without_data} markets in the division have no reported arrivals for this produce. Glut threshold 130% of usual is an assumption.</p>
        </>
      )}
    </>
  );
}

// ---------------------------------------------------------------- M5/M6 rescue
export function Rescue() {
  const { user } = useSession();
  if (user?.role === "NGO") return <NgoRescue />;
  return <SenderRescue />;
}

function NgoRescue() {
  const { t } = useTranslation();
  const { toast, serverNow, meta } = useSession();
  const [offers, setOffers] = useState<any[] | null>(null);
  const [, tick] = useState(0);
  const [err, setErr] = useState<unknown>(null);
  const load = useCallback(() => { api<any[]>("/rescue/offers").then(setOffers).catch(setErr); }, []);
  useEffect(() => { load(); const i = setInterval(() => { tick((x) => x + 1); }, 30000); const j = setInterval(load, 20000); return () => { clearInterval(i); clearInterval(j); }; }, [load]);
  return (
    <>
      <PageTitle sub="Offers from lots that are about to spoil or did not sell. Claim fast: the first NGO to claim gets it.">{t("rescue.title")}</PageTitle>
      <NgoProfileCard commodities={meta?.commodities ?? {}} />
      {err ? <ErrorBox error={err} retry={load} /> : null}
      {!offers ? <Loading /> : offers.length === 0 ? <Empty title="No offers right now">You will get a notification when produce is offered nearby.</Empty> : (
        <ul className="space-y-3">
          {offers.map((o) => (
            <li key={o.id} className="card p-4">
              <div className="flex items-center justify-between gap-2"><b className="capitalize">{weight(o.qty_kg)} {o.commodity}</b><ProvenanceBadge p={o.provenance} /></div>
              <p className="text-sm">From {o.from_name} · {hours(o.road_time_h)} away · safe window ~{hours(o.safe_window_h)}</p>
              <p className="text-xs text-warn">{o.disclaimer}</p>
              {o.status === "OFFERED" ? (
                <div className="mt-2 flex items-center justify-between gap-2">
                  <span className="text-sm text-muted">Offer ends in {countdown(o.offer_expires_at, serverNow())}</span>
                  <Button data-testid="claim" onClick={async () => { try { await api(`/rescue/offers/${o.id}/claim`, { method: "POST" }); toast("Claimed. Collect it and scan the label at pickup.", { tone: "good" }); load(); } catch (e) { toast((e as Error).message, { tone: "bad" }); load(); } }}>{t("rescue.claim")}</Button>
                </div>
              ) : (
                <p className="mt-2 rounded-lg bg-good-soft p-2 text-good">Claimed. Pickup timer: <b data-testid="claim-timer">{countdown(o.claim_expires_at, serverNow())}</b>. Lot code {o.short_code}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function NgoProfileCard({ commodities }: { commodities: Record<string, string> }) {
  const { toast } = useSession();
  const [accepts, setAccepts] = useState<string[]>(Object.keys(commodities));
  const [cap, setCap] = useState("2000");
  const [from, setFrom] = useState("7");
  const [to, setTo] = useState("20");
  const [open, setOpen] = useState(false);
  return (
    <Card title="What you can take" className="mb-4" action={<Button variant="ghost" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? "Close" : "Edit"}</Button>}>
      {open ? (
        <form className="space-y-3" onSubmit={async (e) => { e.preventDefault(); try { await api("/ngo/profile", { method: "PUT", body: { accepted_commodities: accepts, daily_capacity_kg: Number(cap), pickup_start_ist: Number(from), pickup_end_ist: Number(to) } }); toast("Profile saved", { tone: "good" }); setOpen(false); } catch (err) { toast((err as Error).message, { tone: "bad" }); } }}>
          <div className="flex flex-wrap gap-2">{Object.entries(commodities).map(([k, l]) => (
            <label key={k} className="tap flex items-center gap-2 rounded-xl border border-line px-3"><input type="checkbox" className="size-5" checked={accepts.includes(k)} onChange={(e) => setAccepts((a) => e.target.checked ? [...a, k] : a.filter((x) => x !== k))} />{l}</label>
          ))}</div>
          <Field label="Daily capacity (kg)">{(id) => <input id={id} className={inputCls} type="number" min={1} value={cap} onChange={(e) => setCap(e.target.value)} />}</Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Pickup from (hour, IST)">{(id) => <input id={id} className={inputCls} type="number" min={0} max={23} value={from} onChange={(e) => setFrom(e.target.value)} />}</Field>
            <Field label="Pickup until (hour, IST)">{(id) => <input id={id} className={inputCls} type="number" min={1} max={24} value={to} onChange={(e) => setTo(e.target.value)} />}</Field>
          </div>
          <Button type="submit">Save</Button>
        </form>
      ) : <p className="text-sm text-muted">Senders only offer you produce you accept, within your capacity and pickup hours.</p>}
    </Card>
  );
}

function SenderRescue() {
  const { t } = useTranslation();
  const { toast, serverNow } = useSession();
  const [lots, setLots] = useState<any[] | null>(null);
  const [bcasts, setB] = useState<any[]>([]);
  const [matches, setMatches] = useState<Record<string, any>>({});
  const load = useCallback(async () => {
    try {
      setLots((await api<any[]>("/consignments")).filter((l) => l.status === "AT_NODE"));
      setB(await api<any[]>("/rescue/broadcasts"));
    } catch { setLots([]); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  return (
    <>
      <PageTitle sub="Offer lots that are about to spoil or did not sell to nearby NGOs. Donations are counted as donated, not wasted.">{t("rescue.title")}</PageTitle>
      {!lots ? <Loading /> : lots.length === 0 ? <Empty title="No lots at your location." /> : (
        <ul className="space-y-3">
          {lots.map((l) => {
            const m = matches[l.id];
            return (
              <li key={l.id} className="card p-4">
                <div className="flex items-center justify-between gap-2"><Link to={`/lots/${l.id}`} className="font-semibold capitalize">{l.commodity} · {weight(l.current_qty_kg)} <span className="font-mono text-sm text-muted">{l.short_code}</span></Link><ProvenanceBadge p={l.provenance} /></div>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Button variant="secondary" onClick={async () => { try { setMatches({ ...matches, [l.id]: await api(`/rescue/matches/${l.id}`) }); } catch (e) { toast((e as Error).message, { tone: "bad" }); } }}>Find matches</Button>
                  {(["RED", "YELLOW", "UNSOLD"] as const).map((trig) => (
                    <Button key={trig} variant="secondary" onClick={async () => { try { await api("/rescue/broadcasts", { body: { consignment_id: l.id, trigger: trig } }); toast("Offer sent to the nearest NGOs", { tone: "good" }); void load(); } catch (e) { toast((e as Error).message, { tone: "bad" }); } }}>
                      {t("rescue.offer")} ({trig === "UNSOLD" ? "unsold" : trig.toLowerCase()})
                    </Button>
                  ))}
                </div>
                {m ? (
                  <div className="mt-3 text-sm">
                    <p><TrafficLight light={m.light} /> safe window ~{hours(m.safe_window_h)}</p>
                    {m.matches.length === 0 ? <p className="mt-2 text-muted">No NGO can take this in time. Only NGOs that entered a profile are matched.</p> : (
                      <table className="mt-2 w-full text-left">
                        <thead><tr><th>NGO</th><th>Score</th><th>Road time</th><th>Margin</th><th>Capacity</th></tr></thead>
                        <tbody>{m.matches.map((x: any) => (
                          <tr key={x.ngo_node_id} className="border-t border-line"><td>{x.name} <ProvenanceBadge p={x.provenance} /></td><td>{x.score.toFixed(2)}</td><td>{hours(x.road_time_h)}</td><td>{hours(x.life_margin_h)}</td><td>{weight(x.capacity_left_kg)}</td></tr>
                        ))}</tbody>
                      </table>
                    )}
                    <HowCalculated title="Match score"><p>{m.score_formula}</p>{m.matches[0] ? <pre className="mt-2 overflow-x-auto rounded bg-surface-3 p-2 text-xs">{JSON.stringify(m.matches[0].breakdown, null, 2)}</pre> : null}<p className="mt-2 text-warn">{m.disclaimer}</p></HowCalculated>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
      {bcasts.length ? (
        <Card title="Your offers" className="mt-4">
          <ul className="space-y-2 text-sm">
            {bcasts.map((b) => (
              <li key={b.id} className="rounded-lg border border-line p-2">
                <b>{b.status}</b> · {weight(b.qty_kg)} · trigger {b.trigger} · wave {b.wave + 1}
                <ul className="mt-1 text-muted">{b.offers.map((o: any) => <li key={o.id}>{o.ngo_name}: {o.status}{o.status === "CLAIMED" ? ` (pickup within ${countdown(o.claim_expires_at, serverNow())})` : ""}</li>)}</ul>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </>
  );
}
