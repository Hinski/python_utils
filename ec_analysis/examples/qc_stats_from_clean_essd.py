#!/usr/bin/env python3
"""
Berechnet QC-Statistiken (Total n, n und % für QC<=1 und QC=0)
für H, LE und CO2 auf Basis der *_essd_30min_clean.csv Dateien.

Ausgabe: LaTeX-Tabellenzeilen im Stil von Tabelle \\ref{tab:qc_stats}.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DATA_BASE = Path("/Users/hingerl-l/Data")
ESSD_DIR = DATA_BASE / "essd_data_tables"

MISSING_VALUE = -9999

STATIONS = ["Gorigo", "Janga", "Kayoro", "Mole", "Nazinga", "Sumbrungu"]

# Mapping für die drei Flux-Variablen und ihre QC-Spalten im ESSD-Format
VARIABLES = [
    ("H", "H_QC", "H"),
    ("LE", "LE_QC", "LE"),
    # CO2-Flux: in ESSD ist die QC-Spalte CO2_QC, Flux-Name in der Tabelle "CO$_2$"
    ("NEE", "CO2_QC", "CO$_2$"),
]


def load_clean_essd(station: str) -> pd.DataFrame | None:
    """Lädt {station}_essd_30min_clean.csv (oder gibt None zurück, falls nicht vorhanden)."""
    path = ESSD_DIR / f"{station}_essd_30min_clean.csv"
    if not path.exists():
        print(f"{station}: Clean-Datei nicht gefunden: {path}")
        return None

    with path.open("r", encoding="utf-8") as f:
        header_line = f.readline().strip()
        units_line = f.readline().strip()

    var_names = [c.strip() for c in header_line.split(",")]
    # units werden hier nicht benötigt

    df = pd.read_csv(
        path,
        skiprows=2,
        header=None,
        names=var_names,
        low_memory=False,
        na_values=[MISSING_VALUE, str(MISSING_VALUE), "-9999.0", "nan", "NAN"],
    )

    if "TIMESTAMP" not in df.columns or df["TIMESTAMP"].empty:
        print(f"{station}: Keine TIMESTAMP-Spalte gefunden.")
        return None

    ts = pd.to_datetime(df["TIMESTAMP"], format="%Y%m%d%H%M%S", errors="coerce")
    df = df.drop(columns=["TIMESTAMP"])
    df.index = ts
    df = df[df.index.notna()].sort_index()

    # Fehlwerte zuverlässig entfernen
    df = df.replace(MISSING_VALUE, np.nan)
    df = df.replace(float(MISSING_VALUE), np.nan)

    return df


def compute_qc_stats(df: pd.DataFrame, flux_col: str, qc_col: str) -> tuple[int, int, float, int, float]:
    """
    Liefert (n_total, n_le1, pct_le1, n_eq0, pct_eq0).
    n_total: Anzahl Zeilen, in denen Flux und QC beide nicht NaN sind.
    """
    if flux_col not in df.columns or qc_col not in df.columns:
        return 0, 0, 0.0, 0, 0.0

    flux = pd.to_numeric(df[flux_col], errors="coerce")
    qc = pd.to_numeric(df[qc_col], errors="coerce")

    valid = flux.notna() & qc.notna()
    if not valid.any():
        return 0, 0, 0.0, 0, 0.0

    n_total = int(valid.sum())
    le1 = valid & (qc <= 1)
    eq0 = valid & (qc == 0)

    n_le1 = int(le1.sum())
    n_eq0 = int(eq0.sum())

    pct_le1 = 100.0 * n_le1 / n_total if n_total else 0.0
    pct_eq0 = 100.0 * n_eq0 / n_total if n_total else 0.0

    return n_total, n_le1, pct_le1, n_eq0, pct_eq0


def fmt_int(n: int) -> str:
    """Formatiert Ganzzahlen mit dünnem Tausender-Trennzeichen wie in der Tabelle (\,)."""
    return f"{n:,}".replace(",", "\\,")


def main() -> None:
    print("% QC-Statistik aus *_essd_30min_clean.csv (generiert von qc_stats_from_clean_essd.py)")
    rows: list[str] = []

    for station in STATIONS:
        df = load_clean_essd(station)
        if df is None:
            continue
        for flux_col, qc_col, label in VARIABLES:
            n_total, n_le1, pct_le1, n_eq0, pct_eq0 = compute_qc_stats(df, flux_col, qc_col)
            row = (
                f"{station} & {label} "
                f"& {fmt_int(n_total)} "
                f"& {fmt_int(n_le1)} & {pct_le1:.1f} "
                f"& {fmt_int(n_eq0)} & {pct_eq0:.1f} \\\\"
            )
            rows.append(row)

    # LaTeX-Zeilen gruppiert wie in der Beispiel-Tabelle ausgeben
    current_station = None
    for row in rows:
        station = row.split("&", 1)[0].strip()
        if current_station is not None and station != current_station:
            print("\\midrule")
        print(row)
        current_station = station


if __name__ == "__main__":
    main()

