"""Time series aggregation utilities for EC data."""
import pandas as pd
import numpy as np
from typing import Union, Optional

def safe_slice(
    series: pd.Series,
    start: Union[str, pd.Timestamp],
    end: Union[str, pd.Timestamp],
    dropna: bool = False
) -> pd.Series:
    """
    Safely slice a time series by date range.
    
    Parameters
    ----------
    series : pd.Series
        Time series to slice
    start : str | pd.Timestamp
        Start date
    end : str | pd.Timestamp
        End date
    dropna : bool, default=False
        Whether to remove NaN values before slicing
    
    Returns
    -------
    pd.Series
        Sliced time series
    """
    if not isinstance(series.index, pd.DatetimeIndex):
        series.index = pd.to_datetime(series.index, errors="coerce")
    
    series = series.sort_index()
    series = series[~series.index.duplicated(keep="first")]
    
    if dropna:
        series = series.dropna()
    
    mask = (series.index >= pd.to_datetime(start)) & (series.index <= pd.to_datetime(end))
    return series.loc[mask]


def _is_precipitation_column(column_name: str) -> bool:
    """
    Check if a column name indicates precipitation data.
    
    Parameters
    ----------
    column_name : str
        Column name to check
    
    Returns
    -------
    bool
        True if column is precipitation-related
    """
    col_lower = column_name.lower()
    precip_keywords = ['rain', 'precip', '_p_', '_p[', 'precipitation', 'acc_rt_nrt_tot', 'rain_mm_tot', 'ramount_tot']
    return any(keyword in col_lower for keyword in precip_keywords)


def resample_data(
    df: pd.DataFrame,
    freq: str = '30min',
    method: Union[str, dict] = 'auto'
) -> pd.DataFrame:
    """
    Resample time series data to specified frequency.
    
    Precipitation columns are automatically summed, all other columns are averaged.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with datetime index
    freq : str, default='30min'
        Resampling frequency (e.g., '30min', '1H', '1D')
    method : str | dict, default='auto'
        Aggregation method:
        - 'auto': Precipitation columns summed, others averaged
        - 'mean', 'sum', 'max', 'min', 'median': Apply to all columns
        - dict: Specify method per column, e.g., {'H': 'mean', 'Rain_mm_Tot': 'sum'}
    
    Returns
    -------
    pd.DataFrame
        Resampled DataFrame
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame must have DatetimeIndex")
    
    # Handle automatic method selection
    if method == 'auto':
        # Create dictionary with method per column
        agg_dict = {}
        for col in df.columns:
            if _is_precipitation_column(col):
                agg_dict[col] = 'sum'
            else:
                agg_dict[col] = 'mean'
        method = agg_dict
    
    # Handle single method for all columns
    if isinstance(method, str):
        valid_methods = ['mean', 'sum', 'max', 'min', 'median']
        if method not in valid_methods:
            raise ValueError(f"Unknown method: {method}. Use: {valid_methods} or 'auto' or dict")
        # Apply same method to all columns
        resampled = df.resample(freq)
        result = getattr(resampled, method)()
    
    # Handle dictionary with method per column
    elif isinstance(method, dict):
        resampled = df.resample(freq)
        result = pd.DataFrame(index=resampled.groups.keys())
        
        for col in df.columns:
            col_method = method.get(col, 'mean')  # Default to mean if not specified
            if col_method not in ['mean', 'sum', 'max', 'min', 'median']:
                raise ValueError(f"Unknown method '{col_method}' for column '{col}'")
            result[col] = getattr(resampled[col], col_method)()
        
        result.index = pd.to_datetime(result.index)
    
    else:
        raise ValueError("method must be 'auto', a string, or a dictionary")
    
    return result