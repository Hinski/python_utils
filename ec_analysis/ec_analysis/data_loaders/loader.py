"""Unified loader interface with automatic format detection."""
from pathlib import Path
import pandas as pd
from .base import BaseDataLoader
from .toa5_loader import TOA5Loader
from .eddypro_loader import EddyProLoader
from .parquet_loader import ParquetLoader
from .csv_loader import CSVLoader

def detect_file_format(file_path: Path) -> str:
    """Detect file format based on extension and content."""
    file_path = Path(file_path)

    # Check extension
    suffix = file_path.suffix.lower()

    if suffix in [".parquet", ".pq"]:
        return 'parquet'

    if suffix == '.csv':
        # check first row 
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                first_line = f.readline().strip()
                second_line = f.readline().strip() if f else ""

                # Check for EddyPro header streucture
                if 'file_info' in first_line.lower() or 'corrected_fluxes' in first_line.lower():
                    return 'eddypro'

                # TOA5 starts with "TOA5"
                if first_line.startswith('TOA5') or first_line.upper().startswith('TOA5'):
                    return 'toa5'
        except:
            pass
        return 'csv'

    # Prüfe auf .dat Dateien (könnten TOA5 sein)
    if suffix == '.dat':
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                first_line = f.readline().strip()
                if first_line.startswith('"TOA5"') or 'TOA5' in first_line.upper():
                    return 'toa5'
        except:
            pass
        return 'dat'
    
    # Unbekannt
    return 'unknown' 

def load_ec_data(file_path: str | Path, format: str | None = None, tz: str | None = None) -> pd.DataFrame:
    """
    Load EC data file with automatic format detection.
    
    Parameters
    ----------
    file_path : str | Path
        Path to the data file
    format : str | None, optional
        Force specific format: 'parquet', 'toa5', 'eddypro', 'csv', 'dat'
        If None, format is auto-detected
    tz : str | None, optional
        Timezone to apply (e.g., 'UTC', 'Europe/Berlin')
    
    Returns
    -------
    pd.DataFrame
        DataFrame with datetime index and cleaned data
    
    Raises
    ------
    ValueError
        If format cannot be detected or is not supported
    FileNotFoundError
        If file does not exist
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    # Auto-detect format if not specified
    if format is None:
        format = detect_file_format(file_path)
    
    # Load based on format
    if format == 'parquet':
        loader = ParquetLoader(file_path, tz=tz)
    elif format == 'toa5':
        loader = TOA5Loader(file_path, tz=tz)
    elif format == 'eddypro':
        loader = EddyProLoader(file_path, tz=tz)
    elif format == 'csv':
        loader = CSVLoader(file_path, tz=tz)
    else:
        raise ValueError(f"Unsupported format: {format}. Supported: 'parquet', 'toa5', 'eddypro', 'csv'")
    
    return loader.load_data()