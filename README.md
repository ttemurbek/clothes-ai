# Clothes AI — kiyimlar xaritasi + virtual kiyinish xonasi

Shahardagi kiyim doʻkonlarini bitta katalogga birlashtiradi: xaridor kiyimni topadi, oʻzida qanday turishini koʻradi va
**oʻlchami bor eng yaqin doʻkondan bron qiladi**. Sotuv doʻkonning oʻzida boʻladi — biz kiyim sotmaymiz, xaridorni
toʻgʻri kiyim va toʻgʻri doʻkon bilan bogʻlaymiz. Konsepsiya: [docs/PRODUCT_SPEC_UZ.md](docs/PRODUCT_SPEC_UZ.md).

## Nima ishlaydi (v0.4)

| Funksiya | Holat |
|---|---|
| Yagona katalog: qidiruv (oʻ/o‘/o' farqisiz), kategoriya, rang, oʻlcham, narx, saralash | ✅ |
| Xarita (Leaflet + OpenStreetMap), mos kiyimi bor doʻkonlar, "yaqinimda" (masofa boʻyicha) | ✅ |
| Haqiqiy qoldiq: faol bronlar qoldiqdan ayiriladi | ✅ |
| Bron: doʻkon 3 soatda tasdiqlaydi, kiyim 24 soat olib qoʻyiladi, muddat oʻtsa avtomatik tugaydi | ✅ |
| Doʻkon paneli: roʻyxatdan oʻtish, mahsulot/oʻlcham/qoldiq, rasm, bronlar, doʻkon profili va xaritadagi joyi | ✅ |
| Doʻkon statistikasi: koʻrishlar → try-on → bron → kelgan xaridorlar | ✅ |
| Telegram: Mini App (initData imzosi tekshiriladi), bot orqali bron xabari va bir tugma bilan tasdiqlash | ✅ (bot token kerak) |
| "Oilamga yuborib soʻray": 1–4 kiyimli havola, ovoz berish | ✅ |
| Virtual kiyib koʻrish: asinxron vazifalar, maxfiylik, kunlik limit | ✅ infratuzilma; AI provayder ulanmagan |
| AI fotograf (fonni tozalash, studiya rasmi) | ✅ infratuzilma; `PHOTO_PROVIDER` kerak |
| Maxfiylik: asl surat darhol, natija 24 soatda oʻchadi; "Maʼlumotlarimni oʻchirish" | ✅ |
| **AI stilist**: boʻy, vazn, tana rangi, fasl va qayerga → oʻlcham, ranglar, mavjud kiyimlardan toʻplam | ✅ qoidalar; Claude kalit bilan |
| **3D kiyinish xonasi**: boʻy/vazn/jins/tana rangidan 3D maneken, tanlangan kiyimlar kiydiriladi, 360° aylantirish | ✅ brauzerda (Three.js) |
| Onlayn toʻlov va yetkazish | ⏳ 3-bosqich |

Hozir bazada **namuna** doʻkonlar va mahsulotlar bor (sahifada ochiq belgilangan). `SEED_DEMO=0` bilan oʻchiriladi.

## AI stilist

`POST /api/stylist` (`height_cm`, `weight_kg`, `gender`, `skin_tone`, `season`, `occasion`, ixtiyoriy `budget`,
`usual_size`, `shoe_size`, `note`, `lat`/`lng`) → tahlil (BMI, qomat, taxminiy oʻlcham S/M/L va 46/48, teri rangiga
mos va mos boʻlmagan ranglar, fasl va joy talablari, maslahatlar) va **faqat hozir qoldigʻi bor** kiyimlardan
slot boʻyicha toʻplam: ustki kiyim → issiq qatlam → koʻylak → shim → poyabzal → aksessuar (toʻy/bayram uchun asosiy libos).

- Kalitsiz ishlaydi: qoidalar oʻlcham, fasl, joy, rang va qomatga qarab baho beradi (`backend/stylist.py`).
- `ANTHROPIC_API_KEY` berilsa, Claude (`STYLIST_MODEL`, standart `claude-opus-5-5`) eng yaxshi nomzodlar ichidan
  yakuniy toʻplamni tanlaydi va sababini oʻzbekcha tushuntiradi. Javob JSON sxema boʻyicha tekshiriladi, faqat
  nomzodlar roʻyxatidagi mahsulotlar qabul qilinadi; xato yoki vaqt tugasa qoidalar natijasi qaytadi.
  Rad javobi uchun server-side fallback (`fallbacks: "default"`) yoqilgan.
- Profil serverda saqlanmaydi (faqat brauzerda eslab qolinadi). AI yoqilganda boʻy/vazn/rang/istak Claude'ga yuboriladi.
- Doʻkonlar mahsulotga "kim uchun", fasl, qayerga va issiqlik darajasini belgilaydi — stilist shularga tayanadi.

## 3D kiyinish xonasi

`frontend/js/fitting3d.js` brauzerda (WebGL, `frontend/vendor/three.module.min.js` — Three.js r160, MIT, npm
paketidagi fayl bilan sha256 tekshirilgan) maneken quradi: boʻy balandlik koʻlamini, vazn (BMI) gavda kengligini,
jins proporsiyalarni, tana rangi teri tusini belgilaydi. Kiyimlar kategoriya va nomidan shakl oladi (puxovik —
qavatli, palto — tizzagacha, jinsi, yubka, libos, kostyum, botinka, sharf, ryukzak…), rangi va naqshi
(katak, atlas, trikotaj, denim) mahsulotdan. Qatlamlar tartibi: shim → koʻylak → libos → sviter → ustki kiyim.
Aylantirish (sichqoncha/barmoq), yaqinlashtirish, old/yon/orqa koʻrinish, kiyimni yoqish-oʻchirish, oʻlchamni
oʻzgartirish va rasmga olish bor. Bu siluet, rang va uygʻunlikni koʻrsatadi; matoning aniq koʻrinishi emas.

## Lokal ishga tushirish

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
.venv/bin/python -m backend
```

http://127.0.0.1:5000 — xaridor sahifasi, http://127.0.0.1:5000/seller — doʻkon paneli.
Maʼlumotlar `data/` papkasida (SQLite, rasmlar) — u gitga kirmaydi.

Try-on interfeysini AI'siz sinash: `.env` da `TRYON_PROVIDER=demo` (natija ustida "DEMO — bu AI natija emas" yoziladi).

## Testlar

```bash
.venv/bin/python -m pytest -q
```

## Administrator buyruqlari

```bash
.venv/bin/flask --app backend.app shops                           # doʻkonlar va holati
.venv/bin/flask --app backend.app approve-shop <slug>             # tekshirilgan doʻkonni katalogga chiqarish
.venv/bin/flask --app backend.app approve-shop <slug> --founding  # + "asoschi hamkor"
.venv/bin/flask --app backend.app block-shop <slug>
.venv/bin/flask --app backend.app reset-password <login>
.venv/bin/flask --app backend.app purge                           # muddati oʻtgan try-on fayllarini oʻchirish
.venv/bin/flask --app backend.app set-webhook                     # Telegram webhook + menyu tugmasi
```

## Deploy (Railway)

`Procfile`/`railway.json`: `gunicorn --workers 1 --threads 8 backend.wsgi:app`, health check `/api/health`.
Muhit oʻzgaruvchilari: `APP_ENV=production`, `SECRET_KEY` (uzun tasodifiy qator), `PUBLIC_URL=https://…`,
`DATA_DIR` (doimiy volume, masalan `/data`) yoki `DATABASE_URL` (Postgres uchun `psycopg[binary]` qoʻshing).
Bitta worker ishlatiladi: rate limit va try-on navbati jarayon ichida.

### Telegram bot
1. @BotFather → yangi bot; tokenni `TELEGRAM_BOT_TOKEN` ga, nomini `TELEGRAM_BOT_USERNAME` ga yozing.
2. `TELEGRAM_WEBHOOK_SECRET` — tasodifiy qator. `PUBLIC_URL` https boʻlishi shart.
3. `flask --app backend.app set-webhook`. BotFather'da Mini App manzili sifatida `PUBLIC_URL` ni bering.
4. Doʻkon paneli → Doʻkon → "Telegramga ulash" — bronlar shu chatga keladi.

## REST API (qisqacha)

Xaridor: `GET /api/meta`, `GET /api/products?q&category&color&size&min_price&max_price&shop&lat&lng&radius_km&sort&limit&offset`,
`GET /api/products/<id>`, `GET /api/shops`, `GET /api/shops/<slug>`, `GET /api/availability`,
`POST /api/reservations`, `GET /api/reservations/mine`, `GET|POST /api/reservations/<code>[/cancel]`,
`GET /api/try-on/status`, `POST|GET /api/try-on/jobs`, `GET|DELETE /api/try-on/jobs/<id>`, `GET …/image`, `POST …/keep`,
`POST /api/shares`, `GET /api/shares/<token>`, `POST /api/shares/<token>/vote`, `DELETE /api/me/data`.

Doʻkon (`/api/seller/…`): `register`, `login`, `logout`, `me`, `password`, `PATCH shop`, `POST shop/telegram-link`,
`products` (CRUD), `products/<id>/image`, `reservations`, `reservations/<id>/<confirm|decline|visited|sold>`, `stats`.

## Xavfsizlik
- Parollar `werkzeug` hash bilan; kirishda sessiya yangilanadi; login/roʻyxat/bron/try-on uchun rate limit.
- Holatni oʻzgartiruvchi soʻrovlarda Origin tekshiruvi (CSRF), CSP, `nosniff`, HSTS (https'da).
- Rasmlar Pillow bilan ochib tekshiriladi va qayta kodlanadi (EXIF/GPS olib tashlanadi).
- Try-on natijalari ommaviy papkada emas, faqat egasiga beriladi.
- API kalitlari, tokenlar, `.env`, `data/` hech qachon gitga qoʻshilmaydi.
