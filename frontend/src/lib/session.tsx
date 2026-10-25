import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, getToken, setToken } from "./api";
import { onQueueChange, syncNow } from "./offline";

export type User = { id: string; phone: string; role: string; name: string | null; language: string; district: string | null;
  home_node_id: string | null; provenance: string };
export type Meta = { product_name: string; version: string; demo_mode: boolean; auth_mode: string; logo_path: string;
  map: { tile_url: string; attribution: string }; attributions: string[]; commodities: Record<string, string>;
  provenance_legend: Record<string, string>; units: string[] };

type Ctx = {
  meta: Meta | null; user: User | null; ready: boolean; online: boolean; queued: number; clockOffsetMs: number;
  demoClock: boolean; signIn: (token: string, user: User) => void; signOut: () => void; refreshUser: () => Promise<void>;
  serverNow: () => number; toast: (msg: string, opts?: { undo?: () => void; tone?: "good" | "bad" | "info" }) => void;
  toasts: Toast[]; dismissToast: (id: number) => void; sync: () => Promise<void>;
};
export type Toast = { id: number; msg: string; undo?: () => void; tone: "good" | "bad" | "info" };

const SessionCtx = createContext<Ctx | null>(null);
let toastSeq = 1;

export function SessionProvider({ children }: { children: ReactNode }) {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [online, setOnline] = useState(typeof navigator === "undefined" ? true : navigator.onLine);
  const [queued, setQueued] = useState(0);
  const [clockOffsetMs, setOffset] = useState(0);
  const [demoClock, setDemoClock] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);

  const toast = useCallback((msg: string, opts: { undo?: () => void; tone?: "good" | "bad" | "info" } = {}) => {
    const id = toastSeq++;
    setToasts((t) => [...t, { id, msg, undo: opts.undo, tone: opts.tone ?? "info" }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), opts.undo ? 10000 : 5000);
  }, []);
  const dismissToast = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);

  const refreshUser = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      return;
    }
    try {
      setUser(await api<User>("/me"));
    } catch {
      setUser(null);
    }
  }, []);

  const sync = useCallback(async () => {
    try {
      const r = await syncNow();
      if (r.synced) toast(`Synced ${r.synced} offline action(s)`, { tone: "good" });
      r.failed.forEach((f) => toast(`Could not sync “${f.label}”: ${f.message}`, { tone: "bad" }));
    } catch {
      /* still offline */
    }
  }, [toast]);

  useEffect(() => {
    (async () => {
      try {
        setMeta(await api<Meta>("/meta"));
        const c = await api<{ now_utc: string; demo_clock: boolean }>("/clock");
        setOffset(new Date(`${c.now_utc}Z`).getTime() - Date.now());
        setDemoClock(c.demo_clock);
      } catch {
        /* offline first load: meta unavailable */
      }
      await refreshUser();
      setReady(true);
    })();
  }, [refreshUser]);

  useEffect(() => {
    const on = () => {
      setOnline(true);
      void sync();
    };
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    const unsub = onQueueChange(setQueued);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
      unsub();
    };
  }, [sync]);

  const value = useMemo<Ctx>(() => ({
    meta, user, ready, online, queued, clockOffsetMs, demoClock, toasts, toast, dismissToast, refreshUser, sync,
    signIn: (token, u) => {
      setToken(token);
      setUser(u);
    },
    signOut: () => {
      setToken(null);
      setUser(null);
    },
    serverNow: () => Date.now() + clockOffsetMs,
  }), [meta, user, ready, online, queued, clockOffsetMs, demoClock, toasts, toast, dismissToast, refreshUser, sync]);
  return <SessionCtx.Provider value={value}>{children}</SessionCtx.Provider>;
}

export function useSession(): Ctx {
  const c = useContext(SessionCtx);
  if (!c) throw new Error("SessionProvider missing");
  return c;
}
