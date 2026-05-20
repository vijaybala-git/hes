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


@dataclass
class HomeConfig:
    # ── Location ──────────────────────────────────────────────────────────────
    zip_code:           str  = "95112"
    climate_zone:       str  = "CZ12"

    # ── Building ──────────────────────────────────────────────────────────────
    num_bedrooms:       int  = 3          # Phase 2 active — scales hot water
    square_footage:     int  = 1800       # drives baseload formula + EPW in Phase 3
    year_built:         int  = 1985       # carried; future use
    insulation_quality: str  = "average"  # Phase 2 active — poor / average / good → UA

    # ── Baseload formula inputs ───────────────────────────────────────────────
    baseload_constant_before: float      = 500.0   # always-on kWh/yr (current)
    baseload_constant_after:  float      = 300.0   # always-on kWh/yr (post LED/smart plugs)
    baseload_swap_year:       int | None = None    # year of efficiency upgrade
    baseload_install_cost:    float      = 400.0
    baseload_rebate:          float      = 0.0

    # ── Phase 3 carry-forward (unused in Phase 2) ─────────────────────────────
    num_bathrooms:      int  = 2
    stories:            int  = 1
    has_garage:         bool = False
