"""TOA5/CR6 format data loader."""
import io
import re
import csv
from pathlib import Path
import pandas as pd
from .base import BaseDataLoader, DATE_LINE

def iter_clean_toa5_lines(path: Path):
    """Clean TOA5 file lines, extracting header and data."""
    wrote_header = False
    in_header = False
    
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            
            line = re.sub(r'^\s*\d+\s+', '', line)  # Remove line numbers
            if line.count(",") < 5:
                continue
            
            up = line.upper()
            
            if up.startswith('"TOA5"') or up.startswith('"TIMESTAMP"') or up.startswith('"TS"'):
                in_header = True
                if up.startswith('"TIMESTAMP"') and not wrote_header:
                    wrote_header = True
                    yield line + "\n"
                continue
            
            if in_header:
                if DATE_LINE.search(line):
                    in_header = False
                else:
                    continue
            
            if DATE_LINE.search(line):
                if not wrote_header:
                    fields = next(csv.reader([line]))
                    header = ["TIMESTAMP"] + [f"c{i}" for i in range(1, len(fields))]
                    yield ",".join(header) + "\n"
                    wrote_header = True
                
                yield line + "\n"


class TOA5Loader(BaseDataLoader):
    """Loader for TOA5/CR6 format files."""

    def load_data(self) -> pd.DataFrame:
        """Load TOA5/CR6 file and return DataFrame."""
        buf = io.StringIO(''.join(iter_clean_toa5_lines(self.data_path)))
        df = pd.read_csv(
            buf,
            sep=",",
            quotechar='"',
            engine="c",
            header=0,
            na_values=["NAN","NA", "-9999", "-9999.0", "-999", "**************"],
            skipinitialspace=True,
            on_bad_lines="skip",
            low_memory=False
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

