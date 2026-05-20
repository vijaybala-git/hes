"""
HESModel — Phase 2 simulation model.

Scenario A: two JourneyHome instances (journey + do-nothing baseline).
Scenario B: optional second pair, created only when comparison_mode=True.

Climate constants and rate arrays are resolved once at init and injected into devices.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import mesa
import numpy as np

from home_config import HomeConfig, compute_baseload_kwh, HOT_WATER_GAL_PER_DAY
from journey import JourneyHome, DeviceSlot, CATEGORY_ORDER, CATEGORY_LABELS
from rate_loader import RateLoader
from devices.physics  import GasFurnace, HeatPumpHVAC, GasWaterHeater, HeatPumpWaterHeater, CentralAC
from devices.seasonal import GasDryer, HeatPumpDryer, GasCooktop, InductionCooktop, LightsAndPlugs
from devices.schedule import EVCharger

_DATA = Path(__file__).parent.parent / "data"


SCENARIO_PRESETS = {
    "conservative": {"elec": 0.04, "gas": 0.04},
    "moderate":     {"elec": 0.07, "gas": 0.08},
    "stress":       {"elec": 0.10, "gas": 0.12},
}


def _make_device(spec: dict, mesa_model: mesa.Model, *,
                 hdd: np.ndarray, cdd: np.ndarray,
                 inlet_temp: np.ndarray, ua: float,
                 hw_gallons: float, baseload_kwh: float):
    """Instantiate one EnergyConsumer from a slot JSON device spec."""
    cls   = spec["class"]
    age   = spec.get("age", 0)
    ls    = spec.get("lifespan", 15)
    cost  = spec.get("installation_cost", 0.0)

    if cls == "GasFurnace":
        return GasFurnace(mesa_model,
                          afue=spec.get("afue", 0.80),
                          ua_btu_hr_f=ua,
                          monthly_hdd=hdd,
                          age=age, lifespan=ls, installation_cost=cost)

    if cls == "HeatPumpHVAC":
        return HeatPumpHVAC(mesa_model,
                            cop_heating=spec.get("cop_heating", 3.5),
                            seer_cooling=spec.get("seer_cooling", 22),
                            ua_btu_hr_f=ua,
                            monthly_hdd=hdd, monthly_cdd=cdd,
                            age=age, lifespan=ls, installation_cost=cost)

    if cls == "GasWaterHeater":
        return GasWaterHeater(mesa_model,
                              uef=spec.get("uef", 0.65),
                              daily_gallons=hw_gallons,
                              monthly_inlet_temp_f=inlet_temp,
                              age=age, lifespan=ls, installation_cost=cost)

    if cls == "HeatPumpWaterHeater":
        return HeatPumpWaterHeater(mesa_model,
                                   uef=spec.get("uef", 3.5),
                                   daily_gallons=hw_gallons,
                                   monthly_inlet_temp_f=inlet_temp,
                                   age=age, lifespan=ls, installation_cost=cost)

    if cls == "GasDryer":
        return GasDryer(mesa_model,
                        therms_per_cycle=spec.get("therms_per_cycle", 0.22),
                        cycles_per_week=spec.get("cycles_per_week", 5),
                        age=age, lifespan=ls, installation_cost=cost)

    if cls == "HeatPumpDryer":
        return HeatPumpDryer(mesa_model,
                             kwh_per_cycle=spec.get("kwh_per_cycle", 1.8),
                             cycles_per_week=spec.get("cycles_per_week", 5),
                             age=age, lifespan=ls, installation_cost=cost)

    if cls == "GasCooktop":
        return GasCooktop(mesa_model,
                          therms_per_meal=spec.get("therms_per_meal", 0.05),
                          meals_per_week=spec.get("meals_per_week", 14),
                          age=age, lifespan=ls, installation_cost=cost)

    if cls == "InductionCooktop":
        return InductionCooktop(mesa_model,
                                kwh_per_meal=spec.get("kwh_per_meal", 0.9),
                                meals_per_week=spec.get("meals_per_week", 14),
                                age=age, lifespan=ls, installation_cost=cost)

    if cls == "LightsAndPlugs":
        return LightsAndPlugs(mesa_model,
                              annual_kwh=spec.get("annual_kwh", baseload_kwh),
                              age=age, lifespan=ls, installation_cost=cost)

    if cls == "EVCharger":
        return EVCharger(mesa_model, age=age, lifespan=ls, installation_cost=cost)

    if cls == "CentralAC":
        return CentralAC(mesa_model,
                         seer_cooling=spec.get("seer_cooling", 14),
                         ua_btu_hr_f=ua,
                         monthly_cdd=cdd,
                         age=age, lifespan=ls, installation_cost=cost)

    raise ValueError(f"Unknown device class: {cls!r}")


def _build_slots(slot_configs: list, is_baseline: bool,
                 mesa_model: mesa.Model, *,
                 hdd, cdd, inlet_temp, ua, hw_gallons, baseload_kwh) -> list:
    """Create a fresh list of DeviceSlot objects with independent device instances."""
    slots = []
    kw = dict(hdd=hdd, cdd=cdd, inlet_temp=inlet_temp,
              ua=ua, hw_gallons=hw_gallons, baseload_kwh=baseload_kwh)

    for cfg in slot_configs:
        baseline_devs = [
            _make_device(d, mesa_model, **kw)
            for d in cfg.get("baseline_devices", [])
        ]

        elec_spec = cfg.get("electric_device")
        elec_dev  = _make_device(elec_spec, mesa_model, **kw) if elec_spec else None

        # Baseline home: all swap_years set to None; starting_state preserved
        swap_yr = None if is_baseline else cfg.get("swap_year")

        slots.append(DeviceSlot(
            name               = cfg["name"],
            category           = cfg["category"],
            starting_state     = cfg["starting_state"],
            baseline_devices   = baseline_devs,
            has_cooling_baseline = cfg.get("has_cooling_baseline", False),
            electric_device    = elec_dev,
            swap_year          = swap_yr,
            install_cost       = cfg.get("install_cost", 0.0),
            rebate             = cfg.get("rebate", 0.0),
        ))
    return slots


class HESModel(mesa.Model):
    """
    Top-level Phase 2 simulation.

    Parameters
    ----------
    home_config : HomeConfig, optional
        Home profile (bedrooms, insulation, etc.).  Defaults to 3BR average Bay Area home.
    scenario_a : str
        Rate escalation scenario for the primary comparison — "conservative", "moderate",
        or "stress".
    scenario_b : str
        Rate escalation scenario for optional second comparison (used only when
        comparison_mode=True).
    comparison_mode : bool
        When True, a second pair of JourneyHome instances (journey_home_b /
        baseline_home_b) is created under scenario_b and stepped in parallel.
    n_years : int
        Simulation length in years.
    sim_start_year : int
        Real calendar year that simulation year 1 maps to (for rate lookup).
    slot_configs : list, optional
        Override default slot JSON.  Each element is a slot-config dict matching
        the schema in data/homes/journey_slots_default.json.
    """

    def __init__(self,
                 home_config:     HomeConfig | None = None,
                 # Explicit per-fuel CAGRs — take priority over named scenario
                 elec_cagr_a:     float | None = None,
                 gas_cagr_a:      float | None = None,
                 scenario_a:      str  = "moderate",
                 elec_cagr_b:     float | None = None,
                 gas_cagr_b:      float | None = None,
                 scenario_b:      str  = "stress",
                 comparison_mode: bool = False,
                 n_years:         int  = 20,
                 sim_start_year:  int  = 2025,
                 slot_configs:    list | None = None):
        super().__init__()

        self.rate_scenario   = scenario_a
        self.n_years         = n_years
        self.sim_start_year  = sim_start_year
        self.comparison_mode = comparison_mode

        # Resolve CAGRs: explicit value takes priority over scenario preset
        elec_cagr_a = elec_cagr_a if elec_cagr_a is not None else SCENARIO_PRESETS[scenario_a]["elec"]
        gas_cagr_a  = gas_cagr_a  if gas_cagr_a  is not None else SCENARIO_PRESETS[scenario_a]["gas"]
        elec_cagr_b = elec_cagr_b if elec_cagr_b is not None else SCENARIO_PRESETS[scenario_b]["elec"]
        gas_cagr_b  = gas_cagr_b  if gas_cagr_b  is not None else SCENARIO_PRESETS[scenario_b]["gas"]

        if home_config is None:
            home_config = HomeConfig()
        self.home_config = home_config

        # ── Climate constants ─────────────────────────────────────────────────
        with open(_DATA / "climate/bayarea_tmy3.json") as f:
            climate = json.load(f)

        hdd        = np.array(climate["monthly_hdd_65f"],           dtype=float)
        cdd        = np.array(climate["monthly_cdd_65f"],           dtype=float)
        inlet_temp = np.array(climate["monthly_inlet_water_temp_f"], dtype=float)
        ua_map     = climate["ua_by_insulation"]

        ua = float(ua_map[home_config.insulation_quality])

        # ── Baseload formula ──────────────────────────────────────────────────
        baseload_before = compute_baseload_kwh(
            home_config.square_footage,
            home_config.num_bedrooms,
            home_config.baseload_constant_before,
        )
        baseload_after = compute_baseload_kwh(
            home_config.square_footage,
            home_config.num_bedrooms,
            home_config.baseload_constant_after,
        )
        hw_gallons = float(HOT_WATER_GAL_PER_DAY[home_config.num_bedrooms])

        # ── Slot configs ──────────────────────────────────────────────────────
        if slot_configs is None:
            with open(_DATA / "homes/journey_slots_default.json") as f:
                slot_configs = json.load(f)

        # Inject formula values into Lights and Appliances slot
        for cfg in slot_configs:
            if cfg["name"] == "Lights and Appliances":
                for dev in cfg.get("baseline_devices", []):
                    if dev["class"] == "LightsAndPlugs":
                        dev["annual_kwh"] = baseload_before
                ed = cfg.get("electric_device")
                if ed and ed.get("class") == "LightsAndPlugs":
                    ed["annual_kwh"] = baseload_after
                cfg["swap_year"]    = home_config.baseload_swap_year
                cfg["install_cost"] = home_config.baseload_install_cost
                cfg["rebate"]       = home_config.baseload_rebate

        device_kw = dict(hdd=hdd, cdd=cdd, inlet_temp=inlet_temp,
                         ua=ua, hw_gallons=hw_gallons, baseload_kwh=baseload_before)

        # ── Rate arrays — Scenario A ──────────────────────────────────────────
        rl = RateLoader()
        self.elec_rates = rl.get_annual_monthly_rates(
            "electricity", sim_start_year, n_years, scenario_a,
            custom_cagr=elec_cagr_a)   # (n_years, 12)
        self.gas_rates  = rl.get_annual_monthly_rates(
            "gas",         sim_start_year, n_years, scenario_a,
            custom_cagr=gas_cagr_a)    # (n_years, 12)

        self.current_elec_rates = self.elec_rates[0]
        self.current_gas_rates  = self.gas_rates[0]

        # ── Two JourneyHome instances — Scenario A ────────────────────────────
        journey_slots  = _build_slots(slot_configs, False, self, **device_kw)
        baseline_slots = _build_slots(slot_configs, True,  self, **device_kw)

        self.journey_home  = JourneyHome(self, journey_slots,  self.elec_rates, self.gas_rates, is_baseline_home=False)
        self.baseline_home = JourneyHome(self, baseline_slots, self.elec_rates, self.gas_rates, is_baseline_home=True)

        # ── Scenario B (lazy — only when comparison_mode=True) ────────────────
        if comparison_mode:
            self.elec_rates_b = rl.get_annual_monthly_rates(
                "electricity", sim_start_year, n_years, scenario_b,
                custom_cagr=elec_cagr_b)
            self.gas_rates_b  = rl.get_annual_monthly_rates(
                "gas",         sim_start_year, n_years, scenario_b,
                custom_cagr=gas_cagr_b)

            self.current_elec_rates_b = self.elec_rates_b[0]
            self.current_gas_rates_b  = self.gas_rates_b[0]

            journey_slots_b  = _build_slots(slot_configs, False, self, **device_kw)
            baseline_slots_b = _build_slots(slot_configs, True,  self, **device_kw)

            self.journey_home_b  = JourneyHome(self, journey_slots_b,  self.elec_rates_b, self.gas_rates_b, is_baseline_home=False)
            self.baseline_home_b = JourneyHome(self, baseline_slots_b, self.elec_rates_b, self.gas_rates_b, is_baseline_home=True)

        # ── DataCollector ─────────────────────────────────────────────────────
        reporters = {
            "Journey Cum Cost":    lambda m: m.journey_home.cumulative_opex,
            "Baseline Cum Cost":   lambda m: m.baseline_home.cumulative_opex,
            "Journey Annual Cost": lambda m: m.journey_home.annual_opex,
            "Baseline Annual Cost":lambda m: m.baseline_home.annual_opex,
            "Opex Delta":          lambda m: (m.baseline_home.cumulative_opex
                                              - m.journey_home.cumulative_opex),
            "Elec Rate":           lambda m: float(np.mean(m.current_elec_rates)),
            "Gas Rate":            lambda m: float(np.mean(m.current_gas_rates)),
        }
        if comparison_mode:
            reporters.update({
                "Journey Cum Cost B":    lambda m: m.journey_home_b.cumulative_opex,
                "Baseline Cum Cost B":   lambda m: m.baseline_home_b.cumulative_opex,
                "Journey Annual Cost B": lambda m: m.journey_home_b.annual_opex,
                "Baseline Annual Cost B":lambda m: m.baseline_home_b.annual_opex,
                "Gas Rate B":            lambda m: float(np.mean(m.current_gas_rates_b)),
                "Elec Rate B":           lambda m: float(np.mean(m.current_elec_rates_b)),
            })
        self.datacollector = mesa.DataCollector(model_reporters=reporters)

    # ── Backward compat properties for app.py ─────────────────────────────────
    @property
    def location(self):
        return {"region": "San Jose, CA",
                "zip_code": self.home_config.zip_code,
                "climate_zone": self.home_config.climate_zone}

    @property
    def building_specs(self):
        return {"square_footage": self.home_config.square_footage,
                "year_built":     self.home_config.year_built,
                "insulation_quality": self.home_config.insulation_quality}

    def step(self):
        year_idx = self.steps - 1
        self.current_elec_rates = self.elec_rates[year_idx]
        self.current_gas_rates  = self.gas_rates[year_idx]

        self.journey_home.step()
        self.baseline_home.step()

        if self.comparison_mode:
            self.current_elec_rates_b = self.elec_rates_b[year_idx]
            self.current_gas_rates_b  = self.gas_rates_b[year_idx]
            self.journey_home_b.step()
            self.baseline_home_b.step()

        self.datacollector.collect(self)

    def run_all(self):
        """Run the full simulation (n_years steps)."""
        for _ in range(self.n_years):
            self.step()
