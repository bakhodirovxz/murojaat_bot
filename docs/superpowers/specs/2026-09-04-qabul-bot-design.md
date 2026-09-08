# Qabul jadvali Telegram boti — dizayn

Sana: 2026-09-04

## Maqsad

Fuqarolarning qabulga yozilish arizalarini Telegram bot orqali ketma-ket
savol-javob shaklida yig'ish, SQLite bazasida saqlash va admin uchun
«Қабул жадвали» ko'rinishidagi Excel faylini eksport qilish.

## Foydalanuvchilar

- **Fuqaro** — botga `/start` bosadi, 8 ta savolga ketma-ket javob beradi,
  ko'rib chiqish ekranida tasdiqlaydi.
- **Admin** — `.env` dagi `ADMIN_IDS` ro'yxatidagi Telegram foydalanuvchilari.
  `/export` va `/stats` buyruqlaridan foydalanadi.

## Stack

Python 3.10 · aiogram 3 (FSM) · sqlite3 (standart kutubxona) · openpyxl ·
python-dotenv.

`aiosqlite` ishlatilmaydi: yuklama past, so'rovlar mikrosoniyalik, sinxron
`sqlite3` bitta bog'liqlikni kamaytiradi va testlarni soddalashtiradi.

## Ma'lumot oqimi

`/start` → 8 bosqichli FSM → ko'rib chiqish → tasdiq → SQLite → foydalanuvchiga
tartib raqami.

Har bosqichda: «⬅️ Orqaga» (oldingi savolga), «❌ Bekor qilish» (`/cancel` ham).
Xato format kiritilsa — sabab tushuntiriladi va o'sha savol qayta so'raladi,
bosqich yo'qolmaydi.

### Maydonlar

| № | Kalit | Savol | Tekshiruv |
|---|-------|-------|-----------|
| 1 | `fio` | Fuqaro F.I.Sh. | ≥2 so'z, faqat harflar/apostrof/defis, ≤150 belgi |
| 2 | `passport` | Pasport seriyasi | `AA1234567`; kirill harflari lotinga o'giriladi |
| 3 | `jshshir` | ЖШШИР | roppa-rosa 14 raqam |
| 4 | `birth_date` | Tug'ilgan sana | `KK.OO.YYYY`, real sana, 1900..bugun |
| 5 | `address` | Yashash manzili | 10..500 belgi |
| 6 | `phone` | Telefon | `+998XXXXXXXXX`; «📱 Kontaktni yuborish» tugmasi ham |
| 7 | `phone_extra` | Qo'shimcha telefon | ixtiyoriy, «⏭ O'tkazib yuborish» |
| 8 | `message` | Murojaat mazmuni | 10..3000 belgi |

### Ko'rib chiqish ekrani

Barcha javoblar ro'yxat bo'lib chiqadi, inline tugmalar:
`✅ Tasdiqlash` / `✏️ Tahrirlash` / `❌ Bekor qilish`.
«Tahrirlash» bitta maydonni tanlab qayta kiritish imkonini beradi va yana
ko'rib chiqish ekraniga qaytaradi (qolgan javoblar saqlanadi).

## Baza

`applications` jadvali: `id` (= jadvaldagi №), `fio`, `passport`, `jshshir`,
`birth_date`, `address`, `phone`, `phone_extra`, `message`, `tg_user_id`,
`tg_username`, `created_at` (ISO, mahalliy vaqt).

## Admin buyruqlari

- `/export` — barcha arizalar `.xlsx` fayl sifatida.
- `/export 01.09.2026 30.09.2026` — sana oralig'i bo'yicha.
- `/stats` — jami arizalar soni va oxirgi ariza vaqti.

Excel sarlavhalari asl hujjatdagidek kirill yozuvida; telefon va qo'shimcha
telefon bitta ustunda: `+998901234567 (+998971234567)`.

## Modullar

| Fayl | Vazifasi |
|------|----------|
| `bot.py` | ishga tushirish, router'lar, polling |
| `config.py` | `.env` o'qish (`BOT_TOKEN`, `ADMIN_IDS`, `DB_PATH`) |
| `validators.py` | sof funksiyalar: tekshirish + normallashtirish |
| `states.py` | FSM holatlari |
| `fields.py` | maydonlar reestri (savol, tekshiruvchi, tugma turi) |
| `keyboards.py` | tugmalar va matn konstantalari |
| `db.py` | SQLite: `init_db`, `add_application`, `fetch_applications`, `count_applications` |
| `export.py` | openpyxl orqali `.xlsx` yaratish |
| `handlers/form.py` | ketma-ket so'rov oqimi |
| `handlers/admin.py` | `/export`, `/stats` |

Maydonlar reestri (`fields.py`) tufayli 8 ta bir xil handler o'rniga bitta
umumiy handler ishlatiladi.

## Xatolarga chidamlilik

- Validatsiya xatosi → xushmuomala xabar + o'sha savol qayta.
- DB xatosi → log'ga yoziladi, foydalanuvchiga «keyinroq urinib ko'ring».
- FSM xotirada (`MemoryStorage`): bot qayta ishga tushsa to'ldirilmagan ariza
  yo'qoladi — bu qabul qilinadi, chunki tugallangan arizalar bazada.

## Test

`pytest` bilan `validators.py` (formatlar, chegara holatlar), `db.py`
(yozish/o'qish, sana filtri) va `export.py` (fayl tuzilishi) qoplanadi.
Suhbat oqimi qo'lda sinaladi.
