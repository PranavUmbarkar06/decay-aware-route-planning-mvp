"""Shared fixtures: a fresh SQLite database per test module, loaded from the real nodes.csv and seeded with the
fictional demo personas; a TestClient; and a login helper that uses the dev-stub OTP flow end to end."""
import os
import tempfile

import pytest

os.environ.setdefault("PHL_JWT_SECRET", "test-secret-not-for-production-0123456789abcdef")


@pytest.fixture(scope="module")
def app_db():
    from app.cli import load_nodes, seed_demo
    from app.core import db as dbmod
    from app.core.ratelimit import limiter
    from app.models import orm  # noqa: F401

    tmp = tempfile.mkdtemp()
    eng = dbmod.make_engine(f"sqlite:///{tmp}/test.sqlite")
    dbmod.Base.metadata.create_all(eng)
    dbmod.set_engine(eng)
    with dbmod.session() as s:
        load_nodes(s)
        seed_demo(s)
        s.commit()
    limiter.reset()
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def client(app_db):
    from app.main import create_app
    from fastapi.testclient import TestClient
    return TestClient(create_app())


@pytest.fixture
def login(client):
    from app.core.ratelimit import limiter

    def _login(phone: str) -> dict:
        limiter.reset()
        r = client.post("/api/v1/auth/otp/request", json={"phone": phone})
        assert r.status_code == 200, r.text
        ch = r.json()
        r = client.post("/api/v1/auth/otp/verify", json={"challenge_id": ch["challenge_id"], "code": ch["dev_otp"]})
        assert r.status_code == 200, r.text
        return AuthHeaders({"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user"])
    return _login


class AuthHeaders(dict):
    """Request headers that also carry the logged-in user (as `.user`)."""
    def __init__(self, headers: dict, user: dict):
        super().__init__(headers)
        self.user = user
