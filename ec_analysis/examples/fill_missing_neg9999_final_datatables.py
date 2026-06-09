#!/usr/bin/env python3
"""
Setzt fehlende ESSD-Messwerte in final_datatables auf den Sentinel -9999.

Kontext: Gleiche Tabellen wie die übrigen ESSD-Pipelines (2-Zeilen-Header: Variablen,
Einheiten, ab Zeile 3 Daten). Zeilen mit gültigem TIMESTAMP, in denen ein Datenfeld
leer/NaN ist, werden in allen Spalten außer TIMESTAMP mit -9999 gefüllt.

Standard-Eingabe:
  .../final_datatables/*.csv

Standard: schreibt neue Dateien im gleichen Verzeichnis mit Suffix _na9999 vor der
Endung (z. B. Gorigo_30min_na9999.csv). Mit --in-place werden die Originaldateien
überschrieben (optional --backup für .bak-Kopien).
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pandas as pd

FINAL_DATATABLES = Path("/Users/hingerl-l/Data/essd_data_tables/final_datatables")
MISSING_CODE = -9999
TS_COL = "TIMESTAMP"

# Beim Einlesen: nur echte Lücken als NaN, nicht ESSD-Sentinel -9999/-99999
# (sonst wären alle bereits gesetzten Fehlwerte „leer“ und würden mitgezählt).
_READ_NA_VALUES = ["", "NAN", "N/A", "nan", "NA", "None", "none"]


def _read_essd_csv(path: Path) -> tuple[list[str], pd.DataFrame]:
    with path.open("r", encoding="utf-8") as f:
        header_line = f.readline().strip()
        units_line = f.readline().strip()
    var_names = [c.strip() for c in header_line.split(",")]
    df = pd.read_csv(
        path,
        skiprows=2,
        header=None,
        names=var_names,
        low_memory=False,
        na_values=_READ_NA_VALUES,
        keep_default_na=True,
    )
    return [header_line, units_line], df


def _rows_with_valid_timestamp(df: pd.DataFrame, ts_col: str = TS_COL) -> pd.Series:
    s = df[ts_col]
    if pd.api.types.is_numeric_dtype(s):
        return s.notna()
    s_str = s.astype(str).str.strip()
    bad = s_str.str.lower().isin(("", "nan", "none", "<na>"))
    return s.notna() & ~bad


def _write_essd_csv(path: Path, header_lines: list[str], df: pd.DataFrame) -> None:
    n_data_cols = len(df.columns)
    u_parts = [x.strip() for x in header_lines[1].split(",")]
    if len(u_parts) != n_data_cols:
        raise ValueError(
            f"{path}: Header/Units-Spaltenanzahl passt nicht ({n_data_cols} vs {len(u_parts)})"
        )
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(header_lines[0] + "\n")
        f.write(header_lines[1] + "\n")
    df.to_csv(path, mode="a", index=False, header=False, lineterminator="\n")


def process_file(
    path: Path,
    *,
    inplace: bool,
    backup: bool,
    dry_run: bool,
) -> tuple[Path | None, int]:
    """
    Returns (written_path_or_None_if_dry_run_or_skip, number_of_cells_that_were_missing).
    """
    header_lines, df = _read_essd_csv(path)
    if TS_COL not in df.columns:
        raise ValueError(f"{path}: Spalte {TS_COL!r} fehlt")

    data_cols = [c for c in df.columns if c != TS_COL]
    has_ts = _rows_with_valid_timestamp(df, TS_COL)
    sub = df.loc[has_ts, data_cols]
    n_missing = int(sub.isna().sum().sum())

    if dry_run:
        return (None, n_missing)

    if n_missing == 0:
        return (None, 0)

    df = df.copy()
    df.loc[has_ts, data_cols] = df.loc[has_ts, data_cols].fillna(MISSING_CODE)

    if inplace:
        out_path = path
        if backup and path.exists():
            bak = path.with_suffix(path.suffix + ".bak")
            shutil.copy2(path, bak)
    else:
        out_path = path.parent / f"{path.stem}_na9999{path.suffix}"

    _write_essd_csv(out_path, header_lines, df)
    return (out_path, n_missing)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Fehlende Werte in final_datatables (ESSD-CSV) mit -9999 füllen"
    )
    p.add_argument(
        "--data-dir",
        type=Path,
        default=FINAL_DATATABLES,
        help=f"Verzeichnis mit *_30min.csv / *_daily.csv (default: {FINAL_DATATABLES})",
    )
    p.add_argument(
        "--glob",
        dest="glob_pat",
        default="*.csv",
        help='Dateiauswahl relativ zu --data-dir (default: "*.csv")',
    )
    p.add_argument(
        "--in-place",
        action="store_true",
        help="Originaldateien überschreiben statt *_na9999.csv zu schreiben",
    )
    p.add_argument(
        "--backup",
        action="store_true",
        help="Vor Überschreiben .bak-Kopie anlegen (nur mit --in-place)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur zählen, nichts schreiben",
    )
    args = p.parse_args()

    data_dir = args.data_dir
    if not data_dir.is_dir():
        raise SystemExit(f"Kein Verzeichnis: {data_dir}")

    paths = sorted(data_dir.glob(args.glob_pat))
    if not paths:
        raise SystemExit(f"Keine Treffer für {data_dir}/{args.glob_pat}")

    total_cells = 0
    for path in paths:
        if path.name.endswith(".bak") or "_na9999" in path.stem:
            continue
        try:
            out_path, n = process_file(
                path,
                inplace=args.in_place,
                backup=args.backup,
                dry_run=args.dry_run,
            )
        except Exception as e:
            print(f"✗ {path.name}: {e}")
            continue
        total_cells += n
        if args.dry_run:
            print(f"  {path.name}: {n} leere Zellen (Zeilen mit TIMESTAMP)")
        elif out_path is None:
            print(f"  {path.name}: übersprungen (keine Lücken)")
        else:
            print(f"✓ {path.name} → {out_path.name} ({n} Zellen gesetzt)")

    if args.dry_run:
        print(f"Summe: {total_cells} Zellen würden auf {MISSING_CODE} gesetzt.")
    else:
        print(f"Fertig. Insgesamt {total_cells} Zellen auf {MISSING_CODE} gesetzt.")


if __name__ == "__main__":
    main()
