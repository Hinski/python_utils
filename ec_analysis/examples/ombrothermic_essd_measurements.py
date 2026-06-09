#!/usr/bin/env python3
"""
Ombrothermic (Walter–Lieth) diagrams from ESSD final_datatables (in-situ measurements).

Berechnet pro Station:
  - Monatsmitteltemperatur (Mittel aller Tageswerte je Kalendermonat)
  - Mittlere Monatssumme Niederschlag (Mittel der Monatssummen über alle Jahre)

Zusätzlich: Mittelwert über alle Stationen (je Monat).

Daten: {station}_daily.csv in final_datatables (Spalten TA, P).

  python ombrothermic_essd_measurements.py
  python ombrothermic_essd_measurements.py -o plots/ombrothermic_essd_mean.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from walter_lieth_common import MONTH_LABELS, plot_walter_lieth_figure, plot_walter_lieth_on_axes

DATA_DIR = Path("/Users/hingerl-l/Data/essd_data_tables/final_datatables")
STATIONS = ["Nazinga", "Kayoro", "Sumbrungu", "Gorigo", "Janga"]  # ohne Mole
NETWORK_LABEL = "Mittel (alle Stationen)"

MISSING_VALUES = [-9999, -9999.0, "-9999", "NAN", "nan", "NA"]
T_COL = "TA"
P_COL = "P"
MIN_DAYS_PER_MONTH = 10  # Mindest-Tage pro Monat/Jahr für Niederschlags-Monatssumme


def load_daily_station(station: str, data_dir: Path) -> pd.DataFrame:
    path = data_dir / f"{station}_daily.csv"
    if not path.exists():
        raise FileNotFoundError(path)

    header = pd.read_csv(path, nrows=1).columns.tolist()
    df = pd.read_csv(
        path,
        skiprows=2,
        header=None,
        names=header,
        low_memory=False,
        na_values=MISSING_VALUES,
    )
    ts = pd.to_datetime(df["TIMESTAMP"].astype(str).str.strip(), format="%Y%m%d", errors="coerce")
    df = df.drop(columns=["TIMESTAMP"])
    df.index = ts
    df = df[df.index.notna()].sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


def monthly_climatology_from_daily(df: pd.DataFrame) -> tuple[pd.Series, pd.Series, dict]:
    """Return (T_monthly, P_monthly) indexed 1..12 and metadata dict."""
    ta = pd.to_numeric(df[T_COL], errors="coerce")
    pr = pd.to_numeric(df[P_COL], errors="coerce")
    pr = pr.where(pr >= 0)

    # Monatsmitteltemperatur: alle gültigen Tageswerte je Kalendermonat
    t_clim = ta.groupby(ta.index.month).mean()

    # Monatssummen je Jahr-Monat, dann Mittel je Kalendermonat
    daily_ok = pr.notna()
    pr_valid = pr.where(daily_ok)
    monthly_sum = pr_valid.groupby([pr_valid.index.year, pr_valid.index.month]).sum(min_count=1)
    counts = pr_valid.groupby([pr_valid.index.year, pr_valid.index.month]).count()
    monthly_sum = monthly_sum[counts >= MIN_DAYS_PER_MONTH]
    p_clim = monthly_sum.groupby(level=1).mean()

    meta = {
        "n_days_ta": int(ta.notna().sum()),
        "n_days_p": int(pr.notna().sum()),
        "year_start": int(df.index.year.min()) if len(df) else None,
        "year_end": int(df.index.year.max()) if len(df) else None,
        "n_years_p": int(monthly_sum.index.get_level_values(0).nunique()) if len(monthly_sum) else 0,
    }
    return t_clim, p_clim, meta


def _series_to_12(s: pd.Series) -> np.ndarray:
    out = np.full(12, np.nan)
    for m in range(1, 13):
        if m in s.index:
            out[m - 1] = float(s[m])
    return out


def network_mean_climatology(
    station_clims: dict[str, tuple[pd.Series, pd.Series]],
) -> tuple[np.ndarray, np.ndarray]:
    """Einfaches Mittel der Stations-Klimatologien (je Monat, gleichgewichtet)."""
    t_stack, p_stack = [], []
    for t_s, p_s in station_clims.values():
        t_stack.append(_series_to_12(t_s))
        p_stack.append(_series_to_12(p_s))
    t_mean = np.nanmean(np.vstack(t_stack), axis=0)
    p_mean = np.nanmean(np.vstack(p_stack), axis=0)
    return t_mean, p_mean


def _global_y_top(clims: dict[str, tuple[np.ndarray, np.ndarray]]) -> float:
    tops = []
    for t, p in clims.values():
        p_scaled = p / 10.0
        tops.append(max(np.nanmax(t), np.nanmax(p_scaled), 20) * 1.12)
    return float(np.ceil(max(tops) / 5) * 5)


def save_climatology_table(
    path: Path,
    station_data: dict[str, tuple[pd.Series, pd.Series, dict]],
    t_net: np.ndarray,
    p_net: np.ndarray,
) -> None:
    rows = []
    for name in list(STATIONS) + [NETWORK_LABEL]:
        if name == NETWORK_LABEL:
            t_arr, p_arr = t_net, p_net
            years = ""
        else:
            t_s, p_s, meta = station_data[name]
            t_arr, p_arr = _series_to_12(t_s), _series_to_12(p_s)
            years = f"{meta['year_start']}–{meta['year_end']}"
        for m in range(1, 13):
            rows.append(
                {
                    "station": name,
                    "month": m,
                    "month_name": MONTH_LABELS[m - 1],
                    "T_mean_C": t_arr[m - 1],
                    "P_mean_sum_mm": p_arr[m - 1],
                    "years": years,
                }
            )
    pd.DataFrame(rows).to_csv(path, index=False, float_format="%.2f")


def build_panel_figure(
    station_data: dict[str, tuple[pd.Series, pd.Series, dict]],
    t_net: np.ndarray,
    p_net: np.ndarray,
    y_top: float,
) -> plt.Figure:
    order = STATIONS + [NETWORK_LABEL]
    fig, axes = plt.subplots(4, 2, figsize=(12, 14))
    axes_flat = axes.flatten()

    for ax, name in zip(axes_flat, order):
        if name == NETWORK_LABEL:
            t_arr, p_arr = t_net, p_net
        else:
            t_s, p_s, _meta = station_data[name]
            t_arr, p_arr = _series_to_12(t_s), _series_to_12(p_s)
        plot_walter_lieth_on_axes(
            ax,
            t_arr,
            p_arr,
            title=None,
            y_top=y_top,
        )

    fig.tight_layout()
    return fig


def main() -> None:
    parser = argparse.ArgumentParser(description="Walter–Lieth aus final_datatables")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument(
        "-o",
        "--output-mean",
        type=Path,
        default=Path(__file__).parent / "plots" / "ombrothermic_essd_mean.png",
    )
    parser.add_argument(
        "--output-panel",
        type=Path,
        default=Path(__file__).parent / "plots" / "ombrothermic_essd_panel.png",
    )
    parser.add_argument(
        "--output-table",
        type=Path,
        default=Path(__file__).parent / "plots" / "ombrothermic_essd_climatology.csv",
    )
    args = parser.parse_args()

    station_clims: dict[str, tuple[pd.Series, pd.Series, dict]] = {}
    arrays: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    print("Monatsklimatologie aus daily final_datatables")
    print("=" * 60)

    for station in STATIONS:
        df = load_daily_station(station, args.data_dir)
        t_clim, p_clim, meta = monthly_climatology_from_daily(df)
        station_clims[station] = (t_clim, p_clim, meta)
        arrays[station] = (_series_to_12(t_clim), _series_to_12(p_clim))
        print(
            f"\n{station} ({meta['year_start']}–{meta['year_end']}, "
            f"{meta['n_days_ta']} T-Tage, {meta['n_days_p']} P-Tage):"
        )
        for m in range(1, 13):
            print(
                f"  {MONTH_LABELS[m-1]:>3s}: "
                f"T={t_clim.get(m, float('nan')):5.1f} °C  "
                f"P={p_clim.get(m, float('nan')):6.1f} mm"
            )

    t_net, p_net = network_mean_climatology(
        {k: (v[0], v[1]) for k, v in station_clims.items()}
    )
    arrays[NETWORK_LABEL] = (t_net, p_net)

    print(f"\n{NETWORK_LABEL}:")
    for m in range(1, 13):
        print(f"  {MONTH_LABELS[m-1]:>3s}: T={t_net[m-1]:5.1f} °C  P={p_net[m-1]:6.1f} mm")

    y_top = _global_y_top(arrays)

    args.output_mean.parent.mkdir(parents=True, exist_ok=True)
    fig_mean = plot_walter_lieth_figure(t_net, p_net, title=None, footnote=None)
    fig_mean.savefig(args.output_mean, dpi=300, bbox_inches="tight")
    plt.close(fig_mean)

    fig_panel = build_panel_figure(station_clims, t_net, p_net, y_top)
    fig_panel.savefig(args.output_panel, dpi=300, bbox_inches="tight")
    plt.close(fig_panel)

    save_climatology_table(args.output_table, station_clims, t_net, p_net)

    # Einzeldiagramme pro Station
    single_dir = args.output_mean.parent / "ombrothermic_essd_stations"
    single_dir.mkdir(parents=True, exist_ok=True)
    for station in STATIONS:
        t_s, p_s, meta = station_clims[station]
        fig_s = plot_walter_lieth_figure(
            _series_to_12(t_s),
            _series_to_12(p_s),
            title=None,
            footnote=None,
        )
        out_s = single_dir / f"{station}.png"
        fig_s.savefig(out_s, dpi=300, bbox_inches="tight")
        plt.close(fig_s)

    print(f"\n✓ Netzwerkmittel: {args.output_mean}")
    print(f"✓ Alle Stationen:  {args.output_panel}")
    print(f"✓ Tabelle:         {args.output_table}")
    print(f"✓ Einzelplots:     {single_dir}/")


if __name__ == "__main__":
    main()
