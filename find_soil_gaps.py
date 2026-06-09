#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Findet und füllt Lücken in Soil-Parquet-Dateien mit Bodendaten.

Durchsucht alle *_cr1000_merged_long.parquet und *_smt_merged_long.parquet Dateien
in /Users/hingerl-l/Data/merged_long, identifiziert Lücken in diesen Dateien,
durchsucht rekursiv die angegebenen Quellordner nach Bodendaten-Dateien,
und fügt diese Daten direkt in die Parquet-Dateien ein.

Dateien mit "Radiation" im Namen werden ausgelassen (nur Bodendaten, keine Strahlung).

Bodendaten umfassen:
- Soil Heat Flux (G): H_Flux_sc_8_*, shf_cal(*), G_plate_*
- Soil Water Content (VWC/SWC): VW_*_Avg, VWC_*_Avg, SWC_*_*
- Soil Temperature: TCAV_C_Avg(*), TS_*_*_*, T_*_Avg

Verwendung:
    python find_soil_gaps.py
"""

from pathlib import Path
import pandas as pd
import sys
import shutil
import json
import gc
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from data_loader import read_toa5, read_file_head_and_tail

# ---------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------
MERGED_LONG_DIR = Path("/Users/hingerl-l/Data/merged_long")
# CSV-Dateien die als Quelle für fehlende Daten verwendet werden sollen
CSV_SOURCE_DIRS = [
    Path("/Users/hingerl-l/Data"),
]
#SOURCE_DIRS = [
#    Path("/Volumes/DATA_GHANA/ghana/archive/bolga/WASCAL1GORIGU"),
#    Path("/Volumes/DATA_GHANA/ghana/archive/bolga/Data Gorigo 20220718/data"),
#    Path("/Volumes/DATA_GHANA/ghana/archive/bolga/WASCAL 1 Sumbrungu data"),
#    Path("/Volumes/DATA_GHANA/ghana/archive/bolga/WASCAL 2 Kayoro data"),
#    Path("/Volumes/DATA_GHANA/ghana/archive/bolga/WASCAL 3 Nazinga data"),
#] + CSV_SOURCE_DIRS  # Füge CSV-Quellordner hinzu

SOURCE_DIRS = [
#    Path("/Volumes/Extreme SSD/WASCAL_1_GORIGU"),
#    Path("/Volumes/Extreme SSD/WASCAL_5_Mole"),
#    Path("/Volumes/Extreme SSD/WASCAL_4_JANGA"),
#    Path("/Volumes/Extreme SSD/WASCAL_3_NAZINGA"),
#    Path("/Volumes/Extreme SSD/Gorigo"),
#    Path("/Volumes/Extreme SSD/Gorigo EC"),
#    Path("/Volumes/Extreme SSD/Janga_EC"),
    Path("/Volumes/Extreme SSD/WASCAL_2_KAYORO")
]# + CSV_SOURCE_DIRS  # Füge CSV-Quellordner hinzu
# Bodendaten-Signaturen (Spalten, die eindeutig für Soil-Dateien sind)
# Basierend auf ec_analysis und merge_raw_files.py

# CR1000-Dateien: Soil Heat Flux, Soil Water Content, Soil Temperature
# VW_Avg = gleiche Größe wie VW_1_Avg in anderen Dateien
CR1000_SIGNATURE_COLS = [
    # Soil Heat Flux
    'H_FLUX_SC_8_EAST_AVG', 'H_FLUX_SC_8_WEST_AVG', 'H_FLUX_SC_8_MIDDLE_AVG','H_Flux',
    'H_Flux_sc_8_East_Avg', 'H_Flux_sc_8_West_Avg', 'H_Flux_sc_8_Middle_Avg',
    'SHF_CAL(1)', 'SHF_CAL(2)', 'SHF_CAL(3)', 'shf_cal(1)', 'shf_cal(2)', 'shf_cal(3)',
    'G_PLATE_1_1_1', 'G_PLATE_2_1_1', 'G_PLATE_3_1_1', 'G_plate_1_1_1', 'G_plate_2_1_1', 'G_plate_3_1_1',
    # Soil Water Content (VW_Avg = VW_1_Avg in anderen Dateien)
    'VW_1_AVG', 'VW_2_AVG', 'VW_3_AVG', 'VW_1_Avg', 'VW_2_Avg', 'VW_3_Avg', 'VW_Avg',
    'VWC_1_AVG', 'VWC_2_AVG', 'VWC_3_AVG', 'VWC_1_Avg', 'VWC_2_Avg', 'VWC_3_Avg',
    'SWC_1_1_1', 'SWC_2_1_1', 'SWC_3_1_1',
    # Soil Temperature
    'TCAV_C_AVG(1)', 'TCAV_C_AVG(2)', 'TCAV_C_AVG(3)',
    'TCAV_C_Avg(1)', 'TCAV_C_Avg(2)', 'TCAV_C_Avg(3)',
    'TS_1_1_1', 'TS_2_1_1', 'TS_3_1_1',
    # Weitere CR1000-Spalten
    'RAIN_MM_TOT', 'Rain_mm_Tot', 'BATTV_AVG', 'BattV_Avg',
]

# SMT-Dateien: Soil Moisture/Temperature Probes
# T_Avg = TCAV_C_Avg(1), T_2_Avg = TCAV_C_Avg(2), T_3_Avg = TCAV_C_Avg(3) in anderen Dateien
SMT_SIGNATURE_COLS = [
    'VWC_AVG', 'VWC_2_AVG', 'VWC_3_AVG', 'VWC_Avg', 'VWC_2_Avg', 'VWC_3_Avg',
    'EC_AVG', 'EC_2_AVG', 'EC_3_AVG', 'EC_Avg', 'EC_2_Avg', 'EC_3_Avg',
    'T_AVG', 'T_2_AVG', 'T_3_AVG', 'T_Avg', 'T_2_Avg', 'T_3_Avg',
]

# Kombinierte Liste für schnelle Erkennung
SOIL_SIGNATURE_COLS = CR1000_SIGNATURE_COLS + SMT_SIGNATURE_COLS

# Minimale Lückengröße, die wir füllen wollen (in Stunden)
MIN_GAP_HOURS = 1

# Phase 4: Performance bei vielen Dateien (wie find_radiation_gaps.py)
BATCH_MERGE_SIZE = 15
SAVE_INTERVAL = 50
LOAD_PARALLEL = 0      # 0 = sequentiell, sonst Anzahl Worker (z. B. 4 bei lokaler SSD)
PROGRESS_EVERY = 25

# Spalten, anhand derer "Datenlücken" (NaN-Bereiche) erkannt werden
# Wenn alle diese Spalten NaN sind, gilt die Zeile als lückenhaft (wie in find_radiation_gaps.py)
SOIL_GAP_COLS = [
    'VW_1_Avg', 'VW_2_Avg', 'VW_3_Avg',
    'VWC_1_Avg', 'VWC_2_Avg', 'VWC_3_Avg', 'VWC_Avg', 'VWC_2_Avg', 'VWC_3_Avg',
    'TCAV_C_Avg(1)', 'TCAV_C_Avg(2)', 'TCAV_C_Avg(3)',
    'TS_1_1_1', 'TS_2_1_1', 'TS_3_1_1',
    'G_plate_1_1_1', 'G_plate_2_1_1', 'G_plate_3_1_1',
    'H_Flux_sc_8_East_Avg', 'H_Flux_sc_8_West_Avg', 'H_Flux_sc_8_Middle_Avg',
    'shf_cal(1)', 'shf_cal(2)', 'shf_cal(3)',
    'SWC_1_1_1', 'SWC_2_1_1', 'SWC_3_1_1',
    'EC_Avg', 'EC_2_Avg', 'EC_3_Avg',
    'T_Avg', 'T_2_Avg', 'T_3_Avg',
]

# Station-Zuordnung (abgestimmt mit find_radiation_gaps.py)
# Zusätzlich WASCAL_5_Mole für Bodendaten-Ordner
# Identisch zu find_radiation_gaps.py
STATION_FOLDER_MAPPING = {
    'Gorigo': ['WASCAL_1_GORIGU', 'WASCAL1GORIGU', 'Data Gorigo 20220718', 'gorigo', 'gorigo ec'],
    'Kayoro': ['WASCAL 2 Kayoro data', 'WASCAL 2 Kayoro', 'kayoro'],
    'Nazinga': ['WASCAL 3 Nazinga data', 'WASCAL 3 Nazinga', 'nazinga'],
    'Janga': ['janga'],
    'Mole': ['mole', 'WASCAL_5_MOLE', 'WASCAL_5_Mole'],
    'Sumbrungu': ['WASCAL 1 Sumbrungu data', 'WASCAL 1 Sumbrungu', 'sumbrungu', 'sum'],
}

# Spalten-Mapping für Normalisierung (Quellspalte → Parquet-Spalte)
# VW_Avg = VW_1_Avg; T_Avg = TCAV_C_Avg(1), T_2_Avg = TCAV_C_Avg(2), T_3_Avg = TCAV_C_Avg(3)
COLUMN_MAPPING = {
    # CR1000 Varianten
    'VW_1_AVG': 'VW_1_Avg',
    'VW_2_AVG': 'VW_2_Avg',
    'VW_3_AVG': 'VW_3_Avg',
    'VW_AVG': 'VW_1_Avg',  # VW_Avg = VW_1_Avg in anderen Dateien
    'TCAV_C_AVG(1)': 'TCAV_C_Avg(1)',
    'TCAV_C_AVG(2)': 'TCAV_C_Avg(2)',
    'TCAV_C_AVG(3)': 'TCAV_C_Avg(3)',
    'H_FLUX_SC_8_EAST_AVG': 'H_Flux_sc_8_East_Avg',
    'H_FLUX_SC_8_WEST_AVG': 'H_Flux_sc_8_West_Avg',
    'H_FLUX_SC_8_MIDDLE_AVG': 'H_Flux_sc_8_Middle_Avg',
    'SHF_CAL(1)': 'shf_cal(1)',
    'SHF_CAL(2)': 'shf_cal(2)',
    'SHF_CAL(3)': 'shf_cal(3)',
    # SMT Varianten → Parquet (T_Avg = TCAV_C_Avg(1) etc.)
    'VWC_AVG': 'VWC_Avg',
    'VWC_2_AVG': 'VWC_2_Avg',
    'VWC_3_AVG': 'VWC_3_Avg',
    'EC_AVG': 'EC_Avg',
    'EC_2_AVG': 'EC_2_Avg',
    'EC_3_AVG': 'EC_3_Avg',
    'T_AVG': 'TCAV_C_Avg(1)',   # T_Avg = TCAV_C_Avg(1)
    'T_2_AVG': 'TCAV_C_Avg(2)', # T_2_Avg = TCAV_C_Avg(2)
    'T_3_AVG': 'TCAV_C_Avg(3)', # T_3_Avg = TCAV_C_Avg(3)
}


def is_soil_file_fast(file_path: Path) -> bool:
    """
    Schnelle Prüfung ob eine Datei Bodendaten enthält (nur Header lesen).
    Liest nur die ersten 5 Zeilen um Speicher zu sparen.
    Unterstützt sowohl TOA5-Format als auch CSV-Format.

    WICHTIG: Dateien mit "Radiation" im Namen werden ausgelassen (nur Bodendaten).
    """
    try:
        path_lower = str(file_path).lower()
        if "radiation" in path_lower:
            return False
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = []
            for i, line in enumerate(f):
                if i >= 5:  # Nur erste 5 Zeilen lesen
                    break
                lines.append(line)

            if len(lines) < 1:
                return False

            # Prüfe ob es TOA5- oder CR1000/CR3000-Format ist (Campbell Scientific)
            first_line_upper = lines[0].strip().upper().strip('"').strip("'")
            is_toa5 = first_line_upper.startswith('TOA5')
            is_cr1000_or_3000 = first_line_upper.startswith('CR1000') or first_line_upper.startswith('CR3000')

            if is_toa5 or is_cr1000_or_3000:
                # TOA5/CR1000/CR3000: Header (Spaltennamen) ist normalerweise Zeile 1 oder 2
                if len(lines) > 2:
                    header_line = lines[1]  # oft Zeile 1; Zeile 2 als Fallback prüfen
                    if not any(sig.upper() in header_line.upper() for sig in SOIL_SIGNATURE_COLS) and len(lines) > 3:
                        header_line = lines[2]
                elif len(lines) > 1:
                    header_line = lines[1]
                else:
                    header_line = lines[0]
            else:
                # CSV: Header ist normalerweise Zeile 0
                header_line = lines[0]

            header_upper = header_line.upper()
            # Normalisiere Header: Leerzeichen entfernen, damit z. B. "VWC_3_A       vg" → "VWC_3_AVG" erkannt wird
            header_normalized = ''.join(header_upper.split())

            # Prüfe auf Bodendaten-Signatur-Spalten im Header
            signature_found = any(
                sig_col.upper() in header_normalized
                for sig_col in SOIL_SIGNATURE_COLS
            )

            return signature_found
    except Exception as e:
        # Bei Fehler: nicht als Bodendatei behandeln
        return False


def get_file_time_range_optimized(file_path: Path) -> tuple:
    """
    Extrahiert den Zeitbereich einer Bodendatei (speichereffizient).
    Liest nur erste ~60 Zeilen + letzte ~64KB (kein readlines() auf ganzer Datei).
    Unterstützt sowohl TOA5-Format als auch CSV-Format.

    Returns:
        (start_time, end_time) oder (None, None) bei Fehler
    """
    try:
        first_lines, last_lines = read_file_head_and_tail(file_path, head_lines=60, tail_bytes=65536)

        if len(first_lines) < 2:
            return (None, None)

        first_line_upper = first_lines[0].strip().upper().strip('"').strip("'")
        is_toa5 = first_line_upper.startswith('TOA5')
        is_cr1000_or_3000 = first_line_upper.startswith('CR1000') or first_line_upper.startswith('CR3000')

        if is_toa5 or is_cr1000_or_3000:
            if len(first_lines) < 5:
                return (None, None)
            first_data_line = first_lines[4]
            last_data_line = last_lines[-1] if last_lines else first_lines[-1]
        else:
            first_data_line = first_lines[1] if len(first_lines) > 1 else None
            last_data_line = last_lines[-1] if last_lines else (first_lines[-1] if len(first_lines) > 1 else None)

        if not first_data_line or not last_data_line:
            return (None, None)

        try:
            first_timestamp_str = first_data_line.split(',')[0].strip().strip('"').strip("'")
            last_timestamp_str = last_data_line.split(',')[0].strip().strip('"').strip("'")
            first_time = pd.to_datetime(first_timestamp_str, errors='coerce', dayfirst=False)
            last_time = pd.to_datetime(last_timestamp_str, errors='coerce', dayfirst=False)
            if pd.isna(first_time) or pd.isna(last_time):
                return (None, None)
            return (first_time, last_time)
        except Exception:
            return (None, None)

    except Exception:
        return (None, None)


def find_gaps_in_merged(merged_file: Path, min_gap_hours: float = 1.0) -> tuple:
    """
    Findet Lücken in der merged Parquet-Datei (wie find_radiation_gaps.py).

    Zwei Arten von Lücken:
    1) Index-Lücken: fehlende Zeitstempel (Sprung im Index > min_gap_hours)
    2) Daten-Lücken: Zeitbereiche, in denen Bodenspalten durchgehend NaN sind (>= min_gap_hours)

    Returns:
        (gaps_list, data_start, data_end) wobei:
        - gaps_list: Liste von (gap_start, gap_end, gap_duration) Tupeln
        - data_start: Erster Timestamp in merged Datei
        - data_end: Letzter Timestamp in merged Datei
    """
    print(f"📊 Analysiere {merged_file.name}...")

    df = pd.read_parquet(merged_file)

    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    df = df.sort_index()

    data_start = df.index.min()
    data_end = df.index.max()

    print(f"   Zeitraum: {data_start} bis {data_end}")
    print(f"   Anzahl Zeilen: {len(df):,}")

    min_gap = pd.Timedelta(hours=min_gap_hours)
    gaps = []

    # --- 1) Index-Lücken: fehlende Zeitstempel ---
    time_series = df.index.to_series()
    diffs = time_series.diff()
    for i, (timestamp, diff) in enumerate(diffs.items()):
        if pd.isna(diff):
            continue
        if diff > min_gap:
            gap_start = time_series.iloc[i - 1] if i > 0 else df.index.min()
            gap_end = timestamp
            gaps.append((gap_start, gap_end, diff))

    # --- 2) Daten-Lücken: Bodenspalten durchgehend NaN ---
    has_any_col = False
    for c in SOIL_GAP_COLS:
        if c in df.columns:
            has_any_col = True
            break
    if has_any_col:
        has_any_soil = pd.Series(False, index=df.index)
        for c in SOIL_GAP_COLS:
            if c in df.columns:
                has_any_soil = has_any_soil | df[c].notna()
        invalid = ~has_any_soil
        block_start = None
        for ts in df.index:
            if invalid.loc[ts]:
                if block_start is None:
                    block_start = ts
            else:
                if block_start is not None:
                    gap_dur = ts - block_start
                    if gap_dur >= min_gap:
                        gaps.append((block_start, ts, gap_dur))
                    block_start = None
        if block_start is not None:
            gap_dur = df.index.max() - block_start
            if gap_dur >= min_gap:
                gaps.append((block_start, df.index.max(), gap_dur))

    gaps.sort(key=lambda x: x[0])
    print(f"   Gefundene Lücken (>={min_gap_hours}h): {len(gaps)} (Index + Daten-NaN)")

    del df
    return gaps, data_start, data_end


def write_gaps_list(merged_file: Path, gaps: list, station: str, file_type: str, output_dir: Path = None) -> Path:
    """Schreibt CSV-Liste aller Lücken (Start, Ende, Dauer in Stunden)."""
    if output_dir is None:
        output_dir = merged_file.parent
    out_path = output_dir / f"{station}_{file_type}_gaps.csv"
    rows = []
    for gap_start, gap_end, gap_duration in gaps:
        rows.append({
            'gap_start': gap_start.isoformat(),
            'gap_end': gap_end.isoformat(),
            'duration_hours': round(gap_duration.total_seconds() / 3600, 2),
        })
    if rows:
        pd.DataFrame(rows).to_csv(out_path, index=False)
        print(f"   📄 Lückenliste: {out_path.name} ({len(rows)} Lücken)")
    return out_path


CACHE_DIR = MERGED_LONG_DIR / ".gaps_cache"
FILE_RANGES_CACHE = CACHE_DIR / "soil_file_ranges.json"
SEARCHED_NO_DATA_FILE = CACHE_DIR / "soil_searched_no_data.json"


def _load_file_ranges_cache() -> dict:
    if not FILE_RANGES_CACHE.exists():
        return {}
    try:
        with open(FILE_RANGES_CACHE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_file_ranges_cache(cache: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(FILE_RANGES_CACHE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=0)
    except Exception as e:
        print(f"   ⚠️ Cache konnte nicht geschrieben werden: {e}")


def scan_source_directories(source_dirs: list, use_cache: bool = True) -> dict:
    """
    Durchsucht Quellordner rekursiv nach Bodendaten-Dateien.
    Nutzt Cache (.gaps_cache/soil_file_ranges.json): bereits gelesene Zeitbereiche
    werden wiederverwendet → kein erneutes Öffnen der Dateien.

    Returns:
        Dict: {file_path: (start_time, end_time)}
    """
    soil_files = {}
    cache = _load_file_ranges_cache() if use_cache else {}
    cache_updated = False

    for source_dir in source_dirs:
        if not source_dir.exists():
            print(f"⚠️  Ordner existiert nicht: {source_dir}")
            continue

        print(f"\n🔍 Durchsuche: {source_dir}")
        if use_cache and cache:
            print(f"   (Cache: {len(cache)} Dateien – keine erneute Leseoperation für diese)")

        file_count = 0
        skipped_dirs = 0
        for ext in ['*.dat', '*.csv']:
            for file_path in source_dir.rglob(ext):
                path_parts = file_path.parts
                if any('turbulence' in part.lower() for part in path_parts):
                    skipped_dirs += 1
                    continue
                if 'radiation' in file_path.name.lower():
                    continue

                file_count += 1

                if file_count % 100 == 0:
                    print(f"   Geprüft: {file_count} (gefunden: {len(soil_files)})...", end='\r')

                path_str = str(file_path.resolve())
                if use_cache and path_str in cache:
                    cached = cache[path_str]
                    if cached and len(cached) == 2:
                        try:
                            start_t = pd.to_datetime(cached[0])
                            end_t = pd.to_datetime(cached[1])
                            if pd.notna(start_t) and pd.notna(end_t):
                                soil_files[file_path] = (start_t, end_t)
                        except Exception:
                            pass
                    continue

                if not is_soil_file_fast(file_path):
                    continue

                time_range = get_file_time_range_optimized(file_path)
                if time_range[0] is not None:
                    soil_files[file_path] = time_range
                    if use_cache:
                        cache[path_str] = [
                            time_range[0].isoformat() if hasattr(time_range[0], 'isoformat') else str(time_range[0]),
                            time_range[1].isoformat() if hasattr(time_range[1], 'isoformat') else str(time_range[1]),
                        ]
                        cache_updated = True
                    print(f"\n   ✓ Gefunden: {file_path.name} ({time_range[0]} - {time_range[1]})")

                    if len(soil_files) % 200 == 0:
                        import gc
                        gc.collect()

        print(f"\n   Gesamt geprüft: {file_count} Dateien")
        if skipped_dirs > 0:
            print(f"   Übersprungen (Turbulence): {skipped_dirs}")

    if use_cache and cache_updated:
        _save_file_ranges_cache(cache)

    return soil_files


def find_files_filling_gaps(gaps: list, soil_files: dict, data_start: pd.Timestamp, data_end: pd.Timestamp) -> dict:
    """
    Findet Dateien, die Lücken füllen können, sowie Daten vor/nach dem Zeitbereich.

    Returns:
        Dict mit Keys:
        - 'gaps': {gap_index: [(file_path, overlap_start, overlap_end, coverage_pct), ...]}
        - 'before_start': [(file_path, file_start, file_end), ...]
        - 'after_end': [(file_path, file_start, file_end), ...]
        - 'within_range': [(file_path, file_start, file_end), ...] - Dateien innerhalb des Zeitbereichs
    """
    matches = {
        'gaps': defaultdict(list),
        'before_start': [],
        'after_end': [],
        'within_range': []
    }

    print(f"\n🔗 Vergleiche {len(soil_files)} Bodendateien...")
    print(f"   - Mit {len(gaps)} Lücken")
    print(f"   - Vor Start ({data_start})")
    print(f"   - Nach Ende ({data_end})")

    # Gaps nach Start sortieren → frühes Break wenn gap_start > file_end (schneller bei vielen Lücken)
    gaps_sorted = sorted(enumerate(gaps), key=lambda x: x[1][0])

    for file_path, (file_start, file_end) in soil_files.items():
        if file_end < data_start:
            matches['before_start'].append((file_path, file_start, file_end))
            continue
        if file_start > data_end:
            matches['after_end'].append((file_path, file_start, file_end))
            continue

        matched_gap = False
        for gap_idx, (gap_start, gap_end, gap_duration) in gaps_sorted:
            if gap_start > file_end:
                break
            gap_timedelta = gap_end - gap_start
            if file_end < gap_start or file_start > gap_end:
                continue
            overlap_start = max(gap_start, file_start)
            overlap_end = min(gap_end, file_end)
            if overlap_start < overlap_end:
                coverage_pct = ((overlap_end - overlap_start) / gap_timedelta) * 100
                matches['gaps'][gap_idx].append((
                    file_path,
                    overlap_start,
                    overlap_end,
                    coverage_pct
                ))
                matched_gap = True

        if not matched_gap and file_start <= data_end and file_end >= data_start:
            matches['within_range'].append((file_path, file_start, file_end))

    return matches


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalisiert Spaltennamen für Konsistenz mit merged Datei.
    """
    df = df.copy()

    column_mapping = {}
    for col in df.columns:
        col_upper = col.upper()
        if col_upper in COLUMN_MAPPING:
            column_mapping[col] = COLUMN_MAPPING[col_upper]
        else:
            for target_col in COLUMN_MAPPING.values():
                if col.upper() == target_col.upper():
                    column_mapping[col] = target_col
                    break

    if column_mapping:
        df = df.rename(columns=column_mapping)

    return df


def load_and_merge_soil_file(file_path: Path, merged_df=None, target_columns=None, existing_index=None) -> pd.DataFrame:
    """
    Lädt eine Bodendatei (TOA5 oder CSV) und gibt nur neue Daten zurück (keine Duplikate).

    Args:
        file_path: Pfad zur Quelldatei
        merged_df: Optional – Parquet-DataFrame (für Spalten/Index). Wenn target_columns/existing_index gesetzt, ignoriert.
        target_columns: Optional – Liste der Zielspalten (schneller bei vielen Dateien).
        existing_index: Optional – Index der bestehenden Daten (nur neue Zeitstempel zurückgeben).

    Returns:
        DataFrame mit neuen Daten, die noch nicht in merged_df sind
    """
    try:
        cols_ref = target_columns if target_columns is not None else (merged_df.columns if merged_df is not None and not merged_df.empty else None)
        existing = existing_index if existing_index is not None else (merged_df.index if merged_df is not None and not merged_df.empty else None)
        # Prüfe ob es eine CSV-Datei ist
        if file_path.suffix.lower() == '.csv':
            if 'merged' in file_path.name.lower():
                # Merged CSV-Format: TIMESTAMP-Spalte
                df_new = pd.read_csv(
                    file_path,
                    parse_dates=['TIMESTAMP'],
                    index_col='TIMESTAMP',
                    na_values=["NAN", "NA", "-9999", ""],
                    low_memory=False
                )
            else:
                # Andere CSV-Dateien: Versuche TOA5-Format
                try:
                    df_new = read_toa5(file_path)
                except (ValueError, pd.errors.EmptyDataError, TypeError) as e:
                    # Fallback: Versuche als normale CSV zu laden
                    try:
                        df_new = pd.read_csv(
                            file_path,
                            index_col=0,
                            parse_dates=True,
                            na_values=["NAN", "NA", "-9999", ""],
                            low_memory=False,
                            on_bad_lines='skip'
                        )
                        if not isinstance(df_new.index, pd.DatetimeIndex):
                            df_new.index = pd.to_datetime(df_new.index, errors='coerce')
                    except Exception as e2:
                        print(f"      ⚠️  CSV-Laden fehlgeschlagen: {e2}")
                        return pd.DataFrame()
        else:
            # TOA5-Format (.dat Dateien)
            try:
                df_new = read_toa5(file_path)
            except (ValueError, pd.errors.EmptyDataError, TypeError) as e:
                # Fallback: Versuche manuell zu laden
                try:
                    # Versuche als normale CSV zu laden (manche .dat Dateien sind eigentlich CSV)
                    df_new = pd.read_csv(
                        file_path,
                        index_col=0,
                        parse_dates=True,
                        na_values=["NAN", "NA", "-9999", ""],
                        low_memory=False,
                        on_bad_lines='skip'
                    )
                    if not isinstance(df_new.index, pd.DatetimeIndex):
                        df_new.index = pd.to_datetime(df_new.index, errors='coerce')
                except Exception as e2:
                    # Wenn auch das fehlschlägt, überspringe die Datei
                    return pd.DataFrame()

        if df_new.empty:
            return pd.DataFrame()

        # Normalisiere Spalten
        df_new = normalize_columns(df_new)

        # Entferne NaT
        df_new = df_new[df_new.index.notna()]
        if df_new.empty:
            return pd.DataFrame()

        # Entferne RECORD Spalte falls vorhanden
        if 'RECORD' in df_new.columns:
            df_new = df_new.drop(columns=['RECORD'])

        # WICHTIG: Konvertiere alle numerischen Spalten zu numerischen Typen
        for col in df_new.columns:
            if df_new[col].dtype == 'object':
                df_new[col] = pd.to_numeric(df_new[col], errors='coerce')

        if cols_ref is not None:
            common_cols = [col for col in cols_ref if col in df_new.columns]
            if common_cols:
                df_new = df_new[common_cols]

        if existing is not None:
            existing_timestamps = set(existing)
            new_mask = ~df_new.index.isin(existing_timestamps)
            df_new = df_new[new_mask]

        return df_new

    except UnicodeDecodeError as e:
        print(f"    ⚠️  Encoding-Fehler ({file_path.name}): {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"    ⚠️  Fehler beim Laden von {file_path.name}: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


def detect_station_from_path(file_path: Path) -> str:
    """
    Erkennt die Station basierend auf dem Dateipfad.
    """
    path_str = str(file_path).lower()

    for station, folder_keywords in STATION_FOLDER_MAPPING.items():
        for keyword in folder_keywords:
            if keyword.lower() in path_str:
                return station

    return None


def filter_files_for_station(soil_files: dict, station: str) -> dict:
    """
    Filtert Bodendateien für eine bestimmte Station basierend auf dem Pfad.
    """
    station_files = {}

    for file_path, time_range in soil_files.items():
        detected_station = detect_station_from_path(file_path)
        if detected_station == station:
            station_files[file_path] = time_range

    return station_files


def find_soil_parquet_files(merged_long_dir: Path) -> list:
    """
    Findet alle Soil-Parquet-Dateien im merged_long Verzeichnis.
    Berücksichtigt sowohl CR1000 als auch SMT-Dateien.

    Returns:
        Liste von Path-Objekten zu Bodendaten-Parquet-Dateien
    """
    if not merged_long_dir.exists():
        print(f"❌ Verzeichnis existiert nicht: {merged_long_dir}")
        return []

    parquet_files = []

    # CR1000-Dateien
    cr1000_files = list(merged_long_dir.glob("*_cr1000_merged_long.parquet"))
    parquet_files.extend(cr1000_files)

    # SMT-Dateien
    smt_files = list(merged_long_dir.glob("*_smt_merged_long.parquet"))
    parquet_files.extend(smt_files)

    return sorted(parquet_files)


def find_csv_files_for_station(csv_source_dirs: list, station: str, file_type: str) -> list:
    """
    Findet CSV-Dateien die zu einer Station gehören.

    Args:
        csv_source_dirs: Liste von Verzeichnissen zum Durchsuchen
        station: Stationsname (z.B. 'Gorigo')
        file_type: 'cr1000' oder 'smt'

    Returns:
        Liste von CSV-Dateipfaden die zu dieser Station gehören
    """
    csv_files = []

    for csv_dir in csv_source_dirs:
        if not csv_dir.exists():
            continue

        patterns = [
            f"{station}_{file_type}_merged.csv",
            f"{station}_{file_type}_merged_*.csv",
        ]

        for pattern in patterns:
            for csv_file in csv_dir.rglob(pattern):
                if is_soil_file_fast(csv_file):
                    csv_files.append(csv_file)
                    print(f"   ✓ CSV gefunden: {csv_file}")

        # Auch in Unterordnern suchen
        for station_dir in csv_dir.glob(f"*/{station}/*"):
            if station_dir.is_dir():
                for csv_file in station_dir.rglob(f"*{file_type}*merged*.csv"):
                    if is_soil_file_fast(csv_file):
                        csv_files.append(csv_file)
                        print(f"   ✓ CSV gefunden: {csv_file}")

    return csv_files


def find_files_for_parquet(parquet_file: Path, soil_files: dict) -> list:
    """
    Findet alle Dateien, die Lücken in einer Parquet-Datei füllen können.
    """
    # Erkenne Station und Typ aus Dateinamen
    if '_cr1000_merged_long' in parquet_file.stem:
        station = parquet_file.stem.replace('_cr1000_merged_long', '')
        file_type = 'cr1000'
    elif '_smt_merged_long' in parquet_file.stem:
        station = parquet_file.stem.replace('_smt_merged_long', '')
        file_type = 'smt'
    else:
        station = parquet_file.stem.split('_')[0]
        file_type = 'cr1000'  # Fallback

    print(f"\n{'=' * 80}")
    print(f"🔍 Analysiere Station: {station} ({file_type})")
    print(f"   Datei: {parquet_file.name}")
    print("=" * 80)

    # Finde Lücken
    gaps, data_start, data_end = find_gaps_in_merged(parquet_file, MIN_GAP_HOURS)

    if not gaps:
        df = pd.read_parquet(parquet_file)
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        if len(df) > 0:
            data_start = df.index.min()
            data_end = df.index.max()
        del df

    # Filtere Dateien für diese Station
    station_files = filter_files_for_station(soil_files, station)
    print(f"   Gefiltert: {len(station_files)} von {len(soil_files)} Dateien gehören zu {station}")

    # Finde CSV-Dateien
    print(f"\n   Suche CSV-Dateien für {station} ({file_type})...")
    csv_files = find_csv_files_for_station(CSV_SOURCE_DIRS, station, file_type)

    csv_files_with_range = []
    for csv_file in csv_files:
        time_range = get_file_time_range_optimized(csv_file)
        if time_range[0] is not None:
            station_files[csv_file] = time_range
            csv_files_with_range.append((csv_file, time_range))
            print(f"   ✓ CSV hinzugefügt: {csv_file.name} ({time_range[0]} - {time_range[1]})")

    # Finde passende Dateien
    matches = find_files_filling_gaps(gaps, station_files, data_start, data_end)

    # Sammle alle Dateipfade
    file_paths = []

    for file_path, _, _ in matches['before_start']:
        file_paths.append(file_path)

    for file_path, _, _ in matches['after_end']:
        file_paths.append(file_path)

    for gap_matches in matches['gaps'].values():
        for file_path, _, _, _ in gap_matches:
            file_paths.append(file_path)

    if 'within_range' in matches:
        for file_path, _, _ in matches['within_range']:
            if file_path not in file_paths:
                file_paths.append(file_path)
                print(f"   ✓ Datei innerhalb Zeitbereich hinzugefügt: {file_path.name}")

    for csv_file, (csv_start, csv_end) in csv_files_with_range:
        if csv_start <= data_end and csv_end >= data_start:
            if csv_file not in file_paths:
                file_paths.append(csv_file)
                print(f"   ✓ CSV innerhalb Zeitbereich hinzugefügt: {csv_file.name}")

    file_paths = list(set(file_paths))

    if not file_paths:
        print(f"\n⚠️  Keine passenden Dateien für {station} gefunden.")
        return []

    print(f"\n📋 Gefunden: {len(file_paths)} eindeutige Dateien für {station}")
    print(f"   - Vor Start: {len(matches['before_start'])}")
    print(f"   - Nach Ende: {len(matches['after_end'])}")
    print(f"   - Für Lücken: {sum(len(v) for v in matches['gaps'].values())}")
    if 'within_range' in matches:
        print(f"   - Innerhalb Zeitbereich: {len(matches['within_range'])}")
    if csv_files:
        print(f"   - CSV-Dateien: {len(csv_files)}")

    return file_paths


def fill_gaps_in_merged(merged_file: Path, files_to_merge: list) -> bool:
    """
    Füllt Lücken in merged Parquet-Datei mit Daten aus gefundenen Dateien.
    Batch-basiert (wie find_radiation_gaps.py) für bessere Performance bei vielen Dateien.
    """
    if not files_to_merge:
        print("   ⚠️  Keine Dateien zum Mergen")
        return False

    backup_file = merged_file.with_suffix('.parquet.backup')
    if not backup_file.exists():
        print(f"💾 Erstelle Backup: {backup_file.name}")
        shutil.copy2(merged_file, backup_file)
    else:
        print(f"💾 Backup existiert bereits: {backup_file.name}")

    print(f"\n📖 Lade {merged_file.name}...")
    merged_df = pd.read_parquet(merged_file)
    if not isinstance(merged_df.index, pd.DatetimeIndex):
        merged_df.index = pd.to_datetime(merged_df.index)

    original_count = len(merged_df)
    print(f"   Original: {original_count:,} Zeilen")

    target_columns = list(merged_df.columns)
    existing_index = merged_df.index
    total_new_rows = 0
    files_processed = 0
    batch_dfs = []
    file_paths = sorted(files_to_merge)
    n_paths = len(file_paths)
    show_progress = n_paths > 50
    n_workers = max(1, LOAD_PARALLEL) if LOAD_PARALLEL else 1

    print(f"\n   Verarbeite {n_paths} Dateien (Batch-Merge: {BATCH_MERGE_SIZE}, Speichern alle {SAVE_INTERVAL})...")
    if n_workers > 1:
        print(f"   Paralleles Laden: {n_workers} Worker")

    def load_one(path):
        try:
            return path, load_and_merge_soil_file(path, target_columns=target_columns, existing_index=existing_index)
        except Exception:
            return path, None

    i = 0
    while i < n_paths:
        batch_paths = file_paths[i : i + BATCH_MERGE_SIZE]
        i += len(batch_paths)
        files_processed += len(batch_paths)

        if show_progress and (files_processed % PROGRESS_EVERY == 0 or files_processed == n_paths):
            print(f"\n   [{files_processed}/{n_paths}] ...")

        if n_workers > 1 and len(batch_paths) > 1:
            with ThreadPoolExecutor(max_workers=n_workers) as ex:
                for path, df_new in ex.map(load_one, batch_paths):
                    if df_new is not None and not df_new.empty:
                        batch_dfs.append(df_new)
        else:
            for file_path in batch_paths:
                try:
                    df_new = load_and_merge_soil_file(file_path, target_columns=target_columns, existing_index=existing_index)
                    if not df_new.empty:
                        batch_dfs.append(df_new)
                except Exception as e:
                    if not show_progress:
                        print(f"      ⚠️ {file_path.name}: {e}")
                    continue

        if not batch_dfs:
            continue

        combined = pd.concat(batch_dfs, axis=0)
        combined = combined[~combined.index.duplicated(keep='first')]
        combined = combined.sort_index()
        missing_cols = [c for c in target_columns if c not in combined.columns]
        if missing_cols:
            na_df = pd.DataFrame({c: pd.NA for c in missing_cols}, index=combined.index)
            combined = pd.concat([combined, na_df], axis=1)
        combined = combined[target_columns]
        for col in combined.columns:
            if col in merged_df.columns and pd.api.types.is_numeric_dtype(merged_df[col].dtype):
                combined[col] = pd.to_numeric(combined[col], errors='coerce')

        new_rows = len(combined)
        merged_df = pd.concat([merged_df, combined], ignore_index=False, copy=False)
        total_new_rows += new_rows
        existing_index = merged_df.index
        batch_dfs.clear()
        del combined
        gc.collect()

        if files_processed % SAVE_INTERVAL == 0:
            print(f"\n   💾 Zwischenspeicherung ({files_processed} Dateien, {len(merged_df):,} Zeilen)...")
            merged_df = merged_df[~merged_df.index.duplicated(keep='first')]
            temp_file = merged_file.with_suffix('.parquet.temp')
            merged_df.to_parquet(temp_file, compression='snappy')
            if files_processed % (SAVE_INTERVAL * 3) == 0 and files_processed < n_paths:
                del merged_df
                gc.collect()
                merged_df = pd.read_parquet(temp_file)
                if not isinstance(merged_df.index, pd.DatetimeIndex):
                    merged_df.index = pd.to_datetime(merged_df.index)
            existing_index = merged_df.index
            try:
                temp_file.unlink()
            except OSError:
                pass

    print(f"\n   Finale Bereinigung...")
    merged_df = merged_df[~merged_df.index.duplicated(keep='first')]
    print(f"   Sortiere Daten...")
    merged_df = merged_df.sort_index()
    gc.collect()

    print(f"\n💾 Speichere finale Parquet-Datei...")
    merged_df.to_parquet(merged_file, compression='snappy')

    final_count = len(merged_df)
    print(f"\n✅ Fertig!")
    print(f"   Original: {original_count:,} Zeilen")
    print(f"   Neu hinzugefügt: {total_new_rows:,} Zeilen")
    print(f"   Final: {final_count:,} Zeilen")
    print(f"   Zuwachs: {final_count - original_count:,} Zeilen")

    return True


def main():
    """Hauptfunktion"""
    print("=" * 80)
    print("🔍 Suche nach Bodendaten für Soil-Parquet-Dateien")
    print("=" * 80)

    # ═══ Phase 1: Lückenliste erstellen (wo Parquet-Dateien NaNs haben) ═══
    print(f"\n{'=' * 80}")
    print("📋 Phase 1: Lückenliste aus Parquet-Dateien erstellen...")
    print("=" * 80)

    parquet_files = find_soil_parquet_files(MERGED_LONG_DIR)
    if not parquet_files:
        print(f"\n⚠️  Keine Soil-Parquet-Dateien gefunden in {MERGED_LONG_DIR}")
        return

    parquet_info = {}
    for parquet_file in parquet_files:
        if '_cr1000_merged_long' in parquet_file.stem:
            station = parquet_file.stem.replace('_cr1000_merged_long', '')
            file_type = 'cr1000'
        elif '_smt_merged_long' in parquet_file.stem:
            station = parquet_file.stem.replace('_smt_merged_long', '')
            file_type = 'smt'
        else:
            station = parquet_file.stem.split('_')[0]
            file_type = 'cr1000'
        gaps, data_start, data_end = find_gaps_in_merged(parquet_file, MIN_GAP_HOURS)
        if gaps:
            write_gaps_list(parquet_file, gaps, station, file_type, MERGED_LONG_DIR)
        parquet_info[parquet_file] = (station, file_type, gaps, data_start, data_end)

    # ═══ Phase 2: Dateien suchen, die Lücken füllen können ═══
    print(f"\n{'=' * 80}")
    print("🔍 Phase 2: Suche nach Dateien mit Daten für die Lücken...")
    print("=" * 80)

    soil_files = scan_source_directories(SOURCE_DIRS)
    if not soil_files:
        print("\n⚠️  Keine Bodendaten-Dateien gefunden")
        return

    # ═══ Phase 3: Listen erstellen (Dateien mit neuen Daten, bereits durchsucht ohne neue Daten) ═══
    print(f"\n{'=' * 80}")
    print("📋 Phase 3: Listen erstellen...")
    print("=" * 80)

    files_with_new_data = set()
    all_file_paths = {}

    for parquet_file, (station, file_type, gaps, data_start, data_end) in parquet_info.items():
        if pd.isna(data_start) or pd.isna(data_end):
            all_file_paths[parquet_file] = []
            continue
        station_files = filter_files_for_station(soil_files, station).copy()
        csv_files = find_csv_files_for_station(CSV_SOURCE_DIRS, station, file_type)
        for cf in csv_files:
            tr = get_file_time_range_optimized(cf)
            if tr[0] is not None:
                station_files[cf] = tr
        matches = find_files_filling_gaps(gaps, station_files, data_start, data_end)

        paths = []
        for fp, _, _ in matches['before_start'] + matches['after_end']:
            paths.append(fp)
            files_with_new_data.add(fp)
        for v in matches['gaps'].values():
            for fp, _, _, _ in v:
                paths.append(fp)
                files_with_new_data.add(fp)
        if 'within_range' in matches:
            for fp, _, _ in matches['within_range']:
                if fp not in paths:
                    paths.append(fp)
                    files_with_new_data.add(fp)
        for cf in csv_files:
            if cf in station_files:
                cs, ce = station_files[cf]
                if cs <= data_end and ce >= data_start and cf not in paths:
                    paths.append(cf)
                    files_with_new_data.add(cf)

        all_file_paths[parquet_file] = list(set(paths))

    files_searched_no_data = [str(p.resolve()) for p in soil_files if p not in files_with_new_data]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(SEARCHED_NO_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(sorted(files_searched_no_data), f, indent=0)
        print(f"   📄 Dateien ohne neue Daten: {len(files_searched_no_data)} (gespeichert: {SEARCHED_NO_DATA_FILE.name})")
    except Exception as e:
        print(f"   ⚠️ Liste konnte nicht geschrieben werden: {e}")
    print(f"   📄 Dateien mit neuen Daten: {len(files_with_new_data)}")

    # ═══ Phase 4: Dateien laden und in Parquet aufnehmen ═══
    print(f"\n{'=' * 80}")
    print("🔄 Phase 4: Dateien laden und Daten in Parquet aufnehmen...")
    print("=" * 80)

    processed = 0
    for parquet_file, file_paths in all_file_paths.items():
        if not file_paths:
            continue
        station = parquet_file.stem.replace('_cr1000_merged_long', '').replace('_smt_merged_long', '')
        print(f"\n{'=' * 80}")
        print(f"🔧 Verarbeite {station}: {len(file_paths)} Dateien")
        print("=" * 80)

        if fill_gaps_in_merged(parquet_file, file_paths):
            processed += 1

    attempted = sum(1 for p in all_file_paths.values() if p)
    print(f"\n{'=' * 80}")
    print(f"✅ Fertig! {processed} von {attempted} Parquet-Dateien erfolgreich verarbeitet")
    print("=" * 80)


if __name__ == "__main__":
    main()
