import { useCallback, useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../../lib/api";
import { useSession } from "../../lib/session";
import { ist, pct, weight } from "../../lib/format";
import { Button, Card, Empty, ErrorBox, Field, inputCls, Loading, PageTitle, ProvenanceBadge } from "../../components/ui";

const ACTIONS: Record<string, { to: string; label: string; icon: string; hint: string }[]> = {
  FARMER: [{ to: "/lots/new", label: "Register a lot", icon: "➕", hint: "Get a QR label and PIN" }, { to: "/crowd", label: "Mandi crowd", icon: "📊", hint: "Which market is crowded today" }],
  SUPERVISOR: [{ to: "/scan", label: "Scan a lot", icon: "📷", hint: "Receive, weigh, hand over" }, { to: "/storage", label: "Storage", icon: "🚦", hint: "What to send first" }, { to: "/rescue", label: "Rescue", icon: "🤝", hint: "Offer lots to NGOs" }],
  WAREHOUSE: [{ to: "/storage", label: "Storage", icon: "🚦", hint: "First expiring first out" }, { to: "/scan", label: "Scan a lot", icon: "📷", hint: "Receive or dispatch" }, { to: "/rescue", label: "Rescue", icon: "🤝", hint: "Offer lots to NGOs" }],
  DISPATCHER: [{ to: "/advisor", label: "Route advisor", icon: "🧭", hint: "Compare routes for a load" }, { to: "/crowd", label: "Mandi crowd", icon: "📊", hint: "Glut warnings" }, { to: "/lab", label: "Simulation lab", icon: "🧪", hint: "Results and live runs" }],
  NGO: [{ to: "/rescue", label: "Rescue offers", icon: "🤝", hint: "Claim produce nearby" }, { to: "/scan", label: "Scan at pickup", icon: "📷", hint: "Confirm the handover" }],
  TRANSPORTER: [{ to: "/scan", label: "Scan a lot", icon: "📷", hint: "At pickup, on the way, at drop" }],
  ADMIN: [{ to: "/lab", label: "Simulation lab", icon: "🧪", hint: "Results, replay, live" }, { to: "/admin", label: "Admin", icon: "🛠", hint: "Users, places, audit log" }],
};

export function Home() {
  const { t } = useTranslation();
  const { user } = useSession();
  const [handovers, setHandovers] = useState<any[]>([]);
  const [notes, setNotes] = useState<any[] | null>(null);
  const [stats, setStats] = useState<any>(null);
  useEffect(() => {
    void api<any[]>("/handovers").then(setHandovers).catch(() => setHandovers([]));
    void api<any[]>("/notifications").then(setNotes).catch(() => setNotes([]));
    void api("/stats/dispositions").then(setStats).catch(() => setStats(null));
  }, []);
  const incoming = handovers.filter((h) => h.to_node === user?.home_node_id);
  return (
    <div className="space-y-4">
      <PageTitle sub={user ? `${t(`role.${user.role}`)}${user.name ? ` · ${user.name}` : ""}` : undefined}>{t("nav.home")}</PageTitle>
      <div className="grid gap-3 sm:grid-cols-3">
        {(ACTIONS[user?.role ?? ""] ?? []).map((a) => (
          <Link key={a.to} to={a.to} className="card tap flex items-center gap-3 p-4 hover:border-brand">
            <span className="text-3xl" aria-hidden>{a.icon}</span>
            <span><span className="block font-semibold">{a.label}</span><span className="text-sm text-muted">{a.hint}</span></span>
          </Link>
        ))}
      </div>
      {incoming.length ? (
        <Card title={`Waiting for you to confirm (${incoming.length})`}>
          <ul className="space-y-2">{incoming.map((h) => (
            <li key={h.id}><Link to={`/lots/${h.consignment_id}`} className="tap flex items-center justify-between rounded-xl border border-line p-3">
              <span>{weight(h.weight_released_kg)} · sent {ist(h.created_at)}</span><span className="font-semibold text-brand">Confirm →</span></Link></li>
          ))}</ul>
        </Card>
      ) : null}
      <Card title="Notifications">
        {!notes ? <Loading rows={2} /> : notes.length === 0 ? <p className="text-sm text-muted">Nothing new. Rescue offers and alerts appear here.</p> : (
          <ul className="space-y-2">{notes.slice(0, 8).map((n) => (
            <li key={n.id} className="rounded-xl border border-line p-3 text-sm"><b>{n.title}</b><div className="text-muted">{n.body}</div><div className="text-xs text-muted">{ist(n.created_at)}</div></li>
          ))}</ul>
        )}
      </Card>
      {stats ? (
        <Card title="Logged in the app: where produce went">
          <p className="mb-2 text-sm text-muted">{stats.note}</p>
          <div className="overflow-x-auto"><table className="w-full text-left text-sm">
            <thead><tr><th>Data</th><th>Lots</th><th>Sold</th><th>Donated</th><th>Processed</th><th>Wasted</th><th>Logged wastage rate</th></tr></thead>
            <tbody>{Object.entries(stats.by_provenance).map(([p, d]: any) => (
              <tr key={p} className="border-t border-line"><td><ProvenanceBadge p={p} /></td><td>{d.lots}</td><td>{weight(d.sold_kg)}</td><td>{weight(d.donated_kg)}</td><td>{weight(d.processed_kg)}</td><td>{weight(d.wasted_kg)}</td><td>{pct(d.logged_wastage_rate)}</td></tr>
            ))}</tbody>
          </table></div>
        </Card>
      ) : null}
    </div>
  );
}

export function Evidence() {
  const [ev, setEv] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  useEffect(() => { api("/evidence").then(setEv).catch(setErr); }, []);
  if (err) return <ErrorBox error={err} />;
  if (!ev) return <Loading />;
  const STATUS: Record<string, string> = { AVAILABLE: "text-good", PARTIAL: "text-warn", RESTRICTED: "text-bad", MISSING: "text-bad", UNVERIFIED: "text-warn" };
  return (
    <div className="space-y-4">
      <PageTitle sub="What is known, what is assumed, and what is missing.">Evidence & limitations</PageTitle>
      <p className="rounded-xl border-2 border-warn bg-warn-soft p-4 font-semibold text-warn" data-testid="interview-statement">{ev.statement}</p>
      <Card title="How claims are tagged (from the Round-1 brief)">
        <ul className="space-y-3">{ev.evidence_tags.map((tg: any) => (
          <li key={tg.tag}><b>{tg.tag}</b>: {tg.meaning}<ul className="list-disc pl-5 text-sm text-muted">{tg.examples.map((x: string) => <li key={x}>{x}</li>)}</ul></li>
        ))}</ul>
      </Card>
      <Card title="Known limits of this prototype">
        <ul className="list-disc space-y-1 pl-5">{ev.limitations.map((l: string) => <li key={l}>{l}</li>)}</ul>
        <p className="mt-3 font-semibold">{ev.no_target_claim}</p>
      </Card>
      <Card title="Data gaps (generated by the data audit)">
        <div className="overflow-x-auto"><table className="w-full text-left text-sm">
          <thead><tr><th>Need</th><th>Status</th><th>Fallback</th></tr></thead>
          <tbody>{ev.data_gaps.map((g: any) => (
            <tr key={g.need} className="border-t border-line align-top"><td className="py-1">{g.need}<div className="text-xs text-muted">{g.source_name}</div></td>
              <td className={`font-bold ${STATUS[g.status] ?? ""}`}>{g.status}</td><td className="text-muted">{g.fallback || "–"}</td></tr>
          ))}</tbody>
        </table></div>
      </Card>
      <Card title="National loss benchmarks (NABCONS 2022, as tabled in PIB release 2151371)">
        <table className="w-full text-left text-sm"><thead><tr><th>Crop</th><th>Farm operations</th><th>Market level</th></tr></thead>
          <tbody>{ev.benchmarks.map((b: any) => <tr key={b.crop} className="border-t border-line"><td>{b.crop}</td><td>{b.farm_operations_loss_pct}%</td><td>{b.market_level_loss_pct}%</td></tr>)}</tbody></table>
        <p className="mt-2 text-sm text-muted">{ev.benchmark_caveat} <ProvenanceBadge p="REAL_FETCHED" /></p>
      </Card>
    </div>
  );
}

export function Help() {
  return (
    <div className="space-y-4">
      <PageTitle>Help</PageTitle>
      <Card title="Scanning">The QR label carries only the lot code. If the camera does not work, type the code and the 4-digit PIN written on the label. After 5 wrong PINs the PIN locks for 15 minutes.</Card>
      <Card title="Handing over">The sender declares weight and condition; the receiver weighs it and confirms. If the weights differ by more than 2%, the lot is marked "weight disputed" and the difference is kept aside. It is not counted as waste.</Card>
      <Card title="Offline">Scans and wastage logs made without signal are saved on the phone with their real time and sent when you are back online.</Card>
      <Card title="Traffic lights">Red: under 1 day of saleable life left. Yellow: 1 to 3 days. Green: 3 days or more. These come from a model (tap "How is this calculated?"); they are not a food-safety certificate.</Card>
      <Card title="Demo">This deployment runs in demo mode: the people and lots are made up (marked DEMO) and sign-in codes are shown on screen. Try the Guided demo.</Card>
    </div>
  );
}

export function ReportProblem() {
  const { user, toast } = useSession();
  const loc = useLocation();
  const [msg, setMsg] = useState("");
  const [sent, setSent] = useState(false);
  if (!user) return <Empty title="Sign in to report a problem." />;
  return (
    <>
      <PageTitle sub="Your report goes to the team running this prototype. It is not sent anywhere else.">Report a problem</PageTitle>
      <Card>
        {sent ? <p className="text-good">Thank you. The team will look at it.</p> : (
          <form className="space-y-3" onSubmit={async (e) => { e.preventDefault(); try { await api("/feedback", { body: { message: msg, page: (loc.state as any)?.from ?? document.referrer } }); setSent(true); } catch (err) { toast((err as Error).message, { tone: "bad" }); } }}>
            <Field label="What went wrong?">{(id) => <textarea id={id} className={`${inputCls} min-h-32 py-2`} value={msg} onChange={(e) => setMsg(e.target.value)} required maxLength={2000} />}</Field>
            <Button type="submit">Send</Button>
          </form>
        )}
      </Card>
    </>
  );
}

export function Admin() {
  const { toast } = useSession();
  const [audit, setAudit] = useState<any[] | null>(null);
  const [review, setReview] = useState<any[]>([]);
  const [csv, setCsv] = useState("name,node_type,lat,lon,district\n");
  const [result, setResult] = useState<any>(null);
  const [inv, setInv] = useState({ phone: "", role: "SUPERVISOR", name: "" });
  const load = useCallback(() => {
    void api<any[]>("/admin/audit?limit=100").then(setAudit).catch(() => setAudit([]));
    void api<any[]>("/nodes?include_review=true").then((n) => setReview(n.filter((x) => x.needs_review && !x.review_status)));
  }, []);
  useEffect(load, [load]);
  return (
    <div className="space-y-4">
      <PageTitle>Admin</PageTitle>
      <Card title="Invite a user">
        <form className="grid gap-3 sm:grid-cols-4" onSubmit={async (e) => { e.preventDefault(); try { const r = await api("/admin/invites", { body: { ...inv, name: inv.name || null } }); toast(r.status, { tone: "good" }); load(); } catch (err) { toast((err as Error).message, { tone: "bad" }); } }}>
          <Field label="Phone">{(id) => <input id={id} className={inputCls} value={inv.phone} onChange={(e) => setInv({ ...inv, phone: e.target.value })} required pattern="\+?\d{10,15}" />}</Field>
          <Field label="Role">{(id) => <select id={id} className={inputCls} value={inv.role} onChange={(e) => setInv({ ...inv, role: e.target.value })}>{["FARMER", "SUPERVISOR", "WAREHOUSE", "DISPATCHER", "NGO", "TRANSPORTER", "ADMIN"].map((r) => <option key={r}>{r}</option>)}</select>}</Field>
          <Field label="Name">{(id) => <input id={id} className={inputCls} value={inv.name} onChange={(e) => setInv({ ...inv, name: e.target.value })} />}</Field>
          <div className="flex items-end"><Button type="submit" className="w-full">Invite</Button></div>
        </form>
      </Card>
      <Card title="Import places (CSV)">
        <p className="mb-2 text-sm text-muted">Columns: name,node_type,lat,lon,district. Every row is checked; nothing is imported while any row has an error. Imported places stay "needs review" until the road graph is rebuilt.</p>
        <textarea aria-label="CSV" className={`${inputCls} min-h-32 py-2 font-mono text-sm`} value={csv} onChange={(e) => setCsv(e.target.value)} />
        <div className="mt-2 flex gap-2">
          <Button variant="secondary" onClick={async () => setResult(await api("/admin/nodes/import", { body: { csv } }))}>Check</Button>
          <Button onClick={async () => { const r = await api("/admin/nodes/import?commit=true", { body: { csv } }); setResult(r); if (r.committed) toast(`${r.committed} places imported`, { tone: "good" }); }}>Import</Button>
        </div>
        {result ? (
          <div className="mt-3 text-sm" data-testid="import-result">
            <p>{result.valid} valid row(s){result.committed ? `, ${result.committed} imported` : ""}. {result.note ?? ""}</p>
            {result.errors.length ? <ul className="mt-1 list-disc pl-5 text-bad">{result.errors.map((e: any) => <li key={e.row}>Row {e.row}: {e.error}</li>)}</ul> : null}
          </div>
        ) : null}
      </Card>
      <Card title={`Places needing review (${review.length})`}>
        <p className="mb-2 text-sm text-muted">Excluded from routing until reviewed. Decisions are recorded through inputs/node_review.csv and <code>python tasks.py graph-apply-review</code>.</p>
        <ul className="max-h-64 space-y-1 overflow-y-auto text-sm">{review.map((n) => <li key={n.node_id}>{n.name} · {n.node_type} · {n.district} · confidence {n.geocode_confidence ?? "–"}</li>)}</ul>
      </Card>
      <Card title="Audit log (latest 100)">
        {!audit ? <Loading /> : <ul className="max-h-96 space-y-1 overflow-y-auto font-mono text-xs">{audit.map((a) => <li key={a.id}>{ist(a.at_utc)} · {a.action} · {a.entity}:{String(a.entity_id).slice(0, 12)}</li>)}</ul>}
      </Card>
    </div>
  );
}
