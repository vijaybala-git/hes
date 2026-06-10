"""
WhyWatt? — Solara UI (Phase 3 / Objective 1 — Help System)
"""
import os
import json
from pathlib import Path
import solara
import numpy as np
import matplotlib
import matplotlib.ticker
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
matplotlib.use("Agg")
from matplotlib.figure import Figure
from model import HESModel
from home_config import HomeConfig, compute_baseload_kwh
from journey import CATEGORY_ORDER, CATEGORY_LABELS, CapExOnlySlot
from panel_assessor import PanelAssessor
from social_cost import SocialCostConfig
from help_utils import (HelpButton, ChartHelpButton, HelpPopupOverlay,
                        HelpDock, open_help)

# ── Asset paths ───────────────────────────────────────────────────────────────
_HERE         = os.path.dirname(os.path.abspath(__file__))
_ASSETS       = os.path.normpath(os.path.join(_HERE, "..", "docs", "assets"))
_WHYWATT_LOGO = os.path.join(_ASSETS, "whywatt_logo.svg")
_ECHO_LOGO    = os.path.join(_ASSETS, "echo_logo.svg")
_ECHO_ICON    = os.path.join(_ASSETS, "echo_icon.svg")

# Icon-only SVG extracted from whywatt_logo.svg paths (house + bar elements).
# ViewBox crops to the icon area (x 0-88, y 0-92); fills turned white so the
# icon renders cleanly on the .brand-mark gradient background.
_WHYWATT_ICON_SVG = (
    '<svg viewBox="0 0 88 92" xmlns="http://www.w3.org/2000/svg">'
    '<path d="M8 84 L8 44 L44 8 L80 44 L80 84 Z"'
    ' fill="rgba(255,255,255,0.18)" stroke="rgba(255,255,255,0.85)"'
    ' stroke-width="3.5" stroke-linejoin="round"/>'
    '<rect x="30.973" y="44.513" width="8" height="18" rx="4" fill="#fff"/>'
    '<rect x="49.895" y="47.27" width="8" height="13" rx="4" fill="#fff"/>'
    '<path d="M40.487 67 L40.487 72 C43.154 75.333 45.82 75.333 48.487 72'
    ' L48.487 67 Z" fill="#fff"/>'
    '</svg>'
)

# ── Phase 3 redesign design system (injected once via solara.Style in Page) ─────
_REDESIGN_CSS_PATH = os.path.join(_HERE, "styles_redesign.css")
try:
    with open(_REDESIGN_CSS_PATH, "r", encoding="utf-8") as _f:
        _REDESIGN_CSS = _f.read()
except OSError:
    _REDESIGN_CSS = ""

# ── v2 layout layer (cockpit, setup group + collapse, 2-row journey, split card) ─
_LAYOUT_V2_CSS_PATH = os.path.join(_HERE, "layout_v2.css")
try:
    with open(_LAYOUT_V2_CSS_PATH, "r", encoding="utf-8") as _f:
        _LAYOUT_V2_CSS = _f.read()
except OSError:
    _LAYOUT_V2_CSS = ""


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
# Rate model UI colors — distinct from journey Red/Blue
C_RATE_ELEC = "#0288D1"   # light blue — electricity rate
C_RATE_GAS  = "#E65100"   # deep orange — gas rate

# ── Chart design tokens (D6 — design system series colors + transparent bg) ───
_CC_J    = "#3B6FD4"   # journey series (design token)
_CC_B    = "#D2785F"   # baseline series (design token)
_CC_GRID = "#EBEDF1"
_CC_TICK = "#5A6273"
_CC_SOLAR = "#00897B"

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
    "Electric CAGR Projection",
    "Gas CAGR Projection",
    "ACC Rate Projection",
    "Electricity Rate Shape",
    "Journey Timeline",
    "Cost by Device",
    "Energy Use by Device",
    "Annual kWh by Device",
    "Annual Gas by Device",
]

# Reference codes shown in chart titles and headers — used in help files
CHART_CODES = {
    "Cumulative Energy Costs":        "JC.1",
    "Annual Cost by Year":            "JC.2",
    "Cost Breakdown by Category":     "JC.3",
    "Equipment Replacements (CapEx)": "JC.4",
    "Journey Timeline":               "JC.5",
    "Cost by Device":                 "EU.1",
    "Energy Use by Device":           "EU.2",
    "Annual kWh by Device":           "EU.3",
    "Annual Gas by Device":           "EU.4",
    "Electric CAGR Projection":       "R.1",
    "Gas CAGR Projection":            "R.2",
    "ACC Rate Projection":            "R.3",
    "Electricity Rate Shape":         "R.4",
}

# Per-slot color palette (consistent across EU.3 / EU.4 / cost charts)
_SLOT_COLORS = {
    "HVAC":                  "#1565C0",
    "Water Heater":          "#0288D1",
    "Dryer":                 "#D32F2F",
    "Cooktop":               "#F57C00",
    "EV Charger":            "#388E3C",
    "Lights and Appliances": "#78909C",
}

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
    "panel_amps":             200,
    # Electrical nameplate sizing (Phase 3 §2.5)
    "hvac_tonnage":           3.0,
    "ev_charger_amps":        32,
    "induction_amps":         40,
    "hpwh_amps":              15,
    "dryer_amps":             30,
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
    "wh_gas_age":              5,
    "hw_daily_gallons":        65,
    "gas_wh_tank_gallons":     50,
    "hpwh_tank_gallons":       65,
    "hpwh_ambient_location":   "conditioned",
    "wh_inlet_temp_f":         60,
    "wh_setpoint_f":           120,
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
    "elec_rate_model_a":      "cagr_flat",
    "elec_cagr_pct_a":        7,
    "acc_elec_cagr_a":        7,
    "gas_rate_model_a":       "cagr_flat",
    "gas_cagr_pct_a":         8,
    "acc_gas_cagr_a":         8,
    "comparison_mode":        False,
    "elec_rate_model_b":      "acc_shaped",
    "elec_cagr_pct_b":        7,
    "acc_elec_cagr_b":        7,
    "gas_rate_model_b":       "acc_seasonal",
    "gas_cagr_pct_b":         8,
    "acc_gas_cagr_b":         8,
    "years":                  20,
    "sim_start_year":         2025,
    # Social & Health cost of gas (Phase 3 §6)
    "social_climate_enabled": True,
    "social_climate_rate":    1.07,
    "social_health_enabled":  True,
    "social_health_rate":     1.23,
    # Charts
    "chart_left":             "Cumulative Energy Costs",
    "chart_right":            "Cost Breakdown by Category",
    "device_chart_home":      "journey",
    "acc_shape_year":         1,
    "detail_open":            None,
}

# ── Reactive state (initialised from _DEFAULTS) ────────────────────────────────

# Home profile
zip_code           = solara.reactive("95112")
climate_zone       = solara.reactive("CZ12")
num_bedrooms       = solara.reactive(3)
square_footage     = solara.reactive(1800)
year_built         = solara.reactive(1985)
insulation_quality = solara.reactive("average")
panel_amps         = solara.reactive(200)        # Phase 3 §5 — service size 100/150/200

# Electrical nameplate sizing (Phase 3 §2.5) — drive panel assessment, inert for energy
hvac_tonnage    = solara.reactive(3.0)   # slider 2.0–5.0; amps = tonnage × 10
ev_charger_amps = solara.reactive(32)    # selector 32 / 48
induction_amps  = solara.reactive(40)    # editable input
hpwh_amps       = solara.reactive(15)    # editable input
dryer_amps      = solara.reactive(30)    # editable input

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
gas_wh_tank_gallons     = solara.reactive(50)    # gal
hpwh_tank_gallons       = solara.reactive(65)    # gal
hpwh_ambient_location   = solara.reactive("conditioned")  # "conditioned" | "unconditioned"
wh_inlet_temp_f         = solara.reactive(60)    # °F — annual avg cold-water inlet
wh_setpoint_f           = solara.reactive(120)   # °F — tank setpoint

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

# ACC Rate Shape chart — year selector (chart-only, NOT a sim dep)
acc_shape_year = solara.reactive(1)

# Pricing & timeline
elec_rate_model_a = solara.reactive("cagr_flat")   # "cagr_flat" | "acc_shaped"
elec_cagr_pct_a   = solara.reactive(7)
acc_elec_cagr_a   = solara.reactive(7)            # base escalation used when acc_shaped
gas_rate_model_a  = solara.reactive("cagr_flat")   # "cagr_flat" | "acc_seasonal"
gas_cagr_pct_a    = solara.reactive(8)
acc_gas_cagr_a    = solara.reactive(8)             # base escalation used when acc_seasonal
comparison_mode   = solara.reactive(False)
elec_rate_model_b = solara.reactive("acc_shaped")
elec_cagr_pct_b   = solara.reactive(7)
acc_elec_cagr_b   = solara.reactive(7)
gas_rate_model_b  = solara.reactive("acc_seasonal")
gas_cagr_pct_b    = solara.reactive(8)
acc_gas_cagr_b    = solara.reactive(8)
years             = solara.reactive(20)
sim_start_year   = solara.reactive(2025)

# Social & Health cost of gas (Phase 3 §6)
social_climate_enabled = solara.reactive(True)
social_climate_rate    = solara.reactive(1.07)   # $/therm — EPA 2023 + 2% leakage
social_health_enabled  = solara.reactive(True)
social_health_rate     = solara.reactive(1.23)   # $/therm — CPUC D.24-07-015 / E3 2022

# Chart selection
chart_left  = solara.reactive("Cumulative Energy Costs")
chart_right = solara.reactive("Cost Breakdown by Category")

# Detail view state (§25)
detail_open = solara.reactive(None)   # None | "hvac" | "water_heater" | "ev" | "cooktop" | "dryer" | "home" | "solar" | "rates"

# v2 §D — "Setup your home" collapse state (one bool per domain card)
setup_collapsed = solara.reactive({"home": False, "energy": False, "social": False})

def _toggle_setup(key: str):
    """Flip the collapsed flag for one setup card (immutable dict update)."""
    cur = dict(setup_collapsed.value)
    cur[key] = not cur.get(key, False)
    setup_collapsed.set(cur)

def _set_all_setup(collapsed: bool):
    """Collapse or expand all three setup cards at once."""
    setup_collapsed.set({"home": collapsed, "energy": collapsed, "social": collapsed})

# ── Reset function ───────────────────────────────────────────────────────────
def reset_to_defaults():
    """Reset every reactive to its _DEFAULTS value in one shot."""
    zip_code.set(_DEFAULTS["zip_code"])
    climate_zone.set(_DEFAULTS["climate_zone"])
    num_bedrooms.set(_DEFAULTS["num_bedrooms"])
    square_footage.set(_DEFAULTS["square_footage"])
    year_built.set(_DEFAULTS["year_built"])
    insulation_quality.set(_DEFAULTS["insulation_quality"])
    panel_amps.set(_DEFAULTS["panel_amps"])
    hvac_tonnage.set(_DEFAULTS["hvac_tonnage"])
    ev_charger_amps.set(_DEFAULTS["ev_charger_amps"])
    induction_amps.set(_DEFAULTS["induction_amps"])
    hpwh_amps.set(_DEFAULTS["hpwh_amps"])
    dryer_amps.set(_DEFAULTS["dryer_amps"])
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
    gas_wh_tank_gallons.set(_DEFAULTS["gas_wh_tank_gallons"])
    hpwh_tank_gallons.set(_DEFAULTS["hpwh_tank_gallons"])
    hpwh_ambient_location.set(_DEFAULTS["hpwh_ambient_location"])
    wh_inlet_temp_f.set(_DEFAULTS["wh_inlet_temp_f"])
    wh_setpoint_f.set(_DEFAULTS["wh_setpoint_f"])
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
    elec_rate_model_a.set(_DEFAULTS["elec_rate_model_a"])
    elec_cagr_pct_a.set(_DEFAULTS["elec_cagr_pct_a"])
    acc_elec_cagr_a.set(_DEFAULTS["acc_elec_cagr_a"])
    gas_rate_model_a.set(_DEFAULTS["gas_rate_model_a"])
    gas_cagr_pct_a.set(_DEFAULTS["gas_cagr_pct_a"])
    acc_gas_cagr_a.set(_DEFAULTS["acc_gas_cagr_a"])
    comparison_mode.set(_DEFAULTS["comparison_mode"])
    elec_rate_model_b.set(_DEFAULTS["elec_rate_model_b"])
    elec_cagr_pct_b.set(_DEFAULTS["elec_cagr_pct_b"])
    acc_elec_cagr_b.set(_DEFAULTS["acc_elec_cagr_b"])
    gas_rate_model_b.set(_DEFAULTS["gas_rate_model_b"])
    gas_cagr_pct_b.set(_DEFAULTS["gas_cagr_pct_b"])
    acc_gas_cagr_b.set(_DEFAULTS["acc_gas_cagr_b"])
    years.set(_DEFAULTS["years"])
    sim_start_year.set(_DEFAULTS["sim_start_year"])
    social_climate_enabled.set(_DEFAULTS["social_climate_enabled"])
    social_climate_rate.set(_DEFAULTS["social_climate_rate"])
    social_health_enabled.set(_DEFAULTS["social_health_enabled"])
    social_health_rate.set(_DEFAULTS["social_health_rate"])
    chart_left.set(_DEFAULTS["chart_left"])
    chart_right.set(_DEFAULTS["chart_right"])
    device_chart_home.set(_DEFAULTS["device_chart_home"])
    acc_shape_year.set(_DEFAULTS["acc_shape_year"])
    detail_open.set(_DEFAULTS["detail_open"])
    _set_all_setup(False)


# ── Labels / option lists ─────────────────────────────────────────────────────
_CZ_OPTIONS = ["CZ3", "CZ4", "CZ5", "CZ12", "CZ13", "CZ16"]
_BR_OPTIONS = [1, 2, 3, 4, 5]



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
            "circuit_volts": 240, "circuit_amps": 20, "continuous": False,
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
                "circuit_volts": 240,
                "circuit_amps": int(hvac_tonnage.value * 10),
                "continuous": True,
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
                "tank_gallons": gas_wh_tank_gallons.value,
                "setpoint_f": wh_setpoint_f.value,
                "inlet_temp_f": wh_inlet_temp_f.value,
            }],
            "electric_device": {
                "class": "HeatPumpWaterHeater",
                "uef": hpwh_uef.value,
                "lifespan": 15, "installation_cost": 2500,
                "daily_gallons_override": hw_override,
                "tank_gallons": hpwh_tank_gallons.value,
                "ambient_location": hpwh_ambient_location.value,
                "setpoint_f": wh_setpoint_f.value,
                "inlet_temp_f": wh_inlet_temp_f.value,
                "circuit_volts": 240, "circuit_amps": hpwh_amps.value, "continuous": False,
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
                "circuit_volts": 240, "circuit_amps": dryer_amps.value, "continuous": False,
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
                "circuit_volts": 240, "circuit_amps": induction_amps.value, "continuous": False,
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
                "circuit_volts": 240, "circuit_amps": ev_charger_amps.value, "continuous": True,
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
        panel_amps=panel_amps.value,
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
        # Rate model selections (§23) — used once ACCRateLoader is wired in model.py
        elec_rate_model_a=elec_rate_model_a.value,
        gas_rate_model_a=gas_rate_model_a.value,
        elec_rate_model_b=elec_rate_model_b.value,
        gas_rate_model_b=gas_rate_model_b.value,
        acc_elec_cagr_a=acc_elec_cagr_a.value / 100.0,
        acc_gas_cagr_a=acc_gas_cagr_a.value   / 100.0,
        acc_elec_cagr_b=acc_elec_cagr_b.value / 100.0,
        acc_gas_cagr_b=acc_gas_cagr_b.value   / 100.0,
        social_cost_config=SocialCostConfig(
            climate_enabled=social_climate_enabled.value,
            climate_rate=social_climate_rate.value,
            health_enabled=social_health_enabled.value,
            health_rate=social_health_rate.value,
        ),
    )
    m.run_all()
    df = m.datacollector.get_model_vars_dataframe()
    return m, df


# ── Chart helpers ─────────────────────────────────────────────────────────────

def _money(v, _):
    return f"${v:,.0f}"

def _style(ax):
    ax.set_facecolor("none")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(_CC_GRID)
    ax.spines["bottom"].set_color(_CC_GRID)
    ax.grid(True, axis="y", color=_CC_GRID, linewidth=0.7, zorder=0)
    ax.tick_params(colors=_CC_TICK, labelsize=8)
    ax.yaxis.label.set_color(_CC_TICK)
    ax.xaxis.label.set_color(_CC_TICK)

def _new_fig(wide=False):
    w = 12 if wide else 6
    fig = Figure(figsize=(w, 3.35), dpi=100)
    fig.patch.set_alpha(0)
    return fig


# Chart 1 — Cumulative Energy Costs
def make_cumulative_opex(df, model, n):
    fig = _new_fig()
    ax  = fig.add_subplot(111)
    x = np.arange(1, n + 1)
    b = df["Baseline Cum Cost"].values
    lbl_a = " (A)" if model.comparison_mode else ""

    has_solar = solar_planned.value and "Solar Saving" in df.columns

    if has_solar:
        solar_savings_cum = np.cumsum(df["Solar Saving"].values)
        e_no_solar = df["Journey Cum Cost"].values + solar_savings_cum
        e_solar    = df["Journey Cum Cost"].values
        ax.plot(x, b,          color=_CC_B,     lw=2.5, label=f"Do nothing{lbl_a}")
        ax.plot(x, e_no_solar, color=_CC_J,     lw=2.0, linestyle="--",
                label=f"Your journey{lbl_a}")
        ax.plot(x, e_solar,    color=_CC_SOLAR, lw=2.5,
                label=f"Your journey + Solar{lbl_a}")
        ax.fill_between(x, b, e_solar,    where=(b >= e_solar),
                        color=_CC_SOLAR, alpha=0.10, label="Journey + Solar saves")
        ax.fill_between(x, e_solar, e_no_solar, where=(e_no_solar > e_solar),
                        color=_CC_J,    alpha=0.07, label="Solar adds")
    else:
        e = df["Journey Cum Cost"].values
        ax.plot(x, b, color=_CC_B, lw=2.5, label=f"Do nothing{lbl_a}")
        ax.plot(x, e, color=_CC_J, lw=2.5, label=f"Your journey{lbl_a}")
        ax.fill_between(x, b, e, where=(b >= e), color=_CC_J, alpha=0.12, label="Journey saves")
        ax.fill_between(x, b, e, where=(b <  e), color=_CC_B, alpha=0.12, label="Gas saves")

    if model.comparison_mode:
        bB = df["Baseline Cum Cost B"].values
        eB = df["Journey Cum Cost B"].values
        ax.plot(x, bB, color=_CC_B, lw=2.0, linestyle="--", label="Do nothing (B)")
        ax.plot(x, eB, color=_CC_J, lw=2.0, linestyle="--", label="Your journey (B)")
    cfg = getattr(model, "social_cost_config", None)
    if (cfg is not None and cfg.total_rate > 0
            and "Journey Social Climate" in df.columns):
        j_social = np.cumsum(df["Journey Social Climate"].values
                             + df["Journey Social Health"].values)
        b_social = np.cumsum(df["Baseline Social Climate"].values
                             + df["Baseline Social Health"].values)
        ax.plot(x, b + b_social, color=_CC_B, lw=1.5, linestyle=":",
                alpha=0.9, label="Do nothing + social")
        ax.plot(x, df["Journey Cum Cost"].values + j_social, color=_CC_J, lw=1.5,
                linestyle=":", alpha=0.9, label="Your journey + social")

    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(_money))
    ax.set_xlabel("Year")
    ax.set_ylabel("Cumulative Energy Cost")
    ax.legend(fontsize=8, framealpha=0.6)
    ax.set_title("JC.1 · Cumulative Energy Costs", fontsize=10, fontweight="bold", color=_CC_TICK)
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
        ax.bar(x - 1.5 * w, df["Baseline Annual Cost"].values,  w, color=_CC_B, label="Do nothing (A)",   zorder=3)
        ax.bar(x - 0.5 * w, df["Journey Annual Cost"].values,   w, color=_CC_J, label="Your journey (A)", zorder=3)
        ax.bar(x + 0.5 * w, df["Baseline Annual Cost B"].values, w, color=_CC_B, alpha=0.55,
               label="Do nothing (B)", zorder=3, hatch="//")
        ax.bar(x + 1.5 * w, df["Journey Annual Cost B"].values,  w, color=_CC_J, alpha=0.55,
               label="Your journey (B)", zorder=3, hatch="//")
    else:
        w = 0.35
        b_ann = df["Baseline Annual Cost"].values
        j_ann = df["Journey Annual Cost"].values
        ax.bar(x - w / 2, b_ann, w, color=_CC_B, label="Do nothing",   zorder=3)
        ax.bar(x + w / 2, j_ann, w, color=_CC_J, label="Your journey", zorder=3)
        # Social cost — stacked on top when enabled
        cfg = getattr(model, "social_cost_config", None)
        if (cfg is not None and cfg.total_rate > 0
                and "Baseline Social Climate" in df.columns):
            b_soc = (df["Baseline Social Climate"].values
                     + df["Baseline Social Health"].values)
            j_soc = (df["Journey Social Climate"].values
                     + df["Journey Social Health"].values)
            ax.bar(x - w / 2, b_soc, w, bottom=b_ann,
                   color="#FB8C00", alpha=0.85, label="Do nothing — social", zorder=3)
            ax.bar(x + w / 2, j_soc, w, bottom=j_ann,
                   color="#4CAF50", alpha=0.85, label="Your journey — social", zorder=3)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(_money))
    ax.set_xlabel("Year")
    ax.set_ylabel("Annual Energy Cost")
    ax.legend(fontsize=8)
    ax.set_title("JC.2 · Annual Cost by Year", fontsize=10, fontweight="bold", color=_CC_TICK)
    _style(ax)
    fig.tight_layout(pad=1.0)
    return fig


# Chart 3 — Cost Breakdown by Category (stacked cumulative, single pane with toggle)
def make_cost_breakdown(df, model, n, home="journey"):
    """Single-pane cost breakdown; home = 'journey' | 'baseline'."""
    fig = _new_fig(wide=False)
    ax  = fig.add_subplot(111)

    if home == "journey":
        hobj        = model.journey_home
        title_sub   = "Your Journey"
        palette_idx = 1
    else:
        hobj        = model.baseline_home
        title_sub   = "Do Nothing"
        palette_idx = 0

    x      = np.arange(1, n + 1)
    bottom = np.zeros(n)
    for cat in CATEGORY_ORDER:
        annual = hobj.cost_history_by_category.get(cat, [])
        if not annual:
            continue
        cum   = np.cumsum(annual[:n])
        color = CATEGORY_COLORS[cat][palette_idx]
        ax.fill_between(x, bottom, bottom + cum,
                        color=color, alpha=0.85, label=CATEGORY_LABELS[cat])
        ax.plot(x, bottom + cum, color=color, lw=0.5, alpha=0.5)
        bottom = bottom + cum

    # Social & health cost layers — stacked above market categories
    cfg    = getattr(model, "social_cost_config", None)
    therms = np.array(hobj.gas_therms_history[:n], dtype=float)
    if cfg is not None and len(therms):
        if cfg.climate_eff > 0:
            cum = np.cumsum(therms * cfg.climate_eff)
            ax.fill_between(x, bottom, bottom + cum, color="#FB8C00",
                            alpha=0.80, label="Climate cost")
            bottom = bottom + cum
        if cfg.health_eff > 0:
            cum = np.cumsum(therms * cfg.health_eff)
            ax.fill_between(x, bottom, bottom + cum, color="#C62828",
                            alpha=0.80, label="Health cost")
            bottom = bottom + cum

    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(_money))
    ax.set_xlabel("Year")
    ax.set_ylabel("Cumulative Cost")
    ax.set_title(f"JC.3 · Cost by Category — {title_sub}",
                 fontsize=10, fontweight="bold", color=_CC_TICK)
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
    ax.bar(yrs - w / 2, b_vals, w, color=_CC_B, label="Do nothing",   zorder=3)
    ax.bar(yrs + w / 2, e_vals, w, color=_CC_J, label="Your journey", zorder=3)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(_money))
    ax.set_xlabel("Year")
    ax.set_ylabel("Replacement Cost")
    ax.legend(fontsize=8)
    title = "Equipment Replacements (CapEx)"
    if model.comparison_mode:
        title += " — Scenario A"
    ax.set_title(title, fontsize=10, fontweight="bold", color=_CC_TICK)
    _style(ax)
    fig.tight_layout(pad=1.0)
    return fig


# Chart 5 — Electric CAGR Projection
def _elec_rate_label(model_str: str, cagr_pct: int, suffix: str = "") -> str:
    if model_str == "cagr_flat":
        return f"Elec +{cagr_pct}%/yr{suffix}"
    return f"Electricity ACC-shaped{suffix}"

def _gas_rate_label(model_str: str, cagr_pct: int, suffix: str = "") -> str:
    if model_str == "cagr_flat":
        return f"Gas +{cagr_pct}%/yr{suffix}"
    return f"Gas ACC seasonal{suffix}"


def make_elec_price(df, model, n):
    fig = _new_fig()
    ax  = fig.add_subplot(111)
    x = np.arange(1, n + 1)
    lbl_a = _elec_rate_label(model.elec_rate_model_a, elec_cagr_pct_a.value)
    ax.plot(x, df["Elec Rate"].values, color=_CC_J, lw=2.5, label=lbl_a)
    if model.comparison_mode:
        lbl_b = _elec_rate_label(model.elec_rate_model_b, elec_cagr_pct_b.value, " (B)")
        ax.plot(x, df["Elec Rate B"].values, color=_CC_J, lw=2.0, linestyle="--", label=lbl_b)
        ax.legend(fontsize=8)
    ax.set_xlabel("Year")
    ax.set_ylabel("Avg Electricity Price  ($/kWh)")
    ax.set_title("Electric CAGR Projection", fontsize=10, fontweight="bold", color=_CC_TICK)
    _style(ax)
    fig.tight_layout(pad=1.0)
    return fig


# Chart 6 — Gas CAGR Projection
def make_gas_price(df, model, n):
    fig = _new_fig()
    ax  = fig.add_subplot(111)
    x = np.arange(1, n + 1)
    lbl_a = _gas_rate_label(model.gas_rate_model_a, gas_cagr_pct_a.value)
    ax.plot(x, df["Gas Rate"].values, color="#EF6C00", lw=2.5, label=lbl_a)
    if model.comparison_mode:
        lbl_b = _gas_rate_label(model.gas_rate_model_b, gas_cagr_pct_b.value, " (B)")
        ax.plot(x, df["Gas Rate B"].values, color="#EF6C00", lw=2.0, linestyle="--", label=lbl_b)
        ax.legend(fontsize=8)
    ax.set_xlabel("Year")
    ax.set_ylabel("Avg Gas Price  ($/therm)")
    ax.set_title("Gas CAGR Projection", fontsize=10, fontweight="bold", color=_CC_TICK)
    _style(ax)
    fig.tight_layout(pad=1.0)
    return fig


# Chart 7b — ACC Rate Projection (§24.3)
def _load_acc_shapes():
    """Return (elec_shape 12×24, gas_monthly_shape 12) arrays."""
    with open(_ACC_SHAPE_PATH) as f:
        ed = json.load(f)
    with open(_ACC_GAS_SHAPE_PATH) as f:
        gd = json.load(f)
    return np.array(ed["shape_24h_by_month"], dtype=float), np.array(gd["monthly_shape"], dtype=float)


def _plot_rate_band(ax, cal_x, base, lo_factor, hi_factor, lo_lbl, hi_lbl, color):
    """Plot a CAGR base line + shaded seasonal band between lo_factor and hi_factor."""
    ax.fill_between(cal_x, base * lo_factor, base * hi_factor,
                    alpha=0.18, color=color)
    ax.plot(cal_x, base,               color=color, lw=2.5, label="Annual avg")
    ax.plot(cal_x, base * hi_factor,   color=color, lw=1.2, linestyle="--", label=hi_lbl)
    ax.plot(cal_x, base * lo_factor,   color=color, lw=1.2, linestyle=":",  label=lo_lbl)


def make_rate_trajectory(df, model, n):
    fig = Figure(figsize=(7, 5), dpi=100)
    fig.patch.set_facecolor("#F9F9F9")
    ax_elec = fig.add_subplot(211)
    ax_gas  = fig.add_subplot(212)
    x     = np.arange(1, n + 1)
    cal_x = model.sim_start_year + x - 1

    elec_base = df["Elec Rate"].values   # CAGR annual mean $/kWh
    gas_base  = df["Gas Rate"].values    # CAGR annual mean $/therm

    # ── Electric subplot ──────────────────────────────────────────────────────
    if model.elec_rate_model_a == "acc_shaped":
        elec_shape, _ = _load_acc_shapes()
        flat = elec_shape.flatten()
        # p25 = typical cheap off-peak hour; p90 = peak evening hour
        p25 = float(np.percentile(flat, 25))
        p90 = float(np.percentile(flat, 90))
        _plot_rate_band(ax_elec, cal_x, elec_base, p25, p90,
                        f"Off-peak (p25 = {p25:.2f}×)",
                        f"Peak evening (p90 = {p90:.2f}×)",
                        C_RATE_ELEC)
        ax_elec.text(0.01, 0.04,
                     "Shaded band = off-peak to peak-hour rate range (ACC hourly shape)",
                     transform=ax_elec.transAxes, fontsize=6.5, color="#9E9E9E")
    else:
        lbl_ea = _elec_rate_label(model.elec_rate_model_a, elec_cagr_pct_a.value, " (A)")
        ax_elec.plot(cal_x, elec_base, color=C_RATE_ELEC, lw=2.5, label=lbl_ea)

    if model.comparison_mode and "Elec Rate B" in df.columns:
        lbl_eb = _elec_rate_label(model.elec_rate_model_b, elec_cagr_pct_b.value, " (B)")
        ax_elec.plot(cal_x, df["Elec Rate B"].values,
                     color=C_RATE_ELEC, lw=2.0, linestyle="--", label=lbl_eb)

    ax_elec.legend(fontsize=7)
    ax_elec.yaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda v, _: f"${v:.3f}"))
    ax_elec.set_ylabel("$/kWh")
    ax_elec.set_title("ACC Rate Projection", fontsize=10, fontweight="bold")
    _style(ax_elec)

    # ── Gas subplot ───────────────────────────────────────────────────────────
    if model.gas_rate_model_a == "acc_seasonal":
        _, gas_shape = _load_acc_shapes()
        winter_factor = float(np.max(gas_shape))   # ~1.20 (Jan/Dec)
        summer_factor = float(np.min(gas_shape))   # ~0.85 (Apr–Oct)
        _plot_rate_band(ax_gas, cal_x, gas_base, summer_factor, winter_factor,
                        f"Summer (min {summer_factor:.2f}×)",
                        f"Winter (max {winter_factor:.2f}×)",
                        C_RATE_GAS)
        ax_gas.text(0.01, 0.04,
                    "Shaded band = summer low to winter peak (ACC seasonal gas shape)",
                    transform=ax_gas.transAxes, fontsize=6.5, color="#9E9E9E")
    else:
        lbl_ga = _gas_rate_label(model.gas_rate_model_a, gas_cagr_pct_a.value, " (A)")
        ax_gas.plot(cal_x, gas_base, color=C_RATE_GAS, lw=2.5, label=lbl_ga)

    if model.comparison_mode and "Gas Rate B" in df.columns:
        lbl_gb = _gas_rate_label(model.gas_rate_model_b, gas_cagr_pct_b.value, " (B)")
        ax_gas.plot(cal_x, df["Gas Rate B"].values,
                    color=C_RATE_GAS, lw=2.0, linestyle="--", label=lbl_gb)

    ax_gas.legend(fontsize=7)
    ax_gas.yaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda v, _: f"${v:.2f}"))
    ax_gas.set_ylabel("$/therm")
    ax_gas.set_xlabel("Year")
    _style(ax_gas)

    fig.tight_layout(pad=1.2)
    return fig


# Chart 7c — Electricity Rate Shape heatmap (§24.2)
_ACC_SHAPE_PATH = (
    Path(__file__).parent.parent / "data" / "rates" / "acc_electric_shape_pge_2024.json"
)
_ACC_GAS_SHAPE_PATH = (
    Path(__file__).parent.parent / "data" / "rates" / "acc_gas_shape_pge_2024.json"
)

def make_acc_rate_shape(df, model, n):
    uses_acc = (
        model.elec_rate_model_a == "acc_shaped"
        or (model.comparison_mode and model.elec_rate_model_b == "acc_shaped")
    )
    if not uses_acc:
        fig = _new_fig(wide=True)
        ax  = fig.add_subplot(111)
        ax.text(0.5, 0.5,
                "Select ACC-Shaped electricity\nto see the hourly rate shape",
                ha="center", va="center", fontsize=11, color="#9E9E9E",
                transform=ax.transAxes)
        ax.set_axis_off()
        fig.tight_layout()
        return fig

    with open(_ACC_SHAPE_PATH) as f:
        shape_data = json.load(f)
    shape = np.array(shape_data["shape_24h_by_month"], dtype=float)  # (12, 24)

    fig = Figure(figsize=(10, 4), dpi=100)
    fig.patch.set_facecolor("#F9F9F9")
    ax  = fig.add_subplot(111)

    im = ax.pcolormesh(
        np.arange(25),
        np.arange(13),
        shape,
        cmap="RdYlBu_r",
        vmin=0.5, vmax=1.8,
        shading="flat",
    )
    fig.colorbar(im, ax=ax, label="Rate shape factor\n(1.0 = monthly average)")

    ax.set_xticks(np.arange(24) + 0.5)
    ax.set_xticklabels(
        ["12a","1","2","3","4","5","6","7","8","9","10","11",
         "12p","1","2","3","4","5","6","7","8","9","10","11"],
        fontsize=7,
    )
    ax.set_yticks(np.arange(12) + 0.5)
    ax.set_yticklabels(
        ["Jan","Feb","Mar","Apr","May","Jun",
         "Jul","Aug","Sep","Oct","Nov","Dec"],
        fontsize=8,
    )
    ax.set_xlabel("Hour of day")
    ax.set_ylabel("Month")
    ax.set_title(
        f"ACC Electric Rate Shape — PG&E Residential  ({model.sim_start_year} reference)",
        fontsize=10, fontweight="bold",
    )
    ax.text(0.01, -0.18,
            "Source: 2024 CPUC ACC Model (E3), CZ12. Shows avoided cost per hour — "
            "not retail TOU pricing. Winter overnight elevated by heating-season grid capacity.",
            transform=ax.transAxes, fontsize=7, color="#9E9E9E")
    _style(ax)
    fig.tight_layout(pad=1.2)
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
            ax.plot([1, n], [y, y], color=_CC_J, lw=3, solid_capstyle="round", zorder=3)
            ax.text(n + 0.4, y, "✓ Done", va="center", fontsize=8, color=_CC_J)

        elif state == "none":
            if sw is not None and sw <= n:
                ax.plot([sw, n], [y, y], color=_CC_J, lw=3, solid_capstyle="round", zorder=3)
                ax.plot(sw, y, "o", color=_CC_J, ms=8, zorder=5)
                ax.annotate(f"+${net:,.0f}", xy=(sw, y),
                            xytext=(sw + 0.4, y + 0.3), fontsize=7, color=_CC_J, zorder=5)
            else:
                ax.plot([1, n], [y, y], color=_CC_GRID, lw=1.5, linestyle=":", zorder=2)
                ax.text(n + 0.4, y, "Not adding", va="center", fontsize=7, color=_CC_TICK)

        else:  # gas
            if sw is not None and sw <= n:
                ax.plot([1, sw], [y, y], color=_CC_B, lw=2.5, linestyle="--", zorder=3)
                ax.plot([sw, n], [y, y], color=_CC_J, lw=2.5, solid_capstyle="round", zorder=3)
                ax.plot(sw, y, "o", color=_CC_J, ms=8, zorder=5)
                ax.annotate(f"${net:,.0f}", xy=(sw, y),
                            xytext=(sw + 0.4, y + 0.3), fontsize=7, color=_CC_TICK, zorder=5)
            else:
                ax.plot([1, n], [y, y], color=_CC_B, lw=2.5, linestyle="--", zorder=3)

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
    ax.set_title("Journey Timeline — Swap Schedule", fontsize=10, fontweight="bold", color=_CC_TICK)
    handles = [
        Line2D([0], [0], color=_CC_B, lw=2, linestyle="--", label="Gas device running"),
        Line2D([0], [0], color=_CC_J, lw=2, label="Electric device running"),
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


# EU.3 — Annual kWh by Device (stacked bar, single pane, toggle)
def make_annual_kwh(df, model, n, home="journey"):
    """EU.3 · Actual electricity consumption per device per year — stacked bars."""
    hobj      = model.journey_home if home == "journey" else model.baseline_home
    title_sub = "Your Journey" if home == "journey" else "Do Nothing"

    fig = _new_fig(wide=False)
    ax  = fig.add_subplot(111)
    x   = np.arange(1, n + 1)

    slot_names = list(hobj.consumption_history_by_slot.keys())
    bottom = np.zeros(n)
    for sname in slot_names:
        raw   = np.array(hobj.consumption_history_by_slot.get(sname, [0]*n)[:n], dtype=float)
        fuels = hobj.fuel_history_by_slot.get(sname, ["electricity"]*n)[:n]
        kwh   = np.where(np.array(fuels) == "electricity", raw, 0.0)
        if kwh.sum() == 0:
            continue
        color = _SLOT_COLORS.get(sname, "#90A4AE")
        ax.bar(x, kwh, bottom=bottom, label=sname, color=color, alpha=0.82, width=0.7)
        bottom += kwh

    ax.yaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_xlabel("Year")
    ax.set_ylabel("kWh / year")
    ax.set_title(f"EU.3 · Annual kWh — {title_sub}",
                 fontsize=10, fontweight="bold", color=_CC_TICK)
    ax.legend(fontsize=7, framealpha=0.8, loc="upper left")
    _style(ax)
    fig.tight_layout(pad=1.0)
    return fig


# EU.4 — Annual Gas Consumption by Device (stacked bar, single pane, toggle)
def make_annual_gas(df, model, n, home="journey"):
    """EU.4 · Actual gas consumption per device per year — stacked bars (therms)."""
    hobj      = model.journey_home if home == "journey" else model.baseline_home
    title_sub = "Your Journey" if home == "journey" else "Do Nothing"

    fig = _new_fig(wide=False)
    ax  = fig.add_subplot(111)
    x   = np.arange(1, n + 1)

    slot_names = list(hobj.consumption_history_by_slot.keys())
    bottom = np.zeros(n)
    has_any = False
    for sname in slot_names:
        raw   = np.array(hobj.consumption_history_by_slot.get(sname, [0]*n)[:n], dtype=float)
        fuels = hobj.fuel_history_by_slot.get(sname, ["electricity"]*n)[:n]
        therms = np.where(np.array(fuels) == "gas", raw, 0.0)
        if therms.sum() == 0:
            continue
        has_any = True
        color = _SLOT_COLORS.get(sname, "#90A4AE")
        ax.bar(x, therms, bottom=bottom, label=sname, color=color, alpha=0.82, width=0.7)
        bottom += therms

    if not has_any:
        ax.text(0.5, 0.5, "No gas consumption\nin this scenario",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=11, color=_CC_TICK, style="italic")

    ax.yaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_xlabel("Year")
    ax.set_ylabel("Therms / year")
    ax.set_title(f"EU.4 · Annual Gas — {title_sub}",
                 fontsize=10, fontweight="bold", color=_CC_TICK)
    if has_any:
        ax.legend(fontsize=7, framealpha=0.8, loc="upper right")
    _style(ax)
    fig.tight_layout(pad=1.0)
    return fig


CHART_FNS = {
    "Cumulative Energy Costs":        make_cumulative_opex,
    "Annual Cost by Year":            make_annual_cost,
    "Cost Breakdown by Category":     make_cost_breakdown,
    "Equipment Replacements (CapEx)": make_capex,
    "Electric CAGR Projection":        make_elec_price,
    "Gas CAGR Projection":                make_gas_price,
    "ACC Rate Projection":                make_rate_trajectory,
    "Electricity Rate Shape":         make_acc_rate_shape,
    "Journey Timeline":               make_journey_timeline,
    "Annual kWh by Device":           make_annual_kwh,
    "Annual Gas by Device":           make_annual_gas,
}


# ── Sub-components ─────────────────────────────────────────────────────────────

_DEVICE_CHART_NAMES = {"Cost by Device", "Energy Use by Device"}
_TOGGLE_CHART_NAMES = _DEVICE_CHART_NAMES | {
    "Cost Breakdown by Category",
    "Annual kWh by Device",
    "Annual Gas by Device",
}


def _toggle_buttons(active_rv):
    """Render 'Your journey' / 'Do nothing' toggle row using device_chart_home reactive."""
    home = active_rv.value
    with solara.Row(gap="6px", style="margin-bottom:4px"):
        for val, label in [("journey", "Your journey"), ("baseline", "Do nothing")]:
            is_active = home == val
            solara.Button(
                label,
                on_click=lambda v=val: active_rv.set(v),
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


@solara.component
def ChartPane(chart_name, model, df, n):
    if chart_name in _DEVICE_CHART_NAMES:
        chart_type = "device_cost" if chart_name == "Cost by Device" else "device_consumption"
        home = device_chart_home.value
        with solara.Column(gap="4px"):
            _toggle_buttons(device_chart_home)
            fig = render_device_chart(model, home=home, chart_type=chart_type)
            solara.FigureMatplotlib(fig)
    elif chart_name == "Cost Breakdown by Category":
        home = device_chart_home.value
        with solara.Column(gap="4px"):
            _toggle_buttons(device_chart_home)
            fig = make_cost_breakdown(df, model, n, home=home)
            solara.FigureMatplotlib(fig)
    elif chart_name == "Annual kWh by Device":
        home = device_chart_home.value
        with solara.Column(gap="4px"):
            _toggle_buttons(device_chart_home)
            fig = make_annual_kwh(df, model, n, home=home)
            solara.FigureMatplotlib(fig)
    elif chart_name == "Annual Gas by Device":
        home = device_chart_home.value
        with solara.Column(gap="4px"):
            _toggle_buttons(device_chart_home)
            fig = make_annual_gas(df, model, n, home=home)
            solara.FigureMatplotlib(fig)
    elif chart_name == "Electricity Rate Shape":
        fig = make_acc_rate_shape(df, model, n)
        solara.FigureMatplotlib(fig)
        cal = sim_start_year.value + acc_shape_year.value - 1
        solara.SliderInt(
            f"Year {acc_shape_year.value}  ({cal})",
            value=acc_shape_year, min=1, max=n,
        )
        solara.Text(
            "Shape shown for 2025 reference year — multi-year ACC data in Phase 3.",
            style="font-size:0.76em; color:#9E9E9E",
        )
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


_PANEL_STATUS_COLOR = {
    "green":  "#2E7D32",
    "yellow": "#F9A825",
    "orange": "#FB8C00",
    "red":    "#C62828",
}
_PANEL_STATUS_ICON = {
    "green": "✅", "yellow": "⚠", "orange": "⚠", "red": "⛔",
}


def _panel_bar_html(amps, util_pct, panel_a, status, label):
    """One compact load bar row for the Estimated Electrical Load callout."""
    color = _PANEL_STATUS_COLOR[status]
    icon  = _PANEL_STATUS_ICON[status]
    fill  = min(100.0, util_pct)
    return (
        f"<div style='display:flex; align-items:center; gap:10px; margin:3px 0;'>"
        f"<span style='min-width:54px; font-weight:700; color:{color};'>{label}</span>"
        f"<span style='min-width:46px; font-weight:700;'>{amps:.0f}A</span>"
        f"<span style='flex:1; max-width:220px; height:14px; background:#ECEFF1;"
        f" border-radius:7px; overflow:hidden; position:relative;'>"
        f"<span style='position:absolute; left:0; top:0; bottom:0; width:{fill:.0f}%;"
        f" background:{color};'></span></span>"
        f"<span style='min-width:140px; font-size:0.88em; color:#455A64;'>"
        f"{util_pct:.0f}% of {panel_a}A panel {icon}</span>"
        f"</div>"
    )


_PEAK_BADGE = {
    "green":  ("peak-ok",     "Within {p} A panel"),
    "yellow": ("peak-warn",   "Approaching panel limit"),
    "orange": ("peak-warn",   "Near panel capacity"),
    "red":    ("peak-danger", "Exceeds {p} A — panel upgrade"),
}
_LOAD_ICON = ("<span class='ic'><svg viewBox='0 0 24 24' fill='currentColor'>"
              "<path d='M13 2 4 14h6l-1 8 9-12h-6l1-8z'/></svg></span>")
_CHECK_SVG = ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' "
              "stroke-width='2.6' stroke-linecap='round' stroke-linejoin='round'>"
              "<path d='M20 6 9 17l-5-5'/></svg>")


@solara.component
def PanelLoadCallout(model):
    """Estimated Electrical Load — compact single-line strip (redesign §C)."""
    hc = model.home_config
    assessor = PanelAssessor(hc.square_footage, hc.panel_amps)
    timeline = assessor.journey_load_timeline(model.journey_home, model.n_years)
    if not timeline:
        return
    yr1  = timeline[0]
    peak = max(timeline, key=lambda t: t.service_amps)
    panel = hc.panel_amps

    peak_cls, badge_tmpl = _PEAK_BADGE.get(peak.status, _PEAK_BADGE["green"])
    badge_text = badge_tmpl.format(p=panel)
    badge_icon = _CHECK_SVG if peak_cls == "peak-ok" else "⚠"
    peak_dev = peak.new_device or "current load"
    peak_cal = sim_start_year.value + peak.year - 1

    metrics = (
        "<div class='load-metrics'>"
        "<div class='lm'>"
        "<span class='lm-k'>Current Load</span>"
        f"<span class='lm-v'>{yr1.service_amps:.0f} A</span>"
        f"<span class='lm-s'>{yr1.utilization_pct:.0f}% of {panel}&nbsp;A panel</span>"
        "</div>"
        f"<div class='lm peak {peak_cls}'>"
        "<span class='lm-k'>Journey Peak Load</span>"
        f"<span class='lm-v'>{peak.service_amps:.0f} A</span>"
        f"<span class='peak-badge'>{badge_icon} {badge_text}</span>"
        f"<span class='lm-s'>peaks Yr&nbsp;{peak.year} ({peak_cal}) · {peak_dev}</span>"
        "</div></div>"
    )
    title = (
        "<div class='load-title'>"
        f"{_LOAD_ICON}<h3>Estimated Electrical Load</h3></div>"
    )

    with solara.Card(classes=["card", "load-strip"], margin=0,
                     style="margin-bottom:var(--gap)"):
        with solara.Row(classes=["load-line"], style="align-items:center; gap:22px"):
            solara.HTML(tag="div", unsafe_innerHTML=title, style="flex-shrink:0")
            HelpButton("panel_assessment")
            solara.HTML(tag="div", unsafe_innerHTML=metrics, style="flex:1; min-width:0")


@solara.component
def SummaryStats(df, n, model):
    delta_vals = df["Opex Delta"].values
    delta_cum  = float(delta_vals[-1])

    payback_yr = None
    for i, d in enumerate(delta_vals):
        if d > 0:
            payback_yr = i + 1
            break

    journey_cum  = float(df["Journey Cum Cost"].iloc[-1])
    baseline_cum = float(df["Baseline Cum Cost"].iloc[-1])

    # ── Scenario B (comparison mode) ──────────────────────────────────────────
    has_B = model.comparison_mode and "Baseline Cum Cost B" in df.columns
    if has_B:
        bB = float(df["Baseline Cum Cost B"].iloc[-1])
        eB = float(df["Journey Cum Cost B"].iloc[-1])
        dB = bB - eB
        pb_B = None
        for i, (b, e) in enumerate(zip(df["Baseline Cum Cost B"].values,
                                        df["Journey Cum Cost B"].values)):
            if b > e:
                pb_B = i + 1
                break

    # ── Build figure (bars only, no in-plot text) ─────────────────────────────
    fig_h = 1.55 if not has_B else 2.6
    fig = Figure(figsize=(5.8, fig_h))
    fig.patch.set_facecolor("none")
    ax = fig.add_subplot(111)
    ax.set_facecolor("none")

    bar_h = 0.42
    gap   = 0.68
    yticks, y_tick_labels = [], []

    def _draw_bars(y_top, journey_val, baseline_val, label_suffix=""):
        ax.barh(y_top,       journey_val,  height=bar_h, color=C_NAVY, alpha=0.85, zorder=3)
        ax.barh(y_top - gap, baseline_val, height=bar_h, color=C_RED,  alpha=0.72, zorder=3)
        sfx = f"  {label_suffix}" if label_suffix else ""
        yticks.extend([y_top, y_top - gap])
        y_tick_labels.extend([
            f"Your Electrification Journey{sfx}",
            f"Do-Nothing Baseline{sfx}",
        ])
        return max(journey_val, baseline_val)

    if has_B:
        x1 = _draw_bars(2.8,       journey_cum,  baseline_cum, "(A)")
        x2 = _draw_bars(2.8 - 1.5, eB,           bB,           "(B)")
        x_end = max(x1, x2)
    else:
        x_end = _draw_bars(1.0, journey_cum, baseline_cum)

    ax.set_xlim(0, x_end * 1.08)
    ax.set_yticks(yticks)
    ax.set_yticklabels(y_tick_labels, fontsize=8.8)
    ax.tick_params(axis="y", length=0, pad=4)
    ax.xaxis.set_visible(False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    x_ticks = np.linspace(0, x_end, 5)
    for xv in x_ticks[1:]:
        ax.axvline(xv, color="#ccc", linewidth=0.5, zorder=1)
    fig.tight_layout(pad=0.3)

    # ── Right-side text panel ─────────────────────────────────────────────────
    if payback_yr is not None:
        cal_pb   = sim_start_year.value + payback_yr - 1
        pb_line1 = f"Payback year {payback_yr}"
        pb_line2 = f"({cal_pb})"
    else:
        pb_line1 = "No payback"
        pb_line2 = f"within {n} yrs"

    sav_color = "#2E7D32" if delta_cum >= 0 else "#B71C1C"
    sign      = "+" if delta_cum >= 0 else "−"
    sav_line1 = f"{sign}${abs(delta_cum):,.0f}"
    sav_line2 = f"over {n} yrs"

    # Scenario B right-panel text
    if has_B:
        if pb_B is not None:
            pb_B_line1 = f"Payback yr {pb_B}  ({sim_start_year.value + pb_B - 1})"
        else:
            pb_B_line1 = f"No payback in {n} yrs"
        dB_sign     = "+" if dB >= 0 else "−"
        dB_color    = "#2E7D32" if dB >= 0 else "#B71C1C"
        sav_B_line1 = f"{dB_sign}${abs(dB):,.0f}"

    with solara.Row(
        style="justify-content:center; align-items:center; gap:0px; margin:2px 0 0 0"
    ):
        solara.FigureMatplotlib(fig, dependencies=[df, n])

        # Stat box to the right
        with solara.Column(
            gap="0px",
            style=(
                "min-width:148px; padding:6px 14px;"
                " border-left:2px solid #E0E0E0;"
                " justify-content:center;"
            ),
        ):
            # Journey payback (blue)
            solara.HTML(
                tag="div",
                unsafe_innerHTML=(
                    f"<div style='color:{C_NAVY};font-size:1.25em;"
                    f"font-weight:700;line-height:1.15'>{pb_line1}</div>"
                    f"<div style='color:{C_NAVY};font-size:1.05em;"
                    f"font-weight:600;line-height:1.2;margin-bottom:10px'>{pb_line2}</div>"
                    f"<div style='color:{sav_color};font-size:1.45em;"
                    f"font-weight:800;line-height:1.1'>{sav_line1}</div>"
                    f"<div style='color:#555;font-size:0.82em;line-height:1.3'>{sav_line2}</div>"
                    + (
                        f"<div style='margin-top:10px;border-top:1px solid #ddd;padding-top:6px;"
                        f"color:#1565C0;font-size:0.85em;font-weight:600'>"
                        f"B: {pb_B_line1}<br>"
                        f"<span style='color:{dB_color};font-size:1.1em;font-weight:700'>"
                        f"{sav_B_line1}</span></div>"
                        if has_B else ""
                    )
                ),
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




# ── §25 Unified Summary + Detail UI ──────────────────────────────────────────

_DETAIL_TITLES = {
    "hvac":         "🌡️ HVAC — Heating & Cooling",
    "water_heater": "🚿 Water Heater",
    "ev":           "🚗 EV Charger",
    "cooktop":      "🍳 Cooktop",
    "dryer":        "👕 Dryer",
    "panel":        "⚡ Electrical Panel Upgrade",
    "baseload":     "💡 Baseload & Lights",
    "home":         "🏠 Home Profile",
    "solar":        "☀️ Solar + Battery",
    "rates":        "📈 Rate Scenarios",
}

# ── §25.4.1 Style constants for two-column layout ─────────────────────────────
_LEFT_COL  = "flex:1; min-width:180px; padding:0 16px 0 0"
_RIGHT_COL = "flex:1; min-width:180px; padding:0 0 0 16px; border-left:2px solid #E8EAF6"
_COSTS_BOX = (
    "padding:10px 14px; background:#F0F4FF; border-radius:6px;"
    " margin-top:12px; border-top:2px solid #C5CAE9;"
)
_CARD_NORMAL = (
    "border:1px solid #E0E0E0; border-radius:6px;"
    " padding:4px 8px; gap:2px; margin-bottom:6px; background:white;"
)
_CARD_OPEN = (
    "border:1px solid #C5CAE9; border-radius:6px;"
    " padding:4px 8px; gap:2px; margin-bottom:6px; background:#F3F4FF;"
)
_ROW_CTRL = "align-items:center; flex-wrap:wrap; margin-top:3px"
_TOP_ROW  = (
    "align-items:center; flex-wrap:wrap;"
    " padding-bottom:6px; border-bottom:1px solid #EEEEEE; margin-bottom:6px;"
)


# ── §25.4.1 Shared detail-window helpers ──────────────────────────────────────

@solara.component
def DetailTitleBar(title: str):
    """Icon + name left, green ✓ Done right."""
    with solara.Row(style=(
        "background:#E8EAF6; padding:8px 14px;"
        " border-radius:4px 4px 0 0; margin:-16px -16px 12px -16px;"
        " align-items:center;"
    )):
        solara.Text(title, style="font-weight:700; font-size:1.0em; flex:1; color:#0D47A1")
        solara.Button(
            "✓ Done",
            on_click=lambda: detail_open.set(None),
            style=(
                "background:#2E7D32; color:white; border:none;"
                " border-radius:5px; padding:5px 14px;"
                " font-size:0.85em; cursor:pointer; font-weight:600;"
            ),
        )


def _DS(heading: str):
    """DetailSection heading — blue underlined label."""
    solara.HTML(
        tag="div",
        unsafe_innerHTML=(
            f"<div style='font-weight:700; font-size:0.9em; color:#0D47A1;"
            f" border-bottom:1px solid #C5CAE9; padding-bottom:3px;"
            f" margin:6px 0 3px;'>{heading}</div>"
        ),
    )


@solara.component
def _DSl(label, rv, default, lo, hi, step=1, unit="", fmt="{v}"):
    """DetailSlider — wraps SliderWithDefault for use inside detail columns."""
    with solara.Column(gap="0px", style="margin-bottom:4px"):
        SliderWithDefault(label, rv, default, lo, hi, step, unit=unit, fmt=fmt)


def _elec_display(volts: int, amps: int):
    """Read-only Electrical nameplate row (Phase 3 §2.5)."""
    va = volts * amps
    solara.HTML(
        tag="div",
        unsafe_innerHTML=(
            f"<div style='font-size:0.82em; color:#455A64; margin-top:4px;"
            f" padding-top:4px; border-top:1px dashed #CFD8DC;'>"
            f"<strong>Electrical</strong>&nbsp;&nbsp;{volts} V · {amps} A · "
            f"{va:,} VA</div>"
        ),
    )


@solara.component
def _ElecAmpsInput(label, amps_rv, volts: int = 240):
    """Editable amps input + live VA readout for an electric appliance (Phase 3 §2.5)."""
    with solara.Row(gap="8px", style="align-items:center; margin-top:4px;"
                                     " padding-top:4px; border-top:1px dashed #CFD8DC;"):
        with solara.Column(style="min-width:130px"):
            solara.InputInt(label, value=amps_rv)
        solara.HTML(tag="span", unsafe_innerHTML=(
            f"<span style='font-size:0.82em; color:#455A64;'>"
            f"{volts} V · {amps_rv.value} A · "
            f"<strong>{volts * amps_rv.value:,} VA</strong></span>"
        ))


@solara.component
def _DetailCosts(inst_rv, reb_rv):
    """Costs & Rebates — always full-width, always last row of any detail window."""
    net = inst_rv.value - reb_rv.value
    with solara.Column(style=_COSTS_BOX):
        solara.HTML(
            tag="div",
            unsafe_innerHTML=(
                "<div style='font-weight:700; font-size:0.9em; color:#0D47A1;"
                " border-bottom:1px solid #C5CAE9; padding-bottom:4px;"
                " margin-bottom:8px;'>Costs &amp; Rebates</div>"
            ),
        )
        with solara.Row(gap="12px", style="flex-wrap:wrap; align-items:center"):
            with solara.Column(style="min-width:140px"):
                solara.InputInt("Install cost $", value=inst_rv)
            with solara.Column(style="min-width:120px"):
                solara.InputInt("Rebate $", value=reb_rv)
            solara.HTML(
                tag="div",
                unsafe_innerHTML=(
                    f"<div style='font-size:1.05em; font-weight:700; color:#1976D2'>"
                    f"Net ${net:,}</div>"
                ),
            )


# ── §25.2 Summary card helpers ────────────────────────────────────────────────

_DEVICE_ICONS = {
    "hvac":         ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<path d='M12 3v18M3 12h18M5.6 5.6l12.8 12.8M18.4 5.6 5.6 18.4'/>"
                     "<circle cx='12' cy='12' r='2.4' fill='currentColor' stroke='none'/></svg>"),
    "water_heater": ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<rect x='6' y='3' width='12' height='18' rx='3'/>"
                     "<path d='M9 8h6M12 13v4'/></svg>"),
    "ev":           ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<path d='M3 17V8a2 2 0 012-2h7a2 2 0 012 2v9'/>"
                     "<path d='M2 17h13'/><circle cx='5.5' cy='17.5' r='1.6'/>"
                     "<circle cx='11.5' cy='17.5' r='1.6'/><path d='M14 9h2.5L19 12v5h-5'/></svg>"),
    "cooktop":      ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<path d='M12 2c0 6-6 6-6 12a6 6 0 1012 0c0-6-6-6-6-12z'/></svg>"),
    "dryer":        ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<path d='M20.38 3.46 16 2a4 4 0 01-8 0L3.62 3.46a2 2 0 00-1.34 2.23l.58 3.57"
                     "a1 1 0 00.99.84H6v10c0 1.1.9 2 2 2h8a2 2 0 002-2V10h2.15a1 1 0 00.99-.84"
                     "l.58-3.57a2 2 0 00-1.34-2.23z'/></svg>"),
    "panel":        ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<path d='M13 2 4 14h6l-1 8 9-12h-6l1-8z'/></svg>"),
    "baseload":     ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<path d='M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 006 8"
                     "c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5'/>"
                     "<path d='M9 18h6M10 22h4'/></svg>"),
    "home":         ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<path d='M3 11.5 12 4l9 7.5'/><path d='M5 10.5V20h14v-9.5'/></svg>"),
    "solar":        ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<circle cx='12' cy='12' r='4'/>"
                     "<path d='M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2'/>"
                     "</svg>"),
    "rates":        ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<path d='M3 3v18h18'/><path d='M7 14l3-4 3 2 4-6'/></svg>"),
}

# ── Card-level header icons (accent-soft .ic chip in .card-hd) ────────────────
_CARD_IC = {
    "journey": ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                " stroke-linecap='round' stroke-linejoin='round'>"
                "<path d='M4 19V5a2 2 0 012-2h9l5 5v11a2 2 0 01-2 2H6a2 2 0 01-2-2z'/>"
                "<path d='M8 8h5M8 12h8M8 16h8'/></svg>"),
    "home":    ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                " stroke-linecap='round' stroke-linejoin='round'>"
                "<path d='M3 11.5 12 4l9 7.5'/><path d='M5 10.5V20h14v-9.5'/></svg>"),
    "energy":  ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                " stroke-linecap='round' stroke-linejoin='round'>"
                "<path d='M3 3v18h18'/><path d='M7 14l3-4 3 2 4-6'/></svg>"),
}

# ── Panel sub-header icons (smaller .ic chip in .panel-hd) ────────────────────
_PANEL_IC = {
    "home_profile": ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<path d='M3 11.5 12 4l9 7.5'/><path d='M5 10.5V20h14v-9.5'/></svg>"),
    "solar":        ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<circle cx='12' cy='12' r='4'/>"
                     "<path d='M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2'/>"
                     "</svg>"),
    "rates":        ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<path d='M3 17l5-5 4 3 7-8'/><path d='M21 7v5h-5'/></svg>"),
    "social":       ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<path d='M12 22C6.5 22 2 17.5 2 12S6.5 2 12 2s10 4.5 10 10-4.5 10-10 10z'/>"
                     "<path d='M8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01'/></svg>"),
}


_DEVICE_HELP_KEY = {
    "hvac":         "hvac",
    "water_heater": "water_heater",
    "ev":           "ev_charger",
    "cooktop":      "cooktop",
    "dryer":        "dryer",
    "panel":        "panel_upgrade",
    "baseload":     "baseload",
    "home":         "home_profile",
    "solar":        "solar",
    "rates":        "rates",
}


def _card_header(key: str, title: str):
    """Device-hd row: icon + name + ? help button + ⋮ details button."""
    icon_svg = _DEVICE_ICONS.get(key, "")
    help_key = _DEVICE_HELP_KEY.get(key, "")
    with solara.Row(classes=["device-hd"], gap="0px",
                    style="align-items:center; gap:8px"):
        if icon_svg:
            solara.HTML(tag="span", unsafe_innerHTML=(
                f"<span class='di'>{icon_svg}</span>"
            ))
        solara.HTML(tag="span", unsafe_innerHTML=(
            f"<span class='dn'>{title}</span>"
        ), style="flex:1")
        if help_key:
            HelpButton(help_key)
        solara.Button(
            "",
            on_click=lambda k=key: detail_open.set(
                None if detail_open.value == k else k
            ),
            classes=["iconbtn"],
            style="",
            children=[solara.HTML(tag="span", unsafe_innerHTML=(
                "<svg viewBox='0 0 24 24' fill='currentColor'>"
                "<circle cx='5' cy='12' r='1.8'/>"
                "<circle cx='12' cy='12' r='1.8'/>"
                "<circle cx='19' cy='12' r='1.8'/></svg>"
            ))],
        )


def _card_header_main(card_key: str, title: str, help_key: str):
    """Top-level card header: .ic icon chip + h3 title + spacer + ? help button."""
    ic_svg = _CARD_IC.get(card_key, "")
    # Render icon + title as a single HTML block so no extra v-col wrappers split them
    solara.HTML(tag="div", unsafe_innerHTML=(
        f"<div style='display:flex;align-items:center;gap:9px;flex:1;min-width:0'>"
        f"<span class='ic'>{ic_svg}</span>"
        f"<h3 style='margin:0;font-size:14px;font-weight:700;color:var(--ink,#1C2333);"
        f"white-space:nowrap;letter-spacing:-0.01em'>{title}</h3>"
        f"</div>"
    ))
    # Help button as Solara component (needs reactive access)
    HelpButton(help_key)


def _panel_hd(panel_key: str, title: str):
    """Sub-panel header: small .ic chip + h4 title (rendered as HTML, no interactivity needed)."""
    ic_svg = _PANEL_IC.get(panel_key, "")
    solara.HTML(tag="div", unsafe_innerHTML=(
        f"<div class='panel-hd'>"
        f"<span class='ic'>{ic_svg}</span>"
        f"<h4 style='margin:0'>{title}</h4>"
        f"</div>"
    ))


@solara.component
def _PlanCheck(planned_rv, label: str = "Plan", right: bool = True):
    """Rounded (circle-icon), optionally right-justified 'Plan' checkbox."""
    wrap = ("flex:1 1 auto; justify-content:flex-end" if right
            else "justify-content:flex-start")
    with solara.Row(classes=["plan-check"], style=wrap):
        solara.v.Checkbox(
            v_model=planned_rv.value,
            on_v_model=planned_rv.set,
            label=label,
            dense=True,
            hide_details=True,
            ripple=False,
            color="#3B6FD4",
            off_icon="mdi-checkbox-blank-circle-outline",
            on_icon="mdi-check-circle",
        )


def _cost_row(cost_rv, rebate_rv, net: int):
    """Install $ · Rebate $ · Net — compact single line, box-style, integers only."""
    net_color = "var(--positive-ink,#2E7D32)" if net >= 0 else "var(--baseline-ink,#B45B3E)"
    with solara.Row(classes=["cost-row"],
                    style="align-items:flex-end;gap:8px;flex-wrap:nowrap"):
        with solara.Column(classes=["cost-field"], style="max-width:88px;min-width:72px"):
            solara.InputInt("Install $", value=cost_rv)
        with solara.Column(classes=["cost-field"], style="max-width:88px;min-width:72px"):
            solara.InputInt("Rebate $", value=rebate_rv)
        solara.HTML(tag="div", unsafe_innerHTML=(
            "<div style='padding-bottom:6px;line-height:1'>"
            "<div style='font-size:0.72em;color:var(--ink-3,#888);margin-bottom:4px'>Net</div>"
            f"<span style='font-size:0.88em;font-weight:700;color:{net_color};"
            f"font-family:var(--mono,monospace)'>${abs(net):,}</span>"
            "</div>"
        ))


def _appliance_rows(state_rv, planned_rv, year_rv, cost_rv, rebate_rv,
                    state_values=("gas", "electric", "none")):
    """Row content for standard appliance summary cards (HVAC, WH, Cooktop, Dryer)."""
    state = state_rv.value
    # Row 1: state dropdown + plan checkbox (+ electrified badge)
    with solara.Row(gap="8px", style=_ROW_CTRL):
        with solara.Column(style="min-width:90px; max-width:90px"):
            solara.Select("", value=state_rv, values=list(state_values))
        if state != "electric":
            _PlanCheck(planned_rv, "Plan")
        elif state == "electric":
            solara.HTML(tag="span", unsafe_innerHTML=(
                "<span style='font-size:0.80em; color:#2E7D32; margin-left:4px;'>"
                "✓ Electrified</span>"
            ))
    # Row 2: full-width year slider + subscript caption (only when planned)
    if state != "electric" and planned_rv.value:
        yr = year_rv.value
        cal_yr = sim_start_year.value + yr - 1
        with solara.Column(style="width:100%"):
            solara.SliderInt("", value=year_rv, min=1, max=25)
            solara.HTML(tag="div", unsafe_innerHTML=(
                f"<div style='font-size:0.72em;color:var(--ink-3,#888);"
                f"margin-top:-4px;text-align:center'>"
                f"Yr {yr} &nbsp;·&nbsp; {cal_yr}</div>"
            ))
    # Row 2: install cost + rebate + net — all on one line, compact number inputs
    if state != "electric" and planned_rv.value:
        net = cost_rv.value - rebate_rv.value
        _cost_row(cost_rv, rebate_rv, net)
    else:
        solara.HTML(tag="div", unsafe_innerHTML=(
            "<div style='font-size:0.80em; color:#AAAAAA; margin-top:3px;'>"
            + ("No swap planned" if state != "electric" else "") + "</div>"
        ))


# ── §25.3 Summary card components ────────────────────────────────────────────

@solara.component
def HVACSummaryCard():
    """§25.3.1 — state dropdown + plan year | install cost | rebate."""
    with solara.Column(classes=["device"]):
        _card_header("hvac", "HVAC")
        _appliance_rows(hvac_starting_state, hvac_swap_planned, hvac_swap_year,
                        hvac_install_cost, hvac_rebate)


@solara.component
def WHSummaryCard():
    """§25.3.2 — state dropdown + plan year | install cost | rebate."""
    with solara.Column(classes=["device"]):
        _card_header("water_heater", "Water Heater")
        _appliance_rows(wh_starting_state, wh_swap_planned, wh_swap_year,
                        wh_install_cost, wh_rebate)


@solara.component
def EVSummaryCard():
    """§25.3.3 — vehicle preset + plan year | charger L1/L2 | miles/yr."""
    state = ev_starting_state.value
    with solara.Column(classes=["device"]):
        _card_header("ev", "EV Charger")
        # Row 1: vehicle presets + state dropdown + plan checkbox
        with solara.Row(gap="4px", style=_ROW_CTRL):
            for lbl, val in [("Eff", 0.23), ("Avg", 0.30), ("SUV", 0.45)]:
                is_sel = abs(ev_kwh_per_mile.value - val) < 0.01
                solara.Button(
                    lbl,
                    on_click=lambda v=val: ev_kwh_per_mile.set(v),
                    style=(
                        "font-size:0.72em; padding:2px 7px; border-radius:10px;"
                        " cursor:pointer;"
                        + (" background:#C5CAE9; border:1px solid #7986CB; color:#3949AB;"
                           if is_sel else
                           " background:#F5F5F5; border:1px solid #DDD; color:#666;")
                    ),
                )
            with solara.Column(style="min-width:80px; max-width:80px"):
                solara.Select("", value=ev_starting_state, values=["none", "electric"])
            if state == "none":
                _PlanCheck(ev_swap_planned, "Plan")
            elif state == "electric":
                solara.HTML(tag="span", unsafe_innerHTML=(
                    "<span style='font-size:0.80em; color:#2E7D32;'>✓ Installed</span>"
                ))
        # Row 2: full-width year slider + subscript (only when planned)
        if state == "none" and ev_swap_planned.value:
            yr = ev_swap_year.value
            cal_yr = sim_start_year.value + yr - 1
            with solara.Column(style="width:100%"):
                solara.SliderInt("", value=ev_swap_year, min=1, max=25)
                solara.HTML(tag="div", unsafe_innerHTML=(
                    f"<div style='font-size:0.72em;color:var(--ink-3,#888);"
                    f"margin-top:-4px;text-align:center'>"
                    f"Yr {yr} &nbsp;·&nbsp; {cal_yr}</div>"
                ))
        # Row 2: charger type
        solara.HTML(tag="div", unsafe_innerHTML=(
            "<div style='font-size:0.80em; color:#555; margin-top:3px;'>"
            "Charger: <strong>L2</strong> (240 V)</div>"
        ))
        # Row 3: miles/yr input
        with solara.Row(gap="6px", style=_ROW_CTRL):
            with solara.Column(style="min-width:140px"):
                solara.InputInt("Miles/yr", value=ev_miles_per_year)


@solara.component
def CooktopSummaryCard():
    """§25.3.4 — state dropdown + plan year | install cost | rebate."""
    with solara.Column(classes=["device", "minor"]):
        _card_header("cooktop", "Cooktop")
        _appliance_rows(cooktop_starting_state, cooktop_swap_planned, cooktop_swap_year,
                        cooktop_install_cost, cooktop_rebate)


@solara.component
def DryerSummaryCard():
    """§25.3.5 — state dropdown + plan year | install cost | rebate."""
    with solara.Column(classes=["device", "minor"]):
        _card_header("dryer", "Dryer")
        _appliance_rows(dryer_starting_state, dryer_swap_planned, dryer_swap_year,
                        dryer_install_cost, dryer_rebate)


@solara.component
def _PanelControls():
    """Panel Upgrade inline controls (no .device wrapper / header)."""
    planned = panel_upgrade_planned.value
    # Row 1: plan checkbox
    with solara.Row(gap="8px", style=_ROW_CTRL):
        _PlanCheck(panel_upgrade_planned, "Plan 200A upgrade")
    # Row 2: full-width year slider + subscript
    if planned:
        yr = panel_upgrade_year.value
        cal_yr = sim_start_year.value + yr - 1
        with solara.Column(style="width:100%"):
            solara.SliderInt("", value=panel_upgrade_year, min=1, max=25)
            solara.HTML(tag="div", unsafe_innerHTML=(
                f"<div style='font-size:0.72em;color:var(--ink-3,#888);"
                f"margin-top:-4px;text-align:center'>"
                f"Yr {yr} &nbsp;·&nbsp; {cal_yr}</div>"
            ))
        net = panel_upgrade_cost.value - panel_upgrade_rebate.value
        _cost_row(panel_upgrade_cost, panel_upgrade_rebate, net)
    else:
        solara.HTML(tag="div", unsafe_innerHTML=(
            "<div class='noplan' style='margin-top:3px'>Not planned</div>"
        ))


@solara.component
def PanelSummaryCard():
    """§25.3.6 — amperage + plan year | install cost | rebate."""
    with solara.Column(classes=["device"]):
        _card_header("panel", "Panel Upgrade")
        _PanelControls()


@solara.component
def _BaseloadControls():
    """Baseload inline controls (no .device wrapper / header)."""
    bl_kwh = compute_baseload_kwh(square_footage.value, num_bedrooms.value,
                                   baseload_constant_before.value)
    # Row 1: elec kWh/mo
    solara.HTML(tag="div", unsafe_innerHTML=(
        f"<div style='font-size:0.80em; color:#444; margin-top:3px;'>"
        f"~<strong>{bl_kwh/12:,.0f} kWh/mo</strong> electricity</div>"
    ))
    # Row 2: gas therms/mo + plan upgrade checkbox
    with solara.Row(gap="8px", style=_ROW_CTRL):
        solara.HTML(tag="span", unsafe_innerHTML=(
            "<span style='font-size:0.80em; color:#888;'>0 therms/mo gas</span>"
        ))
        _PlanCheck(baseload_swap_planned, "Plan upgrade")
    # Row 3: saving or always-on constant info
    if baseload_swap_planned.value:
        bl_after = compute_baseload_kwh(square_footage.value, num_bedrooms.value,
                                        baseload_constant_after.value)
        saving  = bl_kwh - bl_after
        yr      = baseload_swap_year.value
        cal_yr  = sim_start_year.value + yr - 1
        solara.HTML(tag="div", unsafe_innerHTML=(
            f"<div style='font-size:0.80em; color:#2E7D32; margin-top:3px;'>"
            f"Save ~{saving:,.0f} kWh/yr · yr {yr} ({cal_yr})</div>"
        ))
    else:
        solara.HTML(tag="div", unsafe_innerHTML=(
            f"<div style='font-size:0.80em; color:#888; margin-top:3px;'>"
            f"Always-on: {baseload_constant_before.value} kWh/yr constant</div>"
        ))


@solara.component
def BaseloadSummaryCard():
    """§25.3.7 — elec kWh/mo | gas therms/mo | growth %/yr."""
    with solara.Column(classes=["device"]):
        _card_header("baseload", "Baseload")
        _BaseloadControls()


@solara.component
def HomeSummaryCard():
    """§25.3.8 — zip + bedrooms | sq ft | climate zone."""
    with solara.Column(classes=["device"]):
        _card_header("home", "Home Profile")
        # Row 1: ZIP + bedrooms
        with solara.Row(gap="6px", style=_ROW_CTRL):
            with solara.Column(style="min-width:75px; max-width:75px"):
                solara.InputText("ZIP", value=zip_code)
            with solara.Column(style="min-width:75px; max-width:75px"):
                solara.Select("Beds", value=num_bedrooms, values=[1, 2, 3, 4, 5])
        # Row 2: sq ft
        with solara.Row(gap="6px", style=_ROW_CTRL):
            with solara.Column(style="min-width:140px"):
                solara.InputInt("Sq ft", value=square_footage)
        # Row 3: climate zone
        with solara.Row(gap="6px", style=_ROW_CTRL):
            with solara.Column(style="min-width:120px"):
                solara.Select("Climate zone", value=climate_zone, values=_CZ_OPTIONS)


@solara.component
def SolarSummaryCard():
    """§25.3.9 — add solar + add battery checkboxes | plan yr | % coverage slider."""
    planned = solar_planned.value
    with solara.Column(classes=["device"]):
        _card_header("solar", "Solar + Battery")
        # Row 1: add solar + add battery checkboxes
        with solara.Row(gap="10px", style=_ROW_CTRL):
            solara.Checkbox(label="Add solar", value=solar_planned)
            if planned:
                solara.Checkbox(label="+ Battery", value=solar_include_battery)
        # Row 2: full-width install year slider + subscript (if planned)
        if planned:
            yr = solar_install_year.value
            cal_yr = sim_start_year.value + yr - 1
            with solara.Column(style="width:100%"):
                solara.SliderInt("", value=solar_install_year, min=1, max=25)
                solara.HTML(tag="div", unsafe_innerHTML=(
                    f"<div style='font-size:0.72em;color:var(--ink-3,#888);"
                    f"margin-top:-4px;text-align:center'>"
                    f"Install &nbsp; Yr {yr} &nbsp;·&nbsp; {cal_yr}</div>"
                ))
        else:
            solara.HTML(tag="div", unsafe_innerHTML=(
                "<div style='font-size:0.80em; color:#AAAAAA; margin-top:3px;'>"
                "Not planned</div>"
            ))
        # Row 3: % coverage slider (if planned)
        if planned:
            with solara.Column(style="width:100%"):
                solara.SliderInt("", value=solar_coverage_pct, min=0, max=100, step=5)
                solara.HTML(tag="div", unsafe_innerHTML=(
                    f"<div style='font-size:0.72em;color:var(--ink-3,#888);"
                    f"margin-top:-4px;text-align:center'>"
                    f"{solar_coverage_pct.value}% electricity covered</div>"
                ))


def _model_toggle(label: str, rv, options: list, color: str):
    """Inline model selector — two buttons + optional CAGR badge."""
    with solara.Row(gap="4px", style="align-items:center; flex-wrap:wrap"):
        solara.HTML(tag="span", unsafe_innerHTML=(
            f"<span style='font-size:0.80em; font-weight:600; color:{color};"
            f" min-width:28px'>{label}</span>"
        ))
        for key, display in options:
            is_active = rv.value == key
            solara.Button(
                display,
                on_click=lambda k=key: rv.set(k),
                style=(
                    f"background:{color}; color:white; border:none;"
                    " border-radius:4px; padding:2px 8px; font-size:0.78em; cursor:pointer;"
                    if is_active else
                    "background:#F5F5F5; color:#666; border:1px solid #CCC;"
                    " border-radius:4px; padding:2px 8px; font-size:0.78em; cursor:pointer;"
                ),
            )


@solara.component
def RatesSummaryCard():
    """Energy & Prices summary — elec model | gas model | timeline."""
    elec_model = elec_rate_model_a.value
    gas_model  = gas_rate_model_a.value
    with solara.Column(classes=["device"]):
        _card_header("rates", "Rate Scenarios")
        # Row 1: electricity rate model
        solara.HTML(tag="div", unsafe_innerHTML=(
            f"<div style='font-size:0.78em; font-weight:600; color:{C_RATE_ELEC};"
            " margin-bottom:2px'>Electricity Rate Model</div>"
        ))
        with solara.Row(gap="6px", style="align-items:center; flex-wrap:wrap"):
            _model_toggle("⚡", elec_rate_model_a,
                          [("cagr_flat", "CAGR"), ("acc_shaped", "ACC")], C_RATE_ELEC)
            if elec_model == "cagr_flat":
                solara.HTML(tag="span", unsafe_innerHTML=(
                    f"<span style='font-size:0.80em; color:#546E7A;'>"
                    f"+{elec_cagr_pct_a.value}%/yr</span>"
                ))
        # Row 2: gas rate model
        solara.HTML(tag="div", unsafe_innerHTML=(
            f"<div style='font-size:0.78em; font-weight:600; color:{C_RATE_GAS};"
            " margin-bottom:2px; margin-top:4px'>Gas Rate Model</div>"
        ))
        with solara.Row(gap="6px", style="align-items:center; flex-wrap:wrap"):
            _model_toggle("🔥", gas_rate_model_a,
                          [("cagr_flat", "CAGR"), ("acc_seasonal", "ACC")], C_RATE_GAS)
            if gas_model == "cagr_flat":
                solara.HTML(tag="span", unsafe_innerHTML=(
                    f"<span style='font-size:0.80em; color:#546E7A;'>"
                    f"+{gas_cagr_pct_a.value}%/yr</span>"
                ))
        # Row 3: timeline
        solara.SliderInt(
            f"Model: {years.value} yrs",
            value=years, min=5, max=30,
        )


# ── §25.4 Detail windows ──────────────────────────────────────────────────────

@solara.component
def HVACDetail():
    """HVAC detail — two-column layout per §25.4.3."""
    state = hvac_starting_state.value
    ua    = UA_MAP[insulation_quality.value]

    # Full-width: state + plan controls
    with solara.Row(gap="8px", style=_TOP_ROW):
        with solara.Column(style="min-width:110px"):
            solara.Select("Starting state", value=hvac_starting_state,
                          values=["gas", "electric", "none"])
        if state != "electric":
            with solara.Column(style="min-width:70px"):
                solara.Checkbox(label="Plan swap", value=hvac_swap_planned)
        if state != "electric" and hvac_swap_planned.value:
            yr = hvac_swap_year.value
            cal_yr = sim_start_year.value + yr - 1
            with solara.Column(style="min-width:170px"):
                solara.SliderInt(f"Yr {yr} ({cal_yr})", value=hvac_swap_year, min=1, max=25)

    # ── Heat pump electrical sizing (Phase 3 §2.5) ────────────────────────────
    _tons = hvac_tonnage.value
    _amps = int(_tons * 10)
    _DSl("Heat pump size", hvac_tonnage, _DEFAULTS["hvac_tonnage"],
         2.0, 5.0, 0.5, unit=" ton", fmt="{v:.1f}")
    _elec_display(240, _amps)

    if state == "gas":
        with solara.Row(gap="0px", style="align-items:flex-start; flex-wrap:wrap"):
            with solara.Column(style=_LEFT_COL):
                _DS("Current: Gas Furnace")
                therms = _est_gas_furnace(furnace_afue.value, ua)
                solara.Markdown(
                    f"~**{therms:.0f} therms/yr** heating"
                    + (f"  ·  {_est_hp_hvac_cooling(hvac_ac_seer.value, ua):.0f} kWh/yr AC"
                       if hvac_has_cooling.value else "")
                )
                _DSl("Furnace AFUE", furnace_afue, _DEFAULTS["furnace_afue"],
                     0.70, 0.95, 0.01, fmt="{v:.2f}")
                _DSl("Furnace age", hvac_furnace_age, _DEFAULTS["hvac_furnace_age"],
                     0, 30, 1, unit=" yrs")
                solara.Checkbox(label="Has central AC (baseline)", value=hvac_has_cooling)
                if hvac_has_cooling.value:
                    _DSl("Central AC SEER", hvac_ac_seer, _DEFAULTS["hvac_ac_seer"], 10, 22, 1)
                    _DSl("Central AC age", hvac_ac_age, _DEFAULTS["hvac_ac_age"],
                         0, 20, 1, unit=" yrs")
            with solara.Column(style=_RIGHT_COL):
                _DS("Replacement: Heat Pump HVAC")
                heat_kwh  = _est_hp_hvac_heating(hp_cop_heating.value, ua)
                cool_kwh2 = _est_hp_hvac_cooling(hp_seer_cooling.value, ua)
                solara.Markdown(
                    f"~**{heat_kwh:.0f} kWh/yr** heat  "
                    f"+ **{cool_kwh2:.0f} kWh/yr** cool  "
                    f"= **{heat_kwh + cool_kwh2:.0f} kWh/yr**"
                )
                _DSl("Heating COP", hp_cop_heating, _DEFAULTS["hp_cop_heating"],
                     2.5, 4.5, 0.1, fmt="{v:.1f}")
                _DSl("Cooling SEER", hp_seer_cooling, _DEFAULTS["hp_seer_cooling"], 16, 28, 1)
        if hvac_swap_planned.value:
            _DetailCosts(hvac_install_cost, hvac_rebate)

    elif state == "electric":
        _DS("Current: Heat Pump HVAC")
        heat_kwh = _est_hp_hvac_heating(hp_cop_heating.value, ua)
        cool_kwh = _est_hp_hvac_cooling(hp_seer_cooling.value, ua)
        solara.Markdown(
            f"~**{heat_kwh:.0f} kWh/yr** heating  "
            f"+ **{cool_kwh:.0f} kWh/yr** cooling  "
            f"= **{heat_kwh + cool_kwh:.0f} kWh/yr** total"
        )
        _DSl("Heating COP", hp_cop_heating, _DEFAULTS["hp_cop_heating"],
             2.5, 4.5, 0.1, fmt="{v:.1f}")
        _DSl("Cooling SEER", hp_seer_cooling, _DEFAULTS["hp_seer_cooling"], 16, 28, 1)
        solara.Markdown("<small style='color:#2E7D32'>✓ Already electrified</small>")

    else:  # none
        with solara.Row(gap="0px", style="align-items:flex-start; flex-wrap:wrap"):
            with solara.Column(style=_LEFT_COL):
                _DS("Current: No HVAC")
                solara.Text("No baseline HVAC installed.",
                            style="font-size:0.85em; color:#888")
            with solara.Column(style=_RIGHT_COL):
                _DS("Adding: Heat Pump HVAC")
                heat_kwh = _est_hp_hvac_heating(hp_cop_heating.value, ua)
                cool_kwh = _est_hp_hvac_cooling(hp_seer_cooling.value, ua)
                solara.Markdown(
                    f"Est: **{heat_kwh:.0f} + {cool_kwh:.0f} = "
                    f"{heat_kwh + cool_kwh:.0f} kWh/yr**"
                )
                _DSl("Heating COP", hp_cop_heating, _DEFAULTS["hp_cop_heating"],
                     2.5, 4.5, 0.1, fmt="{v:.1f}")
                _DSl("Cooling SEER", hp_seer_cooling, _DEFAULTS["hp_seer_cooling"], 16, 28, 1)
        if hvac_swap_planned.value:
            _DetailCosts(hvac_install_cost, hvac_rebate)


@solara.component
def WaterHeaterDetail():
    """Water heater detail — §25.4.4 + §20 tank size & ambient location."""
    state   = wh_starting_state.value
    gal     = hw_daily_gallons.value
    inlet   = wh_inlet_temp_f.value
    setp    = wh_setpoint_f.value

    # Top row: starting state / plan / year (mirrors summary card for direct-jump users)
    with solara.Row(gap="8px", style=_TOP_ROW):
        with solara.Column(style="min-width:110px"):
            solara.Select("Starting state", value=wh_starting_state,
                          values=["gas", "electric", "none"])
        if state != "electric":
            with solara.Column(style="min-width:70px"):
                solara.Checkbox(label="Plan swap", value=wh_swap_planned)
        if state != "electric" and wh_swap_planned.value:
            yr = wh_swap_year.value
            cal_yr = sim_start_year.value + yr - 1
            with solara.Column(style="min-width:170px"):
                solara.SliderInt(f"Yr {yr} ({cal_yr})", value=wh_swap_year, min=1, max=25)

    _ElecAmpsInput("HPWH breaker A", hpwh_amps)

    # Shared full-width parameters (affect both gas and HPWH estimates)
    def _set_gal(v):
        hw_daily_gallons.set(v)
        hw_gallons_user_override.set(True)
    solara.SliderInt(
        f"Daily hot water: {gal} gal/day",
        value=hw_daily_gallons, min=20, max=120, step=5,
        on_value=_set_gal,
    )
    solara.SliderInt(
        f"Cold water inlet: {inlet}°F",
        value=wh_inlet_temp_f, min=45, max=75, step=1,
    )
    solara.SliderInt(
        f"Tank setpoint: {setp}°F",
        value=wh_setpoint_f, min=110, max=140, step=5,
    )

    if state == "gas":
        with solara.Row(gap="0px", style="align-items:flex-start; flex-wrap:wrap"):
            with solara.Column(style=_LEFT_COL):
                _DS("Current: Gas Water Heater")
                therms = _est_gas_wh(gas_wh_uef.value, gal, inlet, setp)
                solara.Markdown(
                    f"~**{therms:.0f} therms/yr** ≈ {_kwh_eq(therms):,.0f} kWh-eq")
                _DSl("Gas WH UEF", gas_wh_uef, _DEFAULTS["gas_wh_uef"],
                     0.55, 0.70, 0.01, fmt="{v:.2f}")
                _DSl("Age", wh_gas_age, _DEFAULTS["wh_gas_age"], 0, 20, 1, unit=" yrs")
                solara.Select(
                    f"Tank size: {gas_wh_tank_gallons.value} gal",
                    value=gas_wh_tank_gallons,
                    values=[30, 40, 50, 65, 80],
                )
            with solara.Column(style=_RIGHT_COL):
                _DS("Replacement: Heat Pump Water Heater")
                kwh = _est_hpwh(hpwh_uef.value, gal, inlet, setp)
                solara.Markdown(f"~**{kwh:.0f} kWh/yr**")
                _DSl("HPWH UEF", hpwh_uef, _DEFAULTS["hpwh_uef"],
                     2.5, 4.0, 0.1, fmt="{v:.1f}")
                solara.Select(
                    f"Tank size: {hpwh_tank_gallons.value} gal",
                    value=hpwh_tank_gallons,
                    values=[50, 65, 80],
                )
                solara.ToggleButtonsSingle(
                    value=hpwh_ambient_location,
                    values=["conditioned", "unconditioned"],
                )
                solara.HTML(tag="div", unsafe_innerHTML=(
                    "<div style='font-size:0.75em; color:#999; margin-top:6px;'>"
                    "Preview uses UEF + load only. Ambient COP degradation "
                    "and standby losses are applied in the simulation.</div>"
                ))
        if wh_swap_planned.value:
            _DetailCosts(wh_install_cost, wh_rebate)

    elif state == "electric":
        with solara.Row(gap="0px", style="align-items:flex-start; flex-wrap:wrap"):
            with solara.Column(style=_LEFT_COL):
                _DS("Current: Heat Pump Water Heater")
                kwh = _est_hpwh(hpwh_uef.value, gal, inlet, setp)
                solara.Markdown(f"~**{kwh:.0f} kWh/yr**")
                solara.Markdown("<small style='color:#2E7D32'>✓ Already electrified</small>")
            with solara.Column(style=_RIGHT_COL):
                _DS("HPWH Specs")
                _DSl("HPWH UEF", hpwh_uef, _DEFAULTS["hpwh_uef"], 2.5, 4.0, 0.1, fmt="{v:.1f}")
                solara.Select(
                    f"Tank size: {hpwh_tank_gallons.value} gal",
                    value=hpwh_tank_gallons,
                    values=[50, 65, 80],
                )
                solara.ToggleButtonsSingle(
                    value=hpwh_ambient_location,
                    values=["conditioned", "unconditioned"],
                )
                solara.HTML(tag="div", unsafe_innerHTML=(
                    "<div style='font-size:0.75em; color:#999; margin-top:6px;'>"
                    "Preview uses UEF + load only. Ambient COP degradation "
                    "applied in simulation.</div>"
                ))

    else:  # none
        with solara.Row(gap="0px", style="align-items:flex-start; flex-wrap:wrap"):
            with solara.Column(style=_LEFT_COL):
                _DS("Current: No Water Heater")
                solara.Text("No baseline WH installed.", style="font-size:0.85em; color:#888")
            with solara.Column(style=_RIGHT_COL):
                _DS("Adding: Heat Pump Water Heater")
                kwh = _est_hpwh(hpwh_uef.value, gal, inlet, setp)
                solara.Markdown(f"Est: **{kwh:.0f} kWh/yr**")
                _DSl("HPWH UEF", hpwh_uef, _DEFAULTS["hpwh_uef"],
                     2.5, 4.0, 0.1, fmt="{v:.1f}")
                solara.Select(
                    f"Tank size: {hpwh_tank_gallons.value} gal",
                    value=hpwh_tank_gallons,
                    values=[50, 65, 80],
                )
                solara.ToggleButtonsSingle(
                    value=hpwh_ambient_location,
                    values=["conditioned", "unconditioned"],
                )
                solara.HTML(tag="div", unsafe_innerHTML=(
                    "<div style='font-size:0.75em; color:#999; margin-top:6px;'>"
                    "Preview uses UEF + load only. Ambient COP degradation "
                    "applied in simulation.</div>"
                ))
        if wh_swap_planned.value:
            _DetailCosts(wh_install_cost, wh_rebate)


@solara.component
def EVDetail():
    """EV charger detail — two-column per §25.4.5."""
    state      = ev_starting_state.value
    annual_kwh = _est_ev_kwh(ev_miles_per_year.value, ev_kwh_per_mile.value,
                              ev_charging_efficiency.value)

    with solara.Row(gap="8px", style=_TOP_ROW):
        with solara.Column(style="min-width:110px"):
            solara.Select("Starting state", value=ev_starting_state,
                          values=["none", "electric"])
        if state == "none":
            with solara.Column(style="min-width:80px"):
                solara.Checkbox(label="Plan to add", value=ev_swap_planned)
        if state == "none" and ev_swap_planned.value:
            yr = ev_swap_year.value
            cal_yr = sim_start_year.value + yr - 1
            with solara.Column(style="min-width:170px"):
                solara.SliderInt(f"Yr {yr} ({cal_yr})", value=ev_swap_year, min=1, max=25)

    with solara.Row(gap="0px", style="align-items:flex-start; flex-wrap:wrap"):
        with solara.Column(style=_LEFT_COL):
            _DS("Vehicle")
            _DSl("Annual miles", ev_miles_per_year, _DEFAULTS["ev_miles_per_year"],
                 1000, 30000, step=500, unit=" mi/yr")
            _DSl("Efficiency", ev_kwh_per_mile, _DEFAULTS["ev_kwh_per_mile"],
                 0.23, 0.45, step=0.01, unit=" kWh/mi", fmt="{v:.2f}")
            with solara.Row(gap="3px", style="flex-wrap:wrap; margin-top:4px"):
                for lbl, val in [("Efficient (0.23)", 0.23), ("Average (0.30)", 0.30),
                                  ("Large SUV (0.45)", 0.45)]:
                    is_sel = abs(ev_kwh_per_mile.value - val) < 0.01
                    solara.Button(
                        lbl,
                        on_click=lambda v=val: ev_kwh_per_mile.set(v),
                        style=(
                            "font-size:0.75em; padding:2px 8px; border-radius:10px;"
                            " cursor:pointer; margin:2px;"
                            + (" background:#C5CAE9; border:1px solid #7986CB; color:#3949AB;"
                               if is_sel else
                               " background:#F5F5F5; border:1px solid #DDD; color:#555;")
                        ),
                    )
        with solara.Column(style=_RIGHT_COL):
            _DS("Charger")
            solara.HTML(tag="div", unsafe_innerHTML=(
                "<div style='font-size:0.85em; color:#555; margin-bottom:8px;'>"
                "<strong>L2 charger</strong> (240 V)</div>"
            ))
            # Amperage selector (Phase 3 §2.5) — drives panel load
            with solara.Row(gap="4px", style="margin-bottom:4px; align-items:center"):
                for lbl, amps in [("32 A (7.7 kW)", 32), ("48 A (11.5 kW)", 48)]:
                    is_sel = ev_charger_amps.value == amps
                    solara.Button(
                        lbl,
                        on_click=lambda a=amps: ev_charger_amps.set(a),
                        style=(
                            "font-size:0.74em; padding:2px 8px; border-radius:10px;"
                            " cursor:pointer;"
                            + (" background:#C5CAE9; border:1px solid #7986CB; color:#3949AB;"
                               if is_sel else
                               " background:#F5F5F5; border:1px solid #DDD; color:#555;")
                        ),
                    )
            _elec_display(240, ev_charger_amps.value)
            _DSl("Charging efficiency", ev_charging_efficiency,
                 _DEFAULTS["ev_charging_efficiency"], 0.80, 0.98, step=0.01, fmt="{v:.2f}")
            solara.Markdown(
                f"Est. consumption: **{annual_kwh:,.0f} kWh/yr**  \n"
                f"({ev_miles_per_year.value:,} mi × {ev_kwh_per_mile.value:.2f} kWh/mi ÷ "
                f"{ev_charging_efficiency.value:.2f} eff.)"
            )

    if state == "none" and ev_swap_planned.value:
        _DetailCosts(ev_install_cost, ev_rebate)


@solara.component
def CooktopDetail():
    """Cooktop detail — two-column per §25.4.6."""
    state = cooktop_starting_state.value

    with solara.Row(gap="8px", style=_TOP_ROW):
        with solara.Column(style="min-width:110px"):
            solara.Select("Starting state", value=cooktop_starting_state,
                          values=["gas", "electric", "none"])
        if state != "electric":
            with solara.Column(style="min-width:70px"):
                solara.Checkbox(label="Plan swap", value=cooktop_swap_planned)
        if state != "electric" and cooktop_swap_planned.value:
            yr = cooktop_swap_year.value
            cal_yr = sim_start_year.value + yr - 1
            with solara.Column(style="min-width:170px"):
                solara.SliderInt(f"Yr {yr} ({cal_yr})", value=cooktop_swap_year, min=1, max=25)

    _ElecAmpsInput("Induction breaker A", induction_amps)

    if state == "gas":
        with solara.Row(gap="0px", style="align-items:flex-start; flex-wrap:wrap"):
            with solara.Column(style=_LEFT_COL):
                _DS("Current: Gas Cooktop")
                therms = _est_gas_cooktop(cooktop_gas_therms_per_meal.value,
                                          cooktop_meals_per_week.value)
                solara.Markdown(
                    f"~**{therms:.0f} therms/yr** ≈ {_kwh_eq(therms):,.0f} kWh-eq")
                _DSl("Therms/meal", cooktop_gas_therms_per_meal,
                     _DEFAULTS["cooktop_gas_therms_per_meal"], 0.03, 0.10, 0.01, fmt="{v:.2f}")
                _DSl("Meals/week", cooktop_meals_per_week, _DEFAULTS["cooktop_meals_per_week"],
                     3, 21, 1, unit=" /wk")
            with solara.Column(style=_RIGHT_COL):
                _DS("Replacement: Induction Cooktop")
                kwh = _est_induction(cooktop_induction_kwh_per_meal.value,
                                     cooktop_meals_per_week.value)
                solara.Markdown(f"~**{kwh:.0f} kWh/yr**")
                _DSl("kWh/meal", cooktop_induction_kwh_per_meal,
                     _DEFAULTS["cooktop_induction_kwh_per_meal"], 0.6, 1.4, 0.1, fmt="{v:.1f}")
        if cooktop_swap_planned.value:
            _DetailCosts(cooktop_install_cost, cooktop_rebate)

    elif state == "electric":
        _DS("Current: Induction Cooktop")
        kwh = _est_induction(cooktop_induction_kwh_per_meal.value, cooktop_meals_per_week.value)
        solara.Markdown(f"~**{kwh:.0f} kWh/yr**")
        _DSl("kWh/meal", cooktop_induction_kwh_per_meal,
             _DEFAULTS["cooktop_induction_kwh_per_meal"], 0.6, 1.4, 0.1, fmt="{v:.1f}")
        _DSl("Meals/week", cooktop_meals_per_week, _DEFAULTS["cooktop_meals_per_week"],
             3, 21, 1, unit=" /wk")
        solara.Markdown("<small style='color:#2E7D32'>✓ Already electrified</small>")

    else:  # none
        with solara.Row(gap="0px", style="align-items:flex-start; flex-wrap:wrap"):
            with solara.Column(style=_LEFT_COL):
                _DS("Current: No Cooktop")
                solara.Text("No baseline cooktop.", style="font-size:0.85em; color:#888")
            with solara.Column(style=_RIGHT_COL):
                _DS("Adding: Induction Cooktop")
                kwh = _est_induction(cooktop_induction_kwh_per_meal.value,
                                     cooktop_meals_per_week.value)
                solara.Markdown(f"Est: **{kwh:.0f} kWh/yr**")
                _DSl("kWh/meal", cooktop_induction_kwh_per_meal,
                     _DEFAULTS["cooktop_induction_kwh_per_meal"], 0.6, 1.4, 0.1, fmt="{v:.1f}")
        if cooktop_swap_planned.value:
            _DetailCosts(cooktop_install_cost, cooktop_rebate)


@solara.component
def DryerDetail():
    """Dryer detail — two-column per §25.4.7."""
    state = dryer_starting_state.value

    with solara.Row(gap="8px", style=_TOP_ROW):
        with solara.Column(style="min-width:110px"):
            solara.Select("Starting state", value=dryer_starting_state,
                          values=["gas", "electric", "none"])
        if state != "electric":
            with solara.Column(style="min-width:70px"):
                solara.Checkbox(label="Plan swap", value=dryer_swap_planned)
        if state != "electric" and dryer_swap_planned.value:
            yr = dryer_swap_year.value
            cal_yr = sim_start_year.value + yr - 1
            with solara.Column(style="min-width:170px"):
                solara.SliderInt(f"Yr {yr} ({cal_yr})", value=dryer_swap_year, min=1, max=25)

    _ElecAmpsInput("HP dryer breaker A", dryer_amps)

    if state == "gas":
        with solara.Row(gap="0px", style="align-items:flex-start; flex-wrap:wrap"):
            with solara.Column(style=_LEFT_COL):
                _DS("Current: Gas Dryer")
                therms = _est_gas_dryer(dryer_gas_therms_per_cycle.value,
                                        dryer_loads_per_week.value)
                solara.Markdown(
                    f"~**{therms:.0f} therms/yr** ≈ {_kwh_eq(therms):,.0f} kWh-eq")
                _DSl("Therms/cycle", dryer_gas_therms_per_cycle,
                     _DEFAULTS["dryer_gas_therms_per_cycle"], 0.15, 0.35, 0.01, fmt="{v:.2f}")
                _DSl("Loads/week", dryer_loads_per_week, _DEFAULTS["dryer_loads_per_week"],
                     1, 14, 1, unit=" /wk")
            with solara.Column(style=_RIGHT_COL):
                _DS("Replacement: Heat Pump Dryer")
                kwh = _est_hp_dryer(dryer_hp_kwh_per_cycle.value, dryer_loads_per_week.value)
                solara.Markdown(f"~**{kwh:.0f} kWh/yr**")
                _DSl("kWh/cycle", dryer_hp_kwh_per_cycle,
                     _DEFAULTS["dryer_hp_kwh_per_cycle"], 1.2, 2.5, 0.1, fmt="{v:.1f}")
        if dryer_swap_planned.value:
            _DetailCosts(dryer_install_cost, dryer_rebate)

    elif state == "electric":
        _DS("Current: Heat Pump Dryer")
        kwh = _est_hp_dryer(dryer_hp_kwh_per_cycle.value, dryer_loads_per_week.value)
        solara.Markdown(f"~**{kwh:.0f} kWh/yr**")
        _DSl("kWh/cycle", dryer_hp_kwh_per_cycle, _DEFAULTS["dryer_hp_kwh_per_cycle"],
             1.2, 2.5, 0.1, fmt="{v:.1f}")
        _DSl("Loads/week", dryer_loads_per_week, _DEFAULTS["dryer_loads_per_week"],
             1, 14, 1, unit=" /wk")
        solara.Markdown("<small style='color:#2E7D32'>✓ Already electrified</small>")

    else:  # none
        with solara.Row(gap="0px", style="align-items:flex-start; flex-wrap:wrap"):
            with solara.Column(style=_LEFT_COL):
                _DS("Current: No Dryer")
                solara.Text("No baseline dryer.", style="font-size:0.85em; color:#888")
            with solara.Column(style=_RIGHT_COL):
                _DS("Adding: Heat Pump Dryer")
                kwh = _est_hp_dryer(dryer_hp_kwh_per_cycle.value, dryer_loads_per_week.value)
                solara.Markdown(f"Est: **{kwh:.0f} kWh/yr**")
                _DSl("kWh/cycle", dryer_hp_kwh_per_cycle,
                     _DEFAULTS["dryer_hp_kwh_per_cycle"], 1.2, 2.5, 0.1, fmt="{v:.1f}")
        if dryer_swap_planned.value:
            _DetailCosts(dryer_install_cost, dryer_rebate)


@solara.component
def ElecPanelDetail():
    """Electrical panel upgrade detail — single column per §25.4.8."""
    planned = panel_upgrade_planned.value

    with solara.Row(gap="8px", style=_TOP_ROW):
        solara.Checkbox(label="Plan 200A panel upgrade", value=panel_upgrade_planned)
        if planned:
            yr = panel_upgrade_year.value
            cal_yr = sim_start_year.value + yr - 1
            with solara.Column(style="min-width:170px"):
                solara.SliderInt(f"Yr {yr} ({cal_yr})", value=panel_upgrade_year, min=1, max=25)

    solara.HTML(tag="div", unsafe_innerHTML=(
        "<div style='font-size:0.85em; color:#666; margin-bottom:10px;'>"
        "Often required when adding an EV charger (L2) or heat pump to older "
        "homes with 100A panels. Pure capital cost — no energy savings modelled.</div>"
    ))
    # Current panel size — drives the Estimated Electrical Load assessment (Phase 3 §5)
    with solara.Column(style="max-width:220px; margin-bottom:8px"):
        solara.Select("Current panel size (A)", value=panel_amps, values=[100, 150, 200])
    _DSl("Install cost", panel_upgrade_cost, _DEFAULTS["panel_upgrade_cost"],
         2000, 10000, step=500, unit=" $")
    if planned:
        _DetailCosts(panel_upgrade_cost, panel_upgrade_rebate)


@solara.component
def BaseloadDetail():
    """Baseload & lights detail — single column per §25.4.9."""
    bl_before = compute_baseload_kwh(square_footage.value, num_bedrooms.value,
                                     baseload_constant_before.value)
    _DS("Current: Lights & Appliances")
    solara.Markdown(
        f"Est: **{bl_before:,.0f} kWh/yr** "
        f"({square_footage.value:,} sqft × 0.45 + {num_bedrooms.value} bed × 200 "
        f"+ {baseload_constant_before.value})"
    )
    _DSl("Always-on constant", baseload_constant_before,
         _DEFAULTS["baseload_constant_before"], 0, 1500, step=50, unit=" kWh/yr")
    # Effective A (Phase 3 §2.5.3) — informational; NOT used by PanelAssessor
    _eff_a = bl_before * 1000 / 8760 / 120
    solara.HTML(tag="div", unsafe_innerHTML=(
        f"<div style='font-size:0.82em; color:#455A64; margin-top:4px;"
        f" padding-top:4px; border-top:1px dashed #CFD8DC;'>"
        f"<strong>Electrical</strong>&nbsp;&nbsp;120 V · ~{_eff_a:.0f} A effective"
        f"<br><span style='color:#90A4AE; font-size:0.9em;'>"
        f"(avg across all circuits)</span></div>"
    ))
    solara.Markdown("---")
    with solara.Row(gap="8px", style="align-items:center; flex-wrap:wrap; padding:4px 0"):
        solara.Checkbox(label="Plan efficiency upgrade (LED, smart plugs…)",
                        value=baseload_swap_planned)
        if baseload_swap_planned.value:
            yr = baseload_swap_year.value
            cal_yr = sim_start_year.value + yr - 1
            with solara.Column(style="min-width:170px"):
                solara.SliderInt(f"Yr {yr} ({cal_yr})", value=baseload_swap_year, min=1, max=25)
    if baseload_swap_planned.value:
        bl_after = compute_baseload_kwh(square_footage.value, num_bedrooms.value,
                                        baseload_constant_after.value)
        saving           = bl_before - bl_after
        annual_saving_usd = saving * 0.386
        net_cost         = baseload_install_cost.value - baseload_rebate.value
        pb = (net_cost / annual_saving_usd) if annual_saving_usd > 0 else None
        _DSl("After-upgrade always-on", baseload_constant_after,
             _DEFAULTS["baseload_constant_after"], 0, 1500, step=50, unit=" kWh/yr")
        solara.Markdown(
            f"After: **{bl_after:,.0f} kWh/yr**  ·  "
            f"Save: **{saving:,.0f} kWh/yr ≈ ${annual_saving_usd:,.0f}/yr**  ·  "
            f"Payback: **{'~'+f'{pb:.1f} yrs' if pb else 'N/A'}**"
        )
        _DetailCosts(baseload_install_cost, baseload_rebate)


@solara.component
def HomeDetail():
    """Home profile detail — single column per §25.4.10."""
    _DS("Location & Home")
    solara.InputText("ZIP code", value=zip_code)
    solara.Select("Climate zone", value=climate_zone, values=_CZ_OPTIONS)
    solara.Select("Bedrooms", value=num_bedrooms, values=[1, 2, 3, 4, 5])
    solara.InputInt("Square footage", value=square_footage)
    solara.InputInt("Year built", value=year_built)
    solara.Markdown("---")
    _DS("Building Performance")
    solara.Select("Insulation quality", value=insulation_quality,
                  values=["poor", "average", "good"])
    ua = UA_MAP[insulation_quality.value]
    solara.HTML(tag="div", unsafe_innerHTML=(
        f"<div style='font-size:0.82em; color:#666; margin-top:4px;'>"
        f"UA = {ua} BTU/hr/°F  ·  Annual HDD = 1,910 (Bay Area TMY3)</div>"
    ))


@solara.component
def SolarDetail(model):
    """Solar + battery detail — two-column per §25.4.11."""
    planned = solar_planned.value
    gross = (
        (solar_panels_cost.value  if solar_include_panels.value  else 0)
        + (solar_battery_cost.value if solar_include_battery.value else 0)
        + (solar_install_cost_item.value if solar_include_install.value else 0)
    )
    net = gross - solar_rebate.value

    with solara.Row(gap="8px", style=_TOP_ROW):
        solara.Checkbox(label="Adding solar to my journey", value=solar_planned)
        if planned:
            yr = solar_install_year.value
            cal_yr = sim_start_year.value + yr - 1
            with solara.Column(style="min-width:170px"):
                solara.SliderInt(f"Install yr {yr} ({cal_yr})",
                                 value=solar_install_year, min=1, max=25)

    if not planned:
        solara.Text("Enable solar above to configure options.",
                    style="font-size:0.85em; color:#888")
        return

    with solara.Row(gap="0px", style="align-items:flex-start; flex-wrap:wrap"):
        with solara.Column(style=_LEFT_COL):
            _DS("Solar Panels")
            solara.Checkbox(label="Include solar panels (10 kW)", value=solar_include_panels)
            if solar_include_panels.value:
                solara.InputInt("Panel cost $", value=solar_panels_cost)
            solara.Checkbox(label="Include installation & permitting",
                            value=solar_include_install)
            if solar_include_install.value:
                solara.InputInt("Install cost $", value=solar_install_cost_item)
            with solara.Column(style="min-width:180px"):
                solara.SliderInt(
                    f"{solar_coverage_pct.value}% electricity covered",
                    value=solar_coverage_pct, min=0, max=100, step=5,
                )
            solara.Text("(Phase 3: auto-compute from system size + usage)",
                        style="font-size:0.78em; color:#888")

        with solara.Column(style=_RIGHT_COL):
            _DS("Battery Storage")
            solara.Checkbox(label="Include battery (13.5 kWh)", value=solar_include_battery)
            if solar_include_battery.value:
                solara.InputInt("Battery cost $", value=solar_battery_cost)
            else:
                solara.Text("No battery selected.", style="font-size:0.85em; color:#888")
            solara.Markdown("---")
            solara.Markdown(
                f"| Item | Amount |\n|--|--|\n"
                f"| Gross cost | **${gross:,}** |\n"
                f"| Rebate | **-${solar_rebate.value:,}** |\n"
                f"| **Net cost** | **${net:,}** |\n"
                f"| Lifespan | 25 years |"
            )
            if model is not None and model.journey_home.solar_savings_history:
                annual = model.journey_home.solar_savings_history[0]
                if annual > 0 and net > 0:
                    solara.Markdown(
                        f"Est. annual saving: **${annual:,.0f}/yr**  \n"
                        f"Est. payback: **~{net / annual:.1f} yrs**"
                    )

    with solara.Column(style=_COSTS_BOX):
        solara.HTML(tag="div", unsafe_innerHTML=(
            "<div style='font-weight:700; font-size:0.9em; color:#0D47A1;"
            " border-bottom:1px solid #C5CAE9; padding-bottom:4px;"
            " margin-bottom:8px;'>Costs &amp; Rebates</div>"
        ))
        with solara.Row(gap="12px", style="flex-wrap:wrap; align-items:center"):
            with solara.Column(style="min-width:120px"):
                solara.InputInt("Rebate $", value=solar_rebate)
            solara.HTML(tag="div", unsafe_innerHTML=(
                f"<div style='font-size:1.05em; font-weight:700; color:#1976D2;'>"
                f"Net ${net:,}</div>"
            ))


def _fuel_model_block(heading: str, color: str,
                       model_rv, cagr_rv, acc_cagr_rv,
                       model_options: list, cagr_max: int):
    """Fuel rate model section: toggle buttons + conditional CAGR or ACC-base slider."""
    solara.HTML(tag="div", unsafe_innerHTML=(
        f"<div style='font-weight:600; font-size:0.84em; color:{color};"
        " margin:8px 0 4px'>" + heading + "</div>"
    ))
    with solara.Row(gap="6px", style="flex-wrap:wrap"):
        for key, display in model_options:
            is_active = model_rv.value == key
            solara.Button(
                display,
                on_click=lambda k=key: model_rv.set(k),
                style=(
                    f"background:{color}; color:white; border:none;"
                    " border-radius:4px; padding:3px 10px; font-size:0.80em; cursor:pointer;"
                    if is_active else
                    "background:#F5F5F5; color:#444; border:1px solid #CCC;"
                    " border-radius:4px; padding:3px 10px; font-size:0.80em; cursor:pointer;"
                ),
            )
    if model_rv.value == "cagr_flat":
        solara.SliderInt(
            f"+{cagr_rv.value}%/yr",
            value=cagr_rv, min=0, max=cagr_max,
        )
    else:
        # ACC mode: expose base escalation slider
        solara.SliderInt(
            f"Base escalation (ACC shape applied on top): +{acc_cagr_rv.value}%/yr",
            value=acc_cagr_rv, min=0, max=cagr_max,
        )
        solara.HTML(tag="div", unsafe_innerHTML=(
            "<div style='font-size:0.75em; color:#546E7A; margin:1px 0 4px'>"
            "ACC shape redistributes costs within each year. "
            "This slider sets the overall rate trajectory.</div>"
        ))


@solara.component
def RatesDetail():
    """Rate scenarios detail panel."""
    _DS("Scenario A")
    _fuel_model_block("⚡ Electricity Rate Model", C_RATE_ELEC,
                       elec_rate_model_a, elec_cagr_pct_a, acc_elec_cagr_a,
                       [("cagr_flat", "CAGR Flat"), ("acc_shaped", "ACC-Shaped")], 15)
    _fuel_model_block("🔥 Gas Rate Model", C_RATE_GAS,
                       gas_rate_model_a, gas_cagr_pct_a, acc_gas_cagr_a,
                       [("cagr_flat", "CAGR Flat"), ("acc_seasonal", "ACC Seasonal")], 20)

    solara.HTML(tag="div", unsafe_innerHTML=(
        "<div style='border-top:1px solid #E0E0E0; margin:10px 0 6px'></div>"
    ))
    _DS("Timeline")
    solara.SliderInt(f"Years to model: {years.value}", value=years, min=5, max=30)

    solara.HTML(tag="div", unsafe_innerHTML=(
        "<div style='border-top:1px solid #E0E0E0; margin:10px 0 6px'></div>"
    ))
    solara.Checkbox(label="Compare two scenarios (A vs B)", value=comparison_mode)
    if comparison_mode.value:
        solara.HTML(tag="div", unsafe_innerHTML=(
            "<div style='font-size:0.80em; color:#888; margin:4px 0 2px'>"
            "Scenario A above — solid lines on charts</div>"
        ))
        _DS("Scenario B  (dashed lines)")
        _fuel_model_block("⚡ Electricity Rate Model", C_RATE_ELEC,
                           elec_rate_model_b, elec_cagr_pct_b, acc_elec_cagr_b,
                           [("cagr_flat", "CAGR Flat"), ("acc_shaped", "ACC-Shaped")], 15)
        _fuel_model_block("🔥 Gas Rate Model", C_RATE_GAS,
                           gas_rate_model_b, gas_cagr_pct_b, acc_gas_cagr_b,
                           [("cagr_flat", "CAGR Flat"), ("acc_seasonal", "ACC Seasonal")], 20)


# ── §25 Summary panel components ─────────────────────────────────────────────

@solara.component
def JourneyPlannerPanel():
    with solara.Column(classes=["card"]):
        with solara.Row(classes=["card-hd"]):
            _card_header_main("journey", "Your Electrification Journey", "journey_planner")
        with solara.Column(classes=["card-bd"], gap="8px"):
            HVACSummaryCard()
            WHSummaryCard()
            EVSummaryCard()
            CooktopSummaryCard()
            DryerSummaryCard()
            PanelSummaryCard()
            BaseloadSummaryCard()
            solara.HTML(tag="p", unsafe_innerHTML=(
                "<p style='font-size:.78em;color:var(--ink-3,#888);margin:4px 0 0'>"
                "Click ⋮ on any device to see full details. "
                "The Do-Nothing baseline preserves all current appliances.</p>"
            ))


@solara.component
def HomeProfilePanel():
    with solara.Column(classes=["card"]):
        with solara.Row(classes=["card-hd"]):
            _card_header_main("home", "Home &amp; Solar", "home_profile")
        with solara.Column(classes=["card-bd"], gap="8px"):
            HomeSummaryCard()
            SolarSummaryCard()


@solara.component
def EnergyPricesPanel():
    with solara.Column(classes=["card"]):
        with solara.Row(classes=["card-hd"]):
            _card_header_main("energy", "Energy &amp; Prices", "energy_prices")
        with solara.Column(classes=["card-bd"], gap="8px"):
            RatesSummaryCard()


# Social & Health icon — module-level so SetupGroup header can reuse it
_SOCIAL_IC = ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
              " stroke-linecap='round' stroke-linejoin='round'>"
              "<path d='M12 22C6.5 22 2 17.5 2 12S6.5 2 12 2s10 4.5 10 10-4.5 10-10 10z'/>"
              "<path d='M8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01'/></svg>")


@solara.component
def _SocialBody():
    """Social & Health Cost of Gas — card-bd content (two .device sub-cards)."""
    climate_on = social_climate_enabled.value
    health_on  = social_health_enabled.value
    total = (social_climate_rate.value if climate_on else 0.0) \
          + (social_health_rate.value  if health_on  else 0.0)

    _CLIMATE_IC = ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                   " stroke-linecap='round' stroke-linejoin='round'>"
                   "<path d='M12 2a7 7 0 017 7c0 5-7 13-7 13S5 14 5 9a7 7 0 017-7z'/>"
                   "<circle cx='12' cy='9' r='2.5'/></svg>")
    _HEALTH_IC  = ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                   " stroke-linecap='round' stroke-linejoin='round'>"
                   "<path d='M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78"
                   "l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z'/></svg>")

    with solara.Column(classes=["card-bd"], gap="8px"):
            # ── Climate Cost device card ──────────────────────────────────────
            with solara.Column(classes=["device"]):
                solara.HTML(tag="div", unsafe_innerHTML=(
                    f"<div class='device-hd'>"
                    f"<span class='di'>{_CLIMATE_IC}</span>"
                    f"<span class='dn'>Climate Cost</span>"
                    f"</div>"
                ))
                solara.Checkbox(label="Include CO₂ + methane cost", value=social_climate_enabled)
                if climate_on:
                    SliderWithDefault("Rate", social_climate_rate,
                                      _DEFAULTS["social_climate_rate"], 1.00, 2.00, 0.01,
                                      unit=" $/therm", fmt="{v:.2f}")
                    solara.HTML(tag="div", unsafe_innerHTML=(
                        "<div style='display:flex; justify-content:space-between;"
                        " font-size:0.72em; color:#90A4AE; margin-top:-2px;'>"
                        "<span>$1.00/therm</span><span>$2.00/therm</span></div>"
                    ))
                else:
                    solara.HTML(tag="div", unsafe_innerHTML=(
                        "<div style='font-size:0.80em; color:#AAAAAA;'>Not included</div>"
                    ))

            # ── Health Cost device card ───────────────────────────────────────
            with solara.Column(classes=["device"]):
                solara.HTML(tag="div", unsafe_innerHTML=(
                    f"<div class='device-hd'>"
                    f"<span class='di'>{_HEALTH_IC}</span>"
                    f"<span class='dn'>Health Cost</span>"
                    f"</div>"
                ))
                solara.Checkbox(label="Include air quality cost", value=social_health_enabled)
                if health_on:
                    SliderWithDefault("Rate", social_health_rate,
                                      _DEFAULTS["social_health_rate"], 0.50, 2.00, 0.01,
                                      unit=" $/therm", fmt="{v:.2f}")
                    solara.HTML(tag="div", unsafe_innerHTML=(
                        "<div style='display:flex; justify-content:space-between;"
                        " font-size:0.72em; color:#90A4AE; margin-top:-2px;'>"
                        "<span>$0.50/therm</span><span>$2.00/therm</span></div>"
                    ))
                else:
                    solara.HTML(tag="div", unsafe_innerHTML=(
                        "<div style='font-size:0.80em; color:#AAAAAA;'>Not included</div>"
                    ))

            # ── Total line ────────────────────────────────────────────────────
            if climate_on or health_on:
                solara.HTML(tag="div", unsafe_innerHTML=(
                    f"<div style='font-size:0.84em; color:#37474F; padding:4px 0;'>"
                    f"Total: <strong>${total:.2f}/therm</strong>"
                    f"<span style='color:#90A4AE;'> added to gas cost</span></div>"
                ))
            solara.HTML(tag="div", unsafe_innerHTML=(
                "<div style='font-size:0.74em; color:#90A4AE; font-style:italic;'>"
                "These costs do not appear on your utility bill — they represent damage "
                "to public health and the climate from burning gas.</div>"
            ))


# ── §25.6 Bottom zone routing ─────────────────────────────────────────────────

@solara.component
def DetailView(item: str, model):
    """Detail body — rendered inside the modal dialog."""
    with solara.Column(classes=["detail-body"], style="padding:4px 0"):
        if item == "hvac":
            HVACDetail()
        elif item == "water_heater":
            WaterHeaterDetail()
        elif item == "ev":
            EVDetail()
        elif item == "cooktop":
            CooktopDetail()
        elif item == "dryer":
            DryerDetail()
        elif item == "panel":
            ElecPanelDetail()
        elif item == "baseload":
            BaseloadDetail()
        elif item == "home":
            HomeDetail()
        elif item == "solar":
            SolarDetail(model)
        elif item == "rates":
            RatesDetail()


@solara.component
def BottomZone(model):
    """v2 — Setup group + Journey grid (device detail now renders in DetailDock)."""
    SetupGroup()
    JourneyGrid()


@solara.component
def DetailDock(model):
    """v2 — device-detail editor as an inline panel BELOW the charts (not a modal
    overlay), so the graphs stay visible and update live while sliders move."""
    dopen = detail_open.value
    if dopen is None:
        return

    _DETAIL_ICONS = {
        k: _DEVICE_ICONS.get(k, "")
        for k in ("hvac", "water_heater", "ev", "cooktop", "dryer",
                  "panel", "baseload", "home", "solar", "rates")
    }
    _DETAIL_HELP = {
        "hvac": "hvac", "water_heater": "water_heater", "ev": "ev_charger",
        "cooktop": "cooktop", "dryer": "dryer", "panel": "panel_upgrade",
        "baseload": "baseload", "home": "home_profile", "solar": "solar",
        "rates": "rates",
    }
    icon_svg = _DETAIL_ICONS.get(dopen, "")
    title    = _DETAIL_TITLES.get(dopen, "")
    help_key = _DETAIL_HELP.get(dopen, "")

    with solara.Column(classes=["card", "dock", "detail-dock"]):
        # Dock header — icon + title (flex:1) push [?] + Done to the right
        with solara.Row(classes=["modal-hd"]):
            if icon_svg:
                solara.HTML(tag="div", unsafe_innerHTML=(
                    f"<div class='modal-di'>{icon_svg}</div>"
                ))
            solara.HTML(tag="div", style="flex:1; min-width:0", unsafe_innerHTML=(
                f"<div class='modal-title'>{title}</div>"
            ))
            if help_key:
                HelpButton(help_key, style="width:26px;height:26px;font-size:0.82em")
            solara.Button(
                "✓ Done",
                on_click=lambda: detail_open.set(None),
                classes=["btn", "done"],
            )
        # Dock body
        with solara.Column(classes=["modal-bd", "detail-body"]):
            DetailView(dopen, model)


# ── Phase 3 redesign — masthead + verdict band ──────────────────────────────────

@solara.component
def Masthead():
    """Redesign masthead: preserved logo + one-line context pill + Reset/Help."""
    bl_kwh = compute_baseload_kwh(
        square_footage.value, num_bedrooms.value, baseload_constant_before.value
    )
    cz = climate_zone.value.replace("CZ", "").strip()
    context_html = (
        "<div class='context'>"
        "<span class='loc'>"
        "<svg viewBox='0 0 24 24' fill='currentColor'><path d='M12 2C8.1 2 5 5.1 5 9c0 "
        "5.2 7 13 7 13s7-7.8 7-13c0-3.9-3.1-7-7-7zm0 9.5A2.5 2.5 0 1112 6a2.5 2.5 0 010 "
        "5.5z'/></svg>San Jose, CA</span>"
        f"<span class='spec first'>ZIP <b class='mono'>{zip_code.value}</b></span>"
        f"<span class='spec'>CZ <b>{cz}</b></span>"
        f"<span class='spec'><b>{num_bedrooms.value}</b> bed</span>"
        f"<span class='spec'><b class='mono'>{square_footage.value:,}</b> sq ft</span>"
        f"<span class='spec'>Built <b class='mono'>{year_built.value}</b></span>"
        f"<span class='spec'>Baseload <b class='mono'>{bl_kwh:,.0f}</b> kWh/yr</span>"
        "</div>"
    )
    brand_inner = (
        f"<div class='brand-mark'>{_WHYWATT_ICON_SVG}</div>"
        "<div style='display:flex;flex-direction:column;line-height:1.1'>"
        "<div class='brand-name'>Why<b>Watt?</b></div>"
        "<div class='brand-tag'>Home Electrification Simulator</div>"
        "</div>"
    )
    with solara.Row(classes=["masthead"], style="gap:16px"):
        solara.HTML(tag="div", unsafe_innerHTML=brand_inner, classes=["brand"],
                    style="display:flex; align-items:center; flex-shrink:0")
        solara.HTML(tag="div", unsafe_innerHTML=context_html,
                    style="flex:1; min-width:0")
        with solara.Row(classes=["actions"], style="gap:8px; flex-shrink:0"):
            solara.Button("↺ Reset to defaults", on_click=reset_to_defaults,
                          classes=["btn"])
            solara.Button("? Help", on_click=lambda: open_help("index.html"),
                          classes=["btn", "primary"])


def _verdict_numbers(df, model):
    """Return (journey_cum, baseline_cum, payback_yr_or_None, net_delta, net_social)."""
    delta_vals   = df["Opex Delta"].values
    net_delta    = float(delta_vals[-1])
    payback_yr   = next((i + 1 for i, d in enumerate(delta_vals) if d > 0), None)
    journey_cum  = float(df["Journey Cum Cost"].iloc[-1])
    baseline_cum = float(df["Baseline Cum Cost"].iloc[-1])
    # Net social cost avoided by electrifying (baseline social − journey social)
    net_social = 0.0
    try:
        b_soc = (df.get("Baseline Social Climate", 0) + df.get("Baseline Social Health", 0))
        j_soc = (df.get("Journey Social Climate",  0) + df.get("Journey Social Health",  0))
        net_social = float((b_soc - j_soc).sum())
    except Exception:
        net_social = 0.0
    return journey_cum, baseline_cum, payback_yr, net_delta, net_social


@solara.component
def VerdictBand(df, n, model):
    """Hero result band: two comparison bars + payback/net call-out."""
    journey_cum, baseline_cum, payback_yr, net_delta, net_social = _verdict_numbers(df, model)
    hi = max(journey_cum, baseline_cum, 1.0)
    j_pct = max(8.0, journey_cum  / hi * 100)
    b_pct = max(8.0, baseline_cum / hi * 100)

    positive = net_delta >= 0
    call_bg   = "var(--positive-soft)" if positive else "var(--baseline-soft)"
    call_ink  = "var(--positive-ink)"  if positive else "var(--baseline-ink)"
    if payback_yr is not None:
        cal = sim_start_year.value + payback_yr - 1
        headline = f"Payback in year {payback_yr} ({cal})"
    else:
        headline = f"No payback within {n} yrs"
    big = f"{'+' if positive else '−'}${abs(net_delta):,.0f}"

    # Social cost line — only show if non-zero
    if net_social != 0.0:
        sc_sign     = "+" if net_social >= 0 else "−"
        sc_ink      = "var(--positive-ink)" if net_social >= 0 else "var(--baseline-ink)"
        sc_label_c  = "var(--positive-ink)" if net_social >= 0 else "var(--baseline-ink)"
        social_html = (
            f"<div class='verdict-social'>"
            f"<span class='sc-label' style='color:{sc_label_c}'>net social cost avoided&nbsp;</span>"
            f"<span class='sc-val' style='color:{sc_ink}'>{sc_sign}${abs(net_social):,.0f}</span>"
            f"</div>"
        )
    else:
        social_html = ""

    html = (
        "<section class='verdict'>"
        "<div class='verdict-bars'>"
        "<div class='cmp'>"
        "<div class='cmp-label'><div class='t'>Your Electrification Journey</div>"
        "<div class='s'>20-yr cumulative energy cost</div></div>"
        f"<div class='bar-track'><div class='bar-fill journey' style='width:{j_pct:.0f}%'>"
        f"<span class='v'>${journey_cum:,.0f}</span></div></div></div>"
        "<div class='cmp'>"
        "<div class='cmp-label'><div class='t'>Do-Nothing Baseline</div>"
        "<div class='s'>Keep gas appliances</div></div>"
        f"<div class='bar-track'><div class='bar-fill baseline' style='width:{b_pct:.0f}%'>"
        f"<span class='v'>${baseline_cum:,.0f}</span></div></div></div>"
        "</div>"
        f"<div class='verdict-call' style='background:{call_bg}'>"
        f"<div class='k' style='color:{call_ink}'>Payback</div>"
        f"<div class='headline'>{headline}</div>"
        f"<div class='big' style='color:{call_ink}'>{big}</div>"
        f"{social_html}"
        "</div></section>"
    )
    solara.HTML(tag="div", unsafe_innerHTML=html)


# ── v2 cockpit — merged results bar (payback · bars · panel guidance) ───────────

@solara.component
def Cockpit(df, n, model):
    """v2 §B — one .card.cockpit with three zones: payback call-out,
    comparison bars, electrical-panel guidance. Replaces the former
    VerdictBand + PanelLoadCallout panels."""
    # ── Zone 1 + 2 data — payback / net / bars ────────────────────────────────
    journey_cum, baseline_cum, payback_yr, net_delta, net_social = \
        _verdict_numbers(df, model)
    hi = max(journey_cum, baseline_cum, 1.0)
    j_pct = max(8.0, journey_cum  / hi * 100)
    b_pct = max(8.0, baseline_cum / hi * 100)

    positive = net_delta >= 0
    call_cls = "ck-call" if positive else "ck-call negative"
    if payback_yr is not None:
        cal = sim_start_year.value + payback_yr - 1
        eyebrow = f"PAYBACK · YR {payback_yr} ({cal})"
    else:
        eyebrow = f"NO PAYBACK · {n} YRS"
    big = f"{'+' if positive else '−'}${abs(net_delta):,.0f}"

    if net_social != 0.0:
        sc_sign  = "+" if net_social >= 0 else "−"
        sc_cls   = "sc-val" if net_social >= 0 else "sc-val neg"
        foot = (f"net social cost avoided "
                f"<b class='{sc_cls}'>{sc_sign}${abs(net_social):,.0f}</b>")
    else:
        foot = f"over {n} yrs vs. do nothing"

    call_html = (
        f"<div class='{call_cls}'>"
        f"<div class='k'>{eyebrow}</div>"
        f"<div class='big'>{big}</div>"
        f"<div class='foot'>{foot}</div>"
        f"</div>"
    )

    bars_html = (
        "<div class='ck-bars'>"
        "<div class='cmp'>"
        "<div class='cmp-label'><div class='t'>Your journey</div></div>"
        f"<div class='bar-track'><div class='bar-fill journey' style='width:{j_pct:.0f}%'>"
        f"<span class='v'>${journey_cum:,.0f}</span></div></div></div>"
        "<div class='cmp'>"
        "<div class='cmp-label'><div class='t'>Do nothing</div></div>"
        f"<div class='bar-track'><div class='bar-fill baseline' style='width:{b_pct:.0f}%'>"
        f"<span class='v'>${baseline_cum:,.0f}</span></div></div></div>"
        "</div>"
    )

    # ── Zone 3 data — electrical panel guidance ───────────────────────────────
    hc = model.home_config
    assessor = PanelAssessor(hc.square_footage, hc.panel_amps)
    timeline = assessor.journey_load_timeline(model.journey_home, model.n_years)
    if timeline:
        yr1   = timeline[0]
        peak  = max(timeline, key=lambda t: t.service_amps)
        panel = hc.panel_amps
        peak_cls, badge_tmpl = _PEAK_BADGE.get(peak.status, _PEAK_BADGE["green"])
        badge_text = badge_tmpl.format(p=panel)
        badge_icon = _CHECK_SVG if peak_cls == "peak-ok" else "⚠"
        guide_html = (
            "<div class='ck-guide'>"
            "<div class='guide-box-title'>ELECTRICAL PANEL GUIDANCE</div>"
            f"<div class='guide-metrics {peak_cls}'>"
            "<div class='gm'><span class='k'>Current</span>"
            f"<div class='row'><span class='num'>{yr1.service_amps:.0f}</span>"
            "<span class='unit'>A</span></div></div>"
            "<div class='gm peak'><span class='k'>Peak</span>"
            f"<div class='row'><span class='num'>{peak.service_amps:.0f}</span>"
            "<span class='unit'>A</span></div></div>"
            f"<span class='peak-badge'>{badge_icon} {badge_text}</span>"
            "</div></div>"
        )
    else:
        guide_html = "<div class='ck-guide'></div>"

    solara.HTML(tag="div", classes=["card", "cockpit"],
                unsafe_innerHTML=(call_html + bars_html + guide_html))


# ── v2 §D — "Setup your home" collapsible group ─────────────────────────────────

_CHEVRON_SVG = ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                " stroke-linecap='round' stroke-linejoin='round'><path d='M6 9l6 6 6-6'/></svg>")


def _chev_button(collapse_key: str):
    """Per-card collapse chevron (reuses .iconbtn reset + .chev-btn rotation)."""
    solara.Button(
        "",
        on_click=lambda k=collapse_key: _toggle_setup(k),
        classes=["iconbtn", "chev-btn"],
        children=[solara.HTML(tag="span", unsafe_innerHTML=_CHEVRON_SVG)],
    )


@solara.component
def _SetupCard(collapse_key: str, icon_svg: str, title: str, help_key: str, body):
    """One collapsible domain card inside the setup group."""
    collapsed = setup_collapsed.value.get(collapse_key, False)
    classes = ["card"] + (["is-collapsed"] if collapsed else [])
    with solara.Column(classes=classes):
        with solara.Row(classes=["card-hd"]):
            solara.HTML(tag="div", unsafe_innerHTML=(
                f"<div style='display:flex;align-items:center;gap:9px;flex:1;min-width:0'>"
                f"<span class='ic'>{icon_svg}</span>"
                f"<h3 style='margin:0;font-size:14px;font-weight:700;color:var(--ink,#1C2333);"
                f"white-space:nowrap;letter-spacing:-0.01em'>{title}</h3></div>"
            ))
            _chev_button(collapse_key)
            HelpButton(help_key)
        body()


@solara.component
def _HomeBody():
    with solara.Column(classes=["card-bd"], gap="8px"):
        HomeSummaryCard()
        SolarSummaryCard()


@solara.component
def _EnergyBody():
    with solara.Column(classes=["card-bd"], gap="8px"):
        RatesSummaryCard()


@solara.component
def SetupGroup():
    """v2 §D — tinted group wrapping the three assumption cards with collapse."""
    sc = setup_collapsed.value
    all_collapsed = all(sc.get(k, False) for k in ("home", "energy", "social"))
    group_cls = ["setup-group"] + (["collapsed-all"] if all_collapsed else [])

    label = "Expand all" if all_collapsed else "Collapse all"
    rot   = "transform:rotate(180deg);" if all_collapsed else ""
    btn_inner = (
        f"<span style='display:inline-flex;align-items:center;gap:7px'>{label}"
        f"<span style='display:inline-flex;{rot}transition:transform .18s ease'>"
        f"{_CHEVRON_SVG}</span></span>"
    )

    with solara.Column(classes=group_cls):
        # Group header
        with solara.Row(classes=["sg-hd"], style="align-items:center; gap:10px"):
            solara.HTML(tag="div", style="flex:1; min-width:0", unsafe_innerHTML=(
                f"<div style='display:flex;align-items:center;gap:10px;min-width:0'>"
                f"<span class='ic'>{_CARD_IC['home']}</span>"
                f"<h3 style='margin:0'>Setup your home</h3>"
                f"<span class='scope'>— Home &amp; Solar, Energy &amp; Prices, "
                f"Social &amp; Health collapse together</span></div>"
            ))
            solara.Button(
                "",
                on_click=lambda: _set_all_setup(not all_collapsed),
                classes=["collapse-all"],
                children=[solara.HTML(tag="span", unsafe_innerHTML=btn_inner)],
            )
        # 3-card grid (flex; collapsed-all CSS turns this into a chip row)
        with solara.Row(classes=["setup-grid"]):
            _SetupCard("home",   _CARD_IC["home"],   "Home &amp; Solar",
                       "home_profile",  _HomeBody)
            _SetupCard("energy", _CARD_IC["energy"], "Energy &amp; Prices",
                       "energy_prices", _EnergyBody)
            _SetupCard("social", _SOCIAL_IC,         "Social &amp; Health",
                       "social_cost",   _SocialBody)


# ── v2 §E — Electrification Journey 2-row appliance grid ─────────────────────────

def _subpanel_head(icon_svg: str, name: str, detail_key: str, help_key: str = ""):
    """Split-card subpanel header: icon+name (flex) + ? help + ⋮ details."""
    with solara.Row(style="align-items:center; gap:8px"):
        solara.HTML(tag="div", unsafe_innerHTML=(
            f"<div class='snm'><span class='di'>{icon_svg}</span>{name}</div>"
        ), style="flex:1; min-width:0")
        if help_key:
            HelpButton(help_key)
        solara.Button(
            "",
            on_click=lambda k=detail_key: detail_open.set(
                None if detail_open.value == k else k),
            classes=["iconbtn"],
            children=[solara.HTML(tag="span", unsafe_innerHTML=(
                "<svg viewBox='0 0 24 24' fill='currentColor'>"
                "<circle cx='5' cy='12' r='1.8'/>"
                "<circle cx='12' cy='12' r='1.8'/>"
                "<circle cx='19' cy='12' r='1.8'/></svg>"
            ))],
        )


@solara.component
def PanelBaseloadSplit():
    """v2 §E Change 5 — one .device card split into Electrical Panel | Baseload.
    Per project decision, inline controls are retained (not pushed to modal)."""
    panel_ic    = _DEVICE_ICONS.get("panel", "")
    baseload_ic = _DEVICE_ICONS.get("baseload", "")
    with solara.Column(classes=["device"], style="flex:1.3 1 360px"):
        with solara.Row(classes=["split2"]):
            with solara.Column(classes=["subpanel"]):
                _subpanel_head(panel_ic, "Electrical Panel", "panel", "panel_assessment")
                _PanelControls()
            with solara.Column(classes=["subpanel"]):
                _subpanel_head(baseload_ic, "Baseload", "baseload", "baseload")
                _BaseloadControls()


@solara.component
def JourneyGrid():
    """v2 §E — full-width journey card with two labeled appliance rows."""
    with solara.Column(classes=["card"]):
        with solara.Row(classes=["card-hd"]):
            solara.HTML(tag="div", unsafe_innerHTML=(
                f"<div style='display:flex;align-items:center;gap:9px;flex:1;min-width:0'>"
                f"<span class='ic'>{_CARD_IC['journey']}</span>"
                f"<h3 style='margin:0;font-size:14px;font-weight:700;color:var(--ink,#1C2333);"
                f"white-space:nowrap;letter-spacing:-0.01em'>Your Electrification Journey</h3>"
                f"<span class='count-pill'>6 devices</span></div>"
            ))
            HelpButton("journey_planner")
        with solara.Column(classes=["jbody"]):
            # Row 1 — MAJOR LOADS
            solara.HTML(tag="div", unsafe_innerHTML=(
                "<div class='jrow-label'>Major Loads</div>"))
            with solara.Row(classes=["jgrid"]):
                HVACSummaryCard()
                WHSummaryCard()
                EVSummaryCard()
            # Row 2 — OTHER APPLIANCES
            solara.HTML(tag="div", unsafe_innerHTML=(
                "<div class='jrow-label'>Other Appliances</div>"))
            with solara.Row(classes=["jgrid"]):
                CooktopSummaryCard()
                DryerSummaryCard()
                PanelBaseloadSplit()


# ── Main Page ──────────────────────────────────────────────────────────────────

@solara.component
def Page():
    solara.Title("WhyWatt?")
    solara.Style(_REDESIGN_CSS + "\n" + _LAYOUT_V2_CSS)   # design system + v2 layout

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
        elec_rate_model_a.value, elec_cagr_pct_a.value, acc_elec_cagr_a.value,
        gas_rate_model_a.value,  gas_cagr_pct_a.value,  acc_gas_cagr_a.value,
        comparison_mode.value,
        elec_rate_model_b.value, elec_cagr_pct_b.value, acc_elec_cagr_b.value,
        gas_rate_model_b.value,  gas_cagr_pct_b.value,  acc_gas_cagr_b.value,
        years.value, sim_start_year.value,
        wh_inlet_temp_f.value, wh_setpoint_f.value,
        gas_wh_tank_gallons.value, hpwh_tank_gallons.value, hpwh_ambient_location.value,
        # Phase 3 §5 — panel sizing inputs
        panel_amps.value, hvac_tonnage.value, ev_charger_amps.value,
        induction_amps.value, hpwh_amps.value, dryer_amps.value,
        # Phase 3 §6 — social & health cost of gas
        social_climate_enabled.value, social_climate_rate.value,
        social_health_enabled.value, social_health_rate.value,
    ])

    n = years.value

    with solara.Column(classes=["app"], gap="10px"):

        # Scoped CSS: chart header selectors — no underline, larger arrow, code badge
        solara.HTML(
            tag="div",
            unsafe_innerHTML=(
                "<style>"
                # tighten the chart card header + remove dead space around figures
                ".card-hd.chart-header-sel{padding:6px 10px 5px!important}"
                ".chart-header-sel .v-input{margin:0!important;padding:0!important}"
                ".chart-header-sel .v-input__control{min-height:32px!important}"
                ".chart-header-sel .v-input__slot{margin-bottom:0!important}"
                ".chart-header-sel .v-text-field__details{display:none!important}"
                ".chart-header-sel .v-messages{display:none!important}"
                ".chart-header-sel .v-input__icon--append .v-icon"
                "{font-size:28px!important}"
                ".chart-header-sel .v-input__slot::before,"
                ".chart-header-sel .v-input__slot::after"
                "{display:none!important}"
                ".chart-header-sel .v-input__slot"
                "{border:none!important;background:transparent!important;"
                "padding:0 4px 0 0!important;min-height:32px!important}"
                ".chart-code{font-family:var(--mono,'JetBrains Mono',monospace);"
                "font-size:11px;font-weight:700;color:var(--accent-ink,#3B6FD4);"
                "background:var(--accent-soft,#EBF0FB);border-radius:4px;"
                "padding:2px 6px;margin-right:4px;flex-shrink:0;"
                "align-self:center;letter-spacing:0.04em}"
                "</style>"
            ),
            style="display:none",
        )

        # §25.8.2/3 — suppress Vuetify default form margins in cards and detail body
        solara.HTML(
            tag="div",
            unsafe_innerHTML=(
                "<style>"
                ".summary-card .v-input{margin-bottom:0!important}"
                ".summary-card .v-text-field{margin-top:0!important}"
                ".summary-card .v-input__details{min-height:0!important;padding:0!important}"
                ".summary-card .v-messages{min-height:0!important}"
                ".summary-card .v-slider{margin-top:0!important;margin-bottom:0!important}"
                ".summary-card .v-checkbox{margin-top:0!important;margin-bottom:0!important}"
                ".summary-card .v-select{margin-top:0!important}"
                ".device .v-input{margin-bottom:0!important}"
                ".device .v-text-field{margin-top:0!important}"
                ".device .v-input__details{min-height:0!important;padding:0!important}"
                ".device .v-messages{min-height:0!important}"
                ".device .v-slider{margin-top:0!important;margin-bottom:0!important}"
                ".device .v-checkbox{margin-top:0!important;margin-bottom:0!important}"
                ".device .v-select{margin-top:0!important}"
                ".panel .v-input{margin-bottom:0!important}"
                ".panel .v-text-field{margin-top:0!important}"
                ".panel .v-input__details{min-height:0!important;padding:0!important}"
                ".panel .v-messages{min-height:0!important}"
                ".panel .v-slider{margin-top:0!important;margin-bottom:0!important}"
                ".panel .v-checkbox{margin-top:0!important;margin-bottom:0!important}"
                ".panel .v-select{margin-top:0!important}"
                ".v-col.card{padding:0!important;display:flex!important;flex-direction:column!important}"
                ".v-col.col{padding:0!important}"
                ".v-row.deck{margin:0!important;gap:var(--gap,16px)!important;flex-wrap:nowrap!important}"
                ".v-row.card-hd{margin:0!important;flex-wrap:nowrap!important}"
                ".card-hd>.v-col{padding:0!important;flex:0 0 auto!important;max-width:none!important}"
                ".card-hd>.v-col:first-child{flex:1 1 auto!important}"
                ".v-col.card-bd{padding:0!important}"
                ".v-col.panel-bd{padding:0!important}"
                ".v-col.panel{padding:0!important;display:flex!important;flex-direction:column!important}"
                "@media(max-width:860px){.v-row.deck{flex-wrap:wrap!important}}"
                ".deck{display:flex!important;gap:var(--gap,16px);align-items:start}"
                ".col{display:flex;flex-direction:column;gap:var(--gap,16px);flex:1}"
                ".card{background:var(--surface,#fff)!important;border:1px solid var(--border,#e2e5ed)!important;"
                "border-radius:var(--r-lg,14px)!important;box-shadow:var(--shadow-sm)!important;"
                "overflow:hidden!important}"
                ".card-hd{display:flex!important;align-items:center!important;gap:9px!important;"
                "padding:13px 16px!important;border-bottom:1px solid var(--border-soft,#eaedf3)!important;"
                "background:var(--surface,#fff)!important}"
                ".card-hd .ic{width:26px!important;height:26px!important;border-radius:7px!important;"
                "flex-shrink:0!important;display:grid!important;place-items:center!important;"
                "background:var(--accent-soft,#EEF2FC)!important;color:var(--accent-ink,#3355B5)!important}"
                ".card-hd .ic svg{width:15px!important;height:15px!important}"
                ".card-bd{padding:var(--pad,16px)!important}"
                ".panel{display:flex!important;flex-direction:column!important}"
                ".panel+.panel{border-top:1px solid var(--border-soft,#eaedf3)!important}"
                ".panel-hd{display:flex!important;align-items:center!important;gap:8px!important;"
                "padding:12px 16px!important}"
                ".panel-hd .ic{width:22px!important;height:22px!important;border-radius:6px!important;"
                "flex-shrink:0!important;display:grid!important;place-items:center!important;"
                "background:var(--surface-3,#f0f2f7)!important;color:var(--ink-2,#4a5568)!important}"
                ".panel-hd .ic svg{width:13px!important;height:13px!important}"
                ".panel-hd h4{font-size:13px!important;font-weight:700!important;"
                "color:var(--ink,#1C2333)!important;flex:1!important;margin:0!important}"
                ".panel-bd{padding:0 16px 15px!important;display:flex!important;"
                "flex-direction:column!important;gap:10px!important}"
                ".device{border:1px solid var(--border,#e2e5ed)!important;"
                "border-radius:var(--r,11px)!important;padding:13px!important;"
                "background:var(--surface-2,#F4F6FB)!important;"
                "display:flex!important;flex-direction:column!important;gap:10px!important}"
                ".device-hd{display:flex!important;align-items:center!important;gap:8px!important}"
                ".device-hd .di{display:inline-flex!important;color:var(--journey-ink,#3355B5)!important}"
                ".device-hd .di svg{width:15px!important;height:15px!important}"
                ".device-hd .dn{font-size:13px!important;font-weight:700!important;"
                "color:var(--ink,#1C2333)!important;flex:1!important}"
                ".iconbtn{background:none!important;border:none!important;box-shadow:none!important;"
                "min-width:24px!important;width:24px!important;height:24px!important;"
                "padding:0!important;cursor:pointer;color:var(--ink-4,#999)}"
                ".iconbtn svg{width:15px!important;height:15px!important;display:block}"
                ".detail-body .v-input{margin-bottom:2px!important}"
                ".detail-body .v-input__details{min-height:0!important}"
                ".detail-body .v-slider{margin-top:4px!important;margin-bottom:2px!important}"
                ".device .v-input__slot::before,.panel-bd .v-input__slot::before,"
                ".card-bd .v-input__slot::before,.detail-body .v-input__slot::before"
                "{display:none!important}"
                ".device .v-input__slot::after,.panel-bd .v-input__slot::after,"
                ".card-bd .v-input__slot::after,.detail-body .v-input__slot::after"
                "{display:none!important}"
                ".device .v-input__slot,.panel-bd .v-input__slot,.card-bd .v-input__slot"
                "{border:1px solid var(--border,#e2e5ed)!important;"
                "border-radius:6px!important;padding:0 8px!important;"
                "background:var(--surface,#fff)!important;min-height:32px!important}"
                ".device .v-select .v-input__slot,.panel-bd .v-select .v-input__slot,"
                ".card-bd .v-select .v-input__slot"
                "{padding:0 4px 0 8px!important}"
                ".device .v-input__details,.panel-bd .v-input__details,.card-bd .v-input__details"
                "{min-height:0!important;padding:0!important}"
                ".device .v-messages,.panel-bd .v-messages,.card-bd .v-messages"
                "{min-height:0!important}"
                ".cost-field .v-text-field__slot input{font-size:0.82em!important;"
                "font-family:var(--mono,monospace)!important;padding:4px 0!important}"
                ".cost-field label.v-label{font-size:0.72em!important;top:8px!important}"
                ".device .v-row>.v-col{align-self:center!important;padding-top:0!important;padding-bottom:0!important}"
                ".device .v-input--checkbox{margin-top:0!important;padding-top:0!important}"
                ".device .v-input--checkbox .v-input__control{height:32px!important;display:flex!important;align-items:center!important}"
                ".device .v-select .v-input__control{min-height:32px!important}"
                ".modal-hd{display:flex!important;align-items:center;gap:8px;"
                "padding:14px 18px;border-bottom:1px solid var(--border,#e2e5ed);"
                "position:sticky;top:0;background:var(--surface,#fff);z-index:1}"
                ".modal-di{width:28px;height:28px;background:var(--journey,#3B6FD4);"
                "border-radius:6px;display:flex;align-items:center;justify-content:center;color:#fff}"
                ".modal-di svg{width:18px;height:18px}"
                ".modal-title{flex:1;font-size:1em;font-weight:700;color:var(--ink,#1C2333)}"
                ".modal-bd{padding:16px 18px;overflow-y:auto}"
                ".btn.done{background:var(--positive,#2E7D32)!important;color:#fff!important;"
                "border:none!important;border-radius:6px!important;padding:4px 14px!important;"
                "font-size:.84em!important;font-weight:600!important;cursor:pointer!important}"
                ".foot{margin-top:16px;padding:10px 14px;"
                "border-top:1px solid var(--border,#e2e5ed);"
                "background:var(--surface-2,#F4F6FB);border-radius:0 0 8px 8px}"
                # ── v2 layout: neutralize Vuetify v-col/v-row wrappers ──────────
                ".v-col.cockpit{padding:0!important;margin:0!important}"
                ".v-col.setup-group{padding:16px!important;margin:0!important;"
                "display:flex!important;flex-direction:column!important}"
                ".v-row.sg-hd{margin:0!important;flex-wrap:nowrap!important}"
                ".v-row.setup-grid{margin:0!important;display:flex!important;"
                "flex-wrap:wrap!important;gap:16px!important}"
                ".v-row.setup-grid>.v-col{padding:0!important}"
                ".v-col.jbody{padding:var(--pad,16px)!important;margin:0!important;"
                "display:flex!important;flex-direction:column!important;gap:14px!important}"
                ".v-row.jgrid{margin:0!important;display:flex!important;"
                "flex-wrap:wrap!important;gap:14px!important}"
                ".v-row.jgrid>.v-col{padding:0!important}"
                ".v-row.split2{margin:0!important;display:grid!important;"
                "grid-template-columns:1fr 1fr!important}"
                ".v-row.split2>.v-col{padding:0!important}"
                ".v-col.subpanel>.v-row{margin:0!important}"
                ".setup-grid>.card,.jgrid>.device{margin:0!important}"
                # collapse-all button: beat Vuetify .v-btn--default sizing
                ".v-btn.collapse-all{height:26px!important;min-height:26px!important;"
                "min-width:0!important;padding:0 9px!important}"
                "</style>"
            ),
            style="display:none",
        )

        # ── Masthead (Phase 3 redesign §A) ──────────────────────────────────────
        Masthead()

        # ── Cockpit — merged payback · bars · panel guidance (v2 §B) ────────────
        Cockpit(df, n, model)

        # ── Dual chart panes ─────────────────────────────────────────────────────
        with solara.Row(gap="8px", style="align-items:stretch"):
            with solara.Column(classes=["card"],
                               style="flex:1; min-width:300px; overflow:hidden"):
                with solara.Row(classes=["card-hd", "chart-header-sel"]):
                    solara.HTML(
                        tag="span",
                        unsafe_innerHTML=(
                            f"<code class='chart-code'>"
                            f"{CHART_CODES.get(chart_left.value, '')}"
                            f"</code>"
                        ),
                        style="flex-shrink:0",
                    )
                    solara.Select("", value=chart_left, values=CHART_OPTIONS)
                    ChartHelpButton(chart_left.value)
                with solara.Column(style="padding:0 2px 2px"):
                    ChartPane(chart_left.value, model, df, n)
            with solara.Column(classes=["card"],
                               style="flex:1; min-width:300px; overflow:hidden"):
                with solara.Row(classes=["card-hd", "chart-header-sel"]):
                    solara.HTML(
                        tag="span",
                        unsafe_innerHTML=(
                            f"<code class='chart-code'>"
                            f"{CHART_CODES.get(chart_right.value, '')}"
                            f"</code>"
                        ),
                        style="flex-shrink:0",
                    )
                    solara.Select("", value=chart_right, values=CHART_OPTIONS)
                    ChartHelpButton(chart_right.value)
                with solara.Column(style="padding:0 2px 2px"):
                    ChartPane(chart_right.value, model, df, n)

        # ── Series key strip (legend + scenario eyebrow) ─────────────────────────
        with solara.Row(style="align-items:center; gap:24px"):
            leg = (
                f"<span style='color:{_CC_B};font-weight:bold'>● Do nothing (A)</span>"
                f"&nbsp;&nbsp;"
                f"<span style='color:{_CC_J};font-weight:bold'>● Your journey (A)</span>"
            )
            if comparison_mode.value:
                leg += (
                    f"&nbsp;&nbsp;"
                    f"<span style='color:{_CC_B};opacity:0.6;font-weight:bold'>┅ Do nothing (B)</span>"
                    f"&nbsp;&nbsp;"
                    f"<span style='color:{_CC_J};opacity:0.6;font-weight:bold'>┅ Your journey (B)</span>"
                )
            solara.HTML(tag="div", unsafe_innerHTML=leg, style="flex:1; min-width:0")
            solara.HTML(tag="div", unsafe_innerHTML=(
                "<span class='scenario-eyebrow'>Adjust the scenario below</span>"
            ))

        # ── Inline docks — Help / Device detail render here, BELOW the charts ────
        #    (sliders inside still drive run_simulation, so the graphs above
        #     update live instead of being hidden behind a modal overlay).
        HelpDock()
        DetailDock(model)

        # ── Bottom zone — Setup group + Journey grid ───────────────────────────
        BottomZone(model)

        # ── Footer — ECHo branding ──────────────────────────────────────────────
        echo_svg      = _read_svg(_ECHO_LOGO,  height_px=32)
        echo_icon_svg = _read_svg(_ECHO_ICON, height_px=32)
        with solara.Row(classes=["foot"], style="align-items:center; gap:12px"):
            if echo_svg:
                solara.HTML(tag="div", unsafe_innerHTML=echo_svg,
                            style="display:flex; align-items:center; flex-shrink:0")
            elif echo_icon_svg:
                solara.HTML(tag="div", unsafe_innerHTML=echo_icon_svg,
                            style="display:flex; align-items:center; flex-shrink:0")
            solara.HTML(tag="span", unsafe_innerHTML=(
                "<span style='font-size:.8em;color:#546E7A;flex:1'>"
                "Estimates are illustrative — adjust assumptions to match your home. "
                "Supported by the <strong>Electrification Collaboration</strong>."
                "</span>"
            ))
            solara.HTML(tag="div", unsafe_innerHTML=(
                "<span style='background:#0D47A1;color:#fff;border-radius:6px;"
                "padding:3px 10px;font-size:.74em;font-weight:700;"
                "white-space:nowrap'>WhyWatt? v2.0</span>"
            ))
