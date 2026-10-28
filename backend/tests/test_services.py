from datetime import date, datetime, timezone

import pytest

from app import services
from app.models import Buyer, Campaign, Dealer, Delivery, SuccessFee

TODAY = date(2026, 11, 1)


def _campaign(db, target=3):
    c = Campaign(make="Tata", model="Nexon", variant="Fearless", city="Pune",
                 ex_showroom_rupees=1_200_000, target_buyers=target, closes_on=date(2026, 11, 30))
    db.add(c)
    db.flush()
    return c


def _buyers(db, n, city="Pune"):
    out = [Buyer(name=f"B{i}", phone=f"900000000{i}", city=city) for i in range(n)]
    db.add_all(out)
    db.flush()
    return out


def _dealer(db, name="D1", city="Pune"):
    d = Dealer(name=name, city=city, email=f"{name}@x.in")
    db.add(d)
    db.flush()
    return d


def test_threshold_opens_offers(db, payments):
    c = _campaign(db)
    for b in _buyers(db, 2):
        services.join(db, c, b, TODAY, payments)
    assert c.status == "open"
    extra = Buyer(name="X", phone="9111111111", city="Pune")
    db.add(extra)
    db.flush()
    services.join(db, c, extra, TODAY, payments)
    assert c.status == "offers"
    assert "3 verified buyers in Pune" in services.dealer_pitch(db, c)


def test_duplicate_and_wrong_city_rejected(db, payments):
    c = _campaign(db)
    b, = _buyers(db, 1)
    services.join(db, c, b, TODAY, payments)
    with pytest.raises(services.CampaignError, match="already"):
        services.join(db, c, b, TODAY, payments)
    other = Buyer(name="M", phone="9222222222", city="Mumbai")
    db.add(other)
    db.flush()
    with pytest.raises(services.CampaignError, match="city"):
        services.join(db, c, other, TODAY, payments)


def test_offers_only_after_threshold(db, payments):
    c = _campaign(db)
    with pytest.raises(services.CampaignError, match="not accepting"):
        services.submit_offer(db, c, _dealer(db), 50_000, 0, date(2026, 11, 30), TODAY)


def test_best_offer_counts_freebies_and_skips_expired(db, payments):
    c = _campaign(db, target=1)
    services.join(db, c, _buyers(db, 1)[0], TODAY, payments)
    a = services.submit_offer(db, c, _dealer(db, "A"), 60_000, 0, date(2026, 11, 30), TODAY)
    b = services.submit_offer(db, c, _dealer(db, "B"), 40_000, 30_000, date(2026, 11, 30), TODAY)
    services.submit_offer(db, c, _dealer(db, "C"), 90_000, 0, date(2026, 11, 2), TODAY)
    assert services.best_offer(db, c, date(2026, 11, 10)) is b
    assert services.best_offer(db, c, TODAY).discount_rupees == 90_000
    assert services.savings_pct(c, a) == 5.0


def test_close_success_applies_deposits(db, payments):
    c = _campaign(db, target=2)
    ms = [services.join(db, c, b, TODAY, payments) for b in _buyers(db, 2)]
    o = services.submit_offer(db, c, _dealer(db), 50_000, 0, date(2026, 12, 15), TODAY)
    services.close_campaign(db, c, date(2026, 11, 30), payments)
    assert c.status == "won" and c.winning_offer_id == o.id
    assert all(m.deposit_status == "applied" for m in ms)


def test_close_without_offers_refunds(db, payments):
    c = _campaign(db, target=2)
    ms = [services.join(db, c, b, TODAY, payments) for b in _buyers(db, 2)]
    services.close_campaign(db, c, date(2026, 11, 30), payments)
    assert c.status == "failed"
    assert all(m.deposit_status == "refunded" for m in ms)


def test_cannot_close_early(db, payments):
    with pytest.raises(services.CampaignError, match="closing date"):
        services.close_campaign(db, _campaign(db), TODAY, payments)


def test_unconfirmed_deposits_do_not_count_and_late_confirmation_is_refunded(db, payments):
    payments.pending = True
    c = _campaign(db, target=1)
    m = services.join(db, c, _buyers(db, 1)[0], TODAY, payments)
    assert m.deposit_status == "pending" and c.status == "open"
    services.close_campaign(db, c, date(2026, 11, 30), payments)
    assert c.status == "failed" and m.deposit_status == "failed"
    services.confirm_deposit(db, m, True, payments)  # money arrives after close
    assert m.deposit_status == "refunded"
    assert payments.calls[-1] == ("refund", m.deposit_ref)


def test_settlement_is_idempotent_and_retries_failures(db, payments):
    c = _campaign(db, target=1)
    m = services.join(db, c, _buyers(db, 1)[0], TODAY, payments)
    payments.fail_refunds = True
    services.close_campaign(db, c, date(2026, 11, 30), payments)
    assert m.deposit_status == "refund_failed"
    payments.fail_refunds = False
    assert services.settle_deposits(db, c, payments) == 0
    assert services.settle_deposits(db, c, payments) == 0
    assert m.deposit_status == "refunded"
    assert [op for op, _ in payments.calls].count("refund") == 1


def test_delivery_state_machine_and_fee_freeze(db, payments):
    c = _campaign(db, target=2)
    for b in _buyers(db, 2):
        services.join(db, c, b, TODAY, payments)
    services.submit_offer(db, c, _dealer(db), 50_000, 0, date(2026, 12, 15), TODAY)
    services.close_campaign(db, c, date(2026, 11, 30), payments)
    d1, d2 = db.query(Delivery).order_by(Delivery.id).all()
    now = datetime(2026, 12, 1, tzinfo=timezone.utc)
    services.update_delivery(db, d1, "delivered", date(2026, 12, 1), now, 6000)
    fee = db.query(SuccessFee).one()
    assert (fee.deliveries, fee.amount_rupees) == (1, 6000)
    with pytest.raises(services.CampaignError):
        services.update_delivery(db, d1, "booked", date(2026, 12, 1), now, 6000)
    services.set_fee_status(db, fee, "invoiced", now)
    services.update_delivery(db, d2, "delivered", date(2026, 12, 2), now, 6000)
    assert (fee.deliveries, fee.amount_rupees) == (1, 6000)  # frozen once invoiced
    with pytest.raises(services.CampaignError):
        services.accrue_success_fee(db, _campaign(db), 6000, now)
