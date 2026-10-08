from datetime import date, timedelta
from pathlib import Path

import pytest

from tgforecast import i18n
from tgforecast import summary as S

FIXTURES = Path(__file__).parent / "fixtures"

WMO = (
    0,
    1,
    2,
    3,
    45,
    48,
    51,
    53,
    55,
    56,
    57,
    61,
    63,
    65,
    66,
    67,
    71,
    73,
    75,
    77,
    80,
    81,
    82,
    85,
    86,
    95,
    96,
    99,
)
DAY = date(2026, 10, 6)


def hours(day: date) -> list[str]:
    return [f"{day.isoformat()}T{h:02d}:00" for h in range(24)]


def test_every_wmo_code_has_an_emoji_and_wording():
    for code in WMO:
        emoji, text = S.weather(code)
        assert emoji and text and text != "Unknown", code
    assert S.weather(4242) == ("🌡️", "Unknown")


def test_aqi_band_edges():
    for value, band in {
        0: "Good",
        20: "Good",
        21: "Fair",
        40: "Fair",
        41: "Moderate",
        60: "Moderate",
        61: "Poor",
        80: "Poor",
        81: "Very poor",
        100: "Very poor",
        101: "Extremely poor",
    }.items():
        assert S.aqi_band(value) == band, value


def test_rain_window():
    times = hours(DAY) + hours(DAY + timedelta(days=1))
    dry = [10] * 48
    assert S.rain_window(times, dry, DAY) == "Dry all day"
    wet = [10] * 14 + [60, 70, 55] + [20] * 31
    assert S.rain_window(times, wet, DAY) == "Rain likely 14:00–17:00"
    late = [10] * 21 + [80, 90, 90] + [90] * 24
    assert S.rain_window(times, late, DAY) == "Rain likely 21:00–midnight"
    two_runs = [60] + [10] * 10 + [70] + [10] * 36
    assert S.rain_window(times, two_runs, DAY) == "Rain likely 00:00–01:00"
    gaps = [None] * 48
    assert S.rain_window(times, gaps, DAY) == "Dry all day"


def test_aqi_line():
    air = {"hourly": {"time": hours(DAY), "european_aqi": [10] * 12 + [41] + [None] * 11}}
    assert S.aqi_line(air, DAY) == "Air: up to AQI 41 · Moderate"
    assert S.aqi_line(None, DAY) == "Air: no reading today"
    assert (
        S.aqi_line({"hourly": {"time": hours(DAY), "european_aqi": [None] * 24}}, DAY)
        == "Air: no reading today"
    )


def test_caption_on_the_recording(fx):
    forecast, air = fx("forecast_vienna"), fx("air_vienna")
    day = date.fromisoformat(forecast["daily"]["time"][0])
    text = S.caption(forecast, air, "Vienna, Vienna, AT", "metric", day)
    lines = text.split("\n")
    assert len(lines) == 6
    assert "Vienna, Vienna, AT" in lines[0] and f"{day:%A}" in lines[0]
    assert "°C" in lines[1] and "rain chance" in lines[1] and "km/h" in lines[1]
    assert lines[3].startswith("Air: ")
    assert lines[4].startswith("Tomorrow: ")
    assert lines[5] == S.CREDIT
    assert len(text) <= S.CAPTION_MAX


def test_imperial_labels(fx):
    forecast = fx("forecast_vienna")
    day = date.fromisoformat(forecast["daily"]["time"][0])
    text = S.caption(forecast, None, "Vienna", "imperial", day)
    assert "°F" in text and "mph" in text


def test_names_are_html_escaped(fx):
    forecast = fx("forecast_vienna")
    day = date.fromisoformat(forecast["daily"]["time"][0])
    text = S.caption(forecast, None, "Bosnia & Herzegovina <test>", "metric", day)
    assert "Bosnia &amp; Herzegovina &lt;test&gt;" in text


def test_fit_keeps_the_credit():
    long = "x" * 2000
    text = S.fit("\n".join([long, "line two", S.CREDIT]))
    assert len(text) <= S.CAPTION_MAX and text.endswith(S.CREDIT)
    short = "a\nb\n" + S.CREDIT
    assert S.fit(short) == short


def test_caption_when_tz_day_is_not_in_the_data(fx):
    forecast = fx("forecast_vienna")
    far = date.fromisoformat(forecast["daily"]["time"][0]) + timedelta(days=5)
    assert S.day_index(forecast, far) == 0
    assert S.caption(forecast, None, "Vienna", "metric", far).split("\n")[0]


def test_english_caption_is_unchanged(fx):
    f, a = fx("forecast_vienna"), fx("air_vienna")
    day = date.fromisoformat(f["daily"]["time"][0])
    got = (
        S.caption(f, a, "Vienna, Vienna, AT", "metric", day)
        + "\n---\n"
        + S.caption(f, None, "Vienna", "imperial", day)
        + "\n"
    )
    assert got == (FIXTURES / "caption_vienna_en.txt").read_text()


def test_weather_and_bands_in_other_languages():
    assert S.weather(61, "de") == ("🌧️", "Leichter Regen")
    assert S.weather(4242, "fr") == ("🌡️", "Inconnu")
    assert S.aqi_band(41, "fr") == "Dégradé"
    assert S.aqi_band(101, "es") == "Extremadamente desfavorable"


def test_rain_window_and_air_in_german():
    times = hours(DAY) + hours(DAY + timedelta(days=1))
    assert S.rain_window(times, [10] * 48, DAY, "de") == "Den ganzen Tag trocken"
    late = [10] * 21 + [90] * 27
    assert S.rain_window(times, late, DAY, "de") == "Regen wahrscheinlich 21:00–Mitternacht"
    assert S.aqi_line(None, DAY, "de") == "Luft: heute kein Messwert"


def test_caption_in_german(fx):
    forecast, air = fx("forecast_vienna"), fx("air_vienna")
    day = date.fromisoformat(forecast["daily"]["time"][0])
    lines = S.caption(forecast, air, "Wien, Wien, AT", "metric", day, "de").split("\n")
    assert i18n.date_long(day, "de") in lines[0]
    assert "Regenrisiko" in lines[1] and "Wind bis" in lines[1]
    assert lines[3].startswith("Luft: ") and lines[4].startswith("Morgen: ")
    assert lines[-1] == S.CREDIT


def test_tomorrow_outlook_keeps_german_capitals(fx):
    forecast = fx("forecast_vienna")
    forecast["daily"]["precipitation_probability_max"][1] = 0
    forecast["daily"]["weather_code"][1] = 61
    day = date.fromisoformat(forecast["daily"]["time"][0])
    assert (
        S.caption(forecast, None, "W", "metric", day, "de")
        .split("\n")[4]
        .endswith(", Leichter Regen")
    )
    assert (
        S.caption(forecast, None, "W", "metric", day, "en").split("\n")[4].endswith(", light rain")
    )


def test_week_caption(fx):
    forecast = fx("forecast_vienna_week")
    lines = S.week_caption(forecast, "Vienna, Vienna, AT", "metric").split("\n")
    assert lines[0] == "Vienna, Vienna, AT · next 7 days"
    assert len(lines) == 9 and lines[-1] == S.CREDIT
    first = date.fromisoformat(forecast["daily"]["time"][0])
    assert lines[1].startswith(i18n.week_day(first, "en") + " · ")
    assert "°C" in lines[1] and "km/h" in lines[1] and "rain " in lines[1]


def test_week_caption_imperial_italian_and_escaped(fx):
    forecast = fx("forecast_vienna_week")
    text = S.week_caption(forecast, "A & <B>", "imperial", "it")
    assert text.startswith("A &amp; &lt;B&gt; · prossimi 7 giorni")
    assert "°F" in text and "mph" in text and "pioggia" in text


def test_week_caption_with_missing_values(fx):
    forecast = fx("forecast_vienna_week")
    for key in ("temperature_2m_min", "precipitation_probability_max", "weather_code"):
        forecast["daily"][key][2] = None
    line = S.week_caption(forecast, "V", "metric").split("\n")[3]
    assert "🌡️ –" in line and "rain – %" in line


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_captions_in_every_language_are_complete(fx, lang):
    forecast, air, week = fx("forecast_vienna"), fx("air_vienna"), fx("forecast_vienna_week")
    day = date.fromisoformat(forecast["daily"]["time"][0])
    for text in (
        S.caption(forecast, air, "Vienna", "metric", day, lang),
        S.week_caption(week, "Vienna", "metric", lang),
    ):
        assert text.endswith(S.CREDIT) and len(text) <= S.CAPTION_MAX and "{" not in text


def test_a_huge_label_is_cut_and_the_credit_stays(fx):
    text = S.week_caption(fx("forecast_vienna_week"), "V" * 2000, "metric")
    assert len(text) <= S.CAPTION_MAX and text.endswith(S.CREDIT)
