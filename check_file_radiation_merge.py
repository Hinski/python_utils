#!/usr/bin/env python3
"""
Prüft, ob Strahlungsdaten aus einer Quelldatei im Parquet einer Station ankommen.

Verwendung:
  # Zeitraum aus Quelldatei, Station wählbar (Default: Nazinga)
  python check_nazinga_radiation_merge.py [Station] [Pfad zur .dat Datei]
  python check_nazinga_radiation_merge.py Nazinga "/Volumes/.../W3_RadiationMo_2358.dat"
  python check_nazinga_radiation_merge.py Kayoro "/pfad/zu/datei.dat"

  # Nur Parquet prüfen (fester Beispiel-Zeitraum)
  python check_nazinga_radiation_merge.py [Station]
  python check_nazinga_radiation_merge.py
"""
import sys
from pathlib import Path

import pandas as pd

MERGED_LONG = Path("/Users/hingerl-l/Data/merged_long")
DEFAULT_STATION = "Nazinga"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    station = DEFAULT_STATION
    dat_path = None
    if len(args) >= 2:
        station = args[0]
        dat_path = Path(args[1]).expanduser()
    elif len(args) == 1:
        a = args[0]
        if a.endswith(".dat") or "/" in a or "\\" in a:
            dat_path = Path(a).expanduser()
        else:
            station = a

    parquet_file = MERGED_LONG / f"{station}_radiation_merged_long.parquet"

    if dat_path is not None:
        if not dat_path.exists():
            print(f"Datei nicht gefunden: {dat_path}")
            return
        from data_loader import read_toa5
        df = read_toa5(dat_path)
        if df.empty:
            print(f"Datei konnte nicht geladen werden: {dat_path}")
            return
        check_start = df.index.min().floor("30min")
        check_end = df.index.max().floor("30min")
        print(f"Prüfe Zeitraum aus Quelldatei ({station})...")
        print(f"Quelldatei: {dat_path.name}")
        print(f"Zeitraum: {check_start} bis {check_end} ({len(df)} Zeilen)")
    else:
        check_start = pd.Timestamp("2021-08-21 00:00:00")
        check_end = pd.Timestamp("2021-08-21 23:30:00")
        print(f"Prüfe Zeitraum 2021-08-21 (Beispiel, Station {station})...")

    if not parquet_file.exists():
        print(f"Parquet nicht gefunden: {parquet_file}")
        return

    pq = pd.read_parquet(parquet_file)
    if not isinstance(pq.index, pd.DatetimeIndex):
        pq.index = pd.to_datetime(pq.index)
    pq.index = pq.index.floor("30min")

    in_range = pq.loc[check_start:check_end]
    n_rows = len(in_range)
    rad_cols = [c for c in ["SR_in_Avg", "SR_out_Avg", "NetTot_Avg"] if c in pq.columns]
    n_valid = in_range[rad_cols].notna().any(axis=1).sum() if rad_cols else 0

    print(f"\n{station} Parquet: {parquet_file.name}")
    print(f"  Index: {pq.index.min()} bis {pq.index.max()} ({len(pq):,} Zeilen)")
    print(f"  Im Zeitraum {check_start} bis {check_end}: {n_rows} Zeilen")
    print(f"  Davon mit Strahlungswerten (nicht nur NaN): {n_valid} Zeilen")
    if n_rows == 0:
        print("\n  → Parquet enthält KEINE Zeilen für diesen Zeitraum.")
        print("    combine_first würde neue Zeitstempel ergänzen (Neu hinzugefügt > 0).")
    elif n_valid == 0:
        print("\n  → Zeilen existieren, aber Strahlungsspalten sind alle NaN (Lücke).")
        print("    find_radiation_gaps sollte diese mit Quelldateien füllen.")
    else:
        print("\n  → Daten für diesen Zeitraum sind im Parquet vorhanden.")


if __name__ == "__main__":
    main()
