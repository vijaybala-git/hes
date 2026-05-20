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
