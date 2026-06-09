#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Findet und kopiert CR6 Public Dateien von /Volumes/Elements nach ~/Data/{station}/raw/

Prüft Zeiträume und kopiert nur wenn neue Daten vorhanden sind.
"""

import pandas as pd
from pathlib import Path
import shutil
from datetime import datetime

# Konfiguration
SOURCE_BASE = Path("/Volumes/Elements")
DEST_BASE = Path.home() / "Data"
STATIONS = ["Janga", "Mole"]

def read_cr6_header(file_path: Path):
    """Liest die ersten Zeilen einer CR6-Datei um Format zu prüfen."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = [f.readline() for _ in range(5)]
        return lines
    except:
        return None

def get_time_range_from_cr6(file_path: Path):
    """Liest den Zeitraum aus einer CR6 Public Datei."""
    try:
        # TOA5 Format: Header in Zeile 2 (Index 1)
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = [f.readline() for _ in range(5)]
            
            if len(lines) < 5:
                return None, None
            
            # Prüfe Format
            if 'TOA5' in lines[0] or 'TOB3' in lines[0]:
                # TOA5/TOB3 Format
                # Zeile 1 (Index 1) = Header
                # Zeile 4+ = Daten
                timestamps = []
                f.seek(0)
                # Überspringe Header-Zeilen
                for i in range(4):
                    f.readline()
                
                # Lese Daten
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        parts = line.split(',')
                        if len(parts) > 0:
                            ts_str = parts[0].strip('"')
                            if ts_str and ts_str != 'NAN' and 'TIMESTAMP' not in ts_str:
                                try:
                                    ts = pd.to_datetime(ts_str)
                                    if ts.year >= 2000 and ts.year <= 2030:
                                        timestamps.append(ts)
                                except:
                                    continue
                    except:
                        continue
                    
                    # Limit für Performance
                    if len(timestamps) > 10000:
                        break
                
                if timestamps:
                    return min(timestamps), max(timestamps)
    except Exception as e:
        print(f"      Fehler: {e}")
    return None, None

def find_cr6_public_files(station: str):
    """Findet alle CR6 Public Dateien für eine Station."""
    files = []
    
    for pattern in [
        f"*CR6{station}*Public*.dat",
        f"*CR6*{station}*Public*.dat",
    ]:
        for file_path in SOURCE_BASE.rglob(pattern):
            if file_path.is_file():
                # Überspringe Backup und versteckte Dateien
                if '.bak' not in file_path.name and '._' not in file_path.name:
                    # Prüfe ob es wirklich eine Public Datei ist
                    if 'Public' in file_path.name or 'public' in file_path.name.lower():
                        files.append(file_path)
    
    return list(set(files))  # Entferne Duplikate

def get_existing_time_ranges(dest_dir: Path):
    """Sammelt Zeiträume aus vorhandenen Dateien."""
    time_ranges = []
    
    if not dest_dir.exists():
        return time_ranges
    
    for file in dest_dir.glob("CR6*Public*.dat"):
        if '.bak' not in file.name:
            start, end = get_time_range_from_cr6(file)
            if start and end:
                time_ranges.append((start, end, file.name))
    
    return time_ranges

def has_new_data(src_file: Path, existing_ranges: list):
    """Prüft ob die Quelldatei neue Zeiträume enthält."""
    src_start, src_end = get_time_range_from_cr6(src_file)
    if not src_start or not src_end:
        return False
    
    # Prüfe ob dieser Zeitraum bereits abgedeckt ist
    for exist_start, exist_end, _ in existing_ranges:
        # Wenn Quelle vollständig innerhalb vorhandener Daten
        if exist_start <= src_start <= exist_end and exist_start <= src_end <= exist_end:
            # Aber prüfe auch ob Quelle größer/neuer ist
            if src_end > exist_end or src_start < exist_start:
                return True  # Erweitert den Zeitraum
            return False  # Vollständig abgedeckt
    
    return True  # Enthält neue Daten

def copy_cr6_files(station: str):
    """Findet und kopiert CR6 Public Dateien."""
    print(f"\n{'='*60}")
    print(f"Station: {station}")
    print(f"{'='*60}")
    
    dest_dir = DEST_BASE / station / "raw"
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    # Finde alle CR6 Public Dateien
    source_files = find_cr6_public_files(station)
    
    if not source_files:
        print(f"  ❌ Keine CR6 Public Dateien gefunden")
        return
    
    print(f"  📂 Gefundene Dateien: {len(source_files)}")
    
    # Sammle vorhandene Zeiträume
    existing_ranges = get_existing_time_ranges(dest_dir)
    
    copied_count = 0
    updated_count = 0
    skipped_count = 0
    
    for src_file in source_files:
        print(f"\n    📄 {src_file.name}")
        print(f"       Pfad: {src_file.parent}")
        
        # Prüfe Zeitraum
        src_start, src_end = get_time_range_from_cr6(src_file)
        if src_start and src_end:
            print(f"       Zeitraum: {src_start.date()} → {src_end.date()}")
        else:
            print(f"       ⚠️ Konnte Zeitraum nicht lesen")
            continue
        
        # Bestimme Ziel-Dateiname
        dest_file = dest_dir / src_file.name
        
        # Prüfe ob Datei bereits existiert
        if dest_file.exists():
            # Vergleiche Größe und Datum
            src_size = src_file.stat().st_size
            src_mtime = src_file.stat().st_mtime
            dest_size = dest_file.stat().st_size
            dest_mtime = dest_file.stat().st_mtime
            
            # Prüfe ob neue Daten vorhanden sind
            if has_new_data(src_file, existing_ranges) or src_size > dest_size or src_mtime > dest_mtime:
                print(f"       → UPDATE: Datei existiert, aber Quelle ist neuer/größer")
                shutil.copy2(src_file, dest_file)
                updated_count += 1
                # Aktualisiere Zeiträume
                start, end = get_time_range_from_cr6(dest_file)
                if start and end:
                    existing_ranges.append((start, end, dest_file.name))
            else:
                print(f"       ⏭️  SKIP: Bereits vorhanden und aktuell")
                skipped_count += 1
        else:
            # Neue Datei - kopiere
            print(f"       → COPY: Neue Datei")
            shutil.copy2(src_file, dest_file)
            copied_count += 1
            # Aktualisiere Zeiträume
            start, end = get_time_range_from_cr6(dest_file)
            if start and end:
                existing_ranges.append((start, end, dest_file.name))
    
    print(f"\n  📊 Zusammenfassung für {station}:")
    print(f"     Kopiert: {copied_count}")
    print(f"     Aktualisiert: {updated_count}")
    print(f"     Übersprungen: {skipped_count}")

def main():
    print("\n" + "=" * 60)
    print("  CR6 PUBLIC DATEIEN FINDEN UND KOPIEREN")
    print("=" * 60)
    print(f"\n📁 Quelle:  {SOURCE_BASE}")
    print(f"📁 Ziel:    {DEST_BASE}")
    
    for station in STATIONS:
        copy_cr6_files(station)
    
    print("\n" + "=" * 60)
    print("  FERTIG")
    print("=" * 60)

if __name__ == "__main__":
    main()


