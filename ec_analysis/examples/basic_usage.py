"""
Basic usage examples for the EC Analysis package.

This script demonstrates how to:
1. Load EC data from different formats
2. Clean and process data
3. Calculate energy balance components
4. Create visualizations
"""

import sys
from pathlib import Path

# Add package to path (if not installed)
sys.path.insert(0, str(Path(__file__).parent.parent))

from ec_analysis import (
    load_ec_data,
    clean_dataframe,
    resample_data,
    calculate_soil_heat_flux,
    plot_time_series,
    plot_energy_balance,
)

# Example 1: Load data
print("=" * 60)
print("Example 1: Loading Data")
print("=" * 60)

# Load Parquet file (automatic format detection)
# df = load_ec_data('/Users/hingerl-l/Data/merged_long/Nazinga_radiation_merged_long.parquet')
# print(f"Loaded {len(df)} records")
# print(f"Columns: {list(df.columns[:5])}...")

# Example 2: Clean data
print("\n" + "=" * 60)
print("Example 2: Data Cleaning")
print("=" * 60)

# df_clean = clean_dataframe(df)
# print(f"Cleaned DataFrame: {len(df_clean)} records")

# Example 3: Resample data
print("\n" + "=" * 60)
print("Example 3: Time Aggregation")
print("=" * 60)

# Resample to daily (precipitation summed, others averaged)
# df_daily = resample_data(df_clean, freq='1D', method='auto')
# print(f"Resampled to daily: {len(df_daily)} records")

# Example 4: Calculate soil heat flux
print("\n" + "=" * 60)
print("Example 4: Soil Heat Flux Calculation")
print("=" * 60)

# For a DataFrame with soil sensor data:
# G = calculate_soil_heat_flux(
#     df,
#     station='Nazinga'  # Uses station-specific config
# )
# print(f"Calculated G: {len(G)} values")

# Example 5: Plotting
print("\n" + "=" * 60)
print("Example 5: Plotting")
print("=" * 60)

# Plot time series
# plot_time_series(df['H'], title='Sensible Heat Flux', ylabel='H (W/m²)')

# Plot energy balance (if you have energy balance DataFrame)
# plot_energy_balance(eb_df, title='Energy Balance Components')

print("\n✅ Examples completed!")
print("\nNote: Uncomment the code above and provide actual file paths to run.")

