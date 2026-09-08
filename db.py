"""Ma'lumotlar bazasi: SQLite yoki MySQL.

Barcha funksiyalar birinchi argument sifatida **manzil** oladi:

* `qabul.db` yoki `/www/wwwroot/qabul_bot/qabul.db` — SQLite fayli;
* `mysql://user:parol@host:port/baza` — MySQL.

Shu tufayli chaqiruv joylari o'zgarmaydi: serverda MySQL, lokal ishlab
chiqishda va testlarda SQLite ishlatiladi.
"""

import sqlite3
from datetime import datetime
from typing import Optional
from urllib.parse import unquote, urlparse

STATUS_NEW = "new"
STATUS_IN_PROGRESS = "in_progress"
STATUS_CLOSED = "closed"

STATUS_LABELS = {
    STATUS_NEW: "Yangi",
    STATUS_IN_PROGRESS: "Javob berilmoqda",
    STATUS_CLOSED: "Yopilgan",
}

DIRECTION_ADMIN = "admin"
DIRECTION_CITIZEN = "citizen"

MYSQL_PREFIX = "mysql://"

SCHEMA_SQLITE = (
    """
    CREATE TABLE IF NOT EXISTS applications (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        fio         TEXT NOT NULL,
        passport    TEXT NOT NULL,
        jshshir     TEXT NOT NULL,
        birth_date  TEXT NOT NULL,
        address     TEXT NOT NULL,
        phone       TEXT NOT NULL,
        phone_extra TEXT NOT NULL DEFAULT '',
        message     TEXT NOT NULL,
        tg_user_id  INTEGER,
        tg_username TEXT,
        created_at  TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_applications_created_at ON applications (created_at)",
    """
    CREATE TABLE IF NOT EXISTS messages (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id INTEGER NOT NULL,
        direction      TEXT NOT NULL,
        admin_id       INTEGER,
        text           TEXT NOT NULL DEFAULT '',
        file_id        TEXT NOT NULL DEFAULT '',
        file_path      TEXT NOT NULL DEFAULT '',
        file_name      TEXT NOT NULL DEFAULT '',
        file_type      TEXT NOT NULL DEFAULT '',
        created_at     TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_messages_application ON messages (application_id, id)",
    """
    CREATE TABLE IF NOT EXISTS group_links (
        chat_id        INTEGER NOT NULL,
        message_id     INTEGER NOT NULL,
        application_id INTEGER NOT NULL,
        PRIMARY KEY (chat_id, message_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matrix_links (
        room_id        TEXT NOT NULL,
        event_id       TEXT NOT NULL,
        application_id INTEGER NOT NULL,
        PRIMARY KEY (room_id, event_id)
    )
    """,
)

# MySQL'da TEXT ustunga DEFAULT berib bo'lmaydi va kalit uzunligi cheklangan,
# shuning uchun aniq turlar ishlatiladi.
SCHEMA_MYSQL = (
    """
    CREATE TABLE IF NOT EXISTS applications (
        id                  INT AUTO_INCREMENT PRIMARY KEY,
        fio                 VARCHAR(200) NOT NULL,
        passport            VARCHAR(32) NOT NULL,
        jshshir             VARCHAR(32) NOT NULL,
        birth_date          VARCHAR(16) NOT NULL,
        address             VARCHAR(500) NOT NULL,
        phone               VARCHAR(32) NOT NULL,
        phone_extra         VARCHAR(32) NOT NULL DEFAULT '',
        message             TEXT NOT NULL,
        tg_user_id          BIGINT,
        tg_username         VARCHAR(64),
        created_at          VARCHAR(32) NOT NULL,
        status              VARCHAR(32) NOT NULL DEFAULT 'new',
        assigned_admin      BIGINT,
        assigned_admin_name VARCHAR(200),
        closed_at           VARCHAR(32),
        group_chat_id       BIGINT,
        group_message_id    BIGINT,
        matrix_room_id      VARCHAR(255),
        matrix_event_id     VARCHAR(255),
        KEY idx_applications_created_at (created_at),
        KEY idx_applications_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
        id             INT AUTO_INCREMENT PRIMARY KEY,
        application_id INT NOT NULL,
        direction      VARCHAR(16) NOT NULL,
        admin_id       BIGINT,
        text           TEXT,
        file_id        VARCHAR(255) NOT NULL DEFAULT '',
        file_path      VARCHAR(500) NOT NULL DEFAULT '',
        file_name      VARCHAR(255) NOT NULL DEFAULT '',
        file_type      VARCHAR(32) NOT NULL DEFAULT '',
        created_at     VARCHAR(32) NOT NULL,
        KEY idx_messages_application (application_id, id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS group_links (
        chat_id        BIGINT NOT NULL,
        message_id     BIGINT NOT NULL,
        application_id INT NOT NULL,
        PRIMARY KEY (chat_id, message_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS matrix_links (
        room_id        VARCHAR(255) NOT NULL,
        event_id       VARCHAR(255) NOT NULL,
        application_id INT NOT NULL,
        PRIMARY KEY (room_id, event_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
)

# Keyin qo'shilgan ustunlar — eski bazalar ham yangilanishi uchun.
# (nomi, MySQL uchun ta'rif, SQLite uchun ta'rif)
ADDED_COLUMNS = (
    ("status", "status VARCHAR(32) NOT NULL DEFAULT 'new'", "status TEXT NOT NULL DEFAULT 'new'"),
    ("assigned_admin", "assigned_admin BIGINT", "assigned_admin INTEGER"),
    ("assigned_admin_name", "assigned_admin_name VARCHAR(200)", "assigned_admin_name TEXT"),
    ("closed_at", "closed_at VARCHAR(32)", "closed_at TEXT"),
    ("group_chat_id", "group_chat_id BIGINT", "group_chat_id INTEGER"),
    ("group_message_id", "group_message_id BIGINT", "group_message_id INTEGER"),
    ("matrix_room_id", "matrix_room_id VARCHAR(255)", "matrix_room_id TEXT"),
    ("matrix_event_id", "matrix_event_id VARCHAR(255)", "matrix_event_id TEXT"),
)

FIELD_ORDER = (
    "fio",
    "passport",
    "jshshir",
    "birth_date",
    "address",
    "phone",
    "phone_extra",
    "message",
    "tg_user_id",
    "tg_username",
)

_LAST_ANSWER = """
    (SELECT m.text FROM messages m
      WHERE m.application_id = a.id AND m.direction = 'admin' AND m.text <> ''
      ORDER BY m.id DESC LIMIT 1) AS last_answer
"""


# --- Ulanish --------------------------------------------------------------


def is_mysql(target: str) -> bool:
    return str(target).startswith(MYSQL_PREFIX)


def parse_mysql_url(target: str) -> dict:
    """`mysql://user:parol@host:3306/baza` → pymysql parametrlari."""
    parsed = urlparse(target)
    return {
        "host": parsed.hostname or "127.0.0.1",
        "port": parsed.port or 3306,
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "database": (parsed.path or "").lstrip("/"),
    }


class _Connection:
    """SQLite va MySQL uchun bir xil kichik interfeys."""

    def __init__(self, target: str):
        self.mysql = is_mysql(target)
        if self.mysql:
            import pymysql

            self.raw = pymysql.connect(
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False,
                connect_timeout=10,
                **parse_mysql_url(target),
            )
        else:
            self.raw = sqlite3.connect(target)
            self.raw.row_factory = sqlite3.Row

    def execute(self, query: str, params=()):
        if self.mysql:
            cursor = self.raw.cursor()
            cursor.execute(query.replace("?", "%s"), tuple(params))
            return cursor
        return self.raw.execute(query, tuple(params))

    def script(self, statements) -> None:
        for statement in statements:
            self.execute(statement)

    def columns(self, table: str) -> set:
        if self.mysql:
            return {row["Field"] for row in self.execute(f"SHOW COLUMNS FROM {table}").fetchall()}
        return {row["name"] for row in self.execute(f"PRAGMA table_info({table})").fetchall()}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.raw.commit()
        else:
            self.raw.rollback()
        self.raw.close()
        return False


def _connect(target: str) -> _Connection:
    return _Connection(target)


def _rows(cursor) -> list:
    return [dict(row) for row in cursor.fetchall()]


def _one(cursor, column: str):
    row = cursor.fetchone()
    return dict(row)[column] if row else None


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def init_db(target: str) -> None:
    with _connect(target) as conn:
        conn.script(SCHEMA_MYSQL if conn.mysql else SCHEMA_SQLITE)
        existing = conn.columns("applications")
        for name, mysql_ddl, sqlite_ddl in ADDED_COLUMNS:
            if name not in existing:
                conn.execute(
                    f"ALTER TABLE applications ADD COLUMN "
                    f"{mysql_ddl if conn.mysql else sqlite_ddl}"
                )


# --- Arizalar -------------------------------------------------------------


def add_application(target: str, data: dict) -> int:
    """Arizani yozadi va unga berilgan tartib raqamini qaytaradi."""
    values = [data.get(name) for name in FIELD_ORDER]
    values.append(_now())
    columns = ", ".join(FIELD_ORDER + ("created_at",))
    placeholders = ", ".join("?" * (len(FIELD_ORDER) + 1))
    with _connect(target) as conn:
        cursor = conn.execute(
            f"INSERT INTO applications ({columns}) VALUES ({placeholders})", values
        )
        return cursor.lastrowid


def get_application(target: str, application_id: int) -> Optional[dict]:
    with _connect(target) as conn:
        rows = _rows(
            conn.execute(
                f"SELECT a.*, {_LAST_ANSWER} FROM applications a WHERE a.id = ?",
                (application_id,),
            )
        )
    return rows[0] if rows else None


def fetch_applications(
    target: str, date_from: Optional[str] = None, date_to: Optional[str] = None
) -> list:
    """Arizalarni qaytaradi. Sanalar ISO (`YYYY-MM-DD`), chegaralar kiritiladi."""
    query = f"SELECT a.*, {_LAST_ANSWER} FROM applications a"
    conditions = []
    params = []
    # SUBSTR ikkala bazada bir xil ishlaydi (created_at ISO matn ko'rinishida saqlanadi).
    if date_from:
        conditions.append("SUBSTR(a.created_at, 1, 10) >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("SUBSTR(a.created_at, 1, 10) <= ?")
        params.append(date_to)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY a.id"
    with _connect(target) as conn:
        return _rows(conn.execute(query, params))


def open_applications(target: str, limit: int = 10, offset: int = 0) -> list:
    """Yopilmagan arizalar — eng eskisi birinchi (navbat tartibida)."""
    with _connect(target) as conn:
        return _rows(
            conn.execute(
                "SELECT * FROM applications WHERE status <> ? ORDER BY id LIMIT ? OFFSET ?",
                (STATUS_CLOSED, limit, offset),
            )
        )


def count_open_applications(target: str) -> int:
    with _connect(target) as conn:
        return _one(
            conn.execute(
                "SELECT COUNT(*) AS total FROM applications WHERE status <> ?", (STATUS_CLOSED,)
            ),
            "total",
        )


def search_applications(target: str, query: str, limit: int = 20) -> list:
    """F.I.Sh., telefon, JSHSHIR, pasport yoki ariza raqami bo'yicha qidiradi."""
    text = (query or "").strip()
    if not text:
        return []
    like = f"%{text.lower()}%"
    digits = "".join(ch for ch in text if ch.isdigit())
    application_id = int(digits) if digits and digits == text.lstrip("№# ").strip() else -1
    with _connect(target) as conn:
        return _rows(
            conn.execute(
                """
                SELECT * FROM applications
                 WHERE lower(fio) LIKE ?
                    OR lower(passport) LIKE ?
                    OR jshshir LIKE ?
                    OR phone LIKE ?
                    OR phone_extra LIKE ?
                    OR id = ?
                 ORDER BY id DESC LIMIT ?
                """,
                (like, like, like, like, like, application_id, limit),
            )
        )


def set_status(
    target: str,
    application_id: int,
    status: str,
    assigned_admin: Optional[int] = None,
    assigned_admin_name: Optional[str] = None,
) -> None:
    assignments = ["status = ?", "closed_at = ?"]
    params = [status, _now() if status == STATUS_CLOSED else None]
    if assigned_admin is not None:
        assignments.append("assigned_admin = ?")
        params.append(assigned_admin)
    if assigned_admin_name is not None:
        assignments.append("assigned_admin_name = ?")
        params.append(assigned_admin_name)
    params.append(application_id)
    with _connect(target) as conn:
        conn.execute(f"UPDATE applications SET {', '.join(assignments)} WHERE id = ?", params)


def application_for_user(target: str, tg_user_id: int) -> Optional[dict]:
    """Fuqaroning yozishmasi davom etayotgan arizasi — bo'lmasa oxirgisi."""
    with _connect(target) as conn:
        rows = _rows(
            conn.execute(
                "SELECT * FROM applications WHERE tg_user_id = ? AND status <> ? "
                "ORDER BY id DESC LIMIT 1",
                (tg_user_id, STATUS_CLOSED),
            )
        )
        if not rows:
            rows = _rows(
                conn.execute(
                    "SELECT * FROM applications WHERE tg_user_id = ? ORDER BY id DESC LIMIT 1",
                    (tg_user_id,),
                )
            )
    return rows[0] if rows else None


def count_applications(target: str) -> int:
    with _connect(target) as conn:
        return _one(conn.execute("SELECT COUNT(*) AS total FROM applications"), "total")


def last_created_at(target: str) -> Optional[str]:
    with _connect(target) as conn:
        return _one(
            conn.execute("SELECT created_at FROM applications ORDER BY id DESC LIMIT 1"),
            "created_at",
        )


# --- Guruh va Matrix bog'lanishlari ---------------------------------------


def set_group_message(target: str, application_id: int, chat_id: int, message_id: int) -> None:
    """Guruhdagi asosiy kartochka xabarini arizaga bog'laydi."""
    with _connect(target) as conn:
        conn.execute(
            "UPDATE applications SET group_chat_id = ?, group_message_id = ? WHERE id = ?",
            (chat_id, message_id, application_id),
        )
    link_group_message(target, chat_id, message_id, application_id)


def link_group_message(target: str, chat_id: int, message_id: int, application_id: int) -> None:
    """Guruhdagi istalgan xabarni arizaga bog'laydi — unga reply qilib javob berish uchun."""
    with _connect(target) as conn:
        conn.execute(
            "REPLACE INTO group_links (chat_id, message_id, application_id) VALUES (?, ?, ?)",
            (chat_id, message_id, application_id),
        )


def application_by_group_message(target: str, chat_id: int, message_id: int) -> Optional[int]:
    with _connect(target) as conn:
        return _one(
            conn.execute(
                "SELECT application_id FROM group_links WHERE chat_id = ? AND message_id = ?",
                (chat_id, message_id),
            ),
            "application_id",
        )


def set_matrix_message(target: str, application_id: int, room_id: str, event_id: str) -> None:
    """Matrix xonasidagi asosiy kartochkani arizaga bog'laydi."""
    with _connect(target) as conn:
        conn.execute(
            "UPDATE applications SET matrix_room_id = ?, matrix_event_id = ? WHERE id = ?",
            (room_id, event_id, application_id),
        )
    link_matrix_event(target, room_id, event_id, application_id)


def link_matrix_event(target: str, room_id: str, event_id: str, application_id: int) -> None:
    """Xonadagi istalgan xabarni arizaga bog'laydi — reply orqali javob berish uchun."""
    with _connect(target) as conn:
        conn.execute(
            "REPLACE INTO matrix_links (room_id, event_id, application_id) VALUES (?, ?, ?)",
            (room_id, event_id, application_id),
        )


def application_by_matrix_event(target: str, room_id: str, event_id: str) -> Optional[int]:
    with _connect(target) as conn:
        return _one(
            conn.execute(
                "SELECT application_id FROM matrix_links WHERE room_id = ? AND event_id = ?",
                (room_id, event_id),
            ),
            "application_id",
        )


# --- Yozishma -------------------------------------------------------------


def add_message(target: str, application_id: int, direction: str, **data) -> int:
    values = (
        application_id,
        direction,
        data.get("admin_id"),
        data.get("text", "") or "",
        data.get("file_id", "") or "",
        data.get("file_path", "") or "",
        data.get("file_name", "") or "",
        data.get("file_type", "") or "",
        _now(),
    )
    with _connect(target) as conn:
        cursor = conn.execute(
            "INSERT INTO messages (application_id, direction, admin_id, text, file_id,"
            " file_path, file_name, file_type, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            values,
        )
        return cursor.lastrowid


def fetch_messages(target: str, application_id: int) -> list:
    with _connect(target) as conn:
        return _rows(
            conn.execute(
                "SELECT * FROM messages WHERE application_id = ? ORDER BY id",
                (application_id,),
            )
        )


def count_messages(target: str, application_id: int) -> int:
    with _connect(target) as conn:
        return _one(
            conn.execute(
                "SELECT COUNT(*) AS total FROM messages WHERE application_id = ?",
                (application_id,),
            ),
            "total",
        )


def describe(target: str) -> str:
    """Jurnal uchun xavfsiz ko'rinish — parol hech qachon chiqmaydi."""
    if not is_mysql(target):
        return str(target)
    parts = parse_mysql_url(target)
    return f"mysql://{parts['user']}@{parts['host']}:{parts['port']}/{parts['database']}"
