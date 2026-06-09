#!/usr/bin/env python3
"""
Timeline aller ESSD-Stationen: Messphasen (Farbband + Beschriftung), Balken pro Station,
 Stationsnamen, Jahreszahlen, senkrechtes Gitter (1.1. durchgezogen, 1.7. gestrichelt).

  python3 measurement_phases_timeline_infographic.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Rectangle
from matplotlib.transforms import blended_transform_factory

STATIONS = ["Nazinga", "Kayoro", "Sumbrungu", "Gorigo", "Janga", "Mole"]
STATIONS_SKIP: list[str] = []

COVERAGE_START = pd.Timestamp("2013-01-01")
COVERAGE_END = pd.Timestamp("2025-12-31")

NAZINGA_EMPTY_FROM = pd.Period("2022-04", freq="M")
GORIGO_START = pd.Period("2017-05", freq="M")
GORIGO_EMPTY_FROM = pd.Period("2024-09", freq="M")
KAYORO_EMPTY_FROM = pd.Period("2025-09", freq="M")
SUMBRUNGU_EMPTY_FROM = pd.Period("2016-03", freq="M")
JANGA_START = pd.Period("2022-04", freq="M")
JANGA_EMPTY_FROM = pd.Period("2025-03", freq="M")
MOLE_START = pd.Period("2023-05", freq="M")

PHASE_I_END = pd.Timestamp("2015-12-31")
CONSOLIDATION_END = pd.Timestamp("2021-12-31")

PHASE_COLORS = {
    "I": "#dcedc8",
    "Consolidation": "#bbdefb",
    "II": "#e1bee7",
}
BAR_FACE = "#0d47a1"
BAR_EDGE = "#01579b"

GRID_SOLID = "#757575"
GRID_DASH = "#9e9e9e"

AXIS_FS = 11
STATION_FS = 11
PHASE_FS = 11


def _station_active_window(station: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(COVERAGE_START)
    end = pd.Timestamp(COVERAGE_END)

    if station == "Nazinga":
        end = min(end, pd.Timestamp(NAZINGA_EMPTY_FROM.start_time) - pd.Timedelta(days=1))
    elif station == "Gorigo":
        start = max(start, pd.Timestamp(GORIGO_START.start_time))
        end = min(end, pd.Timestamp(GORIGO_EMPTY_FROM.start_time) - pd.Timedelta(days=1))
    elif station == "Kayoro":
        end = min(end, pd.Timestamp(KAYORO_EMPTY_FROM.start_time) - pd.Timedelta(days=1))
    elif station == "Sumbrungu":
        end = min(end, pd.Timestamp(SUMBRUNGU_EMPTY_FROM.start_time) - pd.Timedelta(days=1))
    elif station == "Janga":
        start = max(start, pd.Timestamp(JANGA_START.start_time))
        end = min(end, pd.Timestamp(JANGA_EMPTY_FROM.start_time) - pd.Timedelta(days=1))
    elif station == "Mole":
        start = max(start, pd.Timestamp(MOLE_START.start_time))

    return start.normalize(), end.normalize()


def _phase_background_spans():
    p1 = PHASE_I_END.normalize()
    c_end = CONSOLIDATION_END.normalize()
    return [
        (COVERAGE_START, p1, "I"),
        (p1 + pd.Timedelta(days=1), c_end, "Consolidation"),
        (c_end + pd.Timedelta(days=1), COVERAGE_END, "II"),
    ]


def _draw_vertical_grid(ax: plt.Axes, x_min: float, x_max: float) -> None:
    """1. Januar: durchgezogen; 1. Juli: gestrichelt (volle Plot-Höhe, bis Tickmarks)."""
    y_first = COVERAGE_START.year
    y_last = COVERAGE_END.year
    for year in range(y_first, y_last + 2):
        ts = pd.Timestamp(year=year, month=1, day=1)
        x = mdates.date2num(ts)
        if x_min <= x <= x_max:
            ax.axvline(
                x,
                ymin=0,
                ymax=1,
                color=GRID_SOLID,
                linewidth=0.9,
                linestyle="-",
                zorder=1,
            )

    for year in range(y_first, y_last + 1):
        ts = pd.Timestamp(year=year, month=7, day=1)
        x = mdates.date2num(ts)
        if x_min <= x <= x_max:
            ax.axvline(
                x,
                ymin=0,
                ymax=1,
                color=GRID_DASH,
                linewidth=0.75,
                linestyle=(0, (4, 3)),
                zorder=1,
            )


def build_figure(*, figsize: tuple[float, float] | None = None, dpi: int = 150) -> tuple[plt.Figure, plt.Axes]:
    stations_used = [s for s in STATIONS if s not in STATIONS_SKIP]
    n = len(stations_used)
    if figsize is None:
        figsize = (13.0, max(3.2, 0.95 * n + 1.4))
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    fig.patch.set_facecolor("white")

    x_min = mdates.date2num(COVERAGE_START)
    x_max = mdates.date2num(COVERAGE_END + pd.Timedelta(days=1))
    y_bottom = -0.72
    y_top = n - 1 + 0.72

    for t0, t1, key in _phase_background_spans():
        ax.axvspan(
            mdates.date2num(t0),
            mdates.date2num(t1 + pd.Timedelta(days=1)),
            facecolor=PHASE_COLORS[key],
            alpha=1.0,
            zorder=0,
            lw=0,
        )

    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_bottom, y_top)
    ax.invert_yaxis()

    _draw_vertical_grid(ax, x_min, x_max)

    bar_h = min(0.58, 0.82 - 0.06 * n)
    for i, station in enumerate(stations_used):
        t0, t1 = _station_active_window(station)
        left = mdates.date2num(t0)
        width = mdates.date2num(t1 + pd.Timedelta(days=1)) - left
        ax.add_patch(
            Rectangle(
                (left, i - bar_h / 2),
                width,
                bar_h,
                facecolor=BAR_FACE,
                edgecolor=BAR_EDGE,
                linewidth=1.5,
                zorder=2,
            )
        )

    ax.set_yticks(range(n))
    ax.set_yticklabels(stations_used, fontsize=STATION_FS, fontweight="bold")

    ax.xaxis.set_major_locator(mdates.YearLocator(1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.tick_params(axis="x", which="major", labelbottom=True, length=6, width=1.0, labelsize=AXIS_FS)
    ax.tick_params(axis="y", labelsize=STATION_FS)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_linewidth(1.0)
    ax.spines["bottom"].set_linewidth(1.0)

    # Phasen-Bezeichnungen (wie Heatmap): mittig über den drei Zeitabschnitten
    trans = blended_transform_factory(ax.transData, ax.transAxes)
    t_cons_0 = PHASE_I_END + pd.Timedelta(days=1)
    t_ii_0 = CONSOLIDATION_END + pd.Timedelta(days=1)
    centers_ts = [
        COVERAGE_START + (PHASE_I_END - COVERAGE_START) / 2,
        t_cons_0 + (CONSOLIDATION_END - t_cons_0) / 2,
        t_ii_0 + (COVERAGE_END - t_ii_0) / 2,
    ]
    for cx_ts, label in zip(
        centers_ts,
        ("Phase I", "Consolidation Phase", "Phase II"),
        strict=True,
    ):
        ax.text(
            mdates.date2num(cx_ts.normalize()),
            1.03,
            label,
            transform=trans,
            ha="center",
            va="bottom",
            fontsize=PHASE_FS,
            fontweight="bold",
            clip_on=False,
        )

    fig.subplots_adjust(left=0.16, right=0.98, top=0.82, bottom=0.12)
    return fig, ax


def main() -> None:
    p = argparse.ArgumentParser(description="Messphasen-Timeline (alle Stationen)")
    p.add_argument("-o", "--output", type=Path, default=Path("measurement_phases_timeline_infographic.png"))
    p.add_argument("--dpi", type=int, default=150)
    args = p.parse_args()

    fig, _ax = build_figure(dpi=args.dpi)
    fig.savefig(args.output, dpi=args.dpi, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"✓ {args.output.resolve()}")


if __name__ == "__main__":
    main()
