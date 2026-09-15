"""Unit conversions to the pipeline's canonical set: pressure -> Pa,
length/depth -> m, temperature -> °C.

Temperature targets °C, NOT Kelvin: rho() and calc_depth() expect Celsius, so
Kelvin here would silently break every downstream density/depth result.

This module is the SINGLE SOURCE OF TRUTH for the conversion constants -- import
PSI_TO_PA etc. from here rather than redefining them anywhere else.
"""

import re

# --- conversion constants (single source of truth) -----------------------
PSI_TO_PA = 6894.757      # 1 psi in pascals
KPA_TO_PA = 1000.0
FT_TO_M   = 0.3048        # 1 foot in metres
CM_TO_M   = 0.01
MM_TO_M   = 0.001


def normalize_unit(unit):
    """'°F' -> 'f', 'psi' -> 'psi'. The ONE normalization rule, shared by the
    readers (to build the column-name suffix) and by convert_to_si (to look the
    unit up below). If these two ever diverged, conversions would silently stop
    matching -- so both sides call this."""
    return re.sub(r"\W+", "", str(unit).lower().replace("°", ""))


def convert_to_si(data, units):
    """Convert recognized columns to a canonical unit set; return (data, units).

    Targets: pressure -> Pa, length/depth -> m, temperature -> °C. The unit
    lives in the column-name suffix and is rewritten in lockstep with the value.
    Unrecognized units (conductivity, etc.) pass through untouched. Run this
    AFTER clean_*, so the columns are numeric.
    """
    data = data.copy()
    units = dict(units)                                # don't mutate caller's dict

    # normalized unit -> (scale, offset, target_label, target_suffix)
    #   converted = raw * scale + offset
    conversions = {
        "psi":  (PSI_TO_PA, 0.0,    "Pa", "pa"),
        "kpa":  (KPA_TO_PA, 0.0,    "Pa", "pa"),
        "pa":   (1.0,       0.0,    "Pa", "pa"),
        "f":    (5/9,       -160/9, "°C", "c"),         # (t - 32) * 5/9
        "c":    (1.0,       0.0,    "°C", "c"),
        "ft":   (FT_TO_M,   0.0,    "m",  "m"),
        "feet": (FT_TO_M,   0.0,    "m",  "m"),
        "cm":   (CM_TO_M,   0.0,    "m",  "m"),
        "mm":   (MM_TO_M,   0.0,    "m",  "m"),
        "m":    (1.0,       0.0,    "m",  "m"),
    }

    for key in list(units):                            # snapshot: units mutates below
        if key not in data.columns:
            continue
        norm = normalize_unit(units[key])
        if norm not in conversions:
            continue                                   # leave conductivity etc. alone
        scale, offset, target_label, target_suffix = conversions[norm]

        data[key] = data[key] * scale + offset

        base = key[:-(len(norm) + 1)] if key.endswith(f"_{norm}") else key
        new_key = f"{base}_{target_suffix}" if target_suffix else base
        if new_key != key:
            data = data.rename(columns={key: new_key})
            del units[key]
        units[new_key] = target_label

    return data, units