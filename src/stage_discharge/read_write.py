"""Source adapters: instrument logs -> canonical (data, units).

Each reader's job is to normalize STRUCTURE and VOCABULARY only: it reshapes to
one-row-per-timestamp, resolves instrument names to canonical standard names
(see standard_names.py), and extracts units. It does not convert units -- that
is convert_to_si's job. It DOES put datetimes on a UTC index, so all three
sources are on one clock downstream.
"""

import re
import warnings
import pandas as pd
from . import standard_names as sn
from .conversions import normalize_unit   # one shared normalization rule


# --- shared naming helpers -----------------------------------------------

def _apply_alias(base_key, alias_map, source):
    """Normalized base name -> canonical standard name.

    'datetime' passes through untouched. An unrecognized name is passed
    through un-aliased with a warning (fail loud, not fail fatal) so a genuinely
    new parameter announces itself instead of silently masquerading as a raw
    column. Flip the warn to a raise if you'd rather hard-stop on the unknown.
    """
    if base_key == "datetime":
        return base_key
    canonical = alias_map.get(base_key)
    if canonical is None:
        warnings.warn(
            f"{source}: unrecognized measurement {base_key!r} -- passing it "
            f"through un-aliased. Add it to standard_names if it's real.",
            stacklevel=2,
        )
        return base_key
    return canonical


def _add_unit_suffix(key, unit):
    """'temperature' + '°C' -> 'temperature_c'. Uses conversions.normalize_unit
    so the suffix here matches the key convert_to_si looks up -- one rule, no
    drift. Unit stays on the name so convert_to_si can rewrite it in lockstep
    with the value."""
    if unit:
        suffix = normalize_unit(unit)
        if suffix:
            return f"{key}_{suffix}"
    return key


# --- VuSitu ---------------------------------------------------------------

# VuSitu labels both the in-water and the in-air pressure channel "Pressure",
# so the caller declares which this file is. Short forms accepted.
_VUSITU_PRESSURE = {
    "absolute":   sn.ABS_PRESSURE,
    "abs":        sn.ABS_PRESSURE,
    "barometric": sn.BARO_PRESSURE,
    "baro":       sn.BARO_PRESSURE,
}

# VuSitu logs NAIVE LOCAL time. Our deployment records at a FIXED UTC-5 offset
# (no DST shift), so localize to a fixed-offset zone -- NOT "US/Eastern", which
# would inject a phantom hour at each DST transition. Note the Etc/ sign is
# inverted: "Etc/GMT+5" IS UTC-5.
VUSITU_SOURCE_TZ = "Etc/GMT+5"


def _vusitu_aliases(pressure_kind):
    """Build the VuSitu alias map for this deployment: the static VUSITU_ALIASES
    plus a 'pressure' entry pointing at abs or baro per pressure_kind.

    Raises ValueError on an unrecognized kind -- a bad choice has no safe
    fallback (it would silently mislabel the pressure channel), so it hard-stops
    rather than warning like an unknown measurement does.
    """
    try:
        pressure = _VUSITU_PRESSURE[pressure_kind]
    except KeyError:
        raise ValueError(
            f"pressure_kind must be one of {sorted(_VUSITU_PRESSURE)}, "
            f"got {pressure_kind!r}"
        ) from None
    return {**sn.VUSITU_ALIASES, "pressure": pressure}


def _clean_column_name(label, alias_map):
    """'Temperature (°C) (569030)' -> ('temperature_c', '°C').
       'Pressure (psi) (750174)'   -> ('abs_pressure_psi', 'psi')   [abs kind]
                                    -> ('baro_pressure_psi', 'psi')  [baro kind]

    VuSitu columns follow '<Name> (<unit>) (<serial>)'. The FIRST parenthetical
    is the unit; the trailing one is the device serial, ignored for naming. The
    base name is resolved to a canonical standard name via the supplied
    alias_map (built by _vusitu_aliases, so 'pressure' already points at abs or
    baro) BEFORE the unit suffix is appended.
    'Date Time' has no parens -> ('datetime', None).
    """
    label = str(label).strip()
    parens = re.findall(r"\(([^)]*)\)", label)          # ['°C', '569030']
    base = re.sub(r"\s*\([^)]*\)", "", label).strip()   # 'Temperature'
    key = re.sub(r"\W+", "_", base.lower()).strip("_")  # 'temperature'
    if key in ("date_time", "time", "date"):
        key = "datetime"                                # match the rest of the pipeline
    else:
        key = _apply_alias(key, alias_map, "VuSitu")
    unit = parens[0].strip() if parens else None
    key = _add_unit_suffix(key, unit)
    return key, unit


def read_vusitu_log(file_path, *, pressure_kind):
    """Read a VuSitu export. pressure_kind is REQUIRED and keyword-only: pass
    'absolute' for an in-water sonde or 'barometric' for a BaroTROLL in air, so
    the 'Pressure' channel lands on the correct canonical name."""
    aliases = _vusitu_aliases(pressure_kind)   # validates kind up front

    # Pass 1: find the data-table label row instead of hardcoding how many
    # metadata lines precede it -- that count shifts between instruments.
    with open(file_path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    label_idx = next(i for i, ln in enumerate(lines)
                     if ln.lstrip('"').startswith("Date Time"))

    header = pd.read_csv(file_path, header=None, names=["field"], nrows=label_idx)

    # Let the real label row be the header, so column COUNT is auto-detected too.
    data = pd.read_csv(file_path, skiprows=label_idx)

    names, units = {}, {}
    for col in data.columns:
        key, unit = _clean_column_name(col, aliases)
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


def clean_vusitu_log(data, meta=None, source_tz=VUSITU_SOURCE_TZ):
    """Clean a VuSitu frame and put its datetime on a UTC index.

    VuSitu logs NAIVE LOCAL time. source_tz is the sonde's clock (default
    VUSITU_SOURCE_TZ = fixed UTC-5). The naive stamps are localized to source_tz
    then converted to UTC, so this frame aligns with the HOBO and LI-COR readers
    (both already UTC). 'Start Time' from meta shares the data's local clock, so
    it gets the same localize-then-convert before comparison.
    """
    data = data.copy()

    dt = pd.to_datetime(data["datetime"], errors="coerce")
    # ambiguous/nonexistent only bite on DST zones; harmless for fixed offsets,
    # and safe if source_tz is overridden to a DST-aware zone.
    dt = dt.dt.tz_localize(source_tz, ambiguous="NaT", nonexistent="NaT")
    data["datetime"] = dt.dt.tz_convert("UTC")

    value_cols = [c for c in data.columns if c != "datetime"]
    for col in value_cols:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data.dropna(subset=["datetime"] + value_cols)

    if meta and "Start Time" in meta:
        start = pd.Timestamp(meta["Start Time"])
        if start.tzinfo is None:                       # Start Time is local, like the data
            start = start.tz_localize(source_tz)
        data = data[data["datetime"] >= start.tz_convert("UTC")]
    else:
        data = data[data["datetime"] >= pd.Timestamp("2000-01-01", tz="UTC")]  # drop epoch junk

    return data.set_index("datetime").sort_index()


# --- HOBO -----------------------------------------------------------------

def _clean_hobo_column(label):
    """'Diff Pressure (MX-DP 22475388:22475388-1),psi,Devils at Dolan,'
        -> ('diff_pressure_psi', 'psi').

    HOBO packs comma-separated parts INSIDE the quoted header:
    '<measurement> (<sensor:serial-channel>), <unit>, <location>,'. The unit is
    the SECOND part; the parenthetical sensor code and the location are dropped.
    The base name is resolved to a canonical standard name
    (standard_names.HOBO_ALIASES) BEFORE the unit suffix is appended.
    """
    label = str(label).strip()
    parts = [p.strip() for p in label.split(",")]
    measurement = re.sub(r"\s*\([^)]*\)", "", parts[0]).strip()   # drop sensor-code paren
    key = re.sub(r"\W+", "_", measurement.lower()).strip("_")
    if key in ("date", "date_time", "time"):
        key = "datetime"
    else:
        key = _apply_alias(key, sn.HOBO_ALIASES, "HOBO")
    unit = parts[1] if len(parts) > 1 and parts[1] else None
    key = _add_unit_suffix(key, unit)
    return key, unit


def read_hobo_log(file_path, date_format="%y-%m-%d %H:%M:%S %z"):
    data = pd.read_csv(file_path)          # header is row 0 -- no metadata preamble
    names, units = {}, {}
    for col in data.columns:
        key, unit = _clean_hobo_column(col)
        names[col] = key
        if unit:
            units[key] = unit
    data = data.rename(columns=names)
    # %z + utc=True -> tz-aware UTC index, same clock as VuSitu/LI-COR
    data["datetime"] = pd.to_datetime(data["datetime"], format=date_format, utc=True)
    if "line" in data.columns:
        data = data.drop(columns="line")   # just an export row counter
    return data, units


def clean_hobo_log(data):
    data = data.copy()
    value_cols = [c for c in data.columns if c != "datetime"]
    for col in value_cols:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    # Keep rows with ANY real reading -- do NOT require all channels present.
    data = data.dropna(subset=["datetime"])
    data = data.dropna(subset=value_cols, how="all")
    return data.set_index("datetime").sort_index()