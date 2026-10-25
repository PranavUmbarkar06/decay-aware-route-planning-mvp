"""Database engine/session. SQLite for the zero-install demo, Postgres via docker-compose (ADR-004): the
same SQLAlchemy models and queries run on both (no dialect-specific SQL)."""
from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import ROOT, app_config


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    url = os.environ.get("PHL_DATABASE_URL") or app_config().runtime.database_url
    if url.startswith("sqlite:///./"):
        url = "sqlite:///" + str(ROOT / url.removeprefix("sqlite:///./")).replace("\\", "/")
    return url


def make_engine(url: str | None = None) -> Engine:
    url = url or database_url()
    if url.startswith("sqlite"):
        if ":memory:" not in url:
            (ROOT / "data" / "cache").mkdir(parents=True, exist_ok=True)
        eng = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(eng, "connect")
        def _pragmas(dbapi_conn, _):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()
        return eng
    return create_engine(url, pool_pre_ping=True)


_engine: Engine | None = None
_Session: sessionmaker[Session] | None = None


def engine() -> Engine:
    global _engine, _Session
    if _engine is None:
        _engine = make_engine()
        _Session = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def set_engine(eng: Engine) -> None:
    """Used by tests to point the app at a temporary database."""
    global _engine, _Session
    _engine = eng
    _Session = sessionmaker(bind=eng, expire_on_commit=False)


def session() -> Session:
    engine()
    assert _Session is not None
    return _Session()


def get_db() -> Iterator[Session]:
    s = session()
    try:
        yield s
    finally:
        s.close()
