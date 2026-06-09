"""
Diurnal cycles of energy balance components for dry and rainy seasons.

Season definition (based on absolute humidity qa, g/m³):
- Rainy: qa > 16 for a minimum of 5 consecutive days
- Dry:   qa < 6  for a minimum of 5 consecutive days
- Transitional: neither criterion met

Run collect_all_variables_30min.py and append_G_to_csv.py first.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent.parent))

from ec_analysis import calculate_soil_heat_flux, build_energy_balance_df

# ============================================================================
# CONFIGURATION
# ============================================================================
OUTPUT_BASE = Path("/Users/hingerl-l/Data")
STATION = "Mole"
START_DATE = "2022-01-01"
END_DATE = "2025-12-31"

# Season thresholds (absolute humidity qa in g/m³)
QA_RAINY_THRESHOLD = 16
QA_DRY_THRESHOLD = 6
QA_MIN_CONSECUTIVE_DAYS = 5

# Column aliases for qa (absolute humidity, g/m³). EddyPro: water_vapor_density in kg/m³, e in Pa.
QA_COL_ALIASES = ["qa", "AH", "absolute_humidity", "rho_h2o", "rho_w", "water_vapor_density"]
RAD_COL_ALIASES = {
    "SW_in": ["SW_in", "SR_in_Avg", "SW_IN", "SW_in korrigiert"],
    "SW_out": ["SW_out", "SR_out_Avg", "SW_OUT", "SW_out korrigiert", "SW_out korrigiert "],
    "LW_in": ["LW_in", "IR_in_Avg", "LW_IN"],
    "LW_out": ["LW_out", "IR_out_Avg", "LW_OUT"],
}


def _get_column(df: pd.DataFrame, aliases: list[str]):
    for name in aliases:
        if name in df.columns:
            return df[name]
    return None


def _infer_e_unit(e: pd.Series) -> float:
    """Return factor to convert e to Pa. EddyPro: Pa; others: hPa or kPa."""
    valid = pd.to_numeric(e, errors="coerce").dropna()
    if valid.empty:
        return 100
    med = valid.median()
    if med < 50:
        return 1000  # kPa
    if med < 1000:
        return 100   # hPa
    return 1         # Pa (EddyPro)


def qa_from_e_tair(e: pd.Series, T: pd.Series) -> pd.Series:
    """Compute absolute humidity qa (g/m³) from vapor pressure e and Tair (°C). Auto-detects e unit."""
    e_num = pd.to_numeric(e, errors="coerce")
    fac = _infer_e_unit(e_num)
    e_Pa = e_num * fac
    T_K = pd.to_numeric(T, errors="coerce") + 273.15
    return e_Pa * 18.015 / (8.314 * T_K)


def classify_seasons(qa_daily: pd.Series) -> pd.Series:
    """
    Classify each day as 'rainy', 'dry', or 'transitional'.
    Rainy: qa > 16 for ≥5 consecutive days.
    Dry:   qa < 6  for ≥5 consecutive days.
    """
    out = pd.Series("transitional", index=qa_daily.index, dtype=str)

    rainy_mask = qa_daily > QA_RAINY_THRESHOLD
    dry_mask = qa_daily < QA_DRY_THRESHOLD

    def mark_runs(mask: pd.Series, label: str) -> None:
        grp = (~mask).cumsum()
        for _, g in mask[mask].groupby(grp[mask]):
            if len(g) >= QA_MIN_CONSECUTIVE_DAYS:
                out.loc[g.index] = label

    mark_runs(rainy_mask, "rainy")
    mark_runs(dry_mask, "dry")

    return out


def load_data(station: str, start_date: str, end_date: str) -> pd.DataFrame | None:
    """Load all_variables CSV and return DataFrame with Rn, LE, H, G, qa, season."""
    path = OUTPUT_BASE / station / "processed" / "all" / f"{station}_all_variables_30min.csv"
    if not path.exists():
        print(f"  CSV not found: {path}")
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
    df = df.loc[(df.index >= start_date) & (df.index <= end_date)]

    qa = None
    qa_col_used = None
    for alias in QA_COL_ALIASES:
        col = _get_column(df, [alias])
        if col is not None:
            qa = pd.to_numeric(col, errors="coerce")
            qa_col_used = alias
            break
    if qa is None:
        e = df.get("e", df.get("e_Avg", df.get("e*", None)))
        T = df.get("Tair", df.get("Ta", df.get("T_Avg", None)))
        if e is not None and T is not None:
            qa = qa_from_e_tair(e, T)
            print(f"  Computed qa from e and Tair (e unit auto-detected)")
        else:
            print(f"  Missing qa and cannot compute from e/Tair. Columns: {list(df.columns)[:20]}...")
            return None
    elif qa_col_used == "water_vapor_density":
        qa = qa * 1000  # EddyPro: kg/m³ → g/m³

    qa_daily = qa.resample("D").mean()
    season_daily = classify_seasons(qa_daily)

    SW_in = _get_column(df, RAD_COL_ALIASES["SW_in"])
    SW_out = _get_column(df, RAD_COL_ALIASES["SW_out"])
    LW_in = _get_column(df, RAD_COL_ALIASES["LW_in"])
    LW_out = _get_column(df, RAD_COL_ALIASES["LW_out"])
    LE = pd.to_numeric(df.get("LE"), errors="coerce")
    H = pd.to_numeric(df.get("H"), errors="coerce")
    G = df.get("G", None)
    if G is None or pd.isna(G).all():
        try:
            G = calculate_soil_heat_flux(df, station=station, return_components=False)
        except Exception as e:
            print(f"  G calc failed: {e}")
            return None
    G = pd.to_numeric(G, errors="coerce")

    if not all([SW_in is not None, SW_out is not None, LW_in is not None, LW_out is not None]):
        print(f"  Missing radiation columns")
        return None

    SW_in = pd.to_numeric(SW_in, errors="coerce")
    SW_out = pd.to_numeric(SW_out, errors="coerce")
    LW_in = pd.to_numeric(LW_in, errors="coerce")
    LW_out = pd.to_numeric(LW_out, errors="coerce")
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
    if eb_df.empty:
        return None

    eb_df["season"] = [season_daily.get(pd.Timestamp(ts).normalize(), "transitional") for ts in eb_df.index]
    eb_df["qa"] = qa.reindex(eb_df.index).values
    return eb_df


def diurnal_cycle(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Hourly mean by hour of day. Filters LE/H to valid range (-300 to 800 W/m²)."""
    if df.empty:
        return pd.DataFrame()
    out = df[columns].copy()
    if "LE" in out.columns:
        out.loc[(out["LE"] < -300) | (out["LE"] > 800), "LE"] = np.nan
    if "H" in out.columns:
        out.loc[(out["H"] < -300) | (out["H"] > 800), "H"] = np.nan
    return out.groupby(df.index.hour).mean()


def main():
    print(f"Loading data for {STATION} ({START_DATE} – {END_DATE})...")
    df = load_data(STATION, START_DATE, END_DATE)
    if df is None:
        print("No data loaded.")
        return

    dry = df[df["season"] == "dry"]
    rainy = df[df["season"] == "rainy"]

    print(f"  Total: {len(df)} records")
    print(f"  Dry season: {len(dry)} records ({dry.index.normalize().nunique()} days)")
    print(f"  Rainy season: {len(rainy)} records ({rainy.index.normalize().nunique()} days)")

    cols = ["Rn", "LE", "H", "G"]
    hourly_dry = diurnal_cycle(dry, cols)
    hourly_rainy = diurnal_cycle(rainy, cols)

    colors = {"Rn": "#1f77b4", "LE": "#2ca02c", "H": "#ff7f0e", "G": "#d62728"}

    fig, axes = plt.subplots(2, 2, figsize=(12, 10), sharex=True)
    axes = axes.flatten()

    for i, col in enumerate(cols):
        ax = axes[i]
        if not hourly_dry.empty and col in hourly_dry.columns:
            ax.plot(hourly_dry.index, hourly_dry[col], "o-", color=colors[col], linewidth=2, markersize=6, label="Dry")
        if not hourly_rainy.empty and col in hourly_rainy.columns:
            ax.plot(hourly_rainy.index, hourly_rainy[col], "s--", color=colors[col], linewidth=2, markersize=6, alpha=0.8, label="Rainy")
        ax.set_ylabel(f"{col} (W/m²)")
        ax.axhline(y=0, color="black", linestyle=":", linewidth=0.5)
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.set_title(col)

    axes[0].set_xlabel("Hour of day")
    axes[1].set_xlabel("Hour of day")
    axes[2].set_xlabel("Hour of day")
    axes[3].set_xlabel("Hour of day")

    plt.suptitle(
        f"Diurnal cycle – {STATION}\n"
        f"Dry: qa < {QA_DRY_THRESHOLD} g/m³ for ≥{QA_MIN_CONSECUTIVE_DAYS} days  |  "
        f"Rainy: qa > {QA_RAINY_THRESHOLD} g/m³ for ≥{QA_MIN_CONSECUTIVE_DAYS} days",
        fontsize=12,
        fontweight="bold",
        y=1.02,
    )
    plt.tight_layout()

    out_path = Path(f"{STATION}_diurnal_dry_rainy_season.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"\n✓ Plot saved: {out_path}")
    plt.show()


if __name__ == "__main__":
    main()
