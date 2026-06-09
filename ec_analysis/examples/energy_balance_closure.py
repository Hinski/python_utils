"""
Example: Create Energy Balance Closure (EBC) plots with calculated soil heat flux.

This script demonstrates how to:
1. Load data from different sources (CR1000, EddyPro, Radiation)
2. Calculate soil heat flux (G) using station-specific configuration
3. Build energy balance DataFrame
4. Create Energy Balance Closure plots
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Add package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ec_analysis import (
    load_ec_data,
    calculate_soil_heat_flux,
    build_energy_balance_df,
    plot_energy_balance_closure,
    plot_energy_balance,
    plot_diurnal_cycle,
    filter_quality_flags,
)
from ec_analysis.plotting.energy_balance import plot_radiation_components, plot_soil_variables

# ============================================================================
# CONFIGURATION
# ============================================================================
STATION = 'Kayoro'  # Change to your station: Nazinga, Mole, Kayoro, Sumbrungu, Gorigo, Janga
DATA_DIR = Path('/Users/hingerl-l/Data/merged_long')
EDDYPRO_DIR = Path('/Users/hingerl-l/Data')
DRAGAN_DATA_DIR = Path('/Users/hingerl-l/Diss/Data/ECdata_Dragan')

# File paths (adjust to your data structure)
# Some stations need data from multiple sources or CSV files
if STATION == 'Mole':
    # Mole: Ground2.dat for VWC/Temperature, Ground1.dat for Heat Flux + Rain
    CR1000_SMT_FILE = EDDYPRO_DIR / STATION / 'raw' / 'cr1000' / f'CR1000X{STATION}_Ground2.dat'
    CR1000_HF_FILE = EDDYPRO_DIR / STATION / 'raw' / 'cr1000' / f'CR1000X{STATION}_Ground1.dat'
    CR1000_SMT_FORMAT = 'toa5'
    CR1000_HF_FORMAT = 'toa5'
    CR1000_FILE = None  # Will be combined
    # Mole radiation data from raw/cr6 directory
    RADIATION_FILE = EDDYPRO_DIR / STATION / 'raw' / 'cr6' / 'CR6Mole_Flux_CSFormat_15_11.dat'
    RADIATION_FORMAT = 'toa5'
elif STATION == 'Gorigo':
    # Gorigo: use CSV file (has proper column names for Heat Flux)
    CR1000_FILE = EDDYPRO_DIR / STATION / 'merged' / f'{STATION}_cr1000_merged.csv'
    CR1000_FORMAT = None  # Auto-detect (will be detected as CSV)
    CR1000_SMT_FILE = None
    CR1000_HF_FILE = None
    RADIATION_FILE = DATA_DIR / f'{STATION}_radiation_merged_long.parquet'
    RADIATION_FORMAT = None
elif STATION == 'Janga':
    # Janga: all data (radiation, soil temp, SWC) from CR6Janga_Flux_AmeriFluxFormat.dat
    CR1000_FILE = None  # Not used for Janga
    CR1000_FORMAT = None
    CR1000_SMT_FILE = None
    CR1000_HF_FILE = None
    RADIATION_FILE = EDDYPRO_DIR / STATION / 'raw' / 'CR6Janga_Flux_AmeriFluxFormat.dat'
    RADIATION_FORMAT = None  # Auto-detect (should be TOA5)
    # Janga G data from separate file
    JANGA_G_FILE = EDDYPRO_DIR / STATION / 'raw' / 'CR6Janga_Public.dat'
elif STATION in ['Kayoro', 'Nazinga', 'Sumbrungu']:
    # These stations use CSV files from ECdata_Dragan directory
    # All variables except LvE and HTs (which come from EddyPro)
    DRAGAN_CSV_FILE = DRAGAN_DATA_DIR / f'{STATION}.csv'
    CR1000_FILE = DRAGAN_CSV_FILE if DRAGAN_CSV_FILE.exists() else None
    CR1000_FORMAT = None  # Auto-detect (CSV)
    CR1000_SMT_FILE = None
    CR1000_HF_FILE = None
    RADIATION_FILE = None  # Will be loaded from the same CSV file
    RADIATION_FORMAT = None
else:
    CR1000_FILE = DATA_DIR / f'{STATION}_cr1000_merged_long.parquet'
    CR1000_FORMAT = None  # Auto-detect
    CR1000_SMT_FILE = None
    CR1000_HF_FILE = None
    RADIATION_FILE = DATA_DIR / f'{STATION}_radiation_merged_long.parquet'
    RADIATION_FORMAT = None

# EddyPro file: override per station to use specific file; empty = auto-detect most recent for all
# Example: EDDYPRO_FILE_OVERRIDE = {"Mole": Path("/Users/hingerl-l/Data/Mole/processed/fluxes/eddypro_Mole_full_output_2026-02-12T180440_adv.csv")}
#EDDYPRO_FILE_OVERRIDE: dict[str, Path] = {"Mole": Path("/Users/hingerl-l/Data/Mole/processed/fluxes/eddypro_Mole_full_output_2026-02-12T180440_adv.csv")}
#EDDYPRO_FILE_OVERRIDE: dict[str, Path] = {"Mole": Path("/Users/hingerl-l/Data/Mole/processed/fluxes/Samuels_eddypro_runs/eddypro_Mole_full_output_2026-02-24T155224_adv.csv")}
#EDDYPRO_FILE_OVERRIDE: dict[str, Path] = {"Mole": Path("/Users/hingerl-l/Data/Mole/processed/fluxes/eddypro_Mole_full_output_2026-03-11T163039_adv.csv")}
EDDYPRO_FILE_OVERRIDE: dict[str, Path] = {"Mole": Path("/Users/hingerl-l/Data/Mole/processed/fluxes/Mole_full_output_merged.csv")}


EDDYPRO_FLUXES_DIR = EDDYPRO_DIR / STATION / 'processed' / 'fluxes'
EDDYPRO_FILE = None
if STATION in EDDYPRO_FILE_OVERRIDE:
    override_path = Path(EDDYPRO_FILE_OVERRIDE[STATION]).expanduser().resolve()
    if override_path.exists():
        EDDYPRO_FILE = override_path
        print(f"✓ Using hardcoded EddyPro file for {STATION}: {EDDYPRO_FILE.name}")
    else:
        print(f"⚠️  Override path does not exist: {override_path}")
if EDDYPRO_FILE is None and EDDYPRO_FLUXES_DIR.exists():
    # Find file matching pattern: eddypro_{station}_full_output_*.csv
    pattern = f'eddypro_{STATION}_full_output_*.csv'
    eddypro_files = list(EDDYPRO_FLUXES_DIR.glob(pattern))
    if eddypro_files:
        # Always use the most recent file (by modification time)
        EDDYPRO_FILE = max(eddypro_files, key=lambda p: p.stat().st_mtime)
        if len(eddypro_files) > 1:
            print(f"✓ Found {len(eddypro_files)} EddyPro files, using most recent: {EDDYPRO_FILE.name}")
        else:
            print(f"✓ Found EddyPro file: {EDDYPRO_FILE.name}")
    else:
        print(f"⚠️  No EddyPro file found matching pattern: {pattern}")
        print(f"   Searched in: {EDDYPRO_FLUXES_DIR}")
elif EDDYPRO_FILE is None:
    print(f"⚠️  EddyPro directory not found: {EDDYPRO_FLUXES_DIR}")

# Date range for analysis
START_DATE = '2013-01-01'
END_DATE = '2015-12-31'  # June has only 30 days

# Option: Enable shift comparison for Energy Balance Closure
# If True, creates multiple EBC plots with shifted LE+H (±30 min)
# If False, creates only the standard EBC plot
ENABLE_SHIFT_COMPARISON = False  # Set to True to enable shift comparison
SHIFTS_TO_TEST = [-1, 0, 1, 2]  # Shifts in 30-min intervals: -30, 0, +30, +60 min

# Option: Apply single shift when ENABLE_SHIFT_COMPARISON = False
# If True, applies a single shift to LE+H for all plots and calculations
# If False, no shift is applied (original behavior)
APPLY_SHIFT = True  # Set to True to apply a shift
SHIFT_INTERVALS = 1  # Shift in 30-min intervals: 1 = +30 min, 2 = +60 min, etc.

# ============================================================================
# STEP 1: Load Data
# ============================================================================
print("=" * 60)
print("Step 1: Loading Data")
print("=" * 60)

# Initialize variables for Dragan station flux comparison
LvE_dragan = None
HTs_dragan = None
# Load CR1000 data (contains soil sensors for G calculation)
if STATION in ['Kayoro', 'Nazinga', 'Sumbrungu']:
    # For these stations: use Dragan CSV for data before 2016, Parquet files for data from 2016 onwards
    cutoff_date = pd.to_datetime('2016-01-01')
    df_cr1000_pre2016 = None
    df_cr1000_post2016 = None
    df_rad_pre2016 = None
    df_rad_post2016 = None

    # Load data before 2016 from Dragan CSV
    if CR1000_FILE and CR1000_FILE.exists():
        print(f"Loading {STATION} data from Dragan CSV (pre-2016): {CR1000_FILE.name}")
        # Load CSV manually to handle T_begin timestamp column
        df_dragan = pd.read_csv(
            CR1000_FILE,
            sep=",",
            low_memory=False,
            na_values=["NAN", "NA", "-9999", "-9999.0", "-999", "**************"]
        )

        # Parse T_begin timestamp column (format: MM/DD/YY HH:MM)
        if 'T_begin' in df_dragan.columns:
            df_dragan['T_begin'] = pd.to_datetime(df_dragan['T_begin'], format='%m/%d/%y %H:%M', errors='coerce')
            df_dragan = df_dragan.set_index('T_begin')
            df_dragan.index.name = 'TIMESTAMP'
            # Remove rows with invalid timestamps
            df_dragan = df_dragan[df_dragan.index.notna()]
            df_dragan = df_dragan.sort_index()
            df_dragan = df_dragan[~df_dragan.index.duplicated(keep='first')]
        else:
            print(f"  ⚠️  Warning: T_begin column not found, trying first column as timestamp")
            # Fallback to standard CSV loader
            df_dragan = load_ec_data(CR1000_FILE, format=CR1000_FORMAT)

        print(f"  ✓ Loaded {len(df_dragan)} records")
        print(f"  ✓ Columns: {list(df_dragan.columns)}")
        print(f"  ✓ Date range: {df_dragan.index.min()} to {df_dragan.index.max()}")

        # Extract LvE and HTs from Dragan file for comparison with EddyPro
        # Note: Column names might have trailing spaces
        for col in ['LvE[W/m_]      ', 'LvE']:
            if col in df_dragan.columns:
                LvE_dragan = df_dragan[col].copy()
                # Filter by quality flags if available (Flag <= 1 for good quality)
                # Check for Flag(LvE) or similar quality flag columns
                flag_cols = ['Flag(LvE)', 'Flag_LvE', 'LvE_Flag', 'qc_LvE']
                for flag_col in flag_cols:
                    if flag_col in df_dragan.columns:
                        flag_le = pd.to_numeric(df_dragan[flag_col], errors='coerce')
                        high_quality_mask = (flag_le <= 1) & (flag_le.notna())
                        LvE_dragan = LvE_dragan[high_quality_mask]
                        print(f"  ✓ Filtered LvE_dragan by {flag_col} <= 1: {LvE_dragan.notna().sum()} high-quality values")
                        break
                else:
                    print(f"  ✓ Found LvE in Dragan file: {LvE_dragan.notna().sum()} values (no quality flags found)")
                break
        for col in ['HTs[W/m_]      ', 'HTs']:
            if col in df_dragan.columns:
                HTs_dragan = df_dragan[col].copy()
                # Filter by quality flags if available (Flag <= 1 for good quality)
                # Check for Flag(HTs) or similar quality flag columns
                flag_cols = ['Flag(HTs)', 'Flag_HTs', 'HTs_Flag', 'qc_HTs']
                for flag_col in flag_cols:
                    if flag_col in df_dragan.columns:
                        flag_h = pd.to_numeric(df_dragan[flag_col], errors='coerce')
                        high_quality_mask = (flag_h <= 1) & (flag_h.notna())
                        HTs_dragan = HTs_dragan[high_quality_mask]
                        print(f"  ✓ Filtered HTs_dragan by {flag_col} <= 1: {HTs_dragan.notna().sum()} high-quality values")
                        break
                else:
                    print(f"  ✓ Found HTs in Dragan file: {HTs_dragan.notna().sum()} values (no quality flags found)")
                break

        # Split data: pre-2016 and post-2016
        df_dragan_pre2016 = df_dragan[df_dragan.index < cutoff_date].copy()

        if len(df_dragan_pre2016) > 0:

            # Exclude LvE, HTs, and G (G is already extracted, LvE/HTs come from EddyPro)
            columns_to_exclude = ['LvE', 'HTs', 'LvE[W/m_]      ', 'HTs[W/m_]      ', 'G ', 'G', 'GHF Mean', 'Gs ']
            df_cr1000_pre2016 = df_dragan_pre2016.drop(columns=[col for col in columns_to_exclude if col in df_dragan_pre2016.columns])

            # Rename columns to remove unit suffixes and map German names to English
            column_rename_map = {}
            for col in df_cr1000_pre2016.columns:
                new_col = col
                # Remove unit suffixes like " [DegC]", " [W/m^2]", etc.
                if ' [DegC]' in new_col:
                    new_col = new_col.replace(' [DegC]', '')
                elif ' [W/m^2]' in new_col:
                    new_col = new_col.replace(' [W/m^2]', '')
                elif ' [W/m_]' in new_col:
                    new_col = new_col.replace(' [W/m_]', '')

                # Map German column names to English
                if new_col.endswith('_Ost_Avg'):
                    new_col = new_col.replace('_Ost_Avg', '_East_Avg')
                elif new_col.endswith('_Mitte_Avg'):
                    new_col = new_col.replace('_Mitte_Avg', '_Middle_Avg')

                if new_col != col:
                    column_rename_map[col] = new_col

            if column_rename_map:
                df_cr1000_pre2016 = df_cr1000_pre2016.rename(columns=column_rename_map)
                print(f"  ✓ Renamed {len(column_rename_map)} columns for pre-2016 data")

            df_rad_pre2016 = df_dragan_pre2016.copy()
            print(f"  ✓ Pre-2016 data: {len(df_cr1000_pre2016)} records ({df_cr1000_pre2016.index.min()} to {df_cr1000_pre2016.index.max()})")
        else:
            print(f"  ⚠️  No pre-2016 data found in Dragan CSV")

    # Load data from 2016 onwards from Parquet files
    parquet_cr1000_file = DATA_DIR / f'{STATION}_cr1000_merged_long.parquet'
    parquet_radiation_file = DATA_DIR / f'{STATION}_radiation_merged_long.parquet'

    if parquet_cr1000_file.exists():
        print(f"\nLoading {STATION} CR1000 data from Parquet (2016+): {parquet_cr1000_file.name}")
        df_cr1000_post2016 = load_ec_data(parquet_cr1000_file)
        # Filter to 2016 and later
        df_cr1000_post2016 = df_cr1000_post2016[df_cr1000_post2016.index >= cutoff_date].copy()
        if len(df_cr1000_post2016) > 0:
            print(f"  ✓ Loaded {len(df_cr1000_post2016)} records")
            print(f"  ✓ Date range: {df_cr1000_post2016.index.min()} to {df_cr1000_post2016.index.max()}")
        else:
            print(f"  ⚠️  No post-2016 data found in Parquet file")
            df_cr1000_post2016 = None
    else:
        print(f"\n⚠️  Parquet CR1000 file not found: {parquet_cr1000_file}")

    if parquet_radiation_file.exists():
        print(f"\nLoading {STATION} radiation data from Parquet (2016+): {parquet_radiation_file.name}")
        df_rad_post2016 = load_ec_data(parquet_radiation_file)
        # Filter to 2016 and later
        df_rad_post2016 = df_rad_post2016[df_rad_post2016.index >= cutoff_date].copy()
        if len(df_rad_post2016) > 0:
            print(f"  ✓ Loaded {len(df_rad_post2016)} records")
            print(f"  ✓ Date range: {df_rad_post2016.index.min()} to {df_rad_post2016.index.max()}")
        else:
            print(f"  ⚠️  No post-2016 data found in Parquet file")
            df_rad_post2016 = None
    else:
        print(f"\n⚠️  Parquet radiation file not found: {parquet_radiation_file}")

    # Combine pre-2016 and post-2016 data
    print(f"\nCombining pre-2016 and post-2016 data...")
    if df_cr1000_pre2016 is not None and df_cr1000_post2016 is not None:
        # Use outer join to keep all columns from both datasets
        df_cr1000 = pd.concat([
            df_cr1000_pre2016,
            df_cr1000_post2016
        ], join='outer', sort=True).sort_index()
        print(f"  ✓ Combined CR1000 data: {len(df_cr1000)} records")
        print(f"     Pre-2016: {len(df_cr1000_pre2016)} records, {len(df_cr1000_pre2016.columns)} columns")
        print(f"     Post-2016: {len(df_cr1000_post2016)} records, {len(df_cr1000_post2016.columns)} columns")
        print(f"     Combined: {len(df_cr1000.columns)} columns")
    elif df_cr1000_pre2016 is not None:
        df_cr1000 = df_cr1000_pre2016
        print(f"  ✓ Using pre-2016 CR1000 data only: {len(df_cr1000)} records")
    elif df_cr1000_post2016 is not None:
        df_cr1000 = df_cr1000_post2016
        print(f"  ✓ Using post-2016 CR1000 data only: {len(df_cr1000)} records")
    else:
        df_cr1000 = None
        print(f"  ⚠️  No CR1000 data available")

    if df_rad_pre2016 is not None and df_rad_post2016 is not None:
        # Use outer join to keep all columns from both datasets
        df_rad = pd.concat([
            df_rad_pre2016,
            df_rad_post2016
        ], join='outer', sort=True).sort_index()
        print(f"  ✓ Combined radiation data: {len(df_rad)} records")
        print(f"     Pre-2016: {len(df_rad_pre2016)} records, {len(df_rad_pre2016.columns)} columns")
        print(f"     Post-2016: {len(df_rad_post2016)} records, {len(df_rad_post2016.columns)} columns")
        print(f"     Combined: {len(df_rad.columns)} columns")
    elif df_rad_pre2016 is not None:
        df_rad = df_rad_pre2016
        print(f"  ✓ Using pre-2016 radiation data only: {len(df_rad)} records")
    elif df_rad_post2016 is not None:
        df_rad = df_rad_post2016
        print(f"  ✓ Using post-2016 radiation data only: {len(df_rad)} records")
    else:
        df_rad = None
        print(f"  ⚠️  No radiation data available")
elif STATION == 'Mole':
    # For Mole, combine Ground2.dat (VWC/Temperature) and Ground1.dat (Heat Flux + Rain) data
    print(f"Loading Mole data from multiple sources:")
    print(f"  - Ground2 data (VWC/Temperature): {CR1000_SMT_FILE.name}")
    if CR1000_SMT_FORMAT:
        df_ground2 = load_ec_data(CR1000_SMT_FILE, format=CR1000_SMT_FORMAT)
    else:
        df_ground2 = load_ec_data(CR1000_SMT_FILE)
    print(f"    ✓ Loaded {len(df_ground2)} records")
    print(f"    ✓ Columns: {list(df_ground2.columns)}")

    print(f"  - Ground1 data (Heat Flux + Rain): {CR1000_HF_FILE.name}")
    if CR1000_HF_FORMAT:
        df_ground1 = load_ec_data(CR1000_HF_FILE, format=CR1000_HF_FORMAT)
    else:
        df_ground1 = load_ec_data(CR1000_HF_FILE)
    print(f"    ✓ Loaded {len(df_ground1)} records")
    print(f"    ✓ Columns: {list(df_ground1.columns[:10])}...")

    # Combine: use VWC/T from Ground2, Heat Flux + Rain from Ground1
    # Rename Ground2 columns to match config
    df_ground2_renamed = df_ground2.rename(columns={
        'VWC_Avg': 'VW_1_Avg',
        'VWC_2_Avg': 'VW_2_Avg',
        'VWC_3_Avg': 'VW_3_Avg',
        'T_Avg': 'TCAV_C_Avg(1)',
        'T_2_Avg': 'TCAV_C_Avg(2)',
        'T_3_Avg': 'TCAV_C_Avg(3)'
    })

    # Start with Ground2 data
    ground2_cols = ['VW_1_Avg', 'VW_2_Avg', 'VW_3_Avg',
                    'TCAV_C_Avg(1)', 'TCAV_C_Avg(2)', 'TCAV_C_Avg(3)']
    available_cols = [c for c in ground2_cols if c in df_ground2_renamed.columns]
    df_cr1000 = df_ground2_renamed[available_cols].copy() if available_cols else pd.DataFrame()

    # Add Ground1 data: Heat Flux + Rain
    hf_cols = ['H_Flux_8_Middle_Avg', 'H_Flux_8_East_Avg', 'H_Flux_8_West_Avg']
    rain_cols = ['Rain_mm_Tot']
    for col in hf_cols + rain_cols:
        if col in df_ground1.columns:
            if df_cr1000.empty:
                df_cr1000 = pd.DataFrame(index=df_ground1.index)
            df_cr1000[col] = df_ground1[col]

    print(f"  ✓ Combined data: {len(df_cr1000)} records")
    print(f"  ✓ Columns: {list(df_cr1000.columns)}")
elif STATION == 'Janga':
    # For Janga, create df_cr1000 from CR6Janga_Flux_AmeriFluxFormat.dat
    # This will be loaded later with radiation data, but we create a placeholder here
    # The actual loading happens in the radiation section
    print(f"Janga: Soil temperature and SWC will be loaded from CR6Janga_Flux_AmeriFluxFormat.dat")
    df_cr1000 = None  # Will be created from radiation file
else:
    print(f"Loading CR1000 data: {CR1000_FILE.name}")
    if CR1000_FORMAT:
        df_cr1000 = load_ec_data(CR1000_FILE, format=CR1000_FORMAT)
    else:
        df_cr1000 = load_ec_data(CR1000_FILE)
    print(f"  ✓ Loaded {len(df_cr1000)} records")
    print(f"  ✓ Columns: {list(df_cr1000.columns[:5])}...")

# Load Radiation data (for Rn calculation)
# For Dragan stations, radiation data is already loaded in df_rad above
if STATION in ['Kayoro', 'Nazinga', 'Sumbrungu']:
    # df_rad already loaded above
    if df_rad is None:
        print(f"\n⚠️  No radiation data available for {STATION}")
elif RADIATION_FILE and RADIATION_FILE.exists():
    print(f"\nLoading Radiation data: {RADIATION_FILE.name}")
    if RADIATION_FORMAT:
        df_rad = load_ec_data(RADIATION_FILE, format=RADIATION_FORMAT)
    else:
        df_rad = load_ec_data(RADIATION_FILE)
    print(f"  ✓ Loaded {len(df_rad)} records")
    print(f"  ✓ Columns: {list(df_rad.columns[:10])}...")

    # For Janga, extract soil temperature and SWC from the same file
    if STATION == 'Janga':
        print(f"  Extracting soil temperature and SWC from CR6Janga_Flux_AmeriFluxFormat.dat")
        # Extract TS (soil temperature) columns: TS_1_1_1, TS_2_1_1, TS_3_1_1
        #ts_cols = ['TS_1_1_1', 'TS_2_1_1', 'TS_3_1_1']
        ts_cols = ['TS_1_1_1']
        available_ts_cols = [col for col in ts_cols if col in df_rad.columns]

        # Extract SWC (soil water content) columns: SWC_1_1_1, SWC_2_1_1, SWC_3_1_1
        #swc_cols = ['SWC_1_1_1', 'SWC_2_1_1', 'SWC_3_1_1']
        swc_cols = ['SWC_1_1_1', 'SWC_2_1_1']
        available_swc_cols = [col for col in swc_cols if col in df_rad.columns]

        # Create df_cr1000-like structure for compatibility
        df_cr1000 = pd.DataFrame(index=df_rad.index)

        if available_ts_cols:
            # Rename to match expected column names (if needed for G calculation)
            for i, col in enumerate(available_ts_cols, 1):
                df_cr1000[f'TCAV_C_Avg({i})'] = df_rad[col]
            print(f"    ✓ Found {len(available_ts_cols)} soil temperature columns: {available_ts_cols}")
        else:
            print(f"    ⚠️  Soil temperature columns not found. Available columns: {list(df_rad.columns[:20])}")

        if available_swc_cols:
            # Rename to match expected column names (if needed for G calculation)
            for i, col in enumerate(available_swc_cols, 1):
                df_cr1000[f'VW_{i}_Avg'] = df_rad[col]
            print(f"    ✓ Found {len(available_swc_cols)} SWC columns: {available_swc_cols}")
        else:
            print(f"    ⚠️  SWC columns not found. Available columns: {list(df_rad.columns[:20])}")

        print(f"  ✓ Created df_cr1000 structure: {len(df_cr1000)} records")
else:
    print(f"\n⚠️  Radiation file not found: {RADIATION_FILE}")
    if STATION == 'Mole':
        print("     Note: Mole radiation data should be in raw directory.")
    elif STATION == 'Janga':
        print("     Note: Janga radiation data should be in raw directory.")
    df_rad = None

# Load EddyPro data (for LE and H)
if EDDYPRO_FILE and EDDYPRO_FILE.exists():
    print(f"\nLoading EddyPro data: {EDDYPRO_FILE.name}")
    df_eddypro = load_ec_data(EDDYPRO_FILE, format='eddypro')
    print(f"  ✓ Loaded {len(df_eddypro)} records")
    print(f"  ✓ Columns: {list(df_eddypro.columns[:5])}...")
else:
    print(f"\n⚠️  EddyPro file not found")
    if EDDYPRO_FLUXES_DIR.exists():
        print(f"   Searched in: {EDDYPRO_FLUXES_DIR}")
        print(f"   Pattern: eddypro_{STATION}_full_output_*.csv")
    df_eddypro = None

# ============================================================================
# STEP 2: Calculate Soil Heat Flux (G) from {station}_all_variables_30min.csv
# ============================================================================
# G is always calculated from the all_variables CSV (run collect_all_variables_30min.py first).
print("\n" + "=" * 60)
print("Step 2: Calculate Soil Heat Flux (G)")
print("=" * 60)

ALL_VARIABLES_CSV = EDDYPRO_DIR / STATION / "processed" / "all" / f"{STATION}_all_variables_30min.csv"
G = None
if ALL_VARIABLES_CSV.exists():
    print(f"Loading G input data from {ALL_VARIABLES_CSV.name}")
    try:
        header = pd.read_csv(ALL_VARIABLES_CSV, nrows=1).columns.tolist()
        df_all = pd.read_csv(
            ALL_VARIABLES_CSV,
            skiprows=2,
            header=None,
            names=header,
            index_col=0,
            parse_dates=True,
            low_memory=False,
            na_values=["NAN", "NA", "-9999", "-9999.0", "-999", "**************"],
            on_bad_lines="warn",
        )
        df_all = df_all[df_all.index.notna()].sort_index()
        df_all = df_all[~df_all.index.duplicated(keep="first")]
        G = calculate_soil_heat_flux(df_all, station=STATION, return_components=False)
        print(f"  ✓ Calculated G from {len(df_all)} records: {G.notna().sum()} values")
        if G.notna().any():
            print(f"  ✓ G range: {G.min():.1f} to {G.max():.1f} W/m²")
    except Exception as e:
        print(f"  ⚠️  Failed to calculate G: {e}")
        G = None
else:
    print(f"  ⚠️  {ALL_VARIABLES_CSV.name} not found. Run collect_all_variables_30min.py first.")

# ============================================================================
# STEP 3: Prepare Energy Balance Components
# ============================================================================
print("\n" + "=" * 60)
print("Step 3: Prepare Energy Balance Components")
print("=" * 60)

# Get radiation components (for Rn calculation)
# For Dragan stations, df_rad is already loaded from CSV
# Initialize variables
SW_in = None
SW_out = None
LW_in = None
LW_out = None

if df_rad is not None:
    # Try different column name conventions
    # First check for Dragan station names (Kayoro, Nazinga, Sumbrungu)
    if STATION in ['Kayoro', 'Nazinga', 'Sumbrungu']:
        # Pre-2016: Dragan columns only; from 2016: Parquet columns only (no mixing)
        cutoff_date = pd.to_datetime('2016-01-01')
        dragan_SW_in = df_rad.get('SW_in korrigiert', None)
        dragan_SW_out = df_rad.get('SW_out korrigiert', None)
        dragan_LW_in = df_rad.get('LW_in_Avg [W/m^2]', None)
        dragan_LW_out = df_rad.get('LW_out_Avg [W/m^2]', None)
        parquet_SW_in = df_rad.get('SR_in_Avg', None)
        parquet_SW_out = df_rad.get('SR_out_Avg', None)
        parquet_LW_in = df_rad.get('IR_in_Avg', None)
        parquet_LW_out = df_rad.get('IR_out_Avg', None)
        idx_pre = df_rad.index < cutoff_date
        idx_post = df_rad.index >= cutoff_date
        if dragan_SW_in is not None and parquet_SW_in is not None:
            SW_in = dragan_SW_in.where(idx_pre).combine_first(parquet_SW_in.where(idx_post))
        elif dragan_SW_in is not None:
            SW_in = dragan_SW_in
        elif parquet_SW_in is not None:
            SW_in = parquet_SW_in
        else:
            SW_in = None
        if dragan_SW_out is not None and parquet_SW_out is not None:
            SW_out = dragan_SW_out.where(idx_pre).combine_first(parquet_SW_out.where(idx_post))
        elif dragan_SW_out is not None:
            SW_out = dragan_SW_out
        elif parquet_SW_out is not None:
            SW_out = parquet_SW_out
        else:
            SW_out = None
        if dragan_LW_in is not None and parquet_LW_in is not None:
            LW_in = dragan_LW_in.where(idx_pre).combine_first(parquet_LW_in.where(idx_post))
        elif dragan_LW_in is not None:
            LW_in = dragan_LW_in
        elif parquet_LW_in is not None:
            LW_in = parquet_LW_in
        else:
            LW_in = None
        if dragan_LW_out is not None and parquet_LW_out is not None:
            LW_out = dragan_LW_out.where(idx_pre).combine_first(parquet_LW_out.where(idx_post))
        elif dragan_LW_out is not None:
            LW_out = dragan_LW_out
        elif parquet_LW_out is not None:
            LW_out = parquet_LW_out
        else:
            LW_out = None

    # Standard names (from radiation files)
    if SW_in is None:
        SW_in = df_rad.get('SR_in_Avg', None)
    if SW_out is None:
        SW_out = df_rad.get('SR_out_Avg', None)
    if LW_in is None:
        LW_in = df_rad.get('IR_in_Avg', None)
    if LW_out is None:
        LW_out = df_rad.get('IR_out_Avg', None)

    # Alternative names (from AmeriFlux format files like Mole/Janga)
    if SW_in is None:
        SW_in = df_rad.get('SW_IN', None)
    if SW_out is None:
        SW_out = df_rad.get('SW_OUT', None)
    if LW_in is None:
        LW_in = df_rad.get('LW_IN', None)
    if LW_out is None:
        LW_out = df_rad.get('LW_OUT', None)

    if all([SW_in is not None, SW_out is not None, LW_in is not None, LW_out is not None]):
        Rn = (SW_in - SW_out) + (LW_in - LW_out)
        print(f"  ✓ Calculated Rn from radiation components: {len(Rn)} values")
        print(f"     Using columns: SW_IN/SW_OUT, LW_IN/LW_OUT")
        if STATION == 'Janga':
            print(f"     Rn index range: {Rn.index.min()} to {Rn.index.max()}")
    else:
        # Try NetTot/NetRad if available
        Rn = df_rad.get('NetTot_Avg', None)
        if Rn is None:
            Rn = df_rad.get('NETRAD', None)
        if Rn is not None:
            print(f"  ✓ Using NetTot_Avg/NETRAD as Rn: {len(Rn)} values")
        else:
            print("  ⚠️  Could not calculate Rn from radiation data")
            print(f"     Available columns: {list(df_rad.columns)}")
            print(f"     Looked for: SR_in_Avg/SW_IN, SR_out_Avg/SW_OUT, IR_in_Avg/LW_IN, IR_out_Avg/LW_OUT, NetTot_Avg/NETRAD")
            Rn = None
else:
    Rn = None
    print("  ⚠️  No radiation data available for Rn")
    if STATION == 'Mole':
        print("     Note: Mole radiation data should be in raw directory.")
    elif STATION == 'Janga':
        print("     Note: Janga radiation data should be in raw directory.")

# Get LE and H from EddyPro or other sources
# For Dragan stations (Kayoro, Nazinga, Sumbrungu), use LvE and HTs from EddyPro
if df_eddypro is not None:
    if STATION in ['Kayoro', 'Nazinga', 'Sumbrungu']:
        # For Dragan stations, use LvE and HTs from EddyPro
        LE = df_eddypro.get('LvE', None)
        H = df_eddypro.get('HTs', None)

        # Fallback to LE and H if LvE/HTs not found
        if LE is None:
            LE = df_eddypro.get('LE', None)
        if H is None:
            H = df_eddypro.get('H', None)
    else:
        # For other stations, use standard LE and H
        LE = df_eddypro.get('LE', None)
        H = df_eddypro.get('H', None)

    # Convert to numeric (EddyPro data may be loaded as strings)
    if LE is not None:
        LE = pd.to_numeric(LE, errors='coerce')
    if H is not None:
        H = pd.to_numeric(H, errors='coerce')

    # Filter by quality flags (Flag <= 1 for good quality)
    # Check for different flag column name conventions
    if df_eddypro is not None:
        # For Dragan stations, check Flag(LvE) and Flag(HTs)
        if STATION in ['Kayoro', 'Nazinga', 'Sumbrungu']:
            # Filter LvE by Flag(LvE)
            if LE is not None and 'Flag(LvE)' in df_eddypro.columns:
                flag_le = pd.to_numeric(df_eddypro['Flag(LvE)'], errors='coerce')
                high_quality_mask = (flag_le <= 1) & (flag_le.notna())
                LE = LE[high_quality_mask]
                print(f"  ✓ Filtered LE by Flag(LvE) <= 1: {LE.notna().sum()} high-quality values")
            # Filter HTs by Flag(HTs)
            if H is not None and 'Flag(HTs)' in df_eddypro.columns:
                flag_h = pd.to_numeric(df_eddypro['Flag(HTs)'], errors='coerce')
                high_quality_mask = (flag_h <= 1) & (flag_h.notna())
                H = H[high_quality_mask]
                print(f"  ✓ Filtered H by Flag(HTs) <= 1: {H.notna().sum()} high-quality values")
        else:
            # For other stations, check Flag(LE) and Flag(H) or qc_LE, qc_H
            # Try Flag(LE) first
            if LE is not None:
                if 'Flag(LE)' in df_eddypro.columns:
                    flag_le = pd.to_numeric(df_eddypro['Flag(LE)'], errors='coerce')
                    high_quality_mask = (flag_le <= 1) & (flag_le.notna())
                    LE = LE[high_quality_mask]
                    print(f"  ✓ Filtered LE by Flag(LE) <= 1: {LE.notna().sum()} high-quality values")
                elif 'qc_LE' in df_eddypro.columns:
                    LE = filter_quality_flags(df_eddypro, 'qc_LE', max_flag=1, data_column='LE')
                    print(f"  ✓ Filtered LE by qc_LE <= 1: {LE.notna().sum()} high-quality values")
            # Try Flag(H) first
            if H is not None:
                if 'Flag(H)' in df_eddypro.columns:
                    flag_h = pd.to_numeric(df_eddypro['Flag(H)'], errors='coerce')
                    high_quality_mask = (flag_h <= 1) & (flag_h.notna())
                    H = H[high_quality_mask]
                    print(f"  ✓ Filtered H by Flag(H) <= 1: {H.notna().sum()} high-quality values")
                elif 'qc_H' in df_eddypro.columns:
                    H = filter_quality_flags(df_eddypro, 'qc_H', max_flag=1, data_column='H')
                    print(f"  ✓ Filtered H by qc_H <= 1: {H.notna().sum()} high-quality values")

    # Additional filter: Remove physically unrealistic LE values (LE > -200 W/m²)
    if LE is not None:
        before_count = LE.notna().sum()
        LE = LE[LE > -200]
        after_count = LE.notna().sum()
        if before_count != after_count:
            print(f"  ✓ Filtered LE by LE > -200: {after_count} values remaining (removed {before_count - after_count} values)")

    if STATION in ['Kayoro', 'Nazinga', 'Sumbrungu']:
        print(f"  ✓ LE (from LvE) from EddyPro: {len(LE) if LE is not None else 0} values")
        print(f"  ✓ H (from HTs) from EddyPro: {len(H) if H is not None else 0} values")
    else:
        print(f"  ✓ LE from EddyPro: {len(LE) if LE is not None else 0} values")
        print(f"  ✓ H from EddyPro: {len(H) if H is not None else 0} values")
    if STATION == 'Janga' and LE is not None:
        print(f"     LE/H index range: {LE.index.min()} to {LE.index.max()}")
else:
    # If not available, you might need to load from other sources
    LE = None
    H = None
    print("  ⚠️  No EddyPro data available for LE and H")
    if STATION in ['Kayoro', 'Nazinga', 'Sumbrungu']:
        print("     For Dragan stations, LvE and HTs should be in EddyPro file")
    else:
        print("     You may need to load LE and H from other sources")

# Storage change (Delta) - you may need to calculate this separately
# For now, we'll use zeros or skip it
Delta = pd.Series(0, index=G.index) if G is not None else None
print("  ⚠️  Delta (storage change) set to zero - calculate separately if needed")

# ============================================================================
# STEP 4: Build Energy Balance DataFrame
# ============================================================================
print("\n" + "=" * 60)
print("Step 4: Build Energy Balance DataFrame")
print("=" * 60)

# Check if we have required components (Rn is optional for some stations)
if all([LE is not None, H is not None, G is not None]):
    # For stations without Rn, create a simplified energy balance
    if Rn is None:
        print("\n  ⚠️  No Rn available - creating Energy Balance without radiation components")
        # Create simplified energy balance DataFrame
        # Align all series to common index
        common_idx = G.index.intersection(LE.index).intersection(H.index)
        LE_aligned = LE.loc[common_idx]
        H_aligned = H.loc[common_idx]
        G_aligned = G.loc[common_idx]

        # Slice to date range
        mask = (common_idx >= pd.to_datetime(START_DATE)) & (common_idx <= pd.to_datetime(END_DATE))
        common_idx_sliced = common_idx[mask]

        eb_df = pd.DataFrame({
            'LE': LE_aligned.loc[common_idx_sliced],
            'H': H_aligned.loc[common_idx_sliced],
            'G': G_aligned.loc[common_idx_sliced],
            'Delta': (Delta.loc[common_idx_sliced] if Delta is not None else pd.Series(0, index=common_idx_sliced)),
            'Rn': pd.Series(0, index=common_idx_sliced),  # Placeholder
            'Residual': pd.Series(0, index=common_idx_sliced)  # Cannot calculate without Rn
        }).dropna()

        print(f"  ✓ Energy Balance DataFrame created (without Rn): {len(eb_df)} records")
    else:
        # Build energy balance DataFrame with Rn
        # For Janga, we need to align all data to a common time index
        # Resample to 30-minute intervals if needed
        if STATION == 'Janga':
            print(f"\n  Aligning data for Janga...")
            # Find common time range
            all_indices = []
            if Rn is not None:
                all_indices.append(Rn.index)
            if LE is not None:
                all_indices.append(LE.index)
            if H is not None:
                all_indices.append(H.index)
            if G is not None:
                all_indices.append(G.index)

            if all_indices:
                # Get overlapping time range
                common_start = max([idx.min() for idx in all_indices])
                common_end = min([idx.max() for idx in all_indices])
                print(f"     Common time range: {common_start} to {common_end}")

                # Resample all series to 30-minute intervals and align
                freq = '30T'  # 30 minutes
                if Rn is not None:
                    Rn = Rn.resample(freq).mean()
                if SW_in is not None:
                    SW_in = SW_in.resample(freq).mean()
                if SW_out is not None:
                    SW_out = SW_out.resample(freq).mean()
                if LW_in is not None:
                    LW_in = LW_in.resample(freq).mean()
                if LW_out is not None:
                    LW_out = LW_out.resample(freq).mean()
                if LE is not None:
                    LE = LE.resample(freq).mean()
                if H is not None:
                    H = H.resample(freq).mean()
                if G is not None:
                    G = G.resample(freq).mean()
                if Delta is not None:
                    Delta = Delta.resample(freq).mean()

                print(f"     Resampled all data to 30-minute intervals")

        eb_df = build_energy_balance_df(
            SW_in=SW_in if SW_in is not None else pd.Series(0, index=G.index if G is not None else pd.DatetimeIndex([])),
            SW_out=SW_out if SW_out is not None else pd.Series(0, index=G.index if G is not None else pd.DatetimeIndex([])),
            LW_in=LW_in if LW_in is not None else pd.Series(0, index=G.index if G is not None else pd.DatetimeIndex([])),
            LW_out=LW_out if LW_out is not None else pd.Series(0, index=G.index if G is not None else pd.DatetimeIndex([])),
            LE=LE,
            H=H,
            G=G,
            Delta=Delta if Delta is not None else pd.Series(0, index=G.index if G is not None else pd.DatetimeIndex([])),
            start=START_DATE,
            end=END_DATE,
            site_name=STATION
        )

    if not eb_df.empty:
        # Track whether shift was actually applied
        shift_applied = False

        # Apply shift to LE and H if APPLY_SHIFT is True and ENABLE_SHIFT_COMPARISON is False
        # Exception: Janga should never have a shift applied
        if not ENABLE_SHIFT_COMPARISON and APPLY_SHIFT and SHIFT_INTERVALS != 0 and STATION != 'Janga':
            print(f"\n  Applying shift of {SHIFT_INTERVALS * 30} minutes to LE and H...")
            # Shift LE and H forward by the specified intervals
            LE_original = eb_df['LE'].copy()
            H_original = eb_df['H'].copy()
            eb_df['LE'] = LE_original.shift(-SHIFT_INTERVALS)
            eb_df['H'] = H_original.shift(-SHIFT_INTERVALS)
            # Recalculate Residual with shifted LE and H
            eb_df['Residual'] = eb_df['Rn'] - eb_df['LE'] - eb_df['H'] - eb_df['G'] - eb_df['Delta']
            shift_applied = True
            print(f"  ✓ Shifted LE and H by {SHIFT_INTERVALS * 30} minutes")
            print(f"     LE: {LE_original.notna().sum()} → {eb_df['LE'].notna().sum()} values after shift")
            print(f"     H:  {H_original.notna().sum()} → {eb_df['H'].notna().sum()} values after shift")
        elif STATION == 'Janga' and APPLY_SHIFT:
            print(f"\n  ⚠️  Shift not applied for Janga (as requested)")

        print(f"  ✓ Energy Balance DataFrame created: {len(eb_df)} records")
        print(f"  ✓ Columns: {list(eb_df.columns)}")
        print(f"\n  Energy Balance Statistics:")
        print(f"    Rn:      {eb_df['Rn'].mean():.1f} ± {eb_df['Rn'].std():.1f} W/m²")
        print(f"    LE:      {eb_df['LE'].mean():.1f} ± {eb_df['LE'].std():.1f} W/m²")
        print(f"    H:       {eb_df['H'].mean():.1f} ± {eb_df['H'].std():.1f} W/m²")
        print(f"    G:       {eb_df['G'].mean():.1f} ± {eb_df['G'].std():.1f} W/m²")
        print(f"    Delta:   {eb_df['Delta'].mean():.1f} ± {eb_df['Delta'].std():.1f} W/m²")
        print(f"    Residual: {eb_df['Residual'].mean():.1f} ± {eb_df['Residual'].std():.1f} W/m²")

        # ============================================================================
        # STEP 5: Create Plots
        # ============================================================================
        print("\n" + "=" * 60)
        print("Step 5: Create Energy Balance Closure Plots")
        print("=" * 60)

        # Energy Balance Closure Plot (only if Rn is available)
        if Rn is not None and (eb_df['Rn'] != 0).any():
            if ENABLE_SHIFT_COMPARISON:
                print("Creating Energy Balance Closure plots with shifts...")

                # Prepare data for shift comparison
                # Get LE and H from eb_df (already filtered and aligned)
                LE_ebc = eb_df['LE'].copy()
                H_ebc = eb_df['H'].copy()
                Rn_ebc = eb_df['Rn'].copy()
                G_ebc = eb_df['G'].copy()
                Delta_ebc = eb_df.get('Delta', pd.Series(0, index=eb_df.index))

                # Calculate X-axis: Rn - G - Delta (exactly as in EBC plot)
                x_data = Rn_ebc - G_ebc
                if Delta_ebc.notna().any() and (Delta_ebc != 0).any():
                    x_data = x_data - Delta_ebc

                # Filter to valid range (same as EBC plot)
                valid_mask = (
                    (LE_ebc >= -300) & (LE_ebc <= 800) &
                    (H_ebc >= -300) & (H_ebc <= 800)
                )
                x_data = x_data[valid_mask]
                LE_ebc = LE_ebc[valid_mask]
                H_ebc = H_ebc[valid_mask]
                Rn_ebc = Rn_ebc[valid_mask]
                G_ebc = G_ebc[valid_mask]

                # Use all data (no daytime filtering) - same as plot_energy_balance_closure()
                x_data_all = x_data
                LE_ebc_all = LE_ebc
                H_ebc_all = H_ebc
                LE_H_ebc_all = LE_ebc_all + H_ebc_all

                print(f"  ✓ Prepared data: {len(x_data_all)} points (all data, no daytime filter)")

                if len(x_data_all) > 10:
                    # Create subplots for all shifts
                    n_shifts = len(SHIFTS_TO_TEST)
                    # Calculate grid layout
                    n_cols = 3
                    n_rows = (n_shifts + n_cols - 1) // n_cols

                    fig_ebc_shifts, axes_ebc = plt.subplots(n_rows, n_cols, figsize=(18, 6*n_rows))
                    if n_shifts == 1:
                        axes_ebc = [axes_ebc]
                    elif n_rows == 1:
                        axes_ebc = axes_ebc.tolist() if isinstance(axes_ebc, np.ndarray) else [axes_ebc]
                    else:
                        axes_ebc = axes_ebc.flatten().tolist() if isinstance(axes_ebc, np.ndarray) else list(axes_ebc.flatten())

                    results = []

                    for idx, shift in enumerate(SHIFTS_TO_TEST):
                        if idx >= len(axes_ebc):
                            break
                        ax = axes_ebc[idx]

                        # Create shift label
                        if shift == 0:
                            label = 'No shift'
                        elif shift > 0:
                            label = f'+{shift * 30} min'
                        else:
                            label = f'{shift * 30} min'

                        if shift == 0:
                            y_data = LE_H_ebc_all
                            x_plot = x_data_all
                        else:
                            # Shift LE+H by shift intervals (30-min steps)
                            LE_H_shifted = LE_H_ebc_all.shift(-shift)
                            # Align indices
                            common_shifted = x_data_all.index.intersection(LE_H_shifted.index)
                            y_data = LE_H_shifted.loc[common_shifted].dropna()
                            x_plot = x_data_all.loc[y_data.index]

                        # Remove NaN values
                        mask = x_plot.notna() & y_data.notna()
                        x_clean = x_plot[mask]
                        y_clean = y_data[mask]

                        if len(x_clean) > 1:
                            # Scatter plot
                            ax.scatter(x_clean, y_clean, alpha=0.5, s=20, edgecolors='none', color='black')

                            # Calculate regression
                            coeffs = np.polyfit(x_clean, y_clean, 1)
                            slope = coeffs[0]
                            intercept = coeffs[1]

                            # Calculate R²
                            y_pred = slope * x_clean + intercept
                            ss_res = np.sum((y_clean - y_pred) ** 2)
                            ss_tot = np.sum((y_clean - np.mean(y_clean)) ** 2)
                            r2 = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

                            # Plot regression line
                            x_reg = np.array([x_clean.min(), x_clean.max()])
                            y_reg = slope * x_reg + intercept
                            ax.plot(x_reg, y_reg, 'r-', linewidth=2, label='Regression', zorder=2)

                            # 1:1 line
                            min_val = min(x_clean.min(), y_clean.min())
                            max_val = max(x_clean.max(), y_clean.max())
                            ax.plot([min_val, max_val], [min_val, max_val], '--', color='grey',
                                   linewidth=1.5, label='1:1 line', zorder=1)

                            # Set limits
                            ax.set_xlim(-200, 1000)
                            ax.set_ylim(-200, 1000)

                            # Labels
                            ax.set_xlabel('Rn - G (W/m²)', fontsize=11)
                            ax.set_ylabel('LE + H (W/m²)', fontsize=11)
                            ax.set_title(f'{label}\nSlope: {slope:.3f}, R²: {r2:.3f}', fontsize=12, fontweight='bold')
                            ax.grid(True, alpha=0.3)
                            ax.legend(fontsize=9)

                            results.append({
                                'shift': shift,
                                'label': label,
                                'slope': slope,
                                'r2': r2,
                                'n_points': len(x_clean)
                            })

                            print(f"  ✓ {label}: Slope={slope:.3f}, R²={r2:.3f}, N={len(x_clean)}")
                        else:
                            ax.text(0.5, 0.5, 'Insufficient data', ha='center', va='center',
                                   transform=ax.transAxes, fontsize=12)
                            ax.set_title(label, fontsize=12)

                    # Hide unused subplots
                    for idx in range(len(SHIFTS_TO_TEST), len(axes_ebc)):
                        axes_ebc[idx].axis('off')

                    fig_ebc_shifts.suptitle(f'Energy Balance Closure Comparison - {STATION}',
                                            fontsize=14, fontweight='bold')
                    plt.tight_layout(rect=[0, 0.03, 1, 0.96])
                    fig_ebc_shifts.savefig(f'{STATION}_energy_balance_closure_shifts.png', dpi=300, bbox_inches='tight')
                    print(f"\n✓ Energy Balance Closure comparison plot saved: {STATION}_energy_balance_closure_shifts.png")

                    # Print comparison summary
                    if len(results) > 0:
                        print("\n  Comparison Summary:")
                        print(f"  {'Shift':<15} {'Slope':<10} {'R²':<10} {'N points':<10}")
                        print("  " + "-" * 50)
                        for r in results:
                            print(f"  {r['label']:<15} {r['slope']:<10.3f} {r['r2']:<10.3f} {r['n_points']:<10}")

                        # Find best shift (highest R²)
                        best = max(results, key=lambda x: x['r2'])
                        print(f"\n  ✓ Best alignment: {best['label']} (R²={best['r2']:.3f}, Slope={best['slope']:.3f})")
                else:
                    print("  ⚠️  Insufficient data for shift comparison")
                    # Fall back to standard plot (with shift if actually applied)
                    shift_label = f' (+{SHIFT_INTERVALS * 30} min shift)' if shift_applied else ''
                    print(f"Creating standard Energy Balance Closure plot{shift_label}...")
                    fig1 = plot_energy_balance_closure(
                        eb_df,
                        start=START_DATE,
                        end=END_DATE,
                        title=f'Energy Balance Closure - {STATION} (EddyPro){shift_label}'
                    )
                    fig1.savefig(f'{STATION}_energy_balance_closure.png', dpi=300, bbox_inches='tight')
                    print(f"  ✓ Energy Balance Closure plot created (EddyPro){shift_label}")
            else:
                # Standard EBC plot (no shifts, or with single shift if actually applied)
                shift_label = f' (+{SHIFT_INTERVALS * 30} min shift)' if shift_applied else ''
                print(f"Creating Energy Balance Closure plot{shift_label}...")
                fig1 = plot_energy_balance_closure(
                    eb_df,
                    start=START_DATE,
                    end=END_DATE,
                    title=f'Energy Balance Closure - {STATION} (EddyPro){shift_label}'
                )
                fig1.savefig(f'{STATION}_energy_balance_closure.png', dpi=300, bbox_inches='tight')
                print(f"  ✓ Energy Balance Closure plot created (EddyPro){shift_label}")
        else:
            print("  ⚠️  Skipping Energy Balance Closure plot (Rn not available)")
            print("     Energy Balance Closure requires Rn (net radiation)")

        # Additional Energy Balance Closure Plot with Dragan data (for Kayoro, Nazinga, Sumbrungu)
        if STATION in ['Kayoro', 'Nazinga', 'Sumbrungu']:
            if LvE_dragan is not None and HTs_dragan is not None and Rn is not None and G is not None:
                print("\nCreating Energy Balance Closure plot with TK3 data...")

                # Apply same filters to Dragan data as to EddyPro data
                # Filter LvE_dragan by quality flags (if available)
                LvE_dragan_filtered = LvE_dragan.copy()
                if LvE_dragan is not None:
                    flag_cols = ['Flag(LvE)', 'Flag_LvE', 'LvE_Flag', 'qc_LvE']
                    for flag_col in flag_cols:
                        if flag_col in df_dragan.columns:
                            flag_le = pd.to_numeric(df_dragan[flag_col], errors='coerce')
                            high_quality_mask = (flag_le <= 1) & (flag_le.notna())
                            LvE_dragan_filtered = LvE_dragan_filtered[high_quality_mask]
                            print(f"  ✓ Filtered LvE_dragan by {flag_col} <= 1: {LvE_dragan_filtered.notna().sum()} high-quality values")
                            break

                    # Filter by LE > -200 (same as EddyPro)
                    before_count = LvE_dragan_filtered.notna().sum()
                    LvE_dragan_filtered = LvE_dragan_filtered[LvE_dragan_filtered > -200]
                    after_count = LvE_dragan_filtered.notna().sum()
                    if before_count != after_count:
                        print(f"  ✓ Filtered LvE_dragan by LE > -200: {after_count} values remaining")

                # Filter HTs_dragan by quality flags (if available)
                HTs_dragan_filtered = HTs_dragan.copy()
                if HTs_dragan is not None:
                    flag_cols = ['Flag(HTs)', 'Flag_HTs', 'HTs_Flag', 'qc_HTs']
                    for flag_col in flag_cols:
                        if flag_col in df_dragan.columns:
                            flag_h = pd.to_numeric(df_dragan[flag_col], errors='coerce')
                            high_quality_mask = (flag_h <= 1) & (flag_h.notna())
                            HTs_dragan_filtered = HTs_dragan_filtered[high_quality_mask]
                            print(f"  ✓ Filtered HTs_dragan by {flag_col} <= 1: {HTs_dragan_filtered.notna().sum()} high-quality values")
                            break

                # Build energy balance DataFrame with Dragan data
                eb_df_dragan = build_energy_balance_df(
                    SW_in=SW_in if SW_in is not None else pd.Series(0, index=G.index if G is not None else pd.DatetimeIndex([])),
                    SW_out=SW_out if SW_out is not None else pd.Series(0, index=G.index if G is not None else pd.DatetimeIndex([])),
                    LW_in=LW_in if LW_in is not None else pd.Series(0, index=G.index if G is not None else pd.DatetimeIndex([])),
                    LW_out=LW_out if LW_out is not None else pd.Series(0, index=G.index if G is not None else pd.DatetimeIndex([])),
                    LE=LvE_dragan_filtered,
                    H=HTs_dragan_filtered,
                    G=G,
                    Delta=Delta if Delta is not None else pd.Series(0, index=G.index if G is not None else pd.DatetimeIndex([])),
                    start=START_DATE,
                    end=END_DATE,
                    site_name=STATION
                )

                if not eb_df_dragan.empty and (eb_df_dragan['Rn'] != 0).any():
                    print(f"  ✓ Energy Balance DataFrame created with TK3 data: {len(eb_df_dragan)} records")
                    fig1_dragan = plot_energy_balance_closure(
                        eb_df_dragan,
                        start=START_DATE,
                        end=END_DATE,
                        title=f'Energy Balance Closure - {STATION} (TK3)'
                    )
                    fig1_dragan.savefig(f'{STATION}_energy_balance_closure_TK3.png', dpi=300, bbox_inches='tight')
                    print("  ✓ Energy Balance Closure plot created (TK3)")
                else:
                    print("  ⚠️  Skipping Energy Balance Closure plot with TK3 data (insufficient data)")
            else:
                print("\n  ⚠️  Skipping Energy Balance Closure plot with TK3 data (TK3 or required data not available)")

        # All Energy Balance Components
        # Create a DataFrame with ALL available data (no dropna) for plotting
        print("\nCreating Energy Balance components plot...")
        print("  Building DataFrame with all available data (for plotting)...")

        from ec_analysis.aggregation import safe_slice

        # Calculate Rn EXACTLY as in plot_radiation_components - directly from df_rad
        # This ensures we use the same data as in the radiation components plot
        if df_rad is not None:
            # Get radiation components directly from df_rad (same as plot_radiation_components)
            # First check for Dragan station names (Kayoro, Nazinga, Sumbrungu)
            if STATION in ['Kayoro', 'Nazinga', 'Sumbrungu']:
                # Pre-2016: Dragan columns only; from 2016: Parquet columns only
                cutoff_date = pd.to_datetime('2016-01-01')
                dragan_SW_in = df_rad.get('SW_in korrigiert', None)
                dragan_SW_out = df_rad.get('SW_out korrigiert', None)
                dragan_LW_in = df_rad.get('LW_in_Avg [W/m^2]', None)
                dragan_LW_out = df_rad.get('LW_out_Avg [W/m^2]', None)
                parquet_SW_in = df_rad.get('SR_in_Avg', None)
                parquet_SW_out = df_rad.get('SR_out_Avg', None)
                parquet_LW_in = df_rad.get('IR_in_Avg', None)
                parquet_LW_out = df_rad.get('IR_out_Avg', None)
                idx_pre = df_rad.index < cutoff_date
                idx_post = df_rad.index >= cutoff_date
                if dragan_SW_in is not None and parquet_SW_in is not None:
                    rad_SW_in = dragan_SW_in.where(idx_pre).combine_first(parquet_SW_in.where(idx_post))
                elif dragan_SW_in is not None:
                    rad_SW_in = dragan_SW_in
                elif parquet_SW_in is not None:
                    rad_SW_in = parquet_SW_in
                else:
                    rad_SW_in = None
                if dragan_SW_out is not None and parquet_SW_out is not None:
                    rad_SW_out = dragan_SW_out.where(idx_pre).combine_first(parquet_SW_out.where(idx_post))
                elif dragan_SW_out is not None:
                    rad_SW_out = dragan_SW_out
                elif parquet_SW_out is not None:
                    rad_SW_out = parquet_SW_out
                else:
                    rad_SW_out = None
                if dragan_LW_in is not None and parquet_LW_in is not None:
                    rad_LW_in = dragan_LW_in.where(idx_pre).combine_first(parquet_LW_in.where(idx_post))
                elif dragan_LW_in is not None:
                    rad_LW_in = dragan_LW_in
                elif parquet_LW_in is not None:
                    rad_LW_in = parquet_LW_in
                else:
                    rad_LW_in = None
                if dragan_LW_out is not None and parquet_LW_out is not None:
                    rad_LW_out = dragan_LW_out.where(idx_pre).combine_first(parquet_LW_out.where(idx_post))
                elif dragan_LW_out is not None:
                    rad_LW_out = dragan_LW_out
                elif parquet_LW_out is not None:
                    rad_LW_out = parquet_LW_out
                else:
                    rad_LW_out = None
            else:
                rad_SW_in = df_rad.get('SW_IN', df_rad.get('SR_in_Avg', None))
                rad_SW_out = df_rad.get('SW_OUT', df_rad.get('SR_out_Avg', None))
                rad_LW_in = df_rad.get('LW_IN', df_rad.get('IR_in_Avg', None))
                rad_LW_out = df_rad.get('LW_OUT', df_rad.get('IR_out_Avg', None))

            # Apply Mole correction if needed (same as plot_radiation_components)
            from ec_analysis.plotting.energy_balance import apply_mole_sw_in_correction
            if rad_SW_in is not None:
                rad_SW_in = apply_mole_sw_in_correction(rad_SW_in, STATION)

            # Slice to date range (same as plot_radiation_components)
            if rad_SW_in is not None:
                rad_SW_in = rad_SW_in.loc[
                    (rad_SW_in.index >= pd.to_datetime(START_DATE)) &
                    (rad_SW_in.index <= pd.to_datetime(END_DATE))
                ]
            if rad_SW_out is not None:
                rad_SW_out = rad_SW_out.loc[
                    (rad_SW_out.index >= pd.to_datetime(START_DATE)) &
                    (rad_SW_out.index <= pd.to_datetime(END_DATE))
                ]
            if rad_LW_in is not None:
                rad_LW_in = rad_LW_in.loc[
                    (rad_LW_in.index >= pd.to_datetime(START_DATE)) &
                    (rad_LW_in.index <= pd.to_datetime(END_DATE))
                ]
            if rad_LW_out is not None:
                rad_LW_out = rad_LW_out.loc[
                    (rad_LW_out.index >= pd.to_datetime(START_DATE)) &
                    (rad_LW_out.index <= pd.to_datetime(END_DATE))
                ]

            # Calculate Rn from radiation components (EXACTLY as in radiation plot)
            if all([rad_SW_in is not None, rad_SW_out is not None,
                    rad_LW_in is not None, rad_LW_out is not None]):
                # Combine all radiation components into a DataFrame
                # Use outer join to preserve all timestamps from all components
                rad_df = pd.DataFrame({
                    'SW_in': rad_SW_in,
                    'SW_out': rad_SW_out,
                    'LW_in': rad_LW_in,
                    'LW_out': rad_LW_out
                })
                # Calculate Rn where all components are available
                has_all_rad = rad_df.notna().all(axis=1)
                rad_df['Rn'] = np.nan
                rad_df.loc[has_all_rad, 'Rn'] = (
                    rad_df.loc[has_all_rad, 'SW_in'] - rad_df.loc[has_all_rad, 'SW_out'] +
                    rad_df.loc[has_all_rad, 'LW_in'] - rad_df.loc[has_all_rad, 'LW_out']
                )
                Rn_plot = rad_df['Rn']
                # Debug: Check Rn_plot time range and frequency
                if len(Rn_plot) > 0:
                    time_diffs = Rn_plot.index.to_series().diff().dropna()
                    if len(time_diffs) > 0:
                        median_diff = time_diffs.median()
                        print(f"  ✓ Rn_plot time range: {Rn_plot.index.min()} to {Rn_plot.index.max()}")
                        print(f"  ✓ Rn_plot frequency: ~{median_diff}, {Rn_plot.notna().sum()} non-NaN values")
            else:
                Rn_plot = None
        else:
            Rn_plot = None

        # Get other components sliced to date range
        plot_series = {}
        if LE is not None:
            LE_sliced = safe_slice(LE, START_DATE, END_DATE)
            plot_series['LE'] = LE_sliced
            # Debug: Check LE frequency
            if len(LE_sliced) > 1:
                time_diffs = LE_sliced.index.to_series().diff().dropna()
                if len(time_diffs) > 0:
                    median_diff = time_diffs.median()
                    print(f"  ✓ LE original frequency: ~{median_diff}, {LE_sliced.notna().sum()} non-NaN values")
        if H is not None:
            H_sliced = safe_slice(H, START_DATE, END_DATE)
            plot_series['H'] = H_sliced
            # Debug: Check H frequency
            if len(H_sliced) > 1:
                time_diffs = H_sliced.index.to_series().diff().dropna()
                if len(time_diffs) > 0:
                    median_diff = time_diffs.median()
                    print(f"  ✓ H original frequency: ~{median_diff}, {H_sliced.notna().sum()} non-NaN values")
        if G is not None:
            G_sliced = safe_slice(G, START_DATE, END_DATE)
            plot_series['G'] = G_sliced
            # Debug: Check G frequency and NaN values
            if len(G_sliced) > 1:
                time_diffs = G_sliced.index.to_series().diff().dropna()
                if len(time_diffs) > 0:
                    most_common_diff = time_diffs.mode()[0] if len(time_diffs.mode()) > 0 else time_diffs.median()
                    print(f"  ✓ G original frequency: ~{most_common_diff}, {G_sliced.notna().sum()} non-NaN values")
                nan_count = G_sliced.isna().sum()
                total_count = len(G_sliced)
                if nan_count > 0:
                    nan_pct = (nan_count / total_count) * 100
                    print(f"  ✓ G: {nan_count}/{total_count} NaN values ({nan_pct:.1f}%)")
        if Delta is not None:
            plot_series['Delta'] = safe_slice(Delta, START_DATE, END_DATE)
        if Rn_plot is not None:
            plot_series['Rn'] = Rn_plot
            # Debug: Check Rn_plot frequency before resampling
            if len(Rn_plot) > 1:
                time_diffs = Rn_plot.index.to_series().diff().dropna()
                if len(time_diffs) > 0:
                    median_diff = time_diffs.median()
                    print(f"  ✓ Rn_plot original frequency: ~{median_diff}, {Rn_plot.notna().sum()} non-NaN values")

        # Plot Rn and G directly after loading (before resampling) for debugging
        print("\n  Creating debug plot: Rn and G before resampling...")
        if (Rn_plot is not None and len(Rn_plot) > 0) or (G is not None and len(G) > 0):
            fig_debug, axes_debug = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

            # Plot Rn
            if Rn_plot is not None and len(Rn_plot) > 0:
                Rn_sliced = safe_slice(Rn_plot, START_DATE, END_DATE)
                if len(Rn_sliced) > 0:
                    axes_debug[0].plot(Rn_sliced.index, Rn_sliced, color='blue', linewidth=1.5, label='Rn (before resampling)', alpha=0.7)
                    axes_debug[0].set_ylabel('Rn (W/m²)', fontsize=12)
                    axes_debug[0].set_title(f'Rn - {STATION} (Before Resampling)', fontsize=12, fontweight='bold')
                    axes_debug[0].grid(True, alpha=0.3)
                    axes_debug[0].axhline(y=0, color='black', linestyle='--', linewidth=0.5)
                    axes_debug[0].legend(fontsize=10)
                    print(f"     ✓ Plotted Rn: {Rn_sliced.notna().sum()} values, time range: {Rn_sliced.index.min()} to {Rn_sliced.index.max()}")

            # Plot G
            if G is not None and len(G) > 0:
                G_sliced_debug = safe_slice(G, START_DATE, END_DATE)
                if len(G_sliced_debug) > 0:
                    axes_debug[1].plot(G_sliced_debug.index, G_sliced_debug, color='red', linewidth=1.5, label='G (before resampling)', alpha=0.7)
                    axes_debug[1].set_ylabel('G (W/m²)', fontsize=12)
                    axes_debug[1].set_xlabel('Date', fontsize=12)
                    axes_debug[1].set_title(f'G - {STATION} (Before Resampling)', fontsize=12, fontweight='bold')
                    axes_debug[1].grid(True, alpha=0.3)
                    axes_debug[1].axhline(y=0, color='black', linestyle='--', linewidth=0.5)
                    axes_debug[1].legend(fontsize=10)
                    print(f"     ✓ Plotted G: {G_sliced_debug.notna().sum()} values, time range: {G_sliced_debug.index.min()} to {G_sliced_debug.index.max()}")

            fig_debug.suptitle(f'Rn and G Before Resampling - {STATION}', fontsize=14, fontweight='bold')
            plt.tight_layout(rect=[0, 0.03, 1, 0.96])
            fig_debug.savefig(f'{STATION}_Rn_G_before_resampling.png', dpi=300, bbox_inches='tight')
            print(f"  ✓ Debug plot saved: {STATION}_Rn_G_before_resampling.png")

        # Resample all series to 30-minute intervals to ensure common timestamps
        # Use origin='start_day' to align all series to the same time grid (00:00, 00:30, 01:00, etc.)
        # This ensures that all series will have matching timestamps after resampling
        freq = '30min'  # 30 minutes

        # Find a common reference point for alignment
        # Use the earliest timestamp from all series, rounded to start of day
        all_starts = []
        for name, series in plot_series.items():
            if series is not None and len(series) > 0:
                all_starts.append(series.index.min())

        if all_starts:
            # Use the earliest timestamp, rounded to start of day, as origin
            # This ensures all series align to the same 30-minute grid
            reference_date = min(all_starts).normalize()  # Start of day
        else:
            reference_date = None

        plot_series_resampled = {}
        for name, series in plot_series.items():
            if series is not None and len(series) > 0:
                # Count non-NaN values before resampling
                original_count = series.notna().sum()

                # Resample to 30-minute intervals using mean
                # Use origin=reference_date to align all series to the same time grid
                # This ensures consistent binning across all series (00:00, 00:30, 01:00, etc.)
                if reference_date is not None:
                    resampled = series.resample(freq, label='right', closed='right', origin=reference_date).mean()
                else:
                    resampled = series.resample(freq, label='right', closed='right').mean()

                resampled_count = resampled.notna().sum()
                plot_series_resampled[name] = resampled

                # Debug: Show first few timestamps after resampling to check alignment
                if name in ['Rn', 'LE', 'H', 'G'] and resampled_count > 0:
                    sample_ts = resampled.dropna().head(3).index
                    print(f"     {name} resampled timestamps (first 3): {sample_ts.tolist()}")

                # Debug output for G (soil heat flux)
                if name == 'G':
                    print(f"  ✓ G: {original_count} values before resampling, {resampled_count} values after resampling")
                    if original_count > 0:
                        # Calculate expected reduction based on frequency
                        # If original is 5-min data, expect ~1/6 reduction (5min -> 30min)
                        time_diffs = series.index.to_series().diff().dropna() if len(series) > 1 else pd.Series()
                        if len(time_diffs) > 0:
                            median_diff = time_diffs.median()
                            if pd.notna(median_diff) and median_diff > pd.Timedelta(0):
                                expected_ratio = pd.Timedelta(freq) / median_diff
                                if expected_ratio > 0:
                                    expected_count = int(original_count / expected_ratio)
                                    print(f"     Expected ~{expected_count} values after resampling (based on {median_diff} frequency)")
                                    if resampled_count < expected_count * 0.7:  # If we have less than 70% of expected
                                        print(f"  ⚠️  Warning: Only {resampled_count} values after resampling, expected ~{expected_count}")
                                        print(f"     This may be due to irregular timestamps or large gaps in data")

                # Debug output for Rn to check alignment
                if name == 'Rn':
                    print(f"  ✓ Rn: {original_count} values before resampling, {resampled_count} values after resampling")
                    if resampled_count > 0:
                        print(f"     Rn time range: {resampled.index.min()} to {resampled.index.max()}")
                        # Show sample timestamps to check alignment
                        sample_ts = resampled.dropna().head(5).index
                        print(f"     Rn sample timestamps: {sample_ts.tolist()}")

                # Debug output for LE to check alignment
                if name == 'LE':
                    print(f"  ✓ LE: {original_count} values before resampling, {resampled_count} values after resampling")
                    if resampled_count > 0:
                        sample_ts = resampled.dropna().head(5).index
                        print(f"     LE sample timestamps: {sample_ts.tolist()}")

                # Debug output for H to check alignment
                if name == 'H':
                    print(f"  ✓ H: {original_count} values before resampling, {resampled_count} values after resampling")
                    if resampled_count > 0:
                        sample_ts = resampled.dropna().head(5).index
                        print(f"     H sample timestamps: {sample_ts.tolist()}")
            else:
                plot_series_resampled[name] = series

        # Create DataFrame from all resampled series
        # Simply concatenate with outer join - this will preserve all timestamps from all series
        if plot_series_resampled:
            # Use concat with outer join to combine all series
            # This will create a union of all time indices, preserving all data points
            eb_df_plot = pd.concat(plot_series_resampled, axis=1, join='outer')
            eb_df_plot.columns = list(plot_series_resampled.keys())

            # Debug: Check if timestamps align properly
            if not eb_df_plot.empty:
                # Check overlap between series
                for col1 in ['Rn', 'LE', 'H', 'G']:
                    if col1 in eb_df_plot.columns:
                        for col2 in ['Rn', 'LE', 'H', 'G']:
                            if col2 in eb_df_plot.columns and col1 != col2:
                                # Find timestamps where both have data
                                both_data = eb_df_plot[[col1, col2]].dropna()
                                if len(both_data) > 0:
                                    print(f"     Overlap {col1}-{col2}: {len(both_data)} timestamps with both data")
                                else:
                                    print(f"     ⚠️  No overlap between {col1} and {col2}")
        else:
            eb_df_plot = pd.DataFrame()

        # Calculate Residual where all components are available
        if not eb_df_plot.empty and all(col in eb_df_plot.columns for col in ['Rn', 'LE', 'H', 'G']):
            has_all = eb_df_plot[['Rn', 'LE', 'H', 'G']].notna().all(axis=1)
            eb_df_plot['Residual'] = np.nan
            eb_df_plot.loc[has_all, 'Residual'] = (
                eb_df_plot.loc[has_all, 'Rn'] -
                (eb_df_plot.loc[has_all, 'LE'] + eb_df_plot.loc[has_all, 'H'] +
                 eb_df_plot.loc[has_all, 'G'] + eb_df_plot.loc[has_all, 'Delta'].fillna(0))
            )

        print(f"  ✓ Plot DataFrame created: {len(eb_df_plot)} records (all available data)")
        print(f"  ✓ All series resampled to 30-minute intervals")

        # Debug: Check alignment of all series and identify missing data periods
        if not eb_df_plot.empty:
            print(f"  ✓ DataFrame time range: {eb_df_plot.index.min()} to {eb_df_plot.index.max()}")
            for col in ['Rn', 'LE', 'H', 'G']:
                if col in eb_df_plot.columns:
                    non_nan_count = eb_df_plot[col].notna().sum()
                    print(f"     {col}: {non_nan_count} non-NaN values in DataFrame")
                    if non_nan_count > 0:
                        # Check time range where data exists
                        col_data = eb_df_plot[col].dropna()
                        if len(col_data) > 0:
                            print(f"       {col} time range: {col_data.index.min()} to {col_data.index.max()}")

            # Check for periods where LE/H have data but Rn/G don't
            if 'LE' in eb_df_plot.columns and 'H' in eb_df_plot.columns:
                le_h_data = eb_df_plot[['LE', 'H']].dropna()
                if len(le_h_data) > 0:
                    print(f"     LE/H data period: {le_h_data.index.min()} to {le_h_data.index.max()}")
                    if 'Rn' in eb_df_plot.columns:
                        # Check Rn in LE/H period
                        rn_in_period = eb_df_plot.loc[le_h_data.index, 'Rn'].dropna()
                        print(f"       Rn values in LE/H period: {len(rn_in_period)} out of {len(le_h_data)}")
                        if len(rn_in_period) < len(le_h_data) * 0.5:
                            print(f"       ⚠️  Warning: Rn missing for {len(le_h_data) - len(rn_in_period)} timestamps where LE/H have data")
                    if 'G' in eb_df_plot.columns:
                        # Check G in LE/H period
                        g_in_period = eb_df_plot.loc[le_h_data.index, 'G'].dropna()
                        print(f"       G values in LE/H period: {len(g_in_period)} out of {len(le_h_data)}")
                        if len(g_in_period) < len(le_h_data) * 0.5:
                            print(f"       ⚠️  Warning: G missing for {len(le_h_data) - len(g_in_period)} timestamps where LE/H have data")

        if Rn_plot is not None:
            print(f"  ✓ Rn: {Rn_plot.notna().sum()} values in original series")
            if 'Rn' in eb_df_plot.columns:
                print(f"  ✓ Rn in DataFrame (after resampling): {eb_df_plot['Rn'].notna().sum()} values")

        fig2 = plot_energy_balance(
            eb_df_plot,
            start=START_DATE,
            end=END_DATE,
            title=f'Energy Balance Components - {STATION}'
        )
        # Save plot (uncomment to save)
        fig2.savefig(f'{STATION}_energy_balance_components.png', dpi=300, bbox_inches='tight')
        print("  ✓ Energy Balance components plot created")

        # Diurnal Cycle
        print("\nCreating Diurnal Cycle plot...")
        fig3 = plot_diurnal_cycle(
            eb_df,
            columns=['Rn', 'LE', 'H', 'G'],
            start=START_DATE,
            end=END_DATE,
            title=f'Diurnal Cycle - {STATION}'
        )
        # Save plot (uncomment to save)
        fig3.savefig(f'{STATION}_diurnal_cycle.png', dpi=300, bbox_inches='tight')
        print("  ✓ Diurnal Cycle plot created")

        # Radiation Components Plot
        if df_rad is not None:
            print("\nCreating Radiation Components plot...")
            fig4 = plot_radiation_components(
                df_rad,
                start=START_DATE,
                end=END_DATE,
                title=f'Radiation Components - {STATION}',
                site_name=STATION
            )
            fig4.savefig(f'{STATION}_radiation_components.png', dpi=300, bbox_inches='tight')
            print("  ✓ Radiation Components plot created")
        else:
            print("\n  ⚠️  Skipping Radiation Components plot (radiation data not available)")

        # Soil Variables Plot
        if df_cr1000 is not None and len(df_cr1000.columns) > 0:
            print("\nCreating Soil Variables plot...")
            # For Janga, use df_rad which contains TS and SWC columns
            soil_df = df_rad if STATION == 'Janga' and df_rad is not None else df_cr1000
            if soil_df is not None:
                fig5 = plot_soil_variables(
                    soil_df,
                    start=START_DATE,
                    end=END_DATE,
                    title=f'Soil Variables - {STATION}'
                )
                fig5.savefig(f'{STATION}_soil_variables.png', dpi=300, bbox_inches='tight')
                print("  ✓ Soil Variables plot created")
            else:
                print("  ⚠️  Skipping Soil Variables plot (soil data not available)")
        else:
            print("\n  ⚠️  Skipping Soil Variables plot (soil data not available)")

        # Comparison Plot: TK3 LvE/HTs vs EddyPro LE/H
        if STATION in ['Kayoro', 'Nazinga', 'Sumbrungu']:
            if (LvE_dragan is not None or HTs_dragan is not None) and (LE is not None or H is not None):
                print("\nCreating Flux Comparison plot (TK3 vs EddyPro)...")

                from ec_analysis.aggregation import safe_slice

                # Prepare data for comparison
                comparison_data = {}

                # Latent heat flux comparison
                if LvE_dragan is not None and LE is not None:
                    LvE_sliced = safe_slice(LvE_dragan, START_DATE, END_DATE)
                    LE_sliced = safe_slice(LE, START_DATE, END_DATE)
                    # Resample to common frequency (30 minutes)
                    freq = '30min'
                    LvE_resampled = LvE_sliced.resample(freq).mean()
                    LE_resampled = LE_sliced.resample(freq).mean()
                    comparison_data['LvE_Dragan'] = LvE_resampled
                    comparison_data['LE_EddyPro'] = LE_resampled

                # Sensible heat flux comparison
                if HTs_dragan is not None and H is not None:
                    HTs_sliced = safe_slice(HTs_dragan, START_DATE, END_DATE)
                    H_sliced = safe_slice(H, START_DATE, END_DATE)
                    # Resample to common frequency (30 minutes)
                    HTs_resampled = HTs_sliced.resample(freq).mean()
                    H_resampled = H_sliced.resample(freq).mean()
                    comparison_data['HTs_Dragan'] = HTs_resampled
                    comparison_data['H_EddyPro'] = H_resampled

                if comparison_data:
                    # Create comparison DataFrame
                    comp_df = pd.DataFrame(comparison_data)

                    # Create plot
                    fig6, axes = plt.subplots(len(comparison_data) // 2, 1, figsize=(14, 8), sharex=True)
                    if len(comparison_data) == 2:
                        axes = [axes]

                    colors_dragan = {'LvE_Dragan': '#2ca02c', 'HTs_Dragan': '#ff7f0e'}
                    colors_eddypro = {'LE_EddyPro': '#1f77b4', 'H_EddyPro': '#d62728'}

                    plot_idx = 0
                    if 'LvE_Dragan' in comp_df.columns and 'LE_EddyPro' in comp_df.columns:
                        ax = axes[plot_idx]
                        ax.plot(comp_df.index, comp_df['LvE_Dragan'],
                               color=colors_dragan['LvE_Dragan'], linewidth=1.5,
                               label='LvE (TK3)', alpha=0.7)
                        ax.plot(comp_df.index, comp_df['LE_EddyPro'],
                               color=colors_eddypro['LE_EddyPro'], linewidth=1.5,
                               label='LE (EddyPro)', alpha=0.7, linestyle='--')
                        ax.set_ylabel('Latent Heat Flux (W/m²)', fontsize=12)
                        ax.set_title('Latent Heat Flux: TK3 vs EddyPro', fontsize=13, fontweight='bold')
                        # Use same limits as energy balance components (LE/H range)
                        ax.set_ylim(-300, 800)
                        ax.grid(True, alpha=0.3)
                        ax.axhline(y=0, color='black', linestyle='--', linewidth=0.5)
                        ax.legend(fontsize=10)
                        plot_idx += 1

                    if 'HTs_Dragan' in comp_df.columns and 'H_EddyPro' in comp_df.columns:
                        ax = axes[plot_idx]
                        ax.plot(comp_df.index, comp_df['HTs_Dragan'],
                               color=colors_dragan['HTs_Dragan'], linewidth=1.5,
                               label='HTs (TK3)', alpha=0.7)
                        ax.plot(comp_df.index, comp_df['H_EddyPro'],
                               color=colors_eddypro['H_EddyPro'], linewidth=1.5,
                               label='H (EddyPro)', alpha=0.7, linestyle='--')
                        ax.set_ylabel('Sensible Heat Flux (W/m²)', fontsize=12)
                        ax.set_title('Sensible Heat Flux: TK3 vs EddyPro', fontsize=13, fontweight='bold')
                        # Use same limits as energy balance components (LE/H range)
                        ax.set_ylim(-300, 800)
                        ax.grid(True, alpha=0.3)
                        ax.axhline(y=0, color='black', linestyle='--', linewidth=0.5)
                        ax.legend(fontsize=10)

                    axes[-1].set_xlabel('Date', fontsize=12)
                    for ax in axes:
                        ax.tick_params(axis='x', rotation=45, labelsize=9)
                        for label in ax.get_xticklabels():
                            label.set_ha('right')

                    fig6.suptitle(f'Heat Flux Comparison - {STATION}', fontsize=14, fontweight='bold')
                    plt.tight_layout(rect=[0, 0.03, 1, 0.96])
                    fig6.savefig(f'{STATION}_flux_comparison.png', dpi=300, bbox_inches='tight')
                    print("  ✓ Flux Comparison plot created")
                else:
                    print("  ⚠️  Skipping Flux Comparison plot (insufficient data)")
            else:
                print("\n  ⚠️  Skipping Flux Comparison plot (TK3 or EddyPro data not available)")

        print("\n✅ All plots created successfully!")
        print("\nNote: Uncomment the savefig() lines to save plots to files.")

    else:
        print("  ⚠️  Energy Balance DataFrame is empty - check date range and data availability")
else:
    print("  ⚠️  Missing required components for Energy Balance:")
    missing = []
    if Rn is None:
        missing.append("Rn")
    if LE is None:
        missing.append("LE")
    if H is None:
        missing.append("H")
    if G is None:
        missing.append("G")
    print(f"     Missing: {', '.join(missing)}")
    print("\n  Please ensure all data sources are available and paths are correct.")

