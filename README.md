# Clothes AI — MVP v0.1

Mobile-first AI fashion platform for virtual try-on, fashion design and commerce.

## Current implementation
- Uzbek-language responsive web experience
- Demo fashion catalog
- Client-side photo preview
- Python Flask REST API with validation
- Unit tests and GitHub Actions CI
- **Virtual try-on AI is NOT connected yet**. Valid inference requests intentionally return HTTP 503 with `AI_NOT_CONFIGURED`.
- Photos are not saved on the server.

## Run locally
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python backend/app.py
```
Visit http://127.0.0.1:5000.

## Test
```bash
python -m pytest -q
```

## REST API
- `GET /api/health`
- `GET /api/products`
- `POST /api/try-on` (multipart photo + product_id)

## Roadmap
1. Commercially licensed AI try-on integration; async jobs, throttling and budget limits
2. Authentication, explicit photo consent and deletion controls
3. Real product imagery, seller dashboard, inventory and sizing data
4. Checkout, payments, shipping and order management
5. Standalone size recommendation engine based on measurements (distinct from visual try-on)

Do not commit API keys, credentials or customer photos.