#!/usr/bin/env python3
"""
Findet fehlende Dateien basierend auf Zeitstempel im Dateinamen.

Vergleicht Dateien zwischen zwei Ordnern anhand des Zeitstempels:
- Format 1: Zyy_ddd_HH.dat (z.B. X19_251_07.dat)
- Format 2a: Zyyddd_HHMM.dat (z.B. X19251_0700.dat)
- Format 2b: Zyyddd_HH.dat (z.B. Y21045_20.dat)
- Format 3: prefix_yy_ddd_HHMM.dat (z.B. jan_19_251_0700.dat, kay_22_193_0900.dat)

Verwendung:
    python find_missing_files.py <rohdaten_ordner> <vergleichs_ordner> [<kopier_ziel_ordner>] [--copy]

    - rohdaten_ordner:     Ordner mit allen (Roh-)Dateien
    - vergleichs_ordner:   Ordner, mit dem verglichen wird (dort liegende Dateien gelten als vorhanden)
    - kopier_ziel_ordner: Nur bei --copy. Wohin fehlende Dateien kopiert werden (separater Ordner,
                          als 3. Argument oder per Abfrage; nie in Rohdaten- oder Vergleichsordner)
"""

import sys
import re
import shutil
from pathlib import Path
from collections import defaultdict


def parse_timestamp_from_filename(filename: str):
    """
    Extrahiert Zeitstempel aus Dateinamen.

    Unterstützte Formate:
    - Zyy_ddd_HH.dat (z.B. X19_251_07.dat)
    - Zyyddd_HHMM.dat (z.B. X19251_0700.dat)
    - prefix_yy_ddd_HHMM.dat (z.B. jan_19_251_0700.dat, kay_20_145_1400.dat)

    Returns:
        Tuple (yy, ddd, HH, MM) oder None wenn nicht geparst werden kann
    """
    name = filename.replace('.dat', '').lower()

    # Format 1: Zyy_ddd_HH.dat (z.B. X19_251_07.dat)
    # Z = X, Y oder Z, yy = Jahr, ddd = Tag, HH = Stunde
    pattern1 = re.compile(r'^[xyz](\d{2})_(\d{3})_(\d{2})$')
    match1 = pattern1.match(name)
    if match1:
        yy, ddd, HH = match1.groups()
        return (yy, ddd, HH, '00')  # MM = 00 für Format 1

    # Format 2a: Zyyddd_HHMM.dat (z.B. X19251_0700.dat)
    # Z = X, Y oder Z, yy = Jahr, ddd = Tag, HHMM = Stunde+Minute
    pattern2a = re.compile(r'^[xyz](\d{2})(\d{3})_(\d{4})$')
    match2a = pattern2a.match(name)
    if match2a:
        yy, ddd, HHMM = match2a.groups()
        HH = HHMM[:2]
        MM = HHMM[2:]
        return (yy, ddd, HH, MM)

    # Format 2b: Zyyddd_HH.dat (z.B. Y21045_20.dat)
    # Z = X, Y oder Z, yy = Jahr, ddd = Tag, HH = Stunde (ohne Minute)
    pattern2b = re.compile(r'^[xyz](\d{2})(\d{3})_(\d{2})$')
    match2b = pattern2b.match(name)
    if match2b:
        yy, ddd, HH = match2b.groups()
        return (yy, ddd, HH, '00')  # MM = 00 für Format ohne Minute

    # Format 3: prefix_yy_ddd_HHMM.dat (z.B. jan_19_251_0700.dat, kay_22_193_0900.dat)
    # prefix = beliebige Buchstaben, yy = Jahr, ddd = Tag, HHMM = Stunde+Minute
    pattern3 = re.compile(r'^[a-z]+_(\d{2})_(\d{3})_(\d{4})$')
    match3 = pattern3.match(name)
    if match3:
        yy, ddd, HHMM = match3.groups()
        HH = HHMM[:2]
        MM = HHMM[2:]
        return (yy, ddd, HH, MM)

    return None


def scan_directory(directory: Path, show_progress: bool = True):
    """
    Scannt einen Ordner nach .dat Dateien und extrahiert Zeitstempel.
    Speichereffizient: Verwendet Iterator statt Liste für große Datenmengen.

    Returns:
        Dict: {(yy, ddd, HH, MM): set of file paths}  # Set statt List für bessere Performance
    """
    timestamp_files = defaultdict(set)

    # Verwende Iterator statt Liste für Speichereffizienz
    dat_files = directory.glob("*.dat")

    file_count = 0
    parsed_count = 0
    unparsed_count = 0

    for file_path in dat_files:
        file_count += 1

        if show_progress and file_count % 10000 == 0:
            print(f"    ... {file_count:,} Dateien gescannt...")

        timestamp = parse_timestamp_from_filename(file_path.name)
        if timestamp:
            timestamp_files[timestamp].add(file_path)  # Set für bessere Performance
            parsed_count += 1
        else:
            unparsed_count += 1
            if unparsed_count <= 10:  # Zeige nur erste 10 unparsbare Dateien
                print(f"  ⚠️ Konnte Zeitstempel nicht parsen: {file_path.name}")

    if show_progress:
        print(f"    Gesamt: {file_count:,} Dateien gescannt")
        print(f"    Geparst: {parsed_count:,} Dateien")
        if unparsed_count > 10:
            print(f"    Nicht geparst: {unparsed_count} Dateien")

    return timestamp_files


def find_missing_files(source_dir: Path, target_dir: Path, copy_files: bool = False, copy_to_dir: Path | None = None):
    """
    Findet Dateien, die im source_dir vorhanden sind, aber im target_dir fehlen.
    Optional: Kopiert fehlende Dateien in copy_to_dir (nicht in target_dir).
    Optimiert für große Datenmengen (500GB+, 70.000+ Dateien).

    Args:
        source_dir: Ordner mit Rohdaten
        target_dir: Ordner zum Vergleich (dort liegende Dateien = vorhanden)
        copy_files: Wenn True, werden fehlende Dateien kopiert
        copy_to_dir: Ordner, in den fehlende Dateien kopiert werden (nur bei copy_files=True)

    Returns:
        Anzahl fehlender Dateien
    """
    print(f"📁 Scanne Rohdaten-Ordner: {source_dir}")
    source_timestamps = scan_directory(source_dir, show_progress=True)
    print(f"   Gefunden: {len(source_timestamps)} einzigartige Zeitstempel")
    total_source_files = sum(len(files) for files in source_timestamps.values())
    print(f"   Gesamt: {total_source_files:,} Dateien")
    print()

    print(f"📁 Scanne Ziel-Ordner: {target_dir}")
    target_timestamps = scan_directory(target_dir, show_progress=True)
    print(f"   Gefunden: {len(target_timestamps)} einzigartige Zeitstempel")
    total_target_files = sum(len(files) for files in target_timestamps.values())
    print(f"   Gesamt: {total_target_files:,} Dateien")
    print()

    # Finde fehlende Zeitstempel
    missing_timestamps = set(source_timestamps.keys()) - set(target_timestamps.keys())

    if not missing_timestamps:
        print("✅ Alle Dateien sind im Zielordner vorhanden!")
        return 0

    print(f"🔍 Fehlende Zeitstempel: {len(missing_timestamps)}")

    # Zähle fehlende Dateien ohne sie alle im Speicher zu halten
    missing_file_count = sum(len(source_timestamps[ts]) for ts in missing_timestamps)
    print(f"   Fehlende Dateien: {missing_file_count:,}")
    print()

    # Zeige Beispiel-Zeitstempel (nur erste 10)
    print("Beispiel fehlende Zeitstempel:")
    for i, timestamp in enumerate(sorted(missing_timestamps)[:10], 1):
        yy, ddd, HH, MM = timestamp
        file_count = len(source_timestamps[timestamp])
        print(f"  {i}. {yy}_{ddd}_{HH}{MM}: {file_count} Datei(en)")
        # Zeige erste Datei als Beispiel
        example_file = next(iter(source_timestamps[timestamp]))
        print(f"     Beispiel: {example_file.name}")
    if len(missing_timestamps) > 10:
        print(f"  ... und {len(missing_timestamps) - 10} weitere Zeitstempel")
    print()

    # Kopiere fehlende Dateien wenn gewünscht (immer in copy_to_dir, nicht in target_dir)
    if copy_files and missing_file_count > 0:
        if not copy_to_dir:
            print("❌ Bei --copy muss ein Kopier-Zielordner angegeben werden.")
            return missing_file_count
        print("📋 Kopiere fehlende Dateien...")
        print(f"   Zielordner für Kopien: {copy_to_dir}")
        print(f"   Zu kopieren: {missing_file_count:,} Dateien")
        print()

        copy_to_dir.mkdir(parents=True, exist_ok=True)
        copied_count = 0
        failed_count = 0
        skipped_count = 0

        # Verarbeite Zeitstempel für besseres Memory-Management
        for timestamp in sorted(missing_timestamps):
            files = source_timestamps[timestamp]

            for file_path in files:
                try:
                    target_path = copy_to_dir / file_path.name

                    # Prüfe ob Ziel bereits existiert
                    if target_path.exists():
                        skipped_count += 1
                        if skipped_count <= 5:
                            print(f"  ⚠️ Übersprungen: {file_path.name} (existiert bereits)")
                        continue

                    # Kopiere Datei
                    shutil.copy2(file_path, target_path)
                    copied_count += 1

                    # Fortschrittsanzeige alle 100 Dateien oder alle 1GB (ca. 143 Dateien bei 7MB)
                    if copied_count % 100 == 0:
                        estimated_size_mb = copied_count * 7
                        estimated_size_gb = estimated_size_mb / 1024
                        print(f"  ✓ {copied_count:,} Dateien kopiert (~{estimated_size_gb:.2f} GB)...")

                except Exception as e:
                    failed_count += 1
                    if failed_count <= 10:
                        print(f"  ⚠️ Fehler beim Kopieren von {file_path.name}: {e}")

        print()
        print("=" * 60)
        print(f"✅ Kopieren abgeschlossen:")
        print(f"   Erfolgreich kopiert: {copied_count:,} Dateien")
        if skipped_count > 0:
            print(f"   Übersprungen (existieren bereits): {skipped_count:,} Dateien")
        if failed_count > 0:
            print(f"   Fehlgeschlagen: {failed_count:,} Dateien")

        if copied_count > 0:
            estimated_size_mb = copied_count * 7
            estimated_size_gb = estimated_size_mb / 1024
            print(f"   Geschätzte kopierte Datenmenge: ~{estimated_size_gb:.2f} GB")
        print("=" * 60)

    return missing_file_count


def main():
    """Hauptfunktion."""
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    copy_files = "--copy" in sys.argv

    if len(args) < 2:
        print("Verwendung: python find_missing_files.py <rohdaten_ordner> <vergleichs_ordner> [<kopier_ziel_ordner>] [--copy]")
        print("\n  rohdaten_ordner     = Ordner mit allen (Roh-)Dateien")
        print("  vergleichs_ordner   = Ordner zum Vergleich (dort liegende Dateien = vorhanden)")
        print("  kopier_ziel_ordner  = Nur bei --copy: wohin fehlende Dateien kopiert werden.")
        print("                        Wird als 3. Argument angegeben oder bei Aufruf abgefragt.")
        print("                        Kopien gehen nie in den Vergleichs-Ordner.")
        print("\nBeispiele:")
        print("  python find_missing_files.py /Volumes/Data/Raw /Volumes/Data/Processed")
        print("  python find_missing_files.py /Volumes/Data/Raw /Volumes/Data/Processed /Volumes/Data/Missing --copy")
        print("\nOptionen:")
        print("  --copy    Kopiert fehlende Dateien in einen separaten Kopier-Zielordner (3. Argument oder Abfrage)")
        print("\nUnterstützte Dateiformate:")
        print("  - Zyy_ddd_HH.dat (z.B. X19_251_07.dat)")
        print("  - Zyyddd_HHMM.dat (z.B. X19251_0700.dat)")
        print("  - prefix_yy_ddd_HHMM.dat (z.B. kay_22_193_0900.dat)")
        sys.exit(1)

    source_dir = Path(args[0])
    target_dir = Path(args[1])
    copy_to_dir = Path(args[2]) if len(args) >= 3 else None

    if copy_files and copy_to_dir is None:
        try:
            prompt = "Kopier-Zielordner (wohin fehlende Dateien kopiert werden): "
            raw = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n❌ Abgebrochen.")
            sys.exit(1)
        if not raw:
            print("❌ Kein Ordner angegeben.")
            sys.exit(1)
        copy_to_dir = Path(raw)

    if copy_files and copy_to_dir is not None:
        copy_res = copy_to_dir.resolve()
        if copy_res == target_dir.resolve():
            print("❌ Der Kopier-Zielordner darf nicht der Vergleichs-Ordner sein.")
            print("   Bitte einen anderen Ordner für die Kopien angeben.")
            sys.exit(1)
        if copy_res == source_dir.resolve():
            print("❌ Der Kopier-Zielordner darf nicht der Rohdaten-Ordner sein.")
            print("   Bitte einen anderen Ordner für die Kopien angeben.")
            sys.exit(1)

    if not source_dir.exists():
        print(f"❌ Rohdaten-Ordner existiert nicht: {source_dir}")
        sys.exit(1)

    if not target_dir.exists():
        print(f"❌ Vergleichs-Ordner existiert nicht: {target_dir}")
        sys.exit(1)

    if copy_to_dir and not copy_to_dir.exists():
        try:
            copy_to_dir.mkdir(parents=True, exist_ok=True)
            print(f"📁 Kopier-Zielordner erstellt: {copy_to_dir}")
        except Exception as e:
            print(f"❌ Konnte Kopier-Zielordner nicht erstellen: {e}")
            sys.exit(1)

    print("=" * 60)
    if copy_files:
        print("Fehlende Dateien finden und in eigenen Ordner kopieren")
    else:
        print("Fehlende Dateien finden")
    print("=" * 60)
    print()

    missing_file_count = find_missing_files(source_dir, target_dir, copy_files=copy_files, copy_to_dir=copy_to_dir)

    print()
    print("=" * 60)
    if missing_file_count > 0:
        print(f"📊 Zusammenfassung:")
        print(f"   {missing_file_count:,} Dateien fehlen im Zielordner")
        if not copy_files:
            print(f"\n💡 Tipp: Verwenden Sie --copy um fehlende Dateien automatisch zu kopieren")
    else:
        print("✅ Keine fehlenden Dateien gefunden!")
    print("=" * 60)


if __name__ == "__main__":
    main()
