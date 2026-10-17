"""The public answer bot: anyone asks, nothing about them is kept.

Memory only, both capped: a 15-minute forecast cache shared by everyone (Open-Meteo's free tier)
and a per-chat throttle. Logs name the command and the outcome, never the text or the chat."""

from __future__ import annotations

import asyncio
import html
import logging
import os
import sys
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

# Opt in to python-telegram-bot's future behaviour, as bot.py does, before telegram is imported.
os.environ.setdefault("PTB_TIMEDELTA", "1")

import httpx  # noqa: E402
from telegram import LinkPreviewOptions  # noqa: E402
from telegram.error import InvalidToken, TelegramError  # noqa: E402
from telegram.ext import Application, ContextTypes, MessageHandler, filters  # noqa: E402
from telegram.ext._utils import webhookhandler  # noqa: E402

from . import bot as stage1  # noqa: E402
from . import chart, config, i18n, summary  # noqa: E402
from . import forecast as fc  # noqa: E402
from .ask import Ask, parse  # noqa: E402

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
        self._chart_lock = asyncio.Lock()  # pyplot's figure registry is not thread-safe

    async def _place(self, ask: Ask) -> fc.Place:
        key = ("place", ask.city.casefold(), ask.qualifier.casefold(), ask.lang)
        if (place := self.cache.get(key)) is None:
            place = await fc.search(self.http, ask.city, ask.qualifier, ask.lang)
            self.cache.put(key, place)
        return place

    async def reply(self, ask: Ask) -> Reply:
        lang = ask.lang
        if ask.kind == "help":
            return Reply(i18n.help_text(lang), status="help")
        if ask.kind == "bad":
            return Reply(i18n.t(lang, "bad_city"), status="bad")
        if ask.kind == "too_many":
            return Reply(i18n.t(lang, "too_many"), status="too_many")
        outage = Reply(i18n.t(lang, "outage"), status="outage")
        try:
            place = await self._place(ask)
        except fc.NotFound:
            name = html.escape(ask.city)
            return Reply(i18n.t(lang, "unknown_place", name=name), status="unknown_place")
        except (fc.FetchError, *MALFORMED):
            return outage
        week = ask.kind == "week"
        days = 7 if week else 2
        key = ("weather", round(place.latitude, 4), round(place.longitude, 4), ask.units, days)
        try:
            hit = self.cache.get(key)
            forecast, air = hit or await fc.fetch(
                self.http, place, ask.units, days=days, with_air=not week
            )
            # The city's own clock, not the server's: Open-Meteo answers in local time.
            offset = timedelta(seconds=forecast.get("utc_offset_seconds", 0))
            local = (self.utcnow() + offset).replace(tzinfo=None)
            if week:
                text = summary.week_caption(forecast, place.label, ask.units, lang)
            else:
                try:
                    text = summary.caption(
                        forecast, air, place.label, ask.units, local.date(), lang
                    )
                except MALFORMED:
                    if air is None:
                        raise
                    air = None  # a bad air payload costs the air line, not the answer
                    text = summary.caption(
                        forecast, air, place.label, ask.units, local.date(), lang
                    )
            if hit is None:  # only an answer that could be written is worth keeping
                self.cache.put(key, (forecast, air))
        except (fc.FetchError, *MALFORMED):
            return outage
        try:
            async with self._chart_lock:
                photo = await asyncio.to_thread(self._chart, forecast, place, ask, local)
        except Exception as e:  # noqa: BLE001 — a broken chart must not cost the answer
            log.warning("%s chart failed: %s", ask.kind, type(e).__name__)
            return Reply(text, status="no_chart")
        return Reply(text, photo)

    @staticmethod
    def _chart(forecast: dict, place: fc.Place, ask: Ask, local: datetime) -> bytes:
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


NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
WEBHOOK_PATH = "telegram"


async def send(bot, chat_id: int, reply: Reply) -> None:
    if reply.photo:
        await bot.send_photo(
            chat_id=chat_id, photo=reply.photo, caption=reply.text, parse_mode="HTML"
        )
    else:
        await bot.send_message(
            chat_id=chat_id, text=reply.text, parse_mode="HTML", link_preview_options=NO_PREVIEW
        )


async def handle(
    bot, data: dict, chat_id: int, text: str, language_code: str | None, private: bool
) -> None:
    try:
        asks = parse(text, language_code, private, bot.username)
    except Exception as e:  # noqa: BLE001 — every question gets an answer
        log.error("message crashed: %s", type(e).__name__)
        await _deliver(bot, chat_id, "message", Reply(i18n.t("en", "crash"), status="crash"))
        return
    for ask in asks:  # one reply per city; each city counts against the throttle
        if not await _answer(bot, data, chat_id, ask):
            return


async def _answer(bot, data: dict, chat_id: int, ask: Ask) -> bool:
    """Reply to one Ask. False once the throttle has gone quiet: the rest of the list is dropped."""
    try:
        gate = data["throttle"].check(chat_id)
        if gate == "quiet":
            return False
        if gate == "note":
            reply = Reply(i18n.t(ask.lang, "throttled"), status="throttled")
        else:
            reply = await data["answerer"].reply(ask)
    except Exception as e:  # noqa: BLE001 — every question gets an answer
        log.error("%s crashed: %s", ask.kind, type(e).__name__)
        reply = Reply(i18n.t(ask.lang, "crash"), status="crash")
    await _deliver(bot, chat_id, ask.kind, reply)
    return reply.status != "throttled"


async def _deliver(bot, chat_id: int, kind: str, reply: Reply) -> None:
    try:
        await send(bot, chat_id, reply)
    except TelegramError as e:  # RetryAfter included: dropped, a sleeping free host does not queue
        log.warning("%s %s: reply not delivered (%s)", kind, reply.status, type(e).__name__)
        return
    log.info("%s %s", kind, reply.status)


async def on_message(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if msg is None or not msg.text:
        return
    user = update.effective_user
    await handle(
        context.bot,
        context.application.bot_data,
        msg.chat_id,
        msg.text,
        user.language_code if user else None,
        msg.chat.type == "private",
    )


async def on_error(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # python-telegram-bot's default handler would log the update, which holds the message text.
    log.error("unhandled %s", type(context.error).__name__)


def menus() -> list[tuple[str | None, list[tuple[str, str]]]]:
    """The command menu per app language; English is the default for everyone else."""
    out = []
    for lang in i18n.LANGS:
        now, week, help_ = i18n.COMMANDS[lang]
        out.append(
            (
                None if lang == "en" else lang,
                [
                    (now, i18n.t(lang, "cmd_now")),
                    (week, i18n.t(lang, "cmd_week")),
                    (help_, i18n.t(lang, "cmd_help")),
                ],
            )
        )
    return out


def descriptions() -> list[tuple[str | None, str, str]]:
    """(language, short, long) for the bot's profile and its empty chat: what a visitor reads
    before pressing Start. Plain text; English is the default."""
    return [
        (None if lang == "en" else lang, i18n.t(lang, "about_short"), i18n.t(lang, "help"))
        for lang in i18n.LANGS
    ]


async def _start(app: Application) -> None:
    http = httpx.AsyncClient()
    app.bot_data.update(http=http, answerer=Answerer(http), throttle=Throttle())
    for code, commands in menus():
        try:
            await app.bot.set_my_commands(commands, language_code=code)
        except TelegramError as e:
            log.warning("command menu %s not set: %s", code or "default", type(e).__name__)
    for code, short, long in descriptions():
        try:
            await app.bot.set_my_short_description(short, language_code=code)
            await app.bot.set_my_description(long, language_code=code)
        except TelegramError as e:
            log.warning("description %s not set: %s", code or "default", type(e).__name__)


async def _stop(app: Application) -> None:
    if http := app.bot_data.get("http"):
        await http.aclose()


def build(settings: config.AnswerSettings) -> Application:
    app = Application.builder().token(settings.token).post_init(_start).post_shutdown(_stop).build()
    app.add_handler(MessageHandler(filters.TEXT, on_message))
    app.add_error_handler(on_error)
    return app


class _DropRawUpdate(logging.Filter):
    """python-telegram-bot logs the whole update, message text included, when it can't parse one."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not str(record.msg).endswith("Received data was: %r")


_DROP_RAW_UPDATE = _DropRawUpdate()


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    for name in ("httpx", "telegram"):  # their INFO lines carry the token URL
        logging.getLogger(name).setLevel(logging.WARNING)
    webhookhandler._LOGGER.addFilter(_DROP_RAW_UPDATE)


def main() -> int:
    configure_logging()
    settings = config.load_answer()
    try:
        stage1.wait_for_telegram(settings.token)
        app = build(settings)
        if settings.webhook_url:
            app.run_webhook(
                listen="0.0.0.0",
                port=settings.port,
                url_path=WEBHOOK_PATH,
                webhook_url=f"{settings.webhook_url}/{WEBHOOK_PATH}",
                secret_token=settings.secret,
                allowed_updates=["message"],
                drop_pending_updates=False,  # the message that woke the service gets its answer
            )
        else:
            log.info("no RENDER_EXTERNAL_URL: long polling (this removes any webhook)")
            app.run_polling(allowed_updates=["message"])
    except InvalidToken:
        print("ANSWER_BOT_TOKEN rejected: create a new one in @BotFather", file=sys.stderr)
        return 1
    return 0
