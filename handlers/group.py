"""Admin guruhida ishlash.

Telegram botlari guruhda maxfiylik rejimida turadi: ular guruhdagi barcha
yozishmani emas, faqat buyruqlar va **o'z xabariga qilingan reply**larni oladi.
Shuning uchun javob berish reply orqali quriladi — bu maxfiylik rejimini
o'chirishni talab qilmaydi va guruhdagi oddiy suhbatga aralashmaydi.
"""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import ChatMemberUpdated, Message, ReactionTypeEmoji

import db
import notify
from config import DB_PATH, is_admin

logger = logging.getLogger(__name__)
router = Router(name="group")

GROUP_TYPES = {"group", "supergroup"}
router.message.filter(F.chat.type.in_(GROUP_TYPES))

CITIZEN_HEADER = "📩 <b>№ {id} — arizangizga javob</b>"
GROUP_CITIZEN_HEADER = "👤 <b>№ {id} · {fio}</b> yozdi:"

SETUP_HINT = (
    "Bu guruhni ishga tushirish uchun quyidagi raqamni <code>.env</code> faylidagi "
    "<b>GROUP_ID</b> ga yozing va botni qayta ishga tushiring:\n"
    "<code>{chat_id}</code>"
)


def display_name(user) -> str:
    parts = [user.first_name or "", user.last_name or ""]
    name = " ".join(part for part in parts if part).strip()
    if user.username:
        name = f"{name} (@{user.username})" if name else f"@{user.username}"
    return name or str(user.id)


@router.message(Command("id"))
async def cmd_chat_id(message: Message) -> None:
    await message.answer(SETUP_HINT.format(chat_id=message.chat.id))


@router.my_chat_member()
async def on_added_to_chat(event: ChatMemberUpdated) -> None:
    """Bot guruhga qo'shilganda o'z chat ID sini aytadi."""
    if event.chat.type not in GROUP_TYPES:
        return
    if event.new_chat_member.status not in {"member", "administrator"}:
        return
    try:
        await event.bot.send_message(event.chat.id, SETUP_HINT.format(chat_id=event.chat.id))
    except Exception:
        logger.warning("Guruhga salomlashuv xabarini yuborib bo'lmadi: %s", event.chat.id)


@router.message(F.reply_to_message)
async def on_admin_reply(message: Message) -> None:
    """Kartochkaga qilingan reply — fuqaroga javob."""
    application_id = db.application_by_group_message(
        DB_PATH, message.chat.id, message.reply_to_message.message_id
    )
    if application_id is None:
        return  # arizaga aloqasi yo'q oddiy suhbat

    if not is_admin(message.from_user.id):
        await message.reply("⚠️ Sizda javob berish huquqi yo'q.")
        return

    application = db.get_application(DB_PATH, application_id)
    if application is None:
        await message.reply("Ariza topilmadi.")
        return
    if not application.get("tg_user_id"):
        await message.reply("⚠️ Bu arizada Telegram foydalanuvchisi ko'rsatilmagan.")
        return
    if notify.unsupported_kind(message):
        await message.reply(
            "⚠️ Bu turdagi xabarni uzatib bo'lmaydi. Matn, hujjat, rasm, video "
            "yoki ovozli xabar yuboring."
        )
        return

    kind, file_id, text, file_path = await notify.store_message(
        message, application_id, db.DIRECTION_ADMIN, admin_id=message.from_user.id
    )
    db.set_status(
        DB_PATH,
        application_id,
        db.STATUS_IN_PROGRESS,
        assigned_admin=message.from_user.id,
        assigned_admin_name=display_name(message.from_user),
    )

    delivered = await notify.deliver(
        message.bot,
        application["tg_user_id"],
        CITIZEN_HEADER.format(id=application_id),
        text,
        kind,
        file_id,
    )
    await notify.relay_to_staff(
        message.bot,
        application,
        notify.ADMIN_ECHO.format(
            id=application_id, who=notify.esc(display_name(message.from_user))
        ),
        text,
        kind,
        file_id,
        file_path,
        skip="group",
    )
    await notify.refresh_cards(message.bot, application_id)

    if delivered:
        # Muvaffaqiyat guruhni xabarga to'ldirmasin: kartochka o'zi yangilanadi.
        try:
            await message.react([ReactionTypeEmoji(emoji="👍")])
        except Exception:
            logger.debug("Reaksiya qo'yib bo'lmadi", exc_info=True)
    else:
        await message.reply(
            "⚠️ Yetkazib bo'lmadi — fuqaro botni bloklagan bo'lishi mumkin. "
            "Xabar yozishmada saqlandi."
        )
