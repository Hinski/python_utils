"""
Mittlerer Tagesgang der Energiebilanzkomponenten für alle Stationen.

6 Plotfenster (2×3): In jedem Fenster alle Komponenten Rn, LE, H, -G für eine
Station übereinander. Schwarzweiß.

Run collect_all_variables_30min.py and append_G_to_csv.py first.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent.parent))

# ============================================================================
# CONFIGURATION
# ============================================================================
FINAL_ESSD_DIR = Path("/Users/hingerl-l/Data/essd_data_tables/final_datatables")
STATIONS = ["Nazinga", "Kayoro", "Sumbrungu", "Mole", "Janga", "Gorigo"]
STATION_LABELS = {
    "Nazinga": "Nazinga (protected forest)",
    "Mole": "Mole (managed forest)",
    "Kayoro": "Kayoro (cropland)",
    "Janga": "Janga (rainfed rice field)",
    "Sumbrungu": "Sumbrungu (degr. grassland)",
    "Gorigo": "Gorigo (semi-degr. grassland)",
}

STATION_DATE_RANGES: dict[str, tuple[str, str]] = {
    "Nazinga": ("2013-01-01", "2016-12-31"),
    "Sumbrungu": ("2013-01-01", "2015-12-31"),
    "Kayoro": ("2013-01-01", "2015-12-31"),
    "Mole": ("2022-01-01", "2025-12-31"),
    "Janga": ("2022-01-01", "2025-12-31"),
    "Gorigo": ("2017-01-01", "2025-12-31"),
}
DEFAULT_START = "2013-01-01"
DEFAULT_END = "2025-12-31"

RAD_COL_ALIASES = {
    "SW_in": ["SW_in", "SW_IN", "SR_in_Avg", "SWdown", "SWdown_Avg", "SW_in korrigiert"],
    "SW_out": ["SW_out", "SW_OUT", "SR_out_Avg", "SW_out korrigiert", "SW_out korrigiert "],
    "LW_in": ["LW_in", "LW_IN", "IR_in_Avg", "LWin"],
    "LW_out": ["LW_out", "LW_OUT", "IR_out_Avg", "LWout"],
    "LE": ["LE", "LE_Avg", "LvE", "LE_corr"],
    "H": ["H", "H_Avg", "Hc", "H_corr"],
    "G": ["G", "G_Avg", "G_plate_1", "G1", "SHF_Avg"],
}

# Graustufen und Linienstile pro Komponente (Schwarzweiß)
COMPONENT_STYLES = {
    "Rn": {"color": "0.1", "ls": "-"},
    "LE": {"color": "0.35", "ls": "--"},
    "H": {"color": "0.55", "ls": "-."},
    "minus_G": {"color": "0.8", "ls": ":"},
}


def station_label(station: str) -> str:
    """Lesbares Stationslabel fuer Plot-Titel."""
    return STATION_LABELS.get(station, station)


def _get_column(df: pd.DataFrame, aliases: list[str]) -> pd.Series | None:
    for name in aliases:
        if name in df.columns:
            return df[name]
    return None


def _candidate_paths_final_datatables(station: str) -> list[Path]:
    return [
        FINAL_ESSD_DIR / f"{station}_30min.csv",
        FINAL_ESSD_DIR / f"{station}_essd_30min_clean.csv",
        FINAL_ESSD_DIR / f"{station}_essd_30min.csv",
    ]


def load_station_ebc_data(station: str, start_date: str, end_date: str) -> pd.DataFrame | None:
    """Load 30-min final_datatables CSV and return DataFrame with Rn, LE, H, G."""
    path = None
    for p in _candidate_paths_final_datatables(station):
        if p.exists():
            path = p
            break
    if path is None:
        return None

    with path.open("r", encoding="utf-8") as f:
        header_line = f.readline().strip()
        _units_line = f.readline().strip()
    header = [c.strip() for c in header_line.split(",")]

    df = pd.read_csv(
        path,
        skiprows=2,
        header=None,
        names=header,
        low_memory=False,
        na_values=[-9999, "-9999", "-9999.0", -99999, "7999", "NAN", "nan", "NA"],
    )
    if "TIMESTAMP" not in df.columns or df["TIMESTAMP"].empty:
        return None
    ts = pd.to_datetime(df["TIMESTAMP"], format="%Y%m%d%H%M%S", errors="coerce")
    df = df.drop(columns=["TIMESTAMP"])
    df.index = ts
    df = df[df.index.notna()].sort_index()
    df = df[~df.index.duplicated(keep="first")]

    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    df = df[(df.index >= start) & (df.index <= end)]
    if df.empty:
        return None

    sw_in = _get_column(df, RAD_COL_ALIASES["SW_in"])
    sw_out = _get_column(df, RAD_COL_ALIASES["SW_out"])
    lw_in = _get_column(df, RAD_COL_ALIASES["LW_in"])
    lw_out = _get_column(df, RAD_COL_ALIASES["LW_out"])
    le = _get_column(df, RAD_COL_ALIASES["LE"])
    h = _get_column(df, RAD_COL_ALIASES["H"])
    g = _get_column(df, RAD_COL_ALIASES["G"])
    if sw_in is None or sw_out is None or lw_in is None or lw_out is None or le is None or h is None:
        return None

    # Rn aus Strahlungskomponenten berechnen: SW_IN - SW_OUT + LW_IN - LW_OUT
    rn = (
        pd.to_numeric(sw_in, errors="coerce")
        - pd.to_numeric(sw_out, errors="coerce")
        + pd.to_numeric(lw_in, errors="coerce")
        - pd.to_numeric(lw_out, errors="coerce")
    )

    out = pd.DataFrame(
        {
            "Rn": rn,
            "LE": pd.to_numeric(le, errors="coerce"),
            "H": pd.to_numeric(h, errors="coerce"),
            "G": pd.to_numeric(g, errors="coerce") if g is not None else np.nan,
        },
        index=df.index,
    ).dropna(how="all")
    return out if not out.empty else None


def diurnal_hourly_mean(df: pd.DataFrame, col: str) -> pd.Series:
    """Stündlicher Mittelwert nach Stunde (0–23)."""
    if df.empty or col not in df.columns:
        return pd.Series(dtype=float)
    if col == "LE" or col == "H":
        s = df[col].copy()
        s[(s < -300) | (s > 800)] = np.nan
        return s.groupby(df.index.hour).mean()
    return df[col].groupby(df.index.hour).mean()


def main():
    print("Loading data for all stations...")
    all_diurnal: dict[str, dict[str, pd.Series]] = {}
    for station in STATIONS:
        start, end = STATION_DATE_RANGES.get(station, (DEFAULT_START, DEFAULT_END))
        eb_df = load_station_ebc_data(station, start, end)
        if eb_df is None or eb_df.empty:
            print(f"  {station}: skip (no data)")
            continue
        eb_df["minus_G"] = -eb_df["G"]
        all_diurnal[station] = {
            "Rn": diurnal_hourly_mean(eb_df, "Rn"),
            "LE": diurnal_hourly_mean(eb_df, "LE"),
            "H": diurnal_hourly_mean(eb_df, "H"),
            "minus_G": diurnal_hourly_mean(eb_df, "minus_G"),
        }
        print(f"  {station}: {len(eb_df)} records")

    if not all_diurnal:
        print("No data loaded.")
        return

    # Layout: 2 rows × 3 cols = 6 Fenster. Jedes Fenster = eine Station, alle Komponenten übereinander
    fig, axes = plt.subplots(2, 3, figsize=(9, 6), sharex=True, sharey=True)
    axes = axes.flatten()

    components = ["Rn", "LE", "H", "minus_G"]
    for i, station in enumerate(STATIONS):
        ax = axes[i]
        diurnal = all_diurnal.get(station)
        if diurnal is None:
            ax.set_visible(False)
            continue
        for col_key in components:
            if station == "Gorigo" and col_key == "minus_G":
                continue
            s = diurnal.get(col_key)
            if s is not None and not s.empty:
                sty = COMPONENT_STYLES.get(col_key, {"color": "0.5", "ls": "-"})
                label = "G" if col_key == "minus_G" else col_key
                ax.plot(s.index, s.values, label=label, color=sty["color"], ls=sty["ls"], linewidth=1.5)
        if i % 3 == 0:
            ax.set_ylabel("W/m²", fontsize=12)
        else:
            ax.set_ylabel("")
        ax.axhline(0, color="gray", linestyle=":", linewidth=0.5)
        ax.tick_params(labelsize=11)
        ax.grid(True, alpha=0.3)
        ax.set_title(station_label(station), fontsize=12)
        ax.legend(fontsize=11, loc="upper right")

    for ax in axes[3:]:
        ax.set_xlabel("Hour", fontsize=12)

    #plt.suptitle("Mittlerer Tagesgang – Energiebilanzkomponenten", fontsize=11, fontweight="bold", y=1.02)
    plt.tight_layout()

    out_path = Path("diurnal_cycle_all_stations.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"\n✓ Plot saved: {out_path}")
    plt.show()


if __name__ == "__main__":
    main()
