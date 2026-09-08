# Qabul jadvali boti

Fuqarolarning qabulga yozilish arizalarini Telegram orqali ketma-ket savol-javob
shaklida yig'adi, adminni darhol xabardor qiladi, admin bilan fuqaro o'rtasida
yozishma olib boradi (fayl almashish bilan) va «Qabul jadvali» ko'rinishidagi
Excel faylini istalgan davr uchun tayyorlaydi.

## Ishga tushirish

1. **Bot yarating.** Telegramda [@BotFather](https://t.me/BotFather) ga yozing →
   `/newbot` → nom va username bering → u sizga **token** beradi.
2. **Sozlamalarni yozing.** `.env.example` dan nusxa oling:

   ```bash
   copy .env.example .env
   ```

   `.env` ichida `BOT_TOKEN` ni to'ldiring.

3. **Kutubxonalarni o'rnating va botni ishga tushiring:**

   ```bash
   python -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   .venv\Scripts\python.exe bot.py
   ```

4. **O'zingizni admin qiling.** Botga `/myid` yozing — u sizning Telegram
   ID ingizni qaytaradi. O'sha raqamni `.env` dagi `ADMIN_IDS` ga yozing va
   botni qayta ishga tushiring. Bir nechta admin bo'lsa vergul bilan ajrating:
   `ADMIN_IDS=123456789,987654321`.

To'xtatish: `Ctrl+C`.

## Fuqaro uchun

`/start` → bot 8 ta savolni ketma-ket beradi:

1. Fuqaro F.I.Sh. 2. Pasport seriyasi 3. JSHSHIR raqami 4. Tug'ilgan sanasi
5. Yashash manzili 6. Telefon raqami 7. Qo'shimcha telefon (ixtiyoriy)
8. Murojaat mazmuni

Har bosqichda «⬅️ Orqaga» va «❌ Bekor qilish» tugmalari bor. Oxirida barcha
ma'lumot ko'rsatiladi — «✏️ Tahrirlash» bilan istalgan bitta maydonni
qolganlarini qayta yozmasdan tuzatish mumkin. «✅ Tasdiqlash» bosilgach ariza
bazaga tushadi, fuqaroga tartib raqami beriladi, adminlarga darhol xabar boradi.

Ariza topshirilgandan keyin fuqaro shu chatga yozgan har qanday xabar (matn yoki
fayl) o'sha arizaga biriktiriladi va mas'ul adminga yetadi.

Buyruqlar: `/start`, `/cancel`, `/myid`, `/help`.

## Admin guruhi

Bot xodimlar guruhida ishlashi mumkin — bunda har bir ariza guruhga kartochka
bo'lib tushadi va javob o'sha yerdan beriladi.

**Sozlash:**

1. Botni guruhga qo'shing (oddiy a'zo bo'lishi kifoya).
2. Guruhda `/id` yozing — bot guruh raqamini qaytaradi.
3. O'sha raqamni `.env` dagi `GROUP_ID` ga yozing va botni qayta ishga tushiring.

**Ishlashi:**

- Yangi ariza guruhga to'liq kartochka bo'lib tushadi, oxirida holat ko'rinadi:
  «⏳ Javob kutilmoqda».
- Javob berish uchun **shu kartochkaga reply qilib** matn yoki fayl yuboriladi.
  Bot uni fuqaroga yetkazadi, xabaringizga 👍 qo'yadi va **kartochkani joyida
  tahrirlaydi**: holat «✍️ Javob berilmoqda», mas'ul admin ismi va almashilgan
  xabarlar soni paydo bo'ladi.
- Fuqaroning javobi guruhda kartochka ostiga reply bo'lib tushadi — unga ham
  reply qilib javob berish mumkin.
- «✅ Yopish» tugmasi arizani yakunlaydi, kartochka «✅ Yopildi» holatiga o'tadi
  va «🔄 Qayta ochish» tugmasi paydo bo'ladi. Fuqaro yana yozsa ariza o'zi
  qayta ochiladi.

Javob berish huquqi `ADMIN_IDS` dagilarda. Guruhning boshqa a'zosi kartochkaga
reply qilsa, bot ogohlantiradi va xabarni uzatmaydi.

Telegram botlari guruhda **maxfiylik rejimida** turadi: bot guruhdagi oddiy
suhbatni ko'rmaydi, faqat buyruqlar va o'z xabarlariga qilingan replylarni
oladi. Shuning uchun javob berish reply orqali qurilgan — rejimni o'chirish
shart emas va bot suhbatga aralashmaydi.

Guruh sozlangan bo'lsa ham, `ADMIN_IDS` dagilar shaxsiy chatda ham nusxa oladi
va u yerda «✍️ Javob berish» tugmasi orqali yozishma rejimida ishlashi mumkin.

## Matrix (Element) xonasi

Telegram bloklangan kompyuterlarda ishlaydigan xodimlar uchun: arizalar
Matrix xonasiga ham tushadi va javob o'sha yerdan beriladi. Mantiq Telegram
guruhidagi bilan bir xil, faqat tugmalar o'rniga buyruqlar ishlatiladi.

**Sozlash:**

1. Homeserverda bot uchun hisob oching (masalan `@qabulbot:example.uz`).
2. `.env` ga yozing: `MATRIX_HOMESERVER`, `MATRIX_USER`, `MATRIX_PASSWORD`
   (yoki `MATRIX_TOKEN`).
3. Botni xonaga taklif qiling va xonada `!id` yozing — u xona ID sini beradi.
   Uni `MATRIX_ROOM_ID` ga yozing.
4. Kim javob bera olishini `MATRIX_ADMINS` da vergul bilan sanang
   (`@aziz:example.uz,@nodir:example.uz`). Bo'sh qoldirilsa — xonaning barcha
   a'zolari.
5. Botni qayta ishga tushiring.

**Buyruqlar** (Element'da `/` mijozning o'ziga tegishli, shuning uchun `!`):

| Buyruq | Vazifasi |
|--------|----------|
| `!list` | Javob kutayotgan arizalar |
| `!ariza 12` | Bitta arizaning kartochkasi |
| `!yozishma 12` | Ariza bo'yicha butun yozishma |
| `!find Karimov` | Qidiruv |
| `!export oy` | Excel eksport: `bugun` · `kecha` · `hafta` · `oy` · `otgan-oy` · `hammasi` · yoki `01.09.2026 30.09.2026` |
| `!stats` | Hisobot |
| `!yopish 12` / `!ochish 12` | Arizani yopish yoki qayta ochish (qisqasi: `!yop`, `!och`) |
| `!id` | Xona ID sini ko'rsatish |

Element'da tugma yo'q, shuning uchun **har bir kartochka o'z buyruqlarini
ko'rsatib turadi** — tugmalar o'rniga:

```
⏳ Javob kutilmoqda
↩️ Javob berish uchun shu xabarga reply qiling.

✅ Yopish: shu xabarga reply qilib !yopish (yoki !yopish 12)
📜 Yozishma: !yozishma 12
```

Kartochkaga **reply** qilib:

- matn yoki fayl yuborsangiz — fuqaroga javob bo'lib ketadi;
- `!yopish` yozsangiz — ariza yopiladi (raqam kerak emas);
- `!yozishma` yozsangiz — o'sha arizaning butun tarixi chiqadi.

Javob yetkazilgach bot xabaringizga 👍 qo'yadi va kartochkani joyida
tahrirlaydi. Yopilgandan keyin kartochka `!ochish 12` ni taklif qiladi.

Xona shifrlanmagan (E2EE emas) bo'lishi kerak.

### Muhim: bot Telegram'ga chiqa olishi shart

Fuqarolar Telegram'da qoladi, shuning uchun bot **api.telegram.org** ga
ulanadigan kompyuterda turishi kerak. Botni yangi serverga ko'chirganda avval
tekshiring:

```bash
python check_server.py
```

U sozlamalar, Telegram, Matrix va papka huquqlarini birma-bir tekshirib, nima
yetishmayotganini aytadi.

## Admin uchun

Yangi ariza kelishi bilan barcha adminlarga to'liq kartochka tushadi:
«✍️ Javob berish», «📜 Yozishma», «✅ Yopish» tugmalari bilan.

| Buyruq | Vazifasi |
|--------|----------|
| `/list` | Javob kutayotgan arizalar ro'yxati (sahifalab) |
| `/find Karimov` | F.I.Sh., telefon, JSHSHIR, pasport yoki № bo'yicha qidiruv |
| `/ariza 12` | Bitta arizaning kartochkasi va butun yozishmasi |
| `/export` | Excel eksport — davrni menyudan tanlaysiz |
| `/stats` | Jami, bugungi, oylik arizalar va javob kutayotganlar soni |

### Yozishma

«✍️ Javob berish» bosilgach admin shu ariza bilan **yozishma rejimiga** kiradi:
yozgan har bir xabari (matn, hujjat, rasm, video, ovozli xabar) to'g'ridan-to'g'ri
fuqaroga yetadi, fuqaroning javobi esa o'sha adminga qaytadi.

- «🏁 Yozishmani tugatish» — rejimdan chiqadi, ariza ochiq qoladi.
- «✅ Arizani yopish» — arizani yakunlaydi, fuqaroga xabar beriladi.
- Fuqaro yopilgan arizaga yana yozsa — ariza **qayta ochiladi**, adminlar
  xabardor qilinadi.

Ariza holati: `Yangi` → `Javob berilmoqda` → `Yopilgan`.

### Eksport

`/export` menyusi: **Bugun · Kecha · Shu hafta · Shu oy · O'tgan oy · Barchasi ·
Davrni kiritish**. Oxirgisi ikkita sana so'raydi (`01.09.2026 30.09.2026`).
Buyruq ko'rinishida ham ishlaydi: `/export 01.09.2026 30.09.2026`.

Excel ustunlari: № · Fuqaro F.I.Sh. · Pasport seriyasi · Fuqaro JSHSHIR raqami ·
Tug'ilgan yili va sanasi · Yashash manzili (to'liq) · Telefon raqami (qo'shimcha) ·
Murojaat mazmuni · Qabul vaqti · Holati · Berilgan javob.

Ustun kengligi va qator balandligi tarkibga qarab avtomatik hisoblanadi — uzun
manzil yoki murojaat matni kesilib qolmaydi. Sarlavha qatori muzlatilgan, filtr
yoqilgan, chop etishda albom yo'nalishi va bir varaqqa sig'dirish tanlangan.

## Ma'lumotlar bazasi

Bot ikkala bazada ham ishlaydi — `.env` dagi `DB_TYPE` hal qiladi.

| | |
|---|---|
| `DB_TYPE=sqlite` | `DB_PATH` dagi bitta fayl. Lokal ish va testlar uchun qulay. |
| `DB_TYPE=mysql` | `MYSQL_HOST` · `MYSQL_PORT` · `MYSQL_USER` · `MYSQL_PASSWORD` · `MYSQL_DATABASE`. Server uchun. |

**MySQL'ga o'tish (aaPanel):**

1. aaPanel → Databases → baza va foydalanuvchi yarating.
2. `.env` da `DB_TYPE=mysql` qiling va `MYSQL_*` ni to'ldiring.
3. Ulanishni tekshiring — bu jadvallarni yaratadi va barcha amallarni sinab
   ko'radi, so'ng o'z test yozuvlarini o'chiradi:

   ```bash
   python check_mysql.py
   ```

4. Mavjud SQLite ma'lumotlari bo'lsa ko'chiring (ariza raqamlari o'zgarmaydi):

   ```bash
   python migrate_to_mysql.py qabul.db
   ```

5. Botni qayta ishga tushiring.

Parol faqat `.env` da turadi, `.gitignore` ga kiritilgan va **hech qachon
jurnalga chiqmaydi** — bot faqat `mysql://user@host:port/baza` ko'rinishini
yozadi.

## Fayllar

- SQLite ishlatilsa `qabul.db` — arizalar va butun yozishma. Zaxira nusxa olib
  qo'yish tavsiya etiladi: shu bitta fayl bilan hamma narsa ko'chadi.
- `files/<ariza №>/` — yozishmada almashilgan fayllar nusxasi. Telegramdagi
  `file_id` ham bazada saqlanadi, shuning uchun qayta yuborish tez bo'ladi.
  Telegram cheklovi: 20 MB gacha.

## Tekshiruvlar

| Maydon | Qoida |
|--------|-------|
| F.I.Sh. | kamida 2 ta so'z, faqat harflar/apostrof/defis |
| Pasport | `AA1234567`; kirill harflari avtomatik lotinga o'giriladi |
| JSHSHIR | roppa-rosa 14 raqam |
| Sana | `KK.OO.YYYY`, mavjud sana, kelajak emas |
| Telefon | `+998XXXXXXXXX`; «📱 Kontaktni yuborish» tugmasi ham ishlaydi |

Xato format kiritilsa bot sababini tushuntiradi va shu savolni qayta beradi —
oldingi javoblar yo'qolmaydi.

## Tarmoq sozlamasi

Tashkilot tarmog'i TLS trafikni tekshirsa, bot `CERTIFICATE_VERIFY_FAILED`
xatosi bilan ishga tushmaydi. Bunday holda `.env` dagi `CA_BUNDLE` ga tashkilot
sertifikatlari `.pem` faylini ko'rsating. Bo'sh qoldirilsa bot `SSL_CERT_FILE`
muhit o'zgaruvchisini, u ham bo'lmasa `certifi` ni ishlatadi.

## Testlar

```bash
.venv\Scripts\python.exe -m pytest -q
```

## Tuzilishi

```
bot.py              ishga tushirish
config.py           .env sozlamalari
net.py              TLS sertifikatlari bilan ulanish
validators.py       tekshirish funksiyalari
states.py           FSM holatlari
fields.py           anketa savollari reestri
keyboards.py        tugmalar
ranges.py           eksport davrlari (bugun, oy, ...)
db.py               baza: SQLite yoki MySQL
check_mysql.py      MySQL ulanishini boshdan-oyoq tekshirish
migrate_to_mysql.py SQLite → MySQL ko'chirish
storage.py          fayllarni diskda saqlash
notify.py           kartochka, yozishma tarixi, xabar uzatish
export.py           Excel
handlers/form.py    anketa oqimi
handlers/dialog.py  shaxsiy chatdagi admin ↔ fuqaro yozishmasi
handlers/group.py   admin guruhi: kartochka, reply orqali javob
handlers/admin.py   /list, /find, /ariza, /export, /stats
matrix_bot.py       Matrix (Element) ko'prigi
bridge.py           faol Matrix ko'prigiga kirish nuqtasi
check_server.py     serverni ishga tayyorligini tekshirish
```

Yangi savol qo'shish uchun `states.py` ga bitta `State()` va `fields.py` ga
bitta `Field(...)` yozish kifoya — qolgani avtomatik ishlaydi.
