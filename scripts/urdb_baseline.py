#!/usr/bin/env python3
"""urdb_baseline.py — resolve a ZIP to its utility baseline allowance (kWh/day) for the default plan.

    ZIP --(RateResolver)--------> EIA utility id
    ZIP --(zip_to_zone.json)----> CEC climate zone      [authoritative]
    CEC zone --(crosswalk)------> baseline territory     [SDG&E high / PG&E approx / SCE n/a]
    territory --(urdb_tou.json)-> baseline kWh/day (summer & winter)

Rates are territory-invariant; this only sets which tier-1 baseline allowance applies. Review/build
tooling (not imported by src/); Phase 7 folds the same lookup into the loader when it applies tiers.

CLI:  .venv/Scripts/python.exe scripts/urdb_baseline.py 95112 94103 92101 92004 90001
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).parent.parent
CLIMATE = ROOT / "data" / "climate" / "zip_to_zone.json"
CROSSWALK = ROOT / "data" / "rates" / "urdb_baseline_crosswalk.json"
URDB = ROOT / "data" / "rates" / "urdb_tou.json"


@dataclass
class BaselineResolution:
    zip_code: str
    eiaid: str | None
    cec_zone: str | None          # e.g. "CA_CZ4"
    region: str | None            # baseline territory, e.g. "X" / "Coastal"
    summer_kwh_day: float | None
    winter_kwh_day: float | None
    confidence: str               # high | approximate | not_applicable | fallback | none
    source: str                   # mapped | representative | flat_no_baseline | unresolved


def _zone_int(cz: str | None):
    if not cz:
        return None
    try:
        return int(cz.replace("CA_CZ", "").replace("CA_", ""))
    except ValueError:
        return None


def baseline_for_zip(eiaid: str | int | None, zipcode: str) -> BaselineResolution:
    z = str(zipcode).strip()
    climate = json.loads(CLIMATE.read_text())
    crosswalk = json.loads(CROSSWALK.read_text())["utilities"]
    db = json.loads(URDB.read_text())["utilities"]
    cec = climate.get(z)
    if eiaid is None or str(eiaid) not in db:
        return BaselineResolution(z, None, cec, None, None, None, "none", "unresolved")

    eid = str(eiaid)
    cw = crosswalk.get(eid, {})
    u = db[eid]
    default = u["tariffs"][u["default_label"]]
    rb = default.get("region_baselines", {})

    if not rb:                              # e.g. SCE flat TOU — no baseline tier at all
        return BaselineResolution(z, eid, cec, None, None, None, "not_applicable", "flat_no_baseline")

    zone_map = cw.get("cec_zone_to_region", {})
    zi = _zone_int(cec)
    region = zone_map.get(str(zi)) if zi is not None else None
    if region and region in rb:
        conf = cw.get("confidence", "approximate")
        source = "mapped"
    else:                                   # unmapped zone -> representative territory
        region = cw.get("representative_region") or default.get("baseline_region")
        conf = "fallback"
        source = "representative"
    b = rb.get(region, {})
    return BaselineResolution(z, eid, cec, region, b.get("summer_kwh_day"),
                              b.get("winter_kwh_day"), conf, source)


def _cli(zips):
    sys.path.insert(0, str(ROOT / "src"))
    from rate_resolver import RateResolver
    rr = RateResolver()
    print(f"{'ZIP':7}{'utility':26}{'CECzone':9}{'region':9}{'summer':8}{'winter':8}{'conf':13}{'source'}")
    for z in zips:
        e = rr.resolve(str(z)).electricity.utility_id
        r = baseline_for_zip(e, z)
        util = (r.eiaid and json.loads(URDB.read_text())["utilities"].get(r.eiaid, {}).get("utility", "")) or "-"
        print(f"{z:7}{util[:24]:26}{str(r.cec_zone):9}{str(r.region):9}"
              f"{str(r.summer_kwh_day):8}{str(r.winter_kwh_day):8}{r.confidence:13}{r.source}")


if __name__ == "__main__":
    _cli(sys.argv[1:] or ["95112", "94103", "92101", "92004", "93704", "90001"])
