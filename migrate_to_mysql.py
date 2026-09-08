"""SQLite bazasidagi arizalarni MySQL'ga ko'chirish.

Serverda MySQL'ga o'tayotganda, mavjud arizalar yo'qolmasligi uchun:

    python migrate_to_mysql.py qabul.db

Manzil `.env` dagi MYSQL_* sozlamalaridan olinadi. Ariza raqamlari (№)
o'zgarmaydi — fuqarolarga aytilgan raqamlar o'z kuchida qoladi.
"""

import sqlite3
import sys

import db

TABLES = (
    ("applications", "id"),
    ("messages", "id"),
    ("group_links", None),
    ("matrix_links", None),
)


def read_table(path: str, table: str) -> list:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]
    except sqlite3.OperationalError:
        return []  # jadval eski bazada bo'lmasligi mumkin
    finally:
        conn.close()


def main() -> int:
    source = sys.argv[1] if len(sys.argv) > 1 else "qabul.db"
    force = "--force" in sys.argv

    import config

    target = config.DB_PATH
    if not db.is_mysql(target):
        print("Maqsad MySQL emas. `.env` da DB_TYPE=mysql va MYSQL_* ni to'ldiring.")
        return 1

    print(f"Manba : {source}")
    print(f"Maqsad: {db.describe(target)}")

    db.init_db(target)
    existing = db.count_applications(target)
    if existing and not force:
        print(f"\nMaqsad bazada allaqachon {existing} ta ariza bor.")
        print("Ustiga yozilmasin deb to'xtatildi. Baribir davom etish: --force")
        return 1

    total = 0
    for table, _ in TABLES:
        rows = read_table(source, table)
        if not rows:
            print(f"  {table:<14} — bo'sh")
            continue
        columns = list(rows[0].keys())
        placeholders = ", ".join("?" * len(columns))
        query = (
            f"REPLACE INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
        )
        with db._connect(target) as conn:
            for row in rows:
                conn.execute(query, [row[name] for name in columns])
        print(f"  {table:<14} — {len(rows)} ta yozuv ko'chirildi")
        total += len(rows)

    print(f"\nJami {total} ta yozuv ko'chirildi.")
    print(f"Tekshiruv: MySQL'da {db.count_applications(target)} ta ariza bor.")
    print("\nEndi `.env` da DB_TYPE=mysql turganiga ishonch hosil qilib, botni qayta ishga tushiring.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
