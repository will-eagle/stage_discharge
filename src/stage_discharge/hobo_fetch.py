import requests
import pandas as pd
import warnings
from . import standard_names as sn
from .read_write import _add_unit_suffix   # same suffix rule as the other readers
from .conversions import to_units          # same SI conversion as clean_*


def fetch_licor_data(serial_number, start_date, end_date, token, report=False):
    """Fetch logger data from the LI-COR Cloud API.

    start_date / end_date are strings in 'YYYY-MM-DD HH:MM:SS'; requests handles
    the URL-encoding of spaces and colons.
    """
    params = {
        "loggers": serial_number,
        "start_date_time": start_date,
        "end_date_time": end_date,
    }
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get("https://api.licor.cloud/v1/data", params=params, headers=headers)
    r.raise_for_status()

    d = r.json()
    if report:
        types = sorted({rec["sensor_measurement_type"] for rec in d["data"]})
        print(f"{d['message']}, sensors = {types}")
    return d


def tidy_licor_data(data):
    '''Parse the JSON dict from fetch_licor_data into a tidy wide-format frame
    (one row per timestamp), with columns on canonical standard names. The frame
    is put on a UTC index and run through to_units(..., "SI"), so it lands on the
    same UTC + SI contract as clean_hobo_log / clean_vusitu_log. Returns (data, units).'''
    df = pd.DataFrame(data["data"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    # one unit per measurement type, keyed by the RAW type (before rename)
    type_units = df.groupby("sensor_measurement_type")["unit"].first().to_dict()

    # raw field -> canonical name + unit suffix; warn on anything new
    rename, units = {}, {}
    for t in df["sensor_measurement_type"].unique():
        canonical = sn.LICOR_ALIASES.get(t)
        if canonical is None:
            warnings.warn(
                f"LI-COR: unrecognized measurement {t!r} -- passing it through "
                f"un-aliased. Add it to standard_names if it's real.",
                stacklevel=2,
            )
            canonical = t
        unit = type_units.get(t)
        key = _add_unit_suffix(canonical, unit)   # 'abs_pressure' + 'psi' -> 'abs_pressure_psi'
        rename[t] = key
        if unit:
            units[key] = unit

    df["sensor_measurement_type"] = df["sensor_measurement_type"].map(rename)

    df_wide = df.pivot(
        index="timestamp",
        columns="sensor_measurement_type",
        values="value",
    )
    df_wide.index.name = "datetime"           # match the clean_* readers' index name
    return to_units(df_wide, "SI"), units