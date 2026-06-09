#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prepare footprint-ready DataFrames for all EC stations.

→ Kombiniert Energy Balance, Turbulenz, Vegetationshöhe und abgeleitete
  Stabilitätsparameter (z/L, z0, d, zm, h, usw.) für jede Station.
"""

import os
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------
# Extract turbulence & meteorological variables
# ---------------------------------------------------------------------
def extract_turb_vars(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Extract and standardize footprint-relevant turbulence variables."""
    df = pd.DataFrame(index=pd.to_datetime(df_raw.index, errors="coerce"))

    df["u_star"] = df_raw.get("ustar[m/s]")
    df["L"] = df_raw.get("z/L")

    # ✓ Sigma_v = sqrt(Var[v]) — korrekt (Querwind-Komponente!)
    df["sigma_v"] = np.sqrt(df_raw.get("Var[v]", np.nan))

    # Windgeschwindigkeit
    u = df_raw.get("u[m/s]", np.nan)
    v = df_raw.get("v[m/s]", np.nan)
    df["WS"] = np.sqrt(u**2 + v**2)
    df["WD"] = df_raw.get("dir[°]")

    # Temperatur & Druck
    df["TA"] = df_raw.get("T_ref[°C]")
    df["P"] = df_raw.get("p_ref[hPa]")

    df = df.replace([-9999, -999, 9999, 99999], np.nan)
    return df


# ---------------------------------------------------------------------
# Merge energy balance + turbulence + vegetation + derived parameters
# ---------------------------------------------------------------------
def merge_with_meteo_and_veg(eb_df, df_turb, df_veg, site_name, zm_default):
    """Merge all components and compute physically consistent parameters."""
    df = eb_df.copy()
    df_turb = extract_turb_vars(df_turb)

    # --- Vegetation height ---
    if "veg_h" in df_veg.columns:
        df_veg = df_veg.rename(columns={"veg_h": "h_veg"})

    df_veg = df_veg.resample("30T").interpolate(limit_direction="both")

    # Merge
    df = df.join(df_turb, how="left")
    df = df.join(df_veg["h_veg"], how="left")

    # --- Derived parameters ---
    df["zm"] = zm_default
    df["d"] = 0.67 * df["h_veg"]

    df["z0"] = 0.1 * df["h_veg"]
    df["z0"] = df["z0"].clip(lower=0.01, upper=df["h_veg"] / 10)

    df["z_L"] = df["zm"] / df["L"]

    # --- Boundary layer height (PBL height) ---
    f = 2 * 7.2921e-5 * np.sin(np.deg2rad(11.0))  # ~2.7e-5
    df["h"] = np.nan

    unstable = df["L"] < 0
    stable   = df["L"] > 0

    df.loc[unstable, "h"] = (
        0.1 * (-df.loc[unstable, "L"])**0.25
        * np.sqrt(df.loc[unstable, "u_star"] / f)
    )
    df.loc[stable, "h"] = 200 + 5 * df.loc[stable, "u_star"] / f
    df["h"] = df["h"].clip(lower=50, upper=2000)

    # ==========================
    # 1) Basis: nur offensichtliche NAs entfernen
    # ==========================
    print(f"\n📊 {site_name}: initial rows: {len(df)}")

    # Wichtige Kerngrößen müssen existieren
    required = ["u_star", "L", "sigma_v", "WS", "WD", "h_veg", "z0", "h"]
    df = df.replace([np.inf, -np.inf], np.nan)
    df_req = df.dropna(subset=required)
    print(f"   ▸ after dropna(required): {len(df_req)}")

    # ==========================
    # 2) Schrittweise Filter-Diagnose
    # ==========================
    def apply_and_report(mask, label, current_df):
        before = len(current_df)
        current_df = current_df[mask]
        after = len(current_df)
        frac = after / before if before > 0 else np.nan
        print(f"   ▸ {label}: {after}/{before} ({frac:.1%})")
        return current_df

    df_f = df_req

    # u_star
    mask = df_f["u_star"].between(0.05, 2.0)
    df_f = apply_and_report(mask, "u_star between 0.05–2.0", df_f)

    # sigma_v
    mask = df_f["sigma_v"].between(0.05, 10)
    df_f = apply_and_report(mask, "sigma_v between 0.05–10", df_f)

    # WS
    mask = df_f["WS"].between(0.05, 20)
    df_f = apply_and_report(mask, "WS between 0.05–20", df_f)

    # L – hier mal ENTschärfen: nur |L| > 0.01
    mask = df_f["L"].abs() > 0.01
    df_f = apply_and_report(mask, "|L| > 0.01", df_f)

    # z_L constraint von FFP
    df["z_L"] = df["z_L"].clip(lower=-15.5)

    # z0 Verhältnis
    mask = df_f["z0"] < df_f["zm"] / 2  # etwas lockern
    df_f = apply_and_report(mask, "z0 < zm/2", df_f)

    # WD
    mask = df_f["WD"].between(0, 360)
    df_f = apply_and_report(mask, "WD between 0–360", df_f)

    # ==========================
    # 3) Füllwerte für FFP-Robustheit
    # ==========================
    #df_f["u_star"].fillna(0.3, inplace=True)
    #df_f["sigma_v"].fillna(0.5, inplace=True)
    #df_f["h"].fillna(300, inplace=True)
    #df_f["WD"].fillna(method="ffill", inplace=True)

    df_f["site"] = site_name

    print(f"✅ {site_name}: final rows: {len(df_f)}\n")
    return df_f.sort_index().dropna(how="all")


# ---------------------------------------------------------------------
# Station parameters
# ---------------------------------------------------------------------
SITE_PARAMS = {
    "Mole": {"zm": 7.19},
    "Kayoro": {"zm": 3.15},
    "Gorigo": {"zm": 2.65},
    "Janga": {"zm": 3.00},
}


# ---------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------
def build_footprint_inputs(energy_dfs, turb_dict, lai_vegh_dict, save_dir):
    os.makedirs(save_dir, exist_ok=True)
    footprint_dfs = {}

    for site, eb_df in energy_dfs.items():
        print(f"\n▶️ Processing {site}...")

        if site not in turb_dict or site not in lai_vegh_dict:
            print(f"⚠️ Missing data for {site}, skipping.")
            continue

        df_turb = turb_dict[site]
        df_veg = lai_vegh_dict[site]
        zm = SITE_PARAMS.get(site, {}).get("zm", 3.0)

        merged = merge_with_meteo_and_veg(eb_df, df_turb, df_veg, site, zm)
        footprint_dfs[site] = merged

        out_path = os.path.join(save_dir, f"footprint_input_{site}.csv")
        merged.to_csv(out_path, index_label="TIMESTAMP")

        print(f"💾 Saved {site} → {out_path} ({len(merged)} rows)")

    print("\n✅ All footprint input DataFrames created.")
    return footprint_dfs
