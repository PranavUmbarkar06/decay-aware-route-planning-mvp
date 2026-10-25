"""data.gov.in OGD API adapter (optional). Activates only when the owner sets DATAGOV_API_KEY in `.env`
or the environment. Without a key it records the source as RESTRICTED: it never uses a shared or
sample key.

Resource id (UNVERIFIED): commonly cited for "Current Daily Price of Various Commodities from Various
Markets (Mandi)". It could not be verified without a key; the data.gov.in catalogue page describes the
dataset as min/max/modal prices (no arrivals). Override with DATAGOV_RESOURCE_ID.
"""
from __future__ import annotations

import os
import sys

from pipelines.common import ROOT, AuditRecord, SourceMeta, fetch_cached, polite_get, write_audit

META = SourceMeta("datagov_mandi", "UNVERIFIED: Government Open Data License - India (GODL) is the platform default; "
                  "confirm on the resource page.", "https://data.gov.in/", "OGD platform API")
DEFAULT_RESOURCE = "9ef84268-d588-465a-a308-a864a43d0070"   # UNVERIFIED
API = "https://api.data.gov.in/resource/{rid}"


def _env_key() -> str | None:
    key = os.environ.get("DATAGOV_API_KEY")
    env = ROOT / ".env"
    if not key and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("DATAGOV_API_KEY="):
                key = line.split("=", 1)[1].strip() or None
    return key


def run(refresh: bool = False) -> None:
    rid = os.environ.get("DATAGOV_RESOURCE_ID", DEFAULT_RESOURCE)
    url = API.format(rid=rid)
    key = _env_key()
    tried = []
    if not key:
        try:
            r = polite_get(url, params={"format": "json", "limit": 1}, retries=0, timeout=30)
            tried.append(f"GET {url} without key → HTTP {r.status_code}: {r.text.strip()[:80]}")
        except ConnectionError as e:
            tried.append(f"GET {url} without key → offline ({e})")
        tried.append("Owner attempted to register for an API key on 2026-10-25; the portal page was broken")
        status, coverage = "RESTRICTED", "none (no API key)"
    else:
        params = {"api-key": key, "format": "json", "limit": 1000, "filters[state.keyword]": "Maharashtra"}
        p, st = fetch_cached(META, f"{rid}_maharashtra.json", url, params=params, refresh=refresh)
        # The key must never be written to the manifest: strip it from the recorded params/url.
        from pipelines.common import load_manifest, save_manifest
        m = load_manifest(META.source)
        for e in m.get("entries", []):
            e["params"] = {k: v for k, v in e.get("params", {}).items() if k != "api-key"}
            e["url"] = e["url"].split("?")[0]
        save_manifest(META.source, m)
        tried.append(f"GET {url} with owner key → {st}")
        status = "PARTIAL" if p else "RESTRICTED"
        coverage = f"raw response cached ({st}); schema to be checked before use"
    write_audit("datagov_mandi", AuditRecord(
        need="Mandi prices via an official API (secondary to Agmarknet exports)",
        source_name="data.gov.in OGD API: mandi daily prices", status=status,
        access="HTTP GET JSON", auth="API key (free registration on data.gov.in)", licence=META.licence,
        coverage=coverage, tried=tried, why_failed="No API key." if not key else "",
        fallback="Not needed for arrivals: Agmarknet manual exports cover arrivals and prices.",
        urls=[url, "https://data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi"],
        known_problems="Resource id UNVERIFIED. Catalogue describes prices only (no arrival quantities).",
        flags=["API_KEY_REQUIRED", "RESOURCE_ID_UNVERIFIED"]))
    print(f"datagov: {status}; {tried}")


if __name__ == "__main__":
    run(refresh="--refresh" in sys.argv)
