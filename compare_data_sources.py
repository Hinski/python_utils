#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Vergleicht Datenverfügbarkeit zwischen zwei Quellen:
1. ~/Diss/Data/test_data/long/ (Samuel's long series)
2. ~/Data/{Station}/merged/   (merged raw files)

Zeigt Zeiträume und Überlappungen für jede Station/Dateityp-Kombination.
"""

import warnings
warnings.filterwarnings('ignore')

from pathlib import Path
import pandas as pd
import re
from datetime import datetime

# ---------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------
LONG_DIR = Path.home() / "Diss/Data/test_data/long"
MERGED_BASE = Path.home() / "Data"

STATIONS = ["Gorigo", "Janga", "Kayoro", "Mole", "Nazinga", "Sumbrungu"]

# Mapping von Dateitypen (long -> merged)
TYPE_MAPPING = {
    "cr1000": "cr1000",
    "rad": "radiation",
    "radiation": "radiation",
    "result": "result",
    "smt": "smt",
    "rs": "rs",       # nur in long
    "wxt": "wxt",     # nur in long
}


def detect_file_format(path: Path) -> str:
    """Erkennt das Dateiformat (TOA5 oder CSV)."""
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        first_line = f.readline()
        if first_line.startswith('"TOA5"'):
            return "toa5"
        return "csv"


def get_time_range(path: Path) -> tuple:
    """
    Liest die erste und letzte Zeile einer Datei um den Zeitraum zu bestimmen.
    Gibt (start, end, rows) zurück.
    """
    try:
        file_format = detect_file_format(path)
        
        if file_format == "toa5":
            # TOA5: 4 Header-Zeilen überspringen
            df = pd.read_csv(
                path,
                skiprows=3,  # Skip first 3 rows (TOA5, units, stat type)
                header=0,    # Row 4 becomes header (TIMESTAMP, RECORD, ...)
                index_col=0,
                parse_dates=True,
                dayfirst=True,
                na_values=["NAN", "NA", "-9999", "INF", "-INF"],
                low_memory=False
            )
        else:
            # Normales CSV
            df = pd.read_csv(
                path,
                index_col=0,
                parse_dates=True,
                dayfirst=True,
                na_values=["NAN", "NA", "-9999", "-9999.9003906"],
                low_memory=False
            )
        
        # Index zu datetime konvertieren falls nötig
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, errors='coerce')
        
        # Ungültige Timestamps entfernen
        df = df[df.index.notna()]
        
        # Unrealistische Daten filtern (vor 2000 oder nach 2030)
        df = df[(df.index.year >= 2000) & (df.index.year <= 2030)]
        
        if df.empty:
            return None, None, 0
        
        df = df.sort_index()
        return df.index.min(), df.index.max(), len(df)
    
    except Exception as e:
        return None, None, 0


def scan_long_files() -> dict:
    """
    Scannt ~/Diss/Data/test_data/long/ nach Dateien.
    Gibt dict zurück: {(station, type): (path, start, end, rows)}
    """
    results = {}
    
    if not LONG_DIR.exists():
        print(f"⚠️ Long-Ordner nicht gefunden: {LONG_DIR}")
        return results
    
    for path in LONG_DIR.glob("*.dat"):
        name = path.stem.lower()
        
        # Parse: {Station}_long_{type}
        for station in STATIONS:
            if station.lower() in name:
                # Typ extrahieren
                match = re.search(r'_long_(\w+)$', name)
                if match:
                    ftype = match.group(1)
                    start, end, rows = get_time_range(path)
                    results[(station, ftype)] = {
                        'path': path,
                        'start': start,
                        'end': end,
                        'rows': rows,
                        'size_mb': path.stat().st_size / (1024*1024)
                    }
                break
    
    return results


def scan_merged_files() -> dict:
    """
    Scannt ~/Data/{Station}/merged/ nach Dateien.
    Gibt dict zurück: {(station, type): (path, start, end, rows)}
    """
    results = {}
    
    for station in STATIONS:
        merged_dir = MERGED_BASE / station / "merged"
        if not merged_dir.exists():
            continue
        
        for path in merged_dir.glob("*.csv"):
            name = path.stem.lower()
            
            # Typ extrahieren
            for ftype in ["cr1000", "radiation", "result", "smt"]:
                if ftype in name:
                    start, end, rows = get_time_range(path)
                    results[(station, ftype)] = {
                        'path': path,
                        'start': start,
                        'end': end,
                        'rows': rows,
                        'size_mb': path.stat().st_size / (1024*1024)
                    }
                    break
    
    return results


def format_date(dt) -> str:
    """Formatiert datetime für Ausgabe."""
    if pd.isna(dt) or dt is None:
        return "---"
    return dt.strftime("%Y-%m-%d")


def compare_sources():
    """Vergleicht beide Datenquellen und gibt Report aus."""
    
    print("\n" + "=" * 80)
    print("  DATENVERGLEICH: Long-Series vs. Merged-Files")
    print("=" * 80)
    print(f"\n📁 Long-Series:  {LONG_DIR}")
    print(f"📁 Merged-Files: {MERGED_BASE}/{{Station}}/merged/\n")
    
    # Scan beide Quellen
    print("Scanne Long-Series...", end=" ", flush=True)
    long_data = scan_long_files()
    print(f"✓ ({len(long_data)} Dateien)")
    
    print("Scanne Merged-Files...", end=" ", flush=True)
    merged_data = scan_merged_files()
    print(f"✓ ({len(merged_data)} Dateien)\n")
    
    # Alle Kombinationen sammeln
    all_types = sorted(set(
        [t for _, t in long_data.keys()] + 
        [t for _, t in merged_data.keys()]
    ))
    
    # Type-Normalisierung für Vergleich (rad -> radiation)
    def normalize_type(t):
        return TYPE_MAPPING.get(t, t)
    
    # Unified types für bessere Darstellung (rad und radiation zusammenfassen)
    unified_types = []
    seen = set()
    for t in all_types:
        normalized = normalize_type(t)
        if normalized not in seen:
            unified_types.append(normalized)
            seen.add(normalized)
    
    # Report pro Station
    for station in STATIONS:
        station_has_data = False
        
        # Check ob Station Daten hat
        for t in unified_types:
            # Long: check both original and normalized type
            if (station, t) in long_data:
                station_has_data = True
                break
            # Check for rad -> radiation mapping
            for orig, norm in TYPE_MAPPING.items():
                if norm == t and (station, orig) in long_data:
                    station_has_data = True
                    break
            if (station, t) in merged_data:
                station_has_data = True
                break
        
        if not station_has_data:
            continue
        
        print("-" * 80)
        print(f"📍 {station}")
        print("-" * 80)
        print(f"{'Typ':<12} │ {'Long-Series':<25} │ {'Merged-Files':<25} │ Differenz")
        print(f"{'':<12} │ {'(Start → End)':<25} │ {'(Start → End)':<25} │")
        print("-" * 80)
        
        for ftype in unified_types:
            # Long data - check normalized type and original types
            long_info = long_data.get((station, ftype))
            if not long_info:
                # Check for reverse mapping (e.g., rad -> radiation)
                for orig, norm in TYPE_MAPPING.items():
                    if norm == ftype and (station, orig) in long_data:
                        long_info = long_data.get((station, orig))
                        break
            
            # Merged data
            merged_info = merged_data.get((station, ftype))
            
            if not long_info and not merged_info:
                continue
            
            # Long-Series Info
            if long_info and long_info['start']:
                long_str = f"{format_date(long_info['start'])} → {format_date(long_info['end'])}"
                long_rows = f"({long_info['rows']:,} rows)"
            elif long_info:
                long_str = "(Lesefehler)"
                long_rows = ""
            else:
                long_str = "---"
                long_rows = ""
            
            # Merged-Files Info
            if merged_info and merged_info['start']:
                merged_str = f"{format_date(merged_info['start'])} → {format_date(merged_info['end'])}"
                merged_rows = f"({merged_info['rows']:,} rows)"
            elif merged_info:
                merged_str = "(Lesefehler)"
                merged_rows = ""
            else:
                merged_str = "---"
                merged_rows = ""
            
            # Differenz berechnen
            diff_str = ""
            if long_info and merged_info and long_info['start'] and merged_info['start']:
                # Vergleiche Enddaten
                if long_info['end'] and merged_info['end']:
                    days_diff = (merged_info['end'] - long_info['end']).days
                    if days_diff > 0:
                        diff_str = f"Merged +{days_diff}d"
                    elif days_diff < 0:
                        diff_str = f"Long +{-days_diff}d"
                    else:
                        diff_str = "gleich"
            elif long_info and not merged_info:
                diff_str = "nur Long"
            elif merged_info and not long_info:
                diff_str = "nur Merged"
            
            print(f"{ftype:<12} │ {long_str:<25} │ {merged_str:<25} │ {diff_str}")
        
        print()
    
    # Zusammenfassung
    print("=" * 80)
    print("  ZUSAMMENFASSUNG")
    print("=" * 80)
    
    # Dateien nur in Long (rs, wxt haben kein Merged-Äquivalent)
    only_long = []
    for (station, ftype) in long_data.keys():
        normalized = normalize_type(ftype)
        if (station, normalized) not in merged_data and (station, ftype) not in merged_data:
            info = long_data[(station, ftype)]
            if info['start']:  # Nur wenn lesbar
                only_long.append((station, ftype, info))
    
    if only_long:
        print("\n📌 Nur in Long-Series vorhanden (rs, wxt):")
        for station, ftype, info in sorted(only_long, key=lambda x: (x[0], x[1])):
            print(f"   - {station}/{ftype}: {format_date(info['start'])} → {format_date(info['end'])}")
    
    # Dateien nur in Merged
    only_merged = []
    for (station, ftype) in merged_data.keys():
        # Check ob es Long-Äquivalent gibt
        has_long = False
        for long_type, mapped in TYPE_MAPPING.items():
            if mapped == ftype and (station, long_type) in long_data:
                has_long = True
                break
        if (station, ftype) in long_data:
            has_long = True
        if not has_long:
            info = merged_data[(station, ftype)]
            if info['start']:
                only_merged.append((station, ftype, info))
    
    if only_merged:
        print("\n📌 Nur in Merged-Files vorhanden:")
        for station, ftype, info in sorted(only_merged, key=lambda x: (x[0], x[1])):
            print(f"   - {station}/{ftype}: {format_date(info['start'])} → {format_date(info['end'])}")
    
    # Empfehlungen
    print("\n" + "-" * 80)
    print("💡 EMPFEHLUNGEN:")
    print("-" * 80)
    
    recommendations = []
    
    # Check wo Long aktueller ist als Merged
    for station in STATIONS:
        for ftype in unified_types:
            long_info = long_data.get((station, ftype))
            if not long_info:
                for orig, norm in TYPE_MAPPING.items():
                    if norm == ftype and (station, orig) in long_data:
                        long_info = long_data.get((station, orig))
                        break
            
            merged_info = merged_data.get((station, ftype))
            
            if long_info and merged_info and long_info['end'] and merged_info['end']:
                days_diff = (long_info['end'] - merged_info['end']).days
                if days_diff > 30:  # Long ist >30 Tage aktueller
                    recommendations.append(
                        f"   → {station}/{ftype}: Long ist {days_diff} Tage aktueller, "
                        f"Merged endet {format_date(merged_info['end'])}"
                    )
    
    if recommendations:
        print("Merged-Files aktualisieren (Long hat neuere Daten):")
        for rec in recommendations:
            print(rec)
    else:
        print("   Keine Aktualisierungen nötig - Merged-Files sind aktuell.")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    compare_sources()

