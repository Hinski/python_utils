import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Add package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

STATION = 'Mole'
DATA_DIR = Path('/Volumes/Extreme SSD/WASCAL_5_MOLE/SD_Card/Mole')
PATTERN = "*AmeriFluxFormat*"
OUTFILE = DATA_DIR / f"{STATION}_AmeriFluxFormat.csv"


def read_ameriflux(file_path: Path) -> pd.DataFrame:
    df = pd.read_csv(
            file_path,
            sep=',',
            quotechar='"',
            header=0,
            na_values=["NAN"],
            on_bad_lines="skip",
            low_memory=False,
            )

    if "TIMESTAMP_START" not in df.columns:
        raise ValueError(f"{file_path.name}: missing columns TIMESTAMP_START")


    df['timestamp'] = pd.to_datetime(
            df['TIMESTAMP_START'].astype(str),
            format="%Y%m%d%H%M",
            errors="coerce",
            )
    df = df.dropna(subset=['timestamp'])

    df = df.set_index('timestamp')

    return df

def load_all_ameriflux_files(data_dir: Path, pattern: str = PATTERN):
    files = sorted(data_dir.glob(pattern))
    files = [p for p in files if p.is_file() and p.suffix.lower() in [".dat",".csv"]]
    return files


def main():
    files = load_all_ameriflux_files(DATA_DIR, PATTERN)

    if not files:
        print(f"X No files fund in {DATA_DIR} matching {PATTERN}")
        return 1

    print(f"Found {len(files)} files")

    for p in files[:5]:
        print(" ", p.name)
    if len(files) > 5:
        print(" ...")

    dfs = []

    for fp in files:
        try:
            df = read_ameriflux(fp)
            df["source_file"] = fp.name
            dfs.append(df)
            print(f"Loaded {fp.name}: {len(df)} rows")
        except Exception as e:
            print(f"Skipping {fp.name}: {e}")

    if not dfs:
        print("No readable files.")
        return 1

    merged = pd.concat(dfs, axis=0, ignore_index=False)
    merged = merged.sort_index()
    merged = merged[~merged.index.duplicated(keep="last")]

    merged.to_csv(OUTFILE, index=True, header=True,na_rep="NaN")
    print(f"\n Wrote merged file: {OUTFILE}")
    print(f"    Rows: len{len(merged)}, Columns: {merged.shape[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())




















