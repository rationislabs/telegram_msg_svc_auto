"""Forecast JSON in, caption text out. Pure: no network, no Telegram.

Telegram allows 1024 characters on a photo caption, sent as HTML; every name
interpolated here is escaped, and the Open-Meteo credit (required by their
licence) is always the last line.
"""

from __future__ import annotations

import html
from datetime import date

CAPTION_MAX = 1024
CREDIT = '<a href="https://open-meteo.com/">Weather data by Open-Meteo.com</a>'
UNIT_LABELS = {"metric": {"temp": "°C", "wind": "km/h"},
               "imperial": {"temp": "°F", "wind": "mph"}}
WET = 50  # % precipitation probability that counts as "rain likely"

# WMO weather interpretation codes, as Open-Meteo documents them.
WEATHER: dict[int, tuple[str, str]] = {
    0: ("☀️", "Clear sky"), 1: ("🌤️", "Mainly clear"), 2: ("⛅", "Partly cloudy"),
    3: ("☁️", "Overcast"), 45: ("🌫️", "Fog"), 48: ("🌫️", "Freezing fog"),
    51: ("🌦️", "Light drizzle"), 53: ("🌦️", "Drizzle"), 55: ("🌦️", "Dense drizzle"),
    56: ("🌧️", "Light freezing drizzle"), 57: ("🌧️", "Freezing drizzle"),
    61: ("🌧️", "Light rain"), 63: ("🌧️", "Rain"), 65: ("🌧️", "Heavy rain"),
    66: ("🌧️", "Light freezing rain"), 67: ("🌧️", "Freezing rain"),
    71: ("🌨️", "Light snow"), 73: ("🌨️", "Snow"), 75: ("❄️", "Heavy snow"),
    77: ("🌨️", "Snow grains"),
    80: ("🌦️", "Light showers"), 81: ("🌧️", "Showers"), 82: ("⛈️", "Violent showers"),
    85: ("🌨️", "Light snow showers"), 86: ("❄️", "Snow showers"),
    95: ("⛈️", "Thunderstorm"), 96: ("⛈️", "Thunderstorm with hail"),
    99: ("⛈️", "Thunderstorm with heavy hail"),
}

# European AQI; each upper edge belongs to its band (20 is Good).
AQI_BANDS = ((20, "Good"), (40, "Fair"), (60, "Moderate"), (80, "Poor"), (100, "Very poor"))


def weather(code: int) -> tuple[str, str]:
    return WEATHER.get(code, ("🌡️", "Unknown"))


def aqi_band(value: float) -> str:
    for upper, name in AQI_BANDS:
        if value <= upper:
            return name
    return "Extremely poor"


def day_index(forecast: dict, day: date) -> int:
    """Index of `day` in the daily arrays; 0 when the bot's TZ and the city's
    calendar disagree."""
    try:
        return forecast["daily"]["time"].index(day.isoformat())
    except ValueError:
        return 0


def _today(times: list[str], values: list, day: date) -> list[tuple[int, object]]:
    prefix = day.isoformat()
    return [(int(t[11:13]), v) for t, v in zip(times, values) if t.startswith(prefix)]


def rain_window(times: list[str], probs: list, day: date) -> str:
    """The first run of hours at or above WET %, as 'HH:00–HH:00'."""
    start = end = None
    for hour, p in _today(times, probs, day):
        wet = p is not None and p >= WET
        if wet and start is None:
            start = hour
        if start is not None:
            if not wet:
                break
            end = hour + 1
    if start is None:
        return "Dry all day"
    stop = "midnight" if end == 24 else f"{end:02d}:00"
    return f"Rain likely {start:02d}:00–{stop}"


def aqi_line(air: dict | None, day: date) -> str:
    if not air:
        return "Air: no reading today"
    values = [v for _, v in _today(air["hourly"]["time"], air["hourly"]["european_aqi"], day)
              if v is not None]
    if not values:
        return "Air: no reading today"
    worst = max(values)
    return f"Air: up to AQI {round(worst)} · {aqi_band(worst)}"


def _r(v) -> str:
    return "–" if v is None else str(round(v))


def caption(forecast: dict, air: dict | None, label: str, units: str, day: date) -> str:
    d, u = forecast["daily"], UNIT_LABELS[units]
    i = day_index(forecast, day)
    shown = date.fromisoformat(d["time"][i])
    emoji, _ = weather(d["weather_code"][i])
    lines = [
        f"{emoji} {html.escape(label)} · {shown:%A} {shown.day} {shown:%B}",
        f"{_r(d['temperature_2m_min'][i])}–{_r(d['temperature_2m_max'][i])} {u['temp']} · "
        f"rain chance {_r(d['precipitation_probability_max'][i])} % · "
        f"wind up to {_r(d['wind_speed_10m_max'][i])} {u['wind']}",
        rain_window(forecast["hourly"]["time"], forecast["hourly"]["precipitation_probability"],
                    shown),
        aqi_line(air, shown),
    ]
    if i + 1 < len(d["time"]):
        p = d["precipitation_probability_max"][i + 1]
        outlook = (f"showers likely ({p} %)" if p is not None and p >= WET
                   else weather(d["weather_code"][i + 1])[1].lower())
        lines.append(f"Tomorrow: {_r(d['temperature_2m_min'][i + 1])}–"
                     f"{_r(d['temperature_2m_max'][i + 1])} {u['temp']}, {outlook}")
    lines.append(CREDIT)
    return fit("\n".join(lines))


def fit(text: str, limit: int = CAPTION_MAX) -> str:
    """At most `limit` characters, cut at a line boundary; the credit stays."""
    if len(text) <= limit:
        return text
    *body, last = text.split("\n")
    while body and len("\n".join([*body, last])) > limit:
        body.pop()
    if not body:  # one enormous first line: cut it, keep the credit
        return text.split("\n")[0][: limit - len(last) - 2] + "…\n" + last
    return "\n".join([*body, last])
