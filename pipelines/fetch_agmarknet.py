"""Agmarknet 2.0.

1. Master data (states, districts, markets, commodities) from the public, captcha-free filter endpoint
   `GET https://api.agmarknet.gov.in/v1/daily-price-arrival/filters` (the endpoint the public report page
   uses to populate its dropdowns). REAL_FETCHED.
2. Arrivals/prices: the public "Daily Price and Arrival Report" requires a captcha (observed 2026-10-24).
   We do NOT automate it (ADR-015). Instead, files the project owner downloads by hand from
   https://agmarknet.gov.in/daily-price-and-arrival-report into `inputs/agmarknet_exports/` are ingested
   with provenance REAL_FETCHED (retrieval = manual_export) and checksummed.
"""
from __future__ import annotations

import json
import re
import sys

import pandas as pd
from app.core.config import commodities_config, geography

from pipelines.common import (
    PROCESSED,
    ROOT,
    AuditRecord,
    SourceMeta,
    fetch_cached,
    manifest_id,
    record,
    sha256_file,
    write_audit,
    write_csv_deterministic,
)

META = SourceMeta(
    source="agmarknet",
    licence="UNVERIFIED: no explicit data licence found on agmarknet.gov.in; Government of India portal. "
            "robots.txt (fetched) allows '/', disallows auth/admin paths. Treat as attribution-required.",
    terms_url="https://agmarknet.gov.in/robots.txt",
    notes="Agmarknet 2.0 (go-live 2025-11-07 per its filter metadata). Master endpoint is undocumented and may change.",
)
FILTERS_URL = "https://api.agmarknet.gov.in/v1/daily-price-arrival/filters"
EXPORT_DIR = ROOT / "inputs" / "agmarknet_exports"


def fetch_master(refresh: bool = False) -> dict:
    fetch_cached(META, "robots.txt", "https://agmarknet.gov.in/robots.txt", refresh=refresh)
    path, status = fetch_cached(META, "filters.json", FILTERS_URL, refresh=refresh, min_interval_s=2)
    if path is None:
        raise RuntimeError(f"Agmarknet filters unavailable ({status}) and no cache")
    return json.loads(path.read_text(encoding="utf-8"))["data"]


def build_master_tables(data: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    geo = geography().current
    sid = geo.agmarknet_state_id
    mid = manifest_id("agmarknet", "filters.json")
    dists = {d["id"]: d["district_name"] for d in data["district_data"] if d["state_id"] == sid}
    wanted = {d.agmarknet.lower(): d.name for d in geo.districts}
    found = {k: wanted[v.lower()] for k, v in dists.items() if v.lower() in wanted}
    missing = sorted(set(wanted.values()) - set(found.values()))
    if missing:
        print(f"WARNING: districts not found in Agmarknet master: {missing}", file=sys.stderr)
    rows = []
    for m in data["market_data"]:
        if m.get("district_id") in found:
            rows.append({
                "agmarknet_market_id": m["id"],
                "agmarknet_market_name": m["mkt_name"],
                "market_name_clean": re.sub(r"\s+", " ", m["mkt_name"]).strip(),
                "district": found[m["district_id"]],
                "agmarknet_district_id": m["district_id"],
                "agmarknet_state_id": sid,
                "provenance": "REAL_FETCHED",
                "source_manifest_id": mid,
            })
    markets = pd.DataFrame(rows)
    cfg = commodities_config().commodities
    by_id = {c["cmdt_id"]: c for c in data["cmdt_data"]}
    crow = []
    for key, c in cfg.items():
        src = by_id.get(c.agmarknet_cmdt_id)
        crow.append({"commodity": key, "agmarknet_cmdt_id": c.agmarknet_cmdt_id,
                     "agmarknet_cmdt_name": src["cmdt_name"] if src else None,
                     "verified_in_master": src is not None,
                     "provenance": "REAL_FETCHED", "source_manifest_id": mid})
    return markets, pd.DataFrame(crow)


ARRIVAL_COLS = ["date", "agmarknet_market_name", "commodity", "arrival_qty", "arrival_unit",
                "min_price", "max_price", "modal_price", "price_unit"]


def ingest_manual_exports() -> tuple[pd.DataFrame, list[str]]:
    """Parse any owner-downloaded report exports. Column names are matched loosely because the export
    format was not observable without solving the captcha; unparseable files are reported, not guessed."""
    notes: list[str] = []
    frames = []
    if not EXPORT_DIR.exists():
        return pd.DataFrame(columns=ARRIVAL_COLS + ["provenance", "source_manifest_id"]), ["no inputs/agmarknet_exports/ directory"]
    meta = SourceMeta("agmarknet_manual_exports", META.licence, META.terms_url,
                      "Report files downloaded by a human from agmarknet.gov.in (captcha solved by the human).")
    for f in sorted(EXPORT_DIR.glob("*")):
        if f.suffix.lower() not in {".csv", ".xlsx", ".xls"}:
            continue
        e = record(meta, f.name, f.read_bytes(), url="manual download from https://agmarknet.gov.in/daily-price-and-arrival-report",
                   retrieval="manual_export", extra={"original_path": str(f.relative_to(ROOT)), "sha256_check": sha256_file(f)})
        try:
            df = pd.read_csv(f) if f.suffix.lower() == ".csv" else pd.read_excel(f)
        except Exception as ex:  # noqa: BLE001
            notes.append(f"{f.name}: unreadable ({ex})")
            continue
        cols = {c: re.sub(r"[^a-z]", "", str(c).lower()) for c in df.columns}
        pick = {}
        for want, pats in {"date": ["arrivaldate", "reporteddate", "date"], "agmarknet_market_name": ["marketname", "market"],
                           "commodity": ["commodity"], "arrival_qty": ["arrivals", "arrival", "arrivalquantity"],
                           "arrival_unit": ["unitofarrivals", "arrivalunit", "unit"], "min_price": ["minprice", "minimumprice"],
                           "max_price": ["maxprice", "maximumprice"], "modal_price": ["modalprice"]}.items():
            for c, norm in cols.items():
                if any(norm == p or norm.startswith(p) for p in pats):
                    pick[want] = c
                    break
        if not {"date", "agmarknet_market_name", "commodity"} <= set(pick):
            notes.append(f"{f.name}: columns not recognised ({list(df.columns)[:12]}); not ingested")
            continue
        out = pd.DataFrame({k: df[v] for k, v in pick.items()})
        for c in ARRIVAL_COLS:
            if c not in out:
                out[c] = None
        out["provenance"] = "REAL_FETCHED"
        out["source_manifest_id"] = e["manifest_id"]
        frames.append(out[ARRIVAL_COLS + ["provenance", "source_manifest_id"]])
        notes.append(f"{f.name}: {len(out)} rows ingested")
    if not frames:
        return pd.DataFrame(columns=ARRIVAL_COLS + ["provenance", "source_manifest_id"]), notes or ["no export files present"]
    return pd.concat(frames, ignore_index=True), notes


def run(refresh: bool = False) -> None:
    data = fetch_master(refresh)
    markets, comms = build_master_tables(data)
    write_csv_deterministic(markets, PROCESSED / "agmarknet_markets.csv", ["agmarknet_market_id"])
    write_csv_deterministic(comms, PROCESSED / "agmarknet_commodities.csv", ["commodity"])
    rng = data["range_data"][0]
    arrivals, notes = ingest_manual_exports()
    write_csv_deterministic(arrivals.astype(str) if len(arrivals) else arrivals,
                            PROCESSED / "agmarknet_arrivals.csv", ["date", "agmarknet_market_name", "commodity"] if len(arrivals) else ARRIVAL_COLS[:1])
    per_district = markets.groupby("district").size().to_dict()
    write_audit("agmarknet_master", AuditRecord(
        need="Market list for pilot geography (business nodes)",
        source_name="Agmarknet 2.0 filter/master endpoint",
        status="AVAILABLE", access="HTTP GET JSON (undocumented endpoint used by the public report page)",
        auth="none", licence=META.licence,
        coverage=f"{len(markets)} markets in pilot districts: {per_district}; commodities verified: "
                 f"{comms[['commodity','agmarknet_cmdt_name']].values.tolist()}",
        tried=[f"GET {FILTERS_URL}"], urls=[FILTERS_URL, "https://agmarknet.gov.in/robots.txt"],
        rate_limits="none published; pipeline uses ≥2 s between calls and caches",
        freshness="master list as of fetch date",
        known_problems="Names are market labels, not coordinates; 'APMC X' labels must be geocoded (Phase 2). "
                       "Includes private markets (e.g. 'M/S … Pvt Ltd'). Endpoint undocumented → may change.",
        flags=["UNDOCUMENTED_API", "LICENCE_UNVERIFIED"]))
    write_audit("agmarknet_arrivals", AuditRecord(
        need="Market arrivals & prices by commodity, market, date (M4 crowd meter, demand proxy)",
        source_name="Agmarknet 2.0 Daily Price and Arrival Report",
        status="PARTIAL" if len(arrivals) else "RESTRICTED",
        access="Public web report gated by captcha; manual export ingestion only",
        auth="captcha (human)", licence=META.licence,
        coverage=(f"{len(arrivals)} rows from manual exports" if len(arrivals) else "none ingested")
                 + f". Portal date ranges: arrival from {rng['arrival']['from_date']}, both price+arrival from "
                   f"{rng['both']['from_date']}; max 1-year span per query.",
        tried=["Opened https://agmarknet.gov.in/daily-price-and-arrival-report in a browser: 'Enter captcha' field present",
               "Did not attempt automated access to report endpoints (ADR-015)"] + notes,
        why_failed="Captcha-protected; automating it would circumvent bot-detection.",
        fallback="Owner downloads report exports by hand into inputs/agmarknet_exports/ (ingested automatically), "
                 "or registers a data.gov.in API key (prices only, see datagov_mandi). Until then M4 shows 'no data' "
                 "and the demo uses SYNTHETIC_DEMO arrivals with a DEMO badge.",
        urls=["https://agmarknet.gov.in/daily-price-and-arrival-report"],
        known_problems="Arrivals may be missing for some market-days; units (quintal/tonne) must be read per row.",
        flags=["CAPTCHA", "MANUAL_STEP_REQUIRED"]))
    print(f"agmarknet: {len(markets)} pilot markets; {len(arrivals)} arrival rows; notes: {notes}")


if __name__ == "__main__":
    run(refresh="--refresh" in sys.argv)
