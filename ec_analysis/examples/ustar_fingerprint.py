#!/usr/bin/env python3
"""
Turbulence fingerprint per station: u* distributions (day vs night) + optional stability inset.

Nutzt EddyPro-Daten aus collect_all_variables_30min.py:
  {OUTPUT_BASE}/{station}/processed/all/{station}_all_variables_30min.csv
Falls diese fehlen, Fallback auf EddyPro full-output direkt:
  {OUTPUT_BASE}/{station}/processed/fluxes/eddypro_{station}_full_output_*.csv

Day/night: SW_in > 10 W m-2 = Tag; sonst Nacht.
"""

from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from ec_analysis import load_ec_data
    from ec_analysis.data_loaders.variable_mapping import map_dataframe_columns
except ImportError:
    load_ec_data = None
    map_dataframe_columns = None

# =============================================================================
# CONFIG
# =============================================================================
OUTPUT_BASE = Path("/Users/hingerl-l/Data")
STATIONS = ["Nazinga", "Kayoro", "Sumbrungu", "Mole", "Janga", "Gorigo"]
STATION_LABELS = {
    "Nazinga": "Nazinga (protected forest)",
    "Mole": "Mole (managed forest)",
    "Kayoro": "Kayoro (cropland)",
    "Janga": "Janga (rainfed rice field)",
    "Sumbrungu": "Sumbrungu (degr. grassland)",
    "Gorigo": "Gorigo (semi-degr. grassland)",
}
STATIONS_SKIP: list[str] = []
EXCLUDE_YEARS_BY_STATION: dict[str, set[int]] = {
  #  "Gorigo": {2017, 2020,2021,2022,2023,2024},
}

OUT_PNG = Path("turbulence_fingerprint_ustar_stability.png")
FONTSIZE = 12  # einheitlich für alle Beschriftungen

DAY_SW_IN_THRESHOLD = 10.0  # W m-2
BINS_USTAR = np.linspace(0.0, 1.5, 45)  # adjust if you have higher u*
DENSITY = True  # True: density; False: counts
YMAX = 9  # oberer Skalenbereich der Y-Achse (Density/Count)
ADD_STABILITY_INSET = True

# Spaltennamen (all_variables + EddyPro full-output, ggf. mit Units wie u*[m/s])
USTAR_ALIASES = ["ustar", "u*", "u_star", "USTAR", "Ustar", "friction_velocity"]
SWIN_ALIASES = ["SW_in", "SW_IN", "SWIN", "Rg", "Rs", "SR_in_Avg", "SWdown", "SWdown_Avg", "SW_in korrigiert"]
STAB_ALIASES = ["z-d_L", "z_d_L", "zdL", "zL", "(z-d)/L", "zeta", "ZL", "stability"]


# =============================================================================
# HELPERS
# =============================================================================
def _get_first_existing(df: pd.DataFrame, aliases: list[str]) -> str | None:
    for a in aliases:
        if a in df.columns:
            return a
    lower_map = {c.lower(): c for c in df.columns}
    for a in aliases:
        if a.lower() in lower_map:
            return lower_map[a.lower()]
    # EddyPro: Spalten mit Units z.B. "u*[m/s]", "Rg[W/m2]" – partieller Match
    for col in df.columns:
        c = str(col)
        for a in aliases:
            if a in c or a.lower() in c.lower():
                return col
    return None


def station_label(station: str) -> str:
    """Lesbares Stationslabel für Plot-Titel."""
    return STATION_LABELS.get(station, station)


def load_all_variables(station: str) -> pd.DataFrame | None:
    """Lädt aus all_variables (collect), bei Fehlen Fallback auf EddyPro full-output."""
    path = OUTPUT_BASE / station / "processed" / "all" / f"{station}_all_variables_30min.csv"
    if path.exists():
        header = pd.read_csv(path, nrows=1).columns.tolist()
        df = pd.read_csv(
            path,
            skiprows=2,
            header=None,
            names=header,
            index_col=0,
            parse_dates=True,
            low_memory=False,
            na_values=["NAN", "NA", "-9999", "-9999.0", "-999", "**************"],
        )
        df = df[df.index.notna()].sort_index()
        df = df[~df.index.duplicated(keep="first")]
        return df

    # Fallback: EddyPro full-output direkt
    if load_ec_data and map_dataframe_columns:
        flux_dir = OUTPUT_BASE / station / "processed" / "fluxes"
        if flux_dir.exists():
            files = list(flux_dir.glob(f"eddypro_{station}_full_output_*.csv"))
            if files:
                ep_path = max(files, key=lambda p: p.stat().st_mtime)
                try:
                    df = load_ec_data(ep_path, format="eddypro")
                    if df is not None and not df.empty:
                        map_dataframe_columns(df, inplace=True)
                        return df
                except Exception:
                    pass
    return None


def classify_stability(zdl: pd.Series) -> pd.Series:
    """
    Stability classes based on (z-d)/L:
      unstable: < -0.1
      near-neutral: [-0.1, 0.1]
      stable: > 0.1
    """
    z = pd.to_numeric(zdl, errors="coerce")
    cls = pd.Series(index=z.index, dtype="object")
    cls[z < -0.1] = "unstable"
    cls[(z >= -0.1) & (z <= 0.1)] = "near-neutral"
    cls[z > 0.1] = "stable"
    return cls


# =============================================================================
# MAIN
# =============================================================================
def main() -> None:
    stations_used = [s for s in STATIONS if s not in STATIONS_SKIP]
    n_plots = len(stations_used)
    if n_plots == 0:
        print("[ERROR] Keine Stationen (alle übersprungen).")
        return

    n_cols = min(3, n_plots)
    n_rows = (n_plots + n_cols - 1) // n_cols
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(5 * n_cols, 4 * n_rows), sharex=True, sharey=True)
    if n_plots == 1:
        axes = np.array([axes])
    axes = axes.ravel()

    used_any = False

    for i in range(len(axes)):
        ax = axes[i]
        if i >= len(stations_used):
            ax.axis("off")
            continue
        station = stations_used[i]
        df = load_all_variables(station)
        if df is None or df.empty:
            ax.set_title(f"{station_label(station)} (no data)")
            ax.axis("off")
            continue
        years_to_exclude = EXCLUDE_YEARS_BY_STATION.get(station, set())
        if years_to_exclude:
            df = df[~df.index.year.isin(years_to_exclude)]
            if df.empty:
                ax.set_title(f"{station_label(station)} (excluded years only)")
                ax.axis("off")
                continue

        u_col = _get_first_existing(df, USTAR_ALIASES)
        sw_col = _get_first_existing(df, SWIN_ALIASES)
        z_col = _get_first_existing(df, STAB_ALIASES)

        if u_col is None:
            ax.set_title(f"{station_label(station)} (ustar missing)")
            ax.axis("off")
            continue

        ustar = pd.to_numeric(df[u_col], errors="coerce")
        # Basic sanity for u*:
        ustar = ustar.where((ustar >= 0) & (ustar < 5))

        if sw_col is None:
            # If SW_in missing, we can't split day/night reliably -> show overall distribution
            mask_day = pd.Series(False, index=df.index)
            mask_night = pd.Series(True, index=df.index)
        else:
            sw_in = pd.to_numeric(df[sw_col], errors="coerce")
            mask_day = sw_in > DAY_SW_IN_THRESHOLD
            mask_night = sw_in <= DAY_SW_IN_THRESHOLD

        u_day = ustar[mask_day].dropna().values
        u_night = ustar[mask_night].dropna().values

        if len(u_day) == 0 and len(u_night) == 0:
            ax.set_title(f"{station_label(station)} (no valid u*)")
            ax.axis("off")
            continue

        used_any = True

        # Mediane berechnen
        median_day = np.median(u_day) if len(u_day) > 0 else np.nan
        median_night = np.median(u_night) if len(u_night) > 0 else np.nan

        # Plot histograms (density or counts) - Rückgabewerte für Höhen, Standard-Farben (weniger grell)
        n_night, bins_night, patches_night = ax.hist(u_night, bins=BINS_USTAR, density=DENSITY, alpha=0.6, label="Night")
        n_day, bins_day, patches_day = ax.hist(u_day, bins=BINS_USTAR, density=DENSITY, alpha=0.6, label="Day")
        
        # Farben aus den Histogrammen extrahieren
        color_night = patches_night[0].get_facecolor() if len(patches_night) > 0 else "C0"
        color_day = patches_day[0].get_facecolor() if len(patches_day) > 0 else "C1"
        # Falls RGBA, zu RGB konvertieren für Text/Linien
        if isinstance(color_night, (tuple, list)) and len(color_night) > 3:
            color_night = tuple(color_night[:3])
        if isinstance(color_day, (tuple, list)) and len(color_day) > 3:
            color_day = tuple(color_day[:3])

        # Y-Achse: Skalenbereich setzen
        ax.set_ylim(0, YMAX)
        ymin, ymax = ax.get_ylim()
        y_cap_night = ymax * 0.93  # obere Grenze für nächtlichen Median (bleibt bei allen Stationen in der Plotbox)
        y_cap_day = ymax * 0.98
        if not np.isnan(median_night) and len(u_night) > 0:
            y_max_night = np.max(n_night) if len(n_night) > 0 else 0
            y_text_night = min(y_max_night * 1.05, y_cap_night)
            ax.plot([median_night, median_night], [0, y_text_night], color=color_night, linestyle="--", linewidth=1.5, alpha=0.7)
            ax.text(median_night, y_text_night, f"{median_night:.2f}", ha="center", va="bottom", fontsize=FONTSIZE, color=color_night, fontweight="bold")
        if not np.isnan(median_day) and len(u_day) > 0:
            y_max_day = np.max(n_day) if len(n_day) > 0 else 0
            y_text_day = min(y_max_day * 1.05, y_cap_day)
            ax.plot([median_day, median_day], [0, y_text_day], color=color_day, linestyle="--", linewidth=1.5, alpha=0.7)
            ax.text(median_day, y_text_day, f"{median_day:.2f}", ha="center", va="bottom", fontsize=FONTSIZE, color=color_day, fontweight="bold")

        ax.set_title(station_label(station), fontsize=FONTSIZE)
        ax.grid(True, alpha=0.25)
        ax.tick_params(axis="both", labelsize=FONTSIZE)
        ax.legend(loc="lower right", fontsize=FONTSIZE, frameon=True)

        # Stability inset: Tag/Nacht-Unterscheidung mit Prozentzahlen über Balken
        if ADD_STABILITY_INSET and (z_col is not None):
            zdl = pd.to_numeric(df[z_col], errors="coerce")
            st_all = classify_stability(zdl).dropna()
            
            if not st_all.empty:
                # Stabilität für Tag und Nacht getrennt
                st_day = classify_stability(zdl[mask_day]).dropna()
                st_night = classify_stability(zdl[mask_night]).dropna()
                
                order = ["stable", "near-neutral", "unstable"]
                pct_day = np.array([(st_day.value_counts().get(k, 0) / len(st_day) * 100) if len(st_day) > 0 else 0 for k in order], dtype=float)
                pct_night = np.array([(st_night.value_counts().get(k, 0) / len(st_night) * 100) if len(st_night) > 0 else 0 for k in order], dtype=float)
                
                inset = ax.inset_axes([0.42, 0.58, 0.56, 0.35])
                x = np.arange(len(order))
                width = 0.35
                bars_day = inset.bar(x - width/2, pct_day, width, label="Day", color=color_day, alpha=0.7)
                bars_night = inset.bar(x + width/2, pct_night, width, label="Night", color=color_night, alpha=0.7)
                
                # Prozentzahlen über die Balken
                for bars, pct_vals in [(bars_day, pct_day), (bars_night, pct_night)]:
                    for bar, pct_val in zip(bars, pct_vals):
                        if pct_val > 0:
                            height = bar.get_height()
                            inset.text(bar.get_x() + bar.get_width()/2., height,
                                     f'{pct_val:.0f}%', ha='center', va='bottom',
                                     fontsize=FONTSIZE - 3, fontweight='bold')
                
                inset.set_xticks(x)
                inset.set_xticklabels(["Stab", "Neu", "Unst"], fontsize=FONTSIZE - 2)
                inset.set_ylim(0, 100)
                inset.set_yticks([0, 50, 100])
                inset.tick_params(axis="y", labelsize=FONTSIZE - 2)
                inset.set_title("(z-d)/L %", fontsize=FONTSIZE - 2)
                inset.grid(True, axis="y", alpha=0.25)
               # inset.legend(fontsize=FONTSIZE - 3, loc="upper right")

        # Sample sizes etwas unterhalb der Mitte
        ax.text(
            0.5,
            0.35,
            f"n(day)={len(u_day):,}\n"
            f"n(night)={len(u_night):,}",
            transform=ax.transAxes,
            va="center",
            ha="center",
            fontsize=FONTSIZE,
            bbox=dict(boxstyle="round,pad=0.25", facecolor="white", alpha=0.7, linewidth=0.0),
        )

    # Y-Achse "Density" nur in 1. Spalte; Density-Zahlen auf allen Y-Achsen
    for i in range(0, n_plots, n_cols):
        axes[i].set_ylabel("Density" if DENSITY else "Count", fontsize=FONTSIZE)
    for i in range(n_plots):
        axes[i].tick_params(axis="y", labelleft=True, labelsize=FONTSIZE)
    # X-Achsen: Label nur unten, aber Werte auf allen
    for i in range(max(0, n_plots - n_cols), n_plots):
        axes[i].set_xlabel("Friction velocity u* (m s$^{-1}$)", fontsize=FONTSIZE)
    for i in range(n_plots):
        axes[i].tick_params(axis="x", labelbottom=True, labelsize=FONTSIZE)

    #fig.suptitle("Turbulence fingerprint: u* distributions (day vs night) with stability overview", y=0.98, fontsize=FONTSIZE + 2)
    fig.tight_layout(rect=[0, 0, 1, 0.96])

    if not used_any:
        print("[ERROR] No stations produced valid plots.")
        return

    plt.savefig(OUT_PNG, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"✓ Saved: {OUT_PNG}")


if __name__ == "__main__":
    main()
