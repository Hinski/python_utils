"""
Cumulative water balance + Bodenwasserspeicher (Top-Empfehlung).

Grafik (2 Panels oder 2 y-Achsen):
  • Linie 1: kumuliertes ∑(P − ET) [mm]
  • Linie 2: Bodenwasserspeicher S aus θ oder ΔS relativ zu Beginn [mm]

S(t) = θ(t) · Z · 1000  [mm],  ΔS(t) = S(t) − S(t₀)
θ in m³/m³, Z = effektive Wurzeltiefe (m).
Mehrschichten: S = Σ θᵢ · Δzᵢ · 1000 (Δzᵢ = Schichtdicke in m).

Verwendet die Niederschlagsvariable und das Jahr mit den meisten Messwerten.
Run collect_all_variables_30min.py first.
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
OUTPUT_BASE = Path("/Users/hingerl-l/Data")
STATIONS = ["Nazinga", "Sumbrungu", "Gorigo", "Kayoro", "Mole", "Janga"]

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

# Niederschlags-Spalten (Reihenfolge für Auswahl)
PRECIP_COLUMNS = [
    "P", "P_pl", "P_tb", "Precip", "Rainfall", "Precip_Tot", "Rain_Tot",
    "precip_rain_e", "precip_total_rain_e", "precip_cv", "Rs_cv",
    "Acc_NRT", "Acc_totNRT", "WXT_Ramount_Tot", "WXT_Hamount_Tot",
    "Rain_mm_Tot", "precip_cv_Tot",
]

# ET von EddyPro: mm/h → für 30min-Intervalle: mm/30min = ET * 0.5
ET_MM_PER_30MIN_FACTOR = 0.5

# VWC-Schichten: (Kandidaten pro Tiefe, Δz in m). 3cm, 10cm, 35cm → Δz = [0.03, 0.07, 0.25]
# Pro Schicht wird die erste vorhandene Spalte verwendet.
VWC_LAYER_COLS: list[tuple[list[str], float]] = [
    (["VWC_1", "VW_1_Avg", "SWC_1_1_1", "SWC_1", "VWC_Avg"], 0.03),
    (["VWC_2", "VW_2_Avg", "SWC_2_1_1", "SWC_2", "VWC_2_Avg"], 0.07),
    (["VWC_3", "VW_3_Avg", "SWC_3_1_1", "SWC_3", "VWC_3_Avg"], 0.25),
]
VWC_SCALE: dict[str, float] = {"Janga": 100.0}  # SWC in % → /100 für m³/m³


def compute_soil_storage(df: pd.DataFrame, station: str) -> pd.Series | None:
    """
    S(t) = Σ θᵢ(t) · Δzᵢ · 1000 [mm]. ΔS(t) = S(t) − S(t₀).
    Pro Schicht: erste verfügbare VWC-Spalte.
    """
    scale = VWC_SCALE.get(station, 1.0)
    S = pd.Series(0.0, index=df.index)
    for cols, dz in VWC_LAYER_COLS:
        for c in cols:
            if c in df.columns:
                th = pd.to_numeric(df[c], errors="coerce") / scale
                S = S + th * dz * 1000
                break
    if S.isna().all():
        return None
    S0 = S.dropna().iloc[0] if S.notna().any() else 0.0
    return S - S0


def load_all_variables(station: str, start_date: str, end_date: str) -> pd.DataFrame | None:
    """Lädt all_variables CSV und filtert auf Datumsbereich."""
    path = OUTPUT_BASE / station / "processed" / "all" / f"{station}_all_variables_30min.csv"
    if not path.exists():
        return None
    header = pd.read_csv(path, nrows=1).columns.tolist()
    df = pd.read_csv(
        path,
        skiprows=2,
        header=None,
        names=header,
        index_col=0,
        parse_dates=True,
        low_memory=False,
        na_values=["NAN", "NA", "-9999", "-9999.0", "-999", "**************"],
    )
    df = df[df.index.notna()].sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df = df.loc[(df.index >= start_date) & (df.index <= end_date)]
    return df


def select_precip_column(df: pd.DataFrame) -> str | None:
    """Wählt die P-Spalte mit den meisten gültigen Messwerten."""
    best_col = None
    best_count = 0
    for col in PRECIP_COLUMNS:
        if col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        count = s.notna().sum()
        if count > best_count:
            best_count = count
            best_col = col
    return best_col


def select_year_with_most_data(df: pd.DataFrame, p_col: str) -> int | None:
    """Wählt das Jahr mit den meisten gültigen P- und ET-Messwerten."""
    et_col = "ET" if "ET" in df.columns else None
    years = df.index.year.unique()
    if not len(years):
        return None
    best_year = None
    best_count = 0
    for year in sorted(years):
        mask = df.index.year == year
        n_p = df.loc[mask, p_col].notna().sum()
        n_et = df.loc[mask, et_col].notna().sum() if et_col else 0
        # Kombiniert: Zeilen mit P und ET
        if et_col:
            count = (df.loc[mask, p_col].notna() & df.loc[mask, et_col].notna()).sum()
        else:
            count = n_p
        if count > best_count:
            best_count = count
            best_year = year
    return best_year


def main():
    print("Cumulative water balance + Bodenwasserspeicher ΔS")
    print("=" * 50)
    for station in STATIONS:
        start, end = STATION_DATE_RANGES.get(station, (DEFAULT_START, DEFAULT_END))
        df = load_all_variables(station, start, end)
        if df is None or df.empty:
            print(f"  {station}: skip (no data)")
            continue

        p_col = select_precip_column(df)
        if p_col is None:
            print(f"  {station}: skip (no P column)")
            continue
        if "ET" not in df.columns:
            print(f"  {station}: skip (no ET column)")
            continue

        year = select_year_with_most_data(df, p_col)
        if year is None:
            print(f"  {station}: skip (no valid year)")
            continue

        df_y = df[df.index.year == year].copy()
        P = pd.to_numeric(df_y[p_col], errors="coerce")
        ET_raw = pd.to_numeric(df_y["ET"], errors="coerce")
        ET_mm = ET_raw * ET_MM_PER_30MIN_FACTOR  # mm/h → mm/30min
        cum_p_minus_et = (P - ET_mm).cumsum()

        DeltaS = compute_soil_storage(df_y, station)

        fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
        axa, axb = axes
        fig.suptitle(f"Cumulative water balance + Bodenwasserspeicher – {station} ({year})", fontsize=14, fontweight="bold", y=1.02)

        # Panel a: Kumulierte Wasserbilanz ∑(P − ET)
        axa.plot(cum_p_minus_et.index, cum_p_minus_et.values, color="#1f77b4", label=r"$\sum(P - ET)$", linewidth=1.5)
        axa.axhline(0, color="gray", linestyle=":", linewidth=0.5)
        axa.set_ylabel("mm", fontsize=11)
        axa.legend(loc="upper left", fontsize=10)
        axa.grid(True, alpha=0.3)
        axa.text(0.02, 0.98, "a)", transform=axa.transAxes, fontsize=14, fontweight="bold", va="top")

        # Panel b: Bodenwasserspeicher ΔS
        if DeltaS is not None and DeltaS.notna().any():
            axb.plot(DeltaS.index, DeltaS.values, color="#2ca02c", label=r"$\Delta S$ (rel. t₀)", linewidth=1.5)
            axb.axhline(0, color="gray", linestyle=":", linewidth=0.5)
        else:
            axb.text(0.5, 0.5, "Keine VWC-Daten", ha="center", va="center", transform=axb.transAxes)
        axb.set_ylabel("mm", fontsize=11)
        axb.set_xlabel("Datum", fontsize=11)
        axb.legend(loc="upper left", fontsize=10)
        axb.grid(True, alpha=0.3)
        axb.text(0.02, 0.98, "b)", transform=axb.transAxes, fontsize=14, fontweight="bold", va="top")

        plt.tight_layout()
        out_path = Path(f"water_balance_{station}_{year}.png")
        plt.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  {station} ({year}): P={p_col}, {len(df_y)} records → {out_path}")

    print("\n✓ Fertig.")


if __name__ == "__main__":
    main()
