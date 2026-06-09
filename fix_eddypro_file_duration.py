#!/usr/bin/env python3
"""
Analysiert ob Dateien kombiniert werden müssen oder ob das Problem woanders liegt.
"""

from pathlib import Path
from collections import defaultdict


def analyze_file_structure():
    """Analysiert die Dateistruktur."""
    data_dir = Path("/Volumes/Data/WASCAL_5_MOLE/Turbulence_eddypro")
    
    print("=" * 70)
    print("Datei-Struktur Analyse")
    print("=" * 70)
    
    # Gruppiere Dateien nach Tag
    files_by_day = defaultdict(list)
    
    for file_path in sorted(data_dir.glob("Mol_25_001_*.dat")):
        # Extrahiere Zeit aus Dateinamen
        match = re.match(r'Mol_25_001_(\d{4})\.dat', file_path.name)
        if match:
            time_str = match.group(1)
            files_by_day[time_str].append(file_path)
    
    # Prüfe erste 10 Zeitpunkte
    print(f"\n📅 Dateien für Tag 001 (2025-01-01):")
    
    all_files = sorted(data_dir.glob("Mol_25_001_*.dat"))
    print(f"  Gesamt: {len(all_files)} Dateien")
    
    # Zeige erste 20
    print(f"\n  Erste 20 Dateien:")
    for i, f in enumerate(all_files[:20], 1):
        print(f"    {i:2d}. {f.name}")
    
    # Prüfe ob es genug Dateien für 30 Minuten gibt
    # Bei 3 Minuten pro Datei brauchen wir 10 Dateien für 30 Minuten
    print(f"\n📊 Analyse:")
    print(f"  - Jede Datei: ~3 Minuten")
    print(f"  - Für 30 Minuten braucht EddyPro: 10 Dateien")
    print(f"  - Verfügbare Dateien für Tag 001: {len(all_files)}")
    
    if len(all_files) >= 10:
        print(f"  ✓ Genug Dateien vorhanden!")
        print(f"\n💡 PROBLEM:")
        print(f"     EddyPro kann mehrere kleine Dateien NICHT automatisch kombinieren!")
        print(f"     Es erwartet EINE Datei mit 30 Minuten Daten")
        print(f"\n🔧 LÖSUNG:")
        print(f"     Die 3-Minuten-Dateien müssen zu 30-Minuten-Dateien kombiniert werden")
        print(f"     z.B. alle Dateien von 0000-0029 → eine Datei für 00:00-00:30")
    else:
        print(f"  ✗ Nicht genug Dateien!")
    
    # Prüfe Metadata-Einstellung für file_duration
    metadata_file = Path.home() / "Data" / "Mole.metadata"
    if metadata_file.exists():
        with open(metadata_file, 'r') as f:
            content = f.read()
        
        file_duration = re.search(r'file_duration=(\d+)', content)
        if file_duration:
            print(f"\n📋 Metadata file_duration: {file_duration.group(1)} Minuten")
            if file_duration.group(1) != "30":
                print(f"  ⚠️ WARNUNG: file_duration ist nicht 30!")
                print(f"     EddyPro erwartet 30-Minuten-Dateien")


if __name__ == "__main__":
    import re
    analyze_file_structure()


