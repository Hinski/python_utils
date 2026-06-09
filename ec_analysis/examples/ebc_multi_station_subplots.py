"""
Energy Balance Closure: Multi-Station Subplots

Creates EBC plots for Nazinga, Kayoro, Sumbrungu, Mole, and Janga in a 2×3 layout.
Row 1: Nazinga, Kayoro, Sumbrungu | Row 2: Mole, Janga, Legend

Run collect_all_variables_30min.py and append_G_to_csv.py first.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from scipy.stats import pearsonr

sys.path.insert(0, str(Path(__file__).parent.parent))

from ec_analysis import build_energy_balance_df
try:
    import yaml
except ImportError:
    yaml = None

# ============================================================================
# CONFIGURATION
# ============================================================================
FINAL_ESSD_DIR = Path("/Users/hingerl-l/Data/essd_data_tables/final_datatables")
STATIONS = ["Nazinga", "Kayoro", "Sumbrungu", "Janga", "Mole"]  # Gorigo ausgelassen
STATION_LABELS = {
    "Nazinga": "Nazinga (protected forest)",
    "Mole": "Mole (managed forest)",
    "Kayoro": "Kayoro (cropland)",
    "Janga": "Janga (rainfed rice field)",
    "Sumbrungu": "Sumbrungu (degr. grassland)",
    "Gorigo": "Gorigo (semi-degr. grassland)",
}

# Zeitraum pro Station (start, end). Stationen ohne Eintrag nutzen DEFAULT_START/END.
# Beispiel: "Nazinga": ("2022-01-01", "2025-12-31"),
STATION_DATE_RANGES: dict[str, tuple[str, str]] = {
    "Nazinga": ("2013-01-01", "2016-12-31"),
    "Sumbrungu": ("2013-01-01", "2015-12-31"),
    "Kayoro": ("2013-01-01", "2015-12-31"),
    "Mole": ("2022-01-01", "2025-12-31"),
    "Janga": ("2022-01-01", "2025-12-31"),
}
DEFAULT_START = "2013-01-01"
DEFAULT_END = "2025-12-31"
QUALITY_FILTERS_CONFIG = Path(__file__).parent.parent / "ec_analysis" / "utils" / "quality_filters_config.yaml"

# Alternative column names for radiation (different stations use different conventions)
RAD_COL_ALIASES = {
    "SW_in": ["SW_IN", "SW_in", "SR_in_Avg", "SW_in korrigiert"],
    "SW_out": ["SW_OUT", "SW_out", "SR_out_Avg", "SW_out korrigiert", "SW_out korrigiert "],
    "LW_in": ["LW_IN", "LW_in", "IR_in_Avg"],
    "LW_out": ["LW_OUT", "LW_out", "IR_out_Avg"],
}
QC_COL_ALIASES = {
    "qc_LE": ["qc_LE", "LE_QC", "Flag(LE)", "qc_LvE", "Flag(LvE)"],
    "qc_H": ["qc_H", "H_QC", "Flag(H)", "qc_HTs", "Flag(HTs)"],
}
DATA_COL_ALIASES = {
    "LE": ["LE", "LE_Avg", "LvE", "LE_corr"],
    "H": ["H", "H_Avg", "Hc", "H_corr"],
    "G": ["G", "G_Avg", "G1", "SHF_Avg", "G_plate_1", "G_plate_1_1_1"],
    "SW_in": RAD_COL_ALIASES["SW_in"],
    "SW_out": RAD_COL_ALIASES["SW_out"],
    "LW_in": RAD_COL_ALIASES["LW_in"],
    "LW_out": RAD_COL_ALIASES["LW_out"],
    "Rn": ["NETRAD", "Rn", "Rn_Avg", "NetTot_Avg", "NETRAD_Avg"],
}


def station_label(station: str) -> str:
    """Lesbares Stationslabel fuer Plot-Titel/Legende."""
    return STATION_LABELS.get(station, station)


def _get_column(df: pd.DataFrame, aliases: list[str]):
    """Return first matching column from df."""
    for name in aliases:
        if name in df.columns:
            return df[name]
    return None


def _get_column_name(df: pd.DataFrame, aliases: list[str]) -> str | None:
    for name in aliases:
        if name in df.columns:
            return name
    return None


def apply_quality_and_physical_filters(df: pd.DataFrame, station: str) -> pd.DataFrame:
    """Apply QC flags and physical limits from quality_filters_config.yaml."""
    if yaml is None or not QUALITY_FILTERS_CONFIG.exists():
        return df

    out = df.copy()
    with QUALITY_FILTERS_CONFIG.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    global_cfg = cfg.get("global", {})
    station_cfg = cfg.get("stations", {}).get(station, {})

    # invalid codes
    invalid_codes = global_cfg.get("invalid_codes", [7999, -9999, -99999])
    for c in invalid_codes:
        if isinstance(c, (int, float)):
            out = out.replace(c, np.nan)
    if "NAN" in str(invalid_codes):
        out = out.replace(["NAN", "nan"], np.nan)

    # quality flags (map config names to actual ESSD/final_datatables columns)
    for item in station_cfg.get("quality_flags", []):
        flag_key = item.get("flag")
        data_key = item.get("data_column")
        max_flag = item.get("max_flag", 1)
        if not flag_key or not data_key:
            continue
        flag_col = _get_column_name(out, QC_COL_ALIASES.get(flag_key, [flag_key]))
        data_col = _get_column_name(out, DATA_COL_ALIASES.get(data_key, [data_key]))
        if flag_col is None or data_col is None:
            continue
        qc = pd.to_numeric(out[flag_col], errors="coerce")
        bad = (qc > max_flag) | qc.isna()
        out.loc[bad, data_col] = np.nan

    # physical limits (global + station override)
    global_limits = global_cfg.get("physical_limits", {})
    station_limits = station_cfg.get("physical_limits") or {}
    merged = {**global_limits, **station_limits}
    for key, lim in merged.items():
        if not isinstance(lim, dict):
            continue
        col = _get_column_name(out, DATA_COL_ALIASES.get(key, [key]))
        if col is None:
            continue
        vmin, vmax = lim.get("min"), lim.get("max")
        vals = pd.to_numeric(out[col], errors="coerce")
        mask = vals.notna()
        if vmin is not None:
            mask &= vals >= vmin
        if vmax is not None:
            mask &= vals <= vmax
        out.loc[~mask, col] = np.nan

    return out


def _candidate_paths_final_datatables(station: str) -> list[Path]:
    return [
        FINAL_ESSD_DIR / f"{station}_30min.csv",
        FINAL_ESSD_DIR / f"{station}_essd_30min_clean.csv",
        FINAL_ESSD_DIR / f"{station}_essd_30min.csv",
    ]


def load_station_ebc_data(station: str, start_date: str, end_date: str) -> dict | None:
    """Load final_datatables CSV and extract Rn, LE, H, G for EBC."""
    path = None
    for p in _candidate_paths_final_datatables(station):
        if p.exists():
            path = p
            break
    if path is None:
        print(f"  {station}: CSV not found in final_datatables")
        return None

    with path.open("r", encoding="utf-8") as f:
        header_line = f.readline().strip()
        _units_line = f.readline().strip()
    header = [c.strip() for c in header_line.split(",")]

    df = pd.read_csv(
        path,
        skiprows=2,
        header=None,
        names=header,
        low_memory=False,
        na_values=[-9999, "-9999", "-9999.0", -99999, "7999", "NAN", "nan", "NA"],
    )
    if "TIMESTAMP" not in df.columns or df["TIMESTAMP"].empty:
        print(f"  {station}: TIMESTAMP missing")
        return None
    ts = pd.to_datetime(df["TIMESTAMP"], format="%Y%m%d%H%M%S", errors="coerce")
    df = df.drop(columns=["TIMESTAMP"])
    df.index = ts
    df = df[df.index.notna()].sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df = apply_quality_and_physical_filters(df, station)

    SW_in = _get_column(df, RAD_COL_ALIASES["SW_in"])
    SW_out = _get_column(df, RAD_COL_ALIASES["SW_out"])
    LW_in = _get_column(df, RAD_COL_ALIASES["LW_in"])
    LW_out = _get_column(df, RAD_COL_ALIASES["LW_out"])

    LE = df.get("LE", None)
    H = df.get("H", None)
    G = df.get("G", None)

    LE = pd.to_numeric(LE, errors="coerce") if LE is not None else None
    H = pd.to_numeric(H, errors="coerce") if H is not None else None
    G = pd.to_numeric(G, errors="coerce") if G is not None else None

    # Same quality filtering as in energy_balance_closure.py: qc_LE/qc_H <= 1, LE > -200
    if LE is not None and "qc_LE" in df.columns:
        qc_le = pd.to_numeric(df["qc_LE"], errors="coerce")
        LE = LE.where((qc_le <= 1) & (qc_le.notna()))
    if H is not None and "qc_H" in df.columns:
        qc_h = pd.to_numeric(df["qc_H"], errors="coerce")
        H = H.where((qc_h <= 1) & (qc_h.notna()))
    if LE is not None:
        LE = LE.where(LE > -200)

    if not all([SW_in is not None, SW_out is not None, LW_in is not None, LW_out is not None]):
        print(f"  {station}: Missing radiation columns")
        return None
    if LE is None or H is None or G is None:
        print(f"  {station}: Missing LE, H, or G")
        return None
    if pd.isna(G).all():
        print(f"  {station}: G missing/empty in final_datatables")
        return None

    # Für Mole Rn explizit aus SW/LW-Komponenten ableiten:
    # Rn = SW_IN - SW_OUT + LW_IN - LW_OUT
    SW_in = pd.to_numeric(SW_in, errors="coerce")
    SW_out = pd.to_numeric(SW_out, errors="coerce")
    LW_in = pd.to_numeric(LW_in, errors="coerce")
    LW_out = pd.to_numeric(LW_out, errors="coerce")
    rn_mole = None
    if station == "Mole":
        rn_mole = SW_in - SW_out + LW_in - LW_out

    Delta = pd.Series(0, index=df.index)

    eb_df = build_energy_balance_df(
        SW_in=SW_in,
        SW_out=SW_out,
        LW_in=LW_in,
        LW_out=LW_out,
        LE=LE,
        H=H,
        G=G,
        Delta=Delta,
        start=start_date,
        end=end_date,
        site_name=station,
    )
    if station == "Mole" and rn_mole is not None and "Rn" in eb_df.columns:
        eb_df["Rn"] = rn_mole.reindex(eb_df.index)

    return {"eb_df": eb_df, "station": station}


# Font sizes for all labels
FONTSIZE_LABEL = 16
FONTSIZE_TICK = 14
FONTSIZE_LETTER = 16
FONTSIZE_EQ = 14


def plot_ebc_on_ax(ax, data: dict, letter: str, legend_entries: list, row: int, col: int) -> bool:
    """Plot EBC on given axes. Appends to legend_entries for summary. Returns success."""
    eb_df = data["eb_df"]
    station = data["station"]

    if eb_df.empty or (eb_df["Rn"] == 0).all():
        ax.text(0.5, 0.5, f"Insufficient data\nfor {station_label(station)}", ha="center", va="center", transform=ax.transAxes, fontsize=FONTSIZE_LABEL)
        ax.set_axis_off()
        return False

    LE_ebc = eb_df["LE"].copy()
    H_ebc = eb_df["H"].copy()
    Rn_ebc = eb_df["Rn"].copy()
    G_ebc = eb_df["G"].copy()
    Delta_ebc = eb_df.get("Delta", pd.Series(0, index=eb_df.index))

    x_data = Rn_ebc - G_ebc
    if Delta_ebc.notna().any() and (Delta_ebc != 0).any():
        x_data = x_data - Delta_ebc

    valid_mask = (LE_ebc >= -300) & (LE_ebc <= 800) & (H_ebc >= -300) & (H_ebc <= 800)
    x_data = x_data[valid_mask]
    LE_ebc = LE_ebc[valid_mask]
    H_ebc = H_ebc[valid_mask]
    LE_H_ebc = LE_ebc + H_ebc

    mask_valid = x_data.notna() & LE_H_ebc.notna()
    x_clean = x_data[mask_valid]
    y_clean = LE_H_ebc[mask_valid]

    mask_final = np.isfinite(x_clean) & np.isfinite(y_clean)
    x_final = x_clean[mask_final]
    y_final = y_clean[mask_final]

    if len(x_final) < 10:
        ax.text(0.5, 0.5, f"Insufficient data\nfor {station_label(station)}", ha="center", va="center", transform=ax.transAxes, fontsize=FONTSIZE_LABEL)
        ax.set_axis_off()
        return False

    coeffs = np.polyfit(x_final, y_final, 1)
    slope = coeffs[0]
    intercept = coeffs[1]
    corr, _ = pearsonr(x_final, y_final)
    r2 = corr**2
    closure_sum = np.sum(y_final) / np.sum(x_final) if np.sum(x_final) != 0 else 0

    legend_entries.append((letter, station_label(station), slope, intercept, closure_sum, r2, len(x_final)))

    ax.scatter(x_clean, y_clean, alpha=0.5, s=20, edgecolors="none", color="black")

    x_reg = np.array([-200, 1000])
    y_reg = slope * x_reg + intercept
    ax.plot(x_reg, y_reg, "r-", linewidth=1.5, zorder=2)
    ax.plot([-200, 1000], [-200, 1000], "--", color="grey", linewidth=1.5, zorder=1)

    ax.set_xlim(-200, 1000)
    ax.set_ylim(-200, 1000)
    # LE + H nur links (col 0), Rn - G nur in unterster Zeile (row 1)
    if col == 0:
        ax.set_ylabel("LE + H [W/m²]", fontsize=FONTSIZE_LABEL)
    if row == 1:
        ax.set_xlabel("Rn - G [W/m²]", fontsize=FONTSIZE_LABEL)

    ax.text(0.02, 0.98, f"{letter})", transform=ax.transAxes, fontsize=FONTSIZE_LETTER, fontweight="bold", verticalalignment="top")
    # Formatierung wie vor der heutigen Rücknahme (.2f)
    eq_text = f"y = {slope:.2f}x + {intercept:.2f}\nR² = {r2:.2f}\nCumulative EBC = {closure_sum:.2f}"
    ax.text(0.98, 0.02, eq_text, transform=ax.transAxes, fontsize=FONTSIZE_EQ, verticalalignment="bottom", horizontalalignment="right", bbox=dict(boxstyle="round", facecolor="white", alpha=0.8))

    ax.tick_params(labelsize=FONTSIZE_TICK)
    ax.grid(True, alpha=0.3)
    ax.set_aspect("equal", adjustable="box")
    return True


def main():
    print("Loading EBC data for all stations...")
    all_data = {}
    for station in STATIONS:
        start_date, end_date = STATION_DATE_RANGES.get(
            station, (DEFAULT_START, DEFAULT_END)
        )
        d = load_station_ebc_data(station, start_date, end_date)
        if d is not None:
            all_data[station] = d
            print(f"  ✓ {station}: {len(d['eb_df'])} records ({start_date} – {end_date})")

    if not all_data:
        print("No data loaded. Run collect_all_variables_30min.py and append_G_to_csv.py first.")
        return

    # 2×3-Layout:
    # Zeile 1: Nazinga, Kayoro, Sumbrungu
    # Zeile 2: Mole, Janga, Legende
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))

    layout = [
        (0, 0, "Nazinga", "a"),
        (0, 1, "Kayoro", "b"),
        (0, 2, "Sumbrungu", "c"),
        (1, 0, "Mole", "d"),
        (1, 1, "Janga", "e"),
    ]

    legend_entries = []
    for row, col, station, letter in layout:
        ax = axes[row, col]
        if station in all_data:
            plot_ebc_on_ax(ax, all_data[station], letter, legend_entries, row, col)
        else:
            ax.text(0.5, 0.5, f"No data\nfor {station_label(station)}", ha="center", va="center", transform=ax.transAxes, fontsize=FONTSIZE_LABEL)
            ax.text(0.02, 0.98, f"{letter})", transform=ax.transAxes, fontsize=FONTSIZE_LETTER, fontweight="bold", verticalalignment="top")
            ax.set_axis_off()

    # Legend in zweiter Zeile, dritte Spalte: Stationen + Regression + 1:1
    ax_leg = axes[1, 2]
    ax_leg.set_axis_off()
    if legend_entries:
        handles = [
            Line2D([0], [0], linestyle="", marker="", color="none", label=f"{letter}) {station}")
            for letter, station, *_ in legend_entries
        ]
        handles += [
            Line2D([0], [0], color="red", linewidth=2, label="Regression"),
            Line2D([0], [0], color="grey", linestyle="--", linewidth=1.5, label="1:1"),
        ]
        ax_leg.legend(handles=handles, loc="center", fontsize=18, framealpha=0.9)

    #plt.suptitle("Energy Balance Closure", fontsize=18, fontweight="bold", y=1.02)
    plt.tight_layout(pad=0.5, h_pad=0.3, w_pad=0.05)

    out_path = Path("EBC_multi_station_subplots.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"\n✓ Plot saved: {out_path}")
    plt.show()


if __name__ == "__main__":
    main()
