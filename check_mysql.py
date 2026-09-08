"""MySQL bazasini boshdan-oyoq tekshirish.

Serverda MySQL'ga o'tgandan keyin BIRINCHI shuni ishga tushiring:

    python check_mysql.py

Skript jadvallarni yaratadi, test arizasi bilan barcha amallarni bajarib
ko'radi va **o'zi yaratgan qatorlarni o'chirib tashlaydi** — bazada iz
qolmaydi. Parol hech qayerda chop etilmaydi.
"""

import sys
from datetime import date

try:
    import db
except ModuleNotFoundError as error:  # pragma: no cover
    print(f"[XATO] Kutubxona o'rnatilmagan: {error.name}")
    print("        bash install.sh   (yoki: python3 -m venv .venv && "
          ".venv/bin/pip install -r requirements.txt)")
    print("        So'ng: .venv/bin/python check_mysql.py")
    raise SystemExit(1)

SAMPLE = {
    "fio": "Tekshiruv Foydalanuvchi Testovich",
    "passport": "ZZ0000000",
    "jshshir": "00000000000000",
    "birth_date": "01.01.1990",
    "address": "Tekshiruv manzili, 1-uy",
    "phone": "+998900000000",
    "phone_extra": "+998910000000",
    "message": "Bu avtomatik tekshiruv arizasi. O'zi o'chib ketadi.",
    "tg_user_id": -1,
    "tg_username": "selftest",
}

passed = 0
failed = []


def check(title: str, condition: bool, detail: str = "") -> None:
    global passed
    if condition:
        passed += 1
        print(f"[OK]   {title}")
    else:
        failed.append(title)
        print(f"[XATO] {title}")
    if detail:
        print(f"        {detail}")


def cleanup(target: str, application_id: int) -> None:
    with db._connect(target) as conn:
        conn.execute("DELETE FROM messages WHERE application_id = ?", (application_id,))
        conn.execute("DELETE FROM group_links WHERE application_id = ?", (application_id,))
        conn.execute("DELETE FROM matrix_links WHERE application_id = ?", (application_id,))
        conn.execute("DELETE FROM applications WHERE id = ?", (application_id,))


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else None
    if target is None:
        try:
            import config
        except ModuleNotFoundError as error:
            print(f"[XATO] Kutubxona o'rnatilmagan: {error.name} — avval: bash install.sh")
            return 1

        target = config.DB_PATH

    print("=" * 68)
    print("MySQL tekshiruvi")
    print("=" * 68)
    print(f"Baza: {db.describe(target)}")

    if not db.is_mysql(target):
        print("\n[!] Bu SQLite manzili. MySQL'ni tekshirish uchun `.env` da")
        print("    DB_TYPE=mysql va MYSQL_* sozlamalarini to'ldiring.")
        return 1

    try:
        db.init_db(target)
        check("Jadvallar yaratildi / mavjud", True)
    except Exception as error:  # noqa: BLE001
        check("Jadvallar yaratildi", False, str(error))
        print("\nUlanib bo'lmadi — host, port, foydalanuvchi, parol va baza nomini tekshiring.")
        return 1

    application_id = None
    try:
        application_id = db.add_application(target, SAMPLE)
        check("Ariza yozildi", bool(application_id), f"№ {application_id}")

        stored = db.get_application(target, application_id)
        check("Ariza o'qildi", stored is not None)
        check(
            "Matn o'zgarmagan (utf8mb4)",
            stored and stored["message"] == SAMPLE["message"] and stored["fio"] == SAMPLE["fio"],
        )
        check("Boshlang'ich holat 'Yangi'", stored and stored["status"] == db.STATUS_NEW)

        db.set_status(
            target,
            application_id,
            db.STATUS_IN_PROGRESS,
            assigned_admin=999,
            assigned_admin_name="Tekshiruvchi",
        )
        stored = db.get_application(target, application_id)
        check(
            "Holat va mas'ul admin yozildi",
            stored["status"] == db.STATUS_IN_PROGRESS and stored["assigned_admin_name"] == "Tekshiruvchi",
        )

        db.add_message(target, application_id, db.DIRECTION_CITIZEN, text="Savol")
        db.add_message(
            target,
            application_id,
            db.DIRECTION_ADMIN,
            admin_id=999,
            text="Rasmiy javob",
            file_id="BQACtest",
            file_name="javob.pdf",
            file_type="document",
        )
        history = db.fetch_messages(target, application_id)
        check("Yozishma yozildi va o'qildi", len(history) == 2, f"{len(history)} ta xabar")
        check("Fayl ma'lumoti saqlandi", history[-1]["file_name"] == "javob.pdf")
        check("Xabarlar soni to'g'ri", db.count_messages(target, application_id) == 2)

        row = db.get_application(target, application_id)
        check("Oxirgi javob eksport uchun topildi", row["last_answer"] == "Rasmiy javob")

        db.set_group_message(target, application_id, -100999, 555)
        check(
            "Telegram guruh kartochkasi bog'landi",
            db.application_by_group_message(target, -100999, 555) == application_id,
        )

        db.set_matrix_message(target, application_id, "!selftest:example.uz", "$abc123")
        check(
            "Matrix kartochkasi bog'landi",
            db.application_by_matrix_event(target, "!selftest:example.uz", "$abc123") == application_id,
        )

        db.link_group_message(target, -100999, 556, application_id)
        db.link_group_message(target, -100999, 556, application_id)
        check("Takroriy bog'lash xato bermaydi", True)

        found = db.search_applications(target, "Tekshiruv")
        check("Qidiruv ishlaydi", any(item["id"] == application_id for item in found))
        found = db.search_applications(target, "900000000")
        check("Telefon bo'yicha qidiruv", any(item["id"] == application_id for item in found))

        today = date.today().isoformat()
        rows = db.fetch_applications(target, today, today)
        check("Sana bo'yicha filtr", any(item["id"] == application_id for item in rows))
        rows = db.fetch_applications(target, "1990-01-01", "1990-12-31")
        check("Eski davrda topilmadi", not any(item["id"] == application_id for item in rows))

        check("Ochiq arizalar sanaladi", db.count_open_applications(target) >= 1)
        db.set_status(target, application_id, db.STATUS_CLOSED)
        stored = db.get_application(target, application_id)
        check("Yopish va vaqti yozildi", stored["status"] == db.STATUS_CLOSED and stored["closed_at"])

        import export

        workbook = export.build_workbook(db.fetch_applications(target))
        check("Excel jadvali yasaldi", workbook.active.max_row >= 3)

    except Exception as error:  # noqa: BLE001
        check("Tekshiruv oxirigacha bordi", False, f"{type(error).__name__}: {error}")
    finally:
        if application_id:
            try:
                cleanup(target, application_id)
                print(f"[OK]   Test ma'lumotlari o'chirildi (№ {application_id})")
            except Exception as error:  # noqa: BLE001
                print(f"[XATO] Test ma'lumotlarini o'chirib bo'lmadi: {error}")
                print(f"        Qo'lda o'chiring: DELETE FROM applications WHERE id = {application_id};")

    print("=" * 68)
    if failed:
        print(f"{len(failed)} ta muammo:")
        for item in failed:
            print(f"  - {item}")
        return 1
    print(f"Hammasi joyida — {passed} ta tekshiruv o'tdi. MySQL ishlashga tayyor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
