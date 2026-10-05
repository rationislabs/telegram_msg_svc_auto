"""When to post, and one attempt at posting. The python-telegram-bot wiring
only schedules `attempt`; every rule lives here, where it is tested.

Every attempt — scheduled, catch-up at start, or retry — asks `should_post`
first, so no path can post twice on one day or post yesterday's forecast.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, time, timedelta

# Opt in now to python-telegram-bot's future behaviour (durations as timedelta);
# _seconds() handles both, and it silences the per-error deprecation warning.
os.environ.setdefault("PTB_TIMEDELTA", "1")

import httpx  # noqa: E402
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter  # noqa: E402

from . import chart, state, summary  # noqa: E402
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
