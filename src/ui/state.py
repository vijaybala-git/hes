"""ui/state.py — all Solara reactive state, defaults, and reset (Phase 4.5).

The single home for the app's ~148 module-level reactives plus _DEFAULTS and
reset_to_defaults(). Moved verbatim from app.py — no behavior change. Every UI module
imports these by name (`from ui.state import *`), so all modules share ONE reactive
instance per cell (Phase 4.5 invariant #1).
"""
import solara

from ui.config import factory_defaults, merge, make_envelope

# ── Defaults — externalized to data/config/whywatt_default.json (Phase 4.5b) ──
# Single source of truth: the reactives below initialize from this dict; reset uses it.
_DEFAULTS = factory_defaults()

# ── Reactive state (initialised from _DEFAULTS) ────────────────────────────────

# Home profile
zip_code           = solara.reactive(_DEFAULTS["zip_code"])
climate_zone       = solara.reactive(_DEFAULTS["climate_zone"])    # display only — resolved live from zip_code
climate_trend      = solara.reactive(_DEFAULTS["climate_trend"])   # §1.5: "none" | "rcp45" | "rcp85"
num_bedrooms       = solara.reactive(_DEFAULTS["num_bedrooms"])
square_footage     = solara.reactive(_DEFAULTS["square_footage"])
year_built         = solara.reactive(_DEFAULTS["year_built"])
insulation_quality = solara.reactive(_DEFAULTS["insulation_quality"])
panel_amps         = solara.reactive(_DEFAULTS["panel_amps"])        # Phase 3 §5 — service size 100/150/200
panel_calc_method  = solara.reactive(_DEFAULTS["panel_calc_method"]) # NEC load calc: "optional" (220.82) | "standard"

# Electrical nameplate sizing (Phase 3 §2.5) — drive panel assessment, inert for energy
hvac_tonnage    = solara.reactive(_DEFAULTS["hvac_tonnage"])   # slider 2.0–5.0; amps = tonnage × 10
ev_charger_amps = solara.reactive(_DEFAULTS["ev_charger_amps"])    # selector 32 / 48
induction_amps  = solara.reactive(_DEFAULTS["induction_amps"])    # editable input
hpwh_amps       = solara.reactive(_DEFAULTS["hpwh_amps"])    # editable input
dryer_amps      = solara.reactive(_DEFAULTS["dryer_amps"])    # editable input

# Baseline device specs
furnace_afue     = solara.reactive(_DEFAULTS["furnace_afue"])
gas_wh_uef       = solara.reactive(_DEFAULTS["gas_wh_uef"])
hvac_has_cooling = solara.reactive(_DEFAULTS["hvac_has_cooling"])

# Electric replacement specs
hp_cop_heating  = solara.reactive(_DEFAULTS["hp_cop_heating"])
hp_seer_cooling = solara.reactive(_DEFAULTS["hp_seer_cooling"])
hpwh_uef        = solara.reactive(_DEFAULTS["hpwh_uef"])

# Journey planner — HVAC
hvac_starting_state = solara.reactive(_DEFAULTS["hvac_starting_state"])
hvac_swap_planned   = solara.reactive(_DEFAULTS["hvac_swap_planned"])
hvac_swap_year      = solara.reactive(_DEFAULTS["hvac_swap_year"])
hvac_install_cost   = solara.reactive(_DEFAULTS["hvac_install_cost"])
hvac_rebate         = solara.reactive(_DEFAULTS["hvac_rebate"])

# Journey planner — Water Heater
wh_starting_state = solara.reactive(_DEFAULTS["wh_starting_state"])
wh_swap_planned   = solara.reactive(_DEFAULTS["wh_swap_planned"])
wh_swap_year      = solara.reactive(_DEFAULTS["wh_swap_year"])
wh_install_cost   = solara.reactive(_DEFAULTS["wh_install_cost"])
wh_rebate         = solara.reactive(_DEFAULTS["wh_rebate"])

# Journey planner — Dryer
dryer_starting_state = solara.reactive(_DEFAULTS["dryer_starting_state"])
dryer_swap_planned   = solara.reactive(_DEFAULTS["dryer_swap_planned"])
dryer_swap_year      = solara.reactive(_DEFAULTS["dryer_swap_year"])
dryer_install_cost   = solara.reactive(_DEFAULTS["dryer_install_cost"])
dryer_rebate         = solara.reactive(_DEFAULTS["dryer_rebate"])

# Journey planner — Cooktop
cooktop_starting_state = solara.reactive(_DEFAULTS["cooktop_starting_state"])
cooktop_swap_planned   = solara.reactive(_DEFAULTS["cooktop_swap_planned"])
cooktop_swap_year      = solara.reactive(_DEFAULTS["cooktop_swap_year"])
cooktop_install_cost   = solara.reactive(_DEFAULTS["cooktop_install_cost"])
cooktop_rebate         = solara.reactive(_DEFAULTS["cooktop_rebate"])

# Journey planner — EV Charger
ev_starting_state = solara.reactive(_DEFAULTS["ev_starting_state"])
ev_swap_planned   = solara.reactive(_DEFAULTS["ev_swap_planned"])
ev_swap_year      = solara.reactive(_DEFAULTS["ev_swap_year"])
ev_install_cost   = solara.reactive(_DEFAULTS["ev_install_cost"])
ev_rebate         = solara.reactive(_DEFAULTS["ev_rebate"])

# Journey planner — Baseload efficiency
baseload_constant_before = solara.reactive(_DEFAULTS["baseload_constant_before"])   # kWh/yr, always-on before upgrade
baseload_constant_after  = solara.reactive(_DEFAULTS["baseload_constant_after"])   # kWh/yr, always-on after upgrade
baseload_swap_planned    = solara.reactive(_DEFAULTS["baseload_swap_planned"])
baseload_swap_year       = solara.reactive(_DEFAULTS["baseload_swap_year"])
baseload_install_cost    = solara.reactive(_DEFAULTS["baseload_install_cost"])
baseload_rebate          = solara.reactive(_DEFAULTS["baseload_rebate"])

# Expand/collapse state (one per slot + Home Profile details)
home_profile_details_expanded = solara.reactive(_DEFAULTS["home_profile_details_expanded"])
panel_expanded   = solara.reactive(_DEFAULTS["panel_expanded"])
hvac_expanded    = solara.reactive(_DEFAULTS["hvac_expanded"])
wh_expanded      = solara.reactive(_DEFAULTS["wh_expanded"])
dryer_expanded   = solara.reactive(_DEFAULTS["dryer_expanded"])
cooktop_expanded = solara.reactive(_DEFAULTS["cooktop_expanded"])
ev_expanded        = solara.reactive(_DEFAULTS["ev_expanded"])
baseload_expanded  = solara.reactive(_DEFAULTS["baseload_expanded"])

# Synthetic read-only reactive for the baseload row state label (always "electric")
_baseload_state = solara.reactive("electric")
_panel_state    = solara.reactive("none")     # upgrade slot: always "none" label

# HVAC detail specs
hvac_furnace_age             = solara.reactive(_DEFAULTS["hvac_furnace_age"])    # yrs — existing furnace age
hvac_baseline_lifespan       = solara.reactive(_DEFAULTS["hvac_baseline_lifespan"])    # yrs — gas furnace expected lifespan
hvac_baseline_replace_cost   = solara.reactive(_DEFAULTS["hvac_baseline_replace_cost"])  # $ — in-kind gas furnace replacement
hvac_ac_seer                 = solara.reactive(_DEFAULTS["hvac_ac_seer"])    # existing CentralAC SEER
hvac_ac_age                  = solara.reactive(_DEFAULTS["hvac_ac_age"])     # yrs

# Water Heater detail specs
wh_gas_age                   = solara.reactive(_DEFAULTS["wh_gas_age"])    # yrs — existing WH age
wh_baseline_lifespan         = solara.reactive(_DEFAULTS["wh_baseline_lifespan"])    # yrs — gas WH expected lifespan
wh_baseline_replace_cost     = solara.reactive(_DEFAULTS["wh_baseline_replace_cost"])  # $ — in-kind gas WH replacement
hw_daily_gallons             = solara.reactive(_DEFAULTS["hw_daily_gallons"])    # gal/day
hw_gallons_user_override     = solara.reactive(False)
gas_wh_tank_gallons          = solara.reactive(_DEFAULTS["gas_wh_tank_gallons"])    # gal
hpwh_tank_gallons            = solara.reactive(_DEFAULTS["hpwh_tank_gallons"])    # gal
hpwh_ambient_location        = solara.reactive(_DEFAULTS["hpwh_ambient_location"])
wh_inlet_temp_f              = solara.reactive(_DEFAULTS["wh_inlet_temp_f"])    # °F
wh_setpoint_f                = solara.reactive(_DEFAULTS["wh_setpoint_f"])   # °F

# Dryer detail specs
dryer_gas_therms_per_cycle   = solara.reactive(_DEFAULTS["dryer_gas_therms_per_cycle"])
dryer_loads_per_week         = solara.reactive(_DEFAULTS["dryer_loads_per_week"])
dryer_hp_kwh_per_cycle       = solara.reactive(_DEFAULTS["dryer_hp_kwh_per_cycle"])
dryer_age                    = solara.reactive(_DEFAULTS["dryer_age"])    # yrs — existing dryer age
dryer_baseline_lifespan      = solara.reactive(_DEFAULTS["dryer_baseline_lifespan"])    # yrs — gas dryer expected lifespan
dryer_baseline_replace_cost  = solara.reactive(_DEFAULTS["dryer_baseline_replace_cost"])   # $ — in-kind gas dryer replacement

# Cooktop detail specs
cooktop_gas_therms_per_meal    = solara.reactive(_DEFAULTS["cooktop_gas_therms_per_meal"])
cooktop_meals_per_week         = solara.reactive(_DEFAULTS["cooktop_meals_per_week"])
cooktop_induction_kwh_per_meal = solara.reactive(_DEFAULTS["cooktop_induction_kwh_per_meal"])
cooktop_age                      = solara.reactive(_DEFAULTS["cooktop_age"])    # yrs — existing cooktop age
cooktop_baseline_lifespan        = solara.reactive(_DEFAULTS["cooktop_baseline_lifespan"])    # yrs — gas cooktop expected lifespan
cooktop_baseline_replace_cost    = solara.reactive(_DEFAULTS["cooktop_baseline_replace_cost"])  # $ — in-kind gas cooktop replacement

# Panel upgrade
panel_upgrade_planned = solara.reactive(_DEFAULTS["panel_upgrade_planned"])
panel_upgrade_year    = solara.reactive(_DEFAULTS["panel_upgrade_year"])      # install in year 1 if planned
panel_upgrade_cost    = solara.reactive(_DEFAULTS["panel_upgrade_cost"])   # slider 2000–10000
panel_upgrade_rebate  = solara.reactive(_DEFAULTS["panel_upgrade_rebate"])

# EV detail specs (retained for backward compat; not used in Transportation slot)
ev_miles_per_year      = solara.reactive(_DEFAULTS["ev_miles_per_year"])   # mi/yr
ev_kwh_per_mile        = solara.reactive(_DEFAULTS["ev_kwh_per_mile"])   # kWh/mi
ev_charging_efficiency = solara.reactive(_DEFAULTS["ev_charging_efficiency"])   # 0–1

# Transportation (§3) — Wave 3 two-slot model (§3.6)
transport_gasoline_miles      = solara.reactive(_DEFAULTS["transport_gasoline_miles"])   # ICE miles/yr now (both scenarios)
transport_ice_miles_after     = solara.reactive(_DEFAULTS["transport_ice_miles_after"])        # ICE miles/yr after switch (journey)
transport_mpg                 = solara.reactive(_DEFAULTS["transport_mpg"])
transport_ev_miles_now        = solara.reactive(_DEFAULTS["transport_ev_miles_now"])        # existing EV miles/yr today (Do Nothing)
transport_plan_electric_miles = solara.reactive(_DEFAULTS["transport_plan_electric_miles"])   # EV miles/yr after switch (journey)
transport_ev_eff              = solara.reactive(_DEFAULTS["transport_ev_eff"])     # mi/kWh battery-out
transport_charging_eff        = solara.reactive(_DEFAULTS["transport_charging_eff"])
transport_pct_home_after      = solara.reactive(_DEFAULTS["transport_pct_home_after"])    # fraction charged at home post-L2 (§3.13)

# External (public/workplace) EV charging price model (§3.13)
external_ev_price_per_kwh     = solara.reactive(_DEFAULTS["external_ev_price_per_kwh"])    # $/kWh
external_ev_escalation_pct    = solara.reactive(_DEFAULTS["external_ev_escalation_pct"])       # % per year real change

# Gasoline price model (§3)
gasoline_price                   = solara.reactive(_DEFAULTS["gasoline_price"])
gasoline_escalation_pct          = solara.reactive(_DEFAULTS["gasoline_escalation_pct"])       # % per year real change
gasoline_climate_enabled         = solara.reactive(_DEFAULTS["gasoline_climate_enabled"])
gasoline_climate_cost_per_gallon = solara.reactive(_DEFAULTS["gasoline_climate_cost_per_gallon"])    # $/gal @ $190/ton SCC
gasoline_health_enabled          = solara.reactive(_DEFAULTS["gasoline_health_enabled"])
gasoline_health_cost_per_gallon  = solara.reactive(_DEFAULTS["gasoline_health_cost_per_gallon"])

# Solar + Battery (§8)
solar_planned          = solara.reactive(_DEFAULTS["solar_planned"])
solar_install_year     = solara.reactive(_DEFAULTS["solar_install_year"])
solar_panels           = solara.reactive(_DEFAULTS["solar_panels"])       # primary sizing control
solar_kw_per_panel     = solara.reactive(_DEFAULTS["solar_kw_per_panel"])     # detail: standard=0.42, premium=0.50
solar_specific_yield   = solara.reactive(_DEFAULTS["solar_specific_yield"])     # detail: kWh/kW/yr (PVWatts typical CA)
solar_battery_enabled  = solara.reactive(_DEFAULTS["solar_battery_enabled"])     # On = NEM 3.0 default
solar_battery_kwh      = solara.reactive(_DEFAULTS["solar_battery_kwh"])     # detail: one Powerwall-class unit
solar_scf              = solara.reactive(_DEFAULTS["solar_scf"])       # self-consumption %; 80 w/battery, 35 solar-only
solar_nem_mode         = solara.reactive(_DEFAULTS["solar_nem_mode"])    # "nbt" (NEM 3.0) | "nem2" (existing)
solar_nbc              = solara.reactive(_DEFAULTS["solar_nbc"])    # $/kWh NBC for NEM 2.0 only
solar_system_cost      = solara.reactive(_DEFAULTS["solar_system_cost"])    # total installed cost from contractor quote
solar_rebate           = solara.reactive(_DEFAULTS["solar_rebate"])

# Device chart home selector (shared by both device chart types)
device_chart_home = solara.reactive(_DEFAULTS["device_chart_home"])   # "journey" | "baseline"

# ACC Rate Shape chart — year selector (chart-only, NOT a sim dep)
acc_shape_year = solara.reactive(_DEFAULTS["acc_shape_year"])

# Pricing & timeline
# §2 per-fuel rate model — "cagr_flat" (= My Utility, EIA per-utility from ZIP) |
# "ca_average" (EIA statewide) | "acc_shaped"/"acc_seasonal" (ACC). The CAGR slider applies
# to both EIA modes and is seeded from each utility's EIA historical CAGR (see EnergyPrices).
elec_rate_model_a = solara.reactive(_DEFAULTS["elec_rate_model_a"])
elec_cagr_pct_a   = solara.reactive(_DEFAULTS["elec_cagr_pct_a"])
acc_elec_cagr_a   = solara.reactive(_DEFAULTS["acc_elec_cagr_a"])            # base escalation used when acc_shaped
gas_rate_model_a  = solara.reactive(_DEFAULTS["gas_rate_model_a"])
gas_cagr_pct_a    = solara.reactive(_DEFAULTS["gas_cagr_pct_a"])
acc_gas_cagr_a    = solara.reactive(_DEFAULTS["acc_gas_cagr_a"])             # base escalation used when acc_seasonal
comparison_mode   = solara.reactive(_DEFAULTS["comparison_mode"])
elec_rate_model_b = solara.reactive(_DEFAULTS["elec_rate_model_b"])
elec_cagr_pct_b   = solara.reactive(_DEFAULTS["elec_cagr_pct_b"])
acc_elec_cagr_b   = solara.reactive(_DEFAULTS["acc_elec_cagr_b"])
gas_rate_model_b  = solara.reactive(_DEFAULTS["gas_rate_model_b"])
gas_cagr_pct_b    = solara.reactive(_DEFAULTS["gas_cagr_pct_b"])
acc_gas_cagr_b    = solara.reactive(_DEFAULTS["acc_gas_cagr_b"])
years             = solara.reactive(_DEFAULTS["years"])
sim_start_year   = solara.reactive(_DEFAULTS["sim_start_year"])

# Social & Health cost of gas (Phase 3 §6)
social_climate_enabled = solara.reactive(_DEFAULTS["social_climate_enabled"])
social_climate_rate    = solara.reactive(_DEFAULTS["social_climate_rate"])   # $/therm — EPA 2023 + 2% leakage
social_health_enabled  = solara.reactive(_DEFAULTS["social_health_enabled"])
social_health_rate     = solara.reactive(_DEFAULTS["social_health_rate"])   # $/therm — CPUC D.24-07-015 / E3 2022

# Chart selection
chart_left  = solara.reactive(_DEFAULTS["chart_left"])
chart_right = solara.reactive(_DEFAULTS["chart_right"])

# Detail view state (§25)
detail_open = solara.reactive(_DEFAULTS["detail_open"])   # None | "hvac" | "water_heater" | "ice" | "ev" | "cooktop" | "dryer" | "home" | "solar" | "rates"

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


def apply_config(values: dict) -> None:
    """Load a config (Phase 4.5b, REPLACE semantics): set EVERY persistent reactive from
    factory ⊕ values. Keys absent from `values` revert to factory; unknown keys are ignored.
    Transient UI reactives are untouched."""
    for k, v in merge({k: v for k, v in values.items() if k in _DEFAULTS}).items():
        globals()[k].set(v)


def export_config(name: str = "my_whywatt_config", description: str = "") -> dict:
    """Snapshot the current persistent reactive values into a versioned, shareable envelope."""
    values = {k: globals()[k].value for k in _DEFAULTS}
    return make_envelope(values, name=name, description=description)


# Export everything defined above (reactives, _DEFAULTS, helpers, reset) so a
# `from ui.state import *` re-exports it all, incl. underscore-prefixed names.
__all__ = [n for n in dir() if not n.startswith("__") and n != "solara"]
