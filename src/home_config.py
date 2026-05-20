"""HomeConfig dataclass + BEDROOM_SCALING — single source of truth for home parameters."""
from dataclasses import dataclass

BEDROOM_SCALING = {
    1: {"baseload_multiplier": 0.50, "hot_water_gal_per_day": 30},
    2: {"baseload_multiplier": 0.83, "hot_water_gal_per_day": 50},
    3: {"baseload_multiplier": 1.00, "hot_water_gal_per_day": 65},   # TMY3 reference
    4: {"baseload_multiplier": 1.17, "hot_water_gal_per_day": 75},
    5: {"baseload_multiplier": 1.33, "hot_water_gal_per_day": 85},
}
# Source: DOE/ENERGY STAR occupancy proxy anchored to 3BR = 65 gal/day, 1200 kWh/yr


@dataclass
class HomeConfig:
    # ── Location ──────────────────────────────────────────────────────────────
    zip_code:           str  = "95112"
    climate_zone:       str  = "CZ12"

    # ── Building ──────────────────────────────────────────────────────────────
    num_bedrooms:       int  = 3          # Phase 2 active — scales baseload + hot water
    square_footage:     int  = 1800       # carried; drives EPW model in Phase 3
    year_built:         int  = 1985       # carried; future use
    insulation_quality: str  = "average"  # Phase 2 active — poor / average / good → UA

    # ── Phase 3 carry-forward (unused in Phase 2) ─────────────────────────────
    num_bathrooms:      int  = 2
    stories:            int  = 1
    has_garage:         bool = False
