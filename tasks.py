#!/usr/bin/env python3
"""Cross-platform task runner. `make <target>` delegates here; on machines without
GNU make (e.g. this Windows dev box) run `python tasks.py <target>` instead.
See docs/DECISIONS.md ADR-014.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IS_WIN = os.name == "nt"
VENV = ROOT / ".venv"
PY = str(VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")) if VENV.exists() else sys.executable
NPM = shutil.which("npm") or "npm"


def run(cmd: list[str], cwd: Path = ROOT, env: dict | None = None, check: bool = True) -> int:
    print(f"$ {' '.join(cmd)}", flush=True)
    full_env = {**os.environ, "PYTHONUTF8": "1", **(env or {})}
    rc = subprocess.call(cmd, cwd=str(cwd), env=full_env, shell=False)
    if check and rc != 0:
        sys.exit(rc)
    return rc


def py(*args: str, **kw) -> int:
    return run([PY, *args], **kw)


def npm(*args: str, **kw) -> int:
    return run([NPM, *args], cwd=ROOT / "frontend", **kw)


# ---------------------------------------------------------------- targets
def setup() -> None:
    """Create venv (Python 3.11) and install pinned deps + frontend deps."""
    if not VENV.exists():
        launcher = ["py", "-3.11"] if IS_WIN and shutil.which("py") else [sys.executable]
        run([*launcher, "-m", "venv", str(VENV)])
    run([PY_AFTER_VENV(), "-m", "pip", "install", "-r", "requirements.lock.txt"])
    if (ROOT / "frontend" / "package.json").exists():
        npm("ci" if (ROOT / "frontend" / "package-lock.json").exists() else "install")


def PY_AFTER_VENV() -> str:  # noqa: N802
    return str(VENV / ("Scripts/python.exe" if IS_WIN else "bin/python"))


def test() -> None:
    """Backend + pipeline unit/property tests (offline)."""
    py("-m", "pytest", "-m", "not network")


def test_network() -> None:
    py("-m", "pytest", "-m", "network")


def lint() -> None:
    py("-m", "ruff", "check", "backend", "pipelines", "tasks.py", "scripts")


def typecheck() -> None:
    py("-m", "mypy")


def honest_check() -> None:
    """Scan UI strings/docs for banned over-claiming phrases."""
    py("scripts/honest_claims_check.py")


def audit_deps() -> None:
    py("-m", "pip_audit", "-r", "requirements.lock.txt", "--progress-spinner", "off")


def data() -> None:
    """Fetch all sources (cache-first; prints what was not refreshed)."""
    py("-m", "pipelines.fetch_all", *sys.argv[2:])


def data_audit() -> None:
    py("-m", "pipelines.audit")


def graph() -> None:
    """OSM extract (cache-first) → road graph, nodes.csv, edges.csv, OD matrix, GeoJSON, graph_report.html."""
    if "--synthetic" not in sys.argv:
        py("-m", "pipelines.osm_extract", *[a for a in sys.argv[2:] if a == "--refresh"])
    py("-m", "pipelines.build_graph", *sys.argv[2:])
    py("-m", "pipelines.audit")


def graph_apply_review() -> None:
    py("-m", "pipelines.apply_review")


def load() -> None:
    """Load processed CSVs + seed demo data into the database."""
    py("-m", "app.cli", "load", env={"PYTHONPATH": str(ROOT / "backend") + os.pathsep + str(ROOT)})


def experiments() -> None:
    py("-m", "app.cli", "experiments", *sys.argv[2:], env={"PYTHONPATH": str(ROOT / "backend") + os.pathsep + str(ROOT)})


def report() -> None:
    py("-m", "app.cli", "report", env={"PYTHONPATH": str(ROOT / "backend") + os.pathsep + str(ROOT)})


def api() -> None:
    py("-m", "uvicorn", "app.main:app", "--port", "8000", "--reload",
       env={"PYTHONPATH": str(ROOT / "backend") + os.pathsep + str(ROOT)})


def frontend_build() -> None:
    npm("run", "build")


def e2e() -> None:
    """Fresh isolated demo stack on :8001 (own SQLite file), then Playwright (Pixel 7 emulation, local Chrome)."""
    import time
    import urllib.request
    db = ROOT / "data" / "cache" / "phl_e2e.sqlite"
    for f in db.parent.glob("phl_e2e.sqlite*"):
        f.unlink()
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONPATH": str(ROOT / "backend") + os.pathsep + str(ROOT), "PHL_DEMO_MODE": "1", "PHL_RATE_LIMIT_MULTIPLIER": "100",
           "PHL_DATABASE_URL": "sqlite:///" + str(db).replace("\\", "/")}
    run([PY, "-m", "app.cli", "load"], env=env)
    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        npm("run", "build")
    srv = subprocess.Popen([PY, "-m", "uvicorn", "app.main:app", "--port", "8001"], cwd=str(ROOT), env=env)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen("http://localhost:8001/readyz", timeout=2)
                break
            except Exception:  # noqa: BLE001
                time.sleep(1)
        rc = npm("run", "e2e", "--", *sys.argv[2:], check=False, env={"PHL_BASE": "http://localhost:8001"})
    finally:
        srv.terminate()
        srv.wait(timeout=20)
    sys.exit(rc)


def demo() -> None:
    """Zero-Docker demo: SQLite + cached data. Builds frontend, serves both on :8000."""
    env = {"PYTHONPATH": str(ROOT / "backend") + os.pathsep + str(ROOT), "PHL_DEMO_MODE": "1"}
    py("-m", "app.cli", "load", env=env)
    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        npm("run", "build")
    print("\nDemo running at http://localhost:8000  (API docs: http://localhost:8000/api/docs)\n", flush=True)
    py("-m", "uvicorn", "app.main:app", "--port", "8000", env=env)


def ci() -> None:
    lint()
    typecheck()
    test()
    honest_check()


TARGETS = {
    "setup": setup, "test": test, "test-network": test_network, "lint": lint, "typecheck": typecheck,
    "honest-check": honest_check, "audit-deps": audit_deps, "data": data, "data-audit": data_audit,
    "graph": graph, "graph-apply-review": graph_apply_review, "load": load, "experiments": experiments,
    "report": report, "api": api, "frontend-build": frontend_build, "e2e": e2e, "demo": demo, "ci": ci,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in TARGETS:
        print("usage: python tasks.py <target>\n  targets: " + ", ".join(TARGETS))
        sys.exit(2)
    TARGETS[sys.argv[1]]()
