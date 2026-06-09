"""Energy balance plotting utilities for EC data."""
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from typing import Union, Optional
from ..aggregation import safe_slice


def apply_mole_sw_in_correction(SW_in: pd.Series, site_name: str = "") -> pd.Series:
    """
    Apply SW_in correction for Mole station.
    
    Mole station requires a correction factor: SW_in * 10.15 / 16.15
    
    Parameters
    ----------
    SW_in : pd.Series
        Shortwave radiation in (W/m²)
    site_name : str, default=""
        Site name to check if correction should be applied
    
    Returns
    -------
    pd.Series
        Corrected SW_in (only corrected if site_name == 'Mole')
    """
    if site_name == 'Mole':
        return SW_in * 10.15 / 16.15
    return SW_in


def plot_energy_balance(
    df: pd.DataFrame,
    start: Optional[Union[str, pd.Timestamp]] = None,
    end: Optional[Union[str, pd.Timestamp]] = None,
    figsize: tuple = (14, 8),
    title: Optional[str] = None
) -> plt.Figure:
    """
    Plot all energy balance components in a single plot (stacked).
    
    Parameters
    ----------
    df : pd.DataFrame
        Energy balance DataFrame with columns: Rn, LE, H, G, Residual
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
    # Required columns (excluding Delta)
    required_cols = ['Rn', 'LE', 'H', 'G', 'Residual']
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    
    # Slice to date range if provided
    if start is not None or end is not None:
        plot_df = df.loc[
            (df.index >= pd.to_datetime(start or df.index.min())) &
            (df.index <= pd.to_datetime(end or df.index.max()))
        ]
    else:
        plot_df = df.copy()
    
    # Filter LE and H to valid range: -300 to 800 W/m² (only for plotting LE and H)
    if 'LE' in plot_df.columns and 'H' in plot_df.columns:
        # Create a copy for LE and H columns with filtered values
        plot_df_filtered = plot_df.copy()
        le_valid = (plot_df['LE'] >= -300) & (plot_df['LE'] <= 800)
        h_valid = (plot_df['H'] >= -300) & (plot_df['H'] <= 800)
        plot_df_filtered.loc[~le_valid, 'LE'] = np.nan
        plot_df_filtered.loc[~h_valid, 'H'] = np.nan
    else:
        plot_df_filtered = plot_df.copy()
    
    # Create subplots: one row per component (vertical stack)
    n_components = len(required_cols)
    fig, axes = plt.subplots(n_components, 1, figsize=figsize, sharex=True)
    
    # If only one component, make axes a list
    if n_components == 1:
        axes = [axes]
    
    # Colors for each component
    colors = {
        'Rn': '#1f77b4',      # Blue
        'LE': '#2ca02c',       # Green
        'H': '#ff7f0e',        # Orange
        'G': '#d62728',        # Red
        'Residual': '#8c564b' # Brown
    }
    
    # Plot each component in its own subplot
    for i, col in enumerate(required_cols):
        ax = axes[i]
        # Use filtered data for LE and H, original data for others
        data_to_plot = plot_df_filtered[col] if col in ['LE', 'H'] else plot_df[col]
        
        # Plot the data - Matplotlib automatically skips NaN values
        # But we ensure we're plotting all available data points
        ax.plot(data_to_plot.index, data_to_plot, color=colors[col], 
               linewidth=1.5, label=col)
        ax.set_ylabel(f'{col} (W/m²)', fontsize=10)
        ax.set_title(col, fontsize=11, fontweight='bold')
        ax.grid(True, alpha=0.3)
        ax.axhline(y=0, color='black', linestyle='--', linewidth=0.5)
        ax.legend(fontsize=9, loc='best')
        
        # Set ylim for all components to -300 to 1000
        ax.set_ylim(-300, 1000)
    
    # Set x-axis label on bottom subplot
    axes[-1].set_xlabel('Date', fontsize=12)
    
    # Rotate x-axis labels to prevent overlap
    for ax in axes:
        ax.tick_params(axis='x', rotation=45, labelsize=9)
        for label in ax.get_xticklabels():
            label.set_ha('right')
    
    if title:
        fig.suptitle(title, fontsize=14, fontweight='bold')
    
    # Adjust layout to make room for rotated labels
    plt.tight_layout(rect=[0, 0.03, 1, 0.96])
    return fig


def plot_energy_balance_closure(
    df: pd.DataFrame,
    start: Optional[Union[str, pd.Timestamp]] = None,
    end: Optional[Union[str, pd.Timestamp]] = None,
    figsize: tuple = (8, 8),
    title: Optional[str] = None
) -> plt.Figure:
    """
    Plot energy balance closure: (LE + H) vs (Rn - G - DeltaS).
    
    X-axis: Rn - G - DeltaS [W/m²] (available energy minus ground heat and storage)
    Y-axis: LE + H [W/m²] (turbulent fluxes)
    
    The regression slope (closure) should be < 1, indicating that turbulent
    fluxes are typically smaller than available energy. A 1:1 line indicates
    perfect closure. Points above the 1:1 line indicate overestimation of
    turbulent fluxes, points below indicate underestimation.
    
    Parameters
    ----------
    df : pd.DataFrame
        Energy balance DataFrame with columns: Rn, LE, H, G, Delta (optional)
    start, end : str | pd.Timestamp | None, optional
        Date range to plot
    figsize : tuple, default=(8, 8)
        Figure size (width, height)
    title : str | None, optional
        Plot title
    
    Returns
    -------
    plt.Figure
        Matplotlib figure object
    """
    # Required columns
    required_cols = ['Rn', 'LE', 'H', 'G']
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    
    # Delta is optional - check if it exists AND has non-zero values
    # If Delta is all zeros or all NaN, it wasn't actually calculated
    has_delta = False
    if 'Delta' in df.columns:
        delta_values = df['Delta'].dropna()
        # Only consider Delta as calculated if there are non-zero values
        if len(delta_values) > 0 and (delta_values != 0).any():
            has_delta = True
    
    # Slice to date range if provided
    if start is not None or end is not None:
        plot_df = df.loc[
            (df.index >= pd.to_datetime(start or df.index.min())) &
            (df.index <= pd.to_datetime(end or df.index.max()))
        ]
    else:
        plot_df = df.copy()
    
    # Filter LE and H to valid range: -300 to 800 W/m²
    valid_mask = (
        (plot_df['LE'] >= -300) & (plot_df['LE'] <= 800) &
        (plot_df['H'] >= -300) & (plot_df['H'] <= 800)
    )
    plot_df = plot_df[valid_mask]
    
    # IMPORTANT: For energy balance closure analysis, we require ALL variables to be present
    # Drop rows where any required variable is NaN (needed for proper closure calculation)
    cols_to_check = ['Rn', 'LE', 'H', 'G']
    if has_delta:
        cols_to_check.append('Delta')
    plot_df = plot_df[cols_to_check].dropna()
    
    # Calculate X-axis: Rn - G - DeltaS (available energy minus ground heat and storage)
    x_data = plot_df['Rn'] - plot_df['G']
    if has_delta:
        x_data = x_data - plot_df['Delta']
    
    # Calculate Y-axis: LE + H (turbulent fluxes)
    y_data = plot_df['LE'] + plot_df['H']
    
    # Align indices (both should already be aligned since we dropped NaN rows above)
    common_idx = x_data.index.intersection(y_data.index)
    x_data = x_data.loc[common_idx]
    y_data = y_data.loc[common_idx]
    
    # Create figure
    fig, ax = plt.subplots(figsize=figsize)
    
    # Scatter plot
    ax.scatter(x_data, y_data, alpha=0.5, s=20, edgecolors='none', color='black')
    
    # Set axis limits
    ax.set_xlim(-200, 1000)
    ax.set_ylim(-200, 1000)
    
    # 1:1 line (dashed grey line)
    ax.plot([-200, 1000], [-200, 1000], '--', color='grey', linewidth=1.5, label='1:1 line', zorder=1)
    
    # Initialize closure variables
    closure_sum = 0
    
    # Calculate regression line
    if len(x_data) > 1:
        # Remove any infinite or extreme values
        mask = np.isfinite(x_data) & np.isfinite(y_data)
        x_clean = x_data[mask]
        y_clean = y_data[mask]
        
        if len(x_clean) > 1:
            # Calculate closure from regression: LE + H = closure * (Rn - G) + intercept
            # Regression of y (LE + H) against x (Rn - G)
            # y = closure * x + intercept
            coeffs = np.polyfit(x_clean, y_clean, 1)
            closure_regression = coeffs[0]  # Closure from regression (should be < 1)
            intercept = coeffs[1]
            
            # Calculate closure from sum ratio: Sum(LE+H) / Sum(Rn-G)
            sum_y = np.sum(y_clean)
            sum_x = np.sum(x_clean)
            closure_sum = sum_y / sum_x if sum_x != 0 else 0
            
            # Calculate R²
            y_pred = closure_regression * x_clean + intercept
            ss_res = np.sum((y_clean - y_pred) ** 2)
            ss_tot = np.sum((y_clean - np.mean(y_clean)) ** 2)
            r2 = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
            
            # Plot regression line
            x_reg = np.array([-200, 1000])
            y_reg = closure_regression * x_reg + intercept
            ax.plot(x_reg, y_reg, 'r-', linewidth=2, label='Regression', zorder=2)
            
            # Display regression equation, R², and closure from sum ratio
            equation_text = (f'y = {closure_regression:.3f}x + {intercept:.2f}\n'
                           f'R² = {r2:.2f}\n'
                           f'Cumulative EBC = {closure_sum:.3f}')
            ax.text(0.05, 0.95, equation_text, transform=ax.transAxes,
                   fontsize=12, verticalalignment='top',
                   bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
            
            # Use regression closure for title (keep for backward compatibility)
            closure = closure_regression
        else:
            r2 = 0
            intercept = 0
            closure = 0
            closure_sum = 0
    else:
        r2 = 0
        intercept = 0
        closure = 0
        closure_sum = 0
    
    # Labels and formatting with larger font size
    delta_label = " - ΔS" if has_delta else ""
    ax.set_xlabel(f'Rn - G{delta_label} [W/m²]', fontsize=14)
    ax.set_ylabel('LE + H [W/m²]', fontsize=14)
    
    if title:
        ax.set_title(title, fontsize=16, fontweight='bold')
    else:
        closure_percent = closure * 100
        closure_sum_percent = closure_sum * 100
        ax.set_title(f'Energy Balance Closure\nClosure (reg): {closure:.3f} ({closure_percent:.1f}%), '
                    f'Cumulative EBC: {closure_sum:.3f} ({closure_sum_percent:.1f}%), R²: {r2:.2f}', 
                    fontsize=16, fontweight='bold')
    
    # Increase tick label size
    ax.tick_params(labelsize=12)
    
    ax.legend(fontsize=12)
    ax.grid(True, alpha=0.3)
    ax.set_aspect('equal', adjustable='box')
    
    plt.tight_layout()
    return fig


def plot_diurnal_cycle(
    df: pd.DataFrame,
    columns: Optional[list[str]] = None,
    start: Optional[Union[str, pd.Timestamp]] = None,
    end: Optional[Union[str, pd.Timestamp]] = None,
    figsize: tuple = (10, 6),
    title: Optional[str] = None
) -> plt.Figure:
    """
    Plot diurnal cycle (hourly averages) of energy balance components.
    
    Parameters
    ----------
    df : pd.DataFrame
        Energy balance DataFrame with datetime index
    columns : list[str] | None, optional
        Columns to plot. If None, plots: Rn, LE, H, G
    start, end : str | pd.Timestamp | None, optional
        Date range to calculate diurnal cycle from
    figsize : tuple, default=(10, 6)
        Figure size (width, height)
    title : str | None, optional
        Plot title
    
    Returns
    -------
    plt.Figure
        Matplotlib figure object
    """
    # Default columns
    if columns is None:
        columns = ['Rn', 'LE', 'H', 'G']
    
    # Check if columns exist
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"Columns not found: {missing}")
    
    # Slice to date range if provided
    if start is not None or end is not None:
        plot_df = df.loc[
            (df.index >= pd.to_datetime(start or df.index.min())) &
            (df.index <= pd.to_datetime(end or df.index.max()))
        ]
    else:
        plot_df = df.copy()
    
    # Filter LE and H to valid range: -300 to 800 W/m² before calculating diurnal cycle
    # Only filter if LE or H are in the columns to plot
    if 'LE' in columns and 'LE' in plot_df.columns:
        le_valid = (plot_df['LE'] >= -300) & (plot_df['LE'] <= 800)
        plot_df.loc[~le_valid, 'LE'] = np.nan
    if 'H' in columns and 'H' in plot_df.columns:
        h_valid = (plot_df['H'] >= -300) & (plot_df['H'] <= 800)
        plot_df.loc[~h_valid, 'H'] = np.nan
    
    # Calculate hourly averages
    hourly_avg = plot_df[columns].groupby(plot_df.index.hour).mean()
    
    # Create figure
    fig, ax = plt.subplots(figsize=figsize)
    
    # Colors
    colors = {
        'Rn': '#1f77b4',
        'LE': '#2ca02c',
        'H': '#ff7f0e',
        'G': '#d62728',
        'Delta': '#9467bd',
        'Residual': '#8c564b'
    }
    
    # Plot each column
    for col in columns:
        color = colors.get(col, None)
        ax.plot(hourly_avg.index, hourly_avg[col], marker='o', 
                label=col, linewidth=2, markersize=4, color=color)
    
    # Formatting
    ax.set_xlabel('Hour of Day')
    ax.set_ylabel('Flux (W/m²)')
    ax.set_xticks(range(0, 24, 2))
    ax.set_xlim(-0.5, 23.5)
    ax.axhline(y=0, color='black', linestyle='--', linewidth=0.5)
    ax.grid(True, alpha=0.3)
    ax.legend()
    
    if title:
        ax.set_title(title)
    else:
        ax.set_title('Diurnal Cycle of Energy Balance Components')
    
    plt.tight_layout()
    return fig


def plot_radiation_components(
    df: pd.DataFrame,
    start: Optional[Union[str, pd.Timestamp]] = None,
    end: Optional[Union[str, pd.Timestamp]] = None,
    figsize: tuple = (14, 8),
    title: Optional[str] = None,
    site_name: str = ""
) -> plt.Figure:
    """
    Plot all radiation components (SW_in, SW_out, LW_in, LW_out) in subplots.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with radiation columns: SW_IN/SR_in_Avg, SW_OUT/SR_out_Avg, 
        LW_IN/IR_in_Avg, LW_OUT/IR_out_Avg
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
    # Try different column name conventions
    # For Dragan stations (Kayoro, Nazinga, Sumbrungu): use Dragan columns for pre-2016, Parquet columns for post-2016
    if site_name in ['Kayoro', 'Nazinga', 'Sumbrungu']:
        cutoff_date = pd.to_datetime('2016-01-01')
        dragan_SW_in = df.get('SW_in korrigiert', None)
        dragan_SW_out = df.get('SW_out korrigiert', None)
        dragan_LW_in = df.get('LW_in_Avg [W/m^2]', None)
        dragan_LW_out = df.get('LW_out_Avg [W/m^2]', None)
        parquet_SW_in = df.get('SR_in_Avg', None)
        parquet_SW_out = df.get('SR_out_Avg', None)
        parquet_LW_in = df.get('IR_in_Avg', None)
        parquet_LW_out = df.get('IR_out_Avg', None)
        
        # Combine pre-2016 (Dragan) and post-2016 (Parquet) data
        if dragan_SW_in is not None and parquet_SW_in is not None:
            idx_pre = df.index < cutoff_date
            idx_post = df.index >= cutoff_date
            SW_in = dragan_SW_in.where(idx_pre).combine_first(parquet_SW_in.where(idx_post))
        elif dragan_SW_in is not None:
            SW_in = dragan_SW_in
        elif parquet_SW_in is not None:
            SW_in = parquet_SW_in
        else:
            SW_in = None
            
        if dragan_SW_out is not None and parquet_SW_out is not None:
            idx_pre = df.index < cutoff_date
            idx_post = df.index >= cutoff_date
            SW_out = dragan_SW_out.where(idx_pre).combine_first(parquet_SW_out.where(idx_post))
        elif dragan_SW_out is not None:
            SW_out = dragan_SW_out
        elif parquet_SW_out is not None:
            SW_out = parquet_SW_out
        else:
            SW_out = None
            
        if dragan_LW_in is not None and parquet_LW_in is not None:
            idx_pre = df.index < cutoff_date
            idx_post = df.index >= cutoff_date
            LW_in = dragan_LW_in.where(idx_pre).combine_first(parquet_LW_in.where(idx_post))
        elif dragan_LW_in is not None:
            LW_in = dragan_LW_in
        elif parquet_LW_in is not None:
            LW_in = parquet_LW_in
        else:
            LW_in = None
            
        if dragan_LW_out is not None and parquet_LW_out is not None:
            idx_pre = df.index < cutoff_date
            idx_post = df.index >= cutoff_date
            LW_out = dragan_LW_out.where(idx_pre).combine_first(parquet_LW_out.where(idx_post))
        elif dragan_LW_out is not None:
            LW_out = dragan_LW_out
        elif parquet_LW_out is not None:
            LW_out = parquet_LW_out
        else:
            LW_out = None
    else:
        # For other stations, try Dragan names first, then standard names
        SW_in = df.get('SW_in korrigiert', None)
        SW_out = df.get('SW_out korrigiert', None)
        LW_in = df.get('LW_in_Avg [W/m^2]', None)
        LW_out = df.get('LW_out_Avg [W/m^2]', None)
        
        # Standard names (from radiation files)
        if SW_in is None:
            SW_in = df.get('SR_in_Avg', None)
        if SW_out is None:
            SW_out = df.get('SR_out_Avg', None)
        if LW_in is None:
            LW_in = df.get('IR_in_Avg', None)
        if LW_out is None:
            LW_out = df.get('IR_out_Avg', None)
    
    # Alternative names (from AmeriFlux format files)
    if SW_in is None:
        SW_in = df.get('SW_IN', None)
    if SW_out is None:
        SW_out = df.get('SW_OUT', None)
    if LW_in is None:
        LW_in = df.get('LW_IN', None)
    if LW_out is None:
        LW_out = df.get('LW_OUT', None)
    
    # Apply Mole SW_in correction if needed
    if SW_in is not None:
        SW_in = apply_mole_sw_in_correction(SW_in, site_name)
    
    # Check which components are available
    components = {}
    if SW_in is not None:
        components['SW_in'] = SW_in
    if SW_out is not None:
        components['SW_out'] = SW_out
    if LW_in is not None:
        components['LW_in'] = LW_in
    if LW_out is not None:
        components['LW_out'] = LW_out
    
    if not components:
        raise ValueError("No radiation components found. Expected: SW_IN/SR_in_Avg, SW_OUT/SR_out_Avg, LW_IN/IR_in_Avg, LW_OUT/IR_out_Avg")
    
    # Slice to date range if provided
    if start is not None or end is not None:
        plot_components = {}
        for name, series in components.items():
            plot_components[name] = series.loc[
                (series.index >= pd.to_datetime(start or series.index.min())) &
                (series.index <= pd.to_datetime(end or series.index.max()))
            ]
    else:
        plot_components = components
    
    # Calculate Rn (net radiation) if all components are available
    if all([SW_in is not None, SW_out is not None, LW_in is not None, LW_out is not None]):
        # Get sliced components for Rn calculation
        sw_in_sliced = plot_components.get('SW_in', SW_in)
        sw_out_sliced = plot_components.get('SW_out', SW_out)
        lw_in_sliced = plot_components.get('LW_in', LW_in)
        lw_out_sliced = plot_components.get('LW_out', LW_out)
        
        # Calculate Rn: Rn = (SW_in - SW_out) + (LW_in - LW_out)
        # Combine into DataFrame to handle NaN values properly
        rad_df = pd.DataFrame({
            'SW_in': sw_in_sliced,
            'SW_out': sw_out_sliced,
            'LW_in': lw_in_sliced,
            'LW_out': lw_out_sliced
        })
        has_all = rad_df.notna().all(axis=1)
        Rn = pd.Series(np.nan, index=rad_df.index)
        Rn.loc[has_all] = (
            rad_df.loc[has_all, 'SW_in'] - rad_df.loc[has_all, 'SW_out'] +
            rad_df.loc[has_all, 'LW_in'] - rad_df.loc[has_all, 'LW_out']
        )
        plot_components['Rn'] = Rn
    
    # Create subplots: include Rn if available
    n_components = len(plot_components)
    # Layout: if we have Rn, use 2 rows x 3 columns (or adjust as needed)
    if n_components <= 3:
        nrows, ncols = 1, n_components
    elif n_components <= 6:
        nrows, ncols = 2, 3
    else:
        nrows, ncols = 3, 3
    
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, sharex=True)
    if n_components == 1:
        axes = [axes]
    else:
        axes = axes.flatten() if n_components > 1 else [axes]
    
    # Colors for each component
    colors = {
        'SW_in': '#ff7f0e',      # Orange
        'SW_out': '#ffbb78',     # Light orange
        'LW_in': '#2ca02c',      # Green
        'LW_out': '#98df8a',     # Light green
        'Rn': '#1f77b4'          # Blue (same as in energy balance plot)
    }
    
    # Plot each component in a specific order: SW_in, SW_out, LW_in, LW_out, Rn
    plot_order = ['SW_in', 'SW_out', 'LW_in', 'LW_out', 'Rn']
    plot_items = [(name, plot_components[name]) for name in plot_order if name in plot_components]
    
    for i, (name, series) in enumerate(plot_items):
        ax = axes[i]
        color = colors.get(name, None)
        ax.plot(series.index, series, color=color, linewidth=1.5, label=name)
        ax.set_ylabel(f'{name} (W/m²)')
        ax.set_title(name)
        ax.grid(True, alpha=0.3)
        ax.axhline(y=0, color='black', linestyle='--', linewidth=0.5)
    
    # Hide unused subplots
    for i in range(len(plot_items), len(axes)):
        axes[i].set_visible(False)
    
    # Set x-axis label on bottom row
    bottom_axes = axes[-2:] if nrows > 1 else axes
    for ax in bottom_axes:
        ax.set_xlabel('Date')
    
    # Rotate x-axis labels to prevent overlap
    for ax in axes:
        if ax.get_visible():
            ax.tick_params(axis='x', rotation=45, labelsize=9)
            for label in ax.get_xticklabels():
                label.set_ha('right')
    
    if title:
        fig.suptitle(title, fontsize=14, fontweight='bold')
    else:
        fig.suptitle('Radiation Components', fontsize=14, fontweight='bold')
    
    # Adjust layout to make room for rotated labels
    plt.tight_layout(rect=[0, 0.03, 1, 0.96])
    return fig


def plot_soil_variables(
    df: pd.DataFrame,
    start: Optional[Union[str, pd.Timestamp]] = None,
    end: Optional[Union[str, pd.Timestamp]] = None,
    figsize: tuple = (14, 10),
    title: Optional[str] = None,
    swc_min: float = 0.0,
    swc_max: float = 1.0
) -> plt.Figure:
    """
    Plot soil temperature and soil water content sensors individually.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with soil variable columns. For Janga: TS_1_1_1, TS_2_1_1, TS_3_1_1
        and SWC_1_1_1, SWC_2_1_1, SWC_3_1_1. For other stations: TCAV_C_Avg(1-3)
        and VW_1_Avg, VW_2_Avg, VW_3_Avg
    start, end : str | pd.Timestamp | None, optional
        Date range to plot
    figsize : tuple, default=(14, 10)
        Figure size (width, height)
    title : str | None, optional
        Plot title
    
    Returns
    -------
    plt.Figure
        Matplotlib figure object
    """
    # Try to find soil temperature columns (different naming conventions)
    ts_cols = []
    # Check for Dragan station names first (with [DegC] suffix)
    for pattern in ['TCAV_C_Avg(1) [DegC]', 'TCAV_C_Avg(2) [DegC]', 'TCAV_C_Avg(3) [DegC]']:
        if pattern in df.columns:
            ts_cols.append(pattern)
    # Then check standard names
    for pattern in ['TS_1_1_1', 'TS_2_1_1', 'TS_3_1_1', 'TCAV_C_Avg(1)', 'TCAV_C_Avg(2)', 'TCAV_C_Avg(3)']:
        if pattern in df.columns and pattern not in ts_cols:
            ts_cols.append(pattern)
    
    # Try to find soil water content columns
    swc_cols = []
    for pattern in ['SWC_1_1_1', 'SWC_2_1_1', 'SWC_3_1_1', 'VW_1_Avg', 'VW_2_Avg', 'VW_3_Avg']:
        if pattern in df.columns:
            swc_cols.append(pattern)
    
    if not ts_cols and not swc_cols:
        raise ValueError("No soil variables found. Expected: TS_1_1_1/TS_2_1_1/TS_3_1_1 or TCAV_C_Avg(1-3) for temperature, "
                        "SWC_1_1_1/SWC_2_1_1/SWC_3_1_1 or VW_1_Avg/VW_2_Avg/VW_3_Avg for water content")
    
    # Slice to date range if provided
    if start is not None or end is not None:
        plot_df = df.loc[
            (df.index >= pd.to_datetime(start or df.index.min())) &
            (df.index <= pd.to_datetime(end or df.index.max()))
        ]
    else:
        plot_df = df.copy()
    
    # Create subplots: 2 rows (temperature and SWC), up to 3 columns (one per sensor)
    nrows = 2 if (ts_cols and swc_cols) else 1
    ncols = max(len(ts_cols), len(swc_cols), 1)
    
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, sharex=True)
    # Ensure axes is always a list of matplotlib axes objects
    # matplotlib.subplots returns different types depending on grid size
    if nrows == 1 and ncols == 1:
        axes = [axes]
    elif nrows == 1 or ncols == 1:
        # Single row or single column - axes is a 1D array
        if isinstance(axes, np.ndarray):
            axes = axes.tolist()
        elif not isinstance(axes, list):
            axes = [axes]
    else:
        # Multiple rows and columns - axes is a 2D array
        if isinstance(axes, np.ndarray):
            axes = axes.flatten().tolist()
        else:
            axes = list(axes.flatten()) if hasattr(axes, 'flatten') else list(axes)
    
    # Colors for sensors
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
    
    # Plot soil temperature
    if ts_cols:
        row_idx = 0
        for i, col in enumerate(ts_cols):
            ax_idx = row_idx * ncols + i
            if ax_idx < len(axes):
                ax = axes[ax_idx]
                color = colors[i % len(colors)]
                sensor_num = col.split('_')[1] if '_' in col else str(i+1)
                ax.plot(plot_df.index, plot_df[col], color=color, linewidth=1.5, 
                       label=f'Sensor {sensor_num}')
                ax.set_ylabel('Temperature (°C)')
                ax.set_title(f'Soil Temperature - Sensor {sensor_num}')
                ax.grid(True, alpha=0.3)
                ax.legend()
    
    # Plot soil water content
    if swc_cols:
        row_idx = 1 if ts_cols else 0
        for i, col in enumerate(swc_cols):
            ax_idx = row_idx * ncols + i
            if ax_idx < len(axes):
                ax = axes[ax_idx]
                color = colors[i % len(colors)]
                sensor_num = col.split('_')[1] if '_' in col else str(i+1)
                
                # Get SWC data and apply physical limits
                swc_data = plot_df[col].copy()
                # Check if data is in percentage (0-100) or fraction (0-1)
                if swc_data.max() > 1.0:
                    # Data is in percentage, convert to fraction for plotting
                    swc_data = swc_data / 100.0
                    ylabel = 'SWC (%)'
                    ylim_max = swc_max * 100
                else:
                    ylabel = 'SWC (m³/m³)' if 'SWC' in col else 'VWC (m³/m³)'
                    ylim_max = swc_max
                
                # Filter to physical limits
                swc_data = swc_data.where((swc_data >= swc_min) & (swc_data <= swc_max))
                
                ax.plot(plot_df.index, swc_data, color=color, linewidth=1.5,
                       label=f'Sensor {sensor_num}')
                ax.set_ylabel(ylabel)
                ax.set_ylim(swc_min, ylim_max)
                ax.set_title(f'Soil Water Content - Sensor {sensor_num}')
                ax.grid(True, alpha=0.3)
                ax.legend()
    
    # Hide unused subplots
    total_plots = len(ts_cols) + len(swc_cols)
    for i in range(total_plots, len(axes)):
        if i < len(axes):
            axes[i].set_visible(False)
    
    # Set x-axis label on bottom row
    bottom_start = ncols if ts_cols and swc_cols else 0
    for ax in axes[bottom_start:]:
        if ax.get_visible():
            ax.set_xlabel('Date')
    
    # Rotate x-axis labels to prevent overlap
    for ax in axes:
        if ax.get_visible():
            ax.tick_params(axis='x', rotation=45, labelsize=9)
            for label in ax.get_xticklabels():
                label.set_ha('right')
    
    if title:
        fig.suptitle(title, fontsize=14, fontweight='bold')
    else:
        fig.suptitle('Soil Variables', fontsize=14, fontweight='bold')
    
    # Adjust layout to make room for rotated labels
    plt.tight_layout(rect=[0, 0.03, 1, 0.96])
    return fig
