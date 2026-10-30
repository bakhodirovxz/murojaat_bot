"""Ketma-ket anketa oqimi."""

import html
import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

import db
import keyboards as kb
import notify
from config import ADMIN_IDS, DB_PATH, GROUP_ID
from fields import FIELDS, INDEX_BY_KEY, active_indices
from states import Form
from validators import ValidationError

logger = logging.getLogger(__name__)
router = Router(name="form")
router.message.filter(F.chat.type == "private")

WELCOME = (
    "Assalomu alaykum! 👋\n\n"
    "Bu bot orqali <b>qabulga yozilish</b> uchun ariza qoldirishingiz mumkin.\n\n"
    "Murojaat turini tanlang:\n"
    f"👤 <b>To'liq ma'lumot bilan</b> — ketma-ket {len(FIELDS)} ta savol beriladi, "
    "siz bilan telefon orqali bog'lanishadi.\n"
    "🕶 <b>Anonim</b> — faqat murojaat matni yoziladi, shaxsingiz xodimlarga "
    "ko'rsatilmaydi. Javob shu bot orqali keladi.\n\n"
    "Istalgan paytda /cancel buyrug'i bilan bekor qilishingiz mumkin."
)

CANCELLED = (
    "Ariza bekor qilindi. Qaytadan boshlash uchun /start buyrug'ini yuboring."
)


async def ask_field(message: Message, state: FSMContext, index: int, editing: bool = False) -> None:
    field = FIELDS[index]
    data = await state.get_data()
    indices = active_indices(data.get("_anonymous", False))
    position = indices.index(index)
    await state.set_state(field.state)
    await state.update_data(_index=index, _editing=editing)
    await message.answer(
        f"<b>{position + 1}/{len(indices)}. {field.label}</b>\n\n{field.prompt}",
        reply_markup=kb.field_keyboard(field, position == 0, editing),
    )


def render_preview(data: dict) -> str:
    anonymous = data.get("_anonymous", False)
    title = "🕶 <b>Anonim murojaat</b>" if anonymous else "📋 <b>Kiritilgan ma'lumotlar</b>"
    lines = [title + "\n"]
    for position, index in enumerate(active_indices(anonymous), start=1):
        field = FIELDS[index]
        value = data.get(field.key) or "—"
        # quote=False: apostrof `&#x27;` ga aylanmasin, o'zbekcha matnda ular ko'p.
        safe = html.escape(str(value), quote=False)
        lines.append(f"<b>{position}. {field.label}:</b>\n{safe}")
    lines.append("\nHammasi to'g'rimi?")
    return "\n\n".join(lines)


async def show_preview(message: Message, state: FSMContext, drop_keyboard: bool = True) -> None:
    await state.set_state(Form.preview)
    await state.update_data(_editing=False)
    data = await state.get_data()
    if drop_keyboard:
        await message.answer("Ma'lumotlar to'plandi.", reply_markup=ReplyKeyboardRemove())
    await message.answer(render_preview(data), reply_markup=kb.preview_keyboard())


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Form.mode)
    await message.answer(WELCOME, reply_markup=ReplyKeyboardRemove())
    await message.answer("Murojaat turini tanlang:", reply_markup=kb.mode_keyboard())


@router.callback_query(Form.mode, F.data.in_({kb.CB_MODE_FULL, kb.CB_MODE_ANONYMOUS}))
async def on_mode(callback: CallbackQuery, state: FSMContext) -> None:
    anonymous = callback.data == kb.CB_MODE_ANONYMOUS
    await state.update_data(_anonymous=anonymous)
    await callback.answer()
    await callback.message.edit_text(
        "🕶 Anonim murojaat tanlandi." if anonymous else "👤 To'liq ma'lumot bilan murojaat tanlandi."
    )
    await ask_field(callback.message, state, active_indices(anonymous)[0])


@router.message(Form.mode)
async def on_mode_text(message: Message) -> None:
    await message.answer("Iltimos, murojaat turini tugmalardan birini bosib tanlang.")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer("Hozircha to'ldirilayotgan ariza yo'q. /start")
        return
    await state.clear()
    await message.answer(CANCELLED, reply_markup=ReplyKeyboardRemove())


@router.message(Command("myid"))
async def cmd_my_id(message: Message) -> None:
    """Sozlash uchun: `.env` dagi ADMIN_IDS ga yoziladigan raqam."""
    await message.answer(
        f"Sizning Telegram ID ingiz: <code>{message.from_user.id}</code>\n"
        "Uni <code>.env</code> faylidagi <b>ADMIN_IDS</b> ga yozsangiz admin bo'lasiz."
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>Buyruqlar</b>\n"
        "/start — yangi ariza to'ldirish\n"
        "/cancel — joriy arizani bekor qilish\n"
        "/help — shu yordam matni"
    )


async def handle_field(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    index = data.get("_index", 0)
    editing = data.get("_editing", False)
    field = FIELDS[index]
    indices = active_indices(data.get("_anonymous", False))
    position = indices.index(index)

    raw = message.text or ""
    if field.ask_contact and message.contact is not None:
        raw = message.contact.phone_number
    raw = raw.strip()

    if raw == kb.CANCEL:
        await state.clear()
        await message.answer(CANCELLED, reply_markup=ReplyKeyboardRemove())
        return

    if raw == kb.BACK:
        if editing:
            await show_preview(message, state)
        elif position == 0:
            await message.answer("Bu birinchi savol, orqaga qaytish mumkin emas.")
        else:
            await ask_field(message, state, indices[position - 1])
        return

    if field.optional and raw == kb.SKIP:
        raw = ""

    try:
        value = field.validator(raw)
    except ValidationError as error:
        await message.answer(f"⚠️ {error}\n\nIltimos, qaytadan kiriting.")
        return

    await state.update_data(**{field.key: value})

    if editing:
        await show_preview(message, state)
    elif position + 1 < len(indices):
        await ask_field(message, state, indices[position + 1])
    else:
        await show_preview(message, state)


for _field in FIELDS:
    router.message.register(handle_field, StateFilter(_field.state))


@router.callback_query(Form.preview, F.data == kb.CB_CONFIRM)
async def on_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    anonymous = data.get("_anonymous", False)
    asked = [FIELDS[index] for index in active_indices(anonymous)]
    missing = [field.label for field in asked if not field.optional and not data.get(field.key)]
    if missing:
        await callback.answer("Ariza to'liq emas.", show_alert=True)
        await callback.message.answer(
            "Ba'zi maydonlar to'ldirilmagan. /start bilan qaytadan boshlang."
        )
        return

    # Anonim arizada so'ralmagan maydonlar bo'sh qoladi. Telegram ID faqat javobni
    # yetkazish uchun saqlanadi, username esa umuman yozilmaydi.
    record = {field.key: data.get(field.key, "") if field in asked else "" for field in FIELDS}
    record["tg_user_id"] = callback.from_user.id
    record["tg_username"] = "" if anonymous else callback.from_user.username or ""
    record["anonymous"] = anonymous

    try:
        application_id = db.add_application(DB_PATH, record)
    except Exception:
        logger.exception("Arizani saqlashda xato")
        await callback.answer()
        await callback.message.answer(
            "❌ Texnik sabablarga ko'ra arizani saqlab bo'lmadi. "
            "Iltimos, birozdan so'ng /start bilan qayta urinib ko'ring."
        )
        return

    application = db.get_application(DB_PATH, application_id)
    if application:
        await notify.publish_application(callback.bot, GROUP_ID, application)
        await notify.notify_admins(
            callback.bot, ADMIN_IDS, application, kb.card_keyboard(application_id)
        )

    await state.clear()
    await callback.answer("Qabul qilindi")
    await callback.message.edit_reply_markup(reply_markup=None)
    contact = (
        "Javob shu bot orqali yuboriladi."
        if anonymous
        else "Siz bilan ko'rsatilgan telefon raqami orqali bog'lanishadi."
    )
    await callback.message.answer(
        "✅ <b>Arizangiz qabul qilindi!</b>\n\n"
        f"Tartib raqami: <b>№ {application_id}</b>\n"
        f"Ariza qabul jadvaliga kiritildi. {contact}\n\n"
        "Yangi ariza uchun /start."
    )


@router.callback_query(Form.preview, F.data == kb.CB_EDIT_MENU)
async def on_edit_menu(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await callback.answer()
    await callback.message.edit_text(
        "Qaysi maydonni tahrirlamoqchisiz?",
        reply_markup=kb.edit_menu_keyboard(active_indices(data.get("_anonymous", False))),
    )


@router.callback_query(Form.preview, F.data == kb.CB_BACK_PREVIEW)
async def on_back_to_preview(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    await callback.message.edit_text(render_preview(data), reply_markup=kb.preview_keyboard())


@router.callback_query(Form.preview, F.data.startswith(kb.CB_EDIT_PREFIX))
async def on_edit_field(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data[len(kb.CB_EDIT_PREFIX):]
    index = INDEX_BY_KEY.get(key)
    data = await state.get_data()
    if index is None or index not in active_indices(data.get("_anonymous", False)):
        await callback.answer("Noma'lum maydon", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await ask_field(callback.message, state, index, editing=True)


@router.callback_query(Form.preview, F.data == kb.CB_CANCEL)
async def on_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(CANCELLED)


@router.message(Form.preview)
async def on_preview_text(message: Message) -> None:
    await message.answer("Iltimos, yuqoridagi tugmalardan birini tanlang.")


@router.message()
async def on_unknown(message: Message) -> None:
    await message.answer(
        "Ariza qoldirish uchun /start buyrug'ini yuboring.\n"
        "Yordam: /help"
    )
