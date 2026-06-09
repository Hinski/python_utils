import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

plt.rcParams["figure.figsize"] = (14, 6)
plt.rcParams["axes.grid"] = True


def load_tk3(path):
    """Load TK3 combined file robustly and convert -9999.9 patterns to NaN."""

    df = pd.read_csv(path, header=0, sep=",", engine="python", dtype=str)

    # --- Convert timestamps ---
    for col in ["T_begin", "T_end"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)

    # --- Set main time axis ---
    if "T_end" in df.columns:
        df["time"] = df["T_end"]
    else:
        df["time"] = df["T_begin"]

    # --- Fix TK3 NA patterns ---
    # TK3 missing values are always like:  -9999.9003906  or -9999.8999 etc.
    na_patterns = ["-9999", "-9999.", "-9999.9", "-9999.90", "-9999.900", "-9999.90039"]

    for col in df.columns:
        if col not in ["T_begin", "T_end", "time"]:
            series = df[col]

            # Replace all patterns by real NaN
            for patt in na_patterns:
                series = series.str.replace(patt, "", regex=False)

            # Empty strings → NaN
            df[col] = series.replace("", np.nan)

            # Convert to numeric
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Sort final DF
    return df.sort_values("time")


def show_plot(df, col):
    """Show a time series plot for the given variable."""
    if col not in df.columns:
        print(f"⚠️ Missing variable: {col}")
        return

    if df[col].dropna().empty:
        print(f"⚠️ Variable {col} is empty or all NA")
        return

    plt.figure()
    plt.plot(df["time"], df[col], lw=0.6)
    plt.title(col)
    plt.xlabel("Time")
    plt.ylabel(col)
    plt.tight_layout()
    plt.show()


def full_quicklook(path):
    path = Path(path)
    print(f"🔍 Loading TK3 data: {path}")

    df = load_tk3(path)
    print(f"→ Loaded rows: {df.shape[0]}, columns: {df.shape[1]}")

    variables = [
        "u[m/s]", "v[m/s]", "w[m/s]",
        "Ts[°C]", "Tp[°C]", "a[g/m³]", "CO2[mmol/m³]",
        "Var[u]", "Var[v]", "Var[w]", "Var[Ts]", "Var[a]", "Var[CO2]",
        "Cov[w'Ts']", "Cov[w'a']", "Cov[w'CO2']",
        "HTs[W/m²]", "LvE[W/m²]", "NEE[mmol/m²s]",
        "ustar[m/s]", "dir[°]", "z/L", "z/L-virt",
        "Footprint_trgt_1", "Footprint_trgt_2", "Footprnt_xmax[m]",
    ]

    print("\n📈 Showing time series...")

    for col in variables:
        show_plot(df, col)

    print("\n🎉 Done — all available variables plotted.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python tk3_quicklook_show.py <path_to_csv>")
        exit(1)

    full_quicklook(sys.argv[1])
