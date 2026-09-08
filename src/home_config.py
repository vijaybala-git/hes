"""HomeConfig dataclass — single source of truth for home parameters."""
from __future__ import annotations

from dataclasses import dataclass

# ── Baseload formula constants (Phase 2 fixed; Phase 3 makes sliders) ────────
BASELOAD_INTENSITY_KWH_PER_SQFT = 0.45   # EIA RECS 2020 CA
BASELOAD_PER_BEDROOM_KWH        = 200.0  # DOE occupancy proxy


def compute_baseload_kwh(sq_ft: int, bedrooms: int, constant: float) -> float:
    """Return annual baseload kWh from formula."""
    return (
        sq_ft * BASELOAD_INTENSITY_KWH_PER_SQFT
        + bedrooms * BASELOAD_PER_BEDROOM_KWH
        + constant
    )


# Hot water scaling — bedroom-driven, independent of baseload formula
HOT_WATER_GAL_PER_DAY = {1: 30, 2: 50, 3: 65, 4: 75, 5: 85}
# Source: DOE/ENERGY STAR; 3BR = TMY3 reference 65 gal/day

# Building envelope UA (BTU/hr/°F) by insulation quality, at the reference home size.
# Climate-INDEPENDENT — a property of the building, not the climate zone. Relocated from
# the old data/climate/bayarea_tmy3.json per Phase 4 §1.9.5 (zone files hold HDD/CDD/inlet).
UA_BY_INSULATION = {"poor": 650, "average": 500, "good": 350}

# Reference conditioned floor area the UA_BY_INSULATION values are calibrated to (a 3BR,
# 1,800 sq ft "average" home resolves to UA 500). UA scales linearly with floor area:
# envelope heat loss ∝ conditioned area is the standard first-order simplification, and it
# makes furnace/AC energy finally track home size (Phase 5.5 Fix 1).
UA_REFERENCE_SQFT = 1800


def compute_ua(insulation_quality: str, sq_ft: int) -> float:
    """Building heat-loss coefficient (BTU/hr/°F), scaled from the reference-size UA by
    conditioned floor area. A 1,800 sq ft home returns UA_BY_INSULATION[q] unchanged."""
    return UA_BY_INSULATION[insulation_quality] * sq_ft / UA_REFERENCE_SQFT


# Indoor design setpoints for the design-day load estimate (ASHRAE-typical residential).
_HEATING_INDOOR_F = 70.0
_COOLING_INDOOR_F = 75.0


def suggest_hvac_tons(ua: float, heating_design_f: float | None,
                      cooling_design_f: float | None) -> float | None:
    """Phase 6 §3e — a design-day HVAC size estimate for a credibility/narrative label ONLY.

    tons = UA × design_ΔT / 12,000 (12,000 BTU/hr = 1 ton), taking the larger of the heating
    and cooling design loads. This is envelope conduction at the ASHRAE 99% heating / 1% cooling
    design temperature — it does NOT feed the annual degree-day energy model (tonnage is a
    design-day concept). Returns None when design temps are unavailable (legacy zones)."""
    if heating_design_f is None and cooling_design_f is None:
        return None
    heating_load = ua * max(0.0, _HEATING_INDOOR_F - heating_design_f) if heating_design_f is not None else 0.0
    cooling_load = ua * max(0.0, cooling_design_f - _COOLING_INDOOR_F) if cooling_design_f is not None else 0.0
    return max(heating_load, cooling_load) / 12000.0


@dataclass
class HomeConfig:
    # ── Location ──────────────────────────────────────────────────────────────
    zip_code:           str  = "95112"
    climate_zone:       str  = "CZ4"     # display only; the live zone is resolved from zip_code

    # ── Building ──────────────────────────────────────────────────────────────
    num_bedrooms:       int  = 3          # Phase 2 active — scales hot water
    square_footage:     int  = 1800       # drives baseload formula + NEC general load
    year_built:         int  = 1985       # carried; future use
    insulation_quality: str  = "average"  # Phase 2 active — poor / average / good → UA
    panel_amps:         int  = 100        # Phase 3 §5 — electrical service size (100/150/200)

    # ── Baseload formula inputs ───────────────────────────────────────────────
    baseload_constant_before: float      = 500.0   # always-on kWh/yr (current)
    baseload_constant_after:  float      = 300.0   # always-on kWh/yr (post LED/smart plugs)
    baseload_swap_year:       int | None = None    # year of efficiency upgrade
    baseload_install_cost:    float      = 400.0
    baseload_rebate:          float      = 0.0

    # ── Hot water override (None = use HOT_WATER_GAL_PER_DAY bedroom lookup) ────
    hot_water_daily_gallons: int | None = None

    # ── Phase 6 §2b — PVWatts roof/array geometry (INERT: carried, sanitized, shared,
    #    reset — but NO device or rate code reads them; consumed by the offline solar
    #    track / Phase 7. Per-zone lat/lon lives in data/climate/tmy3_zones.json). ──
    roof_tilt:      int   = 20            # degrees from horizontal (0–60)   → PVWatts tilt
    roof_azimuth:   int   = 180           # degrees clockwise from north (0–359) → azimuth
    array_type:     str   = "fixed_roof"  # fixed_roof/fixed_open/tracking_1ax/tracking_2ax
    module_type:    str   = "standard"    # standard/premium/thin_film        → module_type
    system_losses:  float = 14.0          # % system losses (0–99)            → losses

    # ── Phase 3 carry-forward (unused in Phase 2) ─────────────────────────────
    num_bathrooms:      int  = 2
    stories:            int  = 1
    has_garage:         bool = False
