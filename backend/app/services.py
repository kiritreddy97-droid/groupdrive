from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Buyer, Campaign, Dealer, Membership, Offer


class CampaignError(Exception):
    pass


def buyer_count(db: Session, campaign_id: int) -> int:
    return db.scalar(select(func.count(Membership.id)).where(Membership.campaign_id == campaign_id))


def join(db: Session, campaign: Campaign, buyer: Buyer, today: date) -> Membership:
    if campaign.status not in ("open", "offers"):
        raise CampaignError(f"campaign is {campaign.status}")
    if today > campaign.closes_on:
        raise CampaignError("campaign has closed")
    if buyer.city.lower() != campaign.city.lower():
        raise CampaignError("buyer is outside the campaign city")
    if db.scalar(select(Membership.id).where(Membership.campaign_id == campaign.id, Membership.buyer_id == buyer.id)):
        raise CampaignError("buyer already joined")
    m = Membership(campaign_id=campaign.id, buyer_id=buyer.id)
    db.add(m)
    db.flush()
    if campaign.status == "open" and buyer_count(db, campaign.id) >= campaign.target_buyers:
        campaign.status = "offers"  # threshold reached: dealers may now bid
    return m


def dealer_pitch(db: Session, campaign: Campaign) -> str:
    """The message sent to dealers in the city when a campaign reaches its threshold."""
    n = buyer_count(db, campaign.id)
    return (
        f"{n} verified buyers in {campaign.city} want a {campaign.make} {campaign.model} {campaign.variant} "
        f"by {campaign.closes_on:%d %b %Y}. Submit your best group offer on GroupDrive."
    )


def submit_offer(db: Session, campaign: Campaign, dealer: Dealer, discount: int, freebies: int,
                 valid_until: date, today: date) -> Offer:
    if campaign.status != "offers":
        raise CampaignError("campaign is not accepting offers")
    if dealer.city.lower() != campaign.city.lower():
        raise CampaignError("dealer is outside the campaign city")
    if discount < 0 or freebies < 0 or discount > campaign.ex_showroom_rupees:
        raise CampaignError("invalid offer amounts")
    if valid_until < today:
        raise CampaignError("offer already expired")
    offer = Offer(campaign_id=campaign.id, dealer_id=dealer.id, discount_rupees=discount,
                  freebies_value_rupees=freebies, valid_until=valid_until)
    db.add(offer)
    db.flush()
    return offer


def offer_value(offer: Offer) -> int:
    return offer.discount_rupees + offer.freebies_value_rupees


def best_offer(db: Session, campaign: Campaign, today: date) -> Offer | None:
    live = [o for o in db.scalars(select(Offer).where(Offer.campaign_id == campaign.id)) if o.valid_until >= today]
    return max(live, key=offer_value, default=None)


def savings_pct(campaign: Campaign, offer: Offer) -> float:
    return round(100 * offer.discount_rupees / campaign.ex_showroom_rupees, 2)


def close_campaign(db: Session, campaign: Campaign, today: date) -> Campaign:
    """Run on/after closes_on. Winner is the best live offer; otherwise deposits are refunded."""
    if campaign.status in ("won", "failed"):
        raise CampaignError(f"campaign already {campaign.status}")
    if today < campaign.closes_on:
        raise CampaignError("campaign has not reached its closing date")
    memberships = list(db.scalars(select(Membership).where(Membership.campaign_id == campaign.id)))
    winner = best_offer(db, campaign, today) if len(memberships) >= campaign.target_buyers else None
    if winner is None:
        campaign.status = "failed"
        for m in memberships:
            m.deposit_status = "refunded"
    else:
        campaign.status = "won"
        campaign.winning_offer_id = winner.id
        for m in memberships:
            m.deposit_status = "applied"  # buyer can still walk away at the dealer; refund path in docs
    db.flush()
    return campaign
