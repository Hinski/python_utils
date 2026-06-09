"""
Alignment test for the three Mole EddyPro files (Rn vs LE+H cross-correlation).

Loads Mole radiation (CR6) once to get Rn, then for each EddyPro full-output file
(fluxes/ and Samuels_eddypro_runs/) runs the same cross-correlation analysis as
in cross_correlation_alignment.py. Reports lag at maximum correlation for each
file and for the merged dataset (newer overwrites older) to detect timestamp
or convention differences between files.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import signal

sys.path.insert(0, str(Path(__file__).parent.parent))

from ec_analysis import load_ec_data, filter_quality_flags
from ec_analysis.aggregation import safe_slice
from ec_analysis.data_loaders.variable_mapping import map_dataframe_columns

# =============================================================================
# CONFIGURATION
# =============================================================================
OUTPUT_BASE = Path("/Users/hingerl-l/Data")
DATA_DIR = Path("/Users/hingerl-l/Data/merged_long")  # fallback for radiation parquet
STATION = "Mole"

# Mole radiation: try CR6 raw file first, then merged_long parquet (same as cross_correlation_alignment).
RADIATION_CANDIDATES = [
    OUTPUT_BASE / STATION / "raw" / "cr6" / "CR6Mole_Flux_CSFormat_15_11.dat",
    DATA_DIR / "Mole_radiation_merged_long.parquet",
]

# Date range for alignment test (same as typical EBC use for Mole)
START_DATE = "2022-01-01"
END_DATE = "2025-12-31"

# Cross-correlation: max lag ±12 h (24 * 30-min intervals)
MAX_LAG_INTERVALS = 24

PLOTS_DIR = Path(__file__).parent / "plots"
PLOTS_DIR.mkdir(exist_ok=True)


def get_mole_eddypro_files() -> list[Path]:
    """Return list of Mole EddyPro full-output CSV paths (fluxes/ + Samuels_eddypro_runs/), sorted by mtime (oldest first)."""
    base_dir = OUTPUT_BASE / STATION / "processed" / "fluxes"
    candidates: list[Path] = []
    if base_dir.exists():
        candidates.extend(sorted(base_dir.glob("eddypro_Mole_full_output_*.csv")))
    sam_dir = base_dir / "Samuels_eddypro_runs"
    if sam_dir.exists():
        candidates.extend(sorted(sam_dir.glob("eddypro_Mole_full_output_*.csv")))
    return sorted(candidates, key=lambda p: p.stat().st_mtime)


def load_mole_rn() -> tuple[pd.Series | None, Path | None]:
    """
    Load Mole radiation from first available source; return (Rn, path_used) or (None, None).

    Priority per file:
    1) Use mapped 'Rn' or raw 'NETRAD' if present.
    2) Otherwise try to compute Rn = SW_IN - SW_OUT + LW_IN - LW_OUT.
    """
    for path in RADIATION_CANDIDATES:
        if not path or not path.exists():
            continue
        fmt = "toa5" if path.suffix.lower() == ".dat" else None
        try:
            df = load_ec_data(path, format=fmt)
        except Exception:
            continue
        if df is None or df.empty:
            continue

        map_dataframe_columns(df, inplace=True)

        # 1) Prefer direct net radiation if available
        rn_series = df.get("Rn", df.get("NETRAD", None))
        if rn_series is not None:
            rn_series = pd.to_numeric(rn_series, errors="coerce")
            rn_series = rn_series.reindex(df.index)
            rn_series.name = "Rn"
            if rn_series.notna().any():
                return rn_series, path

        # 2) Fallback: compute from components
        sw_in = df.get("SW_IN", df.get("SR_in_Avg", None))
        sw_out = df.get("SW_OUT", df.get("SR_out_Avg", None))
        lw_in = df.get("LW_IN", df.get("IR_in_Avg", None))
        lw_out = df.get("LW_OUT", df.get("IR_out_Avg", None))
        if sw_in is None or sw_out is None or lw_in is None or lw_out is None:
            continue
        sw_in = pd.to_numeric(sw_in, errors="coerce")
        sw_out = pd.to_numeric(sw_out, errors="coerce")
        lw_in = pd.to_numeric(lw_in, errors="coerce")
        lw_out = pd.to_numeric(lw_out, errors="coerce")
        rn_series = sw_in - sw_out + lw_in - lw_out
        rn_series = rn_series.reindex(df.index)
        rn_series.name = "Rn"
        if rn_series.notna().any():
            return rn_series, path

    return None, None


def load_eddypro_le_h(path: Path) -> tuple[pd.Series | None, pd.Series | None]:
    """Load one EddyPro CSV, map columns, return (LE, H) with qc filtering if columns exist."""
    try:
        df = load_ec_data(path, format="eddypro")
    except Exception:
        return None, None
    if df is None or df.empty:
        return None, None
    map_dataframe_columns(df, inplace=True)
    LE = df.get("LE", None)
    H = df.get("H", None)
    if LE is None or H is None:
        return None, None
    LE = pd.to_numeric(LE, errors="coerce")
    H = pd.to_numeric(H, errors="coerce")
    if "qc_LE" in df.columns:
        LE = filter_quality_flags(df, "qc_LE", max_flag=1, data_column="LE")
    if "qc_H" in df.columns:
        H = filter_quality_flags(df, "qc_H", max_flag=1, data_column="H")
    if LE is not None:
        LE = LE[LE > -200]
    return LE, H


def run_cross_correlation(
    Rn: pd.Series,
    LE: pd.Series,
    H: pd.Series,
    start: str,
    end: str,
    max_lag: int = MAX_LAG_INTERVALS,
) -> dict | None:
    """
    Align Rn and LE+H to common 30-min index, run cross-correlation.
    Returns dict with lag_at_max, max_corr, corr_at_zero, n_points, lags, correlation (for plotting).
    """
    Rn_s = safe_slice(Rn, start, end)
    LE_s = safe_slice(LE, start, end)
    H_s = safe_slice(H, start, end)
    LE_H = LE_s + H_s

    freq = "30min"
    Rn_r = Rn_s.resample(freq).mean()
    LE_H_r = LE_H.resample(freq).mean()

    common = Rn_r.index.intersection(LE_H_r.index)
    Rn_a = Rn_r.loc[common].dropna()
    LE_H_a = LE_H_r.loc[common].dropna()
    common_final = Rn_a.index.intersection(LE_H_a.index)
    Rn_f = Rn_a.loc[common_final]
    LE_H_f = LE_H_a.loc[common_final]

    if len(Rn_f) < max_lag * 2 + 1:
        return None

    Rn_norm = (Rn_f - Rn_f.mean()) / Rn_f.std()
    LE_H_norm = (LE_H_f - LE_H_f.mean()) / LE_H_f.std()
    valid = Rn_norm.notna() & LE_H_norm.notna()
    Rn_c = Rn_norm[valid].values
    LE_H_c = LE_H_norm[valid].values

    corr = signal.correlate(Rn_c, LE_H_c, mode="full")
    lags = signal.correlation_lags(len(Rn_c), len(LE_H_c), mode="full")
    corr = corr / (len(Rn_c) * np.std(Rn_c) * np.std(LE_H_c))

    lag_mask = (lags >= -max_lag) & (lags <= max_lag)
    lags_f = lags[lag_mask]
    corr_f = corr[lag_mask]

    idx_max = np.argmax(np.abs(corr_f))
    lag_at_max = int(lags_f[idx_max])
    max_corr = float(corr_f[idx_max])
    corr_at_zero = float(corr_f[lags_f == 0][0]) if (lags_f == 0).any() else np.nan

    return {
        "lag_at_max": lag_at_max,
        "lag_minutes": lag_at_max * 30,
        "max_corr": max_corr,
        "corr_at_zero": corr_at_zero,
        "n_points": len(Rn_f),
        "lags": lags_f,
        "correlation": corr_f,
    }


def main() -> None:
    print("=" * 60)
    print("Mole EddyPro alignment test (Rn vs LE+H cross-correlation)")
    print("=" * 60)

    Rn, rn_path = load_mole_rn()
    if Rn is None:
        print("ERROR: Could not load Mole radiation (Rn). Tried:")
        for p in RADIATION_CANDIDATES:
            print(f"   - {p} (exists: {p.exists()})")
        return
    print(f"✓ Rn loaded from {rn_path} ({Rn.notna().sum()} values)")

    files = get_mole_eddypro_files()
    if not files:
        print("ERROR: No Mole EddyPro full-output files found.")
        return
    print(f"✓ Found {len(files)} EddyPro file(s):")
    for p in files:
        print(f"   - {p.relative_to(p.parent.parent.parent)} (mtime: {pd.Timestamp.fromtimestamp(p.stat().st_mtime)})")

    results: list[tuple[str, dict]] = []

    for path in files:
        LE, H = load_eddypro_le_h(path)
        if LE is None or H is None:
            print(f"  Skip {path.name}: could not load LE/H")
            continue
        out = run_cross_correlation(Rn, LE, H, START_DATE, END_DATE)
        if out is None:
            print(f"  Skip {path.name}: insufficient data for cross-correlation")
            continue
        label = path.name
        results.append((label, out))
        lag_min = out["lag_minutes"]
        if out["lag_at_max"] != 0:
            direction = "AHEAD of Rn" if out["lag_at_max"] > 0 else "BEHIND Rn"
            print(f"\n  {label}")
            print(f"    Lag at max corr: {out['lag_at_max']} intervals ({lag_min} min) → LE+H {direction}")
            print(f"    Max correlation: {out['max_corr']:.4f}, at lag 0: {out['corr_at_zero']:.4f}, N={out['n_points']}")
        else:
            print(f"\n  {label}: lag 0 (aligned), max_corr={out['max_corr']:.4f}, N={out['n_points']}")

    # Merged dataset (same logic as load_eddypro_for_mole: concat, keep='last' on duplicates)
    if len(files) > 1:
        from ec_analysis.data_loaders.variable_mapping import COLUMN_MAPPING
        standard_names = set(COLUMN_MAPPING.values())
        frames = []
        for path in files:
            try:
                df = load_ec_data(path, format="eddypro")
            except Exception:
                continue
            if df is None or df.empty:
                continue
            map_dataframe_columns(df, inplace=True)
            keep = [c for c in df.columns if c in standard_names]
            if not keep or "LE" not in keep or "H" not in keep:
                continue
            frames.append(df[keep].copy())
        if frames:
            df_merged = pd.concat(frames).sort_index()
            df_merged = df_merged[~df_merged.index.duplicated(keep="last")]
            LE_m = df_merged.get("LE")
            H_m = df_merged.get("H")
            if LE_m is not None and H_m is not None:
                LE_m = pd.to_numeric(LE_m, errors="coerce")
                H_m = pd.to_numeric(H_m, errors="coerce")
                if "qc_LE" in df_merged.columns:
                    LE_m = filter_quality_flags(df_merged, "qc_LE", max_flag=1, data_column="LE")
                if "qc_H" in df_merged.columns:
                    H_m = filter_quality_flags(df_merged, "qc_H", max_flag=1, data_column="H")
                if LE_m is not None:
                    LE_m = LE_m[LE_m > -200]
                out_m = run_cross_correlation(Rn, LE_m, H_m, START_DATE, END_DATE)
                if out_m is not None:
                    results.append(("merged (newer overwrites older)", out_m))
                    print(f"\n  merged (newer overwrites older): lag at max = {out_m['lag_at_max']} ({out_m['lag_minutes']} min), max_corr={out_m['max_corr']:.4f}, N={out_m['n_points']}")

    # Summary table
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"{'Source':<45} {'Lag (int)':<10} {'Lag (min)':<10} {'max_corr':<10} {'corr@0':<10} {'N':<8}")
    print("-" * 95)
    for label, out in results:
        short = label[:44] if len(label) > 44 else label
        print(f"{short:<45} {out['lag_at_max']:<10} {out['lag_minutes']:<10} {out['max_corr']:<10.4f} {out['corr_at_zero']:<10.4f} {out['n_points']:<8}")

    # Plot: one subplot per source (cross-correlation curve)
    if results:
        n_curves = len(results)
        ncols = min(2, n_curves)
        nrows = (n_curves + ncols - 1) // ncols
        fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 4 * nrows), squeeze=False)
        axes_flat = axes.flatten()
        for idx, (label, out) in enumerate(results):
            ax = axes_flat[idx]
            lags_min = out["lags"] * 30
            ax.plot(lags_min, out["correlation"], "b-", linewidth=2, label="Cross-correlation")
            ax.axvline(out["lag_minutes"], color="r", linestyle="--", linewidth=1.5, label=f"Max at {out['lag_minutes']} min")
            ax.axvline(0, color="k", linestyle=":", alpha=0.5)
            ax.set_xlabel("Lag (minutes)")
            ax.set_ylabel("Cross-correlation")
            ax.set_title(f"{label[:50]}\nlag={out['lag_at_max']} ({out['lag_minutes']} min), corr@0={out['corr_at_zero']:.3f}")
            ax.grid(True, alpha=0.3)
            ax.set_xlim(-MAX_LAG_INTERVALS * 30, MAX_LAG_INTERVALS * 30)
            ax.legend(fontsize=8)
        for j in range(len(results), len(axes_flat)):
            axes_flat[j].set_visible(False)
        plt.tight_layout()
        fig.savefig(PLOTS_DIR / "mole_eddypro_alignment_test.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"\n✓ Plot saved: {PLOTS_DIR.name}/mole_eddypro_alignment_test.png")

    print("\n✅ Alignment test complete.")


if __name__ == "__main__":
    main()
