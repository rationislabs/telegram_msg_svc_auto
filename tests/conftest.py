import json
from pathlib import Path

import httpx
import pytest
import respx

from tgforecast import forecast as fc

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fx():
    """Load a recorded response; a fresh copy each call, so tests may edit it."""
    return lambda name: json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture
def routes(fx):
    """Every Open-Meteo endpoint answered from recordings. Make one fail with
    routes["air"].mock(return_value=httpx.Response(500))."""
    with respx.mock(assert_all_called=False) as router:
        router.get(fc.GEOCODE, name="geocode").mock(
            return_value=httpx.Response(200, json=fx("geocode_vienna")))
        router.get(fc.FORECAST, name="forecast").mock(
            return_value=httpx.Response(200, json=fx("forecast_vienna")))
        router.get(fc.AIR, name="air").mock(
            return_value=httpx.Response(200, json=fx("air_vienna")))
        yield router
