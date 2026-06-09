#!/usr/bin/env python3
"""
Kopie von seasonal_carbon_uptake.py für ESSD final_datatables.

Verwendet 30-min Daten aus:
  /Users/hingerl-l/Data/essd_data_tables/final_datatables
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

import seasonal_carbon_uptake as base

# -----------------------------------------------------------------------------
# Input override: final_datatables
# -----------------------------------------------------------------------------
FINAL_ESSD_DIR = Path("/Users/hingerl-l/Data/essd_data_tables/final_datatables")
DAILY_STAT_METHOD = "mean"  # "median" oder "mean"


def _candidate_paths(station: str) -> list[Path]:
    """Preferred filename order for final datatables."""
    return [
        FINAL_ESSD_DIR / f"{station}_30min.csv",
        FINAL_ESSD_DIR / f"{station}_essd_30min_clean.csv",
        FINAL_ESSD_DIR / f"{station}_essd_30min.csv",
    ]


def load_all_variables_from_final_datatables(station: str) -> pd.DataFrame | None:
    """
    Load ESSD-style 30-min CSV (2-line header) from final_datatables.
    Expected first column: TIMESTAMP (YYYYMMDDHHMMSS).
    """
    path = None
    for p in _candidate_paths(station):
        if p.exists():
            path = p
            break
    if path is None:
        print(f"[WARN] Missing file in final_datatables for {station}")
        return None

    with path.open("r", encoding="utf-8") as f:
        header_line = f.readline().strip()
        _units_line = f.readline().strip()
    var_names = [c.strip() for c in header_line.split(",")]

    df = pd.read_csv(
        path,
        skiprows=2,
        header=None,
        names=var_names,
        low_memory=False,
        na_values=[-9999, "-9999", "-9999.0", -99999, "7999", "NAN", "nan", "NA"],
    )
    if "TIMESTAMP" not in df.columns or df["TIMESTAMP"].empty:
        print(f"[WARN] No TIMESTAMP column: {path}")
        return None

    ts = pd.to_datetime(df["TIMESTAMP"], format="%Y%m%d%H%M%S", errors="coerce")
    df = df.drop(columns=["TIMESTAMP"])
    df.index = ts
    df = df[df.index.notna()].sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


def main() -> None:
    # Monkey-patch loader in base script and run with final_datatables settings.
    base.load_all_variables = load_all_variables_from_final_datatables
    # In final_datatables heißt das NEE-QC-Flag CO2_QC.
    base.QC_FLAG_DEFAULT = "CO2_QC"
    # Optional: tägliche Aggregation als mean statt median.
    base.DAILY_STAT_METHOD = DAILY_STAT_METHOD
    base.main()


if __name__ == "__main__":
    main()

