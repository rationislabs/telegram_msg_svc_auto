import re
import string
from datetime import date

import pytest

from tgforecast import i18n, summary


def fields(text: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


def test_every_language_has_every_string_with_the_same_placeholders():
    for lang in i18n.LANGS:
        assert set(i18n.S[lang]) == set(i18n.S["en"]), lang
        for key, text in i18n.S[lang].items():
            assert fields(text) == fields(i18n.S["en"][key]), (lang, key)


def test_every_language_names_every_weather_code_band_day_and_month():
    for lang in i18n.LANGS[1:]:
        assert set(i18n.WEATHER_TEXT[lang]) == set(summary.WEATHER), lang
    for table, size in (
        (i18n.AQI_NAMES, 6),
        (i18n.WEEKDAYS, 7),
        (i18n.WEEKDAYS_SHORT, 7),
        (i18n.MONTHS, 12),
    ):
        assert set(table) == set(i18n.LANGS)
        assert all(len(v) == size for v in table.values())


@pytest.mark.parametrize(
    "code, lang",
    [
        ("de", "de"),
        ("de-AT", "de"),
        ("it", "it"),
        ("fr-CA", "fr"),
        ("es-419", "es"),
        ("en-GB", "en"),
        ("pt-BR", "en"),
        (None, "en"),
        ("", "en"),
    ],
)
def test_pick(code, lang):
    assert i18n.pick(code) == lang


@pytest.mark.parametrize(
    "lang, text",
    [
        ("en", "Tuesday 6 October"),
        ("de", "Dienstag, 6. Oktober"),
        ("it", "martedì 6 ottobre"),
        ("fr", "mardi 6 octobre"),
        ("es", "martes 6 de octubre"),
    ],
)
def test_date_long(lang, text):
    assert i18n.date_long(date(2026, 10, 6), lang) == text


def test_week_day():
    assert i18n.week_day(date(2026, 10, 12), "en") == "Mon 12"
    assert i18n.week_day(date(2026, 10, 12), "de") == "Mo 12."


def test_commands_are_unique_valid_telegram_commands():
    names = [n for c in i18n.COMMANDS.values() for n in c]
    assert len(names) == len(set(names))
    assert all(re.fullmatch(r"[a-z0-9_]{1,32}", n) for n in names)
    assert set(i18n.COMMANDS) == set(i18n.LANGS)


def test_help_names_its_commands_and_the_credits():
    for lang, (now, week, _) in i18n.COMMANDS.items():
        text = i18n.help_text(lang)
        assert f"/{now} " in text and f"/{week} " in text, lang
        for link in ("open-meteo.com", "geonames.org", "rationis.dev"):
            assert link in text, (lang, link)


def test_english_matches_stage_1_wording():
    assert i18n.t("en", "rain_chance", p=40) == "rain chance 40 %"
    assert i18n.t("en", "chart_temp", unit="°C") == "Temperature (°C)"
    assert i18n.t("en", "chart_rain") == "Chance of rain (%)"
    assert i18n.AQI_NAMES["en"] == (
        "Good",
        "Fair",
        "Moderate",
        "Poor",
        "Very poor",
        "Extremely poor",
    )
