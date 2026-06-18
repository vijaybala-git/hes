"""ui/sim.py — ZIP→zone/utility resolution + rate-display helpers (Phase 4.5).

Shared by both the panels (ui/panels.py) and the layout (app.py). Moved verbatim from app.py.
"""
import functools

from climate_loader import ClimateLoader
from rate_resolver import RateResolver
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


__all__ = ["_APP_CLIMATE_LOADER", "_TREND_LABELS", "_climate_info", "_APP_RATE_RESOLVER",
           "_rate_info", "_utility_line", "_PROV_BADGE", "_rate_line_html",
           "_fuel_resolved_display", "_seed_eia_cagr"]
