#!/usr/bin/env python3
"""
Seasonal carbon uptake (NEE) climatology across stations (ESSD-style).

Creates a compact 2×3 subplot figure:
- Each panel: climatological seasonal cycle of daily NEE (median across years) vs DOY,
  smoothed with a rolling median (default: 15 days, circular).
- Optional shading: interquartile range (IQR) across years (per DOY).
- Optional secondary axis: precipitation climatology (daily median and/or 30-day running sum).

Inputs:
  {OUTPUT_BASE}/{station}/processed/all/{station}_all_variables_30min.csv
  (output from collect_all_variables_30min.py)

Outputs:
  seasonal_nee_climatology_2x3.png

Notes:
- This script tries to find a CO2 flux column using common aliases. If your file uses a
  different name, add it to CO2_FLUX_ALIASES below.
- QC filtering: applies QC<=1 using qc_o2_flux (or station-specific flag if provided).
- Sign convention is NOT altered: negative values may indicate uptake (depending on your convention).
- Year filtering: NEE_STATION_YEAR_RANGES (NEE/IQR/VWC) and P_STATION_YEAR_RANGES (precip only) are independent.
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# =============================================================================
# CONFIG
# =============================================================================
OUTPUT_BASE = Path("/Users/hingerl-l/Data")
STATIONS = ["Nazinga", "Kayoro", "Sumbrungu", "Mole", "Janga", "Gorigo"]
STATION_LABELS = {
    "Nazinga": "Nazinga (protected forest)",
    "Mole": "Mole (managed forest)",
    "Kayoro": "Kayoro (cropland)",
    "Janga": "Janga (rainfed rice field)",
    "Sumbrungu": "Sumbrungu (degr. grassland)",
    "Gorigo": "Gorigo (semi-degr. grassland)",
}

OUT_PNG = Path("seasonal_nee_climatology_2x3.png")

# Niederschlagsvariable pro Station (wie event_scale_water_balance.py)
P_COL_BY_STATION = {
    "Sumbrungu": "P_tb",
    "Nazinga": "P_tb",
    "Kayoro": "P_tb",
    "Gorigo": "P_pl",
    "Janga": "P",
    "Mole": "P_tb",
}

# VWC-Schichten und Skala (wie event_scale_water_balance.py)
VWC_LAYER_COLS: list[tuple[list[str], str]] = [
    (["VWC_1", "VW_1_Avg", "SWC_1_1_1", "SWC_1", "VWC_Avg"], "θ₃cm"),
    (["VWC_2", "VW_2_Avg", "SWC_2_1_1", "SWC_2", "VWC_2_Avg"], "θ₁₀cm"),
    (["VWC_3", "VW_3_Avg", "SWC_3_1_1", "SWC_3", "VWC_3_Avg"], "θ₃₅cm"),
]
VWC_SCALE: dict[str, float] = {"Janga": 100.0}
STATIONS_WITH_3_VWC_LAYERS = frozenset({"Mole", "Janga"})

# --- CO2 flux / NEE aliases (extend if needed)
CO2_FLUX_ALIASES = [
    "NEE", "nee", "co2_flux", "CO2_flux", "Fc", "FC", "Fco2", "FCO2",
    "co2", "CO2", "qc_o2_flux"  # (last one is flag; ignored by getter)
]

# QC flag mapping (EddyPro-style)
QC_FLAG_DEFAULT = "qc_o2_flux"
QC_MAX = 1
APPLY_QC = True

# Fallback-P-Spalten falls Station nicht in P_COL_BY_STATION
P_ALIASES_FALLBACK = ["P", "P_tb", "P_pl", "Precip", "Rainfall", "Rain_Tot", "Precip_Tot"]

# Station-spezifische Jahre für NEE (und IQR, optional VWC): Liste von (start_year, end_year) inklusive
NEE_STATION_YEAR_RANGES: dict[str, list[tuple[int, int]]] = {
    "Sumbrungu": [(2013, 2015)],
    "Gorigo": [(2017, 2020), (2022, 2022)],
    "Nazinga": [(2013, 2017)],
    "Kayoro": [(2014, 2017), (2021, 2023)],
}

# Separater Jahresfilter nur für die Niederschlags-Klimatologie (Sekundärachse).
# Fehlender Stations-Key oder Wert None: gesamter Zeitraum der geladenen Datei (kein Jahr-Filter).
# Leere Liste []: keine Daten (leeres DataFrame) für P.
P_STATION_YEAR_RANGES: dict[str, list[tuple[int, int]] | None] = {
    # Beispiel – anpassen:
    "Sumbrungu": [(2013, 2013)],
    "Janga": [(2023, 2023)],
    "Gorigo": [(2017, 2020), (2022, 2022)],
    "Nazinga": [(2013, 2017)],
    #"Kayoro": [(2014, 2017), (2021, 2023)],
    "Kayoro": [(2013, 2015)],
    # "Nazinga": [(2013, 2022)],
}

# Rückwärtskompatibilität (ältere Skripte / Imports)
STATION_YEAR_RANGES = NEE_STATION_YEAR_RANGES

# Plot options
SMOOTH_WINDOW_DAYS = 15  # rolling window on DOY (circular)
SMOOTH_METHOD = "mean"  # "median" (default) oder "mean"
DAILY_STAT_METHOD = "mean"  # "median" (default) oder "mean" für tägliche NEE/VWC-Aggregation
SHOW_IQR = True
PLOT_PRECIP = True       # secondary axis: precip climatology (30-day running sum)
PLOT_VWC = False         # optional: add VWC climatology as thin line on secondary axis (can clutter)

# Day definition for daily aggregation
DAILY_MIN_COUNT = 24     # minimum 30-min records per day (~12h) to accept daily statistic

# Schriftgrößen (wie gap_length_distribution, ustar_fingerprint)
FONTSIZE = 14
TICK_FONTSIZE = 13

# Vereinheitlichte Y-Limits für alle Subplots
NEE_YLIM = (-9, 4)       # NEE (µmol m⁻² s⁻¹), Hauptachse
P30_YLIM = (0, 190)      # P 30-Tage-Summe (mm), Sekundärachse

# =============================================================================
# IO
# =============================================================================
def load_all_variables(station: str) -> pd.DataFrame | None:
    path = OUTPUT_BASE / station / "processed" / "all" / f"{station}_all_variables_30min.csv"
    if not path.exists():
        print(f"[WARN] Missing file: {path}")
        return None

    header = pd.read_csv(path, nrows=1).columns.tolist()
    df = pd.read_csv(
        path,
        skiprows=2,
        header=None,
        names=header,
        index_col=0,
        parse_dates=True,
        low_memory=False,
        na_values=["NAN", "NA", "-9999", "-9999.0", "-999", "**************"],
    )
    df = df[df.index.notna()].sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


def filter_df_by_station_years(
    df: pd.DataFrame,
    station: str,
    ranges_by_station: dict[str, list[tuple[int, int]] | None] | None,
) -> pd.DataFrame:
    """
    Begrenzt df auf die angegebenen Jahresbereiche pro Station.
    - Key fehlt oder Wert ist None: kein Filter (gesamter Zeitraum in df).
    - Leere Liste: leeres DataFrame.
    """
    if ranges_by_station is None:
        return df
    ranges = ranges_by_station.get(station)
    if ranges is None:
        return df
    if len(ranges) == 0:
        return df.iloc[0:0]
    years = set()
    for start, end in ranges:
        years.update(range(start, end + 1))
    mask = df.index.year.isin(years)
    return df.loc[mask]


def get_first_existing_col(df: pd.DataFrame, aliases: list[str]) -> str | None:
    for a in aliases:
        if a in df.columns:
            return a
    return None


def get_p_col(df: pd.DataFrame, station: str) -> str | None:
    """P-Spalte pro Station (wie event_scale_water_balance.py)."""
    col = P_COL_BY_STATION.get(station)
    if col is not None and col in df.columns:
        return col
    return get_first_existing_col(df, P_ALIASES_FALLBACK)


def station_label(station: str) -> str:
    """Lesbares Stationslabel für Plot-Titel."""
    return STATION_LABELS.get(station, station)


def get_vwc_series_single(df: pd.DataFrame, station: str) -> pd.Series | None:
    """
    Liefert eine VWC-Serie pro Station (wie event_scale_water_balance.py).
    Mole/Janga: Mittelwert der 3 Schichten. Andere: Mittelwert aller Schichten.
    """
    scale = VWC_SCALE.get(station, 1.0)
    series_list: list[pd.Series] = []
    for cols, _ in VWC_LAYER_COLS:
        for c in cols:
            if c in df.columns:
                s = pd.to_numeric(df[c], errors="coerce") / scale
                if s.notna().any():
                    series_list.append(s)
                break
    if not series_list:
        return None
    return pd.concat(series_list, axis=1).mean(axis=1)


def apply_qc_filter(series: pd.Series, qc: pd.Series, qc_max: int = 1) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce").copy()
    q = pd.to_numeric(qc, errors="coerce")
    bad = (q > qc_max) | q.isna()
    s.loc[bad] = np.nan
    return s


# =============================================================================
# CLIMATOLOGY HELPERS
# =============================================================================
def daily_from_halfhourly(s: pd.Series, how: str = "mean") -> pd.Series:
    """
    Convert 30-min series to daily series with robust stats.
    Also enforces a minimum data count per day (DAILY_MIN_COUNT).
    """
    s = pd.to_numeric(s, errors="coerce")
    cnt = s.resample("D").count()
    if how == "mean":
        d = s.resample("D").mean()
    elif how == "sum":
        d = s.resample("D").sum()
    else:
        d = s.resample("D").median()

    d.loc[cnt < DAILY_MIN_COUNT] = np.nan
    return d


def doy_climatology(daily: pd.Series) -> pd.DataFrame:
    """
    Returns a DataFrame indexed by DOY=1..365 with columns:
      median, q25, q75, count
    Drops DOY=366 to keep a consistent 365-day climatology.
    """
    if daily.empty:
        return pd.DataFrame()

    tmp = daily.dropna()
    if tmp.empty:
        return pd.DataFrame()

    doy = tmp.index.dayofyear
    df = pd.DataFrame({"val": tmp.values, "doy": doy})
    df = df[df["doy"] <= 365]  # drop leap day

    g = df.groupby("doy")["val"]
    out = pd.DataFrame({
        "median": g.median(),
        "mean": g.mean(),
        "q25": g.quantile(0.25),
        "q75": g.quantile(0.75),
        "count": g.count(),
    })
    # ensure full 1..365 index
    out = out.reindex(range(1, 366))
    return out


def circular_rolling_median(x: pd.Series, window: int) -> pd.Series:
    """
    Circular rolling median for DOY series (length 365).
    """
    if x.size != 365:
        x = x.reindex(range(1, 366))

    x1 = pd.concat([x, x, x], axis=0)
    # indices: 1..365, repeated 3 times; reset to 1..1095 for rolling
    x1 = x1.reset_index(drop=True)

    sm = x1.rolling(window=window, center=True, min_periods=max(3, window // 3)).median()
    # take the middle year slice
    sm_mid = sm.iloc[365:730].reset_index(drop=True)
    sm_mid.index = range(1, 366)
    return sm_mid


def circular_rolling_mean(x: pd.Series, window: int) -> pd.Series:
    """
    Circular rolling mean for DOY series (length 365).
    """
    if x.size != 365:
        x = x.reindex(range(1, 366))

    x1 = pd.concat([x, x, x], axis=0)
    x1 = x1.reset_index(drop=True)

    sm = x1.rolling(window=window, center=True, min_periods=max(3, window // 3)).mean()
    sm_mid = sm.iloc[365:730].reset_index(drop=True)
    sm_mid.index = range(1, 366)
    return sm_mid


def circular_rolling_smooth(x: pd.Series, window: int, method: str = "median") -> pd.Series:
    """Circular rolling smoother with selectable method ('median' or 'mean')."""
    method = str(method).strip().lower()
    if method == "mean":
        return circular_rolling_mean(x, window)
    return circular_rolling_median(x, window)


def circular_rolling_sum(x: pd.Series, window: int) -> pd.Series:
    """
    Circular rolling sum for DOY series (length 365).
    """
    if x.size != 365:
        x = x.reindex(range(1, 366))

    x1 = pd.concat([x, x, x], axis=0)
    x1 = x1.reset_index(drop=True)

    sm = x1.rolling(window=window, center=True, min_periods=max(3, window // 3)).sum()
    sm_mid = sm.iloc[365:730].reset_index(drop=True)
    sm_mid.index = range(1, 366)
    return sm_mid


# =============================================================================
# MAIN
# =============================================================================
def main() -> None:
    fig, axes = plt.subplots(2, 3, figsize=(16, 9), sharex=True)
    axes = axes.ravel()

    for i, station in enumerate(STATIONS):
        ax = axes[i]

        df_full = load_all_variables(station)
        if df_full is None or df_full.empty:
            ax.set_title(f"{station_label(station)} (no data)", fontsize=FONTSIZE)
            ax.axis("off")
            continue

        df_nee = filter_df_by_station_years(df_full, station, NEE_STATION_YEAR_RANGES)
        if df_nee.empty:
            ax.set_title(f"{station_label(station)} (no data in NEE year range)", fontsize=FONTSIZE)
            ax.axis("off")
            continue

        # --- CO2 flux / NEE
        co2_col = get_first_existing_col(df_nee, [a for a in CO2_FLUX_ALIASES if a != QC_FLAG_DEFAULT])
        if co2_col is None:
            ax.set_title(f"{station_label(station)} (no CO$_2$ flux column)", fontsize=FONTSIZE)
            ax.axis("off")
            continue

        nee_30m = pd.to_numeric(df_nee[co2_col], errors="coerce")

        # QC
        if APPLY_QC and QC_FLAG_DEFAULT in df_nee.columns:
            nee_30m = apply_qc_filter(nee_30m, df_nee[QC_FLAG_DEFAULT], qc_max=QC_MAX)

        nee_daily = daily_from_halfhourly(nee_30m, how=DAILY_STAT_METHOD)
        clim = doy_climatology(nee_daily)

        if clim.empty:
            ax.set_title(f"{station_label(station)} (insufficient NEE)", fontsize=FONTSIZE)
            ax.axis("off")
            continue

        nee_med = clim["median"]
        nee_sm = circular_rolling_smooth(nee_med, SMOOTH_WINDOW_DAYS, SMOOTH_METHOD)

        # IQR shading (optional)
        if SHOW_IQR:
            q25_sm = circular_rolling_smooth(clim["q25"], SMOOTH_WINDOW_DAYS, SMOOTH_METHOD)
            q75_sm = circular_rolling_smooth(clim["q75"], SMOOTH_WINDOW_DAYS, SMOOTH_METHOD)
            ax.fill_between(
                nee_sm.index.values,
                q25_sm.values,
                q75_sm.values,
                alpha=0.2,
                linewidth=0,
                label=f"IQR (15-day rolling {SMOOTH_METHOD})" if i == 0 else None,
                color = "grey"
            )

        #smooth_label = f"NEE (daily {DAILY_STAT_METHOD}, {SMOOTH_METHOD} smoothed)"
        smooth_label = f"NEE (15-day rolling {SMOOTH_METHOD})"
        ax.plot(nee_sm.index, nee_sm.values, linewidth=1.6, label=smooth_label if i == 0 else None,color = "black")

        # Zero line for sink/source visual reference
        ax.axhline(0, linewidth=0.8, alpha=0.6,color = "black")

        ax.set_title(station_label(station), fontsize=FONTSIZE)
        ax.set_xlim(1, 365)
        ax.set_ylim(NEE_YLIM)
        ax.set_xlabel("Day of year (DOY)" if i >= 3 else "", fontsize=FONTSIZE)
        ax.set_ylabel("NEE [µmol m$^{-2}$ s$^{-1}$]" if i in [0, 3] else "", fontsize=FONTSIZE)
        ax.tick_params(axis="both", labelsize=TICK_FONTSIZE)
        ax.grid(True, alpha=0.25)

        # --- Secondary axis: precipitation (rolling sum climatology; eigener Jahresfilter)
        if PLOT_PRECIP:
            df_p = filter_df_by_station_years(df_full, station, P_STATION_YEAR_RANGES)
            p_col = get_p_col(df_p, station)
            if p_col is not None and not df_p.empty:
                p_30m = pd.to_numeric(df_p[p_col], errors="coerce")
                p_daily = daily_from_halfhourly(p_30m, how="sum")
                p_clim = doy_climatology(p_daily)
                if not p_clim.empty:
                    # use median daily precip (per DOY), then 30-day running sum (circular)
                    # Missing DOY values must remain NaN (do not replace by 0),
                    # otherwise the rolling precipitation sum is biased low.
                    p_med = p_clim["mean"]
                    p30 = circular_rolling_sum(p_med, 15)

                    ax2 = ax.twinx()
                    ax2.plot(
                        p30.index, p30.values,
                        linewidth=1.0,
                        alpha=0.7,
                        label="P (15-day rolling sum) [mm]" if i == 0 else None,
                    )
                    if i in [2, 5]:
                        ax2.set_ylabel("P [mm]", fontsize=FONTSIZE, rotation=270, labelpad=15, color = "C0")
                    ax2.set_ylim(P30_YLIM[::-1])  # von oben (0) nach unten (hoch) – Regen fällt
                    ax2.tick_params(axis="y", labelsize=TICK_FONTSIZE, colors="C0")


        # --- Optional: VWC climatology (can clutter; gleiche Jahre wie NEE)
        if PLOT_VWC:
            vwc_30m = get_vwc_series_single(df_nee, station)
            if vwc_30m is not None:
                vwc_daily = daily_from_halfhourly(vwc_30m, how=DAILY_STAT_METHOD)
                vwc_clim = doy_climatology(vwc_daily)
                if not vwc_clim.empty:
                    vwc_sm = circular_rolling_smooth(vwc_clim["median"], SMOOTH_WINDOW_DAYS, SMOOTH_METHOD)
                    ax2 = ax.twinx()
                    ax2.plot(
                        vwc_sm.index, vwc_sm.values,
                        linewidth=1.0,
                        alpha=0.5,
                        linestyle="--",
                        label=f"VWC ({DAILY_STAT_METHOD}, smoothed)" if i == 0 else None,
                    )
                    if i in [2, 5]:
                        ax2.set_ylabel("VWC", fontsize=FONTSIZE)
                    ax2.tick_params(axis="y", labelsize=TICK_FONTSIZE)

    # One combined legend: grab handles from first axis that has them + twinx
    handles, labels = [], []
    for ax in axes:
        if ax.has_data():
            h, l = ax.get_legend_handles_labels()
            handles += h
            labels += l
            # also check twinx if present
            for child in ax.get_children():
                pass
            # check possible twin axes in figure
            break

    # Collect legends from all axes (including twins) safely
    for ax in fig.axes:
        h, l = ax.get_legend_handles_labels()
        for hh, ll in zip(h, l):
            if ll and ll not in labels:
                handles.append(hh)
                labels.append(ll)

    if handles:
        fig.legend(handles, labels, loc="lower center", ncol=3, frameon=True, fontsize=TICK_FONTSIZE)

    fig.tight_layout(rect=[0, 0.05, 1, 1])
    plt.savefig(OUT_PNG, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"✓ Saved: {OUT_PNG}")


if __name__ == "__main__":
    main()
