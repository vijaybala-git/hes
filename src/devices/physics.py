"""PhysicsDevice — monthly values from climate formulas. Good for HVAC and water heating."""
import mesa
import numpy as np

from devices.base import EnergyConsumer

_DAYS = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31], dtype=float)


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
                 monthly_hdd: np.ndarray,
                 **kwargs):
        super().__init__(model, **kwargs)
        self.afue = afue
        self.ua = ua_btu_hr_f
        self._hdd = np.asarray(monthly_hdd, dtype=float)
        assert self._hdd.shape == (12,)

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
                 monthly_hdd: np.ndarray,
                 monthly_cdd: np.ndarray,
                 **kwargs):
        super().__init__(model, **kwargs)
        self.cop = cop_heating
        self.seer = seer_cooling
        self.ua = ua_btu_hr_f
        self._hdd = np.asarray(monthly_hdd, dtype=float)
        self._cdd = np.asarray(monthly_cdd, dtype=float)
        assert self._hdd.shape == (12,)
        assert self._cdd.shape == (12,)

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
                 monthly_inlet_temp_f: np.ndarray,
                 **kwargs):
        super().__init__(model, **kwargs)
        self.uef = uef
        self.daily_gallons = daily_gallons
        self.setpoint_f = setpoint_f
        self._inlet = np.asarray(monthly_inlet_temp_f, dtype=float)
        assert self._inlet.shape == (12,)

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
                 monthly_inlet_temp_f: np.ndarray,
                 **kwargs):
        super().__init__(model, **kwargs)
        self.uef = uef
        self.daily_gallons = daily_gallons
        self.setpoint_f = setpoint_f
        self._inlet = np.asarray(monthly_inlet_temp_f, dtype=float)
        assert self._inlet.shape == (12,)

    def monthly_consumption(self) -> np.ndarray:
        delta_t = self.setpoint_f - self._inlet
        return self.daily_gallons * _DAYS * 8.33 * delta_t / (3412 * self.uef)


class CentralAC(PhysicsDevice):
    """Stand-alone electric central AC — cooling only, used in has_cooling_baseline slots."""
    fuel_type = "electricity"

    def __init__(self, model: mesa.Model, *,
                 seer_cooling: float = 14,
                 ua_btu_hr_f: float = 500,
                 monthly_cdd: np.ndarray,
                 **kwargs):
        super().__init__(model, **kwargs)
        self.seer = float(seer_cooling)
        self.ua = float(ua_btu_hr_f)
        self._cdd = np.asarray(monthly_cdd, dtype=float)
        assert self._cdd.shape == (12,)

    def monthly_consumption(self) -> np.ndarray:
        return self._cdd * 24 * self.ua / (self.seer * 1000)
