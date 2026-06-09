"""
Plot TK3 Energy Fluxes (Gorigo or Dragan stations).

This script loads and plots latent (LvE) and sensible (HTs) heat fluxes
from TK3 result data. No comparison with EddyPro fluxes.

- Gorigo: TK3 from merged result file under /Users/hingerl-l/Data/Gorigo/merged/
- Sumbrungu, Kayoro, Nazinga: TK3 from ECdata_Dragan CSV files (LvE, HTs columns).
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Add package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ============================================================================
# CONFIGURATION
# ============================================================================
# One of: 'Gorigo' (merged TK3 file) or 'Sumbrungu', 'Kayoro', 'Nazinga' (ECdata_Dragan CSV)
STATION = 'Gorigo'

EDDYPRO_DIR = Path('/Users/hingerl-l/Data')
DRAGAN_DATA_DIR = Path('/Users/hingerl-l/Diss/Data/ECdata_Dragan')

# Paths: Gorigo uses merged TK3 file; Dragan stations use ECdata_Dragan CSV
if STATION == 'Gorigo':
    TK3_RESULT_FILE = EDDYPRO_DIR / 'Gorigo' / 'merged' / 'Gorigo_result_merged.csv'
else:
    TK3_RESULT_FILE = DRAGAN_DATA_DIR / f'{STATION}.csv'

USE_DRAGAN_FORMAT = STATION in ['Sumbrungu', 'Kayoro', 'Nazinga']

# Date range for plotting (optional - set to None to use all data)
START_DATE = None  # '2020-01-01'
END_DATE = None    # '2023-01-01'

# ============================================================================
# LOAD DATA
# ============================================================================
print("=" * 60)
print(f"Loading TK3 Energy Fluxes for {STATION}")
print("=" * 60)

if not TK3_RESULT_FILE.exists():
    print(f"❌ Error: TK3 result file not found: {TK3_RESULT_FILE}")
    sys.exit(1)

print(f"Loading TK3 result data: {TK3_RESULT_FILE.name}")
na_vals = ["NAN", "NA", "-9999", "-9999.0", "-9999.9003906", "-999", "**************"]
df_tk3_result = pd.read_csv(TK3_RESULT_FILE, sep=",", low_memory=False, na_values=na_vals)

# Normalize column names (strip spaces) for Dragan files
df_tk3_result.columns = [c.strip() if isinstance(c, str) else c for c in df_tk3_result.columns]

# Timestamp column and parsing
timestamp_col = None
for col in ['TIMESTAMP', 'T_begin', 'Date', 'Time', 'timestamp']:
    if col in df_tk3_result.columns:
        timestamp_col = col
        break

if not timestamp_col:
    print(f"  ❌ Error: Could not find timestamp column. Available: {list(df_tk3_result.columns)}")
    sys.exit(1)

if USE_DRAGAN_FORMAT and timestamp_col == 'T_begin':
    df_tk3_result['T_begin'] = pd.to_datetime(df_tk3_result['T_begin'], format='%m/%d/%y %H:%M', errors='coerce')
else:
    df_tk3_result[timestamp_col] = pd.to_datetime(df_tk3_result[timestamp_col], errors='coerce')

df_tk3_result = df_tk3_result.set_index(timestamp_col)
df_tk3_result.index.name = 'TIMESTAMP'
df_tk3_result = df_tk3_result[df_tk3_result.index.notna()]
df_tk3_result = df_tk3_result.sort_index()
df_tk3_result = df_tk3_result[~df_tk3_result.index.duplicated(keep='first')]
print(f"  ✓ Loaded {len(df_tk3_result)} records")
print(f"  ✓ Date range: {df_tk3_result.index.min()} to {df_tk3_result.index.max()}")

# Extract TK3 fluxes: support both Gorigo-style and Dragan-style column names
LvE = None
HTs = None

# LvE: Gorigo uses LvE[W/m²] etc.; Dragan uses LvE[W/m_] (possibly with spaces)
lve_cols = ['LvE[W/m²]', 'LvE[W/m^2]', 'LvE[W/m_]', 'LvE']
hts_cols = ['HTs[W/m²]', 'HTs[W/m^2]', 'HTs[W/m_]', 'HTs']

for col_name in lve_cols:
    if col_name in df_tk3_result.columns:
        LvE = pd.to_numeric(df_tk3_result[col_name], errors='coerce')
        print(f"  ✓ Found LvE column: {col_name!r}")
        break
if LvE is None:
    for col in df_tk3_result.columns:
        if 'LvE' in str(col) and ('W/m' in str(col) or 'W/m²' in str(col) or 'W/m^2' in str(col)):
            LvE = pd.to_numeric(df_tk3_result[col], errors='coerce')
            print(f"  ✓ Found LvE column (variant): {col!r}")
            break

for col_name in hts_cols:
    if col_name in df_tk3_result.columns:
        HTs = pd.to_numeric(df_tk3_result[col_name], errors='coerce')
        print(f"  ✓ Found HTs column: {col_name!r}")
        break
if HTs is None:
    for col in df_tk3_result.columns:
        if 'HTs' in str(col) and ('W/m' in str(col) or 'W/m²' in str(col) or 'W/m^2' in str(col)):
            HTs = pd.to_numeric(df_tk3_result[col], errors='coerce')
            print(f"  ✓ Found HTs column (variant): {col!r}")
            break

if LvE is None:
    print(f"  ❌ Error: LvE column not found. Available columns: {list(df_tk3_result.columns)}")
    sys.exit(1)
if HTs is None:
    print(f"  ❌ Error: HTs column not found. Available columns: {list(df_tk3_result.columns)}")
    sys.exit(1)

print(f"  ✓ LvE: {LvE.notna().sum()} values (range: {LvE.min():.1f} to {LvE.max():.1f} W/m²)")
print(f"  ✓ HTs: {HTs.notna().sum()} values (range: {HTs.min():.1f} to {HTs.max():.1f} W/m²)")

# Slice to date range if specified
if START_DATE is not None:
    LvE = LvE[LvE.index >= pd.to_datetime(START_DATE)]
    HTs = HTs[HTs.index >= pd.to_datetime(START_DATE)]
    print(f"  ✓ After START_DATE filter: {LvE.notna().sum()} LvE, {HTs.notna().sum()} HTs values")

if END_DATE is not None:
    LvE = LvE[LvE.index <= pd.to_datetime(END_DATE)]
    HTs = HTs[HTs.index <= pd.to_datetime(END_DATE)]
    print(f"  ✓ After END_DATE filter: {LvE.notna().sum()} LvE, {HTs.notna().sum()} HTs values")

# ============================================================================
# CREATE PLOTS
# ============================================================================
print("\n" + "=" * 60)
print("Creating Plots")
print("=" * 60)

# Plot 1: Time series of LvE and HTs
fig1, axes = plt.subplots(2, 1, figsize=(16, 10), sharex=True)

# LvE plot
axes[0].plot(LvE.index, LvE, 'b-', linewidth=1, alpha=0.7, label='LvE (Latent Heat Flux)')
axes[0].set_ylabel('LvE (W/m²)', fontsize=14)
axes[0].set_ylim(-300, 800)
axes[0].set_title(f'TK3 Energy Fluxes - {STATION}', fontsize=16, fontweight='bold')
axes[0].grid(True, alpha=0.3)
axes[0].axhline(y=0, color='k', linestyle='--', linewidth=0.5)
axes[0].legend(fontsize=12)
axes[0].tick_params(axis='both', which='major', labelsize=12)

# HTs plot
axes[1].plot(HTs.index, HTs, 'r-', linewidth=1, alpha=0.7, label='HTs (Sensible Heat Flux)')
axes[1].set_ylabel('HTs (W/m²)', fontsize=14)
axes[1].set_ylim(-300, 800)
axes[1].set_xlabel('Date', fontsize=14)
axes[1].grid(True, alpha=0.3)
axes[1].axhline(y=0, color='k', linestyle='--', linewidth=0.5)
axes[1].legend(fontsize=12)
axes[1].tick_params(axis='both', which='major', labelsize=12)

plt.tight_layout()
fig1.savefig(f'{STATION}_TK3_fluxes_timeseries.png', dpi=300, bbox_inches='tight')
print(f"✓ Plot saved: {STATION}_TK3_fluxes_timeseries.png")

# Plot 2: Combined plot with both fluxes
fig2, ax = plt.subplots(1, 1, figsize=(16, 6))

ax.plot(LvE.index, LvE, 'b-', linewidth=1.5, alpha=0.7, label='LvE (Latent Heat Flux)')
ax.plot(HTs.index, HTs, 'r-', linewidth=1.5, alpha=0.7, label='HTs (Sensible Heat Flux)')
ax.set_ylabel('Energy Flux (W/m²)', fontsize=14)
ax.set_ylim(-300, 800)
ax.set_xlabel('Date', fontsize=14)
ax.set_title(f'TK3 Energy Fluxes - {STATION}', fontsize=16, fontweight='bold')
ax.grid(True, alpha=0.3)
ax.axhline(y=0, color='k', linestyle='--', linewidth=0.5)
ax.legend(fontsize=12)
ax.tick_params(axis='both', which='major', labelsize=12)

plt.tight_layout()
fig2.savefig(f'{STATION}_TK3_fluxes_combined.png', dpi=300, bbox_inches='tight')
print(f"✓ Plot saved: {STATION}_TK3_fluxes_combined.png")

# Plot 3: Diurnal cycle (if enough data)
if len(LvE.dropna()) > 100:
    print("\nCreating diurnal cycle plot...")

    # Calculate hour of day
    LvE_hour = LvE.dropna().groupby(LvE.dropna().index.hour).mean()
    HTs_hour = HTs.dropna().groupby(HTs.dropna().index.hour).mean()

    fig3, ax = plt.subplots(1, 1, figsize=(10, 6))

    ax.plot(LvE_hour.index, LvE_hour, 'b-o', linewidth=2, markersize=6, label='LvE (Latent Heat Flux)', alpha=0.8)
    ax.plot(HTs_hour.index, HTs_hour, 'r-s', linewidth=2, markersize=6, label='HTs (Sensible Heat Flux)', alpha=0.8)
    ax.set_xlabel('Hour of Day', fontsize=14)
    ax.set_ylabel('Energy Flux (W/m²)', fontsize=14)
    ax.set_ylim(-300, 800)
    ax.set_title(f'TK3 Energy Fluxes - Diurnal Cycle - {STATION}', fontsize=16, fontweight='bold')
    ax.set_xlim(-0.5, 23.5)
    ax.set_xticks(range(0, 24, 2))
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='k', linestyle='--', linewidth=0.5)
    ax.legend(fontsize=12)
    ax.tick_params(axis='both', which='major', labelsize=12)

    plt.tight_layout()
    fig3.savefig(f'{STATION}_TK3_fluxes_diurnal.png', dpi=300, bbox_inches='tight')
    print(f"✓ Plot saved: {STATION}_TK3_fluxes_diurnal.png")

# Print statistics
print("\n" + "=" * 60)
print("Statistics")
print("=" * 60)
print(f"LvE (Latent Heat Flux):")
print(f"  Mean: {LvE.mean():.2f} W/m²")
print(f"  Std:  {LvE.std():.2f} W/m²")
print(f"  Min:  {LvE.min():.2f} W/m²")
print(f"  Max:  {LvE.max():.2f} W/m²")
print(f"  Non-NaN values: {LvE.notna().sum()}")
print(f"\nHTs (Sensible Heat Flux):")
print(f"  Mean: {HTs.mean():.2f} W/m²")
print(f"  Std:  {HTs.std():.2f} W/m²")
print(f"  Min:  {HTs.min():.2f} W/m²")
print(f"  Max:  {HTs.max():.2f} W/m²")
print(f"  Non-NaN values: {HTs.notna().sum()}")

print("\n✓ All plots created successfully!")
plt.show()
