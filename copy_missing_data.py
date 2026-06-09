#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kopiert fehlende Rohdaten von /Volumes/DATA_GHANA nach ~/Data/{station}/raw/
Prüft Zeiträume und kopiert nur wenn neue Daten vorhanden sind.
"""

import pandas as pd
import os
from pathlib import Path
from datetime import datetime
import shutil

# Konfiguration
SOURCE_BASE = Path("/Volumes/DATA_GHANA")
DEST_BASE = Path.home() / "Data"
STATIONS = ["Kayoro", "Gorigo", "Nazinga"]

def get_time_range_from_file(filepath):
    """Liest die Zeiträume aus einer TOA5-Datei."""
    try:
        # TOA5 Format: Header in Zeilen 0-3, Daten ab Zeile 4
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            if len(lines) < 5:
                return None, None
            
            # Suche nach TIMESTAMP Spalte
            header_line = lines[1].strip()
            if 'TIMESTAMP' not in header_line:
                return None, None
            
            # Parse Daten
            timestamps = []
            for line in lines[4:]:  # Überspringe Header
                if not line.strip() or line.startswith('"'):
                    continue
                try:
                    parts = line.split(',')
                    if len(parts) > 0:
                        ts_str = parts[0].strip('"')
                        if ts_str and ts_str != 'NAN' and 'TIMESTAMP' not in ts_str:
                            try:
                                ts = pd.to_datetime(ts_str)
                                timestamps.append(ts)
                            except:
                                continue
                except:
                    continue
            
            if not timestamps:
                return None, None
            
            return min(timestamps), max(timestamps)
    except Exception as e:
        print(f"  Fehler beim Lesen von {filepath}: {e}")
        return None, None

def get_existing_time_ranges(dest_dir, filename_pattern):
    """Sammelt alle Zeiträume aus vorhandenen Dateien."""
    time_ranges = []
    if not dest_dir.exists():
        return time_ranges
    
    for file in dest_dir.glob(f"*{filename_pattern}*"):
        if file.suffix == '.dat' or file.suffix == '.csv':
            start, end = get_time_range_from_file(file)
            if start and end:
                time_ranges.append((start, end, file.name))
    
    return time_ranges

def has_new_data(src_file, existing_ranges):
    """Prüft ob die Quelldatei neue Zeiträume enthält."""
    src_start, src_end = get_time_range_from_file(src_file)
    if not src_start or not src_end:
        return False
    
    # Prüfe ob dieser Zeitraum bereits abgedeckt ist
    for exist_start, exist_end, _ in existing_ranges:
        if exist_start <= src_start <= exist_end and exist_start <= src_end <= exist_end:
            return False  # Vollständig abgedeckt
    
    return True  # Enthält neue Daten

def find_and_copy_files():
    """Findet und kopiert fehlende Dateien."""
    for station in STATIONS:
        print(f"\n{'='*60}")
        print(f"Station: {station}")
        print(f"{'='*60}")
        
        dest_dir = DEST_BASE / station / "raw"
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        # Finde alle relevanten Dateien in DATA_GHANA
        source_files = []
        for pattern in [f"*{station}*", f"*{station.upper()}*", f"*{station.lower()}*"]:
            for file in SOURCE_BASE.rglob(pattern):
                if file.is_file() and (file.suffix == '.dat' or file.suffix == '.csv'):
                    # Überspringe Poldi_data
                    if 'Poldi_data' in str(file):
                        continue
                    # Überspringe ._ Dateien
                    if file.name.startswith('._'):
                        continue
                    source_files.append(file)
        
        print(f"Gefundene Dateien: {len(source_files)}")
        
        # Gruppiere nach Dateityp
        file_groups = {}
        for file in source_files:
            # Identifiziere Dateityp aus Namen
            name = file.name.lower()
            if 'smt' in name or 'soil' in name:
                key = 'smt'
            elif 'radiation' in name or 'rad' in name:
                key = 'radiation'
            elif 'cr1000' in name:
                key = 'cr1000'
            elif 'cr3000' in name:
                key = 'cr3000'
            elif 'public' in name:
                key = 'public'
            else:
                key = 'other'
            
            if key not in file_groups:
                file_groups[key] = []
            file_groups[key].append(file)
        
        # Kopiere Dateien
        copied_count = 0
        skipped_count = 0
        
        for file_type, files in file_groups.items():
            print(f"\n  Dateityp: {file_type} ({len(files)} Dateien)")
            
            # Sammle vorhandene Zeiträume für diesen Typ
            existing_ranges = get_existing_time_ranges(dest_dir, file_type)
            
            for src_file in files:
                # Prüfe ob Datei bereits existiert
                dest_file = dest_dir / src_file.name
                
                if dest_file.exists():
                    # Vergleiche Größe und Datum
                    src_size = src_file.stat().st_size
                    src_mtime = src_file.stat().st_mtime
                    dest_size = dest_file.stat().st_size
                    dest_mtime = dest_file.stat().st_mtime
                    
                    if src_size > dest_size or src_mtime > dest_mtime:
                        # Prüfe ob neue Daten vorhanden sind
                        if has_new_data(src_file, existing_ranges):
                            print(f"    UPDATE: {src_file.name} (neue Daten oder neuer)")
                            shutil.copy2(src_file, dest_file)
                            copied_count += 1
                            # Aktualisiere Zeiträume
                            start, end = get_time_range_from_file(dest_file)
                            if start and end:
                                existing_ranges.append((start, end, dest_file.name))
                        else:
                            print(f"    SKIP: {src_file.name} (bereits vorhanden)")
                            skipped_count += 1
                    else:
                        print(f"    SKIP: {src_file.name} (bereits vorhanden)")
                        skipped_count += 1
                else:
                    # Neue Datei - kopiere
                    print(f"    COPY: {src_file.name}")
                    shutil.copy2(src_file, dest_file)
                    copied_count += 1
                    # Aktualisiere Zeiträume
                    start, end = get_time_range_from_file(dest_file)
                    if start and end:
                        existing_ranges.append((start, end, dest_file.name))
        
        print(f"\n  Zusammenfassung für {station}:")
        print(f"    Kopiert: {copied_count}")
        print(f"    Übersprungen: {skipped_count}")

if __name__ == "__main__":
    print("Suche nach fehlenden Rohdaten in /Volumes/DATA_GHANA...")
    find_and_copy_files()
    print("\nFertig!")


