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
import plotly.graph_objects as go  # Phase 5 §4 — Plotly migration

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


def _legend_below(fig, ax, handles=None, labels=None, *, fontsize=8,
                  ncol=None, max_cols=4, title=None, **kw):
    """House style — legend in a reserved band centered beneath the axes.

    Grows the figure height by the legend band so the plot area is preserved, and
    pins a generous left margin so the y-axis label never clips the figure edge.
    With no labelled artists it just sets margins (leaving whitespace where a
    legend would be — intentional, for a consistent plot size across charts).
    Pass `handles`/`labels` explicitly for proxy artists (Patches/Line2D) that are
    not attached to the axes.
    """
    if handles is None:
        handles, labels = ax.get_legend_handles_labels()
    w, h0 = fig.get_size_inches()
    if not handles:
        fig.subplots_adjust(left=0.16, right=0.96, top=0.92, bottom=0.18)
        return None
    if ncol is None:
        ncol = min(max_cols, len(handles))
    nrow = (len(handles) + ncol - 1) // ncol
    band_in = 0.50 + 0.26 * nrow
    new_h = h0 + band_in
    fig.set_size_inches(w, new_h)
    leg_args = dict(loc="lower center", bbox_to_anchor=(0.5, 0.01),
                    bbox_transform=fig.transFigure, ncol=ncol, fontsize=fontsize,
                    title=title, framealpha=0, borderaxespad=0, **kw)
    if labels is None:   # proxy handles carry their own label=
        leg = ax.legend(handles=handles, **leg_args)
    else:
        leg = ax.legend(handles, labels, **leg_args)
    if title:
        leg._legend_box.align = "left"
    fig.subplots_adjust(left=0.16, right=0.96, top=0.92,
                        bottom=(band_in / new_h) + 0.03)
    return leg


# ── Plotly house style (Phase 5 §4 migration) ──────────────────────────────────

# Match the app UI font (--font in styles_redesign.css) so chart text doesn't look
# "finer" than the rest of the app (Inter/system fallback was lighter than Schibsted).
_PL_FONT = dict(family="'Schibsted Grotesk', ui-sans-serif, system-ui, sans-serif",
                size=12, color=_CC_TICK)


def _rgba(hexcolor, alpha):
    h = hexcolor.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _pl_layout(height=300, ytitle="", xtitle="Year", money_y=True, xdtick=None):
    """Compact house layout: transparent bg, tight margins, overlay legend top-inside.

    `xdtick`: set to 1 on timeline charts so the Year axis ticks every year (consistent
    across all timeline graphs). Margins are left/right-balanced so the x-axis title
    reads centered under the plot.
    """
    xaxis = dict(title=xtitle, showgrid=False, zeroline=False, linecolor=_CC_GRID,
                 ticks="outside", tickcolor=_CC_GRID, tickfont=dict(size=10))
    if xdtick is not None:
        xaxis["dtick"] = xdtick
        xaxis["tick0"] = 0
    return dict(
        height=height,
        autosize=True,                 # responsive width — fill the pane, don't default to 700px
        margin=dict(l=54, r=46, t=8, b=36),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=_PL_FONT,
        hovermode="x unified",
        xaxis=xaxis,
        yaxis=dict(title=ytitle, showgrid=True, gridcolor=_CC_GRID, zeroline=False,
                   tickprefix="$" if money_y else "",
                   tickformat=",.0f" if money_y else None, tickfont=dict(size=10)),
        legend=dict(orientation="v", y=0.98, yanchor="top", x=0.01, xanchor="left",
                    bgcolor="rgba(255,255,255,0.55)", borderwidth=0,
                    font=dict(size=10), tracegroupgap=0),
    )


def _stacked_legend(lay, rows=1):
    """Stacked-area legend treatment (Phase 5 §4): lift the legend out of the plot into a
    horizontal box across the top, so a many-layer legend never overlaps the area fill.
    `rows` reserves enough top margin for the expected number of wrapped legend lines.
    Shared by JC.3 / EU.1 / EU.2 / EU.6."""
    lay["legend"] = dict(orientation="h", x=0.5, xanchor="center", y=1.0, yanchor="bottom",
                         bgcolor="rgba(255,255,255,0.85)", bordercolor=_CC_GRID, borderwidth=1,
                         font=dict(size=9), itemwidth=30, tracegroupgap=0)
    lay["margin"] = {**lay["margin"], "t": 16 + 17 * rows}
    return lay


def _pl_empty(msg, height=300):
    """Annotation-only placeholder figure (e.g. 'no gas in this scenario')."""
    fig = go.Figure()
    fig.add_annotation(text=msg, xref="paper", yref="paper", x=0.5, y=0.5,
                       showarrow=False, align="center",
                       font=dict(size=12, color=_CC_TICK, family=_PL_FONT["family"]))
    fig.update_layout(height=height, autosize=True, margin=dict(l=10, r=10, t=10, b=10),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig


# Chart 1 — Cumulative Energy Costs  (Plotly — Phase 5 §4 pilot)
def make_cumulative_opex(df, model, n):
    x = list(range(1, n + 1))
    b = df["Baseline Cum Cost"].values
    lbl_a = " (A)" if model.comparison_mode else ""

    # "Your journey" is a SINGLE line. When solar is selected, Journey Cum Cost is
    # already net of solar+battery savings, so we only relabel it — never split.
    has_solar = solar_planned.value and "Solar Saving" in df.columns
    e = df["Journey Cum Cost"].values
    j_color = _CC_SOLAR if has_solar else _CC_J
    j_label = f"Your journey + Solar{lbl_a}" if has_solar else f"Your journey{lbl_a}"

    fig = go.Figure()
    # Do-nothing first (no fill); journey next with fill back to it = savings band.
    fig.add_trace(go.Scatter(
        x=x, y=b, name=f"Do nothing{lbl_a}", mode="lines",
        line=dict(color=_CC_B, width=2.5), hovertemplate="$%{y:,.0f}<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=x, y=e, name=j_label, mode="lines", line=dict(color=j_color, width=2.5),
        fill="tonexty", fillcolor=_rgba(j_color, 0.12),
        hovertemplate="$%{y:,.0f}<extra></extra>"))

    if model.comparison_mode:
        fig.add_trace(go.Scatter(
            x=x, y=df["Baseline Cum Cost B"].values, name="Do nothing (B)", mode="lines",
            line=dict(color=_CC_B, width=2.0, dash="dash")))
        fig.add_trace(go.Scatter(
            x=x, y=df["Journey Cum Cost B"].values, name="Your journey (B)", mode="lines",
            line=dict(color=_CC_J, width=2.0, dash="dash")))

    # "+ social" lines move with both the gas and gasoline adders.
    if "Journey Social Total" in df.columns and (
            np.any(df["Journey Social Total"].values)
            or np.any(df["Baseline Social Total"].values)):
        j_social = np.cumsum(df["Journey Social Total"].values)
        b_social = np.cumsum(df["Baseline Social Total"].values)
        fig.add_trace(go.Scatter(
            x=x, y=b + b_social, name=f"Do nothing +soc{lbl_a}", mode="lines",
            line=dict(color=_CC_B, width=1.5, dash="dot")))
        fig.add_trace(go.Scatter(
            x=x, y=e + j_social, name=f"Your journey +soc{lbl_a}", mode="lines",
            line=dict(color=j_color, width=1.5, dash="dot")))

    # Payback marker — first year cumulative savings ("Opex Delta") turn positive.
    if "Opex Delta" in df.columns:
        delta_vals = df["Opex Delta"].values
        payback_yr = next((i + 1 for i, d in enumerate(delta_vals) if d > 0), None)
        if payback_yr is not None:
            cal = model.sim_start_year + payback_yr - 1
            fig.add_vline(x=payback_yr, line=dict(color="#555", width=1.2, dash="dash"),
                          annotation_text=f"Payback · Yr {payback_yr} ({cal})",
                          annotation_position="top right",
                          annotation_font=dict(size=10, color="#555"))

    fig.update_layout(**_pl_layout(height=300, ytitle="Cumulative Energy Cost", xdtick=1))
    return fig


# Chart 2 — Annual Cost by Year
def make_annual_cost(df, model, n):
    yrs = list(range(1, n + 1))
    fig = go.Figure()
    if model.comparison_mode and "Baseline Annual Cost B" in df.columns:
        # 4 bars per year (A solid, B hatched) — each its own offsetgroup
        for name, col, color, pat in [
            ("Do nothing (A)", "Baseline Annual Cost", _CC_B, None),
            ("Your journey (A)", "Journey Annual Cost", _CC_J, None),
            ("Do nothing (B)", "Baseline Annual Cost B", _CC_B, "/"),
            ("Your journey (B)", "Journey Annual Cost B", _CC_J, "/"),
        ]:
            mk = dict(color=color, opacity=0.55 if pat else 1.0)
            if pat:
                mk["pattern"] = dict(shape="/", fgcolor="white", solidity=0.35)
            fig.add_trace(go.Bar(x=yrs, y=df[col].values, name=name, offsetgroup=name,
                                 marker=mk,
                                 hovertemplate="$%{y:,.0f}<extra>" + name + "</extra>"))
    else:
        b_ann = df["Baseline Annual Cost"].values
        j_ann = df["Journey Annual Cost"].values
        fig.add_trace(go.Bar(x=yrs, y=b_ann, name="Do nothing", offsetgroup="b",
                             marker=dict(color=_CC_B),
                             hovertemplate="$%{y:,.0f}<extra>Do nothing</extra>"))
        fig.add_trace(go.Bar(x=yrs, y=j_ann, name="Your journey", offsetgroup="j",
                             marker=dict(color=_CC_J),
                             hovertemplate="$%{y:,.0f}<extra>Your journey</extra>"))
        if "Baseline Social Total" in df.columns and (
                np.any(df["Baseline Social Total"].values)
                or np.any(df["Journey Social Total"].values)):
            fig.add_trace(go.Bar(x=yrs, y=df["Baseline Social Total"].values, offsetgroup="b",
                                 name="Do nothing — social",
                                 marker=dict(color="#FB8C00", opacity=0.85),
                                 hovertemplate="$%{y:,.0f}<extra>social</extra>"))
            fig.add_trace(go.Bar(x=yrs, y=df["Journey Social Total"].values, offsetgroup="j",
                                 name="Your journey — social",
                                 marker=dict(color="#4CAF50", opacity=0.85),
                                 hovertemplate="$%{y:,.0f}<extra>social</extra>"))
    lay = _pl_layout(height=300, ytitle="Annual Energy Cost", xtitle="Year",
                     money_y=True, xdtick=1)
    lay["barmode"] = "stack"
    lay["hovermode"] = "closest"
    fig.update_layout(**lay)
    return fig


# Chart 3 — Cost Breakdown by Category (stacked cumulative, single pane with toggle)
def make_cost_breakdown(df, model, n, home="journey"):
    """Single-pane cost breakdown; home = 'journey' | 'baseline' (Plotly — Phase 5 §4)."""
    palette_idx = 1 if home == "journey" else 0
    hobj = model.journey_home if home == "journey" else model.baseline_home

    x = list(range(1, n + 1))
    fig = go.Figure()

    def _layer(cum, color, label, alpha=0.85):
        # stackgroup="one" accumulates each layer on the previous (replaces the manual
        # `bottom` running sum); the thin boundary line mirrors the matplotlib top edge.
        fig.add_trace(go.Scatter(
            x=x, y=list(cum), name=label, mode="lines", stackgroup="one",
            line=dict(color=color, width=0.5), fillcolor=_rgba(color, alpha),
            hovertemplate="$%{y:,.0f}<extra>" + label + "</extra>"))

    for cat in CATEGORY_ORDER:
        annual = hobj.cost_history_by_category.get(cat, [])
        if not annual:
            continue
        _layer(np.cumsum(annual[:n]), CATEGORY_COLORS[cat][palette_idx], CATEGORY_LABELS[cat])

    # Social & health cost layers — natural gas (stacked above market categories)
    cfg    = getattr(model, "social_cost_config", None)
    therms = np.array(hobj.gas_therms_history[:n], dtype=float)
    if cfg is not None and len(therms):
        if cfg.climate_eff > 0:
            _layer(np.cumsum(therms * cfg.climate_eff), "#FB8C00", "Gas — climate cost", 0.80)
        if cfg.health_eff > 0:
            _layer(np.cumsum(therms * cfg.health_eff), "#C62828", "Gas — health cost", 0.80)

    # Gasoline externalities (§3)
    gallons = np.array(hobj.gasoline_gallons_history[:n], dtype=float) if hobj.gasoline_gallons_history else np.zeros(n)
    if gallons.sum() > 0:
        gc = getattr(model, "gasoline_climate_cost_per_gallon", 0.0)
        gh = getattr(model, "gasoline_health_cost_per_gallon", 0.0)
        if gc > 0:
            _layer(np.cumsum(gallons * gc), "#E67E22", "Gasoline — climate", 0.80)
        if gh > 0:
            _layer(np.cumsum(gallons * gh), "#922B21", "Gasoline — health", 0.80)

    fig.update_layout(**_stacked_legend(_pl_layout(
        height=300, ytitle="Cumulative Cost", xtitle="Year", money_y=True, xdtick=1), rows=3))
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


def _make_price_chart(df, model, n, col, color, label_a, label_b, ytitle, unit):
    yrs = list(range(1, n + 1))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=yrs, y=df[col].values, mode="lines", name=label_a,
                             line=dict(color=color, width=2.5),
                             hovertemplate="$%{y:.3f}" + unit + "<extra></extra>"))
    if model.comparison_mode and f"{col} B" in df.columns:
        fig.add_trace(go.Scatter(x=yrs, y=df[f"{col} B"].values, mode="lines", name=label_b,
                                 line=dict(color=color, width=2.0, dash="dash"),
                                 hovertemplate="$%{y:.3f}" + unit + "<extra></extra>"))
    lay = _pl_layout(height=300, ytitle=ytitle, xtitle="Year", money_y=False, xdtick=1)
    lay["yaxis"].update(tickprefix="$", tickformat=".2f")
    fig.update_layout(**lay)
    return fig


def make_elec_price(df, model, n):
    return _make_price_chart(
        df, model, n, "Elec Rate", _CC_J,
        _elec_rate_label(model.elec_rate_model_a, elec_cagr_pct_a.value),
        _elec_rate_label(model.elec_rate_model_b, elec_cagr_pct_b.value, " (B)"),
        "Avg electricity price ($/kWh)", "/kWh")


# Chart 6 — Gas CAGR Projection
def make_gas_price(df, model, n):
    return _make_price_chart(
        df, model, n, "Gas Rate", "#EF6C00",
        _gas_rate_label(model.gas_rate_model_a, gas_cagr_pct_a.value),
        _gas_rate_label(model.gas_rate_model_b, gas_cagr_pct_b.value, " (B)"),
        "Avg gas price ($/therm)", "/therm")


# Chart 7b — ACC Rate Projection (§24.3)
def _load_acc_shapes():
    """Return (elec_shape 12×24, gas_monthly_shape 12) arrays."""
    with open(_ACC_SHAPE_PATH) as f:
        ed = json.load(f)
    with open(_ACC_GAS_SHAPE_PATH) as f:
        gd = json.load(f)
    return np.array(ed["shape_24h_by_month"], dtype=float), np.array(gd["monthly_shape"], dtype=float)


def _pl_rate_band(fig, x, base, lo_factor, hi_factor, lo_lbl, hi_lbl, color, decimals):
    """Add a CAGR annual-avg line + shaded band between lo_factor and hi_factor (Plotly).

    Traces: lo (dotted) → hi (dashed, fills back to lo) → avg (solid, on top). `legendrank`
    keeps the legend reading Annual avg / peak / off-peak regardless of draw order."""
    fmt = "$%{y:." + str(decimals) + "f}"
    lo, hi = base * lo_factor, base * hi_factor
    fig.add_trace(go.Scatter(x=x, y=list(lo), mode="lines", name=lo_lbl, legendrank=3,
                             line=dict(color=color, width=1.2, dash="dot"),
                             hovertemplate=fmt + "<extra>" + lo_lbl + "</extra>"))
    fig.add_trace(go.Scatter(x=x, y=list(hi), mode="lines", name=hi_lbl, legendrank=2,
                             line=dict(color=color, width=1.2, dash="dash"),
                             fill="tonexty", fillcolor=_rgba(color, 0.18),
                             hovertemplate=fmt + "<extra>" + hi_lbl + "</extra>"))
    fig.add_trace(go.Scatter(x=x, y=list(base), mode="lines", name="Annual avg", legendrank=1,
                             line=dict(color=color, width=2.5),
                             hovertemplate=fmt + "<extra>Annual avg</extra>"))


def make_acc_elec_trajectory(df, model, n):
    """R.3 — ACC electricity rate projection: the annual-avg trajectory (following the
    selected rate model) with the ACC off-peak→peak hourly band always overlaid. The band
    factors come from the ACC hourly shape, so it renders regardless of the rate model — this
    is what distinguishes R.3 from the plain CAGR line in R.1."""
    x = list(range(1, n + 1))
    base = df["Elec Rate"].values
    fig = go.Figure()
    elec_shape, _ = _load_acc_shapes()
    flat = elec_shape.flatten()
    # p25 = typical cheap off-peak hour; p90 = peak evening hour
    p25 = float(np.percentile(flat, 25))
    p90 = float(np.percentile(flat, 90))
    _pl_rate_band(fig, x, base, p25, p90,
                  f"Off-peak (p25 = {p25:.2f}×)",
                  f"Peak evening (p90 = {p90:.2f}×)", C_RATE_ELEC, 3)

    if model.comparison_mode and "Elec Rate B" in df.columns:
        lbl_b = _elec_rate_label(model.elec_rate_model_b, elec_cagr_pct_b.value, " (B)")
        fig.add_trace(go.Scatter(x=x, y=list(df["Elec Rate B"].values), mode="lines", name=lbl_b,
                                 line=dict(color=C_RATE_ELEC, width=2.0, dash="dash"),
                                 hovertemplate="$%{y:.3f}<extra></extra>"))

    lay = _pl_layout(height=300, ytitle="$/kWh", xtitle="Year", money_y=False, xdtick=1)
    lay["yaxis"].update(tickprefix="$", tickformat=".3f")
    fig.update_layout(**lay)
    return fig


def make_acc_gas_trajectory(df, model, n):
    """R.4 — ACC gas rate projection: the annual-avg trajectory (following the selected rate
    model) with the ACC summer→winter seasonal band always overlaid. The band factors come
    from the ACC seasonal shape, so it renders regardless of the rate model — this is what
    distinguishes R.4 from the plain CAGR line in R.2."""
    x = list(range(1, n + 1))
    base = df["Gas Rate"].values
    fig = go.Figure()
    _, gas_shape = _load_acc_shapes()
    winter_factor = float(np.max(gas_shape))   # ~1.20 (Jan/Dec)
    summer_factor = float(np.min(gas_shape))   # ~0.85 (Apr–Oct)
    _pl_rate_band(fig, x, base, summer_factor, winter_factor,
                  f"Summer (min {summer_factor:.2f}×)",
                  f"Winter (max {winter_factor:.2f}×)", C_RATE_GAS, 2)

    if model.comparison_mode and "Gas Rate B" in df.columns:
        lbl_b = _gas_rate_label(model.gas_rate_model_b, gas_cagr_pct_b.value, " (B)")
        fig.add_trace(go.Scatter(x=x, y=list(df["Gas Rate B"].values), mode="lines", name=lbl_b,
                                 line=dict(color=C_RATE_GAS, width=2.0, dash="dash"),
                                 hovertemplate="$%{y:.2f}<extra></extra>"))

    lay = _pl_layout(height=300, ytitle="$/therm", xtitle="Year", money_y=False, xdtick=1)
    lay["yaxis"].update(tickprefix="$", tickformat=".2f")
    fig.update_layout(**lay)
    return fig


# Chart 7c — ACC Electrical Rate Shape heatmap (§24.2)
_ACC_SHAPE_PATH = (
    Path(__file__).parent.parent.parent / "data" / "rates" / "acc_electric_shape_pge_2024.json"
)
_ACC_GAS_SHAPE_PATH = (
    Path(__file__).parent.parent.parent / "data" / "rates" / "acc_gas_shape_pge_2024.json"
)

def make_acc_rate_shape(df, model, n):
    """R.5 — ACC electricity rate-shape heatmap (Plotly): hour-of-day × month avoided-cost
    factor. Always rendered from the ACC shape file — independent of the selected rate
    model (the data is the same regardless)."""
    with open(_ACC_SHAPE_PATH) as f:
        shape_data = json.load(f)
    shape = np.array(shape_data["shape_24h_by_month"], dtype=float)  # (12 months, 24 hours)

    hours  = ["12a","1","2","3","4","5","6","7","8","9","10","11",
              "12p","1","2","3","4","5","6","7","8","9","10","11"]
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    # Numeric x avoids Plotly collapsing the duplicate am/pm hour labels into one column;
    # customdata carries the pretty "1pm" label for the hover.
    hover_hours = np.tile(hours, (len(months), 1))

    fig = go.Figure(go.Heatmap(
        z=shape, x=list(range(24)), y=months, customdata=hover_hours,
        colorscale="RdYlBu", reversescale=True, zmin=0.5, zmax=1.8, xgap=0, ygap=0,
        colorbar=dict(title=dict(text="Rate shape factor<br>(1.0 = monthly avg)",
                                 font=dict(size=9, color=_CC_TICK)),
                      thickness=12, tickfont=dict(size=9, color=_CC_TICK)),
        hovertemplate="%{y} · %{customdata}<br>%{z:.2f}× monthly avg<extra></extra>"))

    fig.update_layout(
        height=300, autosize=True, margin=dict(l=46, r=10, t=8, b=58),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=_PL_FONT,
        xaxis=dict(title="Hour of day", showgrid=False, tickmode="array",
                   tickvals=list(range(24)), ticktext=hours, tickfont=dict(size=9)),
        yaxis=dict(title="Month", showgrid=False, tickfont=dict(size=9)),
    )
    fig.add_annotation(
        text=("Source: 2024 CPUC ACC Model (E3), CZ12 — avoided cost per hour, not retail TOU "
              "pricing.<br>Winter overnight elevated by heating-season grid capacity."),
        xref="paper", yref="paper", x=0, y=-0.32, showarrow=False, xanchor="left",
        align="left", font=dict(size=8, color="#9E9E9E"))
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


# Chart 7v2 — Journey Timeline v2  (Plotly — Phase 5 §4)
def make_journey_timeline_v2(df, model, n):
    """
    Central year-rail timeline (Plotly).
    Journey events (filled badges, device color) above the rail; do-nothing wear-out
    events (open badges) below; dashed drift connectors link each pair.
    """
    BG = "#F9F9F9"
    display_slots = [s for s in model.journey_home.slots
                     if s.name != "Lights and Appliances"]
    capex_slots   = model.journey_home.capex_only_slots

    journey_y_placed:   dict[int, list[float]] = {}
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

    # Collect marker / connector / annotation data
    jx, jy, jcode, jcolor, jhover = [], [], [], [], []   # journey (filled)
    dx, dy, dcode, dcolor, dhover = [], [], [], [], []    # do-nothing (open)
    connectors = []                                       # (x0, x1, y0, y1, color)
    cost_anns  = []                                       # (x, y, text, color)
    present:   dict[str, tuple] = {}                      # style_key → (color, label)

    _COST_OFFSETS = [0.22, 0.40, 0.58]
    _ann_idx = 0

    def _add_journey(x, code, color, label, net):
        nonlocal _ann_idx
        yj = _y_journey(x)
        jx.append(x); jy.append(yj); jcode.append(code); jcolor.append(color)
        jhover.append(f"{label} · Yr {x} · ${net:,.0f}")
        v_off = _COST_OFFSETS[_ann_idx % len(_COST_OFFSETS)]
        _ann_idx += 1
        cost_anns.append((x + 0.12, yj + v_off, f"${net:,.0f}", color))
        present[code] = (color, label)
        return yj

    for slot in display_slots:
        st = dstyle(slot.style_key)
        color, code, label = st["color"], st["code"], st["label"]
        is_addon = slot.starting_state == "none"
        net_cost = slot.install_cost - slot.rebate
        sw = slot.swap_year

        if sw is not None and sw <= n and net_cost > 0:
            _add_journey(sw, code, color, label, net_cost)

        if not is_addon and slot.baseline_devices and net_cost > 0:
            dn_yr = max(1, slot.lifespan - slot.existing_age)
            if dn_yr <= n:
                ydn = _y_donothing(dn_yr)
                dx.append(dn_yr); dy.append(ydn); dcode.append(code); dcolor.append(color)
                dhover.append(f"{label} wears out · Yr {dn_yr}")
                present[code] = (color, label)
                if sw is not None and sw <= n:
                    connectors.append((sw, dn_yr, journey_y_placed[sw][-1],
                                       donothing_y_placed[dn_yr][-1], color))

    for cslot in capex_slots:
        if cslot.install_year is not None and cslot.install_year <= n:
            st = dstyle(cslot.style_key)
            _add_journey(cslot.install_year, st["code"], st["color"], st["label"],
                         cslot.install_cost - cslot.rebate)

    fig = go.Figure()
    fig.add_hline(y=0, line=dict(color=_CC_TICK, width=1.2))

    # dashed drift connectors (one trace per color so each keeps its device hue)
    for x0, x1, y0, y1, color in connectors:
        fig.add_trace(go.Scatter(x=[x0, x1], y=[y0, y1], mode="lines", opacity=0.7,
                                 line=dict(color=color, width=1.3, dash="dash"),
                                 hoverinfo="skip", showlegend=False))

    # do-nothing badges (open), then journey badges (filled)
    if dx:
        fig.add_trace(go.Scatter(
            x=dx, y=dy, mode="markers+text", text=dcode, hovertext=dhover,
            textfont=dict(color=dcolor, size=10),
            textposition="middle center",
            marker=dict(symbol="circle", size=30, color=BG,
                        line=dict(color=dcolor, width=2)),
            hovertemplate="%{hovertext}<extra></extra>", showlegend=False))
    if jx:
        fig.add_trace(go.Scatter(
            x=jx, y=jy, mode="markers+text", text=jcode, hovertext=jhover,
            textfont=dict(color="white", size=10),
            textposition="middle center",
            marker=dict(symbol="circle", size=30, color=jcolor,
                        line=dict(color=jcolor, width=2)),
            hovertemplate="%{hovertext}<extra></extra>", showlegend=False))

    # legend entries (one dummy point per present device)
    for code, (color, label) in present.items():
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers", name=f"{code} · {label}",
            marker=dict(symbol="circle", size=10, color=color), showlegend=True))

    # cost labels + side labels
    for x, y, txt, color in cost_anns:
        fig.add_annotation(x=x, y=y, text=txt, showarrow=False, xanchor="left",
                           yanchor="middle", font=dict(size=9, color=color))
    fig.add_annotation(x=-0.45, y=0.18, text="<i>Your journey</i>", showarrow=False,
                       xanchor="left", yanchor="bottom", font=dict(size=11, color=_CC_TICK))
    fig.add_annotation(x=-0.45, y=-0.18, text="<i>Do nothing</i>", showarrow=False,
                       xanchor="left", yanchor="top", font=dict(size=11, color=_CC_TICK))

    lay = _pl_layout(height=300, xtitle="Year", money_y=False, xdtick=1)
    lay["hovermode"] = "closest"
    lay["paper_bgcolor"] = BG
    lay["plot_bgcolor"] = BG
    lay["margin"] = dict(l=12, r=12, t=8, b=34)
    lay["xaxis"].update(range=[-0.7, n + 0.5], showline=False, ticks="")
    lay["yaxis"] = dict(visible=False, range=[-1.3, 1.3], fixedrange=True)
    lay["legend"].update(orientation="h", y=1.0, yanchor="bottom", x=0.5, xanchor="center")
    fig.update_layout(**lay)
    return fig


# Chart 4v2 — Equipment Replacements (CapEx) v2 (Phase 4 §4.3)
def _capex_keys(model):
    return [k for k in DEVICE_ORDER
            if any(model.journey_home.capex_by_device.get(k, {}).values())
            or any(model.baseline_home.capex_by_device.get(k, {}).values())]


def make_capex_header(model, n) -> str:
    """HTML header for JC.4 — stacked above the bars (legends + full-width net banner).

    Rendered as HTML (not Plotly) so the two legends and the bordered banner stack
    cleanly and stay responsive; the matplotlib/Plotly legend-wrapping fights this.
    """
    j_total = sum(model.journey_home.capex_by_year.values())
    b_total = sum(model.baseline_home.capex_by_year.values())
    net = j_total - b_total
    sign = "+" if net >= 0 else "−"
    net_clr = "#B23A2E" if net >= 0 else "#2E7D32"
    hatch = ("background:repeating-linear-gradient(45deg,#9e9e9e 0 2px,"
             "#ffffff 2px 4px);border:1px solid #9e9e9e")
    dev_chips = "".join(
        f"<span style='display:inline-flex;align-items:center;gap:4px;margin-right:11px'>"
        f"<span style='width:11px;height:11px;border-radius:2px;"
        f"background:{dstyle(k)['color']}'></span>{dstyle(k)['label']}</span>"
        for k in _capex_keys(model))
    return (
        "<div style=\"display:flex;flex-direction:column;gap:4px;"
        "font-family:var(--font);font-size:11px;color:var(--ink-3);"
        "padding:2px 4px 6px;background:#F9F9F9\">"
        # row 1 — bar type (hatched vs solid)
        "<div style='display:flex;gap:16px'>"
        f"<span style='display:inline-flex;align-items:center;gap:5px'>"
        f"<span style='width:14px;height:11px;{hatch}'></span>Do nothing (hatched)</span>"
        "<span style='display:inline-flex;align-items:center;gap:5px'>"
        "<span style='width:14px;height:11px;background:#9e9e9e;border:1px solid #9e9e9e'>"
        "</span>Your journey (solid)</span></div>"
        # row 2 — appliances
        f"<div style='display:flex;flex-wrap:wrap;row-gap:3px'>{dev_chips}</div>"
        # row 3 — full-width bordered net banner (2 lines: title + value)
        f"<div style='border:1.4px solid {net_clr};border-radius:6px;padding:4px 10px;"
        "font-family:var(--mono);text-align:center;color:var(--ink);line-height:1.35'>"
        f"Net CapEx · {n} yr (today's $)<br>"
        f"<b style='font-size:13px;color:{net_clr}'>{sign}${abs(net):,.0f}</b>"
        " vs do nothing</div></div>"
    )


def make_capex_v2(df, model, n):
    """Grouped + stacked CapEx bars by device (Plotly) — bars only; the legends and the
    net banner are rendered as an HTML header above the chart (see make_capex_header)."""
    BG = "#F9F9F9"
    yrs = list(range(1, n + 1))
    fig = go.Figure()

    for key in DEVICE_ORDER:
        st = dstyle(key)
        color, label = st["color"], st["label"]
        b_seg = [model.baseline_home.capex_by_device.get(key, {}).get(y, 0) for y in yrs]
        j_seg = [model.journey_home.capex_by_device.get(key, {}).get(y, 0) for y in yrs]
        if not any(b_seg) and not any(j_seg):
            continue
        fig.add_trace(go.Bar(
            x=yrs, y=b_seg, offsetgroup="baseline", showlegend=False,
            marker=dict(color=color, pattern=dict(shape="/", fgcolor="white", solidity=0.35)),
            hovertemplate=f"{label} · do nothing · Yr %{{x}}<br>$%{{y:,.0f}}<extra></extra>"))
        fig.add_trace(go.Bar(
            x=yrs, y=j_seg, offsetgroup="journey", showlegend=False,
            marker=dict(color=color),
            hovertemplate=f"{label} · journey · Yr %{{x}}<br>$%{{y:,.0f}}<extra></extra>"))

    lay = _pl_layout(height=300, ytitle="Replacement cost", xtitle="Year",
                     money_y=True, xdtick=1)
    lay["barmode"] = "stack"
    lay["hovermode"] = "closest"
    lay["showlegend"] = False
    lay["paper_bgcolor"] = BG
    lay["plot_bgcolor"] = BG
    lay["margin"] = dict(l=58, r=20, t=10, b=36)
    fig.update_layout(**lay)
    return fig


def render_device_chart(model, home: str = "journey",
                        chart_type: str = "device_cost"):
    """Stacked area chart — annual cost or kWh-equivalent per device per year
    (Plotly — Phase 5 §4). x is the simulation year (1..n); swap markers carry the
    calendar year in their label."""
    jh = model.journey_home if home == "journey" else model.baseline_home
    n = model.n_years
    x = list(range(1, n + 1))
    is_cost = chart_type == "device_cost"

    fig = go.Figure()
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

        htmpl = ("$%{y:,.0f}" if is_cost else "%{y:,.0f} kWh") + \
                "<extra>" + DEVICE_LABELS[i] + "</extra>"
        fig.add_trace(go.Scatter(
            x=x, y=list(data), name=DEVICE_LABELS[i], mode="lines", stackgroup="one",
            line=dict(color=DEVICE_COLORS[i], width=1.2),
            fillcolor=_rgba(DEVICE_COLORS[i], DEVICE_ALPHAS[i]), hovertemplate=htmpl))

    # Swap markers — journey home only (vertical dashed line + device label at top)
    SWAP_COLORS = {"HVAC": "#0D47A1", "Water Heater": "#1565C0",
                   "Dryer": "#D0302D", "Cooktop": "#EC9B1E"}
    if home == "journey":
        swaps = sorted((s for s in jh.slots if s.swap_year is not None),
                       key=lambda s: s.swap_year)
        for idx, slot in enumerate(swaps):
            cal = model.sim_start_year + slot.swap_year - 1
            color = SWAP_COLORS.get(slot.name, "#78909C")
            fig.add_vline(x=slot.swap_year, line=dict(color=color, width=1.2, dash="dash"),
                          opacity=0.7)
            # Stagger labels down the line so neighbouring swap years don't overprint.
            fig.add_annotation(x=slot.swap_year, y=1.0, yref="paper", text=f"{slot.name} ({cal})",
                               showarrow=False, xanchor="left", yanchor="top", xshift=3,
                               yshift=-12 * (idx % 3), font=dict(size=8, color=color))

    ytitle = "$/yr" if is_cost else "kWh-eq / yr"
    lay = _stacked_legend(_pl_layout(height=300, ytitle=ytitle, xtitle="Year",
                                     money_y=is_cost, xdtick=1), rows=2)
    # Compact SI ticks ($12k / 12k) — mirrors the old "{v/1000:.1f}k" axis formatter.
    lay["yaxis"].update(tickformat="~s", tickprefix="$" if is_cost else "")
    fig.update_layout(**lay)
    return fig


# EU.3 — Annual kWh by Device (stacked bar, single pane, toggle)
def _annual_by_device(model, n, home, fuel, ytitle, unit, empty_msg):
    """EU.3/EU.4 — stacked bars of per-device consumption for one fuel."""
    hobj = model.journey_home if home == "journey" else model.baseline_home
    yrs = list(range(1, n + 1))
    fig = go.Figure()
    any_data = False
    for sname in hobj.consumption_history_by_slot.keys():
        raw = np.array(hobj.consumption_history_by_slot.get(sname, [0]*n)[:n], dtype=float)
        fuels = hobj.fuel_history_by_slot.get(sname, ["electricity"]*n)[:n]
        seg = np.where(np.array(fuels) == fuel, raw, 0.0)
        if seg.sum() == 0:
            continue
        any_data = True
        fig.add_trace(go.Bar(
            x=yrs, y=seg, name=sname, marker=dict(color=_SLOT_COLORS.get(sname, "#90A4AE")),
            hovertemplate=f"{sname} · Yr %{{x}}<br>%{{y:,.0f}} {unit}<extra></extra>"))
    if not any_data:
        return _pl_empty(empty_msg)
    lay = _pl_layout(height=300, ytitle=ytitle, xtitle="Year", money_y=False, xdtick=1)
    lay["barmode"] = "stack"
    lay["hovermode"] = "closest"
    fig.update_layout(**lay)
    return fig


def make_annual_kwh(df, model, n, home="journey"):
    """EU.3 · Per-device electricity consumption per year — stacked bars."""
    return _annual_by_device(model, n, home, "electricity", "kWh / year", "kWh",
                             "No electricity consumption in this scenario")


# EU.4 — Annual Gas Consumption by Device (stacked bar, single pane, toggle)
def make_annual_gas(df, model, n, home="journey"):
    """EU.4 · Per-device gas consumption per year — stacked bars (therms)."""
    return _annual_by_device(model, n, home, "gas", "Therms / year", "therms",
                             "No gas consumption in this scenario")


# EU.5 — Annual Gasoline Consumption (gallons/year)
def make_annual_gasoline(df, model, n, home="journey"):
    """EU.5 · Gasoline consumption (gallons/year) from the Transportation slot."""
    hobj = model.journey_home if home == "journey" else model.baseline_home
    gallons = (np.array(hobj.gasoline_gallons_history[:n], dtype=float)
               if hobj.gasoline_gallons_history else np.zeros(n))
    if gallons.sum() <= 0:
        return _pl_empty("No gasoline consumption in this scenario")
    yrs = list(range(1, n + 1))
    fig = go.Figure()
    fig.add_trace(go.Bar(x=yrs, y=gallons, name="Gasoline", marker=dict(color="#C0392B"),
                         hovertemplate="Yr %{x}<br>%{y:,.0f} gal<extra></extra>"))
    lay = _pl_layout(height=300, ytitle="Gallons / year", xtitle="Year",
                     money_y=False, xdtick=1)
    lay["hovermode"] = "closest"
    fig.update_layout(**lay)
    return fig


# EU.6 — Energy-Mix Timeline (stacked area, kWh-equivalent, §3.14)
def make_energy_mix_timeline(df, model, n, home="journey"):
    """EU.6 · Annual energy mix in kWh-equivalent — stacked area showing how the
    home's energy sources shift across the journey: Gas, Gasoline, Utility-Elec,
    Solar-Elec, External-Elec. Gas is converted via the 29.3 kWh/therm factor and
    gasoline via the 33.7 kWh/gallon (MPGe) factor — display only."""
    hobj = model.journey_home if home == "journey" else model.baseline_home
    x = list(range(1, n + 1))

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

    layers = [("Gas", gas_kwh, "#FB8C00"), ("Gasoline", gasoline_kwh, "#6D4C41"),
              ("Utility-Elec", util_kwh, "#1565C0"), ("Solar-Elec", solar_kwh, _CC_SOLAR),
              ("External-Elec", ext_kwh, "#C0392B")]
    if sum(d.sum() for _, d, _ in layers) <= 0:
        return _pl_empty("No energy use in this scenario")

    fig = go.Figure()
    for label, data, color in layers:
        fig.add_trace(go.Scatter(
            x=x, y=list(data), name=label, mode="lines", stackgroup="one",
            line=dict(color=color, width=0.5), fillcolor=_rgba(color, 0.85),
            hovertemplate="%{y:,.0f} kWh<extra>" + label + "</extra>"))

    fig.update_layout(**_stacked_legend(_pl_layout(
        height=300, ytitle="kWh-equivalent / year", xtitle="Year", money_y=False, xdtick=1)))
    return fig


# Chart JC.6 — Estimated Electrical Load (NEC panel load over the journey)
def make_panel_load_timeline(df, model, n):
    hc = model.home_config
    assessor = PanelAssessor(hc.square_footage, hc.panel_amps,
                             method=panel_calc_method.value)
    timeline = assessor.journey_load_timeline(model.journey_home, n)
    yrs = list(range(1, n + 1))
    amps = [t.service_amps for t in timeline]
    panel = hc.panel_amps

    fig = go.Figure()
    # Stepped service load (flat until a device activates) + light fill.
    fig.add_trace(go.Scatter(
        x=yrs, y=amps, mode="lines", name="Estimated service load",
        line=dict(color=_CC_J, width=2.5, shape="hv"), fill="tozeroy",
        fillcolor=_rgba(_CC_J, 0.10), hovertemplate="%{y:.0f} A · Yr %{x}<extra></extra>"))
    # Panel capacity reference line.
    fig.add_hline(y=panel, line=dict(color="#C62828", width=2.0, dash="dash"),
                  annotation_text=f"{panel} A panel capacity",
                  annotation_position="top left",
                  annotation_font=dict(size=10, color="#C62828"))
    # Device-activation markers + staggered labels.
    mx, my, mtxt = [], [], []
    for i, t in enumerate(tt for tt in timeline if tt.new_device):
        cal = sim_start_year.value + t.year - 1
        mx.append(t.year); my.append(t.service_amps)
        mtxt.append(f"+ {t.new_device} ({cal})")
        fig.add_annotation(x=t.year, y=t.service_amps, text=f"+ {t.new_device}<br>{cal}",
                           showarrow=False, xanchor="left", yanchor="bottom",
                           xshift=4, yshift=(20 if i % 2 else 6),
                           font=dict(size=8, color="#5D4037"), align="left")
    if mx:
        fig.add_trace(go.Scatter(
            x=mx, y=my, mode="markers", showlegend=False, hovertext=mtxt,
            marker=dict(size=10, color="#F57C00", line=dict(color="white", width=1)),
            hovertemplate="%{hovertext}<extra></extra>"))

    peak = max(amps) if amps else 0
    method_lbl = ("Optional · NEC 220.82" if panel_calc_method.value == "optional"
                  else "Standard · NEC 220.42")
    lay = _pl_layout(height=300, ytitle="Service load (A)", xtitle="Year",
                     money_y=False, xdtick=1)
    lay["yaxis"].update(ticksuffix=" A", rangemode="tozero")
    lay["title"] = dict(text=f"Peak {peak:.0f} A of {panel} A · {method_lbl}",
                        x=0.5, xanchor="center", y=0.98,
                        font=dict(size=11, color=_CC_TICK))
    lay["margin"]["t"] = 28
    fig.update_layout(**lay)
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

    slot = next((s for s in hobj.slots if s.name == "HVAC"), None)
    if slot is None:
        return _pl_empty("No HVAC slot")

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

    if heating.sum() + cooling.sum() == 0:
        return _pl_empty("No HVAC energy this year")

    label = "Your journey" if home == "journey" else "Do nothing"
    fig = go.Figure()
    fig.add_trace(go.Bar(x=_M, y=heating, name="Heating", marker=dict(color="#E2603A"),
                         hovertemplate="%{x}<br>%{y:,.0f}<extra>Heating</extra>"))
    if cooling.sum() > 0:
        fig.add_trace(go.Bar(x=_M, y=cooling, name="Cooling", marker=dict(color="#4A90D9"),
                             hovertemplate="%{x}<br>%{y:,.0f}<extra>Cooling</extra>"))
    lay = _pl_layout(height=300, ytitle="kWh-equivalent", xtitle="", money_y=False)
    lay["barmode"] = "stack"
    lay["hovermode"] = "x unified"
    lay["xaxis"] = dict(type="category", tickfont=dict(size=10))
    lay["title"] = dict(text=f"HVAC monthly · {label}, {cal_year}", x=0.5, xanchor="center",
                        y=0.98, font=dict(size=11, color=_CC_TICK))
    lay["margin"]["t"] = 28
    lay["margin"]["b"] = 52
    # Default top-left overlay legend collides with the tall Jan/Dec heating bars
    # (its translucent box tints the bar top). Put it in a horizontal row below the
    # plot instead, clear of the bars.
    lay["legend"] = dict(orientation="h", y=-0.16, yanchor="top", x=0.5, xanchor="center",
                         bgcolor="rgba(0,0,0,0)", font=dict(size=10), tracegroupgap=0)
    fig.update_layout(**lay)
    return fig


CHART_FNS = {
    "Cumulative Energy Costs":        make_cumulative_opex,
    "Estimated Electrical Load":      make_panel_load_timeline,
    "Annual Cost by Year":            make_annual_cost,
    "Cost Breakdown by Category":     make_cost_breakdown,
    "Equipment Replacements (CapEx)": make_capex_v2,
    "Electric CAGR Projection":        make_elec_price,
    "Gas CAGR Projection":                make_gas_price,
    "ACC Electrical Rate Projection": make_acc_elec_trajectory,
    "ACC Gas Rate Projection":        make_acc_gas_trajectory,
    "ACC Electrical Rate Shape":      make_acc_rate_shape,
    "Journey Timeline":               make_journey_timeline_v2,
    "Annual kWh by Device":           make_annual_kwh,
    "Annual Gas by Device":           make_annual_gas,
    "Annual Gasoline by Vehicle":     make_annual_gasoline,
    "HVAC Monthly Energy":            make_hvac_monthly,
    "Energy Mix Timeline":            make_energy_mix_timeline,
}



__all__ = [n for n in dir() if n.startswith("make_")] + ["CHART_FNS", "render_device_chart"]
