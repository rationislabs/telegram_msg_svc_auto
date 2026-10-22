"""The daily workflow is text GitHub runs; check the parts the code relies on."""

from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from tgforecast import bot

WORKFLOW = (Path(__file__).parent.parent / ".github" / "workflows" / "daily.yml").read_text()
CRONS = [
    line.split("cron:")[1].strip().strip("'\"") for line in WORKFLOW.splitlines() if "cron:" in line
]


def test_runs_send_now_with_the_schedule_and_secrets():
    assert "python -m tgforecast" in WORKFLOW
    assert "SCHEDULE: ${{ github.event.schedule }}" in WORKFLOW
    for name in ("TELEGRAM_BOT_TOKEN", "CHAT_ID"):
        assert f"{name}: ${{{{ secrets.{name} }}}}" in WORKFLOW
    assert "workflow_dispatch" in WORKFLOW and "timeout-minutes" in WORKFLOW


def test_exactly_one_cron_is_due_every_day_of_the_year():
    """POST_AT 07:00 in Vienna, summer and winter time: never zero posts, never two."""
    tz, day = ZoneInfo("Europe/Vienna"), date(2026, 1, 1)
    while day.year == 2026:
        due = []
        for cron in CRONS:
            minute, hour = (int(x) for x in cron.split()[:2])
            now = datetime.combine(day, time(hour, minute), tzinfo=UTC)
            due.append(bot.due(cron, now, time(7, 0), tz))
        assert due.count(True) == 1, day
        day += timedelta(days=1)


def test_a_manual_run_never_overlaps_the_scheduled_one():
    assert "concurrency:" in WORKFLOW and "group: daily-post" in WORKFLOW
