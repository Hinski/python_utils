#!/usr/bin/env python3
"""
final_datatables (ESSD, 2 Headerzeilen, Komma-getrennt) → **PANGAEA-konforme** Tabellen.

Anforderungen (Auszug aus PANGAEA „How to prepare tabular Data“):
- **TAB-delimited**, **UTF-8**
- **Eine** Kopfzeile: voller Parametername **inkl. Einheit in eckigen Klammern**
- **Erste Spalte:** Event label (hier: Stationskurzname aus dem Dateinamen, z. B. ``Kayoro``)
- **Zweite Spalte:** 3. Geocode — hier **Höhe über Normalhöhennull** ``Height above sea level [m]``
  (pro Station konfigurierbar, sonst leer)
- **Zeit:** eigene Spalte mit **ISO-8601 in UTC** ``YYYY-MM-DDThh:mm:ss``
- Dateinamen ohne Leerzeichen → Ausgabe ``<Stationsname>_30min.tsv`` / ``*_daily.tsv``

Zusätzlich (Abgleich ESSD):
- **PA:** Quelle **kPa** → Werte **×10**, Kopfzeile **hPa**

Separate Metadaten (Campaign, Event mit Lat/Lon, Parameters/PI) sind bei PANGAEA **zusätzlich**
einzreichen — dieses Skript erzeugt nur die **Datentabelle**.

Beispiel::

  python convert_final_datatables_to_arctex_template.py \\
    --source-dir /Users/hingerl-l/Data/essd_data_tables/final_datatables \\
    --output-dir /Users/hingerl-l/Data/essd_data_tables/final_datatables_pangaea

  python convert_final_datatables_to_arctex_template.py \\
    --stations-meta /path/to/station_heights.json

``station_heights.json`` (optional): {\"Kayoro\": 195.0, \"Gorigo\": 168.0, ...}
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import pandas as pd

DEFAULT_SOURCE = Path("/Users/hingerl-l/Data/essd_data_tables/final_datatables")
DEFAULT_OUTPUT = Path("/Users/hingerl-l/Data/essd_data_tables/final_datatables_pangaea")

MISSING = (-9999, -99999, 7999)

# PANGAEA: ausführliche Parameterbezeichnung (Einheit kommt aus ESSD-Zeile 2 bzw. Sonderfall PA)
DISPLAY_NAME: dict[str, str] = {
    "LE": "Latent heat flux",
    "LE_QC": "Latent heat flux, quality flag",
    "H": "Sensible heat flux",
    "H_QC": "Sensible heat flux, quality flag",
    "NEE": "Net ecosystem exchange",
    "CO2_QC": "Net ecosystem exchange, quality flag",
    "TAU": "Momentum flux",
    "TAU_QC": "Momentum flux, quality flag",
    "G": "Soil heat flux",
    "SW_IN": "Short-wave radiation, incoming",
    "SW_OUT": "Short-wave radiation, outgoing",
    "LW_IN": "Long-wave radiation, incoming",
    "LW_OUT": "Long-wave radiation, outgoing",
    "NETRAD": "Net radiation",
    "P": "Precipitation amount",
    "ET": "Evapotranspiration",
    "PA": "Atmospheric pressure",
    "RH": "Humidity, relative",
    "TA": "Temperature, air",
    "VPD": "Vapor pressure deficit",
    "WD": "Wind direction",
    "WS": "Wind speed",
    "USTAR": "Friction velocity",
    "ZL": "Stability parameter z/L",
    "MO_LENGHT": "Obukhov length",
    "SWC_1_1_1": "Soil water content, horizon 1 sensor 1",
    "SWC_1_2_1": "Soil water content, horizon 2 sensor 1",
    "SWC_1_3_1": "Soil water content, horizon 3 sensor 1",
    "TS_1_1_1": "Soil temperature, horizon 1 sensor 1",
    "TS_1_2_1": "Soil temperature, horizon 2 sensor 1",
    "TS_1_3_1": "Soil temperature, horizon 3 sensor 1",
    "QC_wind_sector_kayoro": "Wind sector quality flag, Kayoro protocol",
}


def _normalize_unit_for_header(unit_raw: str) -> str:
    u = unit_raw.strip()
    fixes = {
        "adiemnsional": "adimensional",
        "deg C": "°C",
        "µmolCO2 m-2 s-1": "µmol CO2 m⁻² s⁻¹",
    }
    return fixes.get(u, u)


def _pangaea_header_for_var(col: str, unit_line: str) -> str:
    if col == "PA":
        u = "hPa"
    else:
        u = _normalize_unit_for_header(unit_line)
    long_name = DISPLAY_NAME.get(col, col.replace("_", " "))
    return f"{long_name} [{u}]"


def _event_label_from_path(path: Path) -> str:
    stem = path.stem
    for suf in ("_30min", "_daily"):
        if stem.endswith(suf):
            return stem[: -len(suf)]
    return stem


def _is_daily_file(path: Path) -> bool:
    return "daily" in path.name.lower()


def _read_essd(path: Path) -> tuple[list[str], list[str], pd.DataFrame]:
    with path.open(encoding="utf-8") as f:
        names = [c.strip() for c in next(csv.reader([f.readline()]))]
        units = [c.strip() for c in next(csv.reader([f.readline()]))]
    if len(names) != len(units):
        raise ValueError(f"{path}: ESSD Header uneinheitlich")
    na_list = list(MISSING) + ["-9999", "-9999.0", "-99999", "7999", "NAN", "nan", "NA"]
    df = pd.read_csv(
        path,
        skiprows=2,
        header=None,
        names=names,
        low_memory=False,
        na_values=na_list,
        keep_default_na=True,
    )
    return names, units, df


def _parse_ts(series: pd.Series, daily: bool) -> pd.Series:
    s = series.astype(str).str.strip()
    if daily:
        return pd.to_datetime(s, format="%Y%m%d", errors="coerce")
    return pd.to_datetime(s, format="%Y%m%d%H%M%S", errors="coerce")


def _pa_kpa_to_hpa(values: pd.Series) -> pd.Series:
    v = pd.to_numeric(values, errors="coerce")
    is_miss = v.isna()
    for m in MISSING:
        is_miss = is_miss | (v == float(m))
    out = v.where(is_miss, v * 10.0)
    return out.fillna(-9999.0)


def _numeric_series(s: pd.Series) -> pd.Series:
    col = pd.to_numeric(s, errors="coerce").fillna(-9999.0)
    for m in MISSING:
        col = col.mask(col == float(m), -9999.0)
    return col


def convert_file(
    src: Path,
    out: Path,
    *,
    station_elevations: dict[str, float | None],
    missing_empty: bool,
    dry_run: bool,
) -> None:
    names, units_line, df = _read_essd(src)
    if "TIMESTAMP" not in df.columns:
        raise ValueError(f"{src}: TIMESTAMP fehlt")

    daily = _is_daily_file(src)
    event = _event_label_from_path(src)
    elev = station_elevations.get(event)
    elev_str = "" if elev is None else f"{float(elev):.1f}"

    ts = _parse_ts(df["TIMESTAMP"], daily)
    time_iso = ts.dt.strftime("%Y-%m-%dT%H:%M:%S").where(ts.notna(), "")

    headers: list[str] = [
        "Event label [-]",
        "Height above sea level [m]",
        "Date/time [UTC]",
    ]
    cols_out: list[pd.Series] = [
        pd.Series([event] * len(df), dtype=object),
        pd.Series([elev_str] * len(df), dtype=object),
        time_iso,
    ]

    name_to_unit = dict(zip(names, units_line))

    for col in names:
        if col == "TIMESTAMP":
            continue
        headers.append(_pangaea_header_for_var(col, name_to_unit[col]))
        raw = df[col]
        if col == "PA":
            vals = _pa_kpa_to_hpa(raw)
        else:
            vals = _numeric_series(raw)
        if missing_empty:
            vmiss = pd.to_numeric(vals, errors="coerce")
            is_miss = vmiss.isna() | (vmiss == -9999.0) | (vmiss == -99999.0) | (vmiss == 7999.0)
            vals = vals.astype(object)
            vals.loc[is_miss.values] = ""
        cols_out.append(vals)

    out_df = pd.concat(cols_out, axis=1, ignore_index=True)
    out_df.columns = headers

    if dry_run:
        print(f"  [dry-run] {src.name} → {out.name} | rows={len(out_df)} cols={len(headers)} event={event!r}")
        return

    out.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out, sep="\t", index=False, encoding="utf-8", lineterminator="\n", na_rep="")


def _load_stations_meta(path: Path | None) -> dict[str, float | None]:
    if path is None or not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, float | None] = {}
    for k, v in data.items():
        if v is None or v == "":
            out[str(k)] = None
        else:
            out[str(k)] = float(v)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="final_datatables → PANGAEA TSV (UTF-8, TAB)")
    ap.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument(
        "--stations-meta",
        type=Path,
        default=None,
        help="JSON: {\"StationName\": Höhe_m, ...} für Height above sea level",
    )
    ap.add_argument("--glob", dest="glob_pat", default="*.csv")
    ap.add_argument("--missing-as-empty", action="store_true", help="Fehlwerte als leere Zelle statt -9999")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    elevations = _load_stations_meta(args.stations_meta)

    src_dir = args.source_dir
    if not src_dir.is_dir():
        raise SystemExit(f"Quellverzeichnis fehlt: {src_dir}")

    files = sorted(src_dir.glob(args.glob_pat))
    if not files:
        raise SystemExit(f"Keine Dateien: {src_dir}/{args.glob_pat}")

    out_dir = args.output_dir
    for path in files:
        if not path.name.lower().endswith(".csv"):
            continue
        if "_na9999" in path.stem:
            continue
        out_name = path.stem + ".tsv"
        out_path = out_dir / out_name
        try:
            convert_file(
                path,
                out_path,
                station_elevations=elevations,
                missing_empty=args.missing_as_empty,
                dry_run=args.dry_run,
            )
        except Exception as e:
            print(f"✗ {path.name}: {e}")
            continue
        if not args.dry_run:
            print(f"✓ {path.name} → {out_path}")

    print("Fertig.")


if __name__ == "__main__":
    main()
