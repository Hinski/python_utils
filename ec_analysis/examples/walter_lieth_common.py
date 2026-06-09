"""Shared Walter–Lieth ombrothermic diagram plotting."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Polygon

MONTH_LABELS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

PRECIP_SCALE = 10.0  # mm per 1 °C on shared axis


def _intersections(x: np.ndarray, t: np.ndarray, p_scaled: np.ndarray) -> list[float]:
    xs: list[float] = []
    n = len(x)
    for i in range(n):
        j = (i + 1) % n
        d0 = p_scaled[i] - t[i]
        d1 = p_scaled[j] - t[j]
        if d0 == 0:
            xs.append(float(x[i]))
        elif d0 * d1 < 0:
            frac = d0 / (d0 - d1)
            xs.append(x[i] + frac * (x[j] - x[i] if j > i else (12 - x[i] + x[j])))
    return xs


def _fill_between_curves(
    ax: plt.Axes,
    x: np.ndarray,
    t: np.ndarray,
    p_scaled: np.ndarray,
    *,
    humid: bool,
) -> None:
    n = len(x)
    x_ext = np.concatenate([x, [x[0] + 12]])
    t_ext = np.concatenate([t, [t[0]]])
    p_ext = np.concatenate([p_scaled, [p_scaled[0]]])

    for i in range(n):
        x0, x1 = x_ext[i], x_ext[i + 1]
        t0, t1 = t_ext[i], t_ext[i + 1]
        p0, p1 = p_ext[i], p_ext[i + 1]
        xx = np.linspace(x0, x1, 30)
        tt = np.interp(xx, [x0, x1], [t0, t1])
        pp = np.interp(xx, [x0, x1], [p0, p1])
        if humid:
            lower, upper, mask = tt, pp, pp > tt
        else:
            lower, upper, mask = pp, tt, tt > pp
        if not np.any(mask):
            continue
        ax.fill_between(
            xx,
            lower,
            upper,
            where=mask,
            interpolate=True,
            color="#bbdefb" if humid else "#ffcdd2",
            alpha=0.55 if humid else 0.45,
            linewidth=0,
            zorder=1,
        )


def plot_walter_lieth_on_axes(
    ax: plt.Axes,
    temp: np.ndarray,
    precip: np.ndarray,
    *,
    title: str | None = None,
    y_top: float | None = None,
    show_legend: bool = False,
    title_fontsize: float = 10,
) -> float:
    """Draw Walter–Lieth diagram on *ax*. Returns y-axis upper limit used."""
    x = np.arange(1, 13, dtype=float)
    t = np.asarray(temp, dtype=float)
    p = np.asarray(precip, dtype=float)
    p_scaled = p / PRECIP_SCALE

    if y_top is None:
        y_top = max(float(np.nanmax(t)), float(np.nanmax(p_scaled)), 20) * 1.12
        y_top = float(np.ceil(y_top / 5) * 5)

    _fill_between_curves(ax, x, t, p_scaled, humid=True)
    _fill_between_curves(ax, x, t, p_scaled, humid=False)

    ax.bar(
        x,
        p_scaled,
        width=0.62,
        color="#1565c0",
        edgecolor="#0d47a1",
        linewidth=0.6,
        alpha=0.85,
        label="Precipitation",
        zorder=3,
    )
    ax.plot(
        x,
        t,
        color="#c62828",
        linewidth=2.0,
        marker="o",
        markersize=5,
        markerfacecolor="#c62828",
        markeredgecolor="white",
        markeredgewidth=0.7,
        label="Temperature",
        zorder=4,
    )

    for xi in _intersections(x, t, p_scaled):
        ax.axvline(xi, color="#455a64", linestyle=":", linewidth=0.8, alpha=0.7, zorder=2)

    ax.set_xlim(0.4, 12.6)
    ax.set_ylim(0, y_top)
    ax.set_xticks(x)
    ax.set_xticklabels(MONTH_LABELS, fontsize=8)
    ax.set_xlabel("Month", fontsize=9)
    ax.set_ylabel("Temperature (°C)", color="#c62828", fontsize=9)
    ax.tick_params(axis="y", labelcolor="#c62828", labelsize=8)

    ax2 = ax.twinx()
    ax2.set_ylim(0, y_top * PRECIP_SCALE)
    ax2.set_ylabel("Precipitation (mm)", color="#1565c0", fontsize=9)
    ax2.tick_params(axis="y", labelcolor="#1565c0", labelsize=8)

    for ref_mm in (100, 200):
        ax.axhline(ref_mm / PRECIP_SCALE, color="#90a4ae", linestyle="--", linewidth=0.6, zorder=0)

    if title:
        ax.set_title(title, fontsize=title_fontsize)

    if show_legend:
        humid_patch = Polygon([[0, 0]], closed=True, color="#bbdefb", alpha=0.55)
        arid_patch = Polygon([[0, 0]], closed=True, color="#ffcdd2", alpha=0.45)
        handles, labels = ax.get_legend_handles_labels()
        ax.legend(
            handles + [humid_patch, arid_patch],
            labels + ["Humid (P > T)", "Arid (T > P)"],
            loc="upper right",
            fontsize=7,
            framealpha=0.95,
        )

    return y_top


def plot_walter_lieth_figure(
    temp: np.ndarray,
    precip: np.ndarray,
    *,
    title: str | None = None,
    footnote: str | None = None,
    show_legend: bool = True,
    figsize: tuple[float, float] = (8, 5.5),
) -> plt.Figure:
    fig, ax = plt.subplots(figsize=figsize)
    plot_walter_lieth_on_axes(ax, temp, precip, title=title, show_legend=show_legend)
    if footnote:
        fig.text(0.01, 0.01, footnote, fontsize=7, color="#666666")
    fig.tight_layout(rect=[0, 0.04 if footnote else 0, 1, 1])
    return fig
