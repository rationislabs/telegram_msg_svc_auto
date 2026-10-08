"""The scheduler side: one Runner ticked every minute decides everything, so a
laptop that slept through POST_AT posts on its next tick, a failing start never
ends the bot, and nothing posts twice."""

import asyncio
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
from telegram.error import Forbidden

from tgforecast import bot, config, state

TZ = ZoneInfo("Europe/Vienna")


class FakeBot:
    def __init__(self, error: Exception | None = None):
        self.sent: list[str] = []
        self.error = error

    async def send_photo(self, **kw):
        if self.error:
            raise self.error
        self.sent.append("photo")

    async def send_message(self, **kw):
        if self.error:
            raise self.error
        self.sent.append("message")


@pytest.fixture
def settings(tmp_path):
    return config.load(
        {"TELEGRAM_BOT_TOKEN": "123:abc", "CHAT_ID": "-1001", "DATA_DIR": str(tmp_path)}
    )


@pytest.fixture
async def runner(settings):
    async with httpx.AsyncClient() as http:
        yield bot.Runner(settings, http)


def at(fx, hh, mm) -> datetime:
    day = date.fromisoformat(fx("forecast_vienna")["daily"]["time"][0])
    return datetime.combine(day, time(hh, mm), tzinfo=TZ)


async def test_waking_late_posts_on_the_next_tick_once(routes, runner, fx):
    fake = FakeBot()
    assert await runner.tick(fake, at(fx, 9, 30)) == "posted"  # asleep at 07:00
    assert await runner.tick(fake, at(fx, 9, 31)) == "done"
    assert fake.sent == ["photo"]


async def test_retries_wait_fifteen_minutes(routes, runner, fx):
    routes["forecast"].mock(return_value=httpx.Response(503))
    fake = FakeBot()
    assert await runner.tick(fake, at(fx, 7, 0)) == "retry"
    assert await runner.tick(fake, at(fx, 7, 1)) == "waiting"
    assert await runner.tick(fake, at(fx, 7, 15)) == "retry"
    assert routes["forecast"].call_count == 2


async def test_four_failures_give_one_notice_then_stop(routes, runner, fx):
    routes["forecast"].mock(return_value=httpx.Response(503))
    fake = FakeBot()
    statuses = [await runner.tick(fake, at(fx, 7, 0) + timedelta(minutes=15 * i)) for i in range(6)]
    assert statuses[:4] == ["retry", "retry", "retry", "gave_up"]
    assert statuses[4:] == ["done", "done"]
    assert fake.sent == ["message"]


async def test_city_lookup_failure_does_not_end_the_bot(routes, runner, fx):
    routes["geocode"].mock(return_value=httpx.Response(503))
    fake = FakeBot()
    assert await runner.tick(fake, at(fx, 7, 0)) == "waiting"
    routes["geocode"].mock(return_value=httpx.Response(200, json=fx("geocode_vienna")))
    assert await runner.tick(fake, at(fx, 7, 1)) == "posted"


async def test_telegram_refusal_stops_for_the_day(routes, runner, fx):
    fake = FakeBot(Forbidden("bot is not a member"))
    assert await runner.tick(fake, at(fx, 7, 0)) == "blocked"
    assert await runner.tick(fake, at(fx, 7, 1)) == "done"


async def test_an_unexpected_response_is_retried_not_fatal(routes, runner, fx):
    routes["forecast"].mock(return_value=httpx.Response(200, json={}))
    assert await runner.tick(FakeBot(), at(fx, 7, 0)) == "retry"


async def test_a_failed_state_write_never_posts_twice(routes, runner, fx, monkeypatch):
    def broken(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(bot.state, "mark_posted", broken)
    fake = FakeBot()
    assert await runner.tick(fake, at(fx, 7, 0)) == "posted"
    assert await runner.tick(fake, at(fx, 7, 1)) == "done"
    assert fake.sent == ["photo"]


async def test_two_ticks_at_once_post_once(routes, runner, fx):
    fake = FakeBot()
    await asyncio.gather(runner.tick(fake, at(fx, 7, 0)), runner.tick(fake, at(fx, 7, 0)))
    assert fake.sent == ["photo"]


async def test_a_new_day_starts_fresh(routes, runner, fx, settings):
    fake = FakeBot()
    await runner.tick(fake, at(fx, 7, 0))
    state.mark_posted(settings.data_dir / "state.json", at(fx, 7, 0).date())
    tomorrow = at(fx, 7, 0) + timedelta(days=1)
    assert await runner.tick(fake, tomorrow - timedelta(hours=1)) == "skipped"


def test_the_tick_job_survives_a_late_wake(settings):
    app = bot.build(settings)
    asyncio.run(bot._start(app))
    job = next(j for j in app.job_queue.jobs() if j.name == "tick")
    assert job.job.misfire_grace_time is None
    assert job.job.trigger.interval == timedelta(seconds=bot.TICK)


def test_startup_network_error_is_retried(monkeypatch, capsys):
    import respx

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake")
    monkeypatch.setenv("CHAT_ID", "-1")
    monkeypatch.setattr(bot.time_module, "sleep", lambda s: None)
    started = []
    monkeypatch.setattr(
        bot, "build", lambda s: type("A", (), {"run_polling": lambda self: started.append(1)})()
    )
    with respx.mock(assert_all_called=False) as router:
        router.post(url__startswith="https://api.telegram.org/bot123:fake/").mock(
            side_effect=[
                httpx.ConnectError("no network"),
                httpx.Response(
                    200,
                    json={
                        "ok": True,
                        "result": {"id": 1, "is_bot": True, "first_name": "b", "username": "b"},
                    },
                ),
            ]
        )
        assert bot.main([]) == 0
    assert started == [1]


def test_wait_for_telegram_retries_then_returns(monkeypatch):
    from telegram.error import NetworkError

    calls, slept = [], []

    async def flaky(token):
        calls.append(token)
        if len(calls) < 3:
            raise NetworkError("down")

    monkeypatch.setattr(bot, "_check_token", flaky)
    monkeypatch.setattr(bot.time_module, "sleep", slept.append)
    bot.wait_for_telegram("123:abc")
    assert len(calls) == 3 and slept == [5, 10]
