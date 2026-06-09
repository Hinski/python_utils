import sys
from pathlib import Path
import pandas as pd
import shutil
from datetime import datetime

# Configuration
DATA_DIR = Path('/Users/hingerl-l/Data/merged_long')
STATION = 'Nazinga'
RADIATION_FILE = DATA_DIR / f'{STATION}_radiation_merged_long.parquet'
BACKUP_SUFFIX = '_backup_before_lw_fix'
FIX_DATE = '2018-01-01'  # Date from which to swap LW_in and LW_out

def main():
    print("=" * 60)
    print(f"Fixing Longwave Radiation for {STATION}")
    print("=" * 60)

    # Check if file exists
    if not RADIATION_FILE.exists():
        print(f"❌ Error: File not found: {RADIATION_FILE}")
        return 1

    # Create backup
    backup_file = RADIATION_FILE.with_suffix(RADIATION_FILE.suffix + BACKUP_SUFFIX + '.parquet')
    print(f"\n1. Creating backup...")
    print(f"   Original: {RADIATION_FILE}")
    print(f"   Backup:   {backup_file}")

    if backup_file.exists():
        print(f"   ⚠️  Backup file already exists. Skipping backup creation.")
    else:
        shutil.copy2(RADIATION_FILE, backup_file)
        print(f"   ✓ Backup created successfully")

    # Load Parquet file
    print(f"\n2. Loading Parquet file...")
    df = pd.read_parquet(RADIATION_FILE)
    print(f"   ✓ Loaded {len(df)} records")
    print(f"   ✓ Date range: {df.index.min()} to {df.index.max()}")
    print(f"   ✓ Columns: {list(df.columns)}")

    # Check if required columns exist
    required_cols = ['IR_in_Avg', 'IR_out_Avg']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        print(f"   ❌ Error: Missing required columns: {missing_cols}")
        return 1

    # Check data before fix
    fix_date = pd.to_datetime(FIX_DATE)
    mask_after_fix = df.index >= fix_date

    print(f"\n3. Analyzing data...")
    print(f"   Fix date: {fix_date}")
    records_to_fix = mask_after_fix.sum()
    print(f"   Records to fix (>= {FIX_DATE}): {records_to_fix}")

    if records_to_fix == 0:
        print(f"   ⚠️  No records found after {FIX_DATE}. Nothing to fix.")
        return 0

    # Show statistics before fix
    print(f"\n4. Statistics before fix (>= {FIX_DATE}):")
    df_after = df[mask_after_fix]


    # Create copies of the columns
    ir_in_original = df['IR_in_Avg'].copy()
    ir_out_original = df['IR_out_Avg'].copy()

    # drop only for data >= fix_date
    df.loc[mask_after_fix, ['IR_in_Avg', 'IR_out_Avg']] = pd.NA

    print(f"   ✓ droped {records_to_fix} records")

    # Show statistics after fix
    print(f"\n6. Statistics after fix (>= {FIX_DATE}):")
    df_after_fixed = df[mask_after_fix]
    print(f"   IR_in_Avg:  mean={df_after_fixed['IR_in_Avg'].mean():.2f}, min={df_after_fixed['IR_in_Avg'].min():.2f}, max={df_after_fixed['IR_in_Avg'].max():.2f}")
    print(f"   IR_out_Avg: mean={df_after_fixed['IR_out_Avg'].mean():.2f}, min={df_after_fixed['IR_out_Avg'].min():.2f}, max={df_after_fixed['IR_out_Avg'].max():.2f}")



    # Save corrected file
    print(f"\n8. Saving corrected file...")
    df.to_parquet(RADIATION_FILE, index=True)
    print(f"   ✓ Saved to: {RADIATION_FILE}")

    print(f"\n✅ Fix completed successfully!")
    print(f"\nNote: Original file backed up to: {backup_file}")
    print(f"      To restore, run: cp {backup_file} {RADIATION_FILE}")

    return 0

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
