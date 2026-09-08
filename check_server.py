"""Serverni tekshirish: bot ishlashi uchun kerak bo'lgan hamma narsa joyidami?

Botni yangi kompyuterga yoki serverga ko'chirganda BIRINCHI shuni ishga tushiring:

    python check_server.py

Har bir band alohida tekshiriladi va nima qilish kerakligi aytiladi.
"""

import asyncio
import os
import socket
import ssl
import sys

OK = "[OK]   "
FAIL = "[XATO] "
WARN = "[!]    "

problems = []


def report(good: bool, title: str, detail: str = "", advice: str = "") -> bool:
    print(f"{OK if good else FAIL}{title}")
    if detail:
        print(f"        {detail}")
    if not good:
        if advice:
            print(f"        → {advice}")
        problems.append(title)
    return good


def warn(title: str, detail: str = "") -> None:
    print(f"{WARN}{title}")
    if detail:
        print(f"        {detail}")


def check_tls(host: str, port: int, ca_file: str = ""):
    """TLS ulanish va sertifikatni kim imzolaganini qaytaradi."""
    context = ssl.create_default_context(cafile=ca_file) if ca_file else ssl.create_default_context()
    with socket.create_connection((host, port), timeout=15) as raw:
        with context.wrap_socket(raw, server_hostname=host) as secure:
            issuer = dict(item[0] for item in secure.getpeercert()["issuer"])
            return issuer.get("organizationName") or issuer.get("commonName") or "?"


def check_tls_trust(host: str, port: int, ca_file: str, title: str) -> None:
    """Avval standart sertifikatlar bilan sinaydi — bot ham aynan shulardan foydalanadi.

    Ular yetsa, tarmoqda aralashuv yo'q. Yetmasa va CA_BUNDLE yordam bersa —
    tarmoqda TLS'ni qayta imzolovchi proksi bor, lekin bot ishlayveradi.
    """
    try:
        import certifi

        default_bundle = certifi.where()
    except ImportError:
        default_bundle = ""

    try:
        issuer = check_tls(host, port, default_bundle)
        report(True, f"{title} bilan TLS aloqa bor", f"sertifikatni imzolagan: {issuer}")
        return
    except ssl.SSLCertVerificationError:
        pass
    except Exception as error:  # noqa: BLE001
        report(
            False,
            f"{title} ga ulanib bo'lmadi",
            str(error),
            "Tarmoq yoki bloklanishni tekshiring",
        )
        return

    if not ca_file:
        report(
            False,
            f"{title}: sertifikat tekshiruvdan o'tmadi",
            "Standart sertifikatlar ro'yxati yetmadi.",
            "Tarmoqda TLS'ni tekshiruvchi proksi bo'lsa, `.env` dagi CA_BUNDLE ga "
            "tashkilot sertifikatlari .pem faylini ko'rsating",
        )
        return

    try:
        issuer = check_tls(host, port, ca_file)
        report(True, f"{title} bilan TLS aloqa bor (CA_BUNDLE orqali)", f"imzolagan: {issuer}")
        warn(
            "Tarmoqda TLS'ni tekshiruvchi proksi bor",
            f"Standart sertifikatlar yetmadi, CA_BUNDLE yordam berdi: {ca_file}",
        )
    except Exception as error:  # noqa: BLE001
        report(
            False,
            f"{title}: sertifikat tekshiruvdan o'tmadi",
            str(error),
            "CA_BUNDLE dagi fayl to'g'ri ekanini tekshiring",
        )


async def main() -> int:
    print("=" * 68)
    print("Qabul boti — server tekshiruvi")
    print("=" * 68)

    # 1. Sozlamalar
    if not os.path.exists(".env"):
        report(
            False,
            ".env fayli topilmadi",
            advice="cp .env.example .env  — so'ng uni to'ldiring",
        )
        return 1

    try:
        import config
    except ModuleNotFoundError as error:
        report(
            False,
            f"Kutubxona o'rnatilmagan: {error.name}",
            "Virtual muhit yaratilmagan yoki bog'liqliklar o'rnatilmagan.",
            "bash install.sh   (yoki: python3 -m venv .venv && "
            ".venv/bin/pip install -r requirements.txt)\n"
            "        So'ng shu skriptni .venv/bin/python check_server.py bilan ishga tushiring",
        )
        return 1
    except Exception as error:  # noqa: BLE001
        report(False, "Sozlamalarni o'qib bo'lmadi (.env)", str(error))
        return 1

    report(
        bool(config.BOT_TOKEN),
        "BOT_TOKEN ko'rsatilgan",
        advice="@BotFather bergan tokenni `.env` ga yozing",
    )
    report(
        bool(config.ADMIN_IDS),
        f"ADMIN_IDS: {sorted(config.ADMIN_IDS) or 'bo`sh'}",
        advice="Botga /myid yozib ID ingizni oling va `.env` ga qo'ying",
    )
    if config.GROUP_ID:
        print(f"{OK}Telegram guruhi: {config.GROUP_ID}")
    else:
        warn("Telegram guruhi sozlanmagan", "GROUP_ID bo'sh — kartochkalar faqat shaxsiy chatlarga boradi")

    # 2. Telegram bilan aloqa — eng muhim band
    print("-" * 68)
    ca_file = ""
    try:
        import net

        ca_file = net.resolve_ca_bundle(config.CA_BUNDLE) or ""
    except Exception:  # noqa: BLE001
        pass

    check_tls_trust("api.telegram.org", 443, ca_file, "api.telegram.org")

    if config.BOT_TOKEN:
        try:
            from aiogram import Bot

            import net

            bot = Bot(config.BOT_TOKEN, session=net.build_session(config.CA_BUNDLE))
            try:
                me = await bot.get_me()
                report(True, "Telegram boti javob berdi", f"@{me.username} ({me.full_name})")
            finally:
                await bot.session.close()
        except Exception as error:  # noqa: BLE001
            report(False, "Telegram API javob bermadi", str(error), "Token yoki tarmoqni tekshiring")

    # 3. Matrix
    print("-" * 68)
    if not config.matrix_enabled():
        warn("Matrix sozlanmagan", "MATRIX_HOMESERVER / MATRIX_USER / parol yoki token bo'sh")
    else:
        host = config.MATRIX_HOMESERVER.split("://", 1)[-1].split("/")[0]
        hostname, _, port = host.partition(":")
        check_tls_trust(hostname, int(port or 443), ca_file, hostname)

        try:
            import matrix_bot

            bridge = matrix_bot.MatrixBridge(
                homeserver=config.MATRIX_HOMESERVER,
                user=config.MATRIX_USER,
                password=config.MATRIX_PASSWORD,
                token=config.MATRIX_TOKEN,
                device=config.MATRIX_DEVICE,
                room_id=config.MATRIX_ROOM_ID,
                store_dir=config.MATRIX_STORE,
            )
            if await bridge.start():
                report(True, "Matrix hisobiga kirildi", bridge.user)
                if config.MATRIX_ROOM_ID:
                    print(f"{OK}Xona: {config.MATRIX_ROOM_ID}")
                else:
                    warn("MATRIX_ROOM_ID bo'sh", "Botni xonaga qo'shib, xonada !id yozing")
            else:
                report(False, "Matrix hisobiga kirib bo'lmadi", advice="Login va parolni tekshiring")
            await bridge.stop()
        except Exception as error:  # noqa: BLE001
            report(False, "Matrix ulanishida xato", str(error))

    # 4. Baza
    print("-" * 68)
    import db

    print(f"Baza: {db.describe(config.DB_PATH)}")
    try:
        db.init_db(config.DB_PATH)
        report(
            True,
            "Bazaga ulanildi va jadvallar joyida",
            f"{db.count_applications(config.DB_PATH)} ta ariza",
        )
    except Exception as error:  # noqa: BLE001
        report(
            False,
            "Bazaga ulanib bo'lmadi",
            str(error),
            "MySQL uchun MYSQL_* sozlamalarini tekshiring, so'ng `python check_mysql.py`",
        )

    # 5. Fayllar
    print("-" * 68)
    targets = [(config.FILES_DIR, "Fayllar papkasi")]
    if not db.is_mysql(config.DB_PATH):
        targets.insert(0, (config.DB_PATH, "Baza fayli"))
    for path, title in targets:
        folder = os.path.dirname(os.path.abspath(path)) if title.startswith("Baza") else path
        try:
            os.makedirs(folder, exist_ok=True)
            probe = os.path.join(folder, ".yozish_testi")
            with open(probe, "w", encoding="utf-8") as handle:
                handle.write("test")
            os.remove(probe)
            report(True, f"{title} yoziladi", folder)
        except Exception as error:  # noqa: BLE001
            report(False, f"{title}ga yozib bo'lmadi", str(error), "Papka huquqlarini tekshiring")

    print("=" * 68)
    if problems:
        print(f"{len(problems)} ta muammo topildi:")
        for item in problems:
            print(f"  - {item}")
        print("\nUlar hal qilinmaguncha bot to'liq ishlamaydi.")
        return 1
    print("Hammasi joyida — botni ishga tushirsa bo'ladi: python bot.py")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
