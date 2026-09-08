"""Matrix (Element) ko'prigi.

Xodimlar Telegram bloklangan kompyuterlarda ishlaydi, shuning uchun arizalar
Matrix xonasiga ham tushadi va javob o'sha yerdan beriladi. Mantiq Telegram
guruhidagi bilan bir xil: kartochka yuboriladi, unga **reply** qilib javob
yoziladi, kartochka esa holat o'zgarganda joyida tahrirlanadi.

Element'da `/` bilan boshlanadigan buyruqlar mijozning o'ziga tegishli, shuning
uchun bot buyruqlari `!` bilan yoziladi.
"""

import asyncio
import html as html_module
import logging
import mimetypes
import os
import re
import tempfile
import time
from datetime import datetime

from nio import (
    AsyncClient,
    AsyncClientConfig,
    RoomMessageMedia,
    RoomMessageText,
    SyncResponse,
)

import db
import export
import notify
import ranges
import storage
from config import DB_PATH, FILES_DIR, matrix_can_answer
from validators import ValidationError

logger = logging.getLogger(__name__)

COMMAND_PREFIX = "!"
_TAG = re.compile(r"<[^>]+>")

HELP = (
    "<b>Qabul boti buyruqlari</b>\n"
    "!list — javob kutayotgan arizalar\n"
    "!ariza 12 — bitta arizaning kartochkasi\n"
    "!yozishma 12 — ariza bo'yicha butun yozishma (qisqasi: !tarix)\n"
    "!find Karimov — F.I.Sh., telefon, JSHSHIR yoki № bo'yicha qidiruv\n"
    "!export oy — Excel eksport (bugun · kecha · hafta · oy · otgan-oy · hammasi "
    "· yoki 01.09.2026 30.09.2026)\n"
    "!stats — hisobot\n"
    "!yopish 12 / !ochish 12 — arizani yopish yoki qayta ochish\n"
    "!id — xona ID sini ko'rsat (sozlash uchun)\n\n"
    "<b>Kartochkaga reply qilib:</b>\n"
    "• matn yoki fayl — fuqaroga javob bo'lib ketadi\n"
    "• <code>!yopish</code> — arizani yopadi (raqam yozish shart emas)\n"
    "• <code>!yozishma</code> — o'sha arizaning tarixini ko'rsatadi"
)


def html_body(text: str) -> str:
    """Bizdagi kartochka matni Matrix HTML'iga: qator ko'chirish <br/> bo'ladi."""
    return text.replace("\n", "<br/>")


def plain_body(text: str) -> str:
    """HTML teglarsiz variant — formatlashni qo'llamaydigan mijozlar uchun."""
    return html_module.unescape(_TAG.sub("", text))


def strip_reply_fallback(body: str) -> str:
    """Matrix reply'ga asl xabarni `> ` bilan qo'shib yuboradi — uni olib tashlaymiz."""
    lines = (body or "").split("\n")
    index = 0
    while index < len(lines) and lines[index].startswith(">"):
        index += 1
    while index < len(lines) and not lines[index].strip():
        index += 1
    return "\n".join(lines[index:]).strip()


def reply_target(event) -> str:
    """Reply qilingan xabar event_id si, bo'lmasa bo'sh satr."""
    relates = (event.source.get("content", {}) or {}).get("m.relates_to", {}) or {}
    return (relates.get("m.in_reply_to", {}) or {}).get("event_id", "") or ""


def parse_command(body: str):
    """`!export oy` → `("export", "oy")`. Buyruq bo'lmasa `(None, "")`."""
    text = (body or "").strip()
    if not text.startswith(COMMAND_PREFIX):
        return None, ""
    without = text[len(COMMAND_PREFIX):].strip()
    if not without:
        return None, ""
    name, _, args = without.partition(" ")
    return name.lower(), args.strip()


def display_name(user_id: str) -> str:
    """`@aziz:example.uz` → `aziz`."""
    return user_id.lstrip("@").split(":")[0] or user_id


def card_text(application: dict, message_count: int = 0) -> str:
    """Kartochka + Matrix uchun amallar. Element'da tugma yo'q, shuning uchun
    har bir kartochka o'z buyruqlarini ko'rsatib turadi."""
    number = application["id"]
    lines = [notify.render_group_card(application, message_count), ""]
    if application.get("status") == db.STATUS_CLOSED:
        lines.append(f"🔄 Qayta ochish: <code>!ochish {number}</code>")
    else:
        lines.append(
            f"✅ Yopish: shu xabarga reply qilib <code>!yopish</code> "
            f"(yoki <code>!yopish {number}</code>)"
        )
    lines.append(f"📜 Yozishma: <code>!yozishma {number}</code>")
    return "\n".join(lines)


class MatrixBridge:
    """Bitta xona bilan ishlaydigan ko'prik."""

    def __init__(
        self,
        homeserver: str,
        user: str,
        password: str = "",
        token: str = "",
        device: str = "qabul-bot",
        room_id: str = "",
        store_dir: str = "matrix_store",
        telegram_bot=None,
    ):
        self.homeserver = homeserver
        self.user = user
        self.password = password
        self.token = token
        self.device = device
        self.room_id = room_id
        self.store_dir = store_dir
        self.telegram_bot = telegram_bot
        self.client = None
        self._task = None
        self._started_ms = 0

    # --- hayotiy sikl -----------------------------------------------------

    async def start(self) -> bool:
        os.makedirs(self.store_dir, exist_ok=True)
        self.client = AsyncClient(
            self.homeserver,
            self.user,
            device_id=self.device,
            store_path=self.store_dir,
            config=AsyncClientConfig(request_timeout=30, max_timeout_retry_wait_time=30),
        )
        if self.token:
            self.client.access_token = self.token
            self.client.user_id = self.user
            self.client.device_id = self.device
        else:
            response = await self.client.login(self.password, device_name=self.device)
            if getattr(response, "access_token", None) is None:
                logger.error("Matrix login muvaffaqiyatsiz: %s", response)
                await self.client.close()
                self.client = None
                return False

        whoami = await self.client.whoami()
        user_id = getattr(whoami, "user_id", None)
        if not user_id:
            logger.error("Matrix hisobini tekshirib bo'lmadi: %s", whoami)
            await self.client.close()
            self.client = None
            return False
        self.user = user_id

        if self.room_id:
            await self.client.join(self.room_id)

        self._started_ms = int(time.time() * 1000)
        self.client.add_event_callback(self._on_text, RoomMessageText)
        self.client.add_event_callback(self._on_media, RoomMessageMedia)
        self.client.add_response_callback(self._on_sync, SyncResponse)
        self._task = asyncio.create_task(self._sync_forever(), name="matrix-sync")
        logger.info("Matrix ulandi: %s (xona: %s)", self.user, self.room_id or "sozlanmagan")
        return True

    async def _on_sync(self, response) -> None:
        """Kelgan takliflarni qabul qiladi — bot xonaga o'zi kiradi."""
        for room_id in list(getattr(response.rooms, "invite", {}) or {}):
            result = await self.client.join(room_id)
            if getattr(result, "room_id", None):
                logger.info("Xonaga qo'shildik: %s", room_id)
                await self._send(
                    "Salom! Men qabul botiman.\n"
                    f"Bu xona ID si: <code>{room_id}</code>\n"
                    "Uni <code>.env</code> faylidagi <b>MATRIX_ROOM_ID</b> ga yozib, "
                    "botni qayta ishga tushiring — shundan keyin arizalar shu yerga tushadi.",
                    room_id=room_id,
                )
            else:
                logger.warning("Xonaga qo'shilib bo'lmadi (%s): %s", room_id, result)

    async def _sync_forever(self) -> None:
        try:
            await self.client.sync_forever(timeout=30000, full_state=False)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Matrix sync to'xtadi")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        if self.client:
            await self.client.close()

    # --- yuborish ---------------------------------------------------------

    async def _send(self, text: str, reply_to: str = "", room_id: str = "") -> str:
        """Formatlangan xabar yuboradi, event_id qaytaradi."""
        target = room_id or self.room_id
        if not self.client or not target:
            return ""
        content = {
            "msgtype": "m.text",
            "body": plain_body(text),
            "format": "org.matrix.custom.html",
            "formatted_body": html_body(text),
        }
        if reply_to:
            content["m.relates_to"] = {"m.in_reply_to": {"event_id": reply_to}}
        try:
            response = await self.client.room_send(target, "m.room.message", content)
        except Exception:
            logger.exception("Matrix'ga xabar yuborib bo'lmadi")
            return ""
        return getattr(response, "event_id", "") or ""

    async def _edit(self, event_id: str, text: str) -> bool:
        if not self.client or not self.room_id or not event_id:
            return False
        new_content = {
            "msgtype": "m.text",
            "body": plain_body(text),
            "format": "org.matrix.custom.html",
            "formatted_body": html_body(text),
        }
        content = dict(new_content)
        content["body"] = "* " + content["body"]
        content["m.new_content"] = new_content
        content["m.relates_to"] = {"rel_type": "m.replace", "event_id": event_id}
        try:
            await self.client.room_send(self.room_id, "m.room.message", content)
            return True
        except Exception:
            logger.exception("Matrix kartochkasini tahrirlab bo'lmadi")
            return False

    async def _send_file(self, path: str, caption: str, file_name: str = "") -> str:
        """Faylni xonaga yuklaydi. Izoh alohida xabar bo'lib ketadi."""
        if not self.client or not self.room_id or not path or not os.path.exists(path):
            return ""
        name = file_name or os.path.basename(path)
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        size = os.path.getsize(path)
        try:
            with open(path, "rb") as handle:
                response, _ = await self.client.upload(
                    handle, content_type=mime, filename=name, filesize=size
                )
            uri = getattr(response, "content_uri", "")
            if not uri:
                logger.warning("Faylni Matrix'ga yuklab bo'lmadi: %s", response)
                return ""
            msgtype = "m.image" if mime.startswith("image/") else "m.file"
            await self.client.room_send(
                self.room_id,
                "m.room.message",
                {
                    "msgtype": msgtype,
                    "body": name,
                    "url": uri,
                    "info": {"mimetype": mime, "size": size},
                },
            )
        except Exception:
            logger.exception("Faylni Matrix'ga yuborib bo'lmadi")
            return ""
        if caption:
            return await self._send(caption)
        return ""

    # --- notify chaqiradigan interfeys ------------------------------------

    async def post_card(self, application: dict) -> bool:
        event_id = await self._send("🆕 <b>Yangi ariza</b>\n\n" + card_text(application))
        if not event_id:
            return False
        db.set_matrix_message(DB_PATH, application["id"], self.room_id, event_id)
        return True

    async def refresh_card(self, application_id: int) -> None:
        application = db.get_application(DB_PATH, application_id)
        if not application or not application.get("matrix_event_id"):
            return
        text = card_text(application, db.count_messages(DB_PATH, application_id))
        await self._edit(application["matrix_event_id"], text)

    async def post_to_room(self, application: dict, header: str, text: str, file_path: str = "", file_name: str = "") -> None:
        """Xabarni xonaga qo'yadi va uni ham arizaga bog'laydi (unga reply qilish uchun)."""
        body = f"{header}\n\n{notify.esc(text)}" if text else header
        if file_path:
            event_id = await self._send_file(file_path, body, file_name)
        else:
            event_id = await self._send(body, reply_to=application.get("matrix_event_id") or "")
        if event_id:
            db.link_matrix_event(DB_PATH, self.room_id, event_id, application["id"])

    # --- kiruvchi xabarlar ------------------------------------------------

    def _skip(self, room, event) -> bool:
        if self.room_id and room.room_id != self.room_id:
            return True
        if event.sender == self.user:
            return True
        # Sync eski tarixni ham beradi — bot ishga tushgunga qadar bo'lganini o'tkazib yuboramiz.
        return event.server_timestamp < self._started_ms

    async def _on_text(self, room, event) -> None:
        if self._skip(room, event):
            return
        body = strip_reply_fallback(event.body)
        command, args = parse_command(body)
        if command == "id":
            await self._send(
                f"Xona ID: <code>{room.room_id}</code>\n"
                "Uni <code>.env</code> faylidagi <b>MATRIX_ROOM_ID</b> ga yozing va "
                "botni qayta ishga tushiring.",
                reply_to=event.event_id,
                room_id=room.room_id,
            )
            return
        if command:
            # Kartochkaga reply qilib `!yopish` yozilsa, raqamni reply'dan olamiz.
            fallback = ""
            target = reply_target(event)
            if target:
                found = db.application_by_matrix_event(DB_PATH, room.room_id, target)
                if found is not None:
                    fallback = str(found)
            await self._handle_command(
                event.sender, command, args or fallback, event.event_id
            )
            return
        await self._handle_reply(room, event, body)

    async def _on_media(self, room, event) -> None:
        if self._skip(room, event):
            return
        await self._handle_reply(room, event, strip_reply_fallback(event.body or ""), media=True)

    async def _handle_reply(self, room, event, body: str, media: bool = False) -> None:
        target = reply_target(event)
        if not target:
            return
        application_id = db.application_by_matrix_event(DB_PATH, room.room_id, target)
        if application_id is None:
            return  # arizaga aloqasi yo'q suhbat

        if not matrix_can_answer(event.sender):
            await self._send(
                f"⚠️ {notify.esc(display_name(event.sender))}, sizda javob berish huquqi yo'q.",
                reply_to=event.event_id,
            )
            return

        application = db.get_application(DB_PATH, application_id)
        if application is None:
            return
        if not application.get("tg_user_id"):
            await self._send("⚠️ Bu arizada Telegram foydalanuvchisi ko'rsatilmagan.", reply_to=event.event_id)
            return

        local_path, file_name = "", ""
        if media:
            local_path, file_name = await self._download(event, application_id)
            if not local_path:
                await self._send("⚠️ Faylni yuklab olib bo'lmadi.", reply_to=event.event_id)
                return

        if not body and not local_path:
            return

        db.add_message(
            DB_PATH,
            application_id,
            db.DIRECTION_ADMIN,
            text=body,
            file_path=local_path,
            file_name=file_name,
            file_type="document" if local_path else "",
        )
        db.set_status(
            DB_PATH,
            application_id,
            db.STATUS_IN_PROGRESS,
            assigned_admin_name=display_name(event.sender),
        )

        delivered = await self._to_citizen(application, body, local_path, file_name)
        await notify.relay_to_staff(
            self.telegram_bot,
            application,
            notify.ADMIN_ECHO.format(
                id=application_id, who=notify.esc(display_name(event.sender))
            ),
            body,
            file_path=local_path,
            skip="matrix",
        )
        await notify.refresh_cards(self.telegram_bot, application_id)

        if delivered:
            await self._react(event.event_id, "👍")
        else:
            await self._send(
                "⚠️ Yetkazib bo'lmadi — fuqaro botni bloklagan bo'lishi mumkin. "
                "Xabar yozishmada saqlandi.",
                reply_to=event.event_id,
            )

    async def _to_citizen(self, application: dict, text: str, path: str, file_name: str) -> bool:
        if self.telegram_bot is None:
            return False
        header = f"📩 <b>№ {application['id']} — arizangizga javob</b>"
        if path:
            return await notify.deliver_local_file(
                self.telegram_bot, application["tg_user_id"], header, text, path, file_name
            )
        return await notify.deliver(self.telegram_bot, application["tg_user_id"], header, text)

    async def _download(self, event, application_id: int):
        """Matrix'dagi faylni diskka tushiradi."""
        url = getattr(event, "url", "") or ""
        name = event.body or "fayl"
        if not url.startswith("mxc://"):
            return "", ""
        target = storage.build_path(FILES_DIR, application_id, name)
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            response = await self.client.download(url)
            data = getattr(response, "body", None)
            if data is None:
                logger.warning("Matrix fayli yuklanmadi: %s", response)
                return "", ""
            with open(target, "wb") as handle:
                handle.write(data)
        except Exception:
            logger.exception("Matrix faylini saqlab bo'lmadi")
            return "", ""
        return target, name

    async def _react(self, event_id: str, emoji: str) -> None:
        try:
            await self.client.room_send(
                self.room_id,
                "m.reaction",
                {"m.relates_to": {"rel_type": "m.annotation", "event_id": event_id, "key": emoji}},
            )
        except Exception:
            logger.debug("Matrix reaksiyasi qo'yilmadi", exc_info=True)

    # --- buyruqlar --------------------------------------------------------

    async def _handle_command(self, sender: str, command: str, args: str, event_id: str) -> None:
        if not matrix_can_answer(sender):
            await self._send(
                f"⚠️ {notify.esc(display_name(sender))}, sizda ruxsat yo'q.", reply_to=event_id
            )
            return

        if command in {"yordam", "help", "start"}:
            await self._send(HELP)
        elif command in {"list", "royxat"}:
            await self._cmd_list()
        elif command in {"ariza", "card"}:
            await self._cmd_application(args)
        elif command in {"yozishma", "tarix", "history"}:
            await self._cmd_history(args)
        elif command in {"find", "qidir"}:
            await self._cmd_find(args)
        elif command in {"export", "eksport"}:
            await self._cmd_export(args)
        elif command in {"stats", "hisobot"}:
            await self._cmd_stats()
        elif command in {"yopish", "yop", "ochish", "och"}:
            await self._cmd_status(command, args)
        else:
            await self._send(f"Noma'lum buyruq: <code>!{notify.esc(command)}</code>\n\n" + HELP)

    async def _cmd_list(self) -> None:
        total = db.count_open_applications(DB_PATH)
        if total == 0:
            await self._send("✅ Javob kutayotgan ariza yo'q.")
            return
        rows = db.open_applications(DB_PATH, 15)
        lines = [f"📋 <b>Javob kutayotgan arizalar</b> — jami {total} ta\n"]
        for row in rows:
            status = db.STATUS_LABELS.get(row["status"], row["status"])
            lines.append(
                f"<b>№ {row['id']}</b> · {notify.esc(row['fio'])} · {notify.esc(row['phone'])} "
                f"· {status}"
            )
        if total > len(rows):
            lines.append(f"\n… va yana {total - len(rows)} ta. Aniqlash: !find yoki !ariza")
        await self._send("\n".join(lines))

    def _application_from_args(self, args: str):
        raw = (args or "").strip().lstrip("№# ")
        if not raw.isdigit():
            return None
        return db.get_application(DB_PATH, int(raw))

    async def _cmd_application(self, args: str) -> None:
        application = self._application_from_args(args)
        if application is None:
            await self._send("Ariza raqamini yozing. Masalan: <code>!ariza 12</code>")
            return
        event_id = await self._send(
            card_text(application, db.count_messages(DB_PATH, application["id"]))
        )
        if event_id:
            db.link_matrix_event(DB_PATH, self.room_id, event_id, application["id"])

    async def _cmd_history(self, args: str) -> None:
        application = self._application_from_args(args)
        if application is None:
            await self._send("Ariza raqamini yozing. Masalan: <code>!yozishma 12</code>")
            return
        messages = db.fetch_messages(DB_PATH, application["id"])
        await self._send(notify.render_history(application, messages))

    async def _cmd_find(self, args: str) -> None:
        if not args:
            await self._send("Qidiruv so'zini yozing. Masalan: <code>!find Karimov</code>")
            return
        found = db.search_applications(DB_PATH, args)
        if not found:
            await self._send(f"«{notify.esc(args)}» bo'yicha ariza topilmadi.")
            return
        for application in found[:5]:
            event_id = await self._send(
                card_text(application, db.count_messages(DB_PATH, application["id"]))
            )
            if event_id:
                db.link_matrix_event(DB_PATH, self.room_id, event_id, application["id"])
        if len(found) > 5:
            await self._send(f"… va yana {len(found) - 5} ta ariza topildi.")

    async def _cmd_export(self, args: str) -> None:
        try:
            date_from, date_to, label = ranges.parse_request(args)
        except ValidationError as error:
            await self._send(f"⚠️ {notify.esc(error)}")
            return

        rows = db.fetch_applications(DB_PATH, date_from, date_to)
        if not rows:
            await self._send(f"«{notify.esc(label)}» uchun ariza topilmadi.")
            return

        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        name = f"qabul_jadvali_{stamp}.xlsx"
        path = os.path.join(tempfile.gettempdir(), name)
        try:
            export.save_workbook(rows, path)
            await self._send_file(path, f"📊 <b>Qabul jadvali</b> · {notify.esc(label)} · {len(rows)} ta ariza", name)
        except Exception:
            logger.exception("Matrix uchun eksport qilib bo'lmadi")
            await self._send("❌ Faylni tayyorlashda xato yuz berdi.")
        finally:
            if os.path.exists(path):
                os.remove(path)

    async def _cmd_stats(self) -> None:
        total = db.count_applications(DB_PATH)
        waiting = db.count_open_applications(DB_PATH)
        today = len(db.fetch_applications(DB_PATH, *ranges.resolve("today")[:2]))
        month = len(db.fetch_applications(DB_PATH, *ranges.resolve("month")[:2]))
        last = db.last_created_at(DB_PATH)
        text = (
            "📊 <b>Hisobot</b>\n\n"
            f"Jami arizalar: <b>{total}</b>\n"
            f"Bugun: <b>{today}</b>\n"
            f"Shu oy: <b>{month}</b>\n"
            f"Javob kutmoqda: <b>{waiting}</b>"
        )
        if last:
            text += f"\nOxirgi ariza: {export.pretty_datetime(last)}"
        await self._send(text)

    async def _cmd_status(self, command: str, args: str) -> None:
        application = self._application_from_args(args)
        if application is None:
            await self._send(
                f"Ariza raqamini yozing. Masalan: <code>!{command} 12</code>\n"
                "Yoki kartochkaga reply qilib yozing."
            )
            return

        application_id = application["id"]
        if command in {"yopish", "yop"}:
            db.set_status(DB_PATH, application_id, db.STATUS_CLOSED)
            note = f"✅ № {application_id} arizasi yopildi."
            citizen_text = (
                f"✅ <b>№ {application_id} arizangiz yakunlandi.</b>\n"
                "Savolingiz qolsa shu yerga yozing — murojaat qayta ochiladi."
            )
        else:
            db.set_status(DB_PATH, application_id, db.STATUS_IN_PROGRESS)
            note = f"🔄 № {application_id} arizasi qayta ochildi."
            citizen_text = f"🔄 <b>№ {application_id} arizangiz qayta ko'rib chiqilmoqda.</b>"

        if application.get("tg_user_id") and self.telegram_bot is not None:
            await notify.deliver(self.telegram_bot, application["tg_user_id"], citizen_text)
        await notify.refresh_cards(self.telegram_bot, application_id)
        await self._send(note)
