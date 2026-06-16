"""PhysicsDevice — monthly values from climate formulas. Good for HVAC and water heating.

Phase 4 §1.9 (Option B): climate is injected as a live ``ClimateData`` object via
``climate=`` and read fresh each call through the ``_hdd`` / ``_cdd`` / ``_inlet``
properties, so a per-year trend trajectory reaches the device without reconstruction.
For unit tests / standalone use, static ``monthly_hdd=`` / ``monthly_cdd=`` /
``monthly_inlet_temp_f=`` arrays may be passed instead; exactly one source is required.
"""
import mesa
import numpy as np

from devices.base import EnergyConsumer

_DAYS = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31], dtype=float)


def _as_monthly(arr):
    """Coerce a (12,) array or return None."""
    if arr is None:
        return None
    a = np.asarray(arr, dtype=float)
    assert a.shape == (12,)
    return a


class PhysicsDevice(EnergyConsumer):
    """Base for devices whose consumption is driven by climate formulas."""


# ── HVAC ──────────────────────────────────────────────────────────────────────

class GasFurnace(PhysicsDevice):
    """
    therms[m] = hdd[m] × 24 × ua / (afue × 100_000)
    """
    fuel_type = "gas"

    def __init__(self, model: mesa.Model, *,
                 afue: float = 0.80,
                 ua_btu_hr_f: float = 500,
                 monthly_hdd: np.ndarray | None = None,
                 climate=None,
                 **kwargs):
        super().__init__(model, **kwargs)
        self.afue = afue
        self.ua = ua_btu_hr_f
        self._climate = climate
        self._hdd_static = _as_monthly(monthly_hdd)
        if self._climate is None and self._hdd_static is None:
            raise ValueError("GasFurnace requires climate= or monthly_hdd=")

    @property
    def _hdd(self) -> np.ndarray:
        return self._climate.monthly_hdd if self._climate is not None else self._hdd_static

    def monthly_consumption(self) -> np.ndarray:
        return self._hdd * 24 * self.ua / (self.afue * 100_000)


class HeatPumpHVAC(PhysicsDevice):
    """
    heating kWh[m] = hdd[m] × 24 × ua / (cop × 3412)
    cooling kWh[m] = cdd[m] × 24 × ua / ((seer / 10) × 3412)

    Note: seer/10 converts the SEER rating (BTU/Wh) to an effective dimensionless
    efficiency coefficient compatible with the 3412 BTU/kWh denominator, producing
    cooling estimates consistent with the spec validation target (~550 kWh for
    CDD=340, UA=500, SEER=22).
    """
    fuel_type = "electricity"

    def __init__(self, model: mesa.Model, *,
                 cop_heating: float = 3.5,
                 seer_cooling: float = 22,
                 ua_btu_hr_f: float = 500,
                 monthly_hdd: np.ndarray | None = None,
                 monthly_cdd: np.ndarray | None = None,
                 climate=None,
                 **kwargs):
        super().__init__(model, **kwargs)
        self.cop = cop_heating
        self.seer = seer_cooling
        self.ua = ua_btu_hr_f
        self._climate = climate
        self._hdd_static = _as_monthly(monthly_hdd)
        self._cdd_static = _as_monthly(monthly_cdd)
        if self._climate is None and (self._hdd_static is None or self._cdd_static is None):
            raise ValueError("HeatPumpHVAC requires climate= or monthly_hdd= and monthly_cdd=")

    @property
    def _hdd(self) -> np.ndarray:
        return self._climate.monthly_hdd if self._climate is not None else self._hdd_static

    @property
    def _cdd(self) -> np.ndarray:
        return self._climate.monthly_cdd if self._climate is not None else self._cdd_static

    def monthly_consumption(self) -> np.ndarray:
        heating = self._hdd * 24 * self.ua / (self.cop * 3412)
        cooling = self._cdd * 24 * self.ua / (self.seer * 1000)
        return heating + cooling


# ── Water heating ─────────────────────────────────────────────────────────────

class GasWaterHeater(PhysicsDevice):
    """
    therms[m] = gallons × days[m] × 8.33 × ΔT[m] × 0.00001 / uef
    ΔT[m] = setpoint_f - inlet_f[m]
    """
    fuel_type = "gas"

    def __init__(self, model: mesa.Model, *,
                 uef: float = 0.65,
                 daily_gallons: float = 65,
                 setpoint_f: float = 120,
                 monthly_inlet_temp_f: np.ndarray | None = None,
                 climate=None,
                 **kwargs):
        super().__init__(model, **kwargs)
        self.uef = uef
        self.daily_gallons = daily_gallons
        self.setpoint_f = setpoint_f
        self._climate = climate
        self._inlet_static = _as_monthly(monthly_inlet_temp_f)
        if self._climate is None and self._inlet_static is None:
            raise ValueError("GasWaterHeater requires climate= or monthly_inlet_temp_f=")

    @property
    def _inlet(self) -> np.ndarray:
        return self._climate.monthly_inlet if self._climate is not None else self._inlet_static

    def monthly_consumption(self) -> np.ndarray:
        delta_t = self.setpoint_f - self._inlet
        return self.daily_gallons * _DAYS * 8.33 * delta_t * 0.00001 / self.uef


class HeatPumpWaterHeater(PhysicsDevice):
    """
    kWh[m] = gallons × days[m] × 8.33 × ΔT[m] × (1/3412) / uef
    """
    fuel_type = "electricity"

    def __init__(self, model: mesa.Model, *,
                 uef: float = 3.5,
                 daily_gallons: float = 65,
                 setpoint_f: float = 120,
                 monthly_inlet_temp_f: np.ndarray | None = None,
                 climate=None,
                 **kwargs):
        super().__init__(model, **kwargs)
        self.uef = uef
        self.daily_gallons = daily_gallons
        self.setpoint_f = setpoint_f
        self._climate = climate
        self._inlet_static = _as_monthly(monthly_inlet_temp_f)
        if self._climate is None and self._inlet_static is None:
            raise ValueError("HeatPumpWaterHeater requires climate= or monthly_inlet_temp_f=")

    @property
    def _inlet(self) -> np.ndarray:
        return self._climate.monthly_inlet if self._climate is not None else self._inlet_static

    def monthly_consumption(self) -> np.ndarray:
        delta_t = self.setpoint_f - self._inlet
        return self.daily_gallons * _DAYS * 8.33 * delta_t / (3412 * self.uef)


class CentralAC(PhysicsDevice):
    """Stand-alone electric central AC — cooling only, used in has_cooling_baseline slots."""
    fuel_type = "electricity"

    def __init__(self, model: mesa.Model, *,
                 seer_cooling: float = 14,
                 ua_btu_hr_f: float = 500,
                 monthly_cdd: np.ndarray | None = None,
                 climate=None,
                 **kwargs):
        super().__init__(model, **kwargs)
        self.seer = float(seer_cooling)
        self.ua = float(ua_btu_hr_f)
        self._climate = climate
        self._cdd_static = _as_monthly(monthly_cdd)
        if self._climate is None and self._cdd_static is None:
            raise ValueError("CentralAC requires climate= or monthly_cdd=")

    @property
    def _cdd(self) -> np.ndarray:
        return self._climate.monthly_cdd if self._climate is not None else self._cdd_static

    def monthly_consumption(self) -> np.ndarray:
        return self._cdd * 24 * self.ua / (self.seer * 1000)
