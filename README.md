# GroupDrive India

> Buy your car together. Dealers compete for a group of ready buyers.

Idea from a creator video: instead of one buyer negotiating alone, a platform gathers buyers for the same car in a city, tells dealers '20 ready buyers', compares offers and shows potential savings.

## What is in this repo
| Path | Purpose |
|---|---|
| `docs/` | Business plan, product requirements, architecture, roadmap, legal checklist, go-to-market, financial model, cloud setup |
| `backend/app/` | FastAPI service: `models.py`, `services.py` (business rules), `main.py` (routes), `deps.py`/`security.py` (auth), `payments.py`/`otp.py` (provider interfaces), `jobs.py` (scheduled close) |
| `backend/migrations/` | Alembic migrations |
| `backend/tests/` | Unit tests for every business rule plus end-to-end API tests (auth failures, full campaign lifecycle, webhook, jobs) |
| `web/index.html` | Draft landing page |
| `finance/model.py` | Editable unit-economics model |
| `Dockerfile`, `docker-compose.yml`, `render.yaml` | Container and cloud deployment |
| `.github/workflows/ci.yml` | Lint, test, build on every push |
| `.devcontainer/` | Cloud dev environment (GitHub Codespaces) |

## Quick start
```bash
cd backend
pip install -r requirements-dev.txt
pytest
alembic upgrade head              # create/upgrade the local SQLite schema
ADMIN_PHONES=9999999999 uvicorn app.main:app --reload     # http://localhost:8000/docs
python -m app.jobs close-due      # close campaigns whose date has arrived
```
In dev the OTP is printed in the server log (`DEV OTP for ...`) and deposits use a fake gateway. Log in as admin by requesting an OTP for a number listed in `ADMIN_PHONES`. All settings are documented in `.env.example`.
With Postgres: `docker compose up --build` (migrations run on start). To run the tests on Postgres: `TEST_DATABASE_URL=postgresql://... pytest`.

## Status
The backend is ready for a first-campaign pilot: OTP/JWT auth with buyer, dealer and admin roles, opt-in contact sharing, Alembic migrations, deposits behind a payment interface (fake implementation and a signature-verified webhook), delivery tracking, dealer success-fee records, a scheduled close job, rate limiting, structured logs, and CI on SQLite and Postgres.

Still needed from the owner before real users: deploy, an SMS provider, a payment aggregator and dealer partnerships. See [`docs/09-launch-checklist.md`](docs/09-launch-checklist.md). The app refuses to start with `APP_ENV=production` until those are configured.

Start reading at `docs/01-business-plan.md`.
