#!/usr/bin/env python3
"""
Analysiert EddyPro-Konfiguration und findet heraus, warum keine Daten gefunden werden.
"""

import re
from pathlib import Path
from datetime import datetime
import glob


def find_eddypro_files(base_dir: Path):
    """Findet EddyPro-Konfigurationsdateien."""
    patterns = [
        "*.metadata",
        "*.eddypro",
        "*metadata*",
        "*eddypro*",
        "*.ini",
        "*.cfg",
        "*.conf"
    ]
    
    found_files = []
    for pattern in patterns:
        found_files.extend(base_dir.rglob(pattern))
    
    return found_files


def parse_metadata_file(file_path: Path):
    """Liest und analysiert eine EddyPro Metadata-Datei."""
    print(f"\n{'='*60}")
    print(f"📄 Analysiere: {file_path.name}")
    print(f"{'='*60}")
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Suche nach wichtigen Konfigurationen
        patterns = {
            'file_name_mask': r'file_name_mask\s*=\s*(.+)',
            'file_path': r'file_path\s*=\s*(.+)',
            'data_path': r'data_path\s*=\s*(.+)',
            'raw_data_path': r'raw_data_path\s*=\s*(.+)',
            'file_prototype': r'file_prototype\s*=\s*(.+)',
            'file_template': r'file_template\s*=\s*(.+)',
            'date_format': r'date_format\s*=\s*(.+)',
            'time_format': r'time_format\s*=\s*(.+)',
            'start_date': r'start_date\s*=\s*(.+)',
            'end_date': r'end_date\s*=\s*(.+)',
        }
        
        found_config = {}
        for key, pattern in patterns.items():
            match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
            if match:
                found_config[key] = match.group(1).strip()
        
        if found_config:
            print("\n🔍 Gefundene Konfigurationen:")
            for key, value in found_config.items():
                print(f"  {key}: {value}")
        else:
            print("\n⚠️ Keine Standard-Konfigurationen gefunden")
            # Zeige erste 20 Zeilen
            lines = content.split('\n')[:20]
            print("\nErste Zeilen der Datei:")
            for i, line in enumerate(lines, 1):
                print(f"  {i:3d}: {line[:80]}")
        
        return found_config, content
        
    except Exception as e:
        print(f"❌ Fehler beim Lesen: {e}")
        return {}, ""


def analyze_filename_pattern(expected_pattern: str, actual_files: list):
    """Analysiert ob die tatsächlichen Dateinamen dem erwarteten Muster entsprechen."""
    print(f"\n{'='*60}")
    print("📋 Dateinamen-Analyse")
    print(f"{'='*60}")
    
    if not actual_files:
        print("⚠️ Keine Dateien gefunden zum Vergleich")
        return
    
    print(f"\nErwartetes Muster: {expected_pattern}")
    print(f"\nTatsächliche Dateien (erste 10):")
    for i, file_path in enumerate(actual_files[:10], 1):
        print(f"  {i:2d}. {file_path.name}")
    
    # Versuche Datum aus Dateinamen zu extrahieren
    print("\n📅 Datumsanalyse der Dateinamen:")
    date_patterns = [
        r'(\d{4})-(\d{2})-(\d{2})',  # YYYY-MM-DD
        r'(\d{2})(\d{3})',  # YY_DOY (z.B. 23_178)
        r'(\d{4})(\d{2})(\d{2})',  # YYYYMMDD
    ]
    
    dates_found = []
    for file_path in actual_files[:20]:
        for pattern in date_patterns:
            match = re.search(pattern, file_path.name)
            if match:
                dates_found.append((file_path.name, match.groups()))
                break
    
    if dates_found:
        print("\nGefundene Datumsmuster:")
        for filename, groups in dates_found[:10]:
            print(f"  {filename}: {groups}")


def check_data_files(data_dir: Path, expected_dates: list):
    """Prüft ob Dateien für erwartete Daten vorhanden sind."""
    print(f"\n{'='*60}")
    print("🔍 Prüfe Verfügbarkeit von Daten")
    print(f"{'='*60}")
    
    if not data_dir.exists():
        print(f"❌ Verzeichnis existiert nicht: {data_dir}")
        return
    
    # Finde alle .dat Dateien
    dat_files = list(data_dir.glob("*.dat"))
    print(f"\nGefundene .dat Dateien: {len(dat_files)}")
    
    if dat_files:
        print("\nBeispiel-Dateinamen:")
        for f in dat_files[:10]:
            print(f"  {f.name}")
    
    # Prüfe für jedes erwartete Datum
    print(f"\n📅 Prüfe für erwartete Daten:")
    for date_str in expected_dates[:5]:  # Nur erste 5
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            year_short = dt.strftime('%y')
            day_of_year = dt.strftime('%j')
            
            # Verschiedene mögliche Namensmuster
            patterns = [
                f"*{year_short}_{day_of_year}_*.dat",  # Jan_23_178_1200.dat
                f"*{dt.strftime('%Y-%m-%d')}*.dat",  # 2023-06-27_1200.dat
                f"*{dt.strftime('%Y%m%d')}*.dat",  # 20230627_1200.dat
            ]
            
            found = False
            for pattern in patterns:
                matches = list(data_dir.glob(pattern))
                if matches:
                    print(f"  ✓ {date_str}: {len(matches)} Dateien gefunden (Pattern: {pattern})")
                    found = True
                    break
            
            if not found:
                print(f"  ✗ {date_str}: Keine Dateien gefunden")
        
        except Exception as e:
            print(f"  ⚠️ {date_str}: Fehler - {e}")


def main():
    """Hauptfunktion."""
    print("=" * 60)
    print("EddyPro Datenanalyse")
    print("=" * 60)
    
    # Frage nach Basis-Verzeichnis
    base_dir_str = input("\n📁 Pfad zum Basis-Verzeichnis (wo EddyPro-Dateien sind): ").strip()
    if not base_dir_str:
        base_dir_str = "/Volumes/DATA_GHANA"
    
    base_dir = Path(base_dir_str)
    
    if not base_dir.exists():
        print(f"❌ Verzeichnis existiert nicht: {base_dir}")
        return
    
    # Frage nach Daten-Verzeichnis
    data_dir_str = input("📁 Pfad zum Daten-Verzeichnis (wo .dat Dateien sind): ").strip()
    if not data_dir_str:
        data_dir_str = "/Volumes/DATA_GHANA/ghana/janga/micromet/raw/fast-response/Turbulence"
    
    data_dir = Path(data_dir_str)
    
    # Finde EddyPro-Dateien
    print(f"\n🔍 Suche EddyPro-Konfigurationsdateien in: {base_dir}")
    eddypro_files = find_eddypro_files(base_dir)
    
    if not eddypro_files:
        print("⚠️ Keine EddyPro-Konfigurationsdateien gefunden")
        print("\nSuche manuell nach:")
        print("  - *.metadata")
        print("  - *.eddypro")
        print("  - *.ini")
    else:
        print(f"✅ Gefunden: {len(eddypro_files)} Dateien")
        for f in eddypro_files[:10]:
            print(f"  - {f}")
    
    # Analysiere gefundene Dateien
    all_configs = {}
    for file_path in eddypro_files[:5]:  # Analysiere erste 5
        config, content = parse_metadata_file(file_path)
        if config:
            all_configs[file_path.name] = config
    
    # Prüfe Daten-Verzeichnis
    expected_dates = [
        "2025-06-27", "2025-06-28", "2025-06-29"
    ]
    
    check_data_files(data_dir, expected_dates)
    
    # Zusammenfassung
    print(f"\n{'='*60}")
    print("📊 Zusammenfassung")
    print(f"{'='*60}")
    
    if all_configs:
        print("\nGefundene Konfigurationen:")
        for filename, config in all_configs.items():
            print(f"\n{filename}:")
            for key, value in config.items():
                print(f"  {key}: {value}")
    
    print("\n💡 Mögliche Probleme:")
    print("  1. Dateinamen-Muster stimmt nicht überein")
    print("  2. Datum in Dateinamen ist falsch (2025 vs 2023/2022)")
    print("  3. Pfad zu Daten ist falsch konfiguriert")
    print("  4. Datumsformat stimmt nicht überein")


if __name__ == "__main__":
    main()


