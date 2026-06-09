from __future__ import annotations

"""
Export 30-min ESSD data tables for all stations from *_all_variables_30min.csv.

Input per station (already created by collect_all_variables_30min.py):
    /Users/hingerl-l/Data/{station}/processed/all/{station}_all_variables_30min.csv

Output per station:
    /Users/hingerl-l/Data/essd_data_tables/{station}_essd_30min.csv

Format:
    - First line: comma-separated variable names (exactly as in variables.txt)
    - Second line: comma-separated units (from variables.txt)
    - Following lines: data rows (missing values as -9999)
"""

import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

try:
    import yaml
except ImportError:  # pragma: no cover - fallback if PyYAML not installed
    yaml = None

BASE_DIR = Path("/Users/hingerl-l/Data")
EXAMPLES_DIR = Path(__file__).parent
VARS_SPEC_PATH = EXAMPLES_DIR / "variables.txt"
OUTPUT_DIR = BASE_DIR / "essd_data_tables"
QUALITY_FILTERS_CONFIG = Path(__file__).parent.parent / "ec_analysis" / "utils" / "quality_filters_config.yaml"

# Stations to process (consistent ordering, wie in data_coverage_qc_heatmap.py)
STATIONS: List[str] = ["Nazinga", "Kayoro", "Sumbrungu", "Gorigo", "Janga", "Mole"]

# Global Zeitfenster wie in data_coverage_qc_heatmap.py
COVERAGE_START = pd.Timestamp("2013-01-01")
COVERAGE_END = pd.Timestamp("2025-12-31")

# Station-spezifische Zeiträume (wie in data_coverage_qc_heatmap.py / gap_length_distribution.py)
NAZINGA_EMPTY_FROM = pd.Timestamp("2022-04-01")   # Nazinga nur bis einschl. März 2022
GORIGO_START = pd.Timestamp("2017-05-01")         # Gorigo erst ab Mai 2017
GORIGO_EMPTY_FROM = pd.Timestamp("2024-09-01")    # Gorigo nur bis einschl. August 2022
KAYORO_EMPTY_FROM = pd.Timestamp("2025-09-01")    # Kayoro nur bis einschl. August 2025
SUMBRUNGU_EMPTY_FROM = pd.Timestamp("2016-03-01") # Sumbrungu nur bis einschl. Februar 2016

# Precipitation column per station (genau wie in event_scale_water_balance.py)
P_COL_BY_STATION: Dict[str, str] = {
    "Sumbrungu": "P_tb",
    "Nazinga": "P_tb",
    "Kayoro": "P_tb",
    "Gorigo": "P_pl",
    "Janga": "P",
    "Mole": "P_tb",
}

# Stations with full SWC profile (3 depths)
SWC_PROFILE_STATIONS = frozenset({"Janga", "Mole"})

# Janga: VWC_1, VWC_2, VWC_3 in all_variables sind bereits in % (0–100), nicht m³/m³
JANGA_VWC_PERCENT_COLS = ("VWC_1", "VWC_2", "VWC_3")


def restrict_to_station_period(df: pd.DataFrame, station: str) -> pd.DataFrame:
    """
    Beschränkt Daten auf das gleiche Zeitfenster wie data_coverage_qc_heatmap.py:
    - global 2013-01-01 bis 2025-12-31
    - Nazinga: nur bis März 2022
    - Gorigo: Mai 2017 bis August 2024
    - Kayoro: nur bis August 2025
    - Sumbrungu: nur bis Februar 2016
    - Janga, Mole: voller Zeitraum
    """
    df = df.loc[COVERAGE_START:COVERAGE_END]
    if station == "Nazinga":
        df = df[df.index < NAZINGA_EMPTY_FROM]
    elif station == "Gorigo":
        df = df[(df.index >= GORIGO_START) & (df.index < GORIGO_EMPTY_FROM)]
    elif station == "Kayoro":
        df = df[df.index < KAYORO_EMPTY_FROM]
    elif station == "Sumbrungu":
        df = df[df.index < SUMBRUNGU_EMPTY_FROM]
    return df


def apply_physical_limits_only(df: pd.DataFrame, station: str) -> pd.DataFrame:
    """
    Apply invalid_codes and physical_limits from quality_filters_config.yaml.

    This removes physically non-sensible values but does NOT apply QC flags.
    """
    if yaml is None or not QUALITY_FILTERS_CONFIG.exists():
        return df

    df = df.copy()
    with QUALITY_FILTERS_CONFIG.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    global_cfg = cfg.get("global", {})
    station_cfg = cfg.get("stations", {}).get(station, {})

    # Replace invalid codes with NaN
    invalid_codes = global_cfg.get("invalid_codes", [7999, -9999, -99999])
    for c in invalid_codes:
        if isinstance(c, (int, float)):
            df = df.replace(c, np.nan)
    if "NAN" in str(invalid_codes):
        df = df.replace(["NAN", "nan"], np.nan)

    # Apply physical limits (global + station-specific)
    global_limits = global_cfg.get("physical_limits", {})
    station_limits = station_cfg.get("physical_limits") or {}
    merged = {**global_limits, **station_limits}

    for col, lim in merged.items():
        if col not in df.columns or not isinstance(lim, dict):
            continue
        vmin, vmax = lim.get("min"), lim.get("max")
        if vmin is None and vmax is None:
            continue
        # Janga: VWC_1/2/3 sind in % (0–100), nicht m³/m³ → Limits 0–100
        if station == "Janga" and col in JANGA_VWC_PERCENT_COLS:
            vmin, vmax = 0, 100
        vals = pd.to_numeric(df[col], errors="coerce")
        mask = vals.notna()
        if vmin is not None:
            mask = mask & (vals >= vmin)
        if vmax is not None:
            mask = mask & (vals <= vmax)
        df.loc[~mask, col] = np.nan

    return df


def _read_variables_spec(path: Path) -> Tuple[List[str], List[str]]:
    """
    Read variables.txt and return (variable_names, units) in the desired order.
    """
    vars_out: List[str] = []
    units_out: List[str] = []
    with path.open("r", encoding="utf-8") as f:
        first = True
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Skip header row
            if first:
                first = False
                continue
            # Split only into first two comma-separated fields; the rest (description)
            # may contain additional commas and is ignored.
            parts = line.split(",", 2)
            if len(parts) < 2:
                continue
            var = parts[0].strip()
            unit = parts[1].strip()
            if not var:
                continue
            vars_out.append(var)
            units_out.append(unit)
    return vars_out, units_out


def _load_all_variables_with_units(station: str) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """
    Load *_all_variables_30min.csv for a station.

    Returns:
        df: DataFrame with DateTimeIndex (from Timestamp column) and data columns.
        units: dict mapping column name -> unit string from second row.
    """
    path = BASE_DIR / station / "processed" / "all" / f"{station}_all_variables_30min.csv"
    if not path.exists():
        raise FileNotFoundError(f"All-variables file not found for {station}: {path}")

    # First row: header (strip whitespace/quotes so column names match)
    header = [str(h).strip().strip('"') for h in pd.read_csv(path, nrows=1).columns.tolist()]

    # Second row: units
    units_row = pd.read_csv(path, skiprows=1, nrows=1, header=None, names=header).iloc[0]
    units: Dict[str, str] = {col: str(units_row[col]).strip() for col in header}

    # Data rows
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
    df.index.name = "Timestamp"
    return df, units


def _first_existing(df: pd.DataFrame, candidates: List[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _first_existing_or_stem(df: pd.DataFrame, candidates: List[str]) -> str | None:
    """Like _first_existing; also matches columns whose name starts with candidate (e.g. 'VWC_1' vs 'VWC_1  [m³/m³]')."""
    found = _first_existing(df, candidates)
    if found is not None:
        return found
    col_stems = {}
    for col in df.columns:
        stem = str(col).strip().split("[")[0].strip()
        if stem and stem not in col_stems:
            col_stems[stem] = col
    for c in candidates:
        if c in col_stems:
            return col_stems[c]
    return None


def _get_pressure_kpa(df: pd.DataFrame, units: Dict[str, str]) -> pd.Series | None:
    """
    Return pressure in kPa.
    """
    col = _first_existing(df, ["PA", "Pa", "WXT_airpressure_Avg"])
    if col is None:
        return None
    s = pd.to_numeric(df[col], errors="coerce")
    unit = units.get(col, "").lower()
    if "kpa" in unit:
        factor = 1.0
    elif "hpa" in unit:
        factor = 0.1
    elif unit == "pa":
        factor = 1.0e-3
    else:
        # Unknown unit, assume Pa → kPa
        factor = 1.0e-3
    return s * factor


def _get_timestamp_str(index: pd.DatetimeIndex) -> pd.Series:
    """
    Format timestamps as YYYYMMDDHHMMSS.
    """
    return pd.Series(index=index, data=index.strftime("%Y%m%d%H%M%S"), name="TIMESTAMP")


def _get_neede_series(df: pd.DataFrame) -> pd.Series | None:
    """
    Get NEE (µmolCO2 m-2 s-1), preferring explicit NEE, then CO2, then FC.
    """
    if "NEE" in df.columns:
        return pd.to_numeric(df["NEE"], errors="coerce")
    for c in ("CO2", "FC"):
        if c in df.columns:
            return pd.to_numeric(df[c], errors="coerce")
    return None


def _get_co2_qc(df: pd.DataFrame) -> pd.Series | None:
    for c in ("CO2_QC", "qc_o2_flux", "FC_QC"):
        if c in df.columns:
            return pd.to_numeric(df[c], errors="coerce")
    return None


def _get_le_qc(df: pd.DataFrame) -> pd.Series | None:
    for c in ("LE_QC", "qc_LE", "LE_SSITC_TEST"):
        if c in df.columns:
            return pd.to_numeric(df[c], errors="coerce")
    return None


def _get_h_qc(df: pd.DataFrame) -> pd.Series | None:
    for c in ("H_QC", "qc_H", "H_SSITC_TEST"):
        if c in df.columns:
            return pd.to_numeric(df[c], errors="coerce")
    return None


def _get_tau_qc(df: pd.DataFrame) -> pd.Series | None:
    """TAU QC: all_variables hat qc_TAU (aus EddyPro qc_Tau)."""
    for c in ("TAU_QC", "qc_TAU", "qc_Tau"):
        if c in df.columns:
            return pd.to_numeric(df[c], errors="coerce")
    return None


def _get_radiation_component(df: pd.DataFrame, kind: str) -> pd.Series | None:
    """
    kind in {"SW_IN", "SW_OUT", "LW_IN", "LW_OUT", "NETRAD"}
    """
    if kind == "SW_IN":
        col = _first_existing(df, ["SW_IN", "SW_in", "Rs_in_Avg"])
    elif kind == "SW_OUT":
        col = _first_existing(df, ["SW_OUT", "SW_out", "Rs_out_Avg"])
    elif kind == "LW_IN":
        col = _first_existing(df, ["LW_IN", "LW_in", "IR_in_Avg"])
    elif kind == "LW_OUT":
        col = _first_existing(df, ["LW_OUT", "LW_out", "IR_out_Avg"])
    elif kind == "NETRAD":
        col = _first_existing(df, ["NETRAD", "Rn", "NetTot_Avg"])
    else:
        return None
    if col is None:
        return None
    return pd.to_numeric(df[col], errors="coerce")


def _get_precip(df: pd.DataFrame, station: str) -> pd.Series | None:
    col = P_COL_BY_STATION.get(station)
    if col is None or col not in df.columns:
        # Fallbacks
        col = _first_existing(
            df,
            [
                "P",
                "P_tb",
                "P_pl",
                "precp_mm",
                "Rain_mm_Tot",
                "WXT_Ramount_Tot",
                "Ramount_Tot",
                "Acc_NRT",
                "Acc_totNRT",
            ],
        )
    if col is None:
        return None
    return pd.to_numeric(df[col], errors="coerce")


def _get_ta(df: pd.DataFrame) -> pd.Series | None:
    col = _first_existing(df, ["TA", "Tair", "TA_1_1_1"])
    if col is None:
        return None
    return pd.to_numeric(df[col], errors="coerce")


def _get_wd(df: pd.DataFrame) -> pd.Series | None:
    col = _first_existing(df, ["WD", "wind_dir", "wind_direction"])
    if col is None:
        return None
    return pd.to_numeric(df[col], errors="coerce")


def _get_ws(df: pd.DataFrame) -> pd.Series | None:
    col = _first_existing(df, ["WS", "wind_speed", "wnd_spd", "WS_RSLT"])
    if col is None:
        return None
    return pd.to_numeric(df[col], errors="coerce")


def _get_zl(df: pd.DataFrame) -> pd.Series | None:
    col = _first_existing(df, ["ZL", "z-d_L"])
    if col is None:
        return None
    return pd.to_numeric(df[col], errors="coerce")


def _get_mo_length(df: pd.DataFrame) -> pd.Series | None:
    # all_variables_30min hat Monin-Obukhov-Länge als "L" (variable_mapping)
    col = _first_existing(df, ["L", "MO_LENGHT", "MO_length"])
    if col is None:
        return None
    return pd.to_numeric(df[col], errors="coerce")


def _get_swc_profiles(df: pd.DataFrame, station: str) -> Tuple[pd.Series | None, pd.Series | None, pd.Series | None]:
    """
    Return (SWC_1_1_1, SWC_1_2_1, SWC_1_3_1) in %.
    Only Janga and Mole get a full profile; other stations get SWC_1_1_1 only.
    Spaltenreihenfolge wie in event_scale_water_balance: VWC_1, VWC_2, VWC_3 zuerst (Janga all_variables).
    """
    # Kandidaten pro Tiefe: VWC_1/2/3 zuerst (wie event_scale_water_balance.VWC_LAYER_COLS)
    depth1_cols = ["VWC_1", "VW_1_Avg", "SWC_1_1_1", "SWC_1", "VWC", "VWC_Avg", "cs65x_ec_1_1_1"]
    depth2_cols = ["VWC_2", "VW_2_Avg", "SWC_1_2_1", "SWC_2", "VWC_2_Avg", "cs65x_ec_2_1_1"]
    depth3_cols = ["VWC_3", "VW_3_Avg", "SWC_1_3_1", "SWC_3", "VWC_3_Avg", "cs65x_ec_3_1_1"]

    def _get_depth(cols: List[str]) -> pd.Series | None:
        c = _first_existing_or_stem(df, cols)
        if c is None:
            return None
        s = pd.to_numeric(df[c], errors="coerce")
        # Ausgabe in %: Janga/Mole all_variables haben VWC oft bereits in % (0–100); sonst m³/m³ → *100
        max_val = s.max(skipna=True) if hasattr(s, "max") else None
        if max_val is not None and max_val <= 1.5:
            s = s * 100.0
        return s

    swc1 = _get_depth(depth1_cols)
    swc2 = _get_depth(depth2_cols) if station in SWC_PROFILE_STATIONS else None
    swc3 = _get_depth(depth3_cols) if station in SWC_PROFILE_STATIONS else None
    return swc1, swc2, swc3


def _get_ts_profile(df: pd.DataFrame) -> Tuple[pd.Series | None, pd.Series | None, pd.Series | None]:
    """
    Return (TS_1_1_1, TS_1_2_1, TS_1_3_1) in deg C.
    """
    depth1_cols = ["TS_1_1_1", "Ts_1", "TA_1_1_1"]
    depth2_cols = ["TS_1_2_1", "Ts_2", "TA_2_1_1"]
    depth3_cols = ["TS_1_3_1", "Ts_3", "TA_3_1_1"]

    def _get_depth(cols: List[str]) -> pd.Series | None:
        c = _first_existing(df, cols)
        if c is None:
            return None
        return pd.to_numeric(df[c], errors="coerce")

    return _get_depth(depth1_cols), _get_depth(depth2_cols), _get_depth(depth3_cols)


def build_essd_table_for_station(station: str, var_names: List[str], var_units: List[str]) -> pd.DataFrame:
    """
    Build ESSD-style table (without header/units rows) for a single station.
    Index = timestamps, columns = var_names.
    """
    df_raw, units = _load_all_variables_with_units(station)
    # Zeitfenster wie in data_coverage_qc_heatmap.py
    df_raw = restrict_to_station_period(df_raw, station)
    # Remove invalid codes and physically non-sensible values
    df = apply_physical_limits_only(df_raw, station)

    out = pd.DataFrame(index=df.index)

    swc1, swc2, swc3 = _get_swc_profiles(df, station)
    ts1, ts2, ts3 = _get_ts_profile(df)
    pa_kpa = _get_pressure_kpa(df, units)
    nee = _get_neede_series(df)
    co2_qc = _get_co2_qc(df)
    le_qc = _get_le_qc(df)
    h_qc = _get_h_qc(df)
    tau_qc = _get_tau_qc(df)
    sw_in = _get_radiation_component(df, "SW_IN")
    sw_out = _get_radiation_component(df, "SW_OUT")
    lw_in = _get_radiation_component(df, "LW_IN")
    lw_out = _get_radiation_component(df, "LW_OUT")
    netrad = _get_radiation_component(df, "NETRAD")
    # Für Nazinga und Kayoro soll ab 2016-01-01 explizit NetTot_Avg aus
    # {station}_all_variables_30min.csv für NETRAD verwendet werden.
    netrad_nettot = None
    if station in ("Nazinga", "Kayoro") and "NetTot_Avg" in df_raw.columns:
        netrad_nettot = pd.to_numeric(df_raw["NetTot_Avg"], errors="coerce")
    p = _get_precip(df, station)
    ta = _get_ta(df)
    wd = _get_wd(df)
    ws = _get_ws(df)
    zl = _get_zl(df)
    mo_length = _get_mo_length(df)

    for name in var_names:
        if name == "TIMESTAMP":
            out[name] = _get_timestamp_str(df.index)
        elif name == "LE":
            out[name] = pd.to_numeric(df.get("LE"), errors="coerce")
        elif name == "LE_QC":
            out[name] = le_qc
        elif name == "H":
            out[name] = pd.to_numeric(df.get("H"), errors="coerce")
        elif name == "H_QC":
            out[name] = h_qc
        elif name == "NEE":
            out[name] = nee
        elif name == "CO2_QC":
            out[name] = co2_qc
        elif name == "G":
            out[name] = pd.to_numeric(df.get("G"), errors="coerce")
        elif name == "SW_IN":
            out[name] = sw_in
        elif name == "SW_OUT":
            out[name] = sw_out
        elif name == "LW_IN":
            out[name] = lw_in
        elif name == "LW_OUT":
            out[name] = lw_out
        elif name == "NETRAD":
            # Standard: aus _get_radiation_component (NETRAD/Rn/NetTot_Avg in df)
            series = netrad
            # Override: Nazinga/Kayoro ab 2016-01-01 mit NetTot_Avg aus df_raw
            if netrad_nettot is not None:
                cutoff = pd.Timestamp("2016-01-01")
                nettot_aligned = netrad_nettot.reindex(out.index)
                if series is None:
                    series = nettot_aligned
                else:
                    series = series.copy()
                    mask = series.index >= cutoff
                    series.loc[mask] = nettot_aligned.loc[mask]
            out[name] = series
        elif name == "P":
            out[name] = p
        elif name == "ET":
            out[name] = pd.to_numeric(df.get("ET"), errors="coerce")
        elif name == "PA":
            out[name] = pa_kpa
        elif name == "RH":
            out[name] = pd.to_numeric(df.get("RH"), errors="coerce")
        elif name == "TA":
            out[name] = ta
        elif name == "VPD":
            # all_variables hat VPD in Pa; ESSD-Ausgabe in hPa
            vpd_pa = pd.to_numeric(df.get("VPD"), errors="coerce")
            out[name] = vpd_pa / 100.0
        elif name == "WD":
            out[name] = wd
        elif name == "WS":
            out[name] = ws
        elif name == "USTAR":
            out[name] = pd.to_numeric(df_raw.get("ustar"), errors="coerce")
        elif name == "ZL":
            out[name] = zl
        elif name == "MO_LENGHT":
            out[name] = mo_length
        elif name == "TAU":
            out[name] = pd.to_numeric(df.get("TAU"), errors="coerce")
        elif name == "TAU_QC":
            out[name] = tau_qc
        elif name == "SWC_1_1_1":
            out[name] = swc1
        elif name == "SWC_1_2_1":
            out[name] = swc2
        elif name == "SWC_1_3_1":
            out[name] = swc3
        elif name == "TS_1_1_1":
            out[name] = ts1
        elif name == "TS_1_2_1":
            out[name] = ts2
        elif name == "TS_1_3_1":
            out[name] = ts3
        else:
            # Fallback: try to use a column with identical name
            if name in df.columns:
                out[name] = pd.to_numeric(df[name], errors="coerce")
            else:
                out[name] = np.nan

    # Nazinga, Kayoro: ab 01.01.2016 LW_IN/LW_OUT durch IR_InCo_Avg / IR_OutCo_Avg ersetzen
    if station in ("Nazinga", "Kayoro"):
        cutoff = pd.Timestamp("2016-01-01")
        if "IR_InCo_Avg" in df.columns and "IR_OutCo_Avg" in df.columns:
            mask = out.index >= cutoff
            out.loc[mask, "LW_IN"] = pd.to_numeric(df.loc[mask, "IR_InCo_Avg"], errors="coerce").values
            out.loc[mask, "LW_OUT"] = pd.to_numeric(df.loc[mask, "IR_OutCo_Avg"], errors="coerce").values

    # Gorigo: LW_IN/LW_OUT durch IR_InCo_Avg / IR_OutCo_Avg ersetzen
    if station == "Gorigo":
        if "IR_InCo_Avg" in df.columns and "IR_OutCo_Avg" in df.columns:
            out["LW_IN"] = pd.to_numeric(df["IR_InCo_Avg"], errors="coerce").reindex(out.index).values
            out["LW_OUT"] = pd.to_numeric(df["IR_OutCo_Avg"], errors="coerce").reindex(out.index).values

    # Nazinga: ab 01.01.2018 LW_in und LW_out vertauschen
    if station == "Nazinga":
        swap_cutoff = pd.Timestamp("2018-01-01")
        mask = out.index >= swap_cutoff
        lw_in_vals = out.loc[mask, "LW_IN"].copy()
        out.loc[mask, "LW_IN"] = out.loc[mask, "LW_OUT"].values
        out.loc[mask, "LW_OUT"] = lw_in_vals.values

    return out


def _write_essd_csv(path: Path, var_names: List[str], var_units: List[str], table: pd.DataFrame) -> None:
    """
    Write ESSD-style CSV with header + unit row and -9999 for missing values.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # Ensure column order
    table = table.copy()
    table = table[var_names]

    # Replace NaN with -9999
    data = table.replace({np.nan: -9999})

    with path.open("w", encoding="utf-8") as f:
        # Header row: variable names
        f.write(",".join(var_names) + "\n")
        # Units row
        f.write(",".join(var_units) + "\n")
        # Data rows
        for _, row in data.iterrows():
            values = []
            for v in row:
                if isinstance(v, str):
                    values.append(v)
                else:
                    # Ensure numeric types and -9999 for missing already applied
                    try:
                        if pd.isna(v):
                            values.append(str(-9999))
                        else:
                            values.append(str(v))
                    except Exception:
                        values.append(str(v))
            f.write(",".join(values) + "\n")


def main(argv: List[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    if not VARS_SPEC_PATH.exists():
        raise FileNotFoundError(f"variables.txt not found: {VARS_SPEC_PATH}")

    var_names, var_units = _read_variables_spec(VARS_SPEC_PATH)

    for station in STATIONS:
        print(f"\n--- {station} ---")
        try:
            table = build_essd_table_for_station(station, var_names, var_units)
        except FileNotFoundError as e:
            print(f"  Skipping (file missing): {e}")
            continue
        out_path = OUTPUT_DIR / f"{station}_essd_30min.csv"
        _write_essd_csv(out_path, var_names, var_units, table)
        print(f"  Saved {len(table)} rows, {len(var_names)} columns -> {out_path}")


if __name__ == "__main__":
    main()

