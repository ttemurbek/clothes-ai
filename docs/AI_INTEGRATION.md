# AI Virtual Try-On integration contract

The current POST /api/try-on endpoint deliberately returns HTTP 503 after input validation.

A commercial provider should be integrated with an asynchronous job queue, not a blocking Flask request.

Proposed contract:
- POST /api/try-on/jobs: authenticated multipart photo + product_id + user consent
- GET /api/try-on/jobs/{id}: queued | processing | completed | failed
- DELETE /api/try-on/jobs/{id}: delete temporary image and generated output

Controls to implement before enabling real uploads:
- Verified product image stored in private object storage
- Strong file decoding and image safety checks (not MIME/header alone)
- Consent for processing personal photos, explicit deletion policy
- Request authorization, per-user limits, spend caps, inference timeouts
- Encrypted short-lived storage with scheduled expiration
- Commercially authorized model and data processing agreement
- Never commit provider credentials; inject them via hosting secrets

The current demo should not be advertised as producing real virtual try-on images.
