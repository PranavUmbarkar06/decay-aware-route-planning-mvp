"""Agmarknet 2.0.

1. Master data (states, districts, markets, commodities) from the public, captcha-free filter endpoint
   `GET https://api.agmarknet.gov.in/v1/daily-price-arrival/filters` (the endpoint the public report page
   uses to populate its dropdowns). REAL_FETCHED.
2. Arrivals/prices: the public "Daily Price and Arrival Report" requires a captcha (observed 2026-10-24).
   We do NOT automate it (ADR-015). Report CSVs the project owner downloads by hand are ingested with
   provenance REAL_FETCHED (retrieval = manual_export) and checksummed. Files are discovered in
   `inputs/agmarknet_exports/` and directly in `inputs/` (any *.csv whose first line carries the report
   title "Daily Price Arrival Report"). `inputs/` is read-only: files are never moved or edited.

Observed export format (2026-10-25): line 1 = report title, line 2 = header
`State/UT,District,Market,Commodity Group,Commodity,Variety,Grade,Min Price,Max Price,Modal Price,
Price Unit,Arrival Quantity,Arrival Unit,Arrival Date`; numbers use thousands separators; dates DD-MM-YYYY.
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
EXPORT_META = SourceMeta(
    "agmarknet_manual_exports", META.licence, META.terms_url,
    "Daily Price and Arrival Report CSVs downloaded by the project owner from agmarknet.gov.in (captcha solved by a human).",
)
FILTERS_URL = "https://api.agmarknet.gov.in/v1/daily-price-arrival/filters"
REPORT_URL = "https://agmarknet.gov.in/daily-price-and-arrival-report"
EXPORT_DIRS = [ROOT / "inputs" / "agmarknet_exports", ROOT / "inputs"]
TITLE = "Daily Price Arrival Report"
HEADER = ["State/UT", "District", "Market", "Commodity Group", "Commodity", "Variety", "Grade", "Min Price",
          "Max Price", "Modal Price", "Price Unit", "Arrival Quantity", "Arrival Unit", "Arrival Date"]
UNIT_TO_KG = {"metric tonnes": 1000.0, "tonnes": 1000.0, "quintal": 100.0, "quintals": 100.0, "kg": 1.0, "kgs": 1.0}
PRICE_UNIT_TO_KG = {"rs./quintal": 100.0, "rs./kg": 1.0}


def fetch_master(refresh: bool = False) -> dict:
    fetch_cached(META, "robots.txt", "https://agmarknet.gov.in/robots.txt", refresh=refresh)
    path, status = fetch_cached(META, "filters.json", FILTERS_URL, refresh=refresh, min_interval_s=2)
    if path is None:
        raise RuntimeError(f"Agmarknet filters unavailable ({status}) and no cache")
    return json.loads(path.read_text(encoding="utf-8"))["data"]


def clean_name(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()


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
    rows = [{
        "agmarknet_market_id": m["id"],
        "agmarknet_market_name": m["mkt_name"],
        "market_name_clean": clean_name(m["mkt_name"]),
        "district": found[m["district_id"]],
        "agmarknet_district_id": m["district_id"],
        "agmarknet_state_id": sid,
        "provenance": "REAL_FETCHED",
        "source_manifest_id": mid,
    } for m in data["market_data"] if m.get("district_id") in found]
    markets = pd.DataFrame(rows)
    cfg = commodities_config().commodities
    by_id = {c["cmdt_id"]: c for c in data["cmdt_data"]}
    crow = [{"commodity": key, "agmarknet_cmdt_id": c.agmarknet_cmdt_id,
             "agmarknet_cmdt_name": by_id[c.agmarknet_cmdt_id]["cmdt_name"] if c.agmarknet_cmdt_id in by_id else None,
             "verified_in_master": c.agmarknet_cmdt_id in by_id,
             "provenance": "REAL_FETCHED", "source_manifest_id": mid} for key, c in cfg.items()]
    return markets, pd.DataFrame(crow)


ARRIVAL_COLS = ["arrival_date", "district", "market_name_clean", "commodity", "commodity_agmarknet", "variety",
                "grade", "min_price_rs_per_q", "max_price_rs_per_q", "modal_price_rs_per_q", "price_unit",
                "arrival_qty", "arrival_unit", "arrival_kg", "in_pilot_district", "in_pilot_commodity",
                "provenance", "source_manifest_id", "source_file"]


def discover_exports() -> list:
    files = []
    for d in EXPORT_DIRS:
        if not d.exists():
            continue
        for f in sorted(d.glob("*.csv")):
            with open(f, encoding="utf-8-sig", errors="replace") as fh:
                if TITLE.lower() in fh.readline().lower():
                    files.append(f)
    return files


def parse_export(f) -> pd.DataFrame:
    """Strict parser: the header row must match the observed format exactly, otherwise the file is
    rejected with a clear message (never guessed)."""
    df = pd.read_csv(f, skiprows=1, thousands=",", encoding="utf-8-sig", dtype={"Arrival Date": str})
    df = df.dropna(how="all")
    if list(df.columns) != HEADER:
        raise ValueError(f"unexpected columns {list(df.columns)}; expected {HEADER}")
    return df


def ingest_manual_exports() -> tuple[pd.DataFrame, list[str]]:
    notes: list[str] = []
    files = discover_exports()
    if not files:
        return pd.DataFrame(columns=ARRIVAL_COLS), ["no report CSVs found in inputs/ or inputs/agmarknet_exports/"]
    geo = geography().current
    pilot_d = {d.agmarknet.lower(): d.name for d in geo.districts} | {d.name.lower(): d.name for d in geo.districts}
    name_to_key = {c.label.lower(): k for k, c in commodities_config().commodities.items()}
    name_to_key |= {k: k for k in commodities_config().commodities}
    frames = []
    for f in files:
        e = record(EXPORT_META, f.name, f.read_bytes(), url=f"manual download from {REPORT_URL}",
                   retrieval="manual_export", extra={"original_path": str(f.relative_to(ROOT)).replace("\\", "/")})
        try:
            df = parse_export(f)
        except Exception as ex:  # noqa: BLE001
            notes.append(f"{f.name}: REJECTED ({ex})")
            continue
        out = pd.DataFrame({
            "arrival_date": pd.to_datetime(df["Arrival Date"], format="%d-%m-%Y", errors="coerce").dt.strftime("%Y-%m-%d"),
            "district": df["District"].map(lambda s: pilot_d.get(str(s).strip().lower(), str(s).strip())),
            "market_name_clean": df["Market"].map(clean_name),
            "commodity_agmarknet": df["Commodity"].map(clean_name),
            "variety": df["Variety"].map(clean_name),
            "grade": df["Grade"].map(clean_name),
            "min_price_rs_per_q": pd.to_numeric(df["Min Price"], errors="coerce"),
            "max_price_rs_per_q": pd.to_numeric(df["Max Price"], errors="coerce"),
            "modal_price_rs_per_q": pd.to_numeric(df["Modal Price"], errors="coerce"),
            "price_unit": df["Price Unit"].map(clean_name),
            "arrival_qty": pd.to_numeric(df["Arrival Quantity"], errors="coerce"),
            "arrival_unit": df["Arrival Unit"].map(clean_name),
        })
        out["commodity"] = out["commodity_agmarknet"].str.lower().map(lambda s: name_to_key.get(s, s))
        factor = out["arrival_unit"].str.lower().map(UNIT_TO_KG)
        out["arrival_kg"] = out["arrival_qty"] * factor
        unknown_units = sorted(out.loc[factor.isna(), "arrival_unit"].dropna().unique())
        if unknown_units:
            notes.append(f"{f.name}: unknown arrival unit(s) {unknown_units} → arrival_kg left empty (not guessed)")
        bad_price_units = sorted(set(out["price_unit"].str.lower()) - set(PRICE_UNIT_TO_KG))
        if bad_price_units:
            notes.append(f"{f.name}: unexpected price unit(s) {bad_price_units}")
        bad_dates = int(out["arrival_date"].isna().sum())
        if bad_dates:
            notes.append(f"{f.name}: {bad_dates} rows with unparseable dates dropped")
            out = out.dropna(subset=["arrival_date"])
        out["in_pilot_district"] = out["district"].str.lower().isin({n.lower() for n in pilot_d.values()})
        out["in_pilot_commodity"] = out["commodity"].isin(commodities_config().commodities.keys())
        out["provenance"] = "REAL_FETCHED"
        out["source_manifest_id"] = e["manifest_id"]
        out["source_file"] = e["original_path"]
        frames.append(out[ARRIVAL_COLS])
        notes.append(f"{f.name}: {len(out)} rows ({out['commodity'].unique().tolist()}, "
                     f"{out['arrival_date'].min()}..{out['arrival_date'].max()})")
    if not frames:
        return pd.DataFrame(columns=ARRIVAL_COLS), notes
    allrows = pd.concat(frames, ignore_index=True)
    # The same report row can appear in several exports (e.g. a one-day export inside a full-year one).
    key = ["arrival_date", "market_name_clean", "commodity", "variety", "grade"]
    dupes = allrows.duplicated(key, keep=False)
    conflict = allrows[dupes].groupby(key)[["arrival_qty", "modal_price_rs_per_q"]].nunique().gt(1).any(axis=1)
    if conflict.any():
        notes.append(f"{int(conflict.sum())} duplicated keys disagree across files; first file (sorted name) kept")
    before = len(allrows)
    allrows = allrows.sort_values(["source_file"]).drop_duplicates(key, keep="first")
    if before != len(allrows):
        notes.append(f"{before - len(allrows)} duplicate rows across export files removed")
    return allrows, notes


def daily_arrivals(rows: pd.DataFrame) -> pd.DataFrame:
    """Market × commodity × day totals (summed over varieties/grades). REAL_DERIVED."""
    g = rows.groupby(["arrival_date", "district", "market_name_clean", "commodity"], as_index=False).agg(
        arrival_kg=("arrival_kg", lambda s: s.sum(min_count=1)),
        n_report_rows=("arrival_kg", "size"),
        modal_price_rs_per_q_min=("modal_price_rs_per_q", "min"),
        modal_price_rs_per_q_max=("modal_price_rs_per_q", "max"),
        in_pilot_district=("in_pilot_district", "first"),
        in_pilot_commodity=("in_pilot_commodity", "first"),
        source_manifest_id=("source_manifest_id", lambda s: ";".join(sorted(set(s)))),
    )
    g["provenance"] = "REAL_DERIVED"
    g["derivation"] = "sum of report rows over variety and grade (pipelines/fetch_agmarknet.daily_arrivals)"
    return g


def run(refresh: bool = False) -> None:
    data = fetch_master(refresh)
    markets, comms = build_master_tables(data)
    write_csv_deterministic(markets, PROCESSED / "agmarknet_markets.csv", ["agmarknet_market_id"])
    write_csv_deterministic(comms, PROCESSED / "agmarknet_commodities.csv", ["commodity"])
    rng = data["range_data"][0]
    rows, notes = ingest_manual_exports()
    key = ["arrival_date", "market_name_clean", "commodity", "variety", "grade"]
    write_csv_deterministic(rows, PROCESSED / "agmarknet_arrivals.csv", key)
    daily = daily_arrivals(rows) if len(rows) else pd.DataFrame()
    if len(daily):
        write_csv_deterministic(daily, PROCESSED / "agmarknet_arrivals_daily.csv",
                                ["arrival_date", "market_name_clean", "commodity"])

    # Coverage by pilot commodity × district (what M4 can and cannot show)
    geo = geography().current
    cov_lines, gaps = [], []
    for ck in commodities_config().commodities:
        sub = daily[daily["commodity"] == ck] if len(daily) else pd.DataFrame()
        if not len(sub):
            gaps.append(f"{ck}: no export supplied")
            continue
        for d in geo.districts:
            sd = sub[sub["district"] == d.name]
            if len(sd):
                cov_lines.append(f"{ck}/{d.name}: {sd['market_name_clean'].nunique()} market(s), {len(sd)} market-days, "
                                 f"{sd['arrival_date'].min()}..{sd['arrival_date'].max()}")
            else:
                gaps.append(f"{ck}/{d.name}: 0 rows in export")
    unmatched = sorted(set(rows["market_name_clean"]) - set(markets["market_name_clean"])) if len(rows) else []
    if unmatched:
        notes.append(f"markets in exports not in master list: {unmatched}")
    pilot_ok = [c for c in commodities_config().commodities if len(daily) and (daily["commodity"] == c).any()]
    status = "PARTIAL" if pilot_ok else "RESTRICTED"

    per_district = markets.groupby("district").size().to_dict()
    write_audit("agmarknet_master", AuditRecord(
        need="Market list for pilot geography (business nodes)",
        source_name="Agmarknet 2.0 filter/master endpoint",
        status="AVAILABLE", access="HTTP GET JSON (undocumented endpoint used by the public report page)",
        auth="none", licence=META.licence,
        coverage=f"{len(markets)} markets in pilot districts: {per_district}; commodities verified: "
                 f"{comms[['commodity', 'agmarknet_cmdt_name']].values.tolist()}",
        tried=[f"GET {FILTERS_URL}"], urls=[FILTERS_URL, "https://agmarknet.gov.in/robots.txt"],
        rate_limits="none published; pipeline uses ≥2 s between calls and caches",
        freshness="master list as of fetch date",
        known_problems="Names are market labels, not coordinates; must be geocoded (Phase 2). "
                       "Includes private markets (e.g. 'M/S … Pvt Ltd'). Endpoint undocumented → may change.",
        flags=["UNDOCUMENTED_API", "LICENCE_UNVERIFIED"]))
    write_audit("agmarknet_arrivals", AuditRecord(
        need="Market arrivals & prices by commodity, market, date (M4 crowd meter, demand proxy)",
        source_name="Agmarknet 2.0 Daily Price and Arrival Report (manual CSV exports)",
        status=status,
        access="Public web report gated by captcha; owner downloads CSVs by hand; pipeline ingests them",
        auth="captcha (human)", licence=META.licence,
        coverage=(f"{len(rows)} report rows → {len(daily)} market-commodity-days. " if len(rows) else "none. ")
                 + " | ".join(cov_lines)
                 + f". Portal limits: price+arrival ('Both') only from {rng['both']['from_date']}; ≤1-year span per query.",
        tried=[f"Browser check of {REPORT_URL}: 'Enter captcha' field present (2026-10-24)",
               "No automated access to report endpoints (ADR-015)"] + notes,
        why_failed="Captcha-protected; automating it would circumvent bot-detection. Remaining gaps: " + "; ".join(gaps),
        fallback="Districts/commodities without rows: M4 shows 'no data' (never imputed). Orange: owner to export "
                 "Fruits → Orange the same way. Data before 2025-11-07 would need the 'Arrival' or 'Price' report types.",
        urls=[REPORT_URL],
        freshness=f"latest arrival date in exports: {rows['arrival_date'].max() if len(rows) else 'n/a'}",
        known_problems="Several rows per market-day (one per variety). Not every market reports every day; a missing "
                       "day is 'not reported', not 'zero arrivals'. Potato is ingested but is not a pilot commodity.",
        flags=["CAPTCHA", "MANUAL_STEP_REQUIRED"]))
    print(f"agmarknet: {len(markets)} pilot markets; {len(rows)} arrival rows; {len(daily)} market-days")
    for n in notes:
        print("  -", n)
    for g in gaps:
        print("  GAP", g)


if __name__ == "__main__":
    run(refresh="--refresh" in sys.argv)
