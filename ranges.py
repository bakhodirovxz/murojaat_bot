"""Eksport uchun sana oraliqlari."""

from datetime import date, timedelta
from typing import Optional, Tuple

MONTHS = (
    "yanvar",
    "fevral",
    "mart",
    "aprel",
    "may",
    "iyun",
    "iyul",
    "avgust",
    "sentabr",
    "oktabr",
    "noyabr",
    "dekabr",
)

# Tugmalar tartibi: (kalit, tugma matni)
BUTTONS = (
    ("today", "📅 Bugun"),
    ("yesterday", "📅 Kecha"),
    ("week", "🗓 Shu hafta"),
    ("month", "🗓 Shu oy"),
    ("prev_month", "🗓 O'tgan oy"),
    ("all", "📊 Barchasi"),
    ("custom", "✏️ Davrni kiritish"),
)


def dmy(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def month_name(value: date) -> str:
    return f"{MONTHS[value.month - 1]} {value.year}"


def _month_start(value: date) -> date:
    return value.replace(day=1)


def resolve(key: str, today: Optional[date] = None) -> Tuple[Optional[str], Optional[str], str]:
    """Kalit bo'yicha (boshlanish, tugash, nom) qaytaradi. ISO sanalar yoki None."""
    today = today or date.today()

    if key == "today":
        return today.isoformat(), today.isoformat(), f"Bugun, {dmy(today)}"

    if key == "yesterday":
        day = today - timedelta(days=1)
        return day.isoformat(), day.isoformat(), f"Kecha, {dmy(day)}"

    if key == "week":
        start = today - timedelta(days=today.weekday())
        return start.isoformat(), today.isoformat(), f"Shu hafta: {dmy(start)} — {dmy(today)}"

    if key == "month":
        start = _month_start(today)
        return start.isoformat(), today.isoformat(), f"Shu oy: {month_name(today)}"

    if key == "prev_month":
        end = _month_start(today) - timedelta(days=1)
        start = _month_start(end)
        return start.isoformat(), end.isoformat(), f"O'tgan oy: {month_name(start)}"

    if key == "all":
        return None, None, "Barcha vaqt"

    raise ValueError(f"Noma'lum oraliq: {key}")


def label_for_custom(date_from: str, date_to: str) -> str:
    return f"Davr: {date_from} — {date_to}"


# Matn bilan davr tanlash (Matrix xonasida tugma yo'q).
KEYWORDS = {
    "bugun": "today",
    "kecha": "yesterday",
    "hafta": "week",
    "shu-hafta": "week",
    "oy": "month",
    "shu-oy": "month",
    "otgan-oy": "prev_month",
    "utgan-oy": "prev_month",
    "hammasi": "all",
    "barchasi": "all",
}

REQUEST_HELP = (
    "Davrni shu ko'rinishlarda yozing: bugun · kecha · hafta · oy · otgan-oy · "
    "hammasi · yoki ikkita sana: 01.09.2026 30.09.2026"
)


def parse_request(text: str, today: Optional[date] = None):
    """Matndan (boshlanish, tugash, nom) chiqaradi. Bo'sh bo'lsa — barcha vaqt."""
    from validators import ValidationError, parse_date

    cleaned = (text or "").strip().lower().replace("'", "").replace("ʻ", "")
    if not cleaned:
        return resolve("all", today)

    parts = cleaned.split()
    if len(parts) == 1 and parts[0] in KEYWORDS:
        return resolve(KEYWORDS[parts[0]], today)

    if len(parts) == 2:
        date_from = parse_date(parts[0])
        date_to = parse_date(parts[1])
        if date_from > date_to:
            raise ValidationError("Boshlanish sanasi tugash sanasidan keyin bo'lmasin.")
        return (
            date_from.isoformat(),
            date_to.isoformat(),
            f"{dmy(date_from)} — {dmy(date_to)}",
        )

    raise ValidationError(REQUEST_HELP)
