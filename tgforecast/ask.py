"""Message text → what it asks. Pure: no network, no Telegram objects.

A localised command name picks the reply language for that one reply; otherwise the sender's
Telegram app language does. Plain text counts as a city only in a private chat, because in a
group the bot only sees commands addressed to it (privacy mode). A `;` separates cities, because a
comma already belongs to the place ("Paris, Texas")."""

from __future__ import annotations

from dataclasses import dataclass

from . import i18n

MAX_CITY = 100
MAX_CITIES = 5
IMPERIAL = {"°f", "ºf", "f", "fahrenheit", "imperial"}
METRIC = {"°c", "ºc", "c", "celsius", "metric"}

# command name → (kind, language it replies in; None = the sender's)
COMMANDS: dict[str, tuple[str, str | None]] = {"start": ("help", None)}
for _lang, _names in i18n.COMMANDS.items():
    for _name, _kind in zip(_names, ("now", "week", "help"), strict=True):
        COMMANDS[_name] = (_kind, None if _lang == "en" else _lang)


@dataclass(frozen=True)
class Ask:
    kind: str  # "help" | "now" | "week" | "bad" | "too_many"
    lang: str
    city: str = ""
    qualifier: str = ""
    units: str = "metric"


def parse(text: str, language_code: str | None, private: bool, bot_username: str) -> list[Ask]:
    """What the message asks, one Ask per city; empty when the message isn't for this bot."""
    text = text.strip()
    if not text:
        return []
    lang = i18n.pick(language_code)
    if not text.startswith("/"):
        return _cities("now", lang, text) if private else []
    parts = text[1:].split(maxsplit=1)
    head, rest = (parts[0] if parts else ""), (parts[1] if len(parts) > 1 else "")
    name, _, target = head.partition("@")
    if target and target.casefold() != bot_username.casefold():
        return []  # addressed to another bot
    hit = COMMANDS.get(name.casefold())
    if hit is None:
        return [Ask("help", lang)] if private else []
    kind, own = hit
    lang = own or lang
    return [Ask("help", lang)] if kind == "help" else _cities(kind, lang, rest)


def _units(words: list[str], units: str | None) -> tuple[str | None, list[str]]:
    """A unit word at the end, if any, and the words before it."""
    if words and words[-1].casefold() in METRIC:
        return "metric", words[:-1]
    if words and words[-1].casefold() in IMPERIAL:
        return "imperial", words[:-1]
    return units, words


def _cities(kind: str, lang: str, rest: str) -> list[Ask]:
    pieces = [p.split() for p in rest.split(";")]
    pieces = [p for p in pieces if p]
    if pieces:
        every, pieces[-1] = _units(pieces[-1], None)  # the message's last unit: for every city
        pieces = [p for p in pieces if p]
    if not pieces:
        return [Ask("help", lang)]
    if len(pieces) > MAX_CITIES:
        return [Ask("too_many", lang)]
    asks = []
    for words in pieces:
        units, words = _units(words, every)
        asks.append(_city(kind, lang, words, units or "metric"))
    return asks


def _city(kind: str, lang: str, words: list[str], units: str) -> Ask:
    whole = " ".join(words)
    city, _, qualifier = whole.partition(",")
    city, qualifier = city.strip(), qualifier.strip()
    if len(whole) > MAX_CITY or not any(c.isalpha() for c in city):
        return Ask("bad", lang)
    return Ask(kind, lang, city, qualifier, units)
