"""
Analyze vertical wind component statistics from raw turbulence data.
Calculates statistics for Planar Fit settings recommendations.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import glob

# Data directory
data_dir = Path('/Volumes/Data/Gorigo/Turbulence')

# Find all .dat files
data_files = sorted(glob.glob(str(data_dir / '*.dat')))

print(f"Found {len(data_files)} data files")
print("=" * 80)

# Store all vertical wind component values
all_w_values = []

# Process each file
for file_path in data_files:
    try:
        # Read CSV file (comma-separated)
        # Assuming: u, v, w, ... (3rd column is w, index 2)
        df = pd.read_csv(file_path, header=None)
        
        # Extract 3rd column (index 2) - vertical wind component
        w_values = df.iloc[:, 2].values
        
        # Remove NaN and infinite values
        w_values = w_values[np.isfinite(w_values)]
        
        all_w_values.extend(w_values)
        
    except Exception as e:
        print(f"Error reading {Path(file_path).name}: {e}")
        continue

# Convert to numpy array
all_w_values = np.array(all_w_values)

print(f"\nTotal data points: {len(all_w_values):,}")
print("=" * 80)

# Calculate statistics
stats = {
    'Minimum': np.min(all_w_values),
    'Maximum': np.max(all_w_values),
    'Mean': np.mean(all_w_values),
    'Median': np.median(all_w_values),
    'Standard Deviation': np.std(all_w_values),
    '25th Percentile': np.percentile(all_w_values, 25),
    '75th Percentile': np.percentile(all_w_values, 75),
    '95th Percentile': np.percentile(all_w_values, 95),
    '99th Percentile': np.percentile(all_w_values, 99),
}

print("\n📊 STATISTICS OF VERTICAL WIND COMPONENT (w) [m/s]")
print("=" * 80)
for key, value in stats.items():
    print(f"{key:25s}: {value:10.4f} m/s")

# Additional statistics for Planar Fit
print("\n" + "=" * 80)
print("📈 ADDITIONAL STATISTICS FOR PLANAR FIT SETTINGS")
print("=" * 80)

# Mean absolute value
mean_abs_w = np.mean(np.abs(all_w_values))
print(f"Mean absolute value (|w|): {mean_abs_w:.4f} m/s")

# Percentage of values within certain thresholds
thresholds = [0.1, 0.2, 0.3, 0.5, 1.0]
print("\nPercentage of values within thresholds:")
for threshold in thresholds:
    pct = np.sum(np.abs(all_w_values) <= threshold) / len(all_w_values) * 100
    print(f"  |w| <= {threshold:4.1f} m/s: {pct:6.2f}%")

# Values outside typical range (for filtering recommendations)
print("\n" + "=" * 80)
print("🔍 RECOMMENDATIONS FOR PLANAR FIT SETTINGS")
print("=" * 80)

# Maximum mean vertical wind component recommendation
# Based on 95th percentile of absolute values
abs_w_values = np.abs(all_w_values)
p95_abs = np.percentile(abs_w_values, 95)
p99_abs = np.percentile(abs_w_values, 99)

print(f"\n1. Maximum Mean Vertical Wind Component:")
print(f"   - 95th percentile of |w|: {p95_abs:.4f} m/s")
print(f"   - 99th percentile of |w|: {p99_abs:.4f} m/s")
print(f"   - Recommended threshold: {p95_abs:.2f} - {p99_abs:.2f} m/s")
print(f"   - Conservative choice: {p95_abs:.2f} m/s")
print(f"   - Strict choice: {p99_abs:.2f} m/s")

# Distribution analysis
print(f"\n2. Distribution Analysis:")
print(f"   - Mean: {stats['Mean']:.4f} m/s (should be close to 0 for good data)")
print(f"   - Std Dev: {stats['Standard Deviation']:.4f} m/s")
print(f"   - Range: [{stats['Minimum']:.2f}, {stats['Maximum']:.2f}] m/s")

# Check for bias
if abs(stats['Mean']) > 0.1:
    print(f"   ⚠️  WARNING: Mean is {stats['Mean']:.4f} m/s - significant bias detected!")
    print(f"      This suggests anemometer tilt or systematic error.")
else:
    print(f"   ✓ Mean is close to zero - good data quality")

# Outlier detection
q1 = stats['25th Percentile']
q3 = stats['75th Percentile']
iqr = q3 - q1
lower_bound = q1 - 1.5 * iqr
upper_bound = q3 + 1.5 * iqr
outliers = np.sum((all_w_values < lower_bound) | (all_w_values > upper_bound))

print(f"\n3. Outlier Detection (IQR method):")
print(f"   - IQR: {iqr:.4f} m/s")
print(f"   - Outliers: {outliers:,} ({outliers/len(all_w_values)*100:.2f}%)")
print(f"   - Outlier range: < {lower_bound:.2f} or > {upper_bound:.2f} m/s")

# Recommendations
print(f"\n" + "=" * 80)
print("💡 RECOMMENDED PLANAR FIT SETTINGS")
print("=" * 80)

print(f"\nBased on the data analysis:")
print(f"  • Maximum Mean Vertical Wind Component: {p95_abs:.2f} m/s")
print(f"    (This filters out ~5% of extreme values)")
print(f"  • Alternative (stricter): {p99_abs:.2f} m/s")
print(f"    (This filters out ~1% of extreme values)")

print(f"\n  • The mean vertical wind component is {stats['Mean']:.4f} m/s")
if abs(stats['Mean']) < 0.05:
    print(f"    ✓ Very close to zero - data quality is good")
elif abs(stats['Mean']) < 0.1:
    print(f"    ⚠️  Small bias present - Planar Fit will correct this")
else:
    print(f"    ⚠️  Significant bias - Planar Fit correction is essential")

print(f"\n  • Standard deviation: {stats['Standard Deviation']:.4f} m/s")
print(f"    This represents the typical variability in vertical wind")

print(f"\n" + "=" * 80)
print("✅ SUMMARY")
print("=" * 80)
print(f"Total data points analyzed: {len(all_w_values):,}")
print(f"Recommended 'Maximum Mean Vertical Wind Component': {p95_abs:.2f} m/s")
print(f"Data quality: {'Good' if abs(stats['Mean']) < 0.1 else 'Needs correction'}")
