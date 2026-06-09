"""Berechnet G aus den CSV-Rohdaten und hängt die Spalte an {station}_all_variables_30min.csv an."""
import sys
import csv
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from ec_analysis import calculate_soil_heat_flux
from ec_analysis.data_loaders.variable_mapping import STANDARD_UNITS

OUTPUT_BASE = Path("/Users/hingerl-l/Data")
STATIONS = ["Nazinga", "Mole", "Kayoro", "Sumbrungu", "Gorigo", "Janga"]

def load_csv_with_units(path: Path) -> tuple[pd.DataFrame, dict]:
    """Lädt CSV mit Header-Zeile 1 und Einheiten-Zeile 2."""
    header = pd.read_csv(path, nrows=1).columns.tolist()
    df = pd.read_csv(
        path, skiprows=2, header=None, names=header,
        index_col=0, parse_dates=True, low_memory=False,
        na_values=["NAN", "NA", "-9999", "-9999.0", "-999", "**************"],
    )
    df = df[df.index.notna()].sort_index()
    df = df[~df.index.duplicated(keep="first")]
    units = {c: STANDARD_UNITS.get(c, "") for c in header[1:]}
    return df, units

def save_csv_with_units(df: pd.DataFrame, path: Path, units: dict) -> None:
    df = df.copy()
    df.index.name = "Timestamp"
    all_units = [units.get(col, STANDARD_UNITS.get(col, "")) for col in df.columns]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([df.index.name] + list(df.columns))
        w.writerow([""] + all_units)
    df.to_csv(path, mode="a", header=False, date_format="%Y-%m-%d %H:%M:%S")

def main():
    for station in STATIONS:
        path = OUTPUT_BASE / station / "processed" / "all" / f"{station}_all_variables_30min.csv"
        if not path.exists():
            print(f"  {station}: Datei nicht gefunden, überspringe.")
            continue
        df, units = load_csv_with_units(path)
        # Drop existing G column if present (e.g. from collect_all_variables_30min or prior run)
        if "G" in df.columns:
            df = df.drop(columns=["G"])
            if "G" in units:
                del units["G"]
        try:
            G = calculate_soil_heat_flux(df, station=station, return_components=False)
            df["G"] = G
            units["G"] = "W/m²"
            save_csv_with_units(df, path, units)
            print(f"  {station}: G angehängt ({G.notna().sum()} Werte)")
        except Exception as e:
            print(f"  {station}: Fehler - {e}")

if __name__ == "__main__":
    main()
