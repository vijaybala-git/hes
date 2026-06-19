"""ui/layout.py — app composition: sub-components, bottom-zone routing, masthead,
cockpit, setup group, journey grid, run_simulation, and the Page (Phase 4.5).

Moved from app.py; app.py is now a thin entry that re-exports Page.
"""
import os
import json
import functools
from pathlib import Path
import solara
import solara.lab
import numpy as np
import matplotlib
import matplotlib.ticker
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
matplotlib.use("Agg")
from matplotlib.figure import Figure
from model import HESModel
from home_config import HomeConfig, compute_baseload_kwh
from climate_loader import ClimateLoader, TREND_SCENARIOS
from rate_resolver import RateResolver
from journey import CATEGORY_ORDER, CATEGORY_LABELS, CapExOnlySlot, SolarBatteryConfig
from ui.device_style import DEVICE_STYLE, DEVICE_ORDER, dstyle, device_legend_handles
from panel_assessor import PanelAssessor
from social_cost import SocialCostConfig
from help_utils import (HelpButton, ChartHelpButton, HelpPopupOverlay,
                        HelpLink)
# Phase 4.5 — leaf modules (pure constants/functions; names unchanged for the body).
from ui.theme import (  # noqa: F401
    C_NAVY, C_SKY, C_RED, C_BASE, C_ELEC, C_RATE_ELEC, C_RATE_GAS,
    _CC_J, _CC_B, _CC_GRID, _CC_TICK, _CC_SOLAR, CATEGORY_COLORS, CHART_OPTIONS, CHART_CODES,
    _SLOT_COLORS, KWH_PER_THERM, KWH_PER_GALLON_GASOLINE, UA_MAP, _SLOT_DISPLAY_ORDER,
    DEVICE_LABELS, DEVICE_COLORS, DEVICE_ALPHAS, _REDESIGN_CSS, _LAYOUT_V2_CSS)
from ui.icons import (  # noqa: F401
    _WHYWATT_ICON_SVG, _DEVICE_ICONS, _CARD_IC, _PANEL_IC, _DEVICE_HELP_KEY, _SOCIAL_IC)
from ui.estimators import (  # noqa: F401
    _est_gas_furnace, _est_hp_hvac_heating, _est_hp_hvac_cooling, _est_gas_wh, _est_hpwh,
    _est_gas_dryer, _est_hp_dryer, _est_gas_cooktop, _est_induction, _est_ev_kwh, _kwh_eq)

# ── Asset paths ───────────────────────────────────────────────────────────────
_HERE         = os.path.dirname(os.path.abspath(__file__))
_ASSETS       = os.path.normpath(os.path.join(_HERE, "..", "..", "docs", "assets"))
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


# ── Display-only: EV efficiency preset (writes a reactive, so it stays here) ──
def _apply_ev_efficiency_preset(label: str):
    presets = {"Efficient": 0.23, "Average": 0.30, "Large": 0.45}
    ev_kwh_per_mile.set(presets[label])

# ── Reactive state, defaults, reset — moved to ui/state.py (Phase 4.5) ────────
from ui.state import *  # noqa: F401,F403 — reactives, _DEFAULTS, reset_to_defaults, helpers
from ui import config   # Phase 4.5b — list/load configs (apply/export come from ui.state)

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
        # Slot A — ICE: gasoline miles now → reduced/zero after switch. The
        # "electric_device" here is the post-journey ICE state (still gasoline).
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
        # Slot B — EV. Two cases:
        #   ev_miles_now == 0 (typical): absent from Do Nothing (starting_state="none");
        #     appears in the journey at swap_year, charging pct_home_after at home.
        #   ev_miles_now  > 0 (existing EV): present in Do Nothing too, charged fully
        #     externally (pct_home=0, no home charger). The journey swaps it to home
        #     charging (pct_home_after) at swap_year. starting_state="gas" is just the
        #     "baseline that transitions" marker — the baseline device is electric.
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
                # L2 home charger nameplate → drives the NEC panel load (continuous).
                # The do-nothing / pre-swap EV charges externally (no circuit) → 0 VA.
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


# ── ZIP resolution + rate-display helpers — moved to ui/sim.py (Phase 4.5) ─────
from ui.sim import *  # noqa: F401,F403

# ── Simulation runner ──────────────────────────────────────────────────────────

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
    # EV charger hardware (L2 install cost) — now a CapExOnlySlot
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


# ── Chart builders (make_*) — moved to ui/charts.py (Phase 4.5) ───────────────
from ui.charts import *  # noqa: F401,F403 — make_* chart builders

# ── Sub-components ─────────────────────────────────────────────────────────────

_DEVICE_CHART_NAMES = {"Home Energy Cost by Device", "Home Energy Use by Device"}
_TOGGLE_CHART_NAMES = _DEVICE_CHART_NAMES | {
    "Cost Breakdown by Category",
    "Annual kWh by Device",
    "Annual Gas by Device",
    "Annual Gasoline by Vehicle",
    "HVAC Monthly Energy",
    "Energy Mix Timeline",
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
        chart_type = "device_cost" if chart_name == "Home Energy Cost by Device" else "device_consumption"
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
    elif chart_name == "Annual Gasoline by Vehicle":
        home = device_chart_home.value
        with solara.Column(gap="4px"):
            _toggle_buttons(device_chart_home)
            fig = make_annual_gasoline(df, model, n, home=home)
            solara.FigureMatplotlib(fig)
    elif chart_name == "HVAC Monthly Energy":
        home = device_chart_home.value
        with solara.Column(gap="4px"):
            _toggle_buttons(device_chart_home)
            fig = make_hvac_monthly(df, model, n, home=home)
            solara.FigureMatplotlib(fig)
    elif chart_name == "Energy Mix Timeline":
        home = device_chart_home.value
        with solara.Column(gap="4px"):
            _toggle_buttons(device_chart_home)
            fig = make_energy_mix_timeline(df, model, n, home=home)
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
    _ci = _climate_info(zip_code.value, climate_trend.value)
    solara.Markdown(
        f"📍 **{_ci.reference_city}, CA** &nbsp;·&nbsp; ZIP {zip_code.value} "
        f"&nbsp;·&nbsp; Climate Zone {_ci.zone_id} "
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
    assessor = PanelAssessor(hc.square_footage, hc.panel_amps,
                             method=panel_calc_method.value)
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


# ── §25 cards / details / setup panels — moved to ui/panels.py (Phase 4.5) ────
from ui.panels import *  # noqa: F401,F403
# ── §25.6 Bottom zone routing ─────────────────────────────────────────────────

@solara.component
def DetailView(item: str, model):
    """Detail body — rendered inside the modal dialog."""
    with solara.Column(classes=["detail-body"], style="padding:4px 0"):
        if item == "hvac":
            HVACDetail()
        elif item == "water_heater":
            WaterHeaterDetail()
        elif item == "ice":
            TransportationDetail()
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
        for k in ("hvac", "water_heater", "ice", "ev", "cooktop", "dryer",
                  "panel", "baseload", "home", "solar", "rates")
    }
    _DETAIL_HELP = {
        "hvac": "hvac", "water_heater": "water_heater",
        "ice": "transportation", "ev": "ev_charger",
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
def _SettingsLoadDialog(open_rv, err_rv):
    """Modal (Phase 4.5b): pick a bundled sample config, or drop an exported .json — both
    apply with REPLACE semantics (factory ⊕ values)."""
    def _apply(source):
        try:
            apply_config(config.load_config(source))
            err_rv.set(""); open_rv.set(False)
        except Exception as e:                      # noqa: BLE001 — surface, never crash
            err_rv.set(f"Could not load settings: {e}")

    def _on_upload(f):
        try:
            _apply(json.loads(f.data.decode("utf-8")))
        except Exception as e:                      # noqa: BLE001
            err_rv.set(f"Invalid settings file: {e}")

    with solara.v.Dialog(v_model=open_rv.value, on_v_model=open_rv.set, max_width="560"):
        with solara.Card("Load settings"):
            solara.Markdown("Pick a bundled sample, or drop a settings `.json` you exported.")
            for c in config.list_configs():
                with solara.Row(style="align-items:center; justify-content:space-between;"
                                      " gap:12px; padding:3px 0"):
                    solara.HTML(tag="div", unsafe_innerHTML=(
                        f"<div><b>{c['name']}</b><br>"
                        f"<span style='font-size:0.82em;color:#607D8B'>{c['description']}</span></div>"))
                    solara.Button("Load", on_click=lambda src=c["key"]: _apply(src))
            solara.FileDrop(label="…or drop a settings .json file here",
                            on_file=_on_upload, lazy=False)
            if err_rv.value:
                solara.Error(err_rv.value)
            with solara.CardActions():
                solara.v.Spacer()
                solara.Button("Close", text=True, on_click=lambda: open_rv.set(False))


@solara.component
def Masthead():
    """Redesign masthead: preserved logo + one-line context pill + Reset/Help."""
    bl_kwh = compute_baseload_kwh(
        square_footage.value, num_bedrooms.value, baseload_constant_before.value
    )
    _ci = _climate_info(zip_code.value, climate_trend.value)
    cz = _ci.zone_id.replace("CZ", "").strip()
    _settings_load_open = solara.use_reactive(False)
    _settings_load_err = solara.use_reactive("")
    context_html = (
        "<div class='context'>"
        "<span class='loc'>"
        "<svg viewBox='0 0 24 24' fill='currentColor'><path d='M12 2C8.1 2 5 5.1 5 9c0 "
        "5.2 7 13 7 13s7-7.8 7-13c0-3.9-3.1-7-7-7zm0 9.5A2.5 2.5 0 1112 6a2.5 2.5 0 010 "
        f"5.5z'/></svg>{_ci.reference_city}, CA</span>"
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
        "<div class='brand-tag'>Home Electrification Explorer</div>"
        "</div>"
    )
    with solara.Row(classes=["masthead"], style="gap:16px"):
        solara.HTML(tag="div", unsafe_innerHTML=brand_inner, classes=["brand"],
                    style="display:flex; align-items:center; flex-shrink:0")
        solara.HTML(tag="div", unsafe_innerHTML=context_html,
                    style="flex:1; min-width:0")
        with solara.Row(classes=["actions"], style="gap:8px; flex-shrink:0; align-items:center"):
            solara.Button("↺ Reset", on_click=reset_to_defaults, classes=["btn"])

            # Settings dropdown — Load… (opens dialog) / Export (downloads JSON).
            with solara.lab.Menu(activator=solara.Button("⚙ Settings ▾", classes=["btn"])):
                with solara.Column(gap="0px", style="padding:4px; min-width:150px"):
                    solara.Button("Load…", text=True, on_click=lambda: (
                        _settings_load_err.set(""), _settings_load_open.set(True)))
                    solara.FileDownload(lambda: json.dumps(export_config(), indent=2),
                                        filename="whywatt_settings.json", label="Export")

            HelpLink("? Help", "index.html", classes=["btn", "primary"],
                     style="text-decoration:none")
        _SettingsLoadDialog(_settings_load_open, _settings_load_err)


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
    assessor = PanelAssessor(hc.square_footage, hc.panel_amps,
                             method=panel_calc_method.value)
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
                TransportationSummaryCard()
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
        zip_code.value, climate_trend.value, num_bedrooms.value,
        square_footage.value, year_built.value, insulation_quality.value,
        furnace_afue.value, gas_wh_uef.value, hvac_has_cooling.value,
        hp_cop_heating.value, hp_seer_cooling.value, hpwh_uef.value,
        hvac_starting_state.value, hvac_swap_planned.value, hvac_swap_year.value,
        hvac_install_cost.value, hvac_rebate.value,
        hvac_furnace_age.value, hvac_ac_seer.value, hvac_ac_age.value,
        hvac_baseline_lifespan.value, hvac_baseline_replace_cost.value,
        wh_starting_state.value, wh_swap_planned.value, wh_swap_year.value,
        wh_install_cost.value, wh_rebate.value,
        wh_gas_age.value, wh_baseline_lifespan.value, wh_baseline_replace_cost.value,
        hw_daily_gallons.value, hw_gallons_user_override.value,
        dryer_starting_state.value, dryer_swap_planned.value, dryer_swap_year.value,
        dryer_install_cost.value, dryer_rebate.value,
        dryer_gas_therms_per_cycle.value, dryer_loads_per_week.value,
        dryer_hp_kwh_per_cycle.value,
        dryer_age.value, dryer_baseline_lifespan.value, dryer_baseline_replace_cost.value,
        cooktop_starting_state.value, cooktop_swap_planned.value, cooktop_swap_year.value,
        cooktop_install_cost.value, cooktop_rebate.value,
        cooktop_gas_therms_per_meal.value, cooktop_meals_per_week.value,
        cooktop_induction_kwh_per_meal.value,
        cooktop_age.value, cooktop_baseline_lifespan.value, cooktop_baseline_replace_cost.value,
        ev_swap_planned.value, ev_swap_year.value, ev_install_cost.value, ev_rebate.value,
        transport_gasoline_miles.value, transport_ice_miles_after.value, transport_mpg.value,
        transport_ev_miles_now.value, transport_plan_electric_miles.value,
        transport_ev_eff.value, transport_charging_eff.value, transport_pct_home_after.value,
        external_ev_price_per_kwh.value, external_ev_escalation_pct.value,
        gasoline_price.value, gasoline_escalation_pct.value,
        gasoline_climate_enabled.value, gasoline_climate_cost_per_gallon.value,
        gasoline_health_enabled.value, gasoline_health_cost_per_gallon.value,
        panel_upgrade_planned.value, panel_upgrade_year.value,
        panel_upgrade_cost.value, panel_upgrade_rebate.value,
        baseload_constant_before.value, baseload_constant_after.value,
        baseload_swap_planned.value, baseload_swap_year.value,
        baseload_install_cost.value, baseload_rebate.value,
        solar_planned.value, solar_install_year.value,
        solar_panels.value, solar_kw_per_panel.value, solar_specific_yield.value,
        solar_battery_enabled.value, solar_battery_kwh.value, solar_scf.value,
        solar_nem_mode.value, solar_nbc.value,
        solar_system_cost.value, solar_rebate.value,
        elec_rate_model_a.value, elec_cagr_pct_a.value, acc_elec_cagr_a.value,
        gas_rate_model_a.value,  gas_cagr_pct_a.value,  acc_gas_cagr_a.value,
        comparison_mode.value,
        elec_rate_model_b.value, elec_cagr_pct_b.value, acc_elec_cagr_b.value,
        gas_rate_model_b.value,  gas_cagr_pct_b.value,  acc_gas_cagr_b.value,
        years.value, sim_start_year.value,
        wh_inlet_temp_f.value, wh_setpoint_f.value,
        gas_wh_tank_gallons.value, hpwh_tank_gallons.value, hpwh_ambient_location.value,
        # Phase 3 §5 — panel sizing inputs
        panel_amps.value, panel_calc_method.value,
        hvac_tonnage.value, ev_charger_amps.value,
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
                # ── Detail dock → reads as an inline popup so users notice "Done" ──
                # (.card.detail-dock beats Vuetify's .v-sheet.elevation-0 box-shadow)
                ".card.detail-dock{border:3px solid var(--border-strong,#c4c9d2)!important;"
                "box-shadow:0 16px 40px rgba(20,28,46,.26),"
                "0 4px 12px rgba(20,28,46,.14)!important;"
                "border-radius:14px!important;overflow:hidden!important;"
                "margin-top:6px!important}"
                ".detail-dock .modal-hd{background:var(--accent-soft,#EEF2FC)!important;"
                "border-bottom:1px solid var(--border,#e2e5ed)!important}"
                ".detail-dock .btn.done{font-size:.92em!important;padding:8px 22px!important;"
                "box-shadow:0 0 0 3px rgba(46,125,50,.22),0 3px 8px rgba(46,125,50,.30)!important;"
                "animation:donePulse 2.4s ease-in-out infinite}"
                "@keyframes donePulse{0%,100%{box-shadow:0 0 0 3px rgba(46,125,50,.22),"
                "0 3px 8px rgba(46,125,50,.30)}"
                "50%{box-shadow:0 0 0 6px rgba(46,125,50,.10),0 3px 8px rgba(46,125,50,.30)}}"
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

        # ── Help — small popup window (dialog) with a "Learn more" link that
        #    opens the full help page in a new browser tab. Device detail still
        #    renders as an inline dock below the charts.
        HelpPopupOverlay()
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
                "Connect on Discord : <a href='https://community.whywatt.org' target='_blank'>https://community.whywatt.org</a> "
                "Supported by the <strong>Electrification Collaboration</strong>."
                "</span>"
            ))
            solara.HTML(tag="div", unsafe_innerHTML=(
                "<span style='background:#0D47A1;color:#fff;border-radius:6px;"
                "padding:3px 10px;font-size:.74em;font-weight:700;"
                "white-space:nowrap'>WhyWatt? v2.0</span>"
            ))
