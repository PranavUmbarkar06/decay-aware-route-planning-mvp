"""FastAPI application. API under /api/v1 (OpenAPI docs at /api/docs); /healthz and /readyz at the root;
the built PWA (frontend/dist) is served at / when present."""
from __future__ import annotations

import json
import logging
import mimetypes
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm.exc import StaleDataError

from app.core.config import ROOT, app_config
from app.core.db import engine
from app.core.security import request_id_var
from app.services.custody import ServiceError


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({"ts": self.formatTime(record), "level": record.levelname, "logger": record.name,
                           "msg": record.getMessage(), "request_id": request_id_var.get()}, ensure_ascii=False)


def _setup_logging() -> None:
    h = logging.StreamHandler()
    h.setFormatter(JsonFormatter())
    root = logging.getLogger("phl")
    if not root.handlers:
        root.addHandler(h)
        root.setLevel(logging.INFO)


# Windows registries often lack these: module workers (MapLibre) and the web manifest need correct types.
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("application/manifest+json", ".webmanifest")


def create_app() -> FastAPI:
    _setup_logging()
    cfg = app_config()
    app = FastAPI(title=cfg.product_name, version=cfg.version, docs_url="/api/docs", redoc_url=None,
                  openapi_url="/api/openapi.json",
                  description="Prototype API. Simulation outputs are not field-validated. See /api/v1/meta.")
    app.add_middleware(CORSMiddleware, allow_origins=cfg.runtime.cors_origins, allow_methods=["*"], allow_headers=["*"])
    log = logging.getLogger("phl.http")

    @app.middleware("http")
    async def request_context(request: Request, call_next):  # noqa: ANN001
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = request_id_var.set(rid)
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            if request.url.path.startswith("/api"):
                log.info("%s %s %s %.0fms", request.method, request.url.path, response.status_code,
                         (time.perf_counter() - t0) * 1000)
        finally:
            request_id_var.reset(token)
        return response

    @app.exception_handler(ServiceError)
    async def service_error(_: Request, e: ServiceError) -> JSONResponse:
        return JSONResponse({"status": e.status, "code": e.code, "message": e.message}, status_code=e.status)

    @app.exception_handler(StaleDataError)
    async def stale(_: Request, __: StaleDataError) -> JSONResponse:
        return JSONResponse({"status": 409, "code": "conflict",
                             "message": "Someone else changed this lot at the same moment. Refresh and try again."},
                            status_code=409)

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict:
        return {"ok": True}

    @app.get("/readyz", tags=["ops"])
    def readyz() -> JSONResponse:
        try:
            with engine().connect() as c:
                c.execute(text("SELECT 1"))
                n = c.execute(text("SELECT COUNT(*) FROM nodes")).scalar()
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"ready": False, "reason": str(e)[:200]}, status_code=503)
        return JSONResponse({"ready": bool(n), "nodes": n}, status_code=200 if n else 503)

    from app.api.routes_core import router as core_router
    app.include_router(core_router)
    try:
        from app.api.routes_ops import router as ops_router  # M3–M7 (Phase 5+)
        app.include_router(ops_router)
    except ImportError:
        pass

    dist = ROOT / "frontend" / "dist"
    geo = ROOT / "data" / "processed" / "geo"
    if geo.exists():
        app.mount("/geo", StaticFiles(directory=geo), name="geo")
    if (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            f = (dist / path).resolve()
            if path and f.is_file() and dist.resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(dist / "index.html")
    return app


app = create_app()
