from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from telegram.error import BadRequest, Forbidden, RetryAfter, TimedOut

from tgforecast import bot, config

TZ = ZoneInfo("Europe/Vienna")
SEVEN = time(7, 0)


@pytest.mark.parametrize(
    "schedule, now, expected",
    [
        ("", datetime(2026, 7, 1, 13, 0, tzinfo=UTC), True),  # by hand: always
        ("0 5 * * *", datetime(2026, 7, 1, 5, 0, tzinfo=UTC), True),  # summer: 07:00 local
        ("0 6 * * *", datetime(2026, 7, 1, 6, 0, tzinfo=UTC), False),  # summer: 08:00
        ("0 5 * * *", datetime(2026, 12, 1, 5, 0, tzinfo=UTC), False),  # winter: 06:00
        ("0 6 * * *", datetime(2026, 12, 1, 6, 0, tzinfo=UTC), True),  # winter: 07:00
        ("0 5 * * *", datetime(2026, 7, 1, 5, 40, tzinfo=UTC), True),  # started late: still due
        ("0 5 * * *", datetime(2026, 12, 1, 6, 10, tzinfo=UTC), False),  # winter, late: not twice
        ("0 6 * * *", datetime(2026, 3, 29, 6, 0, tzinfo=UTC), False),  # clocks went forward
        ("0 5 * * *", datetime(2026, 3, 29, 5, 0, tzinfo=UTC), True),
        ("0 6 * * *", datetime(2026, 10, 25, 6, 0, tzinfo=UTC), True),  # clocks went back
        ("30 4 * * *", datetime(2026, 7, 1, 4, 30, tzinfo=UTC), False),  # 06:30 local
    ],
)
def test_due(schedule, now, expected):
    assert bot.due(schedule, now, SEVEN, TZ) is expected


class FakeBot:
    """Records what would have gone to Telegram; `errors` are raised by the next sends, in order."""

    def __init__(self, *errors: Exception):
        self.sent: list[tuple[str, dict]] = []
        self.about: dict[str, str] = {}
        self.errors = list(errors)

    async def _send(self, kind, kw):
        if self.errors:
            raise self.errors.pop(0)
        self.sent.append((kind, kw))

    async def send_photo(self, **kw):
        await self._send("photo", kw)

    async def send_message(self, **kw):
        await self._send("message", kw)

    async def set_my_short_description(self, short_description):
        self.about["short"] = short_description

    async def set_my_description(self, description):
        self.about["long"] = description


def settings_for(**env):
    return config.load({"TELEGRAM_BOT_TOKEN": "123:abc", "CHAT_ID": "-1001", **env})


def morning(fx) -> datetime:
    """07:05 on the recording's first day, so its data is 'today'."""
    day = date.fromisoformat(fx("forecast_vienna")["daily"]["time"][0])
    return datetime.combine(day, time(7, 5), tzinfo=TZ)


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    waits, now = [], [0.0]

    async def sleep(seconds):
        waits.append(seconds)
        now[0] += seconds  # the retry budget is on the clock

    monkeypatch.setattr(bot.asyncio, "sleep", sleep)
    monkeypatch.setattr(bot, "_now", lambda: now[0])
    return waits


async def run(tg, settings, now):
    async with httpx.AsyncClient() as http:
        return await bot.run(tg, http, settings, now)


async def test_posts_one_photo_per_city(routes, fx):
    fake = FakeBot()
    assert await run(fake, settings_for(CITY="Vienna; Graz"), morning(fx)) is True
    assert [kind for kind, _ in fake.sent] == ["photo", "photo"]
    kind, kw = fake.sent[0]
    assert kw["chat_id"] == "-1001" and kw["parse_mode"] == "HTML"
    assert kw["photo"][:4] == b"\x89PNG" and kw["caption"].endswith("Open-Meteo.com</a>")
    asked = [c.request.url.params["name"] for c in routes["geocode"].calls]
    assert asked == ["Vienna", "Graz"]


async def test_sets_the_description_from_the_settings(routes, fx):
    fake = FakeBot()
    await run(fake, settings_for(CITY="Vienna; Graz", ANSWER_BOT="WeatherAnswerBot"), morning(fx))
    assert fake.about["short"] == "Morning weather for Vienna, Graz, posted daily at 07:00."
    assert "@WeatherAnswerBot" in fake.about["long"]


def test_descriptions_fit_telegram_with_many_long_cities():
    s = settings_for(CITY="; ".join(["Llanfairpwllgwyngyll, Wales"] * 10), ANSWER_BOT="b")
    short, long = bot.descriptions(s)
    assert len(short) <= 120 and len(long) <= 512
    assert short == "Morning weather for 10 cities, posted daily at 07:00."


async def test_chart_failure_sends_the_caption_alone(routes, fx, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("no fonts")

    monkeypatch.setattr(bot.chart, "render", broken)
    fake = FakeBot()
    assert await run(fake, settings_for(), morning(fx)) is True
    assert fake.sent[0][0] == "message"


async def test_open_meteo_down_retries_then_sends_a_notice_per_city(routes, fx, no_waiting):
    routes["forecast"].mock(return_value=httpx.Response(503))
    fake = FakeBot()
    assert await run(fake, settings_for(CITY="Vienna; Graz"), morning(fx)) is False
    assert routes["forecast"].call_count == 2 * bot.TRIES
    assert no_waiting == [bot.RETRY_WAIT] * (2 * (bot.TRIES - 1))
    assert [kw["text"] for _, kw in fake.sent] == [
        bot.NOTICE.format(city="Vienna"),
        bot.NOTICE.format(city="Graz"),
    ]


async def test_unknown_city_is_not_retried_and_the_others_still_post(routes, fx, caplog):
    routes["geocode"].mock(
        side_effect=[
            httpx.Response(200, json={"results": []}),
            httpx.Response(200, json=fx("geocode_vienna")),
        ]
    )
    fake = FakeBot()
    assert await run(fake, settings_for(CITY="Wienn; Vienna"), morning(fx)) is False
    assert [kind for kind, _ in fake.sent] == ["photo"]
    assert "CITY 'Wienn'" in caplog.text


@pytest.mark.parametrize("error", [BadRequest("Chat not found"), Forbidden("not a member")])
async def test_refused_post_names_the_fix(routes, fx, caplog, error):
    assert await run(FakeBot(error), settings_for(), morning(fx)) is False
    assert "Check CHAT_ID" in caplog.text


@pytest.mark.parametrize("given", [30, timedelta(seconds=30)])
async def test_flood_limit_waits_as_told_then_posts(routes, fx, no_waiting, given):
    fake = FakeBot(RetryAfter(given))
    assert await run(fake, settings_for(), morning(fx)) is True
    assert no_waiting == [30.0] and [kind for kind, _ in fake.sent] == ["photo"]


def todays(due: bool) -> str:
    """Of daily.yml's two crons, the one that is (or is not) due today in Vienna at 07:00."""
    now = datetime.now(UTC)
    for cron in ("0 5 * * *", "0 6 * * *"):
        if bot.due(cron, now, time(7, 0), TZ) is due:
            return cron
    raise AssertionError("one of the two crons is always due")


def test_not_due_exits_without_touching_telegram(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("CHAT_ID", "-1")
    monkeypatch.setenv("SCHEDULE", todays(due=False))  # the other half of the summer/winter pair
    with respx.mock():  # any request would fail the test
        assert bot.main([]) == 0


def test_a_schedule_that_can_never_match_post_at_fails_loudly(monkeypatch, capsys):
    # POST_AT moved without new crons: green runs that never post would hide it.
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("CHAT_ID", "-1")
    monkeypatch.setenv("SCHEDULE", "0 12 * * *")  # 13:00 or 14:00 in Vienna, never 07:00
    monkeypatch.setattr(bot, "wait_for_telegram", lambda token: pytest.fail("reached Telegram"))
    assert bot.main([]) == 1
    assert "SCHEDULE does not match POST_AT" in capsys.readouterr().err


def test_a_rerun_of_a_scheduled_job_posts_nothing_and_says_so(monkeypatch, capsys):
    # "Re-run failed jobs" would post again to the cities that already went out.
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("CHAT_ID", "-1")
    monkeypatch.setenv("SCHEDULE", todays(due=True))
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")

    def no_telegram(token):
        raise AssertionError("a re-run reached Telegram")

    monkeypatch.setattr(bot, "wait_for_telegram", no_telegram)
    # Not green: a first attempt that failed before posting would leave nothing posted.
    assert bot.main([]) == 1
    assert "Run workflow" in capsys.readouterr().err


def test_the_retry_budget_counts_time_spent_in_requests_too():
    # Ten-second timeouts are not waits, but they use up the job's 15 minutes all the same.
    now = [0.0]
    budget = bot._Budget(100, clock=lambda: now[0])
    assert budget.take(10)
    now[0] = 95  # slow requests, no waits
    assert not budget.take(10)


async def test_retries_share_one_budget_across_cities(routes, fx, no_waiting):
    routes["forecast"].mock(return_value=httpx.Response(503))
    fake = FakeBot()
    cities = "; ".join(["Vienna"] * 10)
    assert await run(fake, settings_for(CITY=cities), morning(fx)) is False
    assert sum(no_waiting) <= bot.RUN_RETRY_BUDGET
    assert [kw["text"] for _, kw in fake.sent] == [bot.NOTICE.format(city="Vienna")] * 10


async def test_a_send_that_never_connected_is_not_counted_as_sent(routes, fx):
    # A connect or pool timeout: the upload never left, so the post is lost.
    err = TimedOut()
    err.__cause__ = httpx.ConnectTimeout("no route")
    fake = FakeBot(err)
    assert await run(fake, settings_for(), morning(fx)) is False


async def test_a_timed_out_send_counts_as_sent(routes, fx, caplog):
    # Telegram often delivers a photo whose upload timed out: a retry would post it twice.
    fake = FakeBot(TimedOut())
    assert await run(fake, settings_for(), morning(fx)) is True
    assert "timed out" in caplog.text


def test_rejected_token_stops_cleanly(monkeypatch, capsys, caplog):
    """A rejected token: one clear line and exit 1 — no traceback, and the token
    never reaches the logs."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake")
    monkeypatch.setenv("CHAT_ID", "-1")
    monkeypatch.delenv("SCHEDULE", raising=False)
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
