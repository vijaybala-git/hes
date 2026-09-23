#!/usr/bin/env python3
"""solar_regions.py — the region table that drives the offline PVWatts harvest (build_pvwatts.py).

See docs/OfflineSolarData_Plan.md §2b. The harvest is built up one region per run, grouped by CCA
territory. A CCA is only a harvest/review grouping — solar yield is location physics — and a ZIP is
tagged with the first wave that harvests it, which is not a statement about who serves it.

Two kinds of region:
  * ZONE_STATIONS_REGION ("ca_zone_stations", wave 0) — the 16 CEC zone reference stations, sited
    at the lat/lon already in data/climate/tmy3_zones.json. These are the table fallback for every
    CA ZIP (fallback levels 2 and 3), so they are harvested first.
  * ZIP regions (wave 1+) — defined here by *membership rules* (county + member places); the
    concrete ZIP list is DERIVED from Census 2020 ZCTA relationship files by
    scripts/build_solar_regions.py → data/solar/regions.json (committed, reviewable).

Adding a region is a DATA edit here, then `build_solar_regions.py --region <tag>`.
"""
from __future__ import annotations

from dataclasses import dataclass

ZONE_STATIONS_REGION = "ca_zone_stations"
DEFAULT_ZONE = "CA_CZ4"          # fallback level 3 — San José reference station


@dataclass(frozen=True)
class SolarRegion:
    tag: str
    name: str
    wave: int
    source_url: str = ""
    county_geoid: str = ""                 # Census county GEOID the region lies in
    member_places: tuple[str, ...] = ()    # Census NAMELSAD place names (e.g. "Campbell city")
    enclave_places: tuple[str, ...] = ()   # non-member places inside the footprint — same sun
    include_unincorporated: bool = False   # CCA also serves unincorporated county land
    exclude_places: tuple[str, ...] = ()   # places left for another wave (unincorporated rule)
    # ZIP-selection thresholds (fractions of the ZCTA's land area)
    min_in_county: float = 0.45
    min_place_share: float = 0.10
    min_unincorporated: float = 0.50
    max_excluded_share: float = 0.05


REGIONS: dict[str, SolarRegion] = {
    ZONE_STATIONS_REGION: SolarRegion(
        tag=ZONE_STATIONS_REGION,
        name="CEC Building Climate Zone reference stations (CA_CZ1-16)",
        wave=0,
        source_url="data/climate/tmy3_zones.json (station lat/lon from TMYx EPW headers)",
    ),
    "svce": SolarRegion(
        tag="svce",
        name="Silicon Valley Clean Energy",
        wave=1,
        source_url="https://svcleanenergy.org/faqs/ (13 member communities, verified 2026-09-22)",
        county_geoid="06085",              # Santa Clara County
        member_places=(
            "Campbell city", "Cupertino city", "Gilroy city", "Los Altos city",
            "Los Altos Hills town", "Los Gatos town", "Milpitas city", "Monte Sereno city",
            "Morgan Hill city", "Mountain View city", "Saratoga city", "Sunnyvale city",
        ),
        # Municipal utilities (CPAU, Silicon Valley Power) inside SVCE's footprint — not SVCE
        # customers, but the same sun; harvested with the wave that covers them geographically.
        enclave_places=("Palo Alto city", "Santa Clara city"),
        include_unincorporated=True,       # the 13th member: unincorporated Santa Clara County
        exclude_places=("San Jose city",), # San José-majority hill ZIPs belong to wave 2 (sjce)
    ),
    # Wave 2 — `pce` (Peninsula Clean Energy, San Mateo County 06081), `sjce` (City of San José).
}
