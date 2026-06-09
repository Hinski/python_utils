"""
Plot selected variables from collected 30-minute data files.

This script loads CSV files from {station}/processed/all/ and creates
flexible subplots for any number of selected variables.

Usage:
    python plot_all_variables.py --station Nazinga --vars LE H G Rn Tair
    python plot_all_variables.py --station Mole --vars LE H CO2 H2O --start 2020-01-01
    python plot_all_variables.py --station Nazinga --vars LE H G --qc  # Apply quality filters
"""

import argparse
import csv
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec

# Add package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

# ============================================================================
# KONFIGURATION
# ============================================================================
DATA_BASE_DIR = Path("/Users/hingerl-l/Data")

# Standard-Variablen-Gruppen für schnelle Auswahl
VARIABLE_GROUPS = {
    "fluxes": ["LE", "H", "CO2", "G", "Rn"],
    "radiation": ["SW_in", "SW_out", "LW_in", "LW_out", "Rn"],
    "meteo": ["Tair", "Pa", "WS", "WD", "P"],
    "soil": ["G", "VWC", "VWC_1", "VWC_2", "VWC_3", "Ts", "Ts_1", "Ts_2", "Ts_3"],
    "energy_balance": ["Rn", "LE", "H", "G", "Residual"],
    "all_fluxes": ["LE", "H", "CO2", "H2O", "G", "Rn"],
}

# Path to quality filters config (relative to package root)
QUALITY_FILTERS_CONFIG = (
    Path(__file__).parent.parent / "ec_analysis" / "utils" / "quality_filters_config.yaml"
)


def apply_quality_filters(df: pd.DataFrame, station: str, config_path: Path) -> pd.DataFrame:
    """
    Apply quality filters from quality_filters_config.yaml.

    - invalid_codes: Replace with NaN in all columns
    - quality_flags: Set data to NaN where qc > max_flag for LE, H, CO2
    - physical_limits: Set to NaN where value outside [min, max]
    - exclude_periods: Drop rows in configured date ranges
    """
    if yaml is None:
        raise ImportError("PyYAML required for --qc. Install with: pip install pyyaml")

    if not config_path.exists():
        raise FileNotFoundError(f"Quality filters config not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    global_cfg = cfg.get("global", {})
    stations_cfg = cfg.get("stations", {})
    station_cfg = stations_cfg.get(station, {})

    df = df.copy()

    # 1) invalid_codes: replace with NaN
    invalid_codes = global_cfg.get("invalid_codes", [7999, -9999, -99999])
    invalid_numeric = [c for c in invalid_codes if isinstance(c, (int, float))]
    if invalid_numeric:
        df = df.replace(invalid_numeric, np.nan)
    if "NAN" in invalid_codes or "NAN" in str(invalid_codes):
        df = df.replace(["NAN", "nan"], np.nan)

    # 2) quality_flags: mask data where qc > max_flag
    qf_list = station_cfg.get("quality_flags", [])
    for item in qf_list:
        flag_col = item.get("flag")
        data_col = item.get("data_column")
        max_flag = item.get("max_flag", 1)
        if not flag_col or not data_col or flag_col not in df.columns or data_col not in df.columns:
            continue
        qc = pd.to_numeric(df[flag_col], errors="coerce")
        bad_mask = (qc > max_flag) | qc.isna()
        df.loc[bad_mask, data_col] = np.nan

    # 3) physical_limits: merge global + station, apply per column
    global_limits = global_cfg.get("physical_limits", {})
    station_limits = station_cfg.get("physical_limits") or {}
    merged_limits = {**global_limits, **station_limits}
    for col, lim in merged_limits.items():
        if col not in df.columns or not isinstance(lim, dict):
            continue
        vmin = lim.get("min")
        vmax = lim.get("max")
        if vmin is None and vmax is None:
            continue
        vals = pd.to_numeric(df[col], errors="coerce")
        mask = vals.notna()
        if vmin is not None:
            mask = mask & (vals >= vmin)
        if vmax is not None:
            mask = mask & (vals <= vmax)
        df.loc[~mask, col] = np.nan

    # 4) exclude_periods: drop rows in configured date ranges
    exclude_list = station_cfg.get("exclude_periods", [])
    for ep in exclude_list:
        start_s = ep.get("start")
        end_s = ep.get("end")
        if not start_s:
            continue
        start_ts = pd.to_datetime(start_s)
        end_ts = pd.to_datetime(end_s) if end_s else df.index.max()
        mask = (df.index >= start_ts) & (df.index <= end_ts)
        df = df[~mask]

    return df


def load_station_data(
    station: str,
    data_dir: Path = DATA_BASE_DIR,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Tuple[pd.DataFrame, dict]:
    """
    Lade CSV-Datei für eine Station.
    
    - Zeile 1: Variablennamen (erste Spalte = Timestamp)
    - Zeile 2: Einheiten (leer für Timestamp)
    - Ab Zeile 3: Daten
    
    Returns
    -------
    df : pd.DataFrame
        Daten mit Datetime-Index.
    units : dict
        Mapping Variablenname -> Einheit (z. B. {'LE': 'W/m²', 'Tair': '°C'}).
    """
    csv_path = data_dir / station / "processed" / "all" / f"{station}_all_variables_30min.csv"
    
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV-Datei nicht gefunden: {csv_path}")
    
    print(f"Lade Daten von: {csv_path}")
    
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        row2 = next(reader)
    
    # Prüfen, ob Zeile 2 Einheitenzeile ist oder erste Datenzeile (Timestamp)
    has_units_row = True
    if row2 and len(row2) > 0:
        first_parsed = pd.to_datetime(row2[0], errors="coerce")
        if first_parsed is not pd.NaT:
            has_units_row = False  # erste Zelle ist Datum → Zeile 2 = Datenzeile
    
    if not has_units_row:
        # Altes Format: nur Header, dann Daten (Zeile 2 ist schon erste Datenzeile)
        df = pd.read_csv(
            csv_path,
            index_col=0,
            parse_dates=True,
            low_memory=False,
        )
        units = {}
    else:
        # Neues Format: Zeile 1 = Header, Zeile 2 = Einheiten
        if len(row2) >= len(header):
            units_list = [u.strip() if u else "" for u in row2[: len(header)]]
        else:
            units_list = [""] * len(header)
        units = dict(zip(header, units_list))
        df = pd.read_csv(
            csv_path,
            skiprows=2,
            header=None,
            names=header,
            index_col=0,
            parse_dates=True,
            low_memory=False,
        )
    
    print(f"  ✓ Geladen: {len(df)} Zeilen, {len(df.columns)} Spalten")
    print(f"  ✓ Datumsbereich: {df.index.min()} bis {df.index.max()}")
    if any(units.get(c) for c in df.columns):
        print(f"  ✓ Einheitenzeile erkannt")
    print(f"  ✓ Verfügbare Spalten: {', '.join(sorted(df.columns.tolist())[:10])}...")
    
    if start_date:
        df = df[df.index >= pd.to_datetime(start_date)]
        print(f"  ✓ Gefiltert ab: {start_date}")
    if end_date:
        df = df[df.index <= pd.to_datetime(end_date)]
        print(f"  ✓ Gefiltert bis: {end_date}")
    
    return df, units


def plot_variables(
    df: pd.DataFrame,
    variables: List[str],
    station: str,
    units: Optional[dict] = None,
    output_dir: Optional[Path] = None,
    figsize: tuple = (16, 10),
    sharex: bool = True,
    title_prefix: str = "",
    xlim_start: Optional[pd.Timestamp] = None,
    xlim_end: Optional[pd.Timestamp] = None,
) -> Path:
    """
    Plotte ausgewählte Variablen als Subplots.
    
    - units: optional dict Variablenname -> Einheit; wird in der Y-Achsen-Beschriftung verwendet.
    """
    if units is None:
        units = {}
    # Schritt 3: Verfügbare Variablen prüfen
    available_vars = [v for v in variables if v in df.columns]
    missing_vars = [v for v in variables if v not in df.columns]
    
    if missing_vars:
        print(f"  ⚠️  Warnung: Folgende Variablen nicht gefunden: {', '.join(missing_vars)}")
    
    if not available_vars:
        raise ValueError(f"Keine der angegebenen Variablen gefunden: {variables}")
    
    print(f"\nPlotte {len(available_vars)} Variablen: {', '.join(available_vars)}")
    
    # Schritt 4: Immer 1 Spalte, beliebig viele Zeilen
    n_vars = len(available_vars)
    nrows, ncols = n_vars, 1
    
    # Schritt 5: Figur und Subplots erstellen (Höhe skaliert mit Anzahl Variablen)
    width, height = figsize[0], max(4, 2.5 * n_vars)
    fig = plt.figure(figsize=(width, height))
    gs = GridSpec(nrows, ncols, figure=fig, hspace=0.35, wspace=0.2)
    
    # Schritt 6: Jede Variable plotten
    for idx, var in enumerate(available_vars):
        ax = fig.add_subplot(gs[idx, 0])
        
        # Daten plotten
        if var in df.columns:
            ax.plot(df.index, df[var], linewidth=0.8, alpha=0.7, label=var)
            
            # Statistik anzeigen
            valid_data = df[var].dropna()
            if len(valid_data) > 0:
                mean_val = valid_data.mean()
                ax.axhline(y=mean_val, color='r', linestyle='--', linewidth=0.5, alpha=0.5, label=f'Mean: {mean_val:.2f}')
        
        # Schritt 7: Subplot-Formatierung (inkl. Einheit in Y-Achse)
        ax.set_title(var, fontsize=11, fontweight='bold')
        unit_str = units.get(var, "")
        ylabel = f"{var} [{unit_str}]" if unit_str else var
        ax.set_ylabel(ylabel, fontsize=9)
        ax.grid(True, alpha=0.3)
        ax.legend(loc='upper right', fontsize=7)
        # X-Achse: Datumswerte in jedem Subplot
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        # Gemeinsamer Zeitraum: immer gleiche X-Achsen-Limits für alle Subplots
        xmin = xlim_start if xlim_start is not None else df.index.min()
        xmax = xlim_end if xlim_end is not None else df.index.max()
        if xmin is not pd.NaT and xmax is not pd.NaT:
            ax.set_xlim(xmin, xmax)
    
    # Schritt 8: Gesamt-Titel
    title = f"{title_prefix}{station} - {len(available_vars)} Variables" if title_prefix else f"{station} - {len(available_vars)} Variables"
    fig.suptitle(title, fontsize=14, fontweight='bold', y=0.995)
    
    # Schritt 9: Speichern
    if output_dir is None:
        output_dir = Path.cwd()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Dateiname erstellen
    var_names_short = "_".join(available_vars[:3])  # Erste 3 Variablen für Dateiname
    if len(available_vars) > 3:
        var_names_short += f"_and_{len(available_vars)-3}_more"
    filename = f"{station}_variables_{var_names_short}.png"
    output_path = output_dir / filename
    
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"  ✓ Plot gespeichert: {output_path}")
    plt.show()  # Interaktives Fenster (Fenster schließen zum Beenden)
    return output_path


def expand_variable_groups(variables: List[str]) -> List[str]:
    """
    Erweitere Variablen-Gruppen zu einzelnen Variablen.
    
    Beispiel: "fluxes" -> ["LE", "H", "CO2", "G", "Rn"]
    """
    expanded = []
    for var in variables:
        if var in VARIABLE_GROUPS:
            expanded.extend(VARIABLE_GROUPS[var])
        else:
            expanded.append(var)
    return expanded


def main():
    parser = argparse.ArgumentParser(
        description="Plot selected variables from collected 30-minute data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  # Einzelne Variablen plotten
  python plot_all_variables.py --station Nazinga --vars LE H G Rn
  
  # Variablen-Gruppe verwenden
  python plot_all_variables.py --station Mole --vars fluxes
  
  # Kombiniert: Gruppe + einzelne Variablen
  python plot_all_variables.py --station Kayoro --vars fluxes Tair Pa WS
  
  # Mit Datumsbereich
  python plot_all_variables.py --station Gorigo --vars LE H --start 2020-01-01 --end 2021-12-31
  
  # Ausgabeverzeichnis angeben
  python plot_all_variables.py --station Janga --vars soil --output-dir ./plots

  # Mit Quality-Filter (invalid_codes, quality_flags, physical_limits, exclude_periods)
  python plot_all_variables.py --station Nazinga --vars LE H G --qc
        """,
    )
    
    parser.add_argument("--station", type=str, required=True, help="Stationsname")
    parser.add_argument("--vars", type=str, nargs="+", required=True, help="Variablen zum Plotten")
    parser.add_argument("--start", type=str, default=None, help="Startdatum YYYY-MM-DD")
    parser.add_argument("--end", type=str, default=None, help="Enddatum YYYY-MM-DD")
    parser.add_argument("--output-dir", type=str, default=None, help="Ausgabeverzeichnis")
    parser.add_argument("--data-dir", type=str, default=str(DATA_BASE_DIR), help="Daten-Verzeichnis")
    parser.add_argument("--figsize", type=str, default="16,10", help="Figur-Größe 'width,height'")
    parser.add_argument(
        "--qc",
        action="store_true",
        default=False,
        help="Apply quality filters from quality_filters_config.yaml (invalid_codes, quality_flags, physical_limits, exclude_periods)",
    )
    
    args = parser.parse_args()
    
    # Schritt 1: CSV-Datei laden
    print("=" * 60)
    print("SCHRITT 1: CSV-Datei laden")
    print("=" * 60)
    
    try:
        df, units = load_station_data(
            station=args.station,
            data_dir=Path(args.data_dir),
            start_date=args.start,
            end_date=args.end,
        )
    except FileNotFoundError as e:
        print(f"❌ Fehler: {e}")
        return 1

    # Schritt 1b: Quality-Filter anwenden (wenn --qc)
    if args.qc:
        print("\n" + "=" * 60)
        print("SCHRITT 1b: Quality-Filter anwenden (--qc)")
        print("=" * 60)
        try:
            df = apply_quality_filters(df, args.station, QUALITY_FILTERS_CONFIG)
            print(f"  ✓ Quality-Filter angewendet (invalid_codes, quality_flags, physical_limits, exclude_periods)")
            print(f"  ✓ Verbleibende Zeilen: {len(df)}")
        except (ImportError, FileNotFoundError) as e:
            print(f"❌ Fehler bei Quality-Filter: {e}")
            return 1

    # Schritt 2: Variablen erweitern
    print("\n" + "=" * 60)
    print("SCHRITT 2: Variablen auswählen")
    print("=" * 60)
    
    variables = expand_variable_groups(args.vars)
    print(f"  Ausgewählte Variablen: {', '.join(variables)}")
    
    # Schritt 3: Plot erstellen
    print("\n" + "=" * 60)
    print("SCHRITT 3: Subplots erstellen")
    print("=" * 60)
    
    figsize = tuple(map(int, args.figsize.split(",")))
    output_dir = Path(args.output_dir) if args.output_dir else None
    xlim_start = pd.to_datetime(args.start) if args.start else None
    xlim_end = pd.to_datetime(args.end) if args.end else None
    
    try:
        output_path = plot_variables(
            df=df,
            variables=variables,
            station=args.station,
            units=units,
            output_dir=output_dir,
            figsize=figsize,
            xlim_start=xlim_start,
            xlim_end=xlim_end,
        )
        print(f"\n✅ Erfolgreich! Plot gespeichert: {output_path}")
        return 0
    except Exception as e:
        print(f"\n❌ Fehler beim Plotten: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())