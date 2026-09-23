#!/usr/bin/env python3
"""urdb_coverage.py — the "Can we USE a URDB rate for this utility?" gate.

Combines two committed facts, both keyed by EIA-861 id:
  • data/rates/urdb_coverage.json  — the ~114 utilities URDB updates annually (trustworthy).
  • data/rates/urdb_tou.json       — the utilities we have actually harvested + parsed.

Decision for a resolved utility id (from RateResolver.resolve(zip).electricity.utility_id):

    "urdb"              maintained AND harvested  -> use the URDB TOU structure
    "harvest_candidate" maintained, NOT harvested -> URDB is trustworthy; run build_urdb.py for it
    "eia_fallback"      NOT maintained            -> URDB may be stale -> use the EIA rate

This is review/build tooling (not imported by src/); Phase 7 folds the same logic into the loader.
Run it as a CLI to see the decision for ZIPs:

    .venv/Scripts/python.exe scripts/urdb_coverage.py 95112 90001 95814 10001
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
COVERAGE = ROOT / "data" / "rates" / "urdb_coverage.json"
HARVESTED = ROOT / "data" / "rates" / "urdb_tou.json"


def maintained_ids() -> set[str]:
    return set(json.loads(COVERAGE.read_text())["utilities"]) if COVERAGE.exists() else set()


def harvested_ids() -> set[str]:
    return set(json.loads(HARVESTED.read_text()).get("utilities", {})) if HARVESTED.exists() else set()


def decide(eiaid: str | int | None,
           maintained: set[str] | None = None,
           harvested: set[str] | None = None) -> str:
    """Return 'urdb' | 'harvest_candidate' | 'eia_fallback' for an EIA utility id."""
    if eiaid is None:
        return "eia_fallback"                      # ZIP didn't resolve to a priced utility
    eid = str(eiaid)
    maintained = maintained_ids() if maintained is None else maintained
    harvested = harvested_ids() if harvested is None else harvested
    if eid not in maintained:
        return "eia_fallback"
    return "urdb" if eid in harvested else "harvest_candidate"


def can_use_urdb(eiaid: str | int | None) -> bool:
    """True only when we can price off URDB right now (maintained AND harvested)."""
    return decide(eiaid) == "urdb"


def _cli(zips: list[str]) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from rate_resolver import RateResolver
    rr = RateResolver()
    m, h = maintained_ids(), harvested_ids()
    cov = json.loads(COVERAGE.read_text())["utilities"] if COVERAGE.exists() else {}
    print(f"{'ZIP':7}{'utility':30}{'eiaid':7}{'maintained':11}{'decision':18}")
    for z in zips:
        res = RateResolver().resolve(z)
        e = res.electricity.utility_id
        eid = str(e) if e else "-"
        dec = decide(e, m, h)
        name = res.electricity.name[:28]
        print(f"{z:7}{name:30}{eid:7}{('yes' if eid in m else 'no'):11}{dec:18}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        m, h = maintained_ids(), harvested_ids()
        print(f"URDB maintained: {len(m)} utilities | harvested here: {len(h)} "
              f"({', '.join(sorted(h))})")
        print("Pass ZIPs to see per-ZIP decisions, e.g.:  scripts/urdb_coverage.py 95112 90001 95814 10001")
    else:
        _cli(args)
