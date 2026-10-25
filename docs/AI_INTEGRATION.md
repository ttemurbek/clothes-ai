# AI integration (try-on and AI photographer)

Both features are wired end to end; only the model provider is missing.

## Virtual try-on (`backend/tryon.py`, `backend/api/tryon.py`)
- `POST /api/try-on/jobs` (multipart `photo`, `product_id`, `consent=1`) -> 202 with a job id.
  With `TRYON_PROVIDER=none` the request is rejected with 503 `AI_NOT_CONFIGURED` **before anything is stored**.
- `GET /api/try-on/jobs/{id}` -> `queued | processing | completed | failed`; `GET .../image` returns the result to its owner only.
- `POST .../keep` keeps a result for 30 days; `DELETE .../{id}` and `DELETE /api/me/data` remove files immediately.
- The photo is decoded and re-encoded by Pillow (EXIF/GPS removed), stored under `DATA_DIR/private/tryon`
  (never served statically) and deleted as soon as the provider finishes. Results expire after
  `PHOTO_RETENTION_HOURS` (default 24); a cleanup runs every 10 minutes and via `flask purge`.
- Limits: `TRYON_DAILY_LIMIT` per user per day, 20/hour per IP, 2 concurrent provider calls.

### Providers
- `demo`: your own photo with a "DEMO - not AI" banner, for UI work.
- `http`: POST `person_image` + `garment_image` (the product photo) + `category` to `TRYON_API_URL`
  with `Authorization: Bearer TRYON_API_KEY`; the reply may be an image, or JSON with `image_base64` / `image_url`.
  Put a small adapter service in front of any vendor whose API differs.

Licensing: many open try-on models (e.g. IDM-VTON, OOTDiffusion) are research / non-commercial licences.
Use a commercially licensed API or model and sign a data processing agreement before going live.
Products need a photo to be tried on.

## AI photographer (`backend/photo.py`)
Seller uploads with the "AI fotograf" box ticked are cut out and placed on a square studio background with a soft shadow.
`PHOTO_PROVIDER=rembg` runs locally (`pip install rembg`); `http` posts the photo to `PHOTO_API_URL`
and expects a PNG/WebP with alpha. On any failure the plain (re-encoded) photo is saved and the seller is told.

Do not advertise try-on as working until a real provider, budget limits and a privacy review are in place.
