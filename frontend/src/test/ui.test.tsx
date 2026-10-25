import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import "../i18n";
import { ProvenanceBadge, TrafficLight } from "../components/ui";
import { countdown, hours, ist, pct, weight } from "../lib/format";
import { SessionProvider } from "../lib/session";
import { LotList } from "../features/lots/Lots";

describe("format", () => {
  it("converts weights for the display unit", () => {
    expect(weight(1500, "kg")).toBe("1,500 kg");
    expect(weight(1500, "quintal")).toBe("15 q");
    expect(weight(1500, "tonne")).toBe("1.5 t");
    expect(weight(null)).toBe("–");
  });
  it("shows UTC timestamps in IST", () => {
    expect(ist("2026-05-04T06:00:00")).toContain("11:30");
    expect(ist("2026-05-04T06:00:00")).toContain("IST");
  });
  it("formats durations, percentages and countdowns", () => {
    expect(hours(0.5)).toBe("30 min");
    expect(hours(72)).toBe("3.0 days");
    expect(pct(0.1234)).toBe("12.3%");
    expect(countdown("2026-05-04T08:00:00", Date.parse("2026-05-04T06:30:00Z"))).toBe("1h 30m");
    expect(countdown("2026-05-04T06:00:00", Date.parse("2026-05-04T06:30:00Z"))).toBe("expired");
  });
});

describe("provenance + status are never colour-only", () => {
  it("SYNTHETIC_DEMO renders a DEMO badge", () => {
    render(<ProvenanceBadge p="SYNTHETIC_DEMO" />);
    expect(screen.getByText("DEMO")).toHaveAttribute("data-provenance", "SYNTHETIC_DEMO");
  });
  it("traffic light carries an icon and words, not just colour", () => {
    render(<TrafficLight light="RED" hours={10} />);
    const el = screen.getByText(/Red/).closest("[data-light]")!;
    expect(el).toHaveAttribute("data-light", "RED");
    expect(el.textContent).toMatch(/■/);
    expect(el.textContent).toMatch(/10 h/);
  });
});

describe("provenance lint: demo records always show the DEMO badge", () => {
  afterEach(() => vi.restoreAllMocks());
  it("lot list badges every SYNTHETIC_DEMO lot", async () => {
    const lots = [
      { id: "a", short_code: "AAAA2222", commodity: "tomato", current_qty_kg: 10, status: "AT_NODE", provenance: "SYNTHETIC_DEMO" },
      { id: "b", short_code: "BBBB3333", commodity: "onion", current_qty_kg: 20, status: "AT_NODE", provenance: "USER_ENTERED" },
    ];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url: any) => {
      const u = String(url);
      const body = u.endsWith("/consignments") ? lots : u.includes("/clock") ? { now_utc: "2026-05-04T06:00:00", demo_clock: true } : {};
      return new Response(JSON.stringify(body), { status: 200 });
    });
    render(<SessionProvider><MemoryRouter><LotList /></MemoryRouter></SessionProvider>);
    await screen.findByText("AAAA2222");
    const demoRow = screen.getByText("AAAA2222").closest("a")!;
    expect(demoRow.querySelector('[data-provenance="SYNTHETIC_DEMO"]')).not.toBeNull();
    const realRow = screen.getByText("BBBB3333").closest("a")!;
    expect(realRow.querySelector('[data-provenance="SYNTHETIC_DEMO"]')).toBeNull();
  });
});
