#!/usr/bin/env python3
import os
import glob
import sys

print("=== REMOVE TIMESTAMP COLUMN ===")

# Ordner auswählen
if len(sys.argv) == 2:
    folder = sys.argv[1]
else:
    folder = input("Ordner eingeben: ").strip()

if not os.path.isdir(folder):
    print("❌ Fehler: Ordner existiert nicht:", folder)
    sys.exit(1)

os.chdir(folder)
files = sorted(glob.glob("*.dat"))

if not files:
    print("❌ Keine .dat Dateien gefunden.")
    sys.exit(1)

print(f"Gefundene Dateien: {len(files)}\n")

for f in files:
    print(f"🔧 Bearbeite {f} ...")

    bak = f + ".bak"
    if not os.path.exists(bak):
        os.rename(f, bak)
    else:
        print(f"⚠️ Backup {bak} existiert bereits – benutze existierendes Backup.")

    cleaned_lines = []

    with open(bak, "r", errors="ignore") as fh:
        for line in fh:
            parts = line.split(",")
            if len(parts) <= 1:
                continue  # leere oder beschädigte Zeile überspringen

            # Entferne erste Spalte
            new_line = ",".join(parts[1:])

            cleaned_lines.append(new_line)

    with open(f, "w") as fh:
        fh.writelines(cleaned_lines)

print("\n✔ Fertig! Timestamp-Spalten entfernt.")
print("Backups: *.bak")
