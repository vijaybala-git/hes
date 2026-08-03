"""ui/panels.py — §25 summary cards, detail windows, setup-panel components (Phase 4.5).

The interleaved summary/detail/panel components moved verbatim from app.py. Bottom-zone
routing (BottomZone/DetailView/DetailDock) stays in app.py. Components read shared state
(ui.state), resolution/rate helpers (ui.sim), charts (ui.charts), theme, icons, estimators.
"""
import numpy as np
import solara

from ui.state import *   # noqa: F401,F403
from ui.sim import *     # noqa: F401,F403
from ui.charts import *  # noqa: F401,F403
from ui.theme import (
    C_NAVY, C_SKY, C_RED, C_BASE, C_ELEC, C_RATE_ELEC, C_RATE_GAS, KWH_PER_THERM,
    KWH_PER_GALLON_GASOLINE, CATEGORY_COLORS, CHART_OPTIONS, CHART_CODES,
    DEVICE_LABELS, DEVICE_COLORS, DEVICE_ALPHAS, _SLOT_COLORS, _SLOT_DISPLAY_ORDER)
from ui.icons import _DEVICE_ICONS, _CARD_IC, _PANEL_IC, _DEVICE_HELP_KEY, _SOCIAL_IC
from ui.estimators import (
    _est_gas_furnace, _est_hp_hvac_heating, _est_hp_hvac_cooling, _est_gas_wh, _est_hpwh,
    _est_gas_dryer, _est_hp_dryer, _est_gas_cooktop, _est_induction, _est_ev_kwh, _kwh_eq)
from ui.device_style import DEVICE_STYLE, DEVICE_ORDER, dstyle, device_legend_handles
from ui.slider import WhyWattSlider, SliderSpec
from help_utils import HelpButton, ChartHelpButton, HelpPopupOverlay, HelpLink
from journey import CATEGORY_ORDER, CATEGORY_LABELS, CapExOnlySlot, SolarBatteryConfig
from home_config import HomeConfig, compute_baseload_kwh, compute_ua
from model import HESModel
from panel_assessor import PanelAssessor
from social_cost import SocialCostConfig

# ── §25 Unified Summary + Detail UI ──────────────────────────────────────────

_DETAIL_TITLES = {
    "hvac":         "🌡️ HVAC — Heating & Cooling",
    "water_heater": "🚿 Water Heater",
    "ice":          "🚗 Transportation",
    "ev":           "🔌 EV Charger",
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


def _dec_from(fmt, step):
    """Derive display decimals from a legacy fmt string, falling back to the step."""
    for d in (3, 2, 1, 0):
        if f".{d}f" in fmt:
            return d
    if float(step).is_integer():
        return 0
    return len(f"{step}".split(".")[1])


@solara.component
def _DSl(label, rv, default, lo, hi, step=1, unit="", fmt="{v}", show_delta=True):
    """DetailSlider — unified inline WhyWattSlider (Phase 5 rollout). `show_delta`
    is accepted for call-site compatibility but no longer used (inline has no delta)."""
    WhyWattSlider(
        SliderSpec(key=str(label), title=label, minimum=lo, maximum=hi, step=step,
                   default=default, unit=unit.strip(), decimals=_dec_from(fmt, step),
                   layout="inline"),
        value=rv,
    )


def _HSl(title, rv, default, lo, hi, step=1, unit="", decimals=0):
    """HVAC-detail inline slider (Phase 5) — label | track | editable value, aligned.

    Fixed label width aligns every track down a column. Keep titles short.
    """
    WhyWattSlider(
        SliderSpec(key=title.lower().replace(" ", "_"), title=title,
                   minimum=lo, maximum=hi, step=step, default=default,
                   unit=unit, decimals=decimals, layout="inline"),
        value=rv,
    )


def _hp_size():
    """Heat pump size slider + its electrical draw — lives in the HP (right) column."""
    _HSl("Heat pump size", hvac_tonnage, _DEFAULTS["hvac_tonnage"],
         2.0, 5.0, 0.5, unit="ton", decimals=1)
    _elec_display(240, int(hvac_tonnage.value * 10))


def _YSl(rv, default, title="Swap year", max_yr=25):
    """Unified year slider (stack, editable calendar year) — swap/install years."""
    WhyWattSlider(
        SliderSpec(key=title.lower().replace(" ", "_"), title=title,
                   minimum=1, maximum=max_yr, step=1, default=default,
                   decimals=0, dtype="year", base_year=sim_start_year.value),
        value=rv,
    )


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

# Icon dicts (_DEVICE_ICONS, _CARD_IC, _PANEL_IC, _DEVICE_HELP_KEY) -> ui/icons.py (Phase 4.5).


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


def _Check(label, value, on_value=None):
    """Circular-icon checkbox matching the appliance 'Plan' style (mdi-check-circle).

    Drop-in for _Check(label=, value=, on_value=) so all page checkboxes
    share one look.
    """
    def _set(v):
        value.set(v)
        if on_value is not None:
            on_value(v)
    solara.v.Checkbox(
        v_model=value.value,
        on_v_model=_set,
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


# Display labels for the appliance state dropdowns. The stored reactive values stay
# lowercase ("gas"/"electric"/"none" — the validated config enum); only the visible
# label is title-cased. on_value maps the chosen label back to the stored value.
_STATE_LABELS = {"gas": "Gas", "electric": "Electric", "none": "None"}
_STATE_FROM_LABEL = {v: k for k, v in _STATE_LABELS.items()}


def _appliance_rows(state_rv, planned_rv, year_rv, cost_rv, rebate_rv,
                    state_values=("gas", "electric", "none"), year_default=1):
    """Row content for standard appliance summary cards (HVAC, WH, Cooktop, Dryer)."""
    state = state_rv.value
    # Row 1: state dropdown + plan checkbox (+ electrified badge)
    with solara.Row(gap="8px", style=_ROW_CTRL):
        with solara.Column(style="min-width:90px; max-width:90px"):
            solara.Select("", value=_STATE_LABELS.get(state, state),
                          values=[_STATE_LABELS.get(v, v) for v in state_values],
                          on_value=lambda lbl: state_rv.set(_STATE_FROM_LABEL.get(lbl, lbl)))
        if state != "electric":
            _PlanCheck(planned_rv, "Plan")
        elif state == "electric":
            solara.HTML(tag="span", unsafe_innerHTML=(
                "<span style='font-size:0.80em; color:#2E7D32; margin-left:4px;'>"
                "✓ Electrified</span>"
            ))
    # Row 2: full-width year slider (unified component, year mode) — only when planned
    if state != "electric" and planned_rv.value:
        with solara.Column(style="width:100%"):
            WhyWattSlider(
                SliderSpec(
                    key="swap_year", title="Swap year",
                    minimum=1, maximum=25, step=1, default=year_default,
                    decimals=0, dtype="year", base_year=sim_start_year.value,
                ),
                value=year_rv,
            )
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
                        hvac_install_cost, hvac_rebate,
                        year_default=_DEFAULTS["hvac_swap_year"])


@solara.component
def WHSummaryCard():
    """§25.3.2 — state dropdown + plan year | install cost | rebate."""
    with solara.Column(classes=["device"]):
        _card_header("water_heater", "Water Heater")
        _appliance_rows(wh_starting_state, wh_swap_planned, wh_swap_year,
                        wh_install_cost, wh_rebate,
                        year_default=_DEFAULTS["wh_swap_year"])


# ── Transportation "Do Nothing" vehicle mix ─────────────────────────────────────
# The summary dropdown (Gas / Mixed / Electric / None) is a *derived* view over the
# two underlying do-nothing reactives — current gasoline miles + existing EV miles.
# No separate state reactive: the model already reads these two, and detail-panel
# edits keep the dropdown label in sync automatically.
_TRANSPORT_STATES   = ["Gasoline", "Mixed", "Electric", "None"]
_TRANSPORT_FULL_MILES = _DEFAULTS["transport_gasoline_miles"]   # 12,000 — a full driver
_TRANSPORT_MIXED_EV   = 5000                                   # EV miles/yr when "Mixed"


def _transport_state() -> str:
    """Derive the current-vehicle state from the do-nothing miles."""
    g = transport_gasoline_miles.value > 0
    e = transport_ev_miles_now.value > 0
    if g and e:
        return "Mixed"
    if e:
        return "Electric"
    if g:
        return "Gasoline"
    return "None"


def _set_transport_state(s: str):
    """Apply a vehicle-mix choice to the do-nothing miles. Preserves a non-zero
    magnitude where it still applies; falls back to a full-driver default."""
    cur_gas = transport_gasoline_miles.value
    cur_ev  = transport_ev_miles_now.value
    if s == "Gasoline":
        transport_gasoline_miles.set(cur_gas or _TRANSPORT_FULL_MILES)
        transport_ev_miles_now.set(0)
    elif s == "Mixed":
        transport_gasoline_miles.set(cur_gas or _TRANSPORT_FULL_MILES)
        transport_ev_miles_now.set(_TRANSPORT_MIXED_EV)
    elif s == "Electric":
        transport_gasoline_miles.set(0)
        transport_ev_miles_now.set(cur_ev or _TRANSPORT_FULL_MILES)
    else:  # "None"
        transport_gasoline_miles.set(0)
        transport_ev_miles_now.set(0)


@solara.component
def TransportationSummaryCard():
    """Transportation — current-vehicle state dropdown (Gas/Mixed/Electric/None,
    the 'Do Nothing' mix) + plan EV Charger. Mirrors the other appliance cards;
    miles/MPG/efficiency are fine-tuned in the detail panel."""
    with solara.Column(classes=["device"]):
        _card_header("ice", "Transportation")
        # Row 1: current-vehicle state dropdown + Plan EV Charger
        with solara.Row(gap="8px", style=_ROW_CTRL):
            with solara.Column(style="min-width:124px; max-width:140px"):
                solara.Select("", values=_TRANSPORT_STATES,
                              value=_transport_state(),
                              on_value=_set_transport_state)
            _PlanCheck(ev_swap_planned, "Plan EV Charger")
        # When EV charger is planned: year slider + net cost
        if ev_swap_planned.value:
            with solara.Column(style="width:100%"):
                _YSl(ev_swap_year, _DEFAULTS["ev_swap_year"])
            net = ev_install_cost.value - ev_rebate.value
            solara.HTML(tag="div", unsafe_innerHTML=(
                "<div style='font-size:0.74em; color:#888; margin-bottom:2px;'>"
                "Net EV Charger Cost &nbsp;<em style='color:#aaa'>(hardware only — car not modeled)</em></div>"
            ))
            _cost_row(ev_install_cost, ev_rebate, net)
        else:
            solara.HTML(tag="div", unsafe_innerHTML=(
                "<div style='font-size:0.80em; color:#AAAAAA; margin-top:3px;'>"
                "No EV charger planned</div>"
            ))


@solara.component
def TransportationDetail():
    """Detail panel (§3.9) — two scenario columns: Do Nothing | Your Journey.

    Each column carries its own ICE + EV configuration. MPG and mi/kWh are shared
    physical specs (edit in either column). Pricing lives in Energy & Prices.
    """
    planned = ev_swap_planned.value
    gal_now    = transport_gasoline_miles.value / max(transport_mpg.value, 0.1)
    gal_after  = transport_ice_miles_after.value / max(transport_mpg.value, 0.1)
    ev_now     = transport_ev_miles_now.value
    ev_now_kwh = (ev_now / max(transport_ev_eff.value, 0.1)
                  / max(transport_charging_eff.value, 0.01))
    wall_kwh   = (transport_plan_electric_miles.value
                  / max(transport_ev_eff.value, 0.1)
                  / max(transport_charging_eff.value, 0.01))
    home_kwh   = wall_kwh * transport_pct_home_after.value
    ext_kwh    = wall_kwh * (1.0 - transport_pct_home_after.value)

    def _mpg_presets():
        with solara.Row(gap="3px", style="flex-wrap:wrap; margin-top:4px"):
            for lbl, val in [("Compact (35)", 35.0), ("Sedan (28)", 28.0),
                              ("SUV (20)", 20.0), ("Truck (16)", 16.0)]:
                is_sel = abs(transport_mpg.value - val) < 0.5
                solara.Button(lbl, on_click=lambda v=val: transport_mpg.set(v), style=(
                    "font-size:0.74em; padding:2px 7px; border-radius:10px;"
                    " cursor:pointer; margin:2px;"
                    + (" background:#FFCCBC; border:1px solid #FF7043; color:#BF360C;"
                       if is_sel else
                       " background:#F5F5F5; border:1px solid #DDD; color:#555;")))

    def _eff_presets():
        with solara.Row(gap="3px", style="flex-wrap:wrap; margin-top:4px"):
            for lbl, val in [("Efficient (4.5)", 4.5), ("Average (3.5)", 3.5),
                             ("SUV (2.5)", 2.5)]:
                is_sel = abs(transport_ev_eff.value - val) < 0.1
                solara.Button(lbl, on_click=lambda v=val: transport_ev_eff.set(v), style=(
                    "font-size:0.74em; padding:2px 7px; border-radius:10px;"
                    " cursor:pointer; margin:2px;"
                    + (" background:#C5CAE9; border:1px solid #7986CB; color:#3949AB;"
                       if is_sel else
                       " background:#F5F5F5; border:1px solid #DDD; color:#555;")))

    # Top row: Plan EV + Charger + install-year slider
    with solara.Row(gap="8px", style=_TOP_ROW):
        with solara.Column(style="min-width:150px"):
            _Check(label="Plan EV + Charger", value=ev_swap_planned)
        if planned:
            with solara.Column(style="flex:1; min-width:200px"):
                _YSl(ev_swap_year, _DEFAULTS["ev_swap_year"])

    with solara.Row(gap="0px", style="align-items:flex-start; flex-wrap:wrap"):
        # ── Left column: Do Nothing (current vehicles) ────────────────────────
        with solara.Column(style=_LEFT_COL):
            _DS("Do Nothing")
            solara.HTML(tag="div", unsafe_innerHTML=(
                "<div style='font-size:0.74em; color:#888; margin:-2px 0 4px'>"
                "Your current vehicles — kept every year.</div>"
            ))
            solara.Markdown(f"🚗 **ICE** · ~{gal_now:,.0f} gal/yr")
            _DSl("Gas miles/yr", transport_gasoline_miles,
                 _DEFAULTS["transport_gasoline_miles"],
                 1_000, 30_000, step=500, unit=" mi/yr")
            _DSl("Fuel economy", transport_mpg,
                 _DEFAULTS["transport_mpg"],
                 10.0, 60.0, step=0.5, unit=" MPG", fmt="{v:.1f}")
            _mpg_presets()

            solara.HTML(tag="hr", unsafe_innerHTML="", style="margin:8px 0; border-color:#EEE")
            if ev_now > 0:
                solara.Markdown(f"🔌 **EV** · ~{ev_now_kwh:,.0f} kWh/yr _(all external)_")
            else:
                solara.Markdown("🔌 **EV** · none today")
            _DSl("EV miles now", transport_ev_miles_now,
                 _DEFAULTS["transport_ev_miles_now"],
                 0, 30_000, step=500, unit=" mi/yr")
            solara.HTML(tag="div", unsafe_innerHTML=(
                "<div style='font-size:0.74em; color:#888; margin-top:2px'>"
                + ("Charged externally — no home charger in Do Nothing."
                   if ev_now > 0 else
                   "Set &gt; 0 if you already drive an EV today.")
                + "</div>"
            ))

        # ── Right column: Your Journey (after the switch) ─────────────────────
        with solara.Column(style=_RIGHT_COL):
            _DS("Your Journey")
            solara.HTML(tag="div", unsafe_innerHTML=(
                "<div style='font-size:0.74em; color:#888; margin:-2px 0 4px'>"
                "After the EV + charger year.</div>"
            ))
            if not planned:
                solara.HTML(tag="div", unsafe_innerHTML=(
                    "<div style='font-size:0.85em; color:#999; margin-top:4px;'>"
                    "Check 'Plan EV + Charger' above to configure the switch.</div>"
                ))
            else:
                solara.Markdown(
                    f"🚗 **ICE** · ~{gal_after:,.0f} gal/yr"
                    + ("  _(fully replaced)_" if transport_ice_miles_after.value == 0 else "")
                )
                _DSl("Gas mi after", transport_ice_miles_after,
                     _DEFAULTS["transport_ice_miles_after"],
                     0, 30_000, step=500, unit=" mi/yr")

                solara.HTML(tag="hr", unsafe_innerHTML="", style="margin:8px 0; border-color:#EEE")
                solara.Markdown(
                    f"🔌 **EV** · ~{wall_kwh:,.0f} kWh/yr "
                    f"({home_kwh:,.0f} home · {ext_kwh:,.0f} external)"
                )
                _DSl("EV miles/yr", transport_plan_electric_miles,
                     _DEFAULTS["transport_plan_electric_miles"],
                     1_000, 30_000, step=500, unit=" mi/yr")
                _DSl("Efficiency", transport_ev_eff,
                     _DEFAULTS["transport_ev_eff"],
                     2.0, 5.5, step=0.1, unit=" mi/kWh", fmt="{v:.1f}")
                _eff_presets()
                _DSl("% at home", transport_pct_home_after,
                     _DEFAULTS["transport_pct_home_after"],
                     0.50, 1.0, step=0.05, fmt="{v:.0%}")
                solara.HTML(tag="div", unsafe_innerHTML=(
                    "<div style='font-size:0.74em; color:#888; margin-top:2px'>"
                    "Rest billed at the External EV rate "
                    "<em style='color:#aaa'>(set in Energy &amp; Prices)</em>.</div>"
                ))
                _DSl("Charge eff", transport_charging_eff,
                     _DEFAULTS["transport_charging_eff"],
                     0.80, 0.98, step=0.01, fmt="{v:.2f}")

    # ── Full-width: L2 Charger Hardware ───────────────────────────────────────
    if planned:
        solara.HTML(tag="hr", unsafe_innerHTML="", style="margin:10px 0 6px; border-color:#EEE")
        _DS("L2 Charger Hardware")
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
        _DetailCosts(ev_install_cost, ev_rebate)


@solara.component
def CooktopSummaryCard():
    """§25.3.4 — state dropdown + plan year | install cost | rebate."""
    with solara.Column(classes=["device", "minor"]):
        _card_header("cooktop", "Cooktop")
        _appliance_rows(cooktop_starting_state, cooktop_swap_planned, cooktop_swap_year,
                        cooktop_install_cost, cooktop_rebate,
                        year_default=_DEFAULTS["cooktop_swap_year"])


@solara.component
def DryerSummaryCard():
    """§25.3.5 — state dropdown + plan year | install cost | rebate."""
    with solara.Column(classes=["device", "minor"]):
        _card_header("dryer", "Dryer")
        _appliance_rows(dryer_starting_state, dryer_swap_planned, dryer_swap_year,
                        dryer_install_cost, dryer_rebate,
                        year_default=_DEFAULTS["dryer_swap_year"])


@solara.component
def _PanelControls():
    """Panel Upgrade inline controls (no .device wrapper / header)."""
    planned = panel_upgrade_planned.value
    # Row 1: plan checkbox
    with solara.Row(gap="8px", style=_ROW_CTRL):
        _PlanCheck(panel_upgrade_planned, "Plan panel upgrade", right=False)
    # Row 2: full-width year slider + subscript
    if planned:
        with solara.Column(style="width:100%"):
            _YSl(panel_upgrade_year, _DEFAULTS["panel_upgrade_year"])
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
        _card_header("panel", "Electrical Panel")
        _PanelControls()


@solara.component
def _BaseloadControls():
    """Baseload inline controls — clean elec/gas readout + the standard plan →
    year + cost flow, matching the other appliance cards."""
    bl_kwh = compute_baseload_kwh(square_footage.value, num_bedrooms.value,
                                   baseload_constant_before.value)
    # Clean two-line readout (electricity + gas), plan-upgrade checkbox on the right
    with solara.Row(gap="8px", style=_ROW_CTRL + " align-items:center"):
        solara.HTML(tag="div", style="min-width:0; flex:0 1 auto", unsafe_innerHTML=(
            "<div style='display:grid; grid-template-columns:auto auto;"
            " gap:2px 10px; justify-content:start; align-items:baseline;"
            " font-size:0.82em; white-space:nowrap'>"
            "<span style='color:#888'>Electricity Baseload</span>"
            f"<strong style='color:#333'>{bl_kwh/12:,.0f} kWh/month</strong>"
            "<span style='color:#888'>Gas Baseload</span>"
            "<strong style='color:#333'>0 therms/month</strong>"
            "</div>"
        ))
        _PlanCheck(baseload_swap_planned, "Plan upgrade")
    # When planned: year slider + install/rebate cost row (same as other cards)
    if baseload_swap_planned.value:
        with solara.Column(style="width:100%"):
            _YSl(baseload_swap_year, _DEFAULTS["baseload_swap_year"])
        net = baseload_install_cost.value - baseload_rebate.value
        _cost_row(baseload_install_cost, baseload_rebate, net)
    else:
        solara.HTML(tag="div", unsafe_innerHTML=(
            "<div style='font-size:0.80em; color:#AAAAAA; margin-top:3px;'>"
            "No upgrade planned</div>"
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
        # Row 3: climate zone + source — pinned to ZIP (Phase 4 §1)
        _ci = _climate_info(zip_code.value, climate_trend.value)
        _src = ("⚠ ZIP not found — Bay Area default"
                if _ci.fallback else "CEC Title 24 zone · TMY3")
        solara.HTML(tag="div", unsafe_innerHTML=(
            f"<div style='font-size:0.82em; color:#555; margin-top:2px; line-height:1.45;'>"
            f"📍 <b>{_ci.zone_id} — {_ci.reference_city}</b>"
            f"<span style='color:#888;'> &nbsp;HDD {_ci.annual_hdd_65f:,.0f} · "
            f"CDD {_ci.annual_cdd_65f:,.0f}</span>"
            f"<br><span style='color:#999;'>{_src}</span></div>"
        ))


@solara.component
def SolarSummaryCard():
    """Solar + Battery summary card — panels slider, battery toggle, derived kW and coverage %."""
    planned = solar_planned.value
    with solara.Column(classes=["device"]):
        _card_header("solar", "Solar + Battery")
        with solara.Row(gap="10px", style=_ROW_CTRL):
            _Check(label="Add solar", value=solar_planned)
        if planned:
            # Panels slider
            panels = solar_panels.value
            system_kw = panels * solar_kw_per_panel.value
            with solara.Column(style="width:100%"):
                WhyWattSlider(
                    SliderSpec(key="solar_panels", title="Solar panels",
                               minimum=1, maximum=30, step=1,
                               default=_DEFAULTS["solar_panels"], decimals=0,
                               unit=f"≈ {system_kw:.1f} kW"),
                    value=solar_panels,
                )
            # Battery toggle
            with solara.Row(gap="8px", style="align-items:center"):
                _Check(label="Battery", value=solar_battery_enabled)
                if solar_battery_enabled.value:
                    solara.HTML(tag="div", unsafe_innerHTML=(
                        f"<div style='font-size:0.78em; color:#555;'>"
                        f"{solar_battery_kwh.value:.0f} kWh</div>"
                    ))
            # Install year
            with solara.Column(style="width:100%"):
                _YSl(solar_install_year, _DEFAULTS["solar_install_year"],
                     title="Install year")
        else:
            solara.HTML(tag="div", unsafe_innerHTML=(
                "<div style='font-size:0.80em; color:#AAAAAA; margin-top:3px;'>"
                "Not planned</div>"
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
    """Energy & Prices summary (§3.8) — three balance-matched sub-cards:
    Model Timeline · Home Energy Prices · External Energy Price."""
    # Seed the CAGR sliders from each utility's EIA historical CAGR (re-runs on ZIP/mode change).
    solara.use_effect(_seed_eia_cagr,
                      [zip_code.value, elec_rate_model_a.value, gas_rate_model_a.value,
                       elec_rate_model_b.value, gas_rate_model_b.value])

    def _hd(title, show_help=False):
        """Sub-card header: rates icon + title + (optional help) + ⋮ detail opener."""
        icon_svg = _DEVICE_ICONS.get("rates", "")
        with solara.Row(classes=["device-hd"], gap="0px", style="align-items:center; gap:8px"):
            if icon_svg:
                solara.HTML(tag="span", unsafe_innerHTML=f"<span class='di'>{icon_svg}</span>")
            solara.HTML(tag="span", unsafe_innerHTML=f"<span class='dn'>{title}</span>",
                        style="flex:1")
            if show_help:
                HelpButton("rates")
            solara.Button(
                "",
                on_click=lambda: detail_open.set(None if detail_open.value == "rates" else "rates"),
                classes=["iconbtn"],
                children=[solara.HTML(tag="span", unsafe_innerHTML=(
                    "<svg viewBox='0 0 24 24' fill='currentColor'>"
                    "<circle cx='5' cy='12' r='1.8'/><circle cx='12' cy='12' r='1.8'/>"
                    "<circle cx='19' cy='12' r='1.8'/></svg>"))],
            )

    # ── Card 1: Model Timeline ────────────────────────────────────────────────
    with solara.Column(classes=["device"]):
        _hd("Model Timeline", show_help=True)
        solara.SliderInt(f"⏱ Model: {years.value} yrs", value=years, min=5, max=30)

    # ── Card 2: Home Energy Prices — per-fuel rate model (My Utility / CA Average / ACC) ──
    with solara.Column(classes=["device"]):
        _hd("Home Energy Prices")
        _ri_auto = _rate_info(zip_code.value, "auto")
        _ri_ca   = _rate_info(zip_code.value, "ca_average")

        def _picker(fuel, heading, color, mode_rv, options, cagr_pct, acc_cagr_pct):
            solara.HTML(tag="div", unsafe_innerHTML=(
                f"<div style='font-size:0.78em; font-weight:600; color:{color};"
                f" margin-bottom:2px; margin-top:8px'>{heading}</div>"))
            _model_toggle("", mode_rv, options, color)
            name, prov, cagr = _fuel_resolved_display(
                fuel, mode_rv.value, cagr_pct, acc_cagr_pct, _ri_auto, _ri_ca)
            solara.HTML(tag="div", unsafe_innerHTML=_rate_line_html(fuel, name, prov, cagr))

        _picker("electricity", "⚡ Electricity Rate Model", C_RATE_ELEC, elec_rate_model_a,
                [("cagr_flat", "My Utility"), ("ca_average", "CA Average"), ("acc_shaped", "ACC")],
                elec_cagr_pct_a.value, acc_elec_cagr_a.value)
        _picker("gas", "🔥 Gas Rate Model", C_RATE_GAS, gas_rate_model_a,
                [("cagr_flat", "My Utility"), ("ca_average", "CA Average"), ("acc_seasonal", "ACC")],
                gas_cagr_pct_a.value, acc_gas_cagr_a.value)
        solara.HTML(tag="div", unsafe_innerHTML=(
            f"<div style='font-size:0.68em; color:#90A4AE; margin:5px 0 0 4px'>"
            f"{_APP_RATE_RESOLVER.data_vintage} · ZIP {zip_code.value}</div>"))

    # ── Card 3: External Energy Price (gasoline + external EV) ─────────────────
    gpr = gasoline_price.value
    gesc = gasoline_escalation_pct.value
    epr = external_ev_price_per_kwh.value
    eesc = external_ev_escalation_pct.value
    _kv = ("<div style='display:flex; justify-content:space-between;"
           " align-items:baseline; font-size:0.86em; padding:3px 0 3px 4px;'>"
           "<span style='color:#607D8B'>{k}</span>"
           "<strong style='color:#263238'>{v}</strong></div>")
    with solara.Column(classes=["device"]):
        _hd("External Energy Price")
        solara.HTML(tag="div", unsafe_innerHTML=(
            "<div style='font-size:0.78em; font-weight:600; color:#B8860B;"
            " margin-bottom:2px; margin-top:4px'>⛽ Gasoline Rate &amp; CAGR</div>"
        ))
        solara.HTML(tag="div", unsafe_innerHTML=(
            _kv.format(k="Gasoline Price", v=f"${gpr:.2f}/gal")
            + _kv.format(k="Gasoline CAGR", v=f"+{gesc}%/yr")
        ))
        solara.HTML(tag="div", unsafe_innerHTML=(
            "<div style='font-size:0.78em; font-weight:600; color:#1D9E75;"
            " margin-bottom:2px; margin-top:8px'>🔌 External EV Charging Rate &amp; CAGR</div>"
        ))
        solara.HTML(tag="div", unsafe_innerHTML=(
            _kv.format(k="EV Charging Rate", v=f"${epr:.2f}/kWh")
            + _kv.format(k="EV Charging CAGR", v=f"+{eesc}%/yr")
        ))


# ── §25.4 Detail windows ──────────────────────────────────────────────────────

@solara.component
def HVACDetail():
    """HVAC detail — two-column layout per §25.4.3."""
    state = hvac_starting_state.value
    ua    = compute_ua(insulation_quality.value, square_footage.value)

    # Full-width: state + plan controls
    with solara.Row(gap="8px", style=_TOP_ROW):
        with solara.Column(style="min-width:110px"):
            solara.Select("Starting state", value=hvac_starting_state,
                          values=["gas", "electric", "none"])
        if state != "electric":
            with solara.Column(style="min-width:70px"):
                _Check(label="Plan swap", value=hvac_swap_planned)
        if state != "electric" and hvac_swap_planned.value:
            # unified year slider — same as the summary card, but to the right of "Plan"
            with solara.Column(style="flex:1; min-width:200px"):
                WhyWattSlider(
                    SliderSpec(key="hvac_swap_year", title="Swap year",
                               minimum=1, maximum=25, step=1,
                               default=_DEFAULTS["hvac_swap_year"],
                               decimals=0, dtype="year",
                               base_year=sim_start_year.value),
                    value=hvac_swap_year,
                )

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
                _HSl("Furnace AFUE", furnace_afue, _DEFAULTS["furnace_afue"],
                     0.70, 0.95, 0.01, decimals=2)
                _HSl("Furnace age", hvac_furnace_age, _DEFAULTS["hvac_furnace_age"],
                     0, 30, 1, unit="yrs", decimals=0)
                _HSl("Furnace life", hvac_baseline_lifespan, _DEFAULTS["hvac_baseline_lifespan"],
                     5, 30, 1, unit="yrs", decimals=0)
                solara.Markdown(
                    f"*In-kind replacement: **${hvac_baseline_replace_cost.value:,}***",
                    style="font-size:0.82em; color:#555; margin-top:2px;")
                _Check(label="Has central AC (baseline)", value=hvac_has_cooling)
                if hvac_has_cooling.value:
                    _HSl("AC SEER", hvac_ac_seer, _DEFAULTS["hvac_ac_seer"], 10, 22, 1)
                    _HSl("AC age", hvac_ac_age, _DEFAULTS["hvac_ac_age"],
                         0, 20, 1, unit="yrs", decimals=0)
            with solara.Column(style=_RIGHT_COL):
                _DS("Replacement: Heat Pump HVAC")
                heat_kwh  = _est_hp_hvac_heating(hp_cop_heating.value, ua)
                cool_kwh2 = _est_hp_hvac_cooling(hp_seer_cooling.value, ua)
                solara.Markdown(
                    f"~**{heat_kwh:.0f} kWh/yr** heat  "
                    f"+ **{cool_kwh2:.0f} kWh/yr** cool  "
                    f"= **{heat_kwh + cool_kwh2:.0f} kWh/yr**"
                )
                _hp_size()
                _HSl("Heating COP", hp_cop_heating, _DEFAULTS["hp_cop_heating"],
                     2.5, 4.5, 0.1, decimals=1)
                _HSl("Cooling SEER", hp_seer_cooling, _DEFAULTS["hp_seer_cooling"], 16, 28, 1)
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
        _hp_size()
        _HSl("Heating COP", hp_cop_heating, _DEFAULTS["hp_cop_heating"],
             2.5, 4.5, 0.1, decimals=1)
        _HSl("Cooling SEER", hp_seer_cooling, _DEFAULTS["hp_seer_cooling"], 16, 28, 1)
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
                _hp_size()
                _HSl("Heating COP", hp_cop_heating, _DEFAULTS["hp_cop_heating"],
                     2.5, 4.5, 0.1, decimals=1)
                _HSl("Cooling SEER", hp_seer_cooling, _DEFAULTS["hp_seer_cooling"], 16, 28, 1)
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
                _Check(label="Plan swap", value=wh_swap_planned)
        if state != "electric" and wh_swap_planned.value:
            with solara.Column(style="flex:1; min-width:200px"):
                _YSl(wh_swap_year, _DEFAULTS["wh_swap_year"])

    _ElecAmpsInput("HPWH breaker A", hpwh_amps)

    # Shared full-width parameters (affect both gas and HPWH estimates)
    WhyWattSlider(
        SliderSpec(key="hw_daily_gallons", title="Daily hot water",
                   minimum=20, maximum=120, step=5,
                   default=_DEFAULTS["hw_daily_gallons"], unit="gal/day",
                   decimals=0, layout="inline"),
        value=hw_daily_gallons,
        on_change=lambda v: hw_gallons_user_override.set(True),
    )
    _DSl("Cold inlet", wh_inlet_temp_f, _DEFAULTS["wh_inlet_temp_f"],
         45, 75, 1, unit="°F")
    _DSl("Setpoint", wh_setpoint_f, _DEFAULTS["wh_setpoint_f"],
         110, 140, 5, unit="°F")

    if state == "gas":
        with solara.Row(gap="0px", style="align-items:flex-start; flex-wrap:wrap"):
            with solara.Column(style=_LEFT_COL):
                _DS("Current: Gas Water Heater")
                therms = _est_gas_wh(gas_wh_uef.value, gal, inlet, setp)
                solara.Markdown(
                    f"~**{therms:.0f} therms/yr** ≈ {_kwh_eq(therms):,.0f} kWh-eq")
                _DSl("Gas WH UEF", gas_wh_uef, _DEFAULTS["gas_wh_uef"],
                     0.55, 0.70, 0.01, fmt="{v:.2f}")
                _DSl("WH age", wh_gas_age, _DEFAULTS["wh_gas_age"], 0, 20, 1, unit=" yrs")
                _DSl("WH lifespan", wh_baseline_lifespan, _DEFAULTS["wh_baseline_lifespan"],
                     5, 20, 1, unit=" yrs")
                solara.Markdown(
                    f"*In-kind replacement: **${wh_baseline_replace_cost.value:,}***",
                    style="font-size:0.82em; color:#555; margin-top:2px;")
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
                _Check(label="Plan to add", value=ev_swap_planned)
        if state == "none" and ev_swap_planned.value:
            with solara.Column(style="flex:1; min-width:200px"):
                _YSl(ev_swap_year, _DEFAULTS["ev_swap_year"])

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
            _DSl("Charge eff", ev_charging_efficiency,
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
                _Check(label="Plan swap", value=cooktop_swap_planned)
        if state != "electric" and cooktop_swap_planned.value:
            with solara.Column(style="flex:1; min-width:200px"):
                _YSl(cooktop_swap_year, _DEFAULTS["cooktop_swap_year"])

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
                _DSl("Cooktop age", cooktop_age, _DEFAULTS["cooktop_age"],
                     0, 20, 1, unit=" yrs")
                _DSl("Cooktop life", cooktop_baseline_lifespan,
                     _DEFAULTS["cooktop_baseline_lifespan"], 5, 30, 1, unit=" yrs")
                solara.Markdown(
                    f"*In-kind replacement: **${cooktop_baseline_replace_cost.value:,}***",
                    style="font-size:0.82em; color:#555; margin-top:2px;")
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
                _Check(label="Plan swap", value=dryer_swap_planned)
        if state != "electric" and dryer_swap_planned.value:
            with solara.Column(style="flex:1; min-width:200px"):
                _YSl(dryer_swap_year, _DEFAULTS["dryer_swap_year"])

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
                _DSl("Dryer age", dryer_age, _DEFAULTS["dryer_age"],
                     0, 15, 1, unit=" yrs")
                _DSl("Dryer life", dryer_baseline_lifespan,
                     _DEFAULTS["dryer_baseline_lifespan"], 5, 25, 1, unit=" yrs")
                solara.Markdown(
                    f"*In-kind replacement: **${dryer_baseline_replace_cost.value:,}***",
                    style="font-size:0.82em; color:#555; margin-top:2px;")
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
        _Check(label="Plan 200 Amps panel upgrade", value=panel_upgrade_planned)
        if planned:
            with solara.Column(style="flex:1; min-width:200px"):
                _YSl(panel_upgrade_year, _DEFAULTS["panel_upgrade_year"])

    solara.HTML(tag="div", unsafe_innerHTML=(
        "<div style='font-size:0.85em; color:#666; margin-bottom:10px;'>"
        "Often required when adding an EV charger (L2) or heat pump to older "
        "homes with 100A panels. Pure capital cost — no energy savings modelled.</div>"
    ))
    # Current panel size — drives the Estimated Electrical Load assessment (Phase 3 §5)
    with solara.Column(style="max-width:220px; margin-bottom:8px"):
        solara.Select("Current panel size (Amps)", value=panel_amps, values=[100, 150, 200])
    # NEC load-calculation method — Optional (220.82) is the Bay Area permit default
    with solara.Column(style="max-width:260px; margin-bottom:6px"):
        solara.Select("Load calc method", value=panel_calc_method,
                      values=["optional", "standard"])
    solara.HTML(tag="div", unsafe_innerHTML=(
        "<div style='font-size:0.8em; color:#666; margin-bottom:10px;'>"
        "<strong>Optional (NEC 220.82)</strong> — Bay Area permit default; pools "
        "appliances under the 10&nbsp;kVA/40% demand factor (HVAC at 100%). "
        "<strong>Standard</strong> adds every appliance at 100% — always higher.</div>"
    ))
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
    _DSl("Always-on", baseload_constant_before,
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
        _Check(label="Plan efficiency upgrade (LED, smart plugs…)",
                        value=baseload_swap_planned)
        if baseload_swap_planned.value:
            with solara.Column(style="flex:1; min-width:200px"):
                _YSl(baseload_swap_year, _DEFAULTS["baseload_swap_year"])
    if baseload_swap_planned.value:
        bl_after = compute_baseload_kwh(square_footage.value, num_bedrooms.value,
                                        baseload_constant_after.value)
        saving           = bl_before - bl_after
        annual_saving_usd = saving * 0.386
        net_cost         = baseload_install_cost.value - baseload_rebate.value
        pb = (net_cost / annual_saving_usd) if annual_saving_usd > 0 else None
        _DSl("After upgrade", baseload_constant_after,
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
    _ci = _climate_info(zip_code.value, climate_trend.value)

    _DS("Location & Climate")
    solara.InputText("ZIP code", value=zip_code)
    if _ci.fallback:
        solara.HTML(tag="div", unsafe_innerHTML=(
            "<div style='font-size:0.82em; color:#b8860b; margin:3px 0;'>"
            "⚠ ZIP not recognized — using Bay Area defaults (CZ4)</div>"))
    solara.HTML(tag="div", unsafe_innerHTML=(
        f"<div style='font-size:0.85em; color:#444; margin:3px 0; line-height:1.5;'>"
        f"Climate zone <b>{_ci.zone_id} — {_ci.reference_city}</b><br>"
        f"<span style='color:#666;'>Heating <b>{_ci.annual_hdd_65f:,.0f}</b> HDD · "
        f"Cooling <b>{_ci.annual_cdd_65f:,.0f}</b> CDD <span style='color:#999;'>(base 65°F)</span></span>"
        f"<br><span style='color:#999;'>Source: CEC Title 24 zone · NREL TMY3</span></div>"))
    solara.Select("Bedrooms", value=num_bedrooms, values=[1, 2, 3, 4, 5])
    solara.InputInt("Square footage", value=square_footage)
    solara.InputInt("Year built", value=year_built)
    solara.Markdown("---")

    _DS("Climate Trend")
    solara.Select("Warming scenario",
                  value=_TREND_LABELS[climate_trend.value],
                  values=list(_TREND_LABELS.values()),
                  on_value=lambda lbl: climate_trend.set(
                      {v: k for k, v in _TREND_LABELS.items()}[lbl]))
    _trend_note = ("No trend — static TMY3 (reproduces base climate)"
                   if climate_trend.value == "none"
                   else "Applied per simulation year to HDD/CDD (Cal-Adapt)")
    solara.HTML(tag="div", unsafe_innerHTML=(
        f"<div style='font-size:0.82em; color:#666; margin-top:4px; line-height:1.5;'>"
        f"Modeled CAGR: HDD <b>{_ci.hdd_cagr * 100:+.2f}%/yr</b> · "
        f"CDD <b>{_ci.cdd_cagr * 100:+.2f}%/yr</b>"
        f"<br><span style='color:#999;'>{_trend_note}</span></div>"))
    solara.Markdown("---")

    _DS("Building Performance")
    solara.Select("Insulation quality", value=insulation_quality,
                  values=["poor", "average", "good"])
    ua = compute_ua(insulation_quality.value, square_footage.value)
    solara.HTML(tag="div", unsafe_innerHTML=(
        f"<div style='font-size:0.82em; color:#666; margin-top:4px;'>"
        f"UA = {ua:,.0f} BTU/hr/°F  ·  Annual HDD {_ci.annual_hdd_65f:,.0f} · "
        f"CDD {_ci.annual_cdd_65f:,.0f} ({_ci.reference_city} TMY3)</div>"
    ))


@solara.component
def SolarDetail(model):
    """Solar + battery detail panel (§8)."""
    planned = solar_planned.value
    net = solar_system_cost.value - solar_rebate.value

    # ── Row 1: checkbox + full-width install-year slider ─────────────────────
    with solara.Row(gap="12px", style=_TOP_ROW + " align-items:center"):
        _Check(label="Adding solar to my journey", value=solar_planned)
        if planned:
            with solara.Column(style="flex:1; min-width:220px"):
                _YSl(solar_install_year, _DEFAULTS["solar_install_year"],
                     title="Install year")

    if not planned:
        solara.Text("Enable solar above to configure options.",
                    style="font-size:0.85em; color:#888")
        return

    # Derived quantities
    panels     = solar_panels.value
    kw_panel   = solar_kw_per_panel.value
    yield_kwh  = solar_specific_yield.value
    system_kw  = panels * kw_panel
    annual_kwh = system_kw * yield_kwh
    scf_pct    = solar_scf.value
    scf        = scf_pct / 100.0
    self_kwh   = annual_kwh * scf
    export_kwh = annual_kwh * (1.0 - scf)
    nem        = solar_nem_mode.value
    battery_on = solar_battery_enabled.value
    credit_label = "ACC credit" if nem == "nbt" else "NEM 2.0 credit"

    # Shared sub-section box style — matches _COSTS_BOX palette
    _BOX = ("padding:8px 12px; background:#F0F4FF; border-radius:6px;"
            " margin-top:6px; border:1px solid #C5CAE9;")

    # ── Row 2: [System Size] | [Battery & Net Metering] — equal-width boxes ──
    _HALF = "flex:1; min-width:200px"

    with solara.Row(gap="8px", style="align-items:flex-start; flex-wrap:wrap; margin-top:4px"):

        # Left box — System Size
        with solara.Column(style=_HALF):
            with solara.Column(style=_BOX):
                _DS("System Size")
                WhyWattSlider(
                    SliderSpec(key="solar_panels", title="Solar panels",
                               minimum=1, maximum=30, step=1,
                               default=_DEFAULTS["solar_panels"], decimals=0,
                               unit=f"≈ {system_kw:.1f} kW"),
                    value=solar_panels,
                )

        # Right box — Battery & Net Metering
        with solara.Column(style=_HALF):
            with solara.Column(style=_BOX):
                _DS("Battery &amp; Net Metering")

                def _on_battery(enabled):
                    solar_battery_enabled.set(enabled)
                    solar_scf.set(80 if enabled else 35)

                # Single line: [x] Battery  [13.5 kWh]  |  ⦿ NEM 3.0/NBT  ○ NEM 2.0
                with solara.Row(gap="4px", style="align-items:center; flex-wrap:wrap"):
                    _Check(label="Battery", value=solar_battery_enabled,
                                    on_value=_on_battery)
                    if battery_on:
                        with solara.Column(style="width:80px; flex-shrink:0"):
                            solara.InputFloat("kWh", value=solar_battery_kwh)
                    # Thin separator
                    solara.HTML(tag="span", unsafe_innerHTML=(
                        "<span style='color:#C5CAE9; margin:0 4px;'>|</span>"
                    ))
                    # NEM radio options inline
                    for key, lbl in [("nbt", "NEM 3.0/NBT"), ("nem2", "NEM 2.0")]:
                        active = nem == key
                        solara.Button(
                            ("⦿ " if active else "○ ") + lbl,
                            on_click=lambda k=key: solar_nem_mode.set(k),
                            style=(
                                "background:none; border:none; padding:0 6px 0 0; min-width:0;"
                                " font-size:0.78em; cursor:pointer;"
                                " color:#1D9E75; font-weight:600; white-space:nowrap;"
                                if active else
                                "background:none; border:none; padding:0 6px 0 0; min-width:0;"
                                " font-size:0.78em; cursor:pointer; color:#555; white-space:nowrap;"
                            ),
                        )

                solara.HTML(tag="div", unsafe_innerHTML=(
                    "<div style='font-size:0.73em; color:#888; margin-top:2px;'>"
                    + ("Export: ACC avoided cost (~$0.06/kWh avg)" if nem == "nbt"
                       else f"Export: retail − ${solar_nbc.value:.3f}/kWh NBC")
                    + "</div>"
                ))

    # ── Row 3: Self-Consumption slider — full-width box ───────────────────────
    with solara.Column(style=_BOX):
        with solara.Row(gap="8px", style="align-items:center; flex-wrap:wrap"):
            with solara.Column(style="flex:1; min-width:160px"):
                _DSl("Self-use", solar_scf, _DEFAULTS["solar_scf"],
                     10, 98, 1, unit="%")
            solara.HTML(tag="div", unsafe_innerHTML=(
                "<div style='font-size:0.73em; color:#888; min-width:120px;'>"
                "Default: 80% with battery · 35% solar-only</div>"
            ))

    # ── Row 4: Advanced (PVWatts) — 2 panels: [label+input | stat] with divider ─
    # Compute home need from final simulation year (fully-electrified state).
    home_need_kwh = None
    solar_coverage_pct = None
    final_sim_yr = None
    if model is not None:
        jh = model.journey_home
        cons_hists = [h for h in jh.consumption_history_by_slot.values() if h]
        if cons_hists:
            final_idx = len(cons_hists[0]) - 1
            final_sim_yr = final_idx + 1
            total_elec = 0.0
            for sname, cons_h in jh.consumption_history_by_slot.items():
                fuel_h = jh.fuel_history_by_slot.get(sname, [])
                if final_idx < len(cons_h) and final_idx < len(fuel_h):
                    if fuel_h[final_idx] == "electricity":
                        total_elec += cons_h[final_idx]
            if total_elec > 0:
                home_need_kwh = total_elec
                solar_coverage_pct = min(100, int(self_kwh / total_elec * 100))

    with solara.Column(style=_BOX):
        _DS("Advanced (PVWatts)")
        _LBL = ("display:inline-block; font-size:0.80em; color:#555;"
                " width:140px; flex-shrink:0; line-height:1.2;")

        with solara.Row(gap="0", style="align-items:stretch; flex-wrap:nowrap"):

            # ── Left panel: inputs ───────────────────────────────────────────
            with solara.Column(style="flex:1; min-width:160px; gap:4px"):
                with solara.Row(gap="6px", style="align-items:center"):
                    solara.HTML(tag="span", unsafe_innerHTML=(
                        f"<span style='{_LBL}'>kW / panel</span>"
                    ))
                    solara.InputFloat("", value=solar_kw_per_panel)
                with solara.Row(gap="6px", style="align-items:center"):
                    solara.HTML(tag="span", unsafe_innerHTML=(
                        f"<span style='{_LBL}'>Yield (kWh/kW/yr)</span>"
                    ))
                    solara.InputInt("", value=solar_specific_yield)
                solara.HTML(tag="div", unsafe_innerHTML=(
                    "<div style='font-size:0.74em; color:#888; padding-left:2px;"
                    " margin-top:2px;'>CA: ~1,400 fog coast · ~1,650 inland</div>"
                ))
                # Spacer rows to match home-need rows on the right when model has run
                if home_need_kwh is not None:
                    solara.HTML(tag="div", unsafe_innerHTML=(
                        f"<div style='font-size:0.80em; color:#888; margin-top:8px;"
                        f" border-top:1px dashed #C5CAE9; padding-top:6px;'>"
                        f"Journey home (yr {final_sim_yr})</div>"
                    ))

            # ── Vertical divider ─────────────────────────────────────────────
            solara.HTML(tag="div", unsafe_innerHTML=(
                "<div style='width:2px; background:#C5CAE9; margin:0 10px;"
                " align-self:stretch; flex-shrink:0;'></div>"
            ))

            # ── Right panel: derived stats — HTML table for exact alignment ──
            _td_l = "font-size:0.80em; color:#555; white-space:nowrap; padding:4px 4px 4px 0"
            _td_r = "font-size:0.80em; color:#333; text-align:right; white-space:nowrap; padding:4px 0"
            _td_sep = "padding:4px 0; border-top:1px dashed #C5CAE9;"

            # Build optional home-need rows
            need_rows = ""
            if home_need_kwh is not None:
                cov_color = "#1D9E75" if solar_coverage_pct >= 80 else (
                    "#F57C00" if solar_coverage_pct >= 50 else "#C62828")
                need_rows = (
                    f"<tr><td colspan='2' style='{_td_sep}'></td></tr>"
                    f"<tr>"
                    f"  <td style='{_td_l}'>Home need (yr {final_sim_yr})</td>"
                    f"  <td style='{_td_r}'><b>{home_need_kwh:,.0f}</b> kWh</td>"
                    f"</tr><tr>"
                    f"  <td style='{_td_l}'>Solar covers</td>"
                    f"  <td style='{_td_r}'><b style='color:{cov_color}'>"
                    f"{solar_coverage_pct}%</b></td>"
                    f"</tr>"
                )

            with solara.Column(style="flex:1; min-width:140px"):
                solara.HTML(tag="div", unsafe_innerHTML=(
                    f"<table style='width:100%; border-collapse:collapse;'>"
                    f"<tr>"
                    f"  <td style='{_td_l}'>Gross production</td>"
                    f"  <td style='{_td_r}'><b>{annual_kwh:,.0f}</b> kWh</td>"
                    f"</tr><tr>"
                    f"  <td style='{_td_l}'>Self-consumed</td>"
                    f"  <td style='{_td_r}'><b>{self_kwh:,.0f}</b> kWh"
                    f"  <span style='color:#888; font-size:0.9em'>&nbsp;→ retail</span></td>"
                    f"</tr><tr>"
                    f"  <td style='{_td_l}'>Exported</td>"
                    f"  <td style='{_td_r}'><b>{export_kwh:,.0f}</b> kWh"
                    f"  <span style='color:#888; font-size:0.9em'>&nbsp;→ {credit_label}</span></td>"
                    f"</tr>{need_rows}</table>"
                ))

        # Payback line (only once model has run)
        if model is not None and model.journey_home.solar_savings_history:
            annual_saving = model.journey_home.solar_savings_history[0]
            if annual_saving > 0 and net > 0:
                solara.HTML(tag="div", unsafe_innerHTML=(
                    f"<div style='font-size:0.82em; color:#1976D2; margin-top:4px;"
                    f" border-top:1px solid #C5CAE9; padding-top:4px;'>"
                    f"~${annual_saving:,.0f}/yr saving"
                    f" &nbsp;·&nbsp; payback ~{net / annual_saving:.1f} yrs</div>"
                ))

    # ── Footer: Cost & Rebate ─────────────────────────────────────────────────
    with solara.Column(style=_COSTS_BOX):
        solara.HTML(tag="div", unsafe_innerHTML=(
            "<div style='font-weight:700; font-size:0.9em; color:#0D47A1;"
            " border-bottom:1px solid #C5CAE9; padding-bottom:4px;"
            " margin-bottom:6px;'>Cost &amp; Rebate</div>"
        ))
        solara.HTML(tag="div", unsafe_innerHTML=(
            "<div style='font-size:0.79em; color:#555; margin-bottom:6px;'>"
            "Enter the total installed cost from your contractor quote.</div>"
        ))
        with solara.Row(gap="12px", style="flex-wrap:wrap; align-items:center"):
            with solara.Column(style="min-width:130px"):
                solara.InputInt("Total cost $", value=solar_system_cost)
            with solara.Column(style="min-width:120px"):
                solara.InputInt("Rebate $", value=solar_rebate)
            solara.HTML(tag="div", unsafe_innerHTML=(
                f"<div style='font-size:1.05em; font-weight:700; color:#1976D2;'>"
                f"Net ${net:,}</div>"
            ))


def _fuel_model_block(fuel: str, heading: str, color: str,
                       model_rv, cagr_rv, acc_cagr_rv,
                       model_options: list, cagr_max: int, ri_auto, ri_ca):
    """Fuel rate model section: 3-way mode toggle + resolved name line + the editable CAGR
    slider (EIA modes, seeded from JSON) or the ACC base-escalation slider."""
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
    # Resolved utility for this fuel + mode (name + provenance badge).
    _name, _prov, _ = _fuel_resolved_display(
        fuel, model_rv.value, cagr_rv.value, acc_cagr_rv.value, ri_auto, ri_ca)
    solara.HTML(tag="div", unsafe_innerHTML=_rate_line_html(fuel, _name, _prov, None))
    _fkey = "elec" if fuel == "electricity" else "gas"
    _cagr_def = _DEFAULTS[f"{_fkey}_cagr_pct_a"]            # A/B share factory default
    _acc_def = _DEFAULTS[f"acc_{_fkey}_cagr_a"]
    if model_rv.value in ("cagr_flat", "ca_average"):
        WhyWattSlider(
            SliderSpec(key=f"{fuel}_cagr", title="Escalation",
                       minimum=0, maximum=cagr_max, step=1, default=_cagr_def,
                       decimals=0, unit="%/yr", layout="inline"),
            value=cagr_rv,
        )
    else:
        # ACC mode: expose base escalation slider
        WhyWattSlider(
            SliderSpec(key=f"{fuel}_acc_cagr", title="Escalation",
                       minimum=0, maximum=cagr_max, step=1, default=_acc_def,
                       decimals=0, unit="%/yr", layout="inline"),
            value=acc_cagr_rv,
        )
        solara.HTML(tag="div", unsafe_innerHTML=(
            "<div style='font-size:0.75em; color:#546E7A; margin:1px 0 4px'>"
            "ACC shape redistributes costs within each year. "
            "This slider sets the overall rate trajectory.</div>"
        ))


@solara.component
def RatesDetail():
    """Energy & Prices detail panel (§3.8) — timeline on top; gasoline + external EV
    are single shared values below Scenario A; A/B governs electricity + gas only."""
    # ── Model timeline (top) ──────────────────────────────────────────────────
    _DS("⏱ Model Timeline")
    solara.SliderInt(f"Years to model: {years.value}", value=years, min=5, max=30)

    solara.HTML(tag="div", unsafe_innerHTML=(
        "<div style='border-top:1px solid #E0E0E0; margin:10px 0 6px'></div>"
    ))

    # ── Scenario A — electricity + gas (scenario-split) ───────────────────────
    _ri_auto = _rate_info(zip_code.value, "auto")
    _ri_ca   = _rate_info(zip_code.value, "ca_average")
    _DS("Scenario A")
    _fuel_model_block("electricity", "⚡ Electricity Rate Model", C_RATE_ELEC,
                       elec_rate_model_a, elec_cagr_pct_a, acc_elec_cagr_a,
                       [("cagr_flat", "My Utility"), ("ca_average", "CA Average"),
                        ("acc_shaped", "ACC")], 15, _ri_auto, _ri_ca)
    _fuel_model_block("gas", "🔥 Gas Rate Model", C_RATE_GAS,
                       gas_rate_model_a, gas_cagr_pct_a, acc_gas_cagr_a,
                       [("cagr_flat", "My Utility"), ("ca_average", "CA Average"),
                        ("acc_seasonal", "ACC")], 20, _ri_auto, _ri_ca)

    # ── Shared transport fuels (NOT scenario-split) ───────────────────────────
    solara.HTML(tag="div", unsafe_innerHTML=(
        "<div style='border-top:1px solid #E0E0E0; margin:10px 0 6px'></div>"
    ))
    _DS("Transport Fuels  (shared across scenarios)")
    _DSl("⛽ Gas price", gasoline_price, _DEFAULTS["gasoline_price"],
         2.00, 8.00, step=0.10, unit=" $/gal", fmt="{v:.2f}")
    _DSl("⛽ Change/yr", gasoline_escalation_pct, _DEFAULTS["gasoline_escalation_pct"],
         -5, 10, step=1, unit=" %/yr")
    _DSl("🔌 EV price", external_ev_price_per_kwh,
         _DEFAULTS["external_ev_price_per_kwh"],
         0.10, 0.60, step=0.01, unit=" $/kWh", fmt="{v:.2f}")
    _DSl("🔌 Change/yr", external_ev_escalation_pct,
         _DEFAULTS["external_ev_escalation_pct"],
         -5, 10, step=1, unit=" %/yr")
    solara.HTML(tag="div", unsafe_innerHTML=(
        f"<div style='font-size:0.76em; color:#888; margin-top:4px'>"
        f"Gasoline yr 10: <strong>"
        f"${gasoline_price.value * (1 + gasoline_escalation_pct.value/100)**9:.2f}/gal</strong>"
        f" &nbsp;·&nbsp; External EV yr 10: <strong>"
        f"${external_ev_price_per_kwh.value * (1 + external_ev_escalation_pct.value/100)**9:.2f}/kWh"
        f"</strong></div>"
    ))

    # ── Compare A/B (electricity + gas only) ──────────────────────────────────
    solara.HTML(tag="div", unsafe_innerHTML=(
        "<div style='border-top:1px solid #E0E0E0; margin:10px 0 6px'></div>"
    ))
    _Check(label="Compare two scenarios (A vs B)", value=comparison_mode)
    if comparison_mode.value:
        solara.HTML(tag="div", unsafe_innerHTML=(
            "<div style='font-size:0.80em; color:#888; margin:4px 0 2px'>"
            "Scenario A above — solid lines on charts. "
            "Transport fuels are shared (not split).</div>"
        ))
        _DS("Scenario B  (dashed lines)")
        _fuel_model_block("electricity", "⚡ Electricity Rate Model", C_RATE_ELEC,
                           elec_rate_model_b, elec_cagr_pct_b, acc_elec_cagr_b,
                           [("cagr_flat", "My Utility"), ("ca_average", "CA Average"),
                            ("acc_shaped", "ACC")], 15, _ri_auto, _ri_ca)
        _fuel_model_block("gas", "🔥 Gas Rate Model", C_RATE_GAS,
                           gas_rate_model_b, gas_cagr_pct_b, acc_gas_cagr_b,
                           [("cagr_flat", "My Utility"), ("ca_average", "CA Average"),
                            ("acc_seasonal", "ACC")], 20, _ri_auto, _ri_ca)


# ── §25 Summary panel components ─────────────────────────────────────────────

@solara.component
def JourneyPlannerPanel():
    with solara.Column(classes=["card"]):
        with solara.Row(classes=["card-hd"]):
            _card_header_main("journey", "Your Electrification Journey", "journey_planner")
        with solara.Column(classes=["card-bd"], gap="8px"):
            HVACSummaryCard()
            WHSummaryCard()
            TransportationSummaryCard()
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
# _SOCIAL_IC -> ui/icons.py (Phase 4.5)


@solara.component
def _SocialBody():
    """Social & Health Cost of Gas — card-bd content (two .device sub-cards)."""
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
                # Phase 5 §1 test bed — unified debounced slider, owns its gate checkbox
                WhyWattSlider(
                    SliderSpec(
                        key="social_climate_rate", title="Climate rate",
                        minimum=1.00, maximum=2.00, step=0.01,
                        default=_DEFAULTS["social_climate_rate"],
                        unit="$/therm", decimals=2,
                        gate_label="Add CO₂ + Methane Cost",
                    ),
                    value=social_climate_rate,
                    enabled=social_climate_enabled,
                )

            # ── Health Cost device card ───────────────────────────────────────
            with solara.Column(classes=["device"]):
                solara.HTML(tag="div", unsafe_innerHTML=(
                    f"<div class='device-hd'>"
                    f"<span class='di'>{_HEALTH_IC}</span>"
                    f"<span class='dn'>Health Cost</span>"
                    f"</div>"
                ))
                WhyWattSlider(
                    SliderSpec(
                        key="social_health_rate", title="Health rate",
                        minimum=0.50, maximum=2.00, step=0.01,
                        default=_DEFAULTS["social_health_rate"],
                        unit="$/therm", decimals=2,
                        gate_label="Add Air-Quality Cost",
                    ),
                    value=social_health_rate,
                    enabled=social_health_enabled,
                )

            # ── Gasoline externalities ────────────────────────────────────────
            _GAS_IC = ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                       " stroke-linecap='round' stroke-linejoin='round'>"
                       "<path d='M3 19h2l1-5h10l1 5h2'/>"
                       "<path d='M7 14V7a2 2 0 012-2h6a2 2 0 012 2v7'/>"
                       "<path d='M17 7h2a2 2 0 012 2v3a2 2 0 01-2 2h-2'/></svg>")
            solara.HTML(tag="div", unsafe_innerHTML=(
                f"<div class='device-hd' style='margin-top:12px;'>"
                f"<span class='di'>{_GAS_IC}</span>"
                f"<span class='dn'>Gasoline Externalities</span>"
                f"</div>"
            ))
            with solara.Column(classes=["device"]):
                WhyWattSlider(
                    SliderSpec(key="gasoline_climate_cost_per_gallon",
                               title="Climate rate", minimum=0.50, maximum=4.00, step=0.01,
                               default=_DEFAULTS["gasoline_climate_cost_per_gallon"],
                               unit="$/gal", decimals=2, gate_label="Add Climate Cost"),
                    value=gasoline_climate_cost_per_gallon,
                    enabled=gasoline_climate_enabled,
                )
            with solara.Column(classes=["device"]):
                WhyWattSlider(
                    SliderSpec(key="gasoline_health_cost_per_gallon",
                               title="Health rate", minimum=0.25, maximum=2.00, step=0.05,
                               default=_DEFAULTS["gasoline_health_cost_per_gallon"],
                               unit="$/gal", decimals=2, gate_label="Add Health Cost"),
                    value=gasoline_health_cost_per_gallon,
                    enabled=gasoline_health_enabled,
                )



__all__ = ['_DETAIL_TITLES', '_LEFT_COL', '_RIGHT_COL', '_COSTS_BOX', '_CARD_NORMAL', '_CARD_OPEN', '_ROW_CTRL', '_TOP_ROW', 'DetailTitleBar', '_DS', '_DSl', '_elec_display', '_ElecAmpsInput', '_DetailCosts', '_card_header', '_card_header_main', '_panel_hd', '_PlanCheck', '_Check', '_cost_row', '_appliance_rows', 'HVACSummaryCard', 'WHSummaryCard', 'TransportationSummaryCard', 'TransportationDetail', 'CooktopSummaryCard', 'DryerSummaryCard', '_PanelControls', 'PanelSummaryCard', '_BaseloadControls', 'BaseloadSummaryCard', 'HomeSummaryCard', 'SolarSummaryCard', '_model_toggle', 'RatesSummaryCard', 'HVACDetail', 'WaterHeaterDetail', 'EVDetail', 'CooktopDetail', 'DryerDetail', 'ElecPanelDetail', 'BaseloadDetail', 'HomeDetail', 'SolarDetail', '_fuel_model_block', 'RatesDetail', 'JourneyPlannerPanel', 'HomeProfilePanel', 'EnergyPricesPanel', '_SocialBody']
