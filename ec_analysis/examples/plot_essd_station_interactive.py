#!/usr/bin/env python3
"""
Interaktives Skript zum Plotten von Variablen aus einer ESSD-Ergebnisdatei.

- Station wird abgefragt (aus essd_data_tables).
- Eine oder mehrere Variablen können gewählt werden.
- Option: Alle Variablen in einem Plot übereinander ODER jede Variable
  in einem eigenen Subplot untereinander (eine Spalte).
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Pfad zu den ESSD-Tabellen (wie in export_essd_data_tables.py)
DATA_BASE = Path("/Users/hingerl-l/Data")
ESSD_DIR = DATA_BASE / "essd_data_tables"
STATIONS = ["Nazinga", "Kayoro", "Sumbrungu", "Gorigo", "Janga", "Mole"]
MISSING_VALUE = -9999


def load_essd_station(station: str) -> tuple[pd.DataFrame, list[str], list[str]] | None:
    """
    Liest die ESSD-CSV einer Station.
    Returns: (DataFrame mit DatetimeIndex, Variablennamen, Units) oder None.
    """
    clean = ESSD_DIR / f"{station}_essd_30min_clean.csv"
    base = ESSD_DIR / f"{station}_essd_30min.csv"
    if clean.exists():
        path = clean
    elif base.exists():
        path = base
    else:
        ptinr(f" Datei nicht gefunden: {clean} oder {base}")
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
        na_values=[MISSING_VALUE, str(MISSING_VALUE), "-9999.0", "nan", "NAN"],
    )

    if "TIMESTAMP" not in df.columns or df["TIMESTAMP"].empty:
        print("  Keine TIMESTAMP-Spalte gefunden.")
        return None

    ts = pd.to_datetime(df["TIMESTAMP"], format="%Y%m%d%H%M%S", errors="coerce")
    df = df.drop(columns=["TIMESTAMP"])
    df.index = ts
    df = df[df.index.notna()].sort_index()
    df = df.replace(MISSING_VALUE, np.nan)
    df = df.replace(float(MISSING_VALUE), np.nan)

    return df, var_names[1:], units[1:]  # ohne TIMESTAMP


def select_station() -> str | None:
    """Fragt die Station ab und gibt den Namen zurück oder None."""
    available = []
    for s in STATIONS:
        p = ESSD_DIR / f"{s}_essd_30min_clean.csv"
        if p.exists():
            available.append(s)
    if not available:
        print(f"Keine ESSD-Dateien in {ESSD_DIR} gefunden.")
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
    return list(dict.fromkeys(chosen))  # Reihenfolge behalten, Duplikate weg


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
    print("ESSD-Station: Variablen interaktiv plotten")
    print("=" * 50)

    station = select_station()
    if not station:
        print("Abgebrochen.")
        return

    result = load_essd_station(station)
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
        # Ein Fenster, alle Variablen übereinander
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
        # Eine Spalte Subplots, eine Variable pro Subplot
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
