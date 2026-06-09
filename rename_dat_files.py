#!/usr/bin/env python3
"""
Benennt .dat Dateien um: Y#####_##.dat → Y#####_##00.dat

Verwendung:
    python rename_dat_files.py <ordner_pfad>
    python rename_dat_files.py /Users/hingerl-l/Data/Gorigo/processed --dry-run
"""

import sys
import re
from pathlib import Path


def rename_dat_files(directory: Path, dry_run: bool = False):
    """
    Benennt .dat Dateien um: Y#####_##.dat → Y#####_##00.dat
    
    Args:
        directory: Ordnerpfad
        dry_run: Wenn True, werden keine Änderungen vorgenommen, nur angezeigt
    """
    if not directory.exists():
        print(f"❌ Ordner existiert nicht: {directory}")
        return
    
    if not directory.is_dir():
        print(f"❌ Kein Ordner: {directory}")
        return
    
    print(f"📁 Verarbeite Ordner: {directory}")
    if dry_run:
        print("   [DRY RUN Modus - keine Änderungen werden vorgenommen]")
    print()
    
    # Finde alle .dat Dateien
    dat_files = list(directory.glob("*.dat"))
    
    if not dat_files:
        print("  ⚠️ Keine .dat Dateien gefunden")
        return
    
    print(f"  Gefunden: {len(dat_files)} .dat Dateien")
    print()
    
    # Pattern: Y#####_##.dat
    pattern = re.compile(r'^(Y\d+_\d+)\.dat$')
    
    renamed_count = 0
    skipped_count = 0
    
    for file_path in sorted(dat_files):
        match = pattern.match(file_path.name)
        
        if match:
            # Extrahiere den Basisnamen (z.B. "Y13318_17")
            base_name = match.group(1)
            
            # Neuer Name: Basisname + "00.dat"
            new_name = f"{base_name}00.dat"
            new_path = file_path.parent / new_name
            
            # Prüfe ob Ziel bereits existiert
            if new_path.exists() and new_path != file_path:
                print(f"  ⚠️ Übersprungen: {file_path.name} → {new_name} (Ziel existiert bereits)")
                skipped_count += 1
                continue
            
            if dry_run:
                print(f"  [DRY RUN] {file_path.name} → {new_name}")
            else:
                try:
                    file_path.rename(new_path)
                    print(f"  ✓ {file_path.name} → {new_name}")
                except Exception as e:
                    print(f"  ⚠️ Fehler bei {file_path.name}: {e}")
                    skipped_count += 1
                    continue
            
            renamed_count += 1
        else:
            print(f"  ⚠️ Übersprungen: {file_path.name} (passt nicht zum Muster Y#####_##.dat)")
            skipped_count += 1
    
    print()
    if dry_run:
        print(f"📊 [DRY RUN] {renamed_count} Dateien würden umbenannt werden")
        if skipped_count > 0:
            print(f"   {skipped_count} Dateien würden übersprungen")
    else:
        print(f"✅ {renamed_count} Dateien wurden umbenannt")
        if skipped_count > 0:
            print(f"   {skipped_count} Dateien wurden übersprungen")


def main():
    """Hauptfunktion."""
    if len(sys.argv) < 2:
        print("Verwendung: python rename_dat_files.py <ordner_pfad> [--dry-run]")
        print("\nBeispiele:")
        print("  python rename_dat_files.py /Users/hingerl-l/Data/Gorigo/processed")
        print("  python rename_dat_files.py /Users/hingerl-l/Data/Gorigo/processed --dry-run")
        sys.exit(1)
    
    directory = Path(sys.argv[1])
    dry_run = '--dry-run' in sys.argv
    
    rename_dat_files(directory, dry_run=dry_run)


if __name__ == "__main__":
    main()
