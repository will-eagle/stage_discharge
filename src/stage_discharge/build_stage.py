import numpy as np

from .conversions import PSI_TO_PA   # single source of truth; retires the local typo'd copy

G = 9.80665   # standard gravity, m/s^2


def _require_si(data, cols):
    """Guard: refuse to run physics on non-SI columns. The unit suffix IS the
    assertion -- a column not ending _pa/_m/_c means convert_to_si was skipped."""
    bad = {c: c.rsplit("_", 1)[-1] for c in cols
           if not c.endswith(("_pa", "_m", "_c"))}
    if bad:
        raise ValueError(
            f"non-SI columns reached the physics: {bad}. "
            f"Run convert_to_si() first."
        )


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