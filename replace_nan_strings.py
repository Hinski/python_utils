#!/usr/bin/env python3
"""
Ersetzt "NAN" (mit Anführungszeichen) durch NaN (ohne Anführungszeichen)
und setzt Werte in der 5. Spalte auf NaN, wenn sie < 0 oder > 63 sind.

Verwendung:
    python replace_nan_strings.py <ordner_pfad>
"""

import sys
from pathlib import Path
import re
import pandas as pd
import numpy as np


def detect_station(file_path: Path) -> str:
    """
    Erkennt die Station aus dem Dateipfad oder Dateinamen.
    
    Args:
        file_path: Pfad zur Datei
        
    Returns:
        Stationsname (z.B. 'Janga', 'Mole', 'Gorigo') oder None
    """
    path_str = str(file_path).lower()
    filename = file_path.name.lower()
    
    # Prüfe verschiedene Muster
    stations = ['janga', 'mole', 'gorigo', 'kayoro', 'nazinga', 'sumbrungu']
    for station in stations:
        if station in path_str or station in filename:
            return station.capitalize()
    
    return None


def replace_nan_in_file(file_path: Path, dry_run: bool = False, output_path: Path = None, station: str = None):
    """
    Ersetzt "NAN" durch NaN.
    
    Optional: Setzt Werte in Spalten 2-4 auf NaN, wenn die entsprechenden Werte 
    in Spalte 6 < 0, > 63 oder NaN sind (aktuell deaktiviert, siehe ENABLE_COLUMN_2_4_NAN).
    
    Zusätzlich für Janga/Mole: Setzt Werte in Spalten 2-4 auf NaN, wenn Spalte 6 > 0 ist.
    (Spalte 1 = Timeindex, Spalte 2-6 = Daten-Spalten)
    
    Args:
        file_path: Pfad zur Eingabedatei
        dry_run: Wenn True, werden keine Änderungen vorgenommen, nur angezeigt
        output_path: Optionaler Pfad für Ausgabedatei. Wenn None, wird die Eingabedatei überschrieben.
        station: Optionaler Stationsname. Wenn None, wird er aus dem Dateipfad erkannt.
    """
    try:
        # Versuche Datei als CSV zu lesen
        # Prüfe zuerst, ob es eine CSV-Datei ist
        is_csv = file_path.suffix.lower() in ['.csv', '.dat']
        
        # Prüfe ob Spalten 2-4 Operationen aktiviert sind
        ENABLE_COLUMN_2_4_NAN = True  # Setze auf True um diese Funktion zu aktivieren
        
        if is_csv and not ENABLE_COLUMN_2_4_NAN:
            # CSV-Datei: Lese als Text, um Anführungszeichen zu erhalten
            # Text-Modus für einfache String-Ersetzung ohne pandas
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            
            # Ersetze "NAN" Strings direkt im Text (behält alle anderen Anführungszeichen)
            content = content.replace('"NAN"', 'NaN')
            content = content.replace("'NAN'", 'NaN')
            
            # Prüfe ob Änderungen vorgenommen wurden
            string_changes = original_content.count('"NAN"') + original_content.count("'NAN'")
            
            if string_changes > 0:
                if dry_run:
                    print(f"  [DRY RUN] {file_path.name}: {string_changes} 'NAN' Strings würden ersetzt")
                else:
                    target_path = output_path if output_path is not None else file_path
                    # Stelle sicher, dass das Ausgabeverzeichnis existiert
                    if output_path is not None:
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(target_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    print(f"  ✓ {file_path.name}: {string_changes} 'NAN' Strings ersetzt")
                return True
            else:
                return False
        elif is_csv and ENABLE_COLUMN_2_4_NAN:
            # Wenn Spalten 2-4 Operationen aktiviert sind:
            # 1. Lese als Text für String-Ersetzung und Format-Erhaltung
            # 2. Parse mit pandas für Spalten-Operationen
            # 3. Schreibe zurück als Text mit ursprünglicher Formatierung (nur Timestamp mit "")
            
            # Schritt 1: Lese als Text für String-Ersetzung
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            
            # Prüfe ob Timestamp-Spalte Anführungszeichen hat (aus erster Datenzeile)
            timestamp_has_quotes = False
            lines = content.split('\n')
            if len(lines) > 1:  # Mindestens Header + 1 Datenzeile
                first_data_line = lines[1] if lines[0].startswith('"') or ',' in lines[0] else lines[0]
                if first_data_line.strip().startswith('"'):
                    timestamp_has_quotes = True
            
            # Ersetze "NAN" Strings
            content = content.replace('"NAN"', 'NaN')
            content = content.replace("'NAN'", 'NaN')
            
            # Schritt 2: Parse mit pandas für Spalten-Operationen
            # Lese aus dem geänderten Content
            from io import StringIO
            try:
                df = pd.read_csv(StringIO(content), header=0, low_memory=False, dtype=str, keep_default_na=False)
                has_header = True
            except:
                df = pd.read_csv(StringIO(content), header=None, low_memory=False, dtype=str, keep_default_na=False)
                has_header = False
            
            # Entferne Anführungszeichen aus Timestamp-Spalte für pandas-Verarbeitung
            if timestamp_has_quotes and len(df.columns) > 0:
                first_col = df.columns[0]
                df[first_col] = df[first_col].astype(str).str.strip('"')
            
            # Setze original_df für späteren Vergleich (vor Spalten-Operationen)
            original_df = df.copy()
        else:
            # Kein CSV: Textdatei, nur String-Ersetzung
            df = None
            has_header = False
            timestamp_has_quotes = False
        
        # 1. String-Ersetzung: "NAN" → NaN
        # (Für CSV-Dateien wird dies bereits oben im Text-Modus gemacht)
        # Wenn df vorhanden ist (nur bei ENABLE_COLUMN_2_4_NAN), wurde "NAN" bereits ersetzt
        if df is not None:
            # original_df wurde bereits oben gesetzt wenn ENABLE_COLUMN_2_4_NAN aktiviert ist
            # Falls nicht, setze es jetzt
            if 'original_df' not in locals():
                original_df = df.copy()
            
            # Erkenne Station aus Dateipfad oder verwende übergebenen Wert
            if station is None:
                station = detect_station(file_path)
            
            invalid_count = 0
            janga_mole_count = 0
            
            if ENABLE_COLUMN_2_4_NAN and len(df.columns) > 5:
                col_idx_6 = 5  # 6. Spalte (0-basiert)
                col_name_6 = df.columns[col_idx_6]
                
                # Konvertiere Spalte 6 zu numerisch
                df[col_name_6] = pd.to_numeric(df[col_name_6], errors='coerce')
                
                if station in ['Janga', 'Mole']:
                    # Für Janga/Mole: Setze Spalten 2-4 auf NaN, wenn Spalte 6 > 0
                    mask_janga_mole = (df[col_name_6] > 0) & (df[col_name_6].notna())
                    janga_mole_count = mask_janga_mole.sum()
                    
                    if janga_mole_count > 0:
                        if len(df.columns) > 3:
                            cols_to_set_nan = df.columns[1:4]  # Spalten 2-4 (Indizes 1, 2, 3)
                            
                            if dry_run:
                                print(f"    [Station {station}] {janga_mole_count} Werte > 0 in Spalte 6 gefunden")
                                print(f"    → {len(cols_to_set_nan)} Werte in Spalten 2-4 würden auf NaN gesetzt")
                            else:
                                # Setze Spalten 2-4 auf NaN für Zeilen mit Werten > 0 in Spalte 6
                                for col in cols_to_set_nan:
                                    df.loc[mask_janga_mole, col] = np.nan
                else:
                    # Für alle anderen Stationen: Setze Spalten 2-4 auf NaN, wenn Spalte 6 < 0 oder > 63
                    mask = (df[col_name_6] < 0) | (df[col_name_6] > 63) | (df[col_name_6].isna())
                    invalid_count = mask.sum()
                    
                    if invalid_count > 0:
                        if len(df.columns) > 3:
                            cols_to_set_nan = df.columns[1:4]  # Spalten 2-4 (Indizes 1, 2, 3)
                            
                            if dry_run:
                                print(f"    [Station {station}] {invalid_count} ungültige Werte in Spalte 6 gefunden (< 0 oder > 63)")
                                print(f"    → {len(cols_to_set_nan)} Werte in Spalten 2-4 würden auf NaN gesetzt")
                            else:
                                # Setze Spalten 2-4 auf NaN für Zeilen mit ungültigen Werten in Spalte 6
                                for col in cols_to_set_nan:
                                    df.loc[mask, col] = np.nan
            
            # Prüfe ob Änderungen vorgenommen wurden
            # original_content wurde oben im elif-Block gesetzt (wenn ENABLE_COLUMN_2_4_NAN aktiviert)
            if 'original_content' in locals():
                string_changes = original_content.count('"NAN"') + original_content.count("'NAN'")
            else:
                # Fallback: zähle im DataFrame (sollte nicht vorkommen, da df nur bei ENABLE_COLUMN_2_4_NAN gesetzt wird)
                string_changes = 0
                for col in original_df.columns:
                    string_changes += original_df[col].astype(str).str.contains('"NAN"', regex=False, na=False).sum()
                    string_changes += original_df[col].astype(str).str.contains("'NAN'", regex=False, na=False).sum()
            
            # Prüfe ob sich DataFrames unterscheiden (nach String-Ersetzung und Spalten 2-4)
            # invalid_count > 0 oder janga_mole_count > 0 bedeutet, dass Werte in Spalten 2-4 geändert werden
            # Vergleiche auch ob Spalten 2-4 geändert wurden
            cols_changed = False
            if (invalid_count > 0 or janga_mole_count > 0) and len(df.columns) > 3:
                cols_to_check = df.columns[1:4]
                for col in cols_to_check:
                    if not df[col].equals(original_df[col]):
                        cols_changed = True
                        break
            
            has_changes = string_changes > 0 or cols_changed
            
            if has_changes:
                if dry_run:
                    print(f"  [DRY RUN] {file_path.name}: Änderungen gefunden")
                    if invalid_count > 0:
                        if len(df.columns) > 3:
                            cols_count = len(df.columns[1:4])
                            total_set = invalid_count * cols_count
                            print(f"            → {invalid_count} ungültige Werte in Spalte 6 gefunden")
                            print(f"            → {total_set} Werte in Spalten 2-4 würden auf NaN gesetzt")
                    if janga_mole_count > 0:
                        if len(df.columns) > 3:
                            cols_count = len(df.columns[1:4])
                            total_set = janga_mole_count * cols_count
                            print(f"            → {janga_mole_count} Werte > 0 in Spalte 6 gefunden (Station {station})")
                            print(f"            → {total_set} Werte in Spalten 2-4 würden auf NaN gesetzt")
                    if string_changes > 0:
                        print(f"            → {string_changes} 'NAN' Strings würden ersetzt")
                else:
                    # Datei schreiben
                    # Schreibe zurück, aber nur Timestamp-Spalte mit Anführungszeichen
                    # Verwende quoting=0 (QUOTE_MINIMAL) und füge Anführungszeichen manuell um Timestamp hinzu
                    output_lines = []
                    
                    if has_header:
                        # Header schreiben
                        header = df.columns.tolist()
                        if timestamp_has_quotes:
                            header[0] = f'"{header[0]}"'
                        output_lines.append(','.join(header))
                    
                    # Daten schreiben
                    for idx, row in df.iterrows():
                        row_values = []
                        for i, val in enumerate(row):
                            val_str = str(val) if pd.notna(val) else 'NaN'
                            # Nur erste Spalte (Timestamp) mit Anführungszeichen, wenn ursprünglich vorhanden
                            if i == 0 and timestamp_has_quotes:
                                row_values.append(f'"{val_str}"')
                            else:
                                # Keine Anführungszeichen für andere Spalten
                                row_values.append(val_str)
                        output_lines.append(','.join(row_values))
                    
                    # Schreibe zurück
                    target_path = output_path if output_path is not None else file_path
                    # Stelle sicher, dass das Ausgabeverzeichnis existiert
                    if output_path is not None:
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(target_path, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(output_lines))
                    
                    changes_str = []
                    if invalid_count > 0:
                        # Zähle wie viele Werte tatsächlich gesetzt wurden
                        if len(df.columns) > 3:
                            cols_count = len(df.columns[1:4])
                            total_set = invalid_count * cols_count
                            changes_str.append(f"{total_set} Werte in Spalten 2-4 gesetzt (bei {invalid_count} ungültigen Werten in Spalte 6)")
                    if janga_mole_count > 0:
                        if len(df.columns) > 3:
                            cols_count = len(df.columns[1:4])
                            total_set = janga_mole_count * cols_count
                            changes_str.append(f"{total_set} Werte in Spalten 2-4 gesetzt (bei {janga_mole_count} Werten > 0 in Spalte 6, Station {station})")
                    if string_changes > 0:
                        changes_str.append(f"{string_changes} 'NAN' Strings ersetzt")
                    
                    if changes_str:
                        print(f"  ✓ {file_path.name}: {', '.join(changes_str)}")
                    else:
                        print(f"  ✓ {file_path.name}: Änderungen durchgeführt")
                return True
            else:
                return False
        else:
            # Textdatei ohne CSV-Format: Nur String-Ersetzung
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            
            # Ersetze "NAN" (mit Anführungszeichen) durch NaN (ohne Anführungszeichen)
            replacements = [
                ('"NAN"', 'NaN'),
                ("'NAN'", 'NaN'),
                ('"NAN",', 'NaN,'),
                ("'NAN',", 'NaN,'),
                (',"NAN"', ',NaN'),
                (",'NAN'", ',NaN'),
            ]
            
            for old, new in replacements:
                content = content.replace(old, new)
            
            content = re.sub(r'"NAN"(\s*)$', r'NaN\1', content, flags=re.MULTILINE)
            content = re.sub(r"'NAN'(\s*)$", r'NaN\1', content, flags=re.MULTILINE)
            
            if content != original_content:
                changes = original_content.count('"NAN"') + original_content.count("'NAN'")
                if dry_run:
                    print(f"  [DRY RUN] {file_path.name}: {changes} Ersetzungen gefunden")
                else:
                    target_path = output_path if output_path is not None else file_path
                    # Stelle sicher, dass das Ausgabeverzeichnis existiert
                    if output_path is not None:
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(target_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    print(f"  ✓ {file_path.name}: {changes} 'NAN' Strings ersetzt")
                return True
            else:
                return False
            
    except Exception as e:
        print(f"  ⚠️ Fehler bei {file_path.name}: {e}")
        import traceback
        if dry_run:
            traceback.print_exc()
        return False


def process_directory(directory: Path, file_extensions: list = None, dry_run: bool = False, 
                     output_directory: Path = None, station: str = None):
    """
    Verarbeitet alle Dateien in einem Ordner.
    
    Args:
        directory: Eingabe-Ordnerpfad
        file_extensions: Liste von Dateiendungen (z.B. ['.csv', '.dat']). 
                        Wenn None, werden alle Dateien verarbeitet.
        dry_run: Wenn True, werden keine Änderungen vorgenommen
        output_directory: Optionaler Ausgabe-Ordnerpfad. Wenn None, werden Dateien im Eingabeordner überschrieben.
        station: Optionaler Stationsname. Wenn None, wird er aus dem Dateipfad erkannt.
    """
    if not directory.exists():
        print(f"❌ Ordner existiert nicht: {directory}")
        return
    
    if not directory.is_dir():
        print(f"❌ Kein Ordner: {directory}")
        return
    
    print(f"📁 Verarbeite Ordner: {directory}")
    if dry_run:
        print("   [DRY RUN Modus - keine Änderungen werden vorgenommen]")
    print()
    
    # Finde alle Dateien
    if file_extensions:
        files = []
        for ext in file_extensions:
            files.extend(directory.glob(f"*{ext}"))
    else:
        files = list(directory.glob("*"))
        # Nur Dateien, keine Ordner
        files = [f for f in files if f.is_file()]
    
    if not files:
        print("  ⚠️ Keine Dateien gefunden")
        return
    
    print(f"  Gefunden: {len(files)} Dateien")
    print()
    
    # Verarbeite jede Datei
    modified_count = 0
    for file_path in sorted(files):
        # Bestimme Ausgabepfad
        if output_directory is not None:
            output_path = output_directory / file_path.name
        else:
            output_path = None
        
        if replace_nan_in_file(file_path, dry_run=dry_run, output_path=output_path, station=station):
            modified_count += 1
    
    print()
    if dry_run:
        print(f"📊 [DRY RUN] {modified_count} Dateien würden geändert werden")
    else:
        print(f"✅ {modified_count} Dateien wurden geändert")


def main():
    """Hauptfunktion."""
    # Interaktive Eingabe
    print("=" * 60)
    print("replace_nan_strings.py - Interaktive Eingabe")
    print("=" * 60)
    print()
    
    # Station abfragen
    station_input = input("Station (Janga/Mole/Gorigo/Kayoro/Nazinga) [leer lassen für Auto-Erkennung]: ").strip()
    station = station_input.capitalize() if station_input else None
    
    # Input-Pfad abfragen
    input_path_str = input("Input-Pfad (Ordner mit Dateien): ").strip()
    if not input_path_str:
        print("❌ Input-Pfad ist erforderlich!")
        sys.exit(1)
    input_directory = Path(input_path_str)
    
    # Output-Pfad abfragen (optional)
    output_path_str = input("Output-Pfad [leer lassen um Dateien direkt zu ändern]: ").strip()
    output_directory = Path(output_path_str) if output_path_str else None
    
    # Dry-run abfragen
    dry_run_input = input("Dry-run Modus? (j/n) [n]: ").strip().lower()
    dry_run = dry_run_input in ['j', 'ja', 'y', 'yes']
    
    # Dateiendungen abfragen (optional)
    extensions_input = input("Dateiendungen (z.B. .csv .dat) [leer lassen für alle]: ").strip()
    file_extensions = extensions_input.split() if extensions_input else None
    
    print()
    print("=" * 60)
    print("Zusammenfassung:")
    print(f"  Station: {station if station else 'Auto-Erkennung'}")
    print(f"  Input-Pfad: {input_directory}")
    print(f"  Output-Pfad: {output_directory if output_directory else 'Dateien werden direkt geändert'}")
    print(f"  Dry-run: {'Ja' if dry_run else 'Nein'}")
    print(f"  Dateiendungen: {file_extensions if file_extensions else 'Alle'}")
    print("=" * 60)
    print()
    
    # Bestätigung
    if not dry_run:
        confirm = input("Fortfahren? (j/n) [j]: ").strip().lower()
        if confirm and confirm not in ['j', 'ja', 'y', 'yes']:
            print("Abgebrochen.")
            sys.exit(0)
        print()
    
    # Verarbeite Ordner
    process_directory(input_directory, file_extensions=file_extensions, dry_run=dry_run,
                     output_directory=output_directory, station=station)


if __name__ == "__main__":
    main()
