#!/usr/bin/env python3
"""
Interaktives Skript zum Plotten von Variablen aus den all_variables_30min-CSVs.

- Station wird abgefragt (aus {Data}/{station}/processed/all/).
- Eine oder mehrere Variablen können gewählt werden.
- Option: Alle Variablen in einem Plot übereinander ODER jede Variable
  in einem eigenen Subplot untereinander (eine Spalte).

Datenquelle: {station}_all_variables_30min.csv (von collect_all_variables_30min.py).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Pfad wie in collect_all_variables_30min.py
DATA_BASE = Path("/Users/hingerl-l/Data")
STATIONS = ["Nazinga", "Kayoro", "Sumbrungu", "Gorigo", "Janga", "Mole"]
NA_VALUES = ["NAN", "NA", "-9999", "-9999.0", "-999", "**************"]


def get_all_variables_path(station: str) -> Path:
    """Pfad zur all_variables_30min.csv einer Station."""
    return DATA_BASE / station / "processed" / "all" / f"{station}_all_variables_30min.csv"


def load_all_variables_station(station: str) -> tuple[pd.DataFrame, list[str], list[str]] | None:
    """
    Liest die all_variables_30min.csv einer Station.
    Format: Zeile 1 = Header, Zeile 2 = Units, ab Zeile 3 = Daten.
    Returns: (DataFrame mit DatetimeIndex, Variablennamen, Units) oder None.
    """
    path = get_all_variables_path(station)
    if not path.exists():
        print(f"  Datei nicht gefunden: {path}")
        return None

    header = pd.read_csv(path, nrows=1).columns.tolist()
    units_row = pd.read_csv(path, skiprows=1, nrows=1, header=None, names=header).iloc[0]
    units = [str(units_row[c]).strip() for c in header]

    df = pd.read_csv(
        path,
        skiprows=2,
        header=None,
        names=header,
        index_col=0,
        parse_dates=True,
        low_memory=False,
        na_values=NA_VALUES,
    )
    df = df[df.index.notna()].sort_index()
    df = df[~df.index.duplicated(keep="first")]

    # Variablen = alle Spalten außer Index (Timestamp)
    var_names = [c for c in header if c != header[0]]
    units_out = [u for c, u in zip(header, units) if c != header[0]]
    return df, var_names, units_out


def select_station() -> str | None:
    """Fragt die Station ab und gibt den Namen zurück oder None."""
    available = [s for s in STATIONS if get_all_variables_path(s).exists()]
    if not available:
        print(f"Keine all_variables_30min.csv in {DATA_BASE}/{{station}}/processed/all/ gefunden.")
        return None
    print("Verfügbare Stationen:", ", ".join(available))
    while True:
        station = input("Station eingeben: ").strip()
        if not station:
            return None
        for s in available:
            if s.lower() == station.lower():
                return s
        print("  Unbekannte Station. Bitte erneut eingeben.")


def select_variables(df: pd.DataFrame, var_names: list[str], units: list[str]) -> list[str]:
    """Fragt ab, welche Variablen geplottet werden sollen."""
    name_to_unit = dict(zip(var_names, units))
    print("\nVerfügbare Variablen:")
    for i, v in enumerate(var_names, 1):
        u = name_to_unit.get(v, "")
        print(f"  {i:2d}. {v}  [{u}]")
    print("  Eingabe: Nummern durch Komma getrennt (z.B. 1,3,5) oder Variablennamen.")
    raw = input("Variablen wählen: ").strip()
    if not raw:
        return []

    chosen = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            idx = int(part)
            if 1 <= idx <= len(var_names):
                chosen.append(var_names[idx - 1])
        else:
            if part in var_names:
                chosen.append(part)
    return list(dict.fromkeys(chosen))


def plot_mode() -> str:
    """Fragt ab: gleiches Fenster (überlagert) oder eigene Subplots untereinander."""
    print("\n  (1) Alle Variablen in einem Plot übereinander (ein Fenster)")
    print("  (2) Jede Variable in eigenem Subplot untereinander (eine Spalte)")
    while True:
        mode = input("Wahl [1/2]: ").strip() or "1"
        if mode in ("1", "2"):
            return mode
        print("  Bitte 1 oder 2 eingeben.")


def main() -> None:
    print("all_variables_30min: Variablen interaktiv plotten")
    print("=" * 50)

    station = select_station()
    if not station:
        print("Abgebrochen.")
        return

    result = load_all_variables_station(station)
    if result is None:
        return
    df, var_names, units = result
    name_to_unit = dict(zip(var_names, units))
    print(f"\n{station}: {len(df)} Zeilen, {len(var_names)} Variablen geladen.")

    variables = select_variables(df, var_names, units)
    if not variables:
        print("Keine Variablen gewählt. Ende.")
        return

    mode = plot_mode()

    if mode == "1":
        fig, ax = plt.subplots(1, 1, figsize=(12, 5))
        for v in variables:
            if v not in df.columns:
                continue
            s = pd.to_numeric(df[v], errors="coerce")
            ax.plot(df.index, s.values, label=v, alpha=0.8)
        ax.set_xlabel("Zeit")
        ax.set_ylabel(" / ".join(name_to_unit.get(v, "-") for v in variables))
        ax.legend(loc="best", fontsize=9)
        ax.set_title(f"{station} – " + ", ".join(variables))
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
    else:
        n = len(variables)
        fig, axes = plt.subplots(n, 1, figsize=(12, max(3, 2.5 * n)), sharex=True)
        if n == 1:
            axes = [axes]
        for ax, v in zip(axes, variables):
            if v not in df.columns:
                ax.set_visible(False)
                continue
            s = pd.to_numeric(df[v], errors="coerce")
            ax.plot(df.index, s.values, color="C0", alpha=0.8)
            ax.set_ylabel(name_to_unit.get(v, "-"))
            ax.set_title(v, fontsize=10)
            ax.grid(True, alpha=0.3)
        axes[-1].set_xlabel("Zeit")
        fig.suptitle(f"{station}", y=1.02, fontsize=12)
        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    main()
