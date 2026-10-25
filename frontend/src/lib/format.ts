// Display helpers: times are stored in UTC and shown in IST; weights are kg internally with a display toggle.
export type Unit = "kg" | "quintal" | "tonne";
const UNIT_KEY = "phl.unit";

export function getUnit(): Unit {
  try {
    return (localStorage.getItem(UNIT_KEY) as Unit) || "kg";
  } catch {
    return "kg";
  }
}
export function setUnit(u: Unit) {
  try {
    localStorage.setItem(UNIT_KEY, u);
  } catch {
    /* ignore */
  }
}

export function weight(kg: number | null | undefined, unit: Unit = getUnit()): string {
  if (kg === null || kg === undefined || Number.isNaN(kg)) return "–";
  if (unit === "tonne") return `${(kg / 1000).toLocaleString("en-IN", { maximumFractionDigits: 2 })} t`;
  if (unit === "quintal") return `${(kg / 100).toLocaleString("en-IN", { maximumFractionDigits: 1 })} q`;
  return `${kg.toLocaleString("en-IN", { maximumFractionDigits: 0 })} kg`;
}

export function pct(x: number | null | undefined, d = 1): string {
  return x === null || x === undefined || Number.isNaN(x) ? "–" : `${(x * 100).toFixed(d)}%`;
}

/** UTC ISO (naive or Z) → IST display string */
export function ist(iso: string | null | undefined, withDate = true): string {
  if (!iso) return "–";
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
  return d.toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
    ...(withDate ? { day: "numeric", month: "short" } : {}),
  }) + " IST";
}

export function hours(h: number | null | undefined): string {
  if (h === null || h === undefined) return "–";
  if (h < 1) return `${Math.round(h * 60)} min`;
  if (h < 48) return `${h.toFixed(h < 10 ? 1 : 0)} h`;
  return `${(h / 24).toFixed(1)} days`;
}

export function countdown(untilIso: string | null | undefined, nowMs = Date.now()): string {
  if (!untilIso) return "–";
  const ms = new Date(/[zZ]$/.test(untilIso) ? untilIso : `${untilIso}Z`).getTime() - nowMs;
  if (ms <= 0) return "expired";
  const m = Math.floor(ms / 60000);
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`;
}
