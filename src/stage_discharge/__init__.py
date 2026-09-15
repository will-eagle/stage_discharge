"""Stage-discharge tools for HOBO, VuSitu, and LI-COR sensor logs."""

__version__ = "0.1.0"

from .read_write import (
    read_hobo_log,
    read_vusitu_log,
    clean_hobo_log,
    clean_vusitu_log,
    parse_metadata,
)
from .conversions import convert_to_si
from .build_stage import calc_depth, calc_diff_pressure
from .hobo_fetch import fetch_licor_data, tidy_licor_data
from .rating_curve import RatingCurve

__all__ = [
    "read_hobo_log",
    "read_vusitu_log",
    "clean_hobo_log",
    "clean_vusitu_log",
    "parse_metadata",
    "convert_to_si",
    "calc_depth",
    "calc_diff_pressure",
    "fetch_licor_data",
    "tidy_licor_data",
    "RatingCurve",
]