"""
Plot Raw vs Processed Soil Heat Flux Comparison

This script loads soil sensor data and compares:
- Raw soil heat flux (G_raw) from sensors
- Processed soil heat flux (G) after applying calculate_soil_heat_flux()
- Storage term (Gs) and other components

Shows the effect of processing on the soil heat flux measurements.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Add package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ec_analysis import load_ec_data, calculate_soil_heat_flux

# ============================================================================
# CONFIGURATION
# ============================================================================
STATION = 'Kayoro'  # Change to your station: Nazinga, Mole, Kayoro, Sumbrungu, Gorigo, Janga
DATA_DIR = Path('/Users/hingerl-l/Data/merged_long')
EDDYPRO_DIR = Path('/Users/hingerl-l/Data')
DRAGAN_DATA_DIR = Path('/Users/hingerl-l/Diss/Data/ECdata_Dragan')

# Output directory for plots (in same folder as script)
PLOTS_DIR = Path(__file__).parent / 'plots'
PLOTS_DIR.mkdir(exist_ok=True)

# Date range for plotting (optional - set to None to use all data)
START_DATE = '2018-01-01'  # Use post-2016 data where G is calculated
END_DATE = '2024-01-01'

# File paths
if STATION in ['Kayoro', 'Nazinga', 'Sumbrungu']:
    # For Dragan stations: use Parquet files for post-2016 data (where G is calculated)
    CR1000_FILE = DATA_DIR / f'{STATION}_cr1000_merged_long.parquet'
    cutoff_date = pd.to_datetime('2016-01-01')
elif STATION == 'Gorigo':
    CR1000_FILE = EDDYPRO_DIR / STATION / 'merged' / f'{STATION}_cr1000_merged.csv'
else:
    CR1000_FILE = DATA_DIR / f'{STATION}_cr1000_merged_long.parquet'

# ============================================================================
# LOAD DATA
# ============================================================================
print("=" * 60)
print(f"Loading Soil Sensor Data for {STATION}")
print("=" * 60)

if not CR1000_FILE.exists():
    print(f"❌ Error: CR1000 file not found: {CR1000_FILE}")
    sys.exit(1)

print(f"Loading CR1000 data: {CR1000_FILE.name}")
df_cr1000 = load_ec_data(CR1000_FILE)

# Filter to post-2016 for Dragan stations (where G is calculated, not pre-calculated)
if STATION in ['Kayoro', 'Nazinga', 'Sumbrungu']:
    df_cr1000 = df_cr1000[df_cr1000.index >= cutoff_date].copy()
    print(f"  ✓ Filtered to post-2016 data (where G is calculated)")

print(f"  ✓ Loaded {len(df_cr1000)} records")
print(f"  ✓ Date range: {df_cr1000.index.min()} to {df_cr1000.index.max()}")
print(f"  ✓ Columns: {list(df_cr1000.columns[:10])}...")

# Filter to date range if specified
if START_DATE is not None:
    df_cr1000 = df_cr1000[df_cr1000.index >= pd.to_datetime(START_DATE)]
if END_DATE is not None:
    df_cr1000 = df_cr1000[df_cr1000.index <= pd.to_datetime(END_DATE)]

if len(df_cr1000) == 0:
    print(f"❌ Error: No data in specified date range")
    sys.exit(1)

print(f"  ✓ After date filter: {len(df_cr1000)} records")
print(f"  ✓ Date range: {df_cr1000.index.min()} to {df_cr1000.index.max()}")

# ============================================================================
# CALCULATE SOIL HEAT FLUX
# ============================================================================
print("\n" + "=" * 60)
print("Calculating Soil Heat Flux")
print("=" * 60)

try:
    # Calculate G with components
    G_components = calculate_soil_heat_flux(
        df_cr1000,
        station=STATION,
        return_components=True  # Get G_raw, Gs, Cv, etc.
    )

    G_raw = G_components['G_raw']
    G = G_components['G']
    Gs = G_components['Gs']
    Ts = G_components['Ts_3cm']
    VWC = G_components['VWC']
    Cv = G_components['Cv']

    print(f"  ✓ Calculated G components:")
    print(f"     G_raw: {G_raw.notna().sum()} values (range: {G_raw.min():.1f} to {G_raw.max():.1f} W/m²)")
    print(f"     G:     {G.notna().sum()} values (range: {G.min():.1f} to {G.max():.1f} W/m²)")
    print(f"     Gs:    {Gs.notna().sum()} values (range: {Gs.min():.3f} to {Gs.max():.3f} W/m²)")
    print(f"     Ts:    {Ts.notna().sum()} values (range: {Ts.min():.1f} to {Ts.max():.1f} °C)")
    print(f"     VWC:   {VWC.notna().sum()} values (range: {VWC.min():.3f} to {VWC.max():.3f} m³/m³)")

    # Debug: Check if Gs is being added correctly
    common_idx = G_raw.index.intersection(Gs.index)
    if len(common_idx) > 0:
        G_raw_sample = G_raw.loc[common_idx].dropna()
        Gs_sample = Gs.loc[common_idx].dropna()
        G_sample = G.loc[common_idx].dropna()
        common_all = G_raw_sample.index.intersection(Gs_sample.index).intersection(G_sample.index)
        if len(common_all) > 0:
            diff_check = (G_sample.loc[common_all] - G_raw_sample.loc[common_all] - Gs_sample.loc[common_all]).abs()
            print(f"\n  Debug - Checking G = G_raw + Gs:")
            print(f"     Mean absolute difference: {diff_check.mean():.6f} W/m²")
            print(f"     Max absolute difference: {diff_check.max():.6f} W/m²")
            print(f"     Mean Gs magnitude: {Gs_sample.loc[common_all].abs().mean():.3f} W/m²")
            print(f"     Mean G_raw magnitude: {G_raw_sample.loc[common_all].abs().mean():.1f} W/m²")
            print(f"     Gs/G_raw ratio: {(Gs_sample.loc[common_all].abs() / G_raw_sample.loc[common_all].abs()).mean():.4f}")

except Exception as e:
    print(f"❌ Error calculating soil heat flux: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ============================================================================
# CREATE PLOTS
# ============================================================================
print("\n" + "=" * 60)
print("Creating Plots")
print("=" * 60)

# Plot 1: Time series comparison - Raw vs Processed G
fig1, axes = plt.subplots(2, 1, figsize=(16, 10), sharex=True)

# Top panel: G_raw and G
axes[0].plot(G_raw.index, G_raw, 'r-', linewidth=1.5, alpha=0.7, label='G_raw (Raw sensor data)')
axes[0].plot(G.index, G, 'b-', linewidth=1.5, alpha=0.8, label='G (Processed: G_raw + Gs)')
axes[0].set_ylabel('Soil Heat Flux (W/m²)', fontsize=12)
axes[0].set_title(f'Raw vs Processed Soil Heat Flux - {STATION}', fontsize=14, fontweight='bold')
axes[0].set_ylim(-200, 400)
axes[0].grid(True, alpha=0.3)
axes[0].axhline(y=0, color='k', linestyle='--', linewidth=0.5)
axes[0].legend(fontsize=11, loc='upper right')

# Bottom panel: Difference (G - G_raw) = Gs
difference = G - G_raw
axes[1].plot(difference.index, difference, 'g-', linewidth=1.5, alpha=0.7, label='Gs (Storage term = G - G_raw)')
axes[1].set_ylabel('Gs (W/m²)', fontsize=12)
axes[1].set_xlabel('Date', fontsize=12)
axes[1].set_title('Storage Term (Gs)', fontsize=12)
axes[1].grid(True, alpha=0.3)
axes[1].axhline(y=0, color='k', linestyle='--', linewidth=0.5)
axes[1].legend(fontsize=11)

plt.tight_layout()
fig1.savefig(PLOTS_DIR / f'{STATION}_soil_heat_flux_raw_vs_processed.png', dpi=300, bbox_inches='tight')
print(f"✓ Plot saved: {PLOTS_DIR.name}/{STATION}_soil_heat_flux_raw_vs_processed.png")

# Plot 2: Components overview
fig2, axes = plt.subplots(4, 1, figsize=(16, 12), sharex=True)

# G_raw
axes[0].plot(G_raw.index, G_raw, 'r-', linewidth=1.5, alpha=0.7)
axes[0].set_ylabel('G_raw (W/m²)', fontsize=11)
axes[0].set_title(f'Soil Heat Flux Components - {STATION}', fontsize=14, fontweight='bold')
axes[0].grid(True, alpha=0.3)
axes[0].axhline(y=0, color='k', linestyle='--', linewidth=0.5)

# Gs
axes[1].plot(Gs.index, Gs, 'g-', linewidth=1.5, alpha=0.7)
axes[1].set_ylabel('Gs (W/m²)', fontsize=11)
axes[1].grid(True, alpha=0.3)
axes[1].axhline(y=0, color='k', linestyle='--', linewidth=0.5)

# G (total)
axes[2].plot(G.index, G, 'b-', linewidth=1.5, alpha=0.8)
axes[2].set_ylabel('G (W/m²)', fontsize=11)
axes[2].grid(True, alpha=0.3)
axes[2].axhline(y=0, color='k', linestyle='--', linewidth=0.5)

# Soil temperature
axes[3].plot(Ts.index, Ts, 'orange', linewidth=1.5, alpha=0.7)
axes[3].set_ylabel('Ts (°C)', fontsize=11)
axes[3].set_xlabel('Date', fontsize=12)
axes[3].grid(True, alpha=0.3)

plt.tight_layout()
fig2.savefig(PLOTS_DIR / f'{STATION}_soil_heat_flux_components.png', dpi=300, bbox_inches='tight')
print(f"✓ Plot saved: {PLOTS_DIR.name}/{STATION}_soil_heat_flux_components.png")

# Plot 3: Scatter plot - G_raw vs G
fig3, ax = plt.subplots(1, 1, figsize=(10, 8))

# Align indices for scatter plot
common_idx = G_raw.index.intersection(G.index)
G_raw_aligned = G_raw.loc[common_idx].dropna()
G_aligned = G.loc[common_idx].dropna()
common_final = G_raw_aligned.index.intersection(G_aligned.index)
G_raw_scatter = G_raw_aligned.loc[common_final]
G_scatter = G_aligned.loc[common_final]

ax.scatter(G_raw_scatter, G_scatter, alpha=0.5, s=10, edgecolors='none')
ax.plot([G_raw_scatter.min(), G_raw_scatter.max()],
        [G_raw_scatter.min(), G_raw_scatter.max()],
        'r--', linewidth=2, label='1:1 line')

# Calculate statistics
correlation = np.corrcoef(G_raw_scatter, G_scatter)[0, 1]
mean_diff = (G_scatter - G_raw_scatter).mean()
std_diff = (G_scatter - G_raw_scatter).std()

ax.set_xlabel('G_raw (W/m²)', fontsize=12)
ax.set_ylabel('G (Processed) (W/m²)', fontsize=12)
ax.set_title(f'G_raw vs G (Processed) - {STATION}', fontsize=14, fontweight='bold')
ax.grid(True, alpha=0.3)

# Add statistics text
stats_text = f'R² = {correlation**2:.3f}\nMean difference = {mean_diff:.2f} W/m²\nStd difference = {std_diff:.2f} W/m²'
ax.text(0.05, 0.95, stats_text, transform=ax.transAxes, fontsize=11,
        verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
ax.legend(fontsize=11)

plt.tight_layout()
fig3.savefig(PLOTS_DIR / f'{STATION}_soil_heat_flux_scatter.png', dpi=300, bbox_inches='tight')
print(f"✓ Plot saved: {PLOTS_DIR.name}/{STATION}_soil_heat_flux_scatter.png")

# Print statistics
print("\n" + "=" * 60)
print("Statistics")
print("=" * 60)
print(f"G_raw (Raw sensor data):")
print(f"  Mean: {G_raw.mean():.2f} W/m²")
print(f"  Std:  {G_raw.std():.2f} W/m²")
print(f"  Min:  {G_raw.min():.2f} W/m²")
print(f"  Max:  {G_raw.max():.2f} W/m²")
print(f"  Non-NaN values: {G_raw.notna().sum()}")

print(f"\nG (Processed: G_raw + Gs):")
print(f"  Mean: {G.mean():.2f} W/m²")
print(f"  Std:  {G.std():.2f} W/m²")
print(f"  Min:  {G.min():.2f} W/m²")
print(f"  Max:  {G.max():.2f} W/m²")
print(f"  Non-NaN values: {G.notna().sum()}")

print(f"\nGs (Storage term):")
print(f"  Mean: {Gs.mean():.2f} W/m²")
print(f"  Std:  {Gs.std():.2f} W/m²")
print(f"  Min:  {Gs.min():.2f} W/m²")
print(f"  Max:  {Gs.max():.2f} W/m²")

print(f"\nDifference (G - G_raw):")
print(f"  Mean: {mean_diff:.2f} W/m²")
print(f"  Std:  {std_diff:.2f} W/m²")

print("\n✓ All plots created successfully!")
plt.show()
