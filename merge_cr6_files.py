#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Führt CR6 Public Rohdaten zusammen.

Lädt alle CR6 Public Dateien aus ~/Data/{station}/raw/
und führt sie zu einer zusammenhängenden Zeitreihe zusammen.
Entfernt Duplikate und behält möglichst viele Variablen.

Speichert als Parquet in ~/Data/merged_long/
"""

import warnings
warnings.filterwarnings('ignore')

from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime
import argparse

# Konfiguration
RAW_BASE = Path.home() / "Data"
OUTPUT_DIR = Path.home() / "Data" / "merged_long"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

STATIONS = ["Gorigo", "Janga", "Kayoro", "Mole", "Nazinga"]
CR6_STATIONS = ["Janga", "Mole"]  # Stationen mit CR6-Dateien

# Dateinamen-Pattern für CR6 Public Dateien
CR6_PATTERNS = [
    "CR6*_Public*.dat",
    "CR6*Public*.dat",
    "*CR6*Public*.dat",
]


def read_cr6_file(file_path: Path) -> pd.DataFrame:
    """
    Liest eine CR6 Public Datei.
    
    TOA5 Format:
    - Zeile 0: TOA5 Info (überspringen)
    - Zeile 1: Spaltennamen (Header) - BEHALTEN
    - Zeile 2: Einheiten (überspringen)
    - Zeile 3: Aggregationstyp (überspringen)
    - Zeile 4+: Daten
    """
    try:
        # Öffne Datei mit error handling
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            df = pd.read_csv(
                f,
                skiprows=[0, 2],  # Überspringe Zeile 0 und 2 (Zeile 1 = Header)
                header=0,  # Zeile 1 ist der Header
                index_col=0,  # Erste Spalte ist TIMESTAMP
                parse_dates=True,
                na_values=["NAN", "NA", "-9999", "-9999.0", "-9999.9003906", ""],
                low_memory=False,
                on_bad_lines='skip'
            )
        
        # Entferne RECORD Spalte falls vorhanden
        if 'RECORD' in df.columns:
            df = df.drop(columns=['RECORD'])
        
        # Stelle sicher, dass Index Datetime ist
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, errors='coerce')
        
        # Filtere ungültige Daten
        df = df[df.index.notna()]
        df = df[(df.index.year >= 2000) & (df.index.year <= 2030)]
        df = df.sort_index()
        
        # Entferne Duplikate im Index (behalte ersten Wert)
        if df.index.duplicated().any():
            n_dups = df.index.duplicated().sum()
            df = df[~df.index.duplicated(keep='first')]
            print(f"      (entfernt: {n_dups} Index-Duplikate)")
        
        return df
    
    except Exception as e:
        print(f"      ⚠️ Fehler beim Lesen von {file_path.name}: {e}")
        return pd.DataFrame()


def find_cr6_files(station: str) -> list:
    """Findet alle CR6 Public Dateien für eine Station."""
    raw_dir = RAW_BASE / station / "raw"
    
    if not raw_dir.exists():
        return []
    
    cr6_files = []
    for pattern in CR6_PATTERNS:
        for file in raw_dir.glob(pattern):
            if file.is_file() and file.suffix == '.dat':
                # Überspringe Backup-Dateien
                if '.bak' not in file.name and '._' not in file.name:
                    cr6_files.append(file)
    
    # Entferne Duplikate (falls mehrere Patterns matchen)
    cr6_files = list(set(cr6_files))
    cr6_files.sort()  # Sortiere nach Dateiname
    
    return cr6_files


def merge_cr6_dataframes(dataframes: list) -> pd.DataFrame:
    """
    Führt mehrere CR6 DataFrames zusammen.
    
    Strategie:
    1. Kombiniere alle DataFrames mit outer join (behält alle Spalten)
    2. Entferne Duplikate im Index (behalte ersten Wert)
    3. Kombiniere Spalten mit identischen Namen (füllt NaN-Werte)
    """
    if not dataframes:
        return pd.DataFrame()
    
    # Entferne leere DataFrames
    dataframes = [df for df in dataframes if not df.empty]
    
    if not dataframes:
        return pd.DataFrame()
    
    # Wenn nur ein DataFrame, direkt zurückgeben
    if len(dataframes) == 1:
        return dataframes[0]
    
    # Strategie: Kombiniere DataFrames mit outer join
    # Dies behält alle Spalten und kombiniert Werte wo möglich
    
    # Starte mit dem ersten DataFrame
    result = dataframes[0].copy()
    
    # Füge die anderen DataFrames hinzu
    for i, df in enumerate(dataframes[1:], 1):
        # Finde gemeinsame Zeitpunkte und neue Zeitpunkte
        common_idx = result.index.intersection(df.index)
        new_idx = df.index.difference(result.index)
        
        # Für gemeinsame Zeitpunkte: fülle NaN-Werte in result mit Werten aus df
        if len(common_idx) > 0:
            for col in df.columns:
                if col in result.columns:
                    # Spalte existiert: fülle NaN-Werte
                    mask = result.loc[common_idx, col].isna() & df.loc[common_idx, col].notna()
                    if mask.any():
                        result.loc[common_idx[mask], col] = df.loc[common_idx[mask], col]
                else:
                    # Neue Spalte: füge hinzu (erstmal mit NaN)
                    result[col] = np.nan
                    result.loc[common_idx, col] = df.loc[common_idx, col]
        
        # Füge neue Zeitpunkte hinzu
        if len(new_idx) > 0:
            # Erweitere result um neue Spalten falls nötig
            for col in df.columns:
                if col not in result.columns:
                    result[col] = np.nan
            
            # Füge neue Zeilen hinzu
            new_data = df.loc[new_idx].copy()
            # Füge fehlende Spalten hinzu
            for col in result.columns:
                if col not in new_data.columns:
                    new_data[col] = np.nan
            
            # Stelle sicher, dass Spaltenreihenfolge übereinstimmt
            new_data = new_data.reindex(columns=result.columns)
            result = pd.concat([result, new_data], axis=0)
    
    # Sortiere nach Index
    result = result.sort_index()
    
    # Entferne Duplikate im Index (behalte ersten Wert)
    if result.index.duplicated().any():
        n_dups = result.index.duplicated().sum()
        result = result[~result.index.duplicated(keep='first')]
        print(f"    (entfernt: {n_dups} Index-Duplikate nach Merge)")
    
    # Entferne Spalten die komplett leer sind
    result = result.dropna(axis=1, how='all')
    
    # Sortiere Spalten alphabetisch für bessere Übersicht
    result = result.reindex(sorted(result.columns), axis=1)
    
    return result


def process_station(station: str) -> bool:
    """Verarbeitet eine Station."""
    print(f"\n{'='*60}")
    print(f"📍 Station: {station}")
    print("=" * 60)
    
    # Finde CR6-Dateien
    cr6_files = find_cr6_files(station)
    
    if not cr6_files:
        print(f"  ❌ Keine CR6-Dateien gefunden")
        return False
    
    print(f"  📂 Gefundene CR6-Dateien: {len(cr6_files)}")
    
    # Lade alle CR6-Dateien
    dataframes = []
    total_rows = 0
    
    for file_path in cr6_files:
        print(f"    → Lade: {file_path.name}")
        df = read_cr6_file(file_path)
        
        if not df.empty:
            dataframes.append(df)
            total_rows += len(df)
            print(f"      {len(df):,} Zeilen, {len(df.columns)} Spalten, "
                  f"{df.index.min().date()} → {df.index.max().date()}")
        else:
            print(f"      ⚠️ Leer oder Fehler")
    
    if not dataframes:
        print(f"  ❌ Keine gültigen Daten gefunden")
        return False
    
    # Führe zusammen
    print(f"\n  🔄 Führe {len(dataframes)} Dateien zusammen...")
    merged = merge_cr6_dataframes(dataframes)
    
    if merged.empty:
        print(f"  ❌ Merge fehlgeschlagen")
        return False
    
    print(f"  ✅ Zusammenführung erfolgreich:")
    print(f"     {len(merged):,} Zeilen, {len(merged.columns)} Spalten")
    print(f"     {merged.index.min().date()} → {merged.index.max().date()}")
    
    # Statistik: Abdeckung pro Spalte
    coverage = {}
    for col in merged.columns:
        non_null = merged[col].notna().sum()
        coverage_pct = (non_null / len(merged)) * 100
        coverage[col] = coverage_pct
    
    # Zeige Top 10 Spalten mit höchster Abdeckung
    sorted_cols = sorted(coverage.items(), key=lambda x: x[1], reverse=True)
    print(f"\n  📊 Top 10 Variablen (nach Abdeckung):")
    for col, pct in sorted_cols[:10]:
        print(f"     {col:30s} {pct:6.1f}%")
    
    # Speichere als Parquet
    output_file = OUTPUT_DIR / f"{station}_cr6_merged.parquet"
    
    # Konvertiere alle Spalten zu numerisch (außer Index)
    for col in merged.columns:
        if merged[col].dtype == 'object':
            merged[col] = pd.to_numeric(merged[col], errors='coerce')
    
    merged.to_parquet(output_file, compression='snappy')
    file_size = output_file.stat().st_size / (1024*1024)
    
    print(f"\n  💾 Gespeichert: {output_file.name} ({file_size:.1f} MB)")
    
    return True


def select_station() -> str:
    """Fragt den Benutzer nach der Station."""
    print("\n" + "=" * 60)
    print("  Verfügbare Stationen mit CR6-Dateien:")
    print("=" * 60)
    
    available = []
    for i, station in enumerate(CR6_STATIONS, 1):
        files = find_cr6_files(station)
        if files:
            status = "✓"
            available.append(station)
        else:
            status = "✗"
        print(f"  {i}) {station:12s} [{status}]")
    
    print("=" * 60)
    
    while True:
        try:
            choice = input(f"\nStation auswählen (1-{len(CR6_STATIONS)}): ").strip()
            
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(CR6_STATIONS):
                    station = CR6_STATIONS[idx]
                    if station in available:
                        return station
                    else:
                        print(f"⚠️ Keine CR6-Dateien für {station} gefunden")
            else:
                # Name eingegeben
                for station in CR6_STATIONS:
                    if station.lower() == choice.lower():
                        if station in available:
                            return station
                        else:
                            print(f"⚠️ Keine CR6-Dateien für {station} gefunden")
                            break
            
            print(f"⚠️ Ungültige Eingabe.")
        
        except KeyboardInterrupt:
            print("\n\nAbgebrochen.")
            exit(0)


def main():
    parser = argparse.ArgumentParser(
        description="Führt CR6 Public Rohdaten zusammen",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--station', '-s',
        type=str,
        help='Station (Janga, Mole)'
    )
    parser.add_argument(
        '--all', '-a',
        action='store_true',
        help='Verarbeite alle Stationen'
    )
    
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("  CR6 ROHDATEN ZUSAMMENFÜHREN")
    print("=" * 60)
    print(f"\n📁 Rohdaten:  {RAW_BASE}")
    print(f"📁 Ausgabe:   {OUTPUT_DIR}")
    
    # Station(en) auswählen
    if args.all:
        stations_to_process = CR6_STATIONS
    elif args.station:
        if args.station in CR6_STATIONS:
            stations_to_process = [args.station]
        else:
            print(f"⚠️ Unbekannte Station: {args.station}")
            print(f"   Verfügbare Stationen: {', '.join(CR6_STATIONS)}")
            return
    else:
        station = select_station()
        stations_to_process = [station]
    
    # Verarbeite Stationen
    success_count = 0
    for station in stations_to_process:
        if process_station(station):
            success_count += 1
    
    # Zusammenfassung
    print("\n" + "=" * 60)
    print("  ZUSAMMENFASSUNG")
    print("=" * 60)
    print(f"\n✅ Erfolgreich verarbeitet: {success_count}/{len(stations_to_process)}")
    print(f"📁 Alle Dateien in: {OUTPUT_DIR}")
    print("\n🎉 Fertig!")


if __name__ == "__main__":
    main()


