#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Splittet ts_data-Dateien in einstündige Dateien im gleichen Format wie Turbulence.

- Stündliche Dateien werden kontinuierlich geschrieben (Puffer → Flush alle 500 Zeilen pro Stunde).
- Resume: Bereits verarbeitete Quelldateien werden in <Ausgabeordner>/.split_hourly_progress gespeichert.
  Bei Abbruch und Neustart werden nur noch nicht verarbeitete Dateien gelesen.

Geschwindigkeit:
- C-Version (empfohlen): split_ts_data_to_hourly.c  (make -f Makefile.split_hourly)
  Nutzt setvbuf (1 MB Lese-, 512 KB Schreibpuffer), Pass 2 sortiert nach int64-Key statt String-Vergleich.
- Binär-Pipeline (optional, für maximale Geschwindigkeit):
  1) Text → Binär: Zeilen mit int64-Sortierschlüssel (YYYYMMDDHHMMSSmmm) + Länge + Zeile in .bin pro Stunde schreiben.
  2) Stündliche .bin nach Key sortieren (Integer-Vergleich, sehr schnell).
  3) Binär → Text: .bin lesen, nur Zeilen in .dat schreiben.
  Vorteil: Sortierung und I/O schneller; Nachteil: zusätzlicher Format-Schritt und Speicher für .bin.

Speichereffizient: Zwei-Pass
- Pass 1: Quellen zeilenweise lesen, nach Stunde puffern, kontinuierlich in Stundendateien schreiben.
- Pass 2: Jede Stundendatei einlesen, nach Timestamp sortieren, überschreiben (nur 1 Stunde im RAM).

Verwendung:
    python split_ts_data_to_hourly.py
"""

import re
import gc
import time
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta

SOURCE_DIR = Path("/Volumes/Extreme SSD/Gorigo/ts_data")
OUTPUT_DIR = Path("/Volumes/Extreme SSD/Gorigo/ts_data_hourly")  # Ausgabeordner
TURBULENCE_DIR = Path("/Volumes/Extreme SSD/Gorigo/Turbulence")



def parse_first_field(line: str):
    """Extrahiert Timestamp aus der ersten Spalte einer Zeile. Returns (datetime or None, rest_of_line)."""
    line = line.strip()
    if not line:
        return None, line
    m = re.match(r'^("?\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)"?,?(.*)$', line)
    if not m:
        return None, line
    ts_str, rest = m.group(1).strip('"'), m.group(2)
    try:
        # Unterstütze YYYY-MM-DD HH:MM:SS und YYYY-MM-DD HH:MM:SS.ff (für Sortierung)
        if "." in ts_str:
            base, frac = ts_str.split(".", 1)
            dt = datetime.strptime(base, "%Y-%m-%d %H:%M:%S")
            frac = (frac + "000000")[:6]  # auf Mikrosekunden
            dt = dt.replace(microsecond=int(frac))
        else:
            if len(ts_str) <= 16:
                dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M")
            else:
                dt = datetime.strptime(ts_str[:19], "%Y-%m-%d %H:%M:%S")
        return dt, line
    except Exception:
        return None, line


def skip_toa5_header(f):
    """
    Liest die erste Zeile. Wenn TOA5, verwirft 3 weitere Zeilen.
    Returns: (first_data_line or None, is_toa5).
    Bei TOA5: first_data_line = None (Header verworfen).
    Bei Nicht-TOA5: first_data_line = erste Zeile (kann Datenzeile sein).
    """
    first = f.readline()
    if not first:
        return None, False
    s = first.strip().upper().lstrip("\ufeff")
    if s.startswith("TOA5") or s.startswith('"TOA5'):
        for _ in range(3):
            f.readline()
        return None, True
    return first, False


def hour_key(dt: datetime) -> tuple:
    """(yy, ddd, HHMM) für Dateinamen gor_yy_ddd_HHMM.dat."""
    yy = dt.year % 100
    ddd = dt.timetuple().tm_yday
    HHMM = dt.hour * 100 + dt.minute
    return (yy, ddd, HHMM)


def hour_range(yy: int, ddd: int, HHMM: int) -> tuple:
    """
    Start und Ende der Stunde als datetime (für Filter).
    hour_start = XX:00:00.000, hour_end = (XX+1):00:00.000 (exklusiv).
    """
    year = 2000 + yy if yy < 50 else 1900 + yy
    jan1 = datetime(year, 1, 1)
    hour_start = jan1 + timedelta(days=ddd - 1, hours=HHMM // 100, minutes=HHMM % 100)
    hour_end = hour_start + timedelta(hours=1)
    return hour_start, hour_end


def filename_for(yy: int, ddd: int, HHMM: int) -> str:
    return f"gor_{yy:02d}_{ddd:03d}_{HHMM:04d}.dat"


def is_likely_text_file(path: Path, sample_size: int = 8192, max_binary_ratio: float = 0.05) -> bool:
    """
    Heuristik: Liest die ersten sample_size Bytes und prüft, ob die Datei wie Text aussieht.
    Enthält mehr als max_binary_ratio Steuer-/Null-Bytes (außer \\t, \\n, \\r), gilt sie als Binär.
    Leere Dateien werden als Text behandelt.
    """
    try:
        with open(path, "rb") as f:
            chunk = f.read(sample_size)
    except OSError:
        return False
    if not chunk:
        return True
    binary_count = 0
    for b in chunk:
        if b == 0 or (b < 32 and b not in (9, 10, 13)):  # NUL oder sonstige Steuerzeichen
            binary_count += 1
    return (binary_count / len(chunk)) <= max_binary_ratio


# Kleiner Schreibpuffer pro Stunde (weniger Open/Close, RAM bleibt begrenzt)
# Stündliche Dateien werden kontinuierlich geschrieben (alle 500 Zeilen pro Stunde → Flush)
WRITE_BUFFER_SIZE = 500
PROGRESS_FILENAME = ".split_hourly_progress"


def stream_append_to_hourly(source_dir: Path, output_dir: Path, exclude_dot_underscore: bool = True) -> int:
    """
    Pass 1: Liest zeilenweise, puffert pro Stunde (WRITE_BUFFER_SIZE Zeilen), schreibt dann.
    Stündliche Dateien werden kontinuierlich auf Disk geschrieben (kein Verlust bei Abbruch).
    Bereits verarbeitete Quelldateien werden aus .split_hourly_progress gelesen und übersprungen (Resume).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    progress_file = output_dir / PROGRESS_FILENAME

    # Bereits verarbeitete Quelldateien laden (Resume nach Abbruch/Neustart)
    processed = set()
    if progress_file.exists():
        try:
            with open(progress_file, "r", encoding="utf-8") as pf:
                for line in pf:
                    p = line.strip()
                    if p:
                        processed.add(p)
        except OSError:
            pass
        if processed:
            print(f"   📂 Fortschritt geladen: {len(processed)} Quelldatei(en) bereits verarbeitet (Resume)")

    dat_files = sorted(f for f in source_dir.glob("*.dat") if f.is_file())
    if exclude_dot_underscore:
        dat_files = [f for f in dat_files if not f.name.startswith("._")]
    # Binärdateien überspringen (nur Textdateien zeilenweise verarbeiten)
    text_files, skipped_binary = [], []
    for f in dat_files:
        if is_likely_text_file(f):
            text_files.append(f)
        else:
            skipped_binary.append(f)
    dat_files = text_files
    if skipped_binary:
        print(f"   ⚠️ {len(skipped_binary)} .dat-Datei(en) als Binär erkannt und übersprungen (z. B. {skipped_binary[0].name})")
    total_lines = 0
    buf = defaultdict(list)
    start_time = time.perf_counter()
    last_print_time = start_time
    print_interval = 30  # alle 30 Sekunden Fortschritt ausgeben

    def flush_key(key):
        if not buf[key]:
            return
        out_path = output_dir / filename_for(*key)
        with open(out_path, "a", encoding="utf-8", newline="\n") as out:
            for ln in buf[key]:
                out.write(ln + "\n")
        buf[key].clear()

    for n_files, path in enumerate(dat_files, 1):
        path_key = str(path.resolve())
        if path_key in processed:
            print(f"\n   [{n_files}/{len(dat_files)}] {path.name[:60]}… (bereits verarbeitet, übersprungen)")
            continue
        print(f"\n   [{n_files}/{len(dat_files)}] {path.name[:60]}…")
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                first_line, _ = skip_toa5_header(f)
                def line_iter():
                    if first_line:
                        yield first_line
                    for raw in f:
                        yield raw
                for raw in line_iter():
                    line = raw.rstrip("\n\r") if raw else ""
                    if not line.strip():
                        continue
                    dt, full_line = parse_first_field(line)
                    if dt is None:
                        continue
                    key = hour_key(dt)
                    hour_start, hour_end = hour_range(*key)
                    if not (hour_start <= dt < hour_end):
                        continue
                    buf[key].append(full_line)
                    total_lines += 1
                    if len(buf[key]) >= WRITE_BUFFER_SIZE:
                        flush_key(key)
                    if total_lines % 5000 == 0:
                        now = time.perf_counter()
                        if now - last_print_time >= print_interval:
                            elapsed = now - start_time
                            rate = total_lines / elapsed if elapsed > 0 else 0
                            print(f"      … {total_lines:,} Zeilen, {rate:,.0f} Zeilen/s")
                            last_print_time = now
        except Exception as e:
            print(f"   ⚠️ {path.name}: {e}")
        else:
            # Erfolgreich verarbeitet → Fortschritt speichern (Resume bei Neustart)
            processed.add(path_key)
            try:
                with open(progress_file, "a", encoding="utf-8") as pf:
                    pf.write(path_key + "\n")
            except OSError:
                pass
        for key in list(buf.keys()):
            flush_key(key)
        gc.collect()
    for key in list(buf.keys()):
        flush_key(key)
    elapsed = time.perf_counter() - start_time
    print(f"\n   Pass 1 fertig: {total_lines:,} Zeilen in {elapsed/60:.1f} Min ({total_lines/elapsed:,.0f} Zeilen/s)")
    return total_lines


# Max. Zeilen pro Chunk beim Sortieren (Pass 2) – begrenzt RAM pro Stundendatei
SORT_CHUNK_SIZE = 50_000


def sort_hourly_files(output_dir: Path):
    """
    Pass 2: Jede gor_*.dat nach Timestamp sortieren.
    Große Dateien werden in Chunks gelesen, sortiert, in Temp-Dateien geschrieben,
    dann gemergt – so bleibt der RAM konstant begrenzt.
    """
    hour_files = sorted(output_dir.glob("gor_*.dat"))
    for p in hour_files:
        # Chunkweise lesen, sortieren, in Temp-Dateien schreiben
        temp_files = []
        chunk = []
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                ln = raw.rstrip("\n\r")
                if not ln.strip():
                    continue
                chunk.append(ln)
                if len(chunk) >= SORT_CHUNK_SIZE:
                    sort_and_write_chunk(chunk, temp_files, output_dir, p.stem)
                    chunk = []
                    gc.collect()
            if chunk:
                sort_and_write_chunk(chunk, temp_files, output_dir, p.stem)
                chunk = []
        if not temp_files:
            continue
        if len(temp_files) == 1:
            # Nur eine Temp-Datei → umbenennen statt mergen
            temp_files[0].replace(p)
        else:
            merge_sorted_files(temp_files, p)
        for tf in temp_files:
            if tf.exists():
                tf.unlink()
        gc.collect()
    print(f"   Pass 2: {len(hour_files)} Dateien sortiert.")


def sort_and_write_chunk(chunk: list, temp_files: list, output_dir: Path, stem: str):
    """Chunk nach Timestamp sortieren und in neue Temp-Datei schreiben."""
    sort_pairs = []
    for ln in chunk:
        dt, _ = parse_first_field(ln)
        sort_pairs.append((dt if dt is not None else datetime.min, ln))
    sort_pairs.sort(key=lambda x: x[0])
    tf = output_dir / f"{stem}_sort_{len(temp_files):04d}.tmp"
    with open(tf, "w", encoding="utf-8", newline="\n") as f:
        for _, ln in sort_pairs:
            f.write(ln + "\n")
    temp_files.append(tf)


def merge_sorted_files(sorted_paths: list, out_path: Path):
    """Mehrere nach Zeile 1 sortierte Dateien zu einer sortierten Datei mergen."""
    from heapq import merge

    def line_key(ln):
        dt, _ = parse_first_field(ln)
        return dt if dt is not None else datetime.min

    streams = []
    for path in sorted_paths:
        f = open(path, "r", encoding="utf-8", errors="ignore")
        streams.append((f, iter(f)))
    iters = []
    for f, it in streams:
        def _gen(_f, _it):
            for ln in _it:
                yield (line_key(ln), ln)
        iters.append(_gen(f, it))
    with open(out_path, "w", encoding="utf-8", newline="\n") as out:
        for _, ln in merge(*iters, key=lambda x: x[0]):
            out.write(ln.rstrip("\n\r") + "\n")
    for f, _ in streams:
        f.close()


def main():
    print("=" * 60)
    print("Split ts_data → stündliche Dateien (speichereffizient)")
    print("=" * 60)
    print(f"   Quelle:    {SOURCE_DIR}")
    print(f"   Ausgabe:   {OUTPUT_DIR}")
    if not SOURCE_DIR.exists():
        print(f"   ⚠️ Quelle existiert nicht: {SOURCE_DIR}")
        return
    print("\n   Pass 1: Zeilen in Stundendateien appenden (streaming, kein großer RAM-Puffer) …")
    total = stream_append_to_hourly(SOURCE_DIR, OUTPUT_DIR)
    if total == 0:
        print("   Keine Daten geschrieben.")
        return
    print(f"   Pass 1 fertig: {total:,} Zeilen in Stundendateien.")
    print("\n   Pass 2: Stundendateien nach Timestamp sortieren …")
    sort_hourly_files(OUTPUT_DIR)
    print("   Fertig.")


if __name__ == "__main__":
    main()
