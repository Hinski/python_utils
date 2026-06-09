#!/usr/bin/env python3
import pandas as pd
import numpy as np
from pathlib import Path

# --- CONFIG ---
N_COLS = 62   # All TK3 files have 61 or 62 columns → normalize to 62

# Official 62-column TK3 header
TK3_HEADER = [
    'T_begin','T_end','u[m/s]','v[m/s]','w[m/s]','Ts[°C]','Tp[°C]',
    'a[g/m³]','CO2[mmol/m³]','T_ref[°C]','a_ref[g/m³]','p_ref[hPa]',
    'Var[u]','Var[v]','Var[w]','Var[Ts]','Var[Tp]','Var[a]','Var[CO2]',
    "Cov[u'v']","Cov[v'w']","Cov[u'w']","Cov[u'Ts']","Cov[v'Ts']","Cov[w'Ts']",
    "Cov[u'Tp']","Cov[v'Tp']","Cov[w'Tp']","Cov[u'a']","Cov[v'a']","Cov[w'a']",
    "Cov[u'CO2']","Cov[v'CO2']","Cov[w'CO2']",'???','dir[°]','ustar[m/s]',
    'HTs[W/m²]','HTp[W/m²]','LvE[W/m²]','z/L','z/L-virt','Flag(ustar)',
    'Flag(HTs)','Flag(HTp)','Flag(LvE)','Flag(wCO2)','T_mid',
    'FCstor[mmol/m²s]','NEE[mmol/m²s]','Footprint_trgt_1','Footprint_trgt_2',
    'Footprnt_xmax[m]','r_err_ustar[%]','r_err_HTs[%]','r_err_LvE[%]',
    'r_err_co2[%]','noise_ustar[%]','noise_HTs[%]','noise_LvE[%]',
    'noise_co2[%]','Filler_to_reach62'  # 62nd column
]


def load_tk3_file(path: Path) -> pd.DataFrame:
    """
    Loads ANY TK3 file (61 or 62 cols) and normalizes into 62-column DataFrame.
    """

    # Raw read
    df = pd.read_csv(
        path,
        header=None,
        sep=",",
        engine="python",
        on_bad_lines="skip",
        dtype=str,
    )

    n = df.shape[1]

    # Fix too many columns
    if n > N_COLS:
        df = df.iloc[:, :N_COLS]

    # Fix too few columns
    if n < N_COLS:
        for _ in range(N_COLS - n):
            df[df.shape[1]] = np.nan

    # Assign final header
    df.columns = TK3_HEADER

    # Convert timestamps
    df["T_begin"] = pd.to_datetime(df["T_begin"], errors="coerce", dayfirst=True)
    df["T_end"]   = pd.to_datetime(df["T_end"],   errors="coerce", dayfirst=True)

    # Drop rows where date could not be parsed
    df = df.dropna(subset=["T_begin", "T_end"], how="all")

    return df



def combine_tk3(input_dir: str, output_file: str):
    input_dir = Path(input_dir)
    all_rows = []

    print(f"\n🔍 Searching for TK3 files in: {input_dir}")

    files = sorted(input_dir.glob("WASC3_result_*.csv"))
    print(f"📄 Found {len(files)} files.\n")

    for f in files:
        print(f"→ Loading {f.name}")

        try:
            df = load_tk3_file(f)
            print(f"   ✓ Loaded ({df.shape[0]} rows)")
            all_rows.append(df)

        except Exception as e:
            print(f"   ❌ Error in {f.name}: {e}")

    print("\n⏳ Concatenating all valid TK3 frames...")
    if not all_rows:
        raise RuntimeError("No TK3 files could be loaded!")

    df_all = pd.concat(all_rows, ignore_index=True)

    print(f"💾 Saving combined file → {output_file}\n")
    df_all.to_csv(output_file, index=False)

    print("🎉 Done! Final dataset shape:", df_all.shape)



if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("\nUsage:")
        print("  python3 combine_tk3.py <input_directory> <output_csv>\n")
        sys.exit(1)

    combine_tk3(sys.argv[1], sys.argv[2])
