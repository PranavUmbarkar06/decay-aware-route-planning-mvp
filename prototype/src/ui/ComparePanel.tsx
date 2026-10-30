import { CROPS } from "../data/crops";
import { BUYERS, CONSIGNMENTS } from "../data/consignments";
import { fmtH, fmtK, pct, type Outcome, type Sim } from "../model/sim";

function Chart({ series, color }: { series: { pts: [number, number][]; color: string; dash?: string; label: string }[]; color: string }) {
  const all = series.flatMap((s) => s.pts);
  if (all.length < 2) return null;
  const W = 300, H = 110, P = 26;
  const x0 = Math.min(...all.map((p) => p[0])), x1 = Math.max(...all.map((p) => p[0]), x0 + 0.5);
  const yMin = Math.max(0, Math.min(...all.map((p) => p[1])) - 0.03), yMax = Math.min(1, Math.max(...all.map((p) => p[1])) + 0.02);
  const sx = (x: number) => P + ((x - x0) / (x1 - x0)) * (W - P - 6);
  const sy = (y: number) => 6 + (1 - (y - yMin) / (yMax - yMin || 1)) * (H - P);
  const qmin = 0.6;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart">
      {qmin > yMin && qmin < yMax && <>
        <line x1={P} x2={W - 6} y1={sy(qmin)} y2={sy(qmin)} stroke="#ff4d4d" strokeDasharray="3 3" strokeWidth={1} />
        <text x={W - 8} y={sy(qmin) - 3} textAnchor="end" className="ax">Q_min (half unsellable)</text>
      </>}
      <text x={2} y={sy(yMax) + 8} className="ax">{yMax.toFixed(2)}</text>
      <text x={2} y={sy(yMin)} className="ax">{yMin.toFixed(2)}</text>
      <text x={P} y={H - 4} className="ax">{fmtH(x0)}</text>
      <text x={W - 6} y={H - 4} textAnchor="end" className="ax">{fmtH(x1)} into trip</text>
      {series.map((s) => (
        <polyline key={s.label} fill="none" stroke={s.color} strokeWidth={2} strokeDasharray={s.dash}
          points={s.pts.map((p) => `${sx(p[0])},${sy(p[1])}`).join(" ")} />
      ))}
      <title>{`Quality over time — ${color}`}</title>
    </svg>
  );
}

function Row({ label, a, b, better }: { label: string; a: string; b: string; better?: "a" | "b" | null }) {
  return (
    <tr>
      <td>{label}</td>
      <td className={better === "a" ? "win" : ""}>{a}</td>
      <td className={better === "b" ? "win" : ""}>{b}</td>
    </tr>
  );
}

export function ComparePanel({ sim, selected, onSelect }: { sim: Sim; selected: string; onSelect: (id: string) => void }) {
  const smart = sim.trucks.find((t) => t.smart && t.c.id === selected)!;
  const base = sim.trucks.find((t) => !t.smart && t.c.id === selected)!;
  const crop = CROPS[smart.c.crop];
  const B: Outcome = sim.projection(smart);
  const A: Outcome | null = smart.done ? null : smart.fastest;
  const G: Outcome = sim.projection(base);
  const cmp = (x: number, y: number, hi = true) => (Math.abs(x - y) < 1e-6 ? null : (x > y) === hi ? "a" : "b");

  return (
    <section className="card compare">
      <div className="tabs">
        {CONSIGNMENTS.map((c) => (
          <button key={c.id} className={c.id === selected ? "on" : ""} style={{ ["--c" as string]: CROPS[c.crop].color }} onClick={() => onSelect(c.id)}>
            {c.id} · {CROPS[c.crop].label}
          </button>
        ))}
      </div>
      <div className="consign">
        <span>{(smart.c.kg / 1000).toFixed(0)} t from {smart.c.origin.name}</span>
        <span>Quality now <b style={{ color: crop.color }}>{smart.q.toFixed(3)}</b> · {smart.c.harvestNote}</span>
      </div>

      {A ? (
        <>
          <h3>Route A vs Route B <small>(remaining trip)</small></h3>
          <table className="cmp">
            <thead><tr><th></th><th><i className="sw dotted" />A · Fastest</th><th><i className="sw" style={{ background: crop.color }} />B · FreshRoute</th></tr></thead>
            <tbody>
              <Row label="Destination" a={BUYERS[A.buyer].short} b={BUYERS[B.buyer].short} />
              <Row label="Distance" a={`${A.km.toFixed(0)} km`} b={`${B.km.toFixed(0)} km`} better={cmp(A.km, B.km, false)} />
              <Row label="Arrive in" a={fmtH(A.hours - smart.hours)} b={fmtH(B.hours - smart.hours)} better={cmp(A.hours, B.hours, false)} />
              <Row label="Quality on arrival" a={A.qArr.toFixed(3)} b={B.qArr.toFixed(3)} better={cmp(A.qArr, B.qArr)} />
              <Row label="Sellable" a={pct(A.sellFrac)} b={pct(B.sellFrac)} better={cmp(A.sellFrac, B.sellFrac)} />
              <Row label="Lost to rot" a={`${fmtK(smart.c.kg - A.sellKg)} kg`} b={`${fmtK(smart.c.kg - B.sellKg)} kg`} better={cmp(A.sellKg, B.sellKg)} />
              <Row label="Net to farmer" a={`₹${fmtK(A.net)}`} b={`₹${fmtK(B.net)}`} better={cmp(A.net, B.net)} />
            </tbody>
          </table>
        </>
      ) : (
        <div className="arrived">Delivered to <b>{BUYERS[B.buyer].name}</b>: {pct(B.sellFrac)} sellable, net ₹{fmtK(B.net)}</div>
      )}

      <h3>Quality over time</h3>
      <Chart color={crop.label} series={[
        ...(A ? [{ pts: A.profile, color: "#ffffff", dash: "2 3", label: "A" }] : []),
        { pts: B.profile.length ? B.profile : [[0, smart.c.q0], [B.hours, B.qArr]], color: crop.color, label: "B" },
        { pts: G.profile.length ? G.profile : [[0, base.c.q0], [G.hours, G.qArr]], color: "#6b7a90", dash: "5 3", label: "status quo" },
      ]} />
      <div className="legend"><span><i className="sw dotted" />A fastest</span><span><i className="sw" style={{ background: crop.color }} />B FreshRoute</span><span><i className="sw" style={{ background: "#6b7a90" }} />status-quo truck ({BUYERS[G.buyer].short})</span></div>

      {smart.candidates.length > 0 && !smart.done && (
        <>
          <h3>Every buyer, right now</h3>
          <div className="cands">
            {smart.candidates.map((c) => {
              const best = smart.candidates[0].net;
              return (
                <div key={c.buyer} className={`cand ${c.buyer === smart.buyer ? "chosen" : ""}`}>
                  <span className="n">{BUYERS[c.buyer].short}{BUYERS[c.buyer].kind === "processor" && <em>proc</em>}</span>
                  <span className="bar"><i style={{ width: `${Math.max(2, (Math.max(0, c.net) / Math.max(1, best)) * 100)}%`, background: c.buyer === smart.buyer ? crop.color : "#3b4b5e" }} /></span>
                  <span className="v">₹{fmtK(c.net)}</span>
                  <span className="s">{pct(c.sellFrac)} · {fmtH(c.hours - smart.hours)}</span>
                </div>
              );
            })}
          </div>
        </>
      )}
    </section>
  );
}
