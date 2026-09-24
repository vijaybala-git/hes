"""DeviceSlot + JourneyHome — the Phase 2 journey model."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import mesa
import numpy as np

from dispatch import dispatch_month

_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


@dataclass
class SolarConfig:
    """Solar array (Phase 6 WS2 §2a — split from SolarBatteryConfig). User choices only.

    Production per kW comes from the home's location — HomeConfig.solar_resource (PVWatts
    per-ZIP table) — and self-consumption is an OUTPUT of the hourly energy balance
    (dispatch.py, Phase 7 §0/§2), never a field here.
    """
    panels:          int   = 15       # number of panels (primary sizing input)
    kw_per_panel:    float = 0.42     # kW per panel (standard = 0.42, premium = 0.50)
    nem_mode:        str   = "nbt"    # "nbt" (NEM 3.0, default) | "nem2" (existing pre-2023)
    nbc:             float = 0.025    # $/kWh non-bypassable charge (NEM 2.0 only)

    @property
    def system_kw(self) -> float:
        return self.panels * self.kw_per_panel


@dataclass
class BatteryConfig:
    """Home battery — live physics in the hourly energy balance (Phase 7 §2)."""
    battery_enabled: bool  = True     # On by default — NEM 3.0 + battery is the new-install norm
    battery_kwh:     float = 13.5     # usable capacity (one Powerwall-class unit)
    round_trip_eff:  float = 0.90     # energy out / energy in (√η on charge and on discharge)
    power_kw:        float = 5.0      # charge / discharge limit
    grid_charging:   bool  = True     # Cost-saving mode may top up from the grid when it pays

    def params(self):
        """dispatch.BatteryParams for this battery (capacity 0 when switched off)."""
        from dispatch import BatteryParams
        return BatteryParams(cap_kwh=self.battery_kwh if self.battery_enabled else 0.0,
                             round_trip_eff=self.round_trip_eff, power_kw=self.power_kw,
                             grid_charging=self.grid_charging)


@dataclass
class SolarBatteryConfig:
    """Back-compat composition shim over SolarConfig + BatteryConfig (Phase 6 WS2 §2a).

    Keeps the flat constructor used by model.py / ui/sim.py wiring and tests. `.solar` /
    `.battery` expose the two split configs. Retiring the shim is a pure refactor (no numbers
    change), deferred to its own commit after Phase 7 commit C.
    """
    panels:          int   = 15
    kw_per_panel:    float = 0.42
    battery_enabled: bool  = True
    battery_kwh:     float = 13.5
    nem_mode:        str   = "nbt"
    nbc:             float = 0.025
    round_trip_eff:  float = 0.90
    power_kw:        float = 5.0
    grid_charging:   bool  = True

    @property
    def system_kw(self) -> float:
        return self.panels * self.kw_per_panel

    @property
    def solar(self) -> SolarConfig:
        return SolarConfig(panels=self.panels, kw_per_panel=self.kw_per_panel,
                           nem_mode=self.nem_mode, nbc=self.nbc)

    @property
    def battery(self) -> BatteryConfig:
        return BatteryConfig(battery_enabled=self.battery_enabled, battery_kwh=self.battery_kwh,
                             round_trip_eff=self.round_trip_eff, power_kw=self.power_kw,
                             grid_charging=self.grid_charging)

    @classmethod
    def from_parts(cls, solar: SolarConfig, battery: BatteryConfig) -> "SolarBatteryConfig":
        """Compose the shim from the two split configs (round-trips with .solar/.battery)."""
        return cls(panels=solar.panels, kw_per_panel=solar.kw_per_panel,
                   battery_enabled=battery.battery_enabled, battery_kwh=battery.battery_kwh,
                   nem_mode=solar.nem_mode, nbc=solar.nbc,
                   round_trip_eff=battery.round_trip_eff, power_kw=battery.power_kw,
                   grid_charging=battery.grid_charging)

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
             gasoline_rates: np.ndarray | None = None,
             external_ev_rates: np.ndarray | None = None) -> float:
        """
        Step the slot for one simulation year.
        Returns the total OpEx cost for this slot in this year.

        elec_rates_by_category: optional dict {device_class_name: (12,) array}.
          When provided (ACC mode), each electric device uses its category-specific
          effective rate rather than the shared flat rate.  Gas devices always use
          gas_rates regardless of this dict.
        gasoline_rates: shape (12,) in $/gallon; routed to devices with fuel_type="gasoline".
        external_ev_rates: shape (12,) in $/kWh; the external (public/workplace) charging
          rate used for the non-home fraction of an EV with pct_home_charge < 1.0 (§3.13).
          The home fraction uses elec_rates and is what lands on the home meter.
        """
        self._last_active_device = None   # reset; set below after active_list is known
        self._last_gas_therms = 0.0       # gas therms consumed this slot this year
        self._last_gasoline_gallons = 0.0  # gallons consumed (transportation slot only)
        self._last_external_ev_kwh = 0.0   # external (non-home) EV charging kWh (§3.13)
        self._last_external_ev_cost = 0.0  # external EV charging cost — excluded from elec opex

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
            if active.fuel_type == "electricity":
                if elec_rates_by_category is not None:
                    cls_name = type(active).__name__
                    rates = elec_rates_by_category.get(cls_name, elec_rates)
                else:
                    rates = elec_rates

                # §3.13 — EV home/external charging split (two-pass, never blended).
                # Home fraction → home rate (lands on the home meter / elec opex);
                # external fraction → external_ev_rates (separate cost stream).
                pct_home = getattr(active, "pct_home_charge", 1.0)
                if pct_home < 1.0 and external_ev_rates is not None:
                    monthly_cons = active.monthly_consumption()   # (12,) full wall kWh
                    wall_kwh  = float(monthly_cons.sum())
                    ext_frac  = 1.0 - pct_home
                    home_cost = float((monthly_cons * pct_home * rates).sum())
                    ext_cost  = float((monthly_cons * ext_frac * external_ev_rates).sum())
                    # Device history reflects the HOME meter only — so EU.3 (Annual kWh)
                    # and year_elec_opex see home-charged kWh/cost, not the external part.
                    active.history["consumption"].append(wall_kwh * pct_home)
                    active.history["cost"].append(home_cost)
                    active.history["monthly_consumption"].append(
                        np.asarray(monthly_cons * pct_home, dtype=float))
                    active.history["monthly_cost"].append(
                        np.asarray(monthly_cons * pct_home * rates, dtype=float))
                    active.age += 1
                    step_cost += home_cost + ext_cost
                    self._last_external_ev_kwh  += wall_kwh * ext_frac
                    self._last_external_ev_cost += ext_cost
                    continue
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
                 solar_resource=None,
                 hourly_load_shapes: dict | None = None,
                 rate_structure=None,
                 rate_escalation: np.ndarray | None = None,
                 elec_rates_by_category: dict | None = None,
                 gasoline_rates: np.ndarray | None = None,
                 external_ev_rates: np.ndarray | None = None):
        """
        solar_config: SolarBatteryConfig for the journey home; None for baseline.
        solar_resource: SolarResource (HomeConfig.solar_resource) — per-kW PVWatts yield for the
          home's ZIP. Required whenever solar_config is given.
        solar_export_rates: (n_years, 12, 24) $/kWh export credit by month × clock hour. For
          NEM 3.0 these are the ACC hourly avoided-cost values for each calendar year; for NEM
          2.0, retail minus NBC. Built in HESModel and passed in so JourneyHome.step() needs
          no rate-loader access.
        elec_rates_by_category: optional dict {device_class_name: (n_years, 12) array}.
          Provided in ACC mode; each electric device uses its category-specific effective
          rate.  None in CAGR mode — all devices share the flat elec_rates array.
        """
        super().__init__(model)
        self.slots = slots
        self._elec_rates = elec_rates   # shape (n_years, 12)
        self._gas_rates  = gas_rates    # shape (n_years, 12)
        self._gasoline_rates = gasoline_rates  # shape (n_years, 12) | None
        self._external_ev_rates = external_ev_rates  # shape (n_years, 12) | None
        self._elec_rates_by_category = elec_rates_by_category  # dict | None
        self._solar_config       = solar_config        # SolarBatteryConfig | None
        self._solar_export_rates = solar_export_rates  # (n_years, 12, 24) | None
        self._solar_resource     = solar_resource      # SolarResource | None (Phase 7 §1)
        # {device class name: (24,) clock-hour shape summing to 1, "_default": flat} — spreads
        # each electric device's monthly kWh over the representative day (Phase 7 §0.1).
        self._hourly_load_shapes = hourly_load_shapes or {}
        # URDB TOU tariff (Phase 7 §3): tiers + fixed charge applied on the home aggregate;
        # None → today's per-device flat/ACC pricing only.
        self._rate_structure  = rate_structure
        self._rate_escalation = rate_escalation      # (n_years,) $ multiplier | None
        if solar_config is not None and solar_resource is None:
            raise ValueError("solar_config requires solar_resource (HomeConfig.solar_resource)")
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
        # Phase 7 §0/§2 energy balance (kWh/yr unless noted)
        self.solar_direct_history:         list = []  # solar → home, same hour
        self.battery_discharge_history:    list = []  # battery → home
        self.battery_charge_grid_history:  list = []  # grid → battery (Cost-saving top-up)
        self.battery_losses_history:       list = []  # round-trip losses
        self.grid_import_kwh_history:      list = []  # utility → home + battery (with solar)
        self.battery_mode_history:         list = []  # per year: 12 × "self" | "cost"
        self.solar_monthly_bills_history:  list = []  # per year: 12 × {mode: $} (each mode run)
        self.home_elec_bill_history:       list = []  # $/yr home-meter electricity before solar
        self.home_load_hourly_history:     list = []  # per year: (12, 24) kWh representative days | None
        self.gasoline_gallons_history: list = []  # annual gallons (transportation slot)
        self.external_ev_kwh_history:  list = []  # annual external (public) EV charging kWh
        self.external_ev_cost_history: list = []  # annual external EV charging cost ($)
        self.cost_history_by_category:    dict = {cat: []  for cat in CATEGORY_ORDER}
        self.gas_therms_history:          list = []   # annual gas therms (all gas slots)
        self.cost_history_by_slot:        dict = {s.name: [] for s in slots}
        self.consumption_history_by_slot: dict = {s.name: [] for s in slots}
        self.fuel_history_by_slot:        dict = {s.name: [] for s in slots}
        # (12,) per year for seasonal end-use charts (HVAC) — Phase 4 §1.
        self.monthly_consumption_history_by_slot: dict = {s.name: [] for s in slots}
        self.monthly_cost_history_by_slot:        dict = {s.name: [] for s in slots}

    def _month_loads(self, load_by_class: dict) -> list:
        """12 representative-day home loads (24,) from monthly kWh per device class."""
        default_shape = self._hourly_load_shapes.get("_default", np.full(24, 1.0 / 24))
        out = []
        for m in range(12):
            L = np.zeros(24)
            for cls, kwh in load_by_class.items():
                L = L + kwh[m] / _DAYS_IN_MONTH[m] * self._hourly_load_shapes.get(cls, default_shape)
            out.append(L)
        return out

    def step(self):
        year_idx     = self.model.steps - 1   # 0-based array index
        current_year = self.model.steps        # 1-indexed simulation year

        elec_r     = self._elec_rates[year_idx]
        gas_r      = self._gas_rates[year_idx]
        gasoline_r = self._gasoline_rates[year_idx] if self._gasoline_rates is not None else None
        external_ev_r = self._external_ev_rates[year_idx] if self._external_ev_rates is not None else None

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
        year_external_ev_kwh   = 0.0
        year_external_ev_cost  = 0.0
        # (12, 24)-ready: monthly home-meter electric kWh per device class (Phase 7 §0.1)
        year_elec_load_by_class: dict = {}
        year_category_elec_costs = {cat: 0.0 for cat in CATEGORY_ORDER}   # home-meter $ only

        for slot in self.slots:
            cost = slot.step(current_year, elec_r, gas_r, self.is_baseline_home,
                             elec_rates_by_category=elec_by_cat_yr,
                             gasoline_rates=gasoline_r,
                             external_ev_rates=external_ev_r)
            year_opex += cost
            cat = slot.category if slot.category in year_category_costs else "Baseload"
            year_category_costs[cat] += cost

            year_gas_therms       += getattr(slot, "_last_gas_therms", 0.0)
            year_gasoline_gallons += getattr(slot, "_last_gasoline_gallons", 0.0)
            slot_ext_cost          = getattr(slot, "_last_external_ev_cost", 0.0)
            year_external_ev_kwh  += getattr(slot, "_last_external_ev_kwh", 0.0)
            year_external_ev_cost += slot_ext_cost

            self.cost_history_by_slot[slot.name].append(cost)
            active_dev = slot._last_active_device
            if active_dev is not None:
                self.consumption_history_by_slot[slot.name].append(
                    active_dev.history["consumption"][-1])
                self.fuel_history_by_slot[slot.name].append(active_dev.fuel_type)
                # Seasonal (12,) detail for end-use charts (HVAC); guarded for any device
                # whose history carries the monthly vectors this year (§1).
                mc = active_dev.history.get("monthly_consumption")
                if mc:
                    self.monthly_consumption_history_by_slot[slot.name].append(mc[-1])
                    self.monthly_cost_history_by_slot[slot.name].append(
                        active_dev.history["monthly_cost"][-1])
                else:
                    self.monthly_consumption_history_by_slot[slot.name].append(np.zeros(12))
                    self.monthly_cost_history_by_slot[slot.name].append(np.zeros(12))
                if active_dev.fuel_type == "electricity":
                    home_monthly = (np.asarray(mc[-1], dtype=float) if mc else
                                    np.full(12, active_dev.history["consumption"][-1] / 12.0))
                    cls = type(active_dev).__name__
                    year_elec_load_by_class[cls] = (year_elec_load_by_class.get(cls, 0.0)
                                                    + home_monthly)
                    # §3.13 — external EV charging is NOT on the home meter; exclude it
                    # from elec opex so the §8 solar cap can't offset public charging.
                    year_elec_opex += cost - slot_ext_cost
                    year_category_elec_costs[cat] += cost - slot_ext_cost
            else:
                self.consumption_history_by_slot[slot.name].append(0.0)
                self.fuel_history_by_slot[slot.name].append("electricity")
                self.monthly_consumption_history_by_slot[slot.name].append(np.zeros(12))
                self.monthly_cost_history_by_slot[slot.name].append(np.zeros(12))

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

        # ── URDB TOU home-level bill (Phase 7 §0.1/§0.2/§3) ──────────────────────
        # Devices were priced at their own tier-1 peak-weighted rate. The real bill walks the
        # baseline tiers on the HOME's monthly total and adds the fixed charge; the difference
        # is spread over categories in proportion to their electric cost (presentation only —
        # the home total is exact).
        home_bill_no_solar = None
        month_loads = None
        if self._rate_structure is not None:
            rs = self._rate_structure
            esc = float(self._rate_escalation[year_idx]) if self._rate_escalation is not None else 1.0
            peak = rs.peak_mask()
            month_loads = self._month_loads(year_elec_load_by_class)
            home_bill_no_solar = np.array([
                rs.price_month(m, float(month_loads[m][peak].sum()) * _DAYS_IN_MONTH[m],
                               float(month_loads[m][~peak].sum()) * _DAYS_IN_MONTH[m],
                               _DAYS_IN_MONTH[m], esc)
                for m in range(12)])
            adjustment = float(home_bill_no_solar.sum()) - year_elec_opex
            elec_total = sum(year_category_elec_costs.values())
            for cat in CATEGORY_ORDER:
                share = (year_category_elec_costs[cat] / elec_total if elec_total > 0
                         else (1.0 if cat == "Baseload" else 0.0))
                year_category_costs[cat] += adjustment * share
            year_opex += adjustment
            year_elec_opex = float(home_bill_no_solar.sum())
        self.home_elec_bill_history.append(year_elec_opex)
        self.home_load_hourly_history.append(
            np.array(month_loads) if month_loads is not None else None)

        # Append exactly once per category per step (sum-then-append fix)
        for cat in CATEGORY_ORDER:
            self.cost_history_by_category[cat].append(year_category_costs[cat])

        # Annual gas therms — pure physics, independent of social-cost rates
        self.gas_therms_history.append(year_gas_therms)
        self.gasoline_gallons_history.append(year_gasoline_gallons)
        self.external_ev_kwh_history.append(year_external_ev_kwh)
        self.external_ev_cost_history.append(year_external_ev_cost)

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
            # Phase 7 §0/§2 — hourly energy balance on a representative day per month.
            # Solar: per-ZIP PVWatts (clock time). Load: each electric device's monthly
            # home-meter kWh spread by its 24-h shape. Battery: two modes, cheaper per month.
            solar = self._solar_config.solar
            battery = self._solar_config.battery.params()
            res = self._solar_resource
            monthly_production = solar.system_kw * res.ac_monthly                  # (12,) kWh
            retail_by_month = self._elec_rates[year_idx]
            # NEM 3.0: ACC hourly avoided cost.  NEM 2.0: retail minus NBC.  (12, 24) $/kWh
            export_by_month = (self._solar_export_rates[year_idx]
                               if self._solar_export_rates is not None else np.zeros((12, 24)))

            direct = discharge = charge_grid = losses = grid_import = exported = 0.0
            retail_savings = export_credit = 0.0
            modes, bills = [], []
            if month_loads is None:
                month_loads = self._month_loads(year_elec_load_by_class)
            rs = self._rate_structure
            esc = (float(self._rate_escalation[year_idx])
                   if rs is not None and self._rate_escalation is not None else 1.0)
            for m in range(12):
                days = _DAYS_IN_MONTH[m]
                G = monthly_production[m] / days * res.intraday_shape[m]
                L = month_loads[m]
                x = export_by_month[m]                       # (24,) $/kWh by clock hour
                if rs is not None:
                    # URDB TOU: real peak window; the bill (tiers + fixed) decides the mode.
                    rp, ro = rs.tier1_rates(m)
                    mr = dispatch_month(
                        G, L, battery, days=days, mode="auto", peak_hours=rs.peak_hours,
                        r_peak=rp * esc, r_offpeak=ro * esc, export_rate=x,
                        price_fn=lambda pk, op, _m=m, _d=days: rs.price_month(_m, pk, op, _d, esc))
                    d = mr.day
                    exp_m = float(d.export.sum()) * days
                    credit_m = float((d.export * x).sum()) * days
                    grid_m = float(d.grid_import.sum()) * days
                    # Saving = bill with no solar/battery − bill after dispatch (net of export).
                    retail_savings += home_bill_no_solar[m] - (mr.bills[mr.mode] + credit_m)
                else:
                    r = float(retail_by_month[m])
                    # Flat retail (no peak window) → Self-powered.
                    mr = dispatch_month(G, L, battery, days=days, mode="auto", peak_hours=(),
                                        r_peak=r, r_offpeak=r, export_rate=x)
                    d = mr.day
                    exp_m = float(d.export.sum()) * days
                    credit_m = float((d.export * x).sum()) * days
                    grid_m = float(d.grid_import.sum()) * days
                    # Saving vs the same month with no solar/battery: load − grid import at
                    # retail (grid charging adds import) plus the export credit.
                    retail_savings += (float(L.sum()) * days - grid_m) * r
                export_credit += credit_m
                direct      += float(d.solar_direct.sum()) * days
                discharge   += float(d.discharge.sum()) * days
                charge_grid += float(d.charge_grid.sum()) * days
                losses      += d.losses * days
                grid_import += grid_m
                exported    += exp_m
                modes.append(mr.mode)
                bills.append(mr.bills)

            annual_production_kwh = float(monthly_production.sum())
            self_consumed_kwh     = direct + discharge
            exported_kwh          = exported
            # Cap at the year's actual electricity spend — solar can't take the bill below zero
            # (annual, like a NEM true-up: summer credits carry to winter within the year).
            solar_saving = min(retail_savings + export_credit, year_elec_opex)
        else:
            annual_production_kwh = 0.0
            self_consumed_kwh     = 0.0
            exported_kwh          = 0.0
            solar_saving          = 0.0
            direct = discharge = charge_grid = losses = grid_import = 0.0
            modes, bills = [], []

        year_opex -= solar_saving
        self.solar_savings_history.append(solar_saving)
        self.solar_production_kwh_history.append(annual_production_kwh)
        self.solar_self_consumed_history.append(self_consumed_kwh)
        self.solar_exported_kwh_history.append(exported_kwh)
        self.solar_direct_history.append(direct)
        self.battery_discharge_history.append(discharge)
        self.battery_charge_grid_history.append(charge_grid)
        self.battery_losses_history.append(losses)
        self.grid_import_kwh_history.append(grid_import)
        self.battery_mode_history.append(modes)
        self.solar_monthly_bills_history.append(bills)

        self.annual_opex      = year_opex
        self.cumulative_opex += year_opex
