#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Findet alle Dateien, die
  - mit ts_data.dat enden,
  - _Time_Series_ im Namen haben oder
  - die Form TOA5_xxxxx.dat haben (xxxxx = 5-stellige Zahl),
in einem Ordner und allen Unterordnern und verschiebt sie in einen Zielordner.

Quell- und Zielordner werden beim Ausführen abgefragt.

Verwendung:
    python move_ts_data_dat.py
"""

import re
from pathlib import Path
import shutil
from typing import List

# TOA5_xxxxx.dat (xxxxx = genau 5 Ziffern)
TOA5_PATTERN = re.compile(r"^TOA5_\d{5}\.dat$", re.IGNORECASE)


def find_ts_data_files(source_dir: Path) -> List[Path]:
    """Findet passende Dateien (ts_data.dat, _Time_Series_, TOA5_xxxxx.dat) rekursiv."""
    source_dir = Path(source_dir).resolve()
    if not source_dir.is_dir():
        return []
    files: List[Path] = []
    for path in source_dir.rglob("*"):
        if not path.is_file():
            continue
        name = path.name
        if (
            name.endswith("ts_data.dat")
            or "_Time_Series_" in name
            or TOA5_PATTERN.match(name)
        ):
            files.append(path)
    return sorted(files)


def unique_target_name(target_dir: Path, base_name: str) -> Path:
    """Erzeugt einen eindeutigen Dateinamen im Zielordner (bei Namenskollisionen)."""
    out = target_dir / base_name
    if not out.exists():
        return out
    stem = Path(base_name).stem  # z.B. "ts_data" oder "subdir_ts_data"
    suffix = Path(base_name).suffix  # z.B. ".dat"
    n = 1
    while True:
        out = target_dir / f"{stem}_{n}{suffix}"
        if not out.exists():
            return out
        n += 1


def main():
    print("=" * 60)
    print("  ts_data.dat, *_Time_Series_*, TOA5_xxxxx.dat finden und verschieben")
    print("=" * 60)

    # Quellordner abfragen
    source_str = input("\n📁 Quellordner (durchsuchen inkl. Unterordner): ").strip()
    if not source_str:
        print("❌ Kein Quellordner angegeben. Abbruch.")
        return
    source_dir = Path(source_str).expanduser().resolve()
    if not source_dir.is_dir():
        print(f"❌ Ordner existiert nicht: {source_dir}")
        return

    # Zielordner abfragen (Vorschlag: unter /Volumes/Extreme SSD/)
    default_target = Path("/Volumes/Extreme SSD/ts_data_dat")
    target_prompt = f"\n📁 Zielordner [Standard: {default_target}]: "
    target_str = input(target_prompt).strip()
    if not target_str:
        target_dir = default_target
    else:
        target_dir = Path(target_str).expanduser().resolve()

    # Zielordner anlegen
    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n✓ Zielordner: {target_dir}")

    # Dateien suchen
    print(f"\n🔍 Suche nach ts_data.dat, _Time_Series_, TOA5_xxxxx.dat in: {source_dir}")
    files = find_ts_data_files(source_dir)
    if not files:
        print("   Keine passenden Dateien gefunden.")
        return
    print(f"   Gefunden: {len(files)} Datei(en)")

    # Verschieben
    print("\n📦 Verschiebe Dateien...")
    for i, src in enumerate(files, 1):
        try:
            # Eindeutigen Namen bilden: relative Pfadteile mit _ verbinden
            try:
                rel = src.relative_to(source_dir)
                # z.B. subdir1/subdir2/ts_data.dat -> subdir1_subdir2_ts_data.dat
                base_name = "_".join(rel.parts)
            except ValueError:
                base_name = src.name
            dest = unique_target_name(target_dir, base_name)
            shutil.move(str(src), str(dest))
            print(f"   [{i}/{len(files)}] {src.name} → {dest.name}")
        except Exception as e:
            print(f"   ⚠️ Fehler bei {src}: {e}")

    print(f"\n✅ Fertig. {len(files)} Datei(en) nach {target_dir} verschoben.")


if __name__ == "__main__":
    main()
