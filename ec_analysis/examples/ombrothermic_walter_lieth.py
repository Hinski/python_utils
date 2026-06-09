#!/usr/bin/env python3
"""
Ombrothermic (Walter–Lieth) diagram from CRU TS v4.07.

  python ombrothermic_walter_lieth.py
  python ombrothermic_walter_lieth.py --download
"""

from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import xarray as xr

from walter_lieth_common import MONTH_LABELS, plot_walter_lieth_figure

DEFAULT_LAT = 11.1516
DEFAULT_LON = -1.5858
CLIM_START = 1991
CLIM_END = 2020

CRU_BASE_URL = (
    "https://crudata.uea.ac.uk/cru/data/hrg/cru_ts_4.07/cruts.2304141047.v4.07"
)
DECADES = ("1991.2000", "2001.2010", "2011.2020")
VARIABLES = ("tmp", "pre")

DEFAULT_CACHE = Path(__file__).parent / "data" / "cru_ts_4.07"
DEFAULT_OUTPUT = Path(__file__).parent / "plots" / "ombrothermic.png"


def _download_cru_decades(cache_dir: Path) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    for var in VARIABLES:
        for dec in DECADES:
            fname = f"cru_ts4.07.{dec}.{var}.dat.nc.gz"
            dest = cache_dir / fname
            if dest.exists():
                continue
            url = f"{CRU_BASE_URL}/{var}/{fname}"
            print(f"  Downloading {fname} …")
            tmp = dest.with_suffix(dest.suffix + ".part")
            urllib.request.urlretrieve(url, tmp)
            tmp.rename(dest)
    print(f"✓ CRU files in {cache_dir}")


def _open_cru_series(cache_dir: Path, var: str, lat: float, lon: float) -> pd.Series:
    pieces: list[xr.DataArray] = []
    for dec in DECADES:
        path = cache_dir / f"cru_ts4.07.{dec}.{var}.dat.nc.gz"
        if not path.exists():
            raise FileNotFoundError(
                f"Missing {path.name}. Run with --download or place files in {cache_dir}"
            )
        ds = xr.open_dataset(path)
        da = ds[var].sel(lat=lat, lon=lon, method="nearest")
        pieces.append(da.load())
        ds.close()

    combined = xr.concat(pieces, dim="time")
    combined = combined.sel(time=slice(f"{CLIM_START}", f"{CLIM_END}"))
    idx = pd.to_datetime(combined["time"].values)
    return pd.Series(combined.values.astype(float), index=idx, name=var)


def monthly_climatology(series: pd.Series) -> pd.Series:
    df = series.to_frame("v")
    df["month"] = df.index.month
    return df.groupby("month")["v"].mean()


def main() -> None:
    parser = argparse.ArgumentParser(description="Walter–Lieth diagram (CRU TS v4.07)")
    parser.add_argument("--lat", type=float, default=DEFAULT_LAT)
    parser.add_argument("--lon", type=float, default=DEFAULT_LON)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()

    if args.download or not all(
        (args.cache_dir / f"cru_ts4.07.{d}.{v}.dat.nc.gz").exists()
        for v in VARIABLES
        for d in DECADES
    ):
        _download_cru_decades(args.cache_dir)

    tmp_ts = _open_cru_series(args.cache_dir, "tmp", args.lat, args.lon)
    pre_ts = _open_cru_series(args.cache_dir, "pre", args.lat, args.lon)
    t_monthly = monthly_climatology(tmp_ts)
    p_monthly = monthly_climatology(pre_ts)

    ds0 = xr.open_dataset(args.cache_dir / f"cru_ts4.07.{DECADES[0]}.tmp.dat.nc.gz")
    glat = float(ds0["lat"].sel(lat=args.lat, method="nearest"))
    glon = float(ds0["lon"].sel(lon=args.lon, method="nearest"))
    ds0.close()

    fig = plot_walter_lieth_figure(
        t_monthly.values,
        p_monthly.values,
        title=(
            "Ombrothermic diagram (Walter–Lieth)\n"
            f"CRU TS v4.07 ({CLIM_START}–{CLIM_END}); "
            f"Sudanian savanna ({glat:.2f}°N, {glon:.2f}°E)"
        ),
        footnote=f"Target: {args.lat:.2f}°N, {args.lon:.2f}°E | nearest CRU grid cell.",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"✓ Saved: {args.output}")


if __name__ == "__main__":
    main()
