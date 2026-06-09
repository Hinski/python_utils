#!/usr/bin/env python3
"""
Script to read and display Sensible Heat Flux (H) and Latent Heat Flux (LE) 
time series from EddyPro output CSV files.

Usage:
    python plot_eddypro_fluxes.py <eddypro_output_file.csv>
"""

import sys
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path
import numpy as np


def read_eddypro_file(file_path):
    """
    Read EddyPro output CSV file.
    
    The file has a complex header structure:
    - Row 0: Section headers (file_info, corrected_fluxes_and_quality_flags, etc.)
    - Row 1: Column names
    - Row 2: Units
    - Row 3+: Data rows
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    print(f"📖 Reading EddyPro file: {file_path.name}")
    
    # Read the file, skipping the first row (section headers)
    # Use row 1 (index 1) as column names
    df = pd.read_csv(file_path, skiprows=1, low_memory=False)
    
    # Remove the units row (row 2 in original file, now row 0 after skiprows=1)
    # Check if first row looks like units (contains brackets like [yyyy-mm-dd] or [W+1m-2])
    if len(df) > 0:
        first_cell = str(df.iloc[0, 0]) if pd.notna(df.iloc[0, 0]) else ''
        # Check multiple columns to be sure it's the units row
        is_units_row = False
        if first_cell.startswith('[') or '[' in first_cell:
            is_units_row = True
        elif len(df.columns) > 8:  # Check H column (index 8) for units
            h_col_idx = list(df.columns).index('H') if 'H' in df.columns else None
            if h_col_idx is not None and len(df) > 0:
                h_cell = str(df.iloc[0, h_col_idx]) if pd.notna(df.iloc[0, h_col_idx]) else ''
                if '[' in h_cell or h_cell.startswith('['):
                    is_units_row = True
        
        if is_units_row:
            df = df.iloc[1:].reset_index(drop=True)
            print(f"   Removed units row")
    
    print(f"   Found {len(df)} data rows")
    print(f"   Columns: {len(df.columns)}")
    
    return df


def parse_datetime(df):
    """
    Parse date and time columns into a datetime index.
    """
    # Combine date and time columns
    if 'date' in df.columns and 'time' in df.columns:
        datetime_str = df['date'].astype(str) + ' ' + df['time'].astype(str)
        df['datetime'] = pd.to_datetime(datetime_str, format='%Y-%m-%d %H:%M', errors='coerce')
    elif 'date' in df.columns:
        df['datetime'] = pd.to_datetime(df['date'], errors='coerce')
    else:
        raise ValueError("Could not find 'date' column in the file")
    
    # Set datetime as index
    df = df.set_index('datetime')
    
    # Remove rows with invalid datetime
    invalid_dt = df.index.isna()
    if invalid_dt.sum() > 0:
        print(f"   ⚠️ Warning: {invalid_dt.sum()} rows with invalid datetime removed")
        df = df[~invalid_dt]
    
    return df


def extract_fluxes(df):
    """
    Extract H (sensible heat flux) and LE (latent heat flux) from dataframe.
    Filter out invalid values (typically -9999 or NaN).
    """
    # Check available columns
    print(f"\n📊 Available flux columns:")
    flux_cols = [col for col in df.columns if col in ['H', 'LE', 'ET', 'qc_H', 'qc_LE', 'Tau']]
    for col in flux_cols:
        print(f"   - {col}")
    
    # Extract H (sensible heat flux)
    if 'H' not in df.columns:
        raise ValueError("Column 'H' (sensible heat flux) not found in file")
    
    # Convert to numeric, handling scientific notation (E format)
    H = pd.to_numeric(df['H'], errors='coerce')
    
    # Extract LE (latent heat flux) - try LE first, fall back to ET if needed
    if 'LE' in df.columns:
        LE = pd.to_numeric(df['LE'], errors='coerce')
    elif 'ET' in df.columns:
        # If ET exists but LE doesn't, use ET (assuming it's already in W/m² or will be converted)
        print("   ⚠️ Warning: 'LE' column not found, using 'ET' instead")
        LE = pd.to_numeric(df['ET'], errors='coerce')
    else:
        raise ValueError("Column 'LE' (latent heat flux) not found in file")
    
    # Extract quality flags if available
    qc_H = pd.to_numeric(df['qc_H'], errors='coerce') if 'qc_H' in df.columns else None
    qc_LE = pd.to_numeric(df['qc_LE'], errors='coerce') if 'qc_LE' in df.columns else None
    
    # Filter invalid values (EddyPro uses -9999 for missing/invalid data)
    invalid_mask_H = (H == -9999) | (H.isna())
    invalid_mask_LE = (LE == -9999) | (LE.isna())
    
    # Filter for high quality only (qc <= 1)
    if qc_H is not None:
        high_quality_mask_H = (qc_H <= 1) & (~invalid_mask_H)
    else:
        high_quality_mask_H = ~invalid_mask_H
    
    if qc_LE is not None:
        high_quality_mask_LE = (qc_LE <= 1) & (~invalid_mask_LE)
    else:
        high_quality_mask_LE = ~invalid_mask_LE
    
    H_high_quality = H[high_quality_mask_H].copy()
    LE_high_quality = LE[high_quality_mask_LE].copy()
    
    print(f"\n📈 Data statistics (high quality only, qc <= 1):")
    print(f"   H (sensible heat flux):")
    print(f"      Total values: {len(H)}")
    print(f"      High quality values: {len(H_high_quality)} ({100*len(H_high_quality)/len(H):.1f}%)")
    if len(H_high_quality) > 0:
        print(f"      Mean: {H_high_quality.mean():.2f} W m⁻²")
        print(f"      Std: {H_high_quality.std():.2f} W m⁻²")
        print(f"      Min: {H_high_quality.min():.2f} W m⁻²")
        print(f"      Max: {H_high_quality.max():.2f} W m⁻²")
    else:
        print(f"      ⚠️ No high quality H values found!")
    
    print(f"\n   LE (latent heat flux):")
    print(f"      Total values: {len(LE)}")
    print(f"      High quality values: {len(LE_high_quality)} ({100*len(LE_high_quality)/len(LE):.1f}%)")
    if len(LE_high_quality) > 0:
        print(f"      Mean: {LE_high_quality.mean():.2f} W m⁻²")
        print(f"      Std: {LE_high_quality.std():.2f} W m⁻²")
        print(f"      Min: {LE_high_quality.min():.2f} W m⁻²")
        print(f"      Max: {LE_high_quality.max():.2f} W m⁻²")
    else:
        print(f"      ⚠️ No high quality LE values found!")
    
    return H, LE, qc_H, qc_LE, H_high_quality, LE_high_quality


def plot_fluxes(df, H, LE, H_high_quality, LE_high_quality, qc_H=None, qc_LE=None, output_file=None, input_file=None):
    """
    Plot sensible and latent heat flux time series (high quality only, lines only).
    """
    fig, axes = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
    
    # Plot 1: Sensible Heat Flux (H) - high quality only, lines only
    ax1 = axes[0]
    
    if len(H_high_quality) > 0:
        # Plot only high quality data as lines (no markers)
        ax1.plot(H_high_quality.index, H_high_quality, '-', color='red', linewidth=1.5, 
                 label=f'H (high quality: {len(H_high_quality)})', alpha=0.7)
    else:
        ax1.text(0.5, 0.5, 'No high quality H data available', 
                transform=ax1.transAxes, ha='center', va='center', fontsize=14)
    
    ax1.set_ylabel('Sensible Heat Flux (W m⁻²)', fontsize=12, fontweight='bold')
    ax1.set_title('Sensible Heat Flux (H) Time Series - High Quality Only', fontsize=14, fontweight='bold')
    ax1.set_ylim(-300, 700)
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='best')
    ax1.axhline(y=0, color='black', linestyle='--', linewidth=0.5)
    
    # Plot 2: Latent Heat Flux (LE) - high quality only, lines only
    ax2 = axes[1]
    
    if len(LE_high_quality) > 0:
        # Plot only high quality data as lines (no markers)
        ax2.plot(LE_high_quality.index, LE_high_quality, '-', color='blue', linewidth=1.5,
                 label=f'LE (high quality: {len(LE_high_quality)})', alpha=0.7)
        
        ax2.set_ylabel('Latent Heat Flux (W m⁻²)', fontsize=12, fontweight='bold')
        ax2.set_title('Latent Heat Flux (LE) Time Series - High Quality Only', fontsize=14, fontweight='bold')
    else:
        ax2.text(0.5, 0.5, 'No high quality LE data available', 
                transform=ax2.transAxes, ha='center', va='center', fontsize=14)
        ax2.set_ylabel('Latent Heat Flux (W m⁻²)', fontsize=12, fontweight='bold')
        ax2.set_title('Latent Heat Flux (LE) Time Series - No Data', fontsize=14, fontweight='bold')
    
    ax2.set_ylim(-300, 700)
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='best')
    ax2.axhline(y=0, color='black', linestyle='--', linewidth=0.5)
    
    # Format x-axis
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    ax2.xaxis.set_major_locator(mdates.HourLocator(interval=max(1, len(df)//20)))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    plt.tight_layout()
    
    # Save plot if output file is specified
    if output_file:
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"\n💾 Plot saved to: {output_file}")
    
    # Show interactive plot
    plt.show()
    
    return fig


def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python plot_eddypro_fluxes.py <eddypro_output_file.csv> [output_plot.png]")
        print("\nExample:")
        print("  python plot_eddypro_fluxes.py eddypro_Janga_full_output_2025-12-18T090807_exp.csv")
        print("  python plot_eddypro_fluxes.py eddypro_Janga_full_output_2025-12-18T090807_exp.csv plot.png")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    try:
        # Read file
        df = read_eddypro_file(input_file)
        
        # Parse datetime
        df = parse_datetime(df)
        
        # Extract fluxes
        H, LE, qc_H, qc_LE, H_high_quality, LE_high_quality = extract_fluxes(df)
        
        # Plot
        plot_fluxes(df, H, LE, H_high_quality, LE_high_quality, qc_H, qc_LE, output_file, input_file)
        
        print(f"\n✅ Done!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
