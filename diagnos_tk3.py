import pandas as pd
import numpy as np

FILE = "/Users/hingerl-l/ec_data/Nazinga/Nazinga_TK3_result_2013to2020.csv"

df = pd.read_csv(FILE, header=None, dtype=str, sep=",", engine="python", on_bad_lines="skip")

print("=== DIAGNOSE REPORT ===")

# 1) Spaltenanzahl prüfen
col_counts = df.apply(lambda row: len(row.dropna()), axis=1)
print("\nColumn count distribution:")
print(col_counts.value_counts().sort_index())

# 2) Timestamp-Check
def is_timestamp(x):
    try:
        pd.to_datetime(x, errors="raise", dayfirst=True)
        return True
    except:
        return False

valid_begin = df[0].apply(is_timestamp)
valid_end   = df[1].apply(is_timestamp)

print("\nValid timestamp rows:", (valid_begin & valid_end).sum())
print("Invalid timestamp rows:", (~(valid_begin & valid_end)).sum())

# 3) Beispiele für kaputte Zeilen
print("\nSample invalid rows:")
bad_rows = df[~(valid_begin & valid_end)].head(10)
print(bad_rows)
