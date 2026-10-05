from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
from telegram.error import BadRequest, Forbidden, RetryAfter, TimedOut

from tgforecast import bot, config, state
from tgforecast import forecast as fc

TZ = ZoneInfo("Europe/Vienna")
SEVEN = time(7, 0)
VIENNA = fc.Place("Vienna", "Vienna", "AT", 48.2085, 16.3721)


@pytest.mark.parametrize(
    "now, last, expected",
    [
        (datetime(2026, 10, 6, 6, 59, tzinfo=TZ), None, False),  # before POST_AT
        (datetime(2026, 10, 6, 7, 0, tzinfo=TZ), None, True),  # on time
        (datetime(2026, 10, 6, 9, 30, tzinfo=TZ), date(2026, 10, 5), True),  # woke up late
        (datetime(2026, 10, 6, 9, 30, tzinfo=TZ), date(2026, 10, 6), False),  # already posted
        (datetime(2026, 10, 6, 23, 59, tzinfo=TZ), date(2026, 10, 5), True),  # still the same day
        (
            datetime(2026, 10, 7, 0, 0, 30, tzinfo=TZ),
            date(2026, 10, 5),
            False,
        ),  # new day, too early
        (datetime(2026, 3, 29, 7, 0, tzinfo=TZ), None, True),  # clocks go forward
        (datetime(2026, 10, 25, 7, 0, tzinfo=TZ), None, True),  # clocks go back
    ],
)
def test_should_post(now, last, expected):
    assert bot.should_post(now, SEVEN, last) is expected


class FakeBot:
    """Records what would have gone to Telegram; can be told to raise."""

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


@pytest.fixture
def settings(tmp_path):
    return config.load(
        {"TELEGRAM_BOT_TOKEN": "123:abc", "CHAT_ID": "-1001", "DATA_DIR": str(tmp_path)}
    )


def morning(forecast_fixture) -> datetime:
    """07:05 on the recording's first day, so its data is 'today'."""
    day = date.fromisoformat(forecast_fixture["daily"]["time"][0])
    return datetime.combine(day, time(7, 5), tzinfo=TZ)


async def run(sender, settings, now, attempt_no=1):
    async with httpx.AsyncClient() as http:
        return await bot.attempt(sender, settings, VIENNA, http, now, attempt_no)


async def test_posts_once_then_skips(routes, settings, fx):
    now, fake = morning(fx("forecast_vienna")), FakeBot()
    assert await run(fake, settings, now) == ("posted", 0.0)
    kind, kw = fake.sent[0]
    assert kind == "photo" and kw["chat_id"] == "-1001" and kw["parse_mode"] == "HTML"
    assert kw["photo"][:4] == b"\x89PNG" and kw["caption"].endswith("Open-Meteo.com</a>")
    assert state.last_posted(settings.data_dir / "state.json") == now.date()
    assert await run(fake, settings, now + timedelta(hours=1)) == ("skipped", 0.0)
    assert len(fake.sent) == 1


async def test_chart_failure_sends_text_and_marks(routes, settings, fx, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("no fonts")

    monkeypatch.setattr(bot.chart, "render", broken)
    fake = FakeBot()
    assert (await run(fake, settings, morning(fx("forecast_vienna"))))[0] == "posted"
    assert fake.sent[0][0] == "message"


async def test_fetch_failure_retries_then_gives_notice(routes, settings, fx):
    routes["forecast"].mock(return_value=httpx.Response(503))
    now, fake = morning(fx("forecast_vienna")), FakeBot()
    assert await run(fake, settings, now, attempt_no=1) == ("retry", bot.RETRY_EVERY)
    assert fake.sent == [] and state.last_posted(settings.data_dir / "state.json") is None
    assert await run(fake, settings, now, attempt_no=bot.MAX_ATTEMPTS) == ("gave_up", 0.0)
    assert fake.sent == [("message", {"chat_id": "-1001", "text": bot.NOTICE})]
    assert state.last_posted(settings.data_dir / "state.json") == now.date()


async def test_wrong_chat_is_not_retried(routes, settings, fx):
    for error in (BadRequest("Chat not found"), Forbidden("bot is not a member")):
        status, _ = await run(FakeBot(error), settings, morning(fx("forecast_vienna")))
        assert status == "blocked", error
    assert state.last_posted(settings.data_dir / "state.json") is None


async def test_network_error_retries(routes, settings, fx):
    status, delay = await run(FakeBot(TimedOut()), settings, morning(fx("forecast_vienna")))
    assert (status, delay) == ("retry", bot.RETRY_EVERY)


@pytest.mark.parametrize("given", [30, timedelta(seconds=30)])
async def test_flood_limit_waits_as_told(routes, settings, fx, given):
    status, delay = await run(FakeBot(RetryAfter(given)), settings, morning(fx("forecast_vienna")))
    assert (status, delay) == ("retry", 30.0)


def test_rejected_token_stops_cleanly(monkeypatch, capsys, caplog):
    """A rejected token: one clear line and exit 1 — no traceback, and the token
    never reaches the logs."""
    import respx

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake")
    monkeypatch.setenv("CHAT_ID", "-1")
    with respx.mock(assert_all_called=False) as router:
        router.post(url__startswith="https://api.telegram.org/bot123:fake/").mock(
            return_value=httpx.Response(
                401, json={"ok": False, "error_code": 401, "description": "Unauthorized"}
            )
        )
        assert bot.main([]) == 1
    err = capsys.readouterr().err
    assert "TELEGRAM_BOT_TOKEN rejected" in err and "Traceback" not in err
    assert "123:fake" not in caplog.text and "123:fake" not in err
