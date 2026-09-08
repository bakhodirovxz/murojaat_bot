"""Anketa maydonlari reestri.

Bitta umumiy handler shu ro'yxat bo'ylab yuradi, shuning uchun yangi savol
qo'shish uchun faqat shu faylga (va `states.py` ga) qator qo'shiladi.
"""

from dataclasses import dataclass
from typing import Callable

import validators
from states import Form


@dataclass(frozen=True)
class Field:
    key: str
    state: object
    label: str
    prompt: str
    validator: Callable[[str], str]
    optional: bool = False
    ask_contact: bool = False


FIELDS = (
    Field(
        key="fio",
        state=Form.fio,
        label="Fuqaro F.I.Sh.",
        prompt=(
            "Fuqaroning <b>familiya, ism va otasining ismini</b> to'liq kiriting.\n"
            "<i>Masalan: Karimov Aziz Baxtiyorovich</i>"
        ),
        validator=validators.validate_fio,
    ),
    Field(
        key="passport",
        state=Form.passport,
        label="Pasport seriyasi",
        prompt=(
            "<b>Pasport seriyasi va raqamini</b> kiriting.\n"
            "<i>Masalan: AA1234567</i>"
        ),
        validator=validators.validate_passport,
    ),
    Field(
        key="jshshir",
        state=Form.jshshir,
        label="JSHSHIR raqami",
        prompt=(
            "<b>JSHSHIR (PINFL)</b> — 14 xonali raqamni kiriting.\n"
            "<i>U pasportning orqa tomonida yoki ID-kartada yozilgan.</i>"
        ),
        validator=validators.validate_jshshir,
    ),
    Field(
        key="birth_date",
        state=Form.birth_date,
        label="Tug'ilgan sanasi",
        prompt=(
            "<b>Tug'ilgan sanani</b> kun.oy.yil ko'rinishida kiriting.\n"
            "<i>Masalan: 15.03.1990</i>"
        ),
        validator=validators.validate_birth_date,
    ),
    Field(
        key="address",
        state=Form.address,
        label="Yashash manzili",
        prompt=(
            "<b>Yashash manzilini to'liq</b> kiriting.\n"
            "<i>Masalan: Toshkent sh., Chilonzor t., 12-mavze, 5-uy, 24-xonadon</i>"
        ),
        validator=validators.validate_address,
    ),
    Field(
        key="phone",
        state=Form.phone,
        label="Telefon raqami",
        prompt=(
            "<b>Telefon raqamingizni</b> kiriting yoki pastdagi tugma orqali yuboring.\n"
            "<i>Masalan: +998901234567</i>"
        ),
        validator=validators.validate_phone,
        ask_contact=True,
    ),
    Field(
        key="phone_extra",
        state=Form.phone_extra,
        label="Qo'shimcha telefon",
        prompt=(
            "<b>Qo'shimcha telefon raqami</b> bo'lsa kiriting.\n"
            "<i>Bo'lmasa «⏭ O'tkazib yuborish» tugmasini bosing.</i>"
        ),
        validator=validators.validate_phone_optional,
        optional=True,
    ),
    Field(
        key="message",
        state=Form.message,
        label="Murojaat mazmuni",
        prompt=(
            "<b>Murojaat mazmunini</b> batafsil yozing.\n"
            "<i>Muammo nima, qaysi tashkilotga tegishli, qanday yechim kutyapsiz?</i>"
        ),
        validator=validators.validate_message,
    ),
)

FIELDS_BY_KEY = {field.key: field for field in FIELDS}
INDEX_BY_KEY = {field.key: index for index, field in enumerate(FIELDS)}
