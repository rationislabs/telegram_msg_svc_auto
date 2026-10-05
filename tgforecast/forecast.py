"""Open-Meteo: geocoding once at start, then forecast and air quality each
morning. Air quality is optional — the post goes out without it."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"
AIR = "https://air-quality-api.open-meteo.com/v1/air-quality"
TIMEOUT = 10.0
UNIT_PARAMS: dict[str, dict[str, str]] = {
    "metric": {},
    "imperial": {"temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
                 "precipitation_unit": "inch"},
}

log = logging.getLogger(__name__)


class FetchError(Exception):
    """Open-Meteo did not give a usable answer."""


@dataclass(frozen=True)
class Place:
    name: str
    admin1: str
    country_code: str
    latitude: float
    longitude: float

    @property
    def label(self) -> str:
        return ", ".join(p for p in (self.name, self.admin1, self.country_code) if p)


def geocode_params(name: str) -> dict[str, Any]:
    return {"name": name, "count": 1, "language": "en", "format": "json"}


def forecast_params(place: Place, units: str) -> dict[str, Any]:
    return {
        "latitude": place.latitude, "longitude": place.longitude,
        "timezone": "auto", "forecast_days": 2,
        "hourly": "temperature_2m,precipitation_probability,weather_code",
        "daily": "temperature_2m_min,temperature_2m_max,precipitation_probability_max,"
                 "wind_speed_10m_max,weather_code",
        **UNIT_PARAMS[units],
    }


def air_params(place: Place) -> dict[str, Any]:
    return {"latitude": place.latitude, "longitude": place.longitude,
            "timezone": "auto", "forecast_days": 1, "hourly": "european_aqi"}


async def _get_json(http: httpx.AsyncClient, url: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        r = await http.get(url, params=params, timeout=TIMEOUT)
    except httpx.HTTPError as e:
        raise FetchError(f"{url}: {e.__class__.__name__}") from None
    if r.status_code >= 400:
        raise FetchError(f"{url}: HTTP {r.status_code}")
    try:
        return r.json()
    except ValueError:
        raise FetchError(f"{url}: response is not JSON") from None


async def geocode(http: httpx.AsyncClient, name: str) -> Place:
    results = (await _get_json(http, GEOCODE, geocode_params(name))).get("results") or []
    if not results:
        raise FetchError(f"no place called {name!r}")
    r = results[0]
    return Place(r["name"], r.get("admin1", ""), r.get("country_code", ""),
                 r["latitude"], r["longitude"])


async def fetch(http: httpx.AsyncClient, place: Place, units: str) -> tuple[dict, dict | None]:
    forecast = await _get_json(http, FORECAST, forecast_params(place, units))
    try:
        air = await _get_json(http, AIR, air_params(place))
    except FetchError as e:
        log.warning("air quality unavailable, posting without it: %s", e)
        air = None
    return forecast, air
