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


VIENNA = fc.Place("Vienna", "Vienna", "AT", 48.20849, 16.37208)


async def test_forecast_days_and_no_air(routes):
    async with httpx.AsyncClient() as http:
        forecast, air = await fc.fetch(http, VIENNA, "metric", days=7, with_air=False)
    assert routes["forecast"].calls.last.request.url.params["forecast_days"] == "7"
    assert air is None and not routes["air"].called


def test_stage1_request_defaults_unchanged():
    assert fc.forecast_params(VIENNA, "metric")["forecast_days"] == 2
    assert fc.geocode_params("Vienna") == {
        "name": "Vienna",
        "count": 1,
        "language": "en",
        "format": "json",
    }


async def test_search_asks_for_ten_results_in_the_language(routes):
    async with httpx.AsyncClient() as http:
        place = await fc.search(http, "Vienna", language="de")
    params = routes["geocode"].calls.last.request.url.params
    assert (params["count"], params["language"], params["name"]) == ("10", "de", "Vienna")
    assert place.name == "Vienna"  # the recording is English; the language only goes in the request


async def test_search_qualifier_picks_the_match(routes, fx):
    routes["geocode"].mock(return_value=httpx.Response(200, json=fx("geocode_paris")))
    async with httpx.AsyncClient() as http:
        first = await fc.search(http, "Paris")
        texas = await fc.search(http, "Paris", "texas")
        us = await fc.search(http, "Paris", "US")
        miss = await fc.search(http, "Paris", "Atlantis")
    assert first.country_code == "FR"
    assert texas.admin1 == "Texas" and texas.country_code == "US"
    assert us.country_code == "US"
    assert miss == first


async def test_search_with_no_result_is_not_found(routes):
    routes["geocode"].mock(return_value=httpx.Response(200, json={}))
    async with httpx.AsyncClient() as http:
        with pytest.raises(fc.NotFound):
            await fc.search(http, "Xyzzy")


def test_not_found_is_still_a_fetch_error():
    assert issubclass(fc.NotFound, fc.FetchError)  # stage 1 catches FetchError
