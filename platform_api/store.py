"""SQLite persistence: dispatcher alerts + audit trail, shipment outcomes (plan v2 §5b.7, §8.6)."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "app" / "platform.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
  id TEXT PRIMARY KEY, shipment_id TEXT, state TEXT, tier TEXT, created_h REAL, updated_h REAL,
  deadline_h REAL, alert_at_h REAL, pnr_label TEXT, benefit_rs REAL, disruption_ids TEXT,
  payload TEXT, chosen_option INTEGER, snooze_until_h REAL, sent_h REAL, ack_h REAL
);
CREATE TABLE IF NOT EXISTS alert_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, alert_id TEXT, at_h REAL, wall_utc TEXT, actor TEXT,
  action TEXT, from_state TEXT, to_state TEXT, slack_min REAL, detail TEXT
);
CREATE TABLE IF NOT EXISTS outcomes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, shipment_id TEXT, crop TEXT, recorded_utc TEXT, payload TEXT
);
"""


def conn() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def wall() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def log_event(c: sqlite3.Connection, alert_id: str, at_h: float, actor: str, action: str, frm: str | None, to: str | None,
              slack_min: float | None, detail: dict | None = None) -> None:
    c.execute("INSERT INTO alert_events(alert_id, at_h, wall_utc, actor, action, from_state, to_state, slack_min, detail) "
              "VALUES (?,?,?,?,?,?,?,?,?)", (alert_id, at_h, wall(), actor, action, frm, to, slack_min, json.dumps(detail or {})))


def row_dict(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    for k in ("payload", "disruption_ids", "detail"):
        if k in d and isinstance(d[k], str):
            try:
                d[k] = json.loads(d[k])
            except json.JSONDecodeError:
                pass
    return d
