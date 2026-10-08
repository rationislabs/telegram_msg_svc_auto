"""The public answer bot: anyone asks, nothing about them is kept.

Memory only, both capped: a 15-minute forecast cache shared by everyone (Open-Meteo's free tier)
and a per-chat throttle. Logs name the command and the outcome, never the text or the chat."""

from __future__ import annotations

import html
import logging
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import httpx

from . import chart, i18n, summary
from . import forecast as fc
from .ask import Ask

log = logging.getLogger(__name__)

# an answer Open-Meteo shouldn't give
MALFORMED = (KeyError, TypeError, ValueError, IndexError, AttributeError)


@dataclass(frozen=True)
class Reply:
    text: str  # HTML
    photo: bytes | None = None  # with text as its caption
    status: str = "ok"


class TTLCache:
    def __init__(self, ttl: float = 900, size: int = 500, clock=time.monotonic):
        self.ttl, self.size, self.clock = ttl, size, clock
        self._items: OrderedDict = OrderedDict()

    def get(self, key):
        hit = self._items.get(key)
        if hit is None or self.clock() - hit[0] >= self.ttl:
            return None
        return hit[1]

    def put(self, key, value) -> None:
        self._items[key] = (self.clock(), value)
        self._items.move_to_end(key)
        while len(self._items) > self.size:
            self._items.popitem(last=False)


@dataclass
class _Chat:
    stamps: deque = field(default_factory=deque)
    noted: bool = False


class Throttle:
    """`limit` questions per rolling `window` seconds per chat: one note, then silence."""

    def __init__(
        self, limit: int = 10, window: float = 60, chats: int = 10_000, clock=time.monotonic
    ):
        self.limit, self.window, self.chats, self.clock = limit, window, chats, clock
        self._chats: OrderedDict[int, _Chat] = OrderedDict()

    def check(self, chat_id: int) -> str:
        now = self.clock()
        chat = self._chats.pop(chat_id, None) or _Chat()
        self._chats[chat_id] = chat  # most recent last
        while len(self._chats) > self.chats:
            self._chats.popitem(last=False)
        while chat.stamps and chat.stamps[0] <= now - self.window:
            chat.stamps.popleft()
        if len(chat.stamps) < self.limit:
            chat.stamps.append(now)
            chat.noted = False
            return "ok"
        if chat.noted:
            return "quiet"
        chat.noted = True
        return "note"


class Answerer:
    def __init__(self, http: httpx.AsyncClient, clock=time.monotonic, utcnow=None):
        self.http = http
        self.cache = TTLCache(clock=clock)
        self.utcnow = utcnow or (lambda: datetime.now(UTC))

    async def _place(self, ask: Ask) -> fc.Place:
        key = ("place", ask.city.casefold(), ask.qualifier.casefold(), ask.lang)
        if (place := self.cache.get(key)) is None:
            place = await fc.search(self.http, ask.city, ask.qualifier, ask.lang)
            self.cache.put(key, place)
        return place

    async def _weather(self, place: fc.Place, units: str, days: int) -> tuple[dict, dict | None]:
        key = ("weather", round(place.latitude, 4), round(place.longitude, 4), units, days)
        if (hit := self.cache.get(key)) is None:
            hit = await fc.fetch(self.http, place, units, days=days, with_air=days == 2)
            self.cache.put(key, hit)
        return hit

    async def reply(self, ask: Ask) -> Reply:
        lang = ask.lang
        if ask.kind == "help":
            return Reply(i18n.help_text(lang), status="help")
        if ask.kind == "bad":
            return Reply(i18n.t(lang, "bad_city"), status="bad")
        outage = Reply(i18n.t(lang, "outage"), status="outage")
        try:
            place = await self._place(ask)
        except fc.NotFound:
            name = html.escape(ask.city)
            return Reply(i18n.t(lang, "unknown_place", name=name), status="unknown_place")
        except (fc.FetchError, *MALFORMED):
            return outage
        week = ask.kind == "week"
        try:
            forecast, air = await self._weather(place, ask.units, 7 if week else 2)
            # The city's own clock, not the server's: Open-Meteo answers in local time.
            offset = timedelta(seconds=forecast.get("utc_offset_seconds", 0))
            local = (self.utcnow() + offset).replace(tzinfo=None)
            if week:
                text = summary.week_caption(forecast, place.label, ask.units, lang)
            else:
                text = summary.caption(forecast, air, place.label, ask.units, local.date(), lang)
        except (fc.FetchError, *MALFORMED):
            return outage
        try:
            photo = self._chart(forecast, place, ask, local)
        except Exception as e:  # noqa: BLE001 — a broken chart must not cost the answer
            log.warning("%s chart failed: %s", ask.kind, type(e).__name__)
            return Reply(text, status="no_chart")
        return Reply(text, photo)

    @staticmethod
    def _chart(forecast: dict, place: fc.Place, ask: Ask, local: datetime) -> bytes:
        # ponytail: matplotlib blocks the event loop for ~0.2 s per chart; fine for a demo,
        # move to asyncio.to_thread if replies queue up.
        if ask.kind == "week":
            title = i18n.t(ask.lang, "week_title", label=place.label)
            return chart.week_render(chart.week_series(forecast), title, ask.units, ask.lang)
        shown = date.fromisoformat(
            forecast["daily"]["time"][summary.day_index(forecast, local.date())]
        )
        return chart.render(
            chart.series(forecast, shown),
            f"{place.label} · {i18n.date_long(shown, ask.lang)}",
            ask.units,
            mark_hour=local.hour + local.minute / 60,
            lang=ask.lang,
        )
