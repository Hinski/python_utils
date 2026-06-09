"""Parquet format data loader for merged_long files."""
from pathlib import Path
import pandas as pd
from .base import BaseDataLoader

class ParquetLoader(BaseDataLoader):
    """Loader for Parquet files (merged_long)."""

    def load_data(self) -> pd.DataFrame:
        """Load Parquet file and return DataFrame."""
        df = pd.read_parquet(self.data_path)
        
        # Check if index is already datetime index
        if not isinstance(df.index, pd.DatetimeIndex):
            # If not, use first columns as Index
            if len(df.columns) > 0:
                first_col = df.columns[0]
                if first_col.lower() in ["timestamp", "date", "datetime"]:
                    df = df.set_index(first_col)

        # Ensure that index is DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            # try to parse index
            df.index = pd.to_datetime(df.index, errors='coerce')

        # Clean and return
        return self.clean_dataframe(df)