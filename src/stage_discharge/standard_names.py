"""Canonical measurement vocabulary and per-source alias maps.

Single source of truth for what the pipeline calls each physical quantity.
Every reader maps its instrument's raw names onto the canonical names below,
so everything downstream (clean_*, to_units, build_stage) speaks one
vocabulary regardless of which instrument produced the data.
"""

# --- canonical vocabulary ------------------------------------------------
DIFF_PRESSURE = "diff_pressure"
ABS_PRESSURE  = "abs_pressure"
BARO_PRESSURE = "baro_pressure"
TEMPERATURE   = "temperature"
WATER_LEVEL   = "water_level"   # stage, from build_stage
DISCHARGE     = "discharge"     # rating-curve output / field gaugings

# --- per-source alias maps: normalized base name -> canonical ------------
# Keys are the base measurement name AFTER a reader lowercases/underscores it
# and strips the unit -- e.g. "Absolute Pressure" -> "absolute_pressure".

#these are for manual log exports from the licor website
HOBO_ALIASES = {
    "diff_pressure":       DIFF_PRESSURE,
    "absolute_pressure":   ABS_PRESSURE,
    "barometric_pressure": BARO_PRESSURE,
    "temperature":         TEMPERATURE,
    "water_level":         WATER_LEVEL,
}

# VuSitu "Pressure" is deployment-dependent: absolute for an in-water sonde,
# barometric for a BaroTROLL in air -- and In-Situ labels both channels just
# "Pressure". It is therefore NOT fixed here; read_vusitu_log resolves it from
# its required pressure_kind argument and injects the right target at read time.
VUSITU_ALIASES = {
    "temperature": TEMPERATURE,
}

#these are for the licor api call exports
LICOR_ALIASES = {
    "Diff Pressure":       DIFF_PRESSURE,
    "Absolute Pressure":   ABS_PRESSURE,
    "Barometric Pressure": BARO_PRESSURE,
    "Temperature":         TEMPERATURE,
    "Water Level":         WATER_LEVEL,
}

# --- reference only: canonical target units (not yet consumed) -----------
CANONICAL_UNITS = {
    DIFF_PRESSURE: "Pa",
    ABS_PRESSURE:  "Pa",
    BARO_PRESSURE: "Pa",
    TEMPERATURE:   "°C",
    WATER_LEVEL:   "m",
    DISCHARGE:     "m³/s",
}