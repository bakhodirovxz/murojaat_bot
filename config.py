"""`.env` faylidan sozlamalarni o'qish."""

import os
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
# --- Ma'lumotlar bazasi ---
# DB_TYPE=sqlite  -> DB_PATH dagi fayl (lokal ish va testlar uchun)
# DB_TYPE=mysql   -> quyidagi MYSQL_* sozlamalari (serverda)
DB_TYPE = os.getenv("DB_TYPE", "sqlite").strip().lower()

MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1").strip() or "127.0.0.1"
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306").strip() or "3306"
MYSQL_USER = os.getenv("MYSQL_USER", "").strip()
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "").strip()


def _database_target() -> str:
    """Baza manzili: SQLite fayli yoki mysql:// havolasi."""
    if DB_TYPE == "mysql":
        user = quote(MYSQL_USER, safe="")
        password = quote(MYSQL_PASSWORD, safe="")
        return f"mysql://{user}:{password}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
    return os.getenv("DB_PATH", "qabul.db").strip() or "qabul.db"


DB_PATH = _database_target()

# Ixtiyoriy: TLS sertifikatlari to'plami (tashkilot proksisi ortida kerak bo'ladi).
CA_BUNDLE = os.getenv("CA_BUNDLE", "").strip()

# Yozishmadagi fayllar nusxasi saqlanadigan papka.
FILES_DIR = os.getenv("FILES_DIR", "files").strip() or "files"

# Adminlar ishlaydigan guruh chat ID si. Guruhda /id buyrug'i uni ko'rsatadi.
_group = os.getenv("GROUP_ID", "").strip()
GROUP_ID = int(_group) if _group.lstrip("-").isdigit() else 0


def _parse_users(raw: str) -> set:
    """`@aziz:example.uz, @nodir:example.uz` -> to'plam."""
    return {
        chunk.strip()
        for chunk in raw.replace(";", ",").split(",")
        if chunk.strip().startswith("@")
    }


# --- Matrix (Element) ---
# Bo'sh qoldirilsa Matrix umuman ishga tushmaydi, bot faqat Telegram bilan ishlaydi.
MATRIX_HOMESERVER = os.getenv("MATRIX_HOMESERVER", "").strip().rstrip("/")
MATRIX_USER = os.getenv("MATRIX_USER", "").strip()
MATRIX_PASSWORD = os.getenv("MATRIX_PASSWORD", "").strip()
MATRIX_TOKEN = os.getenv("MATRIX_TOKEN", "").strip()
MATRIX_DEVICE = os.getenv("MATRIX_DEVICE", "qabul-bot").strip() or "qabul-bot"
MATRIX_ROOM_ID = os.getenv("MATRIX_ROOM_ID", "").strip()
# Bo'sh bo'lsa xonaning har bir a'zosi javob bera oladi.
MATRIX_ADMINS = _parse_users(os.getenv("MATRIX_ADMINS", ""))
MATRIX_STORE = os.getenv("MATRIX_STORE", "matrix_store").strip() or "matrix_store"


def matrix_enabled() -> bool:
    return bool(MATRIX_HOMESERVER and MATRIX_USER and (MATRIX_PASSWORD or MATRIX_TOKEN))


def matrix_can_answer(user_id: str) -> bool:
    """Xonada javob berish huquqi. Ro'yxat bo'sh bo'lsa — barcha a'zolar."""
    return not MATRIX_ADMINS or user_id in MATRIX_ADMINS


def _parse_admin_ids(raw: str) -> set:
    ids = set()
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if chunk.lstrip("-").isdigit():
            ids.add(int(chunk))
    return ids


ADMIN_IDS = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS
