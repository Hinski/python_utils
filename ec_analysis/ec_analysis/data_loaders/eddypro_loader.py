"""EddyPro output format data loader for energy and CO2 fluxes."""
from pathlib import Path
import pandas as pd
from .base import BaseDataLoader

class EddyProLoader(BaseDataLoader):
    """Loader for EddyPro output CSV files."""

    def load_data(self) -> pd.DataFrame:
        """Load EddyPro output CSV file and return DataFrame."""
        df = pd.read_csv(
            self.data_path,
            skiprows=1,
            low_memory=False,
            na_values=["-9999"]
        )
        
        # Entferne Units Zeile
        if len(df) > 0:
            first_cell = str(df.iloc[0, 0]) if pd.notna(df.iloc[0, 0]) else ""
            # Check if first row has units ("[")
            if first_cell.startswith('[') or '[' in first_cell:
                df = df.iloc[1:].reset_index(drop=True)

        # Parse datetime from 'date' and 'time' columns
        df = self._parse_datetime(df)

        # Clean and return
        return self.clean_dataframe(df)


    def _parse_datetime(self, df: pd.DataFrame) -> pd.DataFrame:
        """Parse datetime from 'date' and 'time' columns."""
        if 'date' in df.columns and 'time' in df.columns:
            datetime_str = df['date'].astype(str) + ' ' + df['time'].astype(str)
            df['datetime'] = pd.to_datetime(datetime_str, format='%Y-%m-%d %H:%M', errors='coerce')
        elif 'date' in df.columns:
            df['datetime'] = pd.to_datetime(df['date'], errors='coerce')
        else:
            raise ValueError("No date column found in EddyPro file.")

        # datetime as index
        df = df.set_index('datetime')

        # remove bad Datetimes
        invalid_dt = df.index.isna()
        if invalid_dt.sum() > 0:
            df = df[~invalid_dt]

        # remove date and time columns
        df = df.drop(columns=['date', 'time'], errors = 'ignore')
        
        # Convert numeric columns to numeric (EddyPro may load as strings)
        # Skip columns that are clearly not numeric (filename, etc.)
        skip_cols = ['filename', 'file_records', 'used_records']
        for col in df.columns:
            if col not in skip_cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        return df