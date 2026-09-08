"""Ariza kartochkasi va xabarlarni ikki tomonga uzatish."""

import html
import logging
import os
from typing import Optional, Tuple

from aiogram.exceptions import TelegramAPIError

import bridge
import db
import export
import keyboards as kb
import storage
from config import DB_PATH, FILES_DIR

logger = logging.getLogger(__name__)

CAPTION_LIMIT = 1024
ADMIN_ECHO = "👮 <b>№ {id} · {who}</b> javob berdi:"
TEXT_LIMIT = 4000

STATUS_ICONS = {
    db.STATUS_NEW: "🆕",
    db.STATUS_IN_PROGRESS: "✍️",
    db.STATUS_CLOSED: "✅",
}

# Telegram'ga izoh bilan yuborish mumkin bo'lgan turlar.
MEDIA_KINDS = ("document", "photo", "video", "audio", "voice")


def esc(text) -> str:
    """HTML uchun xavfsiz matn. Apostrof `&#x27;` ga aylanmasin."""
    return html.escape(str(text or ""), quote=False)


def status_line(application: dict) -> str:
    status = application.get("status") or db.STATUS_NEW
    icon = STATUS_ICONS.get(status, "•")
    return f"{icon} {db.STATUS_LABELS.get(status, status)}"


def render_card(application: dict) -> str:
    """Admin ko'radigan to'liq ariza kartochkasi."""
    phones = export.format_phones(
        application.get("phone", ""), application.get("phone_extra") or ""
    )
    lines = [
        f"<b>№ {application['id']}</b> · {status_line(application)}",
        "",
        f"👤 <b>F.I.Sh.:</b> {esc(application.get('fio'))}",
        f"🪪 <b>Pasport:</b> {esc(application.get('passport'))}",
        f"🔢 <b>JSHSHIR:</b> {esc(application.get('jshshir'))}",
        f"🎂 <b>Tug'ilgan sanasi:</b> {esc(application.get('birth_date'))}",
        f"🏠 <b>Manzil:</b> {esc(application.get('address'))}",
        f"📞 <b>Telefon:</b> {esc(phones)}",
        "",
        f"📝 <b>Murojaat:</b>\n{esc(application.get('message'))}",
        "",
        f"🕒 <b>Qabul vaqti:</b> {export.pretty_datetime(application.get('created_at', ''))}",
    ]
    if application.get("assigned_admin"):
        who = application.get("assigned_admin_name") or f"ID {application['assigned_admin']}"
        lines.append(f"👮 <b>Mas'ul admin:</b> {esc(who)}")
    return "\n".join(lines)


def render_history(application: dict, messages: list) -> str:
    """Ariza bo'yicha butun yozishma."""
    header = f"📜 <b>№ {application['id']} · yozishma</b> ({len(messages)} ta xabar)"
    if not messages:
        return header + "\n\nHozircha xabar almashilmagan."
    lines = [header, ""]
    for item in messages:
        who = "👮 Admin" if item["direction"] == db.DIRECTION_ADMIN else "👤 Fuqaro"
        when = export.pretty_datetime(item["created_at"])
        lines.append(f"<b>{who}</b> · {when}")
        if item["text"]:
            lines.append(esc(item["text"]))
        if item["file_name"] or item["file_type"]:
            lines.append(f"📎 {esc(item['file_name'] or item['file_type'])}")
        lines.append("")
    return "\n".join(lines)[:TEXT_LIMIT]


def extract_media(message) -> Tuple[Optional[str], str, str]:
    """Xabardagi faylni aniqlaydi: `(turi, file_id, nomi)`."""
    if message.document:
        return "document", message.document.file_id, message.document.file_name or "hujjat"
    if message.photo:
        return "photo", message.photo[-1].file_id, "rasm.jpg"
    if message.video:
        return "video", message.video.file_id, message.video.file_name or "video.mp4"
    if message.audio:
        return "audio", message.audio.file_id, message.audio.file_name or "audio.mp3"
    if message.voice:
        return "voice", message.voice.file_id, "ovozli_xabar.ogg"
    return None, "", ""


def unsupported_kind(message) -> bool:
    """Uzatib bo'lmaydigan tur (stiker, video-doira, joylashuv va h.k.)."""
    if message.text or message.caption:
        return False
    kind, _, _ = extract_media(message)
    return kind is None


async def send_media(bot, chat_id: int, kind: str, file_id: str, caption: str):
    method = getattr(bot, f"send_{kind}")
    return await method(chat_id, **{kind: file_id}, caption=caption or None)


async def deliver(
    bot,
    chat_id: int,
    header: str,
    text: str = "",
    kind: Optional[str] = None,
    file_id: str = "",
) -> bool:
    """Xabarni yetkazadi. Bloklangan yoki xato bo'lsa False qaytaradi."""
    body = f"{header}\n\n{esc(text)}" if text else header
    try:
        if kind and file_id:
            await send_media(bot, chat_id, kind, file_id, body[:CAPTION_LIMIT])
        else:
            await bot.send_message(chat_id, body[:TEXT_LIMIT])
        return True
    except TelegramAPIError as error:
        logger.warning("Xabar yetkazilmadi (chat %s): %s", chat_id, error)
        return False


async def notify_admins(bot, admin_ids, application: dict, keyboard=None) -> int:
    """Yangi ariza haqida barcha adminlarga xabar beradi. Yetgan adminlar sonini qaytaradi."""
    delivered = 0
    text = "🆕 <b>Yangi ariza</b>\n\n" + render_card(application)
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text, reply_markup=keyboard)
            delivered += 1
        except TelegramAPIError as error:
            logger.warning("Adminga xabar yetmadi (%s): %s", admin_id, error)
    return delivered


async def store_message(message, application_id: int, direction: str, admin_id=None):
    """Xabar tarkibini ajratadi, faylni saqlaydi va yozishmaga yozadi."""
    kind, file_id, file_name = extract_media(message)
    text = message.text or message.caption or ""
    file_path = ""
    if kind:
        file_path = await storage.save_file(
            message.bot, FILES_DIR, application_id, file_id, file_name
        ) or ""
    db.add_message(
        DB_PATH,
        application_id,
        direction,
        admin_id=admin_id,
        text=text,
        file_id=file_id,
        file_path=file_path,
        file_name=file_name,
        file_type=kind or "",
    )
    return kind, file_id, text, file_path


# --- Guruh kartochkasi ----------------------------------------------------


def render_group_card(application: dict, message_count: int = 0) -> str:
    """Guruhdagi kartochka: ariza + joriy holat + nima qilish kerakligi."""
    lines = [render_card(application), ""]
    status = application.get("status") or db.STATUS_NEW

    if status == db.STATUS_NEW:
        lines.append("⏳ <b>Javob kutilmoqda</b>")
        lines.append("↩️ Javob berish uchun shu xabarga <b>reply</b> qiling.")
    elif status == db.STATUS_IN_PROGRESS:
        lines.append(f"💬 {message_count} ta xabar almashildi")
        lines.append("↩️ Davom ettirish uchun shu xabarga <b>reply</b> qiling.")
    else:
        when = export.pretty_datetime(application.get("closed_at", ""))
        lines.append(f"✅ <b>Yopildi:</b> {when} · {message_count} ta xabar almashildi")
    return "\n".join(lines)[:TEXT_LIMIT]


async def publish_application(bot, group_id: int, application: dict) -> None:
    """Yangi arizani xodimlar kanallariga tarqatadi: Telegram guruhi va Matrix xonasi."""
    if group_id and bot is not None:
        try:
            sent = await bot.send_message(
                group_id,
                render_group_card(application),
                reply_markup=kb.group_card_keyboard(application["id"], closed=False),
            )
            db.set_group_message(DB_PATH, application["id"], group_id, sent.message_id)
        except TelegramAPIError as error:
            logger.warning("Guruhga xabar yuborilmadi (%s): %s", group_id, error)

    matrix = bridge.get()
    if matrix is not None:
        await matrix.post_card(db.get_application(DB_PATH, application["id"]) or application)


async def refresh_cards(bot, application_id: int) -> None:
    """Holat o'zgargach ikkala kartochkani ham joyida tahrirlaydi."""
    matrix = bridge.get()
    if matrix is not None:
        await matrix.refresh_card(application_id)

    application = db.get_application(DB_PATH, application_id)
    if bot is None or not application or not application.get("group_message_id"):
        return
    closed = application.get("status") == db.STATUS_CLOSED
    text = render_group_card(application, db.count_messages(DB_PATH, application_id))
    try:
        await bot.edit_message_text(
            text,
            chat_id=application["group_chat_id"],
            message_id=application["group_message_id"],
            reply_markup=kb.group_card_keyboard(application_id, closed),
        )
    except TelegramAPIError as error:
        # «message is not modified» — normal holat, boshqa xatolar jurnalga tushadi.
        if "not modified" not in str(error):
            logger.warning("Guruh kartochkasini yangilab bo'lmadi (№ %s): %s", application_id, error)


async def relay_to_staff(
    bot,
    application: dict,
    header: str,
    text: str = "",
    kind=None,
    file_id: str = "",
    file_path: str = "",
    skip: str = "",
) -> None:
    """Xabarni xodimlarning ikkala kanaliga qo'yadi.

    `skip` — xabar kelib chiqqan kanal ("group" yoki "matrix"): u yerda xabar
    allaqachon ko'rinib turibdi, takrorlash shart emas.
    """
    if skip != "matrix":
        matrix = bridge.get()
        if matrix is not None:
            await matrix.post_to_room(application, header, text, file_path)

    if skip == "group":
        return
    chat_id = application.get("group_chat_id")
    if not chat_id or bot is None:
        return

    body = f"{header}\n\n{esc(text)}" if text else header
    reply_to = application.get("group_message_id")
    try:
        if kind and file_id:
            method = getattr(bot, f"send_{kind}")
            sent = await method(
                chat_id,
                **{kind: file_id},
                caption=body[:CAPTION_LIMIT],
                reply_to_message_id=reply_to,
            )
        elif file_path and os.path.exists(file_path):
            from aiogram.types import FSInputFile

            sent = await bot.send_document(
                chat_id,
                FSInputFile(file_path),
                caption=body[:CAPTION_LIMIT],
                reply_to_message_id=reply_to,
            )
        else:
            sent = await bot.send_message(
                chat_id, body[:TEXT_LIMIT], reply_to_message_id=reply_to
            )
    except TelegramAPIError as error:
        logger.warning("Xabarni guruhga qo'yib bo'lmadi: %s", error)
        return
    db.link_group_message(DB_PATH, chat_id, sent.message_id, application["id"])


async def deliver_local_file(
    bot, chat_id: int, header: str, text: str, path: str, file_name: str = ""
) -> bool:
    """Diskdagi faylni yuboradi (Matrix'dan kelgan javoblar uchun)."""
    from aiogram.types import FSInputFile

    body = f"{header}\n\n{esc(text)}" if text else header
    name = file_name or os.path.basename(path)
    is_image = os.path.splitext(name)[1].lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    try:
        document = FSInputFile(path, filename=name)
        if is_image:
            await bot.send_photo(chat_id, document, caption=body[:CAPTION_LIMIT])
        else:
            await bot.send_document(chat_id, document, caption=body[:CAPTION_LIMIT])
        return True
    except TelegramAPIError as error:
        logger.warning("Faylni yetkazib bo'lmadi (chat %s): %s", chat_id, error)
        return False
