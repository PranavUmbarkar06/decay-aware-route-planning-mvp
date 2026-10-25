"""Shared pipeline helpers: polite cached fetching, immutable raw files, per-source MANIFEST.json.

Rules (project brief §8): raw files are immutable and checksummed; re-running is idempotent; works offline
from cache and reports which sources were not refreshed.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
CACHE = ROOT / "data" / "cache"
USER_AGENT = "PHL-platform-prototype/0.1 (research prototype; non-commercial; contact via repo owner)"

_last_call: dict[str, float] = {}
REFRESH_LOG: list[dict[str, Any]] = []   # what happened this run, for the end-of-run summary


def utcnow() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class SourceMeta:
    source: str                  # folder name under data/raw/
    licence: str                 # as recorded from the source's own terms page (or "UNVERIFIED: ...")
    terms_url: str | None = None
    notes: str = ""


def _manifest_path(source: str) -> Path:
    return RAW / source / "MANIFEST.json"


def load_manifest(source: str) -> dict[str, Any]:
    p = _manifest_path(source)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"source": source, "entries": []}


def save_manifest(source: str, m: dict[str, Any]) -> None:
    p = _manifest_path(source)
    p.parent.mkdir(parents=True, exist_ok=True)
    m["entries"] = sorted(m["entries"], key=lambda e: e["file"])
    p.write_text(json.dumps(m, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def manifest_entry(source: str, filename: str) -> dict[str, Any] | None:
    for e in load_manifest(source)["entries"]:
        if e["file"] == filename:
            return e
    return None


def manifest_id(source: str, filename: str) -> str:
    e = manifest_entry(source, filename)
    if e is None:
        raise KeyError(f"no manifest entry for {source}/{filename}")
    return e["manifest_id"]


def record(meta: SourceMeta, filename: str, payload: bytes, *, url: str, method: str = "GET",
           params: dict | None = None, http_status: int | None = None, retrieval: str = "pipeline_http",
           extra: dict | None = None) -> dict[str, Any]:
    """Write an immutable raw file + manifest entry. If the file exists with a different hash, the new
    payload is stored under a timestamped name instead of overwriting (raw files are immutable)."""
    d = RAW / meta.source
    d.mkdir(parents=True, exist_ok=True)
    digest = sha256_bytes(payload)
    target = d / filename
    if target.exists() and sha256_file(target) != digest:
        stem, suf = target.stem, target.suffix
        filename = f"{stem}.{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}{suf}"
        target = d / filename
    if not target.exists():
        target.write_bytes(payload)
    m = load_manifest(meta.source)
    m["licence"] = meta.licence
    m["terms_url"] = meta.terms_url
    m["notes"] = meta.notes
    m["entries"] = [e for e in m["entries"] if e["file"] != filename]
    entry = {
        "file": filename,
        "manifest_id": f"{meta.source}:{digest[:12]}",
        "url": url,
        "method": method,
        "params": params or {},
        "fetched_at_utc": utcnow(),
        "sha256": digest,
        "bytes": len(payload),
        "http_status": http_status,
        "retrieval": retrieval,
        **(extra or {}),
    }
    m["entries"].append(entry)
    save_manifest(meta.source, m)
    return entry


def polite_get(url: str, *, params: dict | None = None, min_interval_s: float = 1.0, timeout: float = 120,
               retries: int = 4, method: str = "GET", data: Any = None, headers: dict | None = None
               ) -> requests.Response:
    """Rate-limited per host, exponential backoff on 429/5xx. Never retries 4xx auth/captcha responses."""
    host = url.split("/")[2]
    wait = min_interval_s - (time.monotonic() - _last_call.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    backoff = 5.0
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = requests.request(method, url, params=params, data=data, timeout=timeout,
                                 headers={"User-Agent": USER_AGENT, **(headers or {})})
            _last_call[host] = time.monotonic()
            if r.status_code in (429, 502, 503, 504) and attempt < retries:
                time.sleep(backoff)
                backoff *= 2
                continue
            return r
        except requests.RequestException as e:  # network down / blocked
            last_exc = e
            if attempt < retries:
                time.sleep(backoff)
                backoff *= 2
    raise ConnectionError(f"{url}: {last_exc!r}")


def fetch_cached(meta: SourceMeta, filename: str, url: str, *, params: dict | None = None,
                 refresh: bool = False, min_interval_s: float = 1.0, accept_status: tuple[int, ...] = (200,),
                 method: str = "GET", data: Any = None, headers: dict | None = None,
                 timeout: float = 120) -> tuple[Path | None, str]:
    """Return (path, status) where status ∈ {cached, fetched, http_<code>, offline}. Cache-first."""
    path = RAW / meta.source / filename
    if path.exists() and not refresh:
        REFRESH_LOG.append({"source": meta.source, "file": filename, "status": "cached (not refreshed)"})
        return path, "cached"
    try:
        r = polite_get(url, params=params, min_interval_s=min_interval_s, method=method, data=data,
                       headers=headers, timeout=timeout)
    except ConnectionError as e:
        REFRESH_LOG.append({"source": meta.source, "file": filename, "status": f"offline: {e}"})
        return (path if path.exists() else None), "offline"
    if r.status_code not in accept_status:
        REFRESH_LOG.append({"source": meta.source, "file": filename, "status": f"http_{r.status_code}"})
        return (path if path.exists() else None), f"http_{r.status_code}"
    e = record(meta, filename, r.content, url=r.url if params else url, method=method, params=params,
               http_status=r.status_code)
    REFRESH_LOG.append({"source": meta.source, "file": e["file"], "status": "fetched"})
    return RAW / meta.source / e["file"], "fetched"


def write_csv_deterministic(df, path: Path, sort_by: list[str]) -> None:
    """Byte-reproducible CSV: sorted rows, fixed column order, LF newlines, fixed float format."""
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.sort_values(sort_by, kind="mergesort").reset_index(drop=True)
    out.to_csv(path, index=False, lineterminator="\n", float_format="%.6f", encoding="utf-8")


@dataclass
class AuditRecord:
    """One row of DATA_GAPS.md / DATA_SOURCES.md. Written by each fetcher, read by pipelines.audit."""
    need: str
    source_name: str
    status: str                  # AVAILABLE | PARTIAL | RESTRICTED | MISSING | UNVERIFIED
    access: str
    auth: str
    licence: str
    coverage: str
    tried: list[str] = field(default_factory=list)
    why_failed: str = ""
    fallback: str = ""
    urls: list[str] = field(default_factory=list)
    rate_limits: str = ""
    freshness: str = ""
    known_problems: str = ""
    flags: list[str] = field(default_factory=list)   # e.g. NON_COMMERCIAL, ATTRIBUTION_REQUIRED


AUDIT_DIR = ROOT / "data" / "audit"


def write_audit(key: str, rec: AuditRecord) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIT_DIR / f"{key}.json").write_text(json.dumps(rec.__dict__, indent=2, ensure_ascii=False) + "\n",
                                           encoding="utf-8")
