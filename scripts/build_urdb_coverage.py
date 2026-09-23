#!/usr/bin/env python3
"""build_urdb_coverage.py — bake the URDB "actively maintained" utility list → urdb_coverage.json.

OpenEI publishes (and keeps current) the ~150 utilities whose URDB rates are updated annually —
collectively ~70% of US electricity load. Their own note: *"Rates for any utilities not listed
below should not be assumed to reflect current tariffs."* That is precisely the gate we want: only
trust URDB TOU for a utility on this list; otherwise fall back to EIA.

The table carries an **EIA ID** column — the same key our RateResolver / eia_rates_by_utility.json
use — so the coverage check joins with no new crosswalk.

Source: https://openei.org/wiki/Utility_Rate_Database/Data  (MediaWiki raw wikitext).
Output: data/rates/urdb_coverage.json  (+ raw snapshot with sha256 under data/rates/sources/urdb/).

USAGE:  .venv/Scripts/python.exe scripts/build_urdb_coverage.py
        .venv/Scripts/python.exe scripts/build_urdb_coverage.py --from-cache <raw.wikitext>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
RATES = ROOT / "data" / "rates"
SOURCES = RATES / "sources" / "urdb"
OUT_JSON = RATES / "urdb_coverage.json"
RAW_URL = "https://openei.org/w/index.php?title=Utility_Rate_Database/Data&action=raw"

_ID_RE = re.compile(r"^\|\|?\s*(\d{2,6})\s*$")
_NAME_RE = re.compile(r"^\|\s*\[\[([^\]|]+)")


def parse_table(wikitext: str) -> list[dict]:
    i = wikitext.find("{|")
    table = wikitext[i: wikitext.find("|}", i)]
    rows: list[dict] = []
    cur: dict | None = None
    for ln in table.splitlines():
        s = ln.strip()
        m = _ID_RE.match(s)
        if m:
            cur = {"eiaid": int(m.group(1)), "name": None, "alias": None}
            rows.append(cur)
            continue
        if cur is None:
            continue
        nm = _NAME_RE.match(s)
        if nm and cur["name"] is None:
            cur["name"] = nm.group(1).strip()
            continue
        # optional alias: a plain "|text" line that isn't a row-sep, an id, or a [[link]]
        if cur["name"] and cur["alias"] is None and s.startswith("|") and not s.startswith("|-") \
                and "[[" not in s and not _ID_RE.match(s):
            alias = s.lstrip("|").strip()
            if alias:
                cur["alias"] = alias
    return [r for r in rows if r["name"]]


def main() -> None:
    ap = argparse.ArgumentParser(description="Bake the URDB annually-maintained utility list.")
    ap.add_argument("--from-cache", help="Parse this cached wikitext instead of fetching.")
    args = ap.parse_args()

    if args.from_cache:
        wikitext = Path(args.from_cache).read_text(encoding="utf-8")
    else:
        r = requests.get(RAW_URL, timeout=60, headers={"User-Agent": "whywatt-harvest/1.0"})
        r.raise_for_status()
        wikitext = r.text

    rows = parse_table(wikitext)
    utilities = {str(r["eiaid"]): {"name": r["name"], "alias": r["alias"]} for r in rows}

    SOURCES.mkdir(parents=True, exist_ok=True)
    snap = SOURCES / "urdb_coverage_wikitext.txt"
    snap.write_text(wikitext, encoding="utf-8")

    OUT_JSON.write_text(json.dumps({
        "_meta": {
            "status": f"URDB annually-maintained utilities (~70% of US load); {len(utilities)} listed.",
            "source_url": "https://openei.org/wiki/Utility_Rate_Database/Data",
            "fetched": date.today().isoformat(),
            "note": "Utilities on this list have URDB rates updated annually. Per OpenEI, rates for "
                    "utilities NOT on this list should not be assumed current -> use EIA fallback. "
                    "Keyed by EIA-861 utility id (joins to RateResolver / eia_rates_by_utility.json).",
            "wikitext_sha256": hashlib.sha256(wikitext.encode("utf-8")).hexdigest(),
        },
        "utilities": dict(sorted(utilities.items(), key=lambda kv: int(kv[0]))),
    }, indent=1))

    ca = {"14328": "PG&E", "17609": "SCE", "16609": "SDG&E", "16534": "SMUD"}
    present = [f"{v}({k})" for k, v in ca.items() if k in utilities]
    print(f"wrote {OUT_JSON.relative_to(ROOT)}: {len(utilities)} maintained utilities")
    print(f"CA maintained: {', '.join(present)}")


if __name__ == "__main__":
    main()
