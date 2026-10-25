# Clothes AI product roadmap

## Shipped in MVP
- Uzbek mobile-first landing page
- Demo fashion catalog (not inventory)
- User photo preview with format and size validation
- No photo retention
- Flask API and CI smoke tests

## Phase 2: safe pilot
- Authenticated buyer and seller accounts, email verification, RBAC
- Seller product CRUD with cloud database and object storage
- Catalog assets and variant management
- AI inference via licensed provider with per-user rate limits, cost caps and consent
- Job status / retry / transient image storage and automated deletion
- Full image safety pipeline, privacy policy and retention notice

## Phase 3: commerce
- Checkout, payment-provider integration and webhooks
- Shipping, returns, seller reconciliation
- Size prediction based on product measurements (not visual try-on output)
- Analytics and observability

Do not claim the AI feature works until a real model, usage budget, security review and provider credentials have been configured.
