"""Tugmalar va ular bilan bog'liq matn konstantalari."""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

import ranges
from fields import FIELDS

# --- Anketa ---------------------------------------------------------------

BACK = "⬅️ Orqaga"
CANCEL = "❌ Bekor qilish"
SKIP = "⏭ O'tkazib yuborish"
CONTACT = "📱 Kontaktni yuborish"

CB_CONFIRM = "confirm"
CB_EDIT_MENU = "edit_menu"
CB_CANCEL = "cancel"
CB_BACK_PREVIEW = "back_preview"
CB_EDIT_PREFIX = "edit:"

# --- Admin ----------------------------------------------------------------

DIALOG_END = "🏁 Yozishmani tugatish"
DIALOG_CLOSE = "✅ Arizani yopish"

CB_APP_PREFIX = "app:"  # app:<id>:<amal>
CB_LIST_PREFIX = "list:"  # list:<offset>
CB_EXPORT_PREFIX = "exp:"  # exp:<oraliq kaliti>


def app_callback(application_id: int, action: str) -> str:
    return f"{CB_APP_PREFIX}{application_id}:{action}"


def parse_app_callback(data: str):
    """`app:12:reply` → `(12, "reply")`. Mos kelmasa `(None, "")`."""
    if not data.startswith(CB_APP_PREFIX):
        return None, ""
    parts = data[len(CB_APP_PREFIX):].split(":", 1)
    if len(parts) != 2 or not parts[0].isdigit():
        return None, ""
    return int(parts[0]), parts[1]


def field_keyboard(field, index: int, editing: bool) -> ReplyKeyboardMarkup:
    """Bosqichga mos pastki tugmalar."""
    rows = []
    if field.ask_contact:
        rows.append([KeyboardButton(text=CONTACT, request_contact=True)])
    if field.optional:
        rows.append([KeyboardButton(text=SKIP)])
    navigation = []
    if editing or index > 0:
        navigation.append(KeyboardButton(text=BACK))
    navigation.append(KeyboardButton(text=CANCEL))
    rows.append(navigation)
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=False)


def preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=CB_CONFIRM)],
            [InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=CB_EDIT_MENU)],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data=CB_CANCEL)],
        ]
    )


def edit_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{index + 1}. {field.label}",
                callback_data=f"{CB_EDIT_PREFIX}{field.key}",
            )
        ]
        for index, field in enumerate(FIELDS)
    ]
    rows.append([InlineKeyboardButton(text=BACK, callback_data=CB_BACK_PREVIEW)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def card_keyboard(application_id: int, closed: bool = False) -> InlineKeyboardMarkup:
    """Ariza kartochkasi ostidagi tugmalar."""
    rows = [
        [
            InlineKeyboardButton(
                text="✍️ Javob berish", callback_data=app_callback(application_id, "reply")
            ),
            InlineKeyboardButton(
                text="📜 Yozishma", callback_data=app_callback(application_id, "history")
            ),
        ]
    ]
    if not closed:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Yopish", callback_data=app_callback(application_id, "close")
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def dialog_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=DIALOG_END)], [KeyboardButton(text=DIALOG_CLOSE)]],
        resize_keyboard=True,
    )


def list_keyboard(applications, offset: int, total: int, page_size: int) -> InlineKeyboardMarkup:
    """Arizalar ro'yxati: har biri alohida tugma, oxirida sahifalash."""
    rows = [
        [
            InlineKeyboardButton(
                text=f"№ {app['id']} · {app['fio']}",
                callback_data=app_callback(app["id"], "card"),
            )
        ]
        for app in applications
    ]
    navigation = []
    if offset > 0:
        navigation.append(
            InlineKeyboardButton(
                text="⬅️ Oldingi", callback_data=f"{CB_LIST_PREFIX}{max(0, offset - page_size)}"
            )
        )
    if offset + page_size < total:
        navigation.append(
            InlineKeyboardButton(
                text="Keyingi ➡️", callback_data=f"{CB_LIST_PREFIX}{offset + page_size}"
            )
        )
    if navigation:
        rows.append(navigation)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def export_keyboard() -> InlineKeyboardMarkup:
    """Eksport davrini tanlash menyusi."""
    buttons = [
        InlineKeyboardButton(text=title, callback_data=f"{CB_EXPORT_PREFIX}{key}")
        for key, title in ranges.BUTTONS
    ]
    rows = [buttons[index:index + 2] for index in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def group_card_keyboard(application_id: int, closed: bool = False) -> InlineKeyboardMarkup:
    """Guruhdagi kartochka tugmalari. Javob reply orqali beriladi, tugma kerak emas."""
    row = [
        InlineKeyboardButton(
            text="📜 Yozishma", callback_data=app_callback(application_id, "history")
        )
    ]
    if closed:
        row.append(
            InlineKeyboardButton(
                text="🔄 Qayta ochish", callback_data=app_callback(application_id, "reopen")
            )
        )
    else:
        row.append(
            InlineKeyboardButton(
                text="✅ Yopish", callback_data=app_callback(application_id, "close")
            )
        )
    return InlineKeyboardMarkup(inline_keyboard=[row])
