import logging
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from telegram.error import Forbidden, InvalidToken
from telegram.ext import Application, MessageHandler
from telegram.ext._utils import webhookhandler

from tgforecast import answer, chart, config, i18n
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


def vienna_now(fx, hour: int = 9):
    forecast = fx("forecast_vienna")
    return lambda: local_instant(forecast, hour)


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
    assert gate.check(1) == "ok"  # forgotten, so allowed again
    assert gate.check(3) == "note"  # the newest is remembered


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
        r = await Answerer(http, utcnow=vienna_now(fx)).reply(Ask("week", "en", "Vienna"))
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


async def test_a_failing_chart_sends_the_caption_alone(routes, fx, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no fonts")

    monkeypatch.setattr(chart, "render", boom)
    async with httpx.AsyncClient() as http:
        r = await Answerer(http, utcnow=vienna_now(fx)).reply(Ask("now", "en", "Vienna"))
    assert r.photo is None and r.status == "no_chart" and "rain chance" in r.text


async def test_the_second_question_is_served_from_the_cache(routes, fx):
    async with httpx.AsyncClient() as http:
        a = Answerer(http, utcnow=vienna_now(fx))
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


async def test_a_malformed_forecast_is_not_cached(routes, fx):
    routes["forecast"].mock(
        side_effect=[
            httpx.Response(200, json={"daily": {}}),
            httpx.Response(200, json=fx("forecast_vienna")),
        ]
    )
    async with httpx.AsyncClient() as http:
        a = Answerer(http, utcnow=vienna_now(fx))
        first = await a.reply(Ask("now", "en", "Vienna"))
        second = await a.reply(Ask("now", "en", "Vienna"))
    assert (first.status, second.status) == ("outage", "ok")
    assert routes["forecast"].call_count == 2


@pytest.mark.parametrize("body", [{"hourly": {}}, []])
async def test_a_malformed_air_answer_costs_only_the_air_line(routes, fx, body):
    routes["air"].mock(return_value=httpx.Response(200, json=body))
    async with httpx.AsyncClient() as http:
        r = await Answerer(http, utcnow=vienna_now(fx)).reply(Ask("now", "en", "Vienna"))
    assert r.status == "ok" and i18n.t("en", "air_none") in r.text


async def test_a_forecast_timeout_is_the_outage_reply(routes):
    routes["forecast"].mock(side_effect=httpx.ReadTimeout("t"))
    async with httpx.AsyncClient() as http:
        r = await Answerer(http).reply(Ask("now", "en", "Vienna"))
    assert r.status == "outage"


async def test_a_qualifier_picks_the_place(routes, fx):
    routes["geocode"].mock(return_value=httpx.Response(200, json=fx("geocode_paris")))
    async with httpx.AsyncClient() as http:
        r = await Answerer(http, utcnow=vienna_now(fx)).reply(Ask("now", "en", "Paris", "Texas"))
    assert "Texas" in r.text.split("\n")[0]


async def test_now_and_week_for_one_city_do_not_share_a_cache_entry(routes, fx):
    async with httpx.AsyncClient() as http:
        a = Answerer(http, utcnow=vienna_now(fx))
        await a.reply(Ask("now", "en", "Vienna"))
        routes["forecast"].mock(return_value=httpx.Response(200, json=fx("forecast_vienna_week")))
        await a.reply(Ask("week", "en", "Vienna"))
    assert routes["forecast"].call_count == 2
    assert routes["forecast"].calls.last.request.url.params["forecast_days"] == "7"


class FakeBot:
    username = "WeatherAnswerBot"

    def __init__(self, error: Exception | None = None):
        self.sent: list[tuple[str, dict]] = []
        self.error = error

    async def send_photo(self, **kw):
        if self.error:
            raise self.error
        self.sent.append(("photo", kw))

    async def send_message(self, **kw):
        if self.error:
            raise self.error
        self.sent.append(("message", kw))


def data_for(http, fx, **throttle):
    return {"answerer": Answerer(http, utcnow=vienna_now(fx)), "throttle": Throttle(**throttle)}


async def test_handle_answers_and_logs_no_text_or_chat(routes, fx, caplog):
    caplog.set_level(logging.INFO, logger="tgforecast")
    bot = FakeBot()
    async with httpx.AsyncClient() as http:
        await answer.handle(bot, data_for(http, fx), 4242, "/now Vienna", "en", True)
    kind, kw = bot.sent[0]
    assert kind == "photo" and kw["chat_id"] == 4242 and kw["parse_mode"] == "HTML"
    assert "now ok" in caplog.text
    assert "Vienna" not in caplog.text and "4242" not in caplog.text


async def test_handle_ignores_plain_text_in_groups(fx):
    bot = FakeBot()
    async with httpx.AsyncClient() as http:
        await answer.handle(bot, data_for(http, fx), 1, "Vienna", "en", False)
    assert bot.sent == []


async def test_handle_throttles_with_one_note(fx):
    bot = FakeBot()
    async with httpx.AsyncClient() as http:
        data = data_for(http, fx)
        for _ in range(12):
            await answer.handle(bot, data, 7, "/help", "en", True)
    texts = [kw["text"] for _, kw in bot.sent]
    assert len(texts) == 11 and texts[-1] == i18n.t("en", "throttled")


async def test_handle_crash_sends_a_generic_reply_and_logs_only_the_type(caplog):
    class Broken:
        async def reply(self, ask):
            raise RuntimeError("Graz secret detail")

    caplog.set_level(logging.INFO, logger="tgforecast")
    bot = FakeBot()
    await answer.handle(
        bot, {"answerer": Broken(), "throttle": Throttle()}, 9, "/now Graz", "de", True
    )
    assert bot.sent[0][1]["text"] == i18n.t("de", "crash")
    assert "RuntimeError" in caplog.text and "Graz" not in caplog.text


async def test_handle_survives_telegram_refusing_the_reply(fx, caplog):
    bot = FakeBot(error=Forbidden("bot was blocked by the user"))
    async with httpx.AsyncClient() as http:
        await answer.handle(bot, data_for(http, fx), 9, "/help", "en", True)
    assert "Forbidden" in caplog.text


async def test_on_message_reads_the_update(fx):
    bot = FakeBot()
    async with httpx.AsyncClient() as http:
        update = SimpleNamespace(
            effective_message=SimpleNamespace(
                text="/hilfe", chat_id=5, chat=SimpleNamespace(type="private")
            ),
            effective_user=SimpleNamespace(language_code="en"),
        )
        context = SimpleNamespace(bot=bot, application=SimpleNamespace(bot_data=data_for(http, fx)))
        await answer.on_message(update, context)
    assert bot.sent[0][1]["text"] == i18n.help_text("de")


async def test_a_crash_before_the_answer_step_still_gets_a_reply(caplog):
    class Broken:
        def check(self, chat_id):
            raise RuntimeError("Graz secret detail")

    caplog.set_level(logging.INFO, logger="tgforecast")
    bot = FakeBot()
    await answer.handle(bot, {"answerer": None, "throttle": Broken()}, 9, "/jetzt Graz", "en", True)
    assert bot.sent[0][1]["text"] == i18n.t("de", "crash")
    assert "RuntimeError" in caplog.text and "Graz" not in caplog.text


async def test_a_crash_inside_parse_replies_in_english(monkeypatch, caplog):
    def boom(*a):
        raise RuntimeError("x")

    monkeypatch.setattr(answer, "parse", boom)
    bot = FakeBot()
    await answer.handle(bot, {}, 9, "/now Graz", "de", True)
    assert bot.sent[0][1]["text"] == i18n.t("en", "crash")


def test_menus_per_language():
    menus = dict(answer.menus())
    assert set(menus) == {None, "de", "it", "fr", "es"}
    assert [c for c, _ in menus["de"]] == ["jetzt", "woche", "hilfe"]
    assert [c for c, _ in menus[None]] == ["now", "week", "help"]
    assert all(1 <= len(d) <= 256 for m in menus.values() for _, d in m)


@pytest.fixture
def restore_logging():
    names = ("httpx", "telegram", webhookhandler._LOGGER.name)
    saved = [(lg, lg.level, lg.filters[:]) for lg in map(logging.getLogger, names)]
    yield
    for lg, level, filters in saved:
        lg.setLevel(level)
        lg.filters[:] = filters


def test_configure_logging_quiets_the_libraries_that_log_the_token(restore_logging):
    answer.configure_logging()
    for name in ("httpx", "telegram"):
        assert logging.getLogger(name).level == logging.WARNING


def test_configure_logging_drops_the_raw_update_record_only(restore_logging, caplog):
    answer.configure_logging()
    lg = webhookhandler._LOGGER
    # the format string python-telegram-bot uses when Update.de_json fails
    lg.critical(
        "Something went wrong processing the data received from Telegram. "
        "Received data was *not* processed! Received data was: %r",
        {"message": {"text": "Graz secret"}},
    )
    lg.critical("something else broke")
    # the polling path (telegram/ext/_updater.py) carries no data and stays visible
    lg.critical(
        "Something went wrong processing the data received from Telegram. "
        "Received data was *not* processed!"
    )
    assert "Graz" not in caplog.text and "Received data was:" not in caplog.text
    assert "something else broke" in caplog.text and "*not* processed!" in caplog.text


class FakeApp:
    def __init__(self):
        self.calls = []

    def run_webhook(self, **kw):
        self.calls.append(("webhook", kw))

    def run_polling(self, **kw):
        self.calls.append(("polling", kw))


@pytest.fixture
def fake_main(monkeypatch):
    app = FakeApp()
    monkeypatch.setattr(answer, "configure_logging", lambda: None)
    monkeypatch.setattr(answer.stage1, "wait_for_telegram", lambda token: None)
    monkeypatch.setattr(answer, "build", lambda settings: app)
    for name in ("RENDER_EXTERNAL_URL", "WEBHOOK_SECRET", "PORT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ANSWER_BOT_TOKEN", "456:def")
    return app


def test_main_serves_the_webhook_on_render(fake_main, monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://answer.onrender.com")
    monkeypatch.setenv("WEBHOOK_SECRET", "s3cret")
    monkeypatch.setenv("PORT", "8123")
    assert answer.main() == 0
    secret = config.load_answer().secret
    assert fake_main.calls == [
        (
            "webhook",
            {
                "listen": "0.0.0.0",
                "port": 8123,
                "url_path": "telegram",
                "webhook_url": "https://answer.onrender.com/telegram",
                "secret_token": secret,
                "allowed_updates": ["message"],
                "drop_pending_updates": False,
            },
        )
    ]


def test_main_long_polls_without_a_url(fake_main):
    assert answer.main() == 0
    assert fake_main.calls == [("polling", {"allowed_updates": ["message"]})]


def test_main_rejected_token_is_one_line_not_a_traceback(fake_main, monkeypatch, capsys):
    def reject(token):
        raise InvalidToken("nope")

    monkeypatch.setattr(answer.stage1, "wait_for_telegram", reject)
    assert answer.main() == 1
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and "ANSWER_BOT_TOKEN rejected" in err


def test_build_wires_one_message_handler_and_an_error_handler():
    app = answer.build(config.AnswerSettings(token="123:abc", webhook_url="", secret="", port=1))
    assert isinstance(app, Application)
    handlers = [h for group in app.handlers.values() for h in group]
    assert len(handlers) == 1 and isinstance(handlers[0], MessageHandler)
    assert answer.on_error in app.error_handlers


def test_python_m_tgforecast_answer_needs_its_token():
    env = {k: v for k, v in os.environ.items() if k != "ANSWER_BOT_TOKEN"}
    p = subprocess.run(
        [sys.executable, "-m", "tgforecast", "answer"], env=env, capture_output=True, text=True
    )
    assert p.returncode == 1 and "ANSWER_BOT_TOKEN is not set" in p.stderr


async def test_handle_answers_each_city_in_a_list(routes, fx):
    bot = FakeBot()
    async with httpx.AsyncClient() as http:
        await answer.handle(bot, data_for(http, fx), 3, "/now Vienna; Vienna, AT", "en", True)
    assert [kind for kind, _ in bot.sent] == ["photo", "photo"]


async def test_handle_says_when_a_list_is_too_long(fx):
    bot = FakeBot()
    async with httpx.AsyncClient() as http:
        await answer.handle(bot, data_for(http, fx), 3, "/now Aa; Bb; Cc; Dd; Ee; Ff", "en", True)
    assert [kw["text"] for _, kw in bot.sent] == [i18n.t("en", "too_many")]


async def test_each_city_counts_against_the_throttle(routes, fx):
    bot = FakeBot()
    async with httpx.AsyncClient() as http:
        data = data_for(http, fx, limit=2)
        await answer.handle(bot, data, 3, "/now Vienna; Vienna; Vienna; Vienna", "en", True)
    assert [kind for kind, _ in bot.sent] == ["photo", "photo", "message"]
    assert bot.sent[-1][1]["text"] == i18n.t("en", "throttled")


def test_descriptions_per_language_fit_telegram():
    found = {code: (short, long) for code, short, long in answer.descriptions()}
    assert set(found) == {None, "de", "it", "fr", "es"}
    for short, long in found.values():
        assert 1 <= len(short) <= 120 and 1 <= len(long) <= 512
        assert "<" not in short + long  # Telegram shows descriptions as plain text


async def test_start_sets_menus_and_descriptions_per_language():
    calls = set()

    class Bot:
        async def set_my_commands(self, commands, language_code=None):
            calls.add(("commands", language_code))

        async def set_my_description(self, description, language_code=None):
            calls.add(("description", language_code))

        async def set_my_short_description(self, short_description, language_code=None):
            calls.add(("short", language_code))

    app = SimpleNamespace(bot=Bot(), bot_data={})
    await answer._start(app)
    await app.bot_data["http"].aclose()
    codes = (None, "de", "it", "fr", "es")
    assert calls == {(k, c) for k in ("commands", "description", "short") for c in codes}
