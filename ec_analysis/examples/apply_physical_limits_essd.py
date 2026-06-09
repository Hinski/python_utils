#!/usr/bin/env python3
"""
Wendet physikalische Grenzen auf ESSD-Datentabellen an und speichert als Clean-Version.

- Liest Datensätze von export_essd_data_tables.py (*_essd_30min.csv) oder bestehende
  Clean-Datensätze (*_essd_30min_clean.csv); vorhandene Clean-Datei hat Vorrang.
- Grenzen und invalid_codes kommen aus physical_limits_essd.yaml (im gleichen Verzeichnis
  wie die Datensätze: essd_data_tables). Fallback: YAML im Skriptverzeichnis (examples).
- Werte außerhalb [min, max] sowie invalid_codes werden durch Fehlwerte (-9999) ersetzt.
- Ausgabe immer als *_essd_30min_clean.csv (Original wird nicht überschrieben).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import yaml
except ImportError:
    yaml = None

DATA_BASE = Path("/Users/hingerl-l/Data")
ESSD_DIR = DATA_BASE / "essd_data_tables"
SCRIPT_DIR = Path(__file__).resolve().parent
# YAML im gleichen Verzeichnis wie die Datensätze; Fallback: Skriptverzeichnis
LIMITS_YAML_PATH = ESSD_DIR / "physical_limits_essd.yaml"
LIMITS_YAML_FALLBACK = SCRIPT_DIR / "physical_limits_essd.yaml"
MISSING_VALUE = -9999
STATIONS = ["Nazinga", "Kayoro", "Sumbrungu", "Gorigo", "Janga", "Mole"]


def load_essd_csv(path: Path) -> tuple[pd.DataFrame, list[str], list[str]] | None:
    """Liest ESSD-CSV; Returns (DataFrame mit DatetimeIndex, var_names, units)."""
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        header_line = f.readline().strip()
        units_line = f.readline().strip()
    var_names = [c.strip() for c in header_line.split(",")]
    units = [u.strip() for u in units_line.split(",")]
    if len(units) < len(var_names):
        units.extend([""] * (len(var_names) - len(units)))
    else:
        units = units[: len(var_names)]

    df = pd.read_csv(
        path,
        skiprows=2,
        header=None,
        names=var_names,
        low_memory=False,
        na_values=[MISSING_VALUE, str(MISSING_VALUE), "-9999.0", "nan", "NAN"],
    )
    if "TIMESTAMP" not in df.columns or df["TIMESTAMP"].empty:
        return None
    ts = pd.to_datetime(df["TIMESTAMP"], format="%Y%m%d%H%M%S", errors="coerce")
    df = df.drop(columns=["TIMESTAMP"])
    df.index = ts
    df = df[df.index.notna()].sort_index()
    return df, var_names, units


def write_essd_csv(
    path: Path,
    df: pd.DataFrame,
    var_names: list[str],
    var_units: list[str],
) -> None:
    """Schreibt ESSD-CSV; Fehlwerte als -9999."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data_cols = [c for c in var_names if c != "TIMESTAMP"]
    table = df.reindex(columns=data_cols).replace({np.nan: MISSING_VALUE})
    with path.open("w", encoding="utf-8") as f:
        f.write(",".join(var_names) + "\n")
        f.write(",".join(var_units) + "\n")
        for idx, row in table.iterrows():
            ts_str = idx.strftime("%Y%m%d%H%M%S")
            values = [ts_str]
            for c in data_cols:
                v = row.get(c, MISSING_VALUE)
                values.append(str(MISSING_VALUE) if (pd.isna(v) or v == MISSING_VALUE) else str(v))
            f.write(",".join(values) + "\n")


def get_load_path(station: str) -> Path | None:
    """Clean-Datei falls vorhanden, sonst Basis-Datei."""
    for name in (f"{station}_essd_30min_clean.csv", f"{station}_essd_30min.csv"):
        p = ESSD_DIR / name
        if p.exists():
            return p
    return None


def get_save_path(load_path: Path) -> Path:
    """Immer *_essd_30min_clean.csv (gleiche Datei wenn bereits clean)."""
    if "clean" in load_path.name:
        return load_path
    return load_path.parent / f"{load_path.stem}_clean.csv"


def _get_limits_config_path() -> Path | None:
    """Pfad zur physical_limits_essd.yaml (ESSD-Verzeichnis oder Fallback Skriptverzeichnis)."""
    if LIMITS_YAML_PATH.exists():
        return LIMITS_YAML_PATH
    if LIMITS_YAML_FALLBACK.exists():
        return LIMITS_YAML_FALLBACK
    return None


def get_physical_limits_for_essd(station: str) -> dict[str, dict]:
    """
    Liest physical_limits aus physical_limits_essd.yaml (global + stations.<station>).
    YAML liegt im gleichen Verzeichnis wie die Datensätze (essd_data_tables) oder im Skriptverzeichnis.
    """
    path = _get_limits_config_path()
    if yaml is None or path is None:
        return _fallback_essd_limits()
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    global_limits = cfg.get("global", {}).get("physical_limits", {})
    station_limits = (cfg.get("stations", {}).get(station, {}).get("physical_limits") or {})
    return {**global_limits, **station_limits}


def _fallback_essd_limits() -> dict[str, dict]:
    """Fallback-Limits falls YAML fehlt (ESSD-Namen)."""
    return {
        "LE": {"min": -200, "max": 800},
        "H": {"min": -400, "max": 600},
        "NEE": {"min": -50, "max": 50},
        "G": {"min": -200, "max": 400},
        "SW_IN": {"min": 0, "max": 1500},
        "SW_OUT": {"min": 0, "max": 400},
        "LW_IN": {"min": 100, "max": 600},
        "LW_OUT": {"min": 100, "max": 800},
        "NETRAD": {"min": -100, "max": 1200},
        "P": {"min": 0, "max": 300},
        "ET": {"min": 0, "max": 25},
        "PA": {"min": 80, "max": 110},
        "RH": {"min": 0, "max": 100},
        "TA": {"min": -20, "max": 50},
        "VPD": {"min": 0, "max": 80},
        "WD": {"min": 0, "max": 360},
        "WS": {"min": 0, "max": 50},
        "USTAR": {"min": 0, "max": 5},
        "ZL": {"min": -20, "max": 20},
        "MO_LENGHT": {"min": -2000, "max": 2000},
        "SWC_1_1_1": {"min": 0, "max": 100},
        "SWC_1_2_1": {"min": 0, "max": 100},
        "SWC_1_3_1": {"min": 0, "max": 100},
        "TS_1_1_1": {"min": -10, "max": 60},
        "TS_1_2_1": {"min": -10, "max": 60},
        "TS_1_3_1": {"min": -10, "max": 60},
    }


def apply_limits_and_invalid_codes(
    df: pd.DataFrame,
    station: str,
    invalid_codes: list,
) -> pd.DataFrame:
    """Ersetzt invalid_codes und Werte außerhalb physical_limits durch NaN."""
    df = df.copy()
    for c in invalid_codes:
        if isinstance(c, (int, float)):
            df = df.replace(c, np.nan)
    df = df.replace([MISSING_VALUE, -99999, 7999], np.nan)
    df = df.replace(["NAN", "nan"], np.nan)

    limits = get_physical_limits_for_essd(station)
    for col in df.columns:
        if col not in limits:
            continue
        lim = limits[col]
        vmin, vmax = lim.get("min"), lim.get("max")
        if vmin is None and vmax is None:
            continue
        vals = pd.to_numeric(df[col], errors="coerce")
        mask = vals.notna()
        if vmin is not None:
            mask = mask & (vals >= vmin)
        if vmax is not None:
            mask = mask & (vals <= vmax)
        df.loc[~mask, col] = np.nan
    return df


def main() -> None:
    limits_path = _get_limits_config_path()
    if yaml is None:
        print("PyYAML fehlt; es werden nur Fallback-Limits verwendet.")
    elif limits_path is None:
        print("physical_limits_essd.yaml nicht gefunden (weder in essd_data_tables noch im Skriptverzeichnis) -> Fallback-Limits.")
    else:
        print(f"Limits aus: {limits_path}")

    invalid_codes = [7999, -9999, -99999, "NAN"]
    if yaml and limits_path is not None:
        with limits_path.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        invalid_codes = cfg.get("global", {}).get("invalid_codes", invalid_codes)

    for station in STATIONS:
        load_path = get_load_path(station)
        if load_path is None:
            print(f"  {station}: Keine ESSD-Datei gefunden, übersprungen.")
            continue
        result = load_essd_csv(load_path)
        if result is None:
            print(f"  {station}: Konnte Datei nicht lesen.")
            continue
        df, var_names, var_units = result
        n_before = df.isna().sum().sum()
        df = apply_limits_and_invalid_codes(df, station, invalid_codes)
        n_after = df.isna().sum().sum()
        save_path = get_save_path(load_path)
        write_essd_csv(save_path, df, var_names, var_units)
        print(f"  {station}: {int(n_after - n_before)} weitere Fehlwerte gesetzt (geladen: {load_path.name}) -> {save_path.name}")

    print("Fertig.")


if __name__ == "__main__":
    main()
