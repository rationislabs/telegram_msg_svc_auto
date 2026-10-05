"""When to post, and one attempt at posting. python-telegram-bot only ticks a
Runner every minute; every rule lives here, where it is tested.

A tick, not a 07:00 job: the scheduler waits on a clock that stops while the
laptop sleeps, and a job that fires late is dropped. A tick that asks
`should_post` posts on the first minute after waking, and never twice.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time as time_module
from datetime import date, datetime, time, timedelta

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
)
from telegram.ext import Application, ContextTypes  # noqa: E402

from . import chart, config, state, summary  # noqa: E402
from . import forecast as fc  # noqa: E402
from .config import Settings  # noqa: E402

RETRY_EVERY = 900.0
MAX_ATTEMPTS = 4
TICK = 60  # seconds between checks
NOTICE = "No forecast this morning: Open-Meteo didn't answer. Next try tomorrow."

log = logging.getLogger(__name__)


def should_post(now: datetime, post_at: time, last: date | None) -> bool:
    """`now` is in the configured TZ. Today, at or after POST_AT, not yet posted."""
    return last != now.date() and now.time() >= post_at


def _seconds(retry_after) -> float:
    return retry_after.total_seconds() if isinstance(retry_after, timedelta) else float(retry_after)


async def attempt(
    sender,
    settings: Settings,
    place: fc.Place,
    http: httpx.AsyncClient,
    now: datetime,
    attempt_no: int,
) -> tuple[str, float]:
    path = settings.data_dir / "state.json"
    if not should_post(now, settings.post_at, state.last_posted(path)):
        return "skipped", 0.0
    day = now.date()
    try:
        forecast, air = await fc.fetch(http, place, settings.units)
        text = summary.caption(forecast, air, place.label, settings.units, day)
    except Exception as e:  # noqa: BLE001 — an outage or a malformed answer: retry, never crash
        if attempt_no < MAX_ATTEMPTS:
            log.warning("attempt %d: %s; retrying in 15 minutes", attempt_no, e)
            return "retry", RETRY_EVERY
        log.error("giving up for today after %d attempts: %s", attempt_no, e)
        try:
            await sender.send_message(chat_id=settings.chat_id, text=NOTICE)
        except TelegramError as te:
            log.error("could not send the no-forecast notice either: %s", te)
        _mark(path, day)
        return "gave_up", 0.0

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
        if png:
            await sender.send_photo(
                chat_id=settings.chat_id, photo=png, caption=text, parse_mode="HTML"
            )
        else:
            await sender.send_message(chat_id=settings.chat_id, text=text, parse_mode="HTML")
    except RetryAfter as e:
        return "retry", _seconds(e.retry_after)
    except (BadRequest, Forbidden) as e:  # BadRequest subclasses NetworkError: catch it first
        log.error(
            "Telegram refused the post (%s). Check CHAT_ID, and that the bot is an "
            "admin of the channel with 'Post messages'.",
            e,
        )
        return "blocked", 0.0
    except NetworkError as e:  # includes TimedOut
        log.warning("attempt %d: Telegram unreachable (%s)", attempt_no, e)
        return "retry", RETRY_EVERY
    except TelegramError as e:  # e.g. the token was revoked while running
        log.error("Telegram refused the post: %s", e)
        return "blocked", 0.0
    _mark(path, day)
    log.info("posted the forecast for %s", day)
    return "posted", 0.0


def _mark(path, day: date) -> None:
    """A failed state write must not cost a second post: the Runner remembers the
    day in memory too, so this only logs."""
    try:
        state.mark_posted(path, day)
    except OSError as e:
        log.error("could not record today's post in %s: %s", path, e)


class Runner:
    """One day's bookkeeping between ticks: how many attempts, when the next one
    may run, and whether today is done. The lock makes overlapping ticks wait,
    so two can never both pass should_post before either marks the day."""

    def __init__(self, settings: Settings, http: httpx.AsyncClient):
        self.settings, self.http = settings, http
        self.place: fc.Place | None = None
        self.lock = asyncio.Lock()
        self.day: date | None = None
        self.attempts = 0
        self.next_try: datetime | None = None
        self.done = False
        self.last_problem = ""

    async def tick(self, sender, now: datetime) -> str:
        async with self.lock:
            if self.day != now.date():
                self.day, self.attempts, self.next_try, self.done = now.date(), 0, None, False
            if self.done:
                return "done"
            if self.next_try and now < self.next_try:
                return "waiting"
            if self.place is None:
                try:
                    self.place = await fc.geocode(self.http, self.settings.city)
                    log.info(
                        "posting the forecast for %s at %s %s",
                        self.place.label,
                        self.settings.post_at,
                        self.settings.tz,
                    )
                except fc.FetchError as e:
                    problem = f"CITY={self.settings.city!r}: {e}; trying again every minute"
                    if problem != self.last_problem:  # once per change, not every minute
                        log.warning(problem)
                        self.last_problem = problem
                    return "waiting"
            status, delay = await attempt(
                sender, self.settings, self.place, self.http, now, self.attempts + 1
            )
            if status == "retry":
                self.attempts += 1
                self.next_try = now + timedelta(seconds=delay)
                if self.attempts >= MAX_ATTEMPTS:
                    log.error("no post today: still failing after %d attempts", self.attempts)
                    self.done = True
            elif status in ("posted", "gave_up", "blocked"):
                self.done = True
            return status


async def _tick(context: ContextTypes.DEFAULT_TYPE) -> None:
    runner: Runner = context.application.bot_data["runner"]
    await runner.tick(context.bot, datetime.now(runner.settings.tz))


async def _start(app: Application) -> None:
    settings: Settings = app.bot_data["settings"]
    http = httpx.AsyncClient()
    app.bot_data.update(http=http, runner=Runner(settings, http))
    # misfire_grace_time None: a tick delayed by suspend still runs on waking.
    app.job_queue.run_repeating(
        _tick,
        interval=TICK,
        first=1,
        name="tick",
        job_kwargs={"misfire_grace_time": None, "coalesce": True},
    )


async def _stop(app: Application) -> None:
    if http := app.bot_data.get("http"):
        await http.aclose()


def build(settings: Settings) -> Application:
    app = Application.builder().token(settings.token).post_init(_start).post_shutdown(_stop).build()
    app.bot_data["settings"] = settings
    return app


async def send_now(settings: Settings) -> None:
    """Post today's forecast immediately, for checking the look. state.json is
    not touched, so the scheduled post still goes out."""
    async with httpx.AsyncClient() as http, Bot(settings.token) as tg:
        place = await fc.geocode(http, settings.city)
        forecast, air = await fc.fetch(http, place, settings.units)
        now = datetime.now(settings.tz)
        day = now.date()
        await tg.send_photo(
            chat_id=settings.chat_id,
            parse_mode="HTML",
            caption=summary.caption(forecast, air, place.label, settings.units, day),
            photo=chart.render(
                chart.series(forecast, day),
                f"{place.label} · {day:%A} {day.day} {day:%B}",
                settings.units,
                mark_hour=now.hour + now.minute / 60,
            ),
        )


STARTUP_BACKOFF = (5, 10, 20, 40, 60)  # seconds; then every 60 s until Telegram answers


async def _check_token(token: str) -> None:
    """getMe once before polling. A rejected token then stops with one line;
    python-telegram-bot's own retry loop would log a traceback that quotes it."""
    async with Bot(token):
        pass


def main(argv: list[str]) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)  # its INFO lines carry the token URL
    settings = config.load()
    try:
        for n in range(10**9):  # no network at boot (Wi-Fi not up yet): wait, never die
            try:
                asyncio.run(_check_token(settings.token))
                break
            except InvalidToken:
                raise
            except NetworkError as e:
                wait = STARTUP_BACKOFF[min(n, len(STARTUP_BACKOFF) - 1)]
                log.warning("Telegram unreachable at start (%s); trying again in %d s", e, wait)
                time_module.sleep(wait)
        if argv[:1] == ["send-now"]:
            asyncio.run(send_now(settings))
            return 0
        build(settings).run_polling()
    except InvalidToken:
        print("TELEGRAM_BOT_TOKEN rejected: create a new one in @BotFather", file=sys.stderr)
        return 1
    return 0
