#!/usr/bin/env python3
"""
Fügt die Spalte QC_wind_sector_kayoro zu Kayoro ESSD-Tabellen hinzu.

Logik:
  - Vor Oktober 2016: -9999
  - Ab 2016-10-01: 1 wenn 196 <= WD <= 228, sonst 0
  - Ab 2016-10-01 bei fehlendem WD (NaN nach Einlesen bzw. Sentinel -9999/-99999 in der Datei): QC = -9999
    (entspricht der ESSD-Konvention „fehlend = -9999“)

Eingaben (Standardpfade):
  .../final_datatables/Kayoro_30min.csv  (TIMESTAMP: YYYYMMDDHHMMSS)
  .../final_datatables/Kayoro_daily.csv (TIMESTAMP: YYYYMMDD)

Standard: Ausgabe als neue Dateien im gleichen Verzeichnis mit Suffix _QC_wind_sector.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

FINAL_DATATABLES = Path("/Users/hingerl-l/Data/essd_data_tables/final_datatables")
DEFAULT_30MIN = FINAL_DATATABLES / "Kayoro_30min.csv"
DEFAULT_DAILY = FINAL_DATATABLES / "Kayoro_daily.csv"

CUTOFF = pd.Timestamp("2016-10-01")
WD_MIN = 196.0
WD_MAX = 228.0
MISSING_CODE = -9999
COL_QC = "QC_wind_sector_kayoro"


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


def _parse_timestamp_series(ts_raw: pd.Series, daily: bool) -> pd.Series:
    ts_raw = ts_raw.astype(str).str.strip()
    if daily:
        return pd.to_datetime(ts_raw, format="%Y%m%d", errors="coerce")
    return pd.to_datetime(ts_raw, format="%Y%m%d%H%M%S", errors="coerce")


def _compute_qc(ts: pd.Series, wd: pd.Series) -> pd.Series:
    wd_num = pd.to_numeric(wd, errors="coerce")
    before = ts < CUTOFF
    # Fehlend: NaN (z. B. aus Datei- -9999 via na_values) oder explizite Sentinels
    wd_missing = wd_num.isna() | (wd_num == MISSING_CODE) | (wd_num == -99999)
    in_sector = (wd_num >= WD_MIN) & (wd_num <= WD_MAX)

    qc = pd.Series(MISSING_CODE, index=wd.index, dtype=np.int64)
    after = ~before
    m_valid = after & ~wd_missing
    qc.loc[m_valid & in_sector] = 1
    qc.loc[m_valid & ~in_sector] = 0
    return qc


def process_file(path: Path, daily: bool, output: Path | None) -> Path:
    header_lines, df = _read_essd_csv(path)
    if "TIMESTAMP" not in df.columns:
        raise ValueError(f"{path}: TIMESTAMP fehlt")
    if "WD" not in df.columns:
        raise ValueError(f"{path}: WD fehlt")

    n_data_cols = len(df.columns)
    u_parts = [x.strip() for x in header_lines[1].split(",")]
    if len(u_parts) != n_data_cols:
        raise ValueError(
            f"{path}: Header/Units-Spaltenanzahl passt nicht ({n_data_cols} vs {len(u_parts)})"
        )

    ts = _parse_timestamp_series(df["TIMESTAMP"], daily=daily)
    df[COL_QC] = _compute_qc(ts, df["WD"])

    out_path = output
    if out_path is None:
        out_path = path.parent / f"{path.stem}_QC_wind_sector{path.suffix}"

    # ESSD: zwei Headerzeilen + Daten
    u_parts.append("adimensional")
    with out_path.open("w", encoding="utf-8", newline="") as f:
        f.write(header_lines[0] + "," + COL_QC + "\n")
        f.write(",".join(u_parts) + "\n")
    df.to_csv(out_path, mode="a", index=False, header=False, lineterminator="\n")
    return out_path


def main() -> None:
    p = argparse.ArgumentParser(description="QC_wind_sector_kayoro zu Kayoro-Dateien hinzufügen")
    p.add_argument(
        "--path-30min",
        dest="path_30min",
        type=Path,
        default=DEFAULT_30MIN,
        help=f"Pfad Kayoro_30min.csv (default: {DEFAULT_30MIN})",
    )
    p.add_argument(
        "--path-daily",
        dest="path_daily",
        type=Path,
        default=DEFAULT_DAILY,
        help=f"Pfad Kayoro_daily.csv (default: {DEFAULT_DAILY})",
    )
    p.add_argument(
        "--output-30min",
        type=Path,
        default=None,
        help="Ausgabe 30min (default: <name>_QC_wind_sector.csv neben Eingabe)",
    )
    p.add_argument(
        "--output-daily",
        type=Path,
        default=None,
        help="Ausgabe daily (default: <name>_QC_wind_sector.csv neben Eingabe)",
    )
    p.add_argument(
        "--in-place",
        action="store_true",
        help="Eingabedateien überschreiben (Vorsicht)",
    )
    args = p.parse_args()

    out30 = args.path_30min if args.in_place else args.output_30min
    outdaily = args.path_daily if args.in_place else args.output_daily

    p1 = process_file(args.path_30min, daily=False, output=out30)
    p2 = process_file(args.path_daily, daily=True, output=outdaily)
    print(f"✓ 30min: {p1}")
    print(f"✓ daily: {p2}")


if __name__ == "__main__":
    main()
