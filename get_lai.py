import ee
import pandas as pd
import numpy as np
from datetime import datetime


def get_lai_make_vegh(lat, lon, min_veg_h, max_veg_h,start,end):
    """
    Retrieve MODIS LAI data from Google Earth Engine and derive
    a 30-min vegetation height time series from normalized LAI values.

    Parameters
    ----------
    lat : float
        Latitude of station
    lon : float
        Longitude of station
    min_veg_h : float
        Minimum vegetation height (m)
    max_veg_h : float
        Maximum vegetation height (m)
    """

    # Initialize Earth Engine (ensure your project name matches)
    ee.Initialize(project='analog-context-343700')

    # --- Settings ---
    point = ee.Geometry.Point([lon, lat])
    start_date = start
    end_date = end
    product = 'MODIS/061/MCD15A3H'

    # --- Load MODIS LAI collection ---
    col = (
        ee.ImageCollection(product)
        .filterBounds(point)
        .filterDate(start_date, end_date)
        .select(['Lai', 'FparLai_QC'])
    )

    # --- Extract LAI and QC values for each date ---
    def extract(image):
        date = image.date().format('YYYY-MM-dd')
        lai = image.select('Lai').reduceRegion(
            reducer=ee.Reducer.first(),
            geometry=point,
            scale=500
        ).get('Lai')

        qc = image.select('FparLai_QC').reduceRegion(
            reducer=ee.Reducer.first(),
            geometry=point,
            scale=500
        ).get('FparLai_QC')

        return ee.Algorithms.If(
            ee.Algorithms.IsEqual(lai, None),
            None,
            ee.Feature(None, {
                'date': date,
                'lai_raw': lai,
                'lai_scaled': ee.Number(lai).multiply(0.1),
                'qc': qc
            })
        )

    features = col.map(extract, dropNulls=True)

    # --- Convert to client-side arrays ---
    data = features.aggregate_array('date').getInfo()
    lai = features.aggregate_array('lai_scaled').getInfo()
    qc = features.aggregate_array('qc').getInfo()

    # --- Build DataFrame ---
    df_lai = pd.DataFrame({'date': data, 'LAI': lai, 'QC': qc})
    df_lai['date'] = pd.to_datetime(df_lai['date'])
    df_lai.sort_values('date', inplace=True)
    df_lai.set_index('date', inplace=True)

    # --- Apply QC filter (mask poor-quality data) ---
    # Adjust the condition if your QC codes differ (see MCD15A3H doc)
    mask = df_lai["QC"] == 2
    df_lai.loc[mask, "LAI"] = np.nan

    # --- Cap unrealistic LAI values ---
    df_lai["LAI"] = df_lai["LAI"].clip(upper=4)

    # --- Interpolate to 30-minute resolution ---
    df_lai_interp = (
        df_lai["LAI"]
        .resample("30min")
        .interpolate(method="time")
        .to_frame()
    )

    # --- Normalize LAI robustly (avoid NaN propagation) ---
    denom = df_lai_interp["LAI"].max(skipna=True)
    if pd.isna(denom) or denom == 0:
        df_lai_interp["lai_norm"] = np.nan
    else:
        df_lai_interp["lai_norm"] = df_lai_interp["LAI"] / denom

    # --- Compute vegetation height ---
    veg_range = max_veg_h - min_veg_h
    veg_dyn = veg_range * df_lai_interp["lai_norm"]
    df_lai_interp["veg_h"] = min_veg_h + veg_dyn
    #df_lai_interp["veg_h"] = df_lai_interp["veg_h"].clip(lower=min_veg_h)

    return df_lai_interp


