from pathlib import Path
import re
import pandas as pd
from itertools import chain

# ---------- helpers ----------
FORMATS = (
    "%d.%m.%Y %H:%M",
    "%d.%m.%y %H:%M",
    "%d/%m/%y %H:%M",
    "%Y-%m-%d %H:%M:%S",
)
DT_TOKEN_REGEX = re.compile(r'[0-9][0-9:/\.\- T]{7,}')

def parse_ftypes(s: str) -> list[str]:
    # e.g. "Rad, RS, WXT, SMT" -> ["rad","rs","wxt","smt"]
    return [p.strip().lower() for p in re.split(r"[,\s]+", s) if p.strip()]

def parse_dt_token(token: str):
    t = token.strip().strip('"').strip("'")
    for fmt in FORMATS:
        try:
            return pd.to_datetime(t, format=fmt, errors="raise")
        except Exception:
            pass
    return pd.to_datetime(t, errors="coerce", dayfirst=True)

def extract_year_from_file(path: Path) -> int | None:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f, 1):
                for token in DT_TOKEN_REGEX.findall(line):
                    ts = parse_dt_token(token)
                    if pd.notna(ts):
                        return int(ts.year)
                if i >= 2000:
                    break
    except Exception:
        pass
    return None

def first_matching_ftype(name_lower: str, ftypes_lc: list[str]) -> str | None:
    for ft in ftypes_lc:           # respect user input order
        if ft and ft in name_lower:
            return ft
    return None

# ---------- main logic ----------
def join_per_ftype_per_year(input_folder, output_folder, station: str, ftypes_input: str, recursive=False) -> list[Path]:
    input_folder = Path(input_folder).expanduser().resolve()
    output_folder = Path(output_folder).expanduser().resolve()
    output_folder.mkdir(parents=True, exist_ok=True)

    ftypes = parse_ftypes(ftypes_input)  # lowercased, ordered
    if not ftypes:
        raise ValueError("No ftype substrings provided.")

    # collect candidates
    if recursive:
        it = (p for p in input_folder.rglob("*") if p.is_file())
    else:
        it = (p for p in chain(input_folder.glob("*.dat"), input_folder.glob("*.csv")) if p.is_file())
    candidates = sorted(it)

    # assign files to (ftype, year)
    groups: dict[tuple[str, int], list[Path]] = {}
    skipped_no_year = 0
    skipped_no_match = 0

    for p in candidates:
        name_lc = p.name.lower()
        ft = first_matching_ftype(name_lc, ftypes)
        if ft is None:
            skipped_no_match += 1
            continue
        y = extract_year_from_file(p)
        if y is None:
            skipped_no_year += 1
            continue
        groups.setdefault((ft, y), []).append(p)

    if not groups:
        raise RuntimeError("No files matched any ftype with a detectable year.")

    # write outputs: one per (ftype, year)
    out_paths: list[Path] = []
    for (ft, year), files in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        out_file = output_folder / f"{station}_joined_{ft}_{year}.dat"
        with out_file.open("w", encoding="utf-8") as outfile:
            for d in sorted(files):
                with d.open("r", encoding="utf-8", errors="ignore") as infile:
                    outfile.write(infile.read())
                outfile.write("\n")   # separator
        out_paths.append(out_file)
        print(f"[OK] Wrote {out_file} from {len(files)} files.")

    if skipped_no_match:
        print(f"[INFO] Skipped {skipped_no_match} files (no ftype match).")
    if skipped_no_year:
        print(f"[INFO] Skipped {skipped_no_year} files (no parsable year).")

    return out_paths

# ---------- CLI ----------
if __name__ == "__main__":
    input_dir = input("Enter the input directory with .dat/.csv files: ").strip()
    output_dir = input("Enter the output directory for the joined file(s): ").strip()
    ftypes_str = input('Enter one or more substrings to match (e.g., "Rad, RS, WXT, SMT"): ').strip()
    station = input("Enter the station name (e.g., Gorigo): ").strip()

    outs = join_per_ftype_per_year(input_dir, output_dir, station, ftypes_str, recursive=False)
    for p in outs:
        print(f"Created: {p}")
