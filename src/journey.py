"""DeviceSlot + JourneyHome — the Phase 2 journey model."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

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
class CapExOnlySlot:
    """
    A CapEx-only event (no energy consumption, no OpEx).
    Used for e.g. electrical panel upgrades that cost money but use no energy.
    Baseline home never receives these — they are proactive journey choices.
    """
    name:         str
    category:     str          = "Infrastructure"
    install_cost: float        = 3000.0
    rebate:       float        = 0.0
    lifespan:     int          = 25
    install_year: Optional[int] = None   # None = not planning
    capex_events: list         = field(default_factory=list)

    @property
    def net_install_cost(self) -> float:
        return self.install_cost - self.rebate

    def step(self, current_year: int, **_):
        """Log CapEx at install_year; end-of-life replacement at install_year + lifespan."""
        if self.install_year is None:
            return
        if current_year == self.install_year:
            self.capex_events.append((current_year, self.net_install_cost))
        eol = self.install_year + self.lifespan
        if current_year == eol:
            self.capex_events.append((current_year, self.install_cost))


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
             is_baseline_home: bool = False,
             elec_rates_by_category: dict | None = None) -> float:
        """
        Step the slot for one simulation year.
        Returns the total OpEx cost for this slot in this year.

        elec_rates_by_category: optional dict {device_class_name: (12,) array}.
          When provided (ACC mode), each electric device uses its category-specific
          effective rate rather than the shared flat rate.  Gas devices always use
          gas_rates regardless of this dict.
        """
        self._last_active_device = None   # reset; set below after active_list is known

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
            if active.fuel_type == "electricity" and elec_rates_by_category is not None:
                cls_name = type(active).__name__
                rates = elec_rates_by_category.get(cls_name, elec_rates)
            elif active.fuel_type == "electricity":
                rates = elec_rates
            else:
                rates = gas_rates
            active.step(rates)
            step_cost += active.history["cost"][-1]

        self._last_active_device = active_list[0] if active_list else None

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
                 is_baseline_home: bool = False,
                 capex_only_slots: list | None = None,
                 solar_coverage_pct: float = 0.0,
                 elec_rates_by_category: dict | None = None):
        """
        elec_rates_by_category: optional dict {device_class_name: (n_years, 12) array}.
          Provided in ACC mode; each electric device uses its category-specific effective
          rate.  None in CAGR mode — all devices share the flat elec_rates array.
        """
        super().__init__(model)
        self.slots = slots
        self._elec_rates = elec_rates   # shape (n_years, 12)
        self._gas_rates  = gas_rates    # shape (n_years, 12)
        # ACC mode: per-device-class rate arrays indexed as [n_years, 12]
        self._elec_rates_by_category = elec_rates_by_category  # dict | None
        self.is_baseline_home = is_baseline_home
        self.capex_only_slots: list = capex_only_slots or []
        self.solar_coverage_pct = solar_coverage_pct

        self.annual_opex     = 0.0
        self.cumulative_opex = 0.0
        self.capex_by_year: dict = {}
        self.solar_savings_history: list = []
        self.cost_history_by_category:    dict = {cat: []  for cat in CATEGORY_ORDER}
        self.cost_history_by_slot:        dict = {s.name: [] for s in slots}
        self.consumption_history_by_slot: dict = {s.name: [] for s in slots}
        self.fuel_history_by_slot:        dict = {s.name: [] for s in slots}

    def step(self):
        year_idx     = self.model.steps - 1   # 0-based array index
        current_year = self.model.steps        # 1-indexed simulation year

        elec_r = self._elec_rates[year_idx]
        gas_r  = self._gas_rates[year_idx]

        # ACC mode: slice per-device rate arrays for this year
        elec_by_cat_yr = None
        if self._elec_rates_by_category is not None:
            elec_by_cat_yr = {
                cls: arr[year_idx]
                for cls, arr in self._elec_rates_by_category.items()
            }

        # Sum costs per category first, then append once — fixes Phase 1 bug
        year_category_costs = {cat: 0.0 for cat in CATEGORY_ORDER}
        year_opex      = 0.0
        year_elec_opex = 0.0
        year_capex     = 0.0

        for slot in self.slots:
            cost = slot.step(current_year, elec_r, gas_r, self.is_baseline_home,
                             elec_rates_by_category=elec_by_cat_yr)
            year_opex += cost
            cat = slot.category if slot.category in year_category_costs else "Baseload"
            year_category_costs[cat] += cost

            self.cost_history_by_slot[slot.name].append(cost)
            active_dev = slot._last_active_device
            if active_dev is not None:
                self.consumption_history_by_slot[slot.name].append(
                    active_dev.history["consumption"][-1])
                self.fuel_history_by_slot[slot.name].append(active_dev.fuel_type)
                if active_dev.fuel_type == "electricity":
                    year_elec_opex += cost
            else:
                self.consumption_history_by_slot[slot.name].append(0.0)
                self.fuel_history_by_slot[slot.name].append("electricity")

            for event_year, event_cost in slot.capex_events:
                if event_year == current_year:
                    year_capex += event_cost

        # CapEx-only slots (e.g. electrical panel upgrade) — journey home only
        for cslot in self.capex_only_slots:
            cslot.step(current_year)
            for event_year, event_cost in cslot.capex_events:
                if event_year == current_year:
                    year_capex += event_cost

        # Append exactly once per category per step (sum-then-append fix)
        for cat in CATEGORY_ORDER:
            self.cost_history_by_category[cat].append(year_category_costs[cat])

        if year_capex > 0:
            self.capex_by_year[current_year] = (
                self.capex_by_year.get(current_year, 0.0) + year_capex
            )

        # Solar savings gated by install_year (see §19.1 fix above)
        # Appliance opex gated by swap_year in DeviceSlot.step() — correct
        solar_install_yr = None
        for cslot in self.capex_only_slots:
            if "Solar" in cslot.name and cslot.install_year is not None:
                solar_install_yr = cslot.install_year
                break
        if (self.solar_coverage_pct > 0
                and solar_install_yr is not None
                and current_year >= solar_install_yr):
            solar_saving = year_elec_opex * (self.solar_coverage_pct / 100.0)
        else:
            solar_saving = 0.0
        year_opex -= solar_saving
        self.solar_savings_history.append(solar_saving)

        self.annual_opex      = year_opex
        self.cumulative_opex += year_opex
