#!/usr/bin/env python3
"""build_starting_rates.py — the "current energy rate" when a ZIP resolves to no utility.

Phase 7 §4.1. A home's current energy rate (what it pays today) comes from, in order:
  1. the URDB plan of its electric utility          data/rates/urdb_tou.json
  2. its utility's EIA rate (`starting_rate` block)  data/rates/eia_rates_by_utility.json
  3. its EIA region                                  data/rates/starting_rates.json   ← this file

This script builds (3). One region for now — **EIA — Pacific** (census division 9), taken from
the AEO 2026 Pacific benchmark already carried by the rate-projection bundle, at the bundle's
base year (2025). TODO beyond CA: one entry per EIA census division, chosen from the ZIP's state.

Note: the Pacific level is a Pacific-wide average (includes WA / OR) and sits well below
California utilities' own rates — which is why it is used only when no utility is known.

USAGE (run from project root):
    python scripts/build_starting_rates.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
BUNDLE = ROOT / "data" / "rates" / "projection" / "whywatt_rate_projection.json"
OUT = ROOT / "data" / "rates" / "starting_rates.json"

SCHEMA_VERSION = 1

# region key -> (bundle market, benchmark key, label, census division, states)
REGIONS = {
    "eia_pacific": ("CA_PGE", "eia_pacific", "EIA — Pacific", "Pacific (9)",
                    ["AK", "CA", "HI", "OR", "WA"]),
}
DEFAULT_REGION = "eia_pacific"
UNITS = {"electricity": "$/kWh", "gas": "$/therm"}
FUEL_KEY = {"electricity": "elec", "gas": "gas"}


def build() -> dict:
    raw = BUNDLE.read_bytes()
    bundle = json.loads(raw)
    year = int(bundle["base_year"])
    regions = {}
    for key, (market, bench, label, division, states) in REGIONS.items():
        node = bundle["markets"][market]["benchmarks"][bench]
        rec = {"label": label, "census_division": division, "states": states}
        for fuel in ("electricity", "gas"):
            series = node[FUEL_KEY[fuel]]
            if str(year) not in series:
                raise SystemExit(f"{bench}: no {fuel} value for {year}")
            rec[fuel] = {"year": year, "rate": round(float(series[str(year)]), 5),
                         "unit": UNITS[fuel],
                         "source": f"{node['label']} (bundle benchmarks.{bench}, {year})"}
        regions[key] = rec
    return {
        "_meta": {
            "schema_version": SCHEMA_VERSION,
            "built": str(date.today()),
            "built_by": "scripts/build_starting_rates.py",
            "role": "current energy rate when the ZIP resolves to no utility (Phase 7 §4.1); "
                    "utility-resolved homes use urdb_tou.json or eia_rates_by_utility.json",
            "source_file": str(BUNDLE.relative_to(ROOT)).replace("\\", "/"),
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "source_generated_utc": bundle.get("generated_utc"),
            "todo": "beyond CA: one region per EIA census division, chosen from the ZIP's state",
        },
        "default_region": DEFAULT_REGION,
        "regions": regions,
    }


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    db = build()
    OUT.write_text(json.dumps(db, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for k, r in db["regions"].items():
        print(f"  {k}: elec {r['electricity']['rate']} $/kWh, gas {r['gas']['rate']} $/therm "
              f"({r['electricity']['year']})")
    print(f"Wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
