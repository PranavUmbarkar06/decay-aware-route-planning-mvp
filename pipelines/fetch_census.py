"""Census of India 2011, Table A-02 (decadal variation in population since 1901), Maharashtra.

Catalog: https://censusindia.gov.in/nada/index.php/catalog/43360 (download 47055 = XLS, 47056 = PDF).
censusindia.gov.in serves an incomplete TLS chain; it verifies with the OS trust store (truststore),
verification is never disabled. We keep only the 2011 total population for the pilot districts, which
feeds the per-capita demand proxy (ASSUMPTION-heavy; see ASSUMPTIONS.md).
"""
from __future__ import annotations

import sys
import warnings

import pandas as pd
from app.core.config import geography

from pipelines.common import (
    PROCESSED,
    AuditRecord,
    SourceMeta,
    fetch_cached,
    manifest_id,
    write_audit,
    write_csv_deterministic,
)

META = SourceMeta("census_2011_a02", "UNVERIFIED: Census of India (ORGI) publication; reuse terms not stated on the catalog page.",
                  "https://censusindia.gov.in/nada/index.php/catalog/43360",
                  "Census 2011 Table A-02, Maharashtra (populations adjusted to 2011 jurisdiction)")
URL = "https://censusindia.gov.in/nada/index.php/catalog/43360/download/47055"
# Census spellings differ from our canonical names
CENSUS_NAME = {"Gondia": "Gondiya"}


def run(refresh: bool = False) -> pd.DataFrame:
    fetch_cached(META, "download_47056.bin", "https://censusindia.gov.in/nada/index.php/catalog/43360/download/47056",
                 refresh=refresh, min_interval_s=2)
    p, status = fetch_cached(META, "download_47055.bin", URL, refresh=refresh, min_interval_s=2)
    geo = geography().current
    rows, problems = [], []
    if p is not None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            x = pd.read_excel(p, engine="xlrd", header=None)
        x = x.iloc[6:, :9]
        x.columns = ["state_code", "district_code", "name", "year", "persons", "var_abs", "var_pct", "males", "females"]
        # Only the first (1901) row of each block carries the name/code; later census years are blank.
        x["name"] = x["name"].where(x["name"].notna() & (x["name"].astype(str).str.strip() != ""))
        x[["name", "district_code"]] = x[["name", "district_code"]].ffill()
        x["name"] = x["name"].astype(str).str.strip()
        x = x[pd.to_numeric(x["year"], errors="coerce") == 2011]
        for d in geo.districts:
            want = CENSUS_NAME.get(d.name, d.name)
            hit = x[x["name"].str.lower() == want.lower()]
            if len(hit) != 1:
                problems.append(f"{d.name}: {len(hit)} rows for 2011")
                continue
            r = hit.iloc[0]
            rows.append({"district": d.name, "census_name": r["name"], "census_district_code": str(r["district_code"]),
                         "census_year": 2011, "population": int(r["persons"]), "males": int(r["males"]),
                         "females": int(r["females"]), "provenance": "REAL_FETCHED",
                         "source_manifest_id": manifest_id(META.source, "download_47055.bin")})
    else:
        problems.append(f"download failed: {status}")
    df = pd.DataFrame(rows)
    if len(df):
        write_csv_deterministic(df, PROCESSED / "census_2011_district_population.csv", ["district"])
    status_s = "AVAILABLE" if len(df) == len(geo.districts) else ("PARTIAL" if len(df) else "MISSING")
    write_audit("census_population", AuditRecord(
        need="Demand proxy: district population", source_name="Census of India 2011, Table A-02 (Maharashtra XLS)",
        status=status_s, access="HTTP GET (NADA catalog download)", auth="none", licence=META.licence,
        coverage=f"{len(df)}/{len(geo.districts)} districts, census year 2011: "
                 + ", ".join(f"{r['district']}={r['population']:,}" for r in rows),
        tried=[f"GET {URL} (TLS verified via OS trust store)"], why_failed="; ".join(problems),
        fallback="Demand falls back to the Agmarknet arrivals proxy (labelled) where population is missing.",
        urls=[META.terms_url, URL], freshness="2011: 15 years old. No later census results were used.",
        known_problems="Population ≠ demand for a market: wholesale markets serve areas beyond district lines. "
                       "Per-capita F&V consumption norm has no verified citation (MISSING) → demand is an ASSUMPTION.",
        flags=["STALE_2011", "LICENCE_UNVERIFIED"]))
    write_audit("consumption_norms", AuditRecord(
        need="Per-capita consumption norms (demand)", source_name="Not identified",
        status="MISSING", access="n/a", auth="n/a", licence="n/a", coverage="none",
        tried=["Not located in a machine-readable, citable form during Phase 1"],
        why_failed="No verified source fetched.",
        fallback="Simulation demand = scaled Agmarknet arrivals (REAL_DERIVED where exports exist) or an explicit "
                 "ASSUMPTION per-capita figure, flagged in every output.", flags=["MISSING"]))
    print(f"census: {status_s}; {[(r['district'], r['population']) for r in rows]}; problems: {problems}")
    return df


if __name__ == "__main__":
    run(refresh="--refresh" in sys.argv)
