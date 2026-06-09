#!/usr/bin/env python3
"""
Entfernt Duplikate aus .dat Dateien basierend auf dem Timestamp (erste Spalte).
Behält nur die erste Zeile für jeden eindeutigen Timestamp.

Verwendung:
    python remove_duplicates_dat.py <ordner_pfad>
    python remove_duplicates_dat.py /Volumes/Data/Gorigo/Turbulence_withADiag --dry-run
"""

import sys
from pathlib import Path
import pandas as pd


def remove_duplicates_from_file(file_path: Path, dry_run: bool = False):
    """
    Entfernt Duplikate basierend auf dem Timestamp (erste Spalte).
    
    Args:
        file_path: Pfad zur Datei
        dry_run: Wenn True, werden keine Änderungen vorgenommen, nur angezeigt
    """
    try:
        # Lese Datei
        print(f"  📖 Lese: {file_path.name}")
        
        # Lese als CSV ohne Header
        df = pd.read_csv(file_path, header=None, dtype=str, keep_default_na=False, 
                        quotechar='"', low_memory=False)
        
        original_rows = len(df)
        
        if original_rows == 0:
            print(f"    ⚠️ Datei ist leer")
            return False
        
        # Erste Spalte ist Timestamp
        # Entferne Duplikate basierend auf erster Spalte, behalte erste Zeile
        df_unique = df.drop_duplicates(subset=[0], keep='first')
        
        unique_rows = len(df_unique)
        duplicates_removed = original_rows - unique_rows
        
        if duplicates_removed > 0:
            if dry_run:
                print(f"    [DRY RUN] {original_rows:,} Zeilen → {unique_rows:,} einzigartige Zeilen")
                print(f"            → {duplicates_removed:,} Duplikate würden entfernt")
            else:
                # Schreibe zurück
                # Behalte Anführungszeichen um Timestamp wenn vorhanden
                output_lines = []
                for idx, row in df_unique.iterrows():
                    row_values = []
                    for i, val in enumerate(row):
                        val_str = str(val)
                        # Erste Spalte (Timestamp) mit Anführungszeichen wenn nicht bereits vorhanden
                        if i == 0 and not val_str.startswith('"'):
                            row_values.append(f'"{val_str}"')
                        else:
                            row_values.append(val_str)
                    output_lines.append(','.join(row_values))
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(output_lines))
                
                print(f"    ✓ {original_rows:,} Zeilen → {unique_rows:,} Zeilen")
                print(f"      → {duplicates_removed:,} Duplikate entfernt")
            return True
        else:
            print(f"    → Keine Duplikate gefunden")
            return False
            
    except Exception as e:
        print(f"    ⚠️ Fehler bei {file_path.name}: {e}")
        import traceback
        if dry_run:
            traceback.print_exc()
        return False


def process_directory(directory: Path, dry_run: bool = False):
    """
    Verarbeitet alle .dat Dateien in einem Ordner.
    
    Args:
        directory: Ordnerpfad
        dry_run: Wenn True, werden keine Änderungen vorgenommen
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
    
    # Finde alle .dat Dateien
    dat_files = list(directory.glob("*.dat"))
    
    if not dat_files:
        print("  ⚠️ Keine .dat Dateien gefunden")
        return
    
    print(f"  Gefunden: {len(dat_files)} .dat Dateien")
    print()
    
    # Verarbeite jede Datei
    modified_count = 0
    total_duplicates_removed = 0
    
    for file_path in sorted(dat_files):
        if remove_duplicates_from_file(file_path, dry_run=dry_run):
            modified_count += 1
    
    print()
    if dry_run:
        print(f"📊 [DRY RUN] {modified_count} Dateien würden geändert werden")
    else:
        print(f"✅ {modified_count} Dateien wurden bereinigt")


def main():
    """Hauptfunktion."""
    if len(sys.argv) < 2:
        print("Verwendung: python remove_duplicates_dat.py <ordner_pfad> [--dry-run]")
        print("\nBeispiele:")
        print("  python remove_duplicates_dat.py /Volumes/Data/Gorigo/Turbulence_withADiag")
        print("  python remove_duplicates_dat.py /Volumes/Data/Gorigo/Turbulence_withADiag --dry-run")
        sys.exit(1)
    
    directory = Path(sys.argv[1])
    dry_run = '--dry-run' in sys.argv
    
    process_directory(directory, dry_run=dry_run)


if __name__ == "__main__":
    main()
