#!/usr/bin/env python3
"""
Prüft die EddyPro Metadata-Konfiguration auf Probleme.
"""

from pathlib import Path
import re


def check_metadata_config():
    """Prüft die Metadata-Konfiguration."""
    print("=" * 70)
    print("EddyPro Metadata-Konfiguration Prüfung")
    print("=" * 70)
    
    metadata_file = Path.home() / "Data" / "Mole.metadata"
    data_dir = Path("/Volumes/Data/WASCAL_5_MOLE/Turbulence_eddypro")
    example_file = data_dir / "Mol_25_001_0000.dat"
    
    if not metadata_file.exists():
        print(f"❌ Metadata-Datei nicht gefunden: {metadata_file}")
        return
    
    # Lese Metadata
    with open(metadata_file, 'r') as f:
        metadata_content = f.read()
    
    # Extrahiere wichtige Einstellungen
    print("\n📋 Metadata-Konfiguration:")
    
    # Timing
    acquisition_frequency = re.search(r'acquisition_frequency=([\d.]+)', metadata_content)
    file_duration = re.search(r'file_duration=(\d+)', metadata_content)
    
    if acquisition_frequency:
        freq = float(acquisition_frequency.group(1))
        print(f"  acquisition_frequency: {freq} Hz")
    if file_duration:
        duration = int(file_duration.group(1))
        print(f"  file_duration: {duration} Minuten")
    
    # File settings
    header_rows = re.search(r'header_rows=(\d+)', metadata_content)
    timestamp = re.search(r'timestamp=(\d+)', metadata_content)
    separator = re.search(r'separator=(\w+)', metadata_content)
    
    print(f"\n📄 Datei-Einstellungen:")
    if header_rows:
        print(f"  header_rows: {header_rows.group(1)}")
    if timestamp:
        ts_val = timestamp.group(1)
        print(f"  timestamp: {ts_val}")
        if ts_val == "0":
            print(f"    → Timestamp wird aus Dateinamen extrahiert")
        else:
            print(f"    → Timestamp ist in Spalte {ts_val}")
    if separator:
        print(f"  separator: {separator.group(1)}")
    
    # Prüfe Beispiel-Datei
    if example_file.exists():
        with open(example_file, 'r') as f:
            lines = f.readlines()
        
        print(f"\n📊 Beispiel-Datei: {example_file.name}")
        print(f"  Zeilen: {len(lines)}")
        
        # Berechne erwartete Zeilen
        if acquisition_frequency and file_duration:
            freq = float(acquisition_frequency.group(1))
            duration = int(file_duration.group(1))
            expected_lines = int(freq * 60 * duration)
            print(f"  Erwartet bei {freq} Hz für {duration} Min: {expected_lines} Zeilen")
            
            if len(lines) == expected_lines:
                print(f"  ✓ Dateigröße stimmt überein!")
            else:
                diff = len(lines) - expected_lines
                actual_duration = len(lines) / (freq * 60)
                print(f"  ⚠️ Abweichung: {diff:+d} Zeilen")
                print(f"     Tatsächliche Dauer: ~{actual_duration:.1f} Minuten")
                
                # Prüfe ob Frequenz falsch ist
                if len(lines) == 1800:
                    # Bei 1800 Zeilen für 30 Minuten
                    calculated_freq = len(lines) / (duration * 60)
                    print(f"\n  💡 Mögliche Lösung:")
                    print(f"     Wenn Datei wirklich 30 Minuten enthält:")
                    print(f"     acquisition_frequency sollte sein: {calculated_freq:.1f} Hz")
                    print(f"     Aktuell konfiguriert: {freq} Hz")
    
    # Prüfe Spalten-Konfiguration
    print(f"\n📋 Spalten-Konfiguration:")
    col_vars = {}
    for i in range(1, 19):
        var_match = re.search(rf'col_{i}_variable=(\S+)', metadata_content)
        if var_match:
            var = var_match.group(1)
            if var != 'ignore':
                col_vars[i] = var
    
    print(f"  Konfigurierte Variablen: {len(col_vars)}")
    for col, var in sorted(col_vars.items()):
        print(f"    Spalte {col}: {var}")
    
    # Prüfe ob alle Spalten konfiguriert sind
    if example_file.exists():
        with open(example_file, 'r') as f:
            first_line = f.readline()
            num_cols = len(first_line.strip().split(','))
        
        print(f"\n  Spalten in Datei: {num_cols}")
        print(f"  Konfigurierte Spalten: {max(col_vars.keys()) if col_vars else 0}")
        
        if num_cols != max(col_vars.keys()) if col_vars else 0:
            print(f"  ⚠️ WARNUNG: Spaltenanzahl stimmt nicht überein!")
            print(f"     Datei hat {num_cols} Spalten, aber nur bis Spalte {max(col_vars.keys()) if col_vars else 0} konfiguriert")
    
    # Zusammenfassung
    print(f"\n{'='*70}")
    print("📋 ZUSAMMENFASSUNG")
    print(f"{'='*70}")
    
    if example_file.exists():
        with open(example_file, 'r') as f:
            lines = f.readlines()
        
        if acquisition_frequency and file_duration:
            freq = float(acquisition_frequency.group(1))
            duration = int(file_duration.group(1))
            expected_lines = int(freq * 60 * duration)
            
            if len(lines) != expected_lines:
                print(f"\n❌ PROBLEM GEFUNDEN:")
                print(f"   Dateigröße stimmt nicht mit Konfiguration überein!")
                print(f"   - Datei hat: {len(lines)} Zeilen")
                print(f"   - Erwartet bei {freq} Hz für {duration} Min: {expected_lines} Zeilen")
                print(f"\n💡 MÖGLICHE LÖSUNGEN:")
                if len(lines) == 1800:
                    correct_freq = len(lines) / (duration * 60)
                    print(f"   1. Ändere acquisition_frequency von {freq} Hz auf {correct_freq:.1f} Hz")
                    print(f"      (wenn Datei wirklich {duration} Minuten enthält)")
                else:
                    actual_duration = len(lines) / (freq * 60)
                    print(f"   1. Ändere file_duration von {duration} Min auf {actual_duration:.1f} Min")
                    print(f"      (wenn Frequenz {freq} Hz korrekt ist)")


if __name__ == "__main__":
    check_metadata_config()


