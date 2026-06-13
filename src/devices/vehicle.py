"""GasolineVehicle + ElectricVehicle — transportation device models (§3)."""
from __future__ import annotations

import mesa
import numpy as np

from devices.base import EnergyConsumer

# Mild seasonal driving distribution — summer uptick (vacation travel), winter dip.
# Normalised to sum to 1.0 inside each device.
_DRIVING_SEASONALITY = np.array([
    0.88, 0.88, 0.92, 0.96, 1.04, 1.10,
    1.14, 1.12, 1.02, 0.96, 0.90, 0.88,
], dtype=float)
_WEIGHTS = _DRIVING_SEASONALITY / _DRIVING_SEASONALITY.sum()


class GasolineVehicle(EnergyConsumer):
    """
    ICE vehicle fuel model.  monthly_consumption() returns shape (12,) in gallons.

    Lifespan defaults to 25 (beyond sim horizon) so no do-nothing timeline marker
    is generated for the baseline vehicle — the household is assumed to keep replacing
    ICE vehicles unless they plan a switch.
    """
    fuel_type = "gasoline"

    def __init__(self, model: mesa.Model, *,
                 miles_per_year: float = 12_000,
                 mpg: float = 28.0,
                 **kwargs):
        kwargs.setdefault("lifespan", 25)
        kwargs.setdefault("installation_cost", 0.0)
        super().__init__(model, **kwargs)
        self.miles_per_year = float(miles_per_year)
        self.mpg = float(mpg)

    def monthly_consumption(self) -> np.ndarray:
        annual_gallons = self.miles_per_year / self.mpg
        return annual_gallons * _WEIGHTS


class ElectricVehicle(EnergyConsumer):
    """
    EV charging load.  monthly_consumption() returns shape (12,) in wall-kWh.

    Input basis: battery-out / dashboard efficiency (mi/kWh); charging_efficiency
    converts to wall kWh.  Default 0.88 matches Phase 3 §2.4 value.

    pct_home_charge (Wave 3, §3.13): fraction of wall kWh charged at home (home
    electricity rate); the remainder is billed at the external EV rate. The split
    is performed by DeviceSlot.step(), NOT here — monthly_consumption() always
    returns the full wall kWh regardless of pct_home_charge. Default 1.0 = all home.
    """
    fuel_type = "electricity"

    def __init__(self, model: mesa.Model, *,
                 miles_per_year: float = 12_000,
                 ev_eff_mi_per_kwh: float = 3.5,
                 charging_efficiency: float = 0.88,
                 pct_home_charge: float = 1.0,
                 **kwargs):
        kwargs.setdefault("lifespan", 25)
        kwargs.setdefault("installation_cost", 0.0)
        super().__init__(model, **kwargs)
        self.miles_per_year = float(miles_per_year)
        self.ev_eff_mi_per_kwh = float(ev_eff_mi_per_kwh)
        self.charging_efficiency = float(charging_efficiency)
        self.pct_home_charge = float(pct_home_charge)

    @property
    def annual_wall_kwh(self) -> float:
        battery_kwh = self.miles_per_year / self.ev_eff_mi_per_kwh
        return battery_kwh / self.charging_efficiency

    def monthly_consumption(self) -> np.ndarray:
        return self.annual_wall_kwh * _WEIGHTS
