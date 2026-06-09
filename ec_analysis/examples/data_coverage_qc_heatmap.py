"""
Datenabdeckung (Raw availability) über die Zeit.

Heatmap: x=Zeit (Monate), y=Station×Variable, Farbe=% verfügbar (nur NaN/invalid-Codes).

Datengrundlage (aktuell): {station}_essd_30min_clean.csv in Data/essd_data_tables
für P, NETRAD, LE, H, CO2 (NEE) und VWC (SWC_1_1_1).

Variablen (oben→unten): P, Rn, LE, H, CO2, θ (VWC)
Zeitraum: 01.01.2013 – 31.12.2025
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.transforms import blended_transform_factory
from mpl_toolkits.axes_grid1 import make_axes_locatable

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import yaml
except ImportError:
    yaml = None

try:
    from ec_analysis import load_ec_data
    from ec_analysis.data_loaders.variable_mapping import map_dataframe_columns, normalize_column_name
except ImportError:
    load_ec_data = None
    map_dataframe_columns = None
    normalize_column_name = None

DATA_DIR = Path("/Users/hingerl-l/Data/merged_long")
ESSD_DIR = Path("/Users/hingerl-l/Data/essd_data_tables")
DRAGAN_DATA_DIR = Path("/Users/hingerl-l/Diss/Data/ECdata_Dragan")
SUMBRUNGU_WASCAL_CSV = Path("/Users/hingerl-l/Diss/Data/WASCAL_EC_2012_2016/Sumbrungu_new.csv")

# ============================================================================
# KONFIGURATION
# ============================================================================
OUTPUT_BASE = Path("/Users/hingerl-l/Data")
STATIONS = ["Nazinga", "Kayoro", "Sumbrungu", "Gorigo", "Janga", "Mole"]
# Janga kann bei großen Datensätzen zu Speicherproblemen führen – ggf. temporär weglassen
STATIONS_SKIP: list[str] = []  # z.B. ["Janga","Mole"] bei Exit 134
QUALITY_FILTERS_CONFIG = Path(__file__).parent.parent / "ec_analysis" / "utils" / "quality_filters_config.yaml"

VARIABLES = ["P", "Rn", "LE", "H", "CO2", "VWC"]  # Reihenfolge: oben→unten; VWC wird als θ angezeigt
COVERAGE_START = pd.Timestamp("2013-01-01")
COVERAGE_END = pd.Timestamp("2025-12-31")

# Station-spezifische Lücken: Bereiche auf NaN setzen (fehlerhafte/fehlende Messungen)
NAZINGA_EMPTY_FROM = pd.Period("2022-04", freq="M")   # Nazinga nur bis einschl. März 2022
GORIGO_START = pd.Period("2017-05", freq="M")         # Gorigo erst ab Mai 2017
GORIGO_EMPTY_FROM = pd.Period("2024-09", freq="M")    # Gorigo nur bis einschl. August 2022
KAYORO_EMPTY_FROM = pd.Period("2025-09", freq="M")    # Kayoro nur bis einschl. August 2025
SUMBRUNGU_EMPTY_FROM = pd.Period("2016-03", freq="M") # Sumbrungu nur bis einschl. Februar 2016

# Overlay-Boxen: leicht durchsichtige weiße Rechtecke mit Text über definierten Bereichen
# period_end=None = bis Ende der Heatmap
HEATMAP_ANNOTATIONS: list[dict] = [
    {"station": "Nazinga", "period_start": "2022-04", "period_end": None, "text": "n.a."},
    {"station": "Kayoro", "period_start": "2025-10", "period_end": None, "text": "n.p."},
    {"station": "Sumbrungu", "period_start": "2016-03", "period_end": '2021-12', "text": "measurement disruption due to vandalism"},
    {"station": "Gorigo", "period_start": "2013-01", "period_end": '2017-04', "text": "relocation of Sumbrungu station"},
    {"station": "Gorigo", "period_start": "2024-09", "period_end": None, "text": "n.p."},
    {"station": "Janga", "period_start": "2025-03", "period_end": None, "text": "n.p."},
    {"station": "Nazinga", "period_start": "2017-07", "period_end": "2019-03", "text": "n.a."},
]

VWC_COLS = ["SWC_1_1_1"]  # ESSD: oberste Bodenschicht als VWC-Proxy

RAD_ALIASES = {
    "SW_in": ["SW_in", "SR_in_Avg", "SW_IN"],
    "SW_out": ["SW_out", "SR_out_Avg", "SW_OUT"],
    "LW_in": ["LW_in", "IR_in_Avg", "LW_IN"],
    "LW_out": ["LW_out", "IR_out_Avg", "LW_OUT"],
}


def _get_col(df: pd.DataFrame, aliases: list[str]) -> str | None:
    for a in aliases:
        if a in df.columns:
            return a
    return None


def load_essd_clean(station: str) -> pd.DataFrame | None:
    """
    Läd {station}_essd_30min_clean.csv aus ESSD_DIR.
    Index = Timestamp, Spalten = ESSD-Variablen. Fehlwerte (-9999, etc.) → NaN.
    """
    path = ESSD_DIR / f"{station}_essd_30min_clean.csv"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        header_line = f.readline().strip()
        units_line = f.readline().strip()
    var_names = [c.strip() for c in header_line.split(",")]
    df = pd.read_csv(
        path,
        skiprows=2,
        header=None,
        names=var_names,
        low_memory=False,
        na_values=[-9999, "-9999.0", "-99999", "7999", "nan", "NAN"],
    )
    if "TIMESTAMP" not in df.columns or df["TIMESTAMP"].empty:
        return None
    ts = pd.to_datetime(df["TIMESTAMP"], format="%Y%m%d%H%M%S", errors="coerce")
    df = df.drop(columns=["TIMESTAMP"])
    df.index = ts
    df = df[df.index.notna()].sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


def _load_pre2016_p_from_wascal() -> pd.Series | None:
    """Lädt P_tb aus Sumbrungu WASCAL (wie collect_all_variables_30min)."""
    if load_ec_data is None or map_dataframe_columns is None:
        return None
    if not SUMBRUNGU_WASCAL_CSV.exists():
        return None
    cutoff = pd.Timestamp("2016-01-01")
    try:
        df = pd.read_csv(
            SUMBRUNGU_WASCAL_CSV,
            sep=",",
            low_memory=False,
            na_values=["NAN", "NA", "-9999", "-9999.0", "-999", "**************"],
        )
        if "T_begin" not in df.columns:
            return None
        df["T_begin"] = pd.to_datetime(df["T_begin"], format="%d/%m/%y %H:%M", errors="coerce")
        df = df.set_index("T_begin")
        df = df[df.index.notna()].sort_index()
        df = df[~df.index.duplicated(keep="first")]
        df_pre = df[df.index < cutoff]
        if df_pre.empty:
            return None
        rename = {}
        for col in df_pre.columns:
            new = str(col).strip()
            for suffix in (" [mm]", " [mm/10 min]", " [hits/10 min]", " [DegC]", " [W/m^2]", " [W/m_]", " [usec]"):
                if suffix in new:
                    new = new.replace(suffix, "").strip()
            if " tipping buckt" in new:
                new = new.replace(" tipping buckt", "")
            if new.endswith("_Ost_Avg"):
                new = new.replace("_Ost_Avg", "_East_Avg")
            elif new.endswith("_Mitte_Avg"):
                new = new.replace("_Mitte_Avg", "_Middle_Avg")
            if new != col:
                rename[col] = new
        if rename:
            df_pre = df_pre.rename(columns=rename)
        precip_pat = ("Rain_mm_Tot", "Acc_RT_NRT", "Acc_NRT", "Bucket_RT", "Bucket_NRT", "Ramount_Tot", "Hamount_Tot")
        cols = [c for c in df_pre.columns if any(p in str(c) for p in precip_pat)]
        if not cols:
            return None
        df_sub = df_pre[[c for c in cols if c in df_pre.columns]].copy()
        map_dataframe_columns(df_sub, inplace=True)
        if "P_tb" not in df_sub.columns:
            return None
        s = pd.to_numeric(df_sub["P_tb"], errors="coerce")
        return s if s.notna().any() else None
    except Exception:
        return None


def _load_pre2016_p_from_merged_long(station: str, p_col: str) -> pd.Series | None:
    """Lädt P aus merged_long parquet für pre-2016 – nur primäre Quelle, kein combine."""
    if load_ec_data is None or map_dataframe_columns is None or normalize_column_name is None:
        return None
    cutoff = pd.Timestamp("2016-01-01")
    for name in ("cr1000", "radiation"):
        path = DATA_DIR / f"{station}_{name}_merged_long.parquet"
        if not path.exists():
            continue
        try:
            df = load_ec_data(path)
            if df is None or df.empty:
                continue
            df_pre = df[df.index < cutoff]
            if df_pre.empty:
                continue
            for c in df_pre.columns:
                std = normalize_column_name(str(c).strip())
                if std == p_col:
                    s = pd.to_numeric(df_pre[c], errors="coerce")
                    if s.notna().any():
                        return s
            return None
        except Exception:
            continue
    return None


def _load_post2016_p_from_parquet(station: str, p_col: str) -> pd.Series | None:
    """Lädt P aus parquet für post-2016 – nur primäre Quelle."""
    if load_ec_data is None or map_dataframe_columns is None or normalize_column_name is None:
        return None
    cutoff = pd.Timestamp("2016-01-01")
    paths = []
    if station in ("Kayoro", "Nazinga", "Sumbrungu"):
        paths = [DATA_DIR / f"{station}_cr1000_merged_long.parquet", DATA_DIR / f"{station}_radiation_merged_long.parquet"]
    elif station == "Gorigo":
        paths = [OUTPUT_BASE / station / "merged" / f"{station}_cr1000_merged.csv", DATA_DIR / f"{station}_radiation_merged_long.parquet"]
    elif station == "Janga":
        paths = [OUTPUT_BASE / station / "raw" / "CR6Janga_Public.dat"]
    elif station == "Mole":
        paths = [OUTPUT_BASE / station / "raw" / "cr1000" / "CR1000XMole_Ground1.dat"]
    else:
        paths = [DATA_DIR / f"{station}_cr1000_merged_long.parquet", DATA_DIR / f"{station}_radiation_merged_long.parquet"]
    for path in paths:
        if not path.exists():
            continue
        try:
            df = load_ec_data(path, format="toa5" if path.suffix == ".dat" else None)
            if df is None or df.empty:
                continue
            map_dataframe_columns(df, inplace=True)
            if p_col not in df.columns:
                rain_col = "Rain_mm_Tot" if station == "Mole" else None
                if rain_col and rain_col in df.columns:
                    s = pd.to_numeric(df[rain_col], errors="coerce")
                else:
                    continue
            else:
                s = pd.to_numeric(df[p_col], errors="coerce")
            s = s[s.index >= cutoff]
            if s.notna().any():
                return s
        except Exception:
            continue
    return None


def load_primary_p_series(station: str) -> pd.Series | None:
    """
    Lädt P ausschließlich aus der primären Quelle (wie event_scale_water_balance).
    Kein combine_first – Lücken bleiben NaN → realistische Abdeckung.
    """
    # Diese Funktion wird im ESSD-Modus nicht mehr verwendet; Platzhalter
    if station == "Mole":
        path = OUTPUT_BASE / station / "raw" / "cr1000" / "CR1000XMole_Ground1.dat"
        if path.exists() and load_ec_data:
            try:
                df = load_ec_data(path, format="toa5")
                if df is not None and "Rain_mm_Tot" in df.columns:
                    s = pd.to_numeric(df["Rain_mm_Tot"], errors="coerce")
                else:
                    s = None
            except Exception:
                s = None
        else:
            s = None
    else:
        # Im ESSD-Modus wird load_primary_p_series nicht mehr verwendet.
        s = None
    if s is None or s.empty:
        return None

    def _resample_p(s: pd.Series) -> pd.Series:
        """Resample P: sum nur wenn alle Werte im Slot gemessen (kein NaN), sonst NaN."""
        def slot_sum(x: pd.Series) -> float:
            if x.isna().any():
                return np.nan
            return float(x.sum())
        try:
            return s.resample("30min", origin="start_day").apply(slot_sum)
        except Exception:
            return s.resample("30min").apply(slot_sum)

    resampled = _resample_p(s)
    invalid = [7999, -9999, -99999]
    for v in invalid:
        resampled = resampled.replace(v, np.nan)
    return resampled


def apply_invalid_codes_only(df: pd.DataFrame) -> pd.DataFrame:
    """Ersetzt nur invalid_codes durch NaN (raw availability)."""
    if yaml is None or not QUALITY_FILTERS_CONFIG.exists():
        return df
    df = df.copy()
    with QUALITY_FILTERS_CONFIG.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    invalid_codes = cfg.get("global", {}).get("invalid_codes", [7999, -9999, -99999])
    for c in invalid_codes:
        if isinstance(c, (int, float)):
            df = df.replace(c, np.nan)
    if "NAN" in str(invalid_codes):
        df = df.replace(["NAN", "nan"], np.nan)
    return df


def apply_quality_filters(df: pd.DataFrame, station: str) -> pd.DataFrame:
    """Wendet QC-Flags und physical_limits aus quality_filters_config.yaml an."""
    if yaml is None or not QUALITY_FILTERS_CONFIG.exists():
        return df
    df = df.copy()
    with QUALITY_FILTERS_CONFIG.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    global_cfg = cfg.get("global", {})
    station_cfg = cfg.get("stations", {}).get(station, {})

    invalid_codes = global_cfg.get("invalid_codes", [7999, -9999, -99999])
    for c in invalid_codes:
        if isinstance(c, (int, float)):
            df = df.replace(c, np.nan)

    for item in station_cfg.get("quality_flags", []):
        flag_col = item.get("flag")
        data_col = item.get("data_column")
        max_flag = item.get("max_flag", 1)
        if not flag_col or not data_col or flag_col not in df.columns or data_col not in df.columns:
            continue
        qc = pd.to_numeric(df[flag_col], errors="coerce")
        bad = (qc > max_flag) | qc.isna()
        df.loc[bad, data_col] = np.nan

    global_limits = global_cfg.get("physical_limits", {})
    station_limits = station_cfg.get("physical_limits") or {}
    merged = {**global_limits, **station_limits}
    for col in list(merged.keys()):
        if col not in df.columns or not isinstance(merged[col], dict):
            continue
        lim = merged[col]
        vmin, vmax = lim.get("min"), lim.get("max")
        if vmin is None and vmax is None:
            continue
        vals = pd.to_numeric(df[col], errors="coerce")
        mask = vals.notna()
        if vmin is not None:
            mask = mask & (vals >= vmin)
        if vmax is not None:
            mask = mask & (vals <= vmax)
        df.loc[~mask, col] = np.nan

    return df


def get_variable_series(df: pd.DataFrame, station: str, var: str) -> pd.Series | None:
    """Liefert die Datenreihe für eine Variable nach QC/limits."""
    if var == "P":
        # ESSD: es gibt genau eine P-Spalte
        if "P" not in df.columns:
            return None
        return pd.to_numeric(df["P"], errors="coerce")
    if var == "CO2":
        # ESSD: CO2-Flux heißt NEE
        if "NEE" in df.columns:
            return pd.to_numeric(df["NEE"], errors="coerce")
        return None
    if var == "VWC":
        for c in VWC_COLS:
            if c in df.columns:
                s = pd.to_numeric(df[c], errors="coerce")
                if s.notna().any():
                    return s
        return None
    if var == "Rn":
        # ESSD: NETRAD ist die Nettostrahlung
        if "NETRAD" in df.columns:
            return pd.to_numeric(df["NETRAD"], errors="coerce")
        if "Rn" in df.columns:
            return pd.to_numeric(df["Rn"], errors="coerce")
        return None
    if var in df.columns:
        return pd.to_numeric(df[var], errors="coerce")
    return None


def compute_monthly_pct_valid(station: str, apply_qc: bool = True) -> pd.DataFrame:
    """
    Berechnet % gültig pro Variable und Monat.
    apply_qc=False: Raw availability (nur invalid_codes).
    apply_qc=True: Post-QC (QC-Flags + physical_limits).
    Returns: DataFrame mit Index=Variable, Spalten=Period[M].
    """
    # Für die ESSD-basierte Abdeckung nutzen wir die bereits gereinigten
    # *_essd_30min_clean.csv Dateien. apply_qc-Flag ist hier wirkungslos,
    # da QC/Masks/Limits schon in den Clean-Dateien stecken.
    df = load_essd_clean(station)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.sort_index()
    monthly_count = df.resample("MS").size()
    monthly_count.index = monthly_count.index.to_period("M")

    rows = {}
    for var in VARIABLES:
        s = get_variable_series(df, station, var)
        if s is None or s.empty:
            rows[var] = pd.Series(np.nan, index=monthly_count.index)
            continue
        valid_monthly = s.notna().resample("MS").sum()
        valid_monthly.index = valid_monthly.index.to_period("M")
        pct = valid_monthly / monthly_count * 100
        pct = pct.replace([np.inf, -np.inf], np.nan)
        rows[var] = pct.reindex(monthly_count.index)
    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows)
    return result


def _build_heatmap_df(
    station_data: dict[str, pd.DataFrame],
    all_months: list[pd.Period],
) -> pd.DataFrame:
    """Baut Heatmap-DataFrame: Zeilen = Station×Variable (gruppiert), Spalten = Monate."""
    rows = [(s, v) for s in STATIONS if s not in STATIONS_SKIP for v in VARIABLES]
    heatmap_df = pd.DataFrame(
        index=pd.MultiIndex.from_tuples(rows, names=["Station", "Variable"]),
        columns=all_months,
        dtype=float,
    )
    for station, monthly in station_data.items():
        for var in monthly.columns:
            if var not in VARIABLES:
                continue
            for period in all_months:
                if period in monthly.index:
                    heatmap_df.loc[(station, var), period] = monthly.loc[period, var]
    return heatmap_df


def _apply_station_gaps(heatmap_df: pd.DataFrame) -> pd.DataFrame:
    """
    Setzt bekannte Lücken auf NaN:
    - Nazinga: nur bis März 2022
    - Gorigo: erst ab Mai 2017, nur bis August 2022
    - Kayoro: nur bis August 2025
    - Sumbrungu: nur bis Februar 2016
    """
    df = heatmap_df.copy()
    stations_used = [s for s in STATIONS if s not in STATIONS_SKIP]
    for station in stations_used:
        for period in df.columns:
            if station == "Nazinga" and period >= NAZINGA_EMPTY_FROM:
                for var in VARIABLES:
                    df.loc[(station, var), period] = np.nan
            elif station == "Gorigo" and (period < GORIGO_START or period >= GORIGO_EMPTY_FROM):
                for var in VARIABLES:
                    df.loc[(station, var), period] = np.nan
            elif station == "Kayoro" and period >= KAYORO_EMPTY_FROM:
                for var in VARIABLES:
                    df.loc[(station, var), period] = np.nan
            elif station == "Sumbrungu" and period >= SUMBRUNGU_EMPTY_FROM:
                for var in VARIABLES:
                    df.loc[(station, var), period] = np.nan
    return df


LABEL_FONTSIZE = 11


def _plot_heatmap_panel(
    ax: plt.Axes,
    heatmap_df: pd.DataFrame,
    cmap_name: str = "cividis",
):
    """Zeichnet eine Heatmap mit Station-Blöcken, ausgedünnten X-Ticks, NaN=grau."""
    data = heatmap_df.values.astype(float)
    data = np.ma.masked_invalid(data)

    cmap = plt.get_cmap(cmap_name).copy()
    cmap.set_bad(color="lightgray", alpha=0.7)
    im = ax.imshow(
        data,
        aspect="auto",
        cmap=cmap,
        vmin=0,
        vmax=100,
        interpolation="nearest",
    )

    n_rows, n_cols = data.shape
    n_vars = len(VARIABLES)
    stations_used = [s for s in STATIONS if s not in STATIONS_SKIP]

    # Y-Ticks: Variablennamen (VWC → θ)
    var_labels = [heatmap_df.index.get_level_values("Variable")[i] for i in range(n_rows)]
    var_labels = ["θ" if v == "VWC" else v for v in var_labels]
    ax.set_yticks(np.arange(n_rows))
    ax.set_yticklabels(var_labels, fontsize=LABEL_FONTSIZE)
    # Horizontale Linien: dünn zwischen Variablen, dick zwischen Stationen
    for i in range(n_rows + 1):
        y = i - 0.5
        lw = 2 if (i == 0 or i == n_rows or (i > 0 and i % n_vars == 0)) else 0.5
        ax.axhline(y, color="black", linewidth=lw)

    # Station-Labels links (etwas Abstand zum Plot)
    divider = make_axes_locatable(ax)
    ax_stations = divider.append_axes("left", size="10%", pad=0.5)
    ax_stations.set_xlim(0, 1)
    ax_stations.set_ylim(ax.get_ylim())
    ax_stations.axis("off")
    for i, station in enumerate(stations_used):
        center = i * n_vars + (n_vars - 1) / 2
        ax_stations.text(1, center, station, ha="right", va="center", fontsize=LABEL_FONTSIZE, fontweight="bold", rotation=90)

    # X-Ticks: genau an 01.01. jedes Jahres (= an den vertikalen Gitterlinien)
    xtick_positions = []
    xtick_labels = []
    for j, period in enumerate(heatmap_df.columns):
        if period.month == 1:
            xtick_positions.append(j - 0.5)
            xtick_labels.append(str(period.year))
    ax.set_xticks(xtick_positions)
    ax.set_xticklabels(xtick_labels, rotation=0, ha="center", fontsize=LABEL_FONTSIZE)
    # Vertikale Linien bei Jahreswechsel
    prev_year = None
    for j, period in enumerate(heatmap_df.columns):
        yr = period.year
        if prev_year is not None and yr != prev_year:
            ax.axvline(j - 0.5, color="gray", linestyle="-", linewidth=0.8, alpha=0.7)
        prev_year = yr

    # Phasen-Grenzen: 01.01.2016 und 01.01.2022 (vertikale Linien über gesamten Plot, leicht nach oben hinaus)
    phase_breaks = [
        pd.Period("2016-01", freq="M"),
        pd.Period("2022-01", freq="M"),
    ]
    phase_positions = []
    for p_break in phase_breaks:
        if p_break in heatmap_df.columns:
            j = heatmap_df.columns.get_loc(p_break)
            # Linie an der linken Kante des entsprechenden Monats
            phase_positions.append(j - 0.5)

    if phase_positions:
        phase_positions = sorted(phase_positions)
        y0, y1 = ax.get_ylim()
        y_bottom, y_top = (y0, y1) if y0 < y1 else (y1, y0)
        # Bei imshow(origin='upper') ist die obere Plotkante der kleinere Y-Wert
        y_plot_top = y_bottom   # obere Kante in Datenkoordinaten
        # Linien zeichnen über den gesamten Plot (ohne Überstand), etwas dicker
        for x in phase_positions:
            ax.vlines(
                x,
                y_bottom,
                y_top,
                colors="black",
                linewidth=2.5,
                alpha=0.9,
                clip_on=True,
            )

        # Tickmarks außerhalb des Plots (oberhalb): X in Daten-, Y in Achsenkoordinaten
        trans = blended_transform_factory(ax.transData, ax.transAxes)
        for x in phase_positions:
            ax.vlines(
                x,
                1.0,
                1.04,
                colors="black",
                linewidth=2.5,
                alpha=0.9,
                transform=trans,
                clip_on=False,
            )

        # Phasen-Beschriftung knapp oberhalb des Plots (in Axes-Koordinaten)
        x_start = -0.5
        x_end = len(heatmap_df.columns) - 0.5
        segments = [
            (x_start, phase_positions[0], "Phase I"),
            (phase_positions[0], phase_positions[1] if len(phase_positions) > 1 else x_end, "Consolidation Phase"),
            (phase_positions[1] if len(phase_positions) > 1 else phase_positions[0], x_end, "Phase II"),
        ]
        for x0, x1, label in segments:
            x_center_data = (x0 + x1) / 2.0
            # In relative Axes-Koordinaten (0–1) umrechnen
            x_frac = (x_center_data - x_start) / (x_end - x_start) if x_end != x_start else 0.5
            ax.text(
                x_frac,
                1.02,  # näher an den Plot heran
                label,
                transform=ax.transAxes,
                ha="center",
                va="bottom",
                fontsize=LABEL_FONTSIZE,
                fontweight="bold",
                clip_on=False,
            )

    # Overlay: durchsichtige weiße Boxen mit Text über definierten Bereichen
    for anno in HEATMAP_ANNOTATIONS:
        station = anno["station"]
        if station not in stations_used:
            continue
        i = stations_used.index(station)
        p_start = pd.Period(anno["period_start"], freq="M")
        cols = heatmap_df.columns
        j_start = None
        for j, p in enumerate(cols):
            if p >= p_start:
                j_start = j
                break
        if j_start is None:
            continue
        if anno["period_end"] is None:
            j_end = len(cols) - 1
        else:
            p_end = pd.Period(anno["period_end"], freq="M")
            j_end = None
            for j in range(len(cols) - 1, -1, -1):
                if cols[j] <= p_end:
                    j_end = j
                    break
            if j_end is None:
                continue
        xmin = j_start - 0.5
        xmax = j_end + 0.5
        ymin = i * n_vars - 0.5
        ymax = (i + 1) * n_vars - 0.5
        rect = Rectangle(
            (xmin, ymin),
            width=xmax - xmin,
            height=ymax - ymin,
            facecolor="white",
            alpha=0.75,
            edgecolor="none",
        )
        ax.add_patch(rect)
        ax.text(
            (xmin + xmax) / 2,
            (ymin + ymax) / 2,
            anno["text"],
            ha="center",
            va="center",
            fontsize=LABEL_FONTSIZE,
            fontweight="bold",
        )

    return im


def main() -> None:
    print("Datenabdeckung (Raw availability)")
    print("=" * 45)
    station_data_raw: dict[str, pd.DataFrame] = {}
    all_months: set[pd.Period] = set()

    for station in STATIONS:
        if station in STATIONS_SKIP:
            print(f"  {station}... übersprungen")
            continue
        print(f"  {station}...", end=" ", flush=True)
        try:
            raw = compute_monthly_pct_valid(station, apply_qc=False)
        except Exception as e:
            print(f"Fehler: {e}")
            continue
        if raw.empty:
            print("keine Daten")
            continue
        station_data_raw[station] = raw
        all_months.update(raw.index.tolist())
        print(f"ok")

    if not all_months:
        print("Keine Daten gefunden.")
        return

    # Zeitfenster: 01.01.2013 – 31.12.2025
    p_start = pd.Period(COVERAGE_START, freq="M")
    p_end = pd.Period(COVERAGE_END, freq="M")
    months_sorted = sorted(p for p in all_months if p_start <= p <= p_end)
    if not months_sorted:
        print("Keine Monate im Zeitfenster 2013–2025.")
        return

    heatmap_raw = _build_heatmap_df(station_data_raw, months_sorted)
    heatmap_raw = _apply_station_gaps(heatmap_raw)
    heatmap_raw = heatmap_raw.dropna(how="all", axis=0).dropna(how="all", axis=1)

    if heatmap_raw.empty:
        print("Keine gültigen Daten für Heatmap.")
        return

    fig, ax = plt.subplots(1, 1, figsize=(14, 10))
    im = _plot_heatmap_panel(ax, heatmap_raw, "cividis")
    cbar_ax = fig.add_axes([0.92, 0.15, 0.02, 0.7])
    cbar = fig.colorbar(im, cax=cbar_ax)
    cbar.set_label("%", fontsize=LABEL_FONTSIZE)
    cbar.ax.tick_params(labelsize=LABEL_FONTSIZE)
    fig.subplots_adjust(left=0.08, right=0.88, top=0.94, bottom=0.12)
    out_path = Path("data_coverage_qc_heatmap.png")
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"\n✓ Gespeichert: {out_path}")


if __name__ == "__main__":
    main()
