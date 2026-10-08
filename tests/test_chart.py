import struct
from datetime import date

from tgforecast import chart


def png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    return struct.unpack(">II", data[16:24])


def test_series_is_one_day_of_hours(fx):
    forecast = fx("forecast_vienna")
    day = date.fromisoformat(forecast["daily"]["time"][0])
    s = chart.series(forecast, day)
    assert s["hours"] == list(range(24))
    temps = [t for t in s["temp"] if t is not None]
    assert s["high"][1] == max(temps) and s["low"][1] == min(temps)
    assert s["temp"][s["high"][0]] == s["high"][1]


def test_series_with_no_values():
    forecast = {
        "daily": {"time": ["2026-10-06"]},
        "hourly": {
            "time": [f"2026-10-06T{h:02d}:00" for h in range(24)],
            "temperature_2m": [None] * 24,
            "precipitation_probability": [None] * 24,
        },
    }
    s = chart.series(forecast, date(2026, 10, 6))
    assert s["high"] is None and s["low"] is None


def test_render_is_a_1280_by_800_png(fx):
    forecast = fx("forecast_vienna")
    day = date.fromisoformat(forecast["daily"]["time"][0])
    data = chart.render(
        chart.series(forecast, day), "Vienna · Monday 6 October", "metric", mark_hour=7.0
    )
    assert png_size(data) == (1280, 800)


def test_render_survives_an_empty_day():
    empty = {
        "hours": list(range(24)),
        "temp": [None] * 24,
        "rain": [None] * 24,
        "high": None,
        "low": None,
    }
    assert png_size(chart.render(empty, "Nowhere", "imperial")) == (1280, 800)


def test_week_series(fx):
    forecast = fx("forecast_vienna_week")
    s = chart.week_series(forecast)
    assert len(s["days"]) == 7
    assert s["days"][0] == date.fromisoformat(forecast["daily"]["time"][0])
    assert s["low"] == forecast["daily"]["temperature_2m_min"]
    assert s["high"] == forecast["daily"]["temperature_2m_max"]
    assert s["rain"] == forecast["daily"]["precipitation_probability_max"]


def test_week_render_is_a_1280_by_800_png(fx):
    data = chart.week_series(fx("forecast_vienna_week"))
    for lang in ("en", "de", "es"):
        assert png_size(chart.week_render(data, "Vienna · next 7 days", "metric", lang)) == (
            1280,
            800,
        )


def test_week_render_survives_missing_values():
    days = [date(2026, 10, 12 + i) for i in range(7)]
    data = {"days": days, "low": [None] * 7, "high": [5, None, 7, 8, 9, 10, 11], "rain": [None] * 7}
    assert png_size(chart.week_render(data, "x", "imperial")) == (1280, 800)


def test_day_chart_in_german_is_still_1280_by_800(fx):
    forecast = fx("forecast_vienna")
    day = date.fromisoformat(forecast["daily"]["time"][0])
    png = chart.render(chart.series(forecast, day), "Wien", "metric", mark_hour=9.5, lang="de")
    assert png_size(png) == (1280, 800)


def test_day_chart_titles_come_from_the_tables(fx, monkeypatch):
    titles = []
    real = chart.plt.Axes.set_title
    monkeypatch.setattr(
        chart.plt.Axes,
        "set_title",
        lambda ax, text, *a, **k: titles.append(text) or real(ax, text, *a, **k),
    )
    forecast = fx("forecast_vienna")
    day = date.fromisoformat(forecast["daily"]["time"][0])
    chart.render(chart.series(forecast, day), "W", "metric")
    chart.render(chart.series(forecast, day), "W", "metric", lang="fr")
    assert titles == [
        "Temperature (°C)",
        "Chance of rain (%)",
        "Température (°C)",
        "Risque de pluie (%)",
    ]
