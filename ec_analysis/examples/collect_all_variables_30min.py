"""
Collect all mapped variables for all stations, aggregate to 30 min, save one CSV per station.

- Fluxes (LE, H, CO2, qc_*, etc.): from EddyPro full output; keep only columns that appear
  in variable_mapping.COLUMN_MAPPING. EddyPro timestamps (end-of-period, e.g. 12:30) are
  shifted by -30 min to align with CR1000/TOA5 (start-of-period, e.g. 12:00) for merge.
- Other variables: from same sources as energy_balance_closure (CR1000, radiation, Dragan CSV).
- Aggregation: 30-minute resolution; mean for all variables except P (precipitation) = sum.
- Output: /Users/hingerl-l/Data/{station}/processed/all/{station}_all_variables_30min.csv
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from ec_analysis import load_ec_data
from ec_analysis.aggregation import get_station_config, find_columns_flexible
from ec_analysis.aggregation.energy_balance import apply_mole_sw_in_correction
from ec_analysis.data_loaders.variable_mapping import (
    COLUMN_MAPPING,
    map_dataframe_columns,
    normalize_column_name,
    STANDARD_UNITS,
)

# -----------------------------------------------------------------------------
# Paths and station list (same as energy_balance_closure)
# -----------------------------------------------------------------------------
# EddyPro: override per station to use specific file, or None to auto-detect most recent
# Example: EDDYPRO_FILE_OVERRIDE = {"Mole": Path("/Users/hingerl-l/Data/Mole/processed/fluxes/eddypro_Mole_full_output_2026-02-12T180440_adv.csv")}
EDDYPRO_FILE_OVERRIDE: dict[str, Path | None] = {}

DATA_DIR = Path("/Users/hingerl-l/Data/merged_long")
EDDYPRO_DIR = Path("/Users/hingerl-l/Data")
DRAGAN_DATA_DIR = Path("/Users/hingerl-l/Diss/Data/ECdata_Dragan")
OUTPUT_BASE = Path("/Users/hingerl-l/Data")
# WASCAL EC 2012–2016: Sumbrungu, Nazinga, Kayoro _new.csv (Niederschlag/Boden)
WASCAL_DIR = Path("/Users/hingerl-l/Diss/Data/WASCAL_EC_2012_2016")
SUMBRUNGU_WASCAL_CSV = WASCAL_DIR / "Sumbrungu_new.csv"
# WXT files: /Users/hingerl-l/Data/{station}/merged/{station}_wxt_merged.csv (5-min intervals)
WXT_COLS = ["Wdmin_Min", "Wdavg", "Wdmax_Max", "Wsmin_Min", "Wsavg_Avg", "Wsmax_Max", "airtemp_Avg", "relhumidity_Avg", "airpressure_Avg", "Ramount_Tot", "Rduration_Avg", "Rintensity_Avg", "Hamount_Tot", "Hduration_Avg", "Hintensity_Avg"]
# Statistik row 4 -> aggregation: Min->min, Max->max, Avg/Smp->mean, Tot->sum
WXT_STAT_TO_AGG = {"Min": "min", "Max": "max", "Avg": "mean", "Smp": "mean", "Tot": "sum"}
# Tot columns (mm/10min, hits/10min): nur Zeilen mit :00,:10,:20,:30,:40,:50 verwenden
WXT_TOT_COLS = ["Ramount_Tot", "Hamount_Tot"]
WXT_MISSING_CODE = 7999

# Mole: CR6 Flux-Datei enthält sehr viele Spalten (wie EddyPro Full-Output). Nur Strahlung behalten.
# Nach map_dataframe_columns heißen die Spalten SW_in, SW_out, LW_in, LW_out, Rn (lowercase).
MOLE_RAD_COLUMNS = ["SW_in", "SW_out", "LW_in", "LW_out", "NETRAD", "Rn"]


def load_wxt_and_resample_30min(wxt_path: Path) -> pd.DataFrame | None:
    """
    Load WXT file (TOA5, 5-min), parse row 4 (Statistik) for aggregation method,
    resample to 30 min and return with WXT_ prefix.
    """
    if not wxt_path.exists():
        return None
    try:
        with wxt_path.open("r", encoding="utf-8", errors="ignore") as f:
            lines = [line.strip() for line in f if line.strip()]
        if len(lines) < 5:
            return None
        # Row 0: TOA5, Row 1: var names, Row 2: units, Row 3: Statistik
        header_line = lines[1]
        stat_line = lines[3] if len(lines) > 3 else ""
        header = [c.strip().strip('"') for c in next(csv.reader([header_line]))]
        stats = [s.strip().strip('"') for s in next(csv.reader([stat_line]))]
        # Build agg dict from Statistik row (align by column index)
        agg_map = {}
        for i, stat in enumerate(stats):
            if i < len(header) and header[i] != "TIMESTAMP" and header[i] != "RECORD":
                agg_map[header[i]] = WXT_STAT_TO_AGG.get(stat, "mean")
        # Load data (skip first 4 rows)
        df = pd.read_csv(
            wxt_path,
            skiprows=4,
            header=None,
            names=header,
            na_values=["NAN", "NA", "-9999", "-9999.0", "-999", "**************"],
            low_memory=False,
        )
        if df.empty or "TIMESTAMP" not in df.columns:
            return None
        df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"], errors="coerce")
        df = df.dropna(subset=["TIMESTAMP"])
        df = df.set_index("TIMESTAMP")
        cols = [c for c in WXT_COLS if c in df.columns]
        if not cols:
            return None
        df = df[cols].copy()
        agg_dict = {c: agg_map.get(c, "mean") for c in cols}
        # Tot columns (mm/10min): nur :00,:10,:20,:30,:40,:50 für Aggregation
        tot_cols = [c for c in cols if c in WXT_TOT_COLS]
        other_cols = [c for c in cols if c not in WXT_TOT_COLS]
        # Fehlwerte 7999 entfernen, Skalierung für Ramount_Tot/Hamount_Tot
        df10 = df[df.index.minute.isin([0, 10, 20, 30, 40, 50])].copy()
        if "Ramount_Tot" in df10.columns:
            ra = df10["Ramount_Tot"].replace(WXT_MISSING_CODE, np.nan)
            ra = ra.where(ra <= 1000)
            if "Rduration_Avg" in df10.columns:
                dur = df10["Rduration_Avg"].replace(WXT_MISSING_CODE, np.nan)
                ra = ra.where(dur.notna())
            df10["Ramount_Tot"] = ra / 10.0
        if "Hamount_Tot" in df10.columns:
            ha = df10["Hamount_Tot"].replace(WXT_MISSING_CODE, np.nan)
            ha = ha.where(ha <= 10000)
            if "Hduration_Avg" in df10.columns:
                hdur = df10["Hduration_Avg"].replace(WXT_MISSING_CODE, np.nan)
                ha = ha.where(hdur.notna())
            df10["Hamount_Tot"] = ha / 10.0
        resampled = pd.DataFrame()
        if tot_cols:
            df_tot = df10[tot_cols]
            try:
                res_tot = df_tot.resample("30min", origin="start_day").agg({c: agg_dict[c] for c in tot_cols})
            except Exception:
                res_tot = df_tot.resample("30min").agg({c: agg_dict[c] for c in tot_cols})
            resampled = pd.concat([resampled, res_tot], axis=1)
        if other_cols:
            try:
                res_other = df[other_cols].resample("30min", origin="start_day").agg({c: agg_dict[c] for c in other_cols})
            except Exception:
                res_other = df[other_cols].resample("30min").agg({c: agg_dict[c] for c in other_cols})
            resampled = pd.concat([resampled, res_other], axis=1)
        resampled = resampled.rename(columns={c: f"WXT_{c}" for c in resampled.columns})
        # Reihenfolge gemäß cols
        resampled = resampled[[f"WXT_{c}" for c in cols if f"WXT_{c}" in resampled.columns]]
        return resampled
    except Exception:
        return None


def _match_wxt_cols(df: pd.DataFrame, want: list[str]) -> list[str]:
    """Match wanted column names to actual df columns (strip quotes/whitespace)."""
    normal_to_actual = {str(c).strip().strip('"'): c for c in df.columns}
    found = []
    for w in want:
        if w in df.columns:
            found.append(w)
        elif w in normal_to_actual:
            found.append(normal_to_actual[w])
    return found

STATIONS = ["Nazinga", "Mole", "Kayoro", "Sumbrungu", "Gorigo", "Janga"]
#STATIONS = ["Mole"]

# Standard names we care about (values in COLUMN_MAPPING)
STANDARD_NAMES = set(COLUMN_MAPPING.values())

# Precipitation and totals: sum aggregation; intensity/rate = mean
PRECIP_COLUMNS = ("P", "P_pl", "P_tb", "Precip", "Rainfall", "Precip_Tot", "Rain_Tot", "precip_rain_e", "precip_total_rain_e", "precip_cv", "Rs_cv", "Acc_NRT", "Acc_totNRT", "WXT_Ramount_Tot", "WXT_Hamount_Tot", "Rain_mm_Tot", "precip_cv_Tot", "Acc_RT_NRT", "Bucket_RT", "Bucket_NRT", "Ramount_Tot", "Hamount_Tot")

# EddyPro uses end-of-period timestamps (e.g. 12:30 for 12:00-12:30). Parquet/preprocessed
# data use start-of-period (12:00). Shift EddyPro index by -30 min for alignment with parquet.
# Mole uses raw Campbell/CR6 (SMT, HF, .dat) which also use end-of-period → no shift for Mole.
EDDYPRO_INDEX_SHIFT_MINUTES = -30
STATIONS_EDDYPRO_SHIFT = frozenset({"Nazinga", "Kayoro", "Sumbrungu", "Gorigo", "Janga"})

# All columns computed by EddyPro from high-frequency raw data must only come from EddyPro
# (LE, H, CO2, L, ustar, ET, VPD, qc_*, turbulence params, covariances, fetch, footprint, etc.).
# Even if EddyPro has gaps, do not fill from CR1000/radiation. We overwrite all df_eddy columns.
# Bodenfeuchte (VWC, SWC, VW_*) nie durch EddyPro überschreiben – EddyPro misst keine VWC.
VWC_COLUMNS = frozenset({"VWC", "VWC_1", "VWC_2", "VWC_3", "SWC_1", "SWC_2", "SWC_3", "VW_1_Avg", "VW_2_Avg", "VW_3_Avg", "SWC_1_1_1", "SWC_2_1_1", "SWC_3_1_1"})

# Air temperature: standard name; convert from Kelvin to °C if needed
TAIR_COLUMN = "Tair"
KELVIN_TO_CELSIUS = 273.15
# If median of valid Tair > this threshold, assume data are in Kelvin
TAIR_KELVIN_THRESHOLD = 200.0


def get_station_paths(station: str) -> dict[str, Any]:
    """Resolve file paths for a station (same logic as energy_balance_closure)."""
    paths = {
        "station": station,
        "eddypro_file": None,
        "cr1000_file": None,
        "cr1000_smt_file": None,
        "cr1000_hf_file": None,
        "radiation_file": None,
        "dragan_file": None,
        "janga_g_file": None,
        "wxt_file": None,
        "is_dragan_station": station in ["Kayoro", "Nazinga", "Sumbrungu"],
    }

    if station == "Mole":
        paths["cr1000_smt_file"] = EDDYPRO_DIR / station / "raw" / "cr1000" / f"CR1000X{station}_Ground2.dat"
        paths["cr1000_hf_file"] = EDDYPRO_DIR / station / "raw" / "cr1000" / f"CR1000X{station}_Ground1.dat"
        paths["radiation_file"] = EDDYPRO_DIR / station / "raw" / "cr6" / "CR6Mole_Flux_CSFormat_15_11.dat"
        paths["eddypro_file"] = Path("/Users/hingerl-l/Data/Mole/processed/fluxes/Mole_full_output_merged.csv")
    elif station == "Gorigo":
        paths["cr1000_file"] = EDDYPRO_DIR / station / "merged" / f"{station}_cr1000_merged.csv"
        paths["radiation_file"] = DATA_DIR / f"{station}_radiation_merged_long.parquet"
        paths["radiation_merged_csv"] = EDDYPRO_DIR / station / "merged" / f"{station}_radiation_merged.csv"
        paths["wxt_file"] = EDDYPRO_DIR / station / "merged" / f"{station}_wxt_merged.csv"
    elif station == "Janga":
        paths["radiation_file"] = EDDYPRO_DIR / station / "raw" / "CR6Janga_Flux_AmeriFluxFormat.dat"
        paths["janga_g_file"] = EDDYPRO_DIR / station / "raw" / "CR6Janga_Public.dat"
    elif station in ["Kayoro", "Nazinga", "Sumbrungu"]:
        if station == "Sumbrungu":
            paths["dragan_file"] = DRAGAN_DATA_DIR / "Sumbrungu.csv"
            paths["wascal_file"] = SUMBRUNGU_WASCAL_CSV if SUMBRUNGU_WASCAL_CSV.exists() else None
        else:
            paths["dragan_file"] = DRAGAN_DATA_DIR / f"{station}.csv"
            # Nazinga, Kayoro: Bodentemperatur (Ts_1, Ts_2, Ts_3) aus WASCAL {station}_new.csv
            wascal_path = WASCAL_DIR / f"{station}_new.csv"
            paths["wascal_file"] = wascal_path if wascal_path.exists() else None
        paths["cr1000_file"] = paths["dragan_file"] if paths["dragan_file"].exists() else None
        paths["wxt_file"] = EDDYPRO_DIR / station / "merged" / f"{station}_wxt_merged.csv"
    else:
        paths["cr1000_file"] = DATA_DIR / f"{station}_cr1000_merged_long.parquet"
        paths["radiation_file"] = DATA_DIR / f"{station}_radiation_merged_long.parquet"

    # EddyPro: use override if set, else most recent full output
    if station in EDDYPRO_FILE_OVERRIDE:
        override_path = EDDYPRO_FILE_OVERRIDE[station]
        if override_path and Path(override_path).exists():
            paths["eddypro_file"] = Path(override_path)
    if paths["eddypro_file"] is None:
        eddypro_fluxes_dir = EDDYPRO_DIR / station / "processed" / "fluxes"
        if eddypro_fluxes_dir.exists():
            pattern = f"eddypro_{station}_full_output_*.csv"
            eddypro_files = list(eddypro_fluxes_dir.glob(pattern))
            if eddypro_files:
                paths["eddypro_file"] = max(eddypro_files, key=lambda p: p.stat().st_mtime)

    return paths


def load_eddypro_mapped(eddypro_path: Path) -> pd.DataFrame | None:
    """Load EddyPro CSV and return DataFrame with only columns that map to standard names, renamed."""
    if not eddypro_path or not eddypro_path.exists():
        return None
    df = load_ec_data(eddypro_path, format="eddypro")
    if df is None or df.empty:
        return None
    # Keep only columns that map to a standard name
    keep = [
        c for c in df.columns
        if normalize_column_name(str(c).strip()) in STANDARD_NAMES
    ]
    # Also keep qa-related columns for dry/rainy season classification
    for extra in ("water_vapor_density", "e"):
        if extra in df.columns and extra not in keep:
            keep.append(extra)
    if not keep:
        return None
    df = df[keep].copy()
    map_dataframe_columns(df, inplace=True)
    # If multiple source columns mapped to same name, take first (EddyPro usually one-to-one)
    df = df.loc[:, ~df.columns.duplicated(keep="first")]
    return df



def load_dragan_pre2016(dragan_path: Path, cutoff: pd.Timestamp) -> tuple[pd.DataFrame | None, pd.DataFrame | None, pd.Series | None, pd.DataFrame | None]:
    """Load Dragan CSV for pre-2016; return (df_cr1000, df_rad, G_pre2016, df_cr1000_pre_raw for G calc)."""
    if not dragan_path or not dragan_path.exists():
        return None, None, None, None
    df = pd.read_csv(
        dragan_path,
        sep=",",
        low_memory=False,
        na_values=["NAN", "NA", "-9999", "-9999.0", "-999", "**************"],
    )
    if "T_begin" not in df.columns:
        return None, None, None, None
    df["T_begin"] = pd.to_datetime(df["T_begin"], format="%m/%d/%y %H:%M", errors="coerce")
    df = df.set_index("T_begin")
    df.index.name = "TIMESTAMP"
    df = df[df.index.notna()].sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df_pre = df[df.index < cutoff].copy()

    # Exclude flux columns (we use EddyPro for those)
    exclude = ["LvE", "HTs", "LvE[W/m_]      ", "HTs[W/m_]      ", "G ", "G", "GHF Mean", "Gs "]
    cols_cr = [c for c in df_pre.columns if c not in exclude]
    df_cr1000_pre_raw = df_pre[cols_cr].copy()  # keep for G calculation before mapping
    df_cr1000 = df_cr1000_pre_raw.copy()

    # Rename unit suffixes and German names
    rename = {}
    for col in df_cr1000.columns:
        new = col
        if " [DegC]" in new:
            new = new.replace(" [DegC]", "")
        elif " [W/m^2]" in new:
            new = new.replace(" [W/m^2]", "")
        elif " [W/m_]" in new:
            new = new.replace(" [W/m_]", "")
        if new.endswith("_Ost_Avg"):
            new = new.replace("_Ost_Avg", "_East_Avg")
        elif new.endswith("_Mitte_Avg"):
            new = new.replace("_Mitte_Avg", "_Middle_Avg")
        if new != col:
            rename[col] = new
    if rename:
        df_cr1000 = df_cr1000.rename(columns=rename)
    map_dataframe_columns(df_cr1000, inplace=True)
    df_cr1000 = df_cr1000.loc[:, ~df_cr1000.columns.duplicated(keep="first")]

    df_rad = df_pre.copy()
    map_dataframe_columns(df_rad, inplace=True)
    df_rad = df_rad.loc[:, ~df_rad.columns.duplicated(keep="first")]

    G_pre = None
    for g_col in ["G ", "G", "GHF Mean"]:
        if g_col in df_pre.columns:
            G_pre = pd.to_numeric(df_pre[g_col], errors="coerce")
            break
    if G_pre is not None:
        G_pre = G_pre.reindex(df_pre.index)

    return df_cr1000, df_rad, G_pre, df_cr1000_pre_raw


# Sumbrungu WASCAL: nur Niederschlag + Boden (Radiation aus Dragan, Rest aus EddyPro)
WASCAL_PRECIP_PATTERNS = (
    "Rain_mm_Tot", "Acc_RT_NRT", "Acc_NRT", "Acc_totNRT", "Bucket_RT", "Bucket_NRT",
    "Ramount_Tot", "Hamount_Tot", "Intensity_RT_Avg",
)
WASCAL_SOIL_PATTERNS = (
    "VW_1_Avg", "VW_2_Avg", "VW_3_Avg", "PA_uS_1_Avg", "PA_uS_2_Avg", "PA_uS_3_Avg",
    "TCAV_C_Avg(1)", "TCAV_C_Avg(2)", "TCAV_C_Avg(3)", "Temp_load_cell_Avg",
    "H_Flux_sc_8_Ost_Avg", "H_Flux_sc_8_East_Avg", "H_Flux_sc_8_West_Avg",
    "H_Flux_sc_8_Mitte_Avg", "H_Flux_sc_8_Middle_Avg",
    "shf_cal(1)", "shf_cal(2)", "shf_cal(3)",
)


def load_sumbrungu_wascal_csv(
    path: Path,
    cutoff: pd.Timestamp,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None, pd.Series | None, pd.DataFrame | None]:
    """
    Lädt Sumbrungu_new.csv (WASCAL). Nur Niederschlags- und Bodenvariablen.
    Radiation kommt aus DRAGAN (Sumbrungu.csv), Rest aus EddyPro.
    WASCAL: dd/mm/yy; T_begin = Periodenanfang (30 min).
    """
    if not path or not path.exists():
        return None, None, None, None
    df = pd.read_csv(
        path,
        sep=",",
        low_memory=False,
        na_values=["NAN", "NA", "-9999", "-9999.0", "-999", "**************"],
    )
    if "T_begin" not in df.columns:
        return None, None, None, None
    df["T_begin"] = pd.to_datetime(df["T_begin"], format="%d/%m/%y %H:%M", errors="coerce")
    df = df.set_index("T_begin")
    df.index.name = "TIMESTAMP"
    df = df[df.index.notna()].sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df_pre = df[df.index < cutoff].copy()

    # Spalten bereinigen
    rename = {}
    for col in df_pre.columns:
        new = str(col).strip()
        if " [DegC]" in new:
            new = new.replace(" [DegC]", "")
        elif " [W/m^2]" in new:
            new = new.replace(" [W/m^2]", "")
        elif " [W/m_]" in new:
            new = new.replace(" [W/m_]", "")
        for suffix in (" [mm]", " [mm/10 min]", " [hits/10 min]", " [mm/m]", " [mm/h]", " [usec]"):
            if suffix in new:
                new = new.replace(suffix, "").strip()
        if " tipping buckt" in new:
            new = new.replace(" tipping buckt", "")
        if new.endswith("_Ost_Avg"):
            new = new.replace("_Ost_Avg", "_East_Avg")
        elif new.endswith("_Mitte_Avg"):
            new = new.replace("_Mitte_Avg", "_Middle_Avg")
        if " [W/(m^2 mV)]" in new:
            new = new.replace(" [W/(m^2 mV)]", "").strip()
        if new != col:
            rename[col] = new
    if rename:
        df_pre = df_pre.rename(columns=rename)

    # Nur Niederschlag + Boden behalten
    cols_keep = []
    for col in df_pre.columns:
        col_clean = str(col).strip()
        for pat in WASCAL_PRECIP_PATTERNS + WASCAL_SOIL_PATTERNS:
            if pat in col_clean or col_clean == pat:
                cols_keep.append(col)
                break

    df_cr1000_pre_raw = df_pre[[c for c in cols_keep if c in df_pre.columns]].copy()
    if df_cr1000_pre_raw.empty:
        return None, None, None, None
    df_cr1000 = df_cr1000_pre_raw.copy()
    map_dataframe_columns(df_cr1000, inplace=True)
    df_cr1000 = df_cr1000.loc[:, ~df_cr1000.columns.duplicated(keep="first")]

    # Keine Radiation aus WASCAL (kommt aus Dragan)
    return df_cr1000, None, None, df_cr1000_pre_raw


# Nur Bodentemperatur (TCAV_C_Avg(1),(2),(3)) für Nazinga/Kayoro aus WASCAL _new.csv
WASCAL_TS_PATTERNS = ("TCAV_C_Avg(1)", "TCAV_C_Avg(2)", "TCAV_C_Avg(3)")


def _read_wascal_csv_common(path: Path, cutoff: pd.Timestamp) -> pd.DataFrame | None:
    """Liest WASCAL _new.csv, setzt Index auf T_begin, filtert auf index < cutoff. Spalten werden bereinigt (Unit-Suffixe, Deutsch)."""
    if not path or not path.exists():
        return None
    df = pd.read_csv(
        path,
        sep=",",
        low_memory=False,
        na_values=["NAN", "NA", "-9999", "-9999.0", "-999", "**************"],
    )
    if "T_begin" not in df.columns:
        return None
    # Original behalten: Kayoro nutzt dd.mm.yy (z. B. 10.10.12), Nazinga dd.mm.yyyy (19.10.2012)
    t_begin_raw = df["T_begin"].copy()
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%y %H:%M", "%d/%m/%y %H:%M", "%m/%d/%y %H:%M"):
        try:
            parsed = pd.to_datetime(t_begin_raw, format=fmt, errors="coerce")
            if parsed.notna().any():
                df["T_begin"] = parsed
                break
        except Exception:
            continue
    df = df.set_index("T_begin")
    df.index.name = "TIMESTAMP"
    df = df[df.index.notna()].sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df_pre = df[df.index < cutoff].copy()
    if df_pre.empty:
        return None
    rename = {}
    for col in df_pre.columns:
        new = str(col).strip()
        if " [DegC]" in new:
            new = new.replace(" [DegC]", "")
        if " [°C]" in new:
            new = new.replace(" [°C]", "")
        if " [K]" in new:
            new = new.replace(" [K]", "")
        if " [W/m^2]" in new:
            new = new.replace(" [W/m^2]", "")
        if " [W/m_]" in new:
            new = new.replace(" [W/m_]", "")
        for suffix in (" [mm]", " [mm/10 min]", " [hits/10 min]", " [mm/m]", " [mm/h]", " [usec]"):
            if suffix in new:
                new = new.replace(suffix, "").strip()
        if " tipping buckt" in new:
            new = new.replace(" tipping buckt", "")
        if new.endswith("_Ost_Avg"):
            new = new.replace("_Ost_Avg", "_East_Avg")
        elif new.endswith("_Mitte_Avg"):
            new = new.replace("_Mitte_Avg", "_Middle_Avg")
        if " [W/(m^2 mV)]" in new:
            new = new.replace(" [W/(m^2 mV)]", "").strip()
        if new != col:
            rename[col] = new
    if rename:
        df_pre = df_pre.rename(columns=rename)
    return df_pre


# CNR4- und IR-compensated-Spalten aus WASCAL (Nazinga, Kayoro)
WASCAL_CNR4_COLS = ("CNR4TC_Avg", "CNR4TK_Avg")
WASCAL_IR_COLS = ("IR_OutCo_Avg", "IR_InCo_Avg")  # [W/m^2] nach Rename


def load_wascal_soil_csv(path: Path, cutoff: pd.Timestamp) -> pd.DataFrame | None:
    """
    Lädt aus WASCAL {station}_new.csv Bodentemperatur (TCAV → Ts_1, Ts_2, Ts_3), CNR4-Spalten
    (CNR4TC_Avg, CNR4TK_Avg) und IR-compensated (IR_OutCo_Avg, IR_InCo_Avg) für den Zeitraum
    vor cutoff. Für Nazinga und Kayoro. Gleiche Logik wie bei Sumbrungu (kein Index-Shift).
    """
    df_pre = _read_wascal_csv_common(path, cutoff)
    if df_pre is None:
        return None
    cols_keep = [c for c in df_pre.columns if any(p in str(c).strip() for p in WASCAL_TS_PATTERNS)]
    for p in WASCAL_CNR4_COLS:
        if p in df_pre.columns:
            cols_keep.append(p)
    for p in WASCAL_IR_COLS:
        if p in df_pre.columns:
            cols_keep.append(p)
    cols_keep = list(dict.fromkeys(cols_keep))  # Reihenfolge, keine Duplikate
    if not cols_keep:
        return None
    df_soil = df_pre[[c for c in cols_keep if c in df_pre.columns]].copy()
    if df_soil.empty:
        return None
    map_dataframe_columns(df_soil, inplace=True)
    df_soil = df_soil.loc[:, ~df_soil.columns.duplicated(keep="first")]
    ts_cols = [c for c in ("Ts_1", "Ts_2", "Ts_3") if c in df_soil.columns]
    cnr4_cols = [c for c in WASCAL_CNR4_COLS if c in df_soil.columns]
    ir_cols = [c for c in WASCAL_IR_COLS if c in df_soil.columns]
    if not ts_cols and not cnr4_cols and not ir_cols:
        return None
    out_cols = ts_cols + cnr4_cols + ir_cols
    return df_soil[out_cols]


def load_pre2016_precipitation_from_merged_long(
    station: str, data_dir: Path, cutoff: pd.Timestamp
) -> pd.DataFrame | None:
    """
    Load precipitation (P, P_pl, P_tb) for period before cutoff from merged_long parquet files.
    Tries {station}_cr1000_merged_long.parquet and {station}_radiation_merged_long.parquet.
    Returns a DataFrame with datetime index and standard names (P, P_pl, P_tb), or None if no
    precipitation column found. Preserves distinction between P_pl (pluviometer) and P_tb (tipping bucket).
    """
    for name in ("cr1000", "radiation"):
        parquet_path = data_dir / f"{station}_{name}_merged_long.parquet"
        if not parquet_path.exists():
            continue
        try:
            df = load_ec_data(parquet_path)
            if df is None or df.empty:
                continue
            df_pre = df[df.index < cutoff]
            if df_pre.empty:
                continue
            # Find columns that map to any precipitation standard name (P, P_pl, P_tb)
            out = {}
            for c in df_pre.columns:
                std = normalize_column_name(str(c).strip())
                if std in PRECIP_COLUMNS:
                    ser = pd.to_numeric(df_pre[c], errors="coerce").reindex(df_pre.index)
                    ser.name = std
                    out[std] = ser
            if not out:
                continue
            return pd.DataFrame(out)
        except Exception:
            continue
    return None


def load_gorigo_ir_compensated(csv_path: Path) -> pd.DataFrame | None:
    """
    Lädt IR_InCo_Avg und IR_OutCo_Avg aus Gorigo_radiation_merged.csv.
    Resampelt auf 30 min (Mittelwert), damit Alignment mit combined.
    """
    if not csv_path or not csv_path.exists():
        return None
    try:
        df = pd.read_csv(csv_path, low_memory=False)
    except Exception:
        return None
    if "TIMESTAMP" not in df.columns or "IR_InCo_Avg" not in df.columns or "IR_OutCo_Avg" not in df.columns:
        return None
    df = df[["TIMESTAMP", "IR_InCo_Avg", "IR_OutCo_Avg"]].copy()
    df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"], errors="coerce")
    df = df.set_index("TIMESTAMP")
    df["IR_InCo_Avg"] = pd.to_numeric(df["IR_InCo_Avg"], errors="coerce")
    df["IR_OutCo_Avg"] = pd.to_numeric(df["IR_OutCo_Avg"], errors="coerce")
    df = df[df.index.notna()].sort_index()
    df = df[~df.index.duplicated(keep="first")]
    try:
        df = df.resample("30min", origin="start_day").mean()
    except Exception:
        df = df.resample("30min").mean()
    return df


def load_station_data(station: str) -> pd.DataFrame | None:
    """Load all sources for one station, merge, and return one DataFrame (datetime index, not yet resampled)."""
    paths = get_station_paths(station)

    # 1) EddyPro (fluxes and any mapped vars)
    df_eddy = load_eddypro_mapped(paths["eddypro_file"])
    if df_eddy is None:
        df_eddy = pd.DataFrame()
    elif not df_eddy.empty and station in STATIONS_EDDYPRO_SHIFT:
        # EddyPro uses end-of-period (12:30), parquet uses start-of-period (12:00).
        # Shift EddyPro index for stations using parquet. Mole uses raw Campbell/CR6
        # (end-of-period) → no shift.
        df_eddy = df_eddy.copy()
        df_eddy.index = df_eddy.index + pd.Timedelta(minutes=EDDYPRO_INDEX_SHIFT_MINUTES)

    # 2) CR1000 and radiation
    df_cr1000 = None
    df_rad = None
    G_dragan_pre2016 = None
    df_post_cr_raw = None  # unmapped post-2016 CR1000 for G calculation (Dragan only)
    df_cr1000_pre_raw = None  # unmapped pre-2016 for G (Dragan only)
    df_janga_g_raw = None  # Janga: raw G file for G_plate_* columns
    janga_g_raw_cols = []  # Janga: list of raw G column names to add to output
    df_wxt = None  # WXT sensor data (Gorigo, Nazinga, Kayoro, Sumbrungu)
    cutoff = pd.to_datetime("2016-01-01")

    if paths["is_dragan_station"]:
        if station == "Sumbrungu":
            # Sumbrungu: WASCAL nur Niederschlag+Boden, Dragan nur Radiation, Rest aus EddyPro
            df_cr1000_pre, df_rad_pre = None, None
            if paths.get("wascal_file") and paths["wascal_file"].exists():
                df_cr1000_pre, _, _, _ = load_sumbrungu_wascal_csv(paths["wascal_file"], cutoff)
            if paths["dragan_file"] and paths["dragan_file"].exists():
                _, df_rad_pre, _, _ = load_dragan_pre2016(paths["dragan_file"], cutoff)
            if df_cr1000_pre is not None:
                df_cr1000 = df_cr1000_pre
            if df_rad_pre is not None:
                df_rad = df_rad_pre
        elif paths["dragan_file"] and paths["dragan_file"].exists():
            df_cr1000_pre, df_rad_pre, _, _ = load_dragan_pre2016(paths["dragan_file"], cutoff)
            if df_cr1000_pre is not None:
                df_cr1000 = df_cr1000_pre
            if df_rad_pre is not None:
                df_rad = df_rad_pre
            # Nazinga, Kayoro: drei Bodentemperaturen für pre-2016 aus WASCAL {station}_new.csv
            if station in ("Nazinga", "Kayoro") and paths.get("wascal_file") and paths["wascal_file"].exists():
                df_wascal_soil = load_wascal_soil_csv(paths["wascal_file"], cutoff)
                if df_wascal_soil is not None and not df_wascal_soil.empty and df_cr1000 is not None:
                    for col in df_wascal_soil.columns:
                        # WASCAL-Werte haben Vorrang (combine_first: WASCAL füllt, wo vorhanden)
                        wascal_aligned = df_wascal_soil[col].reindex(df_cr1000.index)
                        if col not in df_cr1000.columns:
                            df_cr1000[col] = wascal_aligned
                        else:
                            df_cr1000[col] = wascal_aligned.combine_first(df_cr1000[col])
        parquet_cr = DATA_DIR / f"{station}_cr1000_merged_long.parquet"
        parquet_rad = DATA_DIR / f"{station}_radiation_merged_long.parquet"
        if parquet_cr.exists():
            df_post_cr = load_ec_data(parquet_cr)
            df_post_cr = df_post_cr[df_post_cr.index >= cutoff]
            map_dataframe_columns(df_post_cr, inplace=True)
            df_post_cr = df_post_cr.loc[:, ~df_post_cr.columns.duplicated(keep="first")]
            df_cr1000 = pd.concat([df_cr1000, df_post_cr], join="outer", sort=True).sort_index() if df_cr1000 is not None else df_post_cr
        if parquet_rad.exists():
            df_post_rad = load_ec_data(parquet_rad)
            df_post_rad = df_post_rad[df_post_rad.index >= cutoff]
            map_dataframe_columns(df_post_rad, inplace=True)
            df_post_rad = df_post_rad.loc[:, ~df_post_rad.columns.duplicated(keep="first")]
            df_rad = pd.concat([df_rad, df_post_rad], join="outer", sort=True).sort_index() if df_rad is not None else df_post_rad
        # Dragan stations: WXT sensor data (5-min -> 30-min resampled)
        if paths.get("wxt_file"):
            df_wxt = load_wxt_and_resample_30min(paths["wxt_file"])

    elif station == "Mole":
        df_cr1000 = pd.DataFrame()
        
        # Ground2: Soil moisture (VWC) and Soil temperature (T)
        if paths["cr1000_smt_file"] and paths["cr1000_smt_file"].exists():
            df_ground2 = load_ec_data(paths["cr1000_smt_file"], format="toa5")
            df_ground2_renamed = df_ground2.rename(columns={
                "VWC_Avg": "VW_1_Avg",
                "VWC_2_Avg": "VW_2_Avg",
                "VWC_3_Avg": "VW_3_Avg",
                "T_Avg": "TCAV_C_Avg(1)",
                "T_2_Avg": "TCAV_C_Avg(2)",
                "T_3_Avg": "TCAV_C_Avg(3)",
            })
            ground2_cols = ["VW_1_Avg", "VW_2_Avg", "VW_3_Avg", "TCAV_C_Avg(1)", "TCAV_C_Avg(2)", "TCAV_C_Avg(3)"]
            available_cols = [c for c in ground2_cols if c in df_ground2_renamed.columns]
            if available_cols:
                df_cr1000 = df_ground2_renamed[available_cols].copy()
        
        # Ground1: Ground heat flux (H_Flux) and Rain (Rain_mm_Tot)
        if paths["cr1000_hf_file"] and paths["cr1000_hf_file"].exists():
            df_ground1 = load_ec_data(paths["cr1000_hf_file"], format="toa5")
            hf_cols = ["H_Flux_8_Middle_Avg", "H_Flux_8_East_Avg", "H_Flux_8_West_Avg"]
            rain_cols = ["Rain_mm_Tot"]
            for col in hf_cols + rain_cols:
                if col in df_ground1.columns:
                    if df_cr1000.empty:
                        df_cr1000 = pd.DataFrame(index=df_ground1.index)
                    df_cr1000[col] = df_ground1[col]
        
        if not df_cr1000.empty:
            map_dataframe_columns(df_cr1000, inplace=True)
            df_cr1000 = df_cr1000.loc[:, ~df_cr1000.columns.duplicated(keep="first")]
        
        # Radiation: nur Strahlungsspalten aus CR6Mole_Flux_CSFormat_15_11.dat (Datei hat viele Spalten)
        if paths["radiation_file"] and paths["radiation_file"].exists():
            df_rad = load_ec_data(paths["radiation_file"], format="toa5")
            map_dataframe_columns(df_rad, inplace=True)
            df_rad = df_rad.loc[:, ~df_rad.columns.duplicated(keep="first")]
            keep_rad = [c for c in MOLE_RAD_COLUMNS if c in df_rad.columns]
            if keep_rad:
                df_rad = df_rad[keep_rad].copy()
            # Mole: SW_in-Korrektur (Faktor 10.15/16.15) wie in energy_balance_closure / build_energy_balance_df
            if "SW_in" in df_rad.columns:
                df_rad["SW_in"] = apply_mole_sw_in_correction(df_rad["SW_in"], "Mole")

    elif station == "Janga":
        # Janga VWC/TS aus CR6Janga_Flux_AmeriFluxFormat.dat (SWC_1_1_1, TS_1_1_1)
        if paths["radiation_file"] and paths["radiation_file"].exists():
            df_rad_raw = load_ec_data(paths["radiation_file"])
            df_rad = df_rad_raw.copy()
            map_dataframe_columns(df_rad, inplace=True)
            df_rad = df_rad.loc[:, ~df_rad.columns.duplicated(keep="first")]
            # df_cr1000 aus Rohdaten, VOR Mapping – sonst SWC_1_1_1 nicht mehr in df_rad
            df_cr1000 = pd.DataFrame(index=df_rad_raw.index)
            for i, col in enumerate(["TS_1_1_1", "TS_2_1_1", "TS_3_1_1"], 1):
                if col in df_rad_raw.columns:
                    df_cr1000[f"TCAV_C_Avg({i})"] = df_rad_raw[col]
            for i, col in enumerate(["SWC_1_1_1", "SWC_2_1_1", "SWC_3_1_1"], 1):
                if col in df_rad_raw.columns:
                    df_cr1000[f"VW_{i}_Avg"] = df_rad_raw[col]
            # Janga: load G_plate columns and precip from CR6Janga_Public.dat (G calculated later from CSV)
            if paths["janga_g_file"] and paths["janga_g_file"].exists():
                df_jg = load_ec_data(paths["janga_g_file"])
                janga_config = get_station_config("Janga")
                g_cols = find_columns_flexible(df_jg, janga_config["g_raw_columns"])
                janga_pub_cols = list(g_cols)
                for extra in ["P", "precip_intensity_rain_e", "precip_rain_e", "precip_total_rain_e", "Rs_cv", "precip_cv", "Intensity_RT_Avg", "Acc_NRT", "Acc_totNRT"]:
                    if extra in df_jg.columns and extra not in janga_pub_cols:
                        janga_pub_cols.append(extra)
                if janga_pub_cols:
                    df_janga_g_raw = df_jg
                    janga_g_raw_cols = janga_pub_cols
            map_dataframe_columns(df_cr1000, inplace=True)
            df_cr1000 = df_cr1000.loc[:, ~df_cr1000.columns.duplicated(keep="first")]
        else:
            df_cr1000 = pd.DataFrame()
            df_rad = None

    elif station == "Gorigo":
        if paths["cr1000_file"] and paths["cr1000_file"].exists():
            df_cr1000 = load_ec_data(paths["cr1000_file"])
            map_dataframe_columns(df_cr1000, inplace=True)
            df_cr1000 = df_cr1000.loc[:, ~df_cr1000.columns.duplicated(keep="first")]
        if paths["radiation_file"] and paths["radiation_file"].exists():
            df_rad = load_ec_data(paths["radiation_file"])
            map_dataframe_columns(df_rad, inplace=True)
            df_rad = df_rad.loc[:, ~df_rad.columns.duplicated(keep="first")]
        # Gorigo: WXT sensor data (5-min -> 30-min resampled)
        if paths.get("wxt_file"):
            df_wxt = load_wxt_and_resample_30min(paths["wxt_file"])

    else:
        if paths["cr1000_file"] and paths["cr1000_file"].exists():
            df_cr1000 = load_ec_data(paths["cr1000_file"])
            map_dataframe_columns(df_cr1000, inplace=True)
            df_cr1000 = df_cr1000.loc[:, ~df_cr1000.columns.duplicated(keep="first")]
        if paths["radiation_file"] and paths["radiation_file"].exists():
            df_rad = load_ec_data(paths["radiation_file"])
            map_dataframe_columns(df_rad, inplace=True)
            df_rad = df_rad.loc[:, ~df_rad.columns.duplicated(keep="first")]

    # 3) Merge: EddyPro first, then rad, then cr1000 (so fluxes from EddyPro, rest from others)
    combined = df_eddy.copy() if not df_eddy.empty else pd.DataFrame()
    if not combined.empty:
        combined = combined.loc[:, ~combined.columns.duplicated(keep="first")]
    if df_rad is not None and not df_rad.empty:
        combined = combined.combine_first(df_rad) if not combined.empty else df_rad.copy()
        combined = combined.loc[:, ~combined.columns.duplicated(keep="first")]
    if df_cr1000 is not None and not df_cr1000.empty:
        combined = combined.combine_first(df_cr1000) if not combined.empty else df_cr1000.copy()
        combined = combined.loc[:, ~combined.columns.duplicated(keep="first")]
    # All EddyPro-derived columns (fluxes, L, ustar, ET, VPD, qc_*, turbulence, etc.) must only
    # come from EddyPro, never from rad/cr1000—even if EddyPro has gaps.
    if not df_eddy.empty:
        for col in df_eddy.columns:
            if col in VWC_COLUMNS:
                continue
            combined[col] = df_eddy[col].reindex(combined.index)
    # Janga: add G_plate and precip from CR6Janga_Public.dat (resample to 30 min for index alignment)
    if station == "Janga" and df_janga_g_raw is not None and janga_g_raw_cols:
        df_janga_add = df_janga_g_raw[janga_g_raw_cols].copy()
        map_dataframe_columns(df_janga_add, inplace=True)
        # Resample to 30 min (CR6Janga_Public has high-freq data)
        agg_janga = {c: "sum" if c in PRECIP_COLUMNS else "mean" for c in df_janga_add.columns}
        try:
            df_janga_30 = df_janga_add.resample("30min", origin="start_day").agg(agg_janga)
        except Exception:
            df_janga_30 = df_janga_add.resample("30min").agg(agg_janga)
        combined = combined.combine_first(df_janga_30)
        combined = combined.loc[:, ~combined.columns.duplicated(keep="first")]
    # Mole: Rain_mm_Tot is already loaded from Ground1.dat above
    # Append WXT columns as last columns (Gorigo, Nazinga, Kayoro, Sumbrungu)
    if df_wxt is not None and not df_wxt.empty:
        for col in df_wxt.columns:
            combined[col] = df_wxt[col].reindex(combined.index)
        # Move WXT columns to end
        wxt_cols = [c for c in df_wxt.columns if c in combined.columns]
        other_cols = [c for c in combined.columns if c not in wxt_cols]
        combined = combined[other_cols + wxt_cols]

    # Gorigo: IR_InCo_Avg und IR_OutCo_Avg aus Gorigo_radiation_merged.csv
    if station == "Gorigo" and paths.get("radiation_merged_csv") and paths["radiation_merged_csv"].exists():
        df_ir = load_gorigo_ir_compensated(paths["radiation_merged_csv"])
        if df_ir is not None and not df_ir.empty:
            combined = combined.combine_first(df_ir)
            combined = combined.loc[:, ~combined.columns.duplicated(keep="first")]

    # 5) Pre-2016 precipitation from merged_long (add/fill where missing; keep P_pl vs P_tb)
    # Mole: P (Rain_mm_Tot) comes from Ground1.dat, skip merged_long
    if not combined.empty and (combined.index < cutoff).any() and station != "Mole":
        P_pre2016 = load_pre2016_precipitation_from_merged_long(station, DATA_DIR, cutoff)
        if P_pre2016 is not None and not P_pre2016.empty:
            for col in P_pre2016.columns:
                if col not in combined.columns:
                    combined[col] = pd.NA
                combined[col] = combined[col].combine_first(P_pre2016[col])

    # 6) Tair: convert from Kelvin to °C if values are in Kelvin range
    if not combined.empty and TAIR_COLUMN in combined.columns:
        t = pd.to_numeric(combined[TAIR_COLUMN], errors="coerce").dropna()
        if len(t) > 0 and t.median() > TAIR_KELVIN_THRESHOLD:
            combined[TAIR_COLUMN] = pd.to_numeric(combined[TAIR_COLUMN], errors="coerce") - KELVIN_TO_CELSIUS

    if combined.empty:
        return None
    combined = combined.sort_index()
    return combined


def save_csv_with_units(df: pd.DataFrame, path: Path) -> None:
    """
    Save DataFrame to CSV with variable names in row 1 and units in row 2.
    Index column is named 'Timestamp'.
    """
    df = df.copy()
    df.index.name = "Timestamp"
    units = [STANDARD_UNITS.get(col, "") for col in df.columns]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([df.index.name] + list(df.columns))
        w.writerow([""] + units)
    df.to_csv(path, mode="a", header=False, date_format="%Y-%m-%d %H:%M:%S")


def resample_30min(df: pd.DataFrame) -> pd.DataFrame:
    """Resample to 30 min: mean for all columns except precipitation (P, P_pl, P_tb) = sum."""
    if df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return df
    df = df.copy()
    # Coerce non-numeric columns to numeric so mean/sum work (object dtype fails on mean)
    for col in df.columns:
        if col in PRECIP_COLUMNS:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        elif not pd.api.types.is_numeric_dtype(df[col]):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    agg = {}
    for col in df.columns:
        if col in PRECIP_COLUMNS:
            # Wichtig: Pandas-Summe mit min_count=0 würde "alle NaN im Slot" zu 0.0 machen.
            # Wir wollen in diesem Fall NaN behalten (fehlende Messung ≠ 0 mm).
            agg[col] = lambda x: x.sum(min_count=1)
        else:
            agg[col] = "mean"
    try:
        out = df.resample("30min", origin="start_day").agg(agg)
    except Exception:
        out = df.resample("30min").agg(agg)
    return out


def main() -> None:
    for station in STATIONS:
        print(f"\n--- {station} ---")
        combined = load_station_data(station)
        if combined is None or combined.empty:
            print(f"  No data for {station}, skip.")
            continue
        resampled = resample_30min(combined)
        out_dir = OUTPUT_BASE / station / "processed" / "all"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{station}_all_variables_30min.csv"
        save_csv_with_units(resampled, out_path)
        print(f"  Saved {len(resampled)} rows, {len(resampled.columns)} columns -> {out_path}")


if __name__ == "__main__":
    main()
