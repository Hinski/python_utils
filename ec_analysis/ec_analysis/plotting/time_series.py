"""Time series plotting utilities for EC data."""
import pandas as pd
import matplotlib.pyplot as plt
from typing import Union, List, Optional
from ..aggregation import safe_slice

def plot_time_series(
    data: Union[pd.Series, pd.DataFrame],
    columns: Optional[List[str]] = None,
    start: Optional[Union[str, pd.Timestamp]] = None,
    end: Optional[Union[str, pd.Timestamp]] = None,
    figsize: tuple = (12, 6),
    title: Optional[str] = None,
    ylabel: Optional[str] = None,
    ax: Optional[plt.Axes] = None
) -> plt.Figure:
    """
    Plot time series data.
    
    Parameters
    ----------
    data : pd.Series | pd.DataFrame
        Time series data with datetime index
    columns : List[str] | None, optional
        Specific columns to plot (if DataFrame). If None, plots all columns
    start, end : str | pd.Timestamp | None, optional
        Date range to plot
    figsize : tuple, default=(12, 6)
        Figure size (width, height)
    title : str | None, optional
        Plot title
    ylabel : str | None, optional
        Y-axis label
    ax : plt.Axes | None, optional
        Existing axes to plot on. If None, creates new figure
    
    Returns
    -------
    plt.Figure
        Matplotlib figure object
    """
    # Convert Series to DataFrame for consistent handling
    if isinstance(data, pd.Series):
        data = pd.DataFrame({data.name or 'value': data})
        if columns is None:
            columns = [data.columns[0]]
    
    # Select columns to plot
    if columns is None:
        columns = data.columns.tolist()
    else:
        # Check if all columns exist
        missing = [c for c in columns if c not in data.columns]
        if missing:
            raise ValueError(f"Columns not found: {missing}")
    
    # Slice data to date range if provided
    if start is not None or end is not None:
        plot_data = pd.DataFrame()
        for col in columns:
            plot_data[col] = safe_slice(data[col], start or data.index.min(), end or data.index.max())
    else:
        plot_data = data[columns].copy()
    
    # Create figure and axes if not provided
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure
    
    # Plot each column
    for col in columns:
        ax.plot(plot_data.index, plot_data[col], label=col, linewidth=1.5)
    
    # Formatting
    ax.set_xlabel('Date')
    if ylabel:
        ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title)
    if len(columns) > 1:
        ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    
    return fig