#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Quicklook-Skript:
- fragt den Nutzer nach einer Station
- findet alle merged CSV-Dateien im Ordner
- lädt sie und beschränkt auf 2012-01-01 bis 2025-12-31
- erstellt für jede Datei einen Coverage-Plot mit mindestens 4 Variablen als PNG
"""

from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

from data_loader import read_toa5, apply_column_names


# ---------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------
BASE = Path(__file__).parent
DATA_BASE = Path("/Users/hingerl-l/Data")
PLOT_DIR = BASE / "plots"

# Verfügbare Stationen
STATIONS = ["Gorigo", "Janga", "Kayoro", "Mole", "Nazinga", "Sumbrungu"]

START = "2012-01-01"
END = "2025-12-31"

# Mindestens 4 Variablen pro Datei plotten
MIN_VARIABLES = 4


def select_station() -> str:
    """
    Fragt den Nutzer nach der zu verarbeitenden Station.
    """
    print("\n" + "=" * 50)
    print("  Verfügbare Stationen:")
    print("=" * 50)
    
    for i, station in enumerate(STATIONS, 1):
        station_path = DATA_BASE / station / "merged"
        exists = "✓" if station_path.exists() else "✗"
        print(f"  {i}) {station:12s} [{exists}]")
    
    print("=" * 50)
    
    while True:
        try:
            choice = input("\nStation auswählen (1-6) oder Name eingeben: ").strip()
            
            # Nummer eingegeben
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(STATIONS):
                    return STATIONS[idx]
                print(f"⚠️ Ungültige Nummer. Bitte 1-{len(STATIONS)} eingeben.")
            
            # Name eingegeben (case-insensitive)
            else:
                for station in STATIONS:
                    if station.lower() == choice.lower():
                        return station
                print(f"⚠️ Station '{choice}' nicht gefunden. Verfügbar: {', '.join(STATIONS)}")
        
        except KeyboardInterrupt:
            print("\n\nAbgebrochen.")
            exit(0)


def read_merged_csv(path: Path) -> pd.DataFrame:
    """
    Read a merged CSV file (output from merge_raw_files.py).
    These are regular CSVs with TIMESTAMP as the first column.
    """
    df = pd.read_csv(
        path,
        index_col=0,
        parse_dates=True,
        na_values=["NAN", "NA", "-9999", "-9999.0", "-9999.9003906", "-99999"],
        low_memory=False
    )
    
    # Sicherstellen, dass der Index ein DatetimeIndex ist
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, errors='coerce')
        df = df[df.index.notna()]
    
    df.index.name = "TIMESTAMP"
    return df


def find_merged_files(data_dir: Path):
    """
    Suche nach allen CSV-Dateien im merged-Ordner.
    """
    for path in data_dir.glob("**/*"):
        if not path.is_file():
            continue
        name = path.name.lower()
        if name.endswith(".csv") or name.endswith(".dat"):
            yield path


def detect_filetype(path: Path) -> str:
    """Bestimme den Dateityp anhand des Namens."""
    name = path.name.lower()
    if "result" in name:
        return "result"
    elif "cr1000" in name:
        return "cr1000"
    elif "radiation" in name:
        return "radiation"
    elif "smt" in name:
        return "smt"
    return "unknown"


def find_columns_by_pattern(df: pd.DataFrame, patterns: list) -> list:
    """
    Finde alle Spalten die einem der Patterns entsprechen (case-insensitive).
    """
    found = []
    for col in df.columns:
        col_lower = col.lower()
        for pattern in patterns:
            if pattern.lower() in col_lower:
                if col not in found:
                    found.append(col)
                break
    return found


def choose_columns(df: pd.DataFrame, filetype: str, n: int = 4) -> list:
    """
    Wähle repräsentative Spalten zum Plotten, je nach Dateityp.
    Für cr1000: alle H_Flux, TCAV und VW Variablen via Pattern-Matching.
    """
    selected = []
    
    if filetype == "cr1000":
        # CR1000: Pattern-basierte Auswahl für wichtige Variablengruppen
        # Alle H_Flux Variablen (z.B. H_Flux_sc_8_East_Avg, H_Flux_sc_8_Ost_Avg, etc.)
        h_flux_cols = find_columns_by_pattern(df, ["H_Flux", "H_flux"])
        # Alle TCAV Variablen (z.B. TCAV_C_Avg(1), TCAV_C_Avg(2), etc.)
        tcav_cols = find_columns_by_pattern(df, ["TCAV"])
        # Alle VW Variablen (z.B. VW_1_Avg, VW_2_Avg, etc.)
        vw_cols = find_columns_by_pattern(df, ["VW"])
        
        # Zusätzliche wichtige Einzelvariablen
        extra_cols = ["BattV_Avg", "Rain_mm_Tot", "PTemp_C_Avg"]
        extra_found = [c for c in extra_cols if c in df.columns]
        
        # Alle zusammenfügen (ohne Duplikate)
        for col in extra_found + h_flux_cols + tcav_cols + vw_cols:
            if col not in selected:
                selected.append(col)
    
    elif filetype == "result":
        # Result: priorisierte Liste
        candidates = [
            "LvE[W/m²]", "HTs[W/m²]", "ustar[m/s]", "NEE[mmol/m²s]",
            "Ts[°C]", "u[m/s]", "dir[°]", "z/L", "CO2[mmol/m³]", "a[g/m³]"
        ]
        selected = [c for c in candidates if c in df.columns][:n]
    
    elif filetype == "radiation":
        # Radiation: priorisierte Liste
        candidates = [
            "SR_in_Avg", "SR_out_Avg", "IR_in_Avg", "IR_out_Avg",
            "NetRs_Avg", "NetRl_Avg", "NetTot_Avg", "Albedo_Avg",
            "CNR4TC_Avg", "InTot_Avg", "OutTot_Avg"
        ]
        selected = [c for c in candidates if c in df.columns][:n]
    
    elif filetype == "smt":
        # SMT: alle c1-c9 Spalten
        candidates = ["c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c9"]
        selected = [c for c in candidates if c in df.columns]
    
    # Falls nicht genug Spalten: numerische Spalten hinzufügen (außer für cr1000)
    if len(selected) < n and filetype != "cr1000":
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        for c in numeric_cols:
            if c not in selected and c.upper() != "RECORD":
                selected.append(c)
            if len(selected) >= n:
                break
    
    return selected


def process_file(path: Path, plot_dir: Path):
    print(f"📄 Verarbeite: {path.name}")

    # Dateiname -> filetype
    filetype = detect_filetype(path)
    name_lower = path.name.lower()

    # Laden - merged CSVs vs raw TOA5 files
    try:
        if "merged" in name_lower or path.suffix.lower() == ".csv":
            # Merged files are regular CSVs
            df = read_merged_csv(path)
        else:
            # Raw files need TOA5 parser
            df = read_toa5(path)
            # Apply column names for raw files
            if filetype in ("result", "cr1000"):
                df = apply_column_names(df, filetype=filetype)
    except Exception as e:
        print(f"  ⚠️ Konnte Datei nicht lesen: {e}")
        return

    # Auf Zeitraum 2012–2025 beschränken
    df = df.loc[START:END]

    if df.empty:
        print("  ⚠️ Keine Daten im Zeitraum 2012–2025.")
        return

    # Daily-Coverage: wie viele Zeitpunkte pro Tag?
    coverage = (
        pd.Series(1, index=df.index)
        .resample("D")
        .count()
    )

    # Wähle Spalten zum Plotten (mind. MIN_VARIABLES, aber alle relevanten für cr1000)
    columns = choose_columns(df, filetype, n=MIN_VARIABLES if filetype != "cr1000" else 20)
    n_cols = len(columns)
    
    if n_cols == 0:
        print("  ⚠️ Keine numerischen Spalten zum Plotten gefunden.")
        return

    # Plot erstellen: 1 Coverage + n Variablen
    n_subplots = 1 + n_cols
    fig, axes = plt.subplots(n_subplots, 1, figsize=(14, 3 * n_subplots), sharex=True)
    
    # Falls nur 1 Subplot, axes in Liste umwandeln
    if n_subplots == 1:
        axes = [axes]
    
    # Farben für die Plots
    colors = plt.cm.tab10.colors

    # 1) Coverage Plot
    axes[0].fill_between(coverage.index, coverage.values, alpha=0.7, color=colors[0])
    axes[0].set_ylabel("Records/Tag")
    axes[0].set_title(f"{path.name} – Datenabdeckung ({filetype})")
    axes[0].grid(True, alpha=0.3)

    # 2-n) Variablen-Plots
    for i, col in enumerate(columns):
        ax = axes[i + 1]
        series = df[col].resample("D").mean()
        ax.plot(series.index, series.values, color=colors[(i + 1) % len(colors)], linewidth=0.8)
        ax.set_ylabel(col)
        ax.grid(True, alpha=0.3)
        
        # Statistiken anzeigen
        valid = series.dropna()
        if len(valid) > 0:
            stats_text = f"min: {valid.min():.2f}  max: {valid.max():.2f}  mean: {valid.mean():.2f}"
            ax.text(0.02, 0.95, stats_text, transform=ax.transAxes, 
                    fontsize=8, verticalalignment='top', 
                    bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    axes[-1].set_xlabel("Datum")
    
    fig.tight_layout()

    out_path = plot_dir / f"{path.stem}_availability.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)

    print(f"  ✅ Quicklook gespeichert → {out_path}")
    print(f"     Variablen: {', '.join(columns)}")


def main():
    # Station auswählen
    station = select_station()
    data_dir = DATA_BASE / station / "merged"
    
    print(f"\n📍 Station: {station}")
    print(f"📂 Suche Dateien in: {data_dir}")
    
    if not data_dir.exists():
        print(f"⚠️ Ordner existiert nicht: {data_dir}")
        return
    
    files = list(find_merged_files(data_dir))

    if not files:
        print("Keine CSV/DAT-Dateien gefunden.")
        return

    print(f"   {len(files)} Dateien gefunden.\n")

    # Plot-Ordner mit Stationsname
    station_plot_dir = PLOT_DIR / station
    station_plot_dir.mkdir(parents=True, exist_ok=True)

    for f in sorted(files):
        process_file(f, station_plot_dir)
    
    print(f"\n🎉 Fertig! Plots gespeichert in: {station_plot_dir}")


if __name__ == "__main__":
    main()

