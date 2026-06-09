import pandas as pd
import numpy as np
from pathlib import Path

# Lade eine Beispiel-Datei
data_file = Path('/Volumes/Data/Gorigo/Turbulence/Gor_24_135_1200.dat')

print("=" * 60)
print("Comparing col_4 (Sonic Temperature) vs col_10 (HMP Fast Temperature)")
print("=" * 60)

# Lese die ersten Zeilen, um die Struktur zu sehen
print("\nFirst 5 lines of file:")
try:
    with open(data_file, 'r') as f:
        first_lines = [f.readline() for _ in range(5)]
        for i, line in enumerate(first_lines):
            print(f"Line {i+1}: {line[:150]}")
except Exception as e:
    print(f"Error reading first lines: {e}")

# Versuche, die Datei zu lesen (nur erste 10000 Zeilen für Vergleich)
print("\n" + "=" * 60)
print("Reading data file...")
try:
    # Prüfe das Format - könnte CSV oder andere Format sein
    # Versuche zuerst mit Komma als Separator
    df_sample = pd.read_csv(data_file, nrows=10000, header=None, low_memory=False, sep=',')
    
    print(f"✓ File read successfully")
    print(f"Number of columns: {len(df_sample.columns)}")
    print(f"Number of rows read: {len(df_sample)}")
    
    # Prüfe, ob wir genug Spalten haben
    if len(df_sample.columns) < 10:
        print(f"\n⚠️ WARNING: File has only {len(df_sample.columns)} columns, but we need at least 10!")
        print("First few columns:")
        print(df_sample.head())
    else:
        print("\n" + "=" * 60)
        print("Column 4 (Sonic Temperature from CSAT3) statistics:")
        print("=" * 60)
        col4 = df_sample.iloc[:, 3].dropna()
        print(f"Non-null values: {len(col4)} / {len(df_sample)}")
        print(f"Mean: {col4.mean():.3f}°C")
        print(f"Std: {col4.std():.3f}°C")
        print(f"Min: {col4.min():.3f}°C")
        print(f"Max: {col4.max():.3f}°C")
        print(f"Range: {col4.max() - col4.min():.3f}°C")
        print(f"Unique values: {col4.nunique()}")
        
        print("\n" + "=" * 60)
        print("Column 10 (HMP Fast Temperature) statistics:")
        print("=" * 60)
        col10 = df_sample.iloc[:, 9].dropna()
        print(f"Non-null values: {len(col10)} / {len(df_sample)}")
        print(f"Mean: {col10.mean():.3f}°C")
        print(f"Std: {col10.std():.3f}°C")
        print(f"Min: {col10.min():.3f}°C")
        print(f"Max: {col10.max():.3f}°C")
        print(f"Range: {col10.max() - col10.min():.3f}°C")
        print(f"Unique values: {col10.nunique()}")
        
        print("\n" + "=" * 60)
        print("Comparison:")
        print("=" * 60)
        # Align indices for comparison
        common_idx = col4.index.intersection(col10.index)
        col4_aligned = col4.loc[common_idx]
        col10_aligned = col10.loc[common_idx]
        
        diff = col4_aligned - col10_aligned
        print(f"Mean difference (col4 - col10): {diff.mean():.3f}°C")
        print(f"Std of difference: {diff.std():.3f}°C")
        print(f"Correlation: {col4_aligned.corr(col10_aligned):.3f}")
        
        # Prüfe auf konstante Werte (Problem-Indikator)
        print("\n" + "=" * 60)
        print("Quality Checks:")
        print("=" * 60)
        if col4.nunique() < 10:
            print(f"⚠️ WARNING: col_4 has only {col4.nunique()} unique values - might be constant or faulty!")
        else:
            print(f"✓ col_4 has {col4.nunique()} unique values - looks good")
            
        if col10.nunique() < 10:
            print(f"⚠️ WARNING: col_10 has only {col10.nunique()} unique values - might be constant or faulty!")
        else:
            print(f"✓ col_10 has {col10.nunique()} unique values - looks good")
        
        # Prüfe Varianz (wichtig für sensible heat flux)
        if col4.std() < 0.1:
            print(f"⚠️ WARNING: col_4 has very low variance (std={col4.std():.3f}°C) - might not capture turbulent fluctuations!")
        else:
            print(f"✓ col_4 has good variance (std={col4.std():.3f}°C)")
            
        if col10.std() < 0.1:
            print(f"⚠️ WARNING: col_10 has very low variance (std={col10.std():.3f}°C) - might not capture turbulent fluctuations!")
        else:
            print(f"✓ col_10 has good variance (std={col10.std():.3f}°C)")
        
        # Welche hat mehr Varianz?
        if col4.std() > col10.std():
            print(f"\n→ col_4 (Sonic Temperature) has higher variance - better for sensible heat flux calculation")
        elif col10.std() > col4.std():
            print(f"\n→ col_10 (HMP Temperature) has higher variance - might be better for sensible heat flux calculation")
        else:
            print(f"\n→ Both columns have similar variance")
            
        # Prüfe auf NaN oder fehlende Werte
        col4_nan = df_sample.iloc[:, 3].isna().sum()
        col10_nan = df_sample.iloc[:, 9].isna().sum()
        print(f"\nMissing values: col_4: {col4_nan}, col_10: {col10_nan}")
        
except Exception as e:
    print(f"Error reading file: {e}")
    import traceback
    traceback.print_exc()
