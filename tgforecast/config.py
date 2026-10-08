"""Settings from the environment. A bad value stops the bot at start with the
one line that fixes it, rather than failing at 07:00."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UNITS = ("metric", "imperial")


@dataclass(frozen=True)
class Settings:
    token: str = field(repr=False)  # never in logs or tracebacks
    chat_id: str
    city: str
    post_at: time
    tz: ZoneInfo
    units: str
    data_dir: Path


def load(env: Mapping[str, str] = os.environ, need_chat: bool = True) -> Settings:
    token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN is not set: create a token in @BotFather and put it in .env"
        )
    chat_id = env.get("CHAT_ID", "").strip()
    if need_chat and not chat_id:
        raise SystemExit(
            "CHAT_ID is not set: run `uv run inv chat-id` and put the channel's id in .env"
        )
    raw_at = env.get("POST_AT", "07:00")
    try:
        hour, minute = (int(x) for x in raw_at.split(":"))
        post_at = time(hour, minute)
    except ValueError:
        raise SystemExit(f"POST_AT={raw_at!r} is not HH:MM, for example 07:00") from None
    raw_tz = env.get("TZ", "Europe/Vienna")
    try:
        tz = ZoneInfo(raw_tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise SystemExit(f"TZ={raw_tz!r} is not a time zone, for example Europe/Vienna") from None
    units = env.get("UNITS", "metric")
    if units not in UNITS:
        raise SystemExit(f"UNITS={units!r} must be metric or imperial")
    return Settings(
        token=token,
        chat_id=chat_id,
        city=env.get("CITY", "Vienna"),
        post_at=post_at,
        tz=tz,
        units=units,
        data_dir=Path(env.get("DATA_DIR", "data")),
    )


@dataclass(frozen=True)
class AnswerSettings:
    token: str = field(repr=False)
    webhook_url: str  # "" → long polling (local runs)
    secret: str = field(repr=False)  # what Telegram sends back in its secret-token header
    port: int


def load_answer(env: Mapping[str, str] = os.environ) -> AnswerSettings:
    token = env.get("ANSWER_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "ANSWER_BOT_TOKEN is not set: create a second bot in @BotFather and put its token "
            "in .env (local) or in Render's dashboard"
        )
    raw_url = env.get("RENDER_EXTERNAL_URL", "").strip()
    url = raw_url.rstrip("/")
    if url and not raw_url.startswith("https://"):
        raise SystemExit(f"RENDER_EXTERNAL_URL={url!r} must start with https://")
    if url and not urlsplit(url).hostname:
        raise SystemExit(f"RENDER_EXTERNAL_URL={raw_url!r} has no host")
    raw = env.get("WEBHOOK_SECRET", "").strip()
    if url and not raw:
        raise SystemExit(
            "WEBHOOK_SECRET is not set: render.yaml generates it; to run locally, leave "
            "RENDER_EXTERNAL_URL unset"
        )
    raw_port = env.get("PORT", "10000")
    try:
        port = int(raw_port)
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise SystemExit(f"PORT={raw_port!r} is not a port number") from None
    # Telegram allows only A-Z a-z 0-9 _ - in a secret token; Render generates base64.
    # Hashing turns any value into 64 hex characters.
    secret = hashlib.sha256(raw.encode()).hexdigest() if raw else ""
    return AnswerSettings(token=token, webhook_url=url, secret=secret, port=port)
