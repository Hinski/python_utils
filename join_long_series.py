#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Führt Zeitreihen aus merged Dateien zusammen:
1. ~/Data/{Station}/merged/ (merged raw files)

Erstellt eine vollständige Zeitreihe von 2013-01-01 bis 2025-12-01.
Speichert als Parquet (effizient) und optional CSV.

Spaltenumbenennung: Deutsche Namen → Englisch
  - Ost → East
  - Mitte → Middle
"""

import warnings
warnings.filterwarnings('ignore')

from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime
import argparse
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# ---------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------
MERGED_BASE = Path.home() / "Data"
OUTPUT_DIR = Path.home() / "Data" / "merged_long"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

STATIONS = ["Gorigo", "Janga", "Kayoro", "Mole", "Nazinga"]

# Zeitraum für die finale Zeitreihe
START_DATE = "2013-01-01"
END_DATE = "2025-12-01"
FREQ = "30min"  # 30-Minuten-Intervalle (typisch für EC-Daten)

# Dateitypen die zusammengeführt werden
FILE_TYPES = ["cr1000", "radiation", "result", "smt"]

# Spaltenumbenennung: Deutsch → Englisch
COLUMN_RENAME = {
    "H_Flux_sc_8_Ost_Avg": "H_Flux_sc_8_East_Avg",
    "H_Flux_sc_8_Mitte_Avg": "H_Flux_sc_8_Middle_Avg",
    "H_Flux_sc_8_West_Avg": "H_Flux_sc_8_West_Avg",  # bleibt gleich
}

# Type mapping: long file types → merged file types
TYPE_MAPPING = {
    "rad": "radiation",
    "radiation": "radiation",
    "cr1000": "cr1000",
    "result": "result",
    "smt": "smt",
}

# Spaltennamen für Dateien ohne Header
RESULT_COLS = [
    'T_end', 'u[m/s]', 'v[m/s]', 'w[m/s]', 'Ts[°C]', 'Tp[°C]', 'a[g/m³]',
    'CO2[mmol/m³]', 'T_ref[°C]', 'a_ref[g/m³]', 'p_ref[hPa]', 'Var[u]',
    'Var[v]', 'Var[w]', 'Var[Ts]', 'Var[Tp]', 'Var[a]', 'Var[CO2]',
    "Cov[u'v']", "Cov[v'w']", "Cov[u'w']", "Cov[u'Ts']", "Cov[v'Ts']",
    "Cov[w'Ts']", "Cov[u'Tp']", "Cov[v'Tp']", "Cov[w'Tp']",
    "Cov[u'a']", "Cov[v'a']", "Cov[w'a']", "Cov[u'CO2']", "Cov[v'CO2']",
    "Cov[w'CO2']", '???', 'dir[°]', 'ustar[m/s]', 'HTs[W/m²]', 'HTp[W/m²]',
    'LvE[W/m²]', 'z/L', 'z/L-virt', 'Flag(ustar)', 'Flag(HTs)',
    'Flag(HTp)', 'Flag(LvE)', 'Flag(wCO2)', 'T_mid', 'FCstor[mmol/m²s]',
    'NEE[mmol/m²s]', 'Footprint_trgt_1', 'Footprint_trgt_2',
    'Footprnt_xmax[m]', 'r_err_ustar[%]', 'r_err_HTs[%]',
    'r_err_LvE[%]', 'r_err_co2[%]', 'noise_ustar[%]', 'noise_HTs[%]',
    'noise_LvE[%]', 'noise_co2[%]', 'Filler_to_reach61'
]

SMT_COLS = [
    'VWC_Avg', 'EC_Avg', 'T_Avg', 'VWC_2_Avg', 'EC_2_Avg',
    'T_2_Avg', 'VWC_3_Avg', 'EC_3_Avg', 'T_3_Avg'
]

CR1000_COLS = [
    'BattV_Avg', 'PTemp_C_Avg', 'VW_1_Avg', 'PA_uS_1_Avg', 'VW_2_Avg',
    'PA_uS_2_Avg', 'VW_3_Avg', 'PA_uS_3_Avg', 'Rain_mm_Tot', 'TCAV_C_Avg(1)',
    'TCAV_C_Avg(2)', 'TCAV_C_Avg(3)', 'Intensity_RT_Avg', 'Acc_RT_NRT_Tot',
    'Acc_NRT', 'Acc_totNRT', 'Bucket_RT', 'Bucket_NRT', 'Temp_load_cell_Avg',
    'H_Flux_sc_8_East_Avg', 'H_Flux_sc_8_West_Avg', 'H_Flux_sc_8_Middle_Avg',
    'shf_cal(1)', 'shf_cal(2)', 'shf_cal(3)'
]

RADIATION_COLS = [
    'SR_out_Avg', 'SR_in_Avg', 'IR_out_Avg', 'IR_in_Avg', 'CNR4TC_Avg',
    'CNR4TK_Avg', 'NetRs_Avg', 'NetRl_Avg', 'Albedo_Avg', 'OutTot_Avg',
    'InTot_Avg', 'NetTot_Avg', 'IR_OutCo_Avg', 'IR_InCo_Avg'
]

# Variablen die bei Aggregation SUMMIERT werden müssen (statt Mittelwert)
# Pattern-basiert (case-insensitive)
SUM_VARIABLE_PATTERNS = [
    "rain",      # Rain_mm_Tot
    "precip",    # Precipitation
    "acc_",      # Acc_RT_NRT_Tot, Acc_NRT, Acc_totNRT
    "bucket",    # Bucket_RT, Bucket_NRT
    "_tot",      # *_Tot Variablen (Totals)
]

# Spalten aus AmeriFlux-Result-Dateien (z. B. Mole_AmeriFluxFormat.csv), die zusätzlich
# zu EddyPro RESULT_COLS in merged_long erhalten bleiben sollen (P = Niederschlag, RH = rel. Luftfeuchte)
RESULT_EXTRA_COLS_AMERIFLUX = [
    "P",         # Niederschlag (AmeriFlux)
    "RH_1_1_1", "RH_2_1_1", "RH_3_1_1",  # Relative Luftfeuchte
]

# Plot-Konfiguration (wird durch Kommandozeilenargument überschrieben)
PLOT_BEFORE_MERGE = False  # Standardmäßig deaktiviert, kann mit --plot aktiviert werden
PLOT_OUTPUT_DIR = Path.home() / "Data" / "merged_long" / "comparison_plots"

# Variablen die für jeden Dateityp geplottet werden sollen
PLOT_VARIABLES = {
    'cr1000': ['VW_1_Avg', 'VW_2_Avg', 'VW_3_Avg', 'Rain_mm_Tot', 'TCAV_C_Avg(1)', 'H_Flux_sc_8_East_Avg'],
    'radiation': ['SR_in_Avg', 'SR_out_Avg', 'IR_in_Avg', 'IR_out_Avg', 'NetTot_Avg', 'Albedo_Avg'],
    'result': ['LvE[W/m²]', 'HTs[W/m²]', 'ustar[m/s]', 'NEE[mmol/m²s]'],
    'smt': ['VWC_Avg', 'VWC_2_Avg', 'VWC_3_Avg', 'T_Avg', 'T_2_Avg', 'T_3_Avg'],
}


def plot_before_merge(merged_df: pd.DataFrame, long_df: pd.DataFrame,
                      station: str, ftype: str, save: bool = True) -> None:
    """
    Erstellt Plots der merged Zeitreihe.

    Args:
        merged_df: DataFrame aus merged CSV
        long_df: Wird nicht mehr verwendet (für Kompatibilität behalten)
        station: Stationsname
        ftype: Dateityp (cr1000, radiation, result, smt)
        save: Ob Plots gespeichert werden sollen
    """
    if merged_df.empty:
        print("      (Keine Daten für Plot)")
        return

    # Finde Spalten zum Plotten
    plot_vars = PLOT_VARIABLES.get(ftype, [])
    merged_cols = set(merged_df.columns)
    vars_to_plot = [v for v in plot_vars if v in merged_cols]

    # Falls keine der vordefinierten Variablen vorhanden, nimm die ersten 4
    if not vars_to_plot:
        vars_to_plot = list(merged_cols)[:4]

    if not vars_to_plot:
        print("      (Keine Variablen zum Plotten)")
        return

    n_vars = len(vars_to_plot)
    n_cols = 2
    n_rows = (n_vars + 1) // 2

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(16, 4 * n_rows))
    if n_vars == 1:
        axes = np.array([[axes]])
    elif n_rows == 1:
        axes = axes.reshape(1, -1)

    fig.suptitle(f'{station} - {ftype.upper()}: Merged Data',
                 fontsize=14, fontweight='bold')

    for idx, var in enumerate(vars_to_plot):
        row, col = idx // n_cols, idx % n_cols
        ax = axes[row, col]

        # Plot merged - blau
        if var in merged_df.columns:
            merged_series = pd.to_numeric(merged_df[var], errors='coerce')
            valid_merged = merged_series.dropna()
            if len(valid_merged) > 0:
                ax.scatter(valid_merged.index, valid_merged.values,
                          s=1, alpha=0.5, c='blue', label=f'merged ({len(valid_merged):,})')
            else:
                ax.text(0.5, 0.5, 'Keine Daten', transform=ax.transAxes,
                       ha='center', va='center', fontsize=12, color='gray')
        else:
            ax.text(0.5, 0.5, 'Keine Daten', transform=ax.transAxes,
                   ha='center', va='center', fontsize=12, color='gray')

        ax.set_title(var, fontsize=11)
        ax.set_xlabel('')
        ax.grid(True, alpha=0.3)
        ax.legend(loc='upper right', fontsize=8, markerscale=5)

        # Formatierung der x-Achse
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

    # Leere Subplots ausblenden
    for idx in range(n_vars, n_rows * n_cols):
        row, col = idx // n_cols, idx % n_cols
        axes[row, col].set_visible(False)

    plt.tight_layout()

    if save:
        PLOT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        plot_path = PLOT_OUTPUT_DIR / f"{station}_{ftype}_comparison.png"
        plt.savefig(plot_path, dpi=150, bbox_inches='tight')
        print(f"      📊 Plot gespeichert: {plot_path.name}")

    plt.show()
    plt.close()


def plot_year_detail(merged_df: pd.DataFrame, long_df: pd.DataFrame,
                     station: str, ftype: str, year: int = 2019,
                     variables: list = None, save: bool = True) -> None:
    """
    Detailplot für ein bestimmtes Jahr.

    Args:
        merged_df: Die merged Datenquelle
        long_df: Wird nicht mehr verwendet (für Kompatibilität behalten)
        station: Stationsname
        ftype: Dateityp
        year: Jahr für Detailansicht
        variables: Liste der zu plottenden Variablen (default: erste 3 aus PLOT_VARIABLES)
        save: Ob Plot gespeichert werden soll
    """
    if variables is None:
        variables = PLOT_VARIABLES.get(ftype, [])[:3]

    # Filtere auf Jahr
    merged_year = pd.DataFrame()

    if not merged_df.empty:
        mask = merged_df.index.year == year
        merged_year = merged_df.loc[mask]

    if merged_year.empty:
        print(f"      (Keine Daten für Jahr {year})")
        return

    # Finde existierende Variablen
    vars_to_plot = [v for v in variables if v in merged_year.columns][:4]

    if not vars_to_plot:
        return

    n_vars = len(vars_to_plot)
    fig, axes = plt.subplots(n_vars, 1, figsize=(16, 3 * n_vars), sharex=True)
    if n_vars == 1:
        axes = [axes]

    fig.suptitle(f'{station} - {ftype.upper()}: Detail {year}',
                 fontsize=14, fontweight='bold')

    for idx, var in enumerate(vars_to_plot):
        ax = axes[idx]

        # Plot merged
        if var in merged_year.columns:
            merged_series = pd.to_numeric(merged_year[var], errors='coerce').dropna()
            if len(merged_series) > 0:
                ax.plot(merged_series.index, merged_series.values,
                       'b-', alpha=0.7, linewidth=0.5, label=f'merged ({len(merged_series):,})')

        ax.set_ylabel(var, fontsize=10)
        ax.grid(True, alpha=0.3)
        ax.legend(loc='upper right', fontsize=8)

    # x-Achse formatieren
    axes[-1].xaxis.set_major_locator(mdates.MonthLocator())
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%b'))

    plt.tight_layout()

    if save:
        PLOT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        plot_path = PLOT_OUTPUT_DIR / f"{station}_{ftype}_detail_{year}.png"
        plt.savefig(plot_path, dpi=150, bbox_inches='tight')
        print(f"      📊 Detail-Plot gespeichert: {plot_path.name}")

    plt.show()
    plt.close()


def is_sum_variable(col_name: str) -> bool:
    """Prüft ob eine Variable bei Aggregation summiert werden soll."""
    # Exakter Spaltenname P (Niederschlag in AmeriFlux)
    if col_name.strip() == "P":
        return True
    col_lower = col_name.lower()
    for pattern in SUM_VARIABLE_PATTERNS:
        if pattern in col_lower:
            return True
    return False


def resample_to_target_freq(df: pd.DataFrame, target_freq: str = "30min") -> pd.DataFrame:
    """
    Resampelt DataFrame auf Zielfrequenz.

    WICHTIG: Vor dem Resampling wird die Zeitreihe auf einen kontinuierlichen
    Index gebracht (fehlende Zeitschritte werden mit NaN aufgefüllt).

    - Niederschlags-/Akkumulationsvariablen: Summe
    - Alle anderen numerischen: Mittelwert
    - Nicht-numerische Spalten: Erster Wert (first)
    """
    if df.empty:
        return df

    # Bestimme aktuelle Frequenz
    if len(df) < 2:
        return df

    # Entferne Duplikate im Index (behalte ersten Wert)
    if df.index.duplicated().any():
        n_dups = df.index.duplicated().sum()
        df = df[~df.index.duplicated(keep='first')]
        print(f"      (Entfernt: {n_dups} Index-Duplikate)")

    # Sortiere Index
    df = df.sort_index()

    # Bestimme Quellfrequenz aus den Daten
    time_diffs = df.index.to_series().diff().dropna()
    if len(time_diffs) == 0:
        return df

    source_freq = time_diffs.median()
    target_td = pd.Timedelta(target_freq)

    # Wenn bereits in Zielfrequenz (±5min Toleranz), kein Resampling nötig
    if abs(source_freq - target_td) < pd.Timedelta("5min"):
        return df

    print(f"      (Resample: {source_freq} → {target_freq})")

    # WICHTIG: Erst kontinuierlichen Index erstellen und reindexen
    # Dies füllt Lücken mit NaN auf, was für korrektes Resampling nötig ist
    start_time = df.index.min()
    end_time = df.index.max()

    # Bestimme Quellfrequenz-String für date_range
    # Typische Frequenzen: 5min, 10min, 30min, 1h
    if source_freq <= pd.Timedelta("6min"):
        source_freq_str = "5min"
    elif source_freq <= pd.Timedelta("11min"):
        source_freq_str = "10min"
    elif source_freq <= pd.Timedelta("16min"):
        source_freq_str = "15min"
    elif source_freq <= pd.Timedelta("35min"):
        source_freq_str = "30min"
    else:
        source_freq_str = "1h"

    # Erstelle kontinuierlichen Index
    continuous_index = pd.date_range(start=start_time, end=end_time, freq=source_freq_str)

    # Reindexiere auf kontinuierlichen Index (füllt Lücken mit NaN)
    df_continuous = df.reindex(continuous_index)

    n_original = len(df)
    n_continuous = len(df_continuous)
    if n_continuous > n_original:
        n_gaps = n_continuous - n_original
        print(f"      (Gefüllt: {n_gaps} fehlende Zeitschritte mit NaN)")

    # Trenne numerische und nicht-numerische Spalten
    numeric_cols = df_continuous.select_dtypes(include=[np.number]).columns.tolist()
    non_numeric_cols = [col for col in df_continuous.columns if col not in numeric_cols]

    # Trenne numerische Spalten nach Aggregationsmethode
    sum_cols = [col for col in numeric_cols if is_sum_variable(col)]
    mean_cols = [col for col in numeric_cols if col not in sum_cols]

    # Resample
    resampled_parts = []

    if mean_cols:
        # Mittelwert: NaN wird ignoriert (korrekt)
        mean_df = df_continuous[mean_cols].resample(target_freq).mean()
        resampled_parts.append(mean_df)

    if sum_cols:
        # Summe: NaN wird als 0 behandelt (min_count=1 sorgt dafür dass all-NaN = NaN bleibt)
        sum_df = df_continuous[sum_cols].resample(target_freq).sum(min_count=1)
        resampled_parts.append(sum_df)

    if non_numeric_cols:
        # Nicht-numerische: nimm ersten Wert pro Intervall
        first_df = df_continuous[non_numeric_cols].resample(target_freq).first()
        resampled_parts.append(first_df)

    if not resampled_parts:
        return df

    # Kombiniere
    result = pd.concat(resampled_parts, axis=1)

    # Ursprüngliche Spaltenreihenfolge wiederherstellen
    result = result.reindex(columns=df.columns)

    return result


def apply_expected_columns(df: pd.DataFrame, ftype: str) -> pd.DataFrame:
    """Wendet die erwarteten Spaltennamen basierend auf Dateityp an."""
    expected_cols = {
        'result': RESULT_COLS,
        'smt': SMT_COLS,
        'cr1000': CR1000_COLS,
        'radiation': RADIATION_COLS,
    }.get(ftype)

    if expected_cols and len(df.columns) == len(expected_cols):
        df.columns = expected_cols

    return df


def rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Benennt deutsche Spaltennamen in englische um und entfernt Duplikate."""
    df = df.copy()

    # Erst: Deutsche Spalten in englische umbenennen, falls die englische noch nicht existiert
    # Dann: Falls beide existieren, kombiniere sie
    for german, english in COLUMN_RENAME.items():
        if german == english:
            continue

        has_german = german in df.columns
        has_english = english in df.columns

        if has_german and has_english:
            # Beide existieren: kombiniere (english hat Priorität, german füllt NaN)
            mask = df[english].isna()
            df.loc[mask, english] = df.loc[mask, german]
            # Deutsche Spalte löschen
            df = df.drop(columns=[german])
        elif has_german and not has_english:
            # Nur deutsch: umbenennen
            df = df.rename(columns={german: english})

    # Entferne doppelte Spalten (behalte erste)
    df = df.loc[:, ~df.columns.duplicated(keep='first')]

    return df


def read_toa5_file(path: Path, ftype: str = None) -> pd.DataFrame:
    """Liest eine TOA5-Datei (Long-Series Format)."""
    try:
        # Result-Dateien haben kein Header (EddyPro Output)
        if ftype == "result":
            df = pd.read_csv(
                path,
                header=None,
                na_values=["NAN", "NA", "-9999", "-9999.9003906", "INF", "-INF", ""],
                on_bad_lines='skip',
                low_memory=False
            )
            # Erste Spalte ist Timestamp (dd.mm.yyyy HH:MM)
            df[0] = pd.to_datetime(df[0], format='%d.%m.%Y %H:%M', errors='coerce')
            df = df.set_index(0)
            df.index.name = "TIMESTAMP"
            # Spaltennamen zuweisen (61 Spalten nach Index)
            if len(df.columns) == len(RESULT_COLS):
                df.columns = RESULT_COLS
            else:
                print(f"      ⚠️ Result: {len(df.columns)} Spalten (erwartet: {len(RESULT_COLS)})")

        # SMT-Dateien haben kein Header
        elif ftype == "smt":
            df = pd.read_csv(
                path,
                header=None,
                parse_dates=[0],
                index_col=0,
                na_values=["NAN", "NA", "-9999", "INF", "-INF", ""],
                on_bad_lines='skip',
                low_memory=False
            )
            df.index.name = "TIMESTAMP"
            # Spaltennamen zuweisen (9 Spalten nach Index)
            if len(df.columns) == len(SMT_COLS):
                df.columns = SMT_COLS
            else:
                print(f"      ⚠️ SMT: {len(df.columns)} Spalten (erwartet: {len(SMT_COLS)})")

        # CR1000/Radiation haben TOA5 Header
        # TOA5 Format:
        #   Zeile 0: "TOA5", Station info (überspringen)
        #   Zeile 1: Spaltennamen (TIMESTAMP, RECORD, ...) - als Header verwenden
        #   Zeile 2: Einheiten (überspringen)
        #   Zeile 3: Aggregationstyp "Avg", "Tot" etc. (überspringen)
        #   Zeile 4+: Daten
        else:
            df = pd.read_csv(
                path,
                skiprows=[0, 2, 3],  # Überspringe Info, Units, Aggregation - behalte Header
                header=0,
                index_col=0,
                parse_dates=True,
                na_values=["NAN", "NA", "-9999", "INF", "-INF", ""],
                low_memory=False,
                on_bad_lines='skip'
            )

        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, errors='coerce')

        df = df[df.index.notna()]
        df = df[(df.index.year >= 2000) & (df.index.year <= 2030)]
        df = df.sort_index()

        # Entferne RECORD Spalte falls vorhanden
        if 'RECORD' in df.columns:
            df = df.drop(columns=['RECORD'])

        # Wende erwartete Spaltennamen an (für CR1000/radiation falls noch nicht geschehen)
        if ftype not in ['result', 'smt']:  # Diese wurden schon oben behandelt
            df = apply_expected_columns(df, ftype)

        # Entferne Duplikate (wichtig für reindex!)
        if df.index.duplicated().any():
            n_dups = df.index.duplicated().sum()
            df = df[~df.index.duplicated(keep='first')]
            print(f"      (entfernt: {n_dups} Duplikate)")

        # Resample auf Zielfrequenz (30min)
        df = resample_to_target_freq(df, FREQ)

        return rename_columns(df)
    except Exception as e:
        print(f"    ⚠️ Fehler beim Lesen von {path.name}: {e}")
        return pd.DataFrame()


def read_merged_csv(path: Path, ftype: str = None) -> pd.DataFrame:
    """Liest eine merged CSV-Datei."""
    try:
        df = pd.read_csv(
            path,
            index_col=0,
            parse_dates=True,
            na_values=["NAN", "NA", "-9999", "-9999.0", "-9999.9003906", ""],
            low_memory=False,
            on_bad_lines='skip'
        )

        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, errors='coerce')

        df = df[df.index.notna()]
        df = df[(df.index.year >= 2000) & (df.index.year <= 2030)]
        df = df.sort_index()

        # Entferne RECORD Spalte falls vorhanden
        if 'RECORD' in df.columns:
            df = df.drop(columns=['RECORD'])

        # Prüfe ob zu viele Spalten (Problem mit merge_raw_files)
        expected_cols = {
            'result': RESULT_COLS,
            'smt': SMT_COLS,
            'cr1000': CR1000_COLS,
            'radiation': RADIATION_COLS,
        }.get(ftype)

        if expected_cols:
            n_expected = len(expected_cols)
            n_actual = len(df.columns)

            if n_actual > n_expected * 1.5:  # Mehr Spalten als EddyPro (z. B. AmeriFlux)
                # Versuche nur die erwarteten Spalten zu extrahieren
                existing_cols = [col for col in expected_cols if col in df.columns]
                has_ameriflux = any(c in df.columns for c in RESULT_EXTRA_COLS_AMERIFLUX)
                if ftype == "result" and has_ameriflux:
                    # AmeriFlux-Result: Alle Spalten behalten (P, RH_* etc. werden in process_station_type übernommen)
                    pass
                elif len(existing_cols) >= n_expected * 0.5:
                    print(f"      → Behalte {len(existing_cols)} erwartete Spalten")
                    df = df[existing_cols]
                else:
                    # Fallback: Nimm die ersten n_expected Spalten (nur bei nicht-AmeriFlux)
                    print(f"      ⚠️ Zu viele Spalten ({n_actual}), Fallback: erste {n_expected}")
                    df = df.iloc[:, :n_expected]
                    df.columns = expected_cols

        # Wende erwartete Spaltennamen an falls Spaltenanzahl passt
        df = apply_expected_columns(df, ftype)

        # Entferne Duplikate (wichtig für reindex!)
        if df.index.duplicated().any():
            n_dups = df.index.duplicated().sum()
            df = df[~df.index.duplicated(keep='first')]
            print(f"      (entfernt: {n_dups} Duplikate)")

        # Resample auf Zielfrequenz (30min)
        df = resample_to_target_freq(df, FREQ)

        return rename_columns(df)
    except Exception as e:
        print(f"    ⚠️ Fehler beim Lesen von {path.name}: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


def find_long_file(station: str, ftype: str) -> Path | None:
    """Findet die Long-Series Datei für Station und Typ.
    
    DEAKTIVIERT: Long-Series werden nicht mehr verwendet.
    """
    return None


def find_merged_file(station: str, ftype: str) -> Path | None:
    """Findet die Merged-Datei für Station und Typ."""
    merged_dir = MERGED_BASE / station / "merged"
    if not merged_dir.exists():
        return None

    patterns = [
        f"{station}_{ftype}_merged.csv",
        f"{station.lower()}_{ftype}_merged.csv",
    ]

    for pattern in patterns:
        path = merged_dir / pattern
        if path.exists():
            return path

    return None


def create_full_index() -> pd.DatetimeIndex:
    """Erstellt den vollständigen Zeit-Index."""
    return pd.date_range(start=START_DATE, end=END_DATE, freq=FREQ)


def merge_dataframes(merged_df: pd.DataFrame, long_df: pd.DataFrame, full_index: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Reindexiert merged DataFrame auf den vollen Zeitraum.
    Long-Series werden nicht mehr verwendet.
    """
    # Erstelle leeren DataFrame mit vollem Index
    result = pd.DataFrame(index=full_index)
    result.index.name = "TIMESTAMP"

    # Füge merged-Daten hinzu
    if not merged_df.empty:
        merged_reindexed = merged_df.reindex(full_index)

        # Füge alle Spalten hinzu
        for col in merged_reindexed.columns:
            result[col] = merged_reindexed[col]

    return result


def process_station_type(station: str, ftype: str) -> pd.DataFrame | None:
    """Verarbeitet eine Station/Typ-Kombination."""
    print(f"\n  📄 {ftype}:")

    # Finde Quelldateien
    merged_path = find_merged_file(station, ftype)

    if not merged_path:
        print(f"    ❌ Keine Dateien gefunden")
        return None

    # Lade merged
    merged_df = pd.DataFrame()
    if merged_path:
        print(f"    → Lade merged: {merged_path.name}")
        merged_df = read_merged_csv(merged_path, ftype=ftype)
        if not merged_df.empty:
            print(f"      {len(merged_df):,} Zeilen, {len(merged_df.columns)} Spalten, {merged_df.index.min().date()} → {merged_df.index.max().date()}")

    if merged_df.empty:
        print(f"    ❌ Keine gültigen Daten")
        return None

    # Erstelle vollen Zeit-Index
    full_index = create_full_index()

    # Reindexiere merged auf vollen Zeitraum
    long_df = pd.DataFrame()  # Leer, wird nicht mehr verwendet
    result = merge_dataframes(merged_df, long_df, full_index)

    # Entferne RECORD-Spalte falls vorhanden
    if 'RECORD' in result.columns:
        result = result.drop(columns=['RECORD'])

    # Behalte nur erwartete Spalten (entfernt Duplikate durch unterschiedliche Benennung)
    expected_cols = {
        'result': RESULT_COLS,
        'smt': SMT_COLS,
        'cr1000': CR1000_COLS,
        'radiation': RADIATION_COLS,
    }.get(ftype)

    if expected_cols:
        # Finde welche der erwarteten Spalten vorhanden sind
        cols_to_keep = [col for col in expected_cols if col in result.columns]

        # Bei result: Zusätzlich AmeriFlux-Spalten behalten (P, RH_1_1_1, …)
        if ftype == "result":
            for col in result.columns:
                if col in RESULT_EXTRA_COLS_AMERIFLUX or (col.strip() == "P"):
                    if col not in cols_to_keep:
                        cols_to_keep.append(col)
            # Wenn P oder RH vorkommt (AmeriFlux), alle Spalten behalten (inkl. P, RH, PA, TA_* etc.)
            if any(c in result.columns for c in RESULT_EXTRA_COLS_AMERIFLUX) or "P" in result.columns:
                cols_to_keep = list(result.columns)

        # Wenn keine erwarteten Spalten gefunden, versuche Umbenennung nach Position (nur bei EddyPro-ähnlicher Spaltenzahl)
        is_ameriflux_result = ftype == "result" and (
            any(c in result.columns for c in RESULT_EXTRA_COLS_AMERIFLUX) or "P" in result.columns
        )
        if not is_ameriflux_result and len(cols_to_keep) < len(expected_cols) * 0.5:
            print(f"    ⚠️ Nur {len(cols_to_keep)}/{len(expected_cols)} erwartete Spalten gefunden")
            if len(result.columns) == len(expected_cols):
                print(f"    → Benenne {len(expected_cols)} Spalten nach Position um")
                result.columns = expected_cols
                cols_to_keep = list(expected_cols)
            elif len(result.columns) == len(expected_cols) * 2:
                print(f"    → Doppelte Spalten erkannt, behalte erste {len(expected_cols)}")
                result = result.iloc[:, :len(expected_cols)]
                result.columns = expected_cols
                cols_to_keep = list(expected_cols)

        if cols_to_keep:
            result = result[[c for c in cols_to_keep if c in result.columns]]
            print(f"    → Finale Spaltenanzahl: {len(result.columns)}")

    # Statistik
    non_empty_rows = result.dropna(how='all').shape[0]
    coverage = non_empty_rows / len(result) * 100

    print(f"    ✅ Kombiniert: {non_empty_rows:,}/{len(result):,} Zeilen ({coverage:.1f}% Abdeckung)")

    return result


def save_dataframe(df: pd.DataFrame, station: str, ftype: str):
    """Speichert DataFrame als Parquet."""
    base_name = f"{station}_{ftype}_merged_long"

    # Konvertiere alle Spalten zu numerisch (außer Index)
    for col in df.columns:
        if df[col].dtype == 'object':
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Parquet speichern
    parquet_path = OUTPUT_DIR / f"{base_name}.parquet"
    df.to_parquet(parquet_path, compression='snappy')
    parquet_size = parquet_path.stat().st_size / (1024*1024)

    print(f"    💾 Gespeichert: {parquet_path.name} ({parquet_size:.1f} MB)")

    return parquet_path


def select_station() -> str:
    """Fragt den Nutzer nach der Station."""
    print("\n" + "=" * 60)
    print("  Verfügbare Stationen:")
    print("=" * 60)

    for i, station in enumerate(STATIONS, 1):
        merged_dir = MERGED_BASE / station / "merged"
        merged_exists = "✓" if merged_dir.exists() else "✗"

        print(f"  {i}) {station:12s} [merged: {merged_exists}]")

    print(f"  {len(STATIONS)+1}) ALLE Stationen verarbeiten")
    print("=" * 60)

    while True:
        try:
            choice = input(f"\nStation auswählen (1-{len(STATIONS)+1}): ").strip()

            if choice.isdigit():
                idx = int(choice) - 1
                if idx == len(STATIONS):
                    return "ALL"
                if 0 <= idx < len(STATIONS):
                    return STATIONS[idx]
            else:
                # Name eingegeben
                for station in STATIONS:
                    if station.lower() == choice.lower():
                        return station
                if choice.lower() == "all":
                    return "ALL"

            print(f"⚠️ Ungültige Eingabe.")

        except KeyboardInterrupt:
            print("\n\nAbgebrochen.")
            exit(0)


def main():
    # Parse Kommandozeilenargumente
    parser = argparse.ArgumentParser(
        description="Führt Zeitreihen aus merged Dateien zusammen",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python join_long_series.py              # Standard
  python join_long_series.py --plot       # Plots aktiviert
  python join_long_series.py -p           # Plots aktiviert (Kurzform)
        """
    )
    parser.add_argument(
        '--plot', '-p',
        action='store_true',
        help='Aktiviere Vergleichsplots vor dem Mergen'
    )
    args = parser.parse_args()
    
    # Überschreibe PLOT_BEFORE_MERGE mit Kommandozeilenargument
    global PLOT_BEFORE_MERGE
    PLOT_BEFORE_MERGE = args.plot
    
    print("\n" + "=" * 60)
    print("  ZEITREIHEN ZUSAMMENFÜHREN")
    print("  Merged → merged_long")
    print("=" * 60)
    print(f"\n📅 Zeitraum: {START_DATE} → {END_DATE}")
    print(f"📁 Ausgabe:  {OUTPUT_DIR}")
    print(f"📊 Plots:    {'AKTIVIERT' if PLOT_BEFORE_MERGE else 'deaktiviert'}")
    if PLOT_BEFORE_MERGE:
        print(f"   → {PLOT_OUTPUT_DIR}")

    # Station auswählen
    selection = select_station()

    if selection == "ALL":
        stations_to_process = STATIONS
    else:
        stations_to_process = [selection]

    # Verarbeite Stationen
    summary = []

    for station in stations_to_process:
        print(f"\n{'='*60}")
        print(f"📍 Station: {station}")
        print("=" * 60)

        for ftype in FILE_TYPES:
            result = process_station_type(station, ftype)

            if result is not None and not result.dropna(how='all').empty:
                parquet_path = save_dataframe(result, station, ftype)

                # Für Summary
                non_empty = result.dropna(how='all').shape[0]
                coverage = non_empty / len(result) * 100
                summary.append({
                    'station': station,
                    'type': ftype,
                    'rows': non_empty,
                    'coverage': coverage,
                    'file': parquet_path.name
                })

    # Zusammenfassung
    print("\n" + "=" * 60)
    print("  ZUSAMMENFASSUNG")
    print("=" * 60)

    if summary:
        print(f"\n{'Station':<12} {'Typ':<12} {'Zeilen':>10} {'Abdeckung':>10} {'Datei'}")
        print("-" * 70)
        for s in summary:
            print(f"{s['station']:<12} {s['type']:<12} {s['rows']:>10,} {s['coverage']:>9.1f}% {s['file']}")

    print(f"\n📁 Alle Dateien in: {OUTPUT_DIR}")
    print("\n🎉 Fertig!")


if __name__ == "__main__":
    main()
