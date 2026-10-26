from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

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
    email: Mapped[str] = mapped_column(String(200))


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
    winning_offer_id: Mapped[int | None] = mapped_column(ForeignKey("offers.id", use_alter=True), nullable=True)


class Membership(Base):
    """A buyer joining a campaign with a refundable token deposit."""

    __tablename__ = "memberships"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("buyers.id"), index=True)
    deposit_rupees: Mapped[int] = mapped_column(Integer, default=1000)
    deposit_status: Mapped[str] = mapped_column(String(20), default="held")  # held|refunded|applied
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    dealer_id: Mapped[int] = mapped_column(ForeignKey("dealers.id"))
    discount_rupees: Mapped[int] = mapped_column(Integer)  # off ex-showroom, per car
    freebies_value_rupees: Mapped[int] = mapped_column(Integer, default=0)  # accessories, warranty, etc.
    valid_until: Mapped[date] = mapped_column(Date)
