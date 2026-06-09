#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Importiert CR6-Dateien von externer Festplatte für Janga und Mole:
1. Sucht CR6-Dateien in /Volumes/Elements
2. Kopiert sie nach ~/Data/{Station}/raw/
3. Führt sie zu einer 30-min Zeitreihe zusammen
4. Speichert als Parquet in ~/Data/merged_long/
"""

import warnings
warnings.filterwarnings('ignore')

import shutil
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime

# ---------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------
EXTERNAL_DRIVE = Path("/Volumes/Elements")
DATA_BASE = Path.home() / "Data"
OUTPUT_DIR = DATA_BASE / "merged_long"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Stationen und ihre Suchpfade auf der externen Festplatte
STATIONS = {
    "Janga": [
        EXTERNAL_DRIVE / "Janga" / "Slow",
        EXTERNAL_DRIVE / "Janga_EC",
        EXTERNAL_DRIVE / "WASCAL_4_JANGA" / "logger",
        EXTERNAL_DRIVE / "WASCAL_4_JANGA" / "Janga",
    ],
    "Mole": [
        EXTERNAL_DRIVE / "Mole" / "Slow",
        EXTERNAL_DRIVE / "WASCAL_5_MOLE" / "Slow",
        EXTERNAL_DRIVE / "WASCAL_5_MOLE" / "SD_Card",
        EXTERNAL_DRIVE / "WASCAL_5_MOLE" / "CR1000X",
    ],
}

# Zeitraum und Frequenz
START_DATE = "2013-01-01"
END_DATE = "2025-12-01"
FREQ = "30min"

# Variablen die summiert werden
SUM_PATTERNS = ["rain", "precip", "acc_", "bucket", "_tot"]


def is_sum_variable(col_name: str) -> bool:
    """Prüft ob Variable bei Aggregation summiert werden soll."""
    col_lower = col_name.lower()
    return any(p in col_lower for p in SUM_PATTERNS)


def find_cr6_files(search_paths: list, station: str) -> list:
    """Findet alle CR6-Dateien in den Suchpfaden."""
    cr6_files = []
    patterns = ["*CR6*", "*cr6*", f"*{station}*Slow*", f"*{station}*Public*"]
    
    for search_path in search_paths:
        if not search_path.exists():
            continue
        
        print(f"  Suche in: {search_path}")
        
        # Direkte Dateien
        for pattern in patterns:
            for f in search_path.glob(pattern):
                if f.is_file() and f.suffix.lower() in ['.dat', '.csv', '.txt']:
                    if f not in cr6_files:
                        cr6_files.append(f)
        
        # Auch in Unterordnern (max 2 Ebenen)
        for subdir in search_path.iterdir():
            if subdir.is_dir():
                for pattern in patterns:
                    for f in subdir.glob(pattern):
                        if f.is_file() and f.suffix.lower() in ['.dat', '.csv', '.txt']:
                            if f not in cr6_files:
                                cr6_files.append(f)
    
    return sorted(cr6_files)


def copy_files_to_raw(files: list, station: str) -> Path:
    """Kopiert Dateien nach ~/Data/{Station}/raw/"""
    raw_dir = DATA_BASE / station / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    
    copied = 0
    for src in files:
        dst = raw_dir / src.name
        if not dst.exists():
            print(f"    Kopiere: {src.name}")
            shutil.copy2(src, dst)
            copied += 1
        else:
            print(f"    Existiert bereits: {src.name}")
    
    print(f"  → {copied} neue Dateien kopiert nach {raw_dir}")
    return raw_dir


def read_cr6_file(path: Path) -> pd.DataFrame:
    """Liest eine CR6/TOA5 Datei."""
    try:
        # TOA5 Format:
        #   Zeile 0: "TOA5", Station info (überspringen)
        #   Zeile 1: Spaltennamen (als Header verwenden)
        #   Zeile 2: Einheiten (überspringen)
        #   Zeile 3: Aggregationstyp "Avg", "Smp" etc. (überspringen)
        #   Zeile 4+: Daten
        df = pd.read_csv(
            path,
            skiprows=[0, 2, 3],  # Überspringe Info, Units, Aggregation - behalte Header (Zeile 1)
            header=0,
            index_col=0,
            parse_dates=True,
            na_values=["NAN", "NA", "-9999", "INF", "-INF", ""],
            low_memory=False
        )
        
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, errors='coerce')
        
        df = df[df.index.notna()]
        df = df[(df.index.year >= 2000) & (df.index.year <= 2030)]
        df = df.sort_index()
        df = df[~df.index.duplicated(keep='first')]
        
        return df
    except Exception as e:
        print(f"    ⚠️ Fehler: {path.name}: {e}")
        return pd.DataFrame()


def resample_to_30min(df: pd.DataFrame) -> pd.DataFrame:
    """Resampelt auf 30-Minuten."""
    if df.empty or len(df) < 2:
        return df
    
    time_diff = df.index.to_series().diff().median()
    target_td = pd.Timedelta(FREQ)
    
    if abs(time_diff - target_td) < pd.Timedelta("5min"):
        return df
    
    print(f"      (Resample: {time_diff} → {FREQ})")
    
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    non_numeric_cols = [c for c in df.columns if c not in numeric_cols]
    
    sum_cols = [c for c in numeric_cols if is_sum_variable(c)]
    mean_cols = [c for c in numeric_cols if c not in sum_cols]
    
    parts = []
    if mean_cols:
        parts.append(df[mean_cols].resample(FREQ).mean())
    if sum_cols:
        parts.append(df[sum_cols].resample(FREQ).sum())
    if non_numeric_cols:
        parts.append(df[non_numeric_cols].resample(FREQ).first())
    
    if not parts:
        return df
    
    result = pd.concat(parts, axis=1)
    return result.reindex(columns=df.columns)


def merge_files(raw_dir: Path, station: str) -> pd.DataFrame:
    """Führt alle CR6-Dateien zusammen."""
    all_files = list(raw_dir.glob("*CR6*")) + list(raw_dir.glob("*cr6*"))
    all_files = [f for f in all_files if f.is_file()]
    all_files = sorted(set(all_files))
    
    if not all_files:
        print("  ⚠️ Keine CR6-Dateien gefunden")
        return pd.DataFrame()
    
    print(f"\n  Lade {len(all_files)} Dateien...")
    
    dfs = []
    for f in all_files:
        print(f"    → {f.name}")
        df = read_cr6_file(f)
        if not df.empty:
            df = resample_to_30min(df)
            dfs.append(df)
    
    if not dfs:
        return pd.DataFrame()
    
    # Kombiniere alle DataFrames
    print(f"\n  Kombiniere {len(dfs)} DataFrames...")
    combined = pd.concat(dfs)
    combined = combined.sort_index()
    combined = combined[~combined.index.duplicated(keep='first')]
    
    # Reindex auf vollen Zeitraum
    full_index = pd.date_range(START_DATE, END_DATE, freq=FREQ)
    result = combined.reindex(full_index)
    result.index.name = "TIMESTAMP"
    
    # Entferne RECORD-Spalte
    if 'RECORD' in result.columns:
        result = result.drop(columns=['RECORD'])
    
    return result


def save_result(df: pd.DataFrame, station: str) -> Path:
    """Speichert als Parquet."""
    output_path = OUTPUT_DIR / f"{station}_cr6_merged_long.parquet"
    df.to_parquet(output_path, compression='snappy')
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  💾 Gespeichert: {output_path.name} ({size_mb:.1f} MB)")
    return output_path


def process_station(station: str, search_paths: list):
    """Verarbeitet eine Station komplett."""
    print(f"\n{'='*60}")
    print(f"📍 Station: {station}")
    print('='*60)
    
    # 1. Finde CR6-Dateien
    print("\n1️⃣ Suche CR6-Dateien...")
    files = find_cr6_files(search_paths, station)
    print(f"   Gefunden: {len(files)} Dateien")
    
    if not files:
        print("   ⚠️ Keine Dateien gefunden!")
        return
    
    # 2. Kopiere nach raw
    print("\n2️⃣ Kopiere nach ~/Data/{}/raw/...".format(station))
    raw_dir = copy_files_to_raw(files, station)
    
    # 3. Merge
    print("\n3️⃣ Führe Dateien zusammen...")
    df = merge_files(raw_dir, station)
    
    if df.empty:
        print("   ⚠️ Keine Daten zum Speichern")
        return
    
    # Statistik
    non_empty = df.dropna(how='all').shape[0]
    total = len(df)
    coverage = non_empty / total * 100
    
    print(f"\n   Zeitraum: {df.index.min()} → {df.index.max()}")
    print(f"   Zeilen: {non_empty:,} / {total:,} ({coverage:.1f}% Abdeckung)")
    print(f"   Spalten: {len(df.columns)}")
    
    # 4. Speichern
    print("\n4️⃣ Speichere...")
    save_result(df, station)


def main():
    print("\n" + "="*60)
    print("  CR6-DATEN IMPORT")
    print("  Von: /Volumes/Elements")
    print("  Nach: ~/Data/{Station}/raw/ → merged_long/")
    print("="*60)
    
    # Prüfe externe Festplatte
    if not EXTERNAL_DRIVE.exists():
        print(f"\n❌ Externe Festplatte nicht gefunden: {EXTERNAL_DRIVE}")
        print("   Bitte Festplatte anschließen und erneut versuchen.")
        return
    
    print(f"\n✓ Externe Festplatte gefunden: {EXTERNAL_DRIVE}")
    
    # Verarbeite beide Stationen
    for station, search_paths in STATIONS.items():
        process_station(station, search_paths)
    
    print("\n" + "="*60)
    print("🎉 Fertig!")
    print("="*60)
    
    # Zeige Ergebnis
    print("\nErstellte Dateien:")
    for f in sorted(OUTPUT_DIR.glob("*_cr6_*.parquet")):
        size = f.stat().st_size / (1024*1024)
        print(f"  - {f.name} ({size:.1f} MB)")


if __name__ == "__main__":
    main()



