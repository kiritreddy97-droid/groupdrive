# GroupDrive India

> Buy your car together. Dealers compete for a group of ready buyers.

Idea from a creator video: instead of one buyer negotiating alone, a platform gathers buyers for the same car in a city, tells dealers '20 ready buyers', compares offers and shows potential savings.

## What is in this repo
| Path | Purpose |
|---|---|
| `docs/` | Business plan, product requirements, architecture, roadmap, legal checklist, go-to-market, financial model, cloud setup |
| `backend/app/` | FastAPI service: `models.py`, `services.py` (business rules), `main.py` (routes) |
| `backend/tests/` | Unit tests for every business rule, plus an API smoke test |
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
uvicorn app.main:app --reload     # http://localhost:8000/docs
```
With Postgres: `docker compose up --build`.

## Status
Backend MVP of the core rules is implemented and tested. Not production-ready: authentication, migrations, payments and integrations are listed as to-do in `docs/03-architecture.md`.

Start reading at `docs/01-business-plan.md`.
