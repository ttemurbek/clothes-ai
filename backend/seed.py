"""Demo data: clearly labelled sample shops in Tashkent. Not real businesses or addresses.

Demo product photos are openly licensed (Creative Commons / public domain, found via Openverse) and live in
backend/demo_media with their credits in manifest.json. They are shown with the author and licence and are
meant to be removed together with the demo shops before launch.
"""
import hashlib
import json
import os
import shutil
from pathlib import Path

from sqlalchemy import select
from werkzeug.security import generate_password_hash

from .models import Product, Seller, Shop, Variant
from .utils import norm_text, size_key

DEMO_SHOPS = [
    ("demo-oq-libos", "Oq Libos (namuna)", "Chilonzor", 41.2756, 69.2034, "10:00–20:00",
     "Kelinlik va kechki liboslar. Namuna doʻkon."),
    ("demo-kostyum-uyi", "Kostyum Uyi (namuna)", "Yunusobod", 41.3643, 69.2847, "09:00–21:00",
     "Erkaklar kostyumlari, koʻylaklar. Namuna doʻkon."),
    ("demo-atlas", "Atlas & Adras (namuna)", "Shayxontohur", 41.3260, 69.2280, "09:00–19:00",
     "Milliy liboslar va matolar. Namuna doʻkon."),
    ("demo-kechki", "Kechki Yulduz (namuna)", "Mirobod", 41.2953, 69.2826, "11:00–22:00",
     "Kechki va bayram liboslari. Namuna doʻkon."),
    ("demo-shahar", "Shahar Uslubi (namuna)", "Mirzo Ulugʻbek", 41.3380, 69.3350, "10:00–21:00",
     "Kundalik va ustki kiyimlar. Namuna doʻkon."),
    ("demo-bolajon", "Bolajon (namuna)", "Yakkasaroy", 41.2870, 69.2550, "10:00–20:00",
     "Bolalar uchun bayram kiyimlari. Namuna doʻkon."),
    ("demo-qishki", "Qishki Uslub (namuna)", "Olmazor", 41.3480, 69.2200, "10:00–21:00",
     "Talabalar va har kun uchun qishki kiyimlar. Namuna doʻkon."),
]

ALL = "qish,bahor,yoz,kuz"
COLD = "kuz,qish"
WARM = "bahor,yoz,kuz"
LETTERS = {"S": 2, "M": 3, "L": 2, "XL": 1}

# (shop slug, name, category, color, price, {size: stock}, description, gender, seasons, occasions, warmth)
DEMO_PRODUCTS = [
    ("demo-oq-libos", "Klassik atlas kelinlik libosi", "Kelinlik libosi", "Oq", 6_900_000,
     {"XS": 1, "S": 2, "M": 1, "L": 0}, "Uzun etak, yopiq yelka, qoʻlda tikilgan marvarid bezaklar.",
     "ayol", ALL, "toy", 0),
    ("demo-oq-libos", "Yengil shifon kelinlik libosi", "Kelinlik libosi", "Oq", 4_500_000,
     {"S": 1, "M": 2, "L": 1}, "Yozgi toʻylar uchun yengil, ochiq yelkali model.", "ayol", WARM, "toy", 0),
    ("demo-oq-libos", "Fotinli nikoh libosi", "Kelinlik libosi", "Kumush rang", 8_200_000,
     {"S": 0, "M": 1, "L": 1, "XL": 1}, "Uzun shleyf, kumush iplar bilan kashta.", "ayol", ALL, "toy", 1),
    ("demo-oq-libos", "Qizlar oqshomi libosi", "Kechki libos", "Pushti", 1_650_000,
     {"XS": 2, "S": 3, "M": 2}, "Qizlar oqshomi va unashtiruv uchun.", "ayol", WARM, "bayram,toy", 0),
    ("demo-kostyum-uyi", "Klassik toʻy kostyumi", "Kostyum", "Qora", 2_400_000,
     {"46": 1, "48": 3, "50": 2, "52": 1, "54": 0}, "Ikki tugmali, jun aralash mato. Shim bilan.",
     "erkak", ALL, "toy,bayram,ish", 1),
    ("demo-kostyum-uyi", "Slim-fit kostyum", "Kostyum", "Koʻk", 1_900_000,
     {"46": 2, "48": 2, "50": 0, "52": 1}, "Toʻq koʻk, tor bichim.", "erkak", ALL, "ish,toy,bayram", 1),
    ("demo-kostyum-uyi", "Bej yozgi kostyum", "Kostyum", "Bej", 1_750_000,
     {"48": 1, "50": 2, "52": 2}, "Zigʻir aralash, yozgi tadbirlar uchun.", "erkak", "bahor,yoz", "toy,bayram,ish", 0),
    ("demo-kostyum-uyi", "Oq klassik koʻylak", "Koʻylak", "Oq", 329_000,
     {"S": 4, "M": 6, "L": 5, "XL": 2}, "Paxta, kostyum ostiga.", "erkak", ALL, "ish,oqish,toy,bayram", 0),
    ("demo-atlas", "Xon atlas koʻylak", "Milliy libos", "Rang-barang", 1_200_000,
     {"S": 2, "M": 2, "L": 1}, "Margʻilon xon atlasidan, zamonaviy bichim.", "ayol", WARM, "bayram,toy", 0),
    ("demo-atlas", "Zarbof chopon", "Milliy libos", "Oltin rang", 3_100_000,
     {"M": 1, "L": 1, "XL": 1}, "Toʻy va bayramlar uchun zarbof chopon.", "erkak", COLD, "toy,bayram", 2),
    ("demo-atlas", "Adras kamzul", "Milliy libos", "Rang-barang", 690_000,
     {"S": 1, "M": 3, "L": 2}, "Adras matosidan kalta kamzul.", "ayol", "bahor,kuz", "kundalik,bayram", 1),
    ("demo-kechki", "Baxmal kechki libos", "Kechki libos", "Binafsha", 1_950_000,
     {"XS": 1, "S": 1, "M": 0, "L": 1}, "Baxmal, uzun yeng, belbogʻ bilan.", "ayol", COLD, "bayram,toy", 1),
    ("demo-kechki", "Atlas uzun libos", "Kechki libos", "Qizil", 2_300_000,
     {"S": 2, "M": 1, "L": 1}, "Ochiq yelkali, yerga tushadigan etak.", "ayol", WARM, "bayram,toy", 0),
    ("demo-kechki", "Paetkali kokteyl libosi", "Kechki libos", "Oltin rang", 1_400_000,
     {"XS": 1, "S": 2, "M": 2}, "Tizzagacha, paetkalar bilan.", "ayol", ALL, "bayram", 0),
    ("demo-shahar", "Essential trench palto", "Ustki kiyim", "Bej", 895_000,
     {"S": 0, "M": 1, "L": 2}, "Kuzgi palto, belbogʻli. Qishda issiq sviter bilan.", "unisex", "bahor,kuz",
     "oqish,ish,kundalik", 1),
    ("demo-shahar", "Minimal blazer", "Ustki kiyim", "Qora", 549_000,
     {"S": 1, "M": 2, "L": 0}, "Ofis va tadbirlar uchun.", "unisex", "bahor,kuz", "ish,oqish,bayram", 1),
    ("demo-bolajon", "Bayramona qizcha libosi", "Bolalar kiyimi", "Pushti", 420_000,
     {"98": 2, "104": 3, "110": 2, "116": 1}, "Tyul etakli, 3–6 yosh.", "bola", ALL, "bayram,toy", 0),
    ("demo-bolajon", "Oʻgʻil bola kostyumi", "Bolalar kiyimi", "Kulrang", 560_000,
     {"104": 1, "110": 2, "116": 2, "122": 1}, "Jilet, shim va koʻylak toʻplami.", "bola", ALL, "bayram,toy", 0),

    # everyday winter wear (students, work, city)
    ("demo-qishki", "Issiq puxovik kurtka", "Ustki kiyim", "Bej", 890_000,
     {"S": 2, "M": 3, "L": 2, "XL": 1}, "Qaymoqrang, kapyushonli, −15 °C gacha issiq. Yengil va ixcham.",
     "erkak", "qish", "oqish,kundalik,sayohat", 3),
    ("demo-qishki", "Jun aralash palto", "Ustki kiyim", "Jigarrang", 1_250_000,
     {"S": 1, "M": 2, "L": 2, "XL": 1}, "Tizzagacha klassik palto, jigarrang tvid, 60% jun.", "erkak", COLD, "ish,oqish,bayram", 3),
    ("demo-qishki", "Qisqa qishki kurtka", "Ustki kiyim", "Jigarrang", 720_000,
     {"S": 1, "M": 2, "L": 1}, "Charm bomber, ichi flis, −10 °C gacha.", "erkak", "kuz,qish", "oqish,kundalik,sport", 2),
    ("demo-qishki", "Yarim boʻgʻiz trikotaj sviter", "Sviter va kofta", "Bej", 340_000,
     {"S": 3, "M": 3, "L": 2, "XL": 1}, "Qaymoqrang, yumshoq jun aralash. Kurtka ostiga qatlam.", "erkak", COLD,
     "oqish,ish,kundalik", 2),
    ("demo-qishki", "Flis kofta", "Sviter va kofta", "Kulrang", 260_000,
     LETTERS, "Yengil va issiq, yoqasi zamokli.", "unisex", COLD, "oqish,kundalik,sport,sayohat", 2),
    ("demo-qishki", "Toʻq koʻk jun sviter", "Sviter va kofta", "Koʻk", 380_000,
     {"S": 2, "M": 2, "L": 2}, "Dumaloq yoqa, koʻylak ustidan kiyiladi.", "erkak", COLD, "oqish,ish", 2),
    ("demo-qishki", "Flanel katak koʻylak", "Koʻylak", "Qizil", 240_000,
     LETTERS, "Bordo katak, qalin paxta flanel.", "erkak", COLD, "oqish,kundalik", 1),
    ("demo-qishki", "Oksford koʻylak", "Koʻylak", "Moviy", 260_000,
     LETTERS, "Och moviy, sviter ostiga yoqasi chiroyli chiqadi.", "erkak", ALL, "oqish,ish", 0),
    ("demo-qishki", "Klassik toʻgʻri jinsi", "Shim va yubka", "Koʻk", 380_000,
     LETTERS, "Toʻq indigo, toʻgʻri bichim, qalin denim.", "erkak", "kuz,qish,bahor", "oqish,kundalik,sayohat", 1),
    ("demo-qishki", "Issiq chino shim", "Shim va yubka", "Jigarrang", 360_000,
     {"S": 2, "M": 2, "L": 1}, "Ichi yumshoq, ofis va oʻqish uchun.", "erkak", COLD, "oqish,ish", 1),
    ("demo-qishki", "Charm qishki botinka", "Poyabzal", "Jigarrang", 650_000,
     {"40": 1, "41": 2, "42": 2, "43": 2, "44": 1}, "Ichi moʻynali, sirpanmaydigan taglik.", "erkak", COLD,
     "oqish,kundalik,ish,sayohat", 2),
    ("demo-qishki", "Qishki krossovka", "Poyabzal", "Qora", 540_000,
     {"40": 2, "41": 2, "42": 2, "43": 1, "44": 1}, "Suv oʻtkazmaydigan, issiq astarli.", "erkak", COLD,
     "oqish,kundalik,sport", 1),
    ("demo-qishki", "Jun sharf", "Aksessuar", "Kulrang", 120_000,
     {"Standart": 8}, "Yumshoq jun aralash.", "unisex", "qish", "oqish,kundalik,ish,sayohat", 1),
    ("demo-qishki", "Oʻquvchi ryukzagi", "Aksessuar", "Qora", 290_000,
     {"Standart": 5}, "Noutbuk boʻlimi 15,6″, suv oʻtkazmaydi.", "unisex", ALL, "oqish,sayohat", 0),
    ("demo-qishki", "Uzun puxovik palto", "Ustki kiyim", "Yashil", 1_100_000,
     {"XS": 1, "S": 2, "M": 2, "L": 1}, "Yalpiz-yashil, kapyushonli, tizzagacha, −20 °C gacha.", "ayol", "qish",
     "oqish,kundalik,ish", 3),
    ("demo-qishki", "Oversize trikotaj sviter", "Sviter va kofta", "Moviy", 320_000,
     {"XS": 1, "S": 2, "M": 2, "L": 1}, "Yumshoq, keng bichim.", "ayol", COLD, "oqish,kundalik", 2),
    ("demo-qishki", "Oq bluzka", "Koʻylak", "Oq", 230_000,
     {"XS": 1, "S": 2, "M": 2, "L": 1}, "Sviter yoki jaket ostiga.", "ayol", ALL, "oqish,ish", 0),
    ("demo-qishki", "Issiq midi yubka", "Shim va yubka", "Koʻk", 290_000,
     {"XS": 1, "S": 2, "M": 2, "L": 1}, "Toʻq koʻk katak, burmali, qalin kolgotka bilan.", "ayol", COLD, "oqish,ish", 1),
    ("demo-qishki", "Keng klassik shim", "Shim va yubka", "Kulrang", 310_000,
     {"XS": 1, "S": 2, "M": 2, "L": 1}, "Baland bel, issiq mato.", "ayol", COLD, "oqish,ish", 1),
    ("demo-qishki", "Qishki etik", "Poyabzal", "Qora", 720_000,
     {"36": 1, "37": 2, "38": 2, "39": 1, "40": 1}, "Ichi moʻynali, past poshna.", "ayol", "qish",
     "oqish,kundalik,ish", 2),
    ("demo-qishki", "Jun roʻmol-sharf", "Aksessuar", "Bej", 140_000,
     {"Standart": 6}, "Katta, yumshoq.", "ayol", "qish", "oqish,kundalik,ish", 1),
]


def product_search_text(product, shop):
    return norm_text(" ".join(x or "" for x in [product.name, product.category, product.color, product.description,
                                                shop.name, shop.district]))


def _sorted_sizes(stock):
    return sorted(stock, key=lambda s: (size_key(s), int(s) if s.isdigit() else 0))


DEMO_MEDIA = Path(__file__).resolve().parent / "demo_media"


def _demo_photos():
    path = DEMO_MEDIA / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _attach_photo(product, entry, media_dir):
    """Copy a demo photo into the media folder (content-addressed name) and set its credit."""
    source = DEMO_MEDIA / entry["file"]
    if not source.is_file() or media_dir is None:
        return False
    name = hashlib.md5(source.read_bytes()).hexdigest() + ".webp"
    target = Path(media_dir) / name
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    credit = json.dumps({k: entry.get(k) for k in ("author", "license", "license_url", "source_url")},
                        ensure_ascii=False)
    if product.image == name and product.photo_credit == credit:
        return False
    product.image, product.photo_credit = name, credit
    return True


def seed_demo(session, media_dir=None):
    """Create the demo shops/products, or add new ones to an existing demo catalog (idempotent).

    Only shops marked is_demo are touched; real shops and their products are never changed.
    """
    shops = {s.slug: s for s in session.scalars(select(Shop).where(Shop.is_demo.is_(True)))}
    real_shops = session.scalar(select(Shop.id).where(Shop.is_demo.is_(False)).limit(1))
    if not shops and real_shops:
        return False  # a live catalog without demo data stays that way
    changed = False
    for slug, name, district, lat, lng, hours, about in DEMO_SHOPS:
        if slug in shops:
            continue
        shop = Shop(slug=slug, name=name, district=district, lat=lat, lng=lng, hours=hours,
                    address=f"{district} tumani, Toshkent (namuna manzil)", description=about,
                    status="active", is_demo=True)
        session.add(shop)
        shops[slug] = shop
        changed = True
    session.flush()
    photos = _demo_photos()
    existing = {(p.shop_id, p.name): p for p in session.scalars(
        select(Product).where(Product.shop_id.in_([s.id for s in shops.values()])))}
    for slug, name, category, color, price, stock, about, gender, seasons, occasions, warmth in DEMO_PRODUCTS:
        shop = shops[slug]
        product = existing.get((shop.id, name))
        if product is None:
            product = Product(shop=shop, name=name, category=category, color=color, price=price, description=about)
            product.variants = [Variant(size=s, stock=stock[s], position=i) for i, s in enumerate(_sorted_sizes(stock))]
            session.add(product)
            changed = True
        attrs = {"category": category, "color": color, "gender": gender, "seasons": seasons, "occasions": occasions,
                 "warmth": warmth, "description": about}
        for key, value in attrs.items():
            if getattr(product, key) != value:
                setattr(product, key, value)
                changed = True
        product.search_text = product_search_text(product, shop)
        for i, size in enumerate(_sorted_sizes([v.size for v in product.variants])):
            variant = next(v for v in product.variants if v.size == size)
            if variant.position != i:
                variant.position, changed = i, True
        entry = photos.get(name)
        if entry and (product.image is None or product.photo_credit):  # never replace a seller's own photo
            changed |= _attach_photo(product, entry, media_dir)
        elif not entry and product.photo_credit:  # a demo photo that was dropped from the manifest
            product.image, product.photo_credit, changed = None, "", True
    password = os.environ.get("DEMO_SELLER_PASSWORD")
    if password and not session.scalar(select(Seller.id).where(Seller.login == "demo@clothes.ai")):
        session.add(Seller(shop=shops["demo-oq-libos"], login="demo@clothes.ai", name="Demo sotuvchi",
                           password_hash=generate_password_hash(password)))
        changed = True
    session.commit()
    return changed
