"""Qabul jadvali boti — ishga tushirish nuqtasi."""

import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
)

import bridge
import config
import db
import matrix_bot
import net
from config import ADMIN_IDS, BOT_TOKEN, CA_BUNDLE, DB_PATH, FILES_DIR, GROUP_ID
from handlers import admin, dialog, form, group

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("qabul_bot")


async def main() -> None:
    if not BOT_TOKEN:
        sys.exit(
            "BOT_TOKEN topilmadi. `.env.example` dan `.env` yarating va "
            "@BotFather bergan tokenni yozing."
        )
    if not ADMIN_IDS:
        logger.warning("ADMIN_IDS bo'sh — admin buyruqlari hech kimga ishlamaydi.")
    logger.info("Adminlar: %s", sorted(ADMIN_IDS) or "yo'q")
    logger.info("Admin guruhi: %s", GROUP_ID or "sozlanmagan (faqat shaxsiy chatlar)")

    db.init_db(DB_PATH)
    os.makedirs(FILES_DIR, exist_ok=True)
    logger.info("Baza tayyor: %s | fayllar: %s", db.describe(DB_PATH), FILES_DIR)

    bot = Bot(
        BOT_TOKEN,
        session=net.build_session(CA_BUNDLE),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(admin.router)
    dispatcher.include_router(group.router)
    dispatcher.include_router(dialog.router)
    dispatcher.include_router(form.router)

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Yangi ariza to'ldirish"),
            BotCommand(command="cancel", description="Arizani bekor qilish"),
            BotCommand(command="myid", description="Telegram ID imni ko'rsat"),
            BotCommand(command="help", description="Yordam"),
        ],
        scope=BotCommandScopeAllPrivateChats(),
    )
    await bot.set_my_commands(
        [
            BotCommand(command="id", description="Guruh ID sini ko'rsat"),
            BotCommand(command="list", description="Javob kutayotgan arizalar"),
            BotCommand(command="find", description="Ariza qidirish"),
            BotCommand(command="ariza", description="Ariza kartochkasi (raqami bilan)"),
            BotCommand(command="export", description="Excel eksport"),
            BotCommand(command="stats", description="Hisobot"),
        ],
        scope=BotCommandScopeAllGroupChats(),
    )

    matrix = None
    if config.matrix_enabled():
        matrix = matrix_bot.MatrixBridge(
            homeserver=config.MATRIX_HOMESERVER,
            user=config.MATRIX_USER,
            password=config.MATRIX_PASSWORD,
            token=config.MATRIX_TOKEN,
            device=config.MATRIX_DEVICE,
            room_id=config.MATRIX_ROOM_ID,
            store_dir=config.MATRIX_STORE,
            telegram_bot=bot,
        )
        if await matrix.start():
            bridge.set_bridge(matrix)
        else:
            logger.error("Matrix ulanmadi — bot faqat Telegram bilan ishlaydi.")
            matrix = None
    else:
        logger.info("Matrix sozlanmagan — bot faqat Telegram bilan ishlaydi.")

    me = await bot.get_me()
    logger.info("Bot ishga tushdi: @%s", me.username)
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dispatcher.start_polling(bot)
    finally:
        if matrix is not None:
            await matrix.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi")
