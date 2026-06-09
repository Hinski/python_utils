"""
Mittlerer Tagesgang nach Rainy/Dry Season (qa-Kriterium).

Gleicher Plot wie diurnal_cycle_all_stations, aber unterteilt:
- Dry: qa < 6 g/m³ für ≥5 aufeinanderfolgende Tage
- Rainy: qa > 16 g/m³ für ≥5 aufeinanderfolgende Tage
Solid = Dry, dashed = Rainy. Schwarzweiß.

Lädt EddyPro direkt aus /Users/hingerl-l/Data/{station}/processed/fluxes/
(jeweils die aktuellste Datei mit full_output im Namen) und merged mit
Strahlung/G aus den gleichen Quellen wie collect_all_variables_30min.py.
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
STATIONS = ["Nazinga", "Kayoro", "Sumbrungu", "Gorigo", "Janga", "Mole"]

STATION_DATE_RANGES: dict[str, tuple[str, str]] = {
    "Nazinga": ("2013-01-01", "2016-12-31"),
    "Sumbrungu": ("2013-01-01", "2015-12-31"),
    "Kayoro": ("2013-01-01", "2015-12-31"),
    "Mole": ("2022-01-01", "2025-12-31"),
    "Janga": ("2022-01-01", "2025-12-31"),
    "Gorigo": ("2017-01-01", "2025-12-31"),
}
DEFAULT_START = "2013-01-01"
DEFAULT_END = "2025-12-31"

QA_RAINY_THRESHOLD = 16
QA_DRY_THRESHOLD = 6
QA_MIN_CONSECUTIVE_DAYS = 5

QA_COL_ALIASES = ["qa", "AH", "absolute_humidity", "rho_h2o", "rho_w", "water_vapor_density"]
RAD_COL_ALIASES = {
    "SW_in": ["SW_in", "SR_in_Avg", "SW_IN", "SW_in korrigiert"],
    "SW_out": ["SW_out", "SR_out_Avg", "SW_OUT", "SW_out korrigiert", "SW_out korrigiert "],
    "LW_in": ["LW_in", "IR_in_Avg", "LW_IN"],
    "LW_out": ["LW_out", "IR_out_Avg", "LW_OUT"],
}

COMPONENT_STYLES = {
    "Rn": {"color": "0.1"},
    "LE": {"color": "0.35"},
    "H": {"color": "0.55"},
    "minus_G": {"color": "0.8"},
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
        return 100  # default assume hPa
    med = valid.median()
    if med < 50:
        return 1000  # kPa
    if med < 1000:
        return 100   # hPa
    return 1         # Pa (EddyPro)


def qa_from_e_tair(e: pd.Series, T: pd.Series) -> pd.Series:
    """Compute qa (g/m³) from vapor pressure e and Tair (°C). Auto-detects e unit."""
    e_num = pd.to_numeric(e, errors="coerce")
    fac = _infer_e_unit(e_num)
    e_Pa = e_num * fac
    T_K = pd.to_numeric(T, errors="coerce") + 273.15
    return e_Pa * 18.015 / (8.314 * T_K)


def _log_qa_stats(station: str, qa_daily: pd.Series) -> None:
    """Print qa range for debugging (dry < 6, rainy > 16 g/m³)."""
    valid = qa_daily.dropna()
    if valid.empty:
        return
    lo, med, hi = valid.min(), valid.median(), valid.max()
    n_dry = (valid < QA_DRY_THRESHOLD).sum()
    n_rainy = (valid > QA_RAINY_THRESHOLD).sum()
    print(f"    {station}: qa daily min={lo:.1f} med={med:.1f} max={hi:.1f} g/m³ "
          f"(days with qa<6: {n_dry}, qa>16: {n_rainy})")


def classify_seasons(qa_daily: pd.Series) -> pd.Series:
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


def _get_eddypro_fluxes_path(station: str) -> Path | None:
    """Most recent EddyPro full_output file in OUTPUT_BASE/station/processed/fluxes/."""
    fluxes_dir = OUTPUT_BASE / station / "processed" / "fluxes"
    if not fluxes_dir.exists():
        return None
    candidates = list(fluxes_dir.glob("*full_output*.csv"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def load_station_ebc_with_season(station: str, start_date: str, end_date: str) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """Load EddyPro from fluxes/ + radiation/G from collect sources, return (eb_dry, eb_rainy)."""
    eddypro_path = _get_eddypro_fluxes_path(station)
    if eddypro_path is None:
        return None

    # Use collect's load_station_data with EddyPro from fluxes/ (most recent full_output)
    import importlib.util
    _collect_path = Path(__file__).parent / "collect_all_variables_30min.py"
    _spec = importlib.util.spec_from_file_location("collect_mod", _collect_path)
    collect_mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(collect_mod)
    collect_mod.EDDYPRO_FILE_OVERRIDE = {**collect_mod.EDDYPRO_FILE_OVERRIDE, station: eddypro_path}

    combined = collect_mod.load_station_data(station)
    if combined is None or combined.empty:
        return None

    df = collect_mod.resample_30min(combined)
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
        else:
            return None
    elif qa_col_used == "water_vapor_density":
        # EddyPro: kg/m³ → g/m³
        qa = qa * 1000
    qa_daily = qa.resample("D").mean()
    _log_qa_stats(station, qa_daily)
    season_daily = classify_seasons(qa_daily)

    SW_in = _get_column(df, RAD_COL_ALIASES["SW_in"])
    SW_out = _get_column(df, RAD_COL_ALIASES["SW_out"])
    LW_in = _get_column(df, RAD_COL_ALIASES["LW_in"])
    LW_out = _get_column(df, RAD_COL_ALIASES["LW_out"])
    LE = pd.to_numeric(df.get("LE"), errors="coerce")
    H = pd.to_numeric(df.get("H"), errors="coerce")
    qc_le = _get_column(df, ["qc_LE", "Flag(LE)", "qc_LvE", "Flag(LvE)"])
    qc_h = _get_column(df, ["qc_H", "Flag(H)", "qc_HTs", "Flag(HTs)"])
    if qc_le is not None:
        LE = LE.where(pd.to_numeric(qc_le, errors="coerce") <= 1)
    if qc_h is not None:
        H = H.where(pd.to_numeric(qc_h, errors="coerce") <= 1)
    G = df.get("G", None)
    if G is None or pd.isna(G).all():
        try:
            G = calculate_soil_heat_flux(df, station=station, return_components=False)
        except Exception:
            return None
    G = pd.to_numeric(G, errors="coerce")

    if not all([SW_in is not None, SW_out is not None, LW_in is not None, LW_out is not None]):
        return None
    if LE is None or H is None or G is None:
        return None

    SW_in = pd.to_numeric(SW_in, errors="coerce")
    SW_out = pd.to_numeric(SW_out, errors="coerce")
    LW_in = pd.to_numeric(LW_in, errors="coerce")
    LW_out = pd.to_numeric(LW_out, errors="coerce")
    Delta = pd.Series(0, index=df.index)

    eb_df = build_energy_balance_df(
        SW_in=SW_in, SW_out=SW_out, LW_in=LW_in, LW_out=LW_out,
        LE=LE, H=H, G=G, Delta=Delta,
        start=start_date, end=end_date, site_name=station,
    )
    if eb_df.empty:
        return None

    eb_df["season"] = [season_daily.get(pd.Timestamp(ts).normalize(), "transitional") for ts in eb_df.index]
    eb_df["minus_G"] = -eb_df["G"]
    eb_dry = eb_df[eb_df["season"] == "dry"]
    eb_rainy = eb_df[eb_df["season"] == "rainy"]
    return eb_dry, eb_rainy


def diurnal_hourly_mean(df: pd.DataFrame, col: str) -> pd.Series:
    if df.empty or col not in df.columns:
        return pd.Series(dtype=float)
    if col in ("LE", "H"):
        s = df[col].copy()
        s[(s < -300) | (s > 800)] = np.nan
        return s.groupby(df.index.hour).mean()
    return df[col].groupby(df.index.hour).mean()


def main():
    print("Loading data (Dry/Rainy by qa)...")
    all_dry: dict[str, dict[str, pd.Series]] = {}
    all_rainy: dict[str, dict[str, pd.Series]] = {}
    for station in STATIONS:
        start, end = STATION_DATE_RANGES.get(station, (DEFAULT_START, DEFAULT_END))
        res = load_station_ebc_with_season(station, start, end)
        if res is None:
            print(f"  {station}: skip (no data)")
            continue
        eb_dry, eb_rainy = res
        all_dry[station] = {
            "Rn": diurnal_hourly_mean(eb_dry, "Rn"),
            "LE": diurnal_hourly_mean(eb_dry, "LE"),
            "H": diurnal_hourly_mean(eb_dry, "H"),
            "minus_G": diurnal_hourly_mean(eb_dry, "minus_G"),
        }
        all_rainy[station] = {
            "Rn": diurnal_hourly_mean(eb_rainy, "Rn"),
            "LE": diurnal_hourly_mean(eb_rainy, "LE"),
            "H": diurnal_hourly_mean(eb_rainy, "H"),
            "minus_G": diurnal_hourly_mean(eb_rainy, "minus_G"),
        }
        print(f"  {station}: dry {len(eb_dry)}, rainy {len(eb_rainy)}")

    if not all_dry:
        print("No data loaded.")
        return

    fig, axes = plt.subplots(2, 3, figsize=(9, 6), sharex=True, sharey=True)
    axes = axes.flatten()
    components = ["Rn", "LE", "H", "minus_G"]

    for i, station in enumerate(STATIONS):
        ax = axes[i]
        dry = all_dry.get(station)
        rainy = all_rainy.get(station)
        if dry is None and rainy is None:
            ax.set_visible(False)
            continue
        for col_key in components:
            if station == "Gorigo" and col_key == "minus_G":
                continue
            label = "G" if col_key == "minus_G" else col_key
            c = COMPONENT_STYLES.get(col_key, {}).get("color", "0.5")
            if dry is not None:
                s = dry.get(col_key)
                if s is not None and not s.empty:
                    ax.plot(s.index, s.values, color=c, ls="-", linewidth=1.5)
            if rainy is not None:
                s = rainy.get(col_key)
                if s is not None and not s.empty:
                    ax.plot(s.index, s.values, color=c, ls="--", linewidth=1.5)
        from matplotlib.lines import Line2D
        handles = [
            Line2D([0], [0], color="gray", ls="-", linewidth=2, label="Dry"),
            Line2D([0], [0], color="gray", ls="--", linewidth=2, label="Rainy"),
        ]
        for col_key in components:
            if station == "Gorigo" and col_key == "minus_G":
                continue
            lbl = "G" if col_key == "minus_G" else col_key
            c = COMPONENT_STYLES.get(col_key, {}).get("color", "0.5")
            handles.append(Line2D([0], [0], color=c, ls="-", linewidth=1.5, label=lbl))
        ax.legend(handles=handles, fontsize=8, loc="upper right", ncol=2)
        if i % 3 == 0:
            ax.set_ylabel("W/m²", fontsize=12)
        else:
            ax.set_ylabel("")
        ax.axhline(0, color="gray", linestyle=":", linewidth=0.5)
        ax.tick_params(labelsize=11)
        ax.grid(True, alpha=0.3)
        ax.set_title(station, fontsize=14)

    for ax in axes[3:]:
        ax.set_xlabel("Hour", fontsize=12)

    plt.suptitle("Mittlerer Tagesgang – Dry vs Rainy (qa-Kriterium)", fontsize=12, fontweight="bold", y=1.02)
    plt.tight_layout()

    out_path = Path("diurnal_cycle_all_stations_dry_rainy.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"\n✓ Plot saved: {out_path}")
    plt.show()


if __name__ == "__main__":
    main()
