"""
Compare data coverage between merged_long parquet files and test_data/long dat files
for Gorigo station.
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('MacOSX')  # Use macOS native backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# Import data loaders
from data_loader import read_toa5, apply_column_names

# =============================================
# Configuration
# =============================================

MERGED_DIR = Path("/Users/hingerl-l/Data/merged_long")
TEST_DIR = Path("/Users/hingerl-l/Diss/Data/test_data/long")

# Column name mappings for result files
RESULT_COLS = [
    'T_end', 'u[m/s]', 'v[m/s]', 'w[m/s]', 'Ts[°C]', 'Tp[°C]', 'a[g/m³]',
    'CO2[mmol/m³]', 'T_ref[°C]', 'a_ref[g/m³]', 'p_ref[hPa]', 'Var[u]',
    'Var[v]', 'Var[w]', 'Var[Ts]', 'Var[Tp]', 'Var[a]', 'Var[CO2]',
    "Cov[u'v']", "Cov[v'w']", "Cov[u'w']", "Cov[u'Ts']", "Cov[v'Ts']",
    "Cov[w'Ts']", "Cov[u'Tp']", "Cov[v'Tp']", "Cov[w'Tp']",
    "Cov[u'a']", "Cov[v'a']", "Cov[w'a']", "Cov[u'CO2']", "Cov[v'CO2']",
    "Cov[w'CO2']", '???', 'dir[°]', 'ustar[m/s]', 'HTs[W/m²]', 'HTp[W/m²]',
    'LvE[W/m²]', 'z/L', 'z/L-virt', 'Flag(ustar)', 'Flag(HTs)',
    'Flag(HTp)', 'Flag(LvE)', 'Flag(wCO2)', 'T_mid', 'FCstor[mmol/m²s]',
    'NEE[mmol/m²s]', 'Footprint_trgt_1', 'Footprint_trgt_2',
    'Footprnt_xmax[m]', ' r_err_ustar[%]', 'r_err_HTs[%]',
    'r_err_LvE[%]', 'r_err_co2[%]', 'noise_ustar[%]', 'noise_HTs[%]',
    'noise_LvE[%]', 'noise_co2[%]', 'Filler_to_reach61'
]

# Y-axis limits for physically realistic ranges
YLIMITS = {
    'NetTot_Avg': (-200, 1000),       # Net radiation W/m²
    'LvE[W/m²]': (-100, 600),          # Latent heat flux W/m²
    'HTs[W/m²]': (-100, 400),          # Sensible heat flux W/m²
    'H_Flux_East': (-50, 150),         # Soil heat flux W/m²
    'H_Flux_Middle': (-50, 150),
    'H_Flux_West': (-50, 150),
    'TCAV_C_Avg': (10, 50),            # Soil temperature °C
    'VW_Avg': (0, 0.6),                # Volumetric water content m³/m³
    'Rain_mm_Tot': (0, 50),            # Precipitation mm/30min
}


# =============================================
# Data Loading Functions
# =============================================

def load_merged_parquet(file_type):
    """Load parquet file from merged_long directory."""
    filepath = MERGED_DIR / f"Gorigo_{file_type}_merged_long.parquet"
    if not filepath.exists():
        print(f"Warning: {filepath} not found")
        return None
    df = pd.read_parquet(filepath)
    return df


def load_test_dat(file_type):
    """Load dat file from test_data/long directory."""
    # Map file types to file names
    file_map = {
        'cr1000': 'Gorigo_long_cr1000.dat',
        'radiation': 'Gorigo_long_rad.dat',
        'result': 'Gorigo_long_result.dat',
        'smt': 'Gorigo_long_smt.dat',
    }
    
    if file_type not in file_map:
        print(f"Unknown file type: {file_type}")
        return None
    
    filepath = TEST_DIR / file_map[file_type]
    if not filepath.exists():
        print(f"Warning: {filepath} not found")
        return None
    
    if file_type == 'result':
        # Result file has no header, special format
        df = pd.read_csv(
            filepath,
            header=None,
            na_values=['NAN', 'nan', '-9999', '-9999.9003906'],
            on_bad_lines='skip'
        )
        # Parse date from first column (format: DD.MM.YYYY HH:MM)
        df[0] = pd.to_datetime(df[0], format='%d.%m.%Y %H:%M', errors='coerce')
        df = df.set_index(0)
        df.index.name = 'TIMESTAMP'
        
        # Apply column names (skip first column which is index)
        if len(df.columns) == len(RESULT_COLS):
            df.columns = RESULT_COLS
        else:
            print(f"Result file has {len(df.columns)} columns, expected {len(RESULT_COLS)}")
    
    elif file_type in ['cr1000', 'radiation']:
        # TOA5 format with header
        df = read_toa5(filepath)
        # Drop RECORD column if present
        if 'RECORD' in df.columns:
            df = df.drop(columns=['RECORD'])
    
    else:
        # SMT file - headerless
        df = pd.read_csv(
            filepath,
            header=None,
            parse_dates=[0],
            index_col=0,
            na_values=['NAN', 'nan', '"NAN"']
        )
        df.index.name = 'TIMESTAMP'
    
    return df


def find_matching_column(df, patterns):
    """Find a column matching any of the given patterns (exact or partial)."""
    # First try exact match
    for pattern in patterns:
        if pattern in df.columns:
            return pattern
    # Then try case-insensitive partial match
    for col in df.columns:
        for pattern in patterns:
            if pattern.lower() in col.lower():
                return col
    return None


# =============================================
# Plotting Functions
# =============================================

def clean_series(series):
    """Clean a series: ensure numeric values, drop NaN, handle bad values."""
    if series is None:
        return None
    
    s = series.copy()
    
    # Ensure index is datetime and drop NaT
    s.index = pd.to_datetime(s.index, errors='coerce')
    s = s[s.index.notna()]
    
    # Convert to numeric, coercing errors
    s = pd.to_numeric(s, errors='coerce')
    
    # Replace bad values
    s = s.replace([-9999, -9999.9, -9999.9003906], np.nan)
    
    # Drop NaN values
    s = s.dropna()
    
    return s


def plot_comparison(merged_data, test_data, var_name, title, ylabel, ylim=None):
    """Create a comparison plot for a single variable."""
    fig, ax = plt.subplots(figsize=(14, 5))
    
    # Clean and plot merged data (blue)
    merged_clean = clean_series(merged_data)
    if merged_clean is not None and len(merged_clean) > 0:
        ax.scatter(merged_clean.index, merged_clean.values, 
                   alpha=0.3, s=1, c='blue', label='merged_long (parquet)')
    
    # Clean and plot test data (red)
    test_clean = clean_series(test_data)
    if test_clean is not None and len(test_clean) > 0:
        ax.scatter(test_clean.index, test_clean.values, 
                   alpha=0.3, s=1, c='red', label='test_data (dat)')
    
    ax.set_title(f'{title}\nData Coverage Comparison', fontsize=12)
    ax.set_xlabel('Date')
    ax.set_ylabel(ylabel)
    ax.legend(loc='upper right', markerscale=5)
    
    # Set y-axis limits if provided
    if ylim:
        ax.set_ylim(ylim)
    
    # Format x-axis
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    return fig


def main():
    """Main function to create all comparison plots."""
    print("Loading data from merged_long (parquet)...")
    merged_cr1000 = load_merged_parquet('cr1000')
    merged_radiation = load_merged_parquet('radiation')
    merged_result = load_merged_parquet('result')
    merged_smt = load_merged_parquet('smt')
    
    print("Loading data from test_data/long (dat)...")
    test_cr1000 = load_test_dat('cr1000')
    test_radiation = load_test_dat('radiation')
    test_result = load_test_dat('result')
    test_smt = load_test_dat('smt')
    
    print("\nCreating comparison plots...\n")
    
    # =============================================
    # 1. Net Radiation
    # =============================================
    print("Plotting Net Radiation...")
    merged_netrad = merged_radiation['NetTot_Avg'] if merged_radiation is not None and 'NetTot_Avg' in merged_radiation.columns else None
    test_netrad = test_radiation['NetTot_Avg'] if test_radiation is not None and 'NetTot_Avg' in test_radiation.columns else None
    
    fig = plot_comparison(merged_netrad, test_netrad, 
                          'NetTot_Avg', 'Net Radiation', 'W/m²', 
                          ylim=YLIMITS['NetTot_Avg'])
    plt.show()
    
    # =============================================
    # 2. Latent Heat Flux
    # =============================================
    print("Plotting Latent Heat Flux...")
    merged_lve = merged_result['LvE[W/m²]'] if merged_result is not None and 'LvE[W/m²]' in merged_result.columns else None
    test_lve = test_result['LvE[W/m²]'] if test_result is not None and 'LvE[W/m²]' in test_result.columns else None
    
    fig = plot_comparison(merged_lve, test_lve, 
                          'LvE[W/m²]', 'Latent Heat Flux (LvE)', 'W/m²', 
                          ylim=YLIMITS['LvE[W/m²]'])
    plt.show()
    
    # =============================================
    # 3. Sensible Heat Flux
    # =============================================
    print("Plotting Sensible Heat Flux...")
    merged_hts = merged_result['HTs[W/m²]'] if merged_result is not None and 'HTs[W/m²]' in merged_result.columns else None
    test_hts = test_result['HTs[W/m²]'] if test_result is not None and 'HTs[W/m²]' in test_result.columns else None
    
    fig = plot_comparison(merged_hts, test_hts, 
                          'HTs[W/m²]', 'Sensible Heat Flux (HTs)', 'W/m²', 
                          ylim=YLIMITS['HTs[W/m²]'])
    plt.show()
    
    # =============================================
    # 4. Soil Heat Flux - Three separate plots
    # =============================================
    print("Plotting Soil Heat Flux (3 plates)...")
    
    # Try different column name patterns for soil heat flux
    # Parquet uses English (East, Middle, West), dat uses German (Ost, Mitte, West)
    shf_patterns = {
        'East': ['H_Flux_sc_8_East_Avg', 'H_Flux_sc_8_Ost_Avg'],
        'Middle': ['H_Flux_sc_8_Middle_Avg', 'H_Flux_sc_8_Mitte_Avg'],
        'West': ['H_Flux_sc_8_West_Avg']
    }
    
    for plate_name, patterns in shf_patterns.items():
        merged_shf = None
        test_shf = None
        
        if merged_cr1000 is not None:
            col = find_matching_column(merged_cr1000, patterns)
            if col:
                merged_shf = merged_cr1000[col]
        
        if test_cr1000 is not None:
            col = find_matching_column(test_cr1000, patterns)
            if col:
                test_shf = test_cr1000[col]
        
        fig = plot_comparison(merged_shf, test_shf, 
                              f'Soil Heat Flux {plate_name}', 
                              f'Soil Heat Flux - Plate {plate_name}', 'W/m²',
                              ylim=YLIMITS[f'H_Flux_{plate_name}'])
        plt.show()
    
    # =============================================
    # 5. Soil Temperature
    # =============================================
    print("Plotting Soil Temperature...")
    
    for i in range(1, 4):
        col_name = f'TCAV_C_Avg({i})'
        merged_temp = merged_cr1000[col_name] if merged_cr1000 is not None and col_name in merged_cr1000.columns else None
        test_temp = test_cr1000[col_name] if test_cr1000 is not None and col_name in test_cr1000.columns else None
        
        fig = plot_comparison(merged_temp, test_temp, 
                              col_name, f'Soil Temperature - Sensor {i}', '°C',
                              ylim=YLIMITS['TCAV_C_Avg'])
        plt.show()
    
    # =============================================
    # 6. Volumetric Soil Water Content
    # =============================================
    print("Plotting Volumetric Soil Water Content...")
    
    for i in range(1, 4):
        col_name = f'VW_{i}_Avg'
        merged_vw = merged_cr1000[col_name] if merged_cr1000 is not None and col_name in merged_cr1000.columns else None
        test_vw = test_cr1000[col_name] if test_cr1000 is not None and col_name in test_cr1000.columns else None
        
        fig = plot_comparison(merged_vw, test_vw, 
                              col_name, f'Volumetric Soil Water Content - Sensor {i}', 'm³/m³',
                              ylim=YLIMITS['VW_Avg'])
        plt.show()
    
    # =============================================
    # 7. Precipitation
    # =============================================
    print("Plotting Precipitation...")
    merged_rain = merged_cr1000['Rain_mm_Tot'] if merged_cr1000 is not None and 'Rain_mm_Tot' in merged_cr1000.columns else None
    test_rain = test_cr1000['Rain_mm_Tot'] if test_cr1000 is not None and 'Rain_mm_Tot' in test_cr1000.columns else None
    
    fig = plot_comparison(merged_rain, test_rain, 
                          'Rain_mm_Tot', 'Precipitation', 'mm',
                          ylim=YLIMITS['Rain_mm_Tot'])
    plt.show()
    
    print("\nAll plots complete! Close all plot windows when done.")


if __name__ == "__main__":
    main()


