"""Radiation plotting utilities for EC data."""
import pandas as pd
import matplotlib.pyplot as plt
from typing import Union, Optional
from ..aggregation import safe_slice


def plot_radiation_components(
    df: pd.DataFrame,
    start: Optional[Union[str, pd.Timestamp]] = None,
    end: Optional[Union[str, pd.Timestamp]] = None,
    figsize: tuple = (14, 8),
    title: Optional[str] = None
) -> plt.Figure:
    """
    Plot radiation components: shortwave, longwave, and net radiation.
    
    Parameters
    ----------
    df : pd.DataFrame
        Radiation DataFrame with columns: SR_in, SR_out, IR_in, IR_out, NetRs, NetRl, NetTot
    start, end : str | pd.Timestamp | None, optional
        Date range to plot
    figsize : tuple, default=(14, 8)
        Figure size (width, height)
    title : str | None, optional
        Plot title
    
    Returns
    -------
    plt.Figure
        Matplotlib figure object
    """
    # Expected columns (flexible - use what's available)
    shortwave_cols = ['SR_in_Avg', 'SR_out_Avg', 'NetRs_Avg']
    longwave_cols = ['IR_in_Avg', 'IR_out_Avg', 'NetRl_Avg']
    net_cols = ['NetTot_Avg']
    
    # Find available columns
    available_shortwave = [c for c in shortwave_cols if c in df.columns]
    available_longwave = [c for c in longwave_cols if c in df.columns]
    available_net = [c for c in net_cols if c in df.columns]
    
    if not (available_shortwave or available_longwave or available_net):
        raise ValueError("No radiation columns found in DataFrame")
    
    # Slice to date range if provided
    if start is not None or end is not None:
        plot_df = df.loc[
            (df.index >= pd.to_datetime(start or df.index.min())) &
            (df.index <= pd.to_datetime(end or df.index.max()))
        ]
    else:
        plot_df = df.copy()
    
    # Create subplots
    n_plots = sum([bool(available_shortwave), bool(available_longwave), bool(available_net)])
    fig, axes = plt.subplots(n_plots, 1, figsize=figsize, sharex=True)
    
    if n_plots == 1:
        axes = [axes]
    
    plot_idx = 0
    
    # Plot shortwave radiation
    if available_shortwave:
        ax = axes[plot_idx]
        for col in available_shortwave:
            ax.plot(plot_df.index, plot_df[col], label=col, linewidth=1.5)
        ax.set_ylabel('Shortwave Radiation (W/m²)')
        ax.set_title('Shortwave Radiation')
        ax.grid(True, alpha=0.3)
        ax.legend()
        plot_idx += 1
    
    # Plot longwave radiation
    if available_longwave:
        ax = axes[plot_idx]
        for col in available_longwave:
            ax.plot(plot_df.index, plot_df[col], label=col, linewidth=1.5)
        ax.set_ylabel('Longwave Radiation (W/m²)')
        ax.set_title('Longwave Radiation')
        ax.grid(True, alpha=0.3)
        ax.legend()
        plot_idx += 1
    
    # Plot net radiation
    if available_net:
        ax = axes[plot_idx]
        for col in available_net:
            ax.plot(plot_df.index, plot_df[col], label=col, linewidth=1.5, color='red')
        ax.set_ylabel('Net Radiation (W/m²)')
        ax.set_title('Net Radiation')
        ax.grid(True, alpha=0.3)
        ax.axhline(y=0, color='black', linestyle='--', linewidth=0.5)
        ax.legend()
        plot_idx += 1
    
    # Set x-axis label on last subplot
    axes[-1].set_xlabel('Date')
    
    if title:
        fig.suptitle(title, fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    return fig


def plot_albedo(
    df: pd.DataFrame,
    start: Optional[Union[str, pd.Timestamp]] = None,
    end: Optional[Union[str, pd.Timestamp]] = None,
    figsize: tuple = (12, 6),
    title: Optional[str] = None
) -> plt.Figure:
    """
    Plot albedo time series.
    
    Parameters
    ----------
    df : pd.DataFrame
        Radiation DataFrame with 'Albedo_Avg' column
    start, end : str | pd.Timestamp | None, optional
        Date range to plot
    figsize : tuple, default=(12, 6)
        Figure size (width, height)
    title : str | None, optional
        Plot title
    
    Returns
    -------
    plt.Figure
        Matplotlib figure object
    """
    if 'Albedo_Avg' not in df.columns:
        raise ValueError("Column 'Albedo_Avg' not found in DataFrame")
    
    # Slice to date range if provided
    if start is not None or end is not None:
        plot_df = df.loc[
            (df.index >= pd.to_datetime(start or df.index.min())) &
            (df.index <= pd.to_datetime(end or df.index.max()))
        ]
    else:
        plot_df = df.copy()
    
    # Create figure
    fig, ax = plt.subplots(figsize=figsize)
    
    # Plot albedo
    ax.plot(plot_df.index, plot_df['Albedo_Avg'], linewidth=1.5, color='blue')
    
    # Formatting
    ax.set_xlabel('Date')
    ax.set_ylabel('Albedo')
    ax.set_title(title or 'Albedo Time Series')
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, 1)  # Albedo is typically between 0 and 1
    
    plt.tight_layout()
    return fig

