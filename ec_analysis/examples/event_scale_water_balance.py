"""
Event-scale water balance: Forcing (P, ET) vs. storage response (VWC).

6 Subplots (2×3), one per station. Per panel (60 min aggregation):
  - P(t) as bars [mm/h] von oben – Forcing (Skala nur obere Hälfte)
  - VWC(t) as line(s), right y-axis – Storage response
  - ET(t) as line, left y-axis – atmospheric demand/loss

Event selection: highest 3-hour P sum per station.
Time window: −2 days to +5 days around event peak.
Run collect_all_variables_30min.py first.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import yaml
except ImportError:
    yaml = None

QUALITY_FILTERS_CONFIG = Path(__file__).parent.parent / "ec_analysis" / "utils" / "quality_filters_config.yaml"

# ============================================================================
# CONFIGURATION
# ============================================================================
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

# Niederschlagsvariable pro Station (fest)
P_COL_BY_STATION = {
    "Sumbrungu": "P_tb",
    "Nazinga": "P_tb",
    "Kayoro": "P_tb",
    "Gorigo": "P_pl",
    "Janga": "P",
    "Mole": "P_tb",
}

# Aggregation: 60 min
RESAMPLE_RULE = "1h"
# Event: 3h = 3 × 1h; Fenster: −2 bis +2 Tage (5 Tage gesamt)
EVENT_WINDOW_HOURS_BEFORE = 2 * 24
EVENT_WINDOW_HOURS_AFTER = 3 * 24
ROLLING_PERIODS_3H = 3  # 3 × 1h = 3h

# VWC-Schichten: Kandidaten pro Tiefe (3cm, 10cm, 30cm)
VWC_LAYER_COLS: list[tuple[list[str], str]] = [
    (["VWC_1", "VW_1_Avg", "SWC_1_1_1", "SWC_1", "VWC_Avg"], "θ₃cm"),
    (["VWC_2", "VW_2_Avg", "SWC_2_1_1", "SWC_2", "VWC_2_Avg"], "θ₁₀cm"),
    (["VWC_3", "VW_3_Avg", "SWC_3_1_1", "SWC_3", "VWC_3_Avg"], "θ₃₅cm"),
]
VWC_SCALE: dict[str, float] = {"Janga": 100.0}

# Stationen mit 3 VWC-Schichten (θ3cm, θ10cm, θ30cm einzeln); andere: Mittelwert
STATIONS_WITH_3_VWC_LAYERS = frozenset({"Mole", "Janga"})

# Station-spezifische Event-Auswahl: (p3h_min, p3h_max) mm für Vergleichbarkeit
P3H_RANGE_BY_STATION: dict[str, tuple[float, float]] = {"Kayoro": (60, 80)}
# Station-spezifisches Jahr für Event-Suche
EVENT_YEAR_BY_STATION: dict[str, int] = {"Janga": 2023, "Mole": 2023}
# Station-spezifisches Datum für Event-Peak (YYYY-MM-DD); Peak = stärkstes 3h P an diesem Tag
EVENT_DATE_BY_STATION: dict[str, str] = {#"Nazinga": "2016-05-28",
                                        "Nazinga": "2016-05-28",
                                        "Kayoro": "2016-03-20",
                                          #"Gorigo": "2019-04-23", "Mole": "2024-04-27"}
                                          "Gorigo": "2021-04-29", "Mole": "2024-04-27"}

# Vereinheitlichte Y-Limits
VWC_YLIM = (0, 0.5)
P_YLIM = (0, 100)  # mm/h; Skala von oben (100) nach unten (0)
ET_YLIM = (0, 1.5)  # mm/h
PRECIP_COLUMNS = frozenset({"P", "P_pl", "P_tb", "Precip", "Rainfall", "Acc_NRT", "Acc_totNRT", "Rain_mm_Tot", "WXT_Ramount_Tot", "Ramount_Tot", "Hamount_Tot", "Acc_RT_NRT", "Bucket_RT", "Bucket_NRT"})


def station_label(station: str) -> str:
    """Lesbares Stationslabel für Plot-Titel und Hinweise."""
    return STATION_LABELS.get(station, station)


def load_all_variables(station: str) -> pd.DataFrame | None:
    """Lädt all_variables CSV (ohne Datumsfilter)."""
    path = OUTPUT_BASE / station / "processed" / "all" / f"{station}_all_variables_30min.csv"
    if not path.exists():
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


def resample_1h(df: pd.DataFrame, p_col: str) -> pd.DataFrame:
    """Aggregiert auf 60 min: P = sum, Rest = mean."""
    agg = {}
    for c in df.columns:
        agg[c] = "sum" if c in PRECIP_COLUMNS else "mean"
    try:
        return df.resample(RESAMPLE_RULE, origin="start_day").agg(agg)
    except Exception:
        return df.resample(RESAMPLE_RULE).agg(agg)


def find_peak_event(
    df: pd.DataFrame, p_col: str, station: str = ""
) -> pd.Timestamp | None:
    """
    Findet den Zeitpunkt des stärksten 3-h-Niederschlagsereignisses.
    EVENT_DATE_BY_STATION: Peak = stärkstes 3h P an diesem Tag.
    P3H_RANGE_BY_STATION: stärkstes Event innerhalb (min, max) mm.
    EVENT_YEAR_BY_STATION: nur Daten aus diesem Jahr.
    """
    event_date = EVENT_DATE_BY_STATION.get(station)
    if event_date is not None:
        target = pd.to_datetime(event_date)
        df = df[(df.index.date >= target.date()) & (df.index.date <= target.date())]
        if df.empty:
            return None
    else:
        year = EVENT_YEAR_BY_STATION.get(station)
        if year is not None:
            df = df[df.index.year == year]
            if df.empty:
                return None
    P = pd.to_numeric(df[p_col], errors="coerce")
    if P.isna().all():
        return None
    P = P.fillna(0)
    p3h = P.rolling(window=ROLLING_PERIODS_3H, center=False, min_periods=1).sum()

    p_range = P3H_RANGE_BY_STATION.get(station) if event_date is None else None
    if p_range is not None:
        p_min, p_max = p_range
        mask = (p3h >= p_min) & (p3h <= p_max)
        if not mask.any():
            return None
        sub = p3h.loc[mask]
        idx_max = sub.idxmax()
    else:
        idx_max = p3h.idxmax()

    if pd.isna(idx_max):
        return None
    return pd.Timestamp(idx_max)


def extract_event_window(
    df: pd.DataFrame, peak: pd.Timestamp
) -> pd.DataFrame:
    """Schneidet −2 bis +2 Tage um den Event-Peak (5 Tage)."""
    start = peak - pd.Timedelta(hours=EVENT_WINDOW_HOURS_BEFORE)
    end = peak + pd.Timedelta(hours=EVENT_WINDOW_HOURS_AFTER)
    return df.loc[(df.index >= start) & (df.index <= end)].copy()


def apply_physical_limits(df: pd.DataFrame, station: str) -> pd.DataFrame:
    """Wendet physikalische Limits aus quality_filters_config.yaml auf VWC-Bodenfeuchte an."""
    if yaml is None or not QUALITY_FILTERS_CONFIG.exists():
        return df
    df = df.copy()
    with QUALITY_FILTERS_CONFIG.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    global_limits = cfg.get("global", {}).get("physical_limits", {})
    station_cfg = cfg.get("stations", {}).get(station, {})
    station_limits = station_cfg.get("physical_limits") or {}
    merged = {**global_limits, **station_limits}
    # Janga: VWC in % (0–100), nutze SWC_* Limits; andere: VWC_* in m³/m³ (0–0.7)
    vwc_col_map = (
        ["VWC_1", "VWC_2", "VWC_3", "VW_1_Avg", "VW_2_Avg", "VW_3_Avg", "SWC_1_1_1", "SWC_2_1_1", "SWC_3_1_1"]
        if station != "Janga"
        else ["VWC_1", "VWC_2", "VWC_3", "SWC_1", "SWC_2", "SWC_3", "VW_1_Avg", "VW_2_Avg", "VW_3_Avg", "SWC_1_1_1", "SWC_2_1_1", "SWC_3_1_1"]
    )
    # Für Janga: VWC_1/2/3 nutzen SWC_1/2/3 Limits (0–100 %)
    limit_key = lambda col: ("SWC_1" if col == "VWC_1" else "SWC_2" if col == "VWC_2" else "SWC_3" if col == "VWC_3" else col)
    for col in vwc_col_map:
        if col not in df.columns:
            continue
        key = limit_key(col) if station == "Janga" else col
        lim = merged.get(key) or merged.get(col)
        if not isinstance(lim, dict):
            continue
        vmin, vmax = lim.get("min"), lim.get("max")
        if vmin is None and vmax is None:
            continue
        vals = pd.to_numeric(df[col], errors="coerce")
        mask = vals.notna()
        if vmin is not None:
            mask = mask & (vals >= vmin)
        if vmax is not None:
            mask = mask & (vals <= vmax)
        df.loc[~mask, col] = np.nan
    return df


def get_vwc_series(
    df: pd.DataFrame, station: str
) -> list[tuple[pd.Series, str]]:
    """
    Mole/Janga: 3 Schichten einzeln (θ3cm, θ10cm, θ30cm).
    Andere: Mittelwert aller vorhandenen VWC → eine Linie.
    """
    scale = VWC_SCALE.get(station, 1.0)
    series_list: list[pd.Series] = []
    labels: list[str] = []
    for cols, label in VWC_LAYER_COLS:
        for c in cols:
            if c in df.columns:
                s = pd.to_numeric(df[c], errors="coerce") / scale
                if s.notna().any():
                    series_list.append(s)
                    labels.append(label)
                break

    if not series_list:
        return []

    if station in STATIONS_WITH_3_VWC_LAYERS:
        return list(zip(series_list, labels))
    # Andere Stationen: Mittelwert
    mean_s = pd.concat(series_list, axis=1).mean(axis=1)
    return [(mean_s, "θ")]


def plot_station_panel(
    ax: plt.Axes,
    df: pd.DataFrame,
    station: str,
    p_col: str,
    peak: pd.Timestamp,
    col_idx: int = 0,
) -> None:
    """
    Plottet eine Kachel: ET links, VWC rechts (von unten), P von oben.
    P-Skala nur obere Hälfte (großzügiges Limit).
    """
    # Schriftgrößen
    fs_label, fs_legend, fs_ticks, fs_title = 16, 14, 14, 16

    # ET links (Hauptachse)
    if "ET" in df.columns:
        ET = pd.to_numeric(df["ET"], errors="coerce")
        ax.plot(ET.index, ET.values, color="#d32f2f", linestyle="--", linewidth=1.2, label="ET")
    ax.set_ylabel("ET (mm/h)" if col_idx == 0 else "", fontsize=fs_label, color="#d32f2f")
    ax.tick_params(axis="y", labelcolor="#d32f2f", labelsize=fs_ticks)
    ax.tick_params(axis="x", labelsize=fs_ticks)
    ax.set_ylim(ET_YLIM)
    ax.set_title(station_label(station), fontsize=fs_title)

    # VWC rechts (unten), P auf gleicher Achse (oben, von oben nach unten)
    ax_vwc = ax.twinx()
    vwc_list = get_vwc_series(df, station)
    colors_vwc = ["#2e7d32", "#66bb6a", "#a5d6a7"]
    for i, (s, label) in enumerate(vwc_list):
        c = colors_vwc[i % len(colors_vwc)]
        ax_vwc.plot(s.index, s.values, color=c, label=label, linewidth=1.2)
    ax_vwc.set_ylabel("θ (m³/m³)" if col_idx == 2 else "", fontsize=fs_label, color="#2e7d32", rotation=270, labelpad=18)
    if col_idx == 2:
        ax_vwc.yaxis.set_label_coords(1.18, 0.25)
    ax_vwc.tick_params(axis="y", labelcolor="#2e7d32", labelsize=fs_ticks)
    ax_vwc.set_ylim(VWC_YLIM)
    ax_vwc.set_yticks([0, 0.1, 0.2])

    # P-Bars: von oben nach unten (Regen fällt)
    P = pd.to_numeric(df[p_col], errors="coerce").fillna(0)
    P_vwc = P * (VWC_YLIM[1] / P_YLIM[1])  # 100 mm = 0.5
    dx = (df.index[1] - df.index[0]).total_seconds() / 86400 if len(df) > 1 else 1 / 24
    width = max(dx * 0.85, 0.008)
    ax_vwc.bar(df.index, -P_vwc.values, width=width, bottom=VWC_YLIM[1], color="#4a90d9", alpha=0.6, label="P", align="edge", zorder=0)
    # P-Skala: 0 oben, 40 unten (invertiert), y_lim (0,100)
    # VWC 0.5 (oben) -> P 0, VWC 0 (unten) -> P 100
    sec_p = ax_vwc.secondary_yaxis("right", functions=(lambda v: (VWC_YLIM[1] - v) * P_YLIM[1] / VWC_YLIM[1], lambda p: VWC_YLIM[1] - p * VWC_YLIM[1] / P_YLIM[1]))
    sec_p.set_ylabel("")  # kein ylabel, stattdessen fig.text
    sec_p.tick_params(axis="y", labelcolor="#4a90d9", labelsize=fs_ticks)
    sec_p.set_yticks([0, 20, 40])
    sec_p.set_ylim(0, 100)
    # P (mm/h) nur bei dritter Spalte
    if col_idx == 2:
        ax_vwc.text(1.16, 0.73, "P (mm/h)", transform=ax_vwc.transAxes, fontsize=fs_label,
                    color="#4a90d9", rotation=270, va="center", ha="center")

    #ax.axvline(peak, color="gray", linestyle=":", linewidth=0.8, alpha=0.8)
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))  # Tickmarks jeden Tag (5 Tage)
    # Nur 2 Datums-Beschriftungen (jeder 2. Tick: pos 1, 3 bei 5 Ticks)
    base_fmt = mdates.DateFormatter("%Y-%m-%d")

    def sparse_date_fmt(x, pos):
        return base_fmt(x) if pos % 2 == 1 else ""

    ax.xaxis.set_major_formatter(FuncFormatter(sparse_date_fmt))
    ax.grid(True, alpha=0.3)
    ax.set_xlim(df.index.min(), df.index.max())
    # ET, VWC und P in einer Legende links oben
    handles_et, labels_et = ax.get_legend_handles_labels()
    handles_vwc, labels_vwc = ax_vwc.get_legend_handles_labels()
    ax.legend(
        handles_et + handles_vwc,
        labels_et + labels_vwc,
        loc="upper left",
        fontsize=fs_legend,
        frameon=True,
    )


def main() -> None:
    print("Event-scale water balance: Forcing vs. storage response")
    print("=" * 55)
    print(f"Event: max 3h P sum | Window: −{EVENT_WINDOW_HOURS_BEFORE//24}d to +{EVENT_WINDOW_HOURS_AFTER//24}d")
    print()

    fig, axes = plt.subplots(2, 3, figsize=(14, 8), sharex=False)
    axes_flat = axes.flatten()

    for idx, station in enumerate(STATIONS):
        ax = axes_flat[idx]
        p_col = P_COL_BY_STATION.get(station)
        if not p_col:
            ax.text(0.5, 0.5, f"{station_label(station)}\nNo P column", ha="center", va="center", transform=ax.transAxes)
            continue

        df = load_all_variables(station)
        if df is None or df.empty:
            ax.text(0.5, 0.5, f"{station_label(station)}\nNo data", ha="center", va="center", transform=ax.transAxes)
            continue
        if p_col not in df.columns:
            ax.text(0.5, 0.5, f"{station_label(station)}\nNo {p_col}", ha="center", va="center", transform=ax.transAxes)
            continue

        df = resample_1h(df, p_col)
        peak = find_peak_event(df, p_col, station)
        if peak is None:
            ax.text(0.5, 0.5, f"{station_label(station)}\nNo event", ha="center", va="center", transform=ax.transAxes)
            continue

        df_win = extract_event_window(df, peak)
        if df_win.empty or len(df_win) < 2:
            ax.text(0.5, 0.5, f"{station_label(station)}\nInsufficient window", ha="center", va="center", transform=ax.transAxes)
            continue

        df_win = apply_physical_limits(df_win, station)
        plot_station_panel(ax, df_win, station, p_col, peak, col_idx=idx % 3)
        p3h = pd.to_numeric(df[p_col], errors="coerce").fillna(0).rolling(ROLLING_PERIODS_3H, min_periods=1).sum()
        peak_val = p3h.loc[peak] if peak in p3h.index else np.nan
        print(f"  {station}: peak {peak.strftime('%Y-%m-%d %H:%M')}, 3h P = {peak_val:.1f} mm (60min agg)")

   # fig.suptitle(
   #     "Event-scale water balance: Forcing (P) vs. storage response (VWC) and ET",
   #     fontsize=17,
   #     fontweight="bold",
   #     y=1.02,
   # )
   # fig.text(
   #     0.5,
   #     -0.02,
   #     "Event = max 3h P sum per station. Mole, Janga: 3 VWC layers (θ₃cm, θ₁₀cm, θ₃₀cm). Others: VWC mean.",
   #     ha="center",
   #     fontsize=12,
   #     style="italic",
   # )
    plt.tight_layout(pad=1.2)
    # Mehr Rand, speziell rechts für P/VWC-Beschriftungen
    plt.subplots_adjust(left=0.06, right=0.92, top=0.92, bottom=0.1, hspace=0.35, wspace=0.35)
    out_path = Path("event_scale_water_balance_6panels.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight", pad_inches=0.3)
    plt.close()
    print(f"\n✓ Saved: {out_path}")


if __name__ == "__main__":
    main()
