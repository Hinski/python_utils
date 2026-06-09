#!/usr/bin/env python3
"""
Gap-length distribution for EC time series (ESSD-style diagnostic).

Creates a 2×3 subplot figure (six stations). For each station it computes the
distribution of consecutive missing-data runs ("gaps") for LE, H, and CO2
on the 30-min grid, and plots gap-length histograms (log-binned) as lines.

- Gaps include both:
  (a) missing timestamps on the 30-min grid (after reindexing), and
  (b) NaNs in the variable itself.
- Optional QC filtering using EddyPro quality flags (QC<=1).

Input (from collect_all_variables_30min.py):
  {OUTPUT_BASE}/{station}/processed/all/{station}_all_variables_30min.csv

Output:
  gap_length_distribution.png
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# =============================================================================
# CONFIG
# =============================================================================
OUTPUT_BASE = Path("/Users/hingerl-l/Data")
STATIONS = ["Nazinga", "Kayoro", "Sumbrungu", "Mole", "Janga", "Gorigo"]

OUT_PNG = Path("gap_length_distribution.png")

# Zeitreihen-Begrenzung: exakt wie data_coverage_qc_heatmap.py (gleiche Zeiträume)
COVERAGE_START = pd.Timestamp("2013-01-01")
COVERAGE_END = pd.Timestamp("2025-12-31")
# Station-spezifische Fenster (wie Heatmap)
NAZINGA_EMPTY_FROM = pd.Timestamp("2022-04-01")   # Nazinga nur bis einschl. März 2022
GORIGO_START = pd.Timestamp("2017-05-01")         # Gorigo erst ab Mai 2017
GORIGO_EMPTY_FROM = pd.Timestamp("2024-09-01")    # Gorigo nur bis einschl. August 2022
KAYORO_EMPTY_FROM = pd.Timestamp("2025-09-01")    # Kayoro nur bis einschl. August 2025
SUMBRUNGU_EMPTY_FROM = pd.Timestamp("2016-03-01") # Sumbrungu nur bis einschl. Februar 2016

# Beschriftungen
FONTSIZE = 17
TICK_FONTSIZE = 15

# Which variables to analyze
VARS = ["LE", "H", "CO2"]
QC_FLAGS = {"LE": "qc_LE", "H": "qc_H", "CO2": "qc_o2_flux"}

APPLY_QC = True          # apply QC flags (QC<=1) before gap computation
QC_MAX = 1

# Expected time step
FREQ = "30min"
DT_HOURS = 0.5  # 30 min

# Log-like bins in HOURS (left edges). Feel free to adjust.
# Includes 0.5 h (one missing half-hour) up to 512 h (~21 days)
BINS_HOURS = np.array([0.5, 1, 2, 4, 8, 16, 24, 48, 96, 192, 384, 512], dtype=float)

# Plot style
PLOT_DENSITY = False     # False: counts per bin; True: normalized to fraction of gaps
YLOG = True              # log y-axis helps see long gaps
GRID_ALPHA = 0.25


# =============================================================================
# IO
# =============================================================================
def load_all_variables(station: str) -> pd.DataFrame | None:
    path = OUTPUT_BASE / station / "processed" / "all" / f"{station}_all_variables_30min.csv"
    if not path.exists():
        print(f"[WARN] Missing file: {path}")
        return None

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


def restrict_to_station_coverage(df: pd.DataFrame, station: str) -> pd.DataFrame:
    """Begrenzt die Zeitreihe auf das stationsspezifische Fenster (exakt wie data_coverage_qc_heatmap)."""
    df = df.loc[COVERAGE_START:COVERAGE_END]
    if station == "Nazinga":
        df = df[df.index < NAZINGA_EMPTY_FROM]
    elif station == "Gorigo":
        df = df[(df.index >= GORIGO_START) & (df.index < GORIGO_EMPTY_FROM)]
    elif station == "Kayoro":
        df = df[df.index < KAYORO_EMPTY_FROM]
    elif station == "Sumbrungu":
        df = df[df.index < SUMBRUNGU_EMPTY_FROM]
    # Mole, Janga: kein Schnitt, voller Zeitraum 2013–2025
    return df


# =============================================================================
# GAP COMPUTATION
# =============================================================================
def apply_qc_flag(s: pd.Series, qc: pd.Series, max_flag: int = 1) -> pd.Series:
    qc_num = pd.to_numeric(qc, errors="coerce")
    s_num = pd.to_numeric(s, errors="coerce")
    bad = (qc_num > max_flag) | qc_num.isna()
    s_num = s_num.copy()
    s_num.loc[bad] = np.nan
    return s_num


def run_lengths(mask: np.ndarray) -> np.ndarray:
    """
    mask: boolean array, True indicates "gap" (missing).
    returns lengths of consecutive True runs.
    """
    if mask.size == 0:
        return np.array([], dtype=int)

    # Find run starts/ends
    diff = np.diff(mask.astype(int))
    starts = np.where(diff == 1)[0] + 1
    ends = np.where(diff == -1)[0] + 1

    # If mask begins with True, include start=0
    if mask[0]:
        starts = np.r_[0, starts]
    # If mask ends with True, include end=len(mask)
    if mask[-1]:
        ends = np.r_[ends, mask.size]

    lengths = ends - starts
    return lengths.astype(int)


def compute_gap_lengths_hours(df: pd.DataFrame, var: str) -> np.ndarray:
    """
    Returns array of gap lengths (in hours) for a given station and variable.
    Includes missing timestamps (after reindexing to full 30-min grid).
    """
    if var not in df.columns:
        return np.array([], dtype=float)

    s = pd.to_numeric(df[var], errors="coerce")

    # Optional QC
    if APPLY_QC and var in QC_FLAGS and QC_FLAGS[var] in df.columns:
        s = apply_qc_flag(s, df[QC_FLAGS[var]], max_flag=QC_MAX)

    # Reindex to continuous 30-min grid to count missing timestamps as gaps
    start = s.index.min()
    end = s.index.max()
    if pd.isna(start) or pd.isna(end):
        return np.array([], dtype=float)

    full_index = pd.date_range(start=start, end=end, freq=FREQ)
    s_full = s.reindex(full_index)

    gap_mask = s_full.isna().to_numpy()
    lengths_steps = run_lengths(gap_mask)

    # Convert to hours (each step is 0.5h)
    lengths_hours = lengths_steps.astype(float) * DT_HOURS
    # Remove zero-length (shouldn't exist) and very tiny
    lengths_hours = lengths_hours[lengths_hours > 0]
    return lengths_hours


def hist_counts(values: np.ndarray, bins_hours: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Returns (bin_centers, counts_or_density) for values in hours.
    Bins are defined by edges = [bins..., inf] so last bin is open-ended.
    """
    if values.size == 0:
        edges = np.r_[bins_hours, np.inf]
        counts = np.zeros(len(edges) - 1, dtype=float)
        centers = np.sqrt(edges[:-1] * np.minimum(edges[1:], edges[:-1] * 2))  # geometric-ish
        centers[-1] = bins_hours[-1] * 1.25
        return centers, counts

    edges = np.r_[bins_hours, np.inf]
    counts, _ = np.histogram(values, bins=edges)

    counts = counts.astype(float)
    if PLOT_DENSITY:
        denom = counts.sum()
        counts = counts / denom if denom > 0 else counts

    # Use geometric bin centers for log-like bins; last bin center is arbitrary
    centers = np.sqrt(edges[:-1] * np.minimum(edges[1:], edges[:-1] * 2))
    centers[-1] = bins_hours[-1] * 1.25
    return centers, counts


# =============================================================================
# PLOTTING
# =============================================================================
def main() -> None:
    fig, axes = plt.subplots(2, 3, figsize=(16, 9), sharex=True, sharey=True)
    axes = axes.ravel()

    any_plotted = False

    for i, station in enumerate(STATIONS):
        ax = axes[i]
        df = load_all_variables(station)
        if df is None or df.empty:
            ax.set_title(f"{station} (no data)", fontsize=FONTSIZE)
            ax.axis("off")
            continue

        df = restrict_to_station_coverage(df, station)
        if df.empty:
            ax.set_title(f"{station} (no data in station window)", fontsize=FONTSIZE)
            ax.axis("off")
            continue

        # Compute and plot for each variable
        gaps_by_var = {}
        for var in VARS:
            gaps = compute_gap_lengths_hours(df, var)
            gaps_by_var[var] = gaps
            centers, counts = hist_counts(gaps, BINS_HOURS)
            label = var if gaps.size > 0 else f"{var} (no gaps?)"
            ax.plot(centers, counts, marker="o", linewidth=1.3, markersize=4, label=label)
            any_plotted = any_plotted or (np.nanmax(counts) > 0)

        med_le = np.nanmedian(gaps_by_var["LE"])
        med_h = np.nanmedian(gaps_by_var["H"])
        med_c = np.nanmedian(gaps_by_var["CO2"])
        ax.text(
            0.63, 0.95,
            f"Median gap:\n"
            f"LE = {med_le:.1f} h\n"
            f"H = {med_h:.1f} h\n"
            f"CO$_2$ = {med_c:.1f} h",
            transform=ax.transAxes,
            va="top",
            ha="left",
            fontsize=FONTSIZE,
            bbox=dict(boxstyle="round,pad=0.25", facecolor="white", alpha=0.7),
        )

        ax.set_title(station, fontsize=FONTSIZE)
        ax.grid(True, which="both", alpha=GRID_ALPHA)
        ax.tick_params(axis="both", labelsize=TICK_FONTSIZE)

        if YLOG:
            ax.set_yscale("log")
            # avoid log(0)
            ymin = 0.8 if not PLOT_DENSITY else 1e-4
            ax.set_ylim(bottom=ymin)

    # Shared formatting
    for ax in axes[::3]:
        ax.set_ylabel("Fraction of gaps" if PLOT_DENSITY else "Number of gaps", fontsize=FONTSIZE)
    for ax in axes[-3:]:
        ax.set_xlabel("Gap length (hours)", fontsize=FONTSIZE)

    # x-axis log makes sense because bins are log-like
    for ax in axes:
        if ax.has_data():
            ax.set_xscale("log")
            ax.set_xlim(left=BINS_HOURS[0] * 0.9, right=BINS_HOURS[-1] * 1.6)
    axes[1].legend(loc="lower left", fontsize=TICK_FONTSIZE, frameon=True)
    qc_txt = f"QC≤{QC_MAX}" if APPLY_QC else "raw (no QC filter)"
    #fig.suptitle(f"Gap-length distributions on 30-min grid (LE, H, CO2) — {qc_txt}", fontsize=FONTSIZE + 2, y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.96])

    if not any_plotted:
        print("[ERROR] Nothing to plot (no gaps detected or no data).")
        return

    plt.savefig(OUT_PNG, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"✓ Saved: {OUT_PNG}")


if __name__ == "__main__":
    main()
