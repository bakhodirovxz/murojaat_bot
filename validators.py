"""Kiritilgan ma'lumotlarni tekshirish va bir xil ko'rinishga keltirish.

Bu yerdagi funksiyalar sof: Telegram'ga bog'liq emas, shuning uchun
to'g'ridan-to'g'ri testlanadi. Har biri normallashtirilgan qiymat qaytaradi
yoki foydalanuvchiga ko'rsatish uchun tayyor matn bilan ValidationError
ko'taradi.
"""

import re
from datetime import date

__all__ = [
    "ValidationError",
    "validate_fio",
    "validate_passport",
    "validate_jshshir",
    "validate_birth_date",
    "validate_address",
    "validate_phone",
    "validate_phone_optional",
    "validate_message",
    "parse_date",
]


class ValidationError(ValueError):
    """Matni to'g'ridan-to'g'ri foydalanuvchiga yuboriladigan xato."""


# Pasport seriyasida kirill harflari terilib qolishi juda keng tarqalgan xato.
_CYR_TO_LAT = str.maketrans(
    "АВСЕНКМОРТХУІЗ",
    "ABCEHKMOPTXYI3",
)

_APOSTROPHES = "'ʻʼ‘’`´"
_FIO_ALLOWED = re.compile(
    r"^[A-Za-zЀ-ӿ" + re.escape(_APOSTROPHES) + r"\- ]+$"
)


def _clean(raw) -> str:
    """Bo'sh joylarni bitta probelga keltiradi."""
    return " ".join((raw or "").split())


def validate_fio(raw) -> str:
    text = _clean(raw)
    if not text:
        return _fail("F.I.Sh. bo'sh bo'lishi mumkin emas.")
    if len(text) > 150:
        return _fail("F.I.Sh. juda uzun (150 belgidan oshmasin).")
    if not _FIO_ALLOWED.match(text):
        return _fail(
            "F.I.Sh. da faqat harflar, apostrof va defis bo'lishi mumkin. "
            "Raqam yoki boshqa belgilarni olib tashlang."
        )
    parts = text.split(" ")
    if len(parts) < 2:
        return _fail(
            "Familiya, ism va otasining ismini to'liq yozing.\n"
            "Masalan: Karimov Aziz Baxtiyorovich"
        )
    if any(len(p) < 2 for p in parts):
        return _fail("F.I.Sh. dagi har bir so'z kamida 2 ta harfdan iborat bo'lsin.")
    return text


def validate_passport(raw) -> str:
    text = (raw or "").replace(" ", "").replace("-", "").upper().translate(_CYR_TO_LAT)
    if not re.fullmatch(r"[A-Z]{2}\d{7}", text):
        return _fail(
            "Pasport seriyasi 2 ta harf va 7 ta raqamdan iborat bo'lishi kerak.\n"
            "Masalan: AA1234567"
        )
    return text


def validate_jshshir(raw) -> str:
    text = re.sub(r"[\s\-]", "", raw or "")
    if not text.isdigit():
        return _fail("JSHSHIR faqat raqamlardan iborat bo'lishi kerak.")
    if len(text) != 14:
        return _fail(
            f"JSHSHIR roppa-rosa 14 ta raqamdan iborat bo'lishi kerak "
            f"(siz {len(text)} ta raqam kiritdingiz)."
        )
    return text


def parse_date(raw) -> date:
    """`KK.OO.YYYY` ni `date` ga aylantiradi. Ajratgich `.`, `/`, `-` bo'lishi mumkin."""
    text = re.sub(r"\s", "", raw or "").replace("/", ".").replace("-", ".")
    match = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if not match:
        return _fail("Sanani kun.oy.yil ko'rinishida yozing.\nMasalan: 15.03.1990")
    day, month, year = (int(g) for g in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return _fail("Bunday sana mavjud emas. Tekshirib qayta kiriting.")


def validate_birth_date(raw) -> str:
    value = parse_date(raw)
    if value > date.today():
        return _fail("Tug'ilgan sana kelajakdagi sana bo'lishi mumkin emas.")
    if value.year < 1900:
        return _fail("Tug'ilgan yil 1900 dan oldin bo'lishi mumkin emas.")
    return value.strftime("%d.%m.%Y")


def validate_address(raw) -> str:
    text = _clean(raw)
    if len(text) < 10:
        return _fail(
            "Manzilni to'liqroq yozing: viloyat/shahar, tuman, ko'cha, uy, xonadon."
        )
    if len(text) > 500:
        return _fail("Manzil juda uzun (500 belgidan oshmasin).")
    return text


def validate_phone(raw) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 9:
        digits = "998" + digits
    elif len(digits) == 12 and digits.startswith("998"):
        pass
    elif len(digits) == 13 and digits.startswith("8998"):
        # Kontakt tugmasi ba'zan "8" bilan qaytaradi.
        digits = digits[1:]
    else:
        return _fail(
            "Telefon raqamini +998XXXXXXXXX ko'rinishida kiriting.\n"
            "Masalan: +998901234567"
        )
    return "+" + digits


def validate_phone_optional(raw) -> str:
    """Bo'sh bo'lsa ruxsat, aks holda oddiy telefon tekshiruvi."""
    if not (raw or "").strip():
        return ""
    return validate_phone(raw)


def validate_message(raw) -> str:
    text = (raw or "").strip()
    if len(text) < 10:
        return _fail("Murojaat mazmunini batafsilroq yozing (kamida 10 ta belgi).")
    if len(text) > 3000:
        return _fail("Murojaat matni juda uzun (3000 belgidan oshmasin).")
    return text


def _fail(message: str):
    raise ValidationError(message)
