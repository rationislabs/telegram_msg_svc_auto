"""Forecast JSON in, caption text out. Pure: no network, no Telegram.

Telegram allows 1024 characters on a photo caption, sent as HTML; every name
interpolated here is escaped, and the Open-Meteo credit (required by their
licence) is always the last line.
"""

from __future__ import annotations

import html
from datetime import date

from . import i18n

CAPTION_MAX = 1024
CREDIT = '<a href="https://open-meteo.com/">Weather data by Open-Meteo.com</a>'
UNIT_LABELS = {"metric": {"temp": "°C", "wind": "km/h"}, "imperial": {"temp": "°F", "wind": "mph"}}
WET = 50  # % precipitation probability that counts as "rain likely"

# WMO weather interpretation codes, as Open-Meteo documents them.
WEATHER: dict[int, tuple[str, str]] = {
    0: ("☀️", "Clear sky"),
    1: ("🌤️", "Mainly clear"),
    2: ("⛅", "Partly cloudy"),
    3: ("☁️", "Overcast"),
    45: ("🌫️", "Fog"),
    48: ("🌫️", "Freezing fog"),
    51: ("🌦️", "Light drizzle"),
    53: ("🌦️", "Drizzle"),
    55: ("🌦️", "Dense drizzle"),
    56: ("🌧️", "Light freezing drizzle"),
    57: ("🌧️", "Freezing drizzle"),
    61: ("🌧️", "Light rain"),
    63: ("🌧️", "Rain"),
    65: ("🌧️", "Heavy rain"),
    66: ("🌧️", "Light freezing rain"),
    67: ("🌧️", "Freezing rain"),
    71: ("🌨️", "Light snow"),
    73: ("🌨️", "Snow"),
    75: ("❄️", "Heavy snow"),
    77: ("🌨️", "Snow grains"),
    80: ("🌦️", "Light showers"),
    81: ("🌧️", "Showers"),
    82: ("⛈️", "Violent showers"),
    85: ("🌨️", "Light snow showers"),
    86: ("❄️", "Snow showers"),
    95: ("⛈️", "Thunderstorm"),
    96: ("⛈️", "Thunderstorm with hail"),
    99: ("⛈️", "Thunderstorm with heavy hail"),
}

# European AQI; each upper edge belongs to its band (20 is Good). Names in i18n.AQI_NAMES.
AQI_EDGES = (20, 40, 60, 80, 100)


def weather(code: int, lang: str = "en") -> tuple[str, str]:
    emoji, text = WEATHER.get(code, ("🌡️", "Unknown"))
    if lang != "en":
        text = i18n.WEATHER_TEXT[lang].get(code, i18n.t(lang, "unknown"))
    return emoji, text


def aqi_band(value: float, lang: str = "en") -> str:
    names = i18n.AQI_NAMES[lang]
    for i, upper in enumerate(AQI_EDGES):
        if value <= upper:
            return names[i]
    return names[-1]


def day_index(forecast: dict, day: date) -> int:
    """Index of `day` in the daily arrays; 0 when the bot's TZ and the city's
    calendar disagree."""
    try:
        return forecast["daily"]["time"].index(day.isoformat())
    except ValueError:
        return 0


def _today(times: list[str], values: list, day: date) -> list[tuple[int, object]]:
    prefix = day.isoformat()
    return [(int(t[11:13]), v) for t, v in zip(times, values, strict=False) if t.startswith(prefix)]


def rain_window(times: list[str], probs: list, day: date, lang: str = "en") -> str:
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
        return i18n.t(lang, "dry")
    stop = i18n.t(lang, "midnight") if end == 24 else f"{end:02d}:00"
    return i18n.t(lang, "rain_window", start=f"{start:02d}:00", stop=stop)


def aqi_line(air: dict | None, day: date, lang: str = "en") -> str:
    if not air:
        return i18n.t(lang, "air_none")
    values = [
        v
        for _, v in _today(air["hourly"]["time"], air["hourly"]["european_aqi"], day)
        if v is not None
    ]
    if not values:
        return i18n.t(lang, "air_none")
    worst = max(values)
    return i18n.t(lang, "air", aqi=round(worst), band=aqi_band(worst, lang))


def _r(v) -> str:
    return "–" if v is None else str(round(v))


def caption(
    forecast: dict, air: dict | None, label: str, units: str, day: date, lang: str = "en"
) -> str:
    d, u = forecast["daily"], UNIT_LABELS[units]
    i = day_index(forecast, day)
    shown = date.fromisoformat(d["time"][i])
    emoji, _ = weather(d["weather_code"][i])
    lines = [
        f"{emoji} {html.escape(label)} · {i18n.date_long(shown, lang)}",
        f"{_r(d['temperature_2m_min'][i])}–{_r(d['temperature_2m_max'][i])} {u['temp']} · "
        + i18n.t(lang, "rain_chance", p=_r(d["precipitation_probability_max"][i]))
        + " · "
        + i18n.t(lang, "wind_up_to", v=_r(d["wind_speed_10m_max"][i]), unit=u["wind"]),
        rain_window(
            forecast["hourly"]["time"],
            forecast["hourly"]["precipitation_probability"],
            shown,
            lang,
        ),
        aqi_line(air, shown, lang),
    ]
    if i + 1 < len(d["time"]):
        p = d["precipitation_probability_max"][i + 1]
        if p is not None and p >= WET:
            outlook = i18n.t(lang, "showers", p=p)
        else:
            outlook = weather(d["weather_code"][i + 1], lang)[1]
            if lang != "de":  # German nouns keep their capital
                outlook = outlook.lower()
        lines.append(
            i18n.t(
                lang,
                "tomorrow",
                low=_r(d["temperature_2m_min"][i + 1]),
                high=_r(d["temperature_2m_max"][i + 1]),
                unit=u["temp"],
                outlook=outlook,
            )
        )
    lines.append(CREDIT)
    return fit("\n".join(lines))


def week_caption(forecast: dict, label: str, units: str, lang: str = "en") -> str:
    """One line per day of the forecast, the place first, the credit last."""
    d, u = forecast["daily"], UNIT_LABELS[units]
    lines = [i18n.t(lang, "week_title", label=html.escape(label))]
    for i, day in enumerate(d["time"]):
        lines.append(
            i18n.t(
                lang,
                "week_line",
                day=i18n.week_day(date.fromisoformat(day), lang),
                emoji=weather(d["weather_code"][i])[0],
                low=_r(d["temperature_2m_min"][i]),
                high=_r(d["temperature_2m_max"][i]),
                unit=u["temp"],
                p=_r(d["precipitation_probability_max"][i]),
                w=_r(d["wind_speed_10m_max"][i]),
                wunit=u["wind"],
            )
        )
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
