from datetime import timedelta

from app import clock, jobs
from app.db import SessionLocal

from .helpers import admin, login, make_campaign, make_dealer, offer_body


def test_close_due_closes_only_due_campaigns_and_is_idempotent(client, payments):
    a = admin(client)
    dealer = make_dealer(client, a)
    due = make_campaign(client, a, target=1, closes_in_days=0)
    later = make_campaign(client, a, target=1, closes_in_days=7)
    h = login(client, "9000000001", "Asha", "Pune")
    client.post(f"/campaigns/{due}/join", headers=h)
    client.post(f"/campaigns/{due}/offers", headers=dealer, json=offer_body())

    assert jobs.close_due(SessionLocal, payments) == {"closed": 1, "unsettled": 0, "errors": 0}
    assert client.get("/me/memberships", headers=h).json()[0]["campaign"]["status"] == "won"
    assert client.get(f"/campaigns/{later}").json()["status"] == "open"
    assert jobs.close_due(SessionLocal, payments) == {"closed": 0, "unsettled": 0, "errors": 0}

    # a week later the second campaign (no buyers) closes as failed
    assert jobs.close_due(SessionLocal, payments, today=clock.today() + timedelta(days=7))["closed"] == 1
    assert client.get(f"/campaigns/{later}").json()["status"] == "failed"


def test_close_due_reports_and_retries_failed_refunds(client, payments):
    a = admin(client)
    cid = make_campaign(client, a, target=1)
    h = login(client, "9000000001", "Asha", "Pune")
    client.post(f"/campaigns/{cid}/join", headers=h)
    payments.fail_refunds = True
    assert jobs.close_due(SessionLocal, payments) == {"closed": 1, "unsettled": 1, "errors": 0}
    payments.fail_refunds = False
    assert jobs.close_due(SessionLocal, payments) == {"closed": 0, "unsettled": 0, "errors": 0}
    assert client.get("/me/memberships", headers=h).json()[0]["deposit_status"] == "refunded"
