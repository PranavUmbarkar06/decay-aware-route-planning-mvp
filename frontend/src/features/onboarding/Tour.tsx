import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useSession } from "../../lib/session";
import { Button, Card, ProvenanceBadge, TrafficLight } from "../../components/ui";

/** Three-step interactive tour per role, on client-side sample data (labelled DEMO, nothing is saved). */
export default function Tour() {
  const { user } = useSession();
  const nav = useNavigate();
  const { t } = useTranslation();
  const [step, setStep] = useState(0);
  const role = user?.role ?? "SUPERVISOR";
  const steps = TOURS[role] ?? TOURS.SUPERVISOR;
  const S = steps[step];
  return (
    <div className="mx-auto max-w-lg space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">{t("onb.tour")}</h1>
        <ProvenanceBadge p="SYNTHETIC_DEMO" />
      </div>
      <ol className="flex gap-2" aria-label="Tour progress">
        {steps.map((_, i) => <li key={i} className={`h-2 flex-1 rounded-full ${i <= step ? "bg-brand" : "bg-surface-3"}`} aria-current={i === step ? "step" : undefined} />)}
      </ol>
      <Card title={`${step + 1}. ${S.title}`}>
        <S.Body next={() => (step < steps.length - 1 ? setStep(step + 1) : nav("/"))} />
      </Card>
      <div className="flex justify-between">
        <Button variant="ghost" onClick={() => nav("/")}>{t("onb.skip")}</Button>
        {step < steps.length - 1 ? <Button variant="secondary" onClick={() => setStep(step + 1)}>{t("onb.continue")}</Button>
          : <Button onClick={() => nav("/")}>{t("onb.done")}</Button>}
      </div>
    </div>
  );
}

type Step = { title: string; Body: (p: { next: () => void }) => React.ReactElement };

function SampleLot({ light, kg }: { light: string; kg: number }) {
  return (
    <div className="flex items-center justify-between rounded-xl border border-line p-3">
      <div><div className="font-semibold">Tomato · Lot 7K3M9QX2</div><div className="text-sm text-muted">{kg} kg · Demo Mandi 1</div></div>
      <TrafficLight light={light} />
    </div>
  );
}

const SupervisorScan: Step["Body"] = ({ next }) => {
  const [scanned, setScanned] = useState(false);
  return (
    <div className="space-y-3">
      <p>Every lot carries a QR label. Scanning it shows the lot and its history.</p>
      {!scanned ? <Button onClick={() => setScanned(true)}>📷 Scan the sample label</Button> : <SampleLot light="GREEN" kg={1000} />}
      {scanned ? <Button onClick={next}>Next: log wastage</Button> : null}
    </div>
  );
};
const SupervisorWaste: Step["Body"] = ({ next }) => {
  const [kg, setKg] = useState(0);
  const [saved, setSaved] = useState(false);
  return (
    <div className="space-y-3">
      <p>Slide to how much was lost, then tap the reason picture.</p>
      <input type="range" className="big" min={0} max={200} step={10} value={kg} onChange={(e) => setKg(+e.target.value)} aria-label="Kilograms lost" />
      <p className="text-center text-2xl font-bold">{kg} kg</p>
      <Button disabled={!kg} onClick={() => setSaved(true)}>☀️ Heat / rotted</Button>
      {saved ? <><p className="text-good">Logged {kg} kg as Heat / rotted (sample).</p><Button onClick={next}>Next</Button></> : null}
    </div>
  );
};
const SupervisorLight: Step["Body"] = () => {
  const [hours, setHours] = useState(80);
  const light = hours < 24 ? "RED" : hours < 72 ? "YELLOW" : "GREEN";
  return (
    <div className="space-y-3">
      <p>As days pass and the weather heats up, the predicted shelf life falls and the light changes. Drag to see it.</p>
      <input type="range" className="big" min={0} max={120} value={hours} onChange={(e) => setHours(+e.target.value)} aria-label="Hours of life left" />
      <SampleLot light={light} kg={940} />
      <p className="text-sm text-muted">Red &lt; 24 h · Yellow 24–72 h · Green ≥ 72 h. These thresholds are assumptions to confirm with operators.</p>
    </div>
  );
};

const NgoProfile: Step["Body"] = ({ next }) => (
  <div className="space-y-3">
    <p>Tell senders what you can take: which produce, how much per day, and when you can collect.</p>
    <div className="rounded-xl border border-line p-3 text-sm">Accepts: tomato, onion · 2,000 kg/day · pickup 07:00–20:00</div>
    <Button onClick={next}>Looks good</Button>
  </div>
);
const NgoOffer: Step["Body"] = ({ next }) => (
  <div className="space-y-3">
    <p>When a lot is about to spoil or does not sell, nearby NGOs get an offer.</p>
    <div className="rounded-xl border border-line p-3"><b>300 kg tomato</b> · 0.8 h away · safe window ~10 h<br /><span className="text-sm text-muted">Model estimate, not a food-safety certificate.</span></div>
    <Button onClick={next}>Next: claim it</Button>
  </div>
);
const NgoClaim: Step["Body"] = () => {
  const [claimed, setClaimed] = useState(false);
  return (
    <div className="space-y-3">
      <p>The first NGO to claim gets it, with a 2-hour pickup timer. Pickup is a scan, and the food is counted as donated, not wasted.</p>
      {!claimed ? <Button onClick={() => setClaimed(true)}>🤝 Claim (sample)</Button> : <p className="text-good">Claimed. Pickup within 2h 00m.</p>}
    </div>
  );
};

const DispLoad: Step["Body"] = ({ next }) => (
  <div className="space-y-3">
    <p>Enter the load: produce, quantity, harvest time and where it is.</p>
    <div className="rounded-xl border border-line p-3 text-sm">Tomato · 3,000 kg · harvested 20 h ago · Demo Mandi 1</div>
    <Button onClick={next}>Next: compare routes</Button>
  </div>
);
const DispCompare: Step["Body"] = ({ next }) => (
  <div className="space-y-3">
    <p>See the usual shortest route next to a quality-aware option, with the reasons and the uncertainty.</p>
    <div className="grid grid-cols-2 gap-2 text-sm">
      <div className="rounded-xl border-2 border-[var(--series-1)] p-2"><b>Usual route</b><br />3.1 h · quality 0.71</div>
      <div className="rounded-xl border-2 border-[var(--series-2)] p-2"><b>Suggested</b><br />2.6 h · quality 0.78</div>
    </div>
    <Button onClick={next}>Next</Button>
  </div>
);
const DispDecide: Step["Body"] = () => (
  <div className="space-y-3">
    <p>You decide. The app only recommends; it never sends a truck by itself. Simulation shows the quality-aware policy trades
      less waste for more unmet demand, so treat its advice with care.</p>
  </div>
);

const TOURS: Record<string, Step[]> = {
  SUPERVISOR: [{ title: "Scan a lot", Body: SupervisorScan }, { title: "Log wastage", Body: SupervisorWaste }, { title: "Watch the traffic light", Body: SupervisorLight }],
  WAREHOUSE: [{ title: "Scan a lot", Body: SupervisorScan }, { title: "Log wastage", Body: SupervisorWaste }, { title: "Watch the traffic light", Body: SupervisorLight }],
  FARMER: [{ title: "Register a lot", Body: SupervisorScan }, { title: "Hand it over", Body: DispLoad }, { title: "Check the mandi crowd", Body: SupervisorLight }],
  NGO: [{ title: "Your profile", Body: NgoProfile }, { title: "Receive an offer", Body: NgoOffer }, { title: "Claim it", Body: NgoClaim }],
  DISPATCHER: [{ title: "Enter a load", Body: DispLoad }, { title: "Compare routes", Body: DispCompare }, { title: "You decide", Body: DispDecide }],
  TRANSPORTER: [{ title: "Scan at pickup", Body: SupervisorScan }, { title: "Scan on the way", Body: DispDecide }, { title: "Scan at drop", Body: SupervisorLight }],
  ADMIN: [{ title: "Enter a load", Body: DispLoad }, { title: "Compare routes", Body: DispCompare }, { title: "You decide", Body: DispDecide }],
};
