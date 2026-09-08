"""Yozishmadagi fayllarni diskda saqlash.

Telegram fayllarni o'zida saqlaydi va `file_id` orqali qayta yuborish mumkin,
lekin arxiv uchun nusxa ham kerak — bot yoki token almashsa `file_id` yaroqsiz
bo'lib qoladi.
"""

import logging
import os
import re
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Telegram bot API orqali yuklab olish chegarasi.
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_name(name: str, default: str = "fayl") -> str:
    """Fayl nomini disk uchun xavfsiz ko'rinishga keltiradi."""
    cleaned = _UNSAFE.sub("_", (name or "").strip()).strip("._")
    return cleaned[:80] or default


def build_path(base_dir: str, application_id: int, file_name: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = os.path.join(base_dir, str(application_id))
    return os.path.join(folder, f"{stamp}_{safe_name(file_name)}")


async def save_file(bot, base_dir: str, application_id: int, file_id: str, file_name: str) -> Optional[str]:
    """Faylni yuklab olib diskka yozadi. Muvaffaqiyatsiz bo'lsa None qaytaradi."""
    path = build_path(base_dir, application_id, file_name)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        await bot.download(file_id, destination=path)
        return path
    except Exception:
        logger.exception("Faylni saqlab bo'lmadi: ariza %s", application_id)
        return None
