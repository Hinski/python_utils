from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

#FILE = Path("/Users/hingerl-l/Data/Janga/raw/CR6Janga_Public.dat")
FILE = Path("/Users/hingerl-l/Data/Janga/raw/CR6Janga_Flux_AmeriFluxFormat.dat")

VARS_TO_PLOT = ["SWC_1_1_1", "SWC_2_1_1", "SWC_3_1_1"]
YLIMS = {
    "SWC_1_1_1": (-1, 100),
    "SWC_2_1_1": (-1, 100),
    "SWC_3_1_1": (-1, 100),
}

def read_toa5_cr6_fast(path: Path, vars_to_keep: list[str], resample_rule="30min") -> pd.DataFrame:
    usecols = ["TIMESTAMP"] + vars_to_keep  # nur das laden, was du wirklich brauchst

    df = pd.read_csv(
        path,
        sep=",",
        header=1,
        skiprows=[2, 3],
        quotechar='"',
        engine="c",                 # deutlich schneller
        usecols=usecols,            # MASSIVER Speedup
        na_values=["NAN", "NaN", "nan", "-99999", "-6999", ""],
        low_memory=False,
    )

    # TIMESTAMP robust parsen (Millisekunden + unregelmäßig ok)
    df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"], errors="coerce")
    df = df.dropna(subset=["TIMESTAMP"]).set_index("TIMESTAMP")
    df.index.name = "datetime"

    # numerisch
    for c in vars_to_keep:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # sortieren + duplikate raus
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="first")]

    # resample (mean passt für Bodenwärmefluss-ähnliche Größen)
    df = df.resample(resample_rule).mean()

    return df

def plot_subplots(df: pd.DataFrame, vars_to_plot: list[str], ylims=None):
    n = len(vars_to_plot)
    fig, axes = plt.subplots(n, 1, figsize=(14, 3*n), sharex=True)
    if n == 1:
        axes = [axes]

    for ax, var in zip(axes, vars_to_plot):
        ax.plot(df.index, df[var])
        ax.set_ylabel(var)
        ax.grid(True)
        if ylims and var in ylims:
            ax.set_ylim(*ylims[var])

    axes[-1].set_xlabel("Time")
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    df = read_toa5_cr6_fast(FILE, VARS_TO_PLOT, resample_rule="30min")

    print("Index dtype:", df.index.dtype)
    print("Zeitbereich:", df.index.min(), "→", df.index.max())

    plot_subplots(df, VARS_TO_PLOT, YLIMS)
