# GroupDrive India: Product Requirements (MVP)

## MVP scope
- Campaigns per make/model/variant/city with target and close date
- Join with refundable token deposit
- Dealer onboarding and bidding after threshold
- Best-offer comparison (discount + freebies)
- Close: winner or full refund
- Delivery tracking and success-fee reconciliation (phase 2)

## Personas
- First-time and upgrade car buyers in metros and tier-2 cities
- Dealerships wanting pre-qualified, ready-to-buy demand
- Corporate groups and housing societies buying together

## Non-goals for MVP
- Native mobile apps (web first), advanced analytics, internationalisation.

## Acceptance
- Every rule in `backend/app/services.py` has tests in `backend/tests/`.
- `/health` responds and the API deploys from the Dockerfile.
- Pricing and legal pages are reviewed against `05-legal-compliance.md` before real users are onboarded.

## API
Run the backend and open `/docs` for the generated OpenAPI documentation.
