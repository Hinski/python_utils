from pathlib import Path
import yaml

# ---------------------------------------
# 1) Hauptpfad
# ---------------------------------------
ROOT = Path("/Users/hingerl-l/Data")
ROOT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------
# 2) Stationsliste
# ---------------------------------------
stations = {
    "Nazinga":  {"lat": 11.1516, "lon": -1.5858, "alt": 302, "start_year": 2013},
    "Kayoro":   {"lat": 10.9181, "lon": -1.3209, "alt": 305, "start_year": 2012},
    "Sumbrungu":{"lat": 10.8466, "lon": -0.9175, "alt": 306, "start_year": 2012},
    "Gorigo":   {"lat": 10.9356, "lon": -0.8241, "alt": 301, "start_year": 2017},
    "Mole":     {"lat": 9.3385,  "lon": -1.8689, "alt": 225, "start_year": 2023},
    "Janga":    {"lat": 10.1300, "lon": -0.8837, "alt": 289, "start_year": 2022},
}

# ---------------------------------------
# 3) Strukturvorlage
# ---------------------------------------
structure = {
    "raw": ["cr1000", "rad", "photos", "metadata"],
    "processed": ["meteo_30min", "turbulence", "fluxes", "ffp", "qc"],
    "external": ["era5", "landcover", "soilgrids", "dem"],
    "derived": ["footprint_results", "daily_summaries", "ml_inputframes"],
}

# ---------------------------------------
# 4) Für jede Station Ordner erzeugen
# ---------------------------------------
for station in stations.keys():
    station_root = ROOT / station
    station_root.mkdir(exist_ok=True)

    for main, subs in structure.items():
        main_path = station_root / main
        main_path.mkdir(exist_ok=True)

        for sub in subs:
            (main_path / sub).mkdir(exist_ok=True)

print("✅ Ordnerstruktur erfolgreich erstellt!")

# ---------------------------------------
# 5) stations.yaml speichern
# ---------------------------------------
yaml_path = ROOT / "stations.yaml"
with open(yaml_path, "w") as f:
    yaml.dump(stations, f)

print(f"✅ stations.yaml erstellt: {yaml_path}")

# ---------------------------------------
# 6) data_access.py erzeugen
# ---------------------------------------
data_access_code = f'''
from pathlib import Path
import yaml

ROOT = Path("{ROOT}")

with open(ROOT / "stations.yaml") as f:
    STATIONS = yaml.safe_load(f)

def get_station_path(station):
    return ROOT / station

def get_raw(station, datatype):
    return ROOT / station / "raw" / datatype

def get_processed(station, datatype):
    return ROOT / station / "processed" / datatype

def get_external(station, datatype):
    return ROOT / station / "external" / datatype

def get_derived(station, datatype):
    return ROOT / station / "derived" / datatype
'''

with open(ROOT / "data_access.py", "w") as f:
    f.write(data_access_code)

print(f"✅ data_access.py erstellt: {ROOT / 'data_access.py'}")

print("\n🎉 Komplette Data-Infrastruktur ist einsatzbereit!")
