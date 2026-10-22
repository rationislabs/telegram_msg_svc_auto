"""The morning post: one run posts today's forecast for every city in CITY, then exits.

GitHub Actions starts it from two UTC crons (the clocks change, POST_AT doesn't); `due` keeps the
one whose scheduled time is POST_AT in TZ. The scheduled time, not the start time: GitHub can
start a run late, and a late run must neither be skipped nor post twice.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time as time_module
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

# Opt in now to python-telegram-bot's future behaviour (durations as timedelta);
# _seconds() handles both, and it silences the per-error deprecation warning.
os.environ.setdefault("PTB_TIMEDELTA", "1")

import httpx  # noqa: E402
from telegram import Bot  # noqa: E402
from telegram.error import (  # noqa: E402
    BadRequest,
    Forbidden,
    InvalidToken,
    NetworkError,
    RetryAfter,
    TelegramError,
    TimedOut,
)

from . import chart, config, summary  # noqa: E402
from . import forecast as fc  # noqa: E402
from .config import Settings  # noqa: E402

TRIES = 3
RETRY_WAIT = 60  # seconds between tries; the Actions job has a timeout of its own
RUN_RETRY_BUDGET = 480  # seconds of retry waits for the whole run, of daily.yml's 15 minutes
NOTICE = "No forecast for {city} this morning: Open-Meteo didn't answer. Next try tomorrow."

log = logging.getLogger(__name__)


def due(schedule: str, now: datetime, post_at: time, tz: ZoneInfo) -> bool:
    """`schedule` is the cron that started the run ("" when started by hand: always due).
    Due when the cron's time today, in `tz`, is POST_AT."""
    if not schedule:
        return True
    minute, hour = (int(x) for x in schedule.split()[:2])
    # ponytail: "today" is the start date; a cron just before midnight UTC that starts after it
    # would look at the wrong day. Our crons run in the morning.
    scheduled = now.astimezone(UTC).replace(hour=hour, minute=minute, second=0, microsecond=0)
    local = scheduled.astimezone(tz)
    return (local.hour, local.minute) == (post_at.hour, post_at.minute)


def _paired(schedule: str, now: datetime, post_at: time, tz: ZoneInfo) -> bool:
    """A cron that is not due today is fine when it is POST_AT's summer/winter partner: one hour
    off. Anything else means POST_AT or TZ changed and the crons were not moved with it."""
    shifted = [(datetime.combine(now.date(), post_at) + timedelta(hours=h)).time() for h in (-1, 1)]
    return any(due(schedule, now, s, tz) for s in shifted)


def descriptions(settings: Settings) -> tuple[str, str]:
    """(short, long) for the bot's profile: Telegram allows 120 and 512 characters."""
    at = f"{settings.post_at:%H:%M}"
    short = f"Morning weather for {', '.join(settings.cities)}, posted daily at {at}."
    if len(short) > 120:
        short = f"Morning weather for {len(settings.cities)} cities, posted daily at {at}."
    long = (
        f"{short}\n\nIt posts to its owner's chat only: a short caption and a chart of today's "
        "temperature and chance of rain. Weather data by Open-Meteo.com."
    )
    if settings.answer_bot:
        long += f"\n\nAsk about any city, any time: @{settings.answer_bot}"
    return short, long


def _seconds(retry_after) -> float:
    return retry_after.total_seconds() if isinstance(retry_after, timedelta) else float(retry_after)


_now = time_module.monotonic


class _Budget:
    """Time for retries in the whole run, on the clock: ten cities in an outage must not
    outlast the job, or the last ones get neither a post nor the notice. The waits and the
    slow requests between them both count."""

    def __init__(self, seconds: float, clock=None) -> None:
        self.clock = clock or _now
        self.until = self.clock() + seconds

    def take(self, seconds: float) -> bool:
        """True if a wait of `seconds` still ends within the budget."""
        return self.clock() + seconds <= self.until


async def _forecast(http: httpx.AsyncClient, city: str, settings: Settings, day, budget: _Budget):
    """Place, forecast and caption, tried TRIES times while the run's retry budget lasts. A city
    that doesn't exist isn't retried."""
    for n in range(1, TRIES + 1):
        try:
            place = await fc.geocode(http, city)
            forecast, air = await fc.fetch(http, place, settings.units)
            return place, forecast, summary.caption(forecast, air, place.label, settings.units, day)
        except fc.NotFound:
            raise
        except Exception as e:  # noqa: BLE001 — an outage or a malformed answer: retry
            if n == TRIES or not budget.take(RETRY_WAIT):
                raise
            log.warning("%s, try %d: %s; again in %d s", city, n, e, RETRY_WAIT)
            await asyncio.sleep(RETRY_WAIT)


async def _send(tg, settings: Settings, text: str, png: bytes | None) -> None:
    """One flood-limit wait, as Telegram asks, then one more try."""
    for last in (False, True):
        try:
            if png:
                await tg.send_photo(
                    chat_id=settings.chat_id, photo=png, caption=text, parse_mode="HTML"
                )
            else:
                await tg.send_message(chat_id=settings.chat_id, text=text, parse_mode="HTML")
            return
        except RetryAfter as e:
            if last:
                raise
            await asyncio.sleep(_seconds(e.retry_after))


async def post(
    tg, http: httpx.AsyncClient, settings: Settings, city: str, now: datetime, budget: _Budget
) -> bool:
    """Today's post for one city. True when it went out."""
    day = now.date()
    try:
        place, forecast, text = await _forecast(http, city, settings, day, budget)
    except fc.NotFound:
        log.error("CITY %r: no such place; check the spelling", city)
        return False
    except Exception as e:  # noqa: BLE001
        log.error("%s: no forecast after %d tries: %s", city, TRIES, e)
        try:
            await tg.send_message(chat_id=settings.chat_id, text=NOTICE.format(city=city))
        except TelegramError as te:
            log.error("could not send the no-forecast notice either: %s", te)
        return False
    try:
        png = chart.render(
            chart.series(forecast, day),
            f"{place.label} · {day:%A} {day.day} {day:%B}",
            settings.units,
            mark_hour=now.hour + now.minute / 60,
        )
    except Exception:  # noqa: BLE001 — a broken chart must not cost the post
        log.exception("chart failed; sending the caption alone")
        png = None
    try:
        await _send(tg, settings, text, png)
    except TimedOut as e:
        if isinstance(e.__cause__, httpx.ConnectTimeout | httpx.PoolTimeout):
            log.error("%s: could not reach Telegram (%s)", place.label, type(e.__cause__).__name__)
            return False
        # Sent but unanswered: the upload often lands anyway, and a retry would post it twice.
        log.warning("%s: Telegram timed out; counted as posted", place.label)
        return True
    except (BadRequest, Forbidden) as e:  # BadRequest subclasses NetworkError: catch it first
        log.error(
            "Telegram refused the post (%s). Check CHAT_ID, and that the bot may post there.", e
        )
        return False
    except TelegramError as e:
        log.error("Telegram refused the post: %s", e)
        return False
    log.info("posted the forecast for %s", place.label)
    return True


async def run(tg, http: httpx.AsyncClient, settings: Settings, now: datetime) -> bool:
    """Describe the bot, then post every city. True when every city went out."""
    short, long = descriptions(settings)
    try:
        await tg.set_my_short_description(short)
        await tg.set_my_description(long)
    except TelegramError as e:  # the profile text must not cost the posts
        log.warning("description not set: %s", type(e).__name__)
    budget = _Budget(RUN_RETRY_BUDGET)
    results = [await post(tg, http, settings, city, now, budget) for city in settings.cities]
    return all(results)


async def _main(settings: Settings) -> bool:
    async with httpx.AsyncClient() as http, Bot(settings.token) as tg:
        return await run(tg, http, settings, datetime.now(settings.tz))


STARTUP_BACKOFF = (5, 10, 20, 40, 60)  # seconds; then every 60 s until Telegram answers


async def _check_token(token: str) -> None:
    """getMe once before polling. A rejected token then stops with one line;
    python-telegram-bot's own retry loop would log a traceback that quotes it."""
    async with Bot(token):
        pass


def wait_for_telegram(token: str) -> None:
    """getMe until Telegram answers: no network at boot (Wi-Fi not up yet) means wait, never die.
    A rejected token raises InvalidToken."""
    for n in range(10**9):
        try:
            asyncio.run(_check_token(token))
            return
        except InvalidToken:
            raise
        except NetworkError as e:
            wait = STARTUP_BACKOFF[min(n, len(STARTUP_BACKOFF) - 1)]
            log.warning("Telegram unreachable at start (%s); trying again in %d s", e, wait)
            time_module.sleep(wait)


def main(argv: list[str]) -> int:
    """`python -m tgforecast` (or `send-now`): post now, or when SCHEDULE says it's due."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)  # its INFO lines carry the token URL
    settings = config.load()
    schedule = os.environ.get("SCHEDULE", "")
    now = datetime.now(UTC)
    if not due(schedule, now, settings.post_at, settings.tz):
        if not _paired(schedule, now, settings.post_at, settings.tz):
            print(
                f"SCHEDULE does not match POST_AT: cron {schedule!r} is never {settings.post_at}"
                f" in {settings.tz}; give daily.yml new hours",
                file=sys.stderr,
            )
            return 1
        log.info("cron %r is not %s in %s: nothing to do", schedule, settings.post_at, settings.tz)
        return 0
    if schedule and os.environ.get("GITHUB_RUN_ATTEMPT", "1") != "1":
        # A re-run would post the cities that went out the first time again.
        print(
            "Re-runs of a scheduled post never post. To post now, use Run workflow"
            " (every city is posted again).",
            file=sys.stderr,
        )
        return 1
    try:
        wait_for_telegram(settings.token)
        return 0 if asyncio.run(_main(settings)) else 1
    except InvalidToken:
        print("TELEGRAM_BOT_TOKEN rejected: create a new one in @BotFather", file=sys.stderr)
        return 1
