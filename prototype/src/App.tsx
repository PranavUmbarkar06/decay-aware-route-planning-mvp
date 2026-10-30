import { useEffect } from "react";
import { AlertRail } from "./components/AlertRail";
import { kg } from "./components/controls";
import { CropPage } from "./pages/CropPage";
import { OutcomesPage } from "./pages/OutcomesPage";
import { RoutePage } from "./pages/RoutePage";
import { ShipmentPage } from "./pages/ShipmentPage";
import { WastagePage } from "./pages/WastagePage";
import { WhatIfPage } from "./pages/WhatIfPage";
import { type Page, useStore } from "./store";

const NAV: { id: Page; label: string; icon: string }[] = [
  { id: "shipment", label: "Shipments", icon: "M4 7h16v10H4zM4 7l3-3h10l3 3M9 12h6" },
  { id: "route", label: "Route optimisation", icon: "M5 19c3-6 4-14 14-14M5 19a2 2 0 1 0 0-.1M19 5a2 2 0 1 0 0-.1" },
  { id: "crops", label: "Crop intelligence", icon: "M12 20c-5-3-7-8-6-14 6 0 10 4 6 14zM12 20c4-3 6-7 5-11" },
  { id: "whatif", label: "What-if simulator", icon: "M5 7h14M5 12h14M5 17h14M9 5v4M15 10v4M11 15v4" },
  { id: "wastage", label: "Wastage analysis", icon: "M5 19V9M10 19V5M15 19v-7M20 19v-4" },
  { id: "outcomes", label: "Shipment outcomes", icon: "M6 4h12v16H6zM9 9h6M9 13h6M9 17h3" },
];

export function App() {
  const { page, set, init, shipment, origin, destination, plan, cfg } = useStore();
  useEffect(() => { void init(); }, [init]);
  const rec = plan?.candidates.find((c) => c.id === plan.recommended_id)?.metrics;
  return (
    <div className={`shell p-${page}`}>
      <nav className="navrail" aria-label="Sections">
        <div className="mark" aria-hidden><svg viewBox="0 0 24 24"><path d="M3 18c4-1 6-5 9-9s6-5 9-5" /><circle cx="6" cy="17" r="2.2" /><circle cx="18" cy="5.5" r="2.2" /></svg></div>
        {NAV.map((n) => (
          <button key={n.id} className={page === n.id ? "on" : ""} aria-current={page === n.id ? "page" : undefined} onClick={() => set({ page: n.id })}>
            <svg viewBox="0 0 24 24" aria-hidden><path d={n.icon} /></svg>
            <span>{n.label}</span>
          </button>
        ))}
      </nav>
      <header className="context">
        <strong className="product">Saleable Routes</strong>
        {cfg && (
          <div className="ctx-items">
            <span className={`crop-dot c-${shipment.crop}`}>{cfg.crops[shipment.crop].label}</span>
            <span>{kg(shipment.kg)}</span>
            <span>{origin?.market ?? "No origin"} to {destination?.market ?? "no destination"}</span>
            <span className="ctx-id">{shipment.shipment_id}</span>
            {rec && <span className="ctx-result">Projected saleable {kg(rec.saleable_kg)}</span>}
          </div>
        )}
      </header>
      <main className="main">
        {page === "shipment" && <ShipmentPage />}
        {page === "route" && <RoutePage />}
        {page === "crops" && <CropPage />}
        {page === "whatif" && <WhatIfPage />}
        {page === "wastage" && <WastagePage />}
        {page === "outcomes" && <OutcomesPage />}
      </main>
      <AlertRail />
    </div>
  );
}
