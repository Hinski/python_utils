"""
Mittlerer Tagesgang von NEE für alle Stationen (analog zu diurnal_cycle_all_stations.py).

Layout: 2×3 Subplots, je Station eine Kurve — NEE als Stundenmittel über alle in den
final_datatables vorhandenen 30-Min-Punkte.

Datenquelle (Halbstundendaten, ESSD-Format):
  /Users/hingerl-l/Data/essd_data_tables/final_datatables
  (Dateinamen wie seasonal_carbon_uptake_final_datatables: {station}_30min.csv, …)

Filter: ausschließlich QC — es werden nur Zeilen mit QC < QC_KEEP_LT (typisch Flags 0 und 1)
beibehalten. Kein Datums- oder Jahresausschnitt.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

# =============================================================================
# CONFIGURATION
# =============================================================================
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

CO2_FLUX_ALIASES = [
    "NEE", "nee", "co2_flux", "CO2_flux", "Fc", "FC", "Fco2", "FCO2",
    "co2", "CO2",
]

# final_datatables: typisch CO2_QC (wie seasonal_carbon_uptake_final_datatables)
QC_COL_ALIASES = ["CO2_QC", "qc_o2_flux", "qc_NEE", "Flag(Fc)", "Flag(NEE)"]
# Nur Werte mit QC < dieses Schwellwerts (z. B. 2 → erlaubt 0 und 1)
QC_KEEP_LT = 2

# Schwarzweiß, eine Linie pro Panel (analog zur Rn-Linie im EB-Plot)
NEE_LINE_STYLE = {"color": "0.15", "ls": "-", "lw": 1.5}

# Einheitliche Y-Skalierung (µmol m⁻² s⁻¹); bei Bedarf anpassen
NEE_YLIM: tuple[float, float] = (-15.0, 8.0)

FONTSIZE_TITLE = 12
FONTSIZE_AXIS = 12
FONTSIZE_TICK = 11


def get_first_existing_col(df: pd.DataFrame, aliases: list[str]) -> str | None:
    for a in aliases:
        if a in df.columns:
            return a
    return None


def apply_qc_lt(series: pd.Series, qc: pd.Series, keep_lt: int = 2) -> pd.Series:
    """Setzt NEE auf NaN, wo QC fehlt oder QC >= keep_lt."""
    s = pd.to_numeric(series, errors="coerce").copy()
    q = pd.to_numeric(qc, errors="coerce")
    bad = q.isna() | (q >= keep_lt)
    s.loc[bad] = np.nan
    return s


def _candidate_paths_final_datatables(station: str) -> list[Path]:
    """Gleiche Reihenfolge wie seasonal_carbon_uptake_final_datatables."""
    return [
        FINAL_ESSD_DIR / f"{station}_30min.csv",
        FINAL_ESSD_DIR / f"{station}_essd_30min_clean.csv",
        FINAL_ESSD_DIR / f"{station}_essd_30min.csv",
    ]


def load_station_csv(station: str) -> pd.DataFrame | None:
    """
    Lädt ESSD-30-Min-CSV (2-Zeilen-Header) aus final_datatables.
    Erste Spalte: TIMESTAMP (YYYYMMDDHHMMSS).
    """
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
    var_names = [c.strip() for c in header_line.split(",")]

    df = pd.read_csv(
        path,
        skiprows=2,
        header=None,
        names=var_names,
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
    return df


def load_nee_series(station: str) -> pd.Series | None:
    """Volle Zeitreihe aus CSV; nur QC < QC_KEEP_LT."""
    df = load_station_csv(station)
    if df is None or df.empty:
        return None

    col = get_first_existing_col(df, CO2_FLUX_ALIASES)
    if col is None:
        return None
    nee = pd.to_numeric(df[col], errors="coerce")

    qc_col = get_first_existing_col(df, QC_COL_ALIASES)
    if qc_col is not None:
        nee = apply_qc_lt(nee, df[qc_col], keep_lt=QC_KEEP_LT)
    else:
        print(f"  [WARN] {station}: no QC column {QC_COL_ALIASES}; using all NEE rows")

    out = nee.dropna()
    return out if not out.empty else None


def diurnal_hourly_mean(s: pd.Series) -> pd.Series:
    """Stundenmittel nach Stunde 0–23."""
    if s.empty:
        return pd.Series(dtype=float)
    return s.groupby(s.index.hour).mean()


def station_label(station: str) -> str:
    """Lesbares Stationslabel für Plot-Titel."""
    return STATION_LABELS.get(station, station)


def main() -> None:
    print(
        f"Loading NEE from {FINAL_ESSD_DIR} "
        f"(full file span, QC < {QC_KEEP_LT})..."
    )
    all_diurnal: dict[str, pd.Series] = {}

    for station in STATIONS:
        nee = load_nee_series(station)
        if nee is None:
            print(f"  {station}: skip (no file or no NEE in final_datatables)")
            continue
        all_diurnal[station] = diurnal_hourly_mean(nee)
        print(f"  {station}: {nee.notna().sum()} half-hour points")

    if not all_diurnal:
        print("No data loaded.")
        return

    fig, axes = plt.subplots(2, 3, figsize=(9, 6), sharex=True, sharey=True)
    axes_flat = axes.flatten()

    for i, station in enumerate(STATIONS):
        ax = axes_flat[i]
        s = all_diurnal.get(station)
        if s is None or s.empty:
            ax.set_visible(False)
            continue
        ax.plot(
            s.index,
            s.values,
            color=NEE_LINE_STYLE["color"],
            ls=NEE_LINE_STYLE["ls"],
            linewidth=NEE_LINE_STYLE["lw"],
        )
        if i % 3 == 0:
            ax.set_ylabel(r"NEE [µmol m$^{-2}$ s$^{-1}$]", fontsize=FONTSIZE_AXIS)
        else:
            ax.set_ylabel("")
        ax.axhline(0, color="gray", linestyle=":", linewidth=0.5)
        ax.tick_params(labelsize=FONTSIZE_TICK)
        ax.grid(True, alpha=0.3)
        ax.set_title(station_label(station), fontsize=FONTSIZE_TITLE)
        ax.set_ylim(NEE_YLIM)

    x_major = [0, 6, 12, 18]
    for ax in axes_flat:
        if ax.get_visible():
            ax.set_xticks(x_major)

    for ax in axes_flat[3:]:
        if ax.get_visible():
            ax.set_xlabel("Hour", fontsize=FONTSIZE_AXIS)

    plt.tight_layout()

    out_path = Path(__file__).resolve().parent / "diurnal_nee_all_stations.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"\n✓ Plot saved: {out_path}")
    plt.show()


if __name__ == "__main__":
    main()
