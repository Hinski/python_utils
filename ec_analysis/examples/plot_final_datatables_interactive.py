#!/usr/bin/env python3
"""
Interaktiver Plotter für final_datatables.

Funktionen:
- User wählt Zeitauflösung (30min oder daily)
- User wählt Station
- User wählt eine oder mehrere Variablen
- Mehrere Variablen werden in mehreren Zeilen untereinander geplottet
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

DATA_DIR = Path("/Users/hingerl-l/Data/essd_data_tables/final_datatables")
STATIONS = ["Nazinga", "Kayoro", "Sumbrungu", "Gorigo", "Janga", "Mole"]
MISSING_VALUE = -9999
QC_FILTER_MAP = {"NEE": "CO2_QC", "LE": "LE_QC", "H": "H_QC"}
QC_MAX = 1


def select_resolution() -> str | None:
    print("Zeitauflösung wählen:")
    print("  1) 30min")
    print("  2) daily")
    raw = input("Wahl [1/2]: ").strip() or "1"
    if raw == "1":
        return "30min"
    if raw == "2":
        return "daily"
    print("  Ungültige Auswahl.")
    return None


def get_station_file(station: str, resolution: str) -> Path:
    return DATA_DIR / f"{station}_{resolution}.csv"


def available_stations(resolution: str) -> list[str]:
    out = []
    for s in STATIONS:
        if get_station_file(s, resolution).exists():
            out.append(s)
    return out


def select_station(resolution: str) -> str | None:
    avail = available_stations(resolution)
    if not avail:
        print(f"Keine Dateien für '{resolution}' in {DATA_DIR} gefunden.")
        return None
    print("Verfügbare Stationen:", ", ".join(avail))
    station = input("Station eingeben: ").strip()
    for s in avail:
        if s.lower() == station.lower():
            return s
    print("  Unbekannte Station.")
    return None


def _parse_timestamp(ts_raw: pd.Series) -> pd.DatetimeIndex:
    s = ts_raw.astype(str).str.strip()
    # Entscheide zwischen daily (YYYYMMDD) und 30min (YYYYMMDDHHMMSS) anhand Länge
    lengths = s.str.len()
    if (lengths == 8).all():
        return pd.to_datetime(s, format="%Y%m%d", errors="coerce")
    return pd.to_datetime(s, format="%Y%m%d%H%M%S", errors="coerce")


def load_table(path: Path) -> tuple[pd.DataFrame, list[str], list[str]] | None:
    if not path.exists():
        print(f"Datei nicht gefunden: {path}")
        return None

    with path.open("r", encoding="utf-8") as f:
        header_line = f.readline().strip()
        units_line = f.readline().strip()

    var_names = [c.strip() for c in header_line.split(",")]
    units = [u.strip() for u in units_line.split(",")]
    if len(units) < len(var_names):
        units.extend([""] * (len(var_names) - len(units)))
    else:
        units = units[: len(var_names)]

    df = pd.read_csv(
        path,
        skiprows=2,
        header=None,
        names=var_names,
        low_memory=False,
        na_values=[MISSING_VALUE, str(MISSING_VALUE), "-9999.0", -99999, "7999", "NAN", "nan", "NA"],
    )
    if "TIMESTAMP" not in df.columns or df["TIMESTAMP"].empty:
        print("  Keine TIMESTAMP-Spalte gefunden.")
        return None

    ts = _parse_timestamp(df["TIMESTAMP"])
    df = df.drop(columns=["TIMESTAMP"])
    df.index = ts
    df = df[df.index.notna()].sort_index()
    df = df.replace(MISSING_VALUE, np.nan)
    return df, var_names[1:], units[1:]


def select_variables(var_names: list[str], units: list[str]) -> list[str]:
    print("\nVerfügbare Variablen:")
    for i, v in enumerate(var_names, 1):
        unit = units[i - 1] if i - 1 < len(units) else ""
        print(f"  {i:2d}. {v} [{unit}]")
    print("Eingabe: Nummern (z.B. 1,3,5) oder Variablennamen (z.B. LE,H,NEE)")
    raw = input("Variablen wählen: ").strip()
    if not raw:
        return []

    chosen: list[str] = []
    for part in raw.split(","):
        p = part.strip()
        if not p:
            continue
        if p.isdigit():
            idx = int(p)
            if 1 <= idx <= len(var_names):
                chosen.append(var_names[idx - 1])
        elif p in var_names:
            chosen.append(p)
    # Duplikate entfernen, Reihenfolge behalten
    return list(dict.fromkeys(chosen))


def plot_variables(df: pd.DataFrame, vars_sel: list[str], units_by_var: dict[str, str], station: str, resolution: str) -> None:
    n = len(vars_sel)
    if n == 0:
        print("Keine gültigen Variablen gewählt.")
        return

    fig, axes = plt.subplots(n, 1, figsize=(14, max(3, 2.8 * n)), sharex=True)
    if n == 1:
        axes = [axes]

    for ax, var in zip(axes, vars_sel):
        if var not in df.columns:
            ax.set_title(f"{var} (nicht vorhanden)")
            ax.axis("off")
            continue
        s = pd.to_numeric(df[var], errors="coerce")
        qc_col = QC_FILTER_MAP.get(var)
        if qc_col is not None and qc_col in df.columns:
            qc = pd.to_numeric(df[qc_col], errors="coerce")
            bad = (qc > QC_MAX) | qc.isna()
            s = s.copy()
            s.loc[bad] = np.nan
        ax.plot(s.index, s.values, linewidth=1.0)
        unit = units_by_var.get(var, "")
        ax.set_ylabel(f"{var}\n[{unit}]")
        ax.grid(True, alpha=0.3)

    axes[0].set_title(f"{station} - final_datatables ({resolution})")
    axes[-1].set_xlabel("Zeit")
    fig.tight_layout()
    plt.show()


def main() -> None:
    resolution = select_resolution()
    if resolution is None:
        return

    station = select_station(resolution)
    if station is None:
        return

    path = get_station_file(station, resolution)
    result = load_table(path)
    if result is None:
        return
    df, var_names, units = result
    units_by_var = dict(zip(var_names, units))

    vars_sel = select_variables(var_names, units)
    plot_variables(df, vars_sel, units_by_var, station, resolution)


if __name__ == "__main__":
    main()

