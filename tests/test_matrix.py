import asyncio
from datetime import date

import pytest

import bridge as bridge_module
import config
import db
import matrix_bot
import notify
import ranges

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

ROOM = "!qabul:example.uz"
ADMIN = "@nodir:example.uz"
OUTSIDER = "@begona:example.uz"


# --- Sof funksiyalar ------------------------------------------------------


class TestReplyFallback:
    def test_strips_quoted_original(self):
        body = "> <@qabulbot:example.uz> № 1 · Yangi\n> Fuqaro ...\n\nJavobim shu"
        assert matrix_bot.strip_reply_fallback(body) == "Javobim shu"

    def test_keeps_plain_message(self):
        assert matrix_bot.strip_reply_fallback("Oddiy xabar") == "Oddiy xabar"

    def test_multiline_answer_survives(self):
        body = "> <@bot:x> kartochka\n\nBirinchi qator\nIkkinchi qator"
        assert matrix_bot.strip_reply_fallback(body) == "Birinchi qator\nIkkinchi qator"

    def test_empty(self):
        assert matrix_bot.strip_reply_fallback("") == ""


class TestCommandParsing:
    @pytest.mark.parametrize(
        "body,expected",
        [
            ("!list", ("list", "")),
            ("!export oy", ("export", "oy")),
            ("!export 01.09.2026 30.09.2026", ("export", "01.09.2026 30.09.2026")),
            ("!FIND Karimov", ("find", "Karimov")),
            ("  !yopish 12  ", ("yopish", "12")),
        ],
    )
    def test_parses(self, body, expected):
        assert matrix_bot.parse_command(body) == expected

    @pytest.mark.parametrize("body", ["", "list", "salom !list", "!", "/list"])
    def test_not_a_command(self, body):
        assert matrix_bot.parse_command(body) == (None, "")


class TestFormatting:
    def test_html_body_keeps_tags_and_breaks_lines(self):
        assert matrix_bot.html_body("<b>Ha</b>\nYo'q") == "<b>Ha</b><br/>Yo'q"

    def test_plain_body_strips_tags_and_unescapes(self):
        assert matrix_bot.plain_body("<b>№ 1</b> &lt;test&gt;") == "№ 1 <test>"

    def test_card_survives_both_conversions(self):
        card = notify.render_group_card(dict(SAMPLE, id=1, status=db.STATUS_NEW, created_at=""))
        assert "<br/>" in matrix_bot.html_body(card)
        assert "<b>" not in matrix_bot.plain_body(card)
        assert "Karimov Aziz Baxtiyorovich" in matrix_bot.plain_body(card)

    def test_display_name(self):
        assert matrix_bot.display_name("@nodir:example.uz") == "nodir"
        assert matrix_bot.display_name("nodir") == "nodir"


class TestPermissions:
    def test_empty_list_allows_everyone(self, monkeypatch):
        monkeypatch.setattr(config, "MATRIX_ADMINS", set())
        assert config.matrix_can_answer(OUTSIDER)

    def test_list_restricts(self, monkeypatch):
        monkeypatch.setattr(config, "MATRIX_ADMINS", {ADMIN})
        assert config.matrix_can_answer(ADMIN)
        assert not config.matrix_can_answer(OUTSIDER)

    def test_parsing_users(self):
        assert config._parse_users("@a:x.uz, @b:x.uz") == {"@a:x.uz", "@b:x.uz"}
        assert config._parse_users("") == set()
        assert config._parse_users("noto'g'ri") == set()


class TestExportRequests:
    TODAY = date(2026, 9, 8)

    def test_keywords(self):
        assert ranges.parse_request("bugun", self.TODAY)[:2] == ("2026-09-08", "2026-09-08")
        assert ranges.parse_request("oy", self.TODAY)[:2] == ("2026-09-01", "2026-09-08")
        assert ranges.parse_request("otgan-oy", self.TODAY)[:2] == ("2026-08-01", "2026-08-31")
        assert ranges.parse_request("hammasi", self.TODAY)[:2] == (None, None)

    def test_empty_means_everything(self):
        assert ranges.parse_request("", self.TODAY)[:2] == (None, None)

    def test_two_dates(self):
        assert ranges.parse_request("01.09.2026 30.09.2026", self.TODAY)[:2] == (
            "2026-09-01",
            "2026-09-30",
        )

    def test_bad_input(self):
        from validators import ValidationError

        with pytest.raises(ValidationError):
            ranges.parse_request("kechagi kun", self.TODAY)


# --- Ko'prikning o'zi -----------------------------------------------------


class FakeResponse:
    def __init__(self, event_id):
        self.event_id = event_id


class FakeRoom:
    def __init__(self, room_id=ROOM):
        self.room_id = room_id


class FakeEvent:
    def __init__(self, body, sender=ADMIN, event_id="$e1", reply_to="", url=""):
        self.body = body
        self.sender = sender
        self.event_id = event_id
        self.server_timestamp = 10_000
        self.url = url
        content = {"body": body}
        if reply_to:
            content["m.relates_to"] = {"m.in_reply_to": {"event_id": reply_to}}
        self.source = {"content": content}


class FakeClient:
    """room_send/upload/download ni yozib boradigan soxta nio mijozi."""

    def __init__(self):
        self.sent = []
        self.edits = []
        self.reactions = []
        self.uploads = []
        self.counter = 0

    async def room_send(self, room_id, event_type, content):
        self.counter += 1
        if event_type == "m.reaction":
            self.reactions.append(content["m.relates_to"]["key"])
            return FakeResponse(f"$r{self.counter}")
        if "m.new_content" in content:
            self.edits.append((content["m.relates_to"]["event_id"], content["m.new_content"]["body"]))
            return FakeResponse(f"$edit{self.counter}")
        self.sent.append((room_id, content))
        return FakeResponse(f"$m{self.counter}")

    async def upload(self, handle, content_type=None, filename=None, filesize=None):
        self.uploads.append(filename)

        class Uploaded:
            content_uri = "mxc://example.uz/abc"

        return Uploaded(), None

    async def download(self, url):
        class Downloaded:
            body = b"matrix fayli"

        return Downloaded()


class SentMessage:
    def __init__(self, message_id):
        self.message_id = message_id


class FakeTelegramBot:
    def __init__(self):
        self.messages = []
        self.documents = []
        self.counter = 1000

    def _next(self):
        self.counter += 1
        return SentMessage(self.counter)

    async def send_message(self, chat_id, text, **kwargs):
        self.messages.append((chat_id, text))
        return self._next()

    async def send_document(self, chat_id, document, caption=None, **kwargs):
        self.documents.append((chat_id, caption))
        self.messages.append((chat_id, caption or ""))
        return self._next()

    async def send_photo(self, chat_id, photo, caption=None, **kwargs):
        self.documents.append((chat_id, caption))
        return self._next()

    async def edit_message_text(self, text, chat_id=None, message_id=None, **kwargs):
        return None


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    """Ishga tushirilgan ko'prik + toza baza."""
    path = str(tmp_path / "matrix.db")
    db.init_db(path)
    monkeypatch.setattr(matrix_bot, "DB_PATH", path)
    monkeypatch.setattr(notify, "DB_PATH", path)
    monkeypatch.setattr(matrix_bot, "FILES_DIR", str(tmp_path / "files"))
    monkeypatch.setattr(config, "MATRIX_ADMINS", {ADMIN})

    telegram = FakeTelegramBot()
    bridge = matrix_bot.MatrixBridge(
        homeserver="https://example.uz",
        user="@qabulbot:example.uz",
        room_id=ROOM,
        telegram_bot=telegram,
    )
    bridge.client = FakeClient()
    bridge._started_ms = 0
    bridge_module.set_bridge(bridge)
    yield bridge, telegram, path
    bridge_module.set_bridge(None)


def run(coroutine):
    return asyncio.run(coroutine)


class TestBridgeFlow:
    def _application(self, path):
        application_id = db.add_application(path, SAMPLE)
        return db.get_application(path, application_id)

    def test_card_is_posted_and_linked(self, wired):
        bridge, _, path = wired
        application = self._application(path)

        assert run(bridge.post_card(application)) is True

        room_id, content = bridge.client.sent[-1]
        assert room_id == ROOM
        assert "Yangi ariza" in content["body"]
        assert "Karimov Aziz Baxtiyorovich" in content["body"]
        assert content["format"] == "org.matrix.custom.html"

        stored = db.get_application(path, application["id"])
        assert stored["matrix_room_id"] == ROOM
        assert stored["matrix_event_id"]
        assert db.application_by_matrix_event(path, ROOM, stored["matrix_event_id"]) == application["id"]

    def test_admin_reply_reaches_the_citizen_and_edits_the_card(self, wired):
        bridge, telegram, path = wired
        application = self._application(path)
        run(bridge.post_card(application))
        card_event = db.get_application(path, application["id"])["matrix_event_id"]

        run(
            bridge._on_text(
                FakeRoom(),
                FakeEvent("Hujjatlaringiz tayyor.", reply_to=card_event, event_id="$reply1"),
            )
        )

        assert telegram.messages, "fuqaroga xabar ketmadi"
        chat_id, text = telegram.messages[-1]
        assert chat_id == SAMPLE["tg_user_id"]
        assert "Hujjatlaringiz tayyor." in text

        stored = db.get_application(path, application["id"])
        assert stored["status"] == db.STATUS_IN_PROGRESS
        assert stored["assigned_admin_name"] == "nodir"
        assert db.count_messages(path, application["id"]) == 1

        assert bridge.client.reactions == ["👍"]
        edited_event, edited_body = bridge.client.edits[-1]
        assert edited_event == card_event
        assert "Javob berilmoqda" in edited_body

    def test_outsider_cannot_answer(self, wired):
        bridge, telegram, path = wired
        application = self._application(path)
        run(bridge.post_card(application))
        card_event = db.get_application(path, application["id"])["matrix_event_id"]

        run(bridge._on_text(FakeRoom(), FakeEvent("Men javob beraman", sender=OUTSIDER, reply_to=card_event)))

        assert telegram.messages == []
        assert db.count_messages(path, application["id"]) == 0
        assert "huquqi yo'q" in bridge.client.sent[-1][1]["body"]

    def test_unrelated_reply_is_ignored(self, wired):
        bridge, telegram, path = wired
        self._application(path)
        before = len(bridge.client.sent)

        run(bridge._on_text(FakeRoom(), FakeEvent("Tushlikka boramizmi?", reply_to="$boshqa")))

        assert len(bridge.client.sent) == before
        assert telegram.messages == []

    def test_own_and_old_events_are_skipped(self, wired):
        bridge, _, path = wired
        application = self._application(path)
        run(bridge.post_card(application))
        card_event = db.get_application(path, application["id"])["matrix_event_id"]
        before = len(bridge.client.sent)

        own = FakeEvent("o'zim", sender=bridge.user, reply_to=card_event)
        run(bridge._on_text(FakeRoom(), own))

        bridge._started_ms = 99_999
        old = FakeEvent("eski xabar", reply_to=card_event)
        run(bridge._on_text(FakeRoom(), old))

        assert len(bridge.client.sent) == before
        assert db.count_messages(path, application["id"]) == 0

    def test_close_command_updates_everything(self, wired):
        bridge, telegram, path = wired
        application = self._application(path)
        run(bridge.post_card(application))

        run(bridge._on_text(FakeRoom(), FakeEvent("!yopish 1")))

        stored = db.get_application(path, application["id"])
        assert stored["status"] == db.STATUS_CLOSED
        assert stored["closed_at"]
        assert any("yakunlandi" in text for _, text in telegram.messages)
        assert "Yopildi" in bridge.client.edits[-1][1]

    def test_close_by_replying_to_the_card(self, wired):
        bridge, _, path = wired
        application = self._application(path)
        run(bridge.post_card(application))
        card_event = db.get_application(path, application["id"])["matrix_event_id"]

        run(bridge._on_text(FakeRoom(), FakeEvent("!yopish", reply_to=card_event)))

        assert db.get_application(path, application["id"])["status"] == db.STATUS_CLOSED

    def test_reopen_command(self, wired):
        bridge, _, path = wired
        application = self._application(path)
        run(bridge.post_card(application))
        db.set_status(path, application["id"], db.STATUS_CLOSED)

        run(bridge._on_text(FakeRoom(), FakeEvent("!ochish 1")))

        assert db.get_application(path, application["id"])["status"] == db.STATUS_IN_PROGRESS

    def test_list_and_stats_commands(self, wired):
        bridge, _, path = wired
        self._application(path)

        run(bridge._on_text(FakeRoom(), FakeEvent("!list")))
        assert "Javob kutayotgan arizalar" in bridge.client.sent[-1][1]["body"]

        run(bridge._on_text(FakeRoom(), FakeEvent("!stats")))
        body = bridge.client.sent[-1][1]["body"]
        assert "Hisobot" in body and "Jami arizalar" in body

    def test_find_command(self, wired):
        bridge, _, path = wired
        self._application(path)

        run(bridge._on_text(FakeRoom(), FakeEvent("!find Karimov")))
        assert "Karimov Aziz Baxtiyorovich" in bridge.client.sent[-1][1]["body"]

        run(bridge._on_text(FakeRoom(), FakeEvent("!find Petrov")))
        assert "topilmadi" in bridge.client.sent[-1][1]["body"]

    def test_export_command_uploads_a_file(self, wired):
        bridge, _, path = wired
        self._application(path)

        run(bridge._on_text(FakeRoom(), FakeEvent("!export hammasi")))

        assert bridge.client.uploads, "Excel fayl yuklanmadi"
        assert bridge.client.uploads[-1].endswith(".xlsx")
        assert "Qabul jadvali" in bridge.client.sent[-1][1]["body"]

    def test_export_with_empty_period(self, wired):
        bridge, _, path = wired
        self._application(path)
        run(bridge._on_text(FakeRoom(), FakeEvent("!export otgan-oy")))
        assert "topilmadi" in bridge.client.sent[-1][1]["body"]

    def test_unknown_command_shows_help(self, wired):
        bridge, _, _ = wired
        run(bridge._on_text(FakeRoom(), FakeEvent("!nimadir")))
        assert "Noma'lum buyruq" in bridge.client.sent[-1][1]["body"]

    def test_id_command_works_without_permission(self, wired):
        bridge, _, _ = wired
        run(bridge._on_text(FakeRoom(), FakeEvent("!id", sender=OUTSIDER)))
        assert ROOM in bridge.client.sent[-1][1]["body"]

    def test_citizen_reply_lands_in_the_room(self, wired):
        bridge, _, path = wired
        application = self._application(path)
        run(bridge.post_card(application))
        application = db.get_application(path, application["id"])

        run(bridge.post_to_room(application, "👤 № 1 yozdi:", "Rahmat!"))

        room_id, content = bridge.client.sent[-1]
        assert room_id == ROOM
        assert "Rahmat!" in content["body"]
        # Bu xabarga ham reply qilib javob berish mumkin bo'lishi kerak.
        event_id = f"$m{bridge.client.counter}"
        assert db.application_by_matrix_event(path, ROOM, event_id) == application["id"]


class FakeRooms:
    def __init__(self, invite=None):
        self.invite = invite or {}


class FakeSync:
    def __init__(self, invited):
        self.rooms = FakeRooms({room: object() for room in invited})


class TestAutoJoin:
    def test_accepts_invitation_and_announces_room_id(self, wired):
        bridge, _, _ = wired
        joined = []

        class Joined:
            def __init__(self, room_id):
                self.room_id = room_id

        async def fake_join(room_id):
            joined.append(room_id)
            return Joined(room_id)

        bridge.client.join = fake_join

        run(bridge._on_sync(FakeSync(["!yangi:example.uz"])))

        assert joined == ["!yangi:example.uz"]
        room_id, content = bridge.client.sent[-1]
        assert room_id == "!yangi:example.uz"
        assert "!yangi:example.uz" in content["body"]
        assert "MATRIX_ROOM_ID" in content["body"]

    def test_failed_join_is_survivable(self, wired):
        bridge, _, _ = wired

        class Failed:
            room_id = None

        async def fake_join(room_id):
            return Failed()

        bridge.client.join = fake_join
        before = len(bridge.client.sent)

        run(bridge._on_sync(FakeSync(["!yopiq:example.uz"])))

        assert len(bridge.client.sent) == before

    def test_no_invitations_does_nothing(self, wired):
        bridge, _, _ = wired
        before = len(bridge.client.sent)
        run(bridge._on_sync(FakeSync([])))
        assert len(bridge.client.sent) == before


class TestCrossChannelEcho:
    """Javob qaysi kanalda berilsa ham, ikkinchisida ko'rinishi kerak."""

    def test_matrix_answer_appears_in_the_telegram_group(self, wired):
        bridge, telegram, path = wired
        application_id = db.add_application(path, SAMPLE)
        db.set_group_message(path, application_id, -100500, 42)
        run(bridge.post_card(db.get_application(path, application_id)))
        card_event = db.get_application(path, application_id)["matrix_event_id"]

        run(bridge._on_text(FakeRoom(), FakeEvent("Hujjat tayyor.", reply_to=card_event)))

        group_messages = [item for item in telegram.messages if item[0] == -100500]
        assert group_messages, "javob Telegram guruhida ko'rinmadi"
        assert "javob berdi" in group_messages[-1][1]
        assert "Hujjat tayyor." in group_messages[-1][1]
        assert "nodir" in group_messages[-1][1]

    def test_matrix_answer_is_not_echoed_back_into_the_room(self, wired):
        bridge, _, path = wired
        application_id = db.add_application(path, SAMPLE)
        db.set_group_message(path, application_id, -100500, 42)
        run(bridge.post_card(db.get_application(path, application_id)))
        card_event = db.get_application(path, application_id)["matrix_event_id"]
        before = len(bridge.client.sent)

        run(bridge._on_text(FakeRoom(), FakeEvent("Javobim", reply_to=card_event)))

        # Xona faqat kartochka tahriri oladi, javob takrorlanmaydi.
        assert len(bridge.client.sent) == before

    def test_group_reply_is_linked_for_further_replies(self, wired):
        bridge, telegram, path = wired
        application_id = db.add_application(path, SAMPLE)
        db.set_group_message(path, application_id, -100500, 42)
        application = db.get_application(path, application_id)

        run(notify.relay_to_staff(telegram, application, "👤 yozdi:", "Savol", skip="matrix"))

        assert telegram.messages[-1][0] == -100500
