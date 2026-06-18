"""ui/state.py — all Solara reactive state, defaults, and reset (Phase 4.5).

The single home for the app's ~148 module-level reactives plus _DEFAULTS and
reset_to_defaults(). Moved verbatim from app.py — no behavior change. Every UI module
imports these by name (`from ui.state import *`), so all modules share ONE reactive
instance per cell (Phase 4.5 invariant #1).
"""
import solara

# ── Defaults (single source of truth for reset) ──────────────────────────────
_DEFAULTS = {
    # Home profile
    "zip_code":               "95112",
    "climate_zone":           "CZ4",
    "climate_trend":          "none",
    "num_bedrooms":           3,
    "square_footage":         1800,
    "year_built":             1985,
    "insulation_quality":     "average",
    "panel_amps":             200,
    "panel_calc_method":      "optional",   # NEC 220.82 optional (default) | standard
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
    # Journey — EV Charger (hardware only — CapExOnlySlot)
    "ev_starting_state":      "none",
    "ev_swap_planned":        False,
    "ev_swap_year":           2,
    "ev_install_cost":        800,
    "ev_rebate":              0,
    # Journey — Transportation (§3)
    "transport_gasoline_miles":      12_000,
    "transport_ice_miles_after":     0,
    "transport_mpg":                 28.0,
    "transport_ev_miles_now":        0,
    "transport_plan_electric_miles": 12_000,
    "transport_ev_eff":              3.5,
    "transport_charging_eff":        0.88,
    "transport_pct_home_after":      0.85,
    "external_ev_price_per_kwh":     0.25,
    "external_ev_escalation_pct":    3,
    # Gasoline price model (§3)
    "gasoline_price":                    4.50,
    "gasoline_escalation_pct":           0,
    "gasoline_climate_enabled":          True,
    "gasoline_climate_cost_per_gallon":  1.69,
    "gasoline_health_enabled":           True,
    "gasoline_health_cost_per_gallon":   0.75,
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
    "hvac_furnace_age":              10,
    "hvac_baseline_lifespan":        20,
    "hvac_baseline_replace_cost":    6000,
    "hvac_ac_seer":                  14,
    "hvac_ac_age":                   7,
    # WH detail specs
    "wh_gas_age":                    10,
    "wh_baseline_lifespan":          12,
    "wh_baseline_replace_cost":      1200,
    "hw_daily_gallons":              65,
    "gas_wh_tank_gallons":           50,
    "hpwh_tank_gallons":             65,
    "hpwh_ambient_location":         "conditioned",
    "wh_inlet_temp_f":               60,
    "wh_setpoint_f":                 120,
    # Dryer detail specs
    "dryer_gas_therms_per_cycle":    0.22,
    "dryer_loads_per_week":          5,
    "dryer_hp_kwh_per_cycle":        1.8,
    "dryer_age":                     10,
    "dryer_baseline_lifespan":       15,
    "dryer_baseline_replace_cost":   800,
    # Cooktop detail specs
    "cooktop_gas_therms_per_meal":    0.05,
    "cooktop_meals_per_week":         14,
    "cooktop_induction_kwh_per_meal": 0.9,
    "cooktop_age":                    10,
    "cooktop_baseline_lifespan":      20,
    "cooktop_baseline_replace_cost":  1000,
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
    "solar_planned":         False,
    "solar_install_year":    1,
    "solar_panels":          15,
    "solar_kw_per_panel":    0.42,
    "solar_specific_yield":  1500,
    "solar_battery_enabled": True,
    "solar_battery_kwh":     13.5,
    "solar_scf":             80,
    "solar_nem_mode":        "nbt",
    "solar_nbc":             0.025,
    "solar_system_cost":     30000,
    "solar_rebate":          0,
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
    "chart_right":            "Journey Timeline",
    "device_chart_home":      "journey",
    "acc_shape_year":         1,
    "detail_open":            None,
}

# ── Reactive state (initialised from _DEFAULTS) ────────────────────────────────

# Home profile
zip_code           = solara.reactive("95112")
climate_zone       = solara.reactive("CZ4")    # display only — resolved live from zip_code
climate_trend      = solara.reactive("none")   # §1.5: "none" | "rcp45" | "rcp85"
num_bedrooms       = solara.reactive(3)
square_footage     = solara.reactive(1800)
year_built         = solara.reactive(1985)
insulation_quality = solara.reactive("average")
panel_amps         = solara.reactive(200)        # Phase 3 §5 — service size 100/150/200
panel_calc_method  = solara.reactive("optional") # NEC load calc: "optional" (220.82) | "standard"

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
hvac_furnace_age             = solara.reactive(10)    # yrs — existing furnace age
hvac_baseline_lifespan       = solara.reactive(20)    # yrs — gas furnace expected lifespan
hvac_baseline_replace_cost   = solara.reactive(6000)  # $ — in-kind gas furnace replacement
hvac_ac_seer                 = solara.reactive(14)    # existing CentralAC SEER
hvac_ac_age                  = solara.reactive(7)     # yrs

# Water Heater detail specs
wh_gas_age                   = solara.reactive(10)    # yrs — existing WH age
wh_baseline_lifespan         = solara.reactive(12)    # yrs — gas WH expected lifespan
wh_baseline_replace_cost     = solara.reactive(1200)  # $ — in-kind gas WH replacement
hw_daily_gallons             = solara.reactive(65)    # gal/day
hw_gallons_user_override     = solara.reactive(False)
gas_wh_tank_gallons          = solara.reactive(50)    # gal
hpwh_tank_gallons            = solara.reactive(65)    # gal
hpwh_ambient_location        = solara.reactive("conditioned")
wh_inlet_temp_f              = solara.reactive(60)    # °F
wh_setpoint_f                = solara.reactive(120)   # °F

# Dryer detail specs
dryer_gas_therms_per_cycle   = solara.reactive(0.22)
dryer_loads_per_week         = solara.reactive(5)
dryer_hp_kwh_per_cycle       = solara.reactive(1.8)
dryer_age                    = solara.reactive(10)    # yrs — existing dryer age
dryer_baseline_lifespan      = solara.reactive(15)    # yrs — gas dryer expected lifespan
dryer_baseline_replace_cost  = solara.reactive(800)   # $ — in-kind gas dryer replacement

# Cooktop detail specs
cooktop_gas_therms_per_meal    = solara.reactive(0.05)
cooktop_meals_per_week         = solara.reactive(14)
cooktop_induction_kwh_per_meal = solara.reactive(0.9)
cooktop_age                      = solara.reactive(10)    # yrs — existing cooktop age
cooktop_baseline_lifespan        = solara.reactive(20)    # yrs — gas cooktop expected lifespan
cooktop_baseline_replace_cost    = solara.reactive(1000)  # $ — in-kind gas cooktop replacement

# Panel upgrade
panel_upgrade_planned = solara.reactive(False)
panel_upgrade_year    = solara.reactive(1)      # install in year 1 if planned
panel_upgrade_cost    = solara.reactive(3000)   # slider 2000–10000
panel_upgrade_rebate  = solara.reactive(0)

# EV detail specs (retained for backward compat; not used in Transportation slot)
ev_miles_per_year      = solara.reactive(7000)   # mi/yr
ev_kwh_per_mile        = solara.reactive(0.30)   # kWh/mi
ev_charging_efficiency = solara.reactive(0.90)   # 0–1

# Transportation (§3) — Wave 3 two-slot model (§3.6)
transport_gasoline_miles      = solara.reactive(12_000)   # ICE miles/yr now (both scenarios)
transport_ice_miles_after     = solara.reactive(0)        # ICE miles/yr after switch (journey)
transport_mpg                 = solara.reactive(28.0)
transport_ev_miles_now        = solara.reactive(0)        # existing EV miles/yr today (Do Nothing)
transport_plan_electric_miles = solara.reactive(12_000)   # EV miles/yr after switch (journey)
transport_ev_eff              = solara.reactive(3.5)     # mi/kWh battery-out
transport_charging_eff        = solara.reactive(0.88)
transport_pct_home_after      = solara.reactive(0.85)    # fraction charged at home post-L2 (§3.13)

# External (public/workplace) EV charging price model (§3.13)
external_ev_price_per_kwh     = solara.reactive(0.25)    # $/kWh
external_ev_escalation_pct    = solara.reactive(3)       # % per year real change

# Gasoline price model (§3)
gasoline_price                   = solara.reactive(4.50)
gasoline_escalation_pct          = solara.reactive(0)       # % per year real change
gasoline_climate_enabled         = solara.reactive(True)
gasoline_climate_cost_per_gallon = solara.reactive(1.69)    # $/gal @ $190/ton SCC
gasoline_health_enabled          = solara.reactive(True)
gasoline_health_cost_per_gallon  = solara.reactive(0.75)

# Solar + Battery (§8)
solar_planned          = solara.reactive(False)
solar_install_year     = solara.reactive(1)
solar_panels           = solara.reactive(15)       # primary sizing control
solar_kw_per_panel     = solara.reactive(0.42)     # detail: standard=0.42, premium=0.50
solar_specific_yield   = solara.reactive(1500)     # detail: kWh/kW/yr (PVWatts typical CA)
solar_battery_enabled  = solara.reactive(True)     # On = NEM 3.0 default
solar_battery_kwh      = solara.reactive(13.5)     # detail: one Powerwall-class unit
solar_scf              = solara.reactive(80)       # self-consumption %; 80 w/battery, 35 solar-only
solar_nem_mode         = solara.reactive("nbt")    # "nbt" (NEM 3.0) | "nem2" (existing)
solar_nbc              = solara.reactive(0.025)    # $/kWh NBC for NEM 2.0 only
solar_system_cost      = solara.reactive(30000)    # total installed cost from contractor quote
solar_rebate           = solara.reactive(0)

# Device chart home selector (shared by both device chart types)
device_chart_home = solara.reactive("journey")   # "journey" | "baseline"

# ACC Rate Shape chart — year selector (chart-only, NOT a sim dep)
acc_shape_year = solara.reactive(1)

# Pricing & timeline
# §2 per-fuel rate model — "cagr_flat" (= My Utility, EIA per-utility from ZIP) |
# "ca_average" (EIA statewide) | "acc_shaped"/"acc_seasonal" (ACC). The CAGR slider applies
# to both EIA modes and is seeded from each utility's EIA historical CAGR (see EnergyPrices).
elec_rate_model_a = solara.reactive("cagr_flat")
elec_cagr_pct_a   = solara.reactive(7)
acc_elec_cagr_a   = solara.reactive(7)            # base escalation used when acc_shaped
gas_rate_model_a  = solara.reactive("cagr_flat")
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
chart_right = solara.reactive("Journey Timeline")

# Detail view state (§25)
detail_open = solara.reactive(None)   # None | "hvac" | "water_heater" | "ice" | "ev" | "cooktop" | "dryer" | "home" | "solar" | "rates"

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
    climate_trend.set(_DEFAULTS["climate_trend"])
    num_bedrooms.set(_DEFAULTS["num_bedrooms"])
    square_footage.set(_DEFAULTS["square_footage"])
    year_built.set(_DEFAULTS["year_built"])
    insulation_quality.set(_DEFAULTS["insulation_quality"])
    panel_amps.set(_DEFAULTS["panel_amps"])
    panel_calc_method.set(_DEFAULTS["panel_calc_method"])
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
    hvac_baseline_lifespan.set(_DEFAULTS["hvac_baseline_lifespan"])
    hvac_baseline_replace_cost.set(_DEFAULTS["hvac_baseline_replace_cost"])
    hvac_ac_seer.set(_DEFAULTS["hvac_ac_seer"])
    hvac_ac_age.set(_DEFAULTS["hvac_ac_age"])
    wh_gas_age.set(_DEFAULTS["wh_gas_age"])
    wh_baseline_lifespan.set(_DEFAULTS["wh_baseline_lifespan"])
    wh_baseline_replace_cost.set(_DEFAULTS["wh_baseline_replace_cost"])
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
    dryer_age.set(_DEFAULTS["dryer_age"])
    dryer_baseline_lifespan.set(_DEFAULTS["dryer_baseline_lifespan"])
    dryer_baseline_replace_cost.set(_DEFAULTS["dryer_baseline_replace_cost"])
    cooktop_gas_therms_per_meal.set(_DEFAULTS["cooktop_gas_therms_per_meal"])
    cooktop_meals_per_week.set(_DEFAULTS["cooktop_meals_per_week"])
    cooktop_induction_kwh_per_meal.set(_DEFAULTS["cooktop_induction_kwh_per_meal"])
    cooktop_age.set(_DEFAULTS["cooktop_age"])
    cooktop_baseline_lifespan.set(_DEFAULTS["cooktop_baseline_lifespan"])
    cooktop_baseline_replace_cost.set(_DEFAULTS["cooktop_baseline_replace_cost"])
    panel_upgrade_planned.set(_DEFAULTS["panel_upgrade_planned"])
    panel_upgrade_year.set(_DEFAULTS["panel_upgrade_year"])
    panel_upgrade_cost.set(_DEFAULTS["panel_upgrade_cost"])
    panel_upgrade_rebate.set(_DEFAULTS["panel_upgrade_rebate"])
    ev_miles_per_year.set(_DEFAULTS["ev_miles_per_year"])
    ev_kwh_per_mile.set(_DEFAULTS["ev_kwh_per_mile"])
    ev_charging_efficiency.set(_DEFAULTS["ev_charging_efficiency"])
    transport_gasoline_miles.set(_DEFAULTS["transport_gasoline_miles"])
    transport_ice_miles_after.set(_DEFAULTS["transport_ice_miles_after"])
    transport_mpg.set(_DEFAULTS["transport_mpg"])
    transport_ev_miles_now.set(_DEFAULTS["transport_ev_miles_now"])
    transport_plan_electric_miles.set(_DEFAULTS["transport_plan_electric_miles"])
    transport_ev_eff.set(_DEFAULTS["transport_ev_eff"])
    transport_charging_eff.set(_DEFAULTS["transport_charging_eff"])
    transport_pct_home_after.set(_DEFAULTS["transport_pct_home_after"])
    external_ev_price_per_kwh.set(_DEFAULTS["external_ev_price_per_kwh"])
    external_ev_escalation_pct.set(_DEFAULTS["external_ev_escalation_pct"])
    gasoline_price.set(_DEFAULTS["gasoline_price"])
    gasoline_escalation_pct.set(_DEFAULTS["gasoline_escalation_pct"])
    gasoline_climate_enabled.set(_DEFAULTS["gasoline_climate_enabled"])
    gasoline_climate_cost_per_gallon.set(_DEFAULTS["gasoline_climate_cost_per_gallon"])
    gasoline_health_enabled.set(_DEFAULTS["gasoline_health_enabled"])
    gasoline_health_cost_per_gallon.set(_DEFAULTS["gasoline_health_cost_per_gallon"])
    solar_planned.set(_DEFAULTS["solar_planned"])
    solar_install_year.set(_DEFAULTS["solar_install_year"])
    solar_panels.set(_DEFAULTS["solar_panels"])
    solar_kw_per_panel.set(_DEFAULTS["solar_kw_per_panel"])
    solar_specific_yield.set(_DEFAULTS["solar_specific_yield"])
    solar_battery_enabled.set(_DEFAULTS["solar_battery_enabled"])
    solar_battery_kwh.set(_DEFAULTS["solar_battery_kwh"])
    solar_scf.set(_DEFAULTS["solar_scf"])
    solar_nem_mode.set(_DEFAULTS["solar_nem_mode"])
    solar_nbc.set(_DEFAULTS["solar_nbc"])
    solar_system_cost.set(_DEFAULTS["solar_system_cost"])
    solar_rebate.set(_DEFAULTS["solar_rebate"])
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


# Export everything defined above (reactives, _DEFAULTS, helpers, reset) so a
# `from ui.state import *` re-exports it all, incl. underscore-prefixed names.
__all__ = [n for n in dir() if not n.startswith("__") and n != "solara"]
