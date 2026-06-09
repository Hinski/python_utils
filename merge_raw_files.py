#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Merged alle Dateien eines Stations-"raw"-Ordners zu EINER sauberen Zeitreihe.
Unterstützte Typen: cr1000, radiation, result, smt

WICHTIG: Typbestimmung erfolgt nach SPALTENINHALT, nicht Dateinamen!

Verwendung:
    python merge_raw_files.py                    # Interaktive Stationsauswahl
    python merge_raw_files.py Gorigo             # Direkt für Gorigo
    python merge_raw_files.py /pfad/zur/station  # Mit vollständigem Pfad
"""

from pathlib import Path
import pandas as pd
import re
import sys

from data_loader import (
    read_cr6_csv,
    read_toa5,
    read_csv_firstrow_header,
    read_dragan_csv,
    apply_column_names,
)

# ---------------------------------------------------------------------
# 🎯 Konfiguration
# ---------------------------------------------------------------------
DATA_BASE = Path("/Users/hingerl-l/Data")
#AVAILABLE_STATIONS = ["Gorigo", "Janga", "Kayoro", "Mole", "Nazinga"]
AVAILABLE_STATIONS = ["Sumbrungu"]

# Diese werden in main() gesetzt
STATION_DIR = None
RAW_DIR = None
OUT_DIR = None

# ---------------------------------------------------------------------
# Spalten-Signaturen zur Typbestimmung (UNIQUE pro Typ!)
# ---------------------------------------------------------------------
# WICHTIG: Reihenfolge matters! Spezifischere Signaturen zuerst prüfen.

# Radiation-Dateien haben diese EINZIGARTIGEN Spalten
RADIATION_SIGNATURE_COLS = ['SR_IN_AVG', 'SR_OUT_AVG', 'IR_IN_AVG','IR_OUT_AVG','NETTOT_AVG', 'CNR4TC_AVG', 'NETRN']

# CR1000-Dateien haben diese EINZIGARTIGEN Spalten (Soil/Rain Logger)
# VW_1_Avg (mit Unterstrich+Nummer) ist CR1000, VWC_Avg (ohne Nummer) ist SMT!
CR1000_SIGNATURE_COLS = ['VW_1_AVG', 'VW_2_AVG', 'VW_3_AVG', 'RAIN_MM_TOT', 'TCAV_C_AVG', 'H_FLUX_SC']

# SMT-Dateien haben diese EINZIGARTIGEN Spalten (Soil Moisture/Temperature Probes)
# VWC_Avg (ohne Nummer zwischen Unterstrich) + EC_Avg zusammen = SMT
SMT_SIGNATURE_COLS = ['VWC_AVG', 'VWC_2_AVG', 'EC_AVG', 'EC_2_AVG']

# Result-Dateien (EddyPro) haben keine TOA5 Header
RESULT_SIGNATURE_COLS = ['LVE[W/M²]', 'HTS[W/M²]', 'USTAR[M/S]', 'NEE[MMOL']


# ---------------------------------------------------------------------
# 🔎 Dateityp anhand des INHALTS bestimmen (nicht Dateinamen!)
# ---------------------------------------------------------------------
def detect_type_from_content(path: Path) -> str:
    """Liest Header und bestimmt Dateityp anhand der Spalten."""
    try:
        # Lese erste 5 Zeilen um Header zu finden
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = [f.readline() for _ in range(5)]

        # Kombiniere und normalisiere (uppercase, entferne Quotes)
        header_content = ' '.join(lines).upper().replace('"', '').replace("'", "")

        # REIHENFOLGE WICHTIG: Spezifischere Typen zuerst!

        # 1. Radiation hat sehr spezifische Spalten (SR_IN, IR_IN, CNR4)
        if any(col in header_content for col in RADIATION_SIGNATURE_COLS):
            return "radiation"

        # 2. CR1000 hat VW_1_AVG (mit Nummer), H_FLUX, RAIN_MM
        if any(col in header_content for col in CR1000_SIGNATURE_COLS):
            return "cr1000"

        # 3. SMT hat VWC_AVG (ohne Nummer in Mitte) + EC_AVG
        # Muss BEIDE haben um sicher SMT zu sein
        has_vwc = any(col in header_content for col in ['VWC_AVG', 'VWC_2_AVG', 'VWC_3_AVG'])
        has_ec = any(col in header_content for col in ['EC_AVG', 'EC_2_AVG', 'EC_3_AVG'])
        if has_vwc and has_ec:
            return "smt"

        # 4. Result - normalerweise kein TOA5 Header
        if any(col in header_content for col in RESULT_SIGNATURE_COLS):
            return "result"

        # Fallback: Versuche nach Dateinamen
        return detect_type_from_name(path)

    except Exception as e:
        print(f"  ⚠️ Kann Header nicht lesen: {path.name} - {e}")
        return detect_type_from_name(path)


def detect_type_from_name(path: Path) -> str:
    """Fallback: Dateityp anhand des Namens bestimmen."""
    name = path.name.lower()

    # SMT vor CR1000 prüfen (weil manche SMT-Dateien "cr1000" im Namen haben)
    if "smt" in name or "table3" in name:
        return "smt"

    if "result" in name:
        return "result"

    if "radiation" in name or "rad" in name:
        return "radiation"

    # CR1000 nur wenn "soilrain" oder "table1" dabei ist
    if ("cr1000" in name or "cr3000" in name) and ("soil" in name or "table1" in name):
        return "cr1000"

    if "cr1000" in name:
        # Könnte auch SMT sein - prüfe Inhalt
        return "unknown_cr1000"

    return "unknown"


def detect_type(path: Path) -> str:
    """Hauptfunktion: Bestimmt Dateityp - bevorzugt nach Inhalt."""
    # Erst versuche nach Inhalt
    content_type = detect_type_from_content(path)

    if content_type not in ["unknown", "unknown_cr1000"]:
        return content_type

    # Fallback nach Namen
    name_type = detect_type_from_name(path)

    if name_type == "unknown_cr1000":
        # Unklarer CR1000-Fall - überspringen und warnen
        print(f"  ⚠️ Unklarer Typ für {path.name} - wird übersprungen")
        return "unknown"

    return name_type


# ---------------------------------------------------------------------
# 📥 Loader pro Typ auswählen
# ---------------------------------------------------------------------
def load_file(path: Path, dtype: str) -> pd.DataFrame:
    try:
        if dtype == "cr1000":
            df = read_toa5(path)
            # Validiere dass es wirklich CR1000-Daten sind
            if not any(col in df.columns for col in ['VW_1_Avg', 'BattV_Avg', 'Rain_mm_Tot']):
                print(f"    ⚠️ Keine CR1000-Spalten gefunden in {path.name}")
                return None

        elif dtype == "result":
            df = read_toa5(path)
            df = apply_column_names(df, "result")

        elif dtype == "radiation":
            df = read_toa5(path)
            # Validiere Radiation-Spalten
            if not any(col in df.columns for col in ['SR_in_Avg', 'SR_out_Avg', 'NetTot_Avg', 'CNR4TC_Avg']):
                print(f"    ⚠️ Keine Radiation-Spalten gefunden in {path.name}")
                return None

        elif dtype == "smt":
            df = read_toa5(path)
            # Validiere SMT-Spalten
            if not any(col in df.columns for col in ['VWC_Avg', 'EC_Avg', 'T_Avg']):
                print(f"    ⚠️ Keine SMT-Spalten gefunden in {path.name}")
                return None

        else:
            print(f"⚠️ Überspringe (unbekannter Typ): {path.name}")
            return None

        # WICHTIG: Stelle sicher dass Index ein DatetimeIndex ist
        if not isinstance(df.index, pd.DatetimeIndex):
            try:
                df.index = pd.to_datetime(df.index, errors='coerce')
            except Exception as e:
                print(f"    ⚠️ Index-Konvertierung fehlgeschlagen: {e}")
                return None

        # Entferne NaT (nicht parsebare Timestamps)
        n_before = len(df)
        df = df[df.index.notna()]
        n_nat = n_before - len(df)
        if n_nat > 0:
            print(f"    (Entfernt: {n_nat} Zeilen mit ungültigem Timestamp)")

        if df.empty:
            print(f"    ⚠️ Keine gültigen Daten nach Timestamp-Filterung")
            return None

        # Cleaning
        df = df.sort_index()
        df = df[~df.index.duplicated(keep="first")]

        # Entferne ungültige Timestamps (z.B. 1936, 2025)
        n_before = len(df)
        df = df[(df.index.year >= 2000) & (df.index.year <= 2030)]
        n_removed = n_before - len(df)
        if n_removed > 0:
            print(f"    (Entfernt: {n_removed} Zeilen mit ungültigem Jahr)")

        if df.empty:
            print(f"    ⚠️ Keine gültigen Daten nach Jahr-Filterung")
            return None

        return df

    except Exception as e:
        print(f"❌ Fehler beim Laden von {path.name}: {e}")
        import traceback
        traceback.print_exc()
        return None


# ---------------------------------------------------------------------
# 📌 Dateien pro Typ sammeln & zusammenbauen
# ---------------------------------------------------------------------
def merge_by_type(dtype: str):
    print(f"\n{'='*60}")
    print(f"  Merging Typ: {dtype.upper()}")
    print(f"{'='*60}")

    # Only include files, not directories
    files = sorted([f for f in RAW_DIR.glob("*") if f.is_file() and detect_type(f) == dtype])

    if not files:
        print("  ❌ Keine Dateien gefunden.")
        return

    print(f"  Gefundene Dateien: {len(files)}")
    for f in files:
        print(f"    - {f.name}")
    print()

    dfs = []

    for f in files:
        print(f"  → Lade {f.name}...")
        df = load_file(f, dtype)
        if df is not None and not df.empty:
            print(f"    ✓ {len(df):,} Zeilen, {len(df.columns)} Spalten")
            if len(df) > 0 and isinstance(df.index, pd.DatetimeIndex):
                try:
                    print(f"    Zeitraum: {df.index.min()} → {df.index.max()}")
                except Exception as e:
                    print(f"    ⚠️ Zeitraum konnte nicht bestimmt werden: {e}")
            dfs.append(df)
        else:
            print(f"    ✗ Keine gültigen Daten")

    if not dfs:
        print("\n⚠️ Keine gültigen Daten geladen.")
        return

    # Zeitlich concatenieren
    print(f"\n  Kombiniere {len(dfs)} DataFrames...")
    merged = pd.concat(dfs)
    merged = merged.sort_index()

    n_dups = merged.index.duplicated().sum()
    if n_dups > 0:
        print(f"  (Entferne {n_dups:,} Duplikate)")
    merged = merged[~merged.index.duplicated(keep="first")]

    # Spalten-Info
    print(f"\n  Finale Spalten ({len(merged.columns)}):")
    for col in merged.columns[:10]:
        print(f"    - {col}")
    if len(merged.columns) > 10:
        print(f"    ... und {len(merged.columns) - 10} weitere")

    # Stelle sicher dass Index ein DatetimeIndex ist (sollte schon sein, aber zur Sicherheit)
    if not isinstance(merged.index, pd.DatetimeIndex):
        print(f"  ⚠️ Konvertiere Index zu DatetimeIndex...")
        merged.index = pd.to_datetime(merged.index, errors='coerce')
        merged = merged[merged.index.notna()]
        if merged.empty:
            print("  ❌ Keine gültigen Daten nach Index-Konvertierung")
            return

    # Ausgabe schreiben
    out_path = OUT_DIR / f"{STATION_DIR.name}_{dtype}_merged.csv"
    merged.to_csv(out_path)

    print(f"\n✅ Gespeichert: {out_path.name}")
    try:
        print(f"   Zeitraum: {merged.index.min()} → {merged.index.max()}")
    except Exception as e:
        print(f"   ⚠️ Zeitraum konnte nicht bestimmt werden: {e}")
    print(f"   Zeilen: {len(merged):,}")
    print(f"   Spalten: {len(merged.columns)}")


# ---------------------------------------------------------------------
# Diagnose: Zeige erkannte Dateitypen
# ---------------------------------------------------------------------
def show_file_classification():
    """Zeigt für jede Datei den erkannten Typ."""
    print("\n" + "=" * 60)
    print("  DATEI-KLASSIFIKATION")
    print("=" * 60)

    files = sorted([f for f in RAW_DIR.glob("*") if f.is_file()])

    by_type = {}
    for f in files:
        dtype = detect_type(f)
        if dtype not in by_type:
            by_type[dtype] = []
        by_type[dtype].append(f.name)

    for dtype in ["cr1000", "radiation", "result", "smt", "unknown"]:
        if dtype in by_type:
            print(f"\n  {dtype.upper()} ({len(by_type[dtype])} Dateien):")
            for fname in by_type[dtype][:5]:
                print(f"    - {fname}")
            if len(by_type[dtype]) > 5:
                print(f"    ... und {len(by_type[dtype]) - 5} weitere")

    print()


# ---------------------------------------------------------------------
# Station auswählen
# ---------------------------------------------------------------------
def select_station() -> Path:
    """Interaktive Stationsauswahl oder Kommandozeilen-Argument."""
    global STATION_DIR, RAW_DIR, OUT_DIR

    # Prüfe Kommandozeilen-Argument
    if len(sys.argv) > 1:
        arg = sys.argv[1]

        # Vollständiger Pfad?
        if "/" in arg:
            station_path = Path(arg)
        else:
            # Stationsname
            station_path = DATA_BASE / arg

        if station_path.exists():
            STATION_DIR = station_path
            RAW_DIR = STATION_DIR / "raw"
            OUT_DIR = STATION_DIR / "merged"
            OUT_DIR.mkdir(exist_ok=True)
            return STATION_DIR
        else:
            print(f"❌ Station nicht gefunden: {station_path}")
            sys.exit(1)

    # Interaktive Auswahl
    print("\n" + "=" * 60)
    print("  VERFÜGBARE STATIONEN")
    print("=" * 60)

    valid_stations = []
    for i, station in enumerate(AVAILABLE_STATIONS, 1):
        station_path = DATA_BASE / station
        raw_path = station_path / "raw"

        if raw_path.exists():
            n_files = len(list(raw_path.glob("*")))
            print(f"  {i}) {station:<12} ({n_files} Dateien)")
            valid_stations.append(station)
        else:
            print(f"  -) {station:<12} (kein raw-Ordner)")

    print("=" * 60)

    while True:
        try:
            choice = input(f"\nStation auswählen (1-{len(valid_stations)}): ").strip()

            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(valid_stations):
                    station_name = valid_stations[idx]
                    break
            else:
                # Name eingegeben
                for station in AVAILABLE_STATIONS:
                    if station.lower() == choice.lower():
                        station_name = station
                        break
                else:
                    print("⚠️ Station nicht gefunden.")
                    continue
                break

            print("⚠️ Ungültige Eingabe.")
        except KeyboardInterrupt:
            print("\n\nAbgebrochen.")
            sys.exit(0)

    STATION_DIR = DATA_BASE / station_name
    RAW_DIR = STATION_DIR / "raw"
    OUT_DIR = STATION_DIR / "merged"
    OUT_DIR.mkdir(exist_ok=True)

    return STATION_DIR


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------
def main():
    # Station auswählen
    select_station()

    print("\n" + "=" * 60)
    print(f"  MERGE RAW FILES")
    print(f"  Station: {STATION_DIR.name}")
    print("=" * 60)
    print(f"\n📁 Raw-Ordner: {RAW_DIR}")
    print(f"📁 Output: {OUT_DIR}")

    if not RAW_DIR.exists():
        print(f"\n❌ Raw-Ordner existiert nicht: {RAW_DIR}")
        return

    # Zeige Datei-Klassifikation
    show_file_classification()

    # Frage ob fortfahren
    response = input("Fortfahren mit Merge? [j/N]: ").strip().lower()
    if response not in ['j', 'y', 'ja', 'yes']:
        print("Abgebrochen.")
        return

    for dtype in ["cr1000", "radiation", "result", "smt"]:
        merge_by_type(dtype)

    print("\n" + "=" * 60)
    print("  🎉 FERTIG!")
    print("=" * 60)


if __name__ == "__main__":
    main()
