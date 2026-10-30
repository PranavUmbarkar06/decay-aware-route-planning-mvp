"""Dispatcher alert book: state machine, hysteresis, earliest-deadline-first queue, workload warnings (plan v2 §5b).

The system never executes a reroute without APPROVED (or MODIFIED) and then ACKNOWLEDGED by the driver.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from typing import Any

from .engine.decision import Buffers, DecisionWindow, tier_for, window_dict
from .store import log_event, row_dict

OPEN = {"ALERTED", "UNDER_REVIEW", "APPROVED", "MODIFIED", "SENT_TO_DRIVER"}
TRANSITIONS = {
    "review": ({"ALERTED"}, "UNDER_REVIEW"),
    "approve": ({"ALERTED", "UNDER_REVIEW"}, "APPROVED"),
    "modify": ({"ALERTED", "UNDER_REVIEW"}, "MODIFIED"),
    "reject": ({"ALERTED", "UNDER_REVIEW"}, "REJECTED"),
    "snooze": ({"ALERTED", "UNDER_REVIEW"}, "ALERTED"),
    "send": ({"APPROVED", "MODIFIED"}, "SENT_TO_DRIVER"),
    "acknowledge": ({"SENT_TO_DRIVER"}, "ACKNOWLEDGED"),
    "execute": ({"ACKNOWLEDGED"}, "EXECUTED"),
}
AUTO_APPROVE_ON_TIMEOUT = False   # deliberately off: no decision ⇒ truck continues on its current route

# Hysteresis thresholds for re-alerting an open alert
DEADLINE_SHIFT_MIN = 5.0
BENEFIT_CHANGE_FRAC = 0.20


def alert_id(shipment_id: str, disruption_ids: list[str]) -> str:
    return hashlib.sha1(f"{shipment_id}|{','.join(sorted(disruption_ids))}".encode()).hexdigest()[:10]


def _best_benefit(w: DecisionWindow) -> float:
    vals = [o.benefit_rs for o in w.options if math.isfinite(o.benefit_rs)]
    return max(vals) if vals else (math.inf if w.options else 0.0)


def upsert(c: sqlite3.Connection, shipment_id: str, w: DecisionWindow, now_h: float, option_arcs: list[list[int]]) -> dict | None:
    """Create, refresh (with hysteresis), supersede or expire the alert for this shipment's disruption set."""
    open_rows = [row_dict(r) for r in c.execute(
        "SELECT * FROM alerts WHERE shipment_id=? AND state IN (%s)" % ",".join("?" * len(OPEN)), (shipment_id, *OPEN))]
    if not w.needed:
        for r in open_rows:
            if r["state"] in ("ALERTED", "UNDER_REVIEW"):
                c.execute("UPDATE alerts SET state='SUPERSEDED', updated_h=? WHERE id=?", (now_h, r["id"]))
                log_event(c, r["id"], now_h, "system", "supersede", r["state"], "SUPERSEDED", None,
                          {"reason": w.reason or "decision no longer needed"})
        return None
    aid = alert_id(shipment_id, w.affecting)
    payload = window_dict(w)
    payload["option_arcs"] = option_arcs
    benefit = _best_benefit(w)
    for r in open_rows:   # a different disruption set supersedes older open alerts awaiting a decision
        if r["id"] != aid and r["state"] in ("ALERTED", "UNDER_REVIEW"):
            c.execute("UPDATE alerts SET state='SUPERSEDED', updated_h=? WHERE id=?", (now_h, r["id"]))
            log_event(c, r["id"], now_h, "system", "supersede", r["state"], "SUPERSEDED", None, {"by": aid})
    row = c.execute("SELECT * FROM alerts WHERE id=?", (aid,)).fetchone()
    if row is None or row["state"] in ("REJECTED", "SUPERSEDED", "EXPIRED", "EXECUTED"):
        if row is not None and row["state"] in ("REJECTED", "EXECUTED"):
            return row_dict(row)          # a human already decided this disruption set; do not nag
        c.execute("INSERT OR REPLACE INTO alerts(id, shipment_id, state, tier, created_h, updated_h, deadline_h, alert_at_h, "
                  "pnr_label, benefit_rs, disruption_ids, payload) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                  (aid, shipment_id, "ALERTED", w.tier, now_h, now_h, w.deadline_h, w.alert_at_h,
                   w.pnr.label if w.pnr else None, benefit if math.isfinite(benefit) else None,
                   json.dumps(w.affecting), json.dumps(payload)))
        log_event(c, aid, now_h, "system", "alert", None, "ALERTED", w.slack_min, {"tier": w.tier, "reason": w.reason})
    else:
        old_deadline = row["deadline_h"] or 0
        old_benefit = row["benefit_rs"] or 0
        shifted = abs((w.deadline_h or 0) - old_deadline) * 60 > DEADLINE_SHIFT_MIN
        changed = (math.isfinite(benefit) and old_benefit and abs(benefit - old_benefit) / abs(old_benefit) > BENEFIT_CHANGE_FRAC)
        tier_up = _tier_rank(w.tier) > _tier_rank(row["tier"])
        c.execute("UPDATE alerts SET tier=?, updated_h=?, deadline_h=?, alert_at_h=?, pnr_label=?, benefit_rs=?, payload=? WHERE id=?",
                  (w.tier, now_h, w.deadline_h, w.alert_at_h, w.pnr.label if w.pnr else None,
                   benefit if math.isfinite(benefit) else None, json.dumps(payload), aid))
        if shifted or changed or tier_up:
            log_event(c, aid, now_h, "system", "re_alert", row["state"], row["state"], w.slack_min,
                      {"deadline_shift": shifted, "benefit_change": bool(changed), "tier": w.tier})
    return row_dict(c.execute("SELECT * FROM alerts WHERE id=?", (aid,)).fetchone())


def _tier_rank(t: str | None) -> int:
    return {"NONE": 0, "MONITOR": 1, "ADVISORY": 2, "HIGH": 3, "CRITICAL": 4, "EXPIRED": 5}.get(t or "NONE", 0)


def expire_due(c: sqlite3.Connection, now_h: float) -> None:
    for r in c.execute("SELECT * FROM alerts WHERE state IN ('ALERTED','UNDER_REVIEW','APPROVED','MODIFIED')").fetchall():
        if r["deadline_h"] is not None and now_h > r["deadline_h"]:
            c.execute("UPDATE alerts SET state='EXPIRED', tier='EXPIRED', updated_h=? WHERE id=?", (now_h, r["id"]))
            log_event(c, r["id"], now_h, "system", "expire", r["state"], "EXPIRED", (r["deadline_h"] - now_h) * 60,
                      {"default": "truck continues on its current route (auto-approve is off)"})


def queue(c: sqlite3.Connection, now_h: float, buf: Buffers) -> dict[str, Any]:
    expire_due(c, now_h)
    rows = [row_dict(r) for r in c.execute(
        "SELECT * FROM alerts WHERE state IN (%s) ORDER BY deadline_h ASC" % ",".join("?" * len(OPEN)), tuple(OPEN))]
    pending = [r for r in rows if r["state"] in ("ALERTED", "UNDER_REVIEW")
               and not (r.get("snooze_until_h") and r["snooze_until_h"] > now_h)]
    # Earliest-deadline-first: a dispatcher works through pending alerts one by one, review time each.
    t = now_h
    warnings = []
    for r in pending:
        t += buf.review / 60
        r["slack_min"] = round((r["deadline_h"] - now_h) * 60, 1) if r["deadline_h"] is not None else None
        r["tier"] = tier_for(r["slack_min"], buf) if r["slack_min"] is not None else r["tier"]
        r["projected_review_done_h"] = t
        if r["deadline_h"] is not None and t > r["deadline_h"]:
            r["at_risk"] = True
            warnings.append(r["id"])
    for r in rows:
        if "slack_min" not in r and r["deadline_h"] is not None:
            r["slack_min"] = round((r["deadline_h"] - now_h) * 60, 1)
    workload_min = len(pending) * buf.review
    msg = (f"{len(warnings)} alert(s) will pass their deadline before they can be reviewed at {buf.review:.0f} min each"
           if warnings else None)
    return {"now_h": now_h, "alerts": rows, "pending": len(pending), "workload_min": workload_min,
            "at_risk": warnings, "warning": msg}


def act(c: sqlite3.Connection, aid: str, action: str, now_h: float, actor: str, *, option: int | None = None,
        until_h: float | None = None, note: str | None = None) -> dict:
    r = c.execute("SELECT * FROM alerts WHERE id=?", (aid,)).fetchone()
    if r is None:
        raise KeyError(aid)
    allowed, to = TRANSITIONS[action]
    if r["state"] not in allowed:
        raise ValueError(f"cannot {action} an alert in state {r['state']}")
    slack = (r["deadline_h"] - now_h) * 60 if r["deadline_h"] is not None else None
    payload = json.loads(r["payload"])
    if action in ("approve", "modify", "send") and r["deadline_h"] is not None and now_h > r["deadline_h"]:
        c.execute("UPDATE alerts SET state='EXPIRED', tier='EXPIRED', updated_h=? WHERE id=?", (now_h, aid))
        log_event(c, aid, now_h, actor, action + "_too_late", r["state"], "EXPIRED", slack, {})
        raise ValueError("deadline passed: this diversion is no longer reachable; re-plan from the truck's position")
    if action == "acknowledge":
        pnr = payload.get("pnr") or {}
        eta_lo = pnr.get("eta_lo_h")
        if eta_lo is not None and now_h > eta_lo - Buffers().manoeuvre / 60:
            c.execute("UPDATE alerts SET state='EXPIRED', tier='EXPIRED', ack_h=?, updated_h=? WHERE id=?", (now_h, now_h, aid))
            log_event(c, aid, now_h, actor, "acknowledge_late", r["state"], "EXPIRED", slack, {})
            raise ValueError("driver acknowledged after the point of no return; re-planning from current position")
    sets = {"state": to, "updated_h": now_h}
    if action in ("approve", "modify"):
        sets["chosen_option"] = option if (action == "modify" and option is not None) else _default_option(payload)
    if action == "snooze":
        sets["snooze_until_h"] = min(until_h or now_h + 0.25, r["deadline_h"] or math.inf)
    if action == "send":
        sets["sent_h"] = now_h
    if action == "acknowledge":
        sets["ack_h"] = now_h
    c.execute("UPDATE alerts SET " + ",".join(f"{k}=?" for k in sets) + " WHERE id=?", (*sets.values(), aid))
    log_event(c, aid, now_h, actor, action, r["state"], to, slack, {"option": sets.get("chosen_option"), "note": note})
    return row_dict(c.execute("SELECT * FROM alerts WHERE id=?", (aid,)).fetchone())


def _default_option(payload: dict) -> int:
    opts = payload.get("options") or []
    if not opts:
        return 0
    # Best net value among options still reachable (benefit is undefined when the current route is blocked).
    ok = [i for i, o in enumerate(opts) if o.get("reachable", True)] or list(range(len(opts)))
    return max(ok, key=lambda i: opts[i].get("net_value_rs") or float("-inf"))


REASON = {
    "blocked": {"en": "road blocked ahead", "hi": "आगे सड़क बंद है", "mr": "पुढे रस्ता बंद आहे", "te": "ముందు రహదారి మూసివేయబడింది"},
    "saves": {"en": "saves about ₹{v:,.0f} of produce value", "hi": "लगभग ₹{v:,.0f} के माल की बचत", "mr": "सुमारे ₹{v:,.0f} मालाची बचत",
              "te": "సుమారు ₹{v:,.0f} విలువైన సరుకు ఆదా"},
}
LANG = {
    "en": "Reroute: at {junction}, {km:.0f} km ahead, take the new route to {dest}. Reason: {reason}. Reply OK.",
    "hi": "मार्ग बदलें: {km:.0f} किमी आगे {junction} पर नया रास्ता लें ({dest})। कारण: {reason}। OK भेजें।",
    "mr": "मार्ग बदला: {km:.0f} किमी पुढे {junction} येथे नवीन मार्ग घ्या ({dest}). कारण: {reason}. OK पाठवा.",
    "te": "మార్గం మార్చండి: {km:.0f} కి.మీ. ముందు {junction} వద్ద కొత్త మార్గం తీసుకోండి ({dest}). కారణం: {reason}. OK పంపండి.",
}


def driver_messages(payload: dict, option_index: int, dest_name: str) -> dict[str, str]:
    opts = payload.get("options") or []
    op = opts[option_index] if 0 <= option_index < len(opts) else (payload.get("pnr") or {})
    key = "blocked" if not payload.get("stay_feasible") else "saves"
    return {k: v.format(junction=op.get("label") or "the next junction", km=op.get("km_ahead") or 0, dest=dest_name,
                        reason=REASON[key][k].format(v=op.get("benefit_rs") or 0))
            for k, v in LANG.items()}
