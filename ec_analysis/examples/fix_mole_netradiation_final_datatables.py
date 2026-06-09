#!/usr/bin/env python3
"""
Korrigiert NETRAD für Mole in den final_datatables:

  NETRAD = SW_IN - SW_OUT + LW_IN - LW_OUT

Nur wenn alle vier Komponenten gültig sind; sonst NETRAD = -9999 (ESSD-Fehlwert).

Standard-Eingaben:
  .../final_datatables/Mole_30min.csv   (TIMESTAMP: YYYYMMDDHHMMSS)
  .../final_datatables/Mole_daily.csv   (TIMESTAMP: YYYYMMDD)

Standard-Ausgabe: neue Dateien mit Suffix _NETRAD_from_components.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

FINAL_DATATABLES = Path("/Users/hingerl-l/Data/essd_data_tables/final_datatables")
DEFAULT_30MIN = FINAL_DATATABLES / "Mole_30min.csv"
DEFAULT_DAILY = FINAL_DATATABLES / "Mole_daily.csv"

MISSING_CODE = -9999
RAD_COLS = ("SW_IN", "SW_OUT", "LW_IN", "LW_OUT")
TARGET_COL = "NETRAD"


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
        na_values=[-9999, "-9999", "-9999.0", -99999, "7999", "NAN", "nan", "NA"],
    )
    return [header_line, units_line], df


def _compute_netr_from_components(df: pd.DataFrame) -> pd.Series:
    for c in RAD_COLS:
        if c not in df.columns:
            raise ValueError(f"Spalte {c} fehlt")
    if TARGET_COL not in df.columns:
        raise ValueError(f"Spalte {TARGET_COL} fehlt")

    swi = pd.to_numeric(df["SW_IN"], errors="coerce")
    swo = pd.to_numeric(df["SW_OUT"], errors="coerce")
    lwi = pd.to_numeric(df["LW_IN"], errors="coerce")
    lwo = pd.to_numeric(df["LW_OUT"], errors="coerce")

    ok = swi.notna() & swo.notna() & lwi.notna() & lwo.notna()
    out = pd.Series(float(MISSING_CODE), index=df.index, dtype="float64")
    net = swi - swo + lwi - lwo
    out.loc[ok] = net.loc[ok]
    return out


def process_file(path: Path, output: Path | None) -> Path:
    header_lines, df = _read_essd_csv(path)
    n_data_cols = len(df.columns)
    u_parts = [x.strip() for x in header_lines[1].split(",")]
    if len(u_parts) != n_data_cols:
        raise ValueError(
            f"{path}: Header/Units-Spaltenanzahl passt nicht ({n_data_cols} vs {len(u_parts)})"
        )

    df = df.copy()
    df[TARGET_COL] = _compute_netr_from_components(df)

    out_path = output
    if out_path is None:
        out_path = path.parent / f"{path.stem}_NETRAD_from_components{path.suffix}"

    with out_path.open("w", encoding="utf-8", newline="") as f:
        f.write(header_lines[0] + "\n")
        f.write(header_lines[1] + "\n")
    df.to_csv(out_path, mode="a", index=False, header=False, lineterminator="\n")
    return out_path


def main() -> None:
    p = argparse.ArgumentParser(
        description="Mole: NETRAD aus SW_IN - SW_OUT + LW_IN - LW_OUT (final_datatables)"
    )
    p.add_argument(
        "--path-30min",
        type=Path,
        default=DEFAULT_30MIN,
        help=f"Pfad Mole_30min.csv (default: {DEFAULT_30MIN})",
    )
    p.add_argument(
        "--path-daily",
        type=Path,
        default=DEFAULT_DAILY,
        help=f"Pfad Mole_daily.csv (default: {DEFAULT_DAILY})",
    )
    p.add_argument("--output-30min", type=Path, default=None)
    p.add_argument("--output-daily", type=Path, default=None)
    p.add_argument(
        "--in-place",
        action="store_true",
        help="Eingabedateien überschreiben (Vorsicht)",
    )
    args = p.parse_args()

    out30 = args.path_30min if args.in_place else args.output_30min
    outdaily = args.path_daily if args.in_place else args.output_daily

    p1 = process_file(args.path_30min, output=out30)
    p2 = process_file(args.path_daily, output=outdaily)
    print(f"✓ 30min: {p1}")
    print(f"✓ daily: {p2}")


if __name__ == "__main__":
    main()
