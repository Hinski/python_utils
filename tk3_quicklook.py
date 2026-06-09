#!/usr/bin/env python3
"""
Quicklook diagnostics for repaired TK3 parquet files (GFE-ready).

Usage:
    python3 tk3_quicklook.py Nazinga_TK3_turbulence.parquet
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path


PLOT_VARS = {
    "ustar[m/s]": "Friction Velocity u*",
    "HTs[W/m²]": "Sensible Heat Flux H",
    "LvE[W/m²]": "Latent Heat Flux LE",
    "dir[°]": "Wind Direction",
    "z/L": "Stability Parameter z/L",
    "Var[u]": "Variance u",
    "Var[w]": "Variance w",
    "Var[Ts]": "Variance Ts",
    "NEE[mmol/m²s]": "NEE",
}


def quicklook(parquet_path):

    parquet_path = Path(parquet_path)
    outdir = parquet_path.parent
    print(f"🔍 Loading TK3 parquet: {parquet_path}")

    df = pd.read_parquet(parquet_path)
    print(f"Loaded {df.shape[0]} rows, {df.shape[1]} columns.")

    # ---- pick time column ----
    if "T_end" in df.columns:
        timecol = "T_end"
    elif "time_start" in df.columns:
        timecol = "time_start"
    else:
        raise RuntimeError("No valid time column found (T_end or time_start)")

    print(f"🕒 Using time column: {timecol}")

    df = df.sort_values(timecol)

    # ---- convert numeric ----
    for col in df.columns:
        if col not in ["T_begin", "T_end", "time_start"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # ---- plotting ----
    for var, title in PLOT_VARS.items():
        if var not in df.columns:
            print(f"⚠️ Skipping {var} (not found)")
            continue

        if df[var].dropna().empty:
            print(f"⚠️ {var} contains no data — skipping")
            continue

        print(f"📈 Plotting {var} → {title}")

        fig, ax = plt.subplots(figsize=(14, 4))
        ax.plot(df[timecol], df[var], linewidth=0.7)
        ax.set_title(title)
        ax.set_ylabel(var)
        ax.grid(True)

        fname = outdir / f"{parquet_path.stem}_{var.replace('/', '-')}.png"
        plt.savefig(fname, dpi=150, bbox_inches="tight")
        print(f"  → saved {fname}")

        plt.show()

    print("\n🎉 Quicklook finished.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python3 tk3_quicklook.py <TK3_parquet_file>")
        exit(1)

    quicklook(sys.argv[1])
