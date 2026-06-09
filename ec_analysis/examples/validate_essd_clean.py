#!/usr/bin/env python3
"""
Prüft, ob die *_essd_30min_clean.csv Dateien die in edit_essd_masks.yaml und
physical_limits_essd.yaml definierten Korrekturen korrekt angewandt haben.

- Masks: Für jeden Eintrag (Station, Variable, start, end) wird geprüft, ob in der
  Clean-Datei in diesem Zeitraum alle Werte der Variable -9999 (oder NaN) sind.
- Physical limits: Für jede Variable mit [min, max] wird geprüft, ob alle Werte
  in der Clean-Datei entweder im Intervall liegen oder -9999/NaN sind.
- Invalid codes: Es wird geprüft, ob die in der YAML genannten invalid_codes
  (z. B. 7999, -99999) in den Daten noch vorkommen.

Ausgabe: Pro Station und Regel „OK“ oder Anzahl Verstöße (+ ggf. Beispiele).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import yaml
except ImportError:
    yaml = None

DATA_BASE = Path("/Users/hingerl-l/Data")
ESSD_DIR = DATA_BASE / "essd_data_tables"
SCRIPT_DIR = Path(__file__).resolve().parent
MASKS_YAML = ESSD_DIR / "edit_essd_masks.yaml"
MASKS_YAML_FALLBACK = SCRIPT_DIR / "edit_essd_masks.yaml"
LIMITS_YAML = ESSD_DIR / "physical_limits_essd.yaml"
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


def _get_masks_config_path() -> Path | None:
    if MASKS_YAML.exists():
        return MASKS_YAML
    if MASKS_YAML_FALLBACK.exists():
        return MASKS_YAML_FALLBACK
    return None


def _get_limits_config_path() -> Path | None:
    if LIMITS_YAML.exists():
        return LIMITS_YAML
    if LIMITS_YAML_FALLBACK.exists():
        return LIMITS_YAML_FALLBACK
    return None


def load_masks_config() -> dict[str, list[dict[str, Any]]]:
    """Lädt edit_essd_masks.yaml und gibt masks_by_station zurück (wie edit_essd_data_tables)."""
    path = _get_masks_config_path()
    if yaml is None or path is None:
        return {}
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    raw_masks = cfg.get("masks") or {}
    if not isinstance(raw_masks, dict):
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for station_key, entries in raw_masks.items():
        if not isinstance(entries, list):
            continue
        station_key = str(station_key).strip()
        if not station_key:
            continue
        list_ok = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            raw_var = e.get("variable") or e.get("variables") or ""
            if isinstance(raw_var, list):
                for v in raw_var:
                    v = str(v).strip()
                    if v and e.get("start") and e.get("end"):
                        list_ok.append({"variable": v, "start": e.get("start"), "end": e.get("end")})
            else:
                var = str(raw_var).strip()
                if var and e.get("start") and e.get("end"):
                    list_ok.append({"variable": var, "start": e.get("start"), "end": e.get("end")})
        if list_ok:
            out[station_key] = list_ok
    return out


def load_limits_config(station: str) -> dict[str, dict[str, Any]]:
    """Lädt physical_limits_essd.yaml: global + stations.<station> → { var: {min, max} }."""
    path = _get_limits_config_path()
    if yaml is None or path is None:
        return {}
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    global_limits = cfg.get("global", {}).get("physical_limits", {})
    station_limits = (cfg.get("stations", {}).get(station, {}).get("physical_limits") or {})
    return {**global_limits, **station_limits}


def load_invalid_codes() -> list[Any]:
    path = _get_limits_config_path()
    if yaml is None or path is None:
        return []
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return cfg.get("global", {}).get("invalid_codes", [])


def check_masks(
    df: pd.DataFrame,
    station: str,
    masks_by_station: dict[str, list[dict[str, Any]]],
    stations_avail: list[str],
) -> list[str]:
    """Prüft Masken für diese Station. Gibt Liste von Fehlermeldungen zurück (leer = OK)."""
    errors = []
    entries = list(masks_by_station.get(station, [])) + list(masks_by_station.get("all", []))
    for entry in entries:
        var = (entry.get("variable") or "").strip()
        start_s = entry.get("start")
        end_s = entry.get("end")
        if not var or not start_s or not end_s:
            continue
        if var not in df.columns:
            errors.append(f"  Maske {var} [{start_s}–{end_s}]: Spalte fehlt in Clean-Datei")
            continue
        try:
            start_ts = pd.Timestamp(start_s)
            end_ts = pd.Timestamp(end_s)
        except Exception:
            errors.append(f"  Maske {var}: ungültiges Datum start={start_s!r} end={end_s!r}")
            continue
        mask = (df.index >= start_ts) & (df.index <= end_ts)
        if not mask.any():
            continue
        series = pd.to_numeric(df.loc[mask, var], errors="coerce")
        is_missing = series.isna() | (series == MISSING_VALUE) | (series == -99999) | (series == 7999)
        violations = (~is_missing).sum()
        if violations > 0:
            errors.append(
                f"  Maske {var} [{start_s}–{end_s}]: {int(violations)} Werte sind nicht -9999/NaN (erwartet: alle maskiert)"
            )
    return errors


def check_limits(
    df: pd.DataFrame,
    station: str,
    limits: dict[str, dict[str, Any]],
) -> list[str]:
    """Prüft physikalische Grenzen. Gibt Liste von Fehlermeldungen zurück."""
    errors = []
    for col, lim in limits.items():
        if col not in df.columns or not isinstance(lim, dict):
            continue
        vmin, vmax = lim.get("min"), lim.get("max")
        if vmin is None and vmax is None:
            continue
        vals = pd.to_numeric(df[col], errors="coerce")
        missing = vals.isna() | (vals == MISSING_VALUE) | (vals == -99999) | (vals == 7999)
        valid = vals[~missing]
        if valid.empty:
            continue
        if vmin is not None:
            below = (valid < vmin).sum()
            if below > 0:
                errors.append(f"  Limit {col} [min={vmin}]: {int(below)} Werte darunter")
        if vmax is not None:
            above = (valid > vmax).sum()
            if above > 0:
                errors.append(f"  Limit {col} [max={vmax}]: {int(above)} Werte darüber")
    return errors


def check_invalid_codes(df: pd.DataFrame, invalid_codes: list[Any]) -> list[str]:
    """Prüft, ob invalid_codes noch in den Daten vorkommen."""
    errors = []
    for code in invalid_codes:
        if not isinstance(code, (int, float)):
            continue
        for col in df.columns:
            try:
                s = pd.to_numeric(df[col], errors="coerce")
                count = (s == code).sum()
                if count > 0:
                    errors.append(f"  Invalid code {code} noch {int(count)}× in Spalte {col}")
            except Exception:
                pass
    return errors


def main() -> None:
    if yaml is None:
        print("PyYAML fehlt. Bitte installieren: pip install pyyaml")
        sys.exit(1)
    masks_path = _get_masks_config_path()
    limits_path = _get_limits_config_path()
    if not limits_path:
        print("physical_limits_essd.yaml nicht gefunden.")
        sys.exit(1)
    print("Validierung der ESSD-Clean-Dateien")
    print("==================================")
    print(f"  Masks:   {masks_path or '(nicht gefunden)'}")
    print(f"  Limits:  {limits_path}")
    print()

    masks_by_station = load_masks_config()
    invalid_codes = load_invalid_codes()
    stations_with_clean = [
        s for s in STATIONS
        if (ESSD_DIR / f"{s}_essd_30min_clean.csv").exists()
    ]
    if not stations_with_clean:
        print("Keine *_essd_30min_clean.csv Dateien gefunden.")
        sys.exit(0)

    all_ok = True
    for station in STATIONS:
        path = ESSD_DIR / f"{station}_essd_30min_clean.csv"
        if not path.exists():
            continue
        result = load_essd_csv(path)
        if result is None:
            print(f"{station}: Konnte Clean-Datei nicht lesen.")
            all_ok = False
            continue
        df, _, _ = result

        errs = []
        # Masks
        errs.extend(check_masks(df, station, masks_by_station, stations_with_clean))
        # Limits
        limits = load_limits_config(station)
        errs.extend(check_limits(df, station, limits))
        # Invalid codes
        errs.extend(check_invalid_codes(df, invalid_codes))

        if errs:
            all_ok = False
            print(f"{station}:")
            for e in errs:
                print(e)
            print()
        else:
            print(f"{station}: OK (Masks + Limits + Invalid-Codes)")

    if all_ok:
        print("\nAlle geprüften Stationen: Korrekturen wie in den YAMLs definiert angewandt.")
    else:
        print("\nEs gibt Verstöße. Bitte edit_essd_data_tables.py und/oder apply_physical_limits_essd.py erneut ausführen.")
        sys.exit(1)


if __name__ == "__main__":
    main()
