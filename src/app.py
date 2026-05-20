"""
WhyWatt? — Solara UI (Phase 2 / Objective 6 — Journey Planner)
"""
import os
import solara
import numpy as np
import matplotlib
import matplotlib.ticker
from matplotlib.lines import Line2D
matplotlib.use("Agg")
from matplotlib.figure import Figure
from model import HESModel, SCENARIO_PRESETS
from home_config import HomeConfig
from journey import CATEGORY_ORDER, CATEGORY_LABELS

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
]

# ── Reactive state ─────────────────────────────────────────────────────────────

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

# ── Labels / option lists ──────────────────────────────────────────────────────
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
    hvac_baseline = [{"class": "GasFurnace", "afue": furnace_afue.value, "age": 10}]
    if has_ac:
        hvac_baseline.append({"class": "CentralAC", "seer_cooling": 14,
                               "age": 7, "installation_cost": 5000})
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
            "baseline_devices": [{"class": "GasWaterHeater",
                                   "uef": gas_wh_uef.value, "age": 5}],
            "electric_device": {"class": "HeatPumpWaterHeater", "uef": hpwh_uef.value},
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
            "baseline_devices": [{"class": "GasDryer",
                                   "therms_per_cycle": 0.22, "cycles_per_week": 5}],
            "electric_device": {"class": "HeatPumpDryer",
                                "kwh_per_cycle": 1.8, "cycles_per_week": 5},
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
            "baseline_devices": [{"class": "GasCooktop",
                                   "therms_per_meal": 0.05, "meals_per_week": 14}],
            "electric_device": {"class": "InductionCooktop",
                                "kwh_per_meal": 0.9, "meals_per_week": 14},
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
            "electric_device": {"class": "EVCharger"},
            "swap_year": _eff_swap_year(ev_starting_state.value,
                                        ev_swap_planned.value, ev_swap_year.value),
            "install_cost": ev_install_cost.value,
            "rebate": ev_rebate.value,
        },
        {
            "name": "Lights and Appliances",
            "category": "Baseload",
            "starting_state": "electric",
            "has_cooling_baseline": False,
            "baseline_devices": [],
            "electric_device": {"class": "LightsAndPlugs", "annual_kwh": 1200},
            "swap_year": None,
            "install_cost": 0,
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
    )
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
    fig = _new_fig()
    ax  = fig.add_subplot(111)
    x = np.arange(1, n + 1)
    b = df["Baseline Cum Cost"].values
    e = df["Journey Cum Cost"].values
    lbl_a = " (A)" if model.comparison_mode else ""
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
    ax.legend(handles=handles, fontsize=8, loc="lower right")
    _style(ax)
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

@solara.component
def ChartPane(chart_name, model, df, n):
    fig = CHART_FNS[chart_name](df, model, n)
    solara.FigureMatplotlib(fig)


@solara.component
def HomeInfoBar():
    """Chip row reading from reactive home-profile state — no model object needed."""
    insulation = insulation_quality.value.capitalize()
    solara.Markdown(
        f"📍 **San Jose, CA** &nbsp;·&nbsp; ZIP {zip_code.value} "
        f"&nbsp;·&nbsp; Climate Zone {climate_zone.value} "
        f"&nbsp;·&nbsp; {num_bedrooms.value} bed "
        f"&nbsp;·&nbsp; {square_footage.value:,} sq ft "
        f"&nbsp;·&nbsp; Built {year_built.value} "
        f"&nbsp;·&nbsp; {insulation} insulation",
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
def JourneyPlannerPanel():
    with solara.Card("🗺️ Your Electrification Journey", margin=0, elevation=1):
        # Column header hint
        with solara.Row(gap="8px",
                        style="padding:2px 0 4px 0; font-size:0.76em; color:#999"):
            solara.Text("Appliance",     style="min-width:110px; max-width:110px; font-weight:600")
            solara.Text("State",         style="min-width:95px;  max-width:95px")
            solara.Text("Plan swap?",    style="min-width:65px;  max-width:65px")
            solara.Text("Year / Cost",   style="flex:1")

        SlotRow("HVAC",
                hvac_starting_state, hvac_swap_planned,
                hvac_swap_year, hvac_install_cost, hvac_rebate)
        with solara.Row(style="padding:2px 0 2px 8px"):
            solara.Checkbox(
                label="Has central AC in baseline (models separate furnace + AC aging)",
                value=hvac_has_cooling,
            )

        SlotRow("Water Heater",
                wh_starting_state, wh_swap_planned,
                wh_swap_year, wh_install_cost, wh_rebate)
        SlotRow("Dryer",
                dryer_starting_state, dryer_swap_planned,
                dryer_swap_year, dryer_install_cost, dryer_rebate)
        SlotRow("Cooktop",
                cooktop_starting_state, cooktop_swap_planned,
                cooktop_swap_year, cooktop_install_cost, cooktop_rebate)
        SlotRow("EV Charger",
                ev_starting_state, ev_swap_planned,
                ev_swap_year, ev_install_cost, ev_rebate)

        solara.Markdown(
            "<small style='color:#888'>ℹ️ <em>\"Do nothing\" baseline runs automatically: "
            "gas devices stay gas; already-done devices stay electric; "
            "no EV added.</em></small>"
        )


@solara.component
def HomeProfilePanel():
    with solara.Card("🏠 Home Profile", margin=0, elevation=1):
        solara.Markdown("**Home Details**")
        solara.InputText("ZIP code", value=zip_code)
        solara.Select("Climate zone", value=climate_zone, values=_CZ_OPTIONS)
        solara.Select("Bedrooms", value=num_bedrooms, values=_BR_OPTIONS)
        solara.InputInt("Square footage", value=square_footage)
        solara.InputInt("Year built", value=year_built)

        solara.Markdown("**Building Performance**")
        solara.Select("Insulation quality", value=insulation_quality,
                      values=["poor", "average", "good"])

        solara.Markdown("**Baseline Device Specs**")
        solara.SliderFloat("Furnace AFUE", value=furnace_afue,
                           min=0.70, max=0.95, step=0.01)
        solara.SliderFloat("Water heater UEF", value=gas_wh_uef,
                           min=0.55, max=0.70, step=0.01)

        solara.Markdown("**Electric Replacement Specs**")
        solara.SliderFloat("Heat pump COP", value=hp_cop_heating,
                           min=2.5, max=4.5, step=0.1)
        solara.SliderInt("Heat pump SEER", value=hp_seer_cooling, min=16, max=28)
        solara.SliderFloat("HPWH UEF", value=hpwh_uef, min=2.5, max=4.0, step=0.1)


def _preset_buttons(gas_rv, elec_rv, apply_fn):
    """Row of preset buttons for one scenario; apply_fn(preset_key) sets the sliders."""
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
    with solara.Card("📈 Energy & Prices", margin=0, elevation=1):
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
        # Home profile
        zip_code.value, climate_zone.value, num_bedrooms.value,
        square_footage.value, year_built.value, insulation_quality.value,
        # Baseline device specs
        furnace_afue.value, gas_wh_uef.value, hvac_has_cooling.value,
        # Electric specs
        hp_cop_heating.value, hp_seer_cooling.value, hpwh_uef.value,
        # Journey planner — HVAC
        hvac_starting_state.value, hvac_swap_planned.value, hvac_swap_year.value,
        hvac_install_cost.value, hvac_rebate.value,
        # Journey planner — Water Heater
        wh_starting_state.value, wh_swap_planned.value, wh_swap_year.value,
        wh_install_cost.value, wh_rebate.value,
        # Journey planner — Dryer
        dryer_starting_state.value, dryer_swap_planned.value, dryer_swap_year.value,
        dryer_install_cost.value, dryer_rebate.value,
        # Journey planner — Cooktop
        cooktop_starting_state.value, cooktop_swap_planned.value, cooktop_swap_year.value,
        cooktop_install_cost.value, cooktop_rebate.value,
        # Journey planner — EV Charger
        ev_starting_state.value, ev_swap_planned.value, ev_swap_year.value,
        ev_install_cost.value, ev_rebate.value,
        # Pricing
        gas_cagr_pct_a.value, elec_cagr_pct_a.value,
        comparison_mode.value,
        gas_cagr_pct_b.value, elec_cagr_pct_b.value,
        years.value, sim_start_year.value,
    ])

    n = years.value

    with solara.Column(margin=3, gap="10px"):

        # ── Header ─────────────────────────────────────────────────────────────
        ww_svg = _read_svg(_WHYWATT_LOGO, height_px=54)
        with solara.Row(style="align-items:center; gap:12px; padding:8px 0"):
            if ww_svg:
                solara.HTML(tag="div", unsafe_innerHTML=ww_svg,
                            style="height:54px; display:flex; align-items:center")
            else:
                solara.Markdown("# ⚡ WhyWatt?")

        # ── Home info bar — reads reactives, no model needed ───────────────────
        HomeInfoBar()

        # ── Summary stats ───────────────────────────────────────────────────────
        SummaryStats(df, n, model)

        # ── Chart selectors ─────────────────────────────────────────────────────
        with solara.Row(gap="16px"):
            with solara.Column(style="flex:1; min-width:200px"):
                solara.Select("Left chart",  value=chart_left,  values=CHART_OPTIONS)
            with solara.Column(style="flex:1; min-width:200px"):
                solara.Select("Right chart", value=chart_right, values=CHART_OPTIONS)

        # ── Dual chart panes ────────────────────────────────────────────────────
        with solara.Row(gap="8px", style="align-items:stretch"):
            with solara.Card(margin=0, elevation=1,
                             style="flex:1; min-width:300px; overflow:hidden"):
                ChartPane(chart_left.value,  model, df, n)
            with solara.Card(margin=0, elevation=1,
                             style="flex:1; min-width:300px; overflow:hidden"):
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
