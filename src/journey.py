"""DeviceSlot + JourneyHome — the Phase 2 journey model."""
from __future__ import annotations

from dataclasses import dataclass, field

import mesa
import numpy as np

# Category constants shared across journey and model layers
CATEGORY_ORDER  = ["Baseload", "WaterHeating", "HVAC_Cooling", "HVAC_Heating"]
CATEGORY_LABELS = {
    "Baseload":     "Baseload",
    "WaterHeating": "Water Heating",
    "HVAC_Cooling": "Cooling",
    "HVAC_Heating": "Heating",
}


@dataclass
class DeviceSlot:
    """One appliance position in a home.  Tracks gas→electric transition over time."""

    name:               str
    category:           str
    starting_state:     str          # "gas" | "electric" | "none"
    baseline_devices:   list         # list[EnergyConsumer] — empty list for "electric"/"none"

    has_cooling_baseline: bool = False   # HVAC only: True when home already has central AC
    electric_device:      object = None  # EnergyConsumer; None only when never planned
    swap_year:            int | None = None
    install_cost:         float = 0.0
    rebate:               float = 0.0
    capex_events:         list = field(default_factory=list)  # [(year, cost)]

    @property
    def net_install_cost(self) -> float:
        return self.install_cost - self.rebate

    def step(self, current_year: int,
             elec_rates: np.ndarray,
             gas_rates:  np.ndarray,
             is_baseline_home: bool = False) -> float:
        """
        Step the slot for one simulation year.
        Returns the total OpEx cost for this slot in this year.
        """
        # ── Determine which devices are active this year ──────────────────────
        if self.starting_state == "electric":
            active_list = [self.electric_device]

        elif self.starting_state == "none" and is_baseline_home:
            return 0.0  # absent from baseline — zero cost, zero consumption

        elif self.swap_year is None or current_year < self.swap_year:
            active_list = self.baseline_devices   # gas phase (may be empty for "none")

        else:
            active_list = [self.electric_device]  # post-swap (including swap year)

        # ── Run active devices, accumulate step cost ──────────────────────────
        step_cost = 0.0
        for active in active_list:
            rates = elec_rates if active.fuel_type == "electricity" else gas_rates
            active.step(rates)
            step_cost += active.history["cost"][-1]

        # ── CapEx: swap install OR per-device end-of-life replacement ─────────
        if (self.swap_year is not None
                and current_year == self.swap_year
                and self.starting_state in ("gas", "none")):
            self.capex_events.append((current_year, self.net_install_cost))
        else:
            for active in active_list:
                if active.age >= active.lifespan:
                    self.capex_events.append((current_year, active.installation_cost))
                    active.age = 0

        return step_cost


class JourneyHome(mesa.Agent):
    """
    Simulates one home over time using a list of DeviceSlot objects.
    Two instances run in parallel: the user's journey and the do-nothing baseline.
    """

    def __init__(self, model: mesa.Model,
                 slots: list,
                 elec_rates: np.ndarray,
                 gas_rates:  np.ndarray,
                 is_baseline_home: bool = False):
        super().__init__(model)
        self.slots = slots
        self._elec_rates = elec_rates   # shape (n_years, 12)
        self._gas_rates  = gas_rates    # shape (n_years, 12)
        self.is_baseline_home = is_baseline_home

        self.annual_opex     = 0.0
        self.cumulative_opex = 0.0
        self.capex_by_year: dict = {}
        self.cost_history_by_category: dict = {cat: [] for cat in CATEGORY_ORDER}

    def step(self):
        year_idx     = self.model.steps - 1   # 0-based array index
        current_year = self.model.steps        # 1-indexed simulation year

        elec_r = self._elec_rates[year_idx]
        gas_r  = self._gas_rates[year_idx]

        # Sum costs per category first, then append once — fixes Phase 1 bug
        year_category_costs = {cat: 0.0 for cat in CATEGORY_ORDER}
        year_opex  = 0.0
        year_capex = 0.0

        for slot in self.slots:
            cost = slot.step(current_year, elec_r, gas_r, self.is_baseline_home)
            year_opex += cost
            cat = slot.category if slot.category in year_category_costs else "Baseload"
            year_category_costs[cat] += cost

            for event_year, event_cost in slot.capex_events:
                if event_year == current_year:
                    year_capex += event_cost

        # Append exactly once per category per step (sum-then-append fix)
        for cat in CATEGORY_ORDER:
            self.cost_history_by_category[cat].append(year_category_costs[cat])

        if year_capex > 0:
            self.capex_by_year[current_year] = (
                self.capex_by_year.get(current_year, 0.0) + year_capex
            )

        self.annual_opex      = year_opex
        self.cumulative_opex += year_opex
