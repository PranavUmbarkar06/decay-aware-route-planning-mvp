import { useEffect, useId, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger"; busy?: boolean };
export function Button({ variant = "primary", busy, className = "", children, disabled, ...p }: BtnProps) {
  const v = {
    primary: "bg-brand text-brand-ink hover:brightness-110",
    secondary: "bg-surface-2 text-ink border border-line hover:bg-surface-3",
    ghost: "bg-transparent text-ink hover:bg-surface-3",
    danger: "bg-bad text-white hover:brightness-110",
  }[variant];
  return (
    <button {...p} disabled={disabled || busy} aria-busy={busy || undefined}
      className={`tap inline-flex items-center justify-center gap-2 rounded-xl px-4 font-semibold transition disabled:opacity-50 ${v} ${className}`}>
      {busy ? <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden /> : null}
      {children}
    </button>
  );
}

export function Card({ children, className = "", title, action }: { children: ReactNode; className?: string; title?: ReactNode; action?: ReactNode }) {
  return (
    <section className={`card p-4 ${className}`}>
      {title || action ? (
        <header className="mb-3 flex items-start justify-between gap-3">
          {title ? <h2 className="text-lg font-semibold leading-tight">{title}</h2> : <span />}
          {action}
        </header>
      ) : null}
      {children}
    </section>
  );
}

const PROV_STYLE: Record<string, string> = {
  REAL_FETCHED: "bg-good-soft text-good",
  REAL_DERIVED: "bg-good-soft text-good",
  USER_ENTERED: "bg-brand-soft text-brand",
  ASSUMPTION: "bg-warn-soft text-warn",
  SYNTHETIC_DEMO: "bg-demo-soft text-demo",
};
const PROV_LABEL: Record<string, string> = {
  REAL_FETCHED: "Real data", REAL_DERIVED: "From real data", USER_ENTERED: "Entered by a user",
  ASSUMPTION: "Assumption", SYNTHETIC_DEMO: "DEMO",
};
export function ProvenanceBadge({ p, className = "" }: { p?: string | null; className?: string }) {
  if (!p) return null;
  return (
    <span data-provenance={p} title={p}
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-bold tracking-wide ${PROV_STYLE[p] ?? "bg-surface-3 text-muted"} ${className}`}>
      {PROV_LABEL[p] ?? p}
    </span>
  );
}

const LIGHT: Record<string, { cls: string; icon: string }> = {
  GREEN: { cls: "bg-good-soft text-good border-good", icon: "●" },
  YELLOW: { cls: "bg-warn-soft text-warn border-warn", icon: "▲" },
  RED: { cls: "bg-bad-soft text-bad border-bad", icon: "■" },
};
export function TrafficLight({ light, hours }: { light: string; hours?: number }) {
  const { t } = useTranslation();
  const s = LIGHT[light] ?? LIGHT.YELLOW;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-lg border px-2 py-1 text-sm font-semibold ${s.cls}`} data-light={light}>
      <span aria-hidden>{s.icon}</span>
      <span>{t(`light.${light}`)}</span>
      {hours !== undefined ? <span className="font-normal">· {Math.round(hours)} h</span> : null}
    </span>
  );
}

export function Skeleton({ h = 20, className = "" }: { h?: number; className?: string }) {
  return <div className={`skeleton ${className}`} style={{ height: h }} aria-hidden />;
}

export function Loading({ rows = 3 }: { rows?: number }) {
  const { t } = useTranslation();
  return (
    <div role="status" aria-label={t("loading")} className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => <Skeleton key={i} h={56} />)}
    </div>
  );
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="card flex flex-col items-center gap-3 p-6 text-center">
      <div aria-hidden className="text-4xl">🧺</div>
      <p className="font-semibold">{title}</p>
      {children ? <div className="text-sm text-muted">{children}</div> : null}
      {action}
    </div>
  );
}

export function ErrorBox({ error, retry }: { error: unknown; retry?: () => void }) {
  const { t } = useTranslation();
  const msg = error instanceof Error ? error.message : t("error.generic");
  return (
    <div role="alert" className="flex items-center justify-between gap-3 rounded-xl border border-bad bg-bad-soft p-3 text-bad">
      <span>⚠ {msg}</span>
      {retry ? <Button variant="secondary" onClick={retry}>Retry</Button> : null}
    </div>
  );
}

export function Field({ label, hint, children, error }: { label: string; hint?: string; children: (id: string) => ReactNode; error?: string }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="font-semibold">{label}</label>
      {children(id)}
      {hint ? <p className="text-sm text-muted">{hint}</p> : null}
      {error ? <p className="text-sm text-bad" role="alert">{error}</p> : null}
    </div>
  );
}

export const inputCls = "tap w-full rounded-xl border border-line bg-surface-2 px-3 text-base text-ink placeholder:text-muted";

export function Modal({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal?.();
    if (!open && d.open) d.close?.();
  }, [open]);
  return (
    <dialog ref={ref} onClose={onClose} aria-label={title}
      className="m-auto w-[min(640px,calc(100vw-24px))] rounded-2xl border border-line bg-surface-2 p-0 text-ink backdrop:bg-black/50">
      <div className="flex items-center justify-between border-b border-line p-4">
        <h2 className="text-lg font-semibold">{title}</h2>
        <Button variant="ghost" onClick={onClose} aria-label="Close">✕</Button>
      </div>
      <div className="max-h-[70vh] overflow-y-auto p-4 text-sm leading-relaxed">{children}</div>
    </dialog>
  );
}

export function HowCalculated({ children, title }: { children: ReactNode; title?: string }) {
  const { t } = useTranslation();
  return <Disclosure label={t("app.howCalculated")} title={title ?? t("app.howCalculated")}>{children}</Disclosure>;
}

export function Disclosure({ label, title, children }: { label: string; title: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className="tap -my-2 text-left text-sm font-semibold text-brand underline underline-offset-4" onClick={() => setOpen(true)}>
        ⓘ {label}
      </button>
      <Modal open={open} onClose={() => setOpen(false)} title={title}>{children}</Modal>
    </>
  );
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: "good" | "bad" }) {
  return (
    <div className="card p-3">
      <div className="text-sm text-muted">{label}</div>
      <div className={`text-2xl font-bold tabular-nums ${tone === "good" ? "text-good" : tone === "bad" ? "text-bad" : ""}`}>{value}</div>
      {sub ? <div className="text-xs text-muted">{sub}</div> : null}
    </div>
  );
}

export function PageTitle({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <div className="mb-4">
      <h1 className="text-2xl font-bold leading-tight">{children}</h1>
      {sub ? <p className="mt-1 text-muted">{sub}</p> : null}
    </div>
  );
}
