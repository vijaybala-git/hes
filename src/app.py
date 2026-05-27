"""
WhyWatt? — Solara UI (Phase 2 / Objective 6 — Journey Planner)
"""
import os
import solara
import numpy as np
import matplotlib
import matplotlib.ticker
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
matplotlib.use("Agg")
from matplotlib.figure import Figure
from model import HESModel, SCENARIO_PRESETS
from home_config import HomeConfig, compute_baseload_kwh
from journey import CATEGORY_ORDER, CATEGORY_LABELS, CapExOnlySlot

# ── Asset paths ───────────────────────────────────────────────────────────────
_HERE         = os.path.dirname(os.path.abspath(__file__))
_ASSETS       = os.path.normpath(os.path.join(_HERE, "..", "docs", "assets"))
_WHYWATT_LOGO = os.path.join(_ASSETS, "whywatt_logo.svg")
_ECHO_LOGO    = os.path.join(_ASSETS, "echo_logo.svg")
_ECHO_ICON    = os.path.join(_ASSETS, "echo_icon.svg")


def _read_svg(path: str, height_px: int | None = None) -> str | None:
    """Return SVG content as a string, or None if file is missing.
    If height_px is given, injects height/width CSS into the <svg> opening tag
    so fixed mm/pt attribute dimensions don't override the desired display size."""
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if height_px is not None:
        content = content.replace(
            "<svg ",
            f'<svg style="height:{height_px}px;width:auto;display:block;" ',
            1,
        )
    return content


# ── Color palette ─────────────────────────────────────────────────────────────
C_NAVY  = "#0D47A1"
C_SKY   = "#50BDF8"
C_RED   = "#D0302D"
C_BASE  = C_RED
C_ELEC  = C_NAVY

CATEGORY_COLORS = {
    "Baseload":     ("#BDBDBD", "#BBDEFB"),
    "WaterHeating": ("#9E9E9E", C_SKY),
    "HVAC_Cooling": ("#757575", "#1E88E5"),
    "HVAC_Heating": ("#424242", C_NAVY),
}

CHART_OPTIONS = [
    "Cumulative Energy Costs",
    "Annual Cost by Year",
    "Cost Breakdown by Category",
    "Equipment Replacements (CapEx)",
    "Electricity Price Trend",
    "Gas Price Trend",
    "Journey Timeline",
    "Cost by Device",
    "Energy Use by Device",
]

KWH_PER_THERM = 29.3

UA_MAP = {"poor": 650, "average": 500, "good": 350}


# ── Display-only consumption estimators (not used in simulation) ──────────────

def _est_gas_furnace(afue: float, ua: int, annual_hdd: int = 1910) -> float:
    return annual_hdd * 24 * ua / (afue * 100_000)

def _est_hp_hvac_heating(cop: float, ua: int, annual_hdd: int = 1910) -> float:
    return annual_hdd * 24 * ua / (cop * 3412)

def _est_hp_hvac_cooling(seer: float, ua: int, annual_cdd: int = 340) -> float:
    return annual_cdd * 24 * ua / (seer * 1000)

def _est_gas_wh(uef: float, daily_gal: int,
                avg_inlet_f: float = 60.0, setpoint_f: float = 120.0) -> float:
    return daily_gal * 365 * 8.33 * (setpoint_f - avg_inlet_f) * 0.00001 / uef

def _est_hpwh(uef: float, daily_gal: int,
              avg_inlet_f: float = 60.0, setpoint_f: float = 120.0) -> float:
    return daily_gal * 365 * 8.33 * (setpoint_f - avg_inlet_f) * 0.000293 / uef

def _est_gas_dryer(therms_per_cycle: float, loads_per_week: int) -> float:
    return therms_per_cycle * loads_per_week * 52

def _est_hp_dryer(kwh_per_cycle: float, loads_per_week: int) -> float:
    return kwh_per_cycle * loads_per_week * 52

def _est_gas_cooktop(therms_per_meal: float, meals_per_week: int) -> float:
    return therms_per_meal * meals_per_week * 52

def _est_induction(kwh_per_meal: float, meals_per_week: int) -> float:
    return kwh_per_meal * meals_per_week * 52

def _est_ev_kwh(miles: int, kwh_per_mile: float,
                charging_eff: float = 0.90) -> float:
    return miles * kwh_per_mile / charging_eff

def _apply_ev_efficiency_preset(label: str):
    presets = {"Efficient": 0.23, "Average": 0.30, "Large": 0.45}
    ev_kwh_per_mile.set(presets[label])

def _kwh_eq(therms: float) -> float:
    return therms * KWH_PER_THERM


DEVICE_ORDER  = ["HVAC", "Water Heater", "Dryer", "Cooktop", "Lights and Appliances"]
DEVICE_LABELS = ["HVAC", "Water Heater", "Dryer", "Cooktop", "Baseload"]
DEVICE_COLORS = ["#0D47A1", "#1565C0", "#D0302D", "#EC9B1E", "#78909C"]
DEVICE_ALPHAS = [0.70,      0.60,       0.55,      0.55,      0.45]

# ── Defaults (single source of truth for reset) ──────────────────────────────
_DEFAULTS = {
    # Home profile
    "zip_code":               "95112",
    "climate_zone":           "CZ12",
    "num_bedrooms":           3,
    "square_footage":         1800,
    "year_built":             1985,
    "insulation_quality":     "average",
    # Baseline device specs
    "furnace_afue":           0.80,
    "gas_wh_uef":             0.65,
    "hvac_has_cooling":       False,
    # Electric replacement specs
    "hp_cop_heating":         3.5,
    "hp_seer_cooling":        22,
    "hpwh_uef":               3.5,
    # Journey — HVAC
    "hvac_starting_state":    "gas",
    "hvac_swap_planned":      True,
    "hvac_swap_year":         3,
    "hvac_install_cost":      14000,
    "hvac_rebate":            3500,
    # Journey — Water Heater
    "wh_starting_state":      "gas",
    "wh_swap_planned":        True,
    "wh_swap_year":           5,
    "wh_install_cost":        2500,
    "wh_rebate":              500,
    # Journey — Dryer
    "dryer_starting_state":   "gas",
    "dryer_swap_planned":     False,
    "dryer_swap_year":        8,
    "dryer_install_cost":     1200,
    "dryer_rebate":           0,
    # Journey — Cooktop
    "cooktop_starting_state": "gas",
    "cooktop_swap_planned":   False,
    "cooktop_swap_year":      10,
    "cooktop_install_cost":   1500,
    "cooktop_rebate":         0,
    # Journey — EV Charger
    "ev_starting_state":      "none",
    "ev_swap_planned":        False,
    "ev_swap_year":           2,
    "ev_install_cost":        800,
    "ev_rebate":              0,
    # Journey — Baseload efficiency
    "baseload_constant_before": 500,
    "baseload_constant_after":  300,
    "baseload_swap_planned":    False,
    "baseload_swap_year":       2,
    "baseload_install_cost":    400,
    "baseload_rebate":          0,
    # Expand/collapse state
    "home_profile_details_expanded": False,
    "panel_expanded":   False,
    "hvac_expanded":    False,
    "wh_expanded":      False,
    "dryer_expanded":   False,
    "cooktop_expanded": False,
    "ev_expanded":        False,
    "baseload_expanded":  False,
    # HVAC detail specs
    "hvac_furnace_age": 10,
    "hvac_ac_seer":     14,
    "hvac_ac_age":      7,
    # WH detail specs
    "wh_gas_age":       5,
    "hw_daily_gallons": 65,
    # Dryer detail specs
    "dryer_gas_therms_per_cycle": 0.22,
    "dryer_loads_per_week":       5,
    "dryer_hp_kwh_per_cycle":     1.8,
    # Cooktop detail specs
    "cooktop_gas_therms_per_meal":    0.05,
    "cooktop_meals_per_week":         14,
    "cooktop_induction_kwh_per_meal": 0.9,
    # Panel upgrade
    "panel_upgrade_planned": False,
    "panel_upgrade_year":    1,
    "panel_upgrade_cost":    3000,
    "panel_upgrade_rebate":  0,
    # EV detail specs
    "ev_miles_per_year":      7000,
    "ev_kwh_per_mile":        0.30,
    "ev_charging_efficiency": 0.90,
    # Solar + Battery
    "solar_planned":           False,
    "solar_install_year":      1,
    "solar_coverage_pct":      60,
    "solar_include_panels":    True,
    "solar_panels_cost":       25000,
    "solar_include_battery":   False,
    "solar_battery_cost":      12000,
    "solar_include_install":   True,
    "solar_install_cost_item": 3000,
    "solar_rebate":            0,
    "solar_cost_expanded":     False,
    # Pricing
    "gas_cagr_pct_a":         8,
    "elec_cagr_pct_a":        7,
    "comparison_mode":        False,
    "gas_cagr_pct_b":         12,
    "elec_cagr_pct_b":        10,
    "years":                  20,
    "sim_start_year":         2025,
    # Charts
    "chart_left":             "Cumulative Energy Costs",
    "chart_right":            "Cost Breakdown by Category",
    "device_chart_home":      "journey",
}

# ── Reactive state (initialised from _DEFAULTS) ────────────────────────────────

# Home profile
zip_code           = solara.reactive("95112")
climate_zone       = solara.reactive("CZ12")
num_bedrooms       = solara.reactive(3)
square_footage     = solara.reactive(1800)
year_built         = solara.reactive(1985)
insulation_quality = solara.reactive("average")

# Baseline device specs
furnace_afue     = solara.reactive(0.80)
gas_wh_uef       = solara.reactive(0.65)
hvac_has_cooling = solara.reactive(False)

# Electric replacement specs
hp_cop_heating  = solara.reactive(3.5)
hp_seer_cooling = solara.reactive(22)
hpwh_uef        = solara.reactive(3.5)

# Journey planner — HVAC
hvac_starting_state = solara.reactive("gas")
hvac_swap_planned   = solara.reactive(True)
hvac_swap_year      = solara.reactive(3)
hvac_install_cost   = solara.reactive(14000)
hvac_rebate         = solara.reactive(3500)

# Journey planner — Water Heater
wh_starting_state = solara.reactive("gas")
wh_swap_planned   = solara.reactive(True)
wh_swap_year      = solara.reactive(5)
wh_install_cost   = solara.reactive(2500)
wh_rebate         = solara.reactive(500)

# Journey planner — Dryer
dryer_starting_state = solara.reactive("gas")
dryer_swap_planned   = solara.reactive(False)
dryer_swap_year      = solara.reactive(8)
dryer_install_cost   = solara.reactive(1200)
dryer_rebate         = solara.reactive(0)

# Journey planner — Cooktop
cooktop_starting_state = solara.reactive("gas")
cooktop_swap_planned   = solara.reactive(False)
cooktop_swap_year      = solara.reactive(10)
cooktop_install_cost   = solara.reactive(1500)
cooktop_rebate         = solara.reactive(0)

# Journey planner — EV Charger
ev_starting_state = solara.reactive("none")
ev_swap_planned   = solara.reactive(False)
ev_swap_year      = solara.reactive(2)
ev_install_cost   = solara.reactive(800)
ev_rebate         = solara.reactive(0)

# Journey planner — Baseload efficiency
baseload_constant_before = solara.reactive(500)   # kWh/yr, always-on before upgrade
baseload_constant_after  = solara.reactive(300)   # kWh/yr, always-on after upgrade
baseload_swap_planned    = solara.reactive(False)
baseload_swap_year       = solara.reactive(2)
baseload_install_cost    = solara.reactive(400)
baseload_rebate          = solara.reactive(0)

# Expand/collapse state (one per slot + Home Profile details)
home_profile_details_expanded = solara.reactive(False)
panel_expanded   = solara.reactive(False)
hvac_expanded    = solara.reactive(False)
wh_expanded      = solara.reactive(False)
dryer_expanded   = solara.reactive(False)
cooktop_expanded = solara.reactive(False)
ev_expanded        = solara.reactive(False)
baseload_expanded  = solara.reactive(False)

# Synthetic read-only reactive for the baseload row state label (always "electric")
_baseload_state = solara.reactive("electric")
_panel_state    = solara.reactive("none")     # upgrade slot: always "none" label

# HVAC detail specs
hvac_furnace_age = solara.reactive(10)   # yrs
hvac_ac_seer     = solara.reactive(14)   # existing CentralAC SEER
hvac_ac_age      = solara.reactive(7)    # yrs

# Water Heater detail specs
wh_gas_age              = solara.reactive(5)     # yrs
hw_daily_gallons        = solara.reactive(65)    # gal/day
hw_gallons_user_override = solara.reactive(False) # True once user moves slider

# Dryer detail specs
dryer_gas_therms_per_cycle = solara.reactive(0.22)
dryer_loads_per_week       = solara.reactive(5)
dryer_hp_kwh_per_cycle     = solara.reactive(1.8)

# Cooktop detail specs
cooktop_gas_therms_per_meal    = solara.reactive(0.05)
cooktop_meals_per_week         = solara.reactive(14)
cooktop_induction_kwh_per_meal = solara.reactive(0.9)

# Panel upgrade
panel_upgrade_planned = solara.reactive(False)
panel_upgrade_year    = solara.reactive(1)      # install in year 1 if planned
panel_upgrade_cost    = solara.reactive(3000)   # slider 2000–10000
panel_upgrade_rebate  = solara.reactive(0)

# EV detail specs
ev_miles_per_year      = solara.reactive(7000)   # mi/yr
ev_kwh_per_mile        = solara.reactive(0.30)   # kWh/mi
ev_charging_efficiency = solara.reactive(0.90)   # 0–1

# Solar + Battery
solar_planned           = solara.reactive(False)
solar_install_year      = solara.reactive(1)
solar_coverage_pct      = solara.reactive(60)     # %, range 0-100, step 5

# Cost items (toggle booleans + editable amounts)
solar_include_panels    = solara.reactive(True)
solar_panels_cost       = solara.reactive(25000)
solar_include_battery   = solara.reactive(False)
solar_battery_cost      = solara.reactive(12000)
solar_include_install   = solara.reactive(True)
solar_install_cost_item = solara.reactive(3000)

# Rebate (single flat value)
solar_rebate            = solara.reactive(0)
solar_cost_expanded     = solara.reactive(False)

# Device chart home selector (shared by both device chart types)
device_chart_home = solara.reactive("journey")   # "journey" | "baseline"

# Pricing & timeline — independent per-fuel CAGRs
gas_cagr_pct_a  = solara.reactive(8)    # %/yr, Scenario A — moderate default
elec_cagr_pct_a = solara.reactive(7)    # %/yr, Scenario A
comparison_mode  = solara.reactive(False)
gas_cagr_pct_b  = solara.reactive(12)   # %/yr, Scenario B — stress default
elec_cagr_pct_b = solara.reactive(10)   # %/yr, Scenario B
years            = solara.reactive(20)
sim_start_year   = solara.reactive(2025)

# Chart selection
chart_left  = solara.reactive("Cumulative Energy Costs")
chart_right = solara.reactive("Cost Breakdown by Category")

# ── Reset function ───────────────────────────────────────────────────────────
def reset_to_defaults():
    """Reset every reactive to its _DEFAULTS value in one shot."""
    zip_code.set(_DEFAULTS["zip_code"])
    climate_zone.set(_DEFAULTS["climate_zone"])
    num_bedrooms.set(_DEFAULTS["num_bedrooms"])
    square_footage.set(_DEFAULTS["square_footage"])
    year_built.set(_DEFAULTS["year_built"])
    insulation_quality.set(_DEFAULTS["insulation_quality"])
    furnace_afue.set(_DEFAULTS["furnace_afue"])
    gas_wh_uef.set(_DEFAULTS["gas_wh_uef"])
    hvac_has_cooling.set(_DEFAULTS["hvac_has_cooling"])
    hp_cop_heating.set(_DEFAULTS["hp_cop_heating"])
    hp_seer_cooling.set(_DEFAULTS["hp_seer_cooling"])
    hpwh_uef.set(_DEFAULTS["hpwh_uef"])
    hvac_starting_state.set(_DEFAULTS["hvac_starting_state"])
    hvac_swap_planned.set(_DEFAULTS["hvac_swap_planned"])
    hvac_swap_year.set(_DEFAULTS["hvac_swap_year"])
    hvac_install_cost.set(_DEFAULTS["hvac_install_cost"])
    hvac_rebate.set(_DEFAULTS["hvac_rebate"])
    wh_starting_state.set(_DEFAULTS["wh_starting_state"])
    wh_swap_planned.set(_DEFAULTS["wh_swap_planned"])
    wh_swap_year.set(_DEFAULTS["wh_swap_year"])
    wh_install_cost.set(_DEFAULTS["wh_install_cost"])
    wh_rebate.set(_DEFAULTS["wh_rebate"])
    dryer_starting_state.set(_DEFAULTS["dryer_starting_state"])
    dryer_swap_planned.set(_DEFAULTS["dryer_swap_planned"])
    dryer_swap_year.set(_DEFAULTS["dryer_swap_year"])
    dryer_install_cost.set(_DEFAULTS["dryer_install_cost"])
    dryer_rebate.set(_DEFAULTS["dryer_rebate"])
    cooktop_starting_state.set(_DEFAULTS["cooktop_starting_state"])
    cooktop_swap_planned.set(_DEFAULTS["cooktop_swap_planned"])
    cooktop_swap_year.set(_DEFAULTS["cooktop_swap_year"])
    cooktop_install_cost.set(_DEFAULTS["cooktop_install_cost"])
    cooktop_rebate.set(_DEFAULTS["cooktop_rebate"])
    ev_starting_state.set(_DEFAULTS["ev_starting_state"])
    ev_swap_planned.set(_DEFAULTS["ev_swap_planned"])
    ev_swap_year.set(_DEFAULTS["ev_swap_year"])
    ev_install_cost.set(_DEFAULTS["ev_install_cost"])
    ev_rebate.set(_DEFAULTS["ev_rebate"])
    baseload_constant_before.set(_DEFAULTS["baseload_constant_before"])
    baseload_constant_after.set(_DEFAULTS["baseload_constant_after"])
    baseload_swap_planned.set(_DEFAULTS["baseload_swap_planned"])
    baseload_swap_year.set(_DEFAULTS["baseload_swap_year"])
    baseload_install_cost.set(_DEFAULTS["baseload_install_cost"])
    baseload_rebate.set(_DEFAULTS["baseload_rebate"])
    home_profile_details_expanded.set(_DEFAULTS["home_profile_details_expanded"])
    panel_expanded.set(_DEFAULTS["panel_expanded"])
    hvac_expanded.set(_DEFAULTS["hvac_expanded"])
    wh_expanded.set(_DEFAULTS["wh_expanded"])
    dryer_expanded.set(_DEFAULTS["dryer_expanded"])
    cooktop_expanded.set(_DEFAULTS["cooktop_expanded"])
    ev_expanded.set(_DEFAULTS["ev_expanded"])
    baseload_expanded.set(_DEFAULTS["baseload_expanded"])
    hvac_furnace_age.set(_DEFAULTS["hvac_furnace_age"])
    hvac_ac_seer.set(_DEFAULTS["hvac_ac_seer"])
    hvac_ac_age.set(_DEFAULTS["hvac_ac_age"])
    wh_gas_age.set(_DEFAULTS["wh_gas_age"])
    hw_daily_gallons.set(_DEFAULTS["hw_daily_gallons"])
    hw_gallons_user_override.set(False)
    dryer_gas_therms_per_cycle.set(_DEFAULTS["dryer_gas_therms_per_cycle"])
    dryer_loads_per_week.set(_DEFAULTS["dryer_loads_per_week"])
    dryer_hp_kwh_per_cycle.set(_DEFAULTS["dryer_hp_kwh_per_cycle"])
    cooktop_gas_therms_per_meal.set(_DEFAULTS["cooktop_gas_therms_per_meal"])
    cooktop_meals_per_week.set(_DEFAULTS["cooktop_meals_per_week"])
    cooktop_induction_kwh_per_meal.set(_DEFAULTS["cooktop_induction_kwh_per_meal"])
    panel_upgrade_planned.set(_DEFAULTS["panel_upgrade_planned"])
    panel_upgrade_year.set(_DEFAULTS["panel_upgrade_year"])
    panel_upgrade_cost.set(_DEFAULTS["panel_upgrade_cost"])
    panel_upgrade_rebate.set(_DEFAULTS["panel_upgrade_rebate"])
    ev_miles_per_year.set(_DEFAULTS["ev_miles_per_year"])
    ev_kwh_per_mile.set(_DEFAULTS["ev_kwh_per_mile"])
    ev_charging_efficiency.set(_DEFAULTS["ev_charging_efficiency"])
    solar_planned.set(_DEFAULTS["solar_planned"])
    solar_install_year.set(_DEFAULTS["solar_install_year"])
    solar_coverage_pct.set(_DEFAULTS["solar_coverage_pct"])
    solar_include_panels.set(_DEFAULTS["solar_include_panels"])
    solar_panels_cost.set(_DEFAULTS["solar_panels_cost"])
    solar_include_battery.set(_DEFAULTS["solar_include_battery"])
    solar_battery_cost.set(_DEFAULTS["solar_battery_cost"])
    solar_include_install.set(_DEFAULTS["solar_include_install"])
    solar_install_cost_item.set(_DEFAULTS["solar_install_cost_item"])
    solar_rebate.set(_DEFAULTS["solar_rebate"])
    solar_cost_expanded.set(_DEFAULTS["solar_cost_expanded"])
    gas_cagr_pct_a.set(_DEFAULTS["gas_cagr_pct_a"])
    elec_cagr_pct_a.set(_DEFAULTS["elec_cagr_pct_a"])
    comparison_mode.set(_DEFAULTS["comparison_mode"])
    gas_cagr_pct_b.set(_DEFAULTS["gas_cagr_pct_b"])
    elec_cagr_pct_b.set(_DEFAULTS["elec_cagr_pct_b"])
    years.set(_DEFAULTS["years"])
    sim_start_year.set(_DEFAULTS["sim_start_year"])
    chart_left.set(_DEFAULTS["chart_left"])
    chart_right.set(_DEFAULTS["chart_right"])
    device_chart_home.set(_DEFAULTS["device_chart_home"])


# ── Labels / option lists ─────────────────────────────────────────────────────
_CZ_OPTIONS = ["CZ3", "CZ4", "CZ5", "CZ12", "CZ13", "CZ16"]
_BR_OPTIONS = [1, 2, 3, 4, 5]

_PRESET_DISPLAY = {
    "conservative": "Conservative",
    "moderate":     "Moderate",
    "stress":       "Stress / CEC",
}


def _current_preset_label(gas_pct: int, elec_pct: int) -> str:
    """Return the matching preset name (Capitalized) or 'Custom'."""
    for name, p in SCENARIO_PRESETS.items():
        if int(p["gas"] * 100) == gas_pct and int(p["elec"] * 100) == elec_pct:
            return name.capitalize()
    return "Custom"


def _apply_preset_a(preset: str):
    p = SCENARIO_PRESETS[preset]
    gas_cagr_pct_a.set(int(p["gas"] * 100))
    elec_cagr_pct_a.set(int(p["elec"] * 100))


def _apply_preset_b(preset: str):
    p = SCENARIO_PRESETS[preset]
    gas_cagr_pct_b.set(int(p["gas"] * 100))
    elec_cagr_pct_b.set(int(p["elec"] * 100))


# ── Slot config builder ────────────────────────────────────────────────────────

def _eff_swap_year(state, planned, yr):
    """Return a swap year int when applicable, else None."""
    if state in ("gas", "none") and planned:
        return yr
    return None


def _build_slot_configs() -> list:
    """Convert current reactive state into a slot-config list for HESModel."""
    has_ac = hvac_has_cooling.value
    hvac_baseline = [{
        "class": "GasFurnace",
        "afue": furnace_afue.value,
        "age": hvac_furnace_age.value,
        "lifespan": 20, "installation_cost": 6000,
    }]
    if has_ac:
        hvac_baseline.append({
            "class": "CentralAC",
            "seer_cooling": hvac_ac_seer.value,
            "age": hvac_ac_age.value,
            "installation_cost": 5000,
        })
    hw_override = hw_daily_gallons.value if hw_gallons_user_override.value else None
    return [
        {
            "name": "HVAC",
            "category": "HVAC_Heating",
            "starting_state": hvac_starting_state.value,
            "has_cooling_baseline": has_ac,
            "baseline_devices": hvac_baseline,
            "electric_device": {
                "class": "HeatPumpHVAC",
                "cop_heating": hp_cop_heating.value,
                "seer_cooling": hp_seer_cooling.value,
                "lifespan": 15, "installation_cost": 14000,
            },
            "swap_year": _eff_swap_year(hvac_starting_state.value,
                                        hvac_swap_planned.value, hvac_swap_year.value),
            "install_cost": hvac_install_cost.value,
            "rebate": hvac_rebate.value,
        },
        {
            "name": "Water Heater",
            "category": "WaterHeating",
            "starting_state": wh_starting_state.value,
            "has_cooling_baseline": False,
            "baseline_devices": [{
                "class": "GasWaterHeater",
                "uef": gas_wh_uef.value,
                "age": wh_gas_age.value,
                "lifespan": 12, "installation_cost": 1200,
                "daily_gallons_override": hw_override,
            }],
            "electric_device": {
                "class": "HeatPumpWaterHeater",
                "uef": hpwh_uef.value,
                "lifespan": 15, "installation_cost": 2500,
                "daily_gallons_override": hw_override,
            },
            "swap_year": _eff_swap_year(wh_starting_state.value,
                                        wh_swap_planned.value, wh_swap_year.value),
            "install_cost": wh_install_cost.value,
            "rebate": wh_rebate.value,
        },
        {
            "name": "Dryer",
            "category": "Baseload",
            "starting_state": dryer_starting_state.value,
            "has_cooling_baseline": False,
            "baseline_devices": [{
                "class": "GasDryer",
                "therms_per_cycle": dryer_gas_therms_per_cycle.value,
                "cycles_per_week":  dryer_loads_per_week.value,
                "lifespan": 15, "installation_cost": 800,
            }],
            "electric_device": {
                "class": "HeatPumpDryer",
                "kwh_per_cycle":   dryer_hp_kwh_per_cycle.value,
                "cycles_per_week": dryer_loads_per_week.value,
                "lifespan": 15, "installation_cost": 1200,
            },
            "swap_year": _eff_swap_year(dryer_starting_state.value,
                                        dryer_swap_planned.value, dryer_swap_year.value),
            "install_cost": dryer_install_cost.value,
            "rebate": dryer_rebate.value,
        },
        {
            "name": "Cooktop",
            "category": "Baseload",
            "starting_state": cooktop_starting_state.value,
            "has_cooling_baseline": False,
            "baseline_devices": [{
                "class": "GasCooktop",
                "therms_per_meal": cooktop_gas_therms_per_meal.value,
                "meals_per_week":  cooktop_meals_per_week.value,
                "lifespan": 20, "installation_cost": 1000,
            }],
            "electric_device": {
                "class": "InductionCooktop",
                "kwh_per_meal":  cooktop_induction_kwh_per_meal.value,
                "meals_per_week": cooktop_meals_per_week.value,
                "lifespan": 20, "installation_cost": 1500,
            },
            "swap_year": _eff_swap_year(cooktop_starting_state.value,
                                        cooktop_swap_planned.value, cooktop_swap_year.value),
            "install_cost": cooktop_install_cost.value,
            "rebate": cooktop_rebate.value,
        },
        {
            "name": "EV Charger",
            "category": "Baseload",
            "starting_state": ev_starting_state.value,
            "has_cooling_baseline": False,
            "baseline_devices": [],
            "electric_device": {
                "class": "PhysicsEVCharger",
                "miles_per_year":      ev_miles_per_year.value,
                "kwh_per_mile":        ev_kwh_per_mile.value,
                "charging_efficiency": ev_charging_efficiency.value,
                "lifespan": 20, "installation_cost": 800,
            },
            "swap_year": _eff_swap_year(ev_starting_state.value,
                                        ev_swap_planned.value, ev_swap_year.value),
            "install_cost": ev_install_cost.value,
            "rebate": ev_rebate.value,
        },
        {
            "name": "Lights and Appliances",
            "category": "Baseload",
            "starting_state": "gas",
            "has_cooling_baseline": False,
            "baseline_devices": [{"class": "LightsAndPlugs", "annual_kwh": 0, "lifespan": 15}],
            "electric_device":   {"class": "LightsAndPlugs", "annual_kwh": 0, "lifespan": 15},
            "swap_year": None,
            "install_cost": 400,
            "rebate": 0,
        },
    ]


# ── Simulation runner ──────────────────────────────────────────────────────────

def run_simulation():
    """Build and run HESModel from current reactive state; return (model, df)."""
    hc = HomeConfig(
        zip_code=zip_code.value,
        climate_zone=climate_zone.value,
        num_bedrooms=num_bedrooms.value,
        square_footage=square_footage.value,
        year_built=year_built.value,
        insulation_quality=insulation_quality.value,
        baseload_constant_before=baseload_constant_before.value,
        baseload_constant_after=baseload_constant_after.value,
        baseload_swap_year=(baseload_swap_year.value
                            if baseload_swap_planned.value else None),
        baseload_install_cost=baseload_install_cost.value,
        baseload_rebate=baseload_rebate.value,
        hot_water_daily_gallons=(hw_daily_gallons.value
                                  if hw_gallons_user_override.value else None),
    )
    capex_slots = []
    if panel_upgrade_planned.value:
        capex_slots.append(CapExOnlySlot(
            name="Electrical Panel",
            install_cost=panel_upgrade_cost.value,
            rebate=panel_upgrade_rebate.value,
            lifespan=25,
            install_year=panel_upgrade_year.value,
        ))

    # Solar derived values
    solar_gross = (
        (solar_panels_cost.value if solar_include_panels.value else 0)
        + (solar_battery_cost.value if solar_include_battery.value else 0)
        + (solar_install_cost_item.value if solar_include_install.value else 0)
    )
    if solar_planned.value:
        capex_slots.append(CapExOnlySlot(
            name="Solar + Battery",
            category="Infrastructure",
            install_cost=solar_gross,
            rebate=solar_rebate.value,
            lifespan=25,
            install_year=solar_install_year.value,
        ))
    solar_coverage = solar_coverage_pct.value if solar_planned.value else 0

    m = HESModel(
        home_config=hc,
        n_years=years.value,
        gas_cagr_a=gas_cagr_pct_a.value / 100.0,
        elec_cagr_a=elec_cagr_pct_a.value / 100.0,
        gas_cagr_b=gas_cagr_pct_b.value / 100.0,
        elec_cagr_b=elec_cagr_pct_b.value / 100.0,
        comparison_mode=comparison_mode.value,
        sim_start_year=sim_start_year.value,
        slot_configs=_build_slot_configs(),
        capex_only_slots=capex_slots or None,
        solar_coverage_pct=float(solar_coverage),
    )
    m.run_all()
    df = m.datacollector.get_model_vars_dataframe()
    return m, df


# ── Chart helpers ─────────────────────────────────────────────────────────────

def _money(v, _):
    return f"${v:,.0f}"

def _style(ax):
    ax.set_facecolor("#F9F9F9")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(True, alpha=0.2, color="#CCCCCC")

def _new_fig(wide=False):
    w = 12 if wide else 6
    fig = Figure(figsize=(w, 3.8), dpi=100)
    fig.patch.set_facecolor("#F9F9F9")
    return fig


# Chart 1 — Cumulative Energy Costs
def make_cumulative_opex(df, model, n):
    C_SOLAR = "#00897B"
    fig = _new_fig()
    ax  = fig.add_subplot(111)
    x = np.arange(1, n + 1)
    b = df["Baseline Cum Cost"].values
    lbl_a = " (A)" if model.comparison_mode else ""

    has_solar = solar_planned.value and "Solar Saving" in df.columns

    if has_solar:
        # Journey Cum Cost already has solar deducted; reconstruct no-solar line
        solar_savings_cum = np.cumsum(df["Solar Saving"].values)
        e_no_solar = df["Journey Cum Cost"].values + solar_savings_cum
        e_solar    = df["Journey Cum Cost"].values
        ax.plot(x, b,         color=C_BASE,  lw=2.5, label=f"Do nothing{lbl_a}")
        ax.plot(x, e_no_solar, color=C_ELEC, lw=2.0, linestyle="--",
                label=f"Your journey{lbl_a}")
        ax.plot(x, e_solar,   color=C_SOLAR, lw=2.5,
                label=f"Your journey + Solar{lbl_a}")
        ax.fill_between(x, b, e_solar, where=(b >= e_solar),
                        color=C_SOLAR, alpha=0.10, label="Journey + Solar saves")
        ax.fill_between(x, e_solar, e_no_solar, where=(e_no_solar > e_solar),
                        color=C_ELEC, alpha=0.07, label="Solar adds")
    else:
        e = df["Journey Cum Cost"].values
        ax.plot(x, b, color=C_BASE, lw=2.5, label=f"Do nothing{lbl_a}")
        ax.plot(x, e, color=C_ELEC, lw=2.5, label=f"Your journey{lbl_a}")
        ax.fill_between(x, b, e, where=(b >= e), color=C_ELEC, alpha=0.12, label="Journey saves")
        ax.fill_between(x, b, e, where=(b <  e), color=C_BASE, alpha=0.12, label="Gas saves")

    if model.comparison_mode:
        bB = df["Baseline Cum Cost B"].values
        eB = df["Journey Cum Cost B"].values
        ax.plot(x, bB, color=C_BASE, lw=2.0, linestyle="--", label="Do nothing (B)")
        ax.plot(x, eB, color=C_ELEC, lw=2.0, linestyle="--", label="Your journey (B)")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(_money))
    ax.set_xlabel("Year")
    ax.set_ylabel("Cumulative Energy Cost")
    ax.legend(fontsize=8, framealpha=0.8)
    ax.set_title("Cumulative Energy Costs", fontsize=10, fontweight="bold")
    _style(ax)
    fig.tight_layout(pad=1.0)
    return fig


# Chart 2 — Annual Cost by Year
def make_annual_cost(df, model, n):
    fig = _new_fig()
    ax  = fig.add_subplot(111)
    x = np.arange(1, n + 1)
    if model.comparison_mode and "Baseline Annual Cost B" in df.columns:
        w = 0.18
        ax.bar(x - 1.5 * w, df["Baseline Annual Cost"].values,   w, color=C_BASE, label="Do nothing (A)",   zorder=3)
        ax.bar(x - 0.5 * w, df["Journey Annual Cost"].values,    w, color=C_ELEC, label="Your journey (A)", zorder=3)
        ax.bar(x + 0.5 * w, df["Baseline Annual Cost B"].values,  w, color=C_BASE, alpha=0.55,
               label="Do nothing (B)", zorder=3, hatch="//")
        ax.bar(x + 1.5 * w, df["Journey Annual Cost B"].values,   w, color=C_ELEC, alpha=0.55,
               label="Your journey (B)", zorder=3, hatch="//")
    else:
        w = 0.35
        ax.bar(x - w / 2, df["Baseline Annual Cost"].values, w, color=C_BASE, label="Do nothing",   zorder=3)
        ax.bar(x + w / 2, df["Journey Annual Cost"].values,  w, color=C_ELEC, label="Your journey", zorder=3)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(_money))
    ax.set_xlabel("Year")
    ax.set_ylabel("Annual Energy Cost")
    ax.legend(fontsize=8)
    ax.set_title("Annual Cost by Year", fontsize=10, fontweight="bold")
    _style(ax)
    fig.tight_layout(pad=1.0)
    return fig


# Chart 3 — Cost Breakdown by Category (stacked cumulative, dual pane)
def make_cost_breakdown(df, model, n):
    fig = _new_fig(wide=True)
    axes = fig.subplots(1, 2)
    title = "Cumulative Cost by Category"
    if model.comparison_mode:
        title += " — Scenario A"
    fig.suptitle(title, fontsize=10, fontweight="bold", y=1.01)
    homes = [
        (model.baseline_home, "Do Nothing",   0),
        (model.journey_home,  "Your Journey", 1),
    ]
    x = np.arange(1, n + 1)
    for ax, (home, title_sub, palette_idx) in zip(axes, homes):
        bottom = np.zeros(n)
        for cat in CATEGORY_ORDER:
            annual = home.cost_history_by_category.get(cat, [])
            if not annual:
                continue
            cum   = np.cumsum(annual[:n])
            color = CATEGORY_COLORS[cat][palette_idx]
            ax.fill_between(x, bottom, bottom + cum,
                            color=color, alpha=0.85, label=CATEGORY_LABELS[cat])
            ax.plot(x, bottom + cum, color=color, lw=0.5, alpha=0.5)
            bottom = bottom + cum
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(_money))
        ax.set_xlabel("Year")
        ax.set_ylabel("Cumulative Cost")
        ax.set_title(title_sub, fontsize=9, fontweight="bold")
        ax.legend(fontsize=7, framealpha=0.8, loc="upper left")
        _style(ax)
    fig.tight_layout(pad=1.0)
    return fig


# Chart 4 — Equipment Replacements (CapEx)
def make_capex(df, model, n):
    fig = _new_fig()
    ax  = fig.add_subplot(111)
    yrs    = np.arange(1, n + 1)
    b_vals = [model.baseline_home.capex_by_year.get(y, 0) for y in yrs]
    e_vals = [model.journey_home.capex_by_year.get(y, 0)  for y in yrs]
    w = 0.35
    ax.bar(yrs - w / 2, b_vals, w, color=C_BASE, label="Do nothing",   zorder=3)
    ax.bar(yrs + w / 2, e_vals, w, color=C_ELEC, label="Your journey", zorder=3)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(_money))
    ax.set_xlabel("Year")
    ax.set_ylabel("Replacement Cost")
    ax.legend(fontsize=8)
    title = "Equipment Replacements (CapEx)"
    if model.comparison_mode:
        title += " — Scenario A"
    ax.set_title(title, fontsize=10, fontweight="bold")
    _style(ax)
    fig.tight_layout(pad=1.0)
    return fig


# Chart 5 — Electricity Price Trend
def make_elec_price(df, model, n):
    fig = _new_fig()
    ax  = fig.add_subplot(111)
    x = np.arange(1, n + 1)
    lbl_a = f"Elec +{elec_cagr_pct_a.value}%/yr"
    ax.plot(x, df["Elec Rate"].values, color=C_ELEC, lw=2.5, label=lbl_a)
    if model.comparison_mode:
        lbl_b = f"Elec +{elec_cagr_pct_b.value}%/yr (B)"
        ax.plot(x, df["Elec Rate B"].values, color=C_ELEC, lw=2.0, linestyle="--", label=lbl_b)
        ax.legend(fontsize=8)
    ax.set_xlabel("Year")
    ax.set_ylabel("Avg Electricity Price  ($/kWh)")
    ax.set_title("Electricity Price Trend", fontsize=10, fontweight="bold")
    _style(ax)
    fig.tight_layout(pad=1.0)
    return fig


# Chart 6 — Gas Price Trend
def make_gas_price(df, model, n):
    fig = _new_fig()
    ax  = fig.add_subplot(111)
    x = np.arange(1, n + 1)
    lbl_a = f"Gas +{gas_cagr_pct_a.value}%/yr"
    ax.plot(x, df["Gas Rate"].values, color="#EF6C00", lw=2.5, label=lbl_a)
    if model.comparison_mode:
        lbl_b = f"Gas +{gas_cagr_pct_b.value}%/yr (B)"
        ax.plot(x, df["Gas Rate B"].values, color="#EF6C00", lw=2.0, linestyle="--", label=lbl_b)
        ax.legend(fontsize=8)
    ax.set_xlabel("Year")
    ax.set_ylabel("Avg Gas Price  ($/therm)")
    ax.set_title("Gas Price Trend", fontsize=10, fontweight="bold")
    _style(ax)
    fig.tight_layout(pad=1.0)
    return fig


# Chart 7 — Journey Timeline
def make_journey_timeline(df, model, n):
    display_slots = [s for s in model.journey_home.slots
                     if s.name != "Lights and Appliances"]
    n_rows = len(display_slots)

    fig = Figure(figsize=(12, max(3.0, n_rows * 0.9 + 1.5)), dpi=100)
    fig.patch.set_facecolor("#F9F9F9")
    ax = fig.add_subplot(111)

    # Gas price background gradient: light→deep orange tracks price rise
    gas_rates = df["Gas Rate"].values
    g_min, g_max = gas_rates.min(), gas_rates.max()
    for yr_idx in range(n):
        norm  = (gas_rates[yr_idx] - g_min) / (g_max - g_min) if g_max > g_min else 0
        alpha = 0.07 + 0.22 * norm
        ax.axvspan(yr_idx + 0.5, yr_idx + 1.5, color="#EF6C00", alpha=alpha, zorder=0)

    for i, slot in enumerate(display_slots):
        y     = i
        sw    = slot.swap_year
        state = slot.starting_state
        net   = slot.install_cost - slot.rebate

        if state == "electric":
            ax.plot([1, n], [y, y], color=C_ELEC, lw=3, solid_capstyle="round", zorder=3)
            ax.text(n + 0.4, y, "✓ Done", va="center", fontsize=8, color=C_ELEC)

        elif state == "none":
            if sw is not None and sw <= n:
                ax.plot([sw, n], [y, y], color=C_ELEC, lw=3, solid_capstyle="round", zorder=3)
                ax.plot(sw, y, "o", color=C_ELEC, ms=8, zorder=5)
                ax.annotate(f"+${net:,.0f}", xy=(sw, y),
                            xytext=(sw + 0.4, y + 0.3), fontsize=7, color=C_ELEC, zorder=5)
            else:
                ax.plot([1, n], [y, y], color="#CCCCCC", lw=1.5, linestyle=":", zorder=2)
                ax.text(n + 0.4, y, "Not adding", va="center", fontsize=7, color="#AAAAAA")

        else:  # gas
            if sw is not None and sw <= n:
                ax.plot([1, sw], [y, y], color=C_BASE, lw=2.5, linestyle="--", zorder=3)
                ax.plot([sw, n], [y, y], color=C_ELEC, lw=2.5, solid_capstyle="round", zorder=3)
                ax.plot(sw, y, "o", color=C_ELEC, ms=8, zorder=5)
                ax.annotate(f"${net:,.0f}", xy=(sw, y),
                            xytext=(sw + 0.4, y + 0.3), fontsize=7, color="#333333", zorder=5)
            else:
                ax.plot([1, n], [y, y], color=C_BASE, lw=2.5, linestyle="--", zorder=3)

    # CapEx-only slot markers — ⚡ for panel, ☀️ for solar
    panel_color = "#78909C"
    solar_color = "#F9A825"
    has_panel_marker = False
    for cslot in model.journey_home.capex_only_slots:
        if cslot.install_year is not None and cslot.install_year <= n:
            is_solar = "Solar" in cslot.name
            color = solar_color if is_solar else panel_color
            icon  = "☀️" if is_solar else "⚡"
            ax.axvline(cslot.install_year, color=color, linewidth=1.5,
                       linestyle=":", alpha=0.8, zorder=4)
            ax.text(cslot.install_year + 0.2, n_rows - 0.55,
                    f"{icon} {cslot.name}\n${cslot.net_install_cost:,.0f}",
                    fontsize=7, color=color, va="top", zorder=5)
            has_panel_marker = True

    ax.set_yticks(range(n_rows))
    ax.set_yticklabels([s.name for s in display_slots], fontsize=9)
    ax.set_xlabel("Simulation Year")
    ax.set_xlim(0.5, n + 3.5)
    ax.set_ylim(-0.7, n_rows - 0.3)
    ax.set_title("Journey Timeline — Swap Schedule", fontsize=10, fontweight="bold")
    handles = [
        Line2D([0], [0], color=C_BASE, lw=2, linestyle="--", label="Gas device running"),
        Line2D([0], [0], color=C_ELEC, lw=2, label="Electric device running"),
    ]
    if has_panel_marker:
        handles.append(
            Line2D([0], [0], color=panel_color, lw=1.5, linestyle=":",
                   label="CapEx event (panel / solar)")
        )
    ax.legend(handles=handles, fontsize=8, loc="lower right")
    _style(ax)
    fig.tight_layout(pad=1.0)
    return fig


def render_device_chart(model, home: str = "journey",
                        chart_type: str = "device_cost") -> Figure:
    """Stacked area chart — annual cost or kWh-equivalent per device per year."""
    jh = model.journey_home if home == "journey" else model.baseline_home
    n = model.n_years
    cal_years = list(range(model.sim_start_year, model.sim_start_year + n))

    fig = Figure(figsize=(8, 3.8), dpi=100)
    fig.patch.set_facecolor("#F9F9F9")
    ax = fig.add_subplot(111)
    ax.set_facecolor("#F9F9F9")

    stack = np.zeros(n)
    patches = []
    is_cost = chart_type == "device_cost"

    if is_cost:
        y_fmt   = lambda v, _: f"${v/1000:.1f}k"
        y_label = "$/yr"
    else:
        y_fmt   = lambda v, _: f"{v/1000:.1f}k"
        y_label = "kWh-eq / yr"

    for i, name in enumerate(DEVICE_ORDER):
        if is_cost:
            data = np.array(
                jh.cost_history_by_slot.get(name, [0] * n), dtype=float)
        else:
            raw   = np.array(
                jh.consumption_history_by_slot.get(name, [0] * n), dtype=float)
            fuels = jh.fuel_history_by_slot.get(name, ["electricity"] * n)
            data  = np.where(np.array(fuels) == "gas", raw * KWH_PER_THERM, raw)

        ax.fill_between(cal_years, stack, stack + data,
                        color=DEVICE_COLORS[i], alpha=DEVICE_ALPHAS[i], linewidth=0)
        ax.plot(cal_years, stack + data, color=DEVICE_COLORS[i], linewidth=1.2)
        patches.append(mpatches.Patch(color=DEVICE_COLORS[i], label=DEVICE_LABELS[i]))
        stack += data

    # Swap annotations — journey home only
    SWAP_COLORS = {"HVAC": "#0D47A1", "Water Heater": "#1565C0",
                   "Dryer": "#D0302D", "Cooktop": "#EC9B1E"}
    if home == "journey":
        for slot in jh.slots:
            if slot.swap_year is None:
                continue
            cal = model.sim_start_year + slot.swap_year - 1
            color = SWAP_COLORS.get(slot.name, "#78909C")
            ax.axvline(cal, color=color, linewidth=1.2,
                       linestyle=(0, (4, 3)), alpha=0.7)
            ax.text(cal + 0.15, 0.93, slot.name,
                    transform=ax.get_xaxis_transform(),
                    fontsize=7, color=color, va="top")

    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(y_fmt))
    ax.set_ylabel(y_label, fontsize=9, color="#78909C")
    ax.set_xlabel("Year", fontsize=9, color="#78909C")
    ax.tick_params(axis="both", labelsize=8, colors="#78909C")
    ax.grid(axis="y", color="#78909C", alpha=0.12, linewidth=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(handles=patches, loc="upper left", fontsize=8, framealpha=0.9, ncol=5)

    home_label  = "Your journey" if home == "journey" else "Do nothing"
    chart_label = "Annual cost by device" if is_cost \
                  else "Annual energy use by device (kWh-eq)"
    ax.set_title(f"{home_label} — {chart_label}",
                 fontsize=10, fontweight="bold", loc="left", pad=8)

    fig.tight_layout(pad=1.0)
    return fig


CHART_FNS = {
    "Cumulative Energy Costs":        make_cumulative_opex,
    "Annual Cost by Year":            make_annual_cost,
    "Cost Breakdown by Category":     make_cost_breakdown,
    "Equipment Replacements (CapEx)": make_capex,
    "Electricity Price Trend":        make_elec_price,
    "Gas Price Trend":                make_gas_price,
    "Journey Timeline":               make_journey_timeline,
}


# ── Sub-components ─────────────────────────────────────────────────────────────

_DEVICE_CHART_NAMES = {"Cost by Device", "Energy Use by Device"}


@solara.component
def ChartPane(chart_name, model, df, n):
    if chart_name in _DEVICE_CHART_NAMES:
        chart_type = "device_cost" if chart_name == "Cost by Device" else "device_consumption"
        home = device_chart_home.value
        with solara.Column(gap="4px"):
            with solara.Row(gap="6px", style="margin-bottom:4px"):
                for val, label in [("journey", "Your journey"), ("baseline", "Do nothing")]:
                    is_active = home == val
                    solara.Button(
                        label,
                        on_click=lambda v=val: device_chart_home.set(v),
                        style=(
                            f"background:{C_NAVY}; color:white; border:none;"
                            " border-radius:4px; padding:4px 14px;"
                            " font-size:0.82em; cursor:pointer;"
                            if is_active else
                            "background:#F5F5F5; color:#444; border:1px solid #CCCCCC;"
                            " border-radius:4px; padding:4px 14px;"
                            " font-size:0.82em; cursor:pointer;"
                        ),
                    )
            fig = render_device_chart(model, home=home, chart_type=chart_type)
            solara.FigureMatplotlib(fig)
    else:
        fig = CHART_FNS[chart_name](df, model, n)
        solara.FigureMatplotlib(fig)


@solara.component
def HomeInfoBar():
    """Chip row reading from reactive home-profile state — no model object needed."""
    insulation = insulation_quality.value.capitalize()
    bl_kwh = compute_baseload_kwh(
        square_footage.value, num_bedrooms.value, baseload_constant_before.value
    )
    solara.Markdown(
        f"📍 **San Jose, CA** &nbsp;·&nbsp; ZIP {zip_code.value} "
        f"&nbsp;·&nbsp; Climate Zone {climate_zone.value} "
        f"&nbsp;·&nbsp; {num_bedrooms.value} bed "
        f"&nbsp;·&nbsp; {square_footage.value:,} sq ft "
        f"&nbsp;·&nbsp; Built {year_built.value} "
        f"&nbsp;·&nbsp; {insulation} insulation "
        f"&nbsp;·&nbsp; Baseload ~{bl_kwh:,.0f} kWh/yr",
        style={"font-size": "0.85em", "color": "#555",
               "background": "#F0F4F8", "padding": "6px 12px",
               "border-radius": "6px"},
    )


@solara.component
def SummaryStats(df, n, model):
    delta_vals = df["Opex Delta"].values
    delta_cum  = float(delta_vals[-1])
    direction  = "saves" if delta_cum >= 0 else "costs extra vs. do-nothing"

    payback_yr = None
    for i, d in enumerate(delta_vals):
        if d > 0:
            payback_yr = i + 1
            break

    if payback_yr is not None:
        cal_pb = sim_start_year.value + payback_yr - 1
        pb_str = f"Payback: year {payback_yr}  ({cal_pb})"
    else:
        pb_str = f"No payback within {n} years"

    color = "#2E7D32" if delta_cum >= 0 else "#C62828"
    with solara.Row(gap="24px", style="flex-wrap:wrap; margin:4px 0"):
        solara.Markdown(
            f"**Journey {direction}:** **${abs(delta_cum):,.0f}** over {n} yrs (Scenario A)",
            style={"color": color, "font-size": "1.05em"},
        )
        solara.Markdown(f"**{pb_str}**", style={"color": "#555"})

        if model.comparison_mode and "Baseline Cum Cost B" in df.columns:
            bB   = float(df["Baseline Cum Cost B"].iloc[-1])
            eB   = float(df["Journey Cum Cost B"].iloc[-1])
            dB   = bB - eB
            dB_d = "saves" if dB >= 0 else "costs extra"
            pb_B = None
            for i, (b, e) in enumerate(zip(df["Baseline Cum Cost B"].values,
                                            df["Journey Cum Cost B"].values)):
                if b > e:
                    pb_B = i + 1
                    break
            pb_B_str = (f"Payback yr {pb_B} ({sim_start_year.value + pb_B - 1})"
                        if pb_B else f"No payback in {n} yrs")
            solara.Markdown(
                f"**Scenario B: {dB_d} ${abs(dB):,.0f}** — {pb_B_str}",
                style={"color": "#1565C0"},
            )


@solara.component
def SliderWithDefault(label, value, default, min, max, step=1, unit="", fmt="{v}"):
    """Slider with a default-position tick mark and a delta label when changed."""
    v = value.value
    at_default = abs(v - default) < (step * 0.01)
    delta = v - default
    tick_pct = int(100 * (default - min) / (max - min)) if max != min else 50
    display_label = f"{label}: {fmt.format(v=v)}{unit}"

    with solara.Column(gap="0px"):
        if isinstance(default, float):
            solara.SliderFloat(display_label, value=value, min=min, max=max, step=step)
        else:
            solara.SliderInt(display_label, value=value, min=min, max=max, step=int(step))

        solara.HTML(
            tag="div",
            unsafe_innerHTML=(
                f"<div style='position:relative;height:6px;margin:-4px 0 2px 0;"
                f"pointer-events:none;'>"
                f"<div style='position:absolute;left:{tick_pct}%;top:0;bottom:0;"
                f"width:2px;background:#0D47A1;opacity:0.5;border-radius:1px;'></div>"
                f"<div style='position:absolute;left:{tick_pct}%;top:50%;"
                f"transform:translate(-50%,-50%);width:6px;height:6px;"
                f"background:#0D47A1;opacity:0.5;border-radius:50%;'></div>"
                f"</div>"
            ),
        )

        if not at_default:
            sign = "+" if delta > 0 else ""
            color = "#D0302D" if delta < 0 else "#2E7D32"
            solara.HTML(
                tag="div",
                unsafe_innerHTML=(
                    f"<div style='font-size:0.75em;color:{color};"
                    f"margin-top:1px;padding-left:2px;'>"
                    f"{sign}{fmt.format(v=delta)}{unit} from default "
                    f"({fmt.format(v=default)}{unit})</div>"
                ),
            )


@solara.component
def SlotRow(name, state_rv, swap_planned_rv, swap_year_rv, install_cost_rv, rebate_rv):
    """One appliance row in the Journey Planner panel."""
    state   = state_rv.value
    planned = swap_planned_rv.value
    yr      = swap_year_rv.value
    inst    = install_cost_rv.value
    reb     = rebate_rv.value
    net     = inst - reb
    cal_yr  = sim_start_year.value + yr - 1

    show_swap = (state in ("gas", "none")) and planned

    with solara.Row(gap="8px", style=(
        "align-items:center; flex-wrap:wrap; padding:6px 0;"
        " border-bottom:1px solid #EEEEEE"
    )):
        with solara.Column(style="min-width:110px; max-width:110px"):
            solara.Text(name, style="font-weight:500; font-size:0.9em")

        with solara.Column(style="min-width:95px; max-width:95px"):
            solara.Select("", value=state_rv, values=["gas", "electric", "none"])

        with solara.Column(style="min-width:65px; max-width:65px"):
            if state != "electric":
                solara.Checkbox(label="Plan", value=swap_planned_rv)

        if show_swap:
            with solara.Column(style="min-width:170px"):
                solara.SliderInt(
                    f"Yr {yr}  ({cal_yr})",
                    value=swap_year_rv, min=1, max=25,
                )
            with solara.Column(style="min-width:100px"):
                solara.InputInt("Install $", value=install_cost_rv)
            with solara.Column(style="min-width:80px"):
                solara.InputInt("Rebate", value=rebate_rv)
            with solara.Column(style="min-width:70px"):
                solara.Text(
                    f"Net ${net:,}",
                    style="color:#1976D2; font-weight:600; font-size:0.85em",
                )
        elif state == "electric":
            solara.Text("✓ Already done", style="color:#2E7D32; font-weight:600; font-size:0.85em")
        else:
            solara.Text("—", style="color:#BBBBBB; font-size:1.2em")


@solara.component
def ExpandableSlotRow(name, state_rv, swap_planned_rv, swap_year_rv,
                      install_cost_rv, rebate_rv, expanded_rv, detail_component,
                      is_upgrade_slot=False):
    state    = state_rv.value
    planned  = swap_planned_rv.value
    yr       = swap_year_rv.value
    net      = install_cost_rv.value - rebate_rv.value
    cal_yr   = sim_start_year.value + yr - 1
    expanded = expanded_rv.value
    chevron  = "▼" if expanded else "▶"
    # upgrade slots (baseload) show swap controls whenever planned, regardless of state
    show_swap = planned if is_upgrade_slot else (state in ("gas", "none")) and planned

    with solara.Row(
        gap="8px",
        style="align-items:center; flex-wrap:wrap; padding:6px 0; border-bottom:1px solid #EEEEEE;",
    ):
        solara.Button(
            chevron,
            on_click=lambda: expanded_rv.set(not expanded_rv.value),
            style=(
                "background:none; border:none; cursor:pointer; color:#78909C;"
                " font-size:0.9em; padding:0 4px 0 0; min-width:14px; flex-shrink:0;"
            ),
        )
        with solara.Column(style="min-width:100px; max-width:100px"):
            solara.Text(name, style="font-weight:500; font-size:0.9em")
        with solara.Column(style="min-width:90px; max-width:90px"):
            if is_upgrade_slot:
                solara.Text("Electric", style="color:#2E7D32; font-size:0.88em; padding:4px 0")
            else:
                solara.Select("", value=state_rv, values=["gas", "electric", "none"])
        with solara.Column(style="min-width:60px; max-width:60px"):
            if is_upgrade_slot or state != "electric":
                solara.Checkbox(label="Plan", value=swap_planned_rv)
        if show_swap:
            with solara.Column(style="min-width:160px"):
                solara.SliderInt(f"Yr {yr} ({cal_yr})", value=swap_year_rv, min=1, max=25)
            with solara.Column(style="min-width:90px"):
                solara.InputInt("Install $", value=install_cost_rv)
            with solara.Column(style="min-width:70px"):
                solara.InputInt("Rebate", value=rebate_rv)
            with solara.Column(style="min-width:65px"):
                solara.Text(f"Net ${net:,}",
                            style="color:#1976D2; font-weight:600; font-size:0.85em")
        elif not is_upgrade_slot and state == "electric":
            solara.Text("✓ Done", style="color:#2E7D32; font-weight:600; font-size:0.85em")
        else:
            solara.Text("—", style="color:#BBBBBB; font-size:1.2em")

    if expanded:
        with solara.Column(
            style=(
                "margin:0 0 8px 24px; padding:10px 14px;"
                " background:#F8F9FA; border-radius:8px;"
                " border-left:3px solid #C5CAE9;"
            )
        ):
            detail_component()


@solara.component
def HVACDetail():
    ua = UA_MAP[insulation_quality.value]
    is_gas = hvac_starting_state.value == "gas"

    solara.Markdown("**Estimated consumption**")
    if is_gas:
        therms = _est_gas_furnace(furnace_afue.value, ua)
        cool_line = (
            f"| Cooling (AC) | ~{_est_hp_hvac_cooling(hvac_ac_seer.value, ua):.0f} kWh/yr |\n"
            if hvac_has_cooling.value else ""
        )
        solara.Markdown(
            f"|  | Current (gas) |\n|--|--|\n"
            f"| Heating | {therms:.0f} therms/yr (~{_kwh_eq(therms):,.0f} kWh-eq) |\n"
            + cool_line
        )
    else:
        heat_kwh = _est_hp_hvac_heating(hp_cop_heating.value, ua)
        cool_kwh = _est_hp_hvac_cooling(hp_seer_cooling.value, ua)
        solara.Markdown(
            f"|  | Current (electric) |\n|--|--|\n"
            f"| Heating | {heat_kwh:.0f} kWh/yr |\n"
            f"| Cooling | {cool_kwh:.0f} kWh/yr |\n"
            f"| Total   | {heat_kwh + cool_kwh:.0f} kWh/yr |\n"
        )

    solara.Markdown("---")
    if is_gas:
        solara.Markdown("**Current: Gas Furnace**")
        SliderWithDefault("Furnace AFUE", furnace_afue, _DEFAULTS["furnace_afue"],
                          0.70, 0.95, 0.01, fmt="{v:.2f}")
        SliderWithDefault("Furnace age", hvac_furnace_age, _DEFAULTS["hvac_furnace_age"],
                          0, 30, 1, unit=" yrs")
        solara.Checkbox(label="Has central AC in baseline", value=hvac_has_cooling)
        if hvac_has_cooling.value:
            SliderWithDefault("Central AC SEER", hvac_ac_seer, _DEFAULTS["hvac_ac_seer"],
                              10, 22, 1)
            SliderWithDefault("Central AC age", hvac_ac_age, _DEFAULTS["hvac_ac_age"],
                              0, 20, 1, unit=" yrs")
    else:
        solara.Markdown("**Current: Heat Pump HVAC**")
        SliderWithDefault("Heating COP", hp_cop_heating, _DEFAULTS["hp_cop_heating"],
                          2.5, 4.5, 0.1, fmt="{v:.1f}")
        SliderWithDefault("Cooling SEER", hp_seer_cooling, _DEFAULTS["hp_seer_cooling"],
                          16, 28, 1)

    if hvac_swap_planned.value and is_gas:
        solara.Markdown("---")
        solara.Markdown("**Replacement: Heat Pump HVAC**")
        heat_kwh = _est_hp_hvac_heating(hp_cop_heating.value, ua)
        cool_kwh = _est_hp_hvac_cooling(hp_seer_cooling.value, ua)
        solara.Markdown(
            f"Est. consumption: {heat_kwh:.0f} kWh/yr heating + "
            f"{cool_kwh:.0f} kWh/yr cooling = **{heat_kwh + cool_kwh:.0f} kWh/yr total**"
        )
        SliderWithDefault("Heating COP", hp_cop_heating, _DEFAULTS["hp_cop_heating"],
                          2.5, 4.5, 0.1, fmt="{v:.1f}")
        SliderWithDefault("Cooling SEER", hp_seer_cooling, _DEFAULTS["hp_seer_cooling"],
                          16, 28, 1)
        solara.InputInt("Install cost $", value=hvac_install_cost)
        solara.InputInt("Rebate $", value=hvac_rebate)
        solara.Text(f"Net cost: ${hvac_install_cost.value - hvac_rebate.value:,}",
                    style="color:#1976D2; font-weight:600")


@solara.component
def WaterHeaterDetail():
    ua = UA_MAP[insulation_quality.value]
    gal = hw_daily_gallons.value
    is_gas = wh_starting_state.value == "gas"

    solara.Markdown("**Estimated consumption**")
    if is_gas:
        therms = _est_gas_wh(gas_wh_uef.value, gal)
        solara.Markdown(
            f"|  | Current (gas) |\n|--|--|\n"
            f"| Water heating | {therms:.0f} therms/yr (~{_kwh_eq(therms):,.0f} kWh-eq) |\n"
        )
    else:
        kwh = _est_hpwh(hpwh_uef.value, gal)
        solara.Markdown(
            f"|  | Current (electric) |\n|--|--|\n"
            f"| Water heating | {kwh:.0f} kWh/yr |\n"
        )

    solara.Markdown("---")
    if is_gas:
        solara.Markdown("**Current: Gas Water Heater**")
        SliderWithDefault("Gas WH UEF", gas_wh_uef, _DEFAULTS["gas_wh_uef"],
                          0.55, 0.70, 0.01, fmt="{v:.2f}")
        SliderWithDefault("Age", wh_gas_age, _DEFAULTS["wh_gas_age"],
                          0, 20, 1, unit=" yrs")
    else:
        solara.Markdown("**Current: Heat Pump Water Heater**")
        SliderWithDefault("HPWH UEF", hpwh_uef, _DEFAULTS["hpwh_uef"],
                          2.5, 4.0, 0.1, fmt="{v:.1f}")

    def _set_gallons(v):
        hw_daily_gallons.set(v)
        hw_gallons_user_override.set(True)

    solara.SliderInt(
        f"Daily hot water: {hw_daily_gallons.value} gal/day",
        value=hw_daily_gallons, min=20, max=120, step=5,
        on_value=_set_gallons,
    )
    solara.Text(f"(bedroom default: {_DEFAULTS['hw_daily_gallons']} gal/day)",
                style="font-size:0.78em; color:#888")

    if wh_swap_planned.value and is_gas:
        solara.Markdown("---")
        solara.Markdown("**Replacement: Heat Pump Water Heater**")
        kwh = _est_hpwh(hpwh_uef.value, gal)
        solara.Markdown(f"Est. consumption: **{kwh:.0f} kWh/yr**")
        SliderWithDefault("HPWH UEF", hpwh_uef, _DEFAULTS["hpwh_uef"],
                          2.5, 4.0, 0.1, fmt="{v:.1f}")
        solara.InputInt("Install cost $", value=wh_install_cost)
        solara.InputInt("Rebate $", value=wh_rebate)
        solara.Text(f"Net cost: ${wh_install_cost.value - wh_rebate.value:,}",
                    style="color:#1976D2; font-weight:600")


@solara.component
def DryerDetail():
    is_gas = dryer_starting_state.value == "gas"

    solara.Markdown("**Estimated consumption**")
    if is_gas:
        therms = _est_gas_dryer(dryer_gas_therms_per_cycle.value, dryer_loads_per_week.value)
        solara.Markdown(
            f"|  | Current (gas) |\n|--|--|\n"
            f"| Dryer | {therms:.0f} therms/yr (~{_kwh_eq(therms):,.0f} kWh-eq) |\n"
        )
    else:
        kwh = _est_hp_dryer(dryer_hp_kwh_per_cycle.value, dryer_loads_per_week.value)
        solara.Markdown(
            f"|  | Current (electric) |\n|--|--|\n"
            f"| Dryer | {kwh:.0f} kWh/yr |\n"
        )

    solara.Markdown("---")
    if is_gas:
        solara.Markdown("**Current: Gas Dryer**")
        SliderWithDefault("Therms/cycle", dryer_gas_therms_per_cycle,
                          _DEFAULTS["dryer_gas_therms_per_cycle"],
                          0.15, 0.35, 0.01, fmt="{v:.2f}")
    else:
        solara.Markdown("**Current: Heat Pump Dryer**")
        SliderWithDefault("kWh/cycle", dryer_hp_kwh_per_cycle,
                          _DEFAULTS["dryer_hp_kwh_per_cycle"],
                          1.2, 2.5, 0.1, fmt="{v:.1f}")
    SliderWithDefault("Loads/week", dryer_loads_per_week, _DEFAULTS["dryer_loads_per_week"],
                      1, 14, 1, unit=" /wk")

    if dryer_swap_planned.value and is_gas:
        solara.Markdown("---")
        solara.Markdown("**Replacement: Heat Pump Dryer**")
        kwh = _est_hp_dryer(dryer_hp_kwh_per_cycle.value, dryer_loads_per_week.value)
        solara.Markdown(f"Est. consumption: **{kwh:.0f} kWh/yr**")
        SliderWithDefault("kWh/cycle", dryer_hp_kwh_per_cycle,
                          _DEFAULTS["dryer_hp_kwh_per_cycle"],
                          1.2, 2.5, 0.1, fmt="{v:.1f}")
        solara.InputInt("Install cost $", value=dryer_install_cost)
        solara.InputInt("Rebate $", value=dryer_rebate)
        solara.Text(f"Net cost: ${dryer_install_cost.value - dryer_rebate.value:,}",
                    style="color:#1976D2; font-weight:600")


@solara.component
def CooktopDetail():
    is_gas = cooktop_starting_state.value == "gas"

    solara.Markdown("**Estimated consumption**")
    if is_gas:
        therms = _est_gas_cooktop(cooktop_gas_therms_per_meal.value, cooktop_meals_per_week.value)
        solara.Markdown(
            f"|  | Current (gas) |\n|--|--|\n"
            f"| Cooktop | {therms:.0f} therms/yr (~{_kwh_eq(therms):,.0f} kWh-eq) |\n"
        )
    else:
        kwh = _est_induction(cooktop_induction_kwh_per_meal.value, cooktop_meals_per_week.value)
        solara.Markdown(
            f"|  | Current (electric) |\n|--|--|\n"
            f"| Cooktop | {kwh:.0f} kWh/yr |\n"
        )

    solara.Markdown("---")
    if is_gas:
        solara.Markdown("**Current: Gas Cooktop**")
        SliderWithDefault("Therms/meal", cooktop_gas_therms_per_meal,
                          _DEFAULTS["cooktop_gas_therms_per_meal"],
                          0.03, 0.10, 0.01, fmt="{v:.2f}")
    else:
        solara.Markdown("**Current: Induction Cooktop**")
        SliderWithDefault("kWh/meal", cooktop_induction_kwh_per_meal,
                          _DEFAULTS["cooktop_induction_kwh_per_meal"],
                          0.6, 1.4, 0.1, fmt="{v:.1f}")
    SliderWithDefault("Meals/week", cooktop_meals_per_week, _DEFAULTS["cooktop_meals_per_week"],
                      3, 21, 1, unit=" /wk")

    if cooktop_swap_planned.value and is_gas:
        solara.Markdown("---")
        solara.Markdown("**Replacement: Induction Cooktop**")
        kwh = _est_induction(cooktop_induction_kwh_per_meal.value, cooktop_meals_per_week.value)
        solara.Markdown(f"Est. consumption: **{kwh:.0f} kWh/yr**")
        SliderWithDefault("kWh/meal", cooktop_induction_kwh_per_meal,
                          _DEFAULTS["cooktop_induction_kwh_per_meal"],
                          0.6, 1.4, 0.1, fmt="{v:.1f}")
        solara.InputInt("Install cost $", value=cooktop_install_cost)
        solara.InputInt("Rebate $", value=cooktop_rebate)
        solara.Text(f"Net cost: ${cooktop_install_cost.value - cooktop_rebate.value:,}",
                    style="color:#1976D2; font-weight:600")


@solara.component
def EVDetail():
    annual_kwh = _est_ev_kwh(ev_miles_per_year.value,
                              ev_kwh_per_mile.value,
                              ev_charging_efficiency.value)
    solara.Markdown("**Estimated consumption**")
    solara.Markdown(
        f"|  | After adding EV |\n|--|--|\n"
        f"| EV charging | **{annual_kwh:,.0f} kWh/yr** "
        f"({ev_miles_per_year.value:,} mi × {ev_kwh_per_mile.value} kWh/mi ÷ "
        f"{ev_charging_efficiency.value} eff.) |\n"
    )
    solara.Text("(Not in do-nothing baseline — absent until you add the EV)",
                style="font-size:0.80em; color:#888")

    if ev_swap_planned.value:
        solara.Markdown("---")
        solara.Markdown("**EV Charger (L2)**")

        SliderWithDefault(
            "Annual miles", ev_miles_per_year,
            _DEFAULTS["ev_miles_per_year"],
            1000, 30000, step=500, unit=" mi/yr",
        )

        SliderWithDefault(
            "Vehicle efficiency", ev_kwh_per_mile,
            _DEFAULTS["ev_kwh_per_mile"],
            0.23, 0.45, step=0.01, unit=" kWh/mi", fmt="{v:.2f}",
        )
        with solara.Row(gap="6px", style="flex-wrap:wrap; margin:-4px 0 4px 0"):
            for label in ("Efficient", "Average", "Large"):
                solara.Button(
                    label,
                    on_click=lambda l=label: _apply_ev_efficiency_preset(l),
                    style=(
                        "font-size:0.78em; padding:2px 8px;"
                        " border-radius:12px; cursor:pointer;"
                        " background:#E8EAF6; border:1px solid #C5CAE9;"
                        " color:#3949AB;"
                    ),
                )

        SliderWithDefault(
            "Charging efficiency", ev_charging_efficiency,
            _DEFAULTS["ev_charging_efficiency"],
            0.80, 0.98, step=0.01, fmt="{v:.2f}",
        )

        est = _est_ev_kwh(ev_miles_per_year.value,
                          ev_kwh_per_mile.value,
                          ev_charging_efficiency.value)
        solara.Text(f"Est. consumption: ~{est:,.0f} kWh/yr",
                    style="font-size:0.85em; color:#1976D2; font-weight:600")

        solara.InputInt("Install cost $", value=ev_install_cost)
        solara.InputInt("Rebate $", value=ev_rebate)
        solara.Text(f"Net cost: ${ev_install_cost.value - ev_rebate.value:,}",
                    style="color:#1976D2; font-weight:600")


@solara.component
def BaseloadDetail():
    """Expanded detail for the Lights & Appliances row."""
    bl_before = compute_baseload_kwh(
        square_footage.value, num_bedrooms.value, baseload_constant_before.value
    )

    solara.Markdown("**Estimated consumption**")
    solara.Markdown(
        f"|  | Current |\n|--|--|\n"
        f"| Lights & appliances | **{bl_before:,.0f} kWh/yr** |\n"
        f"| Formula | {square_footage.value:,} sqft × 0.45 + "
        f"{num_bedrooms.value} bed × 200 + {baseload_constant_before.value} |\n"
    )

    solara.Markdown("---")
    solara.Markdown("**Always-on appliances (constant term)**")
    SliderWithDefault(
        "Always-on", baseload_constant_before,
        _DEFAULTS["baseload_constant_before"],
        0, 1500, step=50, unit=" kWh/yr",
    )
    solara.Markdown(
        f"<small style='color:#555'>→ Estimated total baseload: "
        f"**{bl_before:,.0f} kWh/yr** "
        f"({square_footage.value:,} sqft × 0.45 + {num_bedrooms.value} bed × 200 "
        f"+ {baseload_constant_before.value})</small>"
    )

    if baseload_swap_planned.value:
        bl_after = compute_baseload_kwh(
            square_footage.value, num_bedrooms.value, baseload_constant_after.value
        )
        annual_saving_kwh = bl_before - bl_after
        elec_rate = 0.386
        annual_saving_usd = annual_saving_kwh * elec_rate
        net_cost = baseload_install_cost.value - baseload_rebate.value
        payback = (net_cost / annual_saving_usd) if annual_saving_usd > 0 else None
        pb_str = f"~{payback:.1f} yrs" if payback is not None else "N/A"

        solara.Markdown("---")
        solara.Markdown("**After efficiency upgrade (LED, smart plugs, etc.)**")
        SliderWithDefault(
            "After-upgrade always-on", baseload_constant_after,
            _DEFAULTS["baseload_constant_after"],
            0, 1500, step=50, unit=" kWh/yr",
        )
        solara.Markdown(
            f"<small style='color:#555'>→ Total after: **{bl_after:,.0f} kWh/yr** "
            f"&nbsp;·&nbsp; Saving: **{annual_saving_kwh:,.0f} kWh/yr ≈ "
            f"${annual_saving_usd:,.0f}/yr**</small>"
        )
        solara.Markdown(
            f"<small style='color:#555'>"
            f"Net cost: **${net_cost:,}** &nbsp;·&nbsp; "
            f"Simple payback: **{pb_str}**"
            f"</small>"
        )


@solara.component
def SolarBatteryPanel(model):
    with solara.Card(margin=0, elevation=1, style="overflow:hidden"):
        with solara.Row(style=(
            "background-color:#F0F0F0; padding:6px 12px;"
            " border-radius:4px 4px 0 0; margin:-16px -16px 8px -16px;"
        )):
            solara.Text("☀️🔋 Solar + Battery", style="font-weight:600; font-size:0.95em")
        solara.Checkbox(label="Adding solar + battery to my journey",
                        value=solar_planned)

        if not solar_planned.value:
            return

        cal_yr = sim_start_year.value + solar_install_year.value - 1
        solara.SliderInt(
            f"Install in year {solar_install_year.value}  ({cal_yr})",
            value=solar_install_year, min=1, max=25,
        )
        solara.SliderInt(
            f"% of electricity covered: {solar_coverage_pct.value}%",
            value=solar_coverage_pct, min=0, max=100, step=5,
        )
        solara.Text("(Phase 3 will compute this from system size + usage)",
                    style="font-size:0.78em; color:#888")

        gross_cost = (
            (solar_panels_cost.value if solar_include_panels.value else 0)
            + (solar_battery_cost.value if solar_include_battery.value else 0)
            + (solar_install_cost_item.value if solar_include_install.value else 0)
        )
        net_cost = gross_cost - solar_rebate.value

        # ── Collapsible cost row (same style as appliance rows) ───────────────
        cost_expanded = solar_cost_expanded.value
        cost_chevron  = "▼" if cost_expanded else "▶"
        with solara.Row(
            gap="8px",
            style="align-items:center; flex-wrap:wrap; padding:6px 0; border-top:1px solid #EEEEEE;",
        ):
            solara.Button(
                cost_chevron,
                on_click=lambda: solar_cost_expanded.set(not solar_cost_expanded.value),
                style=(
                    "background:none; border:none; cursor:pointer; color:#78909C;"
                    " font-size:0.9em; padding:0 4px 0 0; min-width:14px; flex-shrink:0;"
                ),
            )
            solara.Text("Cost items", style="font-weight:500; font-size:0.9em; min-width:100px")
            solara.Text(
                f"Net ${net_cost:,}",
                style="color:#1976D2; font-weight:600; font-size:0.85em",
            )

        if cost_expanded:
            with solara.Column(
                style=(
                    "margin:0 0 8px 24px; padding:10px 14px;"
                    " background:#F8F9FA; border-radius:8px;"
                    " border-left:3px solid #C5CAE9;"
                )
            ):
                with solara.Row(gap="8px", style="align-items:center; flex-wrap:wrap"):
                    solara.Checkbox(label="Solar panels (10 kW)", value=solar_include_panels)
                    if solar_include_panels.value:
                        solara.InputInt("$", value=solar_panels_cost)

                with solara.Row(gap="8px", style="align-items:center; flex-wrap:wrap"):
                    solara.Checkbox(label="Battery storage (13.5 kWh)", value=solar_include_battery)
                    if solar_include_battery.value:
                        solara.InputInt("$", value=solar_battery_cost)

                with solara.Row(gap="8px", style="align-items:center; flex-wrap:wrap"):
                    solara.Checkbox(label="Installation & permitting", value=solar_include_install)
                    if solar_include_install.value:
                        solara.InputInt("$", value=solar_install_cost_item)

                solara.InputInt("Rebate $", value=solar_rebate)
                solara.Markdown(
                    f"| | |\n|--|--|\n"
                    f"| Gross cost | **${gross_cost:,}** |\n"
                    f"| Rebate | **-${solar_rebate.value:,}** |\n"
                    f"| **Net cost** | **${net_cost:,}** |\n"
                    f"| Lifespan | 25 years |\n"
                )

        if model is not None and model.journey_home.solar_savings_history:
            annual_saving = model.journey_home.solar_savings_history[0]
            if annual_saving > 0 and net_cost > 0:
                payback = net_cost / annual_saving
                solara.Markdown(
                    f"Est. annual saving: **${annual_saving:,.0f}/yr**  \n"
                    f"Est. simple payback: **~{payback:.1f} yrs**  \n"
                    f"<small style='color:#888'>"
                    f"(Payback improves as electric rates rise over time)</small>"
                )
            elif annual_saving <= 0:
                solara.Text("No electric loads to offset in year 1.",
                            style="font-size:0.82em; color:#888")


@solara.component
def PanelDetail():
    """Expanded detail for the Electrical Panel Upgrade row."""
    solara.Markdown(
        "<small style='color:#888'>Often required when adding an EV charger (L2) "
        "or heat pump to older homes with 100A panels.</small>"
    )
    SliderWithDefault(
        "Install cost", panel_upgrade_cost,
        _DEFAULTS["panel_upgrade_cost"],
        2000, 10000, step=500, unit=" $",
    )
    solara.InputInt("Rebate $", value=panel_upgrade_rebate)
    net = panel_upgrade_cost.value - panel_upgrade_rebate.value
    solara.Markdown(
        f"<small style='color:#555'>"
        f"Net cost: **${net:,}** &nbsp;·&nbsp; Lifespan: **25 years**"
        f"</small>"
    )


@solara.component
def JourneyPlannerPanel():
    with solara.Card(margin=0, elevation=1, style="overflow:hidden"):
        with solara.Row(style=(
            "background-color:#F0F0F0; padding:6px 12px;"
            " border-radius:4px 4px 0 0; margin:-16px -16px 8px -16px;"
        )):
            solara.Text("🗺️ Your Electrification Journey",
                        style="font-weight:600; font-size:0.95em")
        with solara.Row(gap="8px",
                        style="padding:2px 0 4px 0; font-size:0.76em; color:#999"):
            solara.Text(" ",           style="min-width:14px")
            solara.Text("Appliance",   style="min-width:100px; max-width:100px; font-weight:600")
            solara.Text("State",       style="min-width:90px;  max-width:90px")
            solara.Text("Plan swap?",  style="min-width:60px;  max-width:60px")
            solara.Text("Year / Cost", style="flex:1")

        ExpandableSlotRow("HVAC",
                          hvac_starting_state, hvac_swap_planned,
                          hvac_swap_year, hvac_install_cost, hvac_rebate,
                          hvac_expanded, lambda: HVACDetail())
        ExpandableSlotRow("Water Heater",
                          wh_starting_state, wh_swap_planned,
                          wh_swap_year, wh_install_cost, wh_rebate,
                          wh_expanded, lambda: WaterHeaterDetail())
        ExpandableSlotRow("Dryer",
                          dryer_starting_state, dryer_swap_planned,
                          dryer_swap_year, dryer_install_cost, dryer_rebate,
                          dryer_expanded, lambda: DryerDetail())
        ExpandableSlotRow("Cooktop",
                          cooktop_starting_state, cooktop_swap_planned,
                          cooktop_swap_year, cooktop_install_cost, cooktop_rebate,
                          cooktop_expanded, lambda: CooktopDetail())
        ExpandableSlotRow("EV Charger",
                          ev_starting_state, ev_swap_planned,
                          ev_swap_year, ev_install_cost, ev_rebate,
                          ev_expanded, lambda: EVDetail())
        ExpandableSlotRow("Elec. Panel",
                          _panel_state, panel_upgrade_planned,
                          panel_upgrade_year, panel_upgrade_cost, panel_upgrade_rebate,
                          panel_expanded, lambda: PanelDetail(),
                          is_upgrade_slot=True)
        ExpandableSlotRow("Lights & Appliances",
                          _baseload_state, baseload_swap_planned,
                          baseload_swap_year, baseload_install_cost, baseload_rebate,
                          baseload_expanded, lambda: BaseloadDetail(),
                          is_upgrade_slot=True)

        solara.Markdown(
            "<small style='color:#888'>ℹ️ <em>\"Do nothing\" baseline runs automatically: "
            "gas devices stay gas; already-done devices stay electric; "
            "</em></small>"
        )


@solara.component
def HomeProfilePanel():
    expanded = home_profile_details_expanded.value
    chevron  = "▼" if expanded else "▶"

    with solara.Card(margin=0, elevation=1, style="overflow:hidden"):
        with solara.Row(style=(
            "background-color:#F0F0F0; padding:6px 12px;"
            " border-radius:4px 4px 0 0; margin:-16px -16px 8px -16px;"
        )):
            solara.Text("🏠 Home Profile", style="font-weight:600; font-size:0.95em")
        # Always-visible fields
        solara.InputText("ZIP code", value=zip_code)
        solara.Select("Bedrooms", value=num_bedrooms, values=_BR_OPTIONS)
        solara.InputInt("Square footage", value=square_footage)

        # Expand/collapse toggle
        solara.Button(
            f"{chevron} More details...",
            on_click=lambda: home_profile_details_expanded.set(not expanded),
            style=(
                "background:none; border:none; cursor:pointer;"
                " color:#546E7A; font-size:0.85em; padding:4px 0;"
                " text-align:left; display:block;"
            ),
        )

        if expanded:
            solara.Select("Climate zone", value=climate_zone, values=_CZ_OPTIONS)
            solara.InputInt("Year built", value=year_built)
            solara.Markdown("**Building Performance**")
            solara.Select("Insulation quality", value=insulation_quality,
                          values=["poor", "average", "good"])
            solara.Markdown(
                "<small style='color:#888'>Device specs live in each appliance row "
                "(click ▶ to expand).</small>"
            )


def _preset_buttons(gas_rv, elec_rv, apply_fn):
    active = _current_preset_label(gas_rv.value, elec_rv.value)
    with solara.Row(gap="4px", style="flex-wrap:wrap"):
        for key, display in _PRESET_DISPLAY.items():
            is_active = active.lower() == key
            solara.Button(
                display,
                on_click=lambda k=key: apply_fn(k),
                style=(
                    f"background:{C_NAVY}; color:white; border:none;"
                    " border-radius:4px; padding:4px 10px; font-size:0.80em; cursor:pointer;"
                    if is_active else
                    "background:#F5F5F5; color:#444; border:1px solid #CCCCCC;"
                    " border-radius:4px; padding:4px 10px; font-size:0.80em; cursor:pointer;"
                ),
            )
        if active == "Custom":
            solara.Text("⚙️ Custom",
                        style="color:#888; font-size:0.80em; align-self:center")


@solara.component
def EnergyPricesPanel():
    with solara.Card(margin=0, elevation=1, style="overflow:hidden"):
        with solara.Row(style=(
            "background-color:#F0F0F0; padding:6px 12px;"
            " border-radius:4px 4px 0 0; margin:-16px -16px 8px -16px;"
        )):
            solara.Text("📈 Energy & Prices", style="font-weight:600; font-size:0.95em")
        solara.Markdown("**Quick presets**")
        _preset_buttons(gas_cagr_pct_a, elec_cagr_pct_a, _apply_preset_a)

        solara.HTML(tag="div", unsafe_innerHTML=(
            f"<div style='color:{C_RED}; font-size:0.83em; margin:8px 0 -4px 0; font-weight:500'>"
            "🔴 Gas escalation</div>"
        ))
        solara.SliderInt(f"+{gas_cagr_pct_a.value}%/yr",
                         value=gas_cagr_pct_a, min=0, max=20)

        solara.HTML(tag="div", unsafe_innerHTML=(
            f"<div style='color:{C_NAVY}; font-size:0.83em; margin:4px 0 -4px 0; font-weight:500'>"
            "🔵 Electricity escalation</div>"
        ))
        solara.SliderInt(f"+{elec_cagr_pct_a.value}%/yr",
                         value=elec_cagr_pct_a, min=0, max=15)

        solara.Markdown(
            "<small style='color:#888'>💡 Gas typically rises faster than "
            "electricity as grid decarbonises.</small>"
        )

        solara.Markdown("**Scenario Comparison**")
        solara.Checkbox(label="Compare two rate scenarios", value=comparison_mode)
        if comparison_mode.value:
            solara.Markdown("*Scenario B*")
            _preset_buttons(gas_cagr_pct_b, elec_cagr_pct_b, _apply_preset_b)

            solara.HTML(tag="div", unsafe_innerHTML=(
                f"<div style='color:{C_RED}; font-size:0.83em; margin:8px 0 -4px 0; font-weight:500'>"
                "🔴 Gas escalation (B)</div>"
            ))
            solara.SliderInt(f"+{gas_cagr_pct_b.value}%/yr",
                             value=gas_cagr_pct_b, min=0, max=20)

            solara.HTML(tag="div", unsafe_innerHTML=(
                f"<div style='color:{C_NAVY}; font-size:0.83em; margin:4px 0 -4px 0; font-weight:500'>"
                "🔵 Electricity escalation (B)</div>"
            ))
            solara.SliderInt(f"+{elec_cagr_pct_b.value}%/yr",
                             value=elec_cagr_pct_b, min=0, max=15)

            solara.Markdown(
                "<small style='color:#888'>Charts: solid = A, dashed = B</small>"
            )

        solara.Markdown("**Timeline**")
        solara.SliderInt("Years to model", value=years, min=5, max=30)


# ── Main Page ──────────────────────────────────────────────────────────────────

@solara.component
def Page():
    solara.Title("WhyWatt?")

    model, df = solara.use_memo(run_simulation, dependencies=[
        zip_code.value, climate_zone.value, num_bedrooms.value,
        square_footage.value, year_built.value, insulation_quality.value,
        furnace_afue.value, gas_wh_uef.value, hvac_has_cooling.value,
        hp_cop_heating.value, hp_seer_cooling.value, hpwh_uef.value,
        hvac_starting_state.value, hvac_swap_planned.value, hvac_swap_year.value,
        hvac_install_cost.value, hvac_rebate.value,
        hvac_furnace_age.value, hvac_ac_seer.value, hvac_ac_age.value,
        wh_starting_state.value, wh_swap_planned.value, wh_swap_year.value,
        wh_install_cost.value, wh_rebate.value,
        wh_gas_age.value, hw_daily_gallons.value, hw_gallons_user_override.value,
        dryer_starting_state.value, dryer_swap_planned.value, dryer_swap_year.value,
        dryer_install_cost.value, dryer_rebate.value,
        dryer_gas_therms_per_cycle.value, dryer_loads_per_week.value,
        dryer_hp_kwh_per_cycle.value,
        cooktop_starting_state.value, cooktop_swap_planned.value, cooktop_swap_year.value,
        cooktop_install_cost.value, cooktop_rebate.value,
        cooktop_gas_therms_per_meal.value, cooktop_meals_per_week.value,
        cooktop_induction_kwh_per_meal.value,
        ev_starting_state.value, ev_swap_planned.value, ev_swap_year.value,
        ev_install_cost.value, ev_rebate.value,
        ev_miles_per_year.value, ev_kwh_per_mile.value, ev_charging_efficiency.value,
        panel_upgrade_planned.value, panel_upgrade_year.value,
        panel_upgrade_cost.value, panel_upgrade_rebate.value,
        baseload_constant_before.value, baseload_constant_after.value,
        baseload_swap_planned.value, baseload_swap_year.value,
        baseload_install_cost.value, baseload_rebate.value,
        solar_planned.value, solar_install_year.value, solar_coverage_pct.value,
        solar_include_panels.value, solar_panels_cost.value,
        solar_include_battery.value, solar_battery_cost.value,
        solar_include_install.value, solar_install_cost_item.value,
        solar_rebate.value,
        gas_cagr_pct_a.value, elec_cagr_pct_a.value,
        comparison_mode.value,
        gas_cagr_pct_b.value, elec_cagr_pct_b.value,
        years.value, sim_start_year.value,
    ])

    n = years.value

    with solara.Column(margin=3, gap="10px"):

        # Scoped CSS: larger dropdown arrow only in chart header selectors
        solara.HTML(
            tag="div",
            unsafe_innerHTML=(
                "<style>"
                ".chart-header-sel .v-input__icon--append .v-icon"
                "{font-size:28px!important}"
                "</style>"
            ),
            style="display:none",
        )

        # ── Header ─────────────────────────────────────────────────────────────
        ww_svg = _read_svg(_WHYWATT_LOGO, height_px=72)
        with solara.Row(style=(
            "align-items:center; gap:20px; padding:10px 0;"
            " border-bottom:2px solid #E8EAF6; margin-bottom:4px"
        )):
            if ww_svg:
                solara.HTML(
                    tag="div",
                    unsafe_innerHTML=ww_svg,
                    style="height:72px; flex-shrink:0; display:flex; align-items:center",
                )
            else:
                solara.Markdown("# ⚡ WhyWatt?")
            with solara.Column(style="flex:1; justify-content:center"):
                HomeInfoBar()
            # Reset button — far right of header bar
            solara.Button(
                "↺ Reset to defaults",
                on_click=reset_to_defaults,
                style=(
                    "background:transparent; color:#78909C;"
                    " border:1.5px solid #C5CAE9;"
                    " border-radius:6px; padding:5px 12px;"
                    " font-size:0.80em; cursor:pointer;"
                    " white-space:nowrap; flex-shrink:0;"
                    " transition:all 0.15s;"
                ),
            )

        # ── Summary stats ───────────────────────────────────────────────────────
        SummaryStats(df, n, model)

        # ── Dual chart panes (selector in grey title bar inside each card) ──────
        with solara.Row(gap="8px", style="align-items:stretch"):
            with solara.Card(margin=0, elevation=1,
                             style="flex:1; min-width:300px; overflow:hidden"):
                with solara.Row(
                    classes=["chart-header-sel"],
                    style=(
                        "background-color:#F0F0F0; padding:6px 12px;"
                        " border-radius:4px 4px 0 0; margin:-16px -16px 8px -16px;"
                    ),
                ):
                    solara.Select("", value=chart_left, values=CHART_OPTIONS)
                ChartPane(chart_left.value, model, df, n)
            with solara.Card(margin=0, elevation=1,
                             style="flex:1; min-width:300px; overflow:hidden"):
                with solara.Row(
                    classes=["chart-header-sel"],
                    style=(
                        "background-color:#F0F0F0; padding:6px 12px;"
                        " border-radius:4px 4px 0 0; margin:-16px -16px 8px -16px;"
                    ),
                ):
                    solara.Select("", value=chart_right, values=CHART_OPTIONS)
                ChartPane(chart_right.value, model, df, n)

        # ── Legend ──────────────────────────────────────────────────────────────
        with solara.Row(gap="24px"):
            leg = (
                f"<span style='color:{C_BASE};font-weight:bold'>■ Do nothing (A)</span>"
                f"&nbsp;&nbsp;"
                f"<span style='color:{C_ELEC};font-weight:bold'>■ Your journey (A)</span>"
            )
            if comparison_mode.value:
                leg += (
                    f"&nbsp;&nbsp;"
                    f"<span style='color:{C_BASE};opacity:0.6;font-weight:bold'>┅ Do nothing (B)</span>"
                    f"&nbsp;&nbsp;"
                    f"<span style='color:{C_ELEC};opacity:0.6;font-weight:bold'>┅ Your journey (B)</span>"
                )
            solara.Markdown(leg)

        # ── Control panels ──────────────────────────────────────────────────────
        with solara.Row(gap="12px", style="align-items:flex-start; flex-wrap:wrap"):
            with solara.Column(style="flex:2; min-width:300px"):
                JourneyPlannerPanel()
            with solara.Column(style="flex:1; min-width:240px"):
                HomeProfilePanel()
                SolarBatteryPanel(model)
            with solara.Column(style="flex:1; min-width:220px"):
                EnergyPricesPanel()

        # ── Footer — ECHo branding ──────────────────────────────────────────────
        echo_svg      = _read_svg(_ECHO_LOGO,  height_px=36)
        echo_icon_svg = _read_svg(_ECHO_ICON, height_px=36)
        with solara.Row(
            style="margin-top:16px; padding:10px 12px;"
                  " border-top:2px solid #C5CAE9;"
                  " background:#E8EAF6; border-radius:8px;"
                  " align-items:center; gap:14px"
        ):
            if echo_svg:
                solara.HTML(tag="div", unsafe_innerHTML=echo_svg,
                            style="display:flex; align-items:center")
            elif echo_icon_svg:
                solara.HTML(tag="div", unsafe_innerHTML=echo_icon_svg,
                            style="display:flex; align-items:center")
            solara.Markdown(
                "<small style='color:#546E7A; font-size:0.82em'>"
                "WhyWatt? is supported by the "
                "<strong style='color:#50BDF8'>Electrification Collaboration</strong>"
                " — helping California communities make the switch.</small>"
            )
            solara.HTML(
                tag="div",
                unsafe_innerHTML=(
                    "<span style='margin-left:auto; background:#0D47A1; color:white;"
                    " border-radius:6px; padding:3px 10px; font-size:0.75em;"
                    " font-weight:700; white-space:nowrap'>WhyWatt? v2.0</span>"
                ),
                style="margin-left:auto",
            )
