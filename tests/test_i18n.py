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


def test_french_first_of_the_month_is_1er():
    assert i18n.date_long(date(2026, 10, 1), "fr") == "jeudi 1er octobre"
    assert i18n.date_long(date(2026, 10, 2), "fr") == "vendredi 2 octobre"
    assert i18n.date_long(date(2026, 10, 1), "es") == "jueves 1 de octubre"


def test_proofread_wording():
    t = i18n.t
    assert i18n.WEATHER_TEXT["fr"][75] == "Neige forte"
    assert i18n.WEATHER_TEXT["fr"][55] == "Forte bruine"
    assert t("it", "air", aqi=41, band="x") == "Aria: fino a un AQI di 41 · x"
    assert t("fr", "air", aqi=41, band="x") == "Air : jusqu'à un IQA de 41 · x"
    assert t("es", "air", aqi=41, band="x") == "Aire: hasta un ICA de 41 · x"
    assert i18n.AQI_NAMES["es"][1] == "Razonablemente buena"
    assert t("es", "crash") == "Algo salió mal; inténtalo de nuevo."
    assert t("es", "wind_up_to", v=9, unit="km/h") == "viento de hasta 9 km/h"
    assert t("it", "unknown_place", name="X") == "Non conosco nessun luogo chiamato «X»."
    assert t("it", "rain_chance", p=5) == "probabilità di pioggia 5%"
    assert t("it", "showers", p=5) == "rovesci probabili (5%)"
    assert t("fr", "chart_range", unit="°C") == "Min. et max. (°C)"
    assert "pioggia 5% ·" in t(
        "it", "week_line", day="d", emoji="e", low=1, high=2, unit="u", p=5, w=1, wunit="w"
    )
    assert i18n.S["it"]["help"].startswith("Il meteo di qualsiasi città, con i dati di Open-Meteo.")
    assert i18n.S["fr"]["help"].startswith("La météo de n'importe quelle ville, avec les données")
    assert "pour un affichage en Fahrenheit" in i18n.S["fr"]["help"]
    assert "écrire le nom d'une ville" in i18n.S["fr"]["help"]
    assert "escribir el nombre de una ciudad" in i18n.S["es"]["help"]
    assert "despertarse primero" in i18n.S["es"]["help"]


def test_help_shows_a_list_of_cities():
    for lang in i18n.LANGS:
        assert "; " in i18n.S[lang]["help"], lang


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
        for link in ("open-meteo.com", "geonames.org"):
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
