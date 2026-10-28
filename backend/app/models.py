from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from . import clock
from .db import Base


class Buyer(Base):
    __tablename__ = "buyers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20), unique=True)
    city: Mapped[str] = mapped_column(String(80))


class Dealer(Base):
    __tablename__ = "dealers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    city: Mapped[str] = mapped_column(String(80), index=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class OtpCode(Base):
    """A one-time login code. Only a keyed hash is stored, never the code."""

    __tablename__ = "otp_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=clock.now)


class Campaign(Base):
    """A group buy for one car variant in one city."""

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    make: Mapped[str] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(80))
    variant: Mapped[str] = mapped_column(String(80))
    city: Mapped[str] = mapped_column(String(80), index=True)
    ex_showroom_rupees: Mapped[int] = mapped_column(Integer)
    target_buyers: Mapped[int] = mapped_column(Integer, default=20)
    closes_on: Mapped[date] = mapped_column(Date)
    # open -> offers -> won | failed
    status: Mapped[str] = mapped_column(String(20), default="open")
    winning_offer_id: Mapped[int | None] = mapped_column(
        ForeignKey("offers.id", use_alter=True, name="fk_campaigns_winning_offer_id"), nullable=True
    )


class Membership(Base):
    """A buyer joining a campaign with a refundable token deposit."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("campaign_id", "buyer_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("buyers.id"), index=True)
    deposit_rupees: Mapped[int] = mapped_column(Integer, default=1000)
    # pending|held|failed|refunded|applied|refund_failed|apply_failed
    deposit_status: Mapped[str] = mapped_column(String(20), default="pending")
    deposit_ref: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    share_contact: Mapped[bool] = mapped_column(Boolean, default=False)  # buyer opt-in to reveal contact to the winner
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=clock.now)


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    dealer_id: Mapped[int] = mapped_column(ForeignKey("dealers.id"))
    discount_rupees: Mapped[int] = mapped_column(Integer)  # off ex-showroom, per car
    freebies_value_rupees: Mapped[int] = mapped_column(Integer, default=0)  # accessories, warranty, etc.
    valid_until: Mapped[date] = mapped_column(Date)


class Delivery(Base):
    """Tracks one buyer's car from booking to delivery after a campaign is won."""

    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    membership_id: Mapped[int] = mapped_column(ForeignKey("memberships.id"), unique=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="booked")  # booked|invoiced|delivered|cancelled
    delivered_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=clock.now)


class SuccessFee(Base):
    """What the winning dealer owes the platform: a fixed fee per delivered car (phase 2 in docs/02)."""

    __tablename__ = "success_fees"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), unique=True)
    dealer_id: Mapped[int] = mapped_column(ForeignKey("dealers.id"), index=True)
    deliveries: Mapped[int] = mapped_column(Integer, default=0)
    fee_per_delivery_rupees: Mapped[int] = mapped_column(Integer)
    amount_rupees: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="accrued")  # accrued|invoiced|paid|waived
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=clock.now)
