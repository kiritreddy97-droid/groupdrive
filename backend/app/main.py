from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import services
from .db import Base, engine, get_db
from .models import Buyer, Campaign, Dealer


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="GroupDrive India", lifespan=lifespan)


class BuyerIn(BaseModel):
    name: str
    phone: str
    city: str


class DealerIn(BaseModel):
    name: str
    city: str
    email: str


class CampaignIn(BaseModel):
    make: str
    model: str
    variant: str
    city: str
    ex_showroom_rupees: int
    target_buyers: int = 20
    closes_on: date


class OfferIn(BaseModel):
    dealer_id: int
    discount_rupees: int
    freebies_value_rupees: int = 0
    valid_until: date


def _get(db: Session, model, id_: int):
    obj = db.get(model, id_)
    if obj is None:
        raise HTTPException(404, f"{model.__name__} {id_} not found")
    return obj


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/buyers", status_code=201)
def create_buyer(body: BuyerIn, db: Session = Depends(get_db)):
    b = Buyer(**body.model_dump())
    db.add(b)
    db.commit()
    return {"id": b.id}


@app.post("/dealers", status_code=201)
def create_dealer(body: DealerIn, db: Session = Depends(get_db)):
    d = Dealer(**body.model_dump())
    db.add(d)
    db.commit()
    return {"id": d.id}


@app.post("/campaigns", status_code=201)
def create_campaign(body: CampaignIn, db: Session = Depends(get_db)):
    c = Campaign(**body.model_dump())
    db.add(c)
    db.commit()
    return {"id": c.id}


@app.get("/campaigns")
def list_campaigns(city: str | None = None, db: Session = Depends(get_db)):
    q = select(Campaign).where(Campaign.status.in_(["open", "offers"]))
    if city:
        q = q.where(Campaign.city.ilike(city))
    return [
        {"id": c.id, "car": f"{c.make} {c.model} {c.variant}", "city": c.city, "status": c.status,
         "joined": services.buyer_count(db, c.id), "target": c.target_buyers, "closes_on": c.closes_on}
        for c in db.scalars(q)
    ]


@app.post("/campaigns/{campaign_id}/join/{buyer_id}", status_code=201)
def join_campaign(campaign_id: int, buyer_id: int, db: Session = Depends(get_db)):
    try:
        m = services.join(db, _get(db, Campaign, campaign_id), _get(db, Buyer, buyer_id), date.today())
    except services.CampaignError as e:
        raise HTTPException(409, str(e))
    db.commit()
    return {"membership_id": m.id, "deposit_rupees": m.deposit_rupees}


@app.get("/campaigns/{campaign_id}/pitch")
def pitch(campaign_id: int, db: Session = Depends(get_db)):
    return {"message": services.dealer_pitch(db, _get(db, Campaign, campaign_id))}


@app.post("/campaigns/{campaign_id}/offers", status_code=201)
def submit_offer(campaign_id: int, body: OfferIn, db: Session = Depends(get_db)):
    try:
        o = services.submit_offer(db, _get(db, Campaign, campaign_id), _get(db, Dealer, body.dealer_id),
                                  body.discount_rupees, body.freebies_value_rupees, body.valid_until, date.today())
    except services.CampaignError as e:
        raise HTTPException(409, str(e))
    db.commit()
    return {"id": o.id}


@app.get("/campaigns/{campaign_id}/best-offer")
def best_offer(campaign_id: int, db: Session = Depends(get_db)):
    c = _get(db, Campaign, campaign_id)
    o = services.best_offer(db, c, date.today())
    if o is None:
        raise HTTPException(404, "no live offers")
    return {"offer_id": o.id, "dealer_id": o.dealer_id, "savings_pct": services.savings_pct(c, o),
            "total_value_rupees": services.offer_value(o)}


@app.post("/campaigns/{campaign_id}/close")
def close(campaign_id: int, db: Session = Depends(get_db)):
    try:
        c = services.close_campaign(db, _get(db, Campaign, campaign_id), date.today())
    except services.CampaignError as e:
        raise HTTPException(409, str(e))
    db.commit()
    return {"status": c.status, "winning_offer_id": c.winning_offer_id}
