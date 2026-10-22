"""Today's hours as a PNG: temperature on top, rain chance below, sharing the
hour axis. Two panels rather than one chart with two y-axes. Light flat
colours, because Telegram shows the image as sent, also in its dark mode, and
recompresses it."""

from __future__ import annotations

import functools
import io
from datetime import date

import matplotlib

matplotlib.use("Agg")  # no display in a container

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

from . import i18n  # noqa: E402
from .summary import UNIT_LABELS, day_index  # noqa: E402

SURFACE, LINE, BARS = "#fcfcfb", "#1c5cab", "#3987e5"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e1e0d9"
FONT = ["DejaVu Sans"]  # ships with matplotlib, so the image is the same everywhere
try:  # place names in CJK titles: DejaVu has no such glyphs; the image installs this font
    font_manager.findfont("Noto Sans CJK JP", fallback_to_default=False)
    FONT.append("Noto Sans CJK JP")
except ValueError:  # not installed: render as before
    pass


def series(forecast: dict, day: date) -> dict:
    shown = forecast["daily"]["time"][day_index(forecast, day)]
    h = forecast["hourly"]
    by_hour = {
        int(t[11:13]): (temp, rain)
        for t, temp, rain in zip(
            h["time"], h["temperature_2m"], h["precipitation_probability"], strict=False
        )
        if t.startswith(shown)
    }
    hours = list(range(24))
    temp = [by_hour.get(x, (None, None))[0] for x in hours]
    rain = [by_hour.get(x, (None, None))[1] for x in hours]
    known = [(x, t) for x, t in zip(hours, temp, strict=True) if t is not None]
    return {
        "hours": hours,
        "temp": temp,
        "rain": rain,
        "high": max(known, key=lambda p: p[1]) if known else None,
        "low": min(known, key=lambda p: p[1]) if known else None,
    }


def _figure(title: str):
    """Stage 1's look: two panels sharing one axis, never two y-axes; 1280×800 at 200 dpi."""
    plt.rcParams.update(
        {
            "font.family": FONT,
            "font.size": 9,
            "text.color": INK,
            "axes.labelcolor": INK2,
            "xtick.color": INK2,
            "ytick.color": INK2,
        }
    )
    fig, (top, bottom) = plt.subplots(
        2, 1, figsize=(6.4, 4), dpi=200, sharex=True, gridspec_kw={"height_ratios": [3, 2]}
    )
    fig.patch.set_facecolor(SURFACE)
    fig.suptitle(title, fontsize=11, color=INK, x=0.06, ha="left")
    for ax in (top, bottom):
        ax.set_facecolor(SURFACE)
        ax.grid(axis="y", color=GRID, linewidth=0.6)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.tick_params(length=0)
    return fig, top, bottom


def _closes_figures(render):
    """Close every figure the render opened, also when it raises: the answer bot runs for days,
    and pyplot keeps an open figure until it is closed. Concurrent renders are kept
    apart by Answerer._chart_lock."""

    @functools.wraps(render)
    def wrapper(*args, **kwargs):
        before = set(plt.get_fignums())
        try:
            return render(*args, **kwargs)
        finally:
            for n in set(plt.get_fignums()) - before:
                plt.close(n)

    return wrapper


def _png(fig) -> bytes:
    fig.subplots_adjust(left=0.06, right=0.98, top=0.86, bottom=0.08, hspace=0.45)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=SURFACE)
    plt.close(fig)
    return buf.getvalue()


@_closes_figures
def render(
    data: dict, title: str, units: str, mark_hour: float | None = None, lang: str = "en"
) -> bytes:
    u = UNIT_LABELS[units]["temp"]
    fig, top, bottom = _figure(title)
    if mark_hour is not None:
        for ax in (top, bottom):
            ax.axvline(mark_hour, color=INK2, linewidth=0.8, alpha=0.6)

    top.set_title(i18n.t(lang, "chart_temp", unit=u), loc="left", fontsize=9, color=INK2)
    top.plot(data["hours"], data["temp"], color=LINE, linewidth=2)
    top.margins(y=0.2)  # room for the high and low labels inside the panel
    for point, where in ((data["high"], "bottom"), (data["low"], "top")):
        if point:
            x, y = point
            top.annotate(
                f"{round(y)}{u}",
                (x, y),
                textcoords="offset points",
                xytext=(0, 6 if where == "bottom" else -6),
                ha="center",
                va=where,
                fontsize=9,
                color=INK,
            )

    bottom.set_title(i18n.t(lang, "chart_rain"), loc="left", fontsize=9, color=INK2)
    bottom.bar(data["hours"], [r or 0 for r in data["rain"]], color=BARS, width=0.6)
    bottom.set_ylim(0, 100)
    bottom.set_xticks(range(0, 24, 3), [f"{x:02d}:00" for x in range(0, 24, 3)])
    bottom.set_xlim(-0.5, 23.5)
    return _png(fig)


def week_series(forecast: dict) -> dict:
    d = forecast["daily"]
    return {
        "days": [date.fromisoformat(t) for t in d["time"]],
        "low": d["temperature_2m_min"],
        "high": d["temperature_2m_max"],
        "rain": d["precipitation_probability_max"],
    }


@_closes_figures
def week_render(data: dict, title: str, units: str, lang: str = "en") -> bytes:
    """Each day's low–high as a bar with both values labelled; rain chance below."""
    u = UNIT_LABELS[units]["temp"]
    fig, top, bottom = _figure(title)
    x = list(range(len(data["days"])))

    top.set_title(i18n.t(lang, "chart_range", unit=u), loc="left", fontsize=9, color=INK2)
    for i, low, high in zip(x, data["low"], data["high"], strict=True):
        if low is None or high is None:
            continue  # a gap, not a guess
        top.bar(i, max(high - low, 0.2), bottom=low, color=BARS, width=0.5)
        for y, dy, va in ((high, 4, "bottom"), (low, -4, "top")):
            top.annotate(
                f"{round(y)}{u}",
                (i, y),
                textcoords="offset points",
                xytext=(0, dy),
                ha="center",
                va=va,
                fontsize=9,
                color=INK,
            )
    both = [
        (lo, hi) for lo, hi in zip(data["low"], data["high"], strict=True) if None not in (lo, hi)
    ]
    if both:  # room inside the panel for the labels above the highs and below the lows
        lo, hi = min(b[0] for b in both), max(b[1] for b in both)
        pad = max(0.15 * (hi - lo), 2)
        top.set_ylim(lo - pad, hi + pad)
    top.set_axisbelow(True)  # gridlines behind the bars

    bottom.set_title(i18n.t(lang, "chart_rain"), loc="left", fontsize=9, color=INK2)
    bottom.set_axisbelow(True)
    bottom.bar(x, [r or 0 for r in data["rain"]], color=BARS, width=0.5)
    bottom.set_ylim(0, 100)
    bottom.set_xticks(x, [i18n.week_day(d, lang) for d in data["days"]])
    bottom.set_xlim(-0.5, len(x) - 0.5)
    return _png(fig)
