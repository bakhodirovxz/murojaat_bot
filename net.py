"""Telegram bilan tarmoq ulanishi.

aiogram Telegram API'ga faqat `certifi` sertifikatlar ro'yxati bilan ishonadi.
Ba'zi tashkilot tarmoqlarida TLS trafik proksi orqali qayta imzolanadi — bunday
tarmoqda `certifi` yetarli emas va ulanish `CERTIFICATE_VERIFY_FAILED` bilan
tugaydi. Shu sabab, tizimda CA to'plami ko'rsatilgan bo'lsa, o'shani ishlatamiz.
"""

import logging
import os
import ssl
from typing import Optional

from aiogram.client.session.aiohttp import AiohttpSession

logger = logging.getLogger(__name__)


def resolve_ca_bundle(explicit: str = "") -> Optional[str]:
    """`.env` dagi CA_BUNDLE, so'ng standart muhit o'zgaruvchilarini tekshiradi."""
    candidates = (
        explicit,
        os.getenv("CA_BUNDLE", ""),
        os.getenv("SSL_CERT_FILE", ""),
        os.getenv("REQUESTS_CA_BUNDLE", ""),
    )
    for candidate in candidates:
        path = (candidate or "").strip().strip('"')
        if path and os.path.isfile(path):
            return path
    return None


def build_session(ca_bundle: str = "") -> AiohttpSession:
    """Kerak bo'lsa tizim CA to'plamiga sozlangan aiogram sessiyasi."""
    session = AiohttpSession()
    path = resolve_ca_bundle(ca_bundle)
    if path:
        session._connector_init["ssl"] = ssl.create_default_context(cafile=path)
        logger.info("TLS sertifikatlari: %s", path)
    return session
