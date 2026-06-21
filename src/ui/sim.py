"""ui/sim.py — ZIP→zone/utility resolution + rate-display helpers (Phase 4.5).

Shared by both the panels (ui/panels.py) and the layout (app.py). Moved verbatim from app.py.
"""
import functools

from climate_loader import ClimateLoader
from rate_resolver import RateResolver
from model import HESModel
from home_config import HomeConfig
from journey import CapExOnlySlot, SolarBatteryConfig
from social_cost import SocialCostConfig
from panel_assessor import PanelAssessor
from ui.theme import C_RATE_ELEC, C_RATE_GAS
from ui.state import *  # noqa: F401,F403 — reactives read/written by _seed_eia_cagr

# ── Climate resolution (ZIP → CEC zone), pinned to zip_code (Phase 4 §1) ────────

_APP_CLIMATE_LOADER = ClimateLoader()

_TREND_LABELS = {
    "none":  "None (static TMY3)",
    "rcp45": "Moderate (RCP 4.5)",
    "rcp85": "High (RCP 8.5)",
}


@functools.lru_cache(maxsize=256)
def _climate_info(zipcode: str, trend: str):
    """Resolve a ZIP (+trend) to ClimateData for display. Cached; local JSON only."""
    return _APP_CLIMATE_LOADER.get_climate(zipcode, n_years=1, trend_scenario=trend)


# ── Rate resolution (ZIP → electric utility + gas LDC), Phase 4 §2 ──────────────

_APP_RATE_RESOLVER = RateResolver()


@functools.lru_cache(maxsize=256)
def _rate_info(zipcode: str, source: str):
    """Resolve a ZIP to its electric utility + gas LDC for display. Cached; local JSON."""
    return _APP_RATE_RESOLVER.resolve(zipcode, source=source)


def _utility_line(fr) -> str:
    """One-row HTML for a resolved fuel: icon + utility name + provenance badge."""
    icon = "⚡" if fr.fuel == "electricity" else "🔥"
    color = C_RATE_ELEC if fr.fuel == "electricity" else C_RATE_GAS
    if fr.provenance == "inferred":
        badge = ("<span style='font-size:0.72em; color:#B26A00; background:#FFF3E0;"
                 " border-radius:3px; padding:1px 5px; margin-left:6px'>≈ estimated from area</span>")
    elif fr.provenance == "fallback":
        badge = ("<span style='font-size:0.72em; color:#9A4D00; background:#FFE0B2;"
                 " border-radius:3px; padding:1px 5px; margin-left:6px'>⚠ utility not found — CA avg</span>")
    elif fr.provenance == "selected":
        badge = ("<span style='font-size:0.72em; color:#546E7A; background:#ECEFF1;"
                 " border-radius:3px; padding:1px 5px; margin-left:6px'>statewide</span>")
    else:
        badge = ""
    return (f"<div style='display:flex; align-items:baseline; font-size:0.84em;"
            f" padding:2px 0 2px 4px;'>"
            f"<span style='color:{color}; margin-right:6px'>{icon}</span>"
            f"<strong style='color:#263238'>{fr.name}</strong>{badge}</div>")


_PROV_BADGE = {  # provenance -> (text, fg, bg)
    "inferred": ("≈ estimated from area", "#B26A00", "#FFF3E0"),
    "fallback": ("⚠ utility not found — CA avg", "#9A4D00", "#FFE0B2"),
    "selected": ("statewide", "#546E7A", "#ECEFF1"),
    "acc":      ("ACC shape", "#546E7A", "#ECEFF1"),
}


def _rate_line_html(fuel: str, name: str, provenance: str, cagr_pct=None) -> str:
    """Resolved-rate line: icon + name + provenance badge + right-aligned CAGR."""
    icon = "⚡" if fuel == "electricity" else "🔥"
    color = C_RATE_ELEC if fuel == "electricity" else C_RATE_GAS
    badge = ""
    if provenance in _PROV_BADGE:
        t, fg, bg = _PROV_BADGE[provenance]
        badge = (f"<span style='font-size:0.72em; color:{fg}; background:{bg};"
                 f" border-radius:3px; padding:1px 5px; margin-left:6px'>{t}</span>")
    cagr = ("" if cagr_pct is None else
            f"<span style='margin-left:auto; color:#546E7A; font-size:0.82em'>+{cagr_pct}%/yr</span>")
    return (f"<div style='display:flex; align-items:baseline; font-size:0.84em;"
            f" padding:2px 0 2px 4px;'>"
            f"<span style='color:{color}; margin-right:6px'>{icon}</span>"
            f"<strong style='color:#263238'>{name}</strong>{badge}{cagr}</div>")


def _fuel_resolved_display(fuel: str, mode: str, cagr_pct: int, acc_cagr_pct: int,
                           ri_auto, ri_ca) -> tuple[str, str, int]:
    """(name, provenance, cagr) for a fuel given its selected rate mode."""
    fr_auto = ri_auto.electricity if fuel == "electricity" else ri_auto.gas
    if mode in ("acc_shaped", "acc_seasonal"):
        return "PG&E CPUC base", "acc", acc_cagr_pct
    if mode == "ca_average":
        return "California average", "selected", cagr_pct
    return fr_auto.name, fr_auto.provenance, cagr_pct          # cagr_flat = My Utility


def _seed_eia_cagr():
    """Seed the per-fuel CAGR sliders from each utility's EIA historical CAGR (the JSON
    default), for the two EIA modes (both scenarios). Re-seeds on ZIP/mode change; manual
    edits persist until the context changes. ACC modes keep their own base-escalation slider."""
    pairs = [(elec_rate_model_a, elec_cagr_pct_a, "electricity"),
             (gas_rate_model_a,  gas_cagr_pct_a,  "gas"),
             (elec_rate_model_b, elec_cagr_pct_b, "electricity"),
             (gas_rate_model_b,  gas_cagr_pct_b,  "gas")]
    for mode_rv, cagr_rv, fuel in pairs:
        if mode_rv.value in ("cagr_flat", "ca_average"):
            src = "ca_average" if mode_rv.value == "ca_average" else "auto"
            fr = getattr(_rate_info(zip_code.value, src), fuel)
            cagr_rv.set(round(fr.cagr * 100))


# ── Slot config builder + simulation runner — moved verbatim from ui/layout.py ──
# (Phase 4.5 / Regression Test Spec Step 0: make the pipeline UI-free so the
# regression harness can run a case headlessly, with no Solara/matplotlib import.)

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
        "lifespan": hvac_baseline_lifespan.value,
        "installation_cost": hvac_baseline_replace_cost.value,
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
            "style_key": "hvac",
            "starting_state": hvac_starting_state.value,
            "has_cooling_baseline": has_ac,
            "baseline_devices": hvac_baseline,
            "existing_age": hvac_furnace_age.value,
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
            "style_key": "wh",
            "starting_state": wh_starting_state.value,
            "has_cooling_baseline": False,
            "baseline_devices": [{
                "class": "GasWaterHeater",
                "uef": gas_wh_uef.value,
                "age": wh_gas_age.value,
                "lifespan": wh_baseline_lifespan.value,
                "installation_cost": wh_baseline_replace_cost.value,
                "daily_gallons_override": hw_override,
                "tank_gallons": gas_wh_tank_gallons.value,
                "setpoint_f": wh_setpoint_f.value,
                "inlet_temp_f": wh_inlet_temp_f.value,
            }],
            "existing_age": wh_gas_age.value,
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
            "style_key": "dryer",
            "starting_state": dryer_starting_state.value,
            "has_cooling_baseline": False,
            "baseline_devices": [{
                "class": "GasDryer",
                "therms_per_cycle": dryer_gas_therms_per_cycle.value,
                "cycles_per_week":  dryer_loads_per_week.value,
                "lifespan": dryer_baseline_lifespan.value,
                "installation_cost": dryer_baseline_replace_cost.value,
            }],
            "existing_age": dryer_age.value,
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
            "style_key": "cooktop",
            "starting_state": cooktop_starting_state.value,
            "has_cooling_baseline": False,
            "baseline_devices": [{
                "class": "GasCooktop",
                "therms_per_meal": cooktop_gas_therms_per_meal.value,
                "meals_per_week":  cooktop_meals_per_week.value,
                "lifespan": cooktop_baseline_lifespan.value,
                "installation_cost": cooktop_baseline_replace_cost.value,
            }],
            "existing_age": cooktop_age.value,
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
        # ── Transportation — two-slot model (§3.6): ICE + EV run concurrently ──
        {
            "name": "Transportation",
            "category": "Transportation",
            "style_key": "ice",
            "starting_state": "gas",
            "has_cooling_baseline": False,
            "baseline_devices": [{
                "class": "GasolineVehicle",
                "miles_per_year": transport_gasoline_miles.value,
                "mpg":            transport_mpg.value,
                "lifespan": 25, "installation_cost": 0,
            }],
            "existing_age": 0,
            "electric_device": {
                "class": "GasolineVehicle",
                "miles_per_year": transport_ice_miles_after.value,
                "mpg":            transport_mpg.value,
                "lifespan": 25, "installation_cost": 0,
            },
            "swap_year": ev_swap_year.value if ev_swap_planned.value else None,
            "install_cost": 0,
            "rebate": 0,
        },
        {
            "name": "EV Driving",
            "category": "Transportation",
            "style_key": "ev",
            "starting_state": "gas" if transport_ev_miles_now.value > 0 else "none",
            "has_cooling_baseline": False,
            "baseline_devices": ([{
                "class": "ElectricVehicle",
                "miles_per_year":      transport_ev_miles_now.value,
                "ev_eff_mi_per_kwh":   transport_ev_eff.value,
                "charging_efficiency": transport_charging_eff.value,
                "pct_home_charge":     0.0,   # no home charger today → all external
                "lifespan": 25, "installation_cost": 0,
            }] if transport_ev_miles_now.value > 0 else []),
            "existing_age": 0,
            "electric_device": {
                "class": "ElectricVehicle",
                "miles_per_year":      transport_plan_electric_miles.value,
                "ev_eff_mi_per_kwh":   transport_ev_eff.value,
                "charging_efficiency": transport_charging_eff.value,
                "pct_home_charge":     transport_pct_home_after.value,
                "circuit_volts": 240, "circuit_amps": ev_charger_amps.value,
                "continuous": True,
                "lifespan": 25, "installation_cost": 0,
            },
            "swap_year": ev_swap_year.value if ev_swap_planned.value else None,
            "install_cost": 0,
            "rebate": 0,
        },
        {
            "name": "Lights and Appliances",
            "category": "Baseload",
            "style_key": "lights",
            "starting_state": "gas",
            "has_cooling_baseline": False,
            "baseline_devices": [{"class": "LightsAndPlugs", "annual_kwh": 0, "lifespan": 15}],
            "electric_device":   {"class": "LightsAndPlugs", "annual_kwh": 0, "lifespan": 15},
            "swap_year": None,
            "install_cost": 400,
            "rebate": 0,
        },
    ]


def run_simulation():
    """Build and run HESModel from current reactive state; return (model, df)."""
    _ci = _climate_info(zip_code.value, climate_trend.value)
    hc = HomeConfig(
        zip_code=zip_code.value,
        climate_zone=_ci.zone_id,   # resolved from zip, not a manual field
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
            style_key="panel",
        ))
    if ev_swap_planned.value:
        capex_slots.append(CapExOnlySlot(
            name="EV Charger",
            install_cost=ev_install_cost.value,
            rebate=ev_rebate.value,
            lifespan=20,
            install_year=ev_swap_year.value,
            style_key="ev",
        ))

    if solar_planned.value:
        capex_slots.append(CapExOnlySlot(
            name="Solar + Battery",
            category="Infrastructure",
            install_cost=solar_system_cost.value,
            rebate=solar_rebate.value,
            lifespan=25,
            install_year=solar_install_year.value,
            style_key="solar",
        ))

    solar_cfg = SolarBatteryConfig(
        panels=solar_panels.value,
        kw_per_panel=solar_kw_per_panel.value,
        specific_yield=float(solar_specific_yield.value),
        battery_enabled=solar_battery_enabled.value,
        battery_kwh=solar_battery_kwh.value,
        scf=solar_scf.value / 100.0,
        nem_mode=solar_nem_mode.value,
        nbc=solar_nbc.value,
    ) if solar_planned.value else None

    m = HESModel(
        home_config=hc,
        n_years=years.value,
        climate_trend=climate_trend.value,
        gas_cagr_a=gas_cagr_pct_a.value / 100.0,
        elec_cagr_a=elec_cagr_pct_a.value / 100.0,
        gas_cagr_b=gas_cagr_pct_b.value / 100.0,
        elec_cagr_b=elec_cagr_pct_b.value / 100.0,
        comparison_mode=comparison_mode.value,
        sim_start_year=sim_start_year.value,
        slot_configs=_build_slot_configs(),
        capex_only_slots=capex_slots or None,
        solar_config=solar_cfg,
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
        gasoline_price_per_gallon=gasoline_price.value,
        gasoline_escalation_pct=gasoline_escalation_pct.value / 100.0,
        gasoline_climate_enabled=gasoline_climate_enabled.value,
        gasoline_climate_cost_per_gallon=gasoline_climate_cost_per_gallon.value,
        gasoline_health_enabled=gasoline_health_enabled.value,
        gasoline_health_cost_per_gallon=gasoline_health_cost_per_gallon.value,
        external_ev_price_per_kwh=external_ev_price_per_kwh.value,
        external_ev_escalation_pct=external_ev_escalation_pct.value / 100.0,
    )
    m.run_all()
    df = m.datacollector.get_model_vars_dataframe()
    return m, df


def _verdict_numbers(df, model):
    """Return (journey_cum, baseline_cum, payback_yr_or_None, net_delta, net_social).

    The canonical cockpit extraction — the headline summary card reads exactly these.
    Moved from layout.py so the regression harness shares one source of truth.
    """
    delta_vals   = df["Opex Delta"].values
    net_delta    = float(delta_vals[-1])
    payback_yr   = next((i + 1 for i, d in enumerate(delta_vals) if d > 0), None)
    journey_cum  = float(df["Journey Cum Cost"].iloc[-1])
    baseline_cum = float(df["Baseline Cum Cost"].iloc[-1])
    # Net social cost avoided by electrifying (baseline social − journey social)
    net_social = 0.0
    try:
        b_soc = df.get("Baseline Social Total", 0)
        j_soc = df.get("Journey Social Total", 0)
        net_social = float((b_soc - j_soc).sum())
    except Exception:
        net_social = 0.0
    return journey_cum, baseline_cum, payback_yr, net_delta, net_social


def extract_metrics(model, df) -> dict:
    """Headless snapshot of the user-visible numbers from one run (model, df).

    Mirrors the cockpit (via _verdict_numbers) + the JC.6 panel timeline + the
    transport gasoline reporters + per-slot cost/consumption. Values rounded to a
    stable precision (whole $, 0.1 energy, whole amps) so float noise can't break
    the golden compare (Regression_Test_Spec "Comparison method").

    Sign convention: opex_delta = baseline − journey (positive = the journey saves
    money), identical to the model's "Opex Delta" reporter and the cockpit.
    """
    journey_cum, baseline_cum, payback_yr, net_delta, net_social = _verdict_numbers(df, model)

    n = len(df)
    hc = model.home_config
    assessor = PanelAssessor(hc.square_footage, hc.panel_amps, method=panel_calc_method.value)
    timeline = assessor.journey_load_timeline(model.journey_home, n)
    peak = max(timeline, key=lambda t: t.service_amps)

    cockpit = {
        "journey_cumulative_opex":  round(journey_cum),
        "baseline_cumulative_opex": round(baseline_cum),
        "opex_delta":               round(net_delta),
        "payback_year":             payback_yr,
        "net_social_cost_avoided":  round(net_social),
        "current_load_amps":        round(timeline[0].service_amps),
        "peak_amps":                round(peak.service_amps),
        "peak_status":              peak.status,
        "peak_year":                peak.year,
    }

    def _last(col):
        return float(df[col].iloc[-1]) if col in df.columns else 0.0

    gasoline = {
        "journey_gallons":       round(_last("Journey Gasoline Gallons"), 1),
        "baseline_gallons":      round(_last("Baseline Gasoline Gallons"), 1),
        "journey_climate_cost":  round(_last("Journey Gasoline Climate")),
        "baseline_climate_cost": round(_last("Baseline Gasoline Climate")),
        "journey_health_cost":   round(_last("Journey Gasoline Health")),
        "baseline_health_cost":  round(_last("Baseline Gasoline Health")),
    }

    def _slot_view(home, name):
        cons  = home.consumption_history_by_slot.get(name, [])
        fuels = home.fuel_history_by_slot.get(name, [])
        return {
            "cost": round(sum(home.cost_history_by_slot.get(name, []))),
            "final_consumption": round(cons[-1], 1) if cons else 0.0,
            "fuel": fuels[-1] if fuels else None,
        }

    devices = {}
    for name in model.journey_home.cost_history_by_slot:
        j = _slot_view(model.journey_home, name)
        b = _slot_view(model.baseline_home, name)
        devices[name] = {
            "journey_cost":  j["cost"],
            "baseline_cost": b["cost"],
            "journey_final_consumption":  j["final_consumption"],
            "baseline_final_consumption": b["final_consumption"],
            "journey_fuel":  j["fuel"],
            "baseline_fuel": b["fuel"],
        }

    return {"cockpit": cockpit, "gasoline": gasoline, "devices": devices}


__all__ = ["_APP_CLIMATE_LOADER", "_TREND_LABELS", "_climate_info", "_APP_RATE_RESOLVER",
           "_rate_info", "_utility_line", "_PROV_BADGE", "_rate_line_html",
           "_fuel_resolved_display", "_seed_eia_cagr",
           "_eff_swap_year", "_build_slot_configs", "run_simulation",
           "_verdict_numbers", "extract_metrics"]
