from datetime import timedelta

import jwt

from app import clock, security
from app.deps import settings_dep

from .helpers import admin, bearer, login, make_campaign, make_dealer, offer_body


def test_health_and_openapi_are_public(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert "/auth/otp/request" in client.get("/openapi.json").json()["paths"]


def test_protected_routes_require_a_token(client):
    for method, path in [("get", "/me"), ("get", "/me/memberships"), ("post", "/campaigns/1/join"),
                         ("post", "/campaigns"), ("post", "/dealers"), ("post", "/campaigns/1/close"),
                         ("post", "/campaigns/1/offers"), ("get", "/campaigns/1/pitch"),
                         ("get", "/campaigns/1/buyers"), ("get", "/success-fees"),
                         ("get", "/dealer/success-fees"), ("put", "/campaigns/1/contact-consent")]:
        r = getattr(client, method)(path)
        assert r.status_code == 401, (method, path, r.status_code)


def test_garbage_and_tampered_tokens_rejected(client):
    assert client.get("/me", headers=bearer("not-a-jwt")).status_code == 401
    forged = jwt.encode({"sub": "1", "role": "admin", "exp": clock.now() + timedelta(hours=1)}, "wrong-secret",
                        algorithm="HS256")
    assert client.post("/campaigns", headers=bearer(forged), json={}).status_code == 401
    no_exp = jwt.encode({"sub": "1", "role": "buyer"}, "x", algorithm="HS256")
    assert client.get("/me", headers=bearer(no_exp)).status_code == 401


def test_expired_token_rejected(client):
    h = login(client, "9876543210", "Asha", "Pune")
    assert client.get("/me", headers=h).json()["name"] == "Asha"
    expired = jwt.encode({"sub": "1", "role": "buyer", "exp": clock.now() - timedelta(minutes=1)},
                         security._secret(settings_dep()), algorithm="HS256")
    assert client.get("/me", headers=bearer(expired)).status_code == 401


def test_roles_are_enforced(client):
    a = admin(client)
    buyer = login(client, "9876543210", "Asha", "Pune")
    dealer = make_dealer(client, a)
    cid = make_campaign(client, a)
    assert client.post("/campaigns", headers=buyer, json={}).status_code == 403
    assert client.post("/campaigns", headers=dealer, json={}).status_code == 403
    assert client.post(f"/campaigns/{cid}/close", headers=buyer).status_code == 403
    assert client.post(f"/campaigns/{cid}/close", headers=dealer).status_code == 403
    assert client.post(f"/campaigns/{cid}/join", headers=dealer).status_code == 403
    assert client.post(f"/campaigns/{cid}/join", headers=a).status_code == 403
    assert client.post(f"/campaigns/{cid}/offers", headers=buyer, json=offer_body()).status_code == 403
    assert client.get(f"/campaigns/{cid}/buyers", headers=buyer).status_code == 403
    assert client.get(f"/campaigns/{cid}/pitch", headers=buyer).status_code == 403
    assert client.get("/success-fees", headers=dealer).status_code == 403


def test_otp_wrong_code_expiry_reuse_and_lockout(client):
    phone = "9876543210"
    client.post("/auth/otp/request", json={"phone": phone})
    good = client.otp_sender.codes[phone]
    bad = "000000" if good != "000000" else "111111"
    body = {"phone": phone, "name": "A", "city": "Pune"}
    assert client.post("/auth/otp/verify", json={**body, "code": bad}).status_code == 401
    ok = client.post("/auth/otp/verify", json={**body, "code": good})
    assert ok.status_code == 200 and ok.json()["role"] == "buyer"
    assert client.post("/auth/otp/verify", json={**body, "code": good}).status_code == 401  # single use

    client.post("/auth/otp/request", json={"phone": "9123456780"})
    good = client.otp_sender.codes["9123456780"]
    for _ in range(5):
        client.post("/auth/otp/verify", json={"phone": "9123456780", "code": bad})
    # five wrong guesses burn the code, even the right one no longer works
    assert client.post("/auth/otp/verify", json={"phone": "9123456780", "code": good, "name": "B",
                                                  "city": "Pune"}).status_code == 401


def test_otp_expires(client, monkeypatch):
    phone = "9876543210"
    client.post("/auth/otp/request", json={"phone": phone})
    later = clock.now() + timedelta(minutes=10)
    monkeypatch.setattr(clock, "now", lambda: later)
    r = client.post("/auth/otp/verify", json={"phone": phone, "code": client.otp_sender.codes[phone],
                                              "name": "A", "city": "Pune"})
    assert r.status_code == 401


def test_new_account_needs_name_and_city_and_phone_is_validated(client):
    phone = "9876543210"
    client.post("/auth/otp/request", json={"phone": phone})
    r = client.post("/auth/otp/verify", json={"phone": phone, "code": client.otp_sender.codes[phone]})
    assert r.status_code == 422
    assert client.post("/auth/otp/request", json={"phone": "12345"}).status_code == 422
    # +91 formatting maps onto the same account
    h = login(client, "9876543210", "Asha", "Pune")
    h2 = login(client, "+91 98765 43210")
    assert client.get("/me", headers=h2).json() == client.get("/me", headers=h).json()


def test_dealer_login_failures(client):
    a = admin(client)
    make_dealer(client, a, email="Sales@PuneMotors.in")
    wrong = {"email": "sales@punemotors.in", "password": "nope"}
    assert client.post("/auth/dealer/login", json=wrong).status_code == 401
    assert client.post("/auth/dealer/login", json={"email": "ghost@x.in", "password": "x" * 12}).status_code == 401
    assert client.post("/auth/dealer/login", json={"email": "sales@punemotors.in",
                                                   "password": "correct-horse-battery"}).status_code == 200


def test_duplicate_dealer_and_short_password_rejected(client):
    a = admin(client)
    make_dealer(client, a)
    dup = {"name": "X", "city": "Pune", "email": "sales@punemotors.in", "password": "another-long-password"}
    assert client.post("/dealers", json=dup, headers=a).status_code == 409
    short = {**dup, "email": "b@x.in", "password": "short"}
    assert client.post("/dealers", json=short, headers=a).status_code == 422


def test_rate_limits_on_auth_endpoints(client):
    codes = [client.post("/auth/otp/request", json={"phone": "9876543210"}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]  # 3 per phone per 10 minutes
    for _ in range(10):
        client.post("/auth/dealer/login", json={"email": "a@b.in", "password": "x"})
    r = client.post("/auth/dealer/login", json={"email": "a@b.in", "password": "x"})
    assert r.status_code == 429 and "retry-after" in r.headers


def test_responses_carry_request_id(client):
    assert client.get("/health", headers={"X-Request-ID": "abc123"}).headers["x-request-id"] == "abc123"
    assert client.get("/health").headers["x-request-id"]
