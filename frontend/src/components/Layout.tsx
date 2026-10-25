import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useSession } from "../lib/session";
import { getUnit, ist, setUnit, type Unit } from "../lib/format";
import { useState } from "react";

const NAV: Record<string, { to: string; key: string; icon: string }[]> = {
  FARMER: [{ to: "/", key: "nav.home", icon: "🏠" }, { to: "/lots/new", key: "nav.new", icon: "➕" }, { to: "/lots", key: "nav.lots", icon: "📦" }, { to: "/crowd", key: "nav.crowd", icon: "📊" }],
  SUPERVISOR: [{ to: "/", key: "nav.home", icon: "🏠" }, { to: "/scan", key: "nav.scan", icon: "📷" }, { to: "/storage", key: "nav.storage", icon: "🚦" }, { to: "/crowd", key: "nav.crowd", icon: "📊" }, { to: "/rescue", key: "nav.rescue", icon: "🤝" }],
  WAREHOUSE: [{ to: "/", key: "nav.home", icon: "🏠" }, { to: "/scan", key: "nav.scan", icon: "📷" }, { to: "/storage", key: "nav.storage", icon: "🚦" }, { to: "/rescue", key: "nav.rescue", icon: "🤝" }],
  DISPATCHER: [{ to: "/", key: "nav.home", icon: "🏠" }, { to: "/advisor", key: "nav.advisor", icon: "🧭" }, { to: "/crowd", key: "nav.crowd", icon: "📊" }, { to: "/lab", key: "nav.lab", icon: "🧪" }, { to: "/scan", key: "nav.scan", icon: "📷" }],
  NGO: [{ to: "/", key: "nav.home", icon: "🏠" }, { to: "/rescue", key: "nav.rescue", icon: "🤝" }, { to: "/scan", key: "nav.scan", icon: "📷" }],
  TRANSPORTER: [{ to: "/", key: "nav.home", icon: "🏠" }, { to: "/scan", key: "nav.scan", icon: "📷" }],
  ADMIN: [{ to: "/", key: "nav.home", icon: "🏠" }, { to: "/lab", key: "nav.lab", icon: "🧪" }, { to: "/admin", key: "nav.admin", icon: "🛠" }, { to: "/crowd", key: "nav.crowd", icon: "📊" }, { to: "/advisor", key: "nav.advisor", icon: "🧭" }],
};

export function Banners() {
  const { t } = useTranslation();
  const { meta, online, queued, sync, demoClock, serverNow } = useSession();
  return (
    <div className="sticky top-0 z-30">
      {meta?.demo_mode ? (
        <div className="bg-demo-soft px-4 py-1.5 text-center text-sm font-bold text-demo" role="note" data-testid="demo-banner">
          {t("app.demoBanner")}
        </div>
      ) : null}
      {meta?.auth_mode === "dev_stub" ? (
        <div className="bg-warn-soft px-4 py-1 text-center text-xs font-semibold text-warn" role="note" data-testid="devauth-banner">{t("app.devAuth")}</div>
      ) : null}
      {demoClock ? (
        <div className="bg-surface-3 px-4 py-1 text-center text-xs text-ink-2">
          {t("app.demoClock")}: {ist(new Date(serverNow()).toISOString().slice(0, 19))} · inside the weather replay window
        </div>
      ) : null}
      {!online || queued > 0 ? (
        <div className="flex items-center justify-center gap-3 bg-bad-soft px-4 py-1.5 text-sm text-bad" role="status" data-testid="offline-banner">
          <span>{!online ? t("app.offline") : t("app.queued", { count: queued })}</span>
          {online && queued > 0 ? <button className="tap underline" onClick={() => void sync()}>{t("app.syncNow")}</button> : null}
        </div>
      ) : null}
    </div>
  );
}

export function Layout() {
  const { t } = useTranslation();
  const { meta, user, signOut, toasts, dismissToast } = useSession();
  const nav = NAV[user?.role ?? ""] ?? [];
  const navigate = useNavigate();
  const [unit, setU] = useState<Unit>(getUnit());
  return (
    <div className="flex min-h-full flex-col">
      <Banners />
      <header className="border-b border-line bg-surface-2">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-2 px-4 py-2">
          <NavLink to="/" className="flex min-w-0 items-center gap-2 font-bold">
            <img src={meta?.logo_path ?? "/logo-placeholder.svg"} alt="" className="size-8" />
            <span className="truncate text-sm sm:text-base">{meta?.product_name ?? "PHL Platform"}</span>
          </NavLink>
          <div className="flex items-center gap-1">
            <select aria-label="Weight unit" className="tap rounded-lg border border-line bg-surface-2 px-2 text-sm" value={unit}
              onChange={(e) => { setUnit(e.target.value as Unit); setU(e.target.value as Unit); window.dispatchEvent(new Event("phl-unit")); }}>
              <option value="kg">kg</option><option value="quintal">quintal</option><option value="tonne">tonne</option>
            </select>
            <NavLink to="/help" className="tap inline-flex items-center rounded-lg px-2 text-sm">{t("app.help")}</NavLink>
            {user ? <button className="tap rounded-lg px-2 text-sm" onClick={() => { signOut(); navigate("/welcome"); }}>{t("app.signOut")}</button> : null}
          </div>
        </div>
        {nav.length ? (
          <nav aria-label="Main" className="mx-auto flex max-w-5xl gap-1 overflow-x-auto px-2 pb-1">
            {nav.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.to === "/" || n.to === "/lots"}
                className={({ isActive }) => `tap flex shrink-0 items-center gap-1.5 rounded-lg px-3 text-sm font-semibold ${isActive ? "bg-brand-soft text-brand" : "text-ink-2"}`}>
                <span aria-hidden>{n.icon}</span>{t(n.key)}
              </NavLink>
            ))}
            <NavLink to="/demo" className={({ isActive }) => `tap flex shrink-0 items-center gap-1.5 rounded-lg px-3 text-sm font-semibold ${isActive ? "bg-brand-soft text-brand" : "text-ink-2"}`}>🎬 {t("nav.demo")}</NavLink>
            <NavLink to="/evidence" className={({ isActive }) => `tap flex shrink-0 items-center gap-1.5 rounded-lg px-3 text-sm font-semibold ${isActive ? "bg-brand-soft text-brand" : "text-ink-2"}`}>📑 {t("nav.evidence")}</NavLink>
          </nav>
        ) : null}
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-4" id="main">
        <Outlet />
      </main>
      <footer className="border-t border-line px-4 py-3 text-xs text-muted">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-2">
          <span>{meta?.attributions?.join(" · ")}</span>
          <span className="flex gap-3">
            <NavLink to="/report-problem" className="underline">{t("app.report")}</NavLink>
            <NavLink to="/evidence" className="underline">{t("nav.evidence")}</NavLink>
            <span>v{meta?.version}</span>
          </span>
        </div>
      </footer>
      <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 px-4">
        {toasts.map((x) => (
          <div key={x.id} className={`pointer-events-auto flex w-full max-w-md items-center justify-between gap-3 rounded-xl px-4 py-3 shadow-lg ${x.tone === "bad" ? "bg-bad text-white" : x.tone === "good" ? "bg-good text-white" : "bg-ink text-surface"}`}>
            <span>{x.msg}</span>
            <span className="flex gap-2">
              {x.undo ? <button className="tap font-bold underline" onClick={() => { x.undo?.(); dismissToast(x.id); }}>{t("waste.undo")}</button> : null}
              <button className="tap" aria-label="Dismiss" onClick={() => dismissToast(x.id)}>✕</button>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
