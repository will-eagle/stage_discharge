import numpy as np

from .conversions import PSI_TO_PA   # single source of truth; retires the local typo'd copy
from .standard_names import (
    ABS_PRESSURE, BARO_PRESSURE, DIFF_PRESSURE, TEMPERATURE, WATER_LEVEL,
)

G = 9.80665   # standard gravity, m/s^2

_SI_TOKENS = {"pa", "m", "c"}   # the target unit suffixes to_units(..., "SI") emits


def _require_si(names):
    """Guard: refuse to run physics on non-SI columns. The unit suffix IS the
    assertion -- a name carries an SI unit token (_pa/_m/_c) only if
    to_units(..., "SI") produced it. Membership (not just the final token) is
    checked so a merge-suffixed 'temperature_c_abs' still reads as SI while a raw
    'abs_pressure_psi' or 'stage_ft' is rejected."""
    bad = [n for n in names if not (_SI_TOKENS & set(str(n).split("_")))]
    if bad:
        raise ValueError(
            f"non-SI columns reached the physics: {sorted(bad)}. "
            f"Run to_units(data, 'SI') first."
        )


def _find_col(data, base, required=True):
    """Locate the column for a canonical measurement (e.g. 'abs_pressure'),
    whatever its unit suffix. Returns the column name, None if absent and not
    required, or raises on absence/ambiguity so a mislabeled frame fails loud."""
    matches = [c for c in data.columns if c == base or c.startswith(base + "_")]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        if required:
            raise KeyError(f"no {base!r} column in {list(data.columns)}")
        return None
    raise KeyError(f"ambiguous {base!r} columns: {matches} -- pass the name explicitly")


def _require_utc(index):
    """Guard: refuse to run on a non-UTC datetime index. Naive or local-time
    data silently misaligns across sources, so the interior is UTC-only. The
    UTC analogue of _require_si."""
    tz = getattr(index, "tz", None)
    if tz is None or str(tz) != "UTC":
        raise ValueError(
            f"expected a UTC datetime index, got tz={tz!r}. "
            f"Convert on read (localize source tz -> UTC)."
        )


def rho(t, convert_to_c=False):
    """
    Calculates the density of pure water (kg/m^3) at 1 atm 
    using the UNESCO 1981 / Millero & Poisson polynomial equation.
    
    Valid range: 0°C to 30°C (standard oceanographic/limnological limits).
    """
    if convert_to_c:
        t = (t - 32) * (5 / 9)

    # UNESCO 1981 Coefficients for pure water
    a0 = 999.842594
    a1 = 6.793952e-2
    a2 = -9.095290e-3
    a3 = 1.001685e-4
    a4 = -1.120083e-6
    a5 = 6.536332e-9

    rho = a0 + (a1 * t) + (a2 * t**2) + (a3 * t**3) + (a4 * t**4) + (a5 * t**5)
    return rho


def calc_diff_pressure(abs_pa, baro_pa):
    return abs_pa - baro_pa


def calc_depth(diff, temp, convert_to_c=False):
    '''Calculates depth using P = rho(T)*g*h, where P is in pascals and temp is in C.'''
    depth = diff / (rho(temp, convert_to_c) * G)
    return depth


def psi2pascals(psi):
    return psi * PSI_TO_PA


def build_stage(data, *, abs_col=None, baro_col=None, diff_col=None, temp_col=None):
    """Compute differential pressure and water level (stage) for a cleaned frame.
    Returns a copy with 'diff_pressure_pa' (if derived) and 'water_level_m' added.

    Requires SI units and a UTC index -- both guaranteed by clean_*/tidy_*. The
    guards run FIRST so no physics touches a naive/local index or a non-converted
    (psi, ft, °F) column. Columns are found by canonical base name (any suffix)
    unless overridden. Differential pressure is taken from an existing
    diff_pressure column (HOBO) or derived from abs - baro (two VuSitu files).
    """
    _require_utc(data.index)
    temp_col = temp_col or _find_col(data, TEMPERATURE)
    diff_col = diff_col or _find_col(data, DIFF_PRESSURE, required=False)

    data = data.copy()
    if diff_col is None:
        abs_col  = abs_col  or _find_col(data, ABS_PRESSURE)
        baro_col = baro_col or _find_col(data, BARO_PRESSURE)
        _require_si([abs_col, baro_col, temp_col])
        diff_col = f"{DIFF_PRESSURE}_pa"
        data[diff_col] = calc_diff_pressure(data[abs_col], data[baro_col])
    else:
        _require_si([diff_col, temp_col])

    data[f"{WATER_LEVEL}_m"] = calc_depth(data[diff_col], data[temp_col])
    return data