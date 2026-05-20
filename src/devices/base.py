"""EnergyConsumer — abstract base for all simulated devices."""
from abc import abstractmethod

import mesa
import numpy as np


class EnergyConsumer(mesa.Agent):
    """Abstract base. Subclasses implement monthly_consumption()."""

    fuel_type: str  # "electricity" or "gas" — set by subclass

    def __init__(self, model: mesa.Model, *,
                 lifespan: int = 15,
                 installation_cost: float = 0.0,
                 age: int = 0):
        super().__init__(model)
        self.lifespan = lifespan
        self.installation_cost = installation_cost
        self.age = age
        self.capex_events: list = []
        self.history: dict = {"consumption": [], "cost": []}

    @abstractmethod
    def monthly_consumption(self) -> np.ndarray:
        """Return shape (12,) in native unit (kWh or therms)."""

    def annual_consumption(self) -> float:
        return float(self.monthly_consumption().sum())

    def monthly_cost(self, monthly_rates: np.ndarray) -> np.ndarray:
        """monthly_rates shape (12,) in $/kWh or $/therm."""
        return self.monthly_consumption() * monthly_rates

    def step(self, monthly_rates: np.ndarray):
        consumption = self.monthly_consumption()
        cost = self.monthly_cost(monthly_rates)
        self.history["consumption"].append(float(consumption.sum()))
        self.history["cost"].append(float(cost.sum()))
        self.age += 1
