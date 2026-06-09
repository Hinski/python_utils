#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Merged alle WXT-Dateien eines Stations-"raw"-Ordners zu EINER kontinuierlichen Zeitreihe.
Speichert als CSV in ~/Data/{Station}/merged/{Station}_wxt_merged.csv

Verwendung:
    python merge_wxt_files.py                    # Interaktive Stationsauswahl
    python merge_wxt_files.py Gorigo             # Direkt für Gorigo
    python merge_wxt_files.py /pfad/zur/station  # Mit vollständigem Pfad
"""

from pathlib import Path
import pandas as pd
import sys

from data_loader import read_toa5

# ---------------------------------------------------------------------
# 🎯 Konfiguration
# ---------------------------------------------------------------------
DATA_BASE = Path("/Users/hingerl-l/Data")
AVAILABLE_STATIONS = ["Gorigo", "Janga", "Kayoro", "Mole", "Nazinga", "Sumbrungu"]

# Diese werden in main() gesetzt
STATION_DIR = None
RAW_DIR = None
OUT_DIR = None


# ---------------------------------------------------------------------
# WXT-Dateien finden und laden
# ---------------------------------------------------------------------
def find_wxt_files(raw_dir: Path) -> tuple[list[Path], list[Path]]:
    """Findet alle Dateien mit 'WXT' oder 'wxt' im Dateinamen.
    
    Unterstützt verschiedene Namensmuster:
    - gor_WXT_*.dat
    - TOA5_*.WXT*.dat
    - W1_WXT*.dat
    - WXT_*.dat
    - etc.
    
    Returns:
        (files_with_header, files_without_header) - getrennt nach Format
    """
    all_files = []
    # Erweiterte Patterns für verschiedene Namenskonventionen
    # Suche rekursiv in allen Unterordnern
    patterns = [
        "**/*WXT*.dat",
        "**/*wxt*.dat",
        "**/*WXT*",
        "**/*wxt*",
    ]
    
    for pattern in patterns:
        found = list(raw_dir.glob(pattern))
        all_files.extend(found)
    
    # Entferne Duplikate und filtere nur Dateien (keine Ordner, keine .log Dateien)
    all_files = list(set([f for f in all_files if f.is_file() and f.suffix.lower() in ['.dat', '.csv']]))
    all_files = sorted(all_files)
    
    # Trenne nach Format
    files_with_header = []
    files_without_header = []
    
    for f in all_files:
        fmt = detect_wxt_format(f)
        if fmt == 'toa5':
            files_with_header.append(f)
        elif fmt == 'no_header':
            files_without_header.append(f)
        else:
            # Unbekanntes Format - versuche trotzdem zu laden (könnte Header haben)
            # Prüfe ob erste Zeile TOA5/CR3000 enthält
            try:
                with open(f, 'r', encoding='utf-8', errors='ignore') as first_line_check:
                    first_line = first_line_check.readline()
                    if first_line and ('TOA5' in first_line.upper() or 'CR3000' in first_line.upper()):
                        files_with_header.append(f)
                    else:
                        files_without_header.append(f)
            except:
                files_without_header.append(f)
    
    return files_with_header, files_without_header


def extract_wxt_header(path: Path) -> tuple[str, str, str, str] | None:
    """Extrahiert die Header-Zeilen (1, 2, 3, 4) aus einer WXT-Datei.
    
    Struktur:
    - Zeile 1: Metadaten (TOA5, Logger-Info)
    - Zeile 2: Spaltennamen (TIMESTAMP, RECORD, ...)
    - Zeile 3: Einheiten (TS, RN, degree, ...)
    - Zeile 4: Statistik-Typen ("", "", Min, Smp, ...)
    """
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = []
            for i in range(5):  # Lese erste 5 Zeilen
                line = f.readline()
                if not line:
                    break
                lines.append(line)
        
        if len(lines) < 4:
            return None
        
        # Prüfe ob Zeile 1 TOA5/CR3000 enthält
        if len(lines) >= 2:
            line1_upper = lines[0].upper()
            line2_upper = lines[1].upper()
            
            # Validiere dass es eine WXT-Datei ist
            if 'TOA5' not in line1_upper and 'CR3000' not in line1_upper:
                return None
            
            # Suche nach der Zeile mit TIMESTAMP (kann Zeile 2 oder später sein)
            col_header_idx = None
            for i, line in enumerate(lines):
                line_upper = line.upper()
                if 'TIMESTAMP' in line_upper or (i > 0 and 'TS' in line_upper and 'RECORD' in line_upper):
                    col_header_idx = i
                    break
            
            if col_header_idx is None:
                # Keine TIMESTAMP-Zeile gefunden
                return None
            
            # Zeile 1: Metadaten (TOA5, Logger-Info)
            # Zeile col_header_idx: Spaltennamen (TIMESTAMP, RECORD, ...)
            # Zeile col_header_idx+1: Einheiten (TS, RN, degree, ...)
            # Zeile col_header_idx+2: Statistik-Typen ("", "", Min, Smp, ...)
            header_line1 = lines[0].rstrip('\n')
            header_line2 = lines[col_header_idx].rstrip('\n')
            header_line3 = lines[col_header_idx + 1].rstrip('\n') if col_header_idx + 1 < len(lines) else ''
            header_line4 = lines[col_header_idx + 2].rstrip('\n') if col_header_idx + 2 < len(lines) else ''
            
            return (header_line1, header_line2, header_line3, header_line4)
        else:
            return None
    except Exception as e:
        print(f"    ⚠️ Konnte Header nicht extrahieren: {e}")
        return None


def detect_wxt_format(path: Path) -> str:
    """Erkennt das Format einer WXT-Datei: 'toa5' (mit Header) oder 'no_header' (ohne Header)."""
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            # Lese erste paar Zeilen, um Leerzeilen zu überspringen
            lines = []
            for _ in range(5):
                line = f.readline()
                if line:
                    lines.append(line.strip())
                else:
                    break
            
            if not lines:
                return 'unknown'
            
            # Prüfe alle gelesenen Zeilen nach TOA5/CR3000
            for line in lines:
                line_upper = line.upper()
                if 'TOA5' in line_upper or 'CR3000' in line_upper:
                    return 'toa5'
            
            # Prüfe erste nicht-leere Zeile auf Datum (kein Header)
            first_non_empty = next((l for l in lines if l), None)
            if first_non_empty:
                # Prüfe ob erste Zeile ein Datum enthält (Format: YYYY-MM-DD oder ähnlich)
                if any(char.isdigit() for char in first_non_empty[:20]) and ('-' in first_non_empty[:20] or '/' in first_non_empty[:20]):
                    # Prüfe ob es wirklich ein Datum ist (nicht nur Zahlen)
                    if 'TIMESTAMP' not in first_non_empty.upper():
                        return 'no_header'
            
            return 'unknown'
    except Exception as e:
        return 'unknown'


def load_wxt_file(path: Path, expected_columns: list = None, verbose: bool = False) -> tuple[pd.DataFrame | None, str | None]:
    """Lädt eine WXT-Datei - unterstützt sowohl TOA5-Format (mit Header) als auch Dateien ohne Header."""
    try:
        if verbose:
            print(f"  → Lade {path.name}...")
        
        # Erkenne Dateiformat
        file_format = detect_wxt_format(path)
        
        if file_format == 'toa5':
            # Datei mit TOA5-Header
            header_info = extract_wxt_header(path)
            if not header_info:
                if verbose:
                    print(f"    ⚠️ Konnte Header nicht lesen: {path.name}")
                return None, "Header nicht lesbar"
            
            # Parse Spaltennamen aus Header-Zeile 2 (die mit TIMESTAMP)
            import csv
            header_cols_raw = list(csv.reader([header_info[1]]))[0]
            header_cols = [col.strip().strip('"').strip() for col in header_cols_raw]
            header_cols = [col for col in header_cols if col]
            
            # Prüfe ob TIMESTAMP oder TS enthalten ist
            if not any('TIMESTAMP' in col.upper() or col.upper() == 'TS' for col in header_cols):
                if verbose:
                    print(f"    ⚠️ Keine TIMESTAMP/TS Spalte in Header gefunden: {path.name}")
                return None, "Keine TIMESTAMP/TS Spalte"
            
            if not header_cols:
                if verbose:
                    print(f"    ⚠️ Keine Spaltennamen im Header gefunden: {path.name}")
                return None, "Keine Spaltennamen"
            
            # Struktur: Zeile 1-4 sind Header, Daten ab Zeile 5
            skip_rows = 4
            
        elif file_format == 'no_header':
            # Datei ohne Header - verwende erwartete Spaltennamen (aus erster Datei mit Header)
            if not expected_columns:
                if verbose:
                    print(f"    ⚠️ Keine erwarteten Spaltennamen verfügbar (benötigt erste Datei mit Header): {path.name}")
                return None, "Keine erwarteten Spaltennamen"
            
            # Erwartete Spaltennamen verwenden (TIMESTAMP ist erste Spalte in den Daten)
            header_cols = expected_columns.copy()
            skip_rows = 0  # Keine Header-Zeilen zu überspringen
            
        else:
            if verbose:
                print(f"    ⚠️ Unbekanntes Dateiformat: {path.name}")
            return None, "Unbekanntes Format"
        
        # Lade Daten mit pandas
        # Zuerst ohne Spaltennamen laden um Spaltenanzahl zu prüfen
        df_temp = pd.read_csv(
            path,
            skiprows=skip_rows,
            header=None,
            na_values=["NAN", "NA", "-9999", "-999", "**************"],
            low_memory=False,
            on_bad_lines='skip'
        )
        
        if df_temp.empty:
            if verbose:
                print(f"    ⚠️ Keine Daten gefunden: {path.name}")
            return None, "Keine Daten"
        
        # Prüfe Spaltenanzahl und setze Spaltennamen entsprechend
        n_cols = len(df_temp.columns)
        n_expected = len(header_cols)
        
        if n_cols == n_expected:
            # Perfekt: Spaltenanzahl stimmt
            df_temp.columns = header_cols
            df = df_temp
        elif n_cols == n_expected - 1:
            # Eine Spalte fehlt - wahrscheinlich TIMESTAMP fehlt in header_cols oder erste Spalte ist TIMESTAMP
            # Prüfe ob erste Spalte ein Datum ist
            first_col_sample = str(df_temp.iloc[0, 0]) if len(df_temp) > 0 else ""
            if any(char.isdigit() for char in first_col_sample[:10]) and ('-' in first_col_sample[:10] or '/' in first_col_sample[:10]):
                # Erste Spalte ist TIMESTAMP - füge sie zu header_cols hinzu
                df = pd.DataFrame(index=df_temp.index)
                df['TIMESTAMP'] = df_temp.iloc[:, 0]
                data_cols = [col for col in header_cols if col.upper() not in ['TIMESTAMP', 'TS']]
                for i, col in enumerate(data_cols):
                    if i < len(df_temp.columns) - 1:
                        df[col] = df_temp.iloc[:, i + 1]
            else:
                # TIMESTAMP fehlt in Daten - verwende nur Daten-Spalten
                data_cols = [col for col in header_cols if col.upper() not in ['TIMESTAMP', 'TS']]
                if n_cols == len(data_cols):
                    df_temp.columns = data_cols
                    df = df_temp
                else:
                    if verbose:
                        print(f"    ⚠️ Spaltenanzahl stimmt nicht: {n_cols} statt {n_expected}: {path.name}")
                    return None, f"Spaltenanzahl falsch ({n_cols} statt {n_expected})"
        else:
            if verbose:
                print(f"    ⚠️ Spaltenanzahl stimmt nicht: {n_cols} statt {n_expected}: {path.name}")
            return None, f"Spaltenanzahl falsch ({n_cols} statt {n_expected})"
        
        if df.empty:
            if verbose:
                print(f"    ⚠️ Keine Daten gefunden: {path.name}")
            return None, "DataFrame leer"
        
        # TIMESTAMP/TS sollte erste Spalte sein
        timestamp_col = None
        for col in ['TIMESTAMP', 'TS']:
            if col in df.columns:
                timestamp_col = col
                break
        
        if not timestamp_col:
            if verbose:
                print(f"    ⚠️ Keine TIMESTAMP/TS Spalte gefunden: {path.name}")
            return None, "Keine TIMESTAMP Spalte"
        
        # Setze Index auf TIMESTAMP
        df[timestamp_col] = pd.to_datetime(df[timestamp_col], errors='coerce')
        df = df.set_index(timestamp_col)
        df = df[df.index.notna()]
        
        if df.empty:
            if verbose:
                print(f"    ⚠️ Keine gültigen Timestamps: {path.name}")
            return None, "Keine gültigen Timestamps"
        
        # Sortiere nach Index
        df = df.sort_index()
        df = df[~df.index.duplicated(keep="first")]
        
        # Entferne ungültige Timestamps (z.B. 1936, 2025)
        n_before = len(df)
        df = df[(df.index.year >= 2000) & (df.index.year <= 2030)]
        n_removed = n_before - len(df)
        if n_removed > 0:
            print(f"    (Entfernt: {n_removed} Zeilen mit ungültigem Jahr)")
        
        if df.empty:
            if verbose:
                print(f"    ⚠️ Keine gültigen Daten nach Jahr-Filterung: {path.name}")
            return None, "Keine gültigen Daten nach Jahr-Filterung"
        
        if verbose:
            print(f"    ✓ {len(df):,} Zeilen, {len(df.columns)} Spalten")
            if len(df) > 0:
                print(f"    Zeitraum: {df.index.min()} → {df.index.max()}")
            # Debug: Zeige Spaltennamen
            if len(df.columns) <= 20:
                print(f"    Spalten: {', '.join(df.columns.tolist())}")
        
        return df, None
        
    except Exception as e:
        if verbose:
            print(f"    ❌ Fehler beim Laden: {e}")
            import traceback
            traceback.print_exc()
        return None, f"Exception: {str(e)}"


def merge_wxt_files():
    """Merged alle WXT-Dateien zu einer kontinuierlichen Zeitreihe."""
    global STATION_DIR, RAW_DIR, OUT_DIR
    
    print(f"\n{'='*60}")
    print(f"  MERGE WXT-DATEIEN")
    print(f"{'='*60}")
    print(f"📁 Station: {STATION_DIR.name}")
    print(f"📁 Input: {RAW_DIR}")
    print(f"📁 Output: {OUT_DIR}\n")
    
    # Finde WXT-Dateien (getrennt nach Format)
    files_with_header, files_without_header = find_wxt_files(RAW_DIR)
    all_wxt_files = files_with_header + files_without_header
    
    if not all_wxt_files:
        print("  ❌ Keine WXT-Dateien gefunden.")
        print(f"     Gesucht in: {RAW_DIR}")
        print(f"     Pattern: *WXT*, *wxt*")
        return
    
    print(f"  Gefundene WXT-Dateien: {len(all_wxt_files)}")
    print(f"    Mit Header (TOA5): {len(files_with_header)}")
    print(f"    Ohne Header: {len(files_without_header)}")
    
    # Debug: Zeige erste paar Dateien
    if len(all_wxt_files) <= 20:
        print(f"\n  Gefundene Dateien:")
        for f in all_wxt_files[:20]:
            fmt = detect_wxt_format(f)
            print(f"    {f.name} [{fmt}]")
    elif len(all_wxt_files) > 20:
        print(f"\n  Erste 10 Dateien:")
        for f in all_wxt_files[:10]:
            fmt = detect_wxt_format(f)
            print(f"    {f.name} [{fmt}]")
        print(f"    ... und {len(all_wxt_files) - 10} weitere")
    print()
    
    # Finde erste Datei MIT Header (TOA5-Format) um Spaltennamen zu extrahieren
    header_lines = None
    expected_columns = None
    
    if files_with_header:
        print("  Extrahiere Header aus TOA5-Datei...")
        # Versuche mehrere Dateien bis eine funktioniert
        # Bevorzuge Dateien mit "TOA5" im Namen
        priority_files = [f for f in files_with_header if 'TOA5' in f.name.upper()]
        other_files = [f for f in files_with_header if f not in priority_files]
        files_to_try = priority_files[:5] + other_files[:5]  # Versuche zuerst TOA5-Dateien
        
        header_lines = None
        header_file = None
        for f in files_to_try:
            print(f"  → Versuche: {f.name}")
            header_lines = extract_wxt_header(f)
            if header_lines:
                # Validiere Header
                import csv
                try:
                    header_cols_raw = list(csv.reader([header_lines[1]]))[0]
                    header_cols = [col.strip().strip('"').strip() for col in header_cols_raw]
                    header_cols = [col for col in header_cols if col]
                    
                    # Validiere dass TIMESTAMP enthalten ist
                    if any('TIMESTAMP' in col.upper() or col.upper() == 'TS' for col in header_cols):
                        header_file = f
                        print(f"  ✓ Header gefunden in: {f.name}")
                        break
                    else:
                        print(f"    ⚠️ Keine TIMESTAMP/TS in Header")
                        header_lines = None
                except Exception as e:
                    print(f"    ⚠️ Fehler beim Parsen: {e}")
                    header_lines = None
        
        if header_lines and header_file:
            # Parse Spaltennamen aus Header
            import csv
            header_cols_raw = list(csv.reader([header_lines[1]]))[0]  # Spaltennamen-Zeile
            # Entferne Quotes und Whitespace, normalisiere
            expected_columns = [col.strip().strip('"').strip() for col in header_cols_raw]
            # Entferne leere Strings
            expected_columns = [col for col in expected_columns if col]
            
            print(f"  Erwartete Spalten aus Header: {len(expected_columns)}")
            print(f"    {', '.join(expected_columns)}")
        else:
            print("  ⚠️ Konnte Header aus keiner TOA5-Datei extrahieren")
            # Debug: Zeige erste Zeilen einer Datei
            if files_with_header:
                debug_file = files_with_header[0]
                print(f"  Debug: Erste Zeilen von {debug_file.name}:")
                try:
                    with open(debug_file, 'r', encoding='utf-8', errors='ignore') as f:
                        for i in range(5):
                            line = f.readline()
                            if line:
                                print(f"    Zeile {i+1}: {line[:100].rstrip()}")
                except Exception as e:
                    print(f"    Fehler: {e}")
    else:
        print("  ⚠️ Keine Datei mit Header gefunden!")
        print("  ⚠️ Benötige mindestens eine TOA5-Datei um Spaltennamen zu bestimmen")
        return
    
    if not expected_columns:
        print("  ⚠️ Konnte Spaltennamen nicht bestimmen")
        return
    
    # Lade alle Dateien und normalisiere Spaltennamen
    # Zuerst Dateien mit Header, dann ohne Header
    dfs = []
    loaded_count = 0
    skipped_count = 0
    skipped_files = []
    skipped_reasons = {}  # Grund -> Anzahl
    year_stats = {}  # Jahr -> Anzahl Dateien
    
    # Reset Warnungs-Flags
    merge_wxt_files._missing_cols_warned = False
    merge_wxt_files._missing_col_warned = False
    
    print(f"  Lade {len(all_wxt_files)} Dateien...")
    verbose_loading = len(all_wxt_files) <= 50  # Nur bei wenigen Dateien ausführlich ausgeben
    
    for i, f in enumerate(all_wxt_files, 1):
        if not verbose_loading and i % 100 == 0:
            print(f"    Fortschritt: {i}/{len(all_wxt_files)} Dateien verarbeitet...")
        
        df, skip_reason = load_wxt_file(f, expected_columns, verbose=verbose_loading)
        if df is not None and not df.empty:
            # Statistiken sammeln
            if len(df) > 0:
                year = df.index.min().year
                year_stats[year] = year_stats.get(year, 0) + 1
            
            loaded_count += 1
            # Normalisiere Spaltennamen: entferne Whitespace
            df.columns = [col.strip() for col in df.columns]
            
            # Wenn Header vorhanden, verwende nur die erwarteten Spalten
            if expected_columns:
                # Spalten wurden bereits aus Header gelesen, nur Reihenfolge anpassen
                data_cols = [col for col in expected_columns if col.upper() not in ['TIMESTAMP', 'TS']]
                
                # Prüfe ob alle erwarteten Spalten vorhanden sind
                missing_cols = set(data_cols) - set(df.columns)
                if missing_cols:
                    # Nur einmal warnen, nicht bei jeder Datei
                    if not hasattr(merge_wxt_files, '_missing_cols_warned'):
                        print(f"      ⚠️ Fehlende Spalten in einigen Dateien: {missing_cols}")
                        merge_wxt_files._missing_cols_warned = True
                    for col in missing_cols:
                        df[col] = pd.NA
                
                # Sortiere Spalten nach erwarteter Reihenfolge
                df = df[data_cols]
                # Erstelle Mapping: erwartete Spalte -> DataFrame-Spalte
                # TIMESTAMP wird später aus dem Index erstellt, RECORD muss als Spalte bleiben
                col_mapping = {}  # erwartete_col -> df_col
                
                for expected_col in expected_columns:
                    # TIMESTAMP wird später aus Index erstellt
                    if expected_col.upper() in ['TIMESTAMP', 'TS']:
                        continue
                    
                    # Suche nach passender Spalte (case-insensitive, mit Whitespace-Toleranz)
                    found = None
                    for df_col in df.columns:
                        if df_col.strip().upper() == expected_col.strip().upper():
                            found = df_col
                            break
                    
                    if found:
                        col_mapping[expected_col] = found
                    else:
                        # Spalte nicht gefunden - füge als NaN-Spalte hinzu
                        df[expected_col] = pd.NA
                        col_mapping[expected_col] = expected_col
                        # Nur einmal warnen
                        if not hasattr(merge_wxt_files, '_missing_col_warned'):
                            print(f"      ⚠️ Einige Spalten fehlen in manchen Dateien und werden als NaN hinzugefügt")
                            merge_wxt_files._missing_col_warned = True
                
                # Erstelle neuen DataFrame mit erwarteten Spalten in richtiger Reihenfolge
                # (ohne TIMESTAMP, das kommt später aus dem Index)
                data_cols = [col for col in expected_columns if col.upper() not in ['TIMESTAMP', 'TS']]
                df_reordered = pd.DataFrame(index=df.index)
                for expected_col in data_cols:
                    df_reordered[expected_col] = df[col_mapping[expected_col]]
                
                df = df_reordered
                # Nur bei verbose ausgeben
                if verbose_loading:
                    print(f"    Nach Normalisierung: {len(df.columns)} Spalten")
            
            dfs.append(df)
        else:
            skipped_count += 1
            skipped_files.append(f.name)
            reason = skip_reason or "Unbekannt"
            skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
    
    print(f"\n  📊 Statistik:")
    print(f"    Geladen: {loaded_count}/{len(all_wxt_files)} Dateien")
    print(f"    Übersprungen: {skipped_count} Dateien")
    
    if year_stats:
        print(f"\n  📅 Dateien nach Jahr:")
        for year in sorted(year_stats.keys()):
            print(f"    {year}: {year_stats[year]} Dateien")
    
    if skipped_reasons:
        print(f"\n  ⚠️ Gründe für übersprungene Dateien:")
        for reason, count in sorted(skipped_reasons.items(), key=lambda x: x[1], reverse=True):
            print(f"    {reason}: {count} Dateien")
    
    if skipped_files and len(skipped_files) <= 20:
        print(f"\n  ⚠️ Übersprungene Dateien (erste 20):")
        for fname in skipped_files[:20]:
            print(f"    - {fname}")
    elif skipped_files:
        print(f"\n  ⚠️ {len(skipped_files)} Dateien wurden übersprungen")
    
    if not dfs:
        print("\n⚠️ Keine gültigen Daten geladen.")
        return
    
    # Zeitlich concatenieren
    print(f"\n  Kombiniere {len(dfs)} DataFrames...")
    # Stelle sicher dass alle DataFrames die gleichen Spalten haben
    if expected_columns:
        # Entferne TIMESTAMP/TS aus erwarteten Spalten für DataFrame-Spalten
        data_cols = [col for col in expected_columns if col.upper() not in ['TIMESTAMP', 'TS']]
        # Stelle sicher dass alle DataFrames die gleichen Spalten haben
        for i, df in enumerate(dfs):
            missing_cols = set(data_cols) - set(df.columns)
            if missing_cols:
                for col in missing_cols:
                    df[col] = pd.NA
            # Sortiere Spalten nach erwarteter Reihenfolge
            dfs[i] = df[data_cols]
        print(f"  Erwartete Spalten (ohne TIMESTAMP): {len(data_cols)}")
        print(f"  Tatsächliche Spalten nach Normalisierung: {len(dfs[0].columns) if dfs else 0}")
    
    merged = pd.concat(dfs, ignore_index=False)
    merged = merged.sort_index()
    
    # Entferne Duplikate
    n_dups = merged.index.duplicated().sum()
    if n_dups > 0:
        print(f"  (Entferne {n_dups:,} Duplikate)")
    merged = merged[~merged.index.duplicated(keep="first")]
    
    # Spalten-Info
    print(f"\n  Finale Spalten ({len(merged.columns)}):")
    for col in merged.columns[:15]:
        print(f"    - {col}")
    if len(merged.columns) > 15:
        print(f"    ... und {len(merged.columns) - 15} weitere")
    
    # Stelle sicher dass Index ein DatetimeIndex ist
    if not isinstance(merged.index, pd.DatetimeIndex):
        print(f"  ⚠️ Konvertiere Index zu DatetimeIndex...")
        merged.index = pd.to_datetime(merged.index, errors='coerce')
        merged = merged[merged.index.notna()]
        if merged.empty:
            print("  ❌ Keine gültigen Daten nach Index-Konvertierung")
            return
    
    # Zeige Zeitraum-Statistik
    if not merged.empty:
        min_date = merged.index.min()
        max_date = merged.index.max()
        years_covered = sorted(set(merged.index.year))
        
        print(f"\n  📅 Zeitraum-Statistik:")
        print(f"    Von: {min_date}")
        print(f"    Bis: {max_date}")
        print(f"    Jahre mit Daten: {', '.join(map(str, years_covered))}")
        
        # Prüfe auf Lücken
        expected_years = set(range(min(years_covered), max(years_covered) + 1))
        missing_years = expected_years - set(years_covered)
        if missing_years:
            print(f"    ⚠️ Fehlende Jahre: {', '.join(map(str, sorted(missing_years)))}")
    
    # Ausgabe schreiben mit Header-Zeilen
    out_path = OUT_DIR / f"{STATION_DIR.name}_wxt_merged.csv"
    
    if header_lines:
        # Stelle sicher dass TIMESTAMP als erste Spalte geschrieben wird
        # Erstelle DataFrame mit TIMESTAMP als erste Spalte
        merged_output = merged.copy()
        
        # Füge TIMESTAMP als erste Spalte hinzu (aus Index)
        merged_output.insert(0, 'TIMESTAMP', merged.index)
        
        # Stelle sicher dass alle erwarteten Spalten vorhanden sind
        if expected_columns:
            # Prüfe welche Spalten fehlen
            missing_cols = []
            for col in expected_columns:
                if col not in merged_output.columns:
                    missing_cols.append(col)
                    merged_output[col] = pd.NA
            
            if missing_cols:
                print(f"  ⚠️ Fehlende Spalten hinzugefügt: {missing_cols}")
            
            # Sortiere Spalten nach erwarteter Reihenfolge
            merged_output = merged_output[expected_columns]
        
        # Schreibe Header-Zeilen zuerst
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(header_lines[0] + '\n')  # Metadaten (Zeile 1)
            f.write(header_lines[1] + '\n')  # Spaltennamen (Zeile 2)
            f.write(header_lines[2] + '\n')  # Einheiten (Zeile 3)
            f.write(header_lines[3] + '\n')  # Statistik-Typen (Zeile 4)
            
            # Dann die Daten (TIMESTAMP ist jetzt erste Spalte)
            merged_output.to_csv(f, lineterminator='\n', header=False, index=False)
    else:
        # Fallback: Standard CSV ohne speziellen Header
        merged.to_csv(out_path)
    
    print(f"\n✅ Gespeichert: {out_path.name}")
    try:
        print(f"   Zeitraum: {merged.index.min()} → {merged.index.max()}")
    except Exception as e:
        print(f"   ⚠️ Zeitraum konnte nicht bestimmt werden: {e}")
    print(f"   Zeilen: {len(merged):,}")
    print(f"   Spalten: {len(merged.columns)}")


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
            print(f"❌ Pfad nicht gefunden: {station_path}")
            sys.exit(1)
    
    # Interaktive Auswahl
    print("\n" + "=" * 60)
    print("  Verfügbare Stationen:")
    print("=" * 60)
    
    for i, station in enumerate(AVAILABLE_STATIONS, 1):
        station_path = DATA_BASE / station
        raw_exists = "✓" if (station_path / "raw").exists() else "✗"
        print(f"  {i}) {station:12s} [raw: {raw_exists}]")
    
    print("=" * 60)
    
    while True:
        try:
            choice = input(f"\nStation auswählen (1-{len(AVAILABLE_STATIONS)}): ").strip()
            
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(AVAILABLE_STATIONS):
                    station = AVAILABLE_STATIONS[idx]
                    STATION_DIR = DATA_BASE / station
                    RAW_DIR = STATION_DIR / "raw"
                    OUT_DIR = STATION_DIR / "merged"
                    OUT_DIR.mkdir(exist_ok=True)
                    return STATION_DIR
            else:
                # Name eingegeben
                for station in AVAILABLE_STATIONS:
                    if station.lower() == choice.lower():
                        STATION_DIR = DATA_BASE / station
                        RAW_DIR = STATION_DIR / "raw"
                        OUT_DIR = STATION_DIR / "merged"
                        OUT_DIR.mkdir(exist_ok=True)
                        return STATION_DIR
            
            print(f"⚠️ Ungültige Eingabe.")
            
        except KeyboardInterrupt:
            print("\n\nAbgebrochen.")
            sys.exit(0)


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
def main():
    global STATION_DIR, RAW_DIR, OUT_DIR
    
    # Station auswählen
    select_station()
    
    # Prüfe ob raw-Ordner existiert
    if not RAW_DIR.exists():
        print(f"❌ Raw-Ordner nicht gefunden: {RAW_DIR}")
        sys.exit(1)
    
    # Merge WXT-Dateien
    merge_wxt_files()


if __name__ == "__main__":
    main()
