#!/usr/bin/env python3
import pandas as pd
import numpy as np
from pathlib import Path


def load_and_repair_tk3(csv_path: Path) -> pd.DataFrame:
    """
    Lädt eine kombinierte TK3-Datei, entfernt evtl. eingebettete Headerzeilen,
    wandelt TK3-NA-Codes (-9999.9...) in NaN und konvertiert numerische Spalten.
    """

    print(f"🔍 Lade TK3-Datei: {csv_path}")
    df = pd.read_csv(csv_path, sep=",", engine="python", dtype=str)
    print(f"→ Rohform: {df.shape[0]} Zeilen, {df.shape[1]} Spalten")

    # Spaltennamen säubern
    df.columns = df.columns.str.strip()

    # Eingebettete Header-Zeilen entfernen (Zeilen, in denen in col0 'T_begin' steht)
    header_like = df[df.iloc[:, 0].astype(str).str.strip() == "T_begin"]
    if not header_like.empty:
        print(f"⚠️ Eingebettete Header-Zeilen gefunden und entfernt: {len(header_like)}")
        df = df[df.iloc[:, 0].astype(str).str.strip() != "T_begin"]

    # Zeitspalten parsen
    for col in ["T_begin", "T_end"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)

    # Zeitachse
    if "T_end" in df.columns:
        df["time_end"] = df["T_end"]
    else:
        df["time_end"] = df["T_begin"]

    df["time_start"] = df["T_begin"]

    # Numerische Spalten: alles außer Zeitspalten
    numeric_cols = [c for c in df.columns if c not in ["T_begin", "T_end", "time_start", "time_end"]]

    # Zu float konvertieren (wo möglich)
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col].str.strip(), errors="coerce")

    # TK3-NA-Codes sind riesig negative Werte (~ -9999.xx) → NaN
    num_mask = df[numeric_cols] < -9000
    if num_mask.any().any():
        n_bad = int(num_mask.sum().sum())
        print(f"⚠️ Ersetze {n_bad} TK3-NA-Werte (< -9000) durch NaN")
        df.loc[:, numeric_cols] = df[numeric_cols].mask(num_mask)

    print(f"✅ Reparierte Form: {df.shape[0]} Zeilen, {df.shape[1]} Spalten")
    return df


def tk3_to_gfe_features(df: pd.DataFrame, site_id: str) -> pd.DataFrame:
    """
    Wandelt reparierte TK3-Daten in ein GFE-kompatibles Turbulenz-Feature-Format um.
    Erwartet TK3-Spaltennamen wie aus deinem Header.
    """

    # Spaltennamen nochmal säubern
    df = df.copy()
    df.columns = df.columns.str.strip()

    # Prüfen, welche Kernspalten es wirklich gibt
    required = [
        "u[m/s]", "v[m/s]", "w[m/s]", "Ts[°C]",
        "a[g/m³]", "CO2[mmol/m³]",
        "Var[u]", "Var[v]", "Var[w]", "Var[Ts]",
        "HTs[W/m²]", "LvE[W/m²]", "ustar[m/s]",
        "NEE[mmol/m²s]", "dir[°]", "z/L", "z/L-virt",
        "Footprint_trgt_1", "Footprint_trgt_2", "Footprnt_xmax[m]"
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"⚠️ Achtung: folgende erwartete TK3-Spalten fehlen: {missing}")
        print("   → Features für diese Spalten werden als NaN gesetzt, falls verwendet.")

    # Helper: sicher auf Spalte zugreifen (oder NaN)
    def col(name):
        return df[name] if name in df.columns else np.nan

    # Mittelwerte / Grundgrößen
    u = col("u[m/s]")
    v = col("v[m/s]")
    w = col("w[m/s]")
    Ts = col("Ts[°C]")
    q = col("a[g/m³]")
    co2 = col("CO2[mmol/m³]")

    Var_u = col("Var[u]")
    Var_v = col("Var[v]")
    Var_w = col("Var[w]")
    Var_Ts = col("Var[Ts]")

    # Windgeschwindigkeit als Betrag aus u und v
    U_mean = np.sqrt(u**2 + v**2)

    sigma_u = np.sqrt(Var_u)
    sigma_v = np.sqrt(Var_v)
    sigma_w = np.sqrt(Var_w)
    sigma_Ts = np.sqrt(Var_Ts)

    TI_u = sigma_u / U_mean
    TI_w = sigma_w / U_mean

    out = pd.DataFrame({
        "time_start": df["time_start"],
        "time_end": df["time_end"],
        "site_id": site_id,

        "U_mean": U_mean,
        "w_mean": w,
        "Ts_mean": Ts,
        "q_mean": q,
        "CO2_mean": co2,

        "sigma_u": sigma_u,
        "sigma_v": sigma_v,
        "sigma_w": sigma_w,
        "sigma_Ts": sigma_Ts,
        "TI_u": TI_u,
        "TI_w": TI_w,

        "HTs": col("HTs[W/m²]"),
        "LvE": col("LvE[W/m²]"),
        "ustar": col("ustar[m/s]"),
        "NEE": col("NEE[mmol/m²s]"),

        "dir": col("dir[°]"),
        "z_L": col("z/L"),
        "z_L_virt": col("z/L-virt"),

        "Footprint_trgt_1": col("Footprint_trgt_1"),
        "Footprint_trgt_2": col("Footprint_trgt_2"),
        "Footprnt_xmax": col("Footprnt_xmax[m]"),
    })

    # Optional: originale Varianzen/Kovarianzen anhängen für spätere Experimente
    extra_cols = [
        "Var[u]", "Var[v]", "Var[w]", "Var[Ts]",
        "Var[a]", "Var[CO2]",
        "Cov[u'v']", "Cov[v'w']", "Cov[u'w']",
        "Cov[u'Ts']", "Cov[v'Ts']", "Cov[w'Ts']",
        "Cov[u'a']", "Cov[v'a']", "Cov[w'a']",
        "Cov[u'CO2']", "Cov[v'CO2']", "Cov[w'CO2']",
    ]
    for c in extra_cols:
        if c in df.columns:
            out[c] = df[c]

    return out


def convert_tk3_to_parquet(input_csv: str, site_id: str, output_parquet: str):
    input_path = Path(input_csv)
    output_path = Path(output_parquet)

    df_tk3 = load_and_repair_tk3(input_path)
    df_feats = tk3_to_gfe_features(df_tk3, site_id=site_id)

    print(f"📝 Speichere GFE-Turbulenz-Features nach Parquet: {output_path}")
    df_feats.to_parquet(output_path, index=False)
    print("✅ Fertig!")


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 4:
        print("Usage: python tk3_to_gfe_parquet.py <input_csv> <site_id> <output_parquet>")
        print("z.B.:  python tk3_to_gfe_parquet.py "
              "\"/Users/hingerl-l/ec_data/Nazinga/Nazinga_TK3_combined.csv\" "
              "Nazinga "
              "\"/Users/hingerl-l/FluxEngine/global-flux-engine/Nazinga_TK3_turbulence.parquet\"")
        sys.exit(1)

    convert_tk3_to_parquet(sys.argv[1], sys.argv[2], sys.argv[3])
