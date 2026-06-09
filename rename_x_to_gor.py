#!/usr/bin/env python3
"""
Benennt Dateien um: Zyyddd_HH.dat oder Zyyddd_HH_2.dat → naz_yy_ddd_HHMM.dat

Beispiele:
    Z14159_09.dat → naz_14_159_0900.dat
    Z14159_09_2.dat → naz_14_159_0900.dat
    Z14349_00_2.dat → naz_14_349_0000.dat

Verwendung:
    python rename_x_to_gor.py <ordner_pfad>
    python rename_x_to_gor.py /Volumes/Data/Nazinga/Turbulence --dry-run
"""

import sys
import re
from pathlib import Path


def rename_x_to_gor(file_path: Path, dry_run: bool = False):
    """
    Benennt eine Datei um: Zyyddd_HH.dat oder Zyyddd_HH_2.dat → naz_yy_ddd_HHMM.dat

    Args:
        file_path: Pfad zur Datei
        dry_run: Wenn True, werden keine Änderungen vorgenommen, nur angezeigt

    Returns:
        True wenn umbenannt wurde, False sonst
    """
    # Pattern 1: Zyyddd_HH.dat
    # Pattern 2: Zyyddd_HH_2.dat
    # Z = Buchstabe Z
    # yy = 2 Ziffern (Jahr)
    # ddd = 3 Ziffern (Tag des Jahres)
    # HH = 2 Ziffern (Stunde)
    pattern1 = re.compile(r'^X(\d{2})(\d{3})_(\d{2})\.dat$')
    pattern2 = re.compile(r'^X(\d{2})(\d{3})_(\d{2})_2\.dat$')

    match1 = pattern1.match(file_path.name)
    match2 = pattern2.match(file_path.name)

    if not match1 and not match2:
        return False

    # Extrahiere Komponenten (beide Patterns haben die gleiche Struktur)
    match = match1 if match1 else match2
    yy = match.group(1)  # Jahr (2 Ziffern)
    ddd = match.group(2)  # Tag des Jahres (3 Ziffern)
    HH = match.group(3)   # Stunde (2 Ziffern)

    # Neuer Name: naz_yy_ddd_HHMM.dat (HHMM = HH + "00")
    new_name = f"gor_{yy}_{ddd}_{HH}00.dat"
    new_path = file_path.parent / new_name

    # Prüfe ob Ziel bereits existiert
    if new_path.exists() and new_path != file_path:
        print(f"  ⚠️ Übersprungen: {file_path.name} → {new_name} (Ziel existiert bereits)")
        return False

    if dry_run:
        print(f"  [DRY RUN] {file_path.name} → {new_name}")
    else:
        try:
            file_path.rename(new_path)
            print(f"  ✓ {file_path.name} → {new_name}")
        except Exception as e:
            print(f"  ⚠️ Fehler bei {file_path.name}: {e}")
            return False

    return True


def process_directory(directory: Path, dry_run: bool = False):
    """
    Verarbeitet alle Dateien in einem Ordner.

    Args:
        directory: Ordnerpfad
        dry_run: Wenn True, werden keine Änderungen vorgenommen
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

    # Finde alle .dat Dateien die mit X beginnen
    all_files = list(directory.glob("*.dat"))
    x_files = [f for f in all_files if f.name.startswith('X')]

    if not x_files:
        print("  ⚠️ Keine Dateien mit X-Präfix gefunden")
        return

    print(f"  Gefunden: {len(x_files)} Dateien mit X-Präfix")
    print()

    # Verarbeite jede Datei
    renamed_count = 0
    skipped_count = 0

    for file_path in sorted(x_files):
        if rename_x_to_gor(file_path, dry_run=dry_run):
            renamed_count += 1
        else:
            # Prüfe ob es ein bekanntes Format war
            if re.match(r'^Z\d{5}_\d{2}\.dat$', file_path.name) or re.match(r'^Z\d{5}_\d{2}_2\.dat$', file_path.name):
                skipped_count += 1
            else:
                print(f"  ⚠️ Übersprungen: {file_path.name} (passt nicht zum Muster Zyyddd_HH.dat oder Zyyddd_HH_2.dat)")

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
        print("Verwendung: python rename_x_to_gor.py <ordner_pfad> [--dry-run]")
        print("\nBeispiele:")
        print("  python rename_x_to_gor.py /Volumes/Data/Gorigo/Turbulence")
        print("  python rename_x_to_gor.py /Volumes/Data/Gorigo/Turbulence --dry-run")
        print("\nFormat:")
        print("  Zyyddd_HH.dat → naz_yy_ddd_HHMM.dat")
        print("  Zyyddd_HH_2.dat → naz_yy_ddd_HHMM.dat")
        print("  Beispiel: Z14159_09.dat → naz_14_159_0900.dat")
        print("  Beispiel: Z14159_09_2.dat → naz_14_159_0900.dat")
        sys.exit(1)

    directory = Path(sys.argv[1])
    dry_run = '--dry-run' in sys.argv

    process_directory(directory, dry_run=dry_run)


if __name__ == "__main__":
    main()
