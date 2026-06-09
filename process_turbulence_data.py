#!/usr/bin/env python3
"""
Skript zur Verarbeitung von Turbulenz-Rohdaten:
- Aufteilen in halbstündliche Dateien
- Umbenennen im Format: Station_yy_doY_HHMM.dat
- Entfernen von NaN-Werten
- Entfernen der Timestamp-Spalte
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import glob
import os
import csv


def read_turbulence_file(file_path: Path) -> pd.DataFrame:
    """
    Liest eine Turbulenz-Datei ohne Header.
    Erste Spalte ist der Timestamp.
    """
    try:
        # Lese CSV ohne Header, erste Spalte ist Timestamp
        # Verwende quotechar='"' um Anführungszeichen richtig zu behandeln
        df = pd.read_csv(
            file_path,
            header=None,
            quotechar='"',
            na_values=["NAN", "NA", "nan", "NaN", "", "-9999", "N/A"],
            on_bad_lines='skip',
            engine='python'  # Python-Engine für besseres Handling von trailing commas
        )

        if df.empty:
            return pd.DataFrame()

        # Parse erste Spalte als Datetime
        # WICHTIG: pd.to_datetime kann Timestamps mit Nachkommastellen (z.B. 10 Hz) parsen
        # Format: "2023-02-20 03:00:00.0", "2023-02-20 03:00:00.1", etc. werden korrekt erkannt
        if len(df.columns) > 0:
            # Entferne Anführungszeichen falls vorhanden
            timestamp_str = df.iloc[:, 0].astype(str).str.strip().str.strip('"').str.strip("'")
            # Verwende format='mixed' damit pd.to_datetime automatisch verschiedene Formate erkennt
            df.iloc[:, 0] = pd.to_datetime(timestamp_str, errors='coerce', format='mixed')
            df = df.set_index(df.columns[0])
            df.index.name = 'Timestamp'

        # Entferne Zeilen mit ungültigen Timestamps
        df = df[df.index.notna()]

        # Entferne leere Spalten (durch trailing comma)
        # Filtere Spalten die komplett leer sind oder nur NaN enthalten
        df = df.dropna(axis=1, how='all')
        df = df.loc[:, df.columns.notna()]

        # Entferne Spalten die nur leere Strings enthalten
        for col in df.columns:
            if df[col].dtype == 'object':
                non_empty = df[col].astype(str).str.strip().ne('')
                if non_empty.sum() == 0:
                    df = df.drop(columns=[col])

        return df

    except Exception as e:
        print(f"  ⚠️ Fehler beim Lesen von {file_path.name}: {e}")
        return pd.DataFrame()


def process_file_in_chunks(file_path: Path, output_dir: Path, station: str, chunk_size: int = 100000):
    """
    Verarbeitet eine Datei in Chunks und schreibt direkt in halbstündliche Ausgabedateien.
    WICHTIG: Mehrere Eingabedateien für denselben 30-Minuten-Zeitraum werden kombiniert.
    """
    try:
        # Bestimme zuerst die Anzahl der Spalten aus der ersten Zeile
        # um sicherzustellen, dass alle Spalten erkannt werden
        with open(file_path, 'r', encoding='utf-8') as f:
            first_line = f.readline().rstrip('\n\r')
            # Zähle Kommas (auch trailing comma wird gezählt)
            n_cols_expected = first_line.count(',') + 1

        # Lese Datei in Chunks mit expliziter Spaltenanzahl
        # Verwende usecols nicht, damit alle Spalten gelesen werden
        chunk_reader = pd.read_csv(
            file_path,
            header=None,
            quotechar='"',
            na_values=["NAN", "NA", "nan", "NaN", "", "-9999", "-Inf", "N/A"],
            on_bad_lines='skip',
            engine='python',
            chunksize=chunk_size,
            names=list(range(n_cols_expected)),  # Explizite Spaltennamen um alle Spalten zu behalten
            dtype=str  # Lese alles als String um keine Daten zu verlieren
        )

        total_rows = 0
        # Sammle alle Daten aus dieser Datei, um sie dann nach 30-Min-Intervallen zu gruppieren
        all_chunks = []

        for chunk_df in chunk_reader:
            if chunk_df.empty:
                continue

            # Debug: Zeige Anzahl der Spalten beim Lesen
            n_cols_before = len(chunk_df.columns)

            # Parse erste Spalte als Datetime
            if len(chunk_df.columns) > 0:
                # Konvertiere erste Spalte zu Datetime
                # WICHTIG: pd.to_datetime kann Timestamps mit Nachkommastellen (z.B. 10 Hz) parsen
                # Format: "2023-02-20 03:00:00.05" wird korrekt erkannt
                # Entferne Anführungszeichen falls vorhanden
                timestamp_str = chunk_df.iloc[:, 0].astype(str).str.strip().str.strip('"').str.strip("'")
                timestamp_col = pd.to_datetime(timestamp_str, errors='coerce')
                # Behalte ALLE anderen Spalten (Spalte 1 bis Ende)
                data_cols = chunk_df.iloc[:, 1:].copy()
                # Setze Timestamp als Index
                data_cols.index = timestamp_col
                data_cols.index.name = 'Timestamp'
                chunk_df = data_cols

            # Entferne Zeilen mit ungültigen Timestamps
            chunk_df = chunk_df[chunk_df.index.notna()]

            if chunk_df.empty:
                continue

            # Debug: Zeige Timestamp-Bereich (nur beim ersten Chunk)
            if total_rows == 0 and len(chunk_df) > 0:
                print(f"  Timestamp-Bereich: {chunk_df.index.min()} → {chunk_df.index.max()}")
                print(f"  Beispiel-Timestamps: {chunk_df.index[:3].tolist()}")

            # BEHALTE ALLE SPALTEN - entferne nur wirklich komplett leere Spalten am Ende
            # (durch trailing comma verursacht)
            # Entferne nur Spalten die komplett leer sind UND am Ende stehen
            #while len(chunk_df.columns) > 0:
            #    last_col = chunk_df.iloc[:, -1]
            #    # Prüfe ob letzte Spalte komplett leer ist (alle NaN oder leere Strings)
            #    if last_col.isna().all() or (last_col.astype(str).str.strip() == '').all():
            #        chunk_df = chunk_df.iloc[:, :-1]
            #    else:
            #        break

            # Debug: Zeige Anzahl der Spalten nach Verarbeitung
            n_cols_after = len(chunk_df.columns)
            if n_cols_before != n_cols_after + 1:  # +1 weil Timestamp entfernt wurde
                print(f"  ⚠️ Warnung: Spaltenanzahl geändert von {n_cols_before} auf {n_cols_after} (+ Timestamp)")

            # Sammle Chunk für spätere Gruppierung
            all_chunks.append(chunk_df)
            total_rows += len(chunk_df)

        # Kombiniere alle Chunks dieser Datei
        if not all_chunks:
            return total_rows

        combined_df = pd.concat(all_chunks, axis=0)
        combined_df = combined_df.sort_index()

        # Entferne Duplikate im Index (falls vorhanden)
        if combined_df.index.duplicated().any():
            combined_df = combined_df[~combined_df.index.duplicated(keep='first')]

        # Gruppiere nach halbstündlichen Intervallen
        # WICHTIG: floor('30min') funktioniert auch mit Timestamps die Nachkommastellen haben
        # z.B. "2023-02-20 03:00:00.05" wird zu "2023-02-20 03:00:00" gerundet
        # und dann zu "2023-02-20 03:00:00" (30-Minuten-Intervall) gefloor'd
        combined_df['time_group'] = combined_df.index.floor('30min')
        grouped = combined_df.groupby('time_group')

        # Debug: Zeige Informationen über die Gruppierung
        n_groups = len(grouped)
        print(f"  Datei {file_path.name}: {len(combined_df)} Zeilen → {n_groups} 30-Min-Intervalle")
        if n_groups > 0:
            for i, (time_group, group_df) in enumerate(list(grouped)[:3]):  # Zeige erste 3 Gruppen
                group_size = len(group_df)
                time_span = group_df.index.max() - group_df.index.min()
                print(f"    Intervall {i+1}: {time_group} → {group_size} Zeilen (Spanne: {time_span})")
                # Prüfe ob es 30 Minuten sind (bei 10 Hz = 18000 Zeilen)
                expected_30min = 10 * 60 * 30  # 18000
                if group_size < expected_30min:
                    print(f"      ⚠️ WARNUNG: Nur {group_size} Zeilen, erwartet {expected_30min} für 30 Min bei 10 Hz")
                    print(f"      → Das entspricht nur {group_size / (10 * 60):.1f} Minuten")

        for time_group, group_df in grouped:
            # Entferne time_group Spalte
            group_df = group_df.drop(columns=['time_group'], errors='ignore')

            # Entferne Zeilen mit NaN-Werten
            group_df = group_df.dropna()

            if group_df.empty:
                continue

            # Generiere Dateinamen
            year_short = time_group.strftime('%y')
            day_of_year = time_group.strftime('%j')
            hour_minute = time_group.strftime('%H%M')
            filename = f"{station}_{year_short}_{day_of_year}_{hour_minute}.dat"
            output_path = output_dir / filename

            # Bestimme Modus: 'a' wenn Datei existiert, 'w' wenn nicht
            # Dies ermöglicht, dass mehrere Eingabedateien Daten für denselben Zeitraum hinzufügen
            mode = 'a' if output_path.exists() else 'w'

            # Debug: Zeige wenn Datei angehängt wird
            if mode == 'a':
                existing_lines = sum(1 for _ in open(output_path, 'r')) if output_path.exists() else 0
                print(f"      → Hänge {len(group_df)} Zeilen an bestehende Datei ({existing_lines} Zeilen bereits vorhanden)")

            # Schreibe Daten (ohne Index, ohne Header, ohne Anführungszeichen)
            # Schreibe direkt ohne CSV-Formatierung um Anführungszeichen zu vermeiden
            with open(output_path, mode, encoding='utf-8') as f:
                for _, row in group_df.iterrows():
                    # Konvertiere Werte zu Strings und formatiere Floats
                    # WICHTIG: Verwende row.values um ALLE Spalten zu bekommen
                    row_values = []
                    for val in row.values:
                        if pd.isna(val):
                            row_values.append('')
                        elif isinstance(val, (int, float, np.integer, np.floating)):
                            row_values.append(f'{val:.7g}')
                        else:
                            val_str = str(val).strip()
                            row_values.append(val_str)
                    # Schreibe als komma-separierte Zeile ohne Anführungszeichen
                    # Stelle sicher, dass alle Spalten geschrieben werden
                    f.write(','.join(row_values) + '\n')

        return total_rows

    except Exception as e:
        print(f"  ⚠️ Fehler beim Verarbeiten von {file_path.name}: {e}")
        return 0


def clean_output_files(output_dir: Path):
    """
    Bereinigt alle Ausgabedateien: entfernt NaN-Zeilen und Duplikate.
    Wird am Ende aufgerufen, um finale Bereinigung durchzuführen.
    """
    print("\n🧹 Finale Bereinigung der Ausgabedateien...")

    output_files = sorted(output_dir.glob("*.dat"))

    if not output_files:
        return

    cleaned_count = 0

    for output_path in output_files:
        try:
            # Lese Datei - bestimme zuerst die Anzahl der Spalten aus der ersten Zeile
            # um sicherzustellen, dass alle Spalten erkannt werden
            with open(output_path, 'r', encoding='utf-8') as f:
                first_line = f.readline().rstrip('\n\r')
                n_cols_expected = first_line.count(',') + 1

            # Lese Datei mit expliziter Spaltenanzahl
            df = pd.read_csv(
                output_path,
                header=None,
                na_values=["NAN", "NA", "nan", "NaN", "", "-9999", "N/A"],
                engine='python',
                on_bad_lines='skip',
                names=list(range(n_cols_expected)),  # Explizite Spaltennamen um alle Spalten zu behalten
                dtype=str  # Lese alles als String um keine Daten zu verlieren
            )

            if df.empty:
                output_path.unlink()  # Lösche leere Dateien
                continue

            # Entferne nur Zeilen wo ALLE Werte NaN sind (nicht Zeilen mit einzelnen NaN-Werten)
            # Dies behält alle Spalten bei
            df = df.dropna(how='all')

            if df.empty:
                output_path.unlink()  # Lösche leere Dateien
                continue

            # Entferne Duplikate (falls vorhanden)
            df = df.drop_duplicates()

            # Schreibe bereinigte Datei zurück (ohne Anführungszeichen, ohne Timestamp-Spalte)
            # Schreibe direkt ohne CSV-Formatierung um Anführungszeichen zu vermeiden
            with open(output_path, 'w', encoding='utf-8') as f:
                for _, row in df.iterrows():
                    # Konvertiere Werte zu Strings und formatiere Floats
                    # BEHALTE ALLE SPALTEN (KEIN Timestamp) - verwende row.values um alle Spalten zu bekommen
                    row_values = []
                    for val in row.values:
                        if pd.isna(val):
                            row_values.append('')
                        elif isinstance(val, (int, float, np.integer, np.floating)):
                            row_values.append(f'{val:.7g}')
                        else:
                            val_str = str(val).strip()
                            row_values.append(val_str)
                    # Schreibe als komma-separierte Zeile ohne Anführungszeichen
                    # Stelle sicher, dass alle Spalten geschrieben werden (OHNE Timestamp)
                    f.write(','.join(row_values) + '\n')

            cleaned_count += 1
            if cleaned_count % 100 == 0:
                print(f"  ✓ {cleaned_count} Dateien bereinigt...")

        except Exception as e:
            print(f"  ⚠️ Fehler beim Bereinigen von {output_path.name}: {e}")
            continue

    print(f"  ✅ {cleaned_count} Dateien bereinigt")


def split_into_30min_files(input_dir: Path, output_dir: Path, station: str):
    """
    Liest alle .dat Dateien im Input-Ordner, teilt sie in halbstündliche
    Dateien auf und speichert sie im Output-Ordner.
    WICHTIG: Verarbeitet Datei für Datei und schreibt sofort, um Speicherprobleme zu vermeiden.
    30-Minuten-Blöcke basierend auf Zeitstempel:
    - Block 1: HH:00:00.0 bis HH:29:59.9
    - Block 2: HH:30:00.0 bis HH:59:59.9
    """
    # Erstelle Output-Ordner falls nicht vorhanden
    output_dir.mkdir(parents=True, exist_ok=True)

    # Finde alle .dat Dateien
    dat_files = sorted(input_dir.glob("*.dat"))

    if not dat_files:
        print(f"❌ Keine .dat Dateien gefunden in {input_dir}")
        return

    print(f"📁 Gefunden: {len(dat_files)} Dateien")
    print(f"📂 Input: {input_dir}")
    print(f"📂 Output: {output_dir}")
    print(f"🏢 Station: {station}\n")

    # Verarbeite jede Datei einzeln und schreibe sofort
    print("📥 Verarbeite Dateien einzeln...")
    files_processed = 0
    files_skipped = 0
    total_rows_processed = 0

    for i, file_path in enumerate(dat_files, 1):
        if i % 100 == 0:
            print(f"  [{i}/{len(dat_files)}] Dateien verarbeitet...")

        try:
            # Bestimme Spaltenanzahl
            with open(file_path, 'r', encoding='utf-8') as f:
                first_line = f.readline().rstrip('\n\r')
                n_cols_expected = first_line.count(',') + 1

            # Lese Datei in Chunks um Speicher zu sparen
            chunk_reader = pd.read_csv(
                file_path,
                header=None,
                quotechar='"',
                na_values=["NAN", "NA", "nan", "NaN", "", "-9999", "N/A"],
                on_bad_lines='skip',
                engine='python',
                chunksize=50000,  # Verarbeite in Chunks
                names=list(range(n_cols_expected)),
                dtype=str
            )

            file_rows = 0

            for chunk_df in chunk_reader:
                if chunk_df.empty:
                    continue

                # Parse Timestamp
                # WICHTIG: Bei 10 Hz haben Timestamps Nachkommastellen in den Sekunden
                # z.B. "2023-05-28 02:59:50.0", "2023-05-28 02:59:50.1", etc.
                # pd.to_datetime muss diese korrekt parsen können
                timestamp_str = chunk_df.iloc[:, 0].astype(str).str.strip().str.strip('"').str.strip("'")

                # Debug: Zeige Beispiel-Timestamps (nur beim ersten Chunk der ersten Datei)
                if i == 1 and file_rows == 0 and len(timestamp_str) > 0:
                    print(f"    Beispiel-Timestamps aus Datei:")
                    for j, ts_example in enumerate(timestamp_str.head(10), 1):
                        print(f"      {j}. {ts_example}")

                # Verwende format='mixed', damit pd.to_datetime automatisch verschiedene Formate erkennt
                # inklusive Timestamps mit Nachkommastellen
                timestamp_col = pd.to_datetime(timestamp_str, errors='coerce', format='mixed')

                # Debug: Prüfe ob Nachkommastellen erhalten bleiben (nur beim ersten Chunk)
                if i == 1 and file_rows == 0:
                    valid_timestamps = timestamp_col[timestamp_col.notna()]
                    if len(valid_timestamps) > 0:
                        # Prüfe ob Mikrosekunden vorhanden sind
                        has_microseconds = (valid_timestamps.microsecond > 0).any()
                        unique_microseconds = valid_timestamps.microsecond.unique()
                        print(f"    Parsing-Ergebnis: {len(valid_timestamps)} gültige Timestamps")
                        print(f"    Mikrosekunden vorhanden: {has_microseconds}")
                        if has_microseconds:
                            print(f"    Einzigartige Mikrosekunden-Werte: {sorted(unique_microseconds)[:10]}")
                        # Zeige Beispiel-formatierte Timestamps
                        print(f"    Beispiel formatierte Timestamps:")
                        for ts_ex in valid_timestamps.head(5):
                            decimal = int(ts_ex.microsecond / 100000)
                            formatted = ts_ex.strftime('%Y-%m-%d %H:%M:%S') + f'.{decimal}'
                            print(f"      {formatted} (microsecond={ts_ex.microsecond})")

                # Behalte Daten-Spalten
                data_cols = chunk_df.iloc[:, 1:].copy()
                data_cols.index = timestamp_col
                data_cols.index.name = 'Timestamp'

                # Entferne ungültige Timestamps
                data_cols = data_cols[data_cols.index.notna()]

                if data_cols.empty:
                    continue

                # Sortiere nach Zeitstempel (wichtig für korrekte Gruppierung)
                data_cols = data_cols.sort_index()

                # Gruppiere nach 30-Minuten-Intervallen
                # WICHTIG: floor('30min') rundet auf das nächste 30-Minuten-Intervall ab
                # z.B. 03:00:00.0 bis 03:29:59.9 → 03:00:00
                #      03:30:00.0 bis 03:59:59.9 → 03:30:00
                data_cols['time_group'] = data_cols.index.floor('30min')
                grouped = data_cols.groupby('time_group')

                # Debug: Prüfe ob Gruppierung korrekt ist (nur bei ersten Chunks)
                if i == 1 and file_rows == 0:
                    # Prüfe ob es 15-Minuten-Intervalle gibt (falsch)
                    data_cols_15min = data_cols.index.floor('15min')
                    unique_15min = data_cols_15min.unique()
                    unique_30min = data_cols['time_group'].unique()
                    if len(unique_15min) > len(unique_30min):
                        print(f"    ⚠️ WARNUNG: Möglicherweise werden 15-Min-Intervalle erstellt statt 30-Min!")
                        print(f"      15-Min-Intervalle: {len(unique_15min)}, 30-Min-Intervalle: {len(unique_30min)}")

                # Debug: Zeige detaillierte Informationen (nur bei ersten Chunks der ersten Dateien)
                if i == 1 and file_rows == 0:
                    print(f"  Beispiel: {file_path.name}")
                    print(f"    Timestamp-Bereich: {data_cols.index.min()} → {data_cols.index.max()}")
                    print(f"    Zeilen in diesem Chunk: {len(data_cols)}")
                    print(f"    Gefundene 30-Min-Intervalle: {len(grouped)}")
                    for tg, gdf in list(grouped)[:5]:
                        time_span = gdf.index.max() - gdf.index.min()
                        duration_sec = time_span.total_seconds()
                        duration_min = duration_sec / 60
                        print(f"      Intervall {tg}: {len(gdf)} Zeilen, {gdf.index.min()} → {gdf.index.max()} (~{duration_min:.2f} Min)")
                        # Prüfe ob es genau 30 Minuten sind
                        expected_30min = 10 * 60 * 30  # 18000 bei 10 Hz
                        if len(gdf) < expected_30min:
                            print(f"        ⚠️ WARNUNG: Nur {len(gdf)} Zeilen statt {expected_30min} (fehlen {expected_30min - len(gdf)} Zeilen)")

                # Schreibe sofort in entsprechende Ausgabedateien
                for time_group, group_df in grouped:
                    # Entferne time_group Spalte
                    group_df = group_df.drop(columns=['time_group'], errors='ignore')

                    # Entferne Zeilen mit NaN-Werten
                    group_df = group_df.dropna()

                    if group_df.empty:
                        continue

                    # Generiere Dateinamen
                    year_short = time_group.strftime('%y')
                    day_of_year = time_group.strftime('%j')
                    hour_minute = time_group.strftime('%H%M')
                    filename = f"{station}_{year_short}_{day_of_year}_{hour_minute}.dat"
                    output_path = output_dir / filename

                    # Bestimme Modus: 'a' wenn Datei existiert, 'w' wenn nicht
                    mode = 'a' if output_path.exists() else 'w'

                    # Debug: Zeige detaillierte Informationen (nur bei ersten Schreibvorgängen)
                    if i <= 3 and file_rows < 100000:
                        time_span = group_df.index.max() - group_df.index.min()
                        duration_sec = time_span.total_seconds()
                        duration_min = duration_sec / 60
                        expected_30min = 10 * 60 * 30  # 18000 bei 10 Hz
                        mode_str = "ANHÄNGEN" if mode == 'a' else "NEU ERSTELLEN"
                        print(f"      → {filename}: {len(group_df)} Zeilen, {mode_str}, Zeitraum: {group_df.index.min()} → {group_df.index.max()} (~{duration_min:.2f} Min)")
                        if mode == 'a':
                            try:
                                with open(output_path, 'r') as check_f:
                                    existing = sum(1 for _ in check_f)
                                print(f"        (Bestehende Datei: {existing} Zeilen → Gesamt nach Anhängen: {existing + len(group_df)} Zeilen)")
                            except:
                                pass
                        if len(group_df) < expected_30min:
                            print(f"        ⚠️ WARNUNG: Nur {len(group_df)} Zeilen statt {expected_30min} (fehlen {expected_30min - len(group_df)} Zeilen)")

                    # Schreibe Daten SOFORT (ohne Buffering für sofortiges Schreiben)
                    # WICHTIG: Timestamp-Spalte wird NICHT geschrieben (nur für Gruppierung verwendet)
                    with open(output_path, mode, encoding='utf-8', buffering=1) as f:  # Line buffering
                        for idx, row in group_df.iterrows():
                            row_values = []
                            # Schreibe NUR die Daten-Spalten (KEIN Timestamp)
                            for val in row.values:
                                if pd.isna(val):
                                    row_values.append('')
                                elif isinstance(val, (int, float, np.integer, np.floating)):
                                    row_values.append(f'{val:.7g}')
                                else:
                                    val_str = str(val).strip()
                                    row_values.append(val_str)
                            f.write(','.join(row_values) + '\n')
                        f.flush()  # Stelle sicher, dass Daten sofort geschrieben werden

                file_rows += len(data_cols)

            # Debug: Zeige Zusammenfassung für diese Datei (nur bei ersten Dateien)
            if i <= 5:
                print(f"  Datei {i}: {file_path.name} → {file_rows:,} Zeilen verarbeitet")

            if file_rows > 0:
                files_processed += 1
                total_rows_processed += file_rows
            else:
                files_skipped += 1

        except Exception as e:
            print(f"  ⚠️ Fehler bei {file_path.name}: {e}")
            files_skipped += 1
            continue

    print(f"\n📊 Zusammenfassung:")
    print(f"  ✅ Verarbeitet: {files_processed} Dateien")
    print(f"  ⚠️ Übersprungen: {files_skipped} Dateien")
    print(f"  📝 Gesamt: {total_rows_processed:,} Zeilen")

    # Prüfe Ausgabedateien auf korrekte Größe
    print(f"\n🔍 Prüfe Ausgabedateien...")
    output_files = sorted(output_dir.glob("*.dat"))
    expected_30min = 20 * 60 * 30  # 36000 bei 20 Hz

    files_too_small = []
    for output_path in output_files[:10]:  # Prüfe erste 10 Dateien
        try:
            with open(output_path, 'r') as f:
                line_count = sum(1 for _ in f)

            if line_count < expected_30min:
                files_too_small.append((output_path.name, line_count))
        except Exception as e:
            print(f"    ⚠️ Fehler beim Prüfen von {output_path.name}: {e}")

    if files_too_small:
        print(f"  ⚠️ {len(files_too_small)} Dateien haben weniger als {expected_30min} Zeilen:")
        for name, count in files_too_small[:5]:
            duration = count / (10 * 60)
            print(f"    {name}: {count} Zeilen (~{duration:.1f} Min statt 30 Min)")

    # Finale Bereinigung und Sortierung der Ausgabedateien
    print(f"\n🧹 Finale Bereinigung und Sortierung...")
    clean_output_files(output_dir)

    print(f"\n✅ Fertig!")


def main():
    """Hauptfunktion mit Benutzerabfrage."""
    print("=" * 60)
    print("Turbulenz-Daten Verarbeitung")
    print("=" * 60)
    print()

    # Abfrage Input-Ordner
    input_dir_str = input("📁 Pfad zum Input-Ordner: ").strip()
    input_dir = Path(input_dir_str)

    if not input_dir.exists():
        print(f"❌ Fehler: Ordner existiert nicht: {input_dir}")
        return

    if not input_dir.is_dir():
        print(f"❌ Fehler: Kein Ordner: {input_dir}")
        return

    # Abfrage Output-Ordner
    output_dir_str = input("📁 Pfad zum Output-Ordner: ").strip()
    output_dir = Path(output_dir_str)

    # Abfrage Station
    station = input("🏢 Station (Kürzel, z.B. 'Jan'): ").strip()

    if not station:
        print("❌ Fehler: Station muss angegeben werden!")
        return

    # Bestätigung
    print()
    print("=" * 60)
    print("Einstellungen:")
    print(f"  Input:  {input_dir}")
    print(f"  Output: {output_dir}")
    print(f"  Station: {station}")
    print("=" * 60)
    print()

    confirm = input("Fortfahren? (j/n): ").strip().lower()
    if confirm not in ['j', 'ja', 'y', 'yes']:
        print("Abgebrochen.")
        return

    print()

    # Verarbeitung
    split_into_30min_files(input_dir, output_dir, station)


if __name__ == "__main__":
    main()


