import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../../lib/api";
import { useSession, type User } from "../../lib/session";
import { hours, weight } from "../../lib/format";
import { Button, Card, ErrorBox, PageTitle, ProvenanceBadge, TrafficLight } from "../../components/ui";

const P = { farmer: "+910000000001", supervisor: "+910000000002", warehouse: "+910000000003", dispatcher: "+910000000004",
  ngo: "+910000000005", admin: "+910000000007" };

type Caption = { real: string; synthetic: string; assumed: string };
const STEPS: { title: string; caption: Caption }[] = [
  { title: "A farmer registers a lot", caption: { real: "The farmer's location is a real OSM town (origin proxy).", synthetic: "Demo Farmer 1 and the 1,200 kg tomato lot are made up.", assumed: "Harvest 30 hours before the demo clock." } },
  { title: "Handovers build a tamper-evident journey", caption: { real: "Locations are a real Agmarknet mandi and road positions.", synthetic: "Demo Supervisor 1, Demo Warehouse Owner 1 and Demo Cold Store 1 are made up.", assumed: "Weights entered by the demo script." } },
  { title: "Heat moves the traffic light", caption: { real: "Temperatures are replayed Open-Meteo data for this district and date.", synthetic: "The lot is demo data.", assumed: "Shelf life is a cold-storage reference value extrapolated with FAO's curve; thresholds Red < 24 h, Yellow < 72 h." } },
  { title: "The crowd meter warns about a market", caption: { real: "Arrivals are real Agmarknet report data; road times come from the real road graph (free-flow model).", synthetic: "None.", assumed: "Glut warning at 130% of the 14-day median." } },
  { title: "Rescue: broadcast → claim → pickup → DONATED", caption: { real: "Road time from the real road graph.", synthetic: "Demo NGO 1 and its capacity are made up (real NGOs enter their own profiles).", assumed: "Safe window = 50% of model life; not a food-safety certificate." } },
  { title: "Simulation lab: baseline vs quality-aware", caption: { real: "Roads, weather replay and daily market volumes.", synthetic: "All lots (seeded).", assumed: "Congestion, disruptions, decay parameters. Pre-registered result: the proposed policy did not beat the baseline." } },
];

export default function GuidedDemo() {
  const { meta, signIn, serverNow } = useSession();
  const nav = useNavigate();
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [log, setLog] = useState<string[]>([]);
  const [st, setSt] = useState<any>({});
  const say = (s: string) => setLog((l) => [...l, s]);

  async function as(phone: string): Promise<User> {
    const ch = await api("/auth/otp/request", { body: { phone } });
    if (!ch.dev_otp) throw new Error("The guided demo needs DEV AUTH (demo mode).");
    const r = await api<{ token: string; user: User }>("/auth/otp/verify", { body: { challenge_id: ch.challenge_id, code: ch.dev_otp } });
    signIn(r.token, r.user);
    say(`Signed in as ${r.user.name} (DEMO persona)`);
    return r.user;
  }

  async function run() {
    setBusy(true); setErr(null);
    try {
      if (step === 0) {
        const f = await as(P.farmer);
        const made = await api("/consignments", { body: { commodity: "tomato", grade: "A", qty_kg: 1200,
          harvest_time: new Date(serverNow() - 30 * 3600e3).toISOString(), origin_node_id: f.home_node_id } });
        setSt({ ...st, lot: made.consignment, qr: made.qr_png, pin: made.pin });
        say(`Lot ${made.consignment.short_code} registered: QR label + one-time PIN ${made.pin}`);
      } else if (step === 1) {
        const lot = st.lot;
        await as(P.farmer);
        const supUser = await peek(P.supervisor);
        const h1 = await api(`/consignments/${lot.id}/handovers`, { body: { to_node_id: supUser.home_node_id, weight_kg: 1200, condition: "GOOD" } });
        say("Farmer hands over 1,200 kg to the collection centre");
        await as(P.supervisor);
        await api(`/handovers/${h1.id}/confirm`, { body: { weight_kg: 1195, condition: "GOOD" } });
        say("Supervisor weighs 1,195 kg (within 2%) and confirms: two-party record");
        const wh = await peek(P.warehouse);
        const h2 = await api(`/consignments/${lot.id}/handovers`, { body: { to_node_id: wh.home_node_id, weight_kg: 1195, condition: "GOOD" } });
        await as(P.warehouse);
        await api(`/handovers/${h2.id}/confirm`, { body: { weight_kg: 1190, condition: "MINOR_DAMAGE" } });
        say("Cold store receives 1,190 kg");
        const tl = await api(`/consignments/${lot.id}/timeline`);
        setSt({ ...st, timeline: tl });
        say(`Journey: ${tl.events.length} hash-chained events; log ${tl.chain.ok ? "verifies" : "does NOT verify"}`);
      } else if (step === 2) {
        const sl = await api(`/consignments/${st.lot.id}/shelf-life`);
        setSt({ ...st, sl });
        say(`Shelf life now: ${sl.light}, about ${hours(sl.remaining_life_h)} left (${sl.explanation.inputs.temperature_next.mean_c} °C ahead, replayed)`);
      } else if (step === 3) {
        await as(P.dispatcher);
        const disp = await peek(P.dispatcher);
        const day = new Date(serverNow() + 5.5 * 3600e3).toISOString().slice(0, 10);
        const c = await api(`/crowd?commodity=tomato&on=${day}&origin_node_id=${disp.home_node_id}`);
        setSt({ ...st, crowd: c });
        const top = c.markets[0];
        say(top ? `${top.market}: ${top.label}${top.alternates?.length ? `; alternative ${top.alternates[0].market} (${hours(top.alternates[0].road_time_h_from_this_market)} away)` : ""}` : "No market reported tomato arrivals on this date");
      } else if (step === 4) {
        await as(P.warehouse);
        const light = st.sl?.light ?? "RED";
        const trigger = light === "GREEN" ? "UNSOLD" : light;
        let b: any;
        try {
          b = await api("/rescue/broadcasts", { body: { consignment_id: st.lot.id, trigger } });
          say(`Broadcast (${trigger}) to ${b.offers.filter((o: any) => o.status === "OFFERED").length} NGO(s)`);
        } catch (e) { say(`Broadcast: ${(e as Error).message}`); }
        const offer = b?.offers?.find((o: any) => o.status === "OFFERED" && o.ngo_name?.includes("DEMO"));
        const ngoUser = await peek(P.ngo);
        if (offer) {
          await as(P.ngo);
          const c = await api(`/rescue/offers/${offer.id}/claim`, { method: "POST" });
          say(`Demo NGO 1 claims it; pickup timer runs until ${new Date(`${c.claim_expires_at}Z`).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" })} IST (demo clock)`);
        } else say("No demo NGO could take it in time; handing over directly for the demo");
        await as(P.warehouse);
        const lot = await api(`/consignments/${st.lot.id}`);
        const h = await api(`/consignments/${lot.id}/handovers`, { body: { to_node_id: ngoUser.home_node_id, weight_kg: lot.current_qty_kg, condition: "MINOR_DAMAGE" } });
        await as(P.ngo);
        await api(`/handovers/${h.id}/confirm`, { body: { weight_kg: lot.current_qty_kg, condition: "MINOR_DAMAGE" } });
        const done = await api(`/consignments/${st.lot.id}`);
        setSt({ ...st, final: done });
        say(`Pickup confirmed: ${weight(done.donated_kg)} booked as DONATED, ${weight(done.wasted_kg)} wasted. Lot closed.`);
      } else if (step === 5) {
        await as(P.admin);
        say("Opening the Simulation lab as Demo Analyst 1");
        nav("/lab");
      }
      setStep((s) => Math.min(s + 1, STEPS.length));
    } catch (e) { setErr(e); } finally { setBusy(false); }
  }

  async function peek(phone: string): Promise<User> {
    // fictional demo personas and their home locations (demo-mode endpoint; no sign-in needed)
    const ps = await api<User[]>("/demo/personas");
    const u = ps.find((p) => p.phone === phone);
    if (!u) throw new Error("Demo persona not found. Run `python tasks.py load`.");
    return u;
  }

  if (meta && !meta.demo_mode) return <p>The guided demo is only available in demo mode.</p>;
  const cur = STEPS[Math.min(step, STEPS.length - 1)];
  return (
    <div className="space-y-4">
      <PageTitle sub={<>A scripted, repeatable story on <ProvenanceBadge p="SYNTHETIC_DEMO" /> people and lots over the real road graph. Each step says what is real, made up, or assumed.</>}>Guided demo</PageTitle>
      <ol className="flex gap-1" aria-label="Demo progress">{STEPS.map((s, i) => <li key={s.title} title={s.title} className={`h-2 flex-1 rounded-full ${i < step ? "bg-brand" : i === step ? "bg-brand/50" : "bg-surface-3"}`} />)}</ol>
      {err ? <ErrorBox error={err} /> : null}
      {step < STEPS.length ? (
        <Card title={`Step ${step + 1} of ${STEPS.length}: ${cur.title}`}>
          <dl className="grid gap-2 text-sm sm:grid-cols-3">
            <div className="rounded-lg bg-good-soft p-2"><dt className="font-bold text-good">Real</dt><dd>{cur.caption.real}</dd></div>
            <div className="rounded-lg bg-demo-soft p-2"><dt className="font-bold text-demo">Made up (DEMO)</dt><dd>{cur.caption.synthetic}</dd></div>
            <div className="rounded-lg bg-warn-soft p-2"><dt className="font-bold text-warn">Assumed</dt><dd>{cur.caption.assumed}</dd></div>
          </dl>
          <Button className="mt-3" busy={busy} onClick={() => void run()} data-testid="demo-next">▶ Run this step</Button>
        </Card>
      ) : <Card title="Demo complete"><Link to="/lab" className="font-semibold text-brand underline">Open the Simulation lab</Link></Card>}
      {st.qr ? (
        <Card title="Lot label">
          <div className="flex items-center gap-4"><img src={st.qr} alt="QR code for the demo lot" className="size-32 rounded bg-white p-1" />
            <div><div className="font-mono text-xl">{st.lot.short_code}</div><div>PIN <b className="font-mono">{st.pin}</b></div>
              <Link to={`/lots/${st.lot.id}`} className="text-sm text-brand underline">Open lot</Link></div></div>
        </Card>
      ) : null}
      {st.sl ? <Card title="Shelf life at the cold store"><TrafficLight light={st.sl.light} hours={st.sl.remaining_life_h} /><p className="mt-2 text-sm">{st.sl.explanation.why}</p></Card> : null}
      <Card title="What happened">
        <ol className="list-decimal space-y-1 pl-5 text-sm" aria-live="polite" data-testid="demo-log">{log.map((l, i) => <li key={i}>{l}</li>)}</ol>
      </Card>
    </div>
  );
}
