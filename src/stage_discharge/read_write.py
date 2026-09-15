import re
import pandas as pd

def _clean_column_name(label):
    """'Temperature (°C) (569030)' -> ('temperature_c', '°C').

    VuSitu columns follow '<Name> (<unit>) (<serial>)'. The FIRST parenthetical
    is the unit; the trailing one is the device serial, ignored for naming.
    'Date Time' has no parens -> ('datetime', None).
    """
    label = str(label).strip()
    parens = re.findall(r"\(([^)]*)\)", label)          # ['°C', '569030']
    base = re.sub(r"\s*\([^)]*\)", "", label).strip()   # 'Temperature'
    key = re.sub(r"\W+", "_", base.lower()).strip("_")  # 'temperature'
    if key in ("date_time", "time", "date"):
        key = "datetime"                                # match the rest of the pipeline
    unit = parens[0].strip() if parens else None
    if unit:
        suffix = re.sub(r"\W+", "", unit.lower().replace("°", ""))  # '°C' -> 'c'
        if suffix:
            key = f"{key}_{suffix}"
    return key, unit


def read_vusitu_log(file_path):
    # Pass 1: find the data-table label row instead of hardcoding how many
    # metadata lines precede it — that count shifts between instruments.
    with open(file_path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    label_idx = next(i for i, ln in enumerate(lines)
                     if ln.lstrip('"').startswith("Date Time"))

    header = pd.read_csv(file_path, header=None, names=["field"], nrows=label_idx)

    # Let the real label row be the header, so column COUNT is auto-detected too.
    data = pd.read_csv(file_path, skiprows=label_idx)

    names, units = {}, {}
    for col in data.columns:
        key, unit = _clean_column_name(col)
        names[col] = key
        if unit:
            units[key] = unit
    data = data.rename(columns=names)
    return header, data, units

def parse_metadata(header):
    """'Key = Value' preamble -> dict."""
    meta = {}
    for cell in header.iloc[:, 0].dropna():
        if " = " in str(cell):
            key, val = str(cell).split(" = ", 1)
            meta[key.strip()] = val.strip()
    return meta

def clean_vusitu_log(data, meta=None):
    data = data.copy()
    data["datetime"] = pd.to_datetime(data["datetime"], errors="coerce")
    value_cols = [c for c in data.columns if c != "datetime"]
    for col in value_cols:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data.dropna(subset=["datetime"] + value_cols)
    if meta and "Start Time" in meta:
        data = data[data["datetime"] >= pd.Timestamp(meta["Start Time"])]
    else:
        data = data[data["datetime"] >= "2000-01-01"]   # fallback: drop epoch junk
    return data.set_index("datetime").sort_index()


def _clean_hobo_column(label):
    """'Diff Pressure (MX-DP 22475388:22475388-1),psi,Devils at Dolan,'
        -> ('diff_pressure_psi', 'psi').

    HOBO packs comma-separated parts INSIDE the quoted header:
    '<measurement> (<sensor:serial-channel>), <unit>, <location>,'. The unit is
    the SECOND part; the parenthetical sensor code and the location are dropped.
    """
    label = str(label).strip()
    parts = [p.strip() for p in label.split(",")]
    measurement = re.sub(r"\s*\([^)]*\)", "", parts[0]).strip()   # drop sensor-code paren
    key = re.sub(r"\W+", "_", measurement.lower()).strip("_")
    if key in ("date", "date_time", "time"):
        key = "datetime"
    unit = parts[1] if len(parts) > 1 and parts[1] else None
    if unit:
        suffix = re.sub(r"\W+", "", unit.lower().replace("°", ""))  # '°F' -> 'f'
        if suffix:
            key = f"{key}_{suffix}"
    return key, unit


def read_hobo_log(file_path, date_format="%y-%m-%d %H:%M:%S %z"):
    data = pd.read_csv(file_path)          # header is row 0 — no metadata preamble
    names, units = {}, {}
    for col in data.columns:
        key, unit = _clean_hobo_column(col)
        names[col] = key
        if unit:
            units[key] = unit
    data = data.rename(columns=names)
    data["datetime"] = pd.to_datetime(data["datetime"], format=date_format, utc=True)
    if "line" in data.columns:
        data = data.drop(columns="line")   # just an export row counter
    return data, units


def clean_hobo_log(data):
    data = data.copy()
    value_cols = [c for c in data.columns if c != "datetime"]
    for col in value_cols:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    # Keep rows with ANY real reading — do NOT require all channels present.
    data = data.dropna(subset=["datetime"])
    data = data.dropna(subset=value_cols, how="all")
    return data.set_index("datetime").sort_index()

def convert_to_si(data, units):
    