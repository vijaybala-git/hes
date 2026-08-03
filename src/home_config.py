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

    # ── Phase 3 carry-forward (unused in Phase 2) ─────────────────────────────
    num_bathrooms:      int  = 2
    stories:            int  = 1
    has_garage:         bool = False
