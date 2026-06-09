#!/usr/bin/env python3
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

print("=== Z15 .bak SPLITTER ===")
print("1) Liest .dat.bak-Dateien im Ordner")
print("2) Entfernt die erste Spalte (Timestamp)")
print("3) Teilt jede 1h-Datei in 2× 30min-Dateien")
print("4) Passt Dateinamen (Z15_yy_ddd_HHMM.dat) an\n")

# --------------------------------------------------
# Ordner einlesen
# --------------------------------------------------
if len(sys.argv) == 2:
    folder = Path(sys.argv[1])
else:
    folder = Path(input("Ordner mit .dat.bak-Dateien eingeben: ").strip())

if not folder.is_dir():
    print("❌ Fehler: Ordner existiert nicht:", folder)
    sys.exit(1)

# Alle .dat.bak-Dateien suchen
bak_files = sorted(folder.glob("Z15_*.dat.bak"))

if not bak_files:
    print("❌ Keine Z15_*.dat.bak Dateien gefunden in:", folder)
    sys.exit(1)

print(f"Gefundene .bak-Dateien: {len(bak_files)}\n")


# --------------------------------------------------
# Hilfsfunktion: erste Spalte entfernen
# --------------------------------------------------
def drop_first_column(line: str) -> str:
    """
    Entfernt die erste Komma-getrennte Spalte.
    """
    line = line.rstrip("\n")
    parts = line.split(",")
    if len(parts) <= 1:
        return ""  # leere oder kaputte Zeile
    return ",".join(parts[1:]) + "\n"


# --------------------------------------------------
# Hilfsfunktion: Zeit aus Dateinamen parsen
# Format: Z15_yy_ddd_HHMM.dat(.bak)
# --------------------------------------------------
def parse_filename_time(basename: str) -> datetime:
    """
    Parst Z15_yy_ddd_HHMM.* in ein datetime-Objekt.
    Jahr wird als 2000 + yy interpretiert.
    """
    # Beispielbasename: Z15_15_001_0000.dat.bak -> Z15_15_001_0000
    core = basename
    if core.endswith(".dat.bak"):
        core = core[:-8]  # entferne ".dat.bak"
    elif core.endswith(".dat"):
        core = core[:-4]

    # core: Z15_yy_ddd_HHMM
    parts = core.split("_")
    if len(parts) != 4:
        raise ValueError(f"Unerwartetes Dateinamenformat: {basename}")

    _, yy_str, ddd_str, hhmm_str = parts
    yy = int(yy_str)
    ddd = int(ddd_str)
    hh = int(hhmm_str[:2])
    mm = int(hhmm_str[2:])

    year = 2000 + yy  # Annahme: 20xx
    dt0 = datetime(year, 1, 1) + timedelta(days=ddd - 1, hours=hh, minutes=mm)
    return dt0


def format_filename_time(dt: datetime) -> str:
    """
    Baut aus einem datetime wieder yy, ddd, HHMM.
    """
    yy = dt.year % 100
    ddd = dt.timetuple().tm_yday
    hh = dt.hour
    mm = dt.minute
    return f"{yy:02d}_{ddd:03d}_{hh:02d}{mm:02d}"


# --------------------------------------------------
# Hauptschleife
# --------------------------------------------------
for bak_path in bak_files:
    print(f"🔧 Bearbeite {bak_path.name} ...")

    # Zeitinformation aus Dateinamen holen
    try:
        dt_start = parse_filename_time(bak_path.name)
    except Exception as e:
        print(f"   ⚠️ Überspringe (konnte Zeit nicht parsen): {e}")
        continue

    dt_half = dt_start + timedelta(minutes=30)

    # Ziel-Dateinamen konstruieren (ohne .bak)
    half1_tag = format_filename_time(dt_start)
    half2_tag = format_filename_time(dt_half)

    # Basis: "Z15"
    half1_name = f"Z15_{half1_tag}.dat"
    half2_name = f"Z15_{half2_tag}.dat"

    out1_path = bak_path.with_name(half1_name)
    out2_path = bak_path.with_name(half2_name)

    # .bak einlesen
    with bak_path.open("r", errors="ignore") as fh:
        lines = [ln for ln in fh if ln.strip()]

    if not lines:
        print("   ⚠️ Datei leer, überspringe.")
        continue

    # Timestamp-Spalte entfernen
    processed = [drop_first_column(ln) for ln in lines]
    processed = [ln for ln in processed if ln.strip()]  # leere Zeilen raus

    n = len(processed)
    if n < 2:
        print(f"   ⚠️ Zu wenige Zeilen ({n}), überspringe Split.")
        continue

    # mittig teilen (erste Hälfte → erste 30min)
    mid = n // 2  # falls ungerade: zweite Hälfte bekommt eine Zeile mehr
    part1 = processed[:mid]
    part2 = processed[mid:]

    # Dateien schreiben
    print(f"   ➜ Schreibe {out1_path.name} (Zeilen: {len(part1)})")
    with out1_path.open("w") as f1:
        f1.writelines(part1)

    print(f"   ➜ Schreibe {out2_path.name} (Zeilen: {len(part2)})")
    with out2_path.open("w") as f2:
        f2.writelines(part2)

print("\n✅ Split abgeschlossen.")
print("Neue 30min-Dateien liegen als Z15_yy_ddd_HHMM.dat im selben Ordner.")
print("Die Originale bleiben als .dat.bak erhalten.")
