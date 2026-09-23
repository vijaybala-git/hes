#!/usr/bin/env python3
"""build_baseline_crosswalk.py — ZIP -> utility baseline territory, via the CEC climate zone.

WHY A PROXY. There is no clean public ZIP->baseline-territory dataset. Each CA utility defines its
baseline territories differently and NOT by ZIP:
  * PG&E  — 10 territories P..Z, defined by county/community/elevation (tariff maps, PGECZ_90Rev.pdf).
  * SCE   — regions listed in an "Index of Communities" (city -> region); SCE states ZIPs do not
            map to climate zones. (Moot for us: SCE's TOU default is FLAT — no baseline tier.)
  * SDG&E — 4 zones (Coastal/Inland/Mountain/Desert) defined ON the CEC climate-zone boundaries.

The one authoritative, ZIP-keyed climate signal we already hold is the **CEC Building Climate Zone**
(`data/climate/zip_to_zone.json`, from the CEC ZIP->zone table). So the crosswalk is:

    ZIP --(authoritative)--> CEC climate zone --(this table)--> utility baseline territory
                                                            --> baseline kWh/day (urdb_tou.json)

Confidence is recorded per utility. SDG&E is HIGH (its zones ARE the CEC boundaries). PG&E is
APPROXIMATE (territories correlate with, but are not equal to, CEC zones — matched here by climate
character; verified against the harvested per-territory baselines). Unmapped zones fall back to the
utility's representative territory. Rates are territory-invariant; only the baseline allowance moves.

Output: data/rates/urdb_baseline_crosswalk.json
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT = ROOT / "data" / "rates" / "urdb_baseline_crosswalk.json"

# CEC zone number -> baseline territory, per utility EIA id. Zones use the CEC "CA_CZn" naming.
# PG&E: climate-matched to the harvested per-territory baselines (T/Z=cool coast low baseline;
# W/R/S=hot valley high baseline). Marked APPROXIMATE.
PGE = {                       # eiaid 14328  (service area CEC zones ~1-5,11-13,16)
    1: "V",    # North Coast (Eureka)          — cool coastal
    2: "Y",    # Sonoma/Napa inland valleys
    3: "T",    # SF Bay / Oakland coast        — coolest (baseline ~6.5)
    4: "X",    # San Jose / South Bay          — representative default (~9.8)
    5: "Z",    # Central Coast (Santa Maria)   — coastal (~5.9)
    11: "P",   # Red Bluff / N Sacramento Valley
    12: "S",   # Sacramento / Stockton valley  — hot (~15)
    13: "W",   # Fresno / S San Joaquin        — hottest (~19)
    16: "Q",   # Sierra foothills / mountains
}
SDGE = {                      # eiaid 16609  (San Diego county CEC zones 7,10,14,15,16)
    7: "Coastal",
    10: "Inland",
    14: "Desert",
    15: "Desert",
    16: "Mountain",
}


def _int_zone(cz: str) -> int | None:
    # "CA_CZ8" -> 8
    try:
        return int(cz.replace("CA_CZ", "").replace("CA_", ""))
    except ValueError:
        return None


def main() -> None:
    db = json.loads((ROOT / "data" / "rates" / "urdb_tou.json").read_text())["utilities"]
    crosswalk = {
        "14328": {
            "utility": "Pacific Gas & Electric",
            "confidence": "approximate",
            "method": "CEC climate zone -> PG&E territory, matched by climate character and verified "
                      "against harvested per-territory baselines. PG&E territories are defined by "
                      "county/elevation, not ZIP; treat as a proxy. Unmapped zones -> representative.",
            "representative_region": "X",
            "cec_zone_to_region": {str(k): v for k, v in PGE.items()},
        },
        "16609": {
            "utility": "San Diego Gas & Electric",
            "confidence": "high",
            "method": "SDG&E defines Coastal/Inland/Mountain/Desert ON the CEC climate-zone "
                      "boundaries (its inland boundary follows CEC CZ7). Direct CEC-zone map.",
            "representative_region": "Coastal",
            "cec_zone_to_region": {str(k): v for k, v in SDGE.items()},
        },
        "17609": {
            "utility": "Southern California Edison",
            "confidence": "not_applicable",
            "method": "SCE's TOU default (TOU-D-4-9PM) is a FLAT rate with no baseline tier, so no "
                      "territory crosswalk is needed. (Only SCE's legacy tiered Domestic plan is "
                      "region-split — deferred with the tiered legacy plans.)",
            "representative_region": None,
            "cec_zone_to_region": {},
        },
    }
    # sanity: every mapped region must exist in that utility's default region_baselines
    for eid, cw in crosswalk.items():
        u = db.get(eid, {})
        d = u.get("tariffs", {}).get(u.get("default_label"), {}) if u else {}
        have = set(d.get("region_baselines", {}))
        mapped = set(cw["cec_zone_to_region"].values())
        missing = mapped - have if have else set()
        cw["baselines_present"] = sorted(have)
        cw["mapped_regions_without_baseline"] = sorted(missing)

    OUT.write_text(json.dumps({
        "_meta": {
            "status": "ZIP -> baseline territory via CEC climate zone (proxy). CA IOUs.",
            "built": date.today().isoformat(),
            "backbone": "data/climate/zip_to_zone.json (CEC Building Climate Zone by ZIP)",
            "note": "No public ZIP->territory dataset exists; territories are climate-defined and we "
                    "key off the authoritative CEC zone. Rates are territory-invariant; only the "
                    "baseline allowance (kWh/day tier threshold) changes. See per-utility confidence.",
        },
        "utilities": crosswalk,
    }, indent=1))
    print(f"wrote {OUT.relative_to(ROOT)}")
    for eid, cw in crosswalk.items():
        print(f"  {cw['utility']:28} confidence={cw['confidence']:14} "
              f"zones_mapped={len(cw['cec_zone_to_region'])} "
              f"missing_baseline={cw['mapped_regions_without_baseline'] or 'none'}")


if __name__ == "__main__":
    main()
