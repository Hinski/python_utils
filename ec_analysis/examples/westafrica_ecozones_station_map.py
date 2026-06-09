#!/usr/bin/env python3
"""
Schematische Karte: Afrika mit Ökozonen Westafrikas und den sechs EC-Standorten.

Zeigt ganz Afrika (vereinfachter Umriss) und im Nordwesten die phytogeographischen
Zonen des WASCAL-Transects (White 1983 / UNESCO-Savannenklassifikation).

  python westafrica_ecozones_station_map.py
  python westafrica_ecozones_station_map.py -o ../plots/ecozones_map.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from matplotlib.patches import Polygon, Rectangle
from matplotlib.lines import Line2D

# Koordinaten wie in setup_data_system.py / Data/stations.yaml
STATIONS: dict[str, dict[str, float | str]] = {
    "Nazinga": {"lat": 11.1516, "lon": -1.5858, "landcover": "geschützter Wald"},
    "Kayoro": {"lat": 10.9181, "lon": -1.3209, "landcover": "Ackerland"},
    "Sumbrungu": {"lat": 10.8466, "lon": -0.9175, "landcover": "degradiertes Grasland"},
    "Gorigo": {"lat": 10.9356, "lon": -0.8241, "landcover": "halbdegradiertes Grasland"},
    "Janga": {"lat": 10.1300, "lon": -0.8837, "landcover": "Regenfeldbau (Reis)"},
    "Mole": {"lat": 9.3385, "lon": -1.8689, "landcover": "bewirtschafteter Wald"},
}

# Ökozonen des Transects (nur westafrikanischer Längenstreifen)
ECOZONES: list[tuple[float, float, str, str]] = [
    (11.6, 12.6, "#e8d4a8", "Sudansavanne"),
    (10.5, 11.6, "#c8e6a0", "Sudan-Guinea-Savanne"),
    (9.5, 10.5, "#8ecf8e", "Guinea-Savanne"),
    (8.4, 9.5, "#4a9e6b", "Wald-Savannen-Mosaik"),
]

# Gesamtafrika (schematischer Festland-Umriss, lon/lat)
AFRICA_MAINLAND: list[tuple[float, float]] = [
    (-17.0, 20.5), (-16.8, 24.0), (-14.5, 27.0), (-11.0, 28.5), (-7.0, 33.5),
    (-5.5, 35.8), (-2.0, 36.0), (0.0, 36.5), (3.0, 37.2), (8.0, 37.0),
    (12.5, 37.0), (20.0, 32.5), (25.0, 31.8), (30.0, 31.5), (34.0, 29.5),
    (37.0, 24.0), (40.0, 18.0), (43.0, 12.5), (47.0, 11.5), (51.0, 11.0),
    (51.2, 4.0), (48.0, -2.0), (44.0, -6.0), (42.0, -11.0), (41.0, -15.0),
    (39.5, -20.0), (36.0, -26.0), (33.0, -29.5), (28.5, -33.5), (24.0, -34.5),
    (20.0, -34.8), (17.5, -32.5), (14.0, -28.0), (12.0, -22.0), (10.0, -12.0),
    (8.5, -5.0), (6.0, 0.5), (3.5, 4.5), (0.0, 5.2), (-3.0, 5.0), (-6.0, 4.8),
    (-8.5, 5.0), (-11.0, 6.5), (-13.5, 8.5), (-15.5, 12.0), (-17.0, 16.0),
    (-17.0, 20.5),
]

MADAGASCAR: list[tuple[float, float]] = [
    (43.5, -12.0), (47.0, -14.0), (50.5, -18.0), (49.5, -25.5), (45.0, -25.0),
    (43.8, -20.0), (43.5, -12.0),
]

# Westafrika: Ökozonen-Streifen und Studiengebiet
WEST_AFRICA_LON = (-18.0, 6.0)
STUDY_REGION = dict(lon=(-3.6, 1.6), lat=(8.2, 12.7))

STATION_MARKER_COLORS: dict[str, str] = {
    "Nazinga": "#1b5e20",
    "Mole": "#2e7d32",
    "Kayoro": "#e65100",
    "Janga": "#bf360c",
    "Sumbrungu": "#8d6e63",
    "Gorigo": "#a1887f",
}

# Beschriftung in Bildschirm-Punkten (skaliert mit Zoom)
LABEL_OFFSETS_PT: dict[str, tuple[float, float]] = {
    "Nazinga": (-42, 14),
    "Kayoro": (10, 12),
    "Sumbrungu": (12, -16),
    "Gorigo": (14, 8),
    "Janga": (12, -12),
    "Mole": (-48, -10),
}

# Gesamtafrika
LON_MIN, LON_MAX = -20.0, 54.0
LAT_MIN, LAT_MAX = -36.0, 39.0


def _draw_africa(ax: plt.Axes) -> None:
    for pts, face, edge in (
        (AFRICA_MAINLAND, "#f5f0e6", "#666666"),
        (MADAGASCAR, "#f5f0e6", "#666666"),
    ):
        ax.add_patch(
            Polygon(
                pts,
                closed=True,
                facecolor=face,
                edgecolor=edge,
                linewidth=1.0,
                zorder=1,
            )
        )
    ax.text(18, 5, "Afrika", fontsize=14, color="#999999", ha="center", zorder=2, style="italic")


def _draw_ecozones(ax: plt.Axes) -> None:
    lon_lo, lon_hi = WEST_AFRICA_LON
    width = lon_hi - lon_lo
    for lat_lo, lat_hi, color, name in ECOZONES:
        ax.add_patch(
            Rectangle(
                (lon_lo, lat_lo),
                width,
                lat_hi - lat_lo,
                facecolor=color,
                edgecolor="none",
                alpha=0.65,
                zorder=3,
            )
        )
        y_mid = (lat_lo + lat_hi) / 2
        ax.text(
            lon_lo + 0.5,
            y_mid,
            name,
            fontsize=8,
            fontstyle="italic",
            color="#2c3e50",
            va="center",
            ha="left",
            zorder=4,
        )
    ax.text(
        (lon_lo + lon_hi) / 2,
        12.85,
        "Ökozonen (Westafrika, schematisch)",
        fontsize=9,
        ha="center",
        color="#444444",
        zorder=4,
    )


def _draw_study_region(ax: plt.Axes) -> None:
    sr = STUDY_REGION
    ax.add_patch(
        Rectangle(
            (sr["lon"][0], sr["lat"][0]),
            sr["lon"][1] - sr["lon"][0],
            sr["lat"][1] - sr["lat"][0],
            fill=False,
            edgecolor="#1565c0",
            linewidth=1.5,
            linestyle="--",
            zorder=5,
        )
    )
    ax.text(
        sr["lon"][1] - 0.1,
        sr["lat"][1] + 0.25,
        "Messstandorte",
        fontsize=8,
        color="#1565c0",
        ha="right",
        zorder=5,
    )


def _draw_stations(ax: plt.Axes) -> list[Line2D]:
    station_handles: list[Line2D] = []
    for name, meta in STATIONS.items():
        lon = float(meta["lon"])
        lat = float(meta["lat"])
        color = STATION_MARKER_COLORS.get(name, "#c62828")
        ax.scatter(
            lon,
            lat,
            s=55,
            c=color,
            edgecolors="white",
            linewidths=1.2,
            marker="o",
            zorder=7,
        )
        ox, oy = LABEL_OFFSETS_PT.get(name, (10, 5))
        ax.annotate(
            name,
            xy=(lon, lat),
            xytext=(ox, oy),
            textcoords="offset points",
            fontsize=8,
            fontweight="bold",
            ha="left",
            va="center",
            arrowprops=dict(arrowstyle="-", color="#333333", lw=0.6),
            zorder=8,
        )
        lc = str(meta["landcover"])
        station_handles.append(
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor=color,
                markeredgecolor="white",
                markeredgewidth=1.0,
                markersize=7,
                label=f"{name} ({lc})",
            )
        )
    return station_handles


def build_figure() -> plt.Figure:
    fig, ax = plt.subplots(figsize=(10, 11))
    _draw_africa(ax)
    _draw_ecozones(ax)
    _draw_study_region(ax)
    station_handles = _draw_stations(ax)

    ax.set_xlim(LON_MIN, LON_MAX)
    ax.set_ylim(LAT_MIN, LAT_MAX)
    mean_lat = np.deg2rad((LAT_MIN + LAT_MAX) / 2)
    ax.set_aspect(1.0 / np.cos(mean_lat))
    ax.set_xlabel("Längengrad (°; negativ = westlich)", fontsize=11)
    ax.set_ylabel("Breitengrad (°N)", fontsize=11)
    ax.set_title(
        "Afrika: Ökozonen Westafrikas und EC-Messstandorte\n"
        "(schematisch; Zonen nach White 1983 / UNESCO-Savannenklassifikation)",
        fontsize=12,
        pad=12,
    )
    ax.grid(True, linestyle=":", alpha=0.25, zorder=0)

    eco_handles = [
        mpatches.Patch(facecolor=c, alpha=0.7, label=n) for _, _, c, n in ECOZONES
    ]
    leg1 = ax.legend(
        handles=eco_handles,
        title="Ökozonen (Transect)",
        loc="lower left",
        fontsize=7.5,
        title_fontsize=8,
        framealpha=0.92,
    )
    ax.add_artist(leg1)
    ax.legend(
        handles=station_handles,
        title="EC-Stationen",
        loc="upper right",
        fontsize=7,
        title_fontsize=8,
        framealpha=0.92,
    )

    note = (
        "Hinweis: Afrika-Umriss, Ökozonen und Grenzen vereinfacht. "
        "Ökozonen nur im westafrikanischen Längenstreifen dargestellt. "
        "Stationen: stations.yaml (WASCAL)."
    )
    fig.text(0.5, 0.01, note, ha="center", fontsize=7, color="#666666")

    ax.annotate(
        "N",
        xy=(LON_MAX - 2.5, LAT_MAX - 2.0),
        fontsize=11,
        fontweight="bold",
        ha="center",
        zorder=9,
    )
    ax.annotate(
        "",
        xy=(LON_MAX - 2.5, LAT_MAX - 1.2),
        xytext=(LON_MAX - 2.5, LAT_MAX - 4.5),
        arrowprops=dict(arrowstyle="-|>", color="black", lw=1.5),
        zorder=9,
    )

    fig.tight_layout(rect=[0, 0.03, 1, 1])
    return fig


def main() -> None:
    parser = argparse.ArgumentParser(description="Afrika-Karte mit EC-Standorten")
    default_out = Path(__file__).parent / "plots" / "westafrica_ecozones_ec_stations.png"
    parser.add_argument("-o", "--output", type=Path, default=default_out)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig = build_figure()
    fig.savefig(args.output, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"✓ Gespeichert: {args.output}")


if __name__ == "__main__":
    main()
