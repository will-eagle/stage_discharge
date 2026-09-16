import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt

from .build_stage import _require_si, _require_utc   # same SI + UTC guards as the physics
from .conversions import to_units                    # SI -> US for display


def _to_si_values(x, *, si_length=False):
    """Coerce stage/discharge to a float array, enforcing the pipeline's SI + UTC
    contract on any pandas input. A DatetimeIndex must be UTC; a stage series
    (si_length=True) must carry an SI length suffix (_m). Bare arrays -- e.g.
    hand-entered field measurements -- pass through, their SI contract (m, m^3/s)
    resting on the caller."""
    if isinstance(x, (pd.Series, pd.DataFrame)):
        if isinstance(x.index, pd.DatetimeIndex):
            _require_utc(x.index)
        if si_length:
            names = list(x.columns) if isinstance(x, pd.DataFrame) else [x.name]
            _require_si([n for n in names if n is not None])
    return np.asarray(x, dtype=float)


class RatingCurve:
    """Fit a stage-discharge rating from field measurements, then predict
    discharge from a stage series."""

    def __init__(self, site_id):
        self.site = site_id
        self.measurements = None
        self.stage = None
        self.discharge = None
        self.model = None
        self.popt = None
        self.pcov = None
        self.method = None

    @staticmethod
    def power_law(x, a, b, k):
        return a * (x - b) ** k

    @staticmethod
    def linear(x, m, b):
        return m * x + b

    @staticmethod
    def log_linear(x, m, b):
        return m * np.log(x) + b

    def calculate_curve(self, method="powerlaw"):
        models = {
            "powerlaw": self.power_law, 
            "linear": self.linear, 
            "log_linear": self.log_linear
        }
        if method not in models:
            raise ValueError(f"method must be one of {sorted(models)}, got {method!r}")
        
        self.model = models[method]
        self.method = method
        
        if self.stage is None or self.discharge is None:
            raise RuntimeError("stage and discharge data must be set before calling calculate_curve()")

        # SI + UTC required for the fit: stage in metres, discharge in m^3/s.
        stage = _to_si_values(self.stage, si_length=True)
        discharge = _to_si_values(self.discharge)
        
        # Fit in log-log space if log_linear is selected
        if method == "log_linear":
            xdata = stage
            ydata = np.log(discharge)
        else:
            xdata = stage
            ydata = discharge

        # powerlaw a*(x-b)**k NaNs when x <= b, so the default p0=[1,1,1] rarely
        # converges. Seed b (cease-to-flow) just below the lowest stage so the base
        # stays positive, with a modest exponent.
        p0 = None
        if method == "powerlaw":
            span = (stage.max() - stage.min()) or 1.0
            p0 = [1.0, stage.min() - 0.1 * span, 2.0]

        self.popt, self.pcov = curve_fit(self.model, xdata, ydata, p0=p0)
        return self.popt, self.pcov

    def predict(self, stage):
        if self.model is None:
            raise RuntimeError("call calculate_curve() before predict()")

        # A pipeline stage series must be SI (metres) and UTC-indexed.
        stage_arr = _to_si_values(stage, si_length=True)
        pred = self.model(stage_arr, *self.popt)
        
        # Exponentiate back to linear discharge units if using log_linear
        if self.method == "log_linear":
            return np.exp(pred)
            
        return pred

    def plot_measurements(self):
        """Plot raw field measurements and the fitted rating curve."""
        if self.stage is None or self.discharge is None:
            raise RuntimeError("stage and discharge data must be set before plotting()")
            
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # Scatter plot for raw measurements
        ax.scatter(
            self.stage, self.discharge, 
            color='dodgerblue', edgecolor='black', linewidth=0.8, 
            s=60, zorder=3, label='Field Measurements'
        )
        
        # Smooth curve overlay if model is fitted
        if self.model is not None and self.popt is not None:
            stage_smooth = np.linspace(np.min(self.stage), np.max(self.stage), 200)
            discharge_smooth = self.predict(stage_smooth)
            ax.plot(
                stage_smooth, discharge_smooth, 
                color='crimson', linewidth=2.5, linestyle='-', 
                zorder=2, label=f'Fitted Curve ({self.method})'
            )
            
        ax.set_xlabel("Stage (m)", fontsize=11, fontweight='semibold')
        ax.set_ylabel("Discharge (m³/s)", fontsize=11, fontweight='semibold')
        ax.set_title(f"Stage-Discharge Rating Curve — Site: {self.site}", fontsize=13, fontweight='bold', pad=12)
        
        ax.grid(True, linestyle='--', alpha=0.5, zorder=1)
        ax.legend(frameon=True, facecolor='white', edgecolor='lightgray', fontsize=10)
        
        plt.tight_layout()
        plt.show()

    def plot_discharge(self, stage, units='SI', yscale = 'linear'):
        """Plot predicted discharge over time from a stage series.

        `stage` is a water_level_m Series on a UTC index (e.g. build_stage output);
        predict() enforces SI + UTC. Discharge is predicted in m³/s; units='US'
        converts the series to cfs (via to_units) before plotting.
        """
        pred = pd.DataFrame({"discharge_cms": self.predict(stage)},
                            index=getattr(stage, "index", None))
        if units == 'US':
            pred = to_units(pred, "US")          # discharge_cms -> discharge_cfs
        col = pred.columns[0]

        fig, ax = plt.subplots(figsize=(14, 5))
        ax.plot(pred.index, pred[col], color='blue')
        ax.set_xlabel('Datetime')
        ax.set_ylabel('Discharge (cfs)' if units == 'US' else 'Discharge (m³/s)')
        ax.set_title(f'{self.site} Discharge')
        ax.set_yscale(yscale)
        plt.tight_layout()
        plt.show()
        
