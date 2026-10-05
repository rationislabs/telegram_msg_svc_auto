from datetime import date, timedelta

from tgforecast import summary as S

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
