#!/usr/bin/env python3
"""solar_regions.py — the region table that drives the offline PVWatts harvest (build_pvwatts.py).

See docs/OfflineSolarData_Plan.md §2b. The harvest is built up one region per run, grouped by CCA
territory. A CCA is only a harvest/review grouping — solar yield is location physics.

Two kinds of region:
  * ZONE_STATIONS_REGION ("ca_zone_stations", wave 0) — the 16 CEC zone reference stations, sited
    at the lat/lon already in data/climate/tmy3_zones.json. These are the table fallback for every
    CA ZIP (fallback levels 2 and 3), so they are harvested first.
  * ZIP regions (wave 1+) — a CCA's ZIPs, each sited at its 2020 ZCTA centroid.

Adding a region is a DATA edit here: a new `SolarRegion(...)` row with its curated ZIP list.
"""
from __future__ import annotations

from dataclasses import dataclass, field

ZONE_STATIONS_REGION = "ca_zone_stations"
DEFAULT_ZONE = "CA_CZ4"          # fallback level 3 — San José reference station


@dataclass(frozen=True)
class SolarRegion:
    tag: str
    name: str
    wave: int
    source_url: str = ""
    members: tuple[str, ...] = ()      # member jurisdictions, as published by the CCA
    zips: tuple[str, ...] = field(default_factory=tuple)


REGIONS: dict[str, SolarRegion] = {
    ZONE_STATIONS_REGION: SolarRegion(
        tag=ZONE_STATIONS_REGION,
        name="CEC Building Climate Zone reference stations (CA_CZ1-16)",
        wave=0,
        source_url="data/climate/tmy3_zones.json (station lat/lon from TMYx EPW headers)",
    ),
    # Wave 1 — `svce` (Silicon Valley Clean Energy): add once the ZIP list is curated from SVCE's
    # published member communities (verify membership at harvest time).
    # Wave 2 — `pce` (Peninsula Clean Energy), `sjce` (San José Clean Energy).
}
