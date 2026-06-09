#!/usr/bin/env python3
import os
import glob
import sys

print("=== TK3 RAW DATA CLEANER ===")
print("1) Entfernt doppelte Zeitstempel")
print("2) Normiert Missing Values (-99999 → \"NAN\")")
print("3) Belässt alle Originalmesswerte unverändert")
print("4) Speichert Originale als *.bak\n")

# --- Ordner auswählen ---
if len(sys.argv) == 2:
    folder = sys.argv[1]
else:
    folder = input("Ordner mit Rohdaten eingeben: ").strip()

if not os.path.isdir(folder):
    print("❌ Fehler: Ordner existiert nicht:", folder)
    sys.exit(1)

os.chdir(folder)
files = sorted(glob.glob("Z*.dat"))

if not files:
    print("❌ Keine Z*.dat Dateien gefunden in:", folder)
    sys.exit(1)

print(f"Gefundene Dateien: {len(files)}\n")

for f in files:
    print(f"🔧 Bearbeite {f} ...")

    # Backup
    bak = f + ".bak"
    if not os.path.exists(bak):
        os.rename(f, bak)
    else:
        print(f"⚠️ Backup {bak} existiert bereits – benutze existierendes Backup.")

    seen_timestamps = set()
    cleaned_lines = []

    with open(bak, "r", errors="ignore") as fh:
        for line in fh:

            # ---- Missing Value Normalisierung ----
            # Ersetze NUR echte -99999 durch TK3-kompatible "NAN"
            line = line.replace(", -99999,", ',"NAN",')
            line = line.replace(",-99999,", ',"NAN",')
            line = line.replace(", -99999\n", ',"NAN"\n')
            line = line.replace(",-99999\n", ',"NAN"\n')

            # ---- Zeitstempel extrahieren ----
            try:
                ts_raw = line.split(",")[0].strip()
            except Exception:
                # Falls die Zeile beschädigt ist → übernehmen (nicht entfernen)
                cleaned_lines.append(line)
                continue

            # ---- Deduplikation ----
            if ts_raw not in seen_timestamps:
                cleaned_lines.append(line)
                seen_timestamps.add(ts_raw)
            else:
                # Duplikat → verwerfen
                pass
        fh = fh.dropna()
    # Datei zurückschreiben
    with open(f, "w") as fh:
        fh.writelines(cleaned_lines)

print("\n✔ Reinigung abgeschlossen!")
print("Alle bereinigten Dateien wurden in-place erzeugt.")
print("Originale liegen als *.bak im selben Ordner.")

