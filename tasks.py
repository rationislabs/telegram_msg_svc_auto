"""Developer tasks. List them with `uv run inv --list`."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from invoke import task

ROOT = Path(__file__).parent
FIXTURES = ROOT / "tests" / "fixtures"


@task
def fixtures(c):
    """Record real Open-Meteo responses for Vienna for the offline tests."""
    from tgforecast import forecast as fc

    FIXTURES.mkdir(parents=True, exist_ok=True)

    def save(name: str, url: str, params: dict) -> dict:
        data = httpx.get(url, params=params, timeout=30).raise_for_status().json()
        (FIXTURES / f"{name}.json").write_text(json.dumps(data, indent=1) + "\n")
        print(f"wrote tests/fixtures/{name}.json")
        return data

    r = save("geocode_vienna", fc.GEOCODE, fc.geocode_params("Vienna"))["results"][0]
    vienna = fc.Place(
        r["name"], r.get("admin1", ""), r.get("country_code", ""), r["latitude"], r["longitude"]
    )
    save("forecast_vienna", fc.FORECAST, fc.forecast_params(vienna, "metric"))
    save("air_vienna", fc.AIR, fc.air_params(vienna))


def _dotenv() -> dict[str, str]:
    """.env as a dict, without printing it."""
    import os

    env = dict(os.environ)
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    return env


def _token() -> str:
    from tgforecast import config

    return config.load(_dotenv(), need_chat=False).token


@task(name="chat-id")
def chat_id(c):
    """List the chats the bot can see. Post once in your channel first."""
    r = httpx.get(f"https://api.telegram.org/bot{_token()}/getUpdates", timeout=30)
    if r.status_code == 401:
        raise SystemExit("TELEGRAM_BOT_TOKEN rejected: create a new one in @BotFather")
    seen = {}
    for u in r.json().get("result", []):
        msg = u.get("channel_post") or u.get("message") or u.get("my_chat_member") or {}
        chat = msg.get("chat") or {}
        if chat:
            seen[chat["id"]] = f"{chat.get('type')}: {chat.get('title') or chat.get('username')}"
    if not seen:
        print(
            "No chats yet. Add the bot to your channel as an admin, post a message there, "
            "and run this again."
        )
    for cid, what in seen.items():
        print(f"{cid}\t{what}")


@task(name="send-now")
def send_now(c):
    """Post today's forecast to CHAT_ID now (does not touch the daily schedule)."""
    c.run("uv run python -m tgforecast send-now", env=_dotenv(), pty=True)


@task
def up(c):
    """Build and start the bot container."""
    c.run("docker compose up -d --build")


@task
def down(c):
    c.run("docker compose down")


@task
def test(c):
    c.run("uv run pytest", pty=True)


@task
def lint(c):
    c.run("uv run ruff check . && uv run ruff format --check .")


@task(name="fixtures-answer")
def fixtures_answer(c):
    """Record the answer bot's extra responses: Paris (10 results), Vienna for 7 days,
    and Auckland (a city whose date runs ahead of Vienna's)."""
    from tgforecast import forecast as fc

    FIXTURES.mkdir(parents=True, exist_ok=True)

    def save(name: str, url: str, params: dict) -> None:
        data = httpx.get(url, params=params, timeout=30).raise_for_status().json()
        (FIXTURES / f"{name}.json").write_text(json.dumps(data, indent=1) + "\n")
        print(f"wrote tests/fixtures/{name}.json")

    save("geocode_paris", fc.GEOCODE, {**fc.geocode_params("Paris"), "count": 10})
    vienna = fc.Place("Vienna", "Vienna", "AT", 48.20849, 16.37208)
    save("forecast_vienna_week", fc.FORECAST, fc.forecast_params(vienna, "metric", days=7))
    auckland = fc.Place("Auckland", "Auckland", "NZ", -36.84853, 174.76349)
    save("forecast_auckland", fc.FORECAST, fc.forecast_params(auckland, "metric"))


@task
def answer(c):
    """Run the answer bot locally with long polling (ANSWER_BOT_TOKEN from .env). This removes
    the Render webhook; restart the Render service afterwards (Manual Deploy → Restart service) to set it again."""
    c.run(
        "uv run python -m tgforecast answer",
        env={**_dotenv(), "RENDER_EXTERNAL_URL": ""},
        pty=True,
    )
