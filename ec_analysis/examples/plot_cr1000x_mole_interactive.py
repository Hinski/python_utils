#!/usr/bin/env python3
"""
Lädt CR1000XMole_Ground1.dat und CR1000XMole_Ground2.dat und ermöglicht interaktives Plotten.

Verwendung:
  python plot_cr1000x_mole_interactive.py
  python plot_cr1000x_mole_interactive.py --path /Volumes/Extreme\ SSD/WASCAL_5_MOLE

Nach dem Start: Variablenname eingeben (z.B. VW_1_Avg, H_Flux_8_Middle_Avg) und Enter.
Mehrere Variablen durch Komma getrennt. 'list' zeigt alle Variablen. 'q' beendet.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

# Parent for ec_analysis import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ec_analysis import load_ec_data


BASE_PATH = Path("/Users/hingerl-l/Data/Mole/raw/cr1000/")
FILE_1 = "CR1000XMole_Ground1.dat"
FILE_2 = "CR1000XMole_Ground2.dat"


def load_datasets(base: Path) -> dict[str, pd.DataFrame]:
    """Lade beide TOA5-Dateien."""
    if not base.exists():
        print(f"  ⚠ Pfad existiert nicht: {base}")
        return {}
    out = {}
    for name, fname in [("Ground1", FILE_1), ("Ground2", FILE_2)]:
        p = base / fname
        if p.exists():
            try:
                df = load_ec_data(p, format="toa5")
                out[name] = df
                print(f"  ✓ {fname}: {len(df)} Zeilen, {len(df.columns)} Spalten")
            except Exception as e:
                print(f"  ⚠ Fehler beim Laden von {fname}: {e}")
        else:
            print(f"  ⚠ {fname} nicht gefunden unter {p}")
    return out


def plot_variables(datasets: dict[str, pd.DataFrame], vars_str: str) -> None:
    """Plotte angegebene Variablen aus beiden Datensätzen."""
    vars_list = [v.strip() for v in vars_str.split(",") if v.strip()]
    if not vars_list:
        return

    found: list[tuple[str, str, pd.Series]] = []  # (dataset_name, col_name, series)
    for ds_name, df in datasets.items():
        for col in vars_list:
            if col in df.columns:
                ser = pd.to_numeric(df[col], errors="coerce")
                found.append((ds_name, col, ser))
            else:
                print(f"  ⚠ '{col}' nicht in {ds_name}")

    if not found:
        print("  Keine der Variablen gefunden.")
        return

    n = len(found)
    fig, axes = plt.subplots(n, 1, figsize=(12, 3 * n), sharex=True, squeeze=(n == 1))
    if n == 1:
        axes = [axes]

    for ax, (ds_name, col, ser) in zip(axes, found):
        ax.plot(ser.index, ser.values, label=f"{ds_name}.{col}", alpha=0.8)
        ax.set_ylabel(col)
        ax.legend(loc="upper right")
        ax.grid(True, alpha=0.3)

    axes[-1].set_xlabel("Zeit")
    fig.suptitle("CR1000X Mole – interaktiv (Zoom/Pan über Toolbar)", fontsize=10)
    plt.tight_layout()
    plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description="CR1000X Mole Daten interaktiv plotten")
    parser.add_argument(
        "--path", "-p",
        type=Path,
        default=BASE_PATH,
        help=f"Basispfad zu den .dat Dateien (Default: {BASE_PATH})",
    )
    parser.add_argument(
        "--var", "-v",
        type=str,
        default=None,
        help="Variable(n) direkt plotten (Komma-getrennt), ohne interaktive Schleife",
    )
    args = parser.parse_args()

    print("Lade CR1000X Mole Dateien...")
    datasets = load_datasets(args.path)
    if not datasets:
        print("Keine Daten geladen. Beende.")
        sys.exit(1)

    all_cols: set[str] = set()
    for df in datasets.values():
        all_cols.update(c for c in df.columns if c not in ("RECORD",))

    if args.var:
        plot_variables(datasets, args.var)
        return

    print("\nVariablen eingeben (Komma-getrennt für mehrere). 'list' = alle Variablen, 'q' = Ende.\n")

    while True:
        try:
            inp = input("Variable(n): ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not inp:
            continue
        if inp.lower() == "q":
            break
        if inp.lower() == "list":
            for c in sorted(all_cols):
                print(f"  {c}")
            continue

        plot_variables(datasets, inp)


if __name__ == "__main__":
    main()
