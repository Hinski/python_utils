#!/usr/bin/env python3
"""
Erzeugt aus ESSD ``final_datatables``-CSV (2-Zeilen-Header) jeweils eine NetCDF-Datei.

- Zeitdimension aus Spalte ``TIMESTAMP`` (30-min: ``%Y%m%d%H%M%S``, täglich: ``%Y%m%d``).
- Datenvariablen: alle übrigen Spalten, Einheiten aus der zweiten Headerzeile (Attribut ``units``).
- Fehlwerte ``-9999`` / ``-99999`` wie in den CSVs (float32, dokumentiert als ``missing_value``).

Standard:
  Eingabe  ``.../final_datatables/*.csv``
  Ausgabe  gleicher Ordner, Endung ``.nc`` (z. B. ``Gorigo_30min.nc``).

Voraussetzungen
---------------
  pip install pandas xarray netCDF4

Verwendung
----------
  python export_final_datatables_netcdf.py
  python export_final_datatables_netcdf.py --dry-run
  python export_final_datatables_netcdf.py --output-dir /pfad/zu/nc
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import xarray as xr
except ImportError:
    xr = None

FINAL_DATATABLES = Path("/Users/hingerl-l/Data/essd_data_tables/final_datatables")
TS_COL = "TIMESTAMP"
MISSING_FLOAT = np.float32(-9999.0)

# Wie in anderen ESSD-Skripten: echte Zellenlücken; Sentinels in der CSV bleiben Zahlen
_READ_NA_VALUES = ["", "NAN", "N/A", "nan", "NA", "None", "none"]


def _read_essd_csv(path: Path) -> tuple[list[str], list[str], pd.DataFrame]:
    with path.open("r", encoding="utf-8") as f:
        header_line = f.readline().rstrip("\n")
        units_line = f.readline().rstrip("\n")
    var_names = [c.strip() for c in header_line.split(",")]
    u_parts = [x.strip() for x in units_line.split(",")]
    df = pd.read_csv(
        path,
        skiprows=2,
        header=None,
        names=var_names,
        low_memory=False,
        na_values=_READ_NA_VALUES,
        keep_default_na=True,
    )
    return var_names, u_parts, df


def _is_daily_csv(path: Path) -> bool:
    return "daily" in path.name.lower()


def _parse_time(series: pd.Series, daily: bool) -> pd.Series:
    s = series.astype(str).str.strip()
    if daily:
        return pd.to_datetime(s, format="%Y%m%d", errors="coerce")
    return pd.to_datetime(s, format="%Y%m%d%H%M%S", errors="coerce")


def _safe_nc_name(raw: str, used: dict[str, str]) -> str:
    """NetCDF-kompatible Namen; Kollisionen mit Suffix _2, _3 auflösen."""
    s = re.sub(r"[^0-9a-zA-Z_]", "_", raw.strip())
    if not s:
        s = "unknown"
    if s[0].isdigit():
        s = "v_" + s
    base = s
    n = 1
    while s in used and used[s] != raw:
        n += 1
        s = f"{base}_{n}"
    used[s] = raw
    return s


def _dataframe_to_dataset(
    df: pd.DataFrame,
    units_row: list[str],
    var_names: list[str],
    daily: bool,
    source_csv: Path,
) -> xr.Dataset:
    if TS_COL not in df.columns:
        raise ValueError(f"{source_csv}: Spalte {TS_COL!r} fehlt")
    if len(var_names) != len(units_row):
        raise ValueError(f"{source_csv}: Anzahl Namen ({len(var_names)}) ≠ Anzahl Einheiten ({len(units_row)})")

    units_map = {var_names[i]: units_row[i] for i in range(len(var_names))}

    t = _parse_time(df[TS_COL], daily)
    valid = t.notna()
    if not bool(valid.any()):
        raise ValueError(f"{source_csv}: keine gültigen Zeitstempel")
    df = df.loc[valid].copy()
    t = t.loc[valid]
    if t.duplicated().any():
        raise ValueError(f"{source_csv}: doppelte TIMESTAMP-Werte nach Filter")

    time = pd.DatetimeIndex(t).tz_localize(None)
    used_nc: dict[str, str] = {}
    data_vars: dict = {}

    for col in df.columns:
        if col == TS_COL:
            continue
        nc_name = _safe_nc_name(col, used_nc)
        ser = pd.to_numeric(df[col], errors="coerce")
        arr = ser.to_numpy(dtype=np.float64)
        arr[~np.isfinite(arr)] = np.float64(MISSING_FLOAT)
        for miss in (-9999.0, -99999.0, 7999.0):
            arr = np.where(arr == miss, MISSING_FLOAT, arr)
        arr = arr.astype(np.float32)
        data_vars[nc_name] = (["time"], arr)

    ds = xr.Dataset(
        data_vars=data_vars,
        coords={"time": ("time", time)},
    )

    # calendar wird von xarray bei Datetime-Koordinaten gesetzt — nicht doppeln
    ds["time"].attrs.update(
        standard_name="time",
        long_name="time",
    )

    for nc_name, orig in used_nc.items():
        units = units_map.get(orig, "")
        ds[nc_name].attrs["long_name"] = orig
        if units:
            ds[nc_name].attrs["units"] = units
        ds[nc_name].attrs["missing_value"] = float(MISSING_FLOAT)

    ds.attrs.update(
        title=f"ESSD final_datatables — {source_csv.stem}",
        source=f"file://{source_csv.resolve()}",
        featureType="timeSeries",
    )
    return ds


def export_one(
    csv_path: Path,
    out_path: Path,
    *,
    compression: bool,
    float64_store: bool,
) -> None:
    if xr is None:
        raise RuntimeError("xarray fehlt: pip install xarray netCDF4")
    var_names, units_row, df = _read_essd_csv(csv_path)
    daily = _is_daily_csv(csv_path)
    ds = _dataframe_to_dataset(df, units_row, var_names, daily, csv_path)

    if float64_store:
        for v in ds.data_vars:
            ds[v] = ds[v].astype(np.float64)

    encoding: dict = {}
    enc_base: dict = {"zlib": compression, "complevel": 4} if compression else {}
    for v in ds.data_vars:
        enc = dict(enc_base)
        fv = np.float64(-9999.0) if float64_store else MISSING_FLOAT
        enc["_FillValue"] = fv
        enc["dtype"] = "float64" if float64_store else "float32"
        encoding[v] = enc

    out_path.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(out_path, engine="netcdf4", encoding=encoding)


def main() -> None:
    p = argparse.ArgumentParser(description="final_datatables CSV → NetCDF (ESSD-Format)")
    p.add_argument(
        "--data-dir",
        type=Path,
        default=FINAL_DATATABLES,
        help=f"CSV-Verzeichnis (default: {FINAL_DATATABLES})",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Zielverzeichnis für .nc (default: gleich wie --data-dir)",
    )
    p.add_argument("--glob", dest="glob_pat", default="*.csv", help='Dateimuster (default: \"*.csv\")')
    p.add_argument("--dry-run", action="store_true", help="Nur anzeigen, nicht schreiben")
    p.add_argument("--no-compression", action="store_true", help="Kein zlib (schnelleres Schreiben)")
    p.add_argument(
        "--float64",
        action="store_true",
        help="float64 statt float32 (größere Dateien)",
    )
    args = p.parse_args()

    if xr is None:
        raise SystemExit("xarray fehlt: pip install xarray netCDF4")

    data_dir = args.data_dir
    if not data_dir.is_dir():
        raise SystemExit(f"Kein Verzeichnis: {data_dir}")

    out_root = args.output_dir if args.output_dir is not None else data_dir
    compression = not args.no_compression

    paths = sorted(data_dir.glob(args.glob_pat))
    skipped = 0
    n_ok = 0
    for csv_path in paths:
        if not csv_path.is_file():
            continue
        if csv_path.suffix.lower() != ".csv":
            continue
        if "_na9999" in csv_path.stem or csv_path.name.endswith(".bak"):
            skipped += 1
            continue

        out_path = out_root / f"{csv_path.stem}.nc"
        if args.dry_run:
            print(f"  [dry-run] {csv_path.name} → {out_path.name}")
            n_ok += 1
            continue
        try:
            export_one(
                csv_path,
                out_path,
                compression=compression,
                float64_store=args.float64,
            )
        except Exception as e:
            print(f"✗ {csv_path.name}: {e}")
            continue
        print(f"✓ {csv_path.name} → {out_path}")
        n_ok += 1

    extra = f", {skipped} übersprungen (_na9999/.bak)" if skipped else ""
    print(f"Fertig: {n_ok} Datei(en){extra}.")


if __name__ == "__main__":
    main()
