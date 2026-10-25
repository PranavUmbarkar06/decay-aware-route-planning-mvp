"""`make graph-apply-review`: ingest the owner's node review (brief §9A step 6).

Input: inputs/node_review.csv with the nodes.csv columns plus `reviewer` and `decision`:
  decision = accept   → node becomes routable as-is (needs_review=false)
             move     → lat/lon replaced by the reviewer's values, re-snapped at load time
             reject   → node excluded permanently
Output: data/processed/node_overrides.csv (provenance USER_ENTERED). nodes.csv (the generated output) is
never modified; the app applies overrides when loading the database (`python tasks.py load`).
"""
from __future__ import annotations

import sys

import pandas as pd

from pipelines.common import PROCESSED, ROOT, utcnow, write_csv_deterministic

REVIEW = ROOT / "inputs" / "node_review.csv"
DECISIONS = {"accept", "move", "reject"}


def main() -> int:
    if not REVIEW.exists():
        print(f"No review file at {REVIEW.relative_to(ROOT)}. Start from reports/nodes_needing_review.csv, "
              "add 'reviewer' and 'decision' columns, save it there, and rerun.")
        return 0
    rev = pd.read_csv(REVIEW)
    nodes = pd.read_csv(PROCESSED / "nodes.csv").set_index("node_id")
    errors = []
    for col in ("node_id", "reviewer", "decision"):
        if col not in rev.columns:
            errors.append(f"missing column '{col}'")
    if errors:
        print("\n".join(errors))
        return 1
    out = []
    for i, r in rev.iterrows():
        row_no = i + 2
        d = str(r["decision"]).strip().lower()
        if d not in DECISIONS:
            errors.append(f"row {row_no}: decision '{r['decision']}' not in {sorted(DECISIONS)}")
            continue
        if r["node_id"] not in nodes.index:
            errors.append(f"row {row_no}: unknown node_id {r['node_id']}")
            continue
        if d == "move" and (pd.isna(r.get("lat")) or pd.isna(r.get("lon"))):
            errors.append(f"row {row_no}: decision 'move' needs lat and lon")
            continue
        if not str(r["reviewer"]).strip() or pd.isna(r["reviewer"]):
            errors.append(f"row {row_no}: reviewer is required")
            continue
        out.append({"node_id": r["node_id"], "decision": d, "lat": r.get("lat") if d == "move" else None,
                    "lon": r.get("lon") if d == "move" else None, "reviewer": str(r["reviewer"]).strip(),
                    "reviewed_at_utc": utcnow(), "provenance": "USER_ENTERED",
                    "source_manifest_id": "user:inputs/node_review.csv"})
    for e in errors:
        print("ERROR", e)
    if out:
        write_csv_deterministic(pd.DataFrame(out).drop(columns=["reviewed_at_utc"]), PROCESSED / "node_overrides.csv", ["node_id"])
    print(f"applied {len(out)} review decisions; {len(errors)} rows rejected")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
