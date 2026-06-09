#!/usr/bin/env python3
import os
from pathlib import Path
import sys

print("=== REMOVE NAN LINES FROM Z15 FILES ===")
print("Durchsucht Z15_*.dat und löscht alle Zeilen, die 'NAN' enthalten.\n")

# Ordner bestimmen
if len(sys.argv) == 2:
    folder = Path(sys.argv[1])
else:
    folder = Path(input("Ordner eingeben: ").strip())

if not folder.is_dir():
    print("❌ Fehler: Ordner existiert nicht:", folder)
    sys.exit(1)

# Z15-Dateien suchen
files = sorted(folder.glob("Z15_*.dat"))

if not files:
    print("❌ Keine Z15_*.dat Dateien gefunden.")
    sys.exit(1)

print(f"Gefundene Dateien: {len(files)}\n")

for path in files:
    print(f"🔧 Prüfe {path.name} ...")

    # Backup anlegen
    bak_path = path.with_suffix(path.suffix + ".bak")
    if not bak_path.exists():
        path.rename(bak_path)
    else:
        print(f"   ⚠️ Backup existiert bereits → benutze vorhandenes.")

    cleaned_lines = []

    # Datei lesen
    with bak_path.open("r", errors="ignore") as fh:
        for line in fh:
            # Wenn irgendwo "NAN" vorkommt → verwerfen
            if "NAN" in line or "nan" in line.lower():
                continue

            cleaned_lines.append(line)

    # Datei überschreiben
    with path.open("w") as out:
        out.writelines(cleaned_lines)

    print(f"   ➜ {path.name}: {len(cleaned_lines)} Zeilen behalten")

print("\n✅ Fertig! Alle NAN-Zeilen wurden entfernt.")
print("Die Originale liegen im selben Ordner als *.bak")
