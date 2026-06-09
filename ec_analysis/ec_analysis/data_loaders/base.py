import re
from pathlib import Path
from abc import ABC, abstractmethod
import pandas as pd

# Regex patterns for timestamp detection
RE_ISO = re.compile(r'^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?(\.\d+)?$')
DATE_LINE = re.compile(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}")

"""
Base classes and utilities for EC data loaders
"""

class BaseDataLoader(ABC):
    """
    Abstract base class for EC data loaders
    """
    def __init__(self, data_path: str | Path, tz: str | None = None):
        self.data_path = Path(data_path)
        self.tz = tz
        if not self.data_path.exists():
            raise FileNotFoundError(f"File not found: {self.data_path}")

    @abstractmethod
    def load_data(self) -> pd.DataFrame:
        """
        Load data from the data path
        """
        pass

    def parse_timestamp(self, series: pd.Series) -> pd.DatetimeIndex:
        """
        Parse timestamp from the series
        """
        s = series.astype(str).str.strip().str.strip('"')
        idx = pd.Series(pd.NaT, index=series.index)

        # Try ISO format
        mask_iso = s.str.match(RE_ISO)
        if mask_iso.any():
            idx.loc[mask_iso] = pd.to_datetime(s.loc[mask_iso], errors='coerce')

        mask_remaining = idx.isna()
        if mask_remaining.any():
            s_remaining = s.loc[mask_remaining]
            parsed = pd.to_datetime(s_remaining, format="%d/%m/%Y %H:%M", errors='coerce')
            idx.loc[mask_remaining] = parsed

        return pd.DatetimeIndex(idx)

    def clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove invalid timestamps, sort, remove duplicates."""
        df = df[df.index.notna()]
        df.sort_index(inplace=True)
        df = df[~df.index.duplicated(keep='first')]
        if self.tz and df.index.tz is None:
            df.index = df.index.tz_localize(self.tz, nonexistent="shift_forward", ambiguous="NaT")
        return df
