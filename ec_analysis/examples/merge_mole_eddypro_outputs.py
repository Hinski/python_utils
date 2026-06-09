"""
Merge three Mole EddyPro full-output CSV files into one file.

- One common header (from the first file); optional first metadata line preserved once.
- Data rows from all three files are combined and sorted by date/time.
- Output: same CSV structure, single header, one continuous sorted time series.

Usage:
    python merge_mole_eddypro_outputs.py [--output PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# Die drei EddyPro-Output-Dateien (Reihenfolge beliebig, wird nach Zeit sortiert)
INPUT_FILES = [
    Path("/Users/hingerl-l/Data/Mole/processed/fluxes/eddypro_Mole_full_output_2026-02-12T180440_adv.csv"),
    Path("/Users/hingerl-l/Data/Mole/processed/fluxes/Samuels_eddypro_runs/eddypro_Mole_full_output_2026-02-24T155224_adv.csv"),
    Path("/Users/hingerl-l/Data/Mole/processed/fluxes/eddypro_Mole_full_output_2026-03-11T163039_adv.csv"),
]

DEFAULT_OUTPUT = Path("/Users/hingerl-l/Data/Mole/processed/fluxes/eddypro_Mole_full_output_merged.csv")


def _read_eddypro_data(path: Path) -> tuple[pd.DataFrame, list[str] | None, list[str] | None]:
    """
    Liest eine EddyPro-CSV: optional erste Zeile (Metadata), Header, ggf. Units-Zeile, dann Daten.
    Returns: (DataFrame mit datetime-Index, line0 als Liste oder None, Header-Zeile als Liste oder None).
    """
    with path.open("r", encoding="utf-8", errors="replace") as f:
        line0 = f.readline().strip()
        rest = f.read()

    # Erste Zeile der Datei (oft Metadata) für spätere Ausgabe
    first_line = line0.split(",") if line0 else None

    df = pd.read_csv(
        pd.io.common.StringIO(rest),
        low_memory=False,
        na_values=["-9999", "NAN", "NA"],
    )

    if df.empty:
        return pd.DataFrame(), first_line, df.columns.tolist() if len(df.columns) else None

    # EddyPro: Zeile nach dem Header kann Units sein (erste Zelle enthält '[')
    first_cell = str(df.iloc[0, 0]) if pd.notna(df.iloc[0, 0]) else ""
    if first_cell.startswith("[") or "[" in first_cell:
        df = df.iloc[1:].reset_index(drop=True)

    header_names = df.columns.tolist()

    # Datum/Zeit parsen
    if "date" in df.columns and "time" in df.columns:
        datetime_str = df["date"].astype(str) + " " + df["time"].astype(str)
        df["datetime"] = pd.to_datetime(datetime_str, format="%Y-%m-%d %H:%M", errors="coerce")
    elif "date" in df.columns:
        df["datetime"] = pd.to_datetime(df["date"], errors="coerce")
    else:
        raise ValueError(f"Keine Spalte 'date' (und 'time') in {path.name} gefunden.")

    df = df.dropna(subset=["datetime"])
    df = df.set_index("datetime")
    df = df.drop(columns=["date", "time"], errors="ignore")
    df = df.sort_index()

    return df, first_line, header_names


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge Mole EddyPro full-output CSVs into one file.")
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output CSV path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    missing = [p for p in INPUT_FILES if not p.exists()]
    if missing:
        print("Fehler: Folgende Dateien fehlen:", file=sys.stderr)
        for p in missing:
            print(f"  {p}", file=sys.stderr)
        sys.exit(1)

    first_line = None
    header_names = None
    frames: list[pd.DataFrame] = []

    for path in INPUT_FILES:
        df, line0, names = _read_eddypro_data(path)
        if df.empty:
            print(f"  ⚠ {path.name}: keine Datenzeilen")
            continue
        if header_names is None:
            first_line = line0
            header_names = names
        # Daten-Spalten (ohne date/time, die sind im Index)
        data_cols = [c for c in header_names if c not in ("date", "time")]
        df = df.reindex(columns=[c for c in data_cols if c in df.columns])
        for c in data_cols:
            if c not in df.columns:
                df[c] = pd.NA
        df = df[data_cols]
        frames.append(df)

    if not frames:
        print("Keine Daten zum Zusammenführen.")
        sys.exit(1)

    merged = pd.concat(frames, axis=0)
    merged = merged[~merged.index.duplicated(keep="first")]
    merged = merged.sort_index()

    # Zurück in EddyPro-Format: date und time als Spalten
    merged = merged.reset_index()
    merged["date"] = merged["datetime"].dt.strftime("%Y-%m-%d")
    merged["time"] = merged["datetime"].dt.strftime("%H:%M")
    merged = merged.drop(columns=["datetime"])
    # Spaltenreihenfolge: date, time zuerst (wie in EddyPro)
    out_cols = ["date", "time"] + [c for c in header_names if c not in ("date", "time")]
    merged = merged[[c for c in out_cols if c in merged.columns]]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as f:
        if first_line is not None:
            f.write(",".join(str(x) for x in first_line) + "\n")
        merged.to_csv(f, index=False, na_rep="-9999")

    print(f"✓ {len(merged)} Zeilen nach {args.output}")
    print(f"  Zeitraum: {merged['date'].min()} {merged['time'].min()} – {merged['date'].max()} {merged['time'].max()}")


if __name__ == "__main__":
    main()
