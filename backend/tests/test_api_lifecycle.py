import json
from datetime import timedelta

from app import clock, security
from app.deps import settings_dep

from .helpers import admin, login, make_campaign, make_dealer, offer_body

PHONES = ["9000000001", "9000000002", "9000000003"]


def _join_all(client, cid, n=2, city="Pune", consent=()):
    hs = []
    for i, phone in enumerate(PHONES[:n]):
        h = login(client, phone, f"Buyer {i}", city)
        r = client.post(f"/campaigns/{cid}/join", headers=h)
        assert r.status_code == 201, r.text
        assert r.json()["deposit_status"] == "held"
        if i in consent:
            assert client.put(f"/campaigns/{cid}/contact-consent", headers=h,
                              json={"share_contact": True}).status_code == 200
        hs.append(h)
    return hs


def test_full_lifecycle_success(client, payments):
    a = admin(client)
    dealer = make_dealer(client, a)
    cid = make_campaign(client, a, target=2)

    # public view, before any buyer joins
    assert client.get("/campaigns?city=pune").json()[0]["joined"] == 0
    assert client.get(f"/campaigns/{cid}/best-offer").status_code == 404

    # offers are refused until the threshold is reached
    assert client.post(f"/campaigns/{cid}/offers", headers=dealer, json=offer_body()).status_code == 409

    buyers = _join_all(client, cid, n=2, consent=(0,))
    assert client.get(f"/campaigns/{cid}").json()["status"] == "offers"
    assert client.post(f"/campaigns/{cid}/join", headers=buyers[0]).status_code == 409  # already joined
    assert "2 verified buyers in Pune" in client.get(f"/campaigns/{cid}/pitch", headers=dealer).json()["message"]

    assert client.post(f"/campaigns/{cid}/offers", headers=dealer, json=offer_body(60_000, 10_000)).status_code == 201
    best = client.get(f"/campaigns/{cid}/best-offer").json()
    assert best == {"savings_pct": 5.0, "total_value_rupees": 70_000}  # no dealer identity in the public view

    # a second dealer, in another city, cannot bid
    other = make_dealer(client, a, name="Mumbai Cars", city="Mumbai", email="m@cars.in")
    assert client.post(f"/campaigns/{cid}/offers", headers=other, json=offer_body()).status_code == 409

    # the winner is only known (and contact only shared) after close
    assert client.get(f"/campaigns/{cid}/buyers", headers=dealer).status_code == 403
    closed = client.post(f"/campaigns/{cid}/close", headers=a).json()
    assert closed["status"] == "won"
    assert client.post(f"/campaigns/{cid}/close", headers=a).status_code == 409
    assert [op for op, _ in payments.calls if op == "apply"] == ["apply", "apply"]

    mine = client.get("/me/memberships", headers=buyers[0]).json()[0]
    assert mine["deposit_status"] == "applied" and mine["delivery_status"] == "booked"
    assert mine["winning_dealer"] == "Pune Motors"

    # contact details: only the opted-in buyer is revealed, and only to the winning dealer
    rows = client.get(f"/campaigns/{cid}/buyers", headers=dealer).json()
    assert sorted(r["contact"] is not None for r in rows) == [False, True]
    revealed = next(r for r in rows if r["contact"])
    assert revealed["contact"] == {"name": "Buyer 0", "phone": PHONES[0]}
    assert PHONES[1] not in json.dumps(rows)
    assert client.get(f"/campaigns/{cid}/buyers", headers=other).status_code == 403

    # delivery tracking
    ids = [r["membership_id"] for r in rows]
    path = f"/campaigns/{cid}/deliveries"
    assert client.put(f"{path}/{ids[0]}", headers=other, json={"status": "delivered"}).status_code == 403
    assert client.put(f"{path}/{ids[0]}", headers=dealer, json={"status": "teleported"}).status_code == 409
    assert client.put(f"{path}/{ids[0]}", headers=dealer, json={"status": "invoiced"}).status_code == 200
    assert client.put(f"{path}/{ids[0]}", headers=dealer, json={"status": "delivered"}).status_code == 200
    assert client.put(f"{path}/{ids[0]}", headers=dealer, json={"status": "cancelled"}).status_code == 409
    assert client.put(f"{path}/{ids[1]}", headers=dealer, json={"status": "cancelled"}).status_code == 200

    # success fee accrues per delivered car and then follows an invoice -> paid path
    fee = client.get("/dealer/success-fees", headers=dealer).json()[0]
    assert (fee["deliveries"], fee["amount_rupees"], fee["status"]) == (1, 6000, "accrued")
    fid = fee["id"]
    assert client.put(f"/success-fees/{fid}", headers=a, json={"status": "paid"}).status_code == 409
    assert client.put(f"/success-fees/{fid}", headers=a, json={"status": "invoiced"}).status_code == 200
    assert client.put(f"/success-fees/{fid}", headers=a, json={"status": "paid"}).json()["status"] == "paid"
    assert client.get("/success-fees", headers=a).json()[0]["amount_rupees"] == 6000
    assert client.get("/dealer/success-fees", headers=other).json() == []


def test_campaign_fails_without_offers_and_refunds(client, payments):
    a = admin(client)
    cid = make_campaign(client, a, target=2)
    buyers = _join_all(client, cid, n=2)
    assert client.post(f"/campaigns/{cid}/close", headers=a).json()["status"] == "failed"
    assert [op for op, _ in payments.calls if op == "refund"] == ["refund", "refund"]
    assert client.get("/me/memberships", headers=buyers[0]).json()[0]["deposit_status"] == "refunded"
    assert client.post(f"/campaigns/{cid}/join", headers=login(client, PHONES[2], "C", "Pune")).status_code == 409


def test_early_close_and_wrong_city_join_rejected(client):
    a = admin(client)
    cid = make_campaign(client, a, closes_in_days=5)
    assert client.post(f"/campaigns/{cid}/close", headers=a).status_code == 409
    mumbai = login(client, PHONES[0], "M", "Mumbai")
    assert client.post(f"/campaigns/{cid}/join", headers=mumbai).status_code == 409
    assert client.post("/campaigns/999/join", headers=mumbai).status_code == 404


def test_losing_dealer_cannot_manage_deliveries_or_see_buyers(client):
    a = admin(client)
    winner = make_dealer(client, a)
    loser = make_dealer(client, a, name="Rival", email="rival@x.in")
    cid = make_campaign(client, a, target=1)
    _join_all(client, cid, n=1, consent=(0,))
    client.post(f"/campaigns/{cid}/offers", headers=winner, json=offer_body(80_000, 0))
    client.post(f"/campaigns/{cid}/offers", headers=loser, json=offer_body(10_000, 0))
    client.post(f"/campaigns/{cid}/close", headers=a)
    assert client.get(f"/campaigns/{cid}/buyers", headers=loser).status_code == 403
    assert client.get(f"/campaigns/{cid}/buyers", headers=winner).status_code == 200


def test_consent_requires_membership_and_can_be_withdrawn(client):
    a = admin(client)
    dealer = make_dealer(client, a)
    cid = make_campaign(client, a, target=1)
    h = login(client, PHONES[0], "Asha", "Pune")
    assert client.put(f"/campaigns/{cid}/contact-consent", headers=h, json={"share_contact": True}).status_code == 404
    client.post(f"/campaigns/{cid}/join", headers=h)
    client.put(f"/campaigns/{cid}/contact-consent", headers=h, json={"share_contact": True})
    client.put(f"/campaigns/{cid}/contact-consent", headers=h, json={"share_contact": False})
    client.post(f"/campaigns/{cid}/offers", headers=dealer, json=offer_body())
    client.post(f"/campaigns/{cid}/close", headers=a)
    assert client.get(f"/campaigns/{cid}/buyers", headers=dealer).json()[0]["contact"] is None


def test_expired_offer_is_not_the_winner(client):
    a = admin(client)
    dealer = make_dealer(client, a)
    cid = make_campaign(client, a, target=1)
    _join_all(client, cid, n=1)
    stale = {**offer_body(), "valid_until": str(clock.today() - timedelta(days=1))}
    assert client.post(f"/campaigns/{cid}/offers", headers=dealer, json=stale).status_code == 409


def _signed(body: dict) -> tuple[bytes, dict]:
    raw = json.dumps(body).encode()
    sig = security.sign_webhook(settings_dep().payment_webhook_secret, raw)
    return raw, {"X-Signature": sig, "Content-Type": "application/json"}


def test_webhook_rejects_bad_or_missing_signature(client):
    raw = json.dumps({"type": "deposit.held", "ref": "x"}).encode()
    assert client.post("/webhooks/payments", content=raw).status_code == 401
    assert client.post("/webhooks/payments", content=raw, headers={"X-Signature": "deadbeef"}).status_code == 401
    raw2, headers = _signed({"type": "deposit.held", "ref": "x"})
    assert client.post("/webhooks/payments", content=raw2 + b" ", headers=headers).status_code == 401  # tampered body
    assert client.post("/webhooks/payments", content=raw2, headers=headers).json() == {"ignored": True}
    bad, headers = _signed({"nope": 1})
    assert client.post("/webhooks/payments", content=bad, headers=headers).status_code == 400


def test_pending_deposit_confirmed_by_webhook_opens_offers(client, payments):
    payments.pending = True
    a = admin(client)
    cid = make_campaign(client, a, target=1)
    h = login(client, PHONES[0], "Asha", "Pune")
    r = client.post(f"/campaigns/{cid}/join", headers=h).json()
    assert r["deposit_status"] == "pending"
    assert client.get(f"/campaigns/{cid}").json() == {**client.get(f"/campaigns/{cid}").json(), "joined": 0,
                                                       "status": "open"}
    ref = payments.calls[0][1]
    raw, headers = _signed({"type": "deposit.held", "ref": ref})
    assert client.post("/webhooks/payments", content=raw, headers=headers).json()["deposit_status"] == "held"
    assert client.post("/webhooks/payments", content=raw, headers=headers).status_code == 200  # replay is harmless
    assert client.get(f"/campaigns/{cid}").json()["status"] == "offers"


def test_failed_deposit_can_be_retried(client, payments):
    payments.pending = True
    a = admin(client)
    cid = make_campaign(client, a, target=1)
    h = login(client, PHONES[0], "Asha", "Pune")
    client.post(f"/campaigns/{cid}/join", headers=h)
    raw, headers = _signed({"type": "deposit.failed", "ref": payments.calls[0][1]})
    assert client.post("/webhooks/payments", content=raw, headers=headers).json()["deposit_status"] == "failed"
    payments.pending = False
    assert client.post(f"/campaigns/{cid}/join", headers=h).json()["deposit_status"] == "held"
    assert client.get(f"/campaigns/{cid}").json()["joined"] == 1


def test_refund_failure_is_retried_via_settle(client, payments):
    a = admin(client)
    cid = make_campaign(client, a, target=1)
    h = login(client, PHONES[0], "Asha", "Pune")
    client.post(f"/campaigns/{cid}/join", headers=h)
    payments.fail_refunds = True
    assert client.post(f"/campaigns/{cid}/close", headers=a).json()["status"] == "failed"
    assert client.get("/me/memberships", headers=h).json()[0]["deposit_status"] == "refund_failed"
    assert client.post(f"/campaigns/{cid}/settle-deposits", headers=a).json() == {"outstanding": 1}
    payments.fail_refunds = False
    assert client.post(f"/campaigns/{cid}/settle-deposits", headers=a).json() == {"outstanding": 0}
    assert client.get("/me/memberships", headers=h).json()[0]["deposit_status"] == "refunded"
