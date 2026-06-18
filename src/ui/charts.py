"""ui/charts.py — Matplotlib chart builders (make_*) and their helpers (Phase 4.5).

Moved verbatim from app.py (paths to data/ adjusted for the deeper location). Charts take
(df, model, n); a few read shared reactive state (solar_planned, comparison_mode, ...) via
`from ui.state import *`.
"""
import json
from pathlib import Path

import numpy as np
import matplotlib.ticker  # noqa: F401
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from matplotlib.figure import Figure

from ui.theme import (
    _CC_J, _CC_B, _CC_GRID, _CC_TICK, _CC_SOLAR, CATEGORY_COLORS, KWH_PER_THERM,
    KWH_PER_GALLON_GASOLINE, DEVICE_LABELS, DEVICE_COLORS, DEVICE_ALPHAS,
    _SLOT_COLORS, _SLOT_DISPLAY_ORDER, C_RATE_ELEC, C_RATE_GAS)
from ui.state import *  # noqa: F401,F403 — reactive globals read by chart builders
from ui.device_style import dstyle, device_legend_handles, DEVICE_ORDER
from journey import CATEGORY_ORDER, CATEGORY_LABELS
from panel_assessor import PanelAssessor

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

    # Social & health cost layers — natural gas (stacked above market categories)
    cfg    = getattr(model, "social_cost_config", None)
    therms = np.array(hobj.gas_therms_history[:n], dtype=float)
    if cfg is not None and len(therms):
        if cfg.climate_eff > 0:
            cum = np.cumsum(therms * cfg.climate_eff)
            ax.fill_between(x, bottom, bottom + cum, color="#FB8C00",
                            alpha=0.80, label="Gas — climate cost")
            bottom = bottom + cum
        if cfg.health_eff > 0:
            cum = np.cumsum(therms * cfg.health_eff)
            ax.fill_between(x, bottom, bottom + cum, color="#C62828",
                            alpha=0.80, label="Gas — health cost")
            bottom = bottom + cum

    # Gasoline externalities (§3)
    gallons = np.array(hobj.gasoline_gallons_history[:n], dtype=float) if hobj.gasoline_gallons_history else np.zeros(n)
    if gallons.sum() > 0:
        gc = getattr(model, "gasoline_climate_cost_per_gallon", 0.0)
        gh = getattr(model, "gasoline_health_cost_per_gallon", 0.0)
        if gc > 0:
            cum = np.cumsum(gallons * gc)
            ax.fill_between(x, bottom, bottom + cum, color="#E67E22",
                            alpha=0.80, label="Gasoline — climate")
            bottom = bottom + cum
        if gh > 0:
            cum = np.cumsum(gallons * gh)
            ax.fill_between(x, bottom, bottom + cum, color="#922B21",
                            alpha=0.80, label="Gasoline — health")
            bottom = bottom + cum

    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(_money))
    ax.set_xlabel("Year")
    ax.set_ylabel("Cumulative Cost")
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
    _style(ax)
    fig.tight_layout(pad=1.0)
    return fig


# Chart 5 — Electric CAGR Projection
def _elec_rate_label(model_str: str, cagr_pct: int, suffix: str = "") -> str:
    if model_str == "cagr_flat":
        return f"Elec (my utility) +{cagr_pct}%/yr{suffix}"
    if model_str == "ca_average":
        return f"Elec (CA avg) +{cagr_pct}%/yr{suffix}"
    return f"Electricity ACC-shaped{suffix}"

def _gas_rate_label(model_str: str, cagr_pct: int, suffix: str = "") -> str:
    if model_str == "cagr_flat":
        return f"Gas (my utility) +{cagr_pct}%/yr{suffix}"
    if model_str == "ca_average":
        return f"Gas (CA avg) +{cagr_pct}%/yr{suffix}"
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
    Path(__file__).parent.parent.parent / "data" / "rates" / "acc_electric_shape_pge_2024.json"
)
_ACC_GAS_SHAPE_PATH = (
    Path(__file__).parent.parent.parent / "data" / "rates" / "acc_gas_shape_pge_2024.json"
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


# Chart 7v2 — Journey Timeline v2 (Phase 4 §4.2)
def make_journey_timeline_v2(df, model, n):
    """
    Central year-rail timeline.
    Journey events (filled markers, device color) above the rail.
    Do-nothing wear-out events (open markers) below the rail.
    Dashed drift connectors link each pair. Add-on slots show journey only.
    """
    display_slots = [s for s in model.journey_home.slots
                     if s.name != "Lights and Appliances"]
    capex_slots   = model.journey_home.capex_only_slots

    fig = Figure(figsize=(9.5, 4.2), dpi=110)
    fig.patch.set_facecolor("#F9F9F9")
    ax = fig.add_subplot(111)
    ax.set_facecolor("#F9F9F9")

    # --- rail ---
    ax.axhline(0, color=_CC_TICK, lw=1.2, zorder=2)
    ax.set_ylim(-1.25, 1.25)
    ax.set_xlim(-0.5, n + 0.5)
    ax.set_xlabel("Year", fontsize=12)
    ax.set_xticks(range(0, n + 1))
    ax.tick_params(labelsize=12)
    ax.get_yaxis().set_visible(False)
    for spine in ("top", "left", "right"):
        ax.spines[spine].set_visible(False)

    # side labels
    ax.text(-0.45, 0.18, "Your journey", fontsize=12, color=_CC_TICK,
            va="bottom", ha="left", style="italic")
    ax.text(-0.45, -0.18, "Do nothing",  fontsize=12, color=_CC_TICK,
            va="top",    ha="left", style="italic")

    # collision tracking for stagger — also stores placed y so connectors can read it back
    journey_y_placed:   dict[int, list[float]] = {}   # yr → [y0, y1, ...]
    donothing_y_placed: dict[int, list[float]] = {}

    def _y_journey(yr):
        lst = journey_y_placed.setdefault(yr, [])
        y = 0.62 + 0.30 * len(lst)
        lst.append(y)
        return y

    def _y_donothing(yr):
        lst = donothing_y_placed.setdefault(yr, [])
        y = -(0.62 + 0.30 * len(lst))
        lst.append(y)
        return y

    def _draw_marker(x, y, color, filled, code):
        """Draw a circle badge with 2-letter code using bbox annotation (no scatter spill)."""
        ax.annotate(
            code, xy=(x, y), ha="center", va="center",
            fontsize=10, fontweight="bold",
            color="white" if filled else color,
            bbox=dict(
                boxstyle="circle,pad=0.35",
                facecolor=color if filled else "#F9F9F9",
                edgecolor=color,
                linewidth=1.8,
            ),
            zorder=5,
        )

    # Stagger cost labels above journey markers — cycle through 3 heights
    _COST_OFFSETS = [0.22, 0.40, 0.58]
    _ann_idx = 0

    # --- DeviceSlots ---
    for slot in display_slots:
        color = dstyle(slot.style_key)["color"]
        code  = dstyle(slot.style_key)["code"]
        is_addon = slot.starting_state == "none"
        net_cost = slot.install_cost - slot.rebate

        # Journey event — skip $0 slots (e.g. Transportation vehicle switch:
        # no car CapEx is modeled; the EV charger CapExOnlySlot carries that marker)
        sw = slot.swap_year
        if sw is not None and sw <= n and net_cost > 0:
            yj = _y_journey(sw)
            _draw_marker(sw, yj, color, filled=True, code=code)
            v_off = _COST_OFFSETS[_ann_idx % len(_COST_OFFSETS)]
            _ann_idx += 1
            ax.annotate(f"${net_cost:,.0f}", xy=(sw, yj),
                        xytext=(sw + 0.12, yj + v_off),
                        fontsize=9, color=color, zorder=5)

        # Do-nothing event — only for non-add-on slots with a baseline and modeled cost
        if not is_addon and slot.baseline_devices and net_cost > 0:
            dn_yr = max(1, slot.lifespan - slot.existing_age)
            if dn_yr <= n:
                ydn = _y_donothing(dn_yr)
                _draw_marker(dn_yr, ydn, color, filled=False, code=code)

                # Drift connector from journey marker to do-nothing marker
                if sw is not None and sw <= n:
                    yj_val  = journey_y_placed[sw][-1]
                    ydn_val = donothing_y_placed[dn_yr][-1]
                    ax.plot([sw, dn_yr], [yj_val, ydn_val],
                            color=color, lw=1.3, linestyle="--", alpha=0.7, zorder=1)

    # --- CapExOnlySlots (add-on: journey marker only) ---
    for cslot in capex_slots:
        if cslot.install_year is not None and cslot.install_year <= n:
            color = dstyle(cslot.style_key)["color"]
            code  = dstyle(cslot.style_key)["code"]
            yj = _y_journey(cslot.install_year)
            _draw_marker(cslot.install_year, yj, color, filled=True, code=code)
            net = cslot.install_cost - cslot.rebate
            v_off = _COST_OFFSETS[_ann_idx % len(_COST_OFFSETS)]
            _ann_idx += 1
            ax.annotate(f"${net:,.0f}", xy=(cslot.install_year, yj),
                        xytext=(cslot.install_year + 0.12, yj + v_off),
                        fontsize=9, color=color, zorder=5)

    # --- legend (below axes, reserves space via rect) ---
    present_keys = [s.style_key for s in display_slots
                    if s.swap_year is not None and s.swap_year <= n]
    present_keys += [cs.style_key for cs in capex_slots
                     if cs.install_year is not None and cs.install_year <= n]
    if present_keys:
        ax.legend(
            handles=device_legend_handles(present_keys),
            fontsize=10, framealpha=0.85,
            loc="upper center",
            bbox_to_anchor=(0.5, -0.14),
            ncol=min(4, len(present_keys)),
        )

    fig.tight_layout(rect=[0, 0.14, 1, 1])
    return fig


# Chart 4v2 — Equipment Replacements (CapEx) v2 (Phase 4 §4.3)
def make_capex_v2(df, model, n):
    """Grouped + stacked CapEx bars colored by device. Left=do nothing (hatched), right=journey (solid)."""
    fig = Figure(figsize=(9.5, 4.0), dpi=110)
    fig.patch.set_facecolor("#F9F9F9")
    ax = fig.add_subplot(111)
    ax.set_facecolor("#F9F9F9")

    yrs = np.arange(1, n + 1)
    w   = 0.38

    for grp, sign, hatch in (("baseline", -1, "//"), ("journey", +1, None)):
        home    = model.baseline_home if grp == "baseline" else model.journey_home
        bottoms = np.zeros(len(yrs))
        for key in DEVICE_ORDER:
            seg = np.array([
                home.capex_by_device.get(key, {}).get(int(y), 0) for y in yrs
            ])
            if not seg.any():
                continue
            c = dstyle(key)["color"]
            ax.bar(yrs + sign * w / 2, seg, w, bottom=bottoms,
                   color=("none" if hatch else c),
                   edgecolor=c, hatch=hatch, linewidth=0.6, zorder=3)
            bottoms += seg

    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(_money))
    ax.set_xlabel("Year", fontsize=11)
    ax.set_ylabel("Replacement cost", fontsize=11)
    ax.tick_params(labelsize=11)

    # ── Net CapEx over the period (transparency) — journey vs do-nothing total ──
    # All CapEx is in today's dollars (no inflation/escalation), so these are
    # straight nominal sums. Positive net = electrification costs more capital.
    j_total = sum(model.journey_home.capex_by_year.values())
    b_total = sum(model.baseline_home.capex_by_year.values())
    net     = j_total - b_total
    sign    = "+" if net >= 0 else "−"
    net_clr = "#B23A2E" if net >= 0 else "#2E7D32"
    box = (f"Net CapEx over {n} yr (today's $)\n"
           f"Your journey:   ${j_total:,.0f}\n"
           f"Do nothing:     ${b_total:,.0f}\n"
           f"Net:           {sign}${abs(net):,.0f}")
    ax.text(0.985, 0.97, box, transform=ax.transAxes, ha="right", va="top",
            fontsize=9.5, family="monospace", linespacing=1.4, zorder=6,
            bbox=dict(boxstyle="round,pad=0.55", facecolor="white",
                      edgecolor=net_clr, linewidth=1.5, alpha=0.95))

    keys_present = [k for k in DEVICE_ORDER
                    if any(model.journey_home.capex_by_device.get(k, {}).values())
                    or any(model.baseline_home.capex_by_device.get(k, {}).values())]
    if keys_present:
        handles = device_legend_handles(keys_present)
        from matplotlib.patches import Patch
        handles += [
            Patch(facecolor="none", edgecolor="#666", hatch="//", label="Do nothing (hatched)"),
            Patch(facecolor="#aaa", edgecolor="#666", label="Your journey (solid)"),
        ]
        ax.legend(handles=handles, fontsize=10, ncol=2, framealpha=0.85, loc="upper left")

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

    for i, name in enumerate(_SLOT_DISPLAY_ORDER):
        # "Home energy" = what lands on the home meter. Exclude gasoline
        # (transportation) and external/public EV charging in both modes.
        fuels = np.array(
            jh.fuel_history_by_slot.get(name, ["electricity"] * n))[:n]
        if is_cost:
            data = np.array(
                jh.cost_history_by_slot.get(name, [0] * n), dtype=float)[:n]
            # Drop gasoline-phase cost (e.g. the EV slot's gas-car phase).
            data = np.where(fuels == "gasoline", 0.0, data)
            # Drop external (public/workplace) EV charging — off the home meter.
            if name == "EV Driving" and jh.external_ev_cost_history:
                ext = np.array(jh.external_ev_cost_history[:n], dtype=float)
                m = min(len(ext), len(data))
                data[:m] = np.maximum(0.0, data[:m] - ext[:m])
        else:
            raw   = np.array(
                jh.consumption_history_by_slot.get(name, [0] * n), dtype=float)[:n]
            # Gas → kWh-equivalent; gasoline excluded; EV consumption already
            # records home-charged kWh only (§3.13), so external is excluded.
            data  = np.where(fuels == "gas", raw * KWH_PER_THERM, raw)
            data  = np.where(fuels == "gasoline", 0.0, data)

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
    ax.legend(handles=patches, loc="upper left", fontsize=8, framealpha=0.9, ncol=6)

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
    if has_any:
        ax.legend(fontsize=7, framealpha=0.8, loc="upper right")
    _style(ax)
    fig.tight_layout(pad=1.0)
    return fig


# EU.5 — Annual Gasoline Consumption (gallons/year)
def make_annual_gasoline(df, model, n, home="journey"):
    """EU.5 · Gasoline consumption (gallons/year) from the Transportation slot."""
    hobj = model.journey_home if home == "journey" else model.baseline_home
    gallons = np.array(hobj.gasoline_gallons_history[:n], dtype=float) if hobj.gasoline_gallons_history else np.zeros(n)

    fig = _new_fig(wide=False)
    ax  = fig.add_subplot(111)
    x   = np.arange(1, n + 1)

    if gallons.sum() > 0:
        ax.bar(x, gallons, color="#C0392B", alpha=0.82, width=0.7, label="Gasoline")
    else:
        ax.text(0.5, 0.5, "No gasoline consumption\nin this scenario",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=11, color=_CC_TICK, style="italic")

    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_xlabel("Year")
    ax.set_ylabel("Gallons / year")
    if gallons.sum() > 0:
        ax.legend(fontsize=7, framealpha=0.8, loc="upper right")
    _style(ax)
    fig.tight_layout(pad=1.0)
    return fig


# EU.6 — Energy-Mix Timeline (stacked area, kWh-equivalent, §3.14)
def make_energy_mix_timeline(df, model, n, home="journey"):
    """EU.6 · Annual energy mix in kWh-equivalent — stacked area showing how the
    home's energy sources shift across the journey: Gas, Gasoline, Utility-Elec,
    Solar-Elec, External-Elec. Gas is converted via the 29.3 kWh/therm factor and
    gasoline via the 33.7 kWh/gallon (MPGe) factor — display only."""
    hobj = model.journey_home if home == "journey" else model.baseline_home

    fig = _new_fig(wide=False)
    ax  = fig.add_subplot(111)
    x   = np.arange(1, n + 1)

    def _arr(hist):
        a = np.zeros(n)
        if hist:
            v = np.array(hist[:n], dtype=float)
            a[:len(v)] = v
        return a

    # Total home electricity use across electricity-fuel slots. The EV slot already
    # records home-charged kWh only (§3.13), so external charging is excluded here.
    total_elec = np.zeros(n)
    for sname, cons in hobj.consumption_history_by_slot.items():
        raw   = np.array(cons[:n], dtype=float)
        fuels = np.array(hobj.fuel_history_by_slot.get(sname, ["electricity"] * n)[:n])
        m = min(len(raw), len(fuels), n)
        total_elec[:m] += np.where(fuels[:m] == "electricity", raw[:m], 0.0)

    gas_kwh      = _arr(hobj.gas_therms_history) * KWH_PER_THERM
    gasoline_kwh = _arr(hobj.gasoline_gallons_history) * KWH_PER_GALLON_GASOLINE
    solar_kwh    = _arr(hobj.solar_self_consumed_history)
    ext_kwh      = _arr(hobj.external_ev_kwh_history)
    util_kwh     = np.maximum(0.0, total_elec - solar_kwh)  # grid = home elec − solar self-use

    labels = ["Gas", "Gasoline", "Utility-Elec", "Solar-Elec", "External-Elec"]
    data   = [gas_kwh, gasoline_kwh, util_kwh, solar_kwh, ext_kwh]
    colors = ["#FB8C00", "#6D4C41", "#1565C0", _CC_SOLAR, "#C0392B"]

    if sum(d.sum() for d in data) > 0:
        ax.stackplot(x, *data, labels=labels, colors=colors, alpha=0.85)
        ax.plot(x, np.sum(data, axis=0), color="#37474F", lw=0.6, alpha=0.4)
        ax.legend(fontsize=7, framealpha=0.8, loc="upper left")
    else:
        ax.text(0.5, 0.5, "No energy use\nin this scenario",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=11, color=_CC_TICK, style="italic")

    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_xlabel("Year")
    ax.set_ylabel("kWh-equivalent / year")
    ax.set_xlim(1, n)
    ax.margins(x=0)
    _style(ax)
    fig.tight_layout(pad=1.0)
    return fig


# Chart JC.6 — Estimated Electrical Load (NEC panel load over the journey)
def make_panel_load_timeline(df, model, n):
    fig = _new_fig()
    ax  = fig.add_subplot(111)
    hc  = model.home_config
    assessor = PanelAssessor(hc.square_footage, hc.panel_amps,
                             method=panel_calc_method.value)
    timeline = assessor.journey_load_timeline(model.journey_home, n)
    x     = np.arange(1, n + 1)
    amps  = np.array([t.service_amps for t in timeline], dtype=float)
    panel = hc.panel_amps

    # Stepped service load — flat until a device activates, then jumps.
    ax.step(x, amps, where="post", color=_CC_J, lw=2.5, zorder=4,
            label="Estimated service load")
    ax.fill_between(x, 0, amps, step="post", color=_CC_J, alpha=0.10, zorder=2)

    # Panel capacity reference line.
    ax.axhline(panel, color="#C62828", lw=2.0, linestyle="--", zorder=3,
               label=f"{panel} A panel capacity")

    # Device-activation markers + labels (alternating offset to limit overlap).
    n_act = 0
    for t in timeline:
        if not t.new_device:
            continue
        cal = sim_start_year.value + t.year - 1
        ax.scatter([t.year], [t.service_amps], s=42, color="#F57C00",
                   edgecolor="white", linewidth=1.0, zorder=6)
        dy = 22 if (n_act % 2) else 9
        ax.annotate(f"+ {t.new_device}\n{cal}",
                    xy=(t.year, t.service_amps),
                    xytext=(3, dy), textcoords="offset points",
                    ha="left", va="bottom", fontsize=7.2, color="#5D4037",
                    linespacing=0.95, zorder=7)
        n_act += 1

    peak = max(timeline, key=lambda t: t.service_amps)
    ax.set_ylim(0, max(panel, float(amps.max())) * 1.20)
    ax.set_xlim(1, n)
    method_lbl = ("Optional · NEC 220.82" if panel_calc_method.value == "optional"
                  else "Standard · NEC 220.42")
    ax.set_title(f"Peak {peak.service_amps:.0f} A of {panel} A  ·  {method_lbl}",
                 fontsize=9, color=_CC_TICK, loc="left", pad=8)
    ax.yaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f} A"))
    ax.set_xlabel("Year")
    ax.set_ylabel("Service load (A)")
    ax.legend(fontsize=8, framealpha=0.6, loc="lower right")
    _style(ax)
    fig.tight_layout(pad=1.0)
    return fig


def make_hvac_monthly(df, model, n, home="journey"):
    """EU.7 · Monthly HVAC energy for the planned HVAC-swap year — heating (bottom)
    + cooling (top) stacked by month. Do-nothing gas heating is shown in kWh-equivalent
    (29.3 kWh/therm); electric heating/cooling is kWh as-is. Cooling omitted when absent."""
    _M = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    hobj = model.journey_home if home == "journey" else model.baseline_home

    # Compare both homes at the same calendar year: the journey HVAC swap year.
    jslot = next((s for s in model.journey_home.slots if s.name == "HVAC"), None)
    swap_year = getattr(jslot, "swap_year", None)
    year_idx = max(0, min((swap_year - 1) if swap_year else (n - 1), n - 1))
    cal_year = model.sim_start_year + year_idx

    fig = _new_fig(wide=False)
    ax = fig.add_subplot(111)
    slot = next((s for s in hobj.slots if s.name == "HVAC"), None)
    if slot is None:
        ax.text(0.5, 0.5, "No HVAC slot", ha="center", va="center",
                transform=ax.transAxes, color=_CC_TICK)
        return fig

    # Active HVAC device(s) for this home at that year (mirrors DeviceSlot.step logic).
    if home == "baseline" or slot.swap_year is None or (year_idx + 1) < slot.swap_year:
        active = list(slot.baseline_devices)
    else:
        active = [slot.electric_device] if slot.electric_device else []

    prev = model.climate.current_year          # read the chosen year, then restore
    model.climate.advance_to(year_idx)
    heating = np.zeros(12); cooling = np.zeros(12)
    for dev in active:
        if dev is None:
            continue
        f = KWH_PER_THERM if dev.fuel_type == "gas" else 1.0   # gas → kWh-equivalent
        if hasattr(dev, "monthly_heating"):
            heating += np.asarray(dev.monthly_heating(), dtype=float) * f
        if hasattr(dev, "monthly_cooling"):
            cooling += np.asarray(dev.monthly_cooling(), dtype=float) * f
    model.climate.advance_to(prev)

    x = np.arange(12)
    ax.bar(x, heating, color="#E2603A", label="Heating")
    if cooling.sum() > 0:
        ax.bar(x, cooling, bottom=heating, color="#4A90D9", label="Cooling")
    ax.set_xticks(x); ax.set_xticklabels(_M, fontsize=7)
    ax.set_ylabel("kWh-equivalent")
    label = "Your journey" if home == "journey" else "Do nothing"
    ax.set_title(f"HVAC monthly energy — {label}, {cal_year}",
                 fontsize=11, fontweight="bold")
    if heating.sum() + cooling.sum() > 0:
        ax.legend(fontsize=8, framealpha=0.85)
    else:
        ax.text(0.5, 0.5, "No HVAC energy\nthis year", ha="center", va="center",
                transform=ax.transAxes, fontsize=11, color=_CC_TICK, style="italic")
    _style(ax); fig.tight_layout()
    return fig


CHART_FNS = {
    "Cumulative Energy Costs":        make_cumulative_opex,
    "Estimated Electrical Load":      make_panel_load_timeline,
    "Annual Cost by Year":            make_annual_cost,
    "Cost Breakdown by Category":     make_cost_breakdown,
    "Equipment Replacements (CapEx)": make_capex_v2,
    "Electric CAGR Projection":        make_elec_price,
    "Gas CAGR Projection":                make_gas_price,
    "ACC Rate Projection":                make_rate_trajectory,
    "Electricity Rate Shape":         make_acc_rate_shape,
    "Journey Timeline":               make_journey_timeline_v2,
    "Annual kWh by Device":           make_annual_kwh,
    "Annual Gas by Device":           make_annual_gas,
    "Annual Gasoline by Vehicle":     make_annual_gasoline,
    "HVAC Monthly Energy":            make_hvac_monthly,
    "Energy Mix Timeline":            make_energy_mix_timeline,
}



__all__ = [n for n in dir() if n.startswith("make_")] + ["CHART_FNS", "render_device_chart"]
