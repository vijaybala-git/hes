"""ScheduleDevice — monthly values supplied directly. Good for EVs and custom profiles."""
import mesa
import numpy as np

from devices.base import EnergyConsumer

_EV_DEFAULT_MONTHLY_KWH = [290, 270, 290, 280, 300, 310, 320, 320, 300, 290, 280, 290]


class ScheduleDevice(EnergyConsumer):
    """Monthly consumption provided as a fixed 12-element array."""

    def __init__(self, model: mesa.Model, *,
                 monthly_values: list,
                 fuel_type: str,
                 **kwargs):
        super().__init__(model, **kwargs)
        self.fuel_type = fuel_type
        self._monthly = np.array(monthly_values, dtype=float)
        assert len(self._monthly) == 12, "monthly_values must have 12 elements"

    def monthly_consumption(self) -> np.ndarray:
        return self._monthly.copy()


class EVCharger(ScheduleDevice):
    """L2 EV charger with a flat default monthly profile (~3,540 kWh/yr)."""
    fuel_type = "electricity"

    def __init__(self, model: mesa.Model, *,
                 monthly_kwh: list = None,
                 **kwargs):
        if monthly_kwh is None:
            monthly_kwh = _EV_DEFAULT_MONTHLY_KWH
        kwargs.setdefault("installation_cost", 800)
        kwargs.setdefault("lifespan", 20)
        super().__init__(model, monthly_values=monthly_kwh,
                         fuel_type="electricity", **kwargs)


class PhysicsEVCharger(EnergyConsumer):
    """
    EV charger with physics-based annual consumption.
    Monthly profile: flat with slight summer uptick (more driving May–Sep).
    annual_kWh = miles_per_year × kwh_per_mile / charging_efficiency
    """
    fuel_type = "electricity"

    SEASONALITY = np.array(
        [0.94, 0.88, 0.94, 0.91, 0.97, 1.00, 1.03, 1.03, 0.97, 0.94, 0.91, 0.94],
        dtype=float,
    )  # sums to 12.0 — multiply by annual/12 to get monthly

    def __init__(self, model: mesa.Model, *,
                 miles_per_year: int = 7000,
                 kwh_per_mile: float = 0.30,
                 charging_efficiency: float = 0.90,
                 **kwargs):
        kwargs.setdefault("installation_cost", 800)
        kwargs.setdefault("lifespan", 20)
        super().__init__(model, **kwargs)
        self.miles_per_year       = miles_per_year
        self.kwh_per_mile         = kwh_per_mile
        self.charging_efficiency  = charging_efficiency

    @property
    def annual_kwh(self) -> float:
        return self.miles_per_year * self.kwh_per_mile / self.charging_efficiency

    def monthly_consumption(self) -> np.ndarray:
        # Distribute annual_kwh proportionally so monthly values always sum to annual_kwh
        weights = self.SEASONALITY / self.SEASONALITY.sum()
        return self.annual_kwh * weights
