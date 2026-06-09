"""
Cross-Correlation Analysis: Rn vs (LE+H) for Alignment Detection

This script performs cross-correlation analysis between Rn and (LE+H) to detect
temporal misalignment. If the maximum correlation occurs at lag ≠ 0, this indicates
an alignment problem where the time series are shifted relative to each other.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.stats import pearsonr
try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    print("⚠️  Plotly not available. Install with: pip install plotly")

# Add package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ec_analysis import (
    load_ec_data,
    calculate_soil_heat_flux,
    build_energy_balance_df,
    filter_quality_flags,
)
from ec_analysis.aggregation import safe_slice
from ec_analysis.plotting.energy_balance import apply_mole_sw_in_correction

# ============================================================================
# CONFIGURATION
# ============================================================================
STATION = 'Kayoro'  # Change to your station
DATA_DIR = Path('/Users/hingerl-l/Data/merged_long')
EDDYPRO_DIR = Path('/Users/hingerl-l/Data')
DRAGAN_DATA_DIR = Path('/Users/hingerl-l/Diss/Data/ECdata_Dragan')

# Output directory for plots (in same folder as script)
PLOTS_DIR = Path(__file__).parent / 'plots'
PLOTS_DIR.mkdir(exist_ok=True)

# Date range for analysis
START_DATE = '2013-01-01'
END_DATE = '2016-01-01'

# File paths
if STATION in ['Kayoro', 'Nazinga', 'Sumbrungu']:
    DRAGAN_CSV_FILE = DRAGAN_DATA_DIR / f'{STATION}.csv'
    CR1000_FILE = DRAGAN_CSV_FILE if DRAGAN_CSV_FILE.exists() else None
    RADIATION_FILE = None  # Will be loaded from the same CSV file
    TK3_RESULT_FILE = None  # TK3 data in Dragan CSV
elif STATION == 'Gorigo':
    CR1000_FILE = EDDYPRO_DIR / STATION / 'merged' / f'{STATION}_cr1000_merged.csv'
    RADIATION_FILE = DATA_DIR / f'{STATION}_radiation_merged_long.parquet'
    TK3_RESULT_FILE = EDDYPRO_DIR / STATION / 'merged' / f'{STATION}_result_merged.csv'
else:
    CR1000_FILE = DATA_DIR / f'{STATION}_cr1000_merged_long.parquet'
    RADIATION_FILE = DATA_DIR / f'{STATION}_radiation_merged_long.parquet'
    TK3_RESULT_FILE = None

# Find EddyPro file automatically
EDDYPRO_FLUXES_DIR = EDDYPRO_DIR / STATION / 'processed' / 'fluxes'
EDDYPRO_FILE = None
if EDDYPRO_FLUXES_DIR.exists():
    pattern = f'eddypro_{STATION}_full_output_*.csv'
    eddypro_files = list(EDDYPRO_FLUXES_DIR.glob(pattern))
    if eddypro_files:
        EDDYPRO_FILE = max(eddypro_files, key=lambda p: p.stat().st_mtime)
        print(f"✓ Found EddyPro file: {EDDYPRO_FILE.name}")

# ============================================================================
# LOAD DATA
# ============================================================================
print("=" * 60)
print("Loading Data")
print("=" * 60)

# Initialize TK3 flux variables
LvE_dragan = None
HTs_dragan = None

# Load radiation data
if STATION in ['Kayoro', 'Nazinga', 'Sumbrungu']:
    if CR1000_FILE and CR1000_FILE.exists():
        print(f"Loading {STATION} data from Dragan CSV: {CR1000_FILE.name}")
        df_dragan = pd.read_csv(
            CR1000_FILE,
            sep=",",
            low_memory=False,
            na_values=["NAN", "NA", "-9999", "-9999.0", "-999", "**************"]
        )
        # Normalize column names (strip spaces) for compatibility
        df_dragan.columns = [c.strip() if isinstance(c, str) else c for c in df_dragan.columns]
        if 'T_begin' in df_dragan.columns:
            df_dragan['T_begin'] = pd.to_datetime(df_dragan['T_begin'], format='%m/%d/%y %H:%M', errors='coerce')
            df_dragan = df_dragan.set_index('T_begin')
            df_dragan.index.name = 'TIMESTAMP'
            df_dragan = df_dragan[df_dragan.index.notna()]
            df_dragan = df_dragan.sort_index()
            df_dragan = df_dragan[~df_dragan.index.duplicated(keep='first')]
        df_rad = df_dragan.copy()
        # Extract TK3 fluxes for comparison (after normalization, column names are without trailing spaces)
        for col in ['LvE[W/m_]', 'LvE']:
            if col in df_dragan.columns:
                LvE_dragan = pd.to_numeric(df_dragan[col], errors='coerce')
                break
        for col in ['HTs[W/m_]', 'HTs']:
            if col in df_dragan.columns:
                HTs_dragan = pd.to_numeric(df_dragan[col], errors='coerce')
                break
    else:
        df_rad = None
elif STATION == 'Gorigo':
    # Load radiation data
    if RADIATION_FILE and RADIATION_FILE.exists():
        print(f"Loading Radiation data: {RADIATION_FILE.name}")
        df_rad = load_ec_data(RADIATION_FILE)
    else:
        df_rad = None

    # Load TK3 result data for Gorigo
    if TK3_RESULT_FILE and TK3_RESULT_FILE.exists():
        print(f"Loading TK3 result data: {TK3_RESULT_FILE.name}")
        df_tk3_result = pd.read_csv(
            TK3_RESULT_FILE,
            sep=",",
            low_memory=False,
            na_values=["NAN", "NA", "-9999", "-9999.0", "-9999.9003906", "-999", "**************"]
        )
        # Try to find timestamp column
        timestamp_col = None
        for col in ['TIMESTAMP', 'T_begin', 'Date', 'Time']:
            if col in df_tk3_result.columns:
                timestamp_col = col
                break
        if timestamp_col:
            df_tk3_result[timestamp_col] = pd.to_datetime(df_tk3_result[timestamp_col], errors='coerce')
            df_tk3_result = df_tk3_result.set_index(timestamp_col)
            df_tk3_result.index.name = 'TIMESTAMP'
            df_tk3_result = df_tk3_result[df_tk3_result.index.notna()]
            df_tk3_result = df_tk3_result.sort_index()
            df_tk3_result = df_tk3_result[~df_tk3_result.index.duplicated(keep='first')]
            print(f"  ✓ Loaded {len(df_tk3_result)} records")
            print(f"  ✓ Columns: {list(df_tk3_result.columns)}")
        else:
            print(f"  ⚠️  Could not find timestamp column in TK3 result file")
            df_tk3_result = None

        if df_tk3_result is not None:
            # Extract TK3 fluxes: LvE[W/m²] and HTs[W/m²]
            # Try exact match first, then search for variants
            lve_cols = ['LvE[W/m²]', 'LvE[W/m^2]', 'LvE[W/m_]', 'LvE']
            hts_cols = ['HTs[W/m²]', 'HTs[W/m^2]', 'HTs[W/m_]', 'HTs']

            for col_name in lve_cols:
                if col_name in df_tk3_result.columns:
                    LvE_dragan = pd.to_numeric(df_tk3_result[col_name], errors='coerce')
                    print(f"  ✓ Found LvE column: {col_name}")
                    break
            # If not found, search for partial match
            if LvE_dragan is None:
                for col in df_tk3_result.columns:
                    if 'LvE' in col and ('W/m' in col or 'W/m²' in col or 'W/m^2' in col):
                        LvE_dragan = pd.to_numeric(df_tk3_result[col], errors='coerce')
                        print(f"  ✓ Found LvE column (variant): {col}")
                        break

            for col_name in hts_cols:
                if col_name in df_tk3_result.columns:
                    HTs_dragan = pd.to_numeric(df_tk3_result[col_name], errors='coerce')
                    print(f"  ✓ Found HTs column: {col_name}")
                    break
            # If not found, search for partial match
            if HTs_dragan is None:
                for col in df_tk3_result.columns:
                    if 'HTs' in col and ('W/m' in col or 'W/m²' in col or 'W/m^2' in col):
                        HTs_dragan = pd.to_numeric(df_tk3_result[col], errors='coerce')
                        print(f"  ✓ Found HTs column (variant): {col}")
                        break

            if LvE_dragan is not None:
                print(f"  ✓ LvE: {LvE_dragan.notna().sum()} values")
            else:
                print(f"  ⚠️  LvE column not found. Available columns: {list(df_tk3_result.columns)}")
            if HTs_dragan is not None:
                print(f"  ✓ HTs: {HTs_dragan.notna().sum()} values")
            else:
                print(f"  ⚠️  HTs column not found. Available columns: {list(df_tk3_result.columns)}")
    else:
        print(f"  ⚠️  TK3 result file not found: {TK3_RESULT_FILE}")
else:
    if RADIATION_FILE and RADIATION_FILE.exists():
        print(f"Loading Radiation data: {RADIATION_FILE.name}")
        df_rad = load_ec_data(RADIATION_FILE)
    else:
        df_rad = None

# Load CR1000 data (for G calculation)
df_cr1000 = None
if STATION in ['Kayoro', 'Nazinga', 'Sumbrungu']:
    if CR1000_FILE and CR1000_FILE.exists():
        df_cr1000 = df_dragan.copy() if 'df_dragan' in locals() else None
        # Exclude LvE and HTs columns (after normalization, column names are without trailing spaces)
        if df_cr1000 is not None:
            columns_to_exclude = ['LvE', 'HTs', 'LvE[W/m_]', 'HTs[W/m_]']
            df_cr1000 = df_cr1000.drop(columns=[col for col in columns_to_exclude if col in df_cr1000.columns])
elif STATION == 'Gorigo':
    if CR1000_FILE and CR1000_FILE.exists():
        print(f"Loading CR1000 data: {CR1000_FILE.name}")
        df_cr1000 = load_ec_data(CR1000_FILE)
        print(f"  ✓ Loaded {len(df_cr1000)} records")
else:
    if CR1000_FILE and CR1000_FILE.exists():
        print(f"Loading CR1000 data: {CR1000_FILE.name}")
        df_cr1000 = load_ec_data(CR1000_FILE)

# Load EddyPro data
if EDDYPRO_FILE and EDDYPRO_FILE.exists():
    print(f"Loading EddyPro data: {EDDYPRO_FILE.name}")
    df_eddypro = load_ec_data(EDDYPRO_FILE, format='eddypro')
else:
    df_eddypro = None

# ============================================================================
# PREPARE DATA
# ============================================================================
print("\n" + "=" * 60)
print("Preparing Data")
print("=" * 60)

# Get radiation components and calculate Rn
if df_rad is not None:
    if STATION in ['Kayoro', 'Nazinga', 'Sumbrungu']:
        SW_in = df_rad.get('SW_in korrigiert', None)
        SW_out = df_rad.get('SW_out korrigiert', None)
        LW_in = df_rad.get('LW_in_Avg [W/m^2]', None)
        LW_out = df_rad.get('LW_out_Avg [W/m^2]', None)
    else:
        SW_in = df_rad.get('SW_IN', df_rad.get('SR_in_Avg', None))
        SW_out = df_rad.get('SW_OUT', df_rad.get('SR_out_Avg', None))
        LW_in = df_rad.get('LW_IN', df_rad.get('IR_in_Avg', None))
        LW_out = df_rad.get('LW_OUT', df_rad.get('IR_out_Avg', None))

    if all([SW_in is not None, SW_out is not None, LW_in is not None, LW_out is not None]):
        Rn = SW_in - SW_out + LW_in - LW_out
        print(f"✓ Calculated Rn: {Rn.notna().sum()} values")
    else:
        Rn = None
else:
    Rn = None

# Get LE and H from EddyPro
if df_eddypro is not None:
    if STATION in ['Kayoro', 'Nazinga', 'Sumbrungu']:
        LE = df_eddypro.get('LvE', df_eddypro.get('LE', None))
        H = df_eddypro.get('HTs', df_eddypro.get('H', None))
    else:
        LE = df_eddypro.get('LE', None)
        H = df_eddypro.get('H', None)

    if LE is not None:
        LE = pd.to_numeric(LE, errors='coerce')
    if H is not None:
        H = pd.to_numeric(H, errors='coerce')

    # Filter by quality flags
    if STATION in ['Kayoro', 'Nazinga', 'Sumbrungu']:
        if LE is not None and 'Flag(LvE)' in df_eddypro.columns:
            flag_le = pd.to_numeric(df_eddypro['Flag(LvE)'], errors='coerce')
            high_quality_mask = (flag_le <= 1) & (flag_le.notna())
            LE = LE[high_quality_mask]
        if H is not None and 'Flag(HTs)' in df_eddypro.columns:
            flag_h = pd.to_numeric(df_eddypro['Flag(HTs)'], errors='coerce')
            high_quality_mask = (flag_h <= 1) & (flag_h.notna())
            H = H[high_quality_mask]
    else:
        if LE is not None and 'qc_LE' in df_eddypro.columns:
            LE = filter_quality_flags(df_eddypro, 'qc_LE', max_flag=1, data_column='LE')
        if H is not None and 'qc_H' in df_eddypro.columns:
            H = filter_quality_flags(df_eddypro, 'qc_H', max_flag=1, data_column='H')

    # Filter LE > -200
    if LE is not None:
        LE = LE[LE > -200]

    print(f"✓ LE: {LE.notna().sum() if LE is not None else 0} values")
    print(f"✓ H: {H.notna().sum() if H is not None else 0} values")
else:
    LE = None
    H = None

# Calculate G (soil heat flux)
G = None
if df_cr1000 is not None and len(df_cr1000.columns) > 0:
    print(f"\nCalculating G for station: {STATION}")
    G = calculate_soil_heat_flux(
        df_cr1000,
        station=STATION,
        return_components=False
    )
    if G is not None:
        print(f"  ✓ Calculated G: {len(G)} values")
        print(f"  ✓ G range: {G.min():.1f} to {G.max():.1f} W/m²")
else:
    print("\n⚠️  Cannot calculate G - no soil data available")

# Delta (storage change) - set to zero if not available
Delta = pd.Series(0, index=G.index) if G is not None else None

# ============================================================================
# CROSS-CORRELATION ANALYSIS
# ============================================================================
print("\n" + "=" * 60)
print("Cross-Correlation Analysis")
print("=" * 60)

if Rn is not None and LE is not None and H is not None:
    # Slice to date range
    Rn_sliced = safe_slice(Rn, START_DATE, END_DATE)
    LE_sliced = safe_slice(LE, START_DATE, END_DATE)
    H_sliced = safe_slice(H, START_DATE, END_DATE)

    # Calculate LE + H
    LE_H = LE_sliced + H_sliced

    # Resample to common frequency (30 minutes)
    freq = '30min'
    Rn_resampled = Rn_sliced.resample(freq).mean()
    LE_H_resampled = LE_H.resample(freq).mean()

    # Find common timestamps
    common_idx = Rn_resampled.index.intersection(LE_H_resampled.index)
    Rn_aligned = Rn_resampled.loc[common_idx].dropna()
    LE_H_aligned = LE_H_resampled.loc[common_idx].dropna()

    # Find common timestamps where both have data
    common_idx_final = Rn_aligned.index.intersection(LE_H_aligned.index)
    Rn_final = Rn_aligned.loc[common_idx_final]
    LE_H_final = LE_H_aligned.loc[common_idx_final]

    print(f"✓ Aligned data: {len(Rn_final)} timestamps")
    print(f"  Rn range: {Rn_final.min():.1f} to {Rn_final.max():.1f} W/m²")
    print(f"  LE+H range: {LE_H_final.min():.1f} to {LE_H_final.max():.1f} W/m²")

    if len(Rn_final) > 10:
        # Calculate cross-correlation
        # Maximum lag: ±12 hours (24 * 30-minute intervals)
        max_lag = 24

        # Use scipy.signal.correlate for cross-correlation
        # Normalize the data
        Rn_norm = (Rn_final - Rn_final.mean()) / Rn_final.std()
        LE_H_norm = (LE_H_final - LE_H_final.mean()) / LE_H_final.std()

        # Remove NaN values
        valid_mask = Rn_norm.notna() & LE_H_norm.notna()
        Rn_clean = Rn_norm[valid_mask].values
        LE_H_clean = LE_H_norm[valid_mask].values

        if len(Rn_clean) > max_lag * 2:
            # Calculate cross-correlation
            correlation = signal.correlate(Rn_clean, LE_H_clean, mode='full')
            lags = signal.correlation_lags(len(Rn_clean), len(LE_H_clean), mode='full')

            # Normalize correlation
            correlation = correlation / (len(Rn_clean) * Rn_clean.std() * LE_H_clean.std())

            # Find lag range (±max_lag)
            lag_mask = (lags >= -max_lag) & (lags <= max_lag)
            lags_filtered = lags[lag_mask]
            correlation_filtered = correlation[lag_mask]

            # Find maximum correlation
            max_corr_idx = np.argmax(np.abs(correlation_filtered))
            max_lag_value = lags_filtered[max_corr_idx]
            max_corr_value = correlation_filtered[max_corr_idx]

            print(f"\n✓ Cross-correlation results:")
            print(f"  Maximum correlation: {max_corr_value:.4f}")
            print(f"  Lag at maximum: {max_lag_value} intervals ({max_lag_value * 30} minutes)")

            if max_lag_value != 0:
                print(f"\n⚠️  ALIGNMENT PROBLEM DETECTED!")
                print(f"   Maximum correlation occurs at lag {max_lag_value} ({max_lag_value * 30} minutes)")
                if max_lag_value > 0:
                    print(f"   → LE+H is shifted {abs(max_lag_value * 30)} minutes AHEAD of Rn")
                else:
                    print(f"   → LE+H is shifted {abs(max_lag_value * 30)} minutes BEHIND Rn")
            else:
                print(f"\n✓ No alignment problem detected (maximum at lag 0)")

            # Calculate correlation at lag 0
            corr_at_zero = correlation_filtered[lags_filtered == 0][0]
            print(f"  Correlation at lag 0: {corr_at_zero:.4f}")

            # ============================================================================
            # CREATE PLOTS
            # ============================================================================
            print("\n" + "=" * 60)
            print("Creating Plots")
            print("=" * 60)

            # Plot 1: Cross-correlation function
            fig1, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))

            # Cross-correlation plot
            ax1.plot(lags_filtered * 30, correlation_filtered, 'b-', linewidth=2, label='Cross-correlation')
            ax1.axvline(x=max_lag_value * 30, color='r', linestyle='--', linewidth=2,
                       label=f'Maximum at lag {max_lag_value * 30} min')
            ax1.axvline(x=0, color='k', linestyle=':', linewidth=1, alpha=0.5, label='Lag 0')
            ax1.set_xlabel('Lag (minutes)', fontsize=12)
            ax1.set_ylabel('Cross-correlation', fontsize=12)
            ax1.set_title(f'Cross-Correlation: Rn vs (LE+H) - {STATION}', fontsize=14, fontweight='bold')
            ax1.grid(True, alpha=0.3)
            ax1.legend(fontsize=10)
            ax1.set_xlim(-max_lag * 30, max_lag * 30)

            # Scatter plot at optimal lag
            if max_lag_value != 0:
                # Shift LE+H by optimal lag
                if max_lag_value > 0:
                    # LE+H is ahead, shift it back
                    LE_H_shifted = LE_H_final.shift(-max_lag_value)
                else:
                    # LE+H is behind, shift it forward
                    LE_H_shifted = LE_H_final.shift(-max_lag_value)

                # Align again
                common_shifted = Rn_final.index.intersection(LE_H_shifted.index)
                Rn_plot = Rn_final.loc[common_shifted].dropna()
                LE_H_plot = LE_H_shifted.loc[common_shifted].dropna()
                common_final = Rn_plot.index.intersection(LE_H_plot.index)
                Rn_plot = Rn_plot.loc[common_final]
                LE_H_plot = LE_H_plot.loc[common_final]
            else:
                Rn_plot = Rn_final
                LE_H_plot = LE_H_final

            # Scatter plot
            ax2.scatter(Rn_plot, LE_H_plot, alpha=0.5, s=20, edgecolors='none')

            # Calculate correlation after alignment
            if len(Rn_plot) > 1:
                corr_aligned, _ = pearsonr(Rn_plot.dropna(), LE_H_plot.dropna())
                ax2.text(0.05, 0.95, f'Correlation: {corr_aligned:.3f}',
                        transform=ax2.transAxes, fontsize=12,
                        verticalalignment='top',
                        bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

            # 1:1 line
            min_val = min(Rn_plot.min(), LE_H_plot.min())
            max_val = max(Rn_plot.max(), LE_H_plot.max())
            ax2.plot([min_val, max_val], [min_val, max_val], 'r--', linewidth=1.5, label='1:1 line')

            ax2.set_xlabel('Rn (W/m²)', fontsize=12)
            ax2.set_ylabel('LE + H (W/m²)', fontsize=12)
            if max_lag_value != 0:
                ax2.set_title(f'Rn vs (LE+H) - Aligned at lag {max_lag_value * 30} min',
                             fontsize=13, fontweight='bold')
            else:
                ax2.set_title('Rn vs (LE+H) - Original alignment', fontsize=13, fontweight='bold')
            ax2.grid(True, alpha=0.3)
            ax2.legend(fontsize=10)

            plt.tight_layout()
            fig1.savefig(PLOTS_DIR / f'{STATION}_cross_correlation_alignment.png', dpi=300, bbox_inches='tight')
            print(f"✓ Plot saved: {PLOTS_DIR.name}/{STATION}_cross_correlation_alignment.png")

            # Plot 2: Time series comparison (interactive with Plotly)
            if PLOTLY_AVAILABLE:
                # Create interactive subplots
                fig2 = make_subplots(
                    rows=3, cols=1,
                    shared_xaxes=True,
                    vertical_spacing=0.08,
                    subplot_titles=('Rn', 'LE + H', 'Residual'),
                    row_heights=[0.35, 0.35, 0.30]
                )

                # Rn
                fig2.add_trace(
                    go.Scatter(
                        x=Rn_final.index,
                        y=Rn_final.values,
                        mode='lines',
                        name='Rn',
                        line=dict(color='blue', width=1.5),
                        hovertemplate='Rn: %{y:.1f} W/m²<extra></extra>'
                    ),
                    row=1, col=1
                )
                fig2.add_hline(y=0, line_dash="dash", line_color="black", opacity=0.5, row=1, col=1)
                fig2.update_yaxes(title_text="Rn (W/m²)", range=[-300, 800], row=1, col=1)

                # LE+H original
                fig2.add_trace(
                    go.Scatter(
                        x=LE_H_final.index,
                        y=LE_H_final.values,
                        mode='lines',
                        name='LE+H (original)',
                        line=dict(color='red', width=1.5),
                        hovertemplate='LE+H: %{y:.1f} W/m²<extra></extra>'
                    ),
                    row=2, col=1
                )

                if max_lag_value != 0:
                    LE_H_shifted_ts = LE_H_final.shift(-max_lag_value)
                    fig2.add_trace(
                        go.Scatter(
                            x=LE_H_shifted_ts.index,
                            y=LE_H_shifted_ts.values,
                            mode='lines',
                            name=f'LE+H (shifted by {-max_lag_value * 30} min)',
                            line=dict(color='green', width=1.5, dash='dash'),
                            hovertemplate='LE+H (shifted): %{y:.1f} W/m²<extra></extra>'
                        ),
                        row=2, col=1
                    )

                fig2.add_hline(y=0, line_dash="dash", line_color="black", opacity=0.5, row=2, col=1)
                fig2.update_yaxes(title_text="LE + H (W/m²)", range=[-300, 800], row=2, col=1)

                # Difference/Residual
                if max_lag_value != 0:
                    LE_H_shifted_diff = LE_H_final.shift(-max_lag_value)
                    common_diff = Rn_final.index.intersection(LE_H_shifted_diff.index)
                    diff = Rn_final.loc[common_diff] - LE_H_shifted_diff.loc[common_diff]
                    diff_title = 'Residual after alignment'
                else:
                    diff = Rn_final - LE_H_final
                    diff_title = 'Residual'

                fig2.add_trace(
                    go.Scatter(
                        x=diff.index,
                        y=diff.values,
                        mode='lines',
                        name='Residual',
                        line=dict(color='purple', width=1.5),
                        hovertemplate='Residual: %{y:.1f} W/m²<extra></extra>'
                    ),
                    row=3, col=1
                )
                fig2.add_hline(y=0, line_dash="dash", line_color="black", opacity=0.5, row=3, col=1)
                fig2.update_yaxes(title_text="Rn - (LE+H) (W/m²)", row=3, col=1)

                # Update layout
                fig2.update_layout(
                    title=dict(
                        text=f'Time Series Comparison - {STATION}',
                        x=0.5,
                        font=dict(size=16, color='black')
                    ),
                    height=800,
                    showlegend=True,
                    hovermode='x unified',
                    xaxis_title="Date",
                    template='plotly_white'
                )

                # Save as HTML
                html_file = PLOTS_DIR / f'{STATION}_time_series_alignment_interactive.html'
                fig2.write_html(html_file)
                print(f"✓ Interactive plot saved: {PLOTS_DIR.name}/{html_file.name}")

                # Also create static version with matplotlib
                fig2_static, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

                # Rn
                axes[0].plot(Rn_final.index, Rn_final, 'b-', linewidth=1.5, label='Rn', alpha=0.7)
                axes[0].set_ylabel('Rn (W/m²)', fontsize=12)
                axes[0].set_title(f'Time Series Comparison - {STATION}', fontsize=14, fontweight='bold')
                axes[0].set_ylim(-300, 800)
                axes[0].grid(True, alpha=0.3)
                axes[0].axhline(y=0, color='k', linestyle='--', linewidth=0.5)
                axes[0].legend(fontsize=10)

                # LE+H original
                axes[1].plot(LE_H_final.index, LE_H_final, 'r-', linewidth=1.5, label='LE+H (original)', alpha=0.7)
                if max_lag_value != 0:
                    LE_H_shifted_ts = LE_H_final.shift(-max_lag_value)
                    axes[1].plot(LE_H_shifted_ts.index, LE_H_shifted_ts, 'g--', linewidth=1.5,
                               label=f'LE+H (shifted by {-max_lag_value * 30} min)', alpha=0.7)
                axes[1].set_ylabel('LE + H (W/m²)', fontsize=12)
                axes[1].set_ylim(-300, 800)
                axes[1].grid(True, alpha=0.3)
                axes[1].axhline(y=0, color='k', linestyle='--', linewidth=0.5)
                axes[1].legend(fontsize=10)

                # Difference
                axes[2].plot(diff.index, diff, 'purple', linewidth=1.5, alpha=0.7)
                axes[2].set_ylabel('Rn - (LE+H) (W/m²)', fontsize=12)
                axes[2].set_title(diff_title, fontsize=12)
                axes[2].grid(True, alpha=0.3)
                axes[2].axhline(y=0, color='k', linestyle='--', linewidth=0.5)
                axes[2].set_xlabel('Date', fontsize=12)

                plt.tight_layout()
                fig2_static.savefig(PLOTS_DIR / f'{STATION}_time_series_alignment.png', dpi=300, bbox_inches='tight')
                print(f"✓ Static plot saved: {PLOTS_DIR.name}/{STATION}_time_series_alignment.png")

                # Additional Plot 3: Rn and LE+H in same window
                fig3 = make_subplots(
                    rows=1, cols=1,
                    subplot_titles=('Rn vs LE+H')
                )

                fig3.add_trace(
                    go.Scatter(
                        x=Rn_final.index,
                        y=Rn_final.values,
                        mode='lines',
                        name='Rn',
                        line=dict(color='blue', width=1.5),
                        hovertemplate='Rn: %{y:.1f} W/m²<extra></extra>'
                    )
                )
                fig3.add_trace(
                    go.Scatter(
                        x=LE_H_final.index,
                        y=LE_H_final.values,
                        mode='lines',
                        name='LE+H (original)',
                        line=dict(color='red', width=1.5),
                        hovertemplate='LE+H: %{y:.1f} W/m²<extra></extra>'
                    )
                )
                fig3.add_hline(y=0, line_dash="dash", line_color="black", opacity=0.5)
                fig3.update_yaxes(title_text="Flux (W/m²)", range=[-300, 800])
                fig3.update_layout(
                    title=dict(
                        text=f'Rn vs LE+H - {STATION}',
                        x=0.5,
                        font=dict(size=16, color='black')
                    ),
                    height=500,
                    showlegend=True,
                    hovermode='x unified',
                    xaxis_title="Date",
                    template='plotly_white'
                )
                html_file3 = PLOTS_DIR / f'{STATION}_Rn_vs_LEH.html'
                fig3.write_html(html_file3)
                print(f"✓ Interactive plot saved: {PLOTS_DIR.name}/{html_file3.name}")

                # Static version
                fig3_static, ax3 = plt.subplots(1, 1, figsize=(14, 6))
                ax3.plot(Rn_final.index, Rn_final, 'b-', linewidth=1.5, label='Rn', alpha=0.7)
                ax3.plot(LE_H_final.index, LE_H_final, 'r-', linewidth=1.5, label='LE+H (original)', alpha=0.7)
                ax3.set_ylabel('Flux (W/m²)', fontsize=12)
                ax3.set_xlabel('Date', fontsize=12)
                ax3.set_title(f'Rn vs LE+H - {STATION}', fontsize=14, fontweight='bold')
                ax3.set_ylim(-300, 800)
                ax3.grid(True, alpha=0.3)
                ax3.axhline(y=0, color='k', linestyle='--', linewidth=0.5)
                ax3.legend(fontsize=10)
                plt.tight_layout()
                fig3_static.savefig(PLOTS_DIR / f'{STATION}_Rn_vs_LEH.png', dpi=300, bbox_inches='tight')
                print(f"✓ Static plot saved: {PLOTS_DIR.name}/{STATION}_Rn_vs_LEH.png")

                # Additional Plot 4: Rn and LE+H (shifted) in same window
                if max_lag_value != 0:
                    LE_H_shifted_plot = LE_H_final.shift(-max_lag_value)
                    common_shifted_plot = Rn_final.index.intersection(LE_H_shifted_plot.index)
                    Rn_plot_shifted = Rn_final.loc[common_shifted_plot].dropna()
                    LE_H_plot_shifted = LE_H_shifted_plot.loc[common_shifted_plot].dropna()
                    common_final_shifted = Rn_plot_shifted.index.intersection(LE_H_plot_shifted.index)
                    Rn_plot_shifted = Rn_plot_shifted.loc[common_final_shifted]
                    LE_H_plot_shifted = LE_H_plot_shifted.loc[common_final_shifted]

                    fig4 = make_subplots(
                        rows=1, cols=1,
                        subplot_titles=(f'Rn vs LE+H (shifted by {-max_lag_value * 30} min)')
                    )

                    fig4.add_trace(
                        go.Scatter(
                            x=Rn_plot_shifted.index,
                            y=Rn_plot_shifted.values,
                            mode='lines',
                            name='Rn',
                            line=dict(color='blue', width=1.5),
                            hovertemplate='Rn: %{y:.1f} W/m²<extra></extra>'
                        )
                    )
                    fig4.add_trace(
                        go.Scatter(
                            x=LE_H_plot_shifted.index,
                            y=LE_H_plot_shifted.values,
                            mode='lines',
                            name=f'LE+H (shifted by {-max_lag_value * 30} min)',
                            line=dict(color='green', width=1.5, dash='dash'),
                            hovertemplate='LE+H (shifted): %{y:.1f} W/m²<extra></extra>'
                        )
                    )
                    fig4.add_hline(y=0, line_dash="dash", line_color="black", opacity=0.5)
                    fig4.update_yaxes(title_text="Flux (W/m²)", range=[-300, 800])
                    fig4.update_layout(
                        title=dict(
                            text=f'Rn vs LE+H (Aligned) - {STATION}',
                            x=0.5,
                            font=dict(size=16, color='black')
                        ),
                        height=500,
                        showlegend=True,
                        hovermode='x unified',
                        xaxis_title="Date",
                        template='plotly_white'
                    )
                    html_file4 = PLOTS_DIR / f'{STATION}_Rn_vs_LEH_shifted.html'
                    fig4.write_html(html_file4)
                    print(f"✓ Interactive plot saved: {PLOTS_DIR.name}/{html_file4.name}")

                    # Static version
                    fig4_static, ax4 = plt.subplots(1, 1, figsize=(14, 6))
                    ax4.plot(Rn_plot_shifted.index, Rn_plot_shifted, 'b-', linewidth=1.5, label='Rn', alpha=0.7)
                    ax4.plot(LE_H_plot_shifted.index, LE_H_plot_shifted, 'g--', linewidth=1.5,
                            label=f'LE+H (shifted by {-max_lag_value * 30} min)', alpha=0.7)
                    ax4.set_ylabel('Flux (W/m²)', fontsize=12)
                    ax4.set_xlabel('Date', fontsize=12)
                    ax4.set_title(f'Rn vs LE+H (Aligned) - {STATION}', fontsize=14, fontweight='bold')
                    ax4.set_ylim(-300, 800)
                    ax4.grid(True, alpha=0.3)
                    ax4.axhline(y=0, color='k', linestyle='--', linewidth=0.5)
                    ax4.legend(fontsize=10)
                    plt.tight_layout()
                    fig4_static.savefig(PLOTS_DIR / f'{STATION}_Rn_vs_LEH_shifted.png', dpi=300, bbox_inches='tight')
                    print(f"✓ Static plot saved: {PLOTS_DIR.name}/{STATION}_Rn_vs_LEH_shifted.png")
                else:
                    print("  ⚠️  Skipping shifted plot (no alignment needed, lag = 0)")
            else:
                # Fallback to matplotlib if Plotly not available
                fig2, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

                # Rn
                axes[0].plot(Rn_final.index, Rn_final, 'b-', linewidth=1.5, label='Rn', alpha=0.7)
                axes[0].set_ylabel('Rn (W/m²)', fontsize=12)
                axes[0].set_title(f'Time Series Comparison - {STATION}', fontsize=14, fontweight='bold')
                axes[0].set_ylim(-300, 800)
                axes[0].grid(True, alpha=0.3)
                axes[0].axhline(y=0, color='k', linestyle='--', linewidth=0.5)
                axes[0].legend(fontsize=10)

                # LE+H original
                axes[1].plot(LE_H_final.index, LE_H_final, 'r-', linewidth=1.5, label='LE+H (original)', alpha=0.7)
                if max_lag_value != 0:
                    LE_H_shifted_ts = LE_H_final.shift(-max_lag_value)
                    axes[1].plot(LE_H_shifted_ts.index, LE_H_shifted_ts, 'g--', linewidth=1.5,
                               label=f'LE+H (shifted by {-max_lag_value * 30} min)', alpha=0.7)
                axes[1].set_ylabel('LE + H (W/m²)', fontsize=12)
                axes[1].set_ylim(-300, 800)
                axes[1].grid(True, alpha=0.3)
                axes[1].axhline(y=0, color='k', linestyle='--', linewidth=0.5)
                axes[1].legend(fontsize=10)

                # Difference
                if max_lag_value != 0:
                    LE_H_shifted_diff = LE_H_final.shift(-max_lag_value)
                    common_diff = Rn_final.index.intersection(LE_H_shifted_diff.index)
                    diff = Rn_final.loc[common_diff] - LE_H_shifted_diff.loc[common_diff]
                    axes[2].plot(diff.index, diff, 'purple', linewidth=1.5, alpha=0.7)
                    axes[2].set_ylabel('Rn - (LE+H) (W/m²)', fontsize=12)
                    axes[2].set_title('Residual after alignment', fontsize=12)
                else:
                    diff = Rn_final - LE_H_final
                    axes[2].plot(diff.index, diff, 'purple', linewidth=1.5, alpha=0.7)
                    axes[2].set_ylabel('Rn - (LE+H) (W/m²)', fontsize=12)
                    axes[2].set_title('Residual', fontsize=12)

                axes[2].grid(True, alpha=0.3)
                axes[2].axhline(y=0, color='k', linestyle='--', linewidth=0.5)
                axes[2].set_xlabel('Date', fontsize=12)

                plt.tight_layout()
                fig2.savefig(PLOTS_DIR / f'{STATION}_time_series_alignment.png', dpi=300, bbox_inches='tight')
                print(f"✓ Plot saved: {PLOTS_DIR.name}/{STATION}_time_series_alignment.png")

                # Additional Plot 3: Rn and LE+H in same window (matplotlib fallback)
                fig3_static, ax3 = plt.subplots(1, 1, figsize=(14, 6))
                ax3.plot(Rn_final.index, Rn_final, 'b-', linewidth=1.5, label='Rn', alpha=0.7)
                ax3.plot(LE_H_final.index, LE_H_final, 'r-', linewidth=1.5, label='LE+H (original)', alpha=0.7)
                ax3.set_ylabel('Flux (W/m²)', fontsize=12)
                ax3.set_xlabel('Date', fontsize=12)
                ax3.set_title(f'Rn vs LE+H - {STATION}', fontsize=14, fontweight='bold')
                ax3.set_ylim(-300, 800)
                ax3.grid(True, alpha=0.3)
                ax3.axhline(y=0, color='k', linestyle='--', linewidth=0.5)
                ax3.legend(fontsize=10)
                plt.tight_layout()
                fig3_static.savefig(PLOTS_DIR / f'{STATION}_Rn_vs_LEH.png', dpi=300, bbox_inches='tight')
                print(f"✓ Static plot saved: {PLOTS_DIR.name}/{STATION}_Rn_vs_LEH.png")

                # Additional Plot 4: Rn and LE+H (shifted) in same window (matplotlib fallback)
                if max_lag_value != 0:
                    LE_H_shifted_plot = LE_H_final.shift(-max_lag_value)
                    common_shifted_plot = Rn_final.index.intersection(LE_H_shifted_plot.index)
                    Rn_plot_shifted = Rn_final.loc[common_shifted_plot].dropna()
                    LE_H_plot_shifted = LE_H_shifted_plot.loc[common_shifted_plot].dropna()
                    common_final_shifted = Rn_plot_shifted.index.intersection(LE_H_plot_shifted.index)
                    Rn_plot_shifted = Rn_plot_shifted.loc[common_final_shifted]
                    LE_H_plot_shifted = LE_H_plot_shifted.loc[common_final_shifted]

                    fig4_static, ax4 = plt.subplots(1, 1, figsize=(14, 6))
                    ax4.plot(Rn_plot_shifted.index, Rn_plot_shifted, 'b-', linewidth=1.5, label='Rn', alpha=0.7)
                    ax4.plot(LE_H_plot_shifted.index, LE_H_plot_shifted, 'g--', linewidth=1.5,
                            label=f'LE+H (shifted by {-max_lag_value * 30} min)', alpha=0.7)
                    ax4.set_ylabel('Flux (W/m²)', fontsize=12)
                    ax4.set_xlabel('Date', fontsize=12)
                    ax4.set_title(f'Rn vs LE+H (Aligned) - {STATION}', fontsize=14, fontweight='bold')
                    ax4.set_ylim(-300, 800)
                    ax4.grid(True, alpha=0.3)
                    ax4.axhline(y=0, color='k', linestyle='--', linewidth=0.5)
                    ax4.legend(fontsize=10)
                    plt.tight_layout()
                    fig4_static.savefig(PLOTS_DIR / f'{STATION}_Rn_vs_LEH_shifted.png', dpi=300, bbox_inches='tight')
                    print(f"✓ Static plot saved: {PLOTS_DIR.name}/{STATION}_Rn_vs_LEH_shifted.png")
                else:
                    print("  ⚠️  Skipping shifted plot (no alignment needed, lag = 0)")

            # ============================================================================
            # INTERACTIVE PLOT: TK3 vs EddyPro (with shift option)
            # ============================================================================
            # This plot works for Dragan stations (Kayoro, Nazinga, Sumbrungu) and Gorigo
            # IMPORTANT: TK3 fluxes are NEVER shifted - only EddyPro fluxes are shifted
            if LvE_dragan is not None and HTs_dragan is not None:
                print("\nCreating interactive TK3 vs EddyPro plot...")
                freq = '30min'
                # Prepare TK3 LE+H (NOT shifted - TK3 fluxes are always used as-is)
                LE_H_tk3 = (safe_slice(LvE_dragan, START_DATE, END_DATE) + safe_slice(HTs_dragan, START_DATE, END_DATE)).resample(freq).mean()
                # EddyPro LE+H already resampled (LE_H_final)
                # Note: Only EddyPro fluxes are shifted in the panels below, TK3 remains unchanged
                LE_H_eddy = LE_H_final
                # Align indices
                common_tk3 = LE_H_tk3.index.intersection(LE_H_eddy.index)
                LE_H_tk3 = LE_H_tk3.loc[common_tk3].dropna()
                LE_H_eddy = LE_H_eddy.loc[common_tk3].dropna()

                if PLOTLY_AVAILABLE:
                    fig_tk3 = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                                            subplot_titles=('LE+H TK3 vs EddyPro (no shift)',
                                                            'LE+H TK3 vs EddyPro (EddyPro shifted +30 min)',
                                                            'LE+H TK3 vs EddyPro (EddyPro shifted +60 min)'))
                    # Panel 1: no shift
                    fig_tk3.add_trace(go.Scatter(x=LE_H_tk3.index, y=LE_H_tk3.values,
                                                 mode='lines', name='LE+H (TK3)', line=dict(color='green')),
                                      row=1, col=1)
                    fig_tk3.add_trace(go.Scatter(x=LE_H_eddy.index, y=LE_H_eddy.values,
                                                 mode='lines', name='LE+H (EddyPro)', line=dict(color='blue', dash='dash')),
                                      row=1, col=1)
                    fig_tk3.update_yaxes(title_text='LE+H (W/m²)', range=[-300, 800], row=1, col=1)

                    # Panel 2: EddyPro shifted +30 min (shift -1 interval)
                    LE_H_eddy_shift30 = LE_H_eddy.shift(-1)
                    common_shift30 = LE_H_tk3.index.intersection(LE_H_eddy_shift30.index)
                    fig_tk3.add_trace(go.Scatter(x=LE_H_tk3.loc[common_shift30].index, y=LE_H_tk3.loc[common_shift30].values,
                                                 mode='lines', name='LE+H (TK3)', line=dict(color='green')),
                                      row=2, col=1)
                    fig_tk3.add_trace(go.Scatter(x=LE_H_eddy_shift30.loc[common_shift30].index, y=LE_H_eddy_shift30.loc[common_shift30].values,
                                                 mode='lines', name='LE+H (EddyPro, +30 min)', line=dict(color='orange', dash='dash')),
                                      row=2, col=1)
                    fig_tk3.update_yaxes(title_text='LE+H (W/m²)', range=[-300, 800], row=2, col=1)

                    # Panel 3: EddyPro shifted +60 min (shift -2 intervals)
                    LE_H_eddy_shift60 = LE_H_eddy.shift(-2)
                    common_shift60 = LE_H_tk3.index.intersection(LE_H_eddy_shift60.index)
                    fig_tk3.add_trace(go.Scatter(x=LE_H_tk3.loc[common_shift60].index, y=LE_H_tk3.loc[common_shift60].values,
                                                 mode='lines', name='LE+H (TK3)', line=dict(color='green')),
                                      row=3, col=1)
                    fig_tk3.add_trace(go.Scatter(x=LE_H_eddy_shift60.loc[common_shift60].index, y=LE_H_eddy_shift60.loc[common_shift60].values,
                                                 mode='lines', name='LE+H (EddyPro, +60 min)', line=dict(color='blue', dash='dash')),
                                      row=3, col=1)
                    fig_tk3.update_yaxes(title_text='LE+H (W/m²)', range=[-300, 800], row=3, col=1)
                    fig_tk3.update_xaxes(title_text='Date', row=3, col=1)
                    fig_tk3.update_layout(title=dict(text=f'TK3 vs EddyPro LE+H - {STATION}', x=0.5, font=dict(size=16)),
                                          height=950, hovermode='x unified', template='plotly_white')
                    html_tk3 = PLOTS_DIR / f'{STATION}_TK3_vs_EddyPro_LEH.html'
                    fig_tk3.write_html(html_tk3)
                    print(f"✓ Interactive plot saved: {PLOTS_DIR.name}/{html_tk3.name}")
                else:
                    # Static fallback
                    fig_tk3, axes_tk3 = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
                    axes_tk3[0].plot(LE_H_tk3.index, LE_H_tk3, 'g-', label='LE+H (TK3)', alpha=0.7)
                    axes_tk3[0].plot(LE_H_eddy.index, LE_H_eddy, 'b--', label='LE+H (EddyPro)', alpha=0.7)
                    axes_tk3[0].set_ylabel('LE+H (W/m²)')
                    axes_tk3[0].set_ylim(-300, 800)
                    axes_tk3[0].set_title(f'TK3 vs EddyPro LE+H - {STATION}', fontsize=13, fontweight='bold')
                    axes_tk3[0].grid(True, alpha=0.3)
                    axes_tk3[0].axhline(y=0, color='k', linestyle='--', linewidth=0.5)
                    axes_tk3[0].legend()

                    # +30 min shift
                    LE_H_eddy_shift30 = LE_H_eddy.shift(-1)
                    common_shift30 = LE_H_tk3.index.intersection(LE_H_eddy_shift30.index)
                    axes_tk3[1].plot(LE_H_tk3.loc[common_shift30].index, LE_H_tk3.loc[common_shift30], 'g-', label='LE+H (TK3)', alpha=0.7)
                    axes_tk3[1].plot(LE_H_eddy_shift30.loc[common_shift30].index, LE_H_eddy_shift30.loc[common_shift30], 'orange',
                                     label='LE+H (EddyPro, +30 min)', alpha=0.7)
                    axes_tk3[1].set_ylabel('LE+H (W/m²)')
                    axes_tk3[1].set_ylim(-300, 800)
                    axes_tk3[1].grid(True, alpha=0.3)
                    axes_tk3[1].axhline(y=0, color='k', linestyle='--', linewidth=0.5)
                    axes_tk3[1].legend()

                    # +60 min shift
                    LE_H_eddy_shift60 = LE_H_eddy.shift(-2)
                    common_shift60 = LE_H_tk3.index.intersection(LE_H_eddy_shift60.index)
                    axes_tk3[2].plot(LE_H_tk3.loc[common_shift60].index, LE_H_tk3.loc[common_shift60], 'g-', label='LE+H (TK3)', alpha=0.7)
                    axes_tk3[2].plot(LE_H_eddy_shift60.loc[common_shift60].index, LE_H_eddy_shift60.loc[common_shift60], 'b--',
                                     label='LE+H (EddyPro, +60 min)', alpha=0.7)
                    axes_tk3[2].set_ylabel('LE+H (W/m²)')
                    axes_tk3[2].set_xlabel('Date')
                    axes_tk3[2].set_ylim(-300, 800)
                    axes_tk3[2].grid(True, alpha=0.3)
                    axes_tk3[2].axhline(y=0, color='k', linestyle='--', linewidth=0.5)
                    axes_tk3[2].legend()
                    plt.tight_layout()
                    fig_tk3.savefig(PLOTS_DIR / f'{STATION}_TK3_vs_EddyPro_LEH.png', dpi=300, bbox_inches='tight')
                    print(f"✓ Static plot saved: {PLOTS_DIR.name}/{STATION}_TK3_vs_EddyPro_LEH.png")

            # ============================================================================
            # EBC-STYLE COMPARISON WITH SHIFTS
            # ============================================================================
            if G is not None:
                print("\n" + "=" * 60)
                print("EBC-Style Comparison with Shifts")
                print("=" * 60)

                # Prepare data exactly as in EBC plot
                # Resample all to 30-minute intervals
                freq = '30min'
                Rn_ebc = Rn_sliced.resample(freq).mean()
                G_ebc = safe_slice(G, START_DATE, END_DATE).resample(freq).mean()
                LE_ebc = LE_sliced.resample(freq).mean()
                H_ebc = H_sliced.resample(freq).mean()

                # Calculate LE + H
                LE_H_ebc = LE_ebc + H_ebc

                # Find common timestamps
                common_ebc = Rn_ebc.index.intersection(G_ebc.index).intersection(LE_H_ebc.index)
                Rn_ebc = Rn_ebc.loc[common_ebc].dropna()
                G_ebc = G_ebc.loc[common_ebc].dropna()
                LE_H_ebc = LE_H_ebc.loc[common_ebc].dropna()

                # Final common index
                common_final_ebc = Rn_ebc.index.intersection(G_ebc.index).intersection(LE_H_ebc.index)
                Rn_ebc = Rn_ebc.loc[common_final_ebc]
                G_ebc = G_ebc.loc[common_final_ebc]
                LE_H_ebc = LE_H_ebc.loc[common_final_ebc]

                # Calculate X-axis: Rn - G - Delta (exactly as in EBC plot)
                x_data = Rn_ebc - G_ebc
                if Delta is not None:
                    Delta_ebc = safe_slice(Delta, START_DATE, END_DATE).resample(freq).mean()
                    Delta_ebc = Delta_ebc.loc[common_final_ebc]
                    # Check if Delta has non-zero values
                    if Delta_ebc.notna().any() and (Delta_ebc != 0).any():
                        x_data = x_data - Delta_ebc

                # Filter to valid range (same as EBC plot)
                valid_mask = (
                    (LE_ebc.loc[common_final_ebc] >= -300) & (LE_ebc.loc[common_final_ebc] <= 800) &
                    (H_ebc.loc[common_final_ebc] >= -300) & (H_ebc.loc[common_final_ebc] <= 800)
                )
                x_data = x_data[valid_mask]
                LE_H_ebc = LE_H_ebc[valid_mask]

                # Filter to daytime only (Rn > 0)
                daytime_mask = Rn_ebc.loc[valid_mask.index] > 0
                x_data_daytime = x_data[daytime_mask]
                LE_H_ebc_daytime = LE_H_ebc[daytime_mask]

                print(f"✓ Prepared EBC data: {len(x_data)} total points, {len(x_data_daytime)} daytime points")

                if len(x_data_daytime) > 10:
                    # Create scatter plots for different shifts (0, +30, +60, +90, -60 min)
                    shifts = [0, 1, 2, 3, -2]  # 0, +30, +60, +90, -60 min (in 30-min intervals)
                    shift_labels = ['No shift', '+30 min', '+60 min', '+90 min', '-60 min']

                    fig_ebc, axes_ebc = plt.subplots(2, 3, figsize=(18, 10))
                    axes_ebc = axes_ebc.flatten()

                    results = []

                    for idx, (shift, label) in enumerate(zip(shifts, shift_labels)):
                        ax = axes_ebc[idx]

                        if shift == 0:
                            y_data = LE_H_ebc_daytime
                            x_plot = x_data_daytime
                        else:
                            # Shift LE+H
                            LE_H_shifted = LE_H_ebc_daytime.shift(-shift)
                            # Align indices
                            common_shifted = x_data_daytime.index.intersection(LE_H_shifted.index)
                            y_data = LE_H_shifted.loc[common_shifted].dropna()
                            x_plot = x_data_daytime.loc[y_data.index]

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
                            ax.set_xlabel('Rn - G (W/m²)', fontsize=12)
                            ax.set_ylabel('LE + H (W/m²)', fontsize=12)
                            ax.set_title(f'{label}\nSlope: {slope:.3f}, R²: {r2:.3f}', fontsize=13, fontweight='bold')
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
                            ax.set_title(label, fontsize=13)

                    for j in range(len(shifts), len(axes_ebc)):
                        axes_ebc[j].set_visible(False)

                    fig_ebc.suptitle(f'Energy Balance Closure Comparison - {STATION} (Daytime only)',
                                    fontsize=14, fontweight='bold')
                    plt.tight_layout(rect=[0, 0.03, 1, 0.96])
                    fig_ebc.savefig(PLOTS_DIR / f'{STATION}_EBC_comparison_shifts.png', dpi=300, bbox_inches='tight')
                    print(f"\n✓ EBC comparison plot saved: {PLOTS_DIR.name}/{STATION}_EBC_comparison_shifts.png")

                    # Print comparison summary
                    if len(results) > 0:
                        print("\n" + "=" * 60)
                        print("Comparison Summary (Daytime only)")
                        print("=" * 60)
                        print(f"{'Shift':<15} {'Slope':<10} {'R²':<10} {'N points':<10}")
                        print("-" * 60)
                        for r in results:
                            print(f"{r['label']:<15} {r['slope']:<10.3f} {r['r2']:<10.3f} {r['n_points']:<10}")

                        # Find best shift (highest R²)
                        best = max(results, key=lambda x: x['r2'])
                        print(f"\n✓ Best alignment: {best['label']} (R²={best['r2']:.3f}, Slope={best['slope']:.3f})")
                else:
                    print("⚠️  Insufficient daytime data for EBC comparison")
            else:
                print("\n⚠️  Skipping EBC comparison (G not available)")

        else:
            print("⚠️  Insufficient data for cross-correlation analysis")
    else:
        print("⚠️  Insufficient data after alignment")
else:
    print("⚠️  Missing required data (Rn, LE, or H)")

print("\n✅ Analysis complete!")
