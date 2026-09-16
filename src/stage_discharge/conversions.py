"""Unit handling for the pipeline. There is ONE internal system: SI
(pressure -> Pa, length/depth -> m, temperature -> °C, discharge -> m³/s).

The physics is SI-locked -- rho()/calc_depth() need °C and Pa -- so the interior
is always SI. The only unit "choice" is at the I/O edges: readers normalize to SI
on the way in, and to_units(frame, "US") converts a whole frame back to US units
(psi/ft/°F/cfs) on the way out, for display or export.

The unit of each column lives in its name suffix (abs_pressure_pa, temperature_c),
so a frame needs no separate units dict -- the suffix IS the unit. This module is
the SINGLE SOURCE OF TRUTH: the constants below, and the QUANTITIES/UNITS registry
that both directions of to_units read from.
"""

import re

# --- conversion constants (single source of truth) -----------------------
PSI_TO_PA  = 6894.757      # 1 psi in pascals
KPA_TO_PA  = 1000.0
FT_TO_M    = 0.3048        # 1 foot in metres
CM_TO_M    = 0.01
MM_TO_M    = 0.001
CFS_TO_CMS = FT_TO_M ** 3  # 1 cubic foot/s in cubic metres/s (ft^3 -> m^3)

# --- unit-system registry ------------------------------------------------
# quantity -> (SI label, SI suffix, US label, US suffix). The suffix is what a
# column name carries; the label is the human unit. Discharge suffixes are set
# explicitly because normalize_unit("m³/s") is not a usable token.
QUANTITIES = {
    "pressure":    ("Pa",   "pa",  "psi", "psi"),
    "length":      ("m",    "m",   "ft",  "ft"),
    "temperature": ("°C",   "c",   "°F",  "f"),
    "discharge":   ("m³/s", "cms", "cfs", "cfs"),
}

# normalized unit -> (quantity, scale, offset), where  si_value = raw * scale + offset.
# Every unit any reader might emit, plus the SI/US canonical suffixes, maps here.
UNITS = {
    "psi":  ("pressure",    PSI_TO_PA,  0.0),
    "kpa":  ("pressure",    KPA_TO_PA,  0.0),
    "pa":   ("pressure",    1.0,        0.0),
    "f":    ("temperature", 5 / 9,      -160 / 9),   # (t - 32) * 5/9
    "c":    ("temperature", 1.0,        0.0),
    "ft":   ("length",      FT_TO_M,    0.0),
    "feet": ("length",      FT_TO_M,    0.0),
    "cm":   ("length",      CM_TO_M,    0.0),
    "mm":   ("length",      MM_TO_M,    0.0),
    "m":    ("length",      1.0,        0.0),
    "cfs":  ("discharge",   CFS_TO_CMS, 0.0),
    "cms":  ("discharge",   1.0,        0.0),
}


def normalize_unit(unit):
    """'°F' -> 'f', 'psi' -> 'psi'. The ONE normalization rule, shared by the
    readers (to build the column-name suffix) and by to_units (to look the unit
    up in UNITS). If the two ever diverged, conversions would silently stop
    matching -- so both sides call this."""
    return re.sub(r"\W+", "", str(unit).lower().replace("°", ""))


def to_units(data, system="SI"):
    """Convert a whole frame to `system` ("SI" or "US"); return the DataFrame.

    Each column's current unit is read from its name suffix. Columns whose suffix
    is a known unit are converted to the target system's canonical unit for that
    quantity, and the suffix is rewritten in lockstep (abs_pressure_psi <->
    abs_pressure_pa). Unrecognized suffixes (conductivity, etc.) pass through
    untouched, so this is safe to run on any pipeline frame.
    """
    if system not in ("SI", "US"):
        raise ValueError(f"system must be 'SI' or 'US', got {system!r}")
    data = data.copy()

    for key in list(data.columns):
        norm = key.rsplit("_", 1)[-1] if "_" in key else ""
        if norm not in UNITS:
            continue                                   # no/unknown unit suffix -> leave alone
        quantity, scale, offset = UNITS[norm]
        _, si_suffix, _, us_suffix = QUANTITIES[quantity]
        target_suffix = si_suffix if system == "SI" else us_suffix

        si = data[key] * scale + offset                # raw -> SI first
        t_scale, t_offset = UNITS[target_suffix][1:]   # SI -> target (invert)
        data[key] = (si - t_offset) / t_scale

        new_key = f"{key[:-(len(norm) + 1)]}_{target_suffix}"
        if new_key != key:
            data = data.rename(columns={key: new_key})

    return data
