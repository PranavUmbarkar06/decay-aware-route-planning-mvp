"""RBAC matrix: every protected endpoint × every role. 403 = denied by role; anything else = allowed past RBAC
(the request may still fail validation, which is fine here)."""
import pytest

ROLES = {"FARMER": "+910000000001", "SUPERVISOR": "+910000000002", "WAREHOUSE": "+910000000003",
         "DISPATCHER": "+910000000004", "NGO": "+910000000005", "TRANSPORTER": "+910000000006", "ADMIN": "+910000000007"}
ALL = set(ROLES)

# (method, path, allowed roles)
MATRIX = [
    ("POST", "/api/v1/consignments", {"FARMER", "SUPERVISOR", "WAREHOUSE", "DISPATCHER", "ADMIN"}),
    ("GET", "/api/v1/consignments", ALL),
    ("GET", "/api/v1/nodes", ALL),
    ("POST", "/api/v1/consignments/X/handovers", {"FARMER", "SUPERVISOR", "WAREHOUSE", "DISPATCHER", "ADMIN"}),
    ("POST", "/api/v1/handovers/X/confirm", {"SUPERVISOR", "WAREHOUSE", "DISPATCHER", "NGO", "ADMIN"}),
    ("POST", "/api/v1/consignments/X/scan", {"TRANSPORTER", "ADMIN"}),
    ("POST", "/api/v1/consignments/X/wastage", {"SUPERVISOR", "WAREHOUSE", "ADMIN"}),
    ("POST", "/api/v1/wastage/1/undo", {"SUPERVISOR", "WAREHOUSE", "ADMIN"}),
    ("GET", "/api/v1/admin/audit", {"ADMIN"}),
]


@pytest.fixture(scope="module")
def tokens(client):
    from app.core.ratelimit import limiter
    out = {}
    for role, phone in ROLES.items():
        limiter.reset()
        ch = client.post("/api/v1/auth/otp/request", json={"phone": phone}).json()
        out[role] = client.post("/api/v1/auth/otp/verify", json={"challenge_id": ch["challenge_id"],
                                                                 "code": ch["dev_otp"]}).json()["token"]
    return out


@pytest.mark.parametrize("method,path,allowed", MATRIX)
def test_rbac_matrix(client, tokens, method, path, allowed):
    for role in ROLES:
        r = client.request(method, path, headers={"Authorization": f"Bearer {tokens[role]}"}, json={})
        if role in allowed:
            assert r.status_code != 403 or r.json().get("code") not in (None, "forbidden"), (role, path, r.text)
            assert not (r.status_code == 403 and "cannot do this" in r.text), (role, path, r.text)
        else:
            assert r.status_code == 403 and "cannot do this" in r.text, (role, path, r.status_code, r.text)


@pytest.mark.parametrize("method,path,_", MATRIX)
def test_unauthenticated_is_401(client, method, path, _):
    assert client.request(method, path, json={}).status_code == 401


def test_new_user_registration_requires_consent_and_valid_role(client):
    from app.core.ratelimit import limiter
    limiter.reset()
    ch = client.post("/api/v1/auth/otp/request", json={"phone": "+910000000099"}).json()
    r = client.post("/api/v1/auth/otp/verify", json={"challenge_id": ch["challenge_id"], "code": ch["dev_otp"]})
    assert r.status_code == 409 and r.json()["code"] == "needs_profile"
    ch = client.post("/api/v1/auth/otp/request", json={"phone": "+910000000099"}).json()
    r = client.post("/api/v1/auth/otp/verify", json={"challenge_id": ch["challenge_id"], "code": ch["dev_otp"],
                                                     "profile": {"role": "ADMIN", "consent": True}})
    assert r.status_code == 422                               # cannot self-register as admin
    ch = client.post("/api/v1/auth/otp/request", json={"phone": "+910000000099"}).json()
    r = client.post("/api/v1/auth/otp/verify", json={"challenge_id": ch["challenge_id"], "code": ch["dev_otp"],
                                                     "profile": {"role": "FARMER", "consent": True, "language": "mr"}})
    assert r.status_code == 200 and r.json()["user"]["role"] == "FARMER" and r.json()["auth_mode"] == "dev_stub"


def test_otp_wrong_code_and_rate_limit(client):
    from app.core.ratelimit import limiter
    limiter.reset()
    ch = client.post("/api/v1/auth/otp/request", json={"phone": ROLES["FARMER"]}).json()
    bad = "000000" if ch["dev_otp"] != "000000" else "111111"
    assert client.post("/api/v1/auth/otp/verify", json={"challenge_id": ch["challenge_id"], "code": bad}).status_code == 401
    codes = [client.post("/api/v1/auth/otp/request", json={"phone": ROLES["FARMER"]}).status_code for _ in range(6)]
    assert 429 in codes
