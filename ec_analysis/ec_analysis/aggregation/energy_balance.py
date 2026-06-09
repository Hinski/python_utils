"""Energy balance calculations for EC data."""
import json
from pathlib import Path
import pandas as pd
import numpy as np
from typing import Union, List, Dict, Optional
from .time_aggregation import safe_slice


def apply_mole_sw_in_correction(SW_in: pd.Series, site_name: str = "") -> pd.Series:
    """
    Apply SW_in correction for Mole station.
    
    Mole station requires a correction factor: SW_in * 10.15 / 16.15
    
    Parameters
    ----------
    SW_in : pd.Series
        Shortwave radiation in (W/m²)
    site_name : str, default=""
        Site name to check if correction should be applied
    
    Returns
    -------
    pd.Series
        Corrected SW_in (only corrected if site_name == 'Mole')
    """
    if site_name == 'Mole':
        return SW_in * 10.15 / 16.15
    return SW_in


def build_energy_balance_df(
    SW_in: pd.Series,
    SW_out: pd.Series,
    LW_in: pd.Series,
    LW_out: pd.Series,
    LE: pd.Series,
    H: pd.Series,
    G: pd.Series,
    Delta: pd.Series,
    start: Union[str, pd.Timestamp],
    end: Union[str, pd.Timestamp],
    site_name: str = ""
) -> pd.DataFrame:
    """
    Build Energy Balance DataFrame with all components.
    
    Parameters
    ----------
    SW_in, SW_out : pd.Series
        Shortwave radiation in/out (W/m²)
    LW_in, LW_out : pd.Series
        Longwave radiation in/out (W/m²)
    LE : pd.Series
        Latent heat flux (W/m²)
    H : pd.Series
        Sensible heat flux (W/m²)
    G : pd.Series
        Ground heat flux (W/m²)
    Delta : pd.Series
        Storage change (W/m²)
    start, end : str | pd.Timestamp
        Date range
    site_name : str, default=""
        Site name for metadata
    
    Returns
    -------
    pd.DataFrame
        DataFrame with all energy balance components and derived values
    """
    # Apply Mole SW_in correction if needed
    SW_in_corrected = apply_mole_sw_in_correction(SW_in, site_name)
    
    # Slice all components to date range
    df = pd.DataFrame({
        "SW_in": safe_slice(SW_in_corrected, start, end),
        "SW_out": safe_slice(SW_out, start, end),
        "LW_in": safe_slice(LW_in, start, end),
        "LW_out": safe_slice(LW_out, start, end),
        "LE": safe_slice(LE, start, end),
        "H": safe_slice(H, start, end),
        "G": safe_slice(G, start, end),
        "Delta": safe_slice(Delta, start, end)
    })
    
    # For energy balance calculation and closure analysis, require all components
    # Drop rows where any component is NaN (needed for proper energy balance closure)
    df = df.dropna()
    
    if df.empty:
        print(f"⚠️ Warning: No overlapping data for {site_name} ({start}–{end})")
        return pd.DataFrame()
    
    # Calculate derived components
    df["Rn"] = (df["SW_in"] - df["SW_out"]) + (df["LW_in"] - df["LW_out"])
    df["Residual"] = df["Rn"] - (df["LE"] + df["H"] + df["G"] + df["Delta"])
    
    # Add metadata
    df.attrs.update({"site": site_name, "start": start, "end": end})
    
    if site_name:
        print(f"✅ {site_name}: Energy balance DataFrame created ({len(df)} records)")
    
    return df


def calculate_storage_change(
    ah: pd.Series,
    T: pd.Series,
    zm: float,
    veg_h: Union[float, pd.Series],
    Ts: pd.Series,
    start: Union[str, pd.Timestamp],
    end: Union[str, pd.Timestamp]
) -> pd.Series:
    """
    Calculate storage change (Delta) for energy balance.
    
    Delta consists of three components:
    - dSl: Change in latent heat storage
    - dSh: Change in sensible heat storage
    - dSb: Change in biomass storage
    
    Parameters
    ----------
    ah : pd.Series
        Absolute humidity (g/m³)
    T : pd.Series
        Air temperature (°C)
    zm : float
        Measurement height (m)
    veg_h : float | pd.Series
        Vegetation height (m)
    Ts : pd.Series
        Soil temperature (°C)
    start, end : str | pd.Timestamp
        Date range
    
    Returns
    -------
    pd.Series
        Total storage change Delta (W/m²) = dSl + dSh + dSb
    """
    # Slice all series to date range
    ah = safe_slice(ah, start, end)
    T = safe_slice(T, start, end)
    Ts = safe_slice(Ts, start, end)
    
    if isinstance(veg_h, pd.Series):
        veg_h = safe_slice(veg_h, start, end)
    
    # Calculate time difference in seconds
    dt = T.index.to_series().diff().dt.total_seconds()
    
    # ---- dSl: Change in latent heat storage ----
    def calculate_rhov(ah, T):
        """Calculate water vapor density."""
        T_kelvin = T + 273.15
        rhov = (ah * 100) / (461.5 * T_kelvin)
        return rhov
    
    rhov = calculate_rhov(ah, T)
    
    def calculate_dSl(rhov, zm):
        """Calculate change in latent heat storage."""
        L = 2.5e6  # Latent heat of evaporation [J/kg]
        dSl = L * zm * (rhov.diff() / dt)
        return dSl
    
    dSl = calculate_dSl(rhov, zm)
    
    # ---- dSh: Change in sensible heat storage ----
    def calculate_dSh(T, zm):
        """Calculate change in sensible heat storage."""
        pa = 1.225  # Density of dry air [kg/m³]
        cp = 1005   # Specific heat capacity of dry air [J/(kg*K)]
        dSh = pa * cp * zm * (T.diff() / dt)
        return dSh
    
    dSh = calculate_dSh(T, zm)
    
    # ---- dSb: Change in biomass storage ----
    def calculate_dSb(Ts, zh):
        """Calculate change in biomass storage."""
        Ts_kelvin = Ts + 273.15
        cb = 17  # Specific heat capacity of biomass [J/(kg K)]
        mv = 0.8 * zh  # Biomass volume
        dSb = cb * mv * (Ts_kelvin.diff() / dt)
        return dSb
    
    dSb = calculate_dSb(Ts, veg_h)
    
    # Total storage change
    Delta = dSl + dSh + dSb
    
    return Delta


def find_columns_flexible(df: pd.DataFrame, column_names: List[str]) -> List[str]:
    """
    Find columns in DataFrame, trying both with and without unit suffixes.
    
    Searches for columns with patterns like:
    - Exact match
    - With unit suffixes: " [DegC]", " [W/m^2]", " [W/m_]"
    - German names: "Ost" -> "East", "Mitte" -> "Middle", "West" -> "West"
    - Also handles reverse: if config has suffix, tries without
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame to search in
    column_names : List[str]
        List of column names to search for (may or may not have unit suffixes)
    
    Returns
    -------
    List[str]
        List of found column names (in order of preference)
    """
    found_columns = []
    available_cols = set(df.columns)
    unit_suffixes = [' [DegC]', ' [W/m^2]', ' [W/m_]', ' [W/m²]']
    
    for col_name in column_names:
        # Try exact match first
        if col_name in available_cols:
            found_columns.append(col_name)
            continue
        
        # Check if col_name already has a unit suffix
        has_suffix = any(col_name.endswith(suffix) for suffix in unit_suffixes)
        
        if has_suffix:
            # Try without suffix
            base_name = col_name
            for suffix in unit_suffixes:
                if base_name.endswith(suffix):
                    base_name = base_name[:-len(suffix)]
                    break
            if base_name in available_cols:
                found_columns.append(base_name)
                continue
        
        # Try with unit suffixes (if not already tried)
        if not has_suffix:
            found = False
            for suffix in unit_suffixes:
                candidate = col_name + suffix
                if candidate in available_cols:
                    found_columns.append(candidate)
                    found = True
                    break
            if found:
                continue
        
        # Try German name variations
        if '_East_Avg' in col_name or col_name.endswith('_East_Avg'):
            # Try Ost
            candidate = col_name.replace('_East_Avg', '_Ost_Avg')
            if candidate in available_cols:
                found_columns.append(candidate)
                continue
            # Try with unit suffix
            for suffix in unit_suffixes:
                candidate_suffixed = candidate + suffix
                if candidate_suffixed in available_cols:
                    found_columns.append(candidate_suffixed)
                    break
            else:
                continue
        elif '_Middle_Avg' in col_name or col_name.endswith('_Middle_Avg'):
            # Try Mitte
            candidate = col_name.replace('_Middle_Avg', '_Mitte_Avg')
            if candidate in available_cols:
                found_columns.append(candidate)
                continue
            # Try with unit suffix
            for suffix in unit_suffixes:
                candidate_suffixed = candidate + suffix
                if candidate_suffixed in available_cols:
                    found_columns.append(candidate_suffixed)
                    break
            else:
                continue
        elif '_West_Avg' in col_name or col_name.endswith('_West_Avg'):
            # West is the same in German, but try with unit suffix if not already tried
            if not has_suffix:
                for suffix in unit_suffixes:
                    candidate = col_name + suffix
                    if candidate in available_cols:
                        found_columns.append(candidate)
                        break
    
    return found_columns


def load_soil_heat_flux_config(config_path: Optional[Path] = None) -> Dict:
    """
    Load soil heat flux configuration from JSON file.
    
    Parameters
    ----------
    config_path : Path | None, optional
        Path to config file. If None, uses default config in aggregation module.
    
    Returns
    -------
    Dict
        Dictionary with station configurations
    """
    if config_path is None:
        # Use default config file in aggregation module
        module_dir = Path(__file__).parent
        config_path = module_dir / "soil_heat_flux_config.json"
    
    with open(config_path, 'r') as f:
        return json.load(f)


def get_station_config(station: str, config_path: Optional[Path] = None) -> Dict:
    """
    Get configuration for a specific station.
    
    Parameters
    ----------
    station : str
        Station name (e.g., 'Nazinga', 'Mole', 'Kayoro')
    config_path : Path | None, optional
        Path to config file. If None, uses default config.
    
    Returns
    -------
    Dict
        Station-specific configuration
    
    Raises
    ------
    ValueError
        If station not found in config
    """
    config = load_soil_heat_flux_config(config_path)
    
    if station not in config:
        available = ', '.join(config.keys())
        raise ValueError(
            f"Station '{station}' not found in config. "
            f"Available stations: {available}"
        )
    
    return config[station]


def calculate_soil_heat_flux(
    df: pd.DataFrame,
    station: Optional[str] = None,
    vwc_columns: Optional[List[str]] = None,
    ts_columns: Optional[List[str]] = None,
    g_raw_columns: Optional[List[str]] = None,
    fm: Optional[float] = None,
    fo: Optional[float] = None,
    g_min: Optional[float] = None,
    g_max: Optional[float] = None,
    ts_min: Optional[float] = None,
    ts_max: Optional[float] = None,
    vwc_scale: Optional[float] = None,
    config_path: Optional[Path] = None,
    return_components: bool = False
) -> pd.Series | pd.DataFrame:
    """
    Calculate soil heat flux (G) from sensor measurements.
    
    G = G_raw + Gs, where Gs is the storage term calculated from
    soil temperature change and volumetric heat capacity.
    
    Can use station-specific configuration from JSON file, or manual parameters.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with soil sensor data
    station : str | None, optional
        Station name (e.g., 'Nazinga', 'Mole'). If provided, loads config from JSON.
        If None, requires manual parameters.
    vwc_columns : List[str] | None, optional
        Column names for volumetric water content (VWC). Required if station=None.
    ts_columns : List[str] | None, optional
        Column names for soil temperature. Required if station=None.
    g_raw_columns : List[str] | None, optional
        Column names for raw soil heat flux sensors. Required if station=None.
    fm : float | None, optional
        Mineral fraction of soil. Default from config if station provided.
    fo : float | None, optional
        Organic fraction of soil. Default from config if station provided.
    g_min, g_max : float | None, optional
        Valid range for G values (W/m²). Default from config if station provided.
    ts_min, ts_max : float | None, optional
        Valid range for soil temperature (°C). Applied if provided.
    vwc_scale : float | None, optional
        Scale factor for VWC (e.g., 100 for Janga). Applied if provided.
    config_path : Path | None, optional
        Path to config file. If None, uses default config.
    return_components : bool, default=False
        If True, returns DataFrame with components, else returns only G
    
    Returns
    -------
    pd.Series | pd.DataFrame
        Soil heat flux G (W/m²), or DataFrame with components if return_components=True
    
    Examples
    --------
    >>> # Using station config
    >>> G = calculate_soil_heat_flux(df, station='Nazinga')
    
    >>> # Manual parameters
    >>> G = calculate_soil_heat_flux(
    ...     df,
    ...     vwc_columns=['VW_1_Avg', 'VW_2_Avg'],
    ...     ts_columns=['TCAV_C_Avg(1)'],
    ...     g_raw_columns=['H_Flux_sc_8_Ost_Avg'],
    ...     fm=0.5171, fo=0.016
    ... )
    """
    # Load station config if provided
    if station is not None:
        config = get_station_config(station, config_path)
        vwc_columns = config.get('vwc_columns', vwc_columns)
        ts_columns = config.get('ts_columns', ts_columns)
        g_raw_columns = config.get('g_raw_columns', g_raw_columns)
        fm = config.get('fm', fm) if fm is None else fm
        fo = config.get('fo', fo) if fo is None else fo
        g_min = config.get('g_min', g_min) if g_min is None else g_min
        g_max = config.get('g_max', g_max) if g_max is None else g_max
        ts_min = config.get('ts_min', ts_min) if ts_min is None else ts_min
        ts_max = config.get('ts_max', ts_max) if ts_max is None else ts_max
        vwc_scale = config.get('vwc_scale', vwc_scale) if vwc_scale is None else vwc_scale
    
    # Validate required parameters
    if vwc_columns is None or ts_columns is None or g_raw_columns is None:
        raise ValueError(
            "Must provide either 'station' or all of: vwc_columns, ts_columns, g_raw_columns"
        )
    
    if fm is None or fo is None:
        raise ValueError("Must provide 'fm' and 'fo' (or use 'station' parameter)")
    
    if g_min is None:
        g_min = -200
    if g_max is None:
        g_max = 400
    
    # Find columns flexibly (with/without unit suffixes, German/English names)
    vwc_cols_found = find_columns_flexible(df, vwc_columns)
    ts_cols_found = find_columns_flexible(df, ts_columns)
    g_raw_cols_found = find_columns_flexible(df, g_raw_columns)
    
    # Check if we found the required columns
    if not vwc_cols_found:
        raise KeyError(f"VWC columns not found. Looked for: {vwc_columns}")
    if not ts_cols_found:
        raise KeyError(f"Temperature columns not found. Looked for: {ts_columns}")
    if not g_raw_cols_found:
        raise KeyError(f"G_raw columns not found. Looked for: {g_raw_columns}")
    
    # Calculate average VWC
    vwc = df[vwc_cols_found].mean(axis=1)
    
    # Apply VWC scale if needed (e.g., Janga: SWC_1 / 100)
    if vwc_scale is not None:
        vwc = vwc / vwc_scale
    
    vwc = vwc.where((vwc > 0) & (vwc < 0.51))
    
    # Calculate average soil temperature
    Ts = df[ts_cols_found].mean(axis=1)
    
    # Apply temperature range if specified (e.g., Kayoro)
    if ts_min is not None:
        Ts = Ts.where(Ts > ts_min)
    if ts_max is not None:
        Ts = Ts.where(Ts < ts_max)
    
    # Smooth noise with rolling window
    Ts = Ts.rolling(window=3, center=True, min_periods=1).mean()
    
    # Calculate volumetric heat capacity
    Cv = (1.9 * fm + 2.47 * fo + 4.12 * vwc) * 10**6
    
    # Calculate raw soil heat flux (average of sensors)
    G_raw = df[g_raw_cols_found].mean(axis=1)
    G_raw = G_raw.where((G_raw > g_min) & (G_raw < g_max))
    
    # Calculate storage term (Gs)
    # Formula: Gs = Cv * (dT/dt) * depth
    # where dT/dt = delta_Ts / delta_t (in seconds)
    # This represents the heat storage in the soil layer above the heat flux plate
    if len(Ts) > 1:
        # Calculate time differences in seconds
        time_diffs = Ts.index.to_series().diff().dt.total_seconds()
        # Handle first row (NaN) and ensure we have valid time differences
        if time_diffs.notna().any():
            median_interval = time_diffs.median()
            time_diffs = time_diffs.fillna(median_interval)
            # Ensure reasonable time intervals (between 5 min and 2 hours)
            time_diffs = time_diffs.where((time_diffs >= 300) & (time_diffs <= 7200))
            time_diffs = time_diffs.fillna(median_interval)
        else:
            # Fallback: assume 30-minute intervals
            time_diffs = pd.Series(1800.0, index=Ts.index)
        
        # Calculate temperature change (limit to reasonable values: max 2 K change)
        delta_Ts = Ts.diff().where(lambda x: x.abs() < 2)
        
        # Calculate dT/dt (temperature change per second)
        dT_dt = delta_Ts / time_diffs  # K/s
        
        # Depth factor: 0.08 m (8 cm) - typical depth for soil heat flux plates
        # This is the depth of the soil layer above the heat flux plate
        depth = 0.08  # meters
        
        # Calculate storage term: Gs = Cv * (dT/dt) * depth
        # Cv is in J/(m³·K), dT/dt in K/s, depth in m
        # Result: (J/(m³·K)) * (K/s) * m = J/(m²·s) = W/m²
        Gs = Cv * dT_dt * depth
        
        # Ensure Gs has same index as G_raw for proper alignment
        Gs = Gs.reindex(G_raw.index, fill_value=0.0)
    else:
        # Fallback if insufficient data
        Gs = pd.Series(0.0, index=G_raw.index)
    
    # Ensure Gs is finite (handle any inf or very large values)
    Gs = Gs.replace([np.inf, -np.inf], np.nan)
    # Fill NaN values with 0 (no storage change)
    Gs = Gs.fillna(0.0)
    
    # Total soil heat flux: G = G_raw + Gs
    # Ensure proper alignment: both should have the same index
    # Use fill_value=0 for Gs where G_raw exists but Gs doesn't
    Gs_aligned = Gs.reindex(G_raw.index, fill_value=0.0)
    G = G_raw + Gs_aligned
    
    # Apply quality filter
    G = G.where((G >= g_min) & (G <= g_max))
    
    if return_components:
        return pd.DataFrame({
            "G_raw": G_raw,
            "G": G,
            "Ts_3cm": Ts,
            "VWC": vwc,
            "Gs": Gs,
            "Cv": Cv
        })
    
    return G

