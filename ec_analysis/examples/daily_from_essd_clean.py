#!/usr/bin/env python3
"""
Daily aggregation from ESSD 30-min clean tables.

Input (per station):
  /Users/hingerl-l/Data/essd_data_tables/{station}_essd_30min_clean.csv

Rules:
  - Apply QC filtering BEFORE aggregation: for variables that have a matching *_QC
    column, only keep values where QC <= 1 (QC > 1 or missing QC => value set to NaN).
  - Daily aggregation:
      * Sum for: P, ET
      * Mean for: all other (non-QC) variables
    For sums we keep NaN if an entire day is missing (min_count=1).

Output (per station):
  /Users/hingerl-l/Data/essd_data_tables/{station}_essd_daily_clean.csv

Format:
  - Line 1: variable names (TIMESTAMP + variables)
  - Line 2: units (TIMESTAMP unit = YYYYMMDD)
  - Following lines: data (missing values as -9999)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

DATA_BASE = Path("/Users/hingerl-l/Data")
ESSD_DIR = DATA_BASE / "essd_data_tables"
MISSING_VALUE = -9999

STATIONS = ["Nazinga", "Kayoro", "Sumbrungu", "Gorigo", "Janga", "Mole"]

# Variables to sum daily (everything else -> mean)
DAILY_SUM_VARS = {"P", "ET"}


def load_essd_csv(path: Path) -> tuple[pd.DataFrame, list[str], list[str]] | None:
    """Load ESSD CSV with 2-line header. Returns (df, var_names, units)."""
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        header_line = f.readline().strip()
        units_line = f.readline().strip()
    var_names = [c.strip() for c in header_line.split(",")]
    units = [u.strip() for u in units_line.split(",")]
    if len(units) < len(var_names):
        units.extend([""] * (len(var_names) - len(units)))
    else:
        units = units[: len(var_names)]

    df = pd.read_csv(
        path,
        skiprows=2,
        header=None,
        names=var_names,
        low_memory=False,
        na_values=[MISSING_VALUE, str(MISSING_VALUE), "-9999.0", -99999, "7999", "nan", "NAN"],
    )
    if "TIMESTAMP" not in df.columns or df["TIMESTAMP"].empty:
        return None
    ts = pd.to_datetime(df["TIMESTAMP"], format="%Y%m%d%H%M%S", errors="coerce")
    df = df.drop(columns=["TIMESTAMP"])
    df.index = ts
    df = df[df.index.notna()].sort_index()
    return df, var_names, units


def write_essd_daily_csv(path: Path, df_daily: pd.DataFrame, var_names: list[str], var_units: list[str]) -> None:
    """Write ESSD-style CSV with TIMESTAMP as YYYYMMDD and -9999 for missing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df_out = df_daily.copy()
    df_out = df_out.replace({np.nan: MISSING_VALUE})

    data_cols = [c for c in var_names if c != "TIMESTAMP"]
    df_out = df_out.reindex(columns=data_cols)

    with path.open("w", encoding="utf-8") as f:
        f.write(",".join(var_names) + "\n")
        f.write(",".join(var_units) + "\n")
        for idx, row in df_out.iterrows():
            ts_str = idx.strftime("%Y%m%d")
            values = [ts_str]
            for c in data_cols:
                v = row.get(c, MISSING_VALUE)
                values.append(str(MISSING_VALUE) if (pd.isna(v) or v == MISSING_VALUE) else str(v))
            f.write(",".join(values) + "\n")


def apply_qc_filtering(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each variable X with a QC column X_QC present:
      keep X only where X_QC <= 1; else set X to NaN.
    """
    df = df.copy()
    qc_cols = [c for c in df.columns if c.endswith("_QC")]
    for qc_col in qc_cols:
        base = qc_col[: -len("_QC")]
        if base not in df.columns:
            continue
        qc = pd.to_numeric(df[qc_col], errors="coerce")
        bad = (qc > 1) | qc.isna()
        df.loc[bad, base] = np.nan
    return df


def daily_aggregate(df: pd.DataFrame, units_by_var: dict[str, str]) -> pd.DataFrame:
    """Aggregate to daily with mean/sum rules. QC columns are excluded from output."""
    # Exclude QC columns from output; QC is only used for filtering.
    data_cols = [c for c in df.columns if not c.endswith("_QC")]
    out = pd.DataFrame(index=df.index, data={c: pd.to_numeric(df[c], errors="coerce") for c in data_cols})

    agg: dict[str, object] = {}
    for c in out.columns:
        if c in DAILY_SUM_VARS:
            agg[c] = lambda x: x.sum(min_count=1)
        else:
            agg[c] = "mean"
    daily = out.resample("D").agg(agg)
    return daily


def main() -> None:
    for station in STATIONS:
        in_path = ESSD_DIR / f"{station}_essd_30min_clean.csv"
        out_path = ESSD_DIR / f"{station}_essd_daily_clean.csv"

        result = load_essd_csv(in_path)
        if result is None:
            print(f"{station}: missing or unreadable: {in_path}", file=sys.stderr)
            continue
        df, var_names_30, var_units_30 = result

        units_by_var = dict(zip(var_names_30, var_units_30))
        df = apply_qc_filtering(df)
        df_daily = daily_aggregate(df, units_by_var)

        # Output header: TIMESTAMP + all non-QC variables, in original order if possible
        out_vars = ["TIMESTAMP"] + [v for v in var_names_30 if v != "TIMESTAMP" and not v.endswith("_QC") and v in df_daily.columns]
        # Add any remaining columns (if present but not in header order)
        for c in df_daily.columns:
            if c not in out_vars and c != "TIMESTAMP":
                out_vars.append(c)

        out_units = ["YYYYMMDD"] + [units_by_var.get(v, "") for v in out_vars[1:]]
        write_essd_daily_csv(out_path, df_daily, out_vars, out_units)
        print(f"{station}: saved {len(df_daily)} days -> {out_path}")


if __name__ == "__main__":
    main()

