# GroupDrive India: Cloud Setup

Everything is designed to run in the cloud, not on a laptop.

## 1. Develop in the cloud (GitHub Codespaces)
Push this repo to GitHub, open it in a Codespace. `.devcontainer/devcontainer.json` installs dependencies automatically. Run:
```bash
cd backend && uvicorn app.main:app --reload
```

## 2. Test in the cloud
`.github/workflows/ci.yml` runs lint and tests on SQLite, then migrations (up/down/up, `alembic check`) and the full suite on Postgres, then a Docker build, on every push and pull request.

## 3. Deploy in the cloud (Render, free tier to start)
1. Push to GitHub.
2. In Render choose New > Blueprint and select the repo. `render.yaml` creates the API (from the Dockerfile) and a Postgres database. Render generates `JWT_SECRET` and `PAYMENT_WEBHOOK_SECRET`; enter your own phone number(s) as `ADMIN_PHONES` when prompted.
3. The container runs `alembic upgrade head` on every start, then the API.
4. Open `https://<service>.onrender.com/docs`.

The blueprint deploys as `APP_ENV=staging`: OTP codes are written to the service log (no SMS yet) and deposits use the fake gateway, which is fine for a demo and unsafe for real users. `APP_ENV=production` is refused until a real SMS sender and payment aggregator are configured (see [09-launch-checklist.md](09-launch-checklist.md)).

Run the campaign close job daily: `python -m app.jobs close-due` (example cron block in `render.yaml`; Render cron is not on the free plan).

Alternatives: Fly.io, Railway, Google Cloud Run (image from the Dockerfile) or AWS App Runner. Set `DATABASE_URL` from the managed Postgres.

## 4. Before real users
Follow [09-launch-checklist.md](09-launch-checklist.md).
