#!/usr/bin/env python3
"""
Visualisiert die Datenabdeckung für Gorigo merged Dateien.
Plottet Strahlungskomponenten und Bodenvariablen mit Datenabdeckung.
"""

import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path
import numpy as np
import sys


def load_merged_csv(file_path: Path):
    """Lädt eine merged CSV-Datei."""
    print(f"📖 Lade: {file_path.name}")
    df = pd.read_csv(file_path, parse_dates=['TIMESTAMP'], index_col='TIMESTAMP')
    print(f"   Zeitraum: {df.index.min()} → {df.index.max()}")
    print(f"   Anzahl Zeilen: {len(df)}")
    print(f"   Anzahl Spalten: {len(df.columns)}")
    return df


def plot_radiation_coverage(df_rad: pd.DataFrame, output_dir: Path):
    """Plottet Strahlungskomponenten mit Datenabdeckung."""
    
    # Strahlungskomponenten auswählen
    radiation_cols = [
        'SR_in_Avg', 'SR_out_Avg', 'IR_in_Avg', 'IR_out_Avg',
        'NetRs_Avg', 'NetRl_Avg', 'NetTot_Avg', 'Albedo_Avg'
    ]
    
    # Verfügbare Spalten finden
    available_cols = [col for col in radiation_cols if col in df_rad.columns]
    
    if not available_cols:
        print("⚠️ Keine Strahlungsspalten gefunden!")
        return
    
    print(f"\n📊 Plotte {len(available_cols)} Strahlungskomponenten:")
    for col in available_cols:
        print(f"   - {col}")
    
    # Datenabdeckung berechnen (Anzahl Messungen pro Tag)
    coverage = pd.Series(1, index=df_rad.index).resample('D').count()
    
    # Plot erstellen
    n_plots = len(available_cols) + 1  # +1 für Coverage
    fig, axes = plt.subplots(n_plots, 1, figsize=(16, 3 * n_plots), sharex=True)
    
    if n_plots == 1:
        axes = [axes]
    
    # 1. Coverage Plot
    ax = axes[0]
    ax.fill_between(coverage.index, coverage.values, alpha=0.7, color='steelblue')
    ax.set_ylabel('Messungen/Tag', fontsize=11, fontweight='bold')
    ax.set_title('Gorigo Radiation - Datenabdeckung', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.axhline(y=48, color='green', linestyle='--', linewidth=1, alpha=0.5, label='Erwartet (48/Tag)')
    ax.legend(loc='upper right')
    
    # 2-n. Strahlungskomponenten
    colors = plt.cm.tab10(np.linspace(0, 1, len(available_cols)))
    
    for i, col in enumerate(available_cols):
        ax = axes[i + 1]
        
        # Daten plotten
        valid_data = df_rad[col].dropna()
        if len(valid_data) > 0:
            ax.plot(valid_data.index, valid_data.values, '-', 
                   color=colors[i], linewidth=1, alpha=0.7, label=col)
            
            # Statistik anzeigen
            coverage_pct = 100 * len(valid_data) / len(df_rad)
            mean_val = valid_data.mean()
            ax.text(0.02, 0.98, f'Abdeckung: {coverage_pct:.1f}% | Mittel: {mean_val:.2f}',
                   transform=ax.transAxes, verticalalignment='top',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        ax.set_ylabel(col, fontsize=10, fontweight='bold')
        ax.grid(True, alpha=0.3)
        if len(valid_data) > 0:
            ax.legend(loc='upper right', fontsize=9)
    
    # X-Achse formatieren
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    plt.tight_layout()
    
    # Speichern
    output_file = output_dir / 'Gorigo_radiation_coverage.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"\n💾 Plot gespeichert: {output_file}")
    plt.close()


def plot_cr1000_coverage(df_cr1000: pd.DataFrame, output_dir: Path):
    """Plottet Bodenvariablen mit Datenabdeckung."""
    
    # Bodenvariablen auswählen
    # VW (Volumetric Water Content)
    vw_cols = [col for col in df_cr1000.columns if 'VW' in col and 'Avg' in col]
    
    # TCAV (Temperature Cavity)
    tcav_cols = [col for col in df_cr1000.columns if 'TCAV' in col]
    
    # H_Flux (Heat Flux)
    h_flux_cols = [col for col in df_cr1000.columns if 'H_Flux' in col or 'H_flux' in col]
    
    # Weitere wichtige Variablen
    other_cols = ['Rain_mm_Tot', 'PTemp_C_Avg']
    other_cols = [col for col in other_cols if col in df_cr1000.columns]
    
    # Alle zusammenfügen
    soil_cols = vw_cols + tcav_cols + h_flux_cols + other_cols
    
    if not soil_cols:
        print("⚠️ Keine Bodenvariablen gefunden!")
        return
    
    print(f"\n📊 Plotte {len(soil_cols)} Bodenvariablen:")
    for col in soil_cols:
        print(f"   - {col}")
    
    # Datenabdeckung berechnen
    coverage = pd.Series(1, index=df_cr1000.index).resample('D').count()
    
    # Plot erstellen
    n_plots = len(soil_cols) + 1  # +1 für Coverage
    fig, axes = plt.subplots(n_plots, 1, figsize=(16, 3 * n_plots), sharex=True)
    
    if n_plots == 1:
        axes = [axes]
    
    # 1. Coverage Plot
    ax = axes[0]
    ax.fill_between(coverage.index, coverage.values, alpha=0.7, color='darkgreen')
    ax.set_ylabel('Messungen/Tag', fontsize=11, fontweight='bold')
    ax.set_title('Gorigo CR1000 (Bodenvariablen) - Datenabdeckung', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.axhline(y=48, color='green', linestyle='--', linewidth=1, alpha=0.5, label='Erwartet (48/Tag)')
    ax.legend(loc='upper right')
    
    # 2-n. Bodenvariablen
    colors = plt.cm.Set3(np.linspace(0, 1, len(soil_cols)))
    
    for i, col in enumerate(soil_cols):
        ax = axes[i + 1]
        
        # Daten plotten
        valid_data = df_cr1000[col].dropna()
        if len(valid_data) > 0:
            ax.plot(valid_data.index, valid_data.values, '-', 
                   color=colors[i], linewidth=1, alpha=0.7, label=col)
            
            # Statistik anzeigen
            coverage_pct = 100 * len(valid_data) / len(df_cr1000)
            mean_val = valid_data.mean()
            ax.text(0.02, 0.98, f'Abdeckung: {coverage_pct:.1f}% | Mittel: {mean_val:.2f}',
                   transform=ax.transAxes, verticalalignment='top',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        ax.set_ylabel(col, fontsize=10, fontweight='bold')
        ax.grid(True, alpha=0.3)
        if len(valid_data) > 0:
            ax.legend(loc='upper right', fontsize=9)
    
    # X-Achse formatieren
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    plt.tight_layout()
    
    # Speichern
    output_file = output_dir / 'Gorigo_cr1000_coverage.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"\n💾 Plot gespeichert: {output_file}")
    plt.close()


def main():
    """Hauptfunktion."""
    try:
        data_dir = Path("/Users/hingerl-l/Data/Gorigo/merged")
        output_dir = Path("/Users/hingerl-l/Diss/python_utils/plots/Gorigo")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        print("=" * 60)
        print("Gorigo Datenabdeckung - Visualisierung")
        print("=" * 60)
        print()
        
        # Strahlungsdaten laden und plotten
        rad_file = data_dir / "Gorigo_radiation_merged.csv"
        if rad_file.exists():
            try:
                df_rad = load_merged_csv(rad_file)
                plot_radiation_coverage(df_rad, output_dir)
            except Exception as e:
                print(f"❌ Fehler beim Verarbeiten der Strahlungsdaten: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"⚠️ Datei nicht gefunden: {rad_file}")
        
        print()
        
        # CR1000 Daten laden und plotten
        cr1000_file = data_dir / "Gorigo_cr1000_merged.csv"
        if cr1000_file.exists():
            try:
                df_cr1000 = load_merged_csv(cr1000_file)
                plot_cr1000_coverage(df_cr1000, output_dir)
            except Exception as e:
                print(f"❌ Fehler beim Verarbeiten der CR1000-Daten: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"⚠️ Datei nicht gefunden: {cr1000_file}")
        
        print("\n✅ Fertig!")
        
    except Exception as e:
        print(f"❌ Kritischer Fehler: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
