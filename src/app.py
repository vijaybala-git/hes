"""
Home Electrification Simulator — Solara UI  (Phase 1 / Objective 6 rev 2)

EN-ROADS-inspired layout:
  · Header  : title, location/home-spec info bar, key summary stat
  · Charts  : two selectable panes (choose from 6 chart types)
  · Controls: three panels — Gas Home | Electric Home | Energy Pricing
"""
import solara
import numpy as np
import matplotlib
import matplotlib.ticker
matplotlib.use("Agg")
from matplotlib.figure import Figure
from model import HESModel, CATEGORY_ORDER, CATEGORY_LABELS

# ── Color palette ─────────────────────────────────────────────────────────────
C_BASE   = "#9E9E9E"   # grey  — baseline (gas) home
C_ELEC   = "#1976D2"   # blue  — electrified home

# Category colors — (grey shade for baseline, blue shade for electrified)
CATEGORY_COLORS = {
    "Baseload":     ("#E0E0E0", "#BBDEFB"),
    "WaterHeating": ("#BDBDBD", "#64B5F6"),
    "HVAC_Cooling": ("#9E9E9E", "#1E88E5"),
    "HVAC_Heating": ("#616161", "#0D47A1"),
}

# ── Chart menu ────────────────────────────────────────────────────────────────
CHART_OPTIONS = [
    "Cumulative Energy Costs",
    "Annual Cost by Year",
    "Cost Breakdown by Category",
    "Equipment Replacements (CapEx)",
    "Electricity Price Trend",
    "Gas Price Trend",
]

# ── Reactive State ─────────────────────────────────────────────────────────────

years        = solara.reactive(15)
gas_esc_pct  = solara.reactive(4)    # integer %/year
elec_esc_pct = solara.reactive(3)

# Baseline device controls
b_furnace_load    = solara.reactive(40)   # usage units/yr
b_furnace_replace = solara.reactive(5)    # first replacement — year number
b_ac_load         = solara.reactive(15)
b_ac_replace      = solara.reactive(7)
b_wh_load         = solara.reactive(15)
b_wh_replace      = solara.reactive(5)
b_baseload_load   = solara.reactive(9)    # lights + plug loads

# Electrified device controls
e_hp_load         = solara.reactive(40)
e_hp_cop          = solara.reactive(3.5)
e_hp_replace      = solara.reactive(15)
e_hpwh_load       = solara.reactive(15)
e_hpwh_cop        = solara.reactive(3.0)
e_hpwh_replace    = solara.reactive(12)
e_baseload_load   = solara.reactive(9)    # can be raised to model EVs, induction range, etc.

# Chart pane selections
chart_left  = solara.reactive("Cumulative Energy Costs")
chart_right = solara.reactive("Cost Breakdown by Category")


# ── Model runner ──────────────────────────────────────────────────────────────

def run_simulation():
    """Build and run HESModel from current reactive state; return (model, df)."""
    baseline_overrides = {
        "Gas Furnace": {
            "annual_load": float(b_furnace_load.value),
            "age":         max(0, 15 - b_furnace_replace.value),
        },
        "Central AC": {
            "annual_load": float(b_ac_load.value),
            "age":         max(0, 15 - b_ac_replace.value),
        },
        "Gas Water Heater": {
            "annual_load": float(b_wh_load.value),
            "age":         max(0, 10 - b_wh_replace.value),
        },
        "Lights and Computers": {
            "annual_load": float(b_baseload_load.value),
        },
    }
    electrified_overrides = {
        "Heat Pump - Heating": {
            "annual_load": float(e_hp_load.value),
            "efficiency":  float(e_hp_cop.value),
            "age":         max(0, 15 - e_hp_replace.value),
        },
        "Heat Pump Water Heater": {
            "annual_load": float(e_hpwh_load.value),
            "efficiency":  float(e_hpwh_cop.value),
            "age":         max(0, 12 - e_hpwh_replace.value),
        },
        "Lights and Computers": {
            "annual_load": float(e_baseload_load.value),
        },
    }
    model = HESModel(
        gas_esc=gas_esc_pct.value / 100.0,
        elec_esc=elec_esc_pct.value / 100.0,
        baseline_overrides=baseline_overrides,
        electrified_overrides=electrified_overrides,
    )
    for _ in range(years.value):
        model.step()
    df = model.datacollector.get_model_vars_dataframe()
    return model, df


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
    e = df["Electrified Cum Cost"].values
    ax.plot(x, b, color=C_BASE, lw=2.5, label="Gas home")
    ax.plot(x, e, color=C_ELEC, lw=2.5, label="Electric home")
    ax.fill_between(x, b, e, where=(b >= e), color=C_ELEC, alpha=0.12, label="Electric saves")
    ax.fill_between(x, b, e, where=(b <  e), color=C_BASE, alpha=0.12, label="Gas saves")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(_money))
    ax.set_xlabel("Year"); ax.set_ylabel("Cumulative Energy Cost")
    ax.legend(fontsize=8, framealpha=0.8)
    ax.set_title("Cumulative Energy Costs", fontsize=10, fontweight="bold")
    _style(ax); fig.tight_layout(pad=1.0)
    return fig


# Chart 2 — Annual Cost by Year
def make_annual_cost(df, model, n):
    fig = _new_fig()
    ax  = fig.add_subplot(111)
    x = np.arange(1, n + 1)
    w = 0.35
    ax.bar(x - w/2, df["Baseline Annual Cost"].values,    w, color=C_BASE, label="Gas home",      zorder=3)
    ax.bar(x + w/2, df["Electrified Annual Cost"].values, w, color=C_ELEC, label="Electric home", zorder=3)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(_money))
    ax.set_xlabel("Year"); ax.set_ylabel("Annual Energy Cost")
    ax.legend(fontsize=8)
    ax.set_title("Annual Cost by Year", fontsize=10, fontweight="bold")
    _style(ax); fig.tight_layout(pad=1.0)
    return fig


# Chart 3 — Cost Breakdown by Category (stacked cumulative, dual pane)
def make_cost_breakdown(df, model, n):
    fig = _new_fig(wide=True)
    axes = fig.subplots(1, 2)
    fig.suptitle("Cumulative Cost by Category", fontsize=10, fontweight="bold", y=1.01)

    homes = [
        (model.baseline_home,    "Gas Home",      0),   # 0 = grey palette index
        (model.electrified_home, "Electric Home", 1),   # 1 = blue palette index
    ]
    x = np.arange(1, n + 1)

    for ax, (home, title, palette_idx) in zip(axes, homes):
        bottom = np.zeros(n)
        for cat in CATEGORY_ORDER:
            annual = home.cost_history_by_category.get(cat, [])
            if len(annual) == 0:
                continue
            cum = np.cumsum(annual[:n])
            color = CATEGORY_COLORS[cat][palette_idx]
            label = CATEGORY_LABELS[cat]
            ax.fill_between(x, bottom, bottom + cum,
                            color=color, alpha=0.85, label=label)
            ax.plot(x, bottom + cum, color=color, lw=0.5, alpha=0.5)
            bottom = bottom + cum

        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(_money))
        ax.set_xlabel("Year")
        ax.set_ylabel("Cumulative Cost")
        ax.set_title(title, fontsize=9, fontweight="bold")
        ax.legend(fontsize=7, framealpha=0.8, loc="upper left")
        _style(ax)

    fig.tight_layout(pad=1.0)
    return fig


# Chart 4 — Equipment Replacements (CapEx)
def make_capex(df, model, n):
    fig = _new_fig()
    ax  = fig.add_subplot(111)
    yrs = np.arange(1, n + 1)
    b_vals = [model.baseline_home.capex_by_year.get(y, 0)    for y in yrs]
    e_vals = [model.electrified_home.capex_by_year.get(y, 0) for y in yrs]
    w = 0.35
    ax.bar(yrs - w/2, b_vals, w, color=C_BASE, label="Gas home",      zorder=3)
    ax.bar(yrs + w/2, e_vals, w, color=C_ELEC, label="Electric home", zorder=3)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(_money))
    ax.set_xlabel("Year"); ax.set_ylabel("Replacement Cost")
    ax.legend(fontsize=8)
    ax.set_title("Equipment Replacements (CapEx)", fontsize=10, fontweight="bold")
    _style(ax); fig.tight_layout(pad=1.0)
    return fig


# Chart 5 — Electricity Price Trend
def make_elec_price(df, model, n):
    fig = _new_fig()
    ax  = fig.add_subplot(111)
    x = np.arange(1, n + 1)
    ax.plot(x, df["Elec Rate"].values, color=C_ELEC, lw=2.5)
    ax.set_xlabel("Year"); ax.set_ylabel("Avg Electricity Price  ($/MMBtu)")
    ax.set_title("Electricity Price Trend", fontsize=10, fontweight="bold")
    _style(ax); fig.tight_layout(pad=1.0)
    return fig


# Chart 6 — Gas Price Trend
def make_gas_price(df, model, n):
    fig = _new_fig()
    ax  = fig.add_subplot(111)
    x = np.arange(1, n + 1)
    ax.plot(x, df["Gas Rate"].values, color="#EF6C00", lw=2.5)
    ax.set_xlabel("Year"); ax.set_ylabel("Avg Gas Price  ($/MMBtu)")
    ax.set_title("Gas Price Trend", fontsize=10, fontweight="bold")
    _style(ax); fig.tight_layout(pad=1.0)
    return fig


CHART_FNS = {
    "Cumulative Energy Costs":        make_cumulative_opex,
    "Annual Cost by Year":            make_annual_cost,
    "Cost Breakdown by Category":     make_cost_breakdown,
    "Equipment Replacements (CapEx)": make_capex,
    "Electricity Price Trend":        make_elec_price,
    "Gas Price Trend":                make_gas_price,
}


# ── Sub-components ─────────────────────────────────────────────────────────────

@solara.component
def ChartPane(chart_name, model, df, n):
    """Renders one chart — each chart function owns its own Figure."""
    fig = CHART_FNS[chart_name](df, model, n)
    solara.FigureMatplotlib(fig)


@solara.component
def HomeInfoBar(model):
    """Read-only bar showing location + building specs (same for both homes)."""
    loc   = model.location
    specs = model.building_specs
    region       = loc.get("region", "Unknown")
    zip_code     = loc.get("zip_code", "")
    climate_zone = loc.get("climate_zone", "")
    sqft         = specs.get("square_footage", "")
    year_built   = specs.get("year_built", "")
    insulation   = specs.get("insulation_quality", "average").capitalize()

    solara.Markdown(
        f"📍 **{region}** &nbsp;·&nbsp; ZIP {zip_code} &nbsp;·&nbsp; "
        f"Climate Zone {climate_zone} &nbsp;·&nbsp; "
        f"{sqft:,} sq ft &nbsp;·&nbsp; Built {year_built} &nbsp;·&nbsp; "
        f"{insulation} insulation &nbsp; "
        f"*(same location for both scenarios)*",
        style={"font-size": "0.85em", "color": "#555", "background": "#F0F4F8",
               "padding": "6px 12px", "border-radius": "6px"},
    )


@solara.component
def SummaryStats(df, n):
    """Read-only key numbers — one glance view of simulation results."""
    b_annual  = df["Baseline Annual Cost"].iloc[-1]
    e_annual  = df["Electrified Annual Cost"].iloc[-1]
    delta_cum = df["Opex Delta"].iloc[-1]
    direction = "saves" if delta_cum >= 0 else "costs extra"

    with solara.Row(gap="24px", style="flex-wrap:wrap; margin: 4px 0"):
        solara.Markdown(
            f"**Gas home — year {n} annual cost:** ${b_annual:,.0f}",
            style={"color": "#555"},
        )
        solara.Markdown(
            f"**Electric home — year {n} annual cost:** ${e_annual:,.0f}",
            style={"color": "#1976D2"},
        )
        sign_color = "#2E7D32" if delta_cum >= 0 else "#C62828"
        solara.Markdown(
            f"**{n}-year OpEx {direction}: ${abs(delta_cum):,.0f}**",
            style={"color": sign_color, "font-size": "1.05em"},
        )


@solara.component
def BaselineControls():
    with solara.Card("🏠 Gas Home — adjust scenario", margin=0, elevation=1):

        solara.Markdown("**🔥 Gas Furnace (heating)**")
        solara.SliderInt("Annual heating usage", value=b_furnace_load, min=10, max=100)
        solara.SliderInt("First replacement — year", value=b_furnace_replace, min=1, max=15)

        solara.Markdown("**❄️ Air Conditioner**")
        solara.SliderInt("Annual cooling usage", value=b_ac_load, min=5, max=40)
        solara.SliderInt("First replacement — year", value=b_ac_replace, min=1, max=15)

        solara.Markdown("**🚿 Gas Water Heater**")
        solara.SliderInt("Annual hot water usage", value=b_wh_load, min=5, max=30)
        solara.SliderInt("First replacement — year", value=b_wh_replace, min=1, max=10)

        solara.Markdown("**💡 Baseload (lights + plug loads)**")
        solara.SliderInt("Annual baseload usage", value=b_baseload_load, min=3, max=30)

        # Read-only device specs
        solara.Markdown(
            "<details><summary style='cursor:pointer;color:#888;font-size:0.85em'>"
            "▶ View fixed device specs</summary>\n\n"
            "| Device | Efficiency | Lifespan |\n"
            "|--------|-----------|----------|\n"
            "| Gas Furnace | 0.80 AFUE | 15 yrs |\n"
            "| Air Conditioner | SEER 14 (COP 4.1) | 15 yrs |\n"
            "| Gas Water Heater | 0.65 UEF | 10 yrs |\n"
            "| Lights + Plugs | — | 15 yrs |\n"
            "</details>",
        )


@solara.component
def ElectrifiedControls():
    with solara.Card("⚡ Electric Home — adjust scenario", margin=0, elevation=1):

        solara.Markdown("**🌡️ Heat Pump (heating + cooling)**")
        solara.SliderInt("Annual heating usage", value=e_hp_load, min=10, max=100)
        solara.SliderFloat("Efficiency (higher = better)", value=e_hp_cop, min=2.0, max=5.0, step=0.1)
        solara.SliderInt("First replacement — year", value=e_hp_replace, min=1, max=15)

        solara.Markdown("**🚿 Heat Pump Water Heater**")
        solara.SliderInt("Annual hot water usage", value=e_hpwh_load, min=5, max=30)
        solara.SliderFloat("Efficiency (higher = better)", value=e_hpwh_cop, min=1.5, max=4.5, step=0.1)
        solara.SliderInt("First replacement — year", value=e_hpwh_replace, min=1, max=12)

        solara.Markdown("**💡 Baseload (lights + plug loads)**")
        solara.SliderInt("Annual baseload usage", value=e_baseload_load, min=3, max=50)
        solara.Markdown(
            "<small style='color:#888'>Raise to model EVs, induction range, or other new electric loads.</small>"
        )

        # Read-only device specs
        solara.Markdown(
            "<details><summary style='cursor:pointer;color:#888;font-size:0.85em'>"
            "▶ View fixed device specs</summary>\n\n"
            "| Device | Efficiency | Lifespan |\n"
            "|--------|-----------|----------|\n"
            "| Heat Pump | COP 3.5 (adjustable) | 15 yrs |\n"
            "| HP Water Heater | UEF 3.0 (adjustable) | 12 yrs |\n"
            "| Lights + Plugs | — | 15 yrs |\n"
            "</details>",
        )


@solara.component
def PricingControls():
    with solara.Card("📈 Energy Prices & Timeline", margin=0, elevation=1):
        solara.Markdown("**Annual price increases**")
        solara.SliderInt("Gas price rise per year (%)", value=gas_esc_pct,  min=0, max=15)
        solara.SliderInt("Electricity price rise per year (%)", value=elec_esc_pct, min=0, max=15)
        solara.Markdown("**Time horizon**")
        solara.SliderInt("Years to look ahead", value=years, min=5, max=25)


# ── Main Page ──────────────────────────────────────────────────────────────────

@solara.component
def Page():
    solara.Title("Home Electrification Simulator")

    model, df = solara.use_memo(run_simulation, dependencies=[
        years.value,
        gas_esc_pct.value,    elec_esc_pct.value,
        b_furnace_load.value, b_furnace_replace.value,
        b_ac_load.value,      b_ac_replace.value,
        b_wh_load.value,      b_wh_replace.value,
        b_baseload_load.value,
        e_hp_load.value,      e_hp_cop.value,    e_hp_replace.value,
        e_hpwh_load.value,    e_hpwh_cop.value,  e_hpwh_replace.value,
        e_baseload_load.value,
    ])

    n = years.value

    with solara.Column(margin=3, gap="10px"):

        # ── Title ─────────────────────────────────────────────────────────────
        solara.Markdown("# 🏠 ⚡ Home Electrification Simulator")

        # ── Location / home info bar ──────────────────────────────────────────
        HomeInfoBar(model)

        # ── Key summary stats (read-only) ─────────────────────────────────────
        SummaryStats(df, n)

        # ── Chart selectors ───────────────────────────────────────────────────
        with solara.Row(gap="16px"):
            with solara.Column(style="flex:1; min-width:220px"):
                solara.Select("Left chart",  value=chart_left,  values=CHART_OPTIONS)
            with solara.Column(style="flex:1; min-width:220px"):
                solara.Select("Right chart", value=chart_right, values=CHART_OPTIONS)

        # ── Dual chart panes ──────────────────────────────────────────────────
        with solara.Row(gap="8px", style="align-items:stretch"):
            with solara.Card(margin=0, elevation=1, style="flex:1; min-width:300px; overflow:hidden"):
                ChartPane(chart_left.value,  model, df, n)
            with solara.Card(margin=0, elevation=1, style="flex:1; min-width:300px; overflow:hidden"):
                ChartPane(chart_right.value, model, df, n)

        # ── Legend ────────────────────────────────────────────────────────────
        with solara.Row(gap="24px"):
            solara.Markdown(
                f"<span style='color:{C_BASE};font-weight:bold'>■ Gas home</span>"
                "&nbsp;&nbsp;"
                f"<span style='color:{C_ELEC};font-weight:bold'>■ Electric home</span>"
            )

        # ── Control panels ────────────────────────────────────────────────────
        with solara.Row(gap="12px", style="align-items:flex-start"):
            with solara.Column(style="flex:1"):
                BaselineControls()
            with solara.Column(style="flex:1"):
                ElectrifiedControls()
            with solara.Column(style="flex:1"):
                PricingControls()
