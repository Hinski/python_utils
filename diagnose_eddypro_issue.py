#!/usr/bin/env python3
"""
Diagnostiziert das EddyPro-Problem basierend auf den Konfigurationsdateien.
"""

from pathlib import Path
from datetime import datetime, timedelta
import re


def analyze_eddypro_config():
    """Analysiert die EddyPro-Konfiguration."""
    print("=" * 70)
    print("EddyPro Problem-Diagnose")
    print("=" * 70)
    
    # Lese Konfigurationsdateien
    eddypro_file = Path.home() / "Data" / "Mole.eddypro"
    metadata_file = Path.home() / "Data" / "Mole.metadata"
    data_dir = Path("/Volumes/Data/WASCAL_5_MOLE/Turbulence_eddypro")
    
    print("\n📋 Konfiguration:")
    print(f"  EddyPro Datei: {eddypro_file}")
    print(f"  Metadata Datei: {metadata_file}")
    print(f"  Daten-Verzeichnis: {data_dir}")
    
    # Lese .eddypro Datei
    if not eddypro_file.exists():
        print(f"\n❌ EddyPro-Datei nicht gefunden: {eddypro_file}")
        return
    
    with open(eddypro_file, 'r') as f:
        content = f.read()
    
    # Extrahiere wichtige Einstellungen
    file_prototype = re.search(r'file_prototype=(.+)', content)
    pr_start_date = re.search(r'pr_start_date=(.+)', content)
    pr_end_date = re.search(r'pr_end_date=(.+)', content)
    data_path = re.search(r'data_path=(.+)', content)
    
    print("\n🔍 Gefundene Einstellungen:")
    if file_prototype:
        print(f"  file_prototype: {file_prototype.group(1)}")
    if pr_start_date:
        print(f"  pr_start_date: {pr_start_date.group(1)}")
    if pr_end_date:
        print(f"  pr_end_date: {pr_end_date.group(1)}")
    if data_path:
        print(f"  data_path: {data_path.group(1)}")
    
    # Prüfe Daten-Verzeichnis
    if not data_dir.exists():
        print(f"\n❌ Daten-Verzeichnis existiert nicht: {data_dir}")
        return
    
    # Finde alle Dateien
    dat_files = sorted(data_dir.glob("Mol_25_*.dat"))
    
    if not dat_files:
        print(f"\n⚠️ Keine Dateien für 2025 gefunden!")
        # Prüfe andere Jahre
        for year in [23, 24]:
            files = list(data_dir.glob(f"Mol_{year}_*.dat"))
            if files:
                print(f"  Aber {len(files)} Dateien für 20{year} gefunden")
        return
    
    print(f"\n📁 Gefundene Dateien für 2025: {len(dat_files)}")
    
    # Extrahiere Tage
    days = set()
    for f in dat_files:
        match = re.search(r'Mol_25_(\d{3})_', f.name)
        if match:
            days.add(int(match.group(1)))
    
    days_sorted = sorted(days)
    print(f"\n📅 Verfügbare Tage in 2025: {len(days_sorted)}")
    print(f"  Erster Tag: {days_sorted[0]}")
    print(f"  Letzter Tag: {days_sorted[-1]}")
    
    # Prüfe spezifische Tage (178-180 = 27.-29. Juni 2025)
    print(f"\n🔍 Prüfe erwartete Daten:")
    expected_days = [178, 179, 180]
    expected_dates = []
    for day in expected_days:
        date = datetime(2025, 1, 1) + timedelta(days=day - 1)
        expected_dates.append((day, date.strftime("%Y-%m-%d")))
        if day in days:
            files_for_day = [f for f in dat_files if f"Mol_25_{day:03d}_" in f.name]
            print(f"  ✓ Tag {day:03d} ({date.strftime('%Y-%m-%d')}): {len(files_for_day)} Dateien")
        else:
            print(f"  ✗ Tag {day:03d} ({date.strftime('%Y-%m-%d')}): KEINE DATEIEN")
    
    # Finde nächste verfügbare Daten
    print(f"\n💡 Nächste verfügbare Daten:")
    for day, date_str in expected_dates:
        if day not in days:
            # Suche nächsten verfügbaren Tag
            for check_day in range(day - 5, day + 6):
                if check_day in days:
                    check_date = datetime(2025, 1, 1) + timedelta(days=check_day - 1)
                    diff = check_day - day
                    print(f"  Tag {day:03d} fehlt → Nächster: Tag {check_day:03d} ({check_date.strftime('%Y-%m-%d')}, {diff:+d} Tage)")
                    break
    
    # Zeige Lücken
    print(f"\n📊 Datenlücken-Analyse:")
    gaps = []
    prev_day = None
    for day in days_sorted:
        if prev_day is not None and day - prev_day > 1:
            gap_start = datetime(2025, 1, 1) + timedelta(days=prev_day - 1)
            gap_end = datetime(2025, 1, 1) + timedelta(days=day - 1)
            gaps.append((prev_day, day, gap_start, gap_end))
        prev_day = day
    
    if gaps:
        print(f"  Gefundene Lücken: {len(gaps)}")
        for gap_start_day, gap_end_day, gap_start_date, gap_end_date in gaps[:10]:
            print(f"    Tag {gap_start_day:03d} → {gap_end_day:03d} ({gap_start_date.strftime('%Y-%m-%d')} bis {gap_end_date.strftime('%Y-%m-%d')})")
    else:
        print("  Keine großen Lücken gefunden")
    
    # Zusammenfassung
    print(f"\n{'='*70}")
    print("📋 ZUSAMMENFASSUNG")
    print(f"{'='*70}")
    print(f"\n❌ PROBLEM GEFUNDEN:")
    print(f"  EddyPro sucht nach Daten für:")
    for day, date_str in expected_dates:
        print(f"    - {date_str} (Tag {day:03d})")
    print(f"\n  Aber diese Daten sind NICHT vorhanden!")
    print(f"\n💡 LÖSUNG:")
    print(f"  1. Prüfe ob die Daten für diese Tage existieren sollten")
    print(f"  2. Falls ja: Stelle sicher, dass die Dateien im richtigen Verzeichnis sind")
    print(f"  3. Falls nein: Ändere pr_start_date und pr_end_date in der .eddypro Datei")
    print(f"     zu einem Zeitraum, für den Daten vorhanden sind")
    print(f"\n  Verfügbare Daten: Tag {days_sorted[0]:03d} bis {days_sorted[-1]:03d}")


if __name__ == "__main__":
    analyze_eddypro_config()


