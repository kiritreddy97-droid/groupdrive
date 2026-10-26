import logging
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Buyer, Campaign, Dealer, Delivery, Membership, Offer, SuccessFee
from .payments import PaymentError, PaymentGateway

log = logging.getLogger("groupdrive.services")


class CampaignError(Exception):
    pass


def buyer_count(db: Session, campaign_id: int) -> int:
    """Buyers whose deposit is confirmed; unpaid or failed joins do not count towards the threshold."""
    return db.scalar(
        select(func.count(Membership.id)).where(
            Membership.campaign_id == campaign_id, Membership.deposit_status == "held"
        )
    )


def _open_for_offers_if_threshold(db: Session, campaign: Campaign) -> None:
    if campaign.status == "open" and buyer_count(db, campaign.id) >= campaign.target_buyers:
        campaign.status = "offers"  # threshold reached: dealers may now bid


def join(db: Session, campaign: Campaign, buyer: Buyer, today: date, payments: PaymentGateway,
         deposit_rupees: int = 1000) -> Membership:
    if campaign.status not in ("open", "offers"):
        raise CampaignError(f"campaign is {campaign.status}")
    if today > campaign.closes_on:
        raise CampaignError("campaign has closed")
    if buyer.city.lower() != campaign.city.lower():
        raise CampaignError("buyer is outside the campaign city")
    m = db.scalar(select(Membership).where(Membership.campaign_id == campaign.id, Membership.buyer_id == buyer.id))
    if m is not None and m.deposit_status != "failed":
        raise CampaignError("buyer already joined")
    if m is None:  # a failed payment may be retried on the same membership
        m = Membership(campaign_id=campaign.id, buyer_id=buyer.id, deposit_rupees=deposit_rupees)
        db.add(m)
        db.flush()
    try:
        result = payments.hold(m.id, m.deposit_rupees)
    except PaymentError as e:
        raise CampaignError(f"deposit could not be taken: {e}") from e
    m.deposit_ref = result.ref
    m.deposit_status = result.status
    db.flush()
    _open_for_offers_if_threshold(db, campaign)
    return m


def confirm_deposit(db: Session, membership: Membership, ok: bool, payments: PaymentGateway) -> Membership:
    """Apply a payment-provider confirmation (webhook) to a membership. Idempotent."""
    campaign = db.get(Campaign, membership.campaign_id)
    if ok and membership.deposit_status in ("pending", "failed"):
        membership.deposit_status = "held"
        db.flush()
        if campaign.status in ("won", "failed"):
            settle_deposits(db, campaign, payments)  # arrived after close: refunded, not counted
        else:
            _open_for_offers_if_threshold(db, campaign)
    elif not ok and membership.deposit_status == "pending":
        membership.deposit_status = "failed"
    db.flush()
    return membership


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


def close_campaign(db: Session, campaign: Campaign, today: date, payments: PaymentGateway) -> Campaign:
    """Run on/after closes_on. Winner is the best live offer; otherwise deposits are refunded."""
    if campaign.status in ("won", "failed"):
        raise CampaignError(f"campaign already {campaign.status}")
    if today < campaign.closes_on:
        raise CampaignError("campaign has not reached its closing date")
    memberships = list(db.scalars(select(Membership).where(Membership.campaign_id == campaign.id)))
    for m in memberships:
        if m.deposit_status == "pending":
            m.deposit_status = "failed"  # never confirmed; a late confirmation is refunded
    held = [m for m in memberships if m.deposit_status == "held"]
    winner = best_offer(db, campaign, today) if len(held) >= campaign.target_buyers else None
    if winner is None:
        campaign.status = "failed"
    else:
        campaign.status = "won"
        campaign.winning_offer_id = winner.id
        for m in held:
            db.add(Delivery(membership_id=m.id, campaign_id=campaign.id))
    db.flush()
    settle_deposits(db, campaign, payments)
    return campaign


def settle_deposits(db: Session, campaign: Campaign, payments: PaymentGateway) -> int:
    """Refund or apply every held deposit of a closed campaign. Safe to re-run: failed calls are retried.

    Returns the number of deposits that still need settling.
    """
    if campaign.status not in ("won", "failed"):
        raise CampaignError("campaign is not closed")
    delivering = set(db.scalars(select(Delivery.membership_id).where(Delivery.campaign_id == campaign.id)))
    outstanding = 0
    pending_states = ("held", "refund_failed", "apply_failed")
    for m in db.scalars(select(Membership).where(Membership.campaign_id == campaign.id,
                                                 Membership.deposit_status.in_(pending_states))):
        apply = campaign.status == "won" and m.id in delivering
        try:
            if apply:
                payments.apply(m.deposit_ref)
            else:
                payments.refund(m.deposit_ref)
            m.deposit_status = "applied" if apply else "refunded"
        except PaymentError:
            m.deposit_status = "apply_failed" if apply else "refund_failed"
            outstanding += 1
            log.exception("deposit settlement failed", extra={"membership_id": m.id, "campaign_id": campaign.id})
    db.flush()
    return outstanding


def campaigns_due(db: Session, today: date) -> list[Campaign]:
    return list(db.scalars(select(Campaign).where(Campaign.status.in_(["open", "offers"]),
                                                  Campaign.closes_on <= today)))


def campaigns_unsettled(db: Session) -> list[Campaign]:
    stuck = ("held", "refund_failed", "apply_failed")
    return list(db.scalars(
        select(Campaign).where(Campaign.status.in_(["won", "failed"]),
                               Campaign.id.in_(select(Membership.campaign_id).where(Membership.deposit_status.in_(stuck))))
    ))


# ---- delivery tracking and success fee (phase 2) ----

DELIVERY_TRANSITIONS = {
    "booked": {"invoiced", "delivered", "cancelled"},
    "invoiced": {"delivered", "cancelled"},
    "delivered": set(),
    "cancelled": set(),
}
FEE_TRANSITIONS = {"accrued": {"invoiced", "waived"}, "invoiced": {"paid", "waived"}, "paid": set(), "waived": set()}


def update_delivery(db: Session, delivery: Delivery, status: str, today: date, now: datetime,
                    fee_per_delivery_rupees: int) -> Delivery:
    if status not in DELIVERY_TRANSITIONS:
        raise CampaignError(f"unknown delivery status {status!r}")
    if status not in DELIVERY_TRANSITIONS[delivery.status]:
        raise CampaignError(f"cannot move delivery from {delivery.status} to {status}")
    delivery.status = status
    delivery.updated_at = now
    if status == "delivered":
        delivery.delivered_on = today
    db.flush()
    if status == "delivered":
        accrue_success_fee(db, db.get(Campaign, delivery.campaign_id), fee_per_delivery_rupees, now)
    return delivery


def accrue_success_fee(db: Session, campaign: Campaign, fee_per_delivery_rupees: int,
                       now: datetime) -> SuccessFee:
    """Create or refresh the dealer's fee record: deliveries confirmed x fixed fee. Frozen once invoiced."""
    if campaign.status != "won":
        raise CampaignError("only won campaigns carry a success fee")
    winning = db.get(Offer, campaign.winning_offer_id)
    delivered = db.scalar(select(func.count(Delivery.id)).where(Delivery.campaign_id == campaign.id,
                                                                Delivery.status == "delivered"))
    fee = db.scalar(select(SuccessFee).where(SuccessFee.campaign_id == campaign.id))
    if fee is None:
        fee = SuccessFee(campaign_id=campaign.id, dealer_id=winning.dealer_id,
                         fee_per_delivery_rupees=fee_per_delivery_rupees, status="accrued")
        db.add(fee)
    if fee.status == "accrued":
        fee.deliveries = delivered
        fee.amount_rupees = delivered * fee.fee_per_delivery_rupees
        fee.updated_at = now
    db.flush()
    return fee


def set_fee_status(db: Session, fee: SuccessFee, status: str, now: datetime) -> SuccessFee:
    if status not in FEE_TRANSITIONS[fee.status]:
        raise CampaignError(f"cannot move success fee from {fee.status} to {status}")
    fee.status = status
    fee.updated_at = now
    db.flush()
    return fee
