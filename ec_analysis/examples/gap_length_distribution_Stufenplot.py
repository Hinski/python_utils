#!/usr/bin/env python3
"""
Gap-length distribution for EC time series (ESSD-style diagnostic).

Option A: Plot as step-histogram using bin EDGES on the x-axis (no bin centers).
- Bins are log-like in hours.
- Last bin is open-ended [BINS_HOURS[-1], inf). For plotting we cap it at LAST_BIN_RIGHT
  so it becomes [BINS_HOURS[-1], LAST_BIN_RIGHT] visually (counts unchanged).
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
STATIONS = ["Nazinga", "Kayoro", "Sumbrungu", "Gorigo", "Janga", "Mole"]

OUT_PNG = Path("gap_length_distribution_hist.png")

# Station-specific time windows (as in your heatmap script)
COVERAGE_START = pd.Timestamp("2013-01-01")
COVERAGE_END = pd.Timestamp("2025-12-31")
NAZINGA_EMPTY_FROM = pd.Timestamp("2023-01-01")
GORIGO_START = pd.Timestamp("2017-04-01")
SUMBRUNGU_EMPTY_FROM = pd.Timestamp("2016-03-01")
MOLE_START = pd.Timestamp("2023-05-01")
JANGA_START = pd.Timestamp("2022-05-01")

# Labels
FONTSIZE = 17
TICK_FONTSIZE = 15

# Variables + QC flags
VARS = ["LE", "H", "CO2"]
QC_FLAGS = {"LE": "qc_LE", "H": "qc_H", "CO2": "qc_o2_flux"}

APPLY_QC = True
QC_MAX = 1

# Expected timestep
FREQ = "30min"
DT_HOURS = 0.5  # 30 min

# Bin edges (left edges) in HOURS; last bin is open-ended
BINS_HOURS = np.array([0.5, 1, 2, 4, 8, 16, 24, 48, 96, 192, 384, 512], dtype=float)
LAST_BIN_RIGHT = 1024.0  # only for plotting the open-ended last bin

# Plot style
PLOT_DENSITY = False   # False: counts per bin; True: fraction of gaps
YLOG = True
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
    df = df.loc[COVERAGE_START:COVERAGE_END]
    if station == "Nazinga":
        df = df[df.index < NAZINGA_EMPTY_FROM]
    elif station == "Gorigo":
        df = df[df.index >= GORIGO_START]
    elif station == "Sumbrungu":
        df = df[df.index < SUMBRUNGU_EMPTY_FROM]
    elif station == "Mole":
        df = df[df.index >= MOLE_START]
    elif station == "Janga":
        df = df[df.index >= JANGA_START]
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
    """Lengths of consecutive True runs in mask."""
    if mask.size == 0:
        return np.array([], dtype=int)

    diff = np.diff(mask.astype(int))
    starts = np.where(diff == 1)[0] + 1
    ends = np.where(diff == -1)[0] + 1

    if mask[0]:
        starts = np.r_[0, starts]
    if mask[-1]:
        ends = np.r_[ends, mask.size]

    return (ends - starts).astype(int)


def compute_gap_lengths_hours(df: pd.DataFrame, var: str) -> np.ndarray:
    """Gap-run lengths (hours), including missing timestamps after reindexing."""
    if var not in df.columns:
        return np.array([], dtype=float)

    s = pd.to_numeric(df[var], errors="coerce")

    if APPLY_QC and var in QC_FLAGS and QC_FLAGS[var] in df.columns:
        s = apply_qc_flag(s, df[QC_FLAGS[var]], max_flag=QC_MAX)

    start, end = s.index.min(), s.index.max()
    if pd.isna(start) or pd.isna(end):
        return np.array([], dtype=float)

    full_index = pd.date_range(start=start, end=end, freq=FREQ)
    s_full = s.reindex(full_index)

    gap_mask = s_full.isna().to_numpy()
    lengths_steps = run_lengths(gap_mask)

    lengths_hours = lengths_steps.astype(float) * DT_HOURS
    return lengths_hours[lengths_hours > 0]


def hist_counts(values: np.ndarray, bins_hours: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Returns (edges, counts_or_density).
    edges = [bins..., inf] for counting (open-ended last bin).
    """
    edges = np.r_[bins_hours, np.inf]
    if values.size == 0:
        counts = np.zeros(len(edges) - 1, dtype=float)
        return edges, counts

    counts, _ = np.histogram(values, bins=edges)
    counts = counts.astype(float)

    if PLOT_DENSITY:
        denom = counts.sum()
        counts = counts / denom if denom > 0 else counts

    return edges, counts


# =============================================================================
# PLOTTING (Option A)
# =============================================================================
def plot_step_hist(ax, edges: np.ndarray, counts: np.ndarray, label: str) -> None:
    """
    Step-hist with x = bin edges. For plotting, replace inf by LAST_BIN_RIGHT.
    We plot as 'post' steps: y[i] applies to [edge[i], edge[i+1]).
    """
    edges_plot = edges.copy()
    if np.isinf(edges_plot[-1]):
        edges_plot[-1] = LAST_BIN_RIGHT

    # For a post-step, y must have same length as x (or x-1 depending on approach).
    # We'll build y_post length = len(edges_plot), repeating last count.
    y_post = np.r_[counts, counts[-1] if len(counts) else 0.0]

    ax.step(edges_plot, y_post, where="post", linewidth=1.4, label=label)

    # Optional: markers at left edges (visual help, still edges-based)
    ax.plot(edges_plot[:-1], counts, marker="o", linestyle="None", markersize=3)


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

        gaps_by_var = {}
        for var in VARS:
            gaps = compute_gap_lengths_hours(df, var)
            gaps_by_var[var] = gaps
            edges, counts = hist_counts(gaps, BINS_HOURS)
            plot_step_hist(ax, edges, counts, label=var)
            any_plotted = any_plotted or (np.nanmax(counts) > 0)

        # Median info box
        med_le = np.nanmedian(gaps_by_var["LE"]) if gaps_by_var["LE"].size else np.nan
        med_h  = np.nanmedian(gaps_by_var["H"])  if gaps_by_var["H"].size  else np.nan
        med_c  = np.nanmedian(gaps_by_var["CO2"]) if gaps_by_var["CO2"].size else np.nan

        ax.text(
            0.63, 0.95,
            "Median gap:\n"
            f"LE  = {med_le:.1f} h\n"
            f"H   = {med_h:.1f} h\n"
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
            ymin = 0.8 if not PLOT_DENSITY else 1e-4
            ax.set_ylim(bottom=ymin)

        # Log-x fits the log-like bins
        ax.set_xscale("log")
        ax.set_xlim(left=BINS_HOURS[0] * 0.9, right=LAST_BIN_RIGHT * 1.05)

    # Shared labels
    for ax in axes[::3]:
        ax.set_ylabel("Fraction of gaps" if PLOT_DENSITY else "Number of gaps", fontsize=FONTSIZE)
    for ax in axes[-3:]:
        ax.set_xlabel("Gap length (hours; bin edges)", fontsize=FONTSIZE)

    # Legend (one panel is enough)
    axes[1].legend(loc="lower left", fontsize=TICK_FONTSIZE, frameon=True)

    fig.tight_layout(rect=[0, 0, 1, 1])

    if not any_plotted:
        print("[ERROR] Nothing to plot (no gaps detected or no data).")
        return

    plt.savefig(OUT_PNG, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"✓ Saved: {OUT_PNG}")


if __name__ == "__main__":
    main()
