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
from social_cost import SocialCostConfig
from journey import JourneyHome, DeviceSlot, CapExOnlySlot, CATEGORY_ORDER, CATEGORY_LABELS, SolarBatteryConfig
from rate_loader import RateLoader, ACCRateLoader
from devices.physics  import GasFurnace, HeatPumpHVAC, GasWaterHeater, HeatPumpWaterHeater, CentralAC
from devices.seasonal import GasDryer, HeatPumpDryer, GasCooktop, InductionCooktop, LightsAndPlugs
from devices.schedule import EVCharger, PhysicsEVCharger
from devices.vehicle  import GasolineVehicle, ElectricVehicle

_DATA = Path(__file__).parent.parent / "data"


SCENARIO_PRESETS = {
    "conservative": {"elec": 0.04, "gas": 0.04},
    "moderate":     {"elec": 0.07, "gas": 0.08},
    "stress":       {"elec": 0.10, "gas": 0.12},
}

# Maps device class name → ACC device_category for load-profile-weighted rate lookup.
# Gas devices always use "flat" (gas shape is applied uniformly regardless of category).
DEVICE_ACC_CATEGORY: dict[str, str] = {
    "HeatPumpWaterHeater": "hpwh",
    "GasWaterHeater":      "flat",
    "HeatPumpHVAC":        "hvac_heat",   # heating dominates; Phase 3 splits heat/cool
    "GasFurnace":          "flat",
    "CentralAC":           "hvac_cool",
    "EVCharger":           "ev",
    "PhysicsEVCharger":    "ev",
    "LightsAndPlugs":      "baseload",
    "HeatPumpDryer":       "baseload",
    "InductionCooktop":    "baseload",
    "GasDryer":            "flat",
    "GasCooktop":          "flat",
    "ElectricOven":        "baseload",
    "Dishwasher":          "baseload",
}

# All electric ACC categories that need pre-computed rate arrays
_ELEC_ACC_CATEGORIES = ["hpwh", "hvac_heat", "hvac_cool", "ev", "baseload", "flat"]


def _make_loader(base_rl: RateLoader, rate_model: str) -> object:
    """Return ACCRateLoader for ACC models; base RateLoader for CAGR flat."""
    if rate_model in ("acc_shaped", "acc_seasonal"):
        return ACCRateLoader(base_rl)
    return base_rl


def _cagr_for(rate_model: str, cagr: float) -> float | None:
    """Return cagr when CAGR model selected; None for ACC (ignores user CAGR)."""
    return cagr if rate_model == "cagr_flat" else None


def _build_elec_rates_by_class(acc_loader: ACCRateLoader,
                                sim_start_year: int, n_years: int,
                                scenario: str,
                                custom_cagr: float | None = None) -> dict[str, np.ndarray]:
    """
    Pre-compute (n_years, 12) rate arrays for every device class that uses electricity.
    Keys are device class names (matching DEVICE_ACC_CATEGORY).
    custom_cagr: the ACC base escalation rate (from acc_elec_cagr_a/b slider).
    """
    # First build category→array mapping
    cat_arrays: dict[str, np.ndarray] = {}
    for cat in _ELEC_ACC_CATEGORIES:
        cat_arrays[cat] = acc_loader.get_annual_monthly_rates(
            "electricity", sim_start_year, n_years,
            device_category=cat, scenario=scenario, custom_cagr=custom_cagr)

    # Then map device class → array via DEVICE_ACC_CATEGORY
    return {
        cls: cat_arrays[cat]
        for cls, cat in DEVICE_ACC_CATEGORY.items()
        if cat in cat_arrays and cls not in ("GasWaterHeater", "GasFurnace",
                                              "GasDryer", "GasCooktop")
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
    # Electrical nameplate (Phase 3 §2.5) — inert; 0 for gas/unset → rated_va == 0
    elec  = dict(
        circuit_volts=spec.get("circuit_volts", 0),
        circuit_amps=spec.get("circuit_amps", 0),
        continuous=spec.get("continuous", False),
    )

    if cls == "GasFurnace":
        return GasFurnace(mesa_model,
                          afue=spec.get("afue", 0.80),
                          ua_btu_hr_f=ua,
                          monthly_hdd=hdd,
                          age=age, lifespan=ls, installation_cost=cost, **elec)

    if cls == "HeatPumpHVAC":
        return HeatPumpHVAC(mesa_model,
                            cop_heating=spec.get("cop_heating", 3.5),
                            seer_cooling=spec.get("seer_cooling", 22),
                            ua_btu_hr_f=ua,
                            monthly_hdd=hdd, monthly_cdd=cdd,
                            age=age, lifespan=ls, installation_cost=cost, **elec)

    if cls == "GasWaterHeater":
        daily_gal = spec.get("daily_gallons_override") or hw_gallons
        return GasWaterHeater(mesa_model,
                              uef=spec.get("uef", 0.65),
                              daily_gallons=daily_gal,
                              monthly_inlet_temp_f=inlet_temp,
                              age=age, lifespan=ls, installation_cost=cost, **elec)

    if cls == "HeatPumpWaterHeater":
        daily_gal = spec.get("daily_gallons_override") or hw_gallons
        return HeatPumpWaterHeater(mesa_model,
                                   uef=spec.get("uef", 3.5),
                                   daily_gallons=daily_gal,
                                   monthly_inlet_temp_f=inlet_temp,
                                   age=age, lifespan=ls, installation_cost=cost, **elec)

    if cls == "GasDryer":
        return GasDryer(mesa_model,
                        therms_per_cycle=spec.get("therms_per_cycle", 0.22),
                        cycles_per_week=spec.get("cycles_per_week", 5),
                        age=age, lifespan=ls, installation_cost=cost, **elec)

    if cls == "HeatPumpDryer":
        return HeatPumpDryer(mesa_model,
                             kwh_per_cycle=spec.get("kwh_per_cycle", 1.8),
                             cycles_per_week=spec.get("cycles_per_week", 5),
                             age=age, lifespan=ls, installation_cost=cost, **elec)

    if cls == "GasCooktop":
        return GasCooktop(mesa_model,
                          therms_per_meal=spec.get("therms_per_meal", 0.05),
                          meals_per_week=spec.get("meals_per_week", 14),
                          age=age, lifespan=ls, installation_cost=cost, **elec)

    if cls == "InductionCooktop":
        return InductionCooktop(mesa_model,
                                kwh_per_meal=spec.get("kwh_per_meal", 0.9),
                                meals_per_week=spec.get("meals_per_week", 14),
                                age=age, lifespan=ls, installation_cost=cost, **elec)

    if cls == "LightsAndPlugs":
        return LightsAndPlugs(mesa_model,
                              annual_kwh=spec.get("annual_kwh", baseload_kwh),
                              age=age, lifespan=ls, installation_cost=cost, **elec)

    if cls == "EVCharger":
        monthly_override = spec.get("monthly_kwh_override")
        kwh_list = [monthly_override] * 12 if monthly_override is not None else None
        return EVCharger(mesa_model, monthly_kwh=kwh_list,
                         age=age, lifespan=ls, installation_cost=cost, **elec)

    if cls == "PhysicsEVCharger":
        return PhysicsEVCharger(mesa_model,
                                miles_per_year=spec.get("miles_per_year", 7000),
                                kwh_per_mile=spec.get("kwh_per_mile", 0.30),
                                charging_efficiency=spec.get("charging_efficiency", 0.90),
                                age=age, lifespan=ls, installation_cost=cost, **elec)

    if cls == "CentralAC":
        return CentralAC(mesa_model,
                         seer_cooling=spec.get("seer_cooling", 14),
                         ua_btu_hr_f=ua,
                         monthly_cdd=cdd,
                         age=age, lifespan=ls, installation_cost=cost, **elec)

    if cls == "GasolineVehicle":
        return GasolineVehicle(mesa_model,
                               miles_per_year=spec.get("miles_per_year", 12_000),
                               mpg=spec.get("mpg", 28.0),
                               age=age, lifespan=ls, installation_cost=cost)

    if cls == "ElectricVehicle":
        return ElectricVehicle(mesa_model,
                               miles_per_year=spec.get("miles_per_year", 12_000),
                               ev_eff_mi_per_kwh=spec.get("ev_eff_mi_per_kwh", 3.5),
                               charging_efficiency=spec.get("charging_efficiency", 0.88),
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

        # Derive slot-level lifespan from the first baseline device config
        baseline_cfgs = cfg.get("baseline_devices", [])
        slot_lifespan = baseline_cfgs[0]["lifespan"] if baseline_cfgs else 15
        slot_age      = cfg.get("existing_age", slot_lifespan // 2)

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
            style_key          = cfg.get("style_key", "lights"),
            lifespan           = slot_lifespan,
            existing_age       = slot_age,
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
                 n_years:          int  = 20,
                 sim_start_year:   int  = 2025,
                 slot_configs:     list | None = None,
                 capex_only_slots: list | None = None,
                 solar_config: SolarBatteryConfig | None = None,
                 social_cost_config: SocialCostConfig | None = None,
                 # §3 Transportation — gasoline price model
                 gasoline_price_per_gallon:        float = 4.50,
                 gasoline_escalation_pct:           float = 0.0,   # annual fractional change
                 gasoline_climate_enabled:          bool  = True,
                 gasoline_climate_cost_per_gallon:  float = 1.69,  # $/gal at $190/ton SCC
                 gasoline_health_enabled:           bool  = True,
                 gasoline_health_cost_per_gallon:   float = 0.75,
                 # §23 rate model selections — stored, wired when ACCRateLoader is added
                 elec_rate_model_a: str = "cagr_flat",
                 gas_rate_model_a:  str = "cagr_flat",
                 elec_rate_model_b: str = "acc_shaped",
                 gas_rate_model_b:  str = "acc_seasonal",
                 acc_elec_cagr_a:   float = 0.07,
                 acc_gas_cagr_a:    float = 0.08,
                 acc_elec_cagr_b:   float = 0.07,
                 acc_gas_cagr_b:    float = 0.08):
        super().__init__()
        self.elec_rate_model_a = elec_rate_model_a
        self.gas_rate_model_a  = gas_rate_model_a
        self.elec_rate_model_b = elec_rate_model_b
        self.gas_rate_model_b  = gas_rate_model_b

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

        self.social_cost_config = social_cost_config or SocialCostConfig()

        # ── Gasoline externalities (stored for DataCollector) ─────────────────
        self.gasoline_climate_cost_per_gallon = (
            gasoline_climate_cost_per_gallon if gasoline_climate_enabled else 0.0)
        self.gasoline_health_cost_per_gallon = (
            gasoline_health_cost_per_gallon if gasoline_health_enabled else 0.0)

        # ── Gasoline rate array — flat monthly price with annual escalation ────
        # Shape (n_years, 12): each row is the $/gallon rate for that year's 12 months.
        _gasoline_rates = np.array([
            [gasoline_price_per_gallon * (1.0 + gasoline_escalation_pct) ** yr] * 12
            for yr in range(n_years)
        ], dtype=float)
        self.gasoline_rates = _gasoline_rates

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
        hw_gallons = float(
            home_config.hot_water_daily_gallons
            if home_config.hot_water_daily_gallons is not None
            else HOT_WATER_GAL_PER_DAY[home_config.num_bedrooms]
        )

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
        elec_loader_a = _make_loader(rl, elec_rate_model_a)
        gas_loader_a  = _make_loader(rl, gas_rate_model_a)

        # CAGR mode uses user slider; ACC mode uses acc_cagr slider (ignores CAGR slider)
        elec_cagr_a_eff = acc_elec_cagr_a if elec_rate_model_a == "acc_shaped"  else _cagr_for(elec_rate_model_a, elec_cagr_a)
        gas_cagr_a_eff  = acc_gas_cagr_a  if gas_rate_model_a  == "acc_seasonal" else _cagr_for(gas_rate_model_a,  gas_cagr_a)

        self.elec_rates = elec_loader_a.get_annual_monthly_rates(
            "electricity", sim_start_year, n_years,
            scenario=scenario_a, custom_cagr=elec_cagr_a_eff)   # (n_years, 12)
        self.gas_rates  = gas_loader_a.get_annual_monthly_rates(
            "gas", sim_start_year, n_years,
            scenario=scenario_a, custom_cagr=gas_cagr_a_eff)    # (n_years, 12)

        self.current_elec_rates = self.elec_rates[0]
        self.current_gas_rates  = self.gas_rates[0]

        # ACC mode: pre-compute per-device-class effective rate arrays
        elec_by_cls_a = None
        if elec_rate_model_a == "acc_shaped" and isinstance(elec_loader_a, ACCRateLoader):
            elec_by_cls_a = _build_elec_rates_by_class(
                elec_loader_a, sim_start_year, n_years, scenario_a,
                custom_cagr=elec_cagr_a_eff)

        # ── Solar export rates (§8) — built once, used by journey_home only ──
        # NEM 3.0 (nbt): ACC avoided-cost $/kWh from ACCRateLoader.
        #   We always build an ACCRateLoader for this regardless of the consumption
        #   rate mode, because the export credit is a grid property, not a billing choice.
        # NEM 2.0 (nem2): retail rate minus non-bypassable charge (NBC).
        solar_export_rates: np.ndarray | None = None
        if solar_config is not None:
            if solar_config.nem_mode == "nbt":
                _acc_for_export = elec_loader_a if isinstance(elec_loader_a, ACCRateLoader) \
                    else ACCRateLoader(rl)
                solar_export_rates = _acc_for_export.get_nem3_export_rates(
                    sim_start_year, n_years,
                    scenario=scenario_a, custom_cagr=elec_cagr_a_eff)
            else:  # nem2: retail minus NBC, floored at zero
                solar_export_rates = np.maximum(0.0, self.elec_rates - solar_config.nbc)

        # ── Two JourneyHome instances — Scenario A ────────────────────────────
        journey_slots  = _build_slots(slot_configs, False, self, **device_kw)
        baseline_slots = _build_slots(slot_configs, True,  self, **device_kw)

        self.journey_home  = JourneyHome(self, journey_slots,  self.elec_rates, self.gas_rates,
                                         is_baseline_home=False, capex_only_slots=capex_only_slots,
                                         solar_config=solar_config,
                                         solar_export_rates=solar_export_rates,
                                         elec_rates_by_category=elec_by_cls_a,
                                         gasoline_rates=_gasoline_rates)
        self.baseline_home = JourneyHome(self, baseline_slots, self.elec_rates, self.gas_rates,
                                         is_baseline_home=True,
                                         elec_rates_by_category=elec_by_cls_a,
                                         gasoline_rates=_gasoline_rates)

        # ── Scenario B (lazy — only when comparison_mode=True) ────────────────
        if comparison_mode:
            elec_loader_b = _make_loader(rl, elec_rate_model_b)
            gas_loader_b  = _make_loader(rl, gas_rate_model_b)

            elec_cagr_b_eff = acc_elec_cagr_b if elec_rate_model_b == "acc_shaped"  else _cagr_for(elec_rate_model_b, elec_cagr_b)
            gas_cagr_b_eff  = acc_gas_cagr_b  if gas_rate_model_b  == "acc_seasonal" else _cagr_for(gas_rate_model_b,  gas_cagr_b)

            self.elec_rates_b = elec_loader_b.get_annual_monthly_rates(
                "electricity", sim_start_year, n_years,
                scenario=scenario_b, custom_cagr=elec_cagr_b_eff)
            self.gas_rates_b  = gas_loader_b.get_annual_monthly_rates(
                "gas", sim_start_year, n_years,
                scenario=scenario_b, custom_cagr=gas_cagr_b_eff)

            self.current_elec_rates_b = self.elec_rates_b[0]
            self.current_gas_rates_b  = self.gas_rates_b[0]

            elec_by_cls_b = None
            if elec_rate_model_b == "acc_shaped" and isinstance(elec_loader_b, ACCRateLoader):
                elec_by_cls_b = _build_elec_rates_by_class(
                    elec_loader_b, sim_start_year, n_years, scenario_b,
                    custom_cagr=elec_cagr_b_eff)

            journey_slots_b  = _build_slots(slot_configs, False, self, **device_kw)
            baseline_slots_b = _build_slots(slot_configs, True,  self, **device_kw)

            self.journey_home_b  = JourneyHome(self, journey_slots_b,  self.elec_rates_b, self.gas_rates_b,
                                               is_baseline_home=False,
                                               solar_config=solar_config,
                                               solar_export_rates=solar_export_rates,
                                               elec_rates_by_category=elec_by_cls_b,
                                               gasoline_rates=_gasoline_rates)
            self.baseline_home_b = JourneyHome(self, baseline_slots_b, self.elec_rates_b, self.gas_rates_b,
                                               is_baseline_home=True,
                                               elec_rates_by_category=elec_by_cls_b,
                                               gasoline_rates=_gasoline_rates)

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
            "Solar Saving":        lambda m: (m.journey_home.solar_savings_history[-1]
                                              if m.journey_home.solar_savings_history else 0.0),
            # Social & Health cost of gas (Phase 3 §6) — Scenario A; informational
            "Journey Social Climate":  lambda m: (m.journey_home.gas_therms_history[-1]
                                                  * m.social_cost_config.climate_eff),
            "Journey Social Health":   lambda m: (m.journey_home.gas_therms_history[-1]
                                                  * m.social_cost_config.health_eff),
            "Baseline Social Climate": lambda m: (m.baseline_home.gas_therms_history[-1]
                                                  * m.social_cost_config.climate_eff),
            "Baseline Social Health":  lambda m: (m.baseline_home.gas_therms_history[-1]
                                                  * m.social_cost_config.health_eff),
            # §3 Transportation — gasoline gallons + externalities
            "Journey Gasoline Gallons":   lambda m: (m.journey_home.gasoline_gallons_history[-1]
                                                     if m.journey_home.gasoline_gallons_history else 0.0),
            "Baseline Gasoline Gallons":  lambda m: (m.baseline_home.gasoline_gallons_history[-1]
                                                     if m.baseline_home.gasoline_gallons_history else 0.0),
            "Journey Gasoline Climate":   lambda m: (m.journey_home.gasoline_gallons_history[-1]
                                                     * m.gasoline_climate_cost_per_gallon
                                                     if m.journey_home.gasoline_gallons_history else 0.0),
            "Journey Gasoline Health":    lambda m: (m.journey_home.gasoline_gallons_history[-1]
                                                     * m.gasoline_health_cost_per_gallon
                                                     if m.journey_home.gasoline_gallons_history else 0.0),
            "Baseline Gasoline Climate":  lambda m: (m.baseline_home.gasoline_gallons_history[-1]
                                                     * m.gasoline_climate_cost_per_gallon
                                                     if m.baseline_home.gasoline_gallons_history else 0.0),
            "Baseline Gasoline Health":   lambda m: (m.baseline_home.gasoline_gallons_history[-1]
                                                     * m.gasoline_health_cost_per_gallon
                                                     if m.baseline_home.gasoline_gallons_history else 0.0),
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
