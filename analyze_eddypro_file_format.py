#!/usr/bin/env python3
"""
Analysiert das Format der EddyPro-Dateien und die Metadata-Konfiguration.
"""

from pathlib import Path
import re


def analyze_file_format():
    """Analysiert das Format einer Beispiel-Datei."""
    data_dir = Path("/Volumes/Data/WASCAL_5_MOLE/Turbulence_eddypro")
    
    # Prüfe Beispiel-Datei
    example_file = data_dir / "Mol_25_001_0000.dat"
    
    if not example_file.exists():
        print(f"❌ Beispiel-Datei nicht gefunden: {example_file}")
        return
    
    print("=" * 70)
    print("Datei-Format Analyse")
    print("=" * 70)
    
    # Lese Datei
    with open(example_file, 'r') as f:
        lines = f.readlines()
    
    print(f"\n📄 Datei: {example_file.name}")
    print(f"  Anzahl Zeilen: {len(lines)}")
    
    # Prüfe erste Zeilen
    print(f"\n📋 Erste 5 Zeilen:")
    for i, line in enumerate(lines[:5], 1):
        values = line.strip().split(',')
        print(f"  Zeile {i}: {len(values)} Spalten")
        print(f"    Werte: {values[:5]}...")
    
    # Prüfe ob Timestamp vorhanden
    first_line = lines[0].strip()
    first_values = first_line.split(',')
    
    # Versuche zu erkennen ob erste Spalte ein Timestamp ist
    first_val = first_values[0] if first_values else ""
    has_timestamp = False
    
    # Prüfe verschiedene Timestamp-Formate
    timestamp_patterns = [
        r'\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}',  # 2025-01-01 00:00:00
        r'\d{2}/\d{2}/\d{4}',  # 01/01/2025
        r'\d{10}',  # Unix timestamp
    ]
    
    for pattern in timestamp_patterns:
        if re.match(pattern, first_val):
            has_timestamp = True
            print(f"\n✓ Timestamp erkannt in erster Spalte: {first_val}")
            break
    
    if not has_timestamp:
        print(f"\n⚠️ KEIN Timestamp in erster Spalte erkannt")
        print(f"   Erster Wert: {first_val}")
        print(f"   → EddyPro muss Timestamp aus Dateinamen extrahieren")
    
    # Berechne Datenmenge
    # Bei 10 Hz sollten 30 Minuten = 18000 Zeilen sein
    expected_lines_30min = 10 * 60 * 30  # 18000
    expected_lines_3min = 10 * 60 * 3    # 1800
    
    print(f"\n📊 Datenmenge-Analyse:")
    print(f"  Zeilen in Datei: {len(lines)}")
    print(f"  Erwartet für 30 Min (10 Hz): {expected_lines_30min}")
    print(f"  Erwartet für 3 Min (10 Hz): {expected_lines_3min}")
    
    if len(lines) == expected_lines_3min:
        print(f"  ⚠️ PROBLEM: Datei enthält nur ~3 Minuten Daten!")
        print(f"     EddyPro erwartet 30 Minuten für einen Averaging-Intervall")
    elif len(lines) == expected_lines_30min:
        print(f"  ✓ Datei enthält ~30 Minuten Daten")
    else:
        duration_min = len(lines) / (10 * 60)
        print(f"  ⚠️ Datei enthält ~{duration_min:.1f} Minuten Daten")
    
    # Prüfe Metadata-Konfiguration
    metadata_file = Path.home() / "Data" / "Mole.metadata"
    
    if metadata_file.exists():
        print(f"\n📋 Metadata-Konfiguration:")
        with open(metadata_file, 'r') as f:
            metadata_content = f.read()
        
        # Suche wichtige Einstellungen
        header_rows = re.search(r'header_rows=(\d+)', metadata_content)
        timestamp_setting = re.search(r'timestamp=(\d+)', metadata_content)
        separator = re.search(r'separator=(\w+)', metadata_content)
        
        if header_rows:
            print(f"  header_rows: {header_rows.group(1)}")
        if timestamp_setting:
            ts_val = timestamp_setting.group(1)
            print(f"  timestamp: {ts_val}")
            if ts_val == "0":
                print(f"    → Timestamp wird aus Dateinamen extrahiert")
            else:
                print(f"    → Timestamp ist in Spalte {ts_val}")
        if separator:
            print(f"  separator: {separator.group(1)}")
    
    # Prüfe file_prototype
    eddypro_file = Path.home() / "Data" / "Mole.eddypro"
    if eddypro_file.exists():
        with open(eddypro_file, 'r') as f:
            eddypro_content = f.read()
        
        file_prototype = re.search(r'file_prototype=(.+)', eddypro_content)
        if file_prototype:
            print(f"\n📋 EddyPro file_prototype: {file_prototype.group(1)}")
            print(f"   Dateiname: {example_file.name}")
            
            # Prüfe ob Pattern passt
            pattern = file_prototype.group(1)
            # Konvertiere Pattern zu Regex
            regex_pattern = pattern.replace('yy', r'\d{2}').replace('ddd', r'\d{3}').replace('HHMM', r'\d{4}')
            
            if re.match(regex_pattern, example_file.name):
                print(f"   ✓ Pattern passt zu Dateinamen")
            else:
                print(f"   ✗ Pattern passt NICHT zu Dateinamen!")
    
    # Zusammenfassung
    print(f"\n{'='*70}")
    print("📋 ZUSAMMENFASSUNG")
    print(f"{'='*70}")
    
    if len(lines) < expected_lines_30min:
        print(f"\n❌ HAUPTPROBLEM:")
        print(f"   Die Dateien enthalten zu wenig Daten!")
        print(f"   - Datei hat: {len(lines)} Zeilen (~{len(lines)/(10*60):.1f} Minuten)")
        print(f"   - EddyPro braucht: {expected_lines_30min} Zeilen (30 Minuten)")
        print(f"   - Fehlend: {expected_lines_30min - len(lines)} Zeilen")
        print(f"\n💡 LÖSUNG:")
        print(f"   1. Die Dateien müssen 30 Minuten Daten enthalten")
        print(f"   2. Bei 10 Hz = 18000 Zeilen pro Datei")
        print(f"   3. Aktuell haben die Dateien nur ~3 Minuten Daten")
        print(f"   4. Möglicherweise wurden die Dateien falsch aufgeteilt")


if __name__ == "__main__":
    analyze_file_format()


