import sqlite3
from datetime import date

import pytest

import db
import keyboards as kb
import notify
import ranges
import storage

SAMPLE = {
    "fio": "Karimov Aziz Baxtiyorovich",
    "passport": "AA1234567",
    "jshshir": "31234567890123",
    "birth_date": "15.03.1990",
    "address": "Toshkent sh., Chilonzor t., 5-uy",
    "phone": "+998901234567",
    "phone_extra": "",
    "message": "Uy-joy hujjatlari masalasida murojaat.",
    "tg_user_id": 111,
    "tg_username": "aziz",
}


@pytest.fixture()
def database(tmp_path):
    path = str(tmp_path / "flow.db")
    db.init_db(path)
    return path


class TestMigration:
    def test_adds_columns_to_an_old_database(self, tmp_path):
        path = str(tmp_path / "old.db")
        # Yangi ustunlarsiz eski jadval.
        with sqlite3.connect(path) as conn:
            conn.execute(
                "CREATE TABLE applications (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " fio TEXT NOT NULL, passport TEXT NOT NULL, jshshir TEXT NOT NULL,"
                " birth_date TEXT NOT NULL, address TEXT NOT NULL, phone TEXT NOT NULL,"
                " phone_extra TEXT NOT NULL DEFAULT '', message TEXT NOT NULL,"
                " tg_user_id INTEGER, tg_username TEXT, created_at TEXT NOT NULL)"
            )
            conn.execute(
                "INSERT INTO applications (fio, passport, jshshir, birth_date, address,"
                " phone, message, created_at) VALUES ('Eski Ariza Egasi', 'AA1111111',"
                " '11111111111111', '01.01.1980', 'Manzil', '+998900000000', 'Matn',"
                " '2026-01-01T10:00:00')"
            )

        db.init_db(path)

        application = db.get_application(path, 1)
        assert application["status"] == db.STATUS_NEW
        assert application["assigned_admin"] is None
        assert application["fio"] == "Eski Ariza Egasi"  # ma'lumot saqlanib qoldi


class TestStatus:
    def test_new_application_starts_as_new(self, database):
        application_id = db.add_application(database, SAMPLE)
        assert db.get_application(database, application_id)["status"] == db.STATUS_NEW
        assert db.count_open_applications(database) == 1

    def test_assigning_admin_marks_in_progress(self, database):
        application_id = db.add_application(database, SAMPLE)
        db.set_status(database, application_id, db.STATUS_IN_PROGRESS, assigned_admin=555)
        application = db.get_application(database, application_id)
        assert application["status"] == db.STATUS_IN_PROGRESS
        assert application["assigned_admin"] == 555

    def test_closing_records_time_and_hides_from_open_list(self, database):
        application_id = db.add_application(database, SAMPLE)
        db.set_status(database, application_id, db.STATUS_CLOSED)
        application = db.get_application(database, application_id)
        assert application["status"] == db.STATUS_CLOSED
        assert application["closed_at"]
        assert db.count_open_applications(database) == 0
        assert db.open_applications(database) == []

    def test_reopening_clears_closed_at(self, database):
        application_id = db.add_application(database, SAMPLE)
        db.set_status(database, application_id, db.STATUS_CLOSED)
        db.set_status(database, application_id, db.STATUS_IN_PROGRESS)
        assert db.get_application(database, application_id)["closed_at"] is None


class TestUserLookup:
    def test_prefers_open_application(self, database):
        first = db.add_application(database, SAMPLE)
        second = db.add_application(database, SAMPLE)
        db.set_status(database, second, db.STATUS_CLOSED)
        assert db.application_for_user(database, 111)["id"] == first

    def test_falls_back_to_latest_closed(self, database):
        application_id = db.add_application(database, SAMPLE)
        db.set_status(database, application_id, db.STATUS_CLOSED)
        found = db.application_for_user(database, 111)
        assert found["id"] == application_id
        assert found["status"] == db.STATUS_CLOSED

    def test_unknown_user_has_none(self, database):
        db.add_application(database, SAMPLE)
        assert db.application_for_user(database, 999) is None


class TestSearch:
    def test_finds_by_name_phone_jshshir_and_number(self, database):
        application_id = db.add_application(database, SAMPLE)
        for query in ("karimov", "Karimov Aziz", "901234567", "31234567890123", "AA1234567"):
            found = db.search_applications(database, query)
            assert [row["id"] for row in found] == [application_id], query
        assert [row["id"] for row in db.search_applications(database, str(application_id))] == [
            application_id
        ]

    def test_empty_and_missing_queries(self, database):
        db.add_application(database, SAMPLE)
        assert db.search_applications(database, "") == []
        assert db.search_applications(database, "Petrov") == []


class TestMessages:
    def test_history_keeps_order_and_direction(self, database):
        application_id = db.add_application(database, SAMPLE)
        db.add_message(database, application_id, db.DIRECTION_ADMIN, admin_id=555, text="Salom")
        db.add_message(database, application_id, db.DIRECTION_CITIZEN, text="Rahmat")
        db.add_message(
            database,
            application_id,
            db.DIRECTION_ADMIN,
            admin_id=555,
            text="Javob xati",
            file_id="AgAC123",
            file_name="javob.pdf",
            file_type="document",
        )

        history = db.fetch_messages(database, application_id)
        assert [item["direction"] for item in history] == ["admin", "citizen", "admin"]
        assert history[2]["file_name"] == "javob.pdf"
        assert history[0]["admin_id"] == 555

    def test_last_answer_reaches_the_export_row(self, database):
        application_id = db.add_application(database, SAMPLE)
        db.add_message(database, application_id, db.DIRECTION_CITIZEN, text="Savol")
        db.add_message(database, application_id, db.DIRECTION_ADMIN, text="Birinchi javob")
        db.add_message(database, application_id, db.DIRECTION_ADMIN, text="Yakuniy javob")

        row = db.fetch_applications(database)[0]
        assert row["last_answer"] == "Yakuniy javob"

    def test_messages_of_other_applications_do_not_mix(self, database):
        first = db.add_application(database, SAMPLE)
        second = db.add_application(database, SAMPLE)
        db.add_message(database, first, db.DIRECTION_ADMIN, text="Birinchiga")
        assert len(db.fetch_messages(database, second)) == 0


class TestRanges:
    TODAY = date(2026, 9, 8)  # seshanba

    def test_today_and_yesterday(self):
        assert ranges.resolve("today", self.TODAY)[:2] == ("2026-09-08", "2026-09-08")
        assert ranges.resolve("yesterday", self.TODAY)[:2] == ("2026-09-07", "2026-09-07")

    def test_week_starts_on_monday(self):
        assert ranges.resolve("week", self.TODAY)[:2] == ("2026-09-07", "2026-09-08")

    def test_month_and_previous_month(self):
        assert ranges.resolve("month", self.TODAY)[:2] == ("2026-09-01", "2026-09-08")
        assert ranges.resolve("prev_month", self.TODAY)[:2] == ("2026-08-01", "2026-08-31")

    def test_previous_month_crosses_the_year(self):
        assert ranges.resolve("prev_month", date(2026, 1, 15))[:2] == ("2025-12-01", "2025-12-31")

    def test_all_has_no_bounds(self):
        assert ranges.resolve("all", self.TODAY)[:2] == (None, None)

    def test_unknown_key_is_rejected(self):
        with pytest.raises(ValueError):
            ranges.resolve("hafta", self.TODAY)

    def test_every_button_resolves(self):
        for key, _ in ranges.BUTTONS:
            if key == "custom":
                continue
            ranges.resolve(key, self.TODAY)

    def test_range_filter_matches_the_database(self, database):
        db.add_application(database, SAMPLE)
        today_from, today_to, _ = ranges.resolve("today")
        assert len(db.fetch_applications(database, today_from, today_to)) == 1
        past_from, past_to, _ = ranges.resolve("prev_month")
        assert db.fetch_applications(database, past_from, past_to) == []


class TestStorage:
    def test_safe_name_strips_dangerous_characters(self):
        assert storage.safe_name("javob xati.pdf") == "javob_xati.pdf"
        assert storage.safe_name("../../etc/passwd") == "etc_passwd"
        assert storage.safe_name("") == "fayl"
        assert len(storage.safe_name("a" * 200)) <= 80

    def test_path_is_grouped_by_application(self, tmp_path):
        path = storage.build_path(str(tmp_path), 12, "hujjat.pdf")
        assert str(tmp_path / "12") in path
        assert path.endswith("_hujjat.pdf")


class TestCallbackData:
    def test_roundtrip(self):
        assert kb.parse_app_callback(kb.app_callback(12, "reply")) == (12, "reply")

    @pytest.mark.parametrize("bad", ["", "app:", "app:abc:reply", "list:2", "app:12"])
    def test_rejects_broken_data(self, bad):
        assert kb.parse_app_callback(bad) == (None, "")


class TestRendering:
    def test_card_shows_the_template_fields(self, database):
        application_id = db.add_application(
            database, dict(SAMPLE, phone_extra="+998971112233")
        )
        card = notify.render_card(db.get_application(database, application_id))
        for expected in (
            "№ 1",
            "Karimov Aziz Baxtiyorovich",
            "AA1234567",
            "31234567890123",
            "15.03.1990",
            "+998901234567 (+998971112233)",
            "Yangi",
        ):
            assert expected in card

    def test_card_escapes_html_but_keeps_apostrophes(self, database):
        application_id = db.add_application(
            database, dict(SAMPLE, message="Uy <b>qurilishi</b> bo'yicha")
        )
        card = notify.render_card(db.get_application(database, application_id))
        assert "&lt;b&gt;qurilishi&lt;/b&gt;" in card
        assert "bo'yicha" in card

    def test_history_lists_both_sides(self, database):
        application_id = db.add_application(database, SAMPLE)
        db.add_message(database, application_id, db.DIRECTION_CITIZEN, text="Savol")
        db.add_message(
            database,
            application_id,
            db.DIRECTION_ADMIN,
            text="Javob",
            file_name="javob.pdf",
            file_type="document",
        )
        application = db.get_application(database, application_id)
        history = notify.render_history(application, db.fetch_messages(database, application_id))
        assert "Fuqaro" in history and "Admin" in history
        assert "javob.pdf" in history

    def test_history_without_messages(self, database):
        application_id = db.add_application(database, SAMPLE)
        application = db.get_application(database, application_id)
        assert "Hozircha" in notify.render_history(application, [])


class TestGroupLinks:
    def test_card_message_is_linked_to_the_application(self, database):
        application_id = db.add_application(database, SAMPLE)
        db.set_group_message(database, application_id, -1001234567890, 42)

        application = db.get_application(database, application_id)
        assert application["group_chat_id"] == -1001234567890
        assert application["group_message_id"] == 42
        assert db.application_by_group_message(database, -1001234567890, 42) == application_id

    def test_extra_messages_can_be_linked_too(self, database):
        application_id = db.add_application(database, SAMPLE)
        db.set_group_message(database, application_id, -100, 10)
        db.link_group_message(database, -100, 11, application_id)
        assert db.application_by_group_message(database, -100, 11) == application_id

    def test_unrelated_message_has_no_application(self, database):
        db.add_application(database, SAMPLE)
        assert db.application_by_group_message(database, -100, 999) is None

    def test_linking_twice_does_not_fail(self, database):
        application_id = db.add_application(database, SAMPLE)
        db.link_group_message(database, -100, 5, application_id)
        db.link_group_message(database, -100, 5, application_id)
        assert db.application_by_group_message(database, -100, 5) == application_id

    def test_message_counter(self, database):
        application_id = db.add_application(database, SAMPLE)
        assert db.count_messages(database, application_id) == 0
        db.add_message(database, application_id, db.DIRECTION_ADMIN, text="Javob")
        db.add_message(database, application_id, db.DIRECTION_CITIZEN, text="Rahmat")
        assert db.count_messages(database, application_id) == 2


class TestGroupCard:
    def test_new_application_asks_for_a_reply(self, database):
        application_id = db.add_application(database, SAMPLE)
        card = notify.render_group_card(db.get_application(database, application_id))
        assert "Javob kutilmoqda" in card
        assert "reply" in card

    def test_in_progress_shows_admin_and_counter(self, database):
        application_id = db.add_application(database, SAMPLE)
        db.set_status(
            database,
            application_id,
            db.STATUS_IN_PROGRESS,
            assigned_admin=555,
            assigned_admin_name="Aziz K.",
        )
        card = notify.render_group_card(db.get_application(database, application_id), 3)
        assert "Javob berilmoqda" in card
        assert card.count("Aziz K.") == 1  # mas'ul admin bir marta ko'rsatiladi
        assert "3 ta xabar" in card

    def test_closed_shows_time(self, database):
        application_id = db.add_application(database, SAMPLE)
        db.set_status(database, application_id, db.STATUS_CLOSED, assigned_admin_name="Aziz K.")
        card = notify.render_group_card(db.get_application(database, application_id), 5)
        assert "Yopildi" in card
        assert "reply" not in card

    def test_keyboard_switches_between_close_and_reopen(self):
        open_buttons = [
            b.text for row in kb.group_card_keyboard(1, closed=False).inline_keyboard for b in row
        ]
        closed_buttons = [
            b.text for row in kb.group_card_keyboard(1, closed=True).inline_keyboard for b in row
        ]
        assert any("Yopish" in text for text in open_buttons)
        assert any("Qayta ochish" in text for text in closed_buttons)
        # Guruhda «Javob berish» tugmasi bo'lmasligi kerak — javob reply orqali.
        assert not any("Javob berish" in text for text in open_buttons)
