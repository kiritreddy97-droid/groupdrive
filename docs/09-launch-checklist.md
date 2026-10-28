# GroupDrive India: Launch Checklist (owner actions)

The backend is feature-complete for a first campaign. These items need accounts, money, contracts or legal sign-off, so they cannot be done in the repo. Nothing here has been deployed and the repo contains no real secrets.

## 1. Deploy (about 30 minutes)
- [ ] Create a Render account, choose New > Blueprint, select this repo (`render.yaml`).
- [ ] Set `ADMIN_PHONES` to your own 10-digit mobile number(s). You then log in as admin with the OTP flow (code appears in the service log while the console sender is in use).
- [ ] Confirm `/health` and `/docs` respond. Migrations run automatically on start.
- [ ] Schedule `python -m app.jobs close-due` daily (Render cron on a paid plan, or any scheduler that can run the image).
- [ ] Turn on automated Postgres backups (not available on Render's free database) and add error tracking such as Sentry.

## 2. SMS OTP provider
- [ ] Pick a provider (MSG91, Twilio, Gupshup, ...). In India, register the sender ID and the DLT message template first; this takes days, so start early.
- [ ] Implement `OtpSender.send(phone, code)` in `backend/app/otp.py`, add it to `build_sender`, set `OTP_SENDER` and the provider key as a secret.

## 3. Payment aggregator (deposit escrow)
- [ ] Choose an RBI-authorised payment aggregator that supports escrow/nodal holds and refunds (see `docs/05-legal-compliance.md`). Complete their business KYC.
- [ ] Implement `PaymentGateway.hold / refund / apply` in `backend/app/payments.py` and add it to `build_gateway`. Real holds are usually asynchronous: return `status="pending"` and let the webhook confirm (`deposit.held` / `deposit.failed`, body `{"type": ..., "ref": ...}`). Adapt the webhook parser if the provider's payload differs.
- [ ] Give the provider the URL `https://<service>/webhooks/payments` and set the shared signing secret as `PAYMENT_WEBHOOK_SECRET`. Check how the provider signs requests and match `security.verify_webhook`.
- [ ] Set `PAYMENT_PROVIDER` and the provider keys as secrets. Test refund and apply with test-mode keys before any real money.

## 4. Go to production mode
- [ ] Set `APP_ENV=production`. The app will refuse to start until `JWT_SECRET` (32+ characters), `PAYMENT_WEBHOOK_SECRET`, a non-console `OTP_SENDER` and a non-fake `PAYMENT_PROVIDER` are set.
- [ ] Keep `TRUST_PROXY=true` only when running behind a proxy that sets `X-Forwarded-For` (Render does).
- [ ] If you run more than one instance, replace the in-memory rate limiter in `ratelimit.py` with a Redis-backed one.

## 5. Business and legal
- [ ] Dealer partnerships: sign the first dealers in the pilot city, agree the success fee (`SUCCESS_FEE_RUPEES`, default 6,000) and the process for confirming deliveries. An admin creates each dealer account (`POST /dealers`) and shares the password securely.
- [ ] Legal review of the deposit terms, the buyer consent text shown before opting in to share contact details, privacy policy under the DPDP Act, and GST on the platform fee (`docs/05-legal-compliance.md`).
- [ ] Decide the policy when a buyer walks away from a won campaign (the deposit is `applied` today).
- [ ] Build or buy the buyer and dealer screens. The API is ready; `web/index.html` is still a draft landing page.

## 6. Running the first campaign
1. Log in as admin, create the dealer account(s) and a campaign (`POST /dealers`, `POST /campaigns`).
2. Buyers log in with OTP and join; at the target the campaign moves to `offers` and `GET /campaigns/{id}/pitch` gives the message to send dealers.
3. Dealers bid. On the close date the job (or `POST /campaigns/{id}/close`) picks the winner and settles deposits.
4. The winning dealer sees opted-in buyers and updates delivery status; each delivered car accrues the success fee, which admin invoices and marks paid.
