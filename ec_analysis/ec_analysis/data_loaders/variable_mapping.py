"""
Standardized variable name mapping for EC data.

This module provides mappings from various column name formats to standardized names
used throughout the ec_analysis package.
"""

from typing import Dict

# Standardized variable names
STANDARD_VARIABLES = {
    # Energy Balance Components
    'Rn': 'Net radiation',
    'SW_in': 'Shortwave radiation in',
    'SW_out': 'Shortwave radiation out',
    'LW_in': 'Longwave radiation in',
    'LW_out': 'Longwave radiation out',
    'LE': 'Latent heat flux',
    'H': 'Sensible heat flux',
    'CO2': 'CO2 flux',
    'G': 'Soil heat flux',
    'G_raw': 'Raw soil heat flux',
    'Gs': 'Storage term',
    'Delta': 'Storage change',
    'Residual': 'Energy balance residual',

    # Soil Variables
    'VWC': 'Volumetric water content',
    'VWC_1': 'Soil water content in 3cm (Janga, Mole)',
    'VWC_2': 'Soil water content in 10cm (Janga, Mole)',
    'VWC_3': 'Soil water content in 35cm (Janga, Mole)',
    'Ts': 'Soil temperature',
    'Ts_1': 'Soil temperature in 3cm (Janga, Mole)',
    'Ts_2': 'Soil temperature in 10cm (Janga, Mole)',
    'Ts_3': 'Soil temperature in 35cm (Janga, Mole)',
    'Cv': 'Volumetric heat capacity',

    # Meteorological Variables
    'Tair': 'Air temperature',
    'Pa': 'Air pressure',
    'RH': 'Relative humidity',
    # Wind (Originalnamen)
    'WS_1_1_1': 'Wind speed (EC)',
    'WS_ms_Avg': 'Wind speed (avg)',
    'WindSpeed': 'Wind speed',
    'WS_Avg': 'Wind speed (avg)',
    'wind_speed': 'Wind speed',
    'WD_1_1_1': 'Wind direction (EC)',
    'WD_Avg': 'Wind direction (avg)',
    'WindDir': 'Wind direction',
    'wind_direction': 'Wind direction',
    'wind_dir': 'Wind direction',
    # WXT sensor variables (Gorigo, Nazinga, Kayoro, Sumbrungu)
    'WXT_Wdmin_Min': 'WXT wind direction min',
    'WXT_Wdavg': 'WXT wind direction avg',
    'WXT_Wdmax_Max': 'WXT wind direction max',
    'WXT_Wsmin_Min': 'WXT wind speed min',
    'WXT_Wsavg_Avg': 'WXT wind speed avg',
    'WXT_Wsmax_Max': 'WXT wind speed max',
    'WXT_airtemp_Avg': 'WXT air temperature',
    'WXT_relhumidity_Avg': 'WXT relative humidity',
    'WXT_airpressure_Avg': 'WXT air pressure',
    'WXT_Ramount_Tot': 'WXT rain amount total',
    'WXT_Rduration_Avg': 'WXT rain duration avg',
    'WXT_Rintensity_Avg': 'WXT rain intensity avg',
    'WXT_Hamount_Tot': 'WXT hail amount total',
    'WXT_Hduration_Avg': 'WXT hail duration avg',
    'WXT_Hintensity_Avg': 'WXT hail intensity avg',
    'P': 'Precipitation',
    'P_pl': 'Precipitation (pluviometer / Acc_RT_NRT_Tot)',
    'P_tb': 'Precipitation (tipping bucket / Rain_mm_Tot)',
    'Precip': 'Precipitation',
    'Rainfall': 'Rainfall',
    'Precip_Tot': 'Precipitation total',
    'Rain_Tot': 'Precipitation rain total',
    'precip_intensity_rain_e': 'Precipitation intensity (rain event)',
    'precip_rain_e': 'Precipitation rain (event)',
    'precip_total_rain_e': 'Precipitation total rain (event)',
    'precip_cv': 'Precipitation from CV sensor',
    'Rs_cv': 'Precipitation from Rs CV sensor',
    'Intensity_RT_Avg': 'Precipitation intensity (real-time avg)',
    'Acc_NRT': 'Precipitation accumulated NRT',
    'Acc_totNRT': 'Precipitation accumulated total NRT',

    # Gas Concentrations
    'CO2': 'Carbon dioxide concentration',
    'H2O': 'Water vapor concentration',

    # Turbulence and Stability Parameters
    'ET': 'Evapotranspiration',
    'L': 'Obukhov length',
    'z-d_L': 'Stability parameter (z-d)/L',
    'ustar': 'Friction velocity',
    'TAU': 'Momentum flux',
    'bowen_ratio': 'Bowen ratio',
    'VPD': 'Vapor pressure deficit',

    # Quality Flags
    'qc_LE': 'Quality flag for LE',
    'qc_TAU': 'Quality flag for TAU',
    'qc_H': 'Quality flag for H',
    'qc_o2_flux': 'Quality flag for CO2',

    # Timestamp
    'TIMESTAMP': 'Timestamp',
}

# Units for standard variable names (for CSV header row)
STANDARD_UNITS: Dict[str, str] = {
    # Energy Balance
    'Rn': 'W/m²',
    'SW_in': 'W/m²',
    'SW_out': 'W/m²',
    'LW_in': 'W/m²',
    'LW_out': 'W/m²',
    'LE': 'W/m²',
    'H': 'W/m²',
    'CO2': 'µmol/m²/s',
    'G': 'W/m²',
    'G_raw': 'W/m²',
    'G_raw_East': 'W/m²',
    'G_raw_Middle': 'W/m²',
    'G_raw_West': 'W/m²',
    'G_plate_1_1_1': 'W/m²',
    'G_plate_2_1_1': 'W/m²',
    'G_plate_3_1_1': 'W/m²',
    'G_1': 'W/m²',
    'G_2': 'W/m²',
    'G_3': 'W/m²',
    'Gs': 'W/m²',
    'Delta': 'W/m²',
    'Residual': 'W/m²',
    # Soil
    'VWC': 'm³/m³',
    'VWC_1': 'm³/m³',
    'VWC_2': 'm³/m³',
    'VWC_3': 'm³/m³',
    'Ts': '°C',
    'Ts_1': '°C',
    'Ts_2': '°C',
    'Ts_3': '°C',
    'Cv': 'J/m³/K',
    # Meteo
    'Tair': '°C',
    'Pa': 'Pa',
    'RH': '%',
    # Wind (Originalnamen)
    'WS_1_1_1': 'm/s',
    'WS_ms_Avg': 'm/s',
    'WindSpeed': 'm/s',
    'WS_Avg': 'm/s',
    'wind_speed': 'm/s',
    'WD_1_1_1': '°',
    'WD_Avg': '°',
    'WindDir': '°',
    'wind_direction': '°',
    'wind_dir': '°',
    'P': 'mm',
    'P_pl': 'mm',
    'P_tb': 'mm',
    'Precip': 'mm',
    'Rainfall': 'mm',
    'Precip_Tot': 'mm',
    'Rain_Tot': 'mm',
    'precip_intensity_rain_e': 'mm/h',
    'precip_rain_e': 'mm',
    'precip_total_rain_e': 'mm',
    'precip_cv': 'mm',
    'Rs_cv': 'mm',
    'Intensity_RT_Avg': 'mm/h',
    'Acc_NRT': 'mm',
    'Acc_totNRT': 'mm',
    # Gas
    'H2O': 'mmol/mol',
    # Turbulence
    'ET': 'mm',
    'L': 'm',
    'z-d_L': '-',
    'ustar': 'm/s',
    'bowen_ratio': '-',
    'VPD': 'hPa',
    # Quality
    'qc_LE': '-',
    'qc_H': '-',
    'qc_o2_flux': '-',
    'qc_TAU': '-',
    'TAU': 'Kg m-2 s-1',
    # Timestamp
    'TIMESTAMP': '',
    # WXT sensor (Gorigo, Nazinga, Kayoro, Sumbrungu)
    'WXT_Wdmin_Min': '°',
    'WXT_Wdavg': '°',
    'WXT_Wdmax_Max': '°',
    'WXT_Wsmin_Min': 'm/s',
    'WXT_Wsavg_Avg': 'm/s',
    'WXT_Wsmax_Max': 'm/s',
    'WXT_airtemp_Avg': '°C',
    'WXT_relhumidity_Avg': '%',
    'WXT_airpressure_Avg': 'mbar',
    'WXT_Ramount_Tot': 'mm/10min',
    'WXT_Rduration_Avg': 'count',
    'WXT_Rintensity_Avg': 'mm/h',
    'WXT_Hamount_Tot': 'hits/10min',
    'WXT_Hduration_Avg': 'count',
    'WXT_Hintensity_Avg': 'hits/h',
}

# Mapping from alternative column names to standard names
COLUMN_MAPPING: Dict[str, str] = {
    # ========================================================================
    # RADIATION COMPONENTS
    # ========================================================================
    # Shortwave In
    'SW_in korrigiert': 'SW_in',
    'SW_in korrigiert ': 'SW_in',
    'SR_in_Avg': 'SW_in',
    'SR_IN_Avg': 'SW_in',
    'SW_IN': 'SW_in',
    'SW_IN_Avg': 'SW_in',

    # Shortwave Out
    'SW_out korrigiert': 'SW_out',
    'SW_out korrigiert ': 'SW_out',
    'SR_out_Avg': 'SW_out',
    'SR_OUT_Avg': 'SW_out',
    'SW_OUT': 'SW_out',
    'SW_OUT_Avg': 'SW_out',

    # Longwave In
    'LW_in_Avg [W/m^2]': 'LW_in',
    'LW_in_Avg [W/m²]': 'LW_in',
    'LW_in_Avg': 'LW_in',
    'IR_in_Avg': 'LW_in',
    'IR_IN_Avg': 'LW_in',
    'LW_IN': 'LW_in',
    'LW_IN_Avg': 'LW_in',

    # Longwave Out
    'LW_out_Avg [W/m^2]': 'LW_out',
    'LW_out_Avg [W/m²]': 'LW_out',
    'LW_out_Avg': 'LW_out',
    'IR_out_Avg': 'LW_out',
    'IR_OUT_Avg': 'LW_out',
    'LW_OUT': 'LW_out',
    'LW_OUT_Avg': 'LW_out',

    # ========================================================================
    # HEAT FLUXES
    # ========================================================================
    # Latent Heat Flux
    'LvE': 'LE',
    'LvE[W/m²]': 'LE',
    'LvE[W/m^2]': 'LE',
    'LvE[W/m_]': 'LE',
    'LvE[W/m_]      ': 'LE',
    #'LE_1_1_1': 'LE',
    'LE_Avg': 'LE',
    'LE': 'LE',

    # Sensible Heat Flux
    'HTs': 'H',
    'HTs[W/m²]': 'H',
    'HTs[W/m^2]': 'H',
    'HTs[W/m_]': 'H',
    'HTs[W/m_]      ': 'H',
    #'H_1_1_1': 'H',
    'H_Avg': 'H',
    'H': 'H',

    # CO2 Flux (EddyPro standard names)
    'co2_flux': 'CO2',
    'CO2_flux': 'CO2',
    'CO2': 'CO2',
    'co2': 'CO2',
    #'FC_1_1_1': 'CO2',
    #'FC_SSITC_TEST': 'CO2',
    #'un_co2_flux': 'CO2',

    # ========================================================================
    # SOIL HEAT FLUX
    # ========================================================================
    'G ': 'G',
    'G': 'G',  # Keep as is if already standard
    'GHF Mean': 'G',
    'G_1': 'G',
    'G_2': 'G',
    'G_3': 'G',

    # Raw Soil Heat Flux Sensors
    'H_Flux_sc_8_Ost_Avg [W/m^2]': 'G_raw_East',
    'H_Flux_sc_8_Ost_Avg': 'G_raw_East',
    'H_Flux_sc_8_East_Avg': 'G_raw_East',
    'H_Flux_sc_8_Mitte_Avg [W/m^2]': 'G_raw_Middle',
    'H_Flux_sc_8_Mitte_Avg': 'G_raw_Middle',
    'H_Flux_sc_8_Middle_Avg': 'G_raw_Middle',
    'H_Flux_sc_8_West_Avg [W/m^2]': 'G_raw_West',
    'H_Flux_sc_8_West_Avg': 'G_raw_West',
    'H_Flux_8_Middle_Avg': 'G_raw_Middle',
    'H_Flux_8_East_Avg': 'G_raw_East',
    'H_Flux_8_West_Avg': 'G_raw_West',

    # Storage Term
    'Gs ': 'Gs',
    'Gs': 'Gs',

    # ========================================================================
    # SOIL VARIABLES
    # ========================================================================
    # Volumetric Water Content
    'VW_1_Avg': 'VWC_1',
    'VW_2_Avg': 'VWC_2',
    'VW_3_Avg': 'VWC_3',
    'VW Mean': 'VWC',
    'SWC_1_1_1': 'VWC_1',
    'SWC_2_1_1': 'VWC_2',
    'SWC_3_1_1': 'VWC_3',
    'SWC_1': 'VWC_1',
    'SWC_2': 'VWC_2',
    'SWC_3': 'VWC_3',
    # Janga, Mole: VWC_Avg = 3cm, VWC_2_Avg = 10cm, VWC_3_Avg = 35cm
    'VWC_Avg': 'VWC_1',
    'VWC_2_Avg': 'VWC_2',
    'VWC_3_Avg': 'VWC_3',

    # Soil Temperature
    'TCAV_C_Avg(1)': 'Ts_1',
    'TCAV_C_Avg(1) [DegC]': 'Ts_1',
    'TCAV_C_Avg(2)': 'Ts_2',
    'TCAV_C_Avg(2) [DegC]': 'Ts_2',
    'TCAV_C_Avg(3)': 'Ts_3',
    'TCAV_C_Avg(3) [DegC]': 'Ts_3',
    'TS_1_1_1': 'Ts_1',
    'TS_2_1_1': 'Ts_2',
    'TS_3_1_1': 'Ts_3',
    'Tsoil_f': 'Ts',
    'T_Avg': 'Ts',  # If only one layer
    # Janga, Mole: T_Avg = 3cm, T_2_Avg = 10cm, T_3_Avg = 35cm
    'T_2_Avg': 'Ts_2',
    'T_3_Avg': 'Ts_3',

    # ========================================================================
    # METEOROLOGICAL VARIABLES
    # ========================================================================
    # Air Temperature
    'Ta': 'Tair',
    'Tair': 'Tair',
    'AirTC_Avg': 'Tair',
    #'TA_1_1_1': 'Tair',
    #'T_Avg': 'Tair',  # If used for air temp
    'AirTemp': 'Tair',
    'air_temperature': 'Tair',

    # Air Pressure
    'Press_Avg': 'Pa',
    'PA_1_1_1': 'Pa',
    'BP_mmHg_Avg': 'Pa',
    'Pressure': 'Pa',
    'Barometric_Pressure': 'Pa',
    'air_pressure': 'Pa',

    # Wind (Originalnamen)
    'WS_1_1_1': 'WS_1_1_1',
    'WS_ms_Avg': 'WS_ms_Avg',
    'WindSpeed': 'WindSpeed',
    'WS_Avg': 'WS_Avg',
    'wind_speed': 'wind_speed',
    'WD_1_1_1': 'WD_1_1_1',
    'WD_Avg': 'WD_Avg',
    'WindDir': 'WindDir',
    'wind_direction': 'wind_direction',
    'wind_dir': 'wind_dir',

    # Relative Humidity
    'RH_1_1_1': 'RH',
    'RH_2_1_1': 'RH_2',
    'RH_3_1_1': 'RH_3',
    'RH_Avg': 'RH',
    'relhumidity_Avg': 'RH',
    'amb_RH': 'RH',
    'RH_PI_F_1_1_1': 'RH',  # AmeriFlux / Campbell CR6
    'RH_PI_F': 'RH',

    # Precipitation (Originalnamen)
    'Acc_RT_NRT_Tot': 'P_pl',
    'Rain_mm_Tot': 'P_tb',
    'P_RAIN': 'P',
    'PRECIPITATION': 'P',
    'Precip': 'Precip',
    'Rainfall': 'Rainfall',
    'Precip_Tot': 'Precip_Tot',
    'Rain_Tot': 'Rain_Tot',
    # CR6 CR6Mole/CR6Janga Public.dat precipitation (Originalnamen)
    'precip_intensity_rain_e': 'precip_intensity_rain_e',
    'precip_rain_e': 'precip_rain_e',
    'precip_total_rain_e': 'precip_total_rain_e',
    'precip_cv': 'precip_cv',
    'Rs_cv': 'Rs_cv',
    'Intensity_RT_Avg': 'Intensity_RT_Avg',
    'Acc_NRT': 'Acc_NRT',
    'Acc_totNRT': 'Acc_totNRT',

    # ========================================================================
    # GAS CONCENTRATIONS
    # ========================================================================
    # CO2
    'CO2_1_1_1': 'CO2',
    'CO2_dry': 'CO2',
    'CO2_Avg': 'CO2',
    'co2': 'CO2',

    # H2O
    'H2O_1_1_1': 'H2O',
    'H2O_dry': 'H2O',
    'H2O_Avg': 'H2O',
    'h2o': 'H2O',

    # ========================================================================
    # QUALITY FLAGS
    # ========================================================================
    # LE Quality Flags
    'Flag(LvE)': 'qc_LE',
    'Flag_LvE': 'qc_LE',
    'LvE_Flag': 'qc_LE',
    'qc_LvE': 'qc_LE',
    'qc_LE_1_1_1': 'qc_LE',

    # H Quality Flags
    'Flag(HTs)': 'qc_H',
    'Flag_HTs': 'qc_H',
    'HTs_Flag': 'qc_H',
    'qc_HTs': 'qc_H',
    'qc_H_1_1_1': 'qc_H',

    # CO2 Quality Flags
    'qc_co2_flux': 'qc_o2_flux',
    'qc_CO2_flux': 'qc_o2_flux',
    'qc_FC': 'qc_o2_flux',
    'Flag(CO2)': 'qc_o2_flux',
    'Flag_CO2': 'qc_o2_flux',

    # ========================================================================
    # TURBULENCE AND STABILITY PARAMETERS
    # ========================================================================
    # Evapotranspiration
    'ET': 'ET',

    # Obukhov Length
    'L': 'L',
    'MO_LENGTH': 'L',
    'obukhov_length': 'L',

    # Stability Parameter (z-d)/L
    '(z-d)/L': 'z-d_L',
    'z-d_L': 'z-d_L',
    'zeta': 'z-d_L',
    'stability': 'z-d_L',

    # Friction Velocity
    'u*': 'ustar',
    'ustar': 'ustar',
    'u_star': 'ustar',
    'friction_velocity': 'ustar',

    # Momentum flux (tau)
    'tau': 'TAU',
    'TAU': 'TAU',
    'momentum_flux': 'TAU',
    'Tau': 'TAU',

    # TAU Quality Flag
    'qc_tau': 'qc_TAU',
    'qc_TAU': 'qc_TAU',
    'qc_Tau': 'qc_TAU',
    'Flag(tau)': 'qc_TAU',
    'Flag_tau': 'qc_TAU',
    'tau_Flag': 'qc_TAU',

    # Bowen Ratio
    'bowen_ratio': 'bowen_ratio',
    'bowen': 'bowen_ratio',
    'Bowen': 'bowen_ratio',

    # Vapor Pressure Deficit
    'VPD': 'VPD',
    'vpd': 'VPD',
    'vapor_pressure_deficit': 'VPD',

    # ========================================================================
    # TIMESTAMP
    # ========================================================================
    'T_begin': 'TIMESTAMP',
    'Date': 'TIMESTAMP',
    'Time': 'TIMESTAMP',
    'timestamp': 'TIMESTAMP',
}


def normalize_column_name(col_name: str) -> str:
    """
    Normalize a column name to standard format.

    Parameters
    ----------
    col_name : str
        Original column name (may have trailing spaces, unit suffixes, etc.)

    Returns
    -------
    str
        Normalized column name (trimmed, standardized)
    """
    if not isinstance(col_name, str):
        return col_name

    # Strip whitespace
    normalized = col_name.strip()

    # Check if it's in the mapping
    if normalized in COLUMN_MAPPING:
        return COLUMN_MAPPING[normalized]

    # Try case-insensitive match
    for alt_name, std_name in COLUMN_MAPPING.items():
        if alt_name.lower() == normalized.lower():
            return std_name

    # Return original if no mapping found
    return normalized


def map_dataframe_columns(df, inplace: bool = False):
    """
    Map DataFrame columns to standardized names.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with columns to map
    inplace : bool, default=False
        If True, modify DataFrame in place

    Returns
    -------
    pd.DataFrame
        DataFrame with mapped column names
    """
    import pandas as pd

    if not inplace:
        df = df.copy()

    # Create mapping dictionary for columns that exist
    rename_dict = {}
    for col in df.columns:
        normalized = normalize_column_name(str(col))
        if normalized != col:
            rename_dict[col] = normalized

    if rename_dict:
        df.rename(columns=rename_dict, inplace=True)

    return df


def get_standard_variable_description(var_name: str) -> str:
    """
    Get description for a standard variable name.

    Parameters
    ----------
    var_name : str
        Standard variable name

    Returns
    -------
    str
        Description of the variable
    """
    return STANDARD_VARIABLES.get(var_name, f"Unknown variable: {var_name}")
