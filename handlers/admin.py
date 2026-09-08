"""Admin buyruqlari: arizalar ro'yxati, qidiruv, yozishma, eksport."""

import logging
import os
import tempfile
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

import db
import export
import keyboards as kb
import notify
import ranges
from config import DB_PATH, is_admin
from states import Dialog, Export
from validators import ValidationError, parse_date

logger = logging.getLogger(__name__)
router = Router(name="admin")

PAGE_SIZE = 8

USAGE = (
    "<b>Admin buyruqlari</b>\n"
    "/list — javob kutayotgan arizalar\n"
    "/find Karimov — F.I.Sh., telefon, JSHSHIR, pasport yoki № bo'yicha qidiruv\n"
    "/ariza 12 — bitta arizaning kartochkasi va yozishmasi\n"
    "/export — Excel eksport (davrni tanlaysiz)\n"
    "/stats — umumiy hisobot"
)


def _admin_only(event) -> bool:
    return bool(event.from_user) and is_admin(event.from_user.id)


router.message.filter(_admin_only)
router.callback_query.filter(_admin_only)


# --- Arizalar bilan ishlash ----------------------------------------------


async def _show_card(message: Message, application: dict) -> None:
    closed = application.get("status") == db.STATUS_CLOSED
    await message.answer(
        notify.render_card(application), reply_markup=kb.card_keyboard(application["id"], closed)
    )


async def _show_list(message: Message, offset: int = 0, edit: bool = False) -> None:
    total = db.count_open_applications(DB_PATH)
    if total == 0:
        text = "✅ Javob kutayotgan ariza yo'q."
        await (message.edit_text(text) if edit else message.answer(text))
        return
    applications = db.open_applications(DB_PATH, PAGE_SIZE, offset)
    shown = f"{offset + 1}–{offset + len(applications)}"
    text = f"📋 <b>Javob kutayotgan arizalar</b> — jami {total} ta (ko'rsatilmoqda {shown})"
    keyboard = kb.list_keyboard(applications, offset, total, PAGE_SIZE)
    if edit:
        await message.edit_text(text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)


@router.message(Command("list"))
async def cmd_list(message: Message) -> None:
    await _show_list(message)


@router.message(Command("find"))
async def cmd_find(message: Message, command: CommandObject) -> None:
    query = (command.args or "").strip()
    if not query:
        await message.answer("Qidiruv so'zini yozing.\nMasalan: <code>/find Karimov</code>")
        return
    found = db.search_applications(DB_PATH, query)
    if not found:
        await message.answer(f"«{notify.esc(query)}» bo'yicha ariza topilmadi.")
        return
    await message.answer(f"🔍 <b>{len(found)} ta ariza topildi</b>")
    for application in found[:PAGE_SIZE]:
        await _show_card(message, application)


@router.message(Command("ariza"))
async def cmd_application(message: Message, command: CommandObject) -> None:
    raw = (command.args or "").strip().lstrip("№# ")
    if not raw.isdigit():
        await message.answer("Ariza raqamini yozing.\nMasalan: <code>/ariza 12</code>")
        return
    application = db.get_application(DB_PATH, int(raw))
    if application is None:
        await message.answer(f"№ {raw} ariza topilmadi.")
        return
    await _show_card(message, application)


@router.callback_query(F.data.startswith(kb.CB_LIST_PREFIX))
async def on_list_page(callback: CallbackQuery) -> None:
    offset = callback.data[len(kb.CB_LIST_PREFIX):]
    await callback.answer()
    await _show_list(callback.message, int(offset) if offset.isdigit() else 0, edit=True)


@router.callback_query(F.data.startswith(kb.CB_APP_PREFIX))
async def on_application_action(callback: CallbackQuery, state: FSMContext) -> None:
    application_id, action = kb.parse_app_callback(callback.data)
    if application_id is None:
        await callback.answer("Noto'g'ri tugma", show_alert=True)
        return
    application = db.get_application(DB_PATH, application_id)
    if application is None:
        await callback.answer("Ariza topilmadi", show_alert=True)
        return

    if action == "card":
        await callback.answer()
        await _show_card(callback.message, application)
        return

    if action == "history":
        await callback.answer()
        messages = db.fetch_messages(DB_PATH, application_id)
        await callback.message.answer(notify.render_history(application, messages))
        return

    if action == "reopen":
        db.set_status(DB_PATH, application_id, db.STATUS_IN_PROGRESS)
        await callback.answer("Qayta ochildi")
        await notify.refresh_cards(callback.bot, application_id)
        if application.get("tg_user_id"):
            await notify.deliver(
                callback.bot,
                application["tg_user_id"],
                f"🔄 <b>№ {application_id} arizangiz qayta ko'rib chiqilmoqda.</b>",
            )
        return

    if action == "close":
        db.set_status(DB_PATH, application_id, db.STATUS_CLOSED)
        await callback.answer("Yopildi")
        await notify.refresh_cards(callback.bot, application_id)
        if application.get("tg_user_id"):
            await notify.deliver(
                callback.bot,
                application["tg_user_id"],
                f"✅ <b>№ {application_id} arizangiz yakunlandi.</b>\n"
                "Savolingiz qolsa shu yerga yozing — murojaat qayta ochiladi.",
            )
        await callback.message.answer(f"✅ № {application_id} arizasi yopildi.")
        return

    if action == "reply":
        if not application.get("tg_user_id"):
            await callback.answer("Bu arizada Telegram foydalanuvchisi yo'q", show_alert=True)
            return
        db.set_status(
            DB_PATH,
            application_id,
            db.STATUS_IN_PROGRESS,
            assigned_admin=callback.from_user.id,
        )
        await state.set_state(Dialog.chatting)
        await state.update_data(application_id=application_id)
        await notify.refresh_cards(callback.bot, application_id)
        await callback.answer()
        await callback.message.answer(
            f"✍️ <b>№ {application_id} bo'yicha yozishma boshlandi.</b>\n"
            f"Fuqaro: {notify.esc(application['fio'])}\n\n"
            "Endi yozgan har bir xabaringiz (matn, hujjat, rasm, video, ovozli xabar) "
            "to'g'ridan-to'g'ri fuqaroga yetadi. Fuqaroning javobi shu yerga qaytadi.",
            reply_markup=kb.dialog_keyboard(),
        )
        return

    await callback.answer("Noma'lum amal", show_alert=True)


# --- Eksport --------------------------------------------------------------


async def _send_export(message: Message, date_from, date_to, label: str) -> None:
    rows = db.fetch_applications(DB_PATH, date_from, date_to)
    if not rows:
        await message.answer(f"«{label}» uchun ariza topilmadi.")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    path = os.path.join(tempfile.gettempdir(), f"qabul_jadvali_{stamp}.xlsx")
    try:
        export.save_workbook(rows, path)
        await message.answer_document(
            FSInputFile(path), caption=f"Qabul jadvali · {label}\n{len(rows)} ta ariza"
        )
    except Exception:
        logger.exception("Eksport qilishda xato")
        await message.answer("❌ Faylni tayyorlashda xato yuz berdi.")
    finally:
        if os.path.exists(path):
            os.remove(path)


@router.message(Command("export"))
async def cmd_export(message: Message, command: CommandObject) -> None:
    args = (command.args or "").strip()
    if not args:
        await message.answer("📊 <b>Qaysi davr uchun?</b>", reply_markup=kb.export_keyboard())
        return
    parts = args.split()
    if len(parts) != 2:
        await message.answer(
            "Davrni ikkita sana bilan yozing.\n"
            "Masalan: <code>/export 01.09.2026 30.09.2026</code>\n\n"
            "Yoki argumentsiz <code>/export</code> yuboring — menyudan tanlaysiz."
        )
        return
    try:
        date_from = parse_date(parts[0])
        date_to = parse_date(parts[1])
    except ValidationError as error:
        await message.answer(f"⚠️ {error}")
        return
    if date_from > date_to:
        await message.answer("⚠️ Boshlanish sanasi tugash sanasidan keyin bo'lmasin.")
        return
    await _send_export(
        message,
        date_from.isoformat(),
        date_to.isoformat(),
        f"{ranges.dmy(date_from)} — {ranges.dmy(date_to)}",
    )


@router.callback_query(F.data.startswith(kb.CB_EXPORT_PREFIX))
async def on_export_range(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data[len(kb.CB_EXPORT_PREFIX):]
    await callback.answer()

    if key == "custom":
        await state.set_state(Export.custom_range)
        await callback.message.answer(
            "Davrni ikkita sana bilan yozing:\n"
            "<code>01.09.2026 30.09.2026</code>\n\n"
            "Bekor qilish: /cancel"
        )
        return

    try:
        date_from, date_to, label = ranges.resolve(key)
    except ValueError:
        await callback.message.answer("Noma'lum davr.")
        return
    await _send_export(callback.message, date_from, date_to, label)


@router.message(Export.custom_range)
async def on_custom_range(message: Message, state: FSMContext) -> None:
    if (message.text or "").startswith("/cancel"):
        await state.clear()
        await message.answer("Eksport bekor qilindi.")
        return
    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer(
            "Ikkita sana kerak: <code>01.09.2026 30.09.2026</code>\nBekor qilish: /cancel"
        )
        return
    try:
        date_from = parse_date(parts[0])
        date_to = parse_date(parts[1])
    except ValidationError as error:
        await message.answer(f"⚠️ {error}")
        return
    if date_from > date_to:
        await message.answer("⚠️ Boshlanish sanasi tugash sanasidan keyin bo'lmasin.")
        return
    await state.clear()
    await _send_export(
        message,
        date_from.isoformat(),
        date_to.isoformat(),
        f"{ranges.dmy(date_from)} — {ranges.dmy(date_to)}",
    )


# --- Hisobot --------------------------------------------------------------


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    total = db.count_applications(DB_PATH)
    waiting = db.count_open_applications(DB_PATH)
    last = db.last_created_at(DB_PATH)
    today_rows = db.fetch_applications(DB_PATH, *ranges.resolve("today")[:2])
    month_rows = db.fetch_applications(DB_PATH, *ranges.resolve("month")[:2])

    text = (
        "📊 <b>Hisobot</b>\n\n"
        f"Jami arizalar: <b>{total}</b>\n"
        f"Bugun: <b>{len(today_rows)}</b>\n"
        f"Shu oy: <b>{len(month_rows)}</b>\n"
        f"Javob kutmoqda: <b>{waiting}</b>"
    )
    if last:
        text += f"\nOxirgi ariza: {export.pretty_datetime(last)}"
    await message.answer(text + "\n\n" + USAGE)


@router.message(Command("admin"))
async def cmd_admin_help(message: Message) -> None:
    await message.answer(USAGE)
