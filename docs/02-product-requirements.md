# GroupDrive India: Product Requirements (MVP)

## MVP scope
- Campaigns per make/model/variant/city with target and close date
- Join with refundable token deposit
- Dealer onboarding and bidding after threshold
- Best-offer comparison (discount + freebies)
- Close: winner or full refund
- Delivery tracking and success-fee record per delivered car (implemented in the backend; dealer/buyer UIs and invoicing are phase 2)
- OTP login for buyers, dealer and admin logins, buyer opt-in before contact details reach the winning dealer

## Personas
- First-time and upgrade car buyers in metros and tier-2 cities
- Dealerships wanting pre-qualified, ready-to-buy demand
- Corporate groups and housing societies buying together

## Non-goals for MVP
- Native mobile apps (web first), advanced analytics, internationalisation.

## Acceptance
- Every rule in `backend/app/services.py` has tests in `backend/tests/`, and API tests cover auth failures and the full campaign lifecycle.
- `/health` responds and the API deploys from the Dockerfile.
- Pricing and legal pages are reviewed against `05-legal-compliance.md` before real users are onboarded.

## API
Run the backend and open `/docs` for the generated OpenAPI documentation.
