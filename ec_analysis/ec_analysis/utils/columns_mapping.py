"""Column name mappings for EC data files."""
import pandas as pd
from typing import Dict, List

# Standard column names for result files
RESULT_COLUMNS = [
    'T_end', 'u[m/s]', 'v[m/s]', 'w[m/s]', 'Ts[°C]', 'Tp[°C]', 'a[g/m³]',
    'CO2[mmol/m³]', 'T_ref[°C]', 'a_ref[g/m³]', 'p_ref[hPa]', 'Var[u]',
    'Var[v]', 'Var[w]', 'Var[Ts]', 'Var[Tp]', 'Var[a]', 'Var[CO2]',
    "Cov[u'v']", "Cov[v'w']", "Cov[u'w']", "Cov[u'Ts']", "Cov[v'Ts']",
    "Cov[w'Ts']", "Cov[u'Tp']", "Cov[v'Tp']", "Cov[w'Tp']",
    "Cov[u'a']", "Cov[v'a']", "Cov[w'a']", "Cov[u'CO2']", "Cov[v'CO2']",
    "Cov[w'CO2']", '???', 'dir[°]', 'ustar[m/s]', 'HTs[W/m²]', 'HTp[W/m²]',
    'LvE[W/m²]', 'z/L', 'z/L-virt', 'Flag(ustar)', 'Flag(HTs)',
    'Flag(HTp)', 'Flag(LvE)', 'Flag(wCO2)', 'T_mid', 'FCstor[mmol/m²s]',
    'NEE[mmol/m²s]', 'Footprint_trgt_1', 'Footprint_trgt_2',
    'Footprnt_xmax[m]', ' r_err_ustar[%]', 'r_err_HTs[%]',
    'r_err_LvE[%]', 'r_err_co2[%]', 'noise_ustar[%]', 'noise_HTs[%]',
    'noise_LvE[%]', 'noise_co2[%]', 'Filler_to_reach61'
]

# Standard column names for CR1000 logger files
CR1000_COLUMNS = [
    'BattV_Avg', 'PTemp_C_Avg', 'VW_1_Avg', 'PA_uS_1_Avg', 'VW_2_Avg',
    'PA_uS_2_Avg', 'VW_3_Avg', 'PA_uS_3_Avg', 'Rain_mm_Tot',
    'TCAV_C_Avg(1)', 'TCAV_C_Avg(2)', 'TCAV_C_Avg(3)',
    'Intensity_RT_Avg', 'Acc_RT_NRT_Tot', 'Acc_NRT', 'Acc_totNRT',
    'Bucket_RT', 'Bucket_NRT', 'Temp_load_cell_Avg',
    'H_Flux_sc_8_Ost_Avg', 'H_Flux_sc_8_West_Avg',
    'H_Flux_sc_8_Mitte_Avg', 'shf_cal(1)', 'shf_cal(2)', 'shf_cal(3)'
]

# Standard column names for radiation files
RADIATION_COLUMNS = [
    'TIMESTAMP', 'RECORD', 'SR_out_Avg', 'SR_in_Avg', 'IR_out_Avg',
    'IR_in_Avg', 'CNR4TC_Avg', 'CNR4TK_Avg', 'NetRs_Avg', 'NetRl_Avg',
    'Albedo_Avg', 'OutTot_Avg', 'InTot_Avg', 'NetTot_Avg', 'IR_OutCo_Avg',
    'IR_InCo_Avg'
]

def get_column_mapping(filetype: str) -> List[str]:
    """
    Get standard column names for a file type.

    Parameters
    ----------
    filetype : str
        One of: 'result' (TK3 output), 'cr1000', 'radiation'
        Note: 'result' refers to TK3 output files, NOT EddyPro

    Returns
    -------
    List[str]
        List of standard column names

    Raises
    ------
    ValueError
        If filetype is not supported
    """
    filetype = filetype.lower()

    if filetype == 'result':
        return RESULT_COLUMNS.copy()
    elif filetype == 'cr1000':
        return CR1000_COLUMNS.copy()
    elif filetype == 'radiation':
        return RADIATION_COLUMNS.copy()
    else:
        raise ValueError(
            f"Unsupported filetype: {filetype}. "
            f"Supported: 'result' (TK3), 'cr1000', 'radiation'"
        )


def apply_column_names(df: pd.DataFrame, filetype: str) -> pd.DataFrame:
    """
    Assign standard column names to DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with raw column names
    filetype : str
        One of: 'result' (TK3 output), 'cr1000', 'radiation'
        Note: EddyPro files already have standard column names and don't need mapping

    Returns
    -------
    pd.DataFrame
        DataFrame with standardized column names

    Raises
    ------
    ValueError
        If column count doesn't match expected count
    """
    # Get expected column names
    wanted = get_column_mapping(filetype)
    
    # Get current column names
    data_cols = df.columns.tolist()
    
    # Check if column count matches
    if len(data_cols) != len(wanted):
        print("⚠️ Column count mismatch: cannot safely rename.")
        print(f"  → df has      {len(data_cols)} columns")
        print(f"  → expected    {len(wanted)} columns")
        print("  Rename aborted.")
        return df
    
    # Apply column names
    df = df.copy()
    df.columns = wanted
    return df