from datetime import date

import pytest

from app import services
from app.models import Buyer, Campaign, Dealer

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


def test_threshold_opens_offers(db):
    c = _campaign(db)
    for b in _buyers(db, 2):
        services.join(db, c, b, TODAY)
    assert c.status == "open"
    extra = Buyer(name="X", phone="9111111111", city="Pune")
    db.add(extra)
    db.flush()
    services.join(db, c, extra, TODAY)
    assert c.status == "offers"
    assert "3 verified buyers in Pune" in services.dealer_pitch(db, c)


def test_duplicate_and_wrong_city_rejected(db):
    c = _campaign(db)
    b, = _buyers(db, 1)
    services.join(db, c, b, TODAY)
    with pytest.raises(services.CampaignError, match="already"):
        services.join(db, c, b, TODAY)
    other = Buyer(name="M", phone="9222222222", city="Mumbai")
    db.add(other)
    db.flush()
    with pytest.raises(services.CampaignError, match="city"):
        services.join(db, c, other, TODAY)


def test_offers_only_after_threshold(db):
    c = _campaign(db)
    with pytest.raises(services.CampaignError, match="not accepting"):
        services.submit_offer(db, c, _dealer(db), 50_000, 0, date(2026, 11, 30), TODAY)


def test_best_offer_counts_freebies_and_skips_expired(db):
    c = _campaign(db, target=1)
    services.join(db, c, _buyers(db, 1)[0], TODAY)
    a = services.submit_offer(db, c, _dealer(db, "A"), 60_000, 0, date(2026, 11, 30), TODAY)
    b = services.submit_offer(db, c, _dealer(db, "B"), 40_000, 30_000, date(2026, 11, 30), TODAY)
    services.submit_offer(db, c, _dealer(db, "C"), 90_000, 0, date(2026, 11, 2), TODAY)
    assert services.best_offer(db, c, date(2026, 11, 10)) is b
    assert services.best_offer(db, c, TODAY).discount_rupees == 90_000
    assert services.savings_pct(c, a) == 5.0


def test_close_success_applies_deposits(db):
    c = _campaign(db, target=2)
    ms = [services.join(db, c, b, TODAY) for b in _buyers(db, 2)]
    o = services.submit_offer(db, c, _dealer(db), 50_000, 0, date(2026, 12, 15), TODAY)
    services.close_campaign(db, c, date(2026, 11, 30))
    assert c.status == "won" and c.winning_offer_id == o.id
    assert all(m.deposit_status == "applied" for m in ms)


def test_close_without_offers_refunds(db):
    c = _campaign(db, target=2)
    ms = [services.join(db, c, b, TODAY) for b in _buyers(db, 2)]
    services.close_campaign(db, c, date(2026, 11, 30))
    assert c.status == "failed"
    assert all(m.deposit_status == "refunded" for m in ms)


def test_cannot_close_early(db):
    with pytest.raises(services.CampaignError, match="closing date"):
        services.close_campaign(db, _campaign(db), TODAY)
