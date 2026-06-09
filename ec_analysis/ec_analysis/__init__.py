# ec_analysis/__init__.py
"""
EC Data Analysis Package

A comprehensive package for loading, analyzing, and visualizing
Eddy Covariance and climate data.
"""

# Main API: Easy access to data loading
from .data_loaders import load_ec_data, TOA5Loader, EddyProLoader, ParquetLoader

# Utility functions
from .utils import (
    get_column_mapping,
    apply_column_names,
    remove_invalid_values,
    filter_quality_flags,
    clean_dataframe,
)

# Aggregation functions
from .aggregation import (
    safe_slice,
    resample_data,
    build_energy_balance_df,
    calculate_storage_change,
    calculate_soil_heat_flux,
)

# Plotting functions
from .plotting import (
    plot_time_series,
    plot_energy_balance,
    plot_energy_balance_closure,
    plot_diurnal_cycle,
    plot_radiation_components,
    plot_albedo,
)

__version__ = "0.1.0"

__all__ = [
    # Data loaders
    'load_ec_data',
    'TOA5Loader',
    'EddyProLoader',
    'ParquetLoader',
    # Utilities
    'get_column_mapping',
    'apply_column_names',
    'remove_invalid_values',
    'filter_quality_flags',
    'clean_dataframe',
    # Aggregation
    'safe_slice',
    'resample_data',
    'build_energy_balance_df',
    'calculate_storage_change',
    'calculate_soil_heat_flux',
    # Plotting
    'plot_time_series',
    'plot_energy_balance',
    'plot_energy_balance_closure',
    'plot_diurnal_cycle',
    'plot_radiation_components',
    'plot_albedo',
]