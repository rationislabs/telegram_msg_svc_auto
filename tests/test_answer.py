from datetime import UTC, datetime, timedelta

import httpx
import pytest

from tgforecast import chart, i18n
from tgforecast.answer import Answerer, Reply, Throttle, TTLCache
from tgforecast.ask import Ask


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def local_instant(forecast: dict, hour: int) -> datetime:
    """The UTC instant that is `hour`:00 on the recording's first day, in its own time zone."""
    first = datetime.fromisoformat(forecast["daily"]["time"][0])
    return (
        first + timedelta(hours=hour) - timedelta(seconds=forecast["utc_offset_seconds"])
    ).replace(tzinfo=UTC)


def is_png(data: bytes | None) -> bool:
    return bool(data) and data[:8] == b"\x89PNG\r\n\x1a\n"


def test_cache_expires_and_is_capped():
    clock = Clock()
    cache = TTLCache(ttl=900, size=2, clock=clock)
    cache.put("a", 1)
    assert cache.get("a") == 1
    clock.t += 901
    assert cache.get("a") is None
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    assert cache.get("a") is None and cache.get("b") == 2 and cache.get("c") == 3


def test_throttle_notes_once_then_stays_quiet_until_the_minute_passes():
    clock = Clock()
    gate = Throttle(limit=10, window=60, chats=100, clock=clock)
    assert [gate.check(1) for _ in range(10)] == ["ok"] * 10
    assert gate.check(1) == "note"
    assert gate.check(1) == "quiet"
    assert gate.check(2) == "ok"  # other chats are not affected
    clock.t += 61
    assert gate.check(1) == "ok"
    for _ in range(9):
        gate.check(1)
    assert gate.check(1) == "note"  # a fresh minute earns a fresh note


def test_throttle_forgets_the_oldest_chat_beyond_its_cap():
    clock = Clock()
    gate = Throttle(limit=1, window=60, chats=2, clock=clock)
    gate.check(1)
    gate.check(2)
    gate.check(3)
    assert len(gate._chats) == 2
    assert gate.check(1) == "ok"  # forgotten, so allowed again


async def test_help_and_bad_need_no_network():
    async with httpx.AsyncClient() as http:
        a = Answerer(http)
        assert await a.reply(Ask("help", "fr")) == Reply(i18n.help_text("fr"), status="help")
        assert await a.reply(Ask("bad", "es")) == Reply(i18n.t("es", "bad_city"), status="bad")


async def test_now_is_a_photo_with_the_localised_caption(routes, fx):
    forecast = fx("forecast_vienna")
    async with httpx.AsyncClient() as http:
        r = await Answerer(http, utcnow=lambda: local_instant(forecast, 9)).reply(
            Ask("now", "de", "Wien")
        )
    assert r.status == "ok" and is_png(r.photo)
    assert "Regenrisiko" in r.text and r.text.split("\n")[0].count("Vienna") >= 1
    assert routes["geocode"].calls.last.request.url.params["language"] == "de"


async def test_week_is_a_photo_with_seven_lines_and_no_air_call(routes, fx):
    routes["forecast"].mock(return_value=httpx.Response(200, json=fx("forecast_vienna_week")))
    async with httpx.AsyncClient() as http:
        r = await Answerer(http).reply(Ask("week", "en", "Vienna"))
    assert r.status == "ok" and is_png(r.photo)
    assert len(r.text.split("\n")) == 9
    assert routes["forecast"].calls.last.request.url.params["forecast_days"] == "7"
    assert not routes["air"].called


async def test_today_is_the_citys_own_date(routes, fx, monkeypatch):
    auckland = fx("forecast_auckland")
    routes["forecast"].mock(return_value=httpx.Response(200, json=auckland))
    seen = {}
    real = chart.render
    monkeypatch.setattr(chart, "render", lambda *a, **k: seen.update(k) or real(*a, **k))
    # 01:00 on day 0 in Auckland is still the day before in Vienna and in UTC
    async with httpx.AsyncClient() as http:
        r = await Answerer(http, utcnow=lambda: local_instant(auckland, 1)).reply(
            Ask("now", "en", "Auckland")
        )
    day0 = datetime.fromisoformat(auckland["daily"]["time"][0]).date()
    assert i18n.date_long(day0, "en") in r.text.split("\n")[0]
    assert seen["mark_hour"] == 1.0


async def test_west_of_utc_late_evening_is_still_today(routes, fx):
    forecast = fx("forecast_vienna")
    forecast["utc_offset_seconds"] = -5 * 3600  # as if in New York
    routes["forecast"].mock(return_value=httpx.Response(200, json=forecast))
    async with httpx.AsyncClient() as http:
        r = await Answerer(http, utcnow=lambda: local_instant(forecast, 23)).reply(
            Ask("now", "en", "X")
        )
    day0 = datetime.fromisoformat(forecast["daily"]["time"][0]).date()
    assert i18n.date_long(day0, "en") in r.text.split("\n")[0]


async def test_unknown_place_is_named_and_escaped(routes):
    routes["geocode"].mock(return_value=httpx.Response(200, json={}))
    async with httpx.AsyncClient() as http:
        r = await Answerer(http).reply(Ask("now", "en", "<b>Xyz</b>"))
    assert r == Reply(
        "I don't know a place called '&lt;b&gt;Xyz&lt;/b&gt;'.", status="unknown_place"
    )


@pytest.mark.parametrize("route", ["geocode", "forecast"])
async def test_open_meteo_down_is_the_outage_reply(routes, route):
    routes[route].mock(return_value=httpx.Response(503))
    async with httpx.AsyncClient() as http:
        r = await Answerer(http).reply(Ask("now", "it", "Roma"))
    assert r == Reply(i18n.t("it", "outage"), status="outage")


async def test_a_malformed_forecast_is_the_outage_reply(routes):
    routes["forecast"].mock(return_value=httpx.Response(200, json={"daily": {}}))
    async with httpx.AsyncClient() as http:
        r = await Answerer(http).reply(Ask("week", "en", "Vienna"))
    assert r.status == "outage"


async def test_a_failing_chart_sends_the_caption_alone(routes, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no fonts")

    monkeypatch.setattr(chart, "render", boom)
    async with httpx.AsyncClient() as http:
        r = await Answerer(http).reply(Ask("now", "en", "Vienna"))
    assert r.photo is None and r.status == "no_chart" and "rain chance" in r.text


async def test_the_second_question_is_served_from_the_cache(routes):
    async with httpx.AsyncClient() as http:
        a = Answerer(http)
        await a.reply(Ask("now", "en", "Vienna"))
        await a.reply(Ask("now", "en", "vienna"))
    assert routes["geocode"].call_count == 1 and routes["forecast"].call_count == 1


@pytest.mark.parametrize("body", [{"results": [{}]}, {"results": "x"}, []])
async def test_a_malformed_place_answer_is_the_outage_reply(routes, body):
    routes["geocode"].mock(return_value=httpx.Response(200, json=body))
    async with httpx.AsyncClient() as http:
        r = await Answerer(http).reply(Ask("now", "en", "Vienna"))
    assert r.status == "outage"


async def test_a_forecast_that_is_not_an_object_is_the_outage_reply(routes):
    routes["forecast"].mock(return_value=httpx.Response(200, json=[1, 2]))
    async with httpx.AsyncClient() as http:
        r = await Answerer(http).reply(Ask("now", "en", "Vienna"))
    assert r.status == "outage"
