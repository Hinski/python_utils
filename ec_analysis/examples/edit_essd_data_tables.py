#!/usr/bin/env python3
"""
Bearbeitung der ESSD-Datentabellen (export_essd_data_tables.py) anhand einer Konfigurationsdatei.

Alle Bereiche, die durch Fehlwerte (-9999) ersetzt werden sollen, trägst du in
edit_essd_masks.yaml ein (im gleichen Verzeichnis wie die Datensätze: essd_data_tables,
oder im Skriptverzeichnis). Beim Ausführen verarbeitet das Skript alle Einträge in einem Durchlauf.

In der YAML:
  masks: Liste von { station, variables, start, end } – Zeiträume auf -9999 setzen
  removes: optional – Liste von { station, variables } – Variablen komplett entfernen

Es wird nie die ursprüngliche *_essd_30min.csv überschrieben; Ausgabe immer als *_essd_30min_clean.csv.
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
CONFIG_NAME = "edit_essd_masks.yaml"
CONFIG_PATH = ESSD_DIR / CONFIG_NAME
CONFIG_FALLBACK = SCRIPT_DIR / CONFIG_NAME
MISSING_VALUE = -9999
STATIONS = ["Nazinga", "Kayoro", "Sumbrungu", "Gorigo", "Janga", "Mole"]


def load_essd_csv(path: Path) -> tuple[pd.DataFrame, list[str], list[str]] | None:
    """
    Liest ESSD-CSV: Zeile 1 = Variablennamen, Zeile 2 = Units, ab Zeile 3 = Daten.
    Returns: (DataFrame mit DatetimeIndex, Variablennamen inkl. TIMESTAMP, Units) oder None.
    """
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
    """Schreibt ESSD-CSV: Header, Units, Datenzeilen; TIMESTAMP aus Index, Fehlwerte als -9999."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Spaltenreihenfolge: alle var_names außer TIMESTAMP (Index wird als TIMESTAMP geschrieben)
    data_cols = [c for c in var_names if c != "TIMESTAMP"]
    table = df.reindex(columns=data_cols)
    table = table.replace({np.nan: MISSING_VALUE})
    with path.open("w", encoding="utf-8") as f:
        f.write(",".join(var_names) + "\n")
        f.write(",".join(var_units) + "\n")
        for idx, row in table.iterrows():
            ts_str = idx.strftime("%Y%m%d%H%M%S")
            values = [ts_str]
            for c in data_cols:
                v = row.get(c, MISSING_VALUE)
                if pd.isna(v) or v == MISSING_VALUE:
                    values.append(str(MISSING_VALUE))
                else:
                    values.append(str(v))
            f.write(",".join(values) + "\n")


def get_load_path(station: str) -> Path | None:
    """
    Pfad zum Laden: falls *_essd_30min_clean.csv existiert, diese laden (weitere Bearbeitung),
    sonst die ursprüngliche *_essd_30min.csv.
    """
    clean_path = ESSD_DIR / f"{station}_essd_30min_clean.csv"
    base_path = ESSD_DIR / f"{station}_essd_30min.csv"
    if clean_path.exists():
        return clean_path
    if base_path.exists():
        return base_path
    return None


def get_save_path(load_path: Path) -> Path:
    """
    Speicherpfad: steht bereits 'clean' im Dateinamen, dieselbe Datei überschreiben,
    sonst neue Datei mit '_clean' vor der Endung (Original wird nicht überschrieben).
    """
    if "clean" in load_path.name:
        return load_path
    return load_path.parent / f"{load_path.stem}_clean.csv"


def available_stations() -> list[str]:
    return [s for s in STATIONS if get_load_path(s) is not None]


def _get_config_path() -> Path | None:
    if CONFIG_PATH.exists():
        return CONFIG_PATH
    if CONFIG_FALLBACK.exists():
        return CONFIG_FALLBACK
    return None


def _load_config() -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """
    Lädt edit_essd_masks.yaml.
    masks: Dict Station -> Liste von { variable, start, end } (eine Variable pro Eintrag, eigener Zeitraum).
    removes: Liste von { station, variables } wie bisher.
    """
    path = _get_config_path()
    if yaml is None:
        return {}, []
    if path is None:
        return {}, []
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    raw_masks = cfg.get("masks") or {}
    removes = cfg.get("removes") or []
    if not isinstance(removes, list):
        removes = []

    # masks als Dict: Stationsname -> [ { variable, start, end }, ... ]
    masks_by_station: dict[str, list[dict[str, Any]]] = {}
    if isinstance(raw_masks, dict):
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
                    # Eintrag mit variables-Liste: pro Variable einen Eintrag mit gleichem start/end
                    for v in raw_var:
                        v = str(v).strip()
                        if v and e.get("start") and e.get("end"):
                            list_ok.append({"variable": v, "start": e.get("start"), "end": e.get("end")})
                else:
                    var = str(raw_var).strip()
                    if var and e.get("start") and e.get("end"):
                        list_ok.append({"variable": var, "start": e.get("start"), "end": e.get("end")})
            if list_ok:
                masks_by_station[station_key] = list_ok
    return masks_by_station, removes


def _stations_for_entries(
    masks_by_station: dict[str, list[dict[str, Any]]],
    removes: list[dict[str, Any]],
    stations_avail: list[str],
) -> set[str]:
    """Menge der Stationen, die von mindestens einem Eintrag betroffen sind."""
    out: set[str] = set()
    for st in masks_by_station:
        if not st:
            continue
        if st.lower() == "all":
            out.update(stations_avail)
        else:
            for s in stations_avail:
                if s.lower() == st.lower():
                    out.add(s)
                    break
    for e in removes:
        st = (e.get("station") or "").strip()
        if not st:
            continue
        if st.lower() == "all":
            out.update(stations_avail)
        else:
            for s in stations_avail:
                if s.lower() == st.lower():
                    out.add(s)
                    break
    return out


def main() -> None:
    stations_avail = available_stations()
    if not stations_avail:
        print(f"Keine ESSD-Dateien in {ESSD_DIR} gefunden.")
        sys.exit(1)

    config_path = _get_config_path()
    if config_path is None:
        print(f"Konfigurationsdatei nicht gefunden: {CONFIG_NAME}")
        print(f"  Erwartet in: {CONFIG_PATH} oder {CONFIG_FALLBACK}")
        sys.exit(1)
    if yaml is None:
        print("PyYAML fehlt. Bitte installieren: pip install pyyaml")
        sys.exit(1)

    masks_by_station, removes = _load_config()
    stations_to_edit = sorted(_stations_for_entries(masks_by_station, removes, stations_avail))
    if not stations_to_edit:
        print("Keine Stationen durch die Konfiguration betroffen (masks/removes leer oder unbekannte Station).")
        sys.exit(0)
    if not masks_by_station and not removes:
        print("Keine Einträge in masks oder removes. Bitte edit_essd_masks.yaml anpassen.")
        sys.exit(0)

    print(f"Konfiguration: {config_path}")
    print(f"Stationen: {', '.join(stations_to_edit)}")
    print()

    for station in stations_to_edit:
        load_path = get_load_path(station)
        if load_path is None:
            print(f"  {station}: Keine Datei gefunden, übersprungen.")
            continue
        result = load_essd_csv(load_path)
        if result is None:
            print(f"  {station}: Konnte Datei nicht lesen, übersprungen.")
            continue
        df, var_names, var_units = result
        save_path = get_save_path(load_path)
        modified = False

        # Alle Masken anwenden (pro Eintrag: eine Variable, ein Zeitraum -> -9999)
        station_entries = list(masks_by_station.get(station, [])) + list(masks_by_station.get("all", []))
        for entry in station_entries:
            var = (entry.get("variable") or "").strip()
            start_s = entry.get("start")
            end_s = entry.get("end")
            if not var or not start_s or not end_s:
                continue
            try:
                start_ts = pd.Timestamp(start_s)
                end_ts = pd.Timestamp(end_s)
            except Exception:
                print(f"  {station}: Ungültiges Datum (variable={var}, start={start_s!r}, end={end_s!r}), übersprungen.")
                continue
            if var not in df.columns:
                print(f"  {station}: Variable nicht vorhanden (ignoriert): {var}")
                continue
            mask = (df.index >= start_ts) & (df.index <= end_ts)
            n = mask.sum()
            df.loc[mask, var] = np.nan
            modified = True
            print(f"  {station}: {n} Zeilen {start_ts}–{end_ts} für {var} -> -9999")

        # Alle „removes“ anwenden (Spalten löschen)
        to_remove: list[str] = []
        for entry in removes:
            st = (entry.get("station") or "").strip()
            applies = st.lower() == "all" or (st and any(s.lower() == st.lower() for s in [station]))
            if not applies:
                continue
            variables = entry.get("variables") or []
            if isinstance(variables, str):
                variables = [variables]
            for v in variables:
                v = str(v).strip()
                if v and v in df.columns and v != "TIMESTAMP":
                    to_remove.append(v)
        if to_remove:
            to_keep = [v for v in var_names if v not in to_remove]
            if "TIMESTAMP" not in to_keep:
                to_keep.insert(0, "TIMESTAMP")
            units_by_var = dict(zip(var_names, var_units))
            new_units = [units_by_var[v] for v in to_keep]
            df = df[[c for c in df.columns if c in to_keep]]
            var_names, var_units = to_keep, new_units
            modified = True
            print(f"  {station}: Variablen entfernt: {to_remove}")

        if modified:
            write_essd_csv(save_path, df, var_names, var_units)
            print(f"  {station}: gespeichert -> {save_path.name}")
        else:
            print(f"  {station}: keine Änderungen (keine passenden Einträge für diese Station).")

    print("Fertig.")


if __name__ == "__main__":
    main()
