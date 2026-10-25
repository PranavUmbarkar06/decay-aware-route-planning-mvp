"""`make data`: run every fetcher (cache-first), then print exactly which sources were not refreshed.

Usage: python tasks.py data [--refresh] [--offline]
  --refresh  re-download everything (raw files stay immutable: changed payloads get new names)
  --offline  do not touch the network; rebuild processed tables from cache only
"""
from __future__ import annotations

import sys
import traceback

from pipelines import (
    audit,
    fetch_agmarknet,
    fetch_boundaries,
    fetch_census,
    fetch_datagov,
    fetch_references,
    fetch_weather,
    sources_static,
)
from pipelines.common import REFRESH_LOG

STEPS = [("agmarknet", fetch_agmarknet.run), ("boundaries", fetch_boundaries.run), ("weather", fetch_weather.run),
         ("references", fetch_references.run), ("census", fetch_census.run), ("datagov", fetch_datagov.run),
         ("static", sources_static.run)]
NETWORK_ONLY = {"datagov", "static"}


def main(argv: list[str]) -> int:
    refresh, offline = "--refresh" in argv, "--offline" in argv
    failed = []
    for name, fn in STEPS:
        if offline and name in NETWORK_ONLY:
            print(f"[{name}] skipped (--offline)")
            continue
        print(f"\n[{name}]", flush=True)
        try:
            fn(refresh=refresh)
        except Exception as e:  # noqa: BLE001 — keep going, report at the end
            traceback.print_exc()
            failed.append(f"{name}: {e}")
    audit.main()
    print("\n=== Refresh summary ===")
    for r in REFRESH_LOG:
        print(f"  {r['source']:<28} {r['file']:<55} {r['status']}")
    not_refreshed = [r for r in REFRESH_LOG if r["status"] != "fetched"]
    print(f"{len(REFRESH_LOG) - len(not_refreshed)} fetched, {len(not_refreshed)} not refreshed (cached/offline/http error).")
    if failed:
        print("FAILED STEPS:", *failed, sep="\n  ")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
