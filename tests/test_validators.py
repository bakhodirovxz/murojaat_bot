from datetime import date, timedelta

import pytest

from validators import (
    ValidationError,
    parse_date,
    validate_address,
    validate_birth_date,
    validate_fio,
    validate_jshshir,
    validate_message,
    validate_passport,
    validate_phone,
    validate_phone_optional,
)


class TestFio:
    def test_normalizes_whitespace(self):
        assert validate_fio("  Karimov   Aziz  Baxtiyorovich ") == "Karimov Aziz Baxtiyorovich"

    def test_allows_apostrophes_and_cyrillic(self):
        assert validate_fio("Sa'dullayev O'ktam") == "Sa'dullayev O'ktam"
        assert validate_fio("Каримов Азиз Бахтиёрович") == "Каримов Азиз Бахтиёрович"

    @pytest.mark.parametrize("bad", ["", "   ", "Karimov", "Karimov A", "Karimov Aziz1", "A B"])
    def test_rejects_bad_input(self, bad):
        with pytest.raises(ValidationError):
            validate_fio(bad)


class TestPassport:
    def test_uppercases_and_strips(self):
        assert validate_passport(" aa 1234567 ") == "AA1234567"

    def test_converts_cyrillic_lookalikes(self):
        assert validate_passport("АА1234567") == "AA1234567"

    @pytest.mark.parametrize("bad", ["", "A1234567", "AA123456", "AA12345678", "AAA123456"])
    def test_rejects_bad_input(self, bad):
        with pytest.raises(ValidationError):
            validate_passport(bad)


class TestJshshir:
    def test_strips_spaces_and_dashes(self):
        assert validate_jshshir("3123 4567-890123") == "31234567890123"

    @pytest.mark.parametrize("bad", ["", "1234567890123", "123456789012345", "3123456789012a"])
    def test_rejects_bad_input(self, bad):
        with pytest.raises(ValidationError):
            validate_jshshir(bad)


class TestBirthDate:
    @pytest.mark.parametrize(
        "raw", ["15.03.1990", "15/03/1990", "15-03-1990", "5.3.1990"]
    )
    def test_accepts_separators_and_short_parts(self, raw):
        assert validate_birth_date(raw).endswith(".1990")

    def test_normalizes_to_dd_mm_yyyy(self):
        assert validate_birth_date("5.3.1990") == "05.03.1990"

    def test_rejects_future_date(self):
        tomorrow = date.today() + timedelta(days=1)
        with pytest.raises(ValidationError):
            validate_birth_date(tomorrow.strftime("%d.%m.%Y"))

    @pytest.mark.parametrize("bad", ["", "31.02.1990", "1990.03.15", "15.13.1990", "15.03.1890"])
    def test_rejects_bad_input(self, bad):
        with pytest.raises(ValidationError):
            validate_birth_date(bad)

    def test_parse_date_allows_future(self):
        assert parse_date("01.01.2099") == date(2099, 1, 1)


class TestPhone:
    @pytest.mark.parametrize(
        "raw",
        ["901234567", "+998901234567", "998 90 123 45 67", "(90) 123-45-67", "8998901234567"],
    )
    def test_normalizes(self, raw):
        assert validate_phone(raw) == "+998901234567"

    @pytest.mark.parametrize("bad", ["", "12345", "9012345678"])
    def test_rejects_bad_input(self, bad):
        with pytest.raises(ValidationError):
            validate_phone(bad)

    def test_optional_allows_empty(self):
        assert validate_phone_optional("") == ""
        assert validate_phone_optional("   ") == ""

    def test_optional_still_validates_value(self):
        with pytest.raises(ValidationError):
            validate_phone_optional("123")


class TestFreeText:
    def test_address_requires_detail(self):
        with pytest.raises(ValidationError):
            validate_address("Toshkent")
        assert validate_address("Toshkent sh., Chilonzor t., 5-uy").startswith("Toshkent")

    def test_message_length_bounds(self):
        with pytest.raises(ValidationError):
            validate_message("qisqa")
        with pytest.raises(ValidationError):
            validate_message("a" * 3001)
        assert validate_message("  Uy hujjatlari masalasida  ") == "Uy hujjatlari masalasida"
