"""Shaxsiy chatdagi yozishma: admin ↔ fuqaro."""

import logging

from aiogram import F, Router
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

import db
import keyboards as kb
import notify
from config import ADMIN_IDS, DB_PATH
from states import Dialog

logger = logging.getLogger(__name__)
router = Router(name="dialog")
router.message.filter(F.chat.type == "private")

CITIZEN_HEADER = "📩 <b>№ {id} — arizangizga javob</b>"
ADMIN_HEADER = "💬 <b>№ {id} · {fio}</b> javob yozdi"
GROUP_HEADER = "👤 <b>№ {id} · {fio}</b> yozdi:"
CLOSED_TEXT = (
    "✅ <b>№ {id} arizangiz yakunlandi.</b>\n"
    "Savolingiz qolsa shu yerga yozing — murojaat qayta ochiladi."
)
REOPENED = "🔄 <b>№ {id} yopilgan ariza qayta ochildi</b> — fuqaro yangi xabar yozdi."


async def _exit_dialog(message: Message, state: FSMContext, note: str) -> None:
    await state.clear()
    await message.answer(note, reply_markup=ReplyKeyboardRemove())


def _admin_name(user) -> str:
    parts = [user.first_name or "", user.last_name or ""]
    name = " ".join(part for part in parts if part).strip()
    if user.username:
        name = f"{name} (@{user.username})" if name else f"@{user.username}"
    return name or str(user.id)


# --- Admin → fuqaro -------------------------------------------------------


@router.message(Dialog.chatting)
async def admin_message(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    application_id = data.get("application_id")
    application = db.get_application(DB_PATH, application_id) if application_id else None
    if application is None:
        await _exit_dialog(message, state, "Ariza topilmadi, yozishma to'xtatildi.")
        return

    text = (message.text or "").strip()

    if text == kb.DIALOG_END or text.startswith("/cancel"):
        await _exit_dialog(
            message,
            state,
            f"🏁 № {application_id} bo'yicha yozishma to'xtatildi. Ariza ochiq qoldi.",
        )
        return

    if text == kb.DIALOG_CLOSE:
        db.set_status(DB_PATH, application_id, db.STATUS_CLOSED)
        if application.get("tg_user_id"):
            await notify.deliver(
                message.bot, application["tg_user_id"], CLOSED_TEXT.format(id=application_id)
            )
        await notify.refresh_cards(message.bot, application_id)
        await _exit_dialog(message, state, f"✅ № {application_id} arizasi yopildi.")
        return

    if notify.unsupported_kind(message):
        await message.answer(
            "⚠️ Bu turdagi xabarni uzatib bo'lmaydi. Matn, hujjat, rasm, video "
            "yoki ovozli xabar yuboring."
        )
        return

    if not application.get("tg_user_id"):
        await message.answer("⚠️ Bu arizada Telegram foydalanuvchisi ko'rsatilmagan.")
        return

    kind, file_id, text_body, file_path = await notify.store_message(
        message, application_id, db.DIRECTION_ADMIN, admin_id=message.from_user.id
    )
    db.set_status(
        DB_PATH,
        application_id,
        db.STATUS_IN_PROGRESS,
        assigned_admin=message.from_user.id,
        assigned_admin_name=_admin_name(message.from_user),
    )
    delivered = await notify.deliver(
        message.bot,
        application["tg_user_id"],
        CITIZEN_HEADER.format(id=application_id),
        text_body,
        kind,
        file_id,
    )
    await notify.relay_to_staff(
        message.bot,
        application,
        notify.ADMIN_ECHO.format(
            id=application_id, who=notify.esc(_admin_name(message.from_user))
        ),
        text_body,
        kind,
        file_id,
        file_path,
    )
    await notify.refresh_cards(message.bot, application_id)

    if delivered:
        await message.answer("✅ Yuborildi.")
    else:
        await message.answer(
            "⚠️ Yetkazib bo'lmadi — fuqaro botni bloklagan bo'lishi mumkin. "
            "Xabar yozishmada saqlandi."
        )


# --- Fuqaro → admin -------------------------------------------------------


def _not_command(message: Message) -> bool:
    return not (message.text or "").startswith("/")


async def citizen_message(message: Message):
    """Fuqaroning erkin xabari ochiq arizasiga biriktiriladi."""
    application = db.application_for_user(DB_PATH, message.from_user.id)
    if application is None:
        return UNHANDLED
    if notify.unsupported_kind(message):
        return UNHANDLED

    application_id = application["id"]
    reopened = application.get("status") == db.STATUS_CLOSED
    if reopened:
        db.set_status(DB_PATH, application_id, db.STATUS_IN_PROGRESS)

    kind, file_id, text_body, file_path = await notify.store_message(
        message, application_id, db.DIRECTION_CITIZEN
    )

    # Guruhda kartochka ostiga qo'yiladi, keyin shaxsiy chatlarga.
    await notify.relay_to_staff(
        message.bot,
        application,
        GROUP_HEADER.format(id=application_id, fio=notify.esc(application["fio"])),
        text_body,
        kind,
        file_id,
        file_path,
    )
    await notify.refresh_cards(message.bot, application_id)

    assigned = application.get("assigned_admin")
    recipients = [assigned] if assigned in ADMIN_IDS else sorted(ADMIN_IDS)
    header = ADMIN_HEADER.format(id=application_id, fio=notify.esc(application["fio"]))
    delivered = 0
    for admin_id in recipients:
        if reopened:
            await notify.deliver(message.bot, admin_id, REOPENED.format(id=application_id))
        if await notify.deliver(message.bot, admin_id, header, text_body, kind, file_id):
            delivered += 1

    await message.answer("✅ Xabaringiz yuborildi, javobni shu yerda kutib turing.")
    return None


router.message.register(citizen_message, StateFilter(None), _not_command)
