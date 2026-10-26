from datetime import timedelta

from app import clock, security

ADMIN_PHONE = "9999999999"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(client, phone: str, name: str | None = None, city: str | None = None) -> dict:
    assert client.post("/auth/otp/request", json={"phone": phone}).status_code == 200
    body = {"phone": phone, "code": client.otp_sender.codes[security.normalize_phone(phone)]}
    if name:
        body.update(name=name, city=city)
    r = client.post("/auth/otp/verify", json=body)
    assert r.status_code == 200, r.text
    return bearer(r.json()["access_token"])


def admin(client) -> dict:
    return login(client, ADMIN_PHONE)


def make_dealer(client, admin_h, name="Pune Motors", city="Pune", email="sales@punemotors.in",
                password="correct-horse-battery") -> dict:
    r = client.post("/dealers", json={"name": name, "city": city, "email": email, "password": password},
                    headers=admin_h)
    assert r.status_code == 201, r.text
    r = client.post("/auth/dealer/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return bearer(r.json()["access_token"])


def make_campaign(client, admin_h, target=2, closes_in_days=0, city="Pune") -> int:
    r = client.post("/campaigns", headers=admin_h, json={
        "make": "Tata", "model": "Nexon", "variant": "Fearless", "city": city,
        "ex_showroom_rupees": 1_200_000, "target_buyers": target,
        "closes_on": str(clock.today() + timedelta(days=closes_in_days))})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def offer_body(discount=60_000, freebies=10_000) -> dict:
    return {"discount_rupees": discount, "freebies_value_rupees": freebies,
            "valid_until": str(clock.today() + timedelta(days=30))}
