"""Honest-claims check (project brief §14). Fails if UI strings, docs or API code contain over-claiming
phrases. A phrase is allowed when it is clearly negated in the same sentence ("not proven", "never
guaranteed") or the line carries the marker `honest-check: allow` (used only where we quote the rule).
"real-time traffic" is allowed only if a real traffic adapter is registered (none is, ADR-007).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN = [ROOT / "docs", ROOT / "frontend" / "src", ROOT / "backend" / "app", ROOT / "README.md", ROOT / "reports"]
EXTS = {".md", ".ts", ".tsx", ".json", ".py", ".html", ".yaml"}
BANNED = [
    r"reduces? (food )?(waste|wastage|loss(es)?) by",
    r"\bproven\b",
    r"\bguarantee(d|s)?\b",
    r"real[- ]time traffic",
    r"\bcertified safe\b",
    r"\bsafe to eat\b",
    r"\b\d+(\.\d+)?\s?% (less|lower|reduction in) (waste|wastage|loss)",
]
NEGATION = r"\b(not|no|never|isn't|aren't|without|don't|do not|cannot|nor|neither)\b[^.\n]{0,60}"
REAL_TRAFFIC_ADAPTER = False  # flip only when a real traffic data adapter exists


def violations() -> list[str]:
    out: list[str] = []
    for base in SCAN:
        files = [base] if base.is_file() else ([p for p in base.rglob("*") if p.suffix in EXTS] if base.exists() else [])
        for f in files:
            if f.resolve() == Path(__file__).resolve() or "node_modules" in f.parts:
                continue
            for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if "honest-check: allow" in line:
                    continue
                low = line.lower()
                for pat in BANNED:
                    if "traffic" in pat and REAL_TRAFFIC_ADAPTER:
                        continue
                    for m in re.finditer(pat, low):
                        if re.search(NEGATION + re.escape(m.group(0)), low):
                            continue
                        out.append(f"{f.relative_to(ROOT)}:{n}: '{m.group(0)}' in: {line.strip()[:120]}")
    return out


if __name__ == "__main__":
    v = violations()
    for line in v:
        print(line)
    print(f"honest-claims check: {len(v)} violation(s)")
    sys.exit(1 if v else 0)
