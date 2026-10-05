"""Developer tasks. List them with `uv run inv --list`."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from invoke import task

ROOT = Path(__file__).parent
FIXTURES = ROOT / "tests" / "fixtures"


@task
def fixtures(c):
    """Record real Open-Meteo responses for Vienna for the offline tests."""
    from tgforecast import forecast as fc

    FIXTURES.mkdir(parents=True, exist_ok=True)

    def save(name: str, url: str, params: dict) -> dict:
        data = httpx.get(url, params=params, timeout=30).raise_for_status().json()
        (FIXTURES / f"{name}.json").write_text(json.dumps(data, indent=1) + "\n")
        print(f"wrote tests/fixtures/{name}.json")
        return data

    r = save("geocode_vienna", fc.GEOCODE, fc.geocode_params("Vienna"))["results"][0]
    vienna = fc.Place(r["name"], r.get("admin1", ""), r.get("country_code", ""),
                      r["latitude"], r["longitude"])
    save("forecast_vienna", fc.FORECAST, fc.forecast_params(vienna, "metric"))
    save("air_vienna", fc.AIR, fc.air_params(vienna))
