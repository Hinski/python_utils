#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interaktive Plots für Stationsdaten über den gesamten Zeitraum.

Erstellt interaktive Plotly-Plots für:
- Bodenvariablen (VWC, Soil Temperature, Soil Heat Flux) - ein Fenster pro Sensor
- Strahlungsvariablen (SR_in, SR_out, IR_in, IR_out) - ein Fenster pro Variable
- Meteorologische Variablen (Precipitation, Air Temp, Wind Speed, Pressure, Humidity)
- Energieflüsse (Latent Heat Flux, Sensible Heat Flux) - wenn vorhanden
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path
import argparse

# Konfiguration
DATA_DIR = Path.home() / "Data" / "merged_long"
RAW_DATA_DIR = Path.home() / "Data"  # Für CR6-Dateien
STATIONS = ["Gorigo", "Janga", "Kayoro", "Mole", "Nazinga"]
CR6_STATIONS = ["Janga", "Mole"]  # Stationen mit CR6-Dateien

# Variablengruppen
SOIL_VARIABLES = {
    'VWC': ['VWC_Avg', 'VWC_1_Avg', 'VWC_2_Avg', 'VWC_3_Avg', 
            'VW_1_Avg', 'VW_2_Avg', 'VW_3_Avg',
            'cs65x_wc(1)', 'cs65x_wc(2)', 'cs65x_wc(3)'],  # CR6
    'Soil_Temp': ['T_Avg', 'T_1_Avg', 'T_2_Avg', 'T_3_Avg',
                  'TCAV_C_Avg(1)', 'TCAV_C_Avg(2)', 'TCAV_C_Avg(3)',
                  'cs65x_tmpr(1)', 'cs65x_tmpr(2)', 'cs65x_tmpr(3)'],  # CR6
    'Soil_Heat_Flux': ['H_Flux_sc_8_East_Avg', 'H_Flux_sc_8_Middle_Avg', 
                       'H_Flux_sc_8_West_Avg', 'H_Flux_8_West_Avg',
                       'H_Flux_8_Middle_Avg', 'H_Flux_8_East_Avg',
                       'shf_plate(1)', 'shf_plate(2)', 'shf_plate(3)',
                       'G_plate_1_1_1', 'G_plate_2_1_1', 'G_plate_3_1_1',
                       'G_1_1_1', 'G_2_1_1', 'G_3_1_1']  # CR6
}

RADIATION_VARIABLES = {
    'SR_in': ['SR_in_Avg', 'SR_IN_Avg', 'R_SW_in', 'SW_IN_net_rdmtr'],  # CR6
    'SR_out': ['SR_out_Avg', 'SR_OUT_Avg', 'R_SW_out', 'SW_OUT'],  # CR6
    'IR_in': ['IR_in_Avg', 'IR_IN_Avg', 'R_LW_in', 'LW_IN', 'R_LW_in_meas'],  # CR6
    'IR_out': ['IR_out_Avg', 'IR_OUT_Avg', 'R_LW_out', 'LW_OUT', 'R_LW_out_meas']  # CR6
}

METEO_VARIABLES = {
    'Precipitation': ['Rain_mm_Tot', 'precip_total_rain_e', 'precip_rain_e', 'P'],  # CR6
    'Air_Temperature': ['amb_tmpr', 'Tc', 'T_probe', 'T_DP_Probe', 'T_nr'],  # CR6
    'Wind_Speed': ['wnd_spd_cv', 'Ux', 'Uy', 'Uz'],
    'Air_Pressure': ['amb_press', 'P', 'press_cv', 'amb_press_77'],
    'Air_Humidity': ['amb_RH', 'RH', 'RH_probe', 'RH_cv']
}

ENERGY_FLUX_VARIABLES = {
    'Latent_Heat_Flux': ['LE', 'LvE[W/m²]', 'ET'],
    'Sensible_Heat_Flux': ['H', 'HTs[W/m²]', 'H_Flux']
}


def find_data_files(station: str):
    """Findet alle verfügbaren Daten-Dateien für eine Station."""
    files = {}
    
    # Suche nach merged_long Parquet-Dateien
    for ftype in ['cr1000', 'radiation', 'result', 'smt']:
        file_path = DATA_DIR / f"{station}_{ftype}_merged_long.parquet"
        if file_path.exists():
            files[ftype] = file_path
    
    # Für Mole und Janga: Suche auch nach CR6 Public Dateien
    if station in CR6_STATIONS:
        cr6_dir = RAW_DATA_DIR / station / "raw"
        if cr6_dir.exists():
            # Suche nach CR6 Public Dateien
            cr6_patterns = [
                f"CR6{station}_Public.dat",
                f"CR6{station}_Public*.dat",
            ]
            for pattern in cr6_patterns:
                for cr6_file in cr6_dir.glob(pattern):
                    if 'cr6' not in files:  # Nur einmal hinzufügen
                        files['cr6'] = cr6_file
                        break
                if 'cr6' in files:
                    break
    
    return files


def load_cr6_file(file_path: Path):
    """Lädt eine CR6 Public Datei (Header in Zeile 2, Zeile 1 und 3 überspringen)."""
    try:
        # TOA5 Format für CR6:
        # Zeile 0: TOA5 Info (überspringen)
        # Zeile 1: Spaltennamen (Header) - BEHALTEN
        # Zeile 2: Einheiten (überspringen)
        # Zeile 3: Aggregationstyp (überspringen)
        # Zeile 4+: Daten
        
        df = pd.read_csv(
            file_path,
            skiprows=[0, 2],  # Überspringe Zeile 0 und 2 (Zeile 1 wird als Header verwendet)
            header=0,  # Zeile 1 ist der Header
            index_col=0,  # Erste Spalte ist TIMESTAMP
            parse_dates=True,
            na_values=["NAN", "NA", "-9999", "-9999.0", "-9999.9003906", ""],
            low_memory=False,
            on_bad_lines='skip'
        )
        
        # Entferne RECORD Spalte falls vorhanden
        if 'RECORD' in df.columns:
            df = df.drop(columns=['RECORD'])
        
        # Stelle sicher, dass Index Datetime ist
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, errors='coerce')
        
        # Filtere ungültige Daten
        df = df[df.index.notna()]
        df = df[(df.index.year >= 2000) & (df.index.year <= 2030)]
        df = df.sort_index()
        
        return df
    except Exception as e:
        print(f"      ⚠️ Fehler beim Laden von CR6-Datei {file_path.name}: {e}")
        return pd.DataFrame()


def load_station_data(station: str):
    """Lädt alle verfügbaren Daten für eine Station."""
    files = find_data_files(station)
    
    if not files:
        print(f"❌ Keine Daten gefunden für Station {station}")
        return None
    
    data = {}
    for ftype, file_path in files.items():
        try:
            if ftype == 'cr6':
                # CR6-Datei mit speziellem Format laden
                df = load_cr6_file(file_path)
                if not df.empty:
                    data[ftype] = df
                    print(f"  ✓ {ftype}: {len(df):,} Zeilen, {df.index.min().date()} → {df.index.max().date()}")
            else:
                # Parquet-Datei laden
                df = pd.read_parquet(file_path)
                df.index = pd.to_datetime(df.index)
                data[ftype] = df
                print(f"  ✓ {ftype}: {len(df):,} Zeilen, {df.index.min().date()} → {df.index.max().date()}")
        except Exception as e:
            print(f"  ⚠️ Fehler beim Laden von {ftype}: {e}")
    
    return data


def find_variable(df: pd.DataFrame, possible_names: list):
    """Findet eine Variable in einem DataFrame."""
    for name in possible_names:
        if name in df.columns:
            return name
    return None


def get_sensor_number(col_name: str, var_type: str) -> int:
    """Bestimmt die Sensor-Nummer aus dem Spaltennamen."""
    import re
    
    # Suche nach Nummern in Klammern: (1), (2), (3)
    nums = re.findall(r'\((\d+)\)', col_name)
    if nums:
        return int(nums[0])
    
    # Suche nach _1_, _2_, _3_ Pattern (aber nicht _10_, _20_, etc.)
    nums = re.findall(r'_(\d+)_', col_name)
    if nums:
        num = int(nums[0])
        if 1 <= num <= 3:
            return num
    
    # Spezielle Mappings für VWC
    if var_type == 'VWC':
        # CR6: cs65x_wc(1), cs65x_wc(2), cs65x_wc(3)
        if 'cs65x_wc(1)' in col_name:
            return 1
        elif 'cs65x_wc(2)' in col_name:
            return 2
        elif 'cs65x_wc(3)' in col_name:
            return 3
        # VWC_1_Avg, VW_1_Avg -> Sensor 1
        elif re.search(r'(VWC|VW)_1(_|Avg)', col_name):
            return 1
        # VWC_2_Avg, VW_2_Avg -> Sensor 2
        elif re.search(r'(VWC|VW)_2(_|Avg)', col_name):
            return 2
        # VWC_3_Avg, VW_3_Avg -> Sensor 3
        elif re.search(r'(VWC|VW)_3(_|Avg)', col_name):
            return 3
        # VWC_Avg (ohne Nummer) -> Sensor 1
        elif 'VWC_Avg' in col_name and 'VWC_2' not in col_name and 'VWC_3' not in col_name:
            return 1
        # VW_Avg (ohne Nummer) -> Sensor 1
        elif 'VW_Avg' in col_name and 'VW_2' not in col_name and 'VW_3' not in col_name:
            return 1
    
    # Spezielle Mappings für Soil Temperature
    elif var_type == 'Soil_Temp':
        # CR6: cs65x_tmpr(1), cs65x_tmpr(2), cs65x_tmpr(3)
        if 'cs65x_tmpr(1)' in col_name:
            return 1
        elif 'cs65x_tmpr(2)' in col_name:
            return 2
        elif 'cs65x_tmpr(3)' in col_name:
            return 3
        # TCAV_C_Avg(1) oder T_Avg (ohne _2 oder _3) -> Sensor 1
        elif 'TCAV_C_Avg(1)' in col_name:
            return 1
        elif 'TCAV_C_Avg(2)' in col_name:
            return 2
        elif 'TCAV_C_Avg(3)' in col_name:
            return 3
        elif 'T_Avg' in col_name and 'T_2' not in col_name and 'T_3' not in col_name:
            return 1
        # T_1_Avg, T_2_Avg, T_3_Avg
        elif 'T_1_Avg' in col_name:
            return 1
        elif 'T_2_Avg' in col_name:
            return 2
        elif 'T_3_Avg' in col_name:
            return 3
    
    # Spezielle Mappings für Heat Flux
    elif var_type == 'Soil_Heat_Flux':
        # East/Ost -> Sensor 1
        if 'East' in col_name or 'Ost' in col_name:
            return 1
        # Middle/Mitte -> Sensor 2
        elif 'Middle' in col_name or 'Mitte' in col_name:
            return 2
        # West -> Sensor 3
        elif 'West' in col_name:
            return 3
        # shf_plate(1), G_plate_1 -> Sensor 1
        elif 'shf_plate(1)' in col_name or 'G_plate_1' in col_name or 'G_1_1_1' in col_name:
            return 1
        # shf_plate(2), G_plate_2 -> Sensor 2
        elif 'shf_plate(2)' in col_name or 'G_plate_2' in col_name or 'G_2_1_1' in col_name:
            return 2
        # shf_plate(3), G_plate_3 -> Sensor 3
        elif 'shf_plate(3)' in col_name or 'G_plate_3' in col_name or 'G_3_1_1' in col_name:
            return 3
    
    return None


def plot_soil_variables(data: dict, station: str):
    """Plottet Bodenvariablen - 9 Plots: 3 Variablen × 3 Sensoren."""
    # Sammle alle verfügbaren Variablen mit Sensor-Zuordnung
    vwc_data = {1: [], 2: [], 3: []}  # {sensor: [(col_name, ftype, df), ...]}
    temp_data = {1: [], 2: [], 3: []}
    hf_data = {1: [], 2: [], 3: []}
    
    # VWC Variablen
    for col in SOIL_VARIABLES['VWC']:
        for ftype, df in data.items():
            if col in df.columns:
                sensor = get_sensor_number(col, 'VWC')
                if sensor:
                    vwc_data[sensor].append((col, ftype, df))
                break
    
    # Soil Temperature Variablen
    for col in SOIL_VARIABLES['Soil_Temp']:
        for ftype, df in data.items():
            if col in df.columns:
                sensor = get_sensor_number(col, 'Soil_Temp')
                if sensor:
                    temp_data[sensor].append((col, ftype, df))
                break
    
    # Heat Flux Variablen
    for col in SOIL_VARIABLES['Soil_Heat_Flux']:
        for ftype, df in data.items():
            if col in df.columns:
                sensor = get_sensor_number(col, 'Soil_Heat_Flux')
                if sensor:
                    hf_data[sensor].append((col, ftype, df))
                break
    
    # Prüfe ob Daten vorhanden
    has_data = any(vwc_data.values()) or any(temp_data.values()) or any(hf_data.values())
    if not has_data:
        print("  ⚠️ Keine Bodenvariablen gefunden")
        return
    
    # Erstelle 9 Subplots: 3 Reihen (VWC, Temp, HF) × 3 Spalten (Sensor 1, 2, 3)
    fig = make_subplots(
        rows=3,
        cols=3,
        subplot_titles=[
            'VWC Sensor 1', 'VWC Sensor 2', 'VWC Sensor 3',
            'Temp Sensor 1', 'Temp Sensor 2', 'Temp Sensor 3',
            'Heat Flux Sensor 1', 'Heat Flux Sensor 2', 'Heat Flux Sensor 3'
        ],
        vertical_spacing=0.08,
        horizontal_spacing=0.08,
        shared_xaxes='all'
    )
    
    # VWC Plots (Reihe 1)
    for sensor in [1, 2, 3]:
        col_idx = sensor
        row_idx = 1
        
        if vwc_data[sensor]:
            for col_name, ftype, df in vwc_data[sensor]:
                fig.add_trace(
                    go.Scatter(
                        x=df.index,
                        y=df[col_name],
                        name=col_name,
                        mode='lines',
                        line=dict(width=1),
                        showlegend=(sensor == 1),  # Nur für ersten Sensor in Legende
                        legendgroup='vwc',
                        hovertemplate=f'<b>{col_name}</b><br>%{{x}}<br>%{{y:.3f}}<extra></extra>'
                    ),
                    row=row_idx, col=col_idx
                )
        else:
            fig.add_annotation(
                text="Keine Daten",
                xref=f"x{col_idx if col_idx == 1 else ''}",
                yref=f"y{row_idx if row_idx == 1 else ''}",
                x=0.5, y=0.5, xanchor='center', yanchor='middle',
                showarrow=False,
                row=row_idx, col=col_idx
            )
        
        fig.update_yaxes(title_text="VWC", row=row_idx, col=col_idx)
    
    # Temperature Plots (Reihe 2)
    for sensor in [1, 2, 3]:
        col_idx = sensor
        row_idx = 2
        
        if temp_data[sensor]:
            for col_name, ftype, df in temp_data[sensor]:
                fig.add_trace(
                    go.Scatter(
                        x=df.index,
                        y=df[col_name],
                        name=col_name,
                        mode='lines',
                        line=dict(width=1),
                        showlegend=(sensor == 1),
                        legendgroup='temp',
                        hovertemplate=f'<b>{col_name}</b><br>%{{x}}<br>%{{y:.2f}}°C<extra></extra>'
                    ),
                    row=row_idx, col=col_idx
                )
        else:
            fig.add_annotation(
                text="Keine Daten",
                xref=f"x{col_idx if col_idx == 1 else ''}",
                yref=f"y{row_idx if row_idx == 1 else ''}",
                x=0.5, y=0.5, xanchor='center', yanchor='middle',
                showarrow=False,
                row=row_idx, col=col_idx
            )
        
        fig.update_yaxes(title_text="Temp (°C)", row=row_idx, col=col_idx)
    
    # Heat Flux Plots (Reihe 3)
    for sensor in [1, 2, 3]:
        col_idx = sensor
        row_idx = 3
        
        if hf_data[sensor]:
            for col_name, ftype, df in hf_data[sensor]:
                fig.add_trace(
                    go.Scatter(
                        x=df.index,
                        y=df[col_name],
                        name=col_name,
                        mode='lines',
                        line=dict(width=1),
                        showlegend=(sensor == 1),
                        legendgroup='hf',
                        hovertemplate=f'<b>{col_name}</b><br>%{{x}}<br>%{{y:.2f}} W/m²<extra></extra>'
                    ),
                    row=row_idx, col=col_idx
                )
        else:
            fig.add_annotation(
                text="Keine Daten",
                xref=f"x{col_idx if col_idx == 1 else ''}",
                yref=f"y{row_idx if row_idx == 1 else ''}",
                x=0.5, y=0.5, xanchor='center', yanchor='middle',
                showarrow=False,
                row=row_idx, col=col_idx
            )
        
        fig.update_yaxes(title_text="HF (W/m²)", row=row_idx, col=col_idx)
    
    # X-Achsen Labels nur in der unteren Reihe
    for col in [1, 2, 3]:
        fig.update_xaxes(title_text="Datum", row=3, col=col)
    
    fig.update_layout(
        title=f"{station} - Bodenvariablen (9 Plots: 3 Variablen × 3 Sensoren)",
        height=1000,
        showlegend=True,
        hovermode='x unified'
    )
    
    fig.show()


def plot_radiation_variables(data: dict, station: str):
    """Plottet Strahlungsvariablen - ein Fenster pro Variable."""
    fig = make_subplots(
        rows=4,
        cols=1,
        subplot_titles=['SR_in', 'SR_out', 'IR_in', 'IR_out'],
        vertical_spacing=0.05,
        shared_xaxes=True
    )
    
    for idx, (var_name, possible_cols) in enumerate(RADIATION_VARIABLES.items()):
        row = idx + 1
        found = False
        
        for ftype, df in data.items():
            col_name = find_variable(df, possible_cols)
            if col_name:
                fig.add_trace(
                    go.Scatter(
                        x=df.index,
                        y=df[col_name],
                        name=col_name,
                        mode='lines',
                        line=dict(width=1),
                        hovertemplate=f'<b>{col_name}</b><br>%{{x}}<br>%{{y:.2f}} W/m²<extra></extra>'
                    ),
                    row=row, col=1
                )
                found = True
                break
        
        if not found:
            fig.add_annotation(
                text="Keine Daten verfügbar",
                xref=f"x{row}", yref=f"y{row}",
                x=0.5, y=0.5, showarrow=False,
                row=row, col=1
            )
        
        fig.update_yaxes(title_text="W/m²", row=row, col=1)
    
    fig.update_xaxes(title_text="Datum", row=4, col=1)
    fig.update_layout(
        title=f"{station} - Strahlungsvariablen",
        height=800,
        showlegend=True,
        hovermode='x unified'
    )
    
    fig.show()


def plot_meteo_variables(data: dict, station: str):
    """Plottet meteorologische Variablen."""
    fig = make_subplots(
        rows=5,
        cols=1,
        subplot_titles=['Precipitation', 'Air Temperature', 'Wind Speed', 
                       'Air Pressure', 'Air Humidity'],
        vertical_spacing=0.05,
        shared_xaxes=True
    )
    
    row_mapping = {
        'Precipitation': 1,
        'Air_Temperature': 2,
        'Wind_Speed': 3,
        'Air_Pressure': 4,
        'Air_Humidity': 5
    }
    
    for var_name, possible_cols in METEO_VARIABLES.items():
        row = row_mapping[var_name]
        found = False
        
        for ftype, df in data.items():
            col_name = find_variable(df, possible_cols)
            if col_name:
                fig.add_trace(
                    go.Scatter(
                        x=df.index,
                        y=df[col_name],
                        name=col_name,
                        mode='lines',
                        line=dict(width=1),
                        hovertemplate=f'<b>{col_name}</b><br>%{{x}}<br>%{{y:.2f}}<extra></extra>'
                    ),
                    row=row, col=1
                )
                found = True
                break
        
        if not found:
            fig.add_annotation(
                text="Keine Daten verfügbar",
                xref=f"x{row}", yref=f"y{row}",
                x=0.5, y=0.5, showarrow=False,
                row=row, col=1
            )
        
        # Y-Achsen Labels
        units = {
            'Precipitation': 'mm',
            'Air_Temperature': '°C',
            'Wind_Speed': 'm/s',
            'Air_Pressure': 'hPa',
            'Air_Humidity': '%'
        }
        fig.update_yaxes(title_text=units.get(var_name, ''), row=row, col=1)
    
    fig.update_xaxes(title_text="Datum", row=5, col=1)
    fig.update_layout(
        title=f"{station} - Meteorologische Variablen",
        height=1000,
        showlegend=True,
        hovermode='x unified'
    )
    
    fig.show()


def plot_energy_fluxes(data: dict, station: str):
    """Plottet Energieflüsse - wenn vorhanden."""
    fig = make_subplots(
        rows=2,
        cols=1,
        subplot_titles=['Latent Heat Flux', 'Sensible Heat Flux'],
        vertical_spacing=0.1,
        shared_xaxes=True
    )
    
    # Latent Heat Flux
    found_latent = False
    for ftype, df in data.items():
        col_name = find_variable(df, ENERGY_FLUX_VARIABLES['Latent_Heat_Flux'])
        if col_name:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df[col_name],
                    name=col_name,
                    mode='lines',
                    line=dict(width=1),
                    hovertemplate=f'<b>{col_name}</b><br>%{{x}}<br>%{{y:.2f}} W/m²<extra></extra>'
                ),
                row=1, col=1
            )
            found_latent = True
            break
    
    if not found_latent:
        fig.add_annotation(
            text="Keine Daten verfügbar",
            xref="x1", yref="y1",
            x=0.5, y=0.5, showarrow=False,
            row=1, col=1
        )
    
    # Sensible Heat Flux
    found_sensible = False
    for ftype, df in data.items():
        col_name = find_variable(df, ENERGY_FLUX_VARIABLES['Sensible_Heat_Flux'])
        if col_name:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df[col_name],
                    name=col_name,
                    mode='lines',
                    line=dict(width=1),
                    hovertemplate=f'<b>{col_name}</b><br>%{{x}}<br>%{{y:.2f}} W/m²<extra></extra>'
                ),
                row=2, col=1
            )
            found_sensible = True
            break
    
    if not found_sensible:
        fig.add_annotation(
            text="Keine Daten verfügbar",
            xref="x2", yref="y2",
            x=0.5, y=0.5, showarrow=False,
            row=2, col=1
        )
    
    if not found_latent and not found_sensible:
        print("  ⚠️ Keine Energiefluss-Daten gefunden")
        return
    
    fig.update_yaxes(title_text="W/m²", row=1, col=1)
    fig.update_yaxes(title_text="W/m²", row=2, col=1)
    fig.update_xaxes(title_text="Datum", row=2, col=1)
    fig.update_layout(
        title=f"{station} - Energieflüsse",
        height=600,
        showlegend=True,
        hovermode='x unified'
    )
    
    fig.show()


def select_station():
    """Fragt den Benutzer nach der Station."""
    print("\n" + "=" * 60)
    print("  Verfügbare Stationen:")
    print("=" * 60)
    
    available = []
    for i, station in enumerate(STATIONS, 1):
        files = find_data_files(station)
        if files:
            status = "✓"
            available.append(station)
        else:
            status = "✗"
        print(f"  {i}) {station:12s} [{status}]")
    
    print("=" * 60)
    
    while True:
        try:
            choice = input(f"\nStation auswählen (1-{len(STATIONS)}): ").strip()
            
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(STATIONS):
                    station = STATIONS[idx]
                    if station in available:
                        return station
                    else:
                        print(f"⚠️ Keine Daten für {station} verfügbar")
            else:
                # Name eingegeben
                for station in STATIONS:
                    if station.lower() == choice.lower():
                        if station in available:
                            return station
                        else:
                            print(f"⚠️ Keine Daten für {station} verfügbar")
                            break
            
            print(f"⚠️ Ungültige Eingabe.")
        
        except KeyboardInterrupt:
            print("\n\nAbgebrochen.")
            exit(0)


def main():
    parser = argparse.ArgumentParser(
        description="Erstellt interaktive Plots für Stationsdaten",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--station', '-s',
        type=str,
        help='Station (Gorigo, Janga, Kayoro, Mole, Nazinga)'
    )
    parser.add_argument(
        '--skip-soil', action='store_true',
        help='Überspringe Bodenplots'
    )
    parser.add_argument(
        '--skip-radiation', action='store_true',
        help='Überspringe Strahlungsplots'
    )
    parser.add_argument(
        '--skip-meteo', action='store_true',
        help='Überspringe Meteorologieplots'
    )
    parser.add_argument(
        '--skip-energy', action='store_true',
        help='Überspringe Energieflussplots'
    )
    
    args = parser.parse_args()
    
    # Station auswählen
    if args.station:
        station = args.station
        if station not in STATIONS:
            print(f"⚠️ Unbekannte Station: {station}")
            station = select_station()
    else:
        station = select_station()
    
    print(f"\n{'='*60}")
    print(f"📍 Station: {station}")
    print("=" * 60)
    
    # Daten laden
    print("\n📂 Lade Daten...")
    data = load_station_data(station)
    
    if not data:
        print("❌ Keine Daten gefunden")
        return
    
    # Plots erstellen
    print("\n📊 Erstelle Plots...")
    
    if not args.skip_soil:
        print("\n  → Bodenvariablen...")
        plot_soil_variables(data, station)
    
    if not args.skip_radiation:
        print("\n  → Strahlungsvariablen...")
        plot_radiation_variables(data, station)
    
    if not args.skip_meteo:
        print("\n  → Meteorologische Variablen...")
        plot_meteo_variables(data, station)
    
    if not args.skip_energy:
        print("\n  → Energieflüsse...")
        plot_energy_fluxes(data, station)
    
    print("\n✅ Fertig! Plots sollten in Ihrem Browser geöffnet sein.")


if __name__ == "__main__":
    main()


