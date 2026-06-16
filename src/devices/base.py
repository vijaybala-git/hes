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
                 age: int = 0,
                 circuit_volts: int = 0,
                 circuit_amps: int = 0,
                 continuous: bool = False):
        super().__init__(model)
        self.lifespan = lifespan
        self.installation_cost = installation_cost
        self.age = age
        # ── Electrical nameplate (Phase 3 §2.5) — inert; never affects energy/cost ──
        self.circuit_volts = circuit_volts
        self.circuit_amps  = circuit_amps
        self.continuous    = continuous
        self.capex_events: list = []
        # "monthly_consumption"/"monthly_cost" retain the (12,) vectors (Phase 4 §1) so
        # seasonal end-use charts (HVAC) can show month-by-month detail; the scalar
        # "consumption"/"cost" annual sums are unchanged.
        self.history: dict = {"consumption": [], "cost": [],
                              "monthly_consumption": [], "monthly_cost": []}

    @property
    def rated_va(self) -> float:
        """Nameplate VA = volts × amps. Gas devices leave volts/amps at 0 → 0 VA."""
        return float(self.circuit_volts * self.circuit_amps)

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
        self.history["monthly_consumption"].append(np.asarray(consumption, dtype=float))
        self.history["monthly_cost"].append(np.asarray(cost, dtype=float))
        self.age += 1
