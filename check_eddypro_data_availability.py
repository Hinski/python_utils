#!/usr/bin/env python3
"""
Prüft welche Daten für EddyPro verfügbar sind und vergleicht mit erwarteten Daten.
"""

from pathlib import Path
from datetime import datetime, timedelta
import re


def extract_date_from_filename(filename: str):
    """Extrahiert Datum aus verschiedenen Dateinamen-Formaten."""
    patterns = [
        # Jan_23_178_1200.dat (YY_DOY_HHMM)
        (r'(\w+)_(\d{2})_(\d{3})_(\d{4})\.dat', lambda m: {
            'format': 'YY_DOY_HHMM',
            'station': m.group(1),
            'year': int('20' + m.group(2)),
            'doy': int(m.group(3)),
            'time': m.group(4)
        }),
        # 2023-06-27_1200.dat
        (r'(\d{4})-(\d{2})-(\d{2})_(\d{4})\.dat', lambda m: {
            'format': 'YYYY-MM-DD_HHMM',
            'year': int(m.group(1)),
            'month': int(m.group(2)),
            'day': int(m.group(3)),
            'time': m.group(4)
        }),
        # 20230627_1200.dat
        (r'(\d{4})(\d{2})(\d{2})_(\d{4})\.dat', lambda m: {
            'format': 'YYYYMMDD_HHMM',
            'year': int(m.group(1)),
            'month': int(m.group(2)),
            'day': int(m.group(3)),
            'time': m.group(4)
        }),
    ]
    
    for pattern, parser in patterns:
        match = re.match(pattern, filename, re.IGNORECASE)
        if match:
            info = parser(match)
            # Konvertiere zu datetime wenn möglich
            try:
                if 'doy' in info:
                    dt = datetime(info['year'], 1, 1) + timedelta(days=info['doy'] - 1)
                    info['datetime'] = dt
                elif 'month' in info:
                    info['datetime'] = datetime(info['year'], info['month'], info['day'])
            except:
                pass
            return info
    
    return None


def analyze_data_directory(data_dir: Path):
    """Analysiert alle Dateien in einem Verzeichnis."""
    if not data_dir.exists():
        print(f"❌ Verzeichnis existiert nicht: {data_dir}")
        return None
    
    dat_files = sorted(data_dir.glob("*.dat"))
    
    if not dat_files:
        print(f"⚠️ Keine .dat Dateien gefunden in: {data_dir}")
        return None
    
    print(f"\n📁 Gefundene Dateien: {len(dat_files)}")
    
    # Analysiere Dateinamen
    file_info = []
    for file_path in dat_files:
        info = extract_date_from_filename(file_path.name)
        if info:
            info['filename'] = file_path.name
            info['path'] = file_path
            file_info.append(info)
    
    if not file_info:
        print("⚠️ Konnte keine Datumsinformationen aus Dateinamen extrahieren")
        print("\nBeispiel-Dateinamen:")
        for f in dat_files[:10]:
            print(f"  {f.name}")
        return None
    
    # Gruppiere nach Format
    formats = {}
    for info in file_info:
        fmt = info['format']
        if fmt not in formats:
            formats[fmt] = []
        formats[fmt].append(info)
    
    print(f"\n📋 Dateinamen-Formate gefunden:")
    for fmt, files in formats.items():
        print(f"  {fmt}: {len(files)} Dateien")
        if files:
            print(f"    Beispiel: {files[0]['filename']}")
    
    # Finde Datumsbereich
    dates_with_dt = [info for info in file_info if 'datetime' in info]
    if dates_with_dt:
        min_date = min(info['datetime'] for info in dates_with_dt)
        max_date = max(info['datetime'] for info in dates_with_dt)
        print(f"\n📅 Datumsbereich:")
        print(f"  Von: {min_date.strftime('%Y-%m-%d')}")
        print(f"  Bis: {max_date.strftime('%Y-%m-%d')}")
    
    return file_info


def check_expected_dates(file_info: list, expected_dates: list):
    """Prüft ob Dateien für erwartete Daten vorhanden sind."""
    print(f"\n{'='*60}")
    print("🔍 Prüfe Verfügbarkeit für erwartete Daten")
    print(f"{'='*60}")
    
    if not file_info:
        return
    
    # Erstelle Lookup nach Datum
    date_lookup = {}
    for info in file_info:
        if 'datetime' in info:
            date_key = info['datetime'].date()
            if date_key not in date_lookup:
                date_lookup[date_key] = []
            date_lookup[date_key].append(info)
    
    # Prüfe erwartete Daten
    found_count = 0
    missing_count = 0
    
    for date_str in expected_dates:
        try:
            expected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            
            if expected_date in date_lookup:
                files = date_lookup[expected_date]
                print(f"  ✓ {date_str}: {len(files)} Dateien gefunden")
                found_count += 1
            else:
                print(f"  ✗ {date_str}: Keine Dateien gefunden")
                missing_count += 1
                
                # Zeige ähnliche Daten
                if date_lookup:
                    closest_date = min(date_lookup.keys(), 
                                     key=lambda d: abs((d - expected_date).days))
                    days_diff = (closest_date - expected_date).days
                    print(f"      Nächstes Datum: {closest_date} ({days_diff:+d} Tage)")
        
        except Exception as e:
            print(f"  ⚠️ {date_str}: Fehler - {e}")
    
    print(f"\n📊 Zusammenfassung:")
    print(f"  Gefunden: {found_count}/{len(expected_dates)}")
    print(f"  Fehlend: {missing_count}/{len(expected_dates)}")


def suggest_filename_format(file_info: list):
    """Schlägt das erwartete Dateinamen-Format vor."""
    print(f"\n{'='*60}")
    print("💡 Vorschlag für EddyPro-Konfiguration")
    print(f"{'='*60}")
    
    if not file_info:
        return
    
    # Finde häufigstes Format
    format_counts = {}
    for info in file_info:
        fmt = info['format']
        format_counts[fmt] = format_counts.get(fmt, 0) + 1
    
    most_common = max(format_counts.items(), key=lambda x: x[1])
    
    print(f"\nHäufigstes Format: {most_common[0]} ({most_common[1]} Dateien)")
    
    example = file_info[0]
    print(f"\nBeispiel-Dateiname: {example['filename']}")
    
    # Generiere EddyPro file_name_mask
    if example['format'] == 'YY_DOY_HHMM':
        station = example.get('station', 'XXX')
        print(f"\nEddyPro file_name_mask sollte sein:")
        print(f"  {station}_YY_DOY_HHMM.dat")
        print(f"  oder")
        print(f"  {station}_*_*_*.dat")
    elif example['format'] == 'YYYY-MM-DD_HHMM':
        print(f"\nEddyPro file_name_mask sollte sein:")
        print(f"  YYYY-MM-DD_HHMM.dat")
    elif example['format'] == 'YYYYMMDD_HHMM':
        print(f"\nEddyPro file_name_mask sollte sein:")
        print(f"  YYYYMMDD_HHMM.dat")


def main():
    """Hauptfunktion."""
    print("=" * 60)
    print("EddyPro Daten-Verfügbarkeits-Prüfung")
    print("=" * 60)
    
    # Frage nach Daten-Verzeichnis
    data_dir_str = input("\n📁 Pfad zum Daten-Verzeichnis: ").strip()
    if not data_dir_str:
        data_dir_str = "/Volumes/DATA_GHANA/ghana/janga/micromet/raw/fast-response/Turbulence"
    
    data_dir = Path(data_dir_str)
    
    # Analysiere Verzeichnis
    file_info = analyze_data_directory(data_dir)
    
    # Erwartete Daten (aus Fehlermeldung)
    expected_dates = [
        "2025-06-27", "2025-06-28", "2025-06-29"
    ]
    
    # Prüfe Verfügbarkeit
    check_expected_dates(file_info, expected_dates)
    
    # Vorschlag für Konfiguration
    suggest_filename_format(file_info)
    
    print(f"\n{'='*60}")
    print("🔧 Mögliche Lösungen:")
    print(f"{'='*60}")
    print("1. Prüfe ob das Jahr in den Dateinamen korrekt ist (2025 vs 2023)")
    print("2. Prüfe ob das file_name_mask in EddyPro korrekt konfiguriert ist")
    print("3. Prüfe ob der Pfad zu den Daten in EddyPro korrekt ist")
    print("4. Stelle sicher, dass die Dateien im richtigen Verzeichnis sind")


if __name__ == "__main__":
    main()


