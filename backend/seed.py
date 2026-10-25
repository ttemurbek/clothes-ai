"""Demo data: clearly labelled sample shops in Tashkent. Not real businesses or addresses."""
import os

from sqlalchemy import func, select
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
]

# (shop slug, name, category, color, price, {size: stock}, description)
DEMO_PRODUCTS = [
    ("demo-oq-libos", "Klassik atlas kelinlik libosi", "Kelinlik libosi", "Oq", 6_900_000,
     {"XS": 1, "S": 2, "M": 1, "L": 0}, "Uzun etak, yopiq yelka, qoʻlda tikilgan marvarid bezaklar."),
    ("demo-oq-libos", "Yengil shifon kelinlik libosi", "Kelinlik libosi", "Oq", 4_500_000,
     {"S": 1, "M": 2, "L": 1}, "Yozgi toʻylar uchun yengil, ochiq yelkali model."),
    ("demo-oq-libos", "Fotinli nikoh libosi", "Kelinlik libosi", "Kumush rang", 8_200_000,
     {"S": 0, "M": 1, "L": 1, "XL": 1}, "Uzun shleyf, kumush iplar bilan kashta."),
    ("demo-oq-libos", "Qizlar oqshomi libosi", "Kechki libos", "Pushti", 1_650_000,
     {"XS": 2, "S": 3, "M": 2}, "Qizlar oqshomi va unashtiruv uchun."),
    ("demo-kostyum-uyi", "Klassik toʻy kostyumi", "Kostyum", "Qora", 2_400_000,
     {"46": 1, "48": 3, "50": 2, "52": 1, "54": 0}, "Ikki tugmali, jun aralash mato. Shim bilan."),
    ("demo-kostyum-uyi", "Slim-fit kostyum", "Kostyum", "Koʻk", 1_900_000,
     {"46": 2, "48": 2, "50": 0, "52": 1}, "Toʻq koʻk, tor bichim."),
    ("demo-kostyum-uyi", "Bej yozgi kostyum", "Kostyum", "Bej", 1_750_000,
     {"48": 1, "50": 2, "52": 2}, "Zigʻir aralash, yozgi tadbirlar uchun."),
    ("demo-kostyum-uyi", "Oq klassik koʻylak", "Koʻylak", "Oq", 329_000,
     {"S": 4, "M": 6, "L": 5, "XL": 2}, "Paxta, kostyum ostiga."),
    ("demo-atlas", "Xon atlas koʻylak", "Milliy libos", "Rang-barang", 1_200_000,
     {"S": 2, "M": 2, "L": 1}, "Margʻilon xon atlasidan, zamonaviy bichim."),
    ("demo-atlas", "Zarbof chopon", "Milliy libos", "Oltin rang", 3_100_000,
     {"M": 1, "L": 1, "XL": 1}, "Toʻy va bayramlar uchun zarbof chopon."),
    ("demo-atlas", "Adras kamzul", "Milliy libos", "Yashil", 690_000,
     {"S": 1, "M": 3, "L": 2}, "Adras matosidan kalta kamzul."),
    ("demo-kechki", "Baxmal kechki libos", "Kechki libos", "Binafsha", 1_950_000,
     {"XS": 1, "S": 1, "M": 0, "L": 1}, "Baxmal, uzun yeng, belbogʻ bilan."),
    ("demo-kechki", "Atlas uzun libos", "Kechki libos", "Qizil", 2_300_000,
     {"S": 2, "M": 1, "L": 1}, "Ochiq yelkali, yerga tushadigan etak."),
    ("demo-kechki", "Paetkali kokteyl libosi", "Kechki libos", "Oltin rang", 1_400_000,
     {"XS": 1, "S": 2, "M": 2}, "Tizzagacha, paetkalar bilan."),
    ("demo-shahar", "Essential trench palto", "Ustki kiyim", "Bej", 895_000,
     {"S": 0, "M": 1, "L": 2}, "Kuzgi palto, belbogʻli."),
    ("demo-shahar", "Minimal blazer", "Ustki kiyim", "Qora", 549_000,
     {"S": 1, "M": 2, "L": 0}, "Ofis va tadbirlar uchun."),
    ("demo-bolajon", "Bayramona qizcha libosi", "Bolalar kiyimi", "Pushti", 420_000,
     {"98": 2, "104": 3, "110": 2, "116": 1}, "Tyul etakli, 3–6 yosh."),
    ("demo-bolajon", "Oʻgʻil bola kostyumi", "Bolalar kiyimi", "Kulrang", 560_000,
     {"104": 1, "110": 2, "116": 2, "122": 1}, "Jilet, shim va koʻylak toʻplami."),
]


def product_search_text(product, shop):
    return norm_text(" ".join(x or "" for x in [product.name, product.category, product.color, product.description,
                               shop.name, shop.district]))


def seed_demo(session):
    if session.scalar(select(func.count(Shop.id))):
        return False
    shops = {}
    for slug, name, district, lat, lng, hours, about in DEMO_SHOPS:
        shop = Shop(slug=slug, name=name, district=district, lat=lat, lng=lng, hours=hours,
                    address=f"{district} tumani, Toshkent (namuna manzil)", description=about,
                    status="active", is_demo=True)
        session.add(shop)
        shops[slug] = shop
    session.flush()
    for slug, name, category, color, price, stock, about in DEMO_PRODUCTS:
        shop = shops[slug]
        product = Product(shop=shop, name=name, category=category, color=color, price=price,
                          description=about)
        sizes = sorted(stock, key=lambda s: (size_key(s), int(s) if s.isdigit() else 0))
        product.variants = [Variant(size=s, stock=stock[s], position=i) for i, s in enumerate(sizes)]
        product.search_text = product_search_text(product, shop)
        session.add(product)
    password = os.environ.get("DEMO_SELLER_PASSWORD")
    if password:
        session.add(Seller(shop=shops["demo-oq-libos"], login="demo@clothes.ai", name="Demo sotuvchi",
                           password_hash=generate_password_hash(password)))
    session.commit()
    return True
