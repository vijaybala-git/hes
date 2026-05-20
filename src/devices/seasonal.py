"""SeasonalDevice — annual total × monthly weights. Good for dryers, cooktops, lights."""
import mesa
import numpy as np

from devices.base import EnergyConsumer

_FLAT = [1 / 12] * 12  # uniform monthly distribution


class SeasonalDevice(EnergyConsumer):
    """Distributes a fixed annual total across months via seasonality weights."""

    def __init__(self, model: mesa.Model, *,
                 annual_total: float,
                 seasonality: list,
                 fuel_type: str,
                 **kwargs):
        super().__init__(model, **kwargs)
        self.fuel_type = fuel_type
        self._annual_total = float(annual_total)
        weights = np.array(seasonality, dtype=float)
        assert len(weights) == 12, "seasonality must have 12 values"
        self._seasonality = weights / weights.sum()  # normalise

    def monthly_consumption(self) -> np.ndarray:
        return self._annual_total * self._seasonality


# ── Gas seasonal devices ───────────────────────────────────────────────────────

class GasDryer(SeasonalDevice):
    fuel_type = "gas"

    def __init__(self, model: mesa.Model, *,
                 therms_per_cycle: float = 0.22,
                 cycles_per_week: float = 5,
                 **kwargs):
        annual_total = therms_per_cycle * cycles_per_week * 52
        super().__init__(model, annual_total=annual_total,
                         seasonality=_FLAT, fuel_type="gas", **kwargs)


class GasCooktop(SeasonalDevice):
    fuel_type = "gas"

    def __init__(self, model: mesa.Model, *,
                 therms_per_meal: float = 0.05,
                 meals_per_week: float = 14,
                 **kwargs):
        annual_total = therms_per_meal * meals_per_week * 52
        super().__init__(model, annual_total=annual_total,
                         seasonality=_FLAT, fuel_type="gas", **kwargs)


# ── Electric seasonal devices ─────────────────────────────────────────────────

class HeatPumpDryer(SeasonalDevice):
    fuel_type = "electricity"

    def __init__(self, model: mesa.Model, *,
                 kwh_per_cycle: float = 1.8,
                 cycles_per_week: float = 5,
                 **kwargs):
        annual_total = kwh_per_cycle * cycles_per_week * 52
        super().__init__(model, annual_total=annual_total,
                         seasonality=_FLAT, fuel_type="electricity", **kwargs)


class InductionCooktop(SeasonalDevice):
    fuel_type = "electricity"

    def __init__(self, model: mesa.Model, *,
                 kwh_per_meal: float = 0.9,
                 meals_per_week: float = 14,
                 **kwargs):
        annual_total = kwh_per_meal * meals_per_week * 52
        super().__init__(model, annual_total=annual_total,
                         seasonality=_FLAT, fuel_type="electricity", **kwargs)


class LightsAndPlugs(SeasonalDevice):
    fuel_type = "electricity"

    def __init__(self, model: mesa.Model, *,
                 annual_kwh: float = 1200,
                 **kwargs):
        super().__init__(model, annual_total=annual_kwh,
                         seasonality=_FLAT, fuel_type="electricity", **kwargs)


class Dishwasher(SeasonalDevice):
    fuel_type = "electricity"

    def __init__(self, model: mesa.Model, *,
                 kwh_per_cycle: float = 1.2,
                 cycles_per_week: float = 5,
                 **kwargs):
        annual_total = kwh_per_cycle * cycles_per_week * 52
        super().__init__(model, annual_total=annual_total,
                         seasonality=_FLAT, fuel_type="electricity", **kwargs)


class ElectricOven(SeasonalDevice):
    fuel_type = "electricity"

    def __init__(self, model: mesa.Model, *,
                 kwh_per_cycle: float = 2.0,
                 cycles_per_week: float = 5,
                 **kwargs):
        annual_total = kwh_per_cycle * cycles_per_week * 52
        super().__init__(model, annual_total=annual_total,
                         seasonality=_FLAT, fuel_type="electricity", **kwargs)
