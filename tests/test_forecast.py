import httpx
import pytest

from tgforecast import forecast as fc

GRAZ = fc.Place("Graz", "Styria", "AT", 47.067, 15.45)


async def test_geocode_takes_the_first_result(routes):
    async with httpx.AsyncClient() as http:
        place = await fc.geocode(http, "Vienna")
    assert place.name == "Vienna" and place.country_code == "AT"


async def test_geocode_with_no_result_is_an_error(routes):
    routes["geocode"].mock(return_value=httpx.Response(200, json={}))
    async with httpx.AsyncClient() as http:
        with pytest.raises(fc.FetchError, match="Nowhere"):
            await fc.geocode(http, "Nowhere")


async def test_forecast_request_parameters(routes):
    async with httpx.AsyncClient() as http:
        await fc.fetch(http, GRAZ, "imperial")
    sent = routes["forecast"].calls.last.request.url.params
    assert sent["forecast_days"] == "2" and sent["timezone"] == "auto"
    assert "precipitation_probability" in sent["hourly"]
    assert sent["temperature_unit"] == "fahrenheit"


async def test_air_failure_does_not_stop_the_forecast(routes):
    routes["air"].mock(return_value=httpx.Response(503))
    async with httpx.AsyncClient() as http:
        forecast, air = await fc.fetch(http, GRAZ, "metric")
    assert "daily" in forecast and air is None


async def test_forecast_timeout_is_a_fetch_error(routes):
    routes["forecast"].mock(side_effect=httpx.ReadTimeout("slow"))
    async with httpx.AsyncClient() as http:
        with pytest.raises(fc.FetchError):
            await fc.fetch(http, GRAZ, "metric")
