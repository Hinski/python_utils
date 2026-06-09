#!/usr/bin/env python3
"""
Mittlere jährliche Temperatur und mittlere jährliche Niederschlagssumme
für Gorigo, Janga und Mole.

Zeiträume wie in data_coverage_qc_heatmap / gap_length_distribution:
- Gorigo: Mai 2017 – August 2022
- Janga, Mole: 2013–2025 (voller Zeitraum)

Datenquelle: {station}_all_variables_30min.csv (collect_all_variables_30min.py)
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd
import numpy as np

# =============================================================================
# CONFIG
# =============================================================================
OUTPUT_BASE = Path("/Users/hingerl-l/Data")
STATIONS = ["Gorigo", "Janga", "Mole"]

COVERAGE_START = pd.Timestamp("2013-01-01")
COVERAGE_END = pd.Timestamp("2025-12-31")
GORIGO_START = pd.Timestamp("2017-05-01")
GORIGO_EMPTY_FROM = pd.Timestamp("2022-09-01")  # nur bis einschl. August 2022

P_COL_BY_STATION = {"Gorigo": "P_pl", "Janga": "P", "Mole": "P_tb"}
TAIR_ALIASES = ["Tair", "Ta", "T_Avg", "AirTC_Avg", "T_avg", "temp_air"]


def _get_col(df: pd.DataFrame, aliases: list[str]) -> str | None:
    for a in aliases:
        if a in df.columns:
            return a
    return None


def load_all_variables(station: str) -> pd.DataFrame | None:
    path = OUTPUT_BASE / station / "processed" / "all" / f"{station}_all_variables_30min.csv"
    if not path.exists():
        print(f"  [WARN] Missing: {path}")
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


def restrict_to_station_period(df: pd.DataFrame, station: str) -> pd.DataFrame:
    df = df.loc[COVERAGE_START:COVERAGE_END]
    if station == "Gorigo":
        df = df[(df.index >= GORIGO_START) & (df.index < GORIGO_EMPTY_FROM)]
    return df


def main() -> None:
    print("Mittlere jährliche Temperatur und Niederschlag (Gorigo, Janga, Mole)")
    print("=" * 55)

    results = []
    for station in STATIONS:
        df = load_all_variables(station)
        if df is None or df.empty:
            print(f"  {station}: Keine Daten")
            results.append((station, None, None))
            continue

        df = restrict_to_station_period(df, station)
        if df.empty:
            print(f"  {station}: Keine Daten im Zeitfenster")
            results.append((station, None, None))
            continue

        # Temperatur: erste passende Spalte
        t_col = _get_col(df, TAIR_ALIASES)
        if t_col is None:
            print(f"  {station}: Keine Temperaturspalte (gesucht: {TAIR_ALIASES})")
            t_mean_annual = None
        else:
            T = pd.to_numeric(df[t_col], errors="coerce")
            # Von Kelvin nach °C falls nötig
            if T.median() > 200:
                T = T - 273.15
            yearly_mean = T.resample("YE").mean()
            yearly_mean = yearly_mean.dropna()
            t_mean_annual = float(yearly_mean.mean()) if len(yearly_mean) > 0 else None
            if t_mean_annual is not None:
                print(f"  {station}: Mittlere jährliche Temperatur = {t_mean_annual:.2f} °C  (Jahre: {list(yearly_mean.index.year)})")

        # Niederschlag: stationsspezifische Spalte
        p_col = P_COL_BY_STATION.get(station, "P")
        if p_col not in df.columns:
            print(f"  {station}: Spalte {p_col} nicht gefunden")
            p_mean_annual = None
        else:
            P = pd.to_numeric(df[p_col], errors="coerce").fillna(0)
            yearly_sum = P.resample("YE").sum()
            # Station-spezifische Auswahl der Jahre
            years = yearly_sum.index.year
            if station == "Janga":
                mask = years == 2023
                yearly_sum = yearly_sum[mask]
            elif station == "Mole":
                mask = (years >= 2024) & (years <= 2025)
                yearly_sum = yearly_sum[mask]
            elif station == "Gorigo":
                mask = (years >= 2018) & (years <= 2022)
                yearly_sum = yearly_sum[mask]
            p_mean_annual = float(yearly_sum.mean()) if len(yearly_sum) > 0 else None
            if p_mean_annual is not None:
                print(f"  {station}: Mittlere jährliche Niederschlagssumme = {p_mean_annual:.1f} mm  (Jahre: {list(yearly_sum.index.year)})")

        results.append((station, t_mean_annual, p_mean_annual))

    # Kurz-Tabelle
    print()
    print("Zusammenfassung:")
    print("-" * 55)
    print(f"{'Station':<12}  {'T_mean_annual (°C)':<20}  {'P_mean_annual (mm)':<20}")
    print("-" * 55)
    for station, t, p in results:
        t_str = f"{t:.2f}" if t is not None else "–"
        p_str = f"{p:.1f}" if p is not None else "–"
        print(f"{station:<12}  {t_str:<20}  {p_str:<20}")
    print("-" * 55)


if __name__ == "__main__":
    main()
