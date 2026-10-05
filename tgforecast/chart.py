"""Today's hours as a PNG: temperature on top, rain chance below, sharing the
hour axis. Two panels rather than one chart with two y-axes. Light flat
colours, because Telegram shows the image as sent, also in its dark mode, and
recompresses it."""

from __future__ import annotations

import io
from datetime import date

import matplotlib

matplotlib.use("Agg")  # no display in a container

import matplotlib.pyplot as plt  # noqa: E402

from .summary import UNIT_LABELS, day_index  # noqa: E402

SURFACE, LINE, BARS = "#fcfcfb", "#1c5cab", "#3987e5"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e1e0d9"
FONT = ["DejaVu Sans"]  # ships with matplotlib, so the image is the same everywhere


def series(forecast: dict, day: date) -> dict:
    shown = forecast["daily"]["time"][day_index(forecast, day)]
    h = forecast["hourly"]
    by_hour = {int(t[11:13]): (temp, rain) for t, temp, rain in
               zip(h["time"], h["temperature_2m"], h["precipitation_probability"])
               if t.startswith(shown)}
    hours = list(range(24))
    temp = [by_hour.get(x, (None, None))[0] for x in hours]
    rain = [by_hour.get(x, (None, None))[1] for x in hours]
    known = [(x, t) for x, t in zip(hours, temp) if t is not None]
    return {"hours": hours, "temp": temp, "rain": rain,
            "high": max(known, key=lambda p: p[1]) if known else None,
            "low": min(known, key=lambda p: p[1]) if known else None}


def render(data: dict, title: str, units: str, mark_hour: float | None = None) -> bytes:
    u = UNIT_LABELS[units]["temp"]
    plt.rcParams.update({"font.family": FONT, "font.size": 9, "text.color": INK,
                         "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2})
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(6.4, 4), dpi=200, sharex=True,
                                      gridspec_kw={"height_ratios": [3, 2]})
    fig.patch.set_facecolor(SURFACE)
    fig.suptitle(title, fontsize=11, color=INK, x=0.06, ha="left")
    for ax in (top, bottom):
        ax.set_facecolor(SURFACE)
        ax.grid(axis="y", color=GRID, linewidth=0.6)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.tick_params(length=0)
        if mark_hour is not None:
            ax.axvline(mark_hour, color=INK2, linewidth=0.8, alpha=0.6)

    top.set_title(f"Temperature ({u})", loc="left", fontsize=9, color=INK2)
    top.plot(data["hours"], data["temp"], color=LINE, linewidth=2)
    top.margins(y=0.2)  # room for the high and low labels inside the panel
    for point, where in ((data["high"], "bottom"), (data["low"], "top")):
        if point:
            x, y = point
            top.annotate(f"{round(y)}{u}", (x, y), textcoords="offset points",
                         xytext=(0, 6 if where == "bottom" else -6), ha="center",
                         va=where, fontsize=9, color=INK)

    bottom.set_title("Chance of rain (%)", loc="left", fontsize=9, color=INK2)
    bottom.bar(data["hours"], [r or 0 for r in data["rain"]], color=BARS, width=0.6)
    bottom.set_ylim(0, 100)
    bottom.set_xticks(range(0, 24, 3), [f"{x:02d}:00" for x in range(0, 24, 3)])
    bottom.set_xlim(-0.5, 23.5)

    fig.subplots_adjust(left=0.06, right=0.98, top=0.86, bottom=0.08, hspace=0.45)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=SURFACE)
    plt.close(fig)
    return buf.getvalue()
