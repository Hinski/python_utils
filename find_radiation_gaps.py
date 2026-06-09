#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Findet und füllt Lücken in Radiation-Parquet-Dateien mit Strahlungsdaten.

- Erstellt pro Station eine Lückenliste (z. B. Gorigo_radiation_gaps.csv) mit Start/Ende/Dauer
  aller Lücken (fehlende Zeitstempel + durchgehend NaN in Strahlungsspalten).
- Durchsucht explizit die Quellordner nach Daten, die diese Lücken füllen können.
- Quellen für Gorigo-Strahlung: /Volumes/Extreme SSD (WASCAL_1_GORIGU, Gorigo, Gorigo EC),
  ggf. DATA_GHANA (WASCAL1GORIGU, Data Gorigo 20220718), CSV_SOURCE_DIRS.
- Besonders relevante Lücke: Mai 2022 – März 2023 (große Lücke); Daten gezielt in obigen
  Ordnern suchen.

Verwendung:
    python find_radiation_gaps.py
"""

from pathlib import Path
import pandas as pd
import sys
import shutil
import json
import gc
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from data_loader import read_toa5, read_ameriflux_flux, read_file_head_and_tail

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

# Quellordner für Strahlungsdaten (rekursiv durchsucht).
# Gorigo: Weitere mögliche Quellen – DATA_GHANA (WASCAL1GORIGU, Data Gorigo 20220718),
#         Extreme SSD: WASCAL_1_GORIGU, Gorigo, Gorigo EC (für Lücke Mai 2022 – März 2023).
SOURCE_DIRS = [
#    Path("/Volumes/Extreme SSD/WASCAL_1_GORIGU"),
#     Path("/Volumes/Extreme SSD/WASCAL_3_NAZINGA"),
#    Path("/Volumes/Extreme SSD/Gorigo"),
#    Path("/Volumes/Extreme SSD/Gorigo EC"),
#    Path("/Volumes/Extreme SSD/WASCAL_5_MOLE"),
#    Path("/Volumes/Extreme SSD/WASCAL_4_JANGA"),
#    Path("/Volumes/Extreme SSD/Janga"),
#    Path("/Volumes/Extreme SSD/Janga_EC"),
    Path("/Volumes/Extreme SSD/WASCAL_5_MOLE/SD_Card/Mole"),
#    Path("/Volumes/DATA_GHANA/ghana/archive/bolga/WASCAL 3 Nazinga data")
]# + CSV_SOURCE_DIRS  # Füge CSV-Quellordner hinzu


# Strahlungsdaten-Signatur (Spalten, die eindeutig für Radiation-Dateien sind)
# Berücksichtigt alle Varianten, die in anderen Skripten verwendet werden
RADIATION_SIGNATURE_COLS = [
    # Standard CR1000/CR3000 Varianten
    'SR_in_Avg', 'SR_IN_AVG', 'SR_out_Avg', 'SR_OUT_AVG',
    'IR_in_Avg', 'IR_IN_AVG', 'IR_out_Avg', 'IR_OUT_AVG',
    'NetTot_Avg', 'NETTOT_AVG', 'CNR4TC_Avg', 'CNR4TK_Avg',
    'NetRs_Avg', 'NetRl_Avg',
    # Alternative Varianten (aus merge_raw_files.py)
    'NETRN',
    # CR6/AmeriFlux Format Varianten (aus interactive_plots.py und ec_analysis)
    'R_SW_in', 'SW_IN_net_rdmtr', 'R_SW_out', 'SW_OUT',
    'R_LW_in', 'LW_IN', 'R_LW_in_meas', 'R_LW_out', 'LW_OUT', 'R_LW_out_meas',
    'SW_IN', 'SW_OUT', 'LW_IN', 'LW_OUT',  # Kurzformen
    'NETRAD',  # Alternative Net Radiation
    # Weitere Varianten (aus ec_analysis)
    'SW_in korrigiert', 'SW_out korrigiert',  # Deutsche Varianten
    'LW_in_Avg [W/m^2]', 'LW_out_Avg [W/m^2]',  # Mit Einheiten
]

# Minimale Lückengröße, die wir füllen wollen (in Stunden)
MIN_GAP_HOURS = 1

# Phase 4: Performance bei vielen Dateien
BATCH_MERGE_SIZE = 15   # combine_first in Batches (weniger große Merges)
SAVE_INTERVAL = 50     # Zwischenspeicherung alle N Dateien (weniger I/O)
LOAD_PARALLEL = 0      # 0 = sequentiell, sonst Anzahl Worker (z. B. 4 bei lokaler SSD)
PROGRESS_EVERY = 25    # Fortschritt nur alle N Dateien ausgeben (weniger Ausgabe)

# Station-Zuordnung basierend auf Ordnerpfad
# Dateien aus bestimmten Ordnern werden nur bestimmten Stationen zugeordnet
# Gorigo: WASCAL_1_GORIGU, Gorigo, Gorigo EC (alle auf /Volumes/Extreme SSD)
STATION_FOLDER_MAPPING = {
    'Gorigo': ['WASCAL_1_GORIGU', 'WASCAL1GORIGU', 'Data Gorigo 20220718', 'gorigo', 'gorigo ec'],
    'Kayoro': ['WASCAL 2 Kayoro data', 'WASCAL 2 Kayoro', 'kayoro'],
    'Nazinga': ['WASCAL 3 Nazinga data', 'WASCAL 3 Nazinga', 'nazinga', 'WASCAL_3_NAZINGA'],
    'Janga': ['janga'],
    'Mole': ['mole', 'WASCAL_5_MOLE', 'WASCAL_5_Mole'],
    'Sumbrungu': ['WASCAL 1 Sumbrungu data', 'WASCAL 1 Sumbrungu', 'sumbrungu', 'sum'],
}

# Spalten-Mapping für Normalisierung (verschiedene Schreibweisen).
# TOA5 Radiation-Dateien (z. B. TOA5_6830.Radiation_*.dat) haben typischerweise:
#   "SR_out_Avg","SR_in_Avg","IR_out_Avg","IR_in_Avg" → 1:1 in Parquet (SR_in_Avg etc.)
COLUMN_MAPPING = {
    'SR_IN_AVG': 'SR_in_Avg',
    'SR_OUT_AVG': 'SR_out_Avg',
    'IR_IN_AVG': 'IR_in_Avg',
    'IR_OUT_AVG': 'IR_out_Avg',
    'NETTOT_AVG': 'NetTot_Avg',
}


def _header_contains_signature(header_line: str) -> bool:
    """Prüft ob eine Header-Zeile eine Strahlungs-Signatur enthält."""
    if not header_line or not header_line.strip():
        return False
    header_upper = header_line.upper()
    return any(sig_col.upper() in header_upper for sig_col in RADIATION_SIGNATURE_COLS)


def is_radiation_file_fast(file_path: Path) -> bool:
    """
    Schnelle Prüfung ob eine Datei Strahlungsdaten enthält (nur Header lesen).
    Liest nur die ersten 5 Zeilen um Speicher zu sparen.
    Unterstützt TOA5, CSV und mehrzeilige Header (z. B. AmeriFlux mit Zeile 0+1).

    Zusätzlich: Dateien mit "Radiation" im Pfad/Namen (z. B. TOA5_6830.Radiation_*.dat,
    CR3000_Gorigo_Radiation_1.dat) werden akzeptiert, wenn sie TOA5- oder CR3000-Format haben.

    WICHTIG: Überspringt EddyPro-Dateien, da diese keine Strahlungsdaten enthalten,
    sondern nur Fluxnet-Format Outputs sind.
    """
    try:
        # Überspringe EddyPro-Dateien (haben keine Strahlungsdaten, nur Fluxnet-Output)
        if 'eddypro' in file_path.name.lower() and 'fluxnet' in file_path.name.lower():
            return False

        path_lower = str(file_path).lower()
        name_lower = file_path.name.lower()
        has_radiation_in_name = 'radiation' in name_lower or 'radiation' in path_lower

        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = []
            for i, line in enumerate(f):
                if i >= 5:  # Nur erste 5 Zeilen lesen
                    break
                lines.append(line)

            if len(lines) < 1:
                return False

            # Prüfe ob es TOA5- oder CR3000-Format ist (Campbell Scientific)
            first_line_upper = lines[0].strip().lstrip('\ufeff').upper().strip('"').strip("'")
            is_toa5 = first_line_upper.startswith('TOA5')
            is_cr3000 = first_line_upper.startswith('CR3000')

            # Typische Gorigo/WASCAL-Dateien: TOA5_6830.Radiation_*.dat oder CR3000_Gorigo_Radiation_1.dat
            # Wenn "Radiation" im Namen und TOA5/CR3000-Format → als Strahlungsdatei akzeptieren
            if has_radiation_in_name and (is_toa5 or is_cr3000):
                return True

            if is_toa5 or is_cr3000:
                # TOA5/CR3000: Header ist normalerweise Zeile 1, ggf. auch Zeile 2
                header_candidates = [lines[1]] if len(lines) > 1 else [lines[0]]
            else:
                # CSV / AmeriFlux: Header kann in Zeile 0, 1 oder 2 stehen (mehrzeilige Header)
                header_candidates = [lines[i] for i in range(min(3, len(lines)))]

            # Prüfe alle infrage kommenden Zeilen auf Strahlungs-Signatur
            for header_line in header_candidates:
                if _header_contains_signature(header_line):
                    return True
            return False
    except Exception:
        return False


def _parse_timestamp_from_line(line: str):
    """Extrahiert ersten Wert als Timestamp aus einer CSV-Zeile. Gibt pd.NaT bei Fehler."""
    if not line or not line.strip():
        return pd.NaT
    part = line.split(',')[0].strip().strip('"').strip("'").lstrip('\ufeff')
    return pd.to_datetime(part, errors='coerce')


def get_file_time_range_optimized(file_path: Path) -> tuple:
    """
    Extrahiert den Zeitbereich einer Strahlungsdatei (speichereffizient).
    Liest nur erste ~60 Zeilen + letzte ~64KB (kein readlines() auf ganzer Datei).
    Unterstützt TOA5 (auch mit 4–6+ Headerzeilen) und CSV.

    Returns:
        (start_time, end_time) oder (None, None) bei Fehler
    """
    try:
        first_lines, last_lines = read_file_head_and_tail(file_path, head_lines=60, tail_bytes=65536)

        if len(first_lines) < 2:
            return (None, None)

        first_stripped = first_lines[0].strip().lstrip('\ufeff').upper().lstrip('"')
        is_toa5 = first_stripped.startswith('TOA5')
        is_cr3000 = first_stripped.startswith('CR3000')

        if is_toa5 or is_cr3000:
            first_time, last_time = pd.NaT, pd.NaT
            for i in range(4, min(50, len(first_lines))):
                t = _parse_timestamp_from_line(first_lines[i])
                if pd.notna(t):
                    first_time = t
                    break
            if pd.isna(first_time):
                return (None, None)
            for line in reversed(last_lines):
                t = _parse_timestamp_from_line(line)
                if pd.notna(t):
                    last_time = t
                    break
            if pd.isna(last_time) and last_lines:
                # last_lines hatte keine parsebare Zeile (Format o.ä.)
                pass
            if pd.isna(last_time):
                # Kleine Datei: alles in first_lines, last_lines leer → Ende aus letzten Zeilen von first_lines
                for i in range(len(first_lines) - 1, 3, -1):
                    t = _parse_timestamp_from_line(first_lines[i])
                    if pd.notna(t):
                        last_time = t
                        break
            if pd.isna(last_time):
                last_time = first_time
            return (first_time, last_time)
        else:
            first_time = _parse_timestamp_from_line(first_lines[1] if len(first_lines) > 1 else '')
            last_time = pd.NaT
            if last_lines:
                last_time = _parse_timestamp_from_line(last_lines[-1])
            elif len(first_lines) > 1:
                last_time = _parse_timestamp_from_line(first_lines[-1])
            if pd.isna(first_time) or pd.isna(last_time):
                return (None, None)
            return (first_time, last_time)

    except Exception:
        return (None, None)


# Spalten, anhand derer "Datenlücken" (NaN-Bereiche) erkannt werden
# Wenn diese Spalten NaN sind, gilt die Zeile als lückenhaft
RADIATION_GAP_COLS = [
    'SR_in_Avg', 'SR_out_Avg', 'IR_in_Avg', 'IR_out_Avg',
    'SW_IN', 'SW_OUT', 'LW_IN', 'LW_OUT',
    'NetTot_Avg', 'NETRAD',
]


def find_gaps_in_merged(merged_file: Path, min_gap_hours: float = 1.0) -> tuple:
    """
    Findet Lücken in der merged Parquet-Datei und gibt auch Start/Ende zurück.

    Zwei Arten von Lücken:
    1) Index-Lücken: fehlende Zeitstempel (Sprung im Index > min_gap_hours)
    2) Daten-Lücken: Zeitbereiche, in denen Strahlungsspalten durchgehend NaN sind (>= min_gap_hours)

    Returns:
        (gaps_list, data_start, data_end) wobei:
        - gaps_list: Liste von (gap_start, gap_end, gap_duration) Tupeln
        - data_start: Erster Timestamp in merged Datei
        - data_end: Letzter Timestamp in merged Datei
    """
    print(f"📊 Analysiere {merged_file.name}...")

    # Lade Parquet-Datei
    df = pd.read_parquet(merged_file)

    # Stelle sicher, dass Index ein DatetimeIndex ist
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

    # --- 2) Daten-Lücken: Strahlungsspalten durchgehend NaN ---
    # Welche Spalte nutzen? Erste vorhandene aus RADIATION_GAP_COLS
    gap_col = None
    for c in RADIATION_GAP_COLS:
        if c in df.columns:
            gap_col = c
            break
    if gap_col is not None:
        # Zeile hat gültige Strahlungsdaten, wenn mind. eine Strahlungsspalte nicht NaN ist
        has_any_rad = pd.Series(False, index=df.index)
        for c in RADIATION_GAP_COLS:
            if c in df.columns:
                has_any_rad = has_any_rad | df[c].notna()
        invalid = ~has_any_rad
        # Kontinuierliche Blöcke von invalid (NaN) finden
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
    else:
        # Fallback: nur Index-Lücken (keine passende Strahlungsspalte)
        pass

    # Doppelte/überlappende Lücken vermeiden: nach Start sortieren, Überlappungen zusammenfassen optional
    gaps.sort(key=lambda x: x[0])
    print(f"   Gefundene Lücken (>={min_gap_hours}h): {len(gaps)} (Index + Daten-NaN)")

    return gaps, data_start, data_end


def write_gaps_list(merged_file: Path, gaps: list, station: str, output_dir: Path = None) -> Path:
    """
    Schreibt eine CSV-Liste aller Lücken (Start, Ende, Dauer in Stunden).
    Ermöglicht gezielte Suche nach Daten für diese Zeiträume (z. B. Mai 2022 – März 2023).

    Returns:
        Pfad der geschriebenen CSV-Datei
    """
    if output_dir is None:
        output_dir = merged_file.parent
    out_path = output_dir / f"{station}_radiation_gaps.csv"
    rows = []
    for gap_start, gap_end, gap_duration in gaps:
        duration_hours = gap_duration.total_seconds() / 3600
        rows.append({
            'gap_start': gap_start.isoformat(),
            'gap_end': gap_end.isoformat(),
            'duration_hours': round(duration_hours, 2),
        })
    if rows:
        pd.DataFrame(rows).to_csv(out_path, index=False)
        print(f"   📄 Lückenliste geschrieben: {out_path.name} ({len(rows)} Lücken)")
    return out_path


# Dateiendungen, die beim Scannen durchsucht werden (rekursiv in allen Unterordnern)
SCAN_EXTENSIONS = ['*.dat', '*.csv', '*.txt']

# Cache-Ordner für bereits durchsuchte Dateien (Zeitbereich → kein erneutes Lesen)
CACHE_DIR = MERGED_LONG_DIR / ".gaps_cache"
FILE_RANGES_CACHE = CACHE_DIR / "radiation_file_ranges.json"
SEARCHED_NO_DATA_FILE = CACHE_DIR / "radiation_searched_no_data.json"


def _load_file_ranges_cache() -> dict:
    """Lädt Cache: {path_str: [start_iso, end_iso]}."""
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
    Durchsucht Quellordner rekursiv (alle Unterordner) nach Strahlungsdaten-Dateien.
    Nutzt Cache (.gaps_cache/radiation_file_ranges.json): bereits gelesene Zeitbereiche
    werden wiederverwendet → kein erneutes Öffnen der Dateien.

    Returns:
        Dict: {file_path: (start_time, end_time)}
    """
    radiation_files = {}
    cache = _load_file_ranges_cache() if use_cache else {}
    cache_updated = False

    for source_dir in source_dirs:
        if not source_dir.exists():
            print(f"⚠️  Ordner existiert nicht: {source_dir}")
            continue

        print(f"\n🔍 Durchsuche: {source_dir}")
        print(f"   (rekursiv in allen Unterordnern nach {', '.join(SCAN_EXTENSIONS)})")
        if use_cache and cache:
            print(f"   (Cache: {len(cache)} Dateien – keine erneute Leseoperation für diese)")

        file_count = 0
        skipped_turbulence = 0
        skipped_no_signature = 0
        cached_count = 0
        for ext in SCAN_EXTENSIONS:
            for file_path in source_dir.rglob(ext):
                path_parts = file_path.parts
                if any('turbulence' in part.lower() for part in path_parts):
                    skipped_turbulence += 1
                    continue

                file_count += 1

                if file_count % 100 == 0:
                    print(f"   Geprüft: {file_count} (gefunden: {len(radiation_files)})...", end='\r')

                path_str = str(file_path.resolve())
                if use_cache and path_str in cache:
                    cached = cache[path_str]
                    if cached and len(cached) == 2:
                        try:
                            start_t = pd.to_datetime(cached[0])
                            end_t = pd.to_datetime(cached[1])
                            if pd.notna(start_t) and pd.notna(end_t) and start_t != end_t:
                                radiation_files[file_path] = (start_t, end_t)
                                cached_count += 1
                                continue
                            # Start == Ende (früherer Bug bei kleinen Dateien) → Cache verwerfen, neu lesen
                        except Exception:
                            pass
                    # Cache ungültig oder Start==Ende → nicht continue, Zeitbereich unten neu ermitteln

                if not is_radiation_file_fast(file_path):
                    skipped_no_signature += 1
                    continue

                time_range = get_file_time_range_optimized(file_path)
                if time_range[0] is not None:
                    radiation_files[file_path] = time_range
                    if use_cache:
                        cache[path_str] = [
                            time_range[0].isoformat() if hasattr(time_range[0], 'isoformat') else str(time_range[0]),
                            time_range[1].isoformat() if hasattr(time_range[1], 'isoformat') else str(time_range[1]),
                        ]
                        cache_updated = True
                    print(f"\n   ✓ Gefunden: {file_path.name} ({time_range[0]} - {time_range[1]})")

                    if len(radiation_files) % 200 == 0:
                        import gc
                        gc.collect()
                else:
                    skipped_no_signature += 1

        print(f"\n   Gesamt geprüft: {file_count} Dateien")
        if cached_count > 0:
            print(f"   Aus Cache: {cached_count} (keine Datei geöffnet)")
        if skipped_turbulence > 0:
            print(f"   Übersprungen (Turbulence): {skipped_turbulence}")

    if use_cache and cache_updated:
        _save_file_ranges_cache(cache)

    return radiation_files


def find_files_filling_gaps(gaps: list, radiation_files: dict, data_start: pd.Timestamp, data_end: pd.Timestamp) -> dict:
    """
    Findet Dateien, die Lücken füllen können, sowie Daten vor/nach dem Zeitbereich.

    Returns:
        Dict mit Keys:
        - 'gaps': {gap_index: [(file_path, overlap_start, overlap_end, coverage_pct), ...]}
        - 'before_start': [(file_path, file_start, file_end), ...] - Dateien vor data_start
        - 'after_end': [(file_path, file_start, file_end), ...] - Dateien nach data_end
    """
    matches = {
        'gaps': defaultdict(list),
        'before_start': [],
        'after_end': [],
        'within_range': []  # Dateien innerhalb des Zeitbereichs (können fehlende Daten enthalten)
    }

    print(f"\n🔗 Vergleiche {len(radiation_files)} Strahlungsdateien...")
    print(f"   - Mit {len(gaps)} Lücken")
    print(f"   - Vor Start ({data_start})")
    print(f"   - Nach Ende ({data_end})")

    # Gaps nach Start sortieren → frühes Break wenn gap_start > file_end (schneller bei vielen Lücken)
    gaps_sorted = sorted(enumerate(gaps), key=lambda x: x[1][0])

    for file_path, (file_start, file_end) in radiation_files.items():
        # Prüfe ob Datei VOR dem Start liegt
        if file_end < data_start:
            matches['before_start'].append((file_path, file_start, file_end))
            continue

        # Prüfe ob Datei NACH dem Ende liegt
        if file_start > data_end:
            matches['after_end'].append((file_path, file_start, file_end))
            continue

        # Prüfe ob Datei Lücken füllt (nur Lücken mit gap_start <= file_end durchgehen)
        matched_gap = False
        for gap_idx, (gap_start, gap_end, gap_duration) in gaps_sorted:
            if gap_start > file_end:
                break  # restliche Lücken liegen danach
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
            if 'within_range' not in matches:
                matches['within_range'] = []
            matches['within_range'].append((file_path, file_start, file_end))

    return matches


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalisiert Spaltennamen für Konsistenz mit der Parquet-Datei.
    SR_in_Avg, SR_out_Avg, IR_in_Avg, IR_out_Avg aus TOA5/CSV werden
    unverändert übernommen (entsprechen bereits den Parquet-Spalten).
    """
    df = df.copy()

    # Normalisiere Spaltennamen (groß/klein)
    column_mapping = {}
    for col in df.columns:
        col_upper = col.upper()
        # Prüfe ob es ein Mapping gibt
        if col_upper in COLUMN_MAPPING:
            column_mapping[col] = COLUMN_MAPPING[col_upper]
        else:
            # Versuche exakte Übereinstimmung (case-insensitive)
            for target_col in COLUMN_MAPPING.values():
                if col.upper() == target_col.upper():
                    column_mapping[col] = target_col
                    break

    if column_mapping:
        df = df.rename(columns=column_mapping)

    return df


def load_and_merge_radiation_file(file_path: Path, merged_df=None, target_columns=None) -> pd.DataFrame:
    """
    Lädt eine Strahlungsdatei (TOA5 oder CSV) und gibt nur neue Daten zurück (keine Duplikate).

    Args:
        file_path: Pfad zur Quelldatei
        merged_df: Optional – Parquet-DataFrame (für Spaltenabgleich). Wenn target_columns gesetzt, ignoriert.
        target_columns: Optional – Liste der Zielspalten (schneller als merged_df bei vielen Dateien).

    Returns:
        DataFrame mit neuen Daten, die noch nicht in merged_df sind
    """
    try:
        cols_ref = target_columns if target_columns is not None else (merged_df.columns if merged_df is not None and not merged_df.empty else None)
        # Prüfe ob es eine CSV-Datei ist
        if file_path.suffix.lower() == '.csv':
            # Prüfe ob es EddyPro-Format ist (hat "eddypro" im Namen)
            if 'eddypro' in file_path.name.lower():
                # EddyPro CSV-Format: TIMESTAMP ist erste Spalte, kann verschiedene Namen haben
                try:
                    df_new = pd.read_csv(
                        file_path,
                        index_col=0,  # Erste Spalte ist Timestamp
                        parse_dates=True,
                        na_values=["NAN", "NA", "-9999", "", "NaN"],
                        low_memory=False,
                        on_bad_lines='skip'
                    )
                    # Stelle sicher, dass Index ein DatetimeIndex ist
                    if not isinstance(df_new.index, pd.DatetimeIndex):
                        df_new.index = pd.to_datetime(df_new.index, errors='coerce')
                except Exception as e:
                    print(f"    ⚠️  Fehler beim Laden von EddyPro-Datei {file_path.name}: {e}")
                    return pd.DataFrame()
            elif 'merged' in file_path.name.lower():
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
                df_new = read_toa5(file_path)
        else:
            # .dat Dateien: TOA5 oder AmeriFlux Flux-Format
            try:
                if "AmeriFlux" in file_path.name or "ameriflux" in file_path.name.lower():
                    df_new = read_ameriflux_flux(file_path)
                else:
                    df_new = read_toa5(file_path)
            except (pd.errors.EmptyDataError, ValueError, UnicodeDecodeError):
                # Fallback: z.B. TOA5-Parser lieferte keine Zeilen → AmeriFlux versuchen
                try:
                    df_new = read_ameriflux_flux(file_path)
                except UnicodeDecodeError:
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
        # (CSV-Dateien können Spalten als Strings laden)
        for col in df_new.columns:
            if df_new[col].dtype == 'object':
                # Versuche zu numerisch zu konvertieren
                df_new[col] = pd.to_numeric(df_new[col], errors='coerce')

        # Stelle sicher, dass Spalten mit Ziel-Parquet übereinstimmen
        if cols_ref is not None:
            common_cols = [col for col in cols_ref if col in df_new.columns]
            if not common_cols and len(df_new.columns) > 0:
                # Fallback: case-insensitiver Abgleich (z. B. SR_in_avg in Datei ↔ SR_in_Avg in Parquet)
                cols_ref_upper = {c.upper(): c for c in cols_ref}
                for col in list(df_new.columns):
                    if col.upper() in cols_ref_upper:
                        target = cols_ref_upper[col.upper()]
                        if target != col:
                            df_new = df_new.rename(columns={col: target})
                common_cols = [col for col in cols_ref if col in df_new.columns]
            if common_cols:
                df_new = df_new[common_cols]

        # WICHTIG: Alle Zeilen zurückgeben, nicht nur "neue" Zeitstempel.
        # Die Parquet-Datei hat oft für jeden Zeitstempel bereits eine Zeile (mit NaN).
        # Beim Merge wird combine_first verwendet → bestehende NaN werden mit Werten
        # aus der Quelldatei gefüllt; neue Zeitstempel werden ergänzt.
        return df_new

    except UnicodeDecodeError as e:
        print(f"    ⚠️  Encoding-Fehler ({file_path.name}): {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"    ⚠️  Fehler beim Laden von {file_path.name}: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


def fill_gaps_in_merged(merged_file: Path, files_to_merge: set, radiation_files: dict) -> bool:
    """
    Füllt Lücken in der merged Parquet-Datei mit Daten aus den gefundenen Dateien.

    Returns:
        True wenn erfolgreich, False sonst
    """
    print(f"\n{'=' * 80}")
    print("📥 Lade und merge Daten...")
    print("=" * 80)

    # Backup erstellen
    backup_file = merged_file.with_suffix('.parquet.backup')
    if not backup_file.exists():
        print(f"💾 Erstelle Backup: {backup_file.name}")
        shutil.copy2(merged_file, backup_file)
    else:
        print(f"💾 Backup existiert bereits: {backup_file.name}")

    # Lade merged Parquet-Datei
    print(f"\n📖 Lade {merged_file.name}...")
    merged_df = pd.read_parquet(merged_file)

    # Stelle sicher, dass Index ein DatetimeIndex ist
    if not isinstance(merged_df.index, pd.DatetimeIndex):
        merged_df.index = pd.to_datetime(merged_df.index)

    original_count = len(merged_df)
    print(f"   Original: {original_count:,} Zeilen")

    # Lade und merge: combine_first füllt NaN in bestehenden Zeilen und fügt neue Zeitstempel hinzu
    target_columns = list(merged_df.columns)
    files_processed = 0
    total_new_indices = 0
    nan_before = merged_df.isna().sum().sum()

    for file_path in sorted(files_to_merge):
        files_processed += 1
        print(f"\n   [{files_processed}/{len(files_to_merge)}] {file_path.name}")

        df_new = load_and_merge_radiation_file(file_path, target_columns=target_columns)

        if df_new.empty:
            print(f"      → Keine Daten geladen")
            continue

        # Spalten wie merged_df (fehlende mit NaN) – in einem Schritt statt insert-Loop
        missing_cols = [c for c in merged_df.columns if c not in df_new.columns]
        if missing_cols:
            na_df = pd.DataFrame({c: pd.NA for c in missing_cols}, index=df_new.index)
            df_new = pd.concat([df_new, na_df], axis=1)
        df_new = df_new[merged_df.columns]

        # Datentypen angleichen
        for col in df_new.columns:
            if col in merged_df.columns:
                target_dtype = merged_df[col].dtype
                if df_new[col].dtype != target_dtype:
                    if pd.api.types.is_numeric_dtype(target_dtype):
                        df_new[col] = pd.to_numeric(df_new[col], errors='coerce')
                    elif pd.api.types.is_datetime64_any_dtype(target_dtype):
                        df_new[col] = pd.to_datetime(df_new[col], errors='coerce')

        # Neue Zeitstempel (noch nicht in merged_df)
        new_ix = df_new.index.difference(merged_df.index)
        n_new = len(new_ix)

        # combine_first: bestehende NaN mit Werten aus df_new füllen, neue Zeilen ergänzen
        merged_df = merged_df.combine_first(df_new)

        total_new_indices += n_new
        print(f"      → {n_new:,} neue Zeitstempel, {len(df_new):,} Zeilen aus Datei (NaN werden gefüllt)")

        del df_new
        gc.collect()

    nan_after = merged_df.isna().sum().sum()
    filled = int(nan_before - nan_after) if nan_before >= nan_after else 0
    print(f"\n   → {total_new_indices:,} neue Zeitstempel ergänzt, {filled:,} zuvor fehlende Werte (NaN) gefüllt")

    # Sortiere nach Index
    print(f"   Sortiere Daten...")
    merged_df = merged_df.sort_index()
    gc.collect()

    # Speichere als Parquet
    print(f"\n💾 Speichere aktualisierte Parquet-Datei...")
    merged_df.to_parquet(merged_file, compression='snappy')

    final_count = len(merged_df)
    print(f"\n✅ Fertig!")
    print(f"   Original: {original_count:,} Zeilen")
    print(f"   Final: {final_count:,} Zeilen")
    print(f"   Zuwachs: {final_count - original_count:,} Zeilen (inkl. gefüllte NaN)")

    return True


def detect_station_from_path(file_path: Path) -> str:
    """
    Erkennt die Station basierend auf dem Dateipfad.

    Args:
        file_path: Pfad zur Datei

    Returns:
        Stationsname (z.B. 'Gorigo', 'Kayoro') oder None
    """
    path_str = str(file_path).lower()

    # Prüfe Station-Folder-Mapping
    for station, folder_keywords in STATION_FOLDER_MAPPING.items():
        for keyword in folder_keywords:
            if keyword.lower() in path_str:
                return station

    # Fallback: Prüfe Dateinamen
    filename = file_path.name.lower()
    stations = ['gorigo', 'kayoro', 'nazinga', 'janga', 'mole', 'sumbrungu', 'sum']
    for station in stations:
        if station in filename:
            # Spezialfall: "sum" könnte auch "sumbrungu" sein
            if station == 'sum':
                return 'Sumbrungu'
            return station.capitalize()

    return None


def filter_files_for_station(radiation_files: dict, station: str) -> dict:
    """
    Filtert Strahlungsdaten-Dateien basierend auf der Station.

    Args:
        radiation_files: Dict mit allen gefundenen Dateien
        station: Stationsname (z.B. 'Gorigo')

    Returns:
        Gefiltertes Dict mit nur für diese Station relevanten Dateien
    """
    filtered = {}

    for file_path, time_range in radiation_files.items():
        file_station = detect_station_from_path(file_path)

        # Wenn Station erkannt wurde und passt, oder keine Station erkannt wurde (für allgemeine Dateien)
        if file_station == station or file_station is None:
            filtered[file_path] = time_range

    return filtered


def find_radiation_parquet_files(merged_long_dir: Path) -> list:
    """
    Findet alle Radiation-Parquet-Dateien im merged_long Verzeichnis.
    Für Mole und Janga werden auch die CR6-Dateien verwendet (dort sind die Strahlungsdaten).

    Returns:
        Liste von Path-Objekten zu Strahlungsdaten-Parquet-Dateien
    """
    if not merged_long_dir.exists():
        print(f"❌ Verzeichnis existiert nicht: {merged_long_dir}")
        return []

    parquet_files = []

    # Standard: *_radiation_merged_long.parquet Dateien
    radiation_files = list(merged_long_dir.glob("*_radiation_merged_long.parquet"))
    parquet_files.extend(radiation_files)

    # Spezialfall: Mole und Janga haben Strahlungsdaten in CR6-Dateien
    cr6_files = list(merged_long_dir.glob("*_cr6_merged_long.parquet"))
    for cr6_file in cr6_files:
        station = cr6_file.stem.replace('_cr6_merged_long', '')
        if station in ['Janga', 'Mole']:
            parquet_files.append(cr6_file)
            print(f"   ℹ️  {station}: Verwende CR6-Datei für Strahlungsdaten: {cr6_file.name}")

    return sorted(parquet_files)


def find_csv_files_for_station(csv_source_dirs: list, station: str) -> list:
    """
    Findet CSV-Dateien die zu einer Station gehören (z.B. Gorigo_radiation_merged.csv).

    Args:
        csv_source_dirs: Liste von Verzeichnissen zum Durchsuchen
        station: Stationsname (z.B. 'Gorigo')

    Returns:
        Liste von CSV-Dateipfaden die zu dieser Station gehören
    """
    csv_files = []

    for csv_dir in csv_source_dirs:
        if not csv_dir.exists():
            print(f"   ⚠️  CSV-Quellordner existiert nicht: {csv_dir}")
            continue

        print(f"   Durchsuche: {csv_dir}")

        # Suche nach CSV-Dateien die zur Station passen
        # Pattern: Station_radiation_merged.csv oder Station/merged/Station_radiation_merged.csv
        patterns = [
            f"{station}_radiation_merged.csv",
            f"{station}_radiation_merged_*.csv",
        ]

        for pattern in patterns:
            found_pattern_files = list(csv_dir.rglob(pattern))
            print(f"   Pattern '{pattern}': {len(found_pattern_files)} Dateien gefunden")
            for csv_file in found_pattern_files:
                print(f"      Prüfe: {csv_file}")
                # Prüfe ob es wirklich eine Strahlungsdatei ist
                if is_radiation_file_fast(csv_file):
                    csv_files.append(csv_file)
                    print(f"   ✓ CSV gefunden: {csv_file}")
                else:
                    print(f"      → Keine Strahlungsdatei (keine Signatur-Spalten)")

        # Auch in Unterordnern suchen (z.B. Station/merged/)
        station_dirs = list(csv_dir.glob(f"*/{station}/*"))
        print(f"   Station-Unterordner gefunden: {len(station_dirs)}")
        for station_dir in station_dirs:
            if station_dir.is_dir():
                found_in_subdir = list(station_dir.rglob("*radiation*merged*.csv"))
                print(f"      In {station_dir}: {len(found_in_subdir)} CSV-Dateien")
                for csv_file in found_in_subdir:
                    print(f"         Prüfe: {csv_file}")
                    if is_radiation_file_fast(csv_file):
                        csv_files.append(csv_file)
                        print(f"   ✓ CSV gefunden: {csv_file}")
                    else:
                        print(f"         → Keine Strahlungsdatei (keine Signatur-Spalten)")

    return csv_files


def find_files_for_parquet(parquet_file: Path, radiation_files: dict) -> list:
    """
    Findet alle Dateien, die Lücken in einer Parquet-Datei füllen können.
    Gibt nur die Pfade zurück, lädt keine Daten.
    Berücksichtigt auch CSV-Dateien aus CSV_SOURCE_DIRS.

    Returns:
        Liste von Dateipfaden (Path-Objekte)
    """
    # Erkenne Station aus Dateinamen (unterstützt sowohl radiation als auch cr6)
    if '_radiation_merged_long' in parquet_file.stem:
        station = parquet_file.stem.replace('_radiation_merged_long', '')
    elif '_cr6_merged_long' in parquet_file.stem:
        station = parquet_file.stem.replace('_cr6_merged_long', '')
    else:
        # Fallback: Versuche Station aus Dateinamen zu extrahieren
        station = parquet_file.stem.split('_')[0]

    print(f"\n{'=' * 80}")
    print(f"🔍 Analysiere Station: {station}")
    print(f"   Datei: {parquet_file.name}")
    print("=" * 80)

    # 1. Finde Lücken in Parquet-Datei (Index-Lücken + Daten-Lücken mit NaN)
    gaps, data_start, data_end = find_gaps_in_merged(parquet_file, MIN_GAP_HOURS)

    # Lückenliste exportieren (für gezielte Suche, z. B. große Lücke Mai 2022 – März 2023)
    if gaps:
        write_gaps_list(parquet_file, gaps, station, MERGED_LONG_DIR)

    if not gaps:
        # Prüfe ob es Daten vor/nach gibt
        df = pd.read_parquet(parquet_file)
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        if len(df) > 0:
            data_start = df.index.min()
            data_end = df.index.max()
        del df  # Speicher freigeben

    # 2. Filtere Dateien für diese Station basierend auf Ordnerpfad
    station_files = filter_files_for_station(radiation_files, station)
    print(f"   Gefiltert: {len(station_files)} von {len(radiation_files)} Dateien gehören zu {station}")

    # 3. Finde CSV-Dateien für diese Station
    print(f"\n   Suche CSV-Dateien für {station}...")
    csv_files = find_csv_files_for_station(CSV_SOURCE_DIRS, station)

    # Füge CSV-Dateien zu station_files hinzu (mit Zeitbereich)
    csv_files_with_range = []
    for csv_file in csv_files:
        time_range = get_file_time_range_optimized(csv_file)
        if time_range[0] is not None:
            station_files[csv_file] = time_range
            csv_files_with_range.append((csv_file, time_range))
            print(f"   ✓ CSV hinzugefügt: {csv_file.name} ({time_range[0]} - {time_range[1]})")

    # 4. Finde passende Dateien (Lücken + vor/nach)
    matches = find_files_filling_gaps(gaps, station_files, data_start, data_end)

    # 5. Sammle alle Dateipfade (nur Pfade, keine Daten!)
    file_paths = []

    # Dateien vor Start
    for file_path, _, _ in matches['before_start']:
        file_paths.append(file_path)

    # Dateien nach Ende
    for file_path, _, _ in matches['after_end']:
        file_paths.append(file_path)

    # Dateien für Lücken
    for gap_matches in matches['gaps'].values():
        for file_path, _, _, _ in gap_matches:
            file_paths.append(file_path)

    # WICHTIG: Dateien innerhalb des Zeitbereichs hinzufügen (können fehlende Daten enthalten)
    # Dies gilt für ALLE Dateien (auch von der Festplatte), nicht nur CSV-Dateien!
    if 'within_range' in matches:
        for file_path, _, _ in matches['within_range']:
            if file_path not in file_paths:
                file_paths.append(file_path)
                print(f"   ✓ Datei innerhalb Zeitbereich hinzugefügt: {file_path.name} (könnte fehlende Daten enthalten)")

    # WICHTIG: CSV-Dateien IMMER hinzufügen, wenn sie innerhalb oder überlappt mit dem Zeitbereich liegen
    # Diese könnten fehlende Daten enthalten (wird später in load_and_merge_radiation_file geprüft)
    # Auch wenn keine großen Lücken vorhanden sind, können CSV-Dateien einzelne fehlende Timestamps enthalten
    for csv_file, (csv_start, csv_end) in csv_files_with_range:
        # Wenn CSV-Datei innerhalb oder überlappt mit dem Zeitbereich liegt
        if csv_start <= data_end and csv_end >= data_start:
            if csv_file not in file_paths:
                file_paths.append(csv_file)
                print(f"   ✓ CSV innerhalb Zeitbereich hinzugefügt: {csv_file.name} (könnte fehlende Daten enthalten)")

    # Entferne Duplikate
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


def fill_gaps_in_merged(merged_file: Path, file_paths: list) -> bool:
    """
    Füllt Lücken in der merged Parquet-Datei mit Daten aus den gefundenen Dateien.
    Verwendet echtes Streaming: Dateien einzeln laden, mergen, periodisch speichern.

    Args:
        merged_file: Pfad zur Parquet-Datei
        file_paths: Liste von Dateipfaden (nur Pfade, keine Daten)

    Returns:
        True wenn erfolgreich, False sonst
    """
    print(f"\n{'=' * 80}")
    print("📥 Lade und merge Daten (streaming-basiert)...")
    print("=" * 80)

    # Backup erstellen
    backup_file = merged_file.with_suffix('.parquet.backup')
    if not backup_file.exists():
        print(f"💾 Erstelle Backup: {backup_file.name}")
        shutil.copy2(merged_file, backup_file)
    else:
        print(f"💾 Backup existiert bereits: {backup_file.name}")

    # Lade merged Parquet-Datei
    print(f"\n📖 Lade {merged_file.name}...")
    merged_df = pd.read_parquet(merged_file)

    # Stelle sicher, dass Index ein DatetimeIndex ist
    if not isinstance(merged_df.index, pd.DatetimeIndex):
        merged_df.index = pd.to_datetime(merged_df.index)
    # Index immer timezone-naive für zuverlässigen Merge mit Quelldateien
    if merged_df.index.tz is not None:
        merged_df.index = merged_df.index.tz_localize(None)
    # Auf 30-Min-Raster normalisieren (wie Quelldateien), damit Index-Overlap funktioniert
    merged_df.index = merged_df.index.floor('30min')
    merged_df = merged_df[~merged_df.index.duplicated(keep='first')]
    merged_df = merged_df.sort_index()

    original_count = len(merged_df)
    print(f"   Original: {original_count:,} Zeilen")
    nan_before = int(merged_df.isna().sum().sum())

    target_columns = list(merged_df.columns)
    total_new_rows = 0
    files_processed = 0
    files_with_data = 0
    batches_merged = 0
    batch_dfs = []
    n_paths = len(file_paths)
    show_progress = n_paths > 50
    n_workers = max(1, LOAD_PARALLEL) if LOAD_PARALLEL else 1

    print(f"\n   Verarbeite {n_paths} Dateien (Batch-Merge: {BATCH_MERGE_SIZE}, Speichern alle {SAVE_INTERVAL})...")
    if n_workers > 1:
        print(f"   Paralleles Laden: {n_workers} Worker")

    def load_one(path: Path):
        try:
            return path, load_and_merge_radiation_file(path, target_columns=target_columns)
        except Exception as e:
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
                        files_with_data += 1
        else:
            for file_path in batch_paths:
                try:
                    df_new = load_and_merge_radiation_file(file_path, target_columns=target_columns)
                    if not df_new.empty:
                        batch_dfs.append(df_new)
                        files_with_data += 1
                except Exception as e:
                    if not show_progress:
                        print(f"      ⚠️ {file_path.name}: {e}")
                    continue

        if not batch_dfs:
            continue
        batches_merged += 1

        # Batch-Merge: alle geladenen DataFrames zu einem kombinieren, dann einmal combine_first
        combined = pd.concat(batch_dfs, axis=0)
        combined = combined[~combined.index.duplicated(keep='first')]
        combined = combined.sort_index()
        # Index timezone-naive (wie merged_df), damit Indizes exakt matchen
        if combined.index.tz is not None:
            combined.index = combined.index.tz_localize(None)
        # Auf 30-Min-Raster normalisieren (Quelldateien oft 00:00:00.xxx), damit intersection mit Parquet trifft
        combined.index = combined.index.floor('30min')
        combined = combined[~combined.index.duplicated(keep='first')]
        combined = combined.sort_index()
        missing_cols = [c for c in target_columns if c not in combined.columns]
        if missing_cols:
            na_df = pd.DataFrame({c: pd.NA for c in missing_cols}, index=combined.index)
            combined = pd.concat([combined, na_df], axis=1)
        combined = combined[target_columns]
        for col in combined.columns:
            if pd.api.types.is_numeric_dtype(merged_df[col].dtype):
                combined[col] = pd.to_numeric(combined[col], errors='coerce')

        n_new_ix = len(combined.index.difference(merged_df.index))
        merged_df = merged_df.combine_first(combined)
        # Quelldaten explizit zuweisen (update kann bei Index-Darstellung scheitern)
        overlap = combined.index.intersection(merged_df.index)
        if len(overlap) > 0:
            # Explizit an overlap ausrichten, dann zuweisen (Reihenfolge garantiert)
            combined_aligned = combined.reindex(overlap)
            for col in target_columns:
                if col in combined_aligned.columns:
                    vals = combined_aligned[col].values
                    merged_df.loc[overlap, col] = vals
        total_new_rows += n_new_ix
        batch_dfs.clear()
        del combined
        gc.collect()

        # Zwischenspeicherung seltener (nur schreiben, kein Re-Load um I/O zu sparen)
        if files_processed % SAVE_INTERVAL == 0:
            print(f"\n   💾 Zwischenspeicherung ({files_processed} Dateien, {len(merged_df):,} Zeilen)...")
            temp_file = merged_file.with_suffix('.parquet.temp')
            merged_df.to_parquet(temp_file, compression='snappy')
            # Optional: Re-Load nur bei sehr vielen Dateien um Speicherfragmentierung zu mindern
            if files_processed % (SAVE_INTERVAL * 3) == 0 and files_processed < n_paths:
                del merged_df
                gc.collect()
                merged_df = pd.read_parquet(temp_file)
                if not isinstance(merged_df.index, pd.DatetimeIndex):
                    merged_df.index = pd.to_datetime(merged_df.index)
                if merged_df.index.tz is not None:
                    merged_df.index = merged_df.index.tz_localize(None)
                # Index wieder auf 30-Min-Raster (wie beim Start), damit weitere Batches matchen
                merged_df.index = merged_df.index.floor('30min')
                merged_df = merged_df[~merged_df.index.duplicated(keep='first')]
                merged_df = merged_df.sort_index()
            try:
                temp_file.unlink()
            except OSError:
                pass

    # Sortiere nach Index (combine_first erzeugt keine Duplikate)
    print(f"\n   Finale Bereinigung...")
    print(f"   Sortiere Daten...")
    merged_df = merged_df.sort_index()
    gc.collect()

    # Finale Speicherung
    print(f"\n💾 Speichere finale Parquet-Datei...")
    merged_df.to_parquet(merged_file, compression='snappy')

    # Finale Speicher-Bereinigung
    del merged_df
    gc.collect()

    merged_df = pd.read_parquet(merged_file)
    final_count = len(merged_df)
    nan_after = int(merged_df.isna().sum().sum())
    nan_filled = nan_before - nan_after
    del merged_df

    print(f"\n✅ Fertig! ({merged_file.name})")
    print(f"   Dateien mit Daten geladen: {files_with_data:,} / {n_paths:,}")
    print(f"   Batches gemergt: {batches_merged:,}")
    print(f"   Original: {original_count:,} Zeilen")
    print(f"   Neu hinzugefügt (neue Zeitstempel): {total_new_rows:,} Zeilen")
    if nan_filled > 0:
        print(f"   NaN gefüllt (bestehende Zeilen): {nan_filled:,} Werte")
    print(f"   Final: {final_count:,} Zeilen")
    print(f"   Zuwachs: {final_count - original_count:,} Zeilen")

    return True


def main():
    print("=" * 80)
    print("🔍 Suche nach Strahlungsdaten für Radiation-Parquet-Dateien")
    print("=" * 80)

    # ═══ Phase 1: Lückenliste erstellen (wo Parquet-Dateien NaNs haben) ═══
    print(f"\n{'=' * 80}")
    print("📋 Phase 1: Lückenliste aus Parquet-Dateien erstellen...")
    print("=" * 80)

    parquet_files = find_radiation_parquet_files(MERGED_LONG_DIR)
    if not parquet_files:
        print(f"\n⚠️  Keine Radiation-Parquet-Dateien gefunden in {MERGED_LONG_DIR}")
        return

    parquet_info = {}  # {parquet_file: (station, gaps, data_start, data_end)}
    for parquet_file in parquet_files:
        station = parquet_file.stem.replace('_radiation_merged_long', '').replace('_cr6_merged_long', '')
        gaps, data_start, data_end = find_gaps_in_merged(parquet_file, MIN_GAP_HOURS)
        if gaps:
            write_gaps_list(parquet_file, gaps, station, MERGED_LONG_DIR)
        parquet_info[parquet_file] = (station, gaps, data_start, data_end)

    # ═══ Phase 2: Dateien suchen, die Lücken füllen können ═══
    print(f"\n{'=' * 80}")
    print("🔍 Phase 2: Suche nach Dateien mit Daten für die Lücken...")
    print("=" * 80)

    radiation_files = scan_source_directories(SOURCE_DIRS)
    if not radiation_files:
        print("\n⚠️  Keine Strahlungsdaten-Dateien in den Quellordnern gefunden!")
        return

    # ═══ Phase 3: Listen erstellen (Dateien mit neuen Daten, bereits durchsucht ohne neue Daten) ═══
    print(f"\n{'=' * 80}")
    print("📋 Phase 3: Listen erstellen...")
    print("=" * 80)

    files_with_new_data = set()  # Dateien, die Lücken füllen oder vor/nach liegen
    parquet_file_paths = {}

    for parquet_file, (station, gaps, data_start, data_end) in parquet_info.items():
        if pd.isna(data_start) or pd.isna(data_end):
            parquet_file_paths[parquet_file] = []
            continue
        station_files = filter_files_for_station(radiation_files, station).copy()
        csv_files = find_csv_files_for_station(CSV_SOURCE_DIRS, station)
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

        parquet_file_paths[parquet_file] = list(set(paths))

    files_searched_no_data = [
        str(p.resolve()) for p in radiation_files
        if p not in files_with_new_data
    ]
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

    success_count = 0
    for parquet_file, file_paths in parquet_file_paths.items():
        if not file_paths:
            continue
        station = parquet_file.stem.replace('_radiation_merged_long', '').replace('_cr6_merged_long', '')
        print(f"\n{'=' * 80}")
        print(f"🔧 Verarbeite {station}: {len(file_paths)} Dateien")
        print("=" * 80)

        if fill_gaps_in_merged(parquet_file, file_paths):
            success_count += 1

    attempted = sum(1 for p in parquet_file_paths.values() if p)
    print(f"\n{'=' * 80}")
    print(f"✅ Fertig! {success_count} von {attempted} Parquet-Dateien erfolgreich verarbeitet")
    print("=" * 80)


if __name__ == "__main__":
    main()
