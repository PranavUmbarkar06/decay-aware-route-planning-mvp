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
    codes = [client.post("/api/v1/auth/otp/request", json={"phone": ROLES["FARMER"]}).status_code for _ in range(25)]
    assert 429 in codes


def test_invited_user_must_accept_consent_once(client, tokens):
    from app.core.ratelimit import limiter
    limiter.reset()
    r = client.post("/api/v1/admin/invites", headers={"Authorization": f"Bearer {tokens['ADMIN']}"},
                    json={"phone": "+910000000055", "role": "SUPERVISOR"})
    assert r.status_code == 201
    ch = client.post("/api/v1/auth/otp/request", json={"phone": "+910000000055"}).json()
    r = client.post("/api/v1/auth/otp/verify", json={"challenge_id": ch["challenge_id"], "code": ch["dev_otp"]})
    assert r.status_code == 409 and r.json()["code"] == "needs_consent"
    r = client.post("/api/v1/auth/otp/verify", json={"challenge_id": ch["challenge_id"], "code": ch["dev_otp"],
                                                     "profile": {"role": "SUPERVISOR", "consent": True}})
    assert r.status_code == 200 and r.json()["user"]["role"] == "SUPERVISOR"


def test_node_csv_import_reports_row_errors(client, tokens):
    h = {"Authorization": f"Bearer {tokens['ADMIN']}"}
    csv = "name,node_type,lat,lon,district\nGood Store,TransitStorageNode,21.1,79.1,Nagpur\n,Spaceport,99,abc,Mars\n"
    r = client.post("/api/v1/admin/nodes/import?commit=true", headers=h, json={"csv": csv}).json()
    assert r["committed"] == 0 and r["valid"] == 1
    assert r["errors"][0]["row"] == 3 and "name is empty" in r["errors"][0]["error"]
    r = client.post("/api/v1/admin/nodes/import?commit=true", headers=h, json={"csv": csv.splitlines()[0] + "\n" + csv.splitlines()[1]}).json()
    assert r["committed"] == 1
    assert client.post("/api/v1/admin/nodes/import", headers={"Authorization": f"Bearer {tokens['FARMER']}"}, json={"csv": csv}).status_code == 403


def test_evidence_page_is_public_and_says_needs_not_validated(client):
    ev = client.get("/api/v1/evidence").json()
    assert "not yet been validated by interviews" in ev["statement"]
    assert {t["tag"] for t in ev["evidence_tags"]} == {"DOCUMENTED", "INTERPRETATION", "HYPOTHESIS · VALIDATE"}
    assert ev["data_gaps"] and "No percentage reduction is claimed" in ev["no_target_claim"]
