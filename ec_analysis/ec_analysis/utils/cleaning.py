"""Data cleaning utilities for EC data."""
import pandas as pd
import numpy as np
from typing import List, Union

# Common invalid values in EC data
DEFAULT_INVALID_VALUES = [-9999, -99999, -9999.0, -99999.0, -999, -999.0]

def remove_invalid_values(
    df: pd.DataFrame,
    invalid_values: List[Union[int, float]] | None = None,
    columns: List[str] | None = None
) -> pd.DataFrame:
    """
    Replace invalid values with NaN.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame to clean
    invalid_values : List[Union[int, float]] | None, optional
        List of invalid values to replace. If None, uses DEFAULT_INVALID_VALUES
    columns : List[str] | None, optional
        Specific columns to clean. If None, cleans all columns
    
    Returns
    -------
    pd.DataFrame
        DataFrame with invalid values replaced by NaN
    """
    if invalid_values is None:
        invalid_values = DEFAULT_INVALID_VALUES
    
    df = df.copy()
    
    # Select columns to clean
    cols_to_clean = columns if columns is not None else df.columns
    
    # Replace invalid values with NaN
    for col in cols_to_clean:
        if col in df.columns:
            df[col] = df[col].replace(invalid_values, np.nan)
    
    return df

def filter_quality_flags(
    df: pd.DataFrame,
    quality_column: str,
    max_flag: int = 1,
    data_column: str | None = None
) -> pd.Series:
    """
    Filter data based on quality flags.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with quality flags
    quality_column : str
        Name of quality flag column (e.g., 'qc_H', 'qc_LE')
    max_flag : int, default=1
        Maximum quality flag value to keep (lower = better quality)
    data_column : str | None, optional
        Name of data column to return. If None, returns Series with same name as quality_column
    
    Returns
    -------
    pd.Series
        Filtered data series (only high quality values)
    """
    if quality_column not in df.columns:
        raise ValueError(f"Quality column '{quality_column}' not found in DataFrame")
    
    # Get quality flags
    qc = pd.to_numeric(df[quality_column], errors='coerce')
    
    # Create mask for high quality data
    high_quality_mask = (qc <= max_flag) & (qc.notna())
    
    # Get data column
    if data_column is None:
        # Try to infer data column from quality column name
        # e.g., 'qc_H' -> 'H', 'qc_LE' -> 'LE'
        data_column = quality_column.replace('qc_', '').replace('_qc', '')
        if data_column not in df.columns:
            raise ValueError(f"Could not infer data column from '{quality_column}'")
    
    if data_column not in df.columns:
        raise ValueError(f"Data column '{data_column}' not found in DataFrame")
    
    # Get data and filter
    data = pd.to_numeric(df[data_column], errors='coerce')
    filtered_data = data[high_quality_mask].copy()
    
    return filtered_data



def clean_dataframe(
    df: pd.DataFrame,
    remove_invalid: bool = True,
    invalid_values: List[Union[int, float]] | None = None
) -> pd.DataFrame:
    """
    General cleaning function for EC data.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame to clean
    remove_invalid : bool, default=True
        Whether to remove invalid values
    invalid_values : List[Union[int, float]] | None, optional
        Invalid values to remove. If None, uses DEFAULT_INVALID_VALUES
    
    Returns
    -------
    pd.DataFrame
        Cleaned DataFrame
    """
    df = df.copy()
    
    # Remove invalid values
    if remove_invalid:
        df = remove_invalid_values(df, invalid_values=invalid_values)
    
    return df