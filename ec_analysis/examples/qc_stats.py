from pathlib import Path
import pandas as pd

BASE = Path("/Users/hingerl-l/Data")
PATTERN = "*all_variables_30min.csv"

def load_station_file(station_dir: Path) -> pd.DataFrame | None:
    processed = station_dir / "processed" / "all"
    if not processed.exists():
        return None
    files= list(processed.glob(PATTERN))

    if not files:
        return None

    fpath = files[0]
    df = pd.read_csv(fpath, skiprows=[1])

    if "Timestamp" in df.columns:
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors = "coerce")
        df = df.set_index("Timestamp")
    df = df.apply(pd.to_numeric, errors="ignore")
    df.insert(0, "station", station_dir.name)

    return df


def load_all_stations(base: Path = BASE) -> pd.DataFrame:
    frames = []

    for station_dir in sorted([p for p in base.iterdir() if p.is_dir()]):
        df = load_station_file(station_dir)
        if df is not None:
            frames.append(df)

    all_df = pd.concat(frames, axis = 0).sort_index()
    return all_df

def qc_summary(all_df: pd.DataFrame, qc_cols: list[str], good_threshold: int = 1, verygood_threshold: int = 0) -> pd.DataFrame:
    existing = [c for c in qc_cols if c in all_df.columns]
    missing = [c for c in qc_cols if c not in all_df.columns]

    if missing:
        print("Missing QC columns (skipped):", missing)

    rows = []
    for st, g in all_df.groupby("station"):
        for col in existing:
            s = pd.to_numeric(g[col], errors="coerce")
            n = s.notna().sum()
            good = (s <= good_threshold).sum()
            verygood = (s == verygood_threshold).sum()
            rows.append({
                "station": st,
                "qc_var": col,
                "n": int(n),
                "good_(<=1)": int(good),
                "verygood_(=0)": int(verygood),
                "good_%": float(good / n * 100) if n else float("nan"),
                "verygood_%": float(verygood / n * 100) if n else float("nan"),
            })

    return pd.DataFrame(rows).sort_values(["station", "qc_var"])


if __name__ == "__main__":
    all_df = load_all_stations()
    print("Loaded rows:", len(all_df))
    print("Stations:", sorted(all_df["station"].unique()))
    print(all_df.head())

    # Use the QC column names that actually exist in your CSVs (example from your header)
    qc_cols = ["qc_LE", "qc_H", "qc_o2_flux"]  # adjust if your CO2 QC column is named differently
    out = qc_summary(all_df, qc_cols, good_threshold=1)
    print(out.to_string(index=False))
