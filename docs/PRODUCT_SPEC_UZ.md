# Clothes AI — konsepsiyaga asoslangan texnik reja (2026-10-25)

## Bosh tamoyil
Clothes AI kiyim sotib oluvchi marketplace emas. Bu **shahardagi do‘konlar yagona katalogi + AI virtual kiyinish xonasi + yaqin do‘kondan bron** xizmati. Sotuv va to‘lov birinchi bosqichda do‘konda yuz beradi.

## Xaridor yo‘li (Telegram Mini App)
1. Telegram Mini App ichida kirish.
2. Katalogdan kategoriya/narx/rang/o‘lcham/lokatsiya bo‘yicha qidirish.
3. Suratni shaxsiy va xavfsiz ravishda yuklab virtual try-on qilish.
4. Tanlangan o‘lcham bo‘yicha shu tovar qaysi do‘konda borligini ko‘rish.
5. Do‘konga bron yuborish, do‘kon tasdig‘ini kutish, borib kiyib ko‘rib sotib olish.
6. Natijani oilaga Telegram orqali ulashish.

## Do‘kon yo‘li
- Registratsiya va do‘kon ma'lumotlarini tasdiqlash.
- Mahsulot suratlari, o‘lchamlar, qoldiq, narx.
- AI fotograf (fonni tozalash + professional katalog tasviri).
- Telegram bron tasdiqlari va stats: ko‘rishlar, try-on, bron, do‘konga kelgan mijozlar.
- Keyinchalik 1C/MoySklad sinxronlash.

## Arxitektura
Telegram Mini App va web UI -> Flask REST API -> PostgreSQL (shops, products, variants, reservations, users, events). AI foto va try-on uchun alohida GPU worker + queue + vaqtinchalik encrypted image storage. Hozirgi Flask serverda GPU inference ishlatilmaydi.

## Bosqichlar
- 0–6 oy, Toshkent va to‘y/kechki liboslar: 20–30 hamkor do‘kon, katalog, mini app, try-on, xarita, bron, AI fotograf.
- 6–12 oy: boshqa kiyim kategoriyalari, size profile, outfit assembler, 1C/MoySklad.
- 12–24 oy: hududlarga kengayish, mobil ilovalar, obuna/komissiya, to‘lov/yetkazish.

**Darvoza 1:** real bron va qayta kelayotgan xaridorlar.
**Darvoza 2:** do‘konlarga kelgan xaridorlar statistik isboti.

## Biznes modeli
Hujjat bo‘yicha dastlabki 1–2 yil xaridor va do‘kon uchun bepul. Keyin obuna, bron/sotuv komissiyasi, reklama; onlayn savdo keyingi bosqichda.

## Privacy
Suratlar odatda 24 soatdan keyin o‘chirilishi, do‘konlarga ko‘rinmasligi, foydalanuvchida barcha ma'lumotni o‘chirish huquqi bo‘lishi ko‘zda tutiladi. Hosting hududi bo‘yicha O‘zbekiston qonunchiligiga yurist bilan tekshiruv zarur.

## Hozirgi kodning real holati
- GitHub API va UI: namunaviy ikki do‘kon, to‘rtta mahsulot, mavjud size filtri, stock availability endpoint.
- Hammasi demo ma'lumot; haqiqiy do‘konlar, xarita koordinatalari, autentifikatsiya va bron yo‘q.
- AI endpoint ataylab 503 qaytaradi (model va provider ulanmagan).
- Birinchi bosqichning ishlab chiqarish talablari bajarilmaguncha real bronlar qabul qilinmaydi.
