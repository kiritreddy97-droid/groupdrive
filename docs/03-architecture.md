# GroupDrive India: Architecture

```
 Web / mobile client
        |  HTTPS
   FastAPI service  (backend/app/main.py: routes only)
        |
   services.py      (all business rules; pure functions over a DB session; unit-tested)
        |
   SQLAlchemy models --> PostgreSQL (SQLite for local dev and tests)
```

## Principles
- Business rules live in `services.py`, not in route handlers, so they are testable without HTTP.
- Time is passed in (`today`) or read from `clock.py` (which tests patch), always timezone-aware.
- Schema changes only through Alembic: edit `models.py`, then `alembic revision --autogenerate -m "..."`.
- Route handlers translate domain errors to HTTP status codes and commit the transaction.
- Money is stored in integer rupees or paise; never floats.

## Backend modules
| Module | Responsibility |
|---|---|
| `main.py` | Routes, request schemas, domain-error to HTTP translation |
| `deps.py` | Auth dependencies (`buyer_only`, `dealer_only`, `admin_only`, ...), injectable settings, OTP sender, payment gateway |
| `services.py` | All business rules: join, offers, close, deposit settlement, delivery state machine, success fee |
| `security.py` | JWT, OTP hashing, scrypt passwords, webhook HMAC, phone normalisation |
| `otp.py` / `payments.py` | Interfaces (`OtpSender`, `PaymentGateway`) with console / fake implementations |
| `jobs.py` | Scheduled close job: `python -m app.jobs close-due` |
| `ratelimit.py`, `logging_setup.py`, `clock.py`, `config.py` | Cross-cutting concerns |
| `migrations/` | Alembic migrations (the only way the schema changes) |

## Access model
| Role | How they log in | Can do |
|---|---|---|
| Public | none | health, list/view campaigns, headline best-offer saving (no dealer identity) |
| Buyer | OTP by SMS to their phone (`/auth/otp/request`, `/auth/otp/verify`; the account is created on first login) | join a campaign, opt in to contact sharing, see their own memberships |
| Dealer | email + password (`/auth/dealer/login`); accounts are created by an admin | read the pitch, bid in their own city, and, only as the winner, see the buyer list and update delivery status |
| Admin | OTP, for phones listed in `ADMIN_PHONES` | create dealers and campaigns, close campaigns, retry deposit settlement, manage success fees |
| Payment provider | HMAC-SHA256 signature of the body in `X-Signature` | `/webhooks/payments` only |

Buyer contact details (name, phone) are never in a dealer response unless that buyer opted in for that campaign **and** the dealer is the campaign's winner. Opting out again takes effect on the next request.

## Money flow
`join` calls `PaymentGateway.hold` (deposit goes to the aggregator's escrow, never to the platform). A deposit counts toward the campaign threshold only once it is `held` (immediately, or after a `deposit.held` webhook). On close the winner's buyers have their deposit `apply`-ed towards the purchase and every other deposit is `refund`-ed. A failed provider call leaves the deposit as `refund_failed` / `apply_failed`; `POST /campaigns/{id}/settle-deposits` and the scheduled job retry it. Money is integer rupees.

## Delivery and success fee (phase 2)
Winning a campaign creates one delivery per buyer (`booked`, then `invoiced`, then `delivered`, or `cancelled`). Each delivery marked `delivered` accrues `SUCCESS_FEE_RUPEES` (default 6,000, see `docs/07-financial-model.md`) to the winning dealer in a `success_fees` record. Admin moves it `accrued` -> `invoiced` -> `paid` (or `waived`); amounts freeze once invoiced. GST and invoicing documents are outside the system for now.

## Scheduled job
`python -m app.jobs close-due` closes every campaign whose close date has arrived and retries failed deposit settlements. It is idempotent and exits non-zero if anything failed. Run it daily (00:00 IST) from cron or a platform scheduler; a commented example is in `render.yaml`.

## Production hardening checklist
Done in code:
- [x] Authentication and authorisation: OTP + JWT for buyers, password login for dealers, admin role, every non-public route protected, contact reveal gated by opt-in.
- [x] Alembic migrations instead of `create_all`; CI migrates a real Postgres up, down, up and runs `alembic check`.
- [x] Timezone-aware time (`clock.py`); campaign dates use India time.
- [x] Payments behind an interface with a fake implementation and a signature-verified webhook.
- [x] Rate limiting (per IP globally, tighter on login/OTP, per phone for OTP requests) and structured JSON logs with request ids.
- [x] Production refuses to start with a missing/short `JWT_SECRET`, no webhook secret, the console OTP sender or the fake gateway.

Needs the owner or further work (see [09-launch-checklist.md](09-launch-checklist.md)):
- [ ] A real SMS sender and a real payment aggregator implementation of the two interfaces.
- [ ] Rate-limit counters are per process; move to Redis if running more than one instance.
- [ ] Error tracking (e.g. Sentry), database backups and alerting.
- [ ] Secrets in the host's secret manager, never in the repo.
- [ ] A refund path for a buyer who walks away from a won campaign (deposit is `applied` today).
- [ ] GST invoicing for the success fee.

## Environments
`local` (SQLite or docker compose Postgres), `staging` and `production` on a cloud host. See [08-cloud-deploy.md](08-cloud-deploy.md).
