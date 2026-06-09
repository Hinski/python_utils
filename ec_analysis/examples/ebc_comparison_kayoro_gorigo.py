"""
Energy Balance Closure Comparison: Kayoro vs Gorigo

This script creates side-by-side EBC plots for Kayoro and Gorigo,
using LE+H shifted by +30 minutes.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import pearsonr

# Add package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ec_analysis import (
    load_ec_data,
    calculate_soil_heat_flux,
    filter_quality_flags,
    build_energy_balance_df,
)

# ============================================================================
# CONFIGURATION
# ============================================================================
DATA_DIR = Path('/Users/hingerl-l/Data/merged_long')
EDDYPRO_DIR = Path('/Users/hingerl-l/Data')
DRAGAN_DATA_DIR = Path('/Users/hingerl-l/Diss/Data/ECdata_Dragan')

# Date ranges
KAYORO_START = '2013-01-01'
KAYORO_END = '2015-12-31'
GORIGO_START = '2020-01-01'
GORIGO_END = '2022-12-31'

# Shifts: Kayoro +30 minutes, Gorigo +60 minutes (in 30-min intervals)
KAYORO_SHIFT = 1  # +30 minutes
#GORIGO_SHIFT = 2  # +60 minutes
GORIGO_SHIFT = 1  # +30 minutes

# ============================================================================
# Helper function to load station data
# ============================================================================
def load_station_data(station, start_date, end_date):
    """Load all required data for a station."""
    print(f"\n{'='*60}")
    print(f"Loading data for {station}")
    print(f"{'='*60}")

    # Initialize variables
    df_cr1000 = None
    df_rad = None
    df_eddypro = None
    G = None
    Rn = None
    LE = None
    H = None
    Delta = None

    # File paths based on station
    if station == 'Kayoro':
        # Kayoro: Load from Dragan CSV
        CR1000_FILE = DRAGAN_DATA_DIR / 'Kayoro.csv'

        if CR1000_FILE.exists():
            print(f"Loading Kayoro data from Dragan CSV: {CR1000_FILE.name}")
            df_dragan = pd.read_csv(
                CR1000_FILE,
                sep=",",
                low_memory=False,
                na_values=["NAN", "NA", "-9999", "-9999.0", "-999", "**************"]
            )

            # Parse T_begin timestamp column
            if 'T_begin' in df_dragan.columns:
                df_dragan['T_begin'] = pd.to_datetime(df_dragan['T_begin'], format='%m/%d/%y %H:%M', errors='coerce')
                df_dragan = df_dragan.set_index('T_begin')
                df_dragan.index.name = 'TIMESTAMP'
                df_dragan = df_dragan[df_dragan.index.notna()]
                df_dragan = df_dragan.sort_index()
                df_dragan = df_dragan[~df_dragan.index.duplicated(keep='first')]

            print(f"  ✓ Loaded {len(df_dragan)} records")

            # Exclude LvE and HTs (from EddyPro)
            columns_to_exclude = ['LvE', 'HTs', 'LvE[W/m_]      ', 'HTs[W/m_]      ']
            df_cr1000 = df_dragan.drop(columns=[col for col in columns_to_exclude if col in df_dragan.columns])
            df_rad = df_dragan.copy()

        # Load EddyPro data (find most recent file)
        eddypro_dir = EDDYPRO_DIR / 'Kayoro' / 'processed' / 'fluxes'
        if eddypro_dir.exists():
            eddypro_files = list(eddypro_dir.glob('eddypro_Kayoro_full_output_*.csv'))
            if eddypro_files:
                eddypro_file = max(eddypro_files, key=lambda p: p.stat().st_mtime)
                print(f"Loading EddyPro data: {eddypro_file.name}")
                df_eddypro = load_ec_data(eddypro_file)
                print(f"  ✓ Loaded {len(df_eddypro)} records")

    elif station == 'Gorigo':
        # Gorigo: Standard structure
        CR1000_FILE = EDDYPRO_DIR / 'Gorigo' / 'merged' / 'Gorigo_cr1000_merged.csv'
        RADIATION_FILE = DATA_DIR / 'Gorigo_radiation_merged_long.parquet'

        if CR1000_FILE.exists():
            print(f"Loading CR1000 data: {CR1000_FILE.name}")
            df_cr1000 = load_ec_data(CR1000_FILE)
            print(f"  ✓ Loaded {len(df_cr1000)} records")

        if RADIATION_FILE.exists():
            print(f"Loading Radiation data: {RADIATION_FILE.name}")
            df_rad = pd.read_parquet(RADIATION_FILE)
            print(f"  ✓ Loaded {len(df_rad)} records")

        # Load EddyPro data (find most recent file)
        eddypro_dir = EDDYPRO_DIR / 'Gorigo' / 'processed' / 'fluxes'
        if eddypro_dir.exists():
            eddypro_files = list(eddypro_dir.glob('eddypro_Gorigo_full_output_*.csv'))
            if eddypro_files:
                eddypro_file = max(eddypro_files, key=lambda p: p.stat().st_mtime)
                print(f"Loading EddyPro data: {eddypro_file.name}")
                df_eddypro = load_ec_data(eddypro_file)
                print(f"  ✓ Loaded {len(df_eddypro)} records")

    # Calculate G (soil heat flux)
    if df_cr1000 is not None:
        print(f"\nCalculating G for {station}...")
        G = calculate_soil_heat_flux(
            df_cr1000,
            station=station,
            return_components=False
        )
        print(f"  ✓ Calculated G: {len(G)} values")
        print(f"  ✓ G range: {G.min():.1f} to {G.max():.1f} W/m²")

    # Calculate Rn (net radiation)
    if df_rad is not None:
        print(f"\nCalculating Rn for {station}...")
        SW_in = None
        SW_out = None
        LW_in = None
        LW_out = None

        if station == 'Kayoro':
            SW_in = df_rad.get('SW_in korrigiert', None)
            SW_out = df_rad.get('SW_out korrigiert', None)
            LW_in = df_rad.get('LW_in_Avg [W/m^2]', None)
            LW_out = df_rad.get('LW_out_Avg [W/m^2]', None)
        else:
            # Gorigo: Standard names
            SW_in = df_rad.get('SR_in_Avg', None)
            SW_out = df_rad.get('SR_out_Avg', None)
            LW_in = df_rad.get('IR_in_Avg', None)
            LW_out = df_rad.get('IR_out_Avg', None)

        if all([SW_in is not None, SW_out is not None, LW_in is not None, LW_out is not None]):
            Rn = (SW_in - SW_out) + (LW_in - LW_out)
            print(f"  ✓ Calculated Rn: {len(Rn)} values")
        else:
            print("  ⚠️  Could not calculate Rn from radiation components")

    # Get LE and H from EddyPro
    if df_eddypro is not None:
        print(f"\nExtracting LE and H from EddyPro for {station}...")

        if station == 'Kayoro':
            LE = df_eddypro.get('LvE', None)
            H = df_eddypro.get('HTs', None)
            if LE is None:
                LE = df_eddypro.get('LE', None)
            if H is None:
                H = df_eddypro.get('H', None)
        else:
            LE = df_eddypro.get('LE', None)
            H = df_eddypro.get('H', None)

        # Convert to numeric
        if LE is not None:
            LE = pd.to_numeric(LE, errors='coerce')
        if H is not None:
            H = pd.to_numeric(H, errors='coerce')

        # Filter by quality flags
        if station == 'Kayoro':
            if LE is not None and 'Flag(LvE)' in df_eddypro.columns:
                flag_le = pd.to_numeric(df_eddypro['Flag(LvE)'], errors='coerce')
                high_quality_mask = (flag_le <= 1) & (flag_le.notna())
                LE = LE[high_quality_mask]
            if H is not None and 'Flag(HTs)' in df_eddypro.columns:
                flag_h = pd.to_numeric(df_eddypro['Flag(HTs)'], errors='coerce')
                high_quality_mask = (flag_h <= 1) & (flag_h.notna())
                H = H[high_quality_mask]
        else:
            # Gorigo: Check Flag(LE) and Flag(H) or qc_LE, qc_H
            if LE is not None:
                if 'Flag(LE)' in df_eddypro.columns:
                    flag_le = pd.to_numeric(df_eddypro['Flag(LE)'], errors='coerce')
                    high_quality_mask = (flag_le <= 1) & (flag_le.notna())
                    LE = LE[high_quality_mask]
                elif 'qc_LE' in df_eddypro.columns:
                    LE = filter_quality_flags(df_eddypro, 'qc_LE', max_flag=1, data_column='LE')
            if H is not None:
                if 'Flag(H)' in df_eddypro.columns:
                    flag_h = pd.to_numeric(df_eddypro['Flag(H)'], errors='coerce')
                    high_quality_mask = (flag_h <= 1) & (flag_h.notna())
                    H = H[high_quality_mask]
                elif 'qc_H' in df_eddypro.columns:
                    H = filter_quality_flags(df_eddypro, 'qc_H', max_flag=1, data_column='H')

        # Additional filter: LE > -200
        if LE is not None:
            LE = LE[LE > -200]

        print(f"  ✓ LE: {len(LE) if LE is not None else 0} values")
        print(f"  ✓ H: {len(H) if H is not None else 0} values")

    # Delta (storage change) - set to zero
    if G is not None:
        Delta = pd.Series(0, index=G.index)

    # Get radiation components for build_energy_balance_df
    SW_in = None
    SW_out = None
    LW_in = None
    LW_out = None

    if station == 'Kayoro':
        if df_rad is not None:
            SW_in = df_rad.get('SW_in korrigiert', None)
            SW_out = df_rad.get('SW_out korrigiert', None)
            LW_in = df_rad.get('LW_in_Avg [W/m^2]', None)
            LW_out = df_rad.get('LW_out_Avg [W/m^2]', None)
    elif station == 'Gorigo':
        if df_rad is not None:
            SW_in = df_rad.get('SR_in_Avg', None)
            SW_out = df_rad.get('SR_out_Avg', None)
            LW_in = df_rad.get('IR_in_Avg', None)
            LW_out = df_rad.get('IR_out_Avg', None)

    return {
        'G': G,
        'Rn': Rn,
        'LE': LE,
        'H': H,
        'Delta': Delta,
        'SW_in': SW_in,
        'SW_out': SW_out,
        'LW_in': LW_in,
        'LW_out': LW_out,
    }

# ============================================================================
# Main script
# ============================================================================
print("="*60)
print("Energy Balance Closure Comparison: Kayoro vs Gorigo")
print("="*60)

# Load data for both stations
kayoro_data = load_station_data('Kayoro', KAYORO_START, KAYORO_END)
gorigo_data = load_station_data('Gorigo', GORIGO_START, GORIGO_END)

# ============================================================================
# Prepare data and create EBC plots
# ============================================================================
print("\n" + "="*60)
print("Preparing EBC plots (Kayoro: +30 min, Gorigo: +60 min)")
print("="*60)

fig, axes = plt.subplots(1, 2, figsize=(18, 8))
stations_data = [
    ('Kayoro', kayoro_data, KAYORO_START, KAYORO_END, axes[0], KAYORO_SHIFT),
    ('Gorigo', gorigo_data, GORIGO_START, GORIGO_END, axes[1], GORIGO_SHIFT),
]

for station_name, data, start_date, end_date, ax, shift_intervals in stations_data:
    print(f"\nProcessing {station_name}...")

    G = data['G']
    Rn = data['Rn']
    LE = data['LE']
    H = data['H']
    Delta = data['Delta']
    SW_in = data.get('SW_in', None)
    SW_out = data.get('SW_out', None)
    LW_in = data.get('LW_in', None)
    LW_out = data.get('LW_out', None)

    if G is None or Rn is None or LE is None or H is None:
        print(f"  ⚠️  Missing data for {station_name}, skipping...")
        ax.text(0.5, 0.5, f'Insufficient data\nfor {station_name}',
                ha='center', va='center', transform=ax.transAxes, fontsize=14)
        ax.set_title(station_name, fontsize=16, fontweight='bold')
        continue

    # Use build_energy_balance_df to properly align and resample data (same as energy_balance_closure.py)
    print(f"  Building energy balance DataFrame...")

    # Build energy balance DataFrame (this handles resampling and alignment properly)
    eb_df = build_energy_balance_df(
        SW_in=SW_in if SW_in is not None else pd.Series(0, index=G.index if G is not None else pd.DatetimeIndex([])),
        SW_out=SW_out if SW_out is not None else pd.Series(0, index=G.index if G is not None else pd.DatetimeIndex([])),
        LW_in=LW_in if LW_in is not None else pd.Series(0, index=G.index if G is not None else pd.DatetimeIndex([])),
        LW_out=LW_out if LW_out is not None else pd.Series(0, index=G.index if G is not None else pd.DatetimeIndex([])),
        LE=LE,
        H=H,
        G=G,
        Delta=Delta if Delta is not None else pd.Series(0, index=G.index if G is not None else pd.DatetimeIndex([])),
        start=start_date,
        end=end_date,
        site_name=station_name
    )

    if eb_df.empty:
        print(f"  ⚠️  Empty energy balance DataFrame for {station_name}")
        ax.text(0.5, 0.5, f'Insufficient data\nfor {station_name}',
                ha='center', va='center', transform=ax.transAxes, fontsize=14)
        ax.set_title(station_name, fontsize=16, fontweight='bold')
        continue

    print(f"  ✓ Energy balance DataFrame: {len(eb_df)} records")

    # Get data from eb_df (already properly aligned and resampled)
    LE_ebc = eb_df['LE'].copy()
    H_ebc = eb_df['H'].copy()
    Rn_ebc = eb_df['Rn'].copy()
    G_ebc = eb_df['G'].copy()
    Delta_ebc = eb_df.get('Delta', pd.Series(0, index=eb_df.index))

    # Calculate X-axis: Rn - G - Delta (exactly as in energy_balance_closure.py)
    x_data = Rn_ebc - G_ebc
    if Delta_ebc.notna().any() and (Delta_ebc != 0).any():
        x_data = x_data - Delta_ebc

    # Filter to valid range (same as energy_balance_closure.py)
    valid_mask = (
        (LE_ebc >= -300) & (LE_ebc <= 800) &
        (H_ebc >= -300) & (H_ebc <= 800)
    )
    x_data = x_data[valid_mask]
    LE_ebc = LE_ebc[valid_mask]
    H_ebc = H_ebc[valid_mask]
    LE_H_ebc = LE_ebc + H_ebc

    # Use all data (not just daytime)
    # Shift LE+H
    if shift_intervals == 0:
        y_data = LE_H_ebc
        x_plot = x_data
    else:
        LE_H_shifted = LE_H_ebc.shift(-shift_intervals)
        # Align indices
        common_shifted = x_data.index.intersection(LE_H_shifted.index)
        y_data = LE_H_shifted.loc[common_shifted].dropna()
        x_plot = x_data.loc[y_data.index]

    # Remove NaN values
    mask_valid = x_plot.notna() & y_data.notna()
    x_clean = x_plot[mask_valid]
    y_clean = y_data[mask_valid]

    # Use all data (not just daytime)
    if len(x_clean) < 10:
        print(f"  ⚠️  Insufficient data for {station_name} ({len(x_clean)} points)")
        ax.text(0.5, 0.5, f'Insufficient data\nfor {station_name}',
                ha='center', va='center', transform=ax.transAxes, fontsize=14)
        ax.set_title(station_name, fontsize=16, fontweight='bold')
        continue

    print(f"  ✓ {len(x_clean)} data points")

    # Scatter plot
    ax.scatter(x_clean, y_clean, alpha=0.5, s=20, edgecolors='none', color='black')

    # Calculate regression
    # Remove any remaining NaN or infinite values
    mask_final = np.isfinite(x_clean) & np.isfinite(y_clean)
    x_final = x_clean[mask_final]
    y_final = y_clean[mask_final]

    if len(x_final) < 10:
        print(f"  ⚠️  Insufficient valid data for {station_name} after filtering ({len(x_final)} points)")
        ax.text(0.5, 0.5, f'Insufficient data\nfor {station_name}',
                ha='center', va='center', transform=ax.transAxes, fontsize=14)
        ax.set_title(station_name, fontsize=16, fontweight='bold')
        continue

    print(f"  ✓ {len(x_final)} valid data points for regression")
    print(f"  ✓ X range: {x_final.min():.1f} to {x_final.max():.1f} W/m²")
    print(f"  ✓ Y range: {y_final.min():.1f} to {y_final.max():.1f} W/m²")

    coeffs = np.polyfit(x_final, y_final, 1)
    slope = coeffs[0]
    intercept = coeffs[1]

    # Calculate R² using correlation coefficient (more robust)
    corr, _ = pearsonr(x_final, y_final)
    r2 = corr ** 2

    print(f"  ✓ Correlation: {corr:.4f}, R²: {r2:.4f}")

    # Plot regression line
    x_reg = np.array([x_final.min(), x_final.max()])
    y_reg = slope * x_reg + intercept
    ax.plot(x_reg, y_reg, 'r-', linewidth=2, label='Regression', zorder=2)

    # 1:1 line
    min_val = min(x_final.min(), y_final.min())
    max_val = max(x_final.max(), y_final.max())
    ax.plot([min_val, max_val], [min_val, max_val], '--', color='grey',
           linewidth=1.5, label='1:1 line', zorder=1)

    # Set limits
    ax.set_xlim(-200, 1000)
    ax.set_ylim(-200, 1000)

    # Labels and title (larger font sizes for publication)
    ax.set_xlabel('Rn - G (W/m²)', fontsize=20)
    ax.set_ylabel('LE + H (W/m²)', fontsize=20)
    ax.set_title(station_name, fontsize=24, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=18)

    # Increase tick label sizes
    ax.tick_params(axis='both', which='major', labelsize=18)

    # Add equation and R² text (larger font)
    equation_text = f'y = {slope:.2f}x + {intercept:.2f}\nR² = {r2:.2f}'
    ax.text(0.05, 0.95, equation_text, transform=ax.transAxes,
           fontsize=18, verticalalignment='top', bbox=dict(boxstyle='round',
           facecolor='wheat', alpha=0.8))

    print(f"  ✓ Slope: {slope:.3f}, R²: {r2:.3f}, N: {len(x_final)}")

# Finalize plot
plt.tight_layout()
plt.savefig('EBC_comparison_Kayoro_Gorigo.png', dpi=300, bbox_inches='tight')
print(f"\n✓ Plot saved: EBC_comparison_Kayoro_Gorigo.png")
plt.show()
