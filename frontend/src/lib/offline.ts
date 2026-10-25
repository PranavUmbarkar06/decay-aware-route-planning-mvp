// Offline queue (M1/M2). Scans and logs made offline are stored in IndexedDB with their real scan time and replayed
// in order through POST /sync when back online. `client_event_id` makes replays idempotent on the server.
import { get, set } from "idb-keyval";
import { api } from "./api";

export type QueuedOp = {
  op: "handover_start" | "handover_confirm" | "transit_scan" | "wastage";
  client_event_id: string;
  consignment_id?: string;
  handover_id?: string;
  payload: Record<string, unknown>;
  queued_at: string;
  label: string;
};

const KEY = "phl.queue";
const listeners = new Set<(n: number) => void>();
let memory: QueuedOp[] | null = null;     // fallback when IndexedDB is unavailable

async function read(): Promise<QueuedOp[]> {
  try {
    return ((await get(KEY)) as QueuedOp[] | undefined) ?? [];
  } catch {
    return memory ?? [];
  }
}

async function write(q: QueuedOp[]) {
  try {
    await set(KEY, q);
  } catch {
    memory = q;
  }
  listeners.forEach((l) => l(q.length));
}

export function newEventId(): string {
  return (crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`).slice(0, 64);
}

export async function enqueue(op: Omit<QueuedOp, "queued_at">) {
  const q = await read();
  q.push({ ...op, queued_at: new Date().toISOString() });
  await write(q);
}

export async function pending(): Promise<QueuedOp[]> {
  return read();
}

export function onQueueChange(fn: (n: number) => void): () => void {
  listeners.add(fn);
  read().then((q) => fn(q.length));
  return () => listeners.delete(fn);
}

let syncing = false;
export async function syncNow(): Promise<{ synced: number; failed: { label: string; message: string }[] }> {
  if (syncing) return { synced: 0, failed: [] };
  syncing = true;
  try {
    const q = await read();
    if (!q.length) return { synced: 0, failed: [] };
    const res = await api<{ client_event_id: string; ok: boolean; message: string }[]>("/sync", {
      body: q.map(({ op, client_event_id, consignment_id, handover_id, payload }) => ({ op, client_event_id, consignment_id, handover_id, payload })),
    });
    const ok = new Set(res.filter((r) => r.ok).map((r) => r.client_event_id));
    const failed = res.filter((r) => !r.ok).map((r) => ({ label: q.find((x) => x.client_event_id === r.client_event_id)?.label ?? r.client_event_id, message: r.message }));
    // Failed ops are dropped from the queue but reported to the user (they need a human decision, not a retry loop).
    await write([]);
    return { synced: ok.size, failed };
  } finally {
    syncing = false;
  }
}
