"""
data_loaders.py
Sauberes Modul mit Loader- und Cleaning-Funktionen für EC-, Radiation-,
Soil- und Logger-Dateien (TOA5, CR6, CSV, Dragan-Format etc.).
"""

import io
import re
import csv
import struct
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np


# ======================================================
#   REGEX / HILFSFUNKTIONEN
# ======================================================

_LINE_NO = re.compile(r'^\s*\d+\s+')
_RE_ISO  = re.compile(r'^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?(\.\d+)?$')
DATE_LINE = re.compile(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}")


def _strip_leading_line_no(s: str) -> str:
    """Entfernt führende '   1   ' Nummern."""
    return _LINE_NO.sub("", s)


def read_file_head_and_tail(path, head_lines: int = 60, tail_bytes: int = 65536) -> tuple:
    """
    Liest nur die ersten head_lines Zeilen und die letzten tail_bytes Bytes einer Datei.
    Vermeidet readlines() auf ganzen großen Dateien (z. B. TOA5 mit 100k+ Zeilen).

    Returns:
        (first_lines: list[str], last_lines: list[str])
    """
    first_lines = []
    with Path(path).expanduser().open("r", encoding="utf-8", errors="ignore") as f:
        for _ in range(head_lines):
            line = f.readline()
            if not line:
                break
            first_lines.append(line)
        # Tail: seek von Ende, lese letzten Block
        try:
            f.seek(0, 2)
            size = f.tell()
            if size > tail_bytes:
                f.seek(max(0, size - tail_bytes))
                _ = f.readline()  # evtl. abgeschnittene Zeile verwerfen
            last_block = f.read()
            last_lines = [ln for ln in last_block.splitlines() if ln.strip()][-20:]
        except (OSError, IOError):
            last_lines = []
    return first_lines, last_lines


# ======================================================
#   GENERISCHER CSV-LOADER (Header in Zeile 1)
# ======================================================

def iter_clean_firstrow_header(path: Path):
    header_written = False
    with Path(path).expanduser().open("r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip():
                continue

            if not header_written:
                header = _strip_leading_line_no(line).lstrip()
                header_written = True
                yield header + "\n"
                continue

            line = _strip_leading_line_no(line)
            if re.match(r'^\s*Date\s*,', line, flags=re.IGNORECASE):
                continue

            yield line + "\n"


def read_csv_firstrow_header(path, tz: str | None = None) -> pd.DataFrame:
    cleaned = ''.join(iter_clean_firstrow_header(Path(path)))
    df = pd.read_csv(
        io.StringIO(cleaned),
        sep=",",
        quotechar='"',
        engine="python",
        header=0,
        skipinitialspace=True,
        on_bad_lines="skip",
        na_values=["", "NAN", "NaN", "nan", "-9999", "-99999", "-9999.0", "-99999.0"],
        dtype={"Date": "string"},
    )

    if "Date" in df.columns:
        s = df["Date"].astype(str).str.strip().str.strip('"')
        mask_iso = s.str.match(_RE_ISO)
        idx = pd.Series(pd.NaT, index=df.index)

        idx.loc[mask_iso] = pd.to_datetime(s.loc[mask_iso], errors="coerce")
        idx.loc[~mask_iso] = pd.to_datetime(s.loc[~mask_iso], format="%d/%m/%Y %H:%M", errors="coerce")

        df = df.drop(columns=["Date"])
        df.index = idx
        df.index.name = "Date"
        df.sort_index(inplace=True)
        df = df[~df.index.duplicated()]

        if tz:
            df.index = df.index.tz_localize(tz, nonexistent="shift_forward", ambiguous="NaT")

    return df


# ======================================================
#   TOA5 / CR6 Loader
# ======================================================

def iter_clean_toa5_lines(path: Path):
    wrote_header = False
    in_header = False

    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue

            line = re.sub(r'^\s*\d+\s+', '', line)
            if line.count(",") < 5:
                continue

            up = line.upper()

            # TOA5, CR1000 und CR3000 (Campbell Scientific) – Header bis zur Zeile mit Spaltennamen
            if (up.startswith('"TOA5"') or up.startswith('TOA5') or
                    up.startswith('"CR1000"') or up.startswith('CR1000') or
                    up.startswith('"CR3000"') or up.startswith('CR3000') or
                    up.startswith('"TIMESTAMP"') or up.startswith('"TS"')):
                in_header = True
                if (up.startswith('"TIMESTAMP"') or up.startswith('"TS"')) and not wrote_header:
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


def read_toa5(path, tz: str | None = None) -> pd.DataFrame:
    buf = io.StringIO(''.join(iter_clean_toa5_lines(Path(path))))
    df = pd.read_csv(
        buf,
        sep=",",
        quotechar='"',
        engine="c",
        header=0,
        na_values=["NAN","NA","-9999","-999","**************"],
        skipinitialspace=True,
        on_bad_lines="skip",
        low_memory=False
    )

    # Explizite Timestamp-Parsing mit mehreren Format-Versuchen
    # Dies verhindert Fehlinterpretationen durch dayfirst=True, besonders bei Mitternacht (00:00)
    timestamp_col = "TIMESTAMP" if "TIMESTAMP" in df.columns else (df.columns[0] if len(df.columns) > 0 else None)

    if timestamp_col:
        s = df[timestamp_col].astype(str).str.strip().str.strip('"').str.strip("'")

        # Versuche verschiedene Formate in Reihenfolge
        idx = pd.Series(pd.NaT, index=df.index)

        # Format 1: ISO-Format (YYYY-MM-DD HH:MM:SS oder YYYY-MM-DD HH:MM)
        mask_iso = s.str.match(_RE_ISO)
        if mask_iso.any():
            # Versuche zuerst mit explizitem Format
            s_iso = s.loc[mask_iso]
            # Prüfe ob Sekunden vorhanden sind
            has_seconds = s_iso.str.contains(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', regex=True, na=False)
            # Parse mit Format
            parsed_iso = pd.Series(pd.NaT, index=s_iso.index)
            if has_seconds.any():
                parsed_iso.loc[has_seconds] = pd.to_datetime(
                    s_iso.loc[has_seconds],
                    format='%Y-%m-%d %H:%M:%S',
                    errors='coerce'
                )
            if (~has_seconds).any():
                parsed_iso.loc[~has_seconds] = pd.to_datetime(
                    s_iso.loc[~has_seconds],
                    format='%Y-%m-%d %H:%M',
                    errors='coerce'
                )
            idx.loc[mask_iso] = parsed_iso

        # Format 2: DD/MM/YYYY HH:MM oder DD.MM.YYYY HH:MM
        mask_remaining = idx.isna()
        if mask_remaining.any():
            s_remaining = s.loc[mask_remaining]
            # Versuche zuerst DD/MM/YYYY HH:MM
            parsed = pd.to_datetime(s_remaining, format="%d/%m/%Y %H:%M", errors="coerce")
            # Falls fehlgeschlagen, versuche DD.MM.YYYY HH:MM
            mask_failed = parsed.isna()
            if mask_failed.any():
                parsed.loc[mask_failed] = pd.to_datetime(
                    s_remaining.loc[mask_failed],
                    format="%d.%m.%Y %H:%M",
                    errors="coerce"
                )
            # Falls immer noch fehlgeschlagen, versuche mit dayfirst (Fallback)
            # Aber nur wenn es nicht ISO-Format ist (YYYY-MM-DD)
            mask_still_failed = parsed.isna()
            if mask_still_failed.any():
                s_failed = s_remaining.loc[mask_still_failed]
                # Prüfe ob ISO-Format - dann dayfirst=False, sonst True
                # Verarbeite ISO und Nicht-ISO separat
                is_iso = s_failed.str.match(r'^\d{4}-\d{2}-\d{2}')
                if is_iso.any():
                    parsed.loc[mask_still_failed & is_iso] = pd.to_datetime(
                        s_failed.loc[is_iso],
                        dayfirst=False,
                        errors="coerce"
                    )
                if (~is_iso).any():
                    parsed.loc[mask_still_failed & (~is_iso)] = pd.to_datetime(
                        s_failed.loc[~is_iso],
                        dayfirst=True,
                        errors="coerce"
                    )
            idx.loc[mask_remaining] = parsed

        df = df.drop(columns=[timestamp_col])
        df.index = idx
        df.index.name = "TIMESTAMP"

    # Entferne NaT (nicht parsebare Timestamps)
    df = df[df.index.notna()]

    df.sort_index(inplace=True)
    df = df[~df.index.duplicated()]
    if tz:
        df.index = df.index.tz_localize(tz, nonexistent="shift_forward", ambiguous="NaT")
    return df


# ======================================================
#   TOB3 / Flux CSFormat (Campbell Scientific, binär)
# ======================================================
# Format: 6 Zeilen Text-Header, danach Binärdaten (IEEE4B, INT4, ASCII).
# Zeile 1: TOB3, Logger, CR6, …; Zeile 2: Tabellenname, Intervall, …; Zeile 3: Spaltennamen;
# Zeile 4: Einheiten; Zeile 5: Aggregation; Zeile 6: Datentypen (IEEE4B, INT4, ASCII(8), …).

def _tob3_type_size(typ: str) -> int:
    """Bytes pro Feld für TOB3-Typen."""
    t = typ.strip().upper()
    if t == "IEEE4B":
        return 4
    if t in ("INT4", "LONG"):
        return 4
    if t.startswith("ASCII("):
        m = re.match(r"ASCII\((\d+)\)", t)
        return int(m.group(1)) if m else 8
    return 4  # Fallback


def read_tob3_csformat(path, tz: str | None = None) -> pd.DataFrame:
    """
    Liest Campbell Scientific TOB3/Flux_CSFormat-Dateien (z.B. 17691_Flux_CSFormat_65.dat).
    Header = 6 Zeilen Text, danach Binärdaten (IEEE4B, INT4, ASCII).
    Erste Spalte wird als Zeitstempel interpretiert (Sec100Usec → Sekunden seit 1990-01-01).
    """
    path = Path(path)
    with path.open("rb") as f:
        # 6 Headerzeilen (Text)
        lines = []
        for _ in range(6):
            line = f.readline().decode("utf-8", errors="replace").strip()
            lines.append(line)
        binary_start = f.tell()
        rest = f.read()

    if len(lines) < 6:
        return pd.DataFrame()

    # Spaltennamen aus Zeile 3 (CSV mit Anführungszeichen)
    names_line = lines[2]
    reader = csv.reader(io.StringIO(names_line), quotechar='"')
    col_names = next(reader)

    # Datentypen aus Zeile 6
    types_line = lines[5]
    reader = csv.reader(io.StringIO(types_line), quotechar='"')
    type_list = next(reader)

    # Gleiche Anzahl Spalten
    while len(type_list) < len(col_names):
        type_list.append("IEEE4B")
    type_list = type_list[: len(col_names)]

    # Bytes pro Feld und pro Zeile
    type_sizes = [_tob3_type_size(t) for t in type_list]
    record_size = sum(type_sizes)

    if record_size == 0:
        return pd.DataFrame()

    # TOB3: Binärdaten = ggf. 12-Byte-Frame-Header pro Frame, dann Records.
    # Einfach: zuerst ohne Frame-Header (nur aufeinanderfolgende Records).
    n_total = len(rest)
    if n_total < record_size:
        return pd.DataFrame()

    # Wenn (n_total - 12) durch record_size teilbar: 12-Byte-Header vor erstem Record
    use_leading_header = (n_total - 12) >= record_size and (n_total - 12) % record_size == 0
    skip_leading = 12 if use_leading_header else 0

    rows = []
    pos = skip_leading
    frame_header_size = 0
    idx_vals = []

    while pos + frame_header_size + record_size <= n_total:
        pos += frame_header_size
        record = rest[pos : pos + record_size]
        pos += record_size
        if len(record) < record_size:
            break
        row = []
        off = 0
        for i, (typ, size) in enumerate(zip(type_list, type_sizes)):
            chunk = record[off : off + size]
            off += size
            if len(chunk) < size:
                row.append(np.nan)
                continue
            t = typ.strip().upper()
            if t == "IEEE4B":
                try:
                    row.append(struct.unpack("<f", chunk)[0])
                except Exception:
                    row.append(np.nan)
            elif t in ("INT4", "LONG"):
                try:
                    row.append(struct.unpack("<i", chunk)[0])
                except Exception:
                    row.append(np.nan)
            elif t.startswith("ASCII"):
                try:
                    s = chunk.decode("utf-8", errors="replace").strip("\x00 ")
                    row.append(s if s else np.nan)
                except Exception:
                    row.append(np.nan)
            else:
                row.append(np.nan)
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=col_names[: len(rows[0])])

    # Bei Flux_CSFormat ist die erste Spalte oft FC_mass, nicht Zeitstempel.
    # Zeitstempel stecken ggf. im 12-Byte-Frame-Header (nicht als Spalte).
    # Index = Zeilen (0, 1, …); alle Spalten bleiben erhalten.

    if tz:
        try:
            df.index = df.index.tz_localize(tz, nonexistent="shift_forward", ambiguous="NaT")
        except Exception:
            pass
    return df


# ======================================================
#   AMERIFLUX FLUX FORMAT (.dat mit Header-Zeile, kein TOA5)
# ======================================================

def read_ameriflux_flux(path, tz: str | None = None) -> pd.DataFrame:
    """
    Liest AmeriFlux-Format Flux-Dateien (z.B. 17692_Flux_AmeriFluxFormat_6.dat).
    Format: erste Zeile = Spaltennamen (oft TIMESTAMP zuerst), danach Daten.
    Fehlwerte typisch -9999. Nicht für TOA5-Dateien verwenden.
    """
    path = Path(path)
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        first_line = f.readline().strip()
    # Wenn doch TOA5, an read_toa5 delegieren
    if first_line.upper().startswith("TOA5") or first_line.upper().startswith('"TOA5"'):
        return read_toa5(path, tz=tz)
    # Mit errors='ignore' öffnen, damit ungültige Bytes (z. B. 0xac) nicht zu UnicodeDecodeError führen
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        df = pd.read_csv(
            f,
            sep=",",
            quotechar='"',
            engine="c",
            header=0,
            skipinitialspace=True,
            on_bad_lines="skip",
            low_memory=False,
            na_values=["NAN", "NA", "-9999", "-999", "-9999.0", "**************", ""],
        )
    if df.empty or len(df.columns) < 1:
        return df
    # Erste Spalte als Index (meist TIMESTAMP oder TIMESTAMP_START)
    first_col = df.columns[0]
    s = df[first_col].astype(str).str.strip().str.strip('"').str.strip("'")
    idx = pd.to_datetime(s, errors="coerce")
    df = df.drop(columns=[first_col])
    df.index = idx
    df.index.name = "TIMESTAMP"
    df = df[df.index.notna()]
    df.sort_index(inplace=True)
    df = df[~df.index.duplicated()]
    if tz:
        df.index = df.index.tz_localize(tz, nonexistent="shift_forward", ambiguous="NaT")
    return df


# ======================================================
#   DRAGAN / GENERISCHE CSVs
# ======================================================

def read_dragan_csv(filepath: str) -> pd.DataFrame:
    df = pd.read_csv(
        filepath,
        sep=";",
        decimal=",",
        parse_dates=[0],
        date_format="%d.%m.%y %H:%M",
        dayfirst=True,
        index_col=0,
        na_values=["", "NA", "NAN", "-9999"],
    )
    df.columns = [c.strip() for c in df.columns]
    return df


def read_csv(path):
    df = pd.read_csv(path, sep=";", header=None, dtype=str)
    df = df.replace("", pd.NA)
    df[0] = pd.to_datetime(df[0], format="%d.%m.%y %H:%M", errors="coerce")
    df = df.set_index(0)
    return df


# ======================================================
#   CR6 CLEAN PARSER
# ======================================================

def read_cr6_csv(filepath: str) -> pd.DataFrame:
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        _ = f.readline()
        header_line = f.readline().strip()
        _ = f.readline()
        _ = f.readline()

    header = [h.strip('"') for h in header_line.split(",")]

    df = pd.read_csv(
        filepath,
        skiprows=4,
        names=header,
        na_values=["NAN", "-2.147484E+09", "-2147483648"],
        low_memory=False
    )

    if "TIMESTAMP" not in df.columns:
        raise ValueError(f"'TIMESTAMP' fehlt! Spalten: {df.columns.tolist()}")

    df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"], errors="coerce")
    df = df.set_index("TIMESTAMP")

    df = df.apply(pd.to_numeric, errors="coerce")
    return df


# =============================================
# read tabbed csv files from Samuel
# =============================================

def read_tabbed_file(path, tz=None):
    df = pd.read_csv(
        path,
        sep="\t",
        header=0,
        na_values=["", "NAN", "NaN", "nan", "-9999", "-99999", "-9999.0", "-99999.0"],
        skipinitialspace=True
    )

    if "TIMESTAMP" in df.columns:
        s = df["TIMESTAMP"].astype(str).str.strip()
        idx = pd.to_datetime(s, format="%d/%m/%Y %H:%M", errors="coerce")
        df = df.drop(columns=["TIMESTAMP"])
        df.index = idx
        df.index.name = "Date"
        df = df[~df.index.duplicated(keep="first")]
        if tz:
            df.index = df.index.tz_localize(tz, nonexistent="shift_forward", ambiguous="NaT")

    return df




def apply_column_names(df: pd.DataFrame, filetype: str) -> pd.DataFrame:
    """
    Assign official column names for:
      - "result"  → Eddy-covariance result files
      - "cr1000"  → Soil/CR1000 logger files

    Parameters
    ----------
    df : pd.DataFrame
        The loaded dataframe (raw columns).
    filetype : str
        One of: "result", "cr1000"

    Returns
    -------
    pd.DataFrame
        DataFrame with standardized column names.
    """

    result_cols = [
        'T_end', 'u[m/s]', 'v[m/s]', 'w[m/s]', 'Ts[°C]', 'Tp[°C]', 'a[g/m³]',
        'CO2[mmol/m³]', 'T_ref[°C]', 'a_ref[g/m³]', 'p_ref[hPa]', 'Var[u]',
        'Var[v]', 'Var[w]', 'Var[Ts]', 'Var[Tp]', 'Var[a]', 'Var[CO2]',
        "Cov[u'v']", "Cov[v'w']", "Cov[u'w']", "Cov[u'Ts']", "Cov[v'Ts']",
        "Cov[w'Ts']", "Cov[u'Tp']", "Cov[v'Tp']", "Cov[w'Tp']",
        "Cov[u'a']", "Cov[v'a']", "Cov[w'a']", "Cov[u'CO2']", "Cov[v'CO2']",
        "Cov[w'CO2']", '???', 'dir[°]', 'ustar[m/s]', 'HTs[W/m²]', 'HTp[W/m²]',
        'LvE[W/m²]', 'z/L', 'z/L-virt', 'Flag(ustar)', 'Flag(HTs)',
        'Flag(HTp)', 'Flag(LvE)', 'Flag(wCO2)', 'T_mid', 'FCstor[mmol/m²s]',
        'NEE[mmol/m²s]', 'Footprint_trgt_1', 'Footprint_trgt_2',
        'Footprnt_xmax[m]', ' r_err_ustar[%]', 'r_err_HTs[%]',
        'r_err_LvE[%]', 'r_err_co2[%]', 'noise_ustar[%]', 'noise_HTs[%]',
        'noise_LvE[%]', 'noise_co2[%]', 'Filler_to_reach61'
    ]

    cr1000_cols = [
        'BattV_Avg', 'PTemp_C_Avg', 'VW_1_Avg', 'PA_uS_1_Avg', 'VW_2_Avg',
        'PA_uS_2_Avg', 'VW_3_Avg', 'PA_uS_3_Avg', 'Rain_mm_Tot',
        'TCAV_C_Avg(1)', 'TCAV_C_Avg(2)', 'TCAV_C_Avg(3)',
        'Intensity_RT_Avg', 'Acc_RT_NRT_Tot', 'Acc_NRT', 'Acc_totNRT',
        'Bucket_RT', 'Bucket_NRT', 'Temp_load_cell_Avg',
        'H_Flux_sc_8_Ost_Avg', 'H_Flux_sc_8_West_Avg',
        'H_Flux_sc_8_Mitte_Avg', 'shf_cal(1)', 'shf_cal(2)', 'shf_cal(3)'
    ]

    # remove index column if present in df (like TIMESTAMP)
    data_cols = df.columns.tolist()

    if filetype.lower() == "result":
        wanted = result_cols
    elif filetype.lower() == "cr1000":
        wanted = cr1000_cols
    else:
        raise ValueError("filetype must be either 'result' or 'cr1000'")

    if len(data_cols) != len(wanted):
        print("⚠️ Column count mismatch: cannot safely rename.")
        print(f"  → df has      {len(data_cols)} columns")
        print(f"  → expected    {len(wanted)} columns")
        print("  Rename aborted.")
        return df

    df = df.copy()
    df.columns = wanted
    return df
