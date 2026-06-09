"""
Fix swapped longwave radiation (LW_in and LW_out) for Nazinga.

This script corrects ONLY the newly added data that still has swapped longwave radiation.
It identifies data that needs fixing by checking if IR_in_Avg < IR_out_Avg (which indicates
the data is still swapped, since IR_in should typically be higher than IR_out).

Previously fixed data (where IR_in > IR_out) will NOT be touched.
Only data >= 2018-01-01 that still has IR_in < IR_out will be swapped.
"""

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
    print(f"This script swaps IR_in_Avg and IR_out_Avg ONLY for data >= {FIX_DATE}")
    print(f"that still has IR_in < IR_out (indicating it's still swapped).")
    print(f"Previously fixed data (IR_in > IR_out) will NOT be touched.")
    print("=" * 60)
    
    # Check if file exists
    if not RADIATION_FILE.exists():
        print(f"❌ Error: File not found: {RADIATION_FILE}")
        return 1
    
    # Create backup with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = RADIATION_FILE.with_suffix(RADIATION_FILE.suffix + f'{BACKUP_SUFFIX}_{timestamp}.parquet')
    print(f"\n1. Creating backup...")
    print(f"   Original: {RADIATION_FILE}")
    print(f"   Backup:   {backup_file}")
    
    if backup_file.exists():
        print(f"   ⚠️  Backup file already exists. Creating new backup with timestamp.")
        backup_file = RADIATION_FILE.with_suffix(RADIATION_FILE.suffix + f'{BACKUP_SUFFIX}_{timestamp}.parquet')
    
    shutil.copy2(RADIATION_FILE, backup_file)
    print(f"   ✓ Backup created successfully")
    
    # Load Parquet file
    print(f"\n2. Loading Parquet file...")
    df = pd.read_parquet(RADIATION_FILE)
    print(f"   ✓ Loaded {len(df)} records")
    print(f"   ✓ Date range: {df.index.min()} to {df.index.max()}")
    
    # Check if index is datetime
    if not isinstance(df.index, pd.DatetimeIndex):
        print(f"   ⚠️  Warning: Index is not DatetimeIndex. Attempting to convert...")
        try:
            df.index = pd.to_datetime(df.index)
            print(f"   ✓ Converted index to DatetimeIndex")
        except Exception as e:
            print(f"   ❌ Error: Could not convert index to DatetimeIndex: {e}")
            return 1
    
    # Check if required columns exist
    required_cols = ['IR_in_Avg', 'IR_out_Avg']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        print(f"   ❌ Error: Missing required columns: {missing_cols}")
        print(f"   Available columns: {list(df.columns)}")
        return 1
    
    # Check data before fix
    fix_date = pd.to_datetime(FIX_DATE)
    mask_after_fix_date = df.index >= fix_date
    
    print(f"\n3. Analyzing data...")
    print(f"   Fix date: {fix_date}")
    records_after_fix_date = mask_after_fix_date.sum()
    records_before_fix_date = (~mask_after_fix_date).sum()
    print(f"   Records before {FIX_DATE}: {records_before_fix_date}")
    print(f"   Records >= {FIX_DATE}: {records_after_fix_date}")
    
    if records_after_fix_date == 0:
        print(f"   ⚠️  No records found after {FIX_DATE}. Nothing to fix.")
        return 0
    
    # Identify which records still need fixing (IR_in < IR_out indicates swapped data)
    # Only swap data that is still swapped, not data that was already fixed
    df_after = df[mask_after_fix_date].copy()
    
    # Check which records have IR_in < IR_out (still swapped)
    # Also check for NaN values - we'll skip those
    both_valid = df_after['IR_in_Avg'].notna() & df_after['IR_out_Avg'].notna()
    still_swapped = both_valid & (df_after['IR_in_Avg'] < df_after['IR_out_Avg'])
    already_fixed = both_valid & (df_after['IR_in_Avg'] > df_after['IR_out_Avg'])
    
    records_still_swapped = still_swapped.sum()
    records_already_fixed = already_fixed.sum()
    records_with_nan = (~both_valid).sum()
    
    print(f"\n4. Identifying records that need fixing...")
    print(f"   Records >= {FIX_DATE} with valid data: {both_valid.sum()}")
    print(f"   - Already fixed (IR_in > IR_out): {records_already_fixed}")
    print(f"   - Still swapped (IR_in < IR_out): {records_still_swapped}")
    print(f"   - With NaN values (skipped): {records_with_nan}")
    
    if records_still_swapped == 0:
        print(f"\n   ✓ No records need fixing! All data >= {FIX_DATE} is already correct.")
        print(f"   (IR_in > IR_out for all valid records)")
        return 0
    
    # Show statistics before fix for swapped records only
    print(f"\n5. Statistics BEFORE fix (records that will be swapped):")
    df_swapped = df_after[still_swapped]
    ir_in_before = df_swapped['IR_in_Avg']
    ir_out_before = df_swapped['IR_out_Avg']
    
    print(f"   IR_in_Avg:  mean={ir_in_before.mean():.2f}, min={ir_in_before.min():.2f}, max={ir_in_before.max():.2f}")
    print(f"   IR_out_Avg: mean={ir_out_before.mean():.2f}, min={ir_out_before.min():.2f}, max={ir_out_before.max():.2f}")
    print(f"   ⚠️  IR_in_Avg < IR_out_Avg (data is swapped)")
    
    # Create mask for records that need swapping (only those that are still swapped)
    # We need to map back to the original dataframe index
    mask_to_swap = pd.Series(False, index=df.index)
    mask_to_swap.loc[mask_after_fix_date] = still_swapped
    
    # Swap IR_in_Avg and IR_out_Avg ONLY for records that are still swapped
    print(f"\n6. Swapping IR_in_Avg and IR_out_Avg for {records_still_swapped} records...")
    
    # Create copies of the columns for the swap
    ir_in_original = df['IR_in_Avg'].copy()
    ir_out_original = df['IR_out_Avg'].copy()
    
    # Swap only for records that are still swapped
    df.loc[mask_to_swap, 'IR_in_Avg'] = ir_out_original[mask_to_swap]
    df.loc[mask_to_swap, 'IR_out_Avg'] = ir_in_original[mask_to_swap]
    
    print(f"   ✓ Swapped {records_still_swapped} records")
    
    # Show statistics after fix for swapped records only
    print(f"\n7. Statistics AFTER fix (records that were swapped):")
    df_after_fixed = df[mask_to_swap]
    ir_in_after = df_after_fixed['IR_in_Avg']
    ir_out_after = df_after_fixed['IR_out_Avg']
    
    print(f"   IR_in_Avg:  mean={ir_in_after.mean():.2f}, min={ir_in_after.min():.2f}, max={ir_in_after.max():.2f}")
    print(f"   IR_out_Avg: mean={ir_out_after.mean():.2f}, min={ir_out_after.min():.2f}, max={ir_out_after.max():.2f}")
    
    # Verify the swap
    print(f"\n8. Verifying swap...")
    # Check that IR_in now contains what was in IR_out
    ir_in_swapped_correctly = (df.loc[mask_to_swap, 'IR_in_Avg'] == ir_out_original[mask_to_swap]).all()
    # Check that IR_out now contains what was in IR_in
    ir_out_swapped_correctly = (df.loc[mask_to_swap, 'IR_out_Avg'] == ir_in_original[mask_to_swap]).all()
    
    if ir_in_swapped_correctly and ir_out_swapped_correctly:
        print(f"   ✓ Swap verified successfully")
        print(f"      IR_in_Avg now contains original IR_out_Avg values")
        print(f"      IR_out_Avg now contains original IR_in_Avg values")
    else:
        print(f"   ⚠️  Warning: Swap verification failed.")
        print(f"      IR_in correctly swapped: {ir_in_swapped_correctly}")
        print(f"      IR_out correctly swapped: {ir_out_swapped_correctly}")
        print(f"      Please check manually.")
    
    # Check if the fix makes sense (IR_in should now be > IR_out typically)
    if ir_in_after.mean() > ir_out_after.mean():
        print(f"   ✓ After fix: IR_in_Avg mean > IR_out_Avg mean (this is correct)")
    else:
        print(f"   ⚠️  After fix: IR_in_Avg mean < IR_out_Avg mean (unusual, but may be correct)")
    
    # Verify that previously fixed data was not touched
    print(f"\n9. Verifying previously fixed data was not touched...")
    df_after_check = df[mask_after_fix_date].copy()
    both_valid_check = df_after_check['IR_in_Avg'].notna() & df_after_check['IR_out_Avg'].notna()
    still_correct = both_valid_check & (df_after_check['IR_in_Avg'] > df_after_check['IR_out_Avg'])
    now_swapped = both_valid_check & (df_after_check['IR_in_Avg'] < df_after_check['IR_out_Avg'])
    
    if now_swapped.sum() == 0:
        print(f"   ✓ All previously fixed data is still correct (IR_in > IR_out)")
        print(f"   ✓ No previously fixed records were accidentally swapped")
    else:
        print(f"   ⚠️  Warning: {now_swapped.sum()} records now have IR_in < IR_out")
        print(f"      This should not happen if data was previously fixed correctly")
    
    # Show date range of fixed data
    if records_still_swapped > 0:
        print(f"\n10. Date range of newly fixed data:")
        print(f"   From: {df_after_fixed.index.min()}")
        print(f"   To:   {df_after_fixed.index.max()}")
        print(f"   Total records fixed: {records_still_swapped}")
    
    # Save corrected file
    print(f"\n11. Saving corrected file...")
    try:
        df.to_parquet(RADIATION_FILE, index=True)
        print(f"   ✓ Saved to: {RADIATION_FILE}")
        
        # Verify file was saved correctly
        df_verify = pd.read_parquet(RADIATION_FILE)
        if len(df_verify) == len(df):
            print(f"   ✓ File verification: {len(df_verify)} records saved correctly")
        else:
            print(f"   ⚠️  Warning: Record count mismatch after save")
    except Exception as e:
        print(f"   ❌ Error saving file: {e}")
        return 1
    
    print(f"\n✅ Fix completed successfully!")
    print(f"\nSummary:")
    print(f"  - Fixed {records_still_swapped} records (only those that were still swapped)")
    print(f"  - Left {records_already_fixed} previously fixed records unchanged")
    print(f"  - Backup saved to: {backup_file}")
    print(f"  - Original file updated: {RADIATION_FILE}")
    print(f"\nNote: To restore original file, run:")
    print(f"      cp {backup_file} {RADIATION_FILE}")
    
    return 0

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
