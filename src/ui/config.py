"""ui/config.py — externalized, versioned UI defaults + config load/export (Phase 4.5b).

The factory defaults live in data/config/whywatt_default.json (the single source of truth);
ui/state.py initializes its reactives from factory_defaults(). Layer 2 adds list/load/validate/
envelope helpers here; apply_config()/export_config() (which touch the reactives) live in
ui/state.py to avoid a config<->state import cycle.
"""
import json
from pathlib import Path

SCHEMA_VERSION = 1
CONFIG_DIR = Path(__file__).parent.parent.parent / "data" / "config"
FACTORY = "whywatt_default"


def _load_envelope(name: str) -> dict:
    """Read a config envelope (schema_version/name/description/based_on/values) by name."""
    return json.loads((CONFIG_DIR / f"{name}.json").read_text(encoding="utf-8"))


def factory_defaults() -> dict:
    """Factory default reactive values — the 'values' block of whywatt_default.json.

    Returns a fresh copy so callers cannot mutate the on-disk baseline.
    """
    return dict(_load_envelope(FACTORY)["values"])


def merge(values: dict) -> dict:
    """REPLACE-semantics merge: start from the factory defaults, override with `values`.

    A key absent from `values` keeps its factory value — so a delta config (a few keys) and a
    full snapshot apply identically (Phase 4.5b). Layer 2 uses this for apply_config().
    """
    return {**factory_defaults(), **values}


# ── Layer 2 — list / load / validate / envelope ────────────────────────────────

def list_configs() -> list[dict]:
    """Bundled configs (factory base + everything in profiles/) as {key, name, description},
    base first. `key` is what load_config() accepts."""
    out, files = [], [CONFIG_DIR / f"{FACTORY}.json"]
    pdir = CONFIG_DIR / "profiles"
    if pdir.exists():
        files += sorted(pdir.glob("*.json"))
    for p in files:
        try:
            env = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        key = FACTORY if p.stem == FACTORY else f"profiles/{p.stem}"
        out.append({"key": key, "name": env.get("name", p.stem),
                    "description": env.get("description", "")})
    return out


def load_config(source) -> dict:
    """Return the bare `values` dict from a config source.

    source = bundled key ("whywatt_default" | "profiles/foo") | file path | envelope dict |
    bare values dict. The caller merges the result onto the factory base.
    """
    if isinstance(source, dict):
        env = source
    else:
        s = str(source)
        p = Path(s)
        env = json.loads((p if p.exists() else CONFIG_DIR / f"{s}.json").read_text(encoding="utf-8"))
    return dict(env.get("values", env))


def validate(values: dict) -> list[str]:
    """Warnings produced while sanitizing `values` (unknown/transient keys dropped, bad
    types dropped, out-of-range numbers clamped). Returns only the warning list; use
    sanitize() when you also need the cleaned dict. Empty list == fully clean payload."""
    return sanitize(values)[1]


def make_envelope(values: dict, name: str, description: str = "", based_on: str = FACTORY) -> dict:
    """Wrap a values dict in the versioned, self-describing envelope (for export/sharing)."""
    return {"schema_version": SCHEMA_VERSION, "name": name, "description": description,
            "based_on": based_on, "values": values}


# ── Layer 3 — input validation / sanitization ──────────────────────────────────
# Security boundary for UNTRUSTED config payloads (a shared link or a dropped .json a
# user received from someone else). The threat is NOT code execution — the load path is
# JSON-only, and apply_config() whitelists keys to _DEFAULTS, so no eval/pickle/attribute
# injection is possible. The threat is BAD DATA: a tampered value that crashes the
# recipient's session (wrong type) or exhausts resources (e.g. years=1e9 sizes sim
# arrays). sanitize() drops anything unknown/wrong-typed and clamps numbers into range.

import math

# Persistent reactives that are transient UI state. Never accepted from an imported
# config — a hand-crafted link must not force a recipient's panels open or swap their
# charts. (export_config also need not emit these; here we drop them on the way IN.)
SHARE_EXCLUDE = {
    "home_profile_details_expanded", "panel_expanded", "hvac_expanded", "wh_expanded",
    "dryer_expanded", "cooktop_expanded", "ev_expanded", "baseload_expanded",
    "chart_left", "chart_right", "device_chart_home", "detail_open",
}

# Reactives excluded from the SHARE delta beyond SHARE_EXCLUDE. Empty since Phase 5.5 Fix 6:
# the CAGR sliders (elec/gas_cagr_pct_a/b) used to live here on the theory they re-derive
# from the ZIP on load — but that made a shared scenario non-deterministic (the ZIP seeder
# raced apply_config) and silently dropped a manual CAGR override. CAGR is now captured like
# any other input; the ZIP→CAGR auto-fill is an interactive-only convenience (it no longer
# runs on load — see state.mark_scenario_loaded / _seed_eia_cagr). Kept as a named set so the
# share layer's `SHARE_EXCLUDE | SHARE_DERIVED` union and imports stay stable.
SHARE_DERIVED: set[str] = set()

MAX_KEYS = 200      # front-line DoS guard: reject the whole payload before per-key work
MAX_STR_LEN = 64    # bounds payload size; blocks giant-string abuse

# Keys that MUST be whole numbers (used as loop counts / array sizes / years). These are
# int-coerced after clamping; all other numerics keep their native JSON type so a
# fractional percentage / cost / efficiency is preserved.
INT_KEYS = {
    "years", "sim_start_year", "num_bedrooms", "year_built", "square_footage",
    "panel_amps", "ev_charger_amps", "induction_amps", "hpwh_amps", "dryer_amps",
    "hvac_swap_year", "wh_swap_year", "dryer_swap_year", "cooktop_swap_year",
    "ev_swap_year", "baseload_swap_year", "panel_upgrade_year", "solar_install_year",
    "hvac_furnace_age", "hvac_ac_age", "wh_gas_age", "dryer_age", "cooktop_age",
    "hvac_baseline_lifespan", "wh_baseline_lifespan", "dryer_baseline_lifespan",
    "cooktop_baseline_lifespan", "dryer_loads_per_week", "cooktop_meals_per_week",
    "solar_panels",
}

_STATES = {"gas", "electric", "none"}
_RATE_MODELS = {"cagr_flat", "ca_average", "acc_shaped", "acc_seasonal"}
# Allowed values for string enums. A value outside the set is dropped (reverts to factory).
ENUMS = {
    "climate_zone": {f"CZ{i}" for i in range(1, 17)},
    "climate_trend": {"none", "rcp45", "rcp85"},
    "insulation_quality": {"poor", "average", "good"},
    "panel_calc_method": {"optional", "standard"},
    "hpwh_ambient_location": {"conditioned", "unconditioned"},
    "solar_nem_mode": {"nbt", "nem2"},
    "hvac_starting_state": _STATES, "wh_starting_state": _STATES,
    "dryer_starting_state": _STATES, "cooktop_starting_state": _STATES,
    "ev_starting_state": _STATES,
    "elec_rate_model_a": _RATE_MODELS, "elec_rate_model_b": _RATE_MODELS,
    "gas_rate_model_a": _RATE_MODELS, "gas_rate_model_b": _RATE_MODELS,
}

# Inclusive numeric bounds [lo, hi]. Out-of-range values are CLAMPED (keeps near-miss
# intent; pins DoS-relevant fields). Keys absent here fall back to GENERIC_NUM.
GENERIC_NUM = (-1e9, 1e9)
_COST = (0.0, 1e7)          # install / rebate / replacement costs ($)
_PCT = (-20.0, 50.0)        # escalation / CAGR percentages
_FRAC = (0.0, 1.0)          # efficiencies / fractions
_AMPS = (5, 200)
_AGE = (0, 100)
_LIFESPAN = (1, 100)
_SWAP_YEAR = (1, 30)
_MILES = (0, 1_000_000)
RANGES = {
    "years": (1, 30), "sim_start_year": (2000, 2100),
    "num_bedrooms": (1, 5), "square_footage": (100, 25000), "year_built": (1850, 2030),
    "panel_amps": (30, 600), "ev_charger_amps": _AMPS, "induction_amps": _AMPS,
    "hpwh_amps": _AMPS, "dryer_amps": _AMPS, "hvac_tonnage": (0.5, 20.0),
    "furnace_afue": (0.3, 1.0), "gas_wh_uef": (0.3, 1.0), "hpwh_uef": (1.0, 6.0),
    "hp_cop_heating": (1.0, 10.0), "hp_seer_cooling": (5.0, 60.0), "hvac_ac_seer": (5.0, 60.0),
    "hvac_swap_year": _SWAP_YEAR, "wh_swap_year": _SWAP_YEAR, "dryer_swap_year": _SWAP_YEAR,
    "cooktop_swap_year": _SWAP_YEAR, "ev_swap_year": _SWAP_YEAR, "baseload_swap_year": _SWAP_YEAR,
    "panel_upgrade_year": _SWAP_YEAR, "solar_install_year": _SWAP_YEAR,
    "hvac_install_cost": _COST, "hvac_rebate": _COST, "wh_install_cost": _COST, "wh_rebate": _COST,
    "dryer_install_cost": _COST, "dryer_rebate": _COST, "cooktop_install_cost": _COST,
    "cooktop_rebate": _COST, "ev_install_cost": _COST, "ev_rebate": _COST,
    "baseload_install_cost": _COST, "baseload_rebate": _COST, "panel_upgrade_cost": _COST,
    "panel_upgrade_rebate": _COST, "hvac_baseline_replace_cost": _COST,
    "wh_baseline_replace_cost": _COST, "dryer_baseline_replace_cost": _COST,
    "cooktop_baseline_replace_cost": _COST, "solar_system_cost": _COST, "solar_rebate": _COST,
    "hvac_furnace_age": _AGE, "hvac_ac_age": _AGE, "wh_gas_age": _AGE, "dryer_age": _AGE,
    "cooktop_age": _AGE, "hvac_baseline_lifespan": _LIFESPAN, "wh_baseline_lifespan": _LIFESPAN,
    "dryer_baseline_lifespan": _LIFESPAN, "cooktop_baseline_lifespan": _LIFESPAN,
    "transport_gasoline_miles": _MILES, "transport_ice_miles_after": _MILES,
    "transport_ev_miles_now": _MILES, "transport_plan_electric_miles": _MILES,
    "ev_miles_per_year": _MILES, "transport_mpg": (5.0, 150.0), "transport_ev_eff": (0.5, 10.0),
    "transport_charging_eff": _FRAC, "transport_pct_home_after": _FRAC,
    "ev_kwh_per_mile": (0.1, 2.0), "ev_charging_efficiency": _FRAC,
    "external_ev_price_per_kwh": (0.0, 5.0), "external_ev_escalation_pct": _PCT,
    "gasoline_price": (0.0, 30.0), "gasoline_escalation_pct": _PCT,
    "gasoline_climate_cost_per_gallon": (0.0, 50.0), "gasoline_health_cost_per_gallon": (0.0, 50.0),
    "baseload_constant_before": (0, 50000), "baseload_constant_after": (0, 50000),
    "hw_daily_gallons": (0, 500),
    "wh_setpoint_f": (90, 160),
    "dryer_gas_therms_per_cycle": (0.0, 5.0), "dryer_hp_kwh_per_cycle": (0.0, 20.0),
    "dryer_loads_per_week": (0, 50), "cooktop_gas_therms_per_meal": (0.0, 5.0),
    "cooktop_induction_kwh_per_meal": (0.0, 20.0), "cooktop_meals_per_week": (0, 100),
    "solar_panels": (0, 200), "solar_kw_per_panel": (0.05, 2.0), "solar_specific_yield": (300, 3000),
    "solar_battery_kwh": (0.0, 200.0), "solar_scf": (0, 100), "solar_nbc": (0.0, 1.0),
    "elec_cagr_pct_a": _PCT, "acc_elec_cagr_a": _PCT, "gas_cagr_pct_a": _PCT, "acc_gas_cagr_a": _PCT,
    "elec_cagr_pct_b": _PCT, "acc_elec_cagr_b": _PCT, "gas_cagr_pct_b": _PCT, "acc_gas_cagr_b": _PCT,
    "social_climate_rate": (0.0, 100.0), "social_health_rate": (0.0, 100.0),
}


def _is_number(x) -> bool:
    """True for real numbers only — bool is excluded (it's an int subclass)."""
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def sanitize(values: dict) -> tuple[dict, list[str]]:
    """Clean an untrusted config payload against the factory schema.

    Returns (clean, warnings). `clean` contains only known, non-transient, well-typed,
    in-range overrides — safe to feed to merge()/apply_config(). Every rejected or
    adjusted key is noted in `warnings`. Never raises.

    Rules: too many keys → reject whole payload · unknown/transient key → drop ·
    wrong type → drop · non-finite (NaN/Inf) number → drop · out-of-range number →
    clamp · over-long or non-enum / bad-ZIP string → drop.
    """
    warnings: list[str] = []
    if not isinstance(values, dict):
        return {}, ["payload is not an object"]
    if len(values) > MAX_KEYS:
        return {}, [f"too many keys ({len(values)} > {MAX_KEYS}); payload rejected"]

    base = factory_defaults()
    clean: dict = {}
    for k, v in values.items():
        if k not in base:
            warnings.append(f"unknown key ignored: {k!r}"); continue
        if k in SHARE_EXCLUDE:
            warnings.append(f"transient key ignored: {k!r}"); continue
        default = base[k]

        if isinstance(default, bool):
            if not isinstance(v, bool):
                warnings.append(f"{k}: expected bool, dropped"); continue
            clean[k] = v
        elif _is_number(default):
            if not _is_number(v) or not math.isfinite(v):
                warnings.append(f"{k}: expected finite number, dropped"); continue
            lo, hi = RANGES.get(k, GENERIC_NUM)
            cv = min(max(v, lo), hi)
            if cv != v:
                warnings.append(f"{k}: {v} clamped to [{lo}, {hi}]")
            clean[k] = int(round(cv)) if k in INT_KEYS else cv
        elif isinstance(default, str):
            if not isinstance(v, str):
                warnings.append(f"{k}: expected string, dropped"); continue
            if len(v) > MAX_STR_LEN:
                warnings.append(f"{k}: string too long, dropped"); continue
            if k in ENUMS and v not in ENUMS[k]:
                warnings.append(f"{k}: {v!r} not allowed, dropped"); continue
            if k == "zip_code" and not (v.isdigit() and len(v) == 5):
                warnings.append(f"{k}: not a 5-digit ZIP, dropped"); continue
            clean[k] = v
        else:                                   # default is None or an unexpected type
            if v is None:
                clean[k] = v
            else:
                warnings.append(f"{k}: unsupported value, dropped")
    return clean, warnings
