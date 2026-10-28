"""Scheduled jobs. Run from cron / a platform scheduler:

    python -m app.jobs close-due

Closes every campaign whose closing date has arrived (winner chosen or deposits refunded) and retries any
deposit refunds/applications that failed earlier. Safe to run repeatedly. Exits non-zero if anything failed.
"""
import argparse
import logging
import sys

from . import clock, services
from .config import get_settings
from .db import SessionLocal
from .deps import payments_dep
from .logging_setup import configure_logging
from .models import Campaign
from .payments import PaymentGateway

log = logging.getLogger("groupdrive.jobs")


def close_due(session_factory=SessionLocal, payments: PaymentGateway | None = None, today=None) -> dict:
    payments = payments or payments_dep()
    today = today or clock.today()
    summary = {"closed": 0, "unsettled": 0, "errors": 0}
    with session_factory() as db:
        due_ids = [c.id for c in services.campaigns_due(db, today)]
    for campaign_id in due_ids:
        with session_factory() as db:  # one transaction per campaign so one failure cannot block the rest
            try:
                c = services.close_campaign(db, db.get(Campaign, campaign_id), today, payments)
                db.commit()
                summary["closed"] += 1
                log.info("campaign closed", extra={"campaign_id": campaign_id, "status": c.status})
            except Exception:
                db.rollback()
                summary["errors"] += 1
                log.exception("closing campaign failed", extra={"campaign_id": campaign_id})
    with session_factory() as db:
        for c in services.campaigns_unsettled(db):
            outstanding = services.settle_deposits(db, c, payments)
            db.commit()
            summary["unsettled"] += outstanding
    log.info("close-due finished", extra=summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.jobs")
    parser.add_argument("job", choices=["close-due"])
    parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    settings.validate()
    summary = close_due()
    return 1 if summary["errors"] or summary["unsettled"] else 0


if __name__ == "__main__":
    sys.exit(main())
