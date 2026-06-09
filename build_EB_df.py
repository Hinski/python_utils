#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Build unified Energy Balance DataFrames for all active stations.
No plotting – only clean, standardized DataFrames saved to disk.
Author: Poldi
"""

import pandas as pd
import os


# ---------------------------------------------------------------------
# Helper: safely slice and clean time series
# ---------------------------------------------------------------------
def safe_slice(series, start, end):
    """Safely slice a time series by date range with sorted, unique index."""
    if not isinstance(series.index, pd.DatetimeIndex):
        series.index = pd.to_datetime(series.index, errors="coerce")

    series = series.dropna().sort_index()
    series = series[~series.index.duplicated(keep="first")]

    mask = (series.index >= pd.to_datetime(start)) & (series.index <= pd.to_datetime(end))
    return series.loc[mask]


# ---------------------------------------------------------------------
# Builder: create DataFrame with all EB components
# ---------------------------------#------------------------------------
def build_energy_balance_df(
    SW_in, SW_out, LW_in, LW_out, LE, H, G, Delta,
    start, end, site_name
) -> pd.DataFrame:
    """Return cleaned DataFrame with all energy balance components."""

    df = pd.DataFrame({
        "SW_in": safe_slice(SW_in, start, end),
        "SW_out": safe_slice(SW_out, start, end),
        "LW_in": safe_slice(LW_in, start, end),
        "LW_out": safe_slice(LW_out, start, end),
        "LE": safe_slice(LE, start, end),
        "H": safe_slice(H, start, end),
        "G": safe_slice(G, start, end),
        "Delta": safe_slice(Delta, start, end)
    }).dropna()

    if df.empty:
        print(f"⚠️ Warning: No overlapping data for {site_name} ({start}–{end})")
        return pd.DataFrame()

    # Derived components
    df["Rn"] = (df["SW_in"] - df["SW_out"]) + (df["LW_in"] - df["LW_out"])
    df["Residual"] = df["Rn"] - (df["LE"] + df["H"] + df["G"] + df["Delta"])

    df.attrs.update({"site": site_name, "start": start, "end": end})
    print(f"✅ {site_name}: Energy balance DataFrame created ({len(df)} records)")
    return df



# =========================================================
# Function to plot the control variables of the ffp input
# =========================================================

def plot_control_vars(df, site):
    """Plot core footprint control variables (u*, L, z/L, WS, WD, h_veg, TA)."""
    vars_to_plot = ["u_star", "L", "z_L", "WS", "WD", "h_veg"]
    titles = ["Friction velocity u*", "Obukhov length L", "z/L",
              "Wind speed", "Wind direction", "Vegetation height"]

    fig, axes = plt.subplots(3, 2, figsize=(12, 8), sharex=True)
    axes = axes.flatten()

    for ax, var, title in zip(axes, vars_to_plot, titles):
        if var in df.columns:
            ax.plot(df.index, df[var], color="black", lw=0.6)
            ax.set_title(title, fontsize=11)
            ax.grid(True, alpha=0.3)
        else:
            ax.text(0.5, 0.5, f"{var} not found", ha="center", va="center")

    fig.suptitle(f"Footprint Control Variables – {site}", fontsize=14, weight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.show()
