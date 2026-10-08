"""Message text → what it asks. Pure: no network, no Telegram objects.

A localised command name picks the reply language for that one reply; otherwise the sender's
Telegram app language does. Plain text counts as a city only in a private chat, because in a
group the bot only sees commands addressed to it (privacy mode)."""

from __future__ import annotations

from dataclasses import dataclass

from . import i18n

MAX_CITY = 100
IMPERIAL = {"°f", "ºf", "f", "fahrenheit", "imperial"}
METRIC = {"°c", "ºc", "c", "celsius", "metric"}

# command name → (kind, language it replies in; None = the sender's)
COMMANDS: dict[str, tuple[str, str | None]] = {"start": ("help", None)}
for _lang, _names in i18n.COMMANDS.items():
    for _name, _kind in zip(_names, ("now", "week", "help"), strict=True):
        COMMANDS[_name] = (_kind, None if _lang == "en" else _lang)


@dataclass(frozen=True)
class Ask:
    kind: str  # "help" | "now" | "week" | "bad"
    lang: str
    city: str = ""
    qualifier: str = ""
    units: str = "metric"


def parse(text: str, language_code: str | None, private: bool, bot_username: str) -> Ask | None:
    text = text.strip()
    if not text:
        return None
    lang = i18n.pick(language_code)
    if not text.startswith("/"):
        return _city("now", lang, text) if private else None
    parts = text[1:].split(maxsplit=1)
    head, rest = (parts[0] if parts else ""), (parts[1] if len(parts) > 1 else "")
    name, _, target = head.partition("@")
    if target and target.casefold() != bot_username.casefold():
        return None  # addressed to another bot
    hit = COMMANDS.get(name.casefold())
    if hit is None:
        return Ask("help", lang) if private else None
    kind, own = hit
    lang = own or lang
    return Ask("help", lang) if kind == "help" else _city(kind, lang, rest)


def _city(kind: str, lang: str, rest: str) -> Ask:
    words = rest.split()
    units = "metric"
    if words and words[-1].casefold() in METRIC:
        words = words[:-1]
    elif words and words[-1].casefold() in IMPERIAL:
        units, words = "imperial", words[:-1]
    if not words:
        return Ask("help", lang)
    whole = " ".join(words)
    city, _, qualifier = whole.partition(",")
    city, qualifier = city.strip(), qualifier.strip()
    if len(whole) > MAX_CITY or not any(c.isalpha() for c in city):
        return Ask("bad", lang)
    return Ask(kind, lang, city, qualifier, units)
