"""When to post, and one attempt at posting. The python-telegram-bot wiring
only schedules `attempt`; every rule lives here, where it is tested.

Every attempt — scheduled, catch-up at start, or retry — asks `should_post`
first, so no path can post twice on one day or post yesterday's forecast.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
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
)
from telegram.ext import Application, ContextTypes  # noqa: E402

from . import chart, config, state, summary  # noqa: E402
from . import forecast as fc  # noqa: E402
from .config import Settings  # noqa: E402

RETRY_EVERY = 900.0
MAX_ATTEMPTS = 4
NOTICE = "No forecast this morning: Open-Meteo didn't answer. Next try tomorrow."

log = logging.getLogger(__name__)


def should_post(now: datetime, post_at: time, last: date | None) -> bool:
    """`now` is in the configured TZ. Today, at or after POST_AT, not yet posted."""
    return last != now.date() and now.time() >= post_at


def _seconds(retry_after) -> float:
    return retry_after.total_seconds() if isinstance(retry_after, timedelta) else float(retry_after)


async def attempt(sender, settings: Settings, place: fc.Place, http: httpx.AsyncClient,
                  now: datetime, attempt_no: int) -> tuple[str, float]:
    path = settings.data_dir / "state.json"
    if not should_post(now, settings.post_at, state.last_posted(path)):
        return "skipped", 0.0
    day = now.date()
    try:
        forecast, air = await fc.fetch(http, place, settings.units)
    except fc.FetchError as e:
        if attempt_no < MAX_ATTEMPTS:
            log.warning("attempt %d: %s; retrying in 15 minutes", attempt_no, e)
            return "retry", RETRY_EVERY
        log.error("giving up for today after %d attempts: %s", attempt_no, e)
        await sender.send_message(chat_id=settings.chat_id, text=NOTICE)
        state.mark_posted(path, day)
        return "gave_up", 0.0

    text = summary.caption(forecast, air, place.label, settings.units, day)
    try:
        png = chart.render(chart.series(forecast, day),
                           f"{place.label} · {day:%A} {day.day} {day:%B}",
                           settings.units, mark_hour=now.hour + now.minute / 60)
    except Exception:  # noqa: BLE001 — a broken chart must not cost the post
        log.exception("chart failed; sending the caption alone")
        png = None

    try:
        if png:
            await sender.send_photo(chat_id=settings.chat_id, photo=png, caption=text,
                                    parse_mode="HTML")
        else:
            await sender.send_message(chat_id=settings.chat_id, text=text, parse_mode="HTML")
    except RetryAfter as e:
        return "retry", _seconds(e.retry_after)
    except (BadRequest, Forbidden) as e:  # BadRequest subclasses NetworkError: catch it first
        log.error("Telegram refused the post (%s). Check CHAT_ID, and that the bot is an "
                  "admin of the channel with 'Post messages'.", e)
        return "blocked", 0.0
    except NetworkError as e:  # includes TimedOut
        log.warning("attempt %d: Telegram unreachable (%s)", attempt_no, e)
        return "retry", RETRY_EVERY
    state.mark_posted(path, day)
    log.info("posted the forecast for %s", day)
    return "posted", 0.0


def daily_time(settings: Settings) -> time:
    return settings.post_at.replace(tzinfo=settings.tz)


async def _job(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.application.bot_data
    attempt_no = context.job.data or 1
    status, delay = await attempt(context.bot, data["settings"], data["place"], data["http"],
                                  datetime.now(data["settings"].tz), attempt_no)
    if status == "retry":
        if attempt_no < MAX_ATTEMPTS:
            context.job_queue.run_once(_job, when=delay, data=attempt_no + 1, name="retry")
        else:
            log.error("no post today: Telegram stayed unreachable for %d attempts", attempt_no)


async def _start(app: Application) -> None:
    settings: Settings = app.bot_data["settings"]
    http = httpx.AsyncClient()
    try:
        place = await fc.geocode(http, settings.city)
    except fc.FetchError as e:
        await http.aclose()
        raise SystemExit(f"CITY={settings.city!r}: {e}") from None
    log.info("posting the forecast for %s at %s %s", place.label, settings.post_at, settings.tz)
    app.bot_data.update(http=http, place=place)
    app.job_queue.run_daily(_job, time=daily_time(settings), data=1, name="daily")
    app.job_queue.run_once(_job, when=1, data=1, name="catch-up")  # should_post decides


async def _stop(app: Application) -> None:
    if http := app.bot_data.get("http"):
        await http.aclose()


def build(settings: Settings) -> Application:
    app = (Application.builder().token(settings.token)
           .post_init(_start).post_shutdown(_stop).build())
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
            chat_id=settings.chat_id, parse_mode="HTML",
            caption=summary.caption(forecast, air, place.label, settings.units, day),
            photo=chart.render(chart.series(forecast, day),
                               f"{place.label} · {day:%A} {day.day} {day:%B}",
                               settings.units, mark_hour=now.hour + now.minute / 60))


async def _check_token(token: str) -> None:
    """getMe once before polling. A rejected token then stops with one line;
    python-telegram-bot's own retry loop would log a traceback that quotes it."""
    async with Bot(token):
        pass


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # its INFO lines carry the token URL
    settings = config.load()
    try:
        asyncio.run(_check_token(settings.token))
        if argv[:1] == ["send-now"]:
            asyncio.run(send_now(settings))
            return 0
        build(settings).run_polling()
    except InvalidToken:
        print("TELEGRAM_BOT_TOKEN rejected: create a new one in @BotFather", file=sys.stderr)
        return 1
    return 0
