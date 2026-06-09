#!/usr/bin/env python3
"""
ERA5-Reanalyse-Niederschlag für Gorigo & Janga: Lädt ERA5, füllt P-Lücken in den
final_datatables **nur im Arbeitsspeicher** und gibt den **mittleren Jahresniederschlag**
(mm/a) je Station aus — **keine** abgespeicherten Zeitreihen.

Voraussetzungen
---------------
  pip install cdsapi xarray netCDF4

  (Dask ist nicht nötig — ``open_dataset(..., chunks=None)`` vermeidet den Chunk-
  Manager; ``chunks=False`` würde in xarray 2026+ weiterhin Dask anfordern.)

  ~/.cdsapirc (CDS API Key), siehe:
  https://cds.climate.copernicus.eu/how-to-api

Verwendung
----------
  python fill_precip_gorigo_janga_era5.py

MAP: bevorzugt aus der **30-Min**-Datei (wenn vorhanden), sonst aus der **Tagesdatei**;
     Jahressummen aus der ERA5-gefüllten P-Spalte, Mittelwert über Jahre.

ERA5 ``total_precipitation``: in m; Standard ist De-Akkumulation zu mm/h (Copernicus/ECMWF),
  sonst nur ×1000 (--no-era5-tp-deaccum). Je 30-Min-Zeile: Hälfte der UTC-Stundenrate.

Mittlerer Jahresniederschlag: **Janga** nur aus **2022–2024**, **Gorigo** alle Datenjahre
  (Konstante ``STATION_MAP_YEARS``). Zusätzlich: Zeile „nur Mess-P“ = Lücken fließen in
  Tages-/Jahressummen nicht ein (Vergleich zum ERA5-gefüllten Mittel).

Koordinaten-Defaults — mit ESSD/Standort abgleichen
(``--lat-gorigo`` / ``--lon-gorigo`` / ``--lat-janga`` / ``--lon-janga``).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import cdsapi
except ImportError:
    cdsapi = None
try:
    import xarray as xr
except ImportError:
    xr = None

FINAL_DATATABLES = Path("/Users/hingerl-l/Data/essd_data_tables/final_datatables")
DEFAULT_CACHE = Path("/Users/hingerl-l/Data/era5_cache_tp")

STATION_LATLON_DEFAULT = {
    "Gorigo": (10.936, -0.824),
    "Janga": (10.13, -0.884),
}

MISSING_SENTINELS = [-9999, -99999, 7999]
TARGET_STATIONS = ("Gorigo", "Janga")

# Mittlerer Jahresniederschlag: nur diese Jahre einbeziehen (None = alle Jahre mit Daten)
STATION_MAP_YEARS: dict[str, frozenset[int] | None] = {
    "Gorigo": None,
    "Janga": frozenset({2022, 2023, 2024}),
}


def _read_essd_csv(path: Path) -> tuple[list[str], pd.DataFrame]:
    with path.open("r", encoding="utf-8") as f:
        h0 = f.readline().strip()
        h1 = f.readline().strip()
    names = [c.strip() for c in h0.split(",")]
    na_list = [-9999, "-9999", "-9999.0", -99999, "7999", "NAN", "nan", "NA"]
    df = pd.read_csv(path, skiprows=2, header=None, names=names, low_memory=False, na_values=na_list)
    return [h0, h1], df


def _parse_ts(series: pd.Series, daily: bool) -> pd.DatetimeIndex:
    s = series.astype(str).str.strip()
    if daily:
        parsed = pd.to_datetime(s, format="%Y%m%d", errors="coerce")
    else:
        parsed = pd.to_datetime(s, format="%Y%m%d%H%M%S", errors="coerce")
    # to_datetime auf Series → Series; für .year brauchen wir DatetimeIndex
    return pd.DatetimeIndex(parsed)


def _lon_era5(lon_deg: float) -> float:
    if lon_deg < 0:
        return 360.0 + lon_deg
    return lon_deg


def _cds_area(lat: float, lon: float, pad: float = 0.25) -> list[float]:
    north = min(lat + pad, 90.0)
    south = max(lat - pad, -90.0)
    west = lon - pad
    east = lon + pad
    return [north, west, south, east]


def _era5_tp_m_to_hourly_mm(series_m: pd.Series, deaccumulate: bool) -> pd.Series:
    """
    CDS ``total_precipitation`` ist in Metern; oft **akkumuliert** entlang der Zeit,
    dann liefert ``diff`` die Stundenmenge (mm). Bei negativem Sprung (Reset) wird
    der neue Stufenwert als Stundenanteil genutzt — vgl. ECMWF/ Copernicus-Hinweise
    zur De-Akkumulation von ``tp``.

    Wenn ``deaccumulate=False`` oder die Serie wie bereits-dekumulierte Stufen
    aussieht, bleibt es bei ``* 1000`` (m → mm pro Stufe als mm/Stunde).
    """
    s = pd.to_numeric(series_m, errors="coerce").sort_index()
    s_mm = (s * 1000.0).astype(float)
    if not deaccumulate or len(s_mm) < 2:
        return s_mm

    inc = s_mm.diff()
    med = float(np.nanmedian(inc.iloc[1:])) if inc.notna().any() else 0.0
    pos_share = float((inc.iloc[1:] > 0).mean()) if len(inc) > 1 else 0.0
    # Bereits „Stufenweise Niederschlag“: viele Werte ~0, Diff wechselt oft Vorzeichen ohne Tages-Akkumulation
    looks_hourly_independent = med >= 0 and pos_share < 0.45 and (s_mm.quantile(0.95) < 5.0)
    if looks_hourly_independent:
        return s_mm

    hourly = inc.copy()
    neg = hourly < 0
    hourly.loc[neg] = s_mm.loc[neg]
    if len(hourly) and pd.isna(hourly.iloc[0]):
        hourly.iloc[0] = s_mm.iloc[0]
    return hourly.clip(lower=0.0)


def _era5_time_dim(ds: xr.Dataset) -> str:
    """Zeitdimension in CDS-ERA5-NetCDF (meist ``valid_time`` oder ``time``)."""
    for name in ("valid_time", "time", "forecast_time"):
        if name in ds.dims:
            return name
    raise ValueError(
        f"Keine bekannte Zeitdimension in NetCDF: dims={dict(ds.sizes)} coords={list(ds.coords)}"
    )


def load_era5_tp_timeseries(
    lat: float,
    lon: float,
    nc_paths: list[Path],
    *,
    deaccumulate_tp: bool = True,
) -> pd.Series:
    """tp in mm pro Stunde, Index UTC."""
    if xr is None:
        raise RuntimeError("xarray fehlt (pip install xarray netCDF4)")
    existing = [p for p in sorted(nc_paths) if p.exists()]
    if not existing:
        raise FileNotFoundError("Keine ERA5-NetCDF-Dateien gefunden (Download fehlgeschlagen?)")

    # xarray 2026+: ``chunks=False`` triggert trotzdem _chunk_ds (Dask). ``chunks=None`` nicht.
    # ``open_mfdataset`` kann auch ohne Dask fehlschlagen — daher Dateien einzeln öffnen.
    open_kw: dict = {"engine": "netcdf4", "chunks": None}
    pieces: list[xr.Dataset] = []
    try:
        for path in existing:
            with xr.open_dataset(path, **open_kw) as part:
                pieces.append(part.load())

        if len(pieces) == 1:
            ds = pieces[0]
        else:
            tdim = _era5_time_dim(pieces[0])
            ds = xr.concat(
                pieces,
                dim=tdim,
                data_vars="minimal",
                coords="minimal",
                compat="override",
            )

        if "tp" not in ds:
            raise ValueError(f"Variable 'tp' fehlt: {list(ds.data_vars)}")
        sub = ds["tp"].sel(latitude=lat, longitude=_lon_era5(lon), method="nearest")
        series = sub.to_series()
        series.index = pd.to_datetime(series.index).tz_localize(None)
        series = series.sort_index()
        series = _era5_tp_m_to_hourly_mm(series, deaccumulate=deaccumulate_tp)
        series.name = "tp_mm_per_hour"
        return series
    finally:
        for p in pieces:
            p.close()


def era5_tp_to_30min_mm(idx: pd.DatetimeIndex, tp_hourly_mm: pd.Series) -> np.ndarray:
    idx = pd.DatetimeIndex(idx).tz_localize(None)
    floor_h = idx.floor("h")
    hourly = tp_hourly_mm.copy()
    hourly.index = pd.DatetimeIndex(hourly.index).tz_localize(None)
    v = hourly.reindex(floor_h).to_numpy(dtype=float) / 2.0
    return v


def era5_tp_to_daily_mm(dates: pd.DatetimeIndex, tp_hourly_mm: pd.Series) -> np.ndarray:
    hourly = tp_hourly_mm.copy()
    hourly.index = pd.DatetimeIndex(hourly.index).tz_localize(None)
    daily_sum = hourly.resample("D").sum()
    d_norm = pd.to_datetime(dates).normalize()
    aligned = daily_sum.reindex(d_norm)
    return aligned.to_numpy(dtype=float)


def filled_p_array(df: pd.DataFrame, fill_mm: np.ndarray) -> np.ndarray:
    if "P" not in df.columns:
        raise ValueError("Spalte P fehlt")
    if len(fill_mm) != len(df):
        raise ValueError("Länge fill_mm passt nicht zum DataFrame")
    p = pd.to_numeric(df["P"], errors="coerce")
    for s in MISSING_SENTINELS:
        p = p.mask(p == float(s), np.nan)
    missing = p.isna()
    arr_p = p.to_numpy(dtype=float, copy=True)
    m = missing.to_numpy()
    use = m & np.isfinite(fill_mm)
    arr_p[use] = fill_mm[use]
    arr_p[m & ~np.isfinite(arr_p)] = -9999.0
    return arr_p


def mean_annual_from_30min(
    ts: pd.DatetimeIndex,
    p_mm: np.ndarray | pd.Series,
    years_include: frozenset[int] | set[int] | None = None,
) -> float:
    ts = pd.DatetimeIndex(ts).tz_localize(None)
    vals = p_mm.to_numpy(dtype=float) if hasattr(p_mm, "to_numpy") else np.asarray(p_mm, dtype=float)
    s = pd.Series(vals, index=ts)
    for sen in MISSING_SENTINELS:
        s = s.mask(s == float(sen), np.nan)
    daily = s.resample("D").sum(min_count=1)
    yearly = daily.groupby(daily.index.year).sum(min_count=1).dropna()
    if years_include is not None:
        yearly = yearly.loc[yearly.index.isin(list(years_include))]
    if yearly.empty:
        return float("nan")
    return float(yearly.mean())


def mean_annual_from_daily(
    ts: pd.DatetimeIndex,
    p_mm: np.ndarray | pd.Series,
    years_include: frozenset[int] | set[int] | None = None,
) -> float:
    ts = pd.to_datetime(ts).normalize()
    vals = p_mm.to_numpy(dtype=float) if hasattr(p_mm, "to_numpy") else np.asarray(p_mm, dtype=float)
    s = pd.Series(vals, index=ts)
    for sen in MISSING_SENTINELS:
        s = s.mask(s == float(sen), np.nan)
    yearly = s.groupby(s.index.year).sum(min_count=1).dropna()
    if years_include is not None:
        yearly = yearly.loc[yearly.index.isin(list(years_include))]
    if yearly.empty:
        return float("nan")
    return float(yearly.mean())


def process_station(
    station: str,
    lat: float,
    lon: float,
    cache_dir: Path,
    force_download: bool,
    client: cdsapi.Client,
    *,
    deaccumulate_tp: bool,
) -> None:
    print(f"\n=== {station} ({lat:.4f}°N, {lon:.4f}°E) ===")

    paths_30 = [FINAL_DATATABLES / f"{station}_30min.csv"]
    paths_daily = [FINAL_DATATABLES / f"{station}_daily.csv"]

    years: set[int] = set()
    for p in paths_30 + paths_daily:
        if not p.exists():
            print(f"  [hinweis] fehlt: {p}")
            continue
        _, df = _read_essd_csv(p)
        ts = _parse_ts(df["TIMESTAMP"], daily="daily" in p.name.lower())
        ts_ok = ts[ts.notna()]
        years.update(int(y) for y in np.unique(ts_ok.year))

    if not years:
        print("  Keine Datenjahre gefunden.")
        return

    subdir = cache_dir / station
    subdir.mkdir(parents=True, exist_ok=True)
    nc_files: list[Path] = []
    for y in sorted(years):
        out_nc = subdir / f"era5_tp_{y}.nc"
        nc_files.append(out_nc)
        if out_nc.exists() and not force_download:
            continue
        print(f"  ERA5-Download {y} … (CDS kann mehrere Minuten dauern)")
        client.retrieve(
            "reanalysis-era5-single-levels",
            {
                "product_type": "reanalysis",
                "data_format": "netcdf",
                "variable": "total_precipitation",
                "year": str(y),
                "month": [f"{m:02d}" for m in range(1, 13)],
                "day": [f"{d:02d}" for d in range(1, 32)],
                "time": [f"{h:02d}:00" for h in range(24)],
                "area": _cds_area(lat, lon, pad=0.25),
            },
            str(out_nc),
        )

    map_years = STATION_MAP_YEARS.get(station)
    ylabel = (
        f" (Jahre {sorted(map_years)})"
        if map_years is not None
        else " (alle Datenjahre)"
    )

    tp_h = load_era5_tp_timeseries(lat, lon, nc_files, deaccumulate_tp=deaccumulate_tp)
    print(f"  ERA5 stündlich: n={len(tp_h)}, {tp_h.index.min()} … {tp_h.index.max()}")

    map_30: float | None = None
    map_30_obs: float | None = None
    map_d: float | None = None
    map_d_obs: float | None = None

    p30 = paths_30[0]
    if p30.exists():
        _, df = _read_essd_csv(p30)
        ts = _parse_ts(df["TIMESTAMP"], daily=False)
        fill = era5_tp_to_30min_mm(ts, tp_h)
        p_raw = pd.to_numeric(df["P"], errors="coerce")
        for s in MISSING_SENTINELS:
            p_raw = p_raw.mask(p_raw == float(s), np.nan)
        p_arr = filled_p_array(df, fill)
        map_30 = mean_annual_from_30min(ts, p_arr, years_include=map_years)
        map_30_obs = mean_annual_from_30min(ts, p_raw, years_include=map_years)

    pdaily = paths_daily[0]
    if pdaily.exists():
        _, df = _read_essd_csv(pdaily)
        ts = _parse_ts(df["TIMESTAMP"], daily=True)
        fill = era5_tp_to_daily_mm(ts, tp_h)
        p_raw = pd.to_numeric(df["P"], errors="coerce")
        for s in MISSING_SENTINELS:
            p_raw = p_raw.mask(p_raw == float(s), np.nan)
        p_arr = filled_p_array(df, fill)
        map_d = mean_annual_from_daily(ts, p_arr, years_include=map_years)
        map_d_obs = mean_annual_from_daily(ts, p_raw, years_include=map_years)

    if map_30 is not None and np.isfinite(map_30):
        print(
            f"  Mittlerer Jahresniederschlag{ylabel}: {map_30:.1f} mm/a "
            f"(30-min, P-Lücken mit ERA5 gefüllt)"
        )
        if map_30_obs is not None and np.isfinite(map_30_obs):
            print(
                f"  … nur Mess-P (Lücken zählen nicht in Tages-/Jahressummen): {map_30_obs:.1f} mm/a"
            )
    elif map_d is not None and np.isfinite(map_d):
        print(
            f"  Mittlerer Jahresniederschlag{ylabel}: {map_d:.1f} mm/a "
            f"(Tages-Tabelle, P-Lücken mit ERA5 gefüllt)"
        )
        if map_d_obs is not None and np.isfinite(map_d_obs):
            print(
                f"  … nur Mess-P (Lücken zählen nicht in Tages-/Jahressummen): {map_d_obs:.1f} mm/a"
            )
    else:
        print("  MAP: nicht berechenbar (keine passende Datei oder keine gültigen Jahressummen).")


def main() -> None:
    ap = argparse.ArgumentParser(description="Gorigo/Janga: MAP aus ERA5-gefülltem P (kein CSV-Export)")
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--force-download", action="store_true")
    ap.add_argument("--lat-gorigo", type=float, default=STATION_LATLON_DEFAULT["Gorigo"][0])
    ap.add_argument("--lon-gorigo", type=float, default=STATION_LATLON_DEFAULT["Gorigo"][1])
    ap.add_argument("--lat-janga", type=float, default=STATION_LATLON_DEFAULT["Janga"][0])
    ap.add_argument("--lon-janga", type=float, default=STATION_LATLON_DEFAULT["Janga"][1])
    ap.add_argument(
        "--no-era5-tp-deaccum",
        action="store_true",
        help="Keine De-Akkumulation von ERA5 tp (legacy: nur *1000 m→mm pro Stufe)",
    )
    args = ap.parse_args()

    if cdsapi is None:
        raise SystemExit("cdsapi fehlt: pip install cdsapi")
    if xr is None:
        raise SystemExit("xarray fehlt: pip install xarray netCDF4")

    dotrc = Path.home() / ".cdsapirc"
    if not dotrc.is_file():
        raise SystemExit(
            f"CDS-API-Konfiguration fehlt: {dotrc}\n\n"
            "1) Konto: https://cds.climate.copernicus.eu/ (einloggen/registrieren)\n"
            "2) Unter Profil einen API-Key erzeugen\n"
            "3) Datei ~/.cdsapirc anlegen (nur für dich, nicht committen), z. B.:\n\n"
            "   url: https://cds.climate.copernicus.eu/api\n"
            "   key: <deine_UID>:<dein_API_Key>\n\n"
            "Anleitung: https://cds.climate.copernicus.eu/how-to-api\n"
        )
    try:
        client = cdsapi.Client()
    except Exception as e:
        msg = str(e).lower()
        if "missing" in msg or "incomplete" in msg or "cdsapirc" in msg:
            raise SystemExit(
                f"{e}\n\nPrüfe {dotrc}: zwei Zeilen 'url:' und 'key:' (Format UID:API_KEY).\n"
                "https://cds.climate.copernicus.eu/how-to-api"
            ) from e
        raise
    coords = {
        "Gorigo": (args.lat_gorigo, args.lon_gorigo),
        "Janga": (args.lat_janga, args.lon_janga),
    }
    for st in TARGET_STATIONS:
        lat, lon = coords[st]
        process_station(
            st,
            lat,
            lon,
            args.cache_dir,
            args.force_download,
            client,
            deaccumulate_tp=not args.no_era5_tp_deaccum,
        )

    print("\nFertig.")


if __name__ == "__main__":
    main()
