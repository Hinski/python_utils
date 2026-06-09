#!/usr/bin/env python3
"""
Repair combined TK3 files (mixed 61/62 columns, wrong header, trailing commas)
and convert them into a clean GFE-ready parquet dataset.

Usage:
    python3 tk3_repair_and_convert.py input.csv output_basename

Examples:
    python3 tk3_repair_and_convert.py input.csv Nazinga_TK3
"""

import pandas as pd
import numpy as np
from pathlib import Path


# ---------------------------------------------------------------------
# Correct TK3 header (61 cols)
# ---------------------------------------------------------------------
TK3_HEADER = [
    'T_begin','T_end','u[m/s]','v[m/s]','w[m/s]','Ts[°C]','Tp[°C]',
    'a[g/m³]','CO2[mmol/m³]','T_ref[°C]','a_ref[g/m³]','p_ref[hPa]',
    'Var[u]','Var[v]','Var[w]','Var[Ts]','Var[Tp]','Var[a]','Var[CO2]',
    "Cov[u'v']","Cov[v'w']","Cov[u'w']","Cov[u'Ts']","Cov[v'Ts']","Cov[w'Ts']",
    "Cov[u'Tp']","Cov[v'Tp']","Cov[w'Tp']","Cov[u'a']","Cov[v'a']","Cov[w'a']",
    "Cov[u'CO2']","Cov[v'CO2']","Cov[w'CO2']",'???','dir[°]','ustar[m/s]',
    'HTs[W/m²]','HTp[W/m²]','LvE[W/m²]','z/L','z/L-virt','Flag(ustar)',
    'Flag(HTs)','Flag(HTp)','Flag(LvE)','Flag(wCO2)','T_mid',
    'FCstor[mmol/m²s]','NEE[mmol/m²s]','Footprint_trgt_1','Footprint_trgt_2',
    'Footprnt_xmax[m]','r_err_ustar[%]','r_err_HTs[%]','r_err_LvE[%]',
    'r_err_co2[%]','noise_ustar[%]','noise_HTs[%]','noise_LvE[%]',
    'noise_co2[%]','Filler_to_reach61'
]
N_COLS = len(TK3_HEADER)


# ---------------------------------------------------------------------
# Normalize ANY TK3 CSV to 61 columns
# ---------------------------------------------------------------------
def load_and_fix_tk3(path: Path) -> pd.DataFrame:
    print(f"🔍 Loading TK3 file: {path}")

    df = pd.read_csv(
        path,
        header=None,
        sep=",",
        engine="python",
        dtype=str,
        on_bad_lines="skip"
    )

    print(f"  → Loaded shape: {df.shape}")

    # Remove header-like repeated rows
    header_mask = df.iloc[:, 0].astype(str).str.contains("T_begin", na=False)
    if header_mask.any():
        print(f"⚠️ Removing {header_mask.sum()} duplicated header rows.")
        df = df[~header_mask]

    # Normalize column count
    n = df.shape[1]
    if n > N_COLS:
        print(f"⚠️ Cutting columns: {n} → {N_COLS}")
        df = df.iloc[:, :N_COLS]
    if n < N_COLS:
        print(f"⚠️ Padding columns: {n} → {N_COLS}")
        for _ in range(N_COLS - n):
            df[df.shape[1]] = np.nan

    # Assign header
    df.columns = TK3_HEADER

    # Parse timestamps
    df["T_begin"] = pd.to_datetime(df["T_begin"], errors="coerce")
    df["T_end"]   = pd.to_datetime(df["T_end"],   errors="coerce")

    # Remove invalid timestamps
    before = len(df)
    df = df.dropna(subset=["T_begin", "T_end"])
    after = len(df)
    if before != after:
        print(f"⚠️ Dropped {before - after} invalid timestamp rows.")

    # Convert all numeric columns
    for col in df.columns:
        if col not in ["T_begin", "T_end"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    print(f"✅ Final shape: {df.shape}")
    return df


# ---------------------------------------------------------------------
# File writer
# ---------------------------------------------------------------------
def repair_and_export(input_path, output_base):
    input_path = Path(input_path)
    output_base = Path(output_base)

    # If user provides a file (like .parquet), strip suffix → we need only the basename
    if output_base.suffix != "":
        output_base = output_base.with_suffix("")  # remove extension

    df = load_and_fix_tk3(input_path)

    # Clean CSV
    clean_csv = output_base.as_posix() + "_clean.csv"
    df.to_csv(clean_csv, index=False)
    print(f"💾 Clean CSV written → {clean_csv}")

    # Parquet
    parquet_path = output_base.as_posix() + ".parquet"
    df.to_parquet(parquet_path, index=False)
    print(f"💾 Parquet written → {parquet_path}")

    print("\n🎉 DONE — TK3 repaired & GFE-ready!")
    return df


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python3 tk3_repair_and_convert.py input.csv output_basename")
        exit(1)

    repair_and_export(sys.argv[1], sys.argv[2])
