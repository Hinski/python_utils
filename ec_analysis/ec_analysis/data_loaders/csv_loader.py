"""Generic CSV format data loader."""
from pathlib import Path
import pandas as pd
from .base import BaseDataLoader


class CSVLoader(BaseDataLoader):
    """Loader for generic CSV files with TIMESTAMP column."""

    def load_data(self) -> pd.DataFrame:
        """Load CSV file and return DataFrame."""
        df = pd.read_csv(
            self.data_path,
            sep=",",
            low_memory=False,
            na_values=["NAN", "NA", "-9999", "-9999.0", "-999", "**************"]
        )
        
        # Parse timestamp
        timestamp_col = "TIMESTAMP" if "TIMESTAMP" in df.columns else (df.columns[0] if len(df.columns) > 0 else None)
        if timestamp_col:
            s = df[timestamp_col].astype(str).str.strip().str.strip('"').str.strip("'")
            idx = self.parse_timestamp(s)
            df = df.drop(columns=[timestamp_col])
            df.index = idx
            df.index.name = "TIMESTAMP"
        
        return self.clean_dataframe(df)

