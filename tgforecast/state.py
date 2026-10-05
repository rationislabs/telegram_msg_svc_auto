"""The one fact the bot remembers: the last day it posted.

Written atomically (temp file, then rename), so a crash mid-write cannot leave
a half file; anything unreadable counts as "never posted", which at worst
sends today's post once more."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path


def last_posted(path: Path) -> date | None:
    try:
        return date.fromisoformat(json.loads(path.read_text())["last_posted"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def mark_posted(path: Path, day: date) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"last_posted": day.isoformat()}))
    os.replace(tmp, path)
