#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Konvertiert Campbell Scientific TOB3/Flux_CSFormat-Dateien (.dat, binär)
in lesbare CSV-Dateien.

Format: 6 Zeilen Text-Header (TOB3, Tabellenname, Spalten, Einheiten, Aggregation, Datentypen),
danach Binärdaten (IEEE4B, INT4, ASCII). Nach dem Lesen wird eine CSV mit TIMESTAMP und allen
Spalten geschrieben.

Verwendung:
    python tob3_to_csv.py <eingabedatei.dat> [ausgabedatei.csv]
    python tob3_to_csv.py "/Volumes/Extreme SSD/WASCAL_5_MOLE/SD_Card/Mole/17691_Flux_CSFormat_65.dat"
"""

import sys
from pathlib import Path

from data_loader import read_tob3_csformat


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("Beispiel:")
        print('  python tob3_to_csv.py "/Volumes/Extreme SSD/.../17691_Flux_CSFormat_65.dat"')
        sys.exit(1)

    inp = Path(sys.argv[1])
    if not inp.exists():
        print(f"Datei nicht gefunden: {inp}")
        sys.exit(1)

    out = Path(sys.argv[2]) if len(sys.argv) > 2 else inp.with_suffix(".csv")

    print(f"Lese: {inp}")
    df = read_tob3_csformat(inp)
    if df.empty:
        print("Keine Daten gelesen (Format evtl. abweichend oder Datei leer).")
        sys.exit(1)

    print(f"Zeilen: {len(df):,}, Spalten: {len(df.columns)}")
    df.to_csv(out)
    print(f"Geschrieben: {out}")


if __name__ == "__main__":
    main()
