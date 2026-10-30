import { clock, type SimEvent } from "../model/sim";

export function EventFeed({ events }: { events: SimEvent[] }) {
  return (
    <section className="card feed">
      <h3>Decision log</h3>
      <ul>
        {events.map((e) => (
          <li key={e.id} className={e.kind} style={{ borderColor: e.color }}>
            <time>{clock(e.t)}</time>
            <span>{e.kind === "reroute" && <b className="badge">REROUTE</b>}{e.text}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function DriverAlert({ event, onClose }: { event: SimEvent; onClose: () => void }) {
  return (
    <div className="phone" onClick={onClose} title="click to dismiss">
      <div className="notch" />
      <div className="app-head">📲 FreshRoute · Driver {event.truck}</div>
      <div className="bubble">
        <p>{event.hi}</p>
        <p>{event.mr}</p>
        <div className="actions"><span>✅ ठीक है</span><span>📞 कॉल</span></div>
      </div>
      <small>Sent over SMS / WhatsApp, works on any phone</small>
    </div>
  );
}
