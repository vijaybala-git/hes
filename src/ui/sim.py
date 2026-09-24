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
from projected_rate_source import PROJECTION_LABELS
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


# ── Current energy rate vs projection method (Phase 7 §4.1, U2) ─────────────────
# Projection methods shown as primary buttons (short labels; the card says "WhyWatt").
PROJECTION_BUTTONS = (("whywatt_conservative", "Conservative"),
                      ("whywatt_moderate", "Moderate"),
                      ("whywatt_stress", "Stress"),
                      ("eia_pacific", "EIA Pacific"))
# Legacy fixed-%/yr methods — the Details dropdown (My Utility stays the default through P7).
LEGACY_METHODS = {
    "electricity": (("cagr_flat", "My Utility"), ("ca_average", "CA Average"),
                    ("acc_shaped", "ACC")),
    "gas": (("cagr_flat", "My Utility"), ("ca_average", "CA Average"),
            ("acc_seasonal", "ACC")),
}
_UNIT_SHORT = {"electricity": "kWh", "gas": "therm"}


def _starting_rate(fuel: str):
    """The home's current energy rate for `fuel` (StartingRate) — shared by scenarios A/B."""
    from starting_rates import get_starting_rates
    fr = getattr(_rate_info(zip_code.value, "auto"), fuel)
    label = (elec_tariff_label.value or None) if fuel == "electricity" else None
    return get_starting_rates().resolve(fuel, fr.utility_id, zip_code.value, label)


def _current_rate_display(fuel: str, method: str) -> tuple[str, str, str]:
    """(headline, detail, kind) for the current energy rate a method prices from.

    Projection methods use the home's StartingRate (URDB plan / utility EIA 2025 / EIA —
    Pacific). Legacy methods keep their own starting price (shown as such)."""
    unit = _UNIT_SHORT[fuel]
    fr = getattr(_rate_info(zip_code.value, "auto"), fuel)
    if method in PROJECTION_LABELS:
        st = _starting_rate(fuel)
        if st.kind == "urdb":
            from urdb_rates import peak_hours_label
            rs = st.structure
            peak = (f"peak {peak_hours_label(rs.peak_hours)}" if rs.is_tou
                    else "tiered, no peak window")
            return st.label, f"{peak} · URDB plan, effective {rs.startdate}", "urdb"
        if st.kind == "eia_utility":
            est = " · 2024 rate carried to 2025" if st.method == "bridged_state_ratio" else ""
            note = ""
            if fuel == "electricity":
                from urdb_rates import get_urdb
                u = get_urdb()
                if u.decision(st.utility_id) == "quarantined":
                    note = " · plan data under review"
                elif u.decision(st.utility_id) != "urdb":
                    note = " · no plan data yet"
            return st.label, f"${st.rate:.3f}/{unit}{est}{note}", "eia_utility"
        return st.label, f"${st.rate:.3f}/{unit} · regional average (no utility found)", \
            "eia_region"
    if method in ("acc_shaped", "acc_seasonal"):
        return "PG&E CPUC base", "ACC shape · fixed %/yr", "legacy"
    if method == "ca_average":
        ca = _rate_info(zip_code.value, "ca_average")
        r = getattr(ca, fuel)
        return "California average", f"${r.rate:.3f}/{unit} · EIA {r.base_year}", "legacy"
    return (fr.name, f"${fr.rate:.3f}/{unit} · EIA {fr.base_year} · My Utility", "legacy")


def _utilities_html(zipcode: str) -> str:
    """Home Profile line: the ZIP's electric + gas utility (or the fallback)."""
    from starting_rates import get_starting_rates
    ri = _rate_info(zipcode, "auto")
    parts = []
    for fr in (ri.electricity, ri.gas):
        icon = "⚡" if fr.fuel == "electricity" else "🔥"
        if fr.utility_id is None:
            name = "<span style='color:#9A4D00'>not found — EIA Pacific</span>"
        else:
            short = get_starting_rates().short_name(fr.fuel, fr.utility_id) or fr.name
            name = "<b>" + short + "</b>"
            if fr.provenance == "inferred":
                name += "<span style='color:#B26A00'> ≈</span>"
        parts.append(f"{icon} {name}")
    return ("<div style='font-size:0.82em; color:#555; margin-top:2px;'>"
            "Your utilities: " + " &nbsp;·&nbsp; ".join(parts) + "</div>")


def _seed_eia_cagr():
    """Seed the per-fuel CAGR sliders from each utility's EIA historical CAGR (the JSON
    default), for the two EIA modes (both scenarios). Re-seeds on ZIP/mode change; manual
    edits persist until the context changes. ACC modes keep their own base-escalation slider.

    Skips entirely right after a scenario load (Phase 5.5 Fix 6): a loaded scenario carries
    its own CAGR and must reproduce verbatim, so seeding does not clobber it until the user
    next changes the ZIP or a rate model."""
    if _seed_suppressed():
        return
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
                "setpoint_f": wh_setpoint_f.value,
            }],
            "existing_age": wh_gas_age.value,
            "electric_device": {
                "class": "HeatPumpWaterHeater",
                "uef": hpwh_uef.value,
                "lifespan": 15, "installation_cost": 2500,
                "daily_gallons_override": hw_override,
                "ambient_location": hpwh_ambient_location.value,
                "setpoint_f": wh_setpoint_f.value,
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
        # Phase 6 §2b — inert PVWatts geometry (carried through; no device reads them).
        roof_tilt=roof_tilt.value,
        roof_azimuth=roof_azimuth.value,
        array_type=array_type.value,
        module_type=module_type.value,
        system_losses=system_losses.value,
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
        battery_enabled=solar_battery_enabled.value,
        battery_kwh=solar_battery_kwh.value,
        round_trip_eff=solar_battery_rte_pct.value / 100.0,
        charge_kw=solar_battery_charge_kw.value,
        discharge_kw=solar_battery_discharge_kw.value,
        grid_charging=solar_battery_grid_charging.value,
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
        elec_tariff_label=elec_tariff_label.value or None,
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

    # Rates + battery (Phase 7): which plan / projection priced the run, so a silent fallback
    # (e.g. an unknown tariff label → the utility default) changes the snapshot.
    import numpy as _np
    from dispatch import battery_mode_summary
    rs, esc = model.rate_structure_a, model.rate_escalation_a
    jh = model.journey_home
    rates = {
        "elec_model": model.elec_rate_model_a,
        "gas_model": model.gas_rate_model_a,
        "elec_priced_by": (f"URDB {rs.family}" if rs is not None else "flat"),
        # the current energy rate — used only by projection methods (None under legacy modes)
        "elec_start": (model.starting_rate_elec.label
                       if model.elec_rate_model_a in PROJECTION_LABELS else None),
        "gas_start": (model.starting_rate_gas.label
                      if model.gas_rate_model_a in PROJECTION_LABELS else None),
        "elec_y1_mean": round(float(_np.mean(model.elec_rates[0])), 4),
        "elec_final_mean": round(float(_np.mean(model.elec_rates[-1])), 4),
        "gas_y1_mean": round(float(_np.mean(model.gas_rates[0])), 4),
        "gas_final_mean": round(float(_np.mean(model.gas_rates[-1])), 4),
        "elec_escalation_final": (round(float(esc[-1]), 4) if esc is not None else None),
        "journey_final_elec_bill": (round(jh.home_elec_bill_history[-1])
                                    if jh.home_elec_bill_history
                                    and jh.home_elec_bill_history[-1] is not None else None),
    }
    solar_on = bool(jh.solar_production_kwh_history and jh.solar_production_kwh_history[-1] > 0)
    battery = {
        "final_mode": (battery_mode_summary(jh.battery_mode_history[-1])
                       if solar_on and jh.battery_mode_history[-1] else None),
        "final_discharge_kwh": round(jh.battery_discharge_history[-1], 1) if solar_on else 0.0,
        "final_export_kwh": round(jh.solar_exported_kwh_history[-1], 1) if solar_on else 0.0,
    }

    return {"cockpit": cockpit, "gasoline": gasoline, "devices": devices,
            "rates": rates, "battery": battery}


__all__ = ["_APP_CLIMATE_LOADER", "_TREND_LABELS", "_climate_info", "_APP_RATE_RESOLVER",
           "_rate_info", "_seed_eia_cagr",
           "PROJECTION_BUTTONS", "LEGACY_METHODS", "_starting_rate", "_current_rate_display",
           "_utilities_html",
           "_eff_swap_year", "_build_slot_configs", "run_simulation",
           "_verdict_numbers", "extract_metrics"]
