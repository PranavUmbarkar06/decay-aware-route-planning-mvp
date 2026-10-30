// Dispatcher alert rail (plan v2 §5b). Each open decision gets a "decision clock": a bar that drains from the
// moment the alert was raised to the decision deadline (point of no return minus driver communication buffers).
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useStore } from "../store";
import type { Alert } from "../types";
import { clock, kg, rs } from "./controls";

const TIER_TEXT: Record<string, string> = {
  CRITICAL: "Decide now", HIGH: "Decide soon", ADVISORY: "Decision needed", MONITOR: "Watching", EXPIRED: "Window closed", NONE: "",
};
const STATE_TEXT: Record<string, string> = {
  ALERTED: "Awaiting review", UNDER_REVIEW: "In review", APPROVED: "Approved", MODIFIED: "Approved (modified)",
  SENT_TO_DRIVER: "Sent to driver", ACKNOWLEDGED: "Driver acknowledged", EXECUTED: "Truck diverted", REJECTED: "Rejected",
  EXPIRED: "Expired, truck continues", SUPERSEDED: "Superseded",
};

function DecisionClock({ a, nowH }: { a: Alert; nowH: number }) {
  if (a.deadline_h == null) return null;
  const total = Math.max(0.01, a.deadline_h - a.created_h);
  const left = a.deadline_h - nowH;
  const frac = Math.max(0, Math.min(1, left / total));
  const min = left * 60;
  return (
    <div className={`dclock t-${a.tier.toLowerCase()}`} aria-label={`Decision deadline in ${Math.max(0, Math.round(min))} minutes`}>
      <div className="dclock-bar"><span style={{ width: `${frac * 100}%` }} /></div>
      <div className="dclock-text">
        <strong>{min < 0 ? "Deadline passed" : min < 90 ? `${Math.round(min)} min to decide` : `${(min / 60).toFixed(1)} h to decide`}</strong>
        <span>by {clock(useStore.getState().shipment.dispatch_hour, a.deadline_h)}</span>
      </div>
    </div>
  );
}

function AlertCard({ a }: { a: Alert }) {
  const nowH = useStore((s) => s.replay.nowH);
  const open = useStore((s) => s.openAlert === a.id);
  const set = useStore((s) => s.set);
  const act = useStore((s) => s.actOnAlert);
  const dispatchHour = useStore((s) => s.shipment.dispatch_hour);
  const p = a.payload;
  const decidable = ["ALERTED", "UNDER_REVIEW"].includes(a.state);
  const best = p.options?.length ? p.options.reduce((x, y) => ((y.benefit_rs ?? Infinity) > (x.benefit_rs ?? Infinity) ? y : x)) : null;
  return (
    <article className={`alert-card s-${a.state.toLowerCase()} ${a.at_risk ? "at-risk" : ""}`}>
      <header>
        <span className={`tier t-${a.tier.toLowerCase()}`}>{TIER_TEXT[a.tier] ?? a.tier}</span>
        <span className="alert-state">{STATE_TEXT[a.state] ?? a.state}</span>
      </header>
      <h4>{a.shipment_id}</h4>
      <p className="alert-reason">{p.reason}</p>
      {decidable && <DecisionClock a={a} nowH={nowH} />}
      {a.at_risk && <p className="warn">Queue too long: this alert passes its deadline before review at the current pace.</p>}
      {p.wait_and_see && decidable && (
        <p className="hint">Disruption is unconfirmed or still far off. Recommended decision time {clock(dispatchHour, p.recommended_decision_h ?? nowH)}; waiting keeps options open.</p>
      )}
      {decidable && (
        <div className="alert-actions">
          <button className="btn primary" onClick={() => void act(a, "approve")}>Approve diversion</button>
          <button className="btn" onClick={() => void act(a, "reject")}>Keep route</button>
          <button className="btn quiet" onClick={() => void act(a, "snooze", { until_h: nowH + 10 / 60 })}>Snooze 10 min</button>
          <button className="btn quiet" onClick={() => { set({ openAlert: open ? null : a.id }); if (a.state === "ALERTED") void act(a, "review"); }}>
            {open ? "Hide options" : "Review options"}
          </button>
        </div>
      )}
      {open && (
        <div className="alert-detail">
          {p.benefit_curve?.length > 1 && (
            <>
              <h5>Benefit of diverting, by junction</h5>
              <ResponsiveContainer width="100%" height={90}>
                <LineChart data={p.benefit_curve.map(([m, b]) => ({ m, b }))} margin={{ top: 4, right: 6, bottom: 0, left: -12 }}>
                  <XAxis dataKey="m" tickFormatter={(v) => `${Math.round(v)}′`} fontSize={10} stroke="#8a8f94" />
                  <YAxis tickFormatter={(v) => `${Math.round(v / 1000)}k`} fontSize={10} stroke="#8a8f94" />
                  <Tooltip formatter={(v) => rs(Number(v))} labelFormatter={(v) => `${Math.round(Number(v))} min ahead`} />
                  <Line dataKey="b" stroke="#17734a" dot={{ r: 2 }} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </>
          )}
          <h5>Diversion points still open</h5>
          <ol className="options">
            {p.options.map((o, i) => (
              <li key={i} className={o === best ? "best" : ""}>
                <div>
                  <strong>{o.label}</strong>
                  <span>{o.km_ahead.toFixed(0)} km ahead, decide by {clock(dispatchHour, o.deadline_h)}</span>
                  <span>{o.benefit_rs == null ? "Required: current route blocked" : `+${rs(o.benefit_rs)}`}, wastage {kg(o.wastage_kg)}</span>
                </div>
                {decidable && o.reachable && <button className="btn small" onClick={() => void act(a, "modify", { option: i })}>Use this</button>}
              </li>
            ))}
          </ol>
          {p.stay_feasible && <p className="hint">Staying: wastage {kg(p.stay_wastage_kg)}, net {rs(p.stay_net_rs)}.</p>}
        </div>
      )}
    </article>
  );
}

export function AlertRail() {
  const q = useStore((s) => s.queue);
  const r = useStore((s) => s.replay);
  const messages = useStore((s) => s.messages);
  const set = useStore((s) => s.set);
  const buffers = useStore((s) => s.buffers);
  const dispatchHour = useStore((s) => s.shipment.dispatch_hour);
  const alerts = q?.alerts ?? [];
  return (
    <aside className="rail" aria-label="Dispatcher decisions">
      <div className="rail-head">
        <h2>Dispatcher</h2>
        {r.started && <span className="rail-clock">{clock(dispatchHour, r.nowH)}</span>}
      </div>
      {!r.started && <p className="empty-state">Start a trip on the route page. Disruptions on the truck's path raise a decision here with its deadline.</p>}
      {r.started && alerts.length === 0 && <p className="empty-state">No decision needed. Add a disruption ahead of the truck to see how much time the dispatcher has.</p>}
      {q?.warning && <p className="warn">{q.warning}</p>}
      {q && q.pending > 0 && <p className="hint">{q.pending} open, about {q.workload_min} min of review at {buffers.review} min each.</p>}
      {alerts.map((a) => <AlertCard key={a.id} a={a} />)}
      {messages && (
        <section className="driver-msg">
          <h3>Message sent to driver</h3>
          {Object.entries(messages).map(([k, v]) => <p key={k} lang={k}><b>{k.toUpperCase()}</b> {v}</p>)}
          <p className="hint">SMS or WhatsApp. Acknowledgement is simulated after {buffers.acknowledgement} min.</p>
          <button className="btn quiet small" onClick={() => set({ messages: null })}>Dismiss</button>
        </section>
      )}
      {r.log.length > 0 && (
        <section className="trip-log">
          <h3>Trip log</h3>
          <ul>{[...r.log].reverse().slice(0, 12).map((l, i) => <li key={i}><time>{clock(dispatchHour, l.h)}</time>{l.text}</li>)}</ul>
        </section>
      )}
    </aside>
  );
}
