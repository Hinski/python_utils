import os
import shutil
from pathlib import Path

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------
START_DIR = Path("/Volumes/Elements/")    # <-- HIER ANPASSEN
OUTPUT_DIR = Path("/Users/hingerl-l/Data/Sumbrungu/raw/")    # <-- HIER ANPASSEN

#TARGET_FOLDER_NAMES = ["WASCAL_3_NAZINGA","wascal3", "wascal-3", "wascal_3", "wascal 3",
#                       "wascal3", "WASCAL-3", "nazinga"]

TARGET_FOLDER_NAMES = ["Sumbrungu", "sumbrungu", "WASCAL 1 Sumbrungu", "WASCAL 1 Sumbrungu data", "WASCAL_1_ Sumbrungu"]

FILE_KEYWORDS = ["cr1000", "rad", "result","Radiation","SMT","Rad","smt"]
#FILE_KEYWORDS = ["wxt","WXT"]

# Ordner die übersprungen werden sollen
EXCLUDE_DIRS = ["Turbulence", "work", "cam", "TrashedData","mxdata","Trashed","mxcam","OttParsivel","pictures","OttParsivel_1","Turbulence1","Turbulence_1"]

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------
# Helfer: prüft, ob Ordnername relevant ist
# ------------------------------------------------------------
def folder_matches(name: str) -> bool:
    name_lower = name.lower()
    for pattern in TARGET_FOLDER_NAMES:
        if pattern.lower() in name_lower:
            return True
    return False

def should_exclude_dir(name: str) -> bool:
    """Prüft ob ein Ordner übersprungen werden soll."""
    name_lower = name.lower()
    for exclude in EXCLUDE_DIRS:
        if exclude.lower() == name_lower:
            return True
    return False


# ------------------------------------------------------------
# Hauptfunktion
# ------------------------------------------------------------
def collect_files(start_dir: Path, out_dir: Path):
    print(f"🔍 Scanne: {start_dir}")

    for root, dirs, files in os.walk(start_dir):
        # Überspringe ausgeschlossene Ordner
        dirs[:] = [d for d in dirs if not should_exclude_dir(d)]

        root_path = Path(root)

        # Prüfen, ob dieser Ordner relevant ist
        if folder_matches(root_path.name):
            print(f"📁 Treffer-Ordner (durchsuche vollständig): {root_path}")

            # In diesem Ordner + allen Unterordnern nach Dateien suchen
            for r2, d2, f2 in os.walk(root_path):
                # Überspringe ausgeschlossene Ordner auch in Unterordnern
                d2[:] = [d for d in d2 if not should_exclude_dir(d)]

                for file in f2:
                    file_lower = file.lower()

                    # Prüfen ob eine der Ziel-Keywords enthalten ist
                    if any(keyword in file_lower for keyword in FILE_KEYWORDS):

                        source = Path(r2) / file
                        dest = out_dir / file

                        # Falls Datei schon existiert, Versionsnummer anhängen
                        if dest.exists():
                            base = dest.stem
                            ext = dest.suffix
                            i = 1
                            while True:
                                new_dest = out_dir / f"{base}_{i}{ext}"
                                if not new_dest.exists():
                                    dest = new_dest
                                    break
                                i += 1

                        print(f"   📄 Kopiere: {source}  →  {dest}")
                        shutil.copy2(source, dest)


# ------------------------------------------------------------
# AUSFÜHREN
# ------------------------------------------------------------
if __name__ == "__main__":
    collect_files(START_DIR, OUTPUT_DIR)
    print("✅ Fertig!")
