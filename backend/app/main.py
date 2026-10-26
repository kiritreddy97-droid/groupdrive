import hmac
import json
import logging
from contextlib import asynccontextmanager
from datetime import date, timedelta

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import clock, ratelimit, security, services
from .config import Settings, get_settings
from .db import get_db
from .deps import (
    Principal,
    admin_only,
    buyer_only,
    dealer_only,
    dealer_or_admin,
    global_rate_limit,
    otp_sender_dep,
    payments_dep,
    settings_dep,
)
from .logging_setup import RequestLogMiddleware, configure_logging
from .models import Buyer, Campaign, Dealer, Delivery, Membership, Offer, OtpCode, SuccessFee
from .otp import OtpSender
from .payments import PaymentGateway

log = logging.getLogger("groupdrive.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    settings.validate()
    yield


app = FastAPI(title="GroupDrive India", lifespan=lifespan, dependencies=[Depends(global_rate_limit)])
app.add_middleware(RequestLogMiddleware)


# ---------- schemas ----------

class OtpRequestIn(BaseModel):
    phone: str


class OtpVerifyIn(BaseModel):
    phone: str
    code: str = Field(min_length=6, max_length=6)
    name: str | None = Field(default=None, min_length=1, max_length=120)  # required on first login
    city: str | None = Field(default=None, min_length=1, max_length=80)


class DealerLoginIn(BaseModel):
    email: str
    password: str


class DealerIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    city: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=10, max_length=128)


class CampaignIn(BaseModel):
    make: str = Field(min_length=1, max_length=60)
    model: str = Field(min_length=1, max_length=80)
    variant: str = Field(min_length=1, max_length=80)
    city: str = Field(min_length=1, max_length=80)
    ex_showroom_rupees: int = Field(gt=0)
    target_buyers: int = Field(default=20, ge=1)
    closes_on: date


class OfferIn(BaseModel):
    discount_rupees: int
    freebies_value_rupees: int = 0
    valid_until: date


class ConsentIn(BaseModel):
    share_contact: bool


class DeliveryIn(BaseModel):
    status: str


class FeeStatusIn(BaseModel):
    status: str


# ---------- helpers ----------

def _get(db: Session, model, id_: int):
    obj = db.get(model, id_)
    if obj is None:
        raise HTTPException(404, f"{model.__name__} {id_} not found")
    return obj


def _domain(db: Session, fn, *args, **kwargs):
    try:
        return fn(db, *args, **kwargs)
    except services.CampaignError as e:
        db.rollback()
        raise HTTPException(409, str(e)) from e


def _campaign_view(db: Session, c: Campaign) -> dict:
    return {"id": c.id, "car": f"{c.make} {c.model} {c.variant}", "city": c.city, "status": c.status,
            "joined": services.buyer_count(db, c.id), "target": c.target_buyers, "closes_on": c.closes_on}


def _winning_dealer_id(db: Session, campaign: Campaign) -> int | None:
    if campaign.winning_offer_id is None:
        return None
    return db.get(Offer, campaign.winning_offer_id).dealer_id


def _require_winner(db: Session, who: Principal, campaign: Campaign) -> None:
    """Dealers only act on campaigns they won; admins on any."""
    if who.role == "dealer" and (campaign.status != "won" or _winning_dealer_id(db, campaign) != who.id):
        raise HTTPException(403, "only the winning dealer can do this")


# ---------- public ----------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/campaigns")
def list_campaigns(city: str | None = None, db: Session = Depends(get_db)):
    q = select(Campaign).where(Campaign.status.in_(["open", "offers"]))
    if city:
        q = q.where(Campaign.city.ilike(city))
    return [_campaign_view(db, c) for c in db.scalars(q)]


@app.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: int, db: Session = Depends(get_db)):
    return _campaign_view(db, _get(db, Campaign, campaign_id))


@app.get("/campaigns/{campaign_id}/best-offer")
def best_offer(campaign_id: int, db: Session = Depends(get_db)):
    """Public headline number for the campaign page. The dealer's identity is not exposed here."""
    c = _get(db, Campaign, campaign_id)
    o = services.best_offer(db, c, clock.today())
    if o is None:
        raise HTTPException(404, "no live offers")
    return {"savings_pct": services.savings_pct(c, o), "total_value_rupees": services.offer_value(o)}


# ---------- auth ----------

@app.post("/auth/otp/request")
def otp_request(body: OtpRequestIn, request: Request, db: Session = Depends(get_db),
                settings: Settings = Depends(settings_dep), sender: OtpSender = Depends(otp_sender_dep)):
    try:
        phone = security.normalize_phone(body.phone)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    ratelimit.enforce(request, settings, "otp-request-ip", 5, 60)
    ratelimit.enforce(request, settings, "otp-request-phone", 3, 600, extra_key=phone)
    now = clock.now()
    for old in db.scalars(select(OtpCode).where(OtpCode.phone == phone, OtpCode.consumed.is_(False))):
        old.consumed = True
    code = security.new_otp()
    db.add(OtpCode(phone=phone, code_hash=security.hash_code(settings, phone, code),
                   expires_at=now + timedelta(seconds=settings.otp_ttl_seconds)))
    db.commit()
    sender.send(phone, code)
    return {"sent": True}


@app.post("/auth/otp/verify")
def otp_verify(body: OtpVerifyIn, request: Request, db: Session = Depends(get_db),
               settings: Settings = Depends(settings_dep)):
    ratelimit.enforce(request, settings, "otp-verify", 10, 60)
    try:
        phone = security.normalize_phone(body.phone)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    otp = db.scalar(select(OtpCode).where(OtpCode.phone == phone, OtpCode.consumed.is_(False))
                    .order_by(OtpCode.id.desc()))
    bad = HTTPException(401, "invalid or expired code")
    if otp is None or clock.as_utc(otp.expires_at) < clock.now():
        raise bad
    otp.attempts += 1
    if otp.attempts > settings.otp_max_attempts:
        otp.consumed = True
    ok = not otp.consumed and hmac.compare_digest(otp.code_hash, security.hash_code(settings, phone, body.code))
    if not ok:
        db.commit()  # persist the attempt count
        raise bad
    otp.consumed = True
    if phone in settings.admin_phones:
        db.commit()
        return {"access_token": security.issue_token(settings, phone, "admin"), "token_type": "bearer",
                "role": "admin"}
    buyer = db.scalar(select(Buyer).where(Buyer.phone == phone))
    if buyer is None:
        if not body.name or not body.city:
            db.commit()
            raise HTTPException(422, "name and city are required for a new account")
        buyer = Buyer(name=body.name, phone=phone, city=body.city)
        db.add(buyer)
        db.flush()
    db.commit()
    return {"access_token": security.issue_token(settings, buyer.id, "buyer"), "token_type": "bearer",
            "role": "buyer"}


_DUMMY_HASH = security.hash_password("not-a-real-password")


@app.post("/auth/dealer/login")
def dealer_login(body: DealerLoginIn, request: Request, db: Session = Depends(get_db),
                 settings: Settings = Depends(settings_dep)):
    ratelimit.enforce(request, settings, "dealer-login", 10, 60)
    dealer = db.scalar(select(Dealer).where(Dealer.email == body.email.lower()))
    stored = dealer.password_hash if dealer and dealer.password_hash else _DUMMY_HASH
    ok = security.verify_password(body.password, stored)  # always hashes, so timing does not reveal the email
    if not (ok and dealer and dealer.active):
        raise HTTPException(401, "invalid email or password")
    return {"access_token": security.issue_token(settings, dealer.id, "dealer"), "token_type": "bearer",
            "role": "dealer"}


# ---------- buyer ----------

@app.get("/me")
def me(who: Principal = Depends(buyer_only)):
    b = who.obj
    return {"id": b.id, "name": b.name, "phone": b.phone, "city": b.city}


@app.post("/campaigns/{campaign_id}/join", status_code=201)
def join_campaign(campaign_id: int, who: Principal = Depends(buyer_only), db: Session = Depends(get_db),
                  settings: Settings = Depends(settings_dep), payments: PaymentGateway = Depends(payments_dep)):
    m = _domain(db, services.join, _get(db, Campaign, campaign_id), who.obj, clock.today(), payments,
                settings.deposit_rupees)
    db.commit()
    return {"membership_id": m.id, "deposit_rupees": m.deposit_rupees, "deposit_status": m.deposit_status}


@app.put("/campaigns/{campaign_id}/contact-consent")
def contact_consent(campaign_id: int, body: ConsentIn, who: Principal = Depends(buyer_only),
                    db: Session = Depends(get_db)):
    """Opt in (or out) of sharing name and phone with the winning dealer."""
    m = db.scalar(select(Membership).where(Membership.campaign_id == campaign_id, Membership.buyer_id == who.id))
    if m is None:
        raise HTTPException(404, "you have not joined this campaign")
    m.share_contact = body.share_contact
    db.commit()
    return {"share_contact": m.share_contact}


@app.get("/me/memberships")
def my_memberships(who: Principal = Depends(buyer_only), db: Session = Depends(get_db)):
    out = []
    for m in db.scalars(select(Membership).where(Membership.buyer_id == who.id).order_by(Membership.id)):
        c = db.get(Campaign, m.campaign_id)
        d = db.scalar(select(Delivery).where(Delivery.membership_id == m.id))
        dealer_id = _winning_dealer_id(db, c)
        out.append({
            "membership_id": m.id, "campaign": _campaign_view(db, c), "deposit_status": m.deposit_status,
            "share_contact": m.share_contact, "delivery_status": d.status if d else None,
            "winning_dealer": db.get(Dealer, dealer_id).name if dealer_id else None,
        })
    return out


# ---------- dealer ----------

@app.get("/campaigns/{campaign_id}/pitch")
def pitch(campaign_id: int, _: Principal = Depends(dealer_or_admin), db: Session = Depends(get_db)):
    return {"message": services.dealer_pitch(db, _get(db, Campaign, campaign_id))}


@app.post("/campaigns/{campaign_id}/offers", status_code=201)
def submit_offer(campaign_id: int, body: OfferIn, who: Principal = Depends(dealer_only),
                 db: Session = Depends(get_db)):
    o = _domain(db, services.submit_offer, _get(db, Campaign, campaign_id), who.obj, body.discount_rupees,
                body.freebies_value_rupees, body.valid_until, clock.today())
    db.commit()
    return {"id": o.id}


@app.get("/campaigns/{campaign_id}/buyers")
def campaign_buyers(campaign_id: int, who: Principal = Depends(dealer_or_admin), db: Session = Depends(get_db)):
    """The winning dealer's customer list. Name and phone appear only for buyers who opted in."""
    c = _get(db, Campaign, campaign_id)
    _require_winner(db, who, c)
    rows = []
    for m in db.scalars(select(Membership).where(Membership.campaign_id == c.id).order_by(Membership.id)):
        d = db.scalar(select(Delivery).where(Delivery.membership_id == m.id))
        if d is None:
            continue  # not part of the winning group (deposit refunded)
        row = {"membership_id": m.id, "delivery_status": d.status, "contact": None}
        if m.share_contact:
            b = db.get(Buyer, m.buyer_id)
            row["contact"] = {"name": b.name, "phone": b.phone}
        rows.append(row)
    return rows


@app.put("/campaigns/{campaign_id}/deliveries/{membership_id}")
def update_delivery(campaign_id: int, membership_id: int, body: DeliveryIn, who: Principal = Depends(dealer_or_admin),
                    db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    c = _get(db, Campaign, campaign_id)
    _require_winner(db, who, c)
    d = db.scalar(select(Delivery).where(Delivery.campaign_id == c.id, Delivery.membership_id == membership_id))
    if d is None:
        raise HTTPException(404, "delivery not found")
    _domain(db, services.update_delivery, d, body.status, clock.today(), clock.now(), settings.success_fee_rupees)
    db.commit()
    return {"membership_id": membership_id, "status": d.status}


def _fee_view(f: SuccessFee) -> dict:
    return {"id": f.id, "campaign_id": f.campaign_id, "dealer_id": f.dealer_id, "deliveries": f.deliveries,
            "fee_per_delivery_rupees": f.fee_per_delivery_rupees, "amount_rupees": f.amount_rupees,
            "status": f.status}


@app.get("/dealer/success-fees")
def dealer_fees(who: Principal = Depends(dealer_only), db: Session = Depends(get_db)):
    return [_fee_view(f) for f in db.scalars(select(SuccessFee).where(SuccessFee.dealer_id == who.id))]


# ---------- admin ----------

@app.post("/dealers", status_code=201)
def create_dealer(body: DealerIn, _: Principal = Depends(admin_only), db: Session = Depends(get_db)):
    d = Dealer(name=body.name, city=body.city, email=body.email.lower(),
               password_hash=security.hash_password(body.password))
    db.add(d)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "a dealer with this email already exists") from None
    return {"id": d.id}


@app.post("/campaigns", status_code=201)
def create_campaign(body: CampaignIn, _: Principal = Depends(admin_only), db: Session = Depends(get_db)):
    c = Campaign(**body.model_dump())
    db.add(c)
    db.commit()
    return {"id": c.id}


@app.post("/campaigns/{campaign_id}/close")
def close(campaign_id: int, _: Principal = Depends(admin_only), db: Session = Depends(get_db),
          payments: PaymentGateway = Depends(payments_dep)):
    c = _domain(db, services.close_campaign, _get(db, Campaign, campaign_id), clock.today(), payments)
    db.commit()
    return {"status": c.status, "winning_offer_id": c.winning_offer_id}


@app.post("/campaigns/{campaign_id}/settle-deposits")
def settle(campaign_id: int, _: Principal = Depends(admin_only), db: Session = Depends(get_db),
           payments: PaymentGateway = Depends(payments_dep)):
    """Retry deposit refunds/applications that failed at the payment provider."""
    outstanding = _domain(db, services.settle_deposits, _get(db, Campaign, campaign_id), payments)
    db.commit()
    return {"outstanding": outstanding}


@app.post("/campaigns/{campaign_id}/success-fee")
def refresh_success_fee(campaign_id: int, _: Principal = Depends(admin_only), db: Session = Depends(get_db),
                        settings: Settings = Depends(settings_dep)):
    f = _domain(db, services.accrue_success_fee, _get(db, Campaign, campaign_id), settings.success_fee_rupees,
                clock.now())
    db.commit()
    return _fee_view(f)


@app.get("/success-fees")
def list_fees(_: Principal = Depends(admin_only), db: Session = Depends(get_db)):
    return [_fee_view(f) for f in db.scalars(select(SuccessFee).order_by(SuccessFee.id))]


@app.put("/success-fees/{fee_id}")
def update_fee(fee_id: int, body: FeeStatusIn, _: Principal = Depends(admin_only), db: Session = Depends(get_db)):
    f = _domain(db, services.set_fee_status, _get(db, SuccessFee, fee_id), body.status, clock.now())
    db.commit()
    return _fee_view(f)


# ---------- payment provider webhook ----------

@app.post("/webhooks/payments")
async def payments_webhook(request: Request, db: Session = Depends(get_db),
                           settings: Settings = Depends(settings_dep),
                           payments: PaymentGateway = Depends(payments_dep)):
    """Signed by the provider: HMAC-SHA256 of the raw body in the X-Signature header."""
    body = await request.body()
    if not security.verify_webhook(settings.payment_webhook_secret, body, request.headers.get("x-signature")):
        raise HTTPException(401, "invalid signature")
    try:
        event = json.loads(body)
        kind, ref = event["type"], event["ref"]
    except (ValueError, KeyError, TypeError):
        raise HTTPException(400, "malformed event") from None
    if kind not in ("deposit.held", "deposit.failed"):
        return {"ignored": True}
    m = db.scalar(select(Membership).where(Membership.deposit_ref == ref))
    if m is None:
        return {"ignored": True}  # acknowledge so the provider stops retrying an unknown reference
    services.confirm_deposit(db, m, kind == "deposit.held", payments)
    db.commit()
    return {"ok": True, "deposit_status": m.deposit_status}
