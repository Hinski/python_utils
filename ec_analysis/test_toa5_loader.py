"""Test script for TOA5Loader."""
from pathlib import Path
from ec_analysis.data_loaders.toa5_loader import TOA5Loader
from ec_analysis.data_loaders.eddypro_loader import EddyProLoader

# Pfad zu Ihrer TOA5/CR6 Datei - bitte anpassen!
test_file = Path("/Users/hingerl-l/Diss/Data/test_data/long/Gorigo_long_cr1000.dat")
test_file_eddypro = Path("/Users/hingerl-l/Data/Janga/processed/fluxes/eddypro_Janga_full_output_2025-12-30T165108_adv.csv")
# Test
try:
    loader = TOA5Loader(test_file)
    df = loader.load_data()
    loader_eddypro = EddyProLoader(test_file_eddypro)
    df_eddypro = loader_eddypro.load_data()

    print(f"✅ Erfolg! Geladen: {len(df)} Zeilen")
    print(f"✅ Erfolg! Geladen: {len(df_eddypro)} Zeilen")
    print(f"   Spalten: {list(df.columns)[:5]}...")  # Erste 5 Spalten
    print(f"   Spalten: {list(df_eddypro.columns)[:5]}...")  # Erste 5 Spalten
    print(f"   Zeitraum: {df.index.min()} bis {df.index.max()}")
    print(f"   Zeitraum: {df_eddypro.index.min()} bis {df_eddypro.index.max()}")
    print(f"   Shape: {df.shape}")
    print(f"   Shape: {df_eddypro.shape}")
    
except Exception as e:
    print(f"❌ Fehler: {e}")
    import traceback
    traceback.print_exc()