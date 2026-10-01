"""Stage drift correction against manual (staff gage / tape-down) readings.

v1: linear drift correction. The offset between the logger and the manual
reading is computed at each field visit and linearly interpolated in time
between visits, then removed from the continuous record.
"""
from __future__ import annotations

import pandas as pd


def correct_stage(
    stage_continuous: pd.Series,
    stage_measured: pd.Series,
    tolerance: str | pd.Timedelta = "15min",
    anchor_start: bool = True,
    extrapolate: str = "hold",
) -> pd.DataFrame:
    """Correct continuous stage using discrete measured stage.

    Parameters
    ----------
    stage_continuous : pd.Series
        Logger stage, DatetimeIndex, same units/datum as measured.
    stage_measured : pd.Series
        Manual stage readings, DatetimeIndex.
    tolerance : str or Timedelta
        Max gap allowed when pairing a manual reading to the nearest logger
        sample. (Manual reads almost never land exactly on a logger
        timestamp, so an exact inner join would drop most of them.)
    anchor_start : bool
        If True, assume zero error at the first logger sample (sensor is
        correct at deployment) and ramp drift from there to the first visit.
    extrapolate : {"hold", "zero"}
        Error applied after the last visit (and before the first, if
        anchor_start is False): "hold" = last/first known error,
        "zero" = no correction.

    Returns
    -------
    pd.DataFrame
        Columns: stage_raw, error, stage_corrected. Indexed like
        stage_continuous. Attribute `.attrs["checks"]` holds the paired
        visit table for QA.

    Notes
    -----
    Sign convention: error = continuous - measured, so
    corrected = continuous - error. (The pseudocode used
    measured - continuous with corrected = stage - error, which
    doubles the offset instead of removing it.)
    """
    cont = stage_continuous.dropna().sort_index().rename("stage_raw")
    meas = stage_measured.dropna().sort_index().rename("stage_measured")

    # Pair each manual reading with the nearest logger sample
    checks = pd.merge_asof(
        meas.to_frame(),
        cont.to_frame().reset_index().rename(columns={cont.index.name or "index": "t_logger"})
            .set_index("t_logger", drop=False),
        left_index=True,
        right_index=True,
        direction="nearest",
        tolerance=pd.Timedelta(tolerance),
    ).dropna(subset=["stage_raw"])

    if checks.empty:
        raise ValueError("No manual readings fall within tolerance of the logger record.")

    checks["error"] = checks["stage_raw"] - checks["stage_measured"]

    # Error control points on the time axis
    err_pts = checks["error"].copy()
    if anchor_start and cont.index[0] < err_pts.index[0]:
        err_pts = pd.concat([pd.Series([0.0], index=[cont.index[0]]), err_pts])
    err_pts = err_pts[~err_pts.index.duplicated(keep="last")]

    # Interpolate error onto logger timestamps (linear in time)
    grid = err_pts.reindex(err_pts.index.union(cont.index))
    error = grid.interpolate(method="time", limit_area="inside")

    if extrapolate == "hold":
        error = error.ffill().bfill()
    elif extrapolate == "zero":
        error = error.fillna(0.0)
    else:
        raise ValueError("extrapolate must be 'hold' or 'zero'")

    error = error.reindex(cont.index)

    out = pd.DataFrame({
        "stage_raw": cont,
        "error": error,
        "stage_corrected": cont - error,
    })
    out.attrs["checks"] = checks
    return out