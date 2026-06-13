"""DeviceSlot + JourneyHome — the Phase 2 journey model."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import mesa
import numpy as np


@dataclass
class SolarBatteryConfig:
    """Physics model for a solar + optional battery system (§8).

    System size drives production; battery determines self-consumption split;
    NEM mode determines the export credit rate used in model.py.
    """
    panels:          int   = 15       # number of panels (primary sizing input)
    kw_per_panel:    float = 0.42     # kW per panel (standard = 0.42, premium = 0.50)
    specific_yield:  float = 1500.0   # kWh/kW/yr — CA PVWatts typical; ~1,400 coast, ~1,650 inland
    battery_enabled: bool  = True     # On by default — NEM 3.0 + battery is the new-install norm
    battery_kwh:     float = 13.5     # usable battery capacity (one Powerwall-class unit)
    nem_mode:        str   = "nbt"    # "nbt" (NEM 3.0, default) | "nem2" (existing pre-2023)
    nbc:             float = 0.025    # $/kWh non-bypassable charge (NEM 2.0 only)

    @property
    def system_kw(self) -> float:
        return self.panels * self.kw_per_panel

    @property
    def self_consumption_fraction(self) -> float:
        """Two-point model: battery shifts midday surplus to evening demand."""
        return 0.80 if self.battery_enabled else 0.35

# Category constants shared across journey and model layers
CATEGORY_ORDER  = ["Baseload", "WaterHeating", "HVAC_Cooling", "HVAC_Heating", "Transportation"]
CATEGORY_LABELS = {
    "Baseload":       "Baseload",
    "WaterHeating":   "Water Heating",
    "HVAC_Cooling":   "Cooling",
    "HVAC_Heating":   "Heating",
    "Transportation": "Transportation",
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
    style_key:    str          = "panel"  # maps to DEVICE_STYLE in src/ui/device_style.py

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
    style_key:            str = "lights"   # maps to DEVICE_STYLE in src/ui/device_style.py
    lifespan:             int = 15         # baseline device lifespan (years); drives do_nothing_year
    existing_age:         int = 0          # current age of baseline device at sim start

    @property
    def net_install_cost(self) -> float:
        return self.install_cost - self.rebate

    def step(self, current_year: int,
             elec_rates: np.ndarray,
             gas_rates:  np.ndarray,
             is_baseline_home: bool = False,
             elec_rates_by_category: dict | None = None,
             gasoline_rates: np.ndarray | None = None) -> float:
        """
        Step the slot for one simulation year.
        Returns the total OpEx cost for this slot in this year.

        elec_rates_by_category: optional dict {device_class_name: (12,) array}.
          When provided (ACC mode), each electric device uses its category-specific
          effective rate rather than the shared flat rate.  Gas devices always use
          gas_rates regardless of this dict.
        gasoline_rates: shape (12,) in $/gallon; routed to devices with fuel_type="gasoline".
        """
        self._last_active_device = None   # reset; set below after active_list is known
        self._last_gas_therms = 0.0       # gas therms consumed this slot this year
        self._last_gasoline_gallons = 0.0  # gallons consumed (transportation slot only)

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
            elif active.fuel_type == "gasoline":
                rates = gasoline_rates if gasoline_rates is not None else np.zeros(12)
            else:
                rates = gas_rates
            active.step(rates)
            step_cost += active.history["cost"][-1]

        self._last_active_device = active_list[0] if active_list else None

        # Gas therms across ALL active natural-gas devices
        self._last_gas_therms = sum(
            a.history["consumption"][-1]
            for a in active_list
            if a.fuel_type == "gas"
        )

        # Gasoline gallons (transportation slot only)
        self._last_gasoline_gallons = sum(
            a.history["consumption"][-1]
            for a in active_list
            if a.fuel_type == "gasoline"
        )

        # ── CapEx: swap install OR per-device end-of-life replacement ─────────
        # Only log if net cost > 0 — $0 transitions (e.g. transportation) produce
        # no timeline marker and no CapEx bar segment.
        if (self.swap_year is not None
                and current_year == self.swap_year
                and self.starting_state in ("gas", "none")
                and self.net_install_cost > 0):
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
                 solar_config: SolarBatteryConfig | None = None,
                 solar_export_rates: np.ndarray | None = None,
                 elec_rates_by_category: dict | None = None,
                 gasoline_rates: np.ndarray | None = None):
        """
        solar_config: SolarBatteryConfig for the journey home; None for baseline.
        solar_export_rates: (n_years, 12) $/kWh export credit rates. For NEM 3.0 these
          are the ACC avoided-cost values; for NEM 2.0, retail minus NBC. Built in
          HESModel and passed in so JourneyHome.step() needs no rate-loader access.
        elec_rates_by_category: optional dict {device_class_name: (n_years, 12) array}.
          Provided in ACC mode; each electric device uses its category-specific effective
          rate.  None in CAGR mode — all devices share the flat elec_rates array.
        """
        super().__init__(model)
        self.slots = slots
        self._elec_rates = elec_rates   # shape (n_years, 12)
        self._gas_rates  = gas_rates    # shape (n_years, 12)
        self._gasoline_rates = gasoline_rates  # shape (n_years, 12) | None
        self._elec_rates_by_category = elec_rates_by_category  # dict | None
        self._solar_config       = solar_config        # SolarBatteryConfig | None
        self._solar_export_rates = solar_export_rates  # (n_years, 12) | None
        self.is_baseline_home = is_baseline_home
        self.capex_only_slots: list = capex_only_slots or []

        self.annual_opex     = 0.0
        self.cumulative_opex = 0.0
        self.capex_by_year:   dict = {}
        self.capex_by_device: dict = {}  # {style_key: {year: amount}}
        self.solar_savings_history:       list = []  # $/yr bill savings
        self.solar_production_kwh_history: list = []  # kWh/yr gross production
        self.solar_self_consumed_history:  list = []  # kWh/yr self-consumed
        self.solar_exported_kwh_history:   list = []  # kWh/yr exported
        self.gasoline_gallons_history: list = []  # annual gallons (transportation slot)
        self.cost_history_by_category:    dict = {cat: []  for cat in CATEGORY_ORDER}
        self.gas_therms_history:          list = []   # annual gas therms (all gas slots)
        self.cost_history_by_slot:        dict = {s.name: [] for s in slots}
        self.consumption_history_by_slot: dict = {s.name: [] for s in slots}
        self.fuel_history_by_slot:        dict = {s.name: [] for s in slots}

    def step(self):
        year_idx     = self.model.steps - 1   # 0-based array index
        current_year = self.model.steps        # 1-indexed simulation year

        elec_r     = self._elec_rates[year_idx]
        gas_r      = self._gas_rates[year_idx]
        gasoline_r = self._gasoline_rates[year_idx] if self._gasoline_rates is not None else None

        # ACC mode: slice per-device rate arrays for this year
        elec_by_cat_yr = None
        if self._elec_rates_by_category is not None:
            elec_by_cat_yr = {
                cls: arr[year_idx]
                for cls, arr in self._elec_rates_by_category.items()
            }

        # Sum costs per category first, then append once — fixes Phase 1 bug
        year_category_costs    = {cat: 0.0 for cat in CATEGORY_ORDER}
        year_opex              = 0.0
        year_elec_opex         = 0.0
        year_capex             = 0.0
        year_gas_therms        = 0.0
        year_gasoline_gallons  = 0.0

        for slot in self.slots:
            cost = slot.step(current_year, elec_r, gas_r, self.is_baseline_home,
                             elec_rates_by_category=elec_by_cat_yr,
                             gasoline_rates=gasoline_r)
            year_opex += cost
            cat = slot.category if slot.category in year_category_costs else "Baseload"
            year_category_costs[cat] += cost

            year_gas_therms       += getattr(slot, "_last_gas_therms", 0.0)
            year_gasoline_gallons += getattr(slot, "_last_gasoline_gallons", 0.0)

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
                    key = slot.style_key
                    yr_map = self.capex_by_device.setdefault(key, {})
                    yr_map[current_year] = yr_map.get(current_year, 0.0) + event_cost

        # CapEx-only slots (e.g. electrical panel upgrade) — journey home only
        for cslot in self.capex_only_slots:
            cslot.step(current_year)
            for event_year, event_cost in cslot.capex_events:
                if event_year == current_year:
                    year_capex += event_cost
                    key = cslot.style_key
                    yr_map = self.capex_by_device.setdefault(key, {})
                    yr_map[current_year] = yr_map.get(current_year, 0.0) + event_cost

        # Append exactly once per category per step (sum-then-append fix)
        for cat in CATEGORY_ORDER:
            self.cost_history_by_category[cat].append(year_category_costs[cat])

        # Annual gas therms — pure physics, independent of social-cost rates
        self.gas_therms_history.append(year_gas_therms)
        self.gasoline_gallons_history.append(year_gasoline_gallons)

        if year_capex > 0:
            self.capex_by_year[current_year] = (
                self.capex_by_year.get(current_year, 0.0) + year_capex
            )

        # Solar savings — physics model (§8)
        # Install year is read from the Solar CapExOnlySlot so it stays in sync
        # with the capex event on the journey timeline.
        solar_install_yr = None
        for cslot in self.capex_only_slots:
            if "Solar" in cslot.name and cslot.install_year is not None:
                solar_install_yr = cslot.install_year
                break

        if (self._solar_config is not None
                and solar_install_yr is not None
                and current_year >= solar_install_yr):
            cfg = self._solar_config
            annual_production_kwh = cfg.system_kw * cfg.specific_yield
            scf = cfg.self_consumption_fraction   # 0.80 battery, 0.35 solar-only

            self_consumed_kwh = annual_production_kwh * scf
            exported_kwh      = annual_production_kwh * (1.0 - scf)

            # Retail rate: mean of this year's 12 monthly rates.
            # In ACC mode, self._elec_rates uses the flat profile → equals retail.
            avg_retail = float(self._elec_rates[year_idx].mean())

            # Export credit rate from the pre-built (n_years,12) array.
            # NEM 3.0: ACC avoided-cost $/kWh.  NEM 2.0: retail minus NBC.
            avg_export = float(self._solar_export_rates[year_idx].mean()) \
                if self._solar_export_rates is not None else 0.0

            retail_savings = self_consumed_kwh * avg_retail
            export_credit  = exported_kwh      * avg_export
            # Cap at actual electricity spend — solar can't reduce below zero
            solar_saving = min(retail_savings + export_credit, year_elec_opex)
        else:
            annual_production_kwh = 0.0
            self_consumed_kwh     = 0.0
            exported_kwh          = 0.0
            solar_saving          = 0.0

        year_opex -= solar_saving
        self.solar_savings_history.append(solar_saving)
        self.solar_production_kwh_history.append(annual_production_kwh)
        self.solar_self_consumed_history.append(self_consumed_kwh)
        self.solar_exported_kwh_history.append(exported_kwh)

        self.annual_opex      = year_opex
        self.cumulative_opex += year_opex
