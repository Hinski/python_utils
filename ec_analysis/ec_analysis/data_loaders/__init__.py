"""Data loaders for EC and climate data formats."""
from .base import BaseDataLoader
from .toa5_loader import TOA5Loader
from .eddypro_loader import EddyProLoader
from .parquet_loader import ParquetLoader
from .csv_loader import CSVLoader
from .loader import load_ec_data, detect_file_format

__all__ = [
    'BaseDataLoader',
    'TOA5Loader',
    'EddyProLoader',
    'ParquetLoader',
    'CSVLoader',
    'load_ec_data',
    'detect_file_format',
]