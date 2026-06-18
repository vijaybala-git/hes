#!/usr/bin/env python3
"""build_zip_utility_map.py — ZIP → utility crosswalks for WhyWatt rate resolution.

Phase 4 §2 (EIA-Based Rate Modeling). Emits two committed lookup tables so the live app can
resolve a ZIP to its electric utility and gas LDC with no network call (mirrors the climate
zip_to_zone.json pattern).

  data/rates/zip_to_electric_utility.json   ZIP -> [EIA-861 utility numbers]
  data/rates/zip_to_gas_ldc.json            ZIP -> [EIA-176 gas LDC ids]

ELECTRIC source: OpenEI "U.S. Electric Utility Companies and Rates: Look-up by Zip Code
(2024)" — the IOU file (iou_zipcodes_2024.csv), built from EIA-861 + ABB Velocity Suite.
Authoritative ZIP→utility mapping; a ZIP may list several utilities (border areas).

GAS source: there is no clean national ZIP→gas-LDC crosswalk. For California the gas LDC is
*derived* from the electric IOU per the territory correspondence (PG&E electric → PG&E gas,
SCE → SoCalGas, SDG&E electric → SDG&E gas). This is correct for the major metros (Bay Area,
Sacramento, LA basin, San Diego). KNOWN LIMITATION: on the Central Coast / southern San
Joaquin, some PG&E-*electric* areas are served by SoCalGas for *gas*; those ZIPs will resolve
to PG&E gas here. The resolver falls back to the CA state average for any unmatched ZIP, and
the user can always override the utility manually.

USAGE (run from project root):
    python scripts/build_zip_utility_map.py --states CA
    python scripts/build_zip_utility_map.py --check     # parse cached snapshot, no download
"""
from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import sys
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
RATES = ROOT / "data" / "rates"
SOURCES = RATES / "sources"
ELEC_JSON = RATES / "zip_to_electric_utility.json"
GAS_JSON = RATES / "zip_to_gas_ldc.json"

IOU_CSV_URL = "https://data.openei.org/files/8563/iou_zipcodes_2024.csv"
IOU_CSV_NAME = "openei_iou_zipcodes_2024.csv"
NON_IOU_CSV_URL = "https://data.openei.org/files/8563/non_iou_zipcodes_2024.csv"
NON_IOU_CSV_NAME = "openei_non_iou_zipcodes_2024.csv"
# Real-ZIP universe used to confine the gap backfill to actual CA ZIPs (CEC table).
CLIMATE_ZIP_JSON = ROOT / "data" / "climate" / "zip_to_zone.json"

# ── Per-state config ───────────────────────────────────────────────────────────
# elec_to_gas: EIA-861 electric utility number (str) -> EIA-176 gas LDC id (str).
# Utilities not listed have no gas mapping → those ZIPs fall back for gas.
STATE_CONFIG: dict[str, dict] = {
    "CA": {
        "label": "California",
        "elec_to_gas": {
            "14328": "17610617",  # Pacific Gas & Electric (dual-fuel)
            "17609": "17621931",  # Southern California Edison (elec) → SoCalGas (gas)
            "16609": "17611927",  # San Diego Gas & Electric (dual-fuel)
        },
    },
}

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def _get(url: str, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=timeout, context=_CTX).read()


def _download(check: bool) -> tuple[Path, Path, str, str]:
    iou_p, non_p = SOURCES / IOU_CSV_NAME, SOURCES / NON_IOU_CSV_NAME
    if not check:
        SOURCES.mkdir(parents=True, exist_ok=True)
        for url, p, label in ((IOU_CSV_URL, iou_p, IOU_CSV_NAME),
                              (NON_IOU_CSV_URL, non_p, NON_IOU_CSV_NAME)):
            data = _get(url)
            p.write_bytes(data)
            print(f"  snapshot {label}: {len(data):,} bytes  sha {hashlib.sha256(data).hexdigest()[:12]}…")
    iou_sha = hashlib.sha256(iou_p.read_bytes()).hexdigest()
    non_sha = hashlib.sha256(non_p.read_bytes()).hexdigest()
    return iou_p, non_p, iou_sha, non_sha


def build(states: list[str], check: bool):
    iou_p, non_p, iou_sha, non_sha = _download(check)
    iou = pd.read_csv(iou_p, dtype={"zip": str, "eiaid": "Int64"})
    iou = iou[iou["state"].isin(states)]
    non = pd.read_csv(non_p, dtype={"zip": str})
    non = non[non["state"].isin(states)]

    # Real-ZIP universe (CA CEC table) — confines the backfill to actual ZIPs.
    climate = json.loads(CLIMATE_ZIP_JSON.read_text())
    universe = {k for k in climate if not k.startswith("_")}

    elec_map: dict[str, list[str]] = {}
    gas_map: dict[str, list[str]] = {}
    inferred_elec: set[str] = set()    # backfilled by ZIP-prefix (lower confidence)
    inferred_gas: set[str] = set()
    gas_missing_elec: set[str] = set()

    for state in states:
        cfg = STATE_CONFIG.get(state)
        if cfg is None:
            print(f"  WARN: no config for {state!r}; skipping", file=sys.stderr)
            continue
        e2g = cfg["elec_to_gas"]
        ours = set(e2g)                       # our in-DB IOU ids
        sub = iou[iou["state"] == state]

        # ── 1. Authoritative mapping from the OpenEI IOU file ──────────────────
        for zc, grp in sub.groupby("zip"):
            zip5 = str(zc).zfill(5)
            eiaids = sorted({str(int(e)) for e in grp["eiaid"].dropna()})
            elec_map[zip5] = eiaids
            gas_ids = sorted({e2g[e] for e in eiaids if e in e2g})
            if gas_ids:
                gas_map[zip5] = gas_ids
            gas_missing_elec.update(e for e in eiaids if e not in e2g)

        # ── 2. Guarded gap backfill (chosen option 2) ─────────────────────────
        # Prefix (ZIP3) → set of ALL IOU ids present. Backfill a genuine-gap ZIP
        # only when its prefix maps to exactly ONE utility and it is one of ours
        # (no ambiguity, no foreign IOU). Excludes real munis/coops (in non-IOU
        # file) and non-existent ZIPs (outside the CEC universe).
        pref: dict[str, set] = {}
        for zc, grp in sub.groupby("zip"):
            pref.setdefault(str(zc)[:3], set()).update(
                str(int(e)) for e in grp["eiaid"].dropna())
        non_zips = set(non[non["state"] == state]["zip"])
        for zc in sorted(universe):
            if zc in elec_map or zc in non_zips:
                continue
            p = pref.get(zc[:3], set())
            if len(p) == 1 and p <= ours:           # unambiguous & one of ours
                eid = next(iter(p))
                elec_map[zc] = [eid]
                inferred_elec.add(zc)
                if eid in e2g:
                    gas_map[zc] = [e2g[eid]]
                    inferred_gas.add(zc)

    meta = {
        "status": f"OpenEI IOU ZIP→utility (2024) + guarded ZIP-prefix gap backfill, "
                  f"states {sorted(states)}.",
        "sources": {IOU_CSV_NAME: iou_sha, NON_IOU_CSV_NAME: non_sha},
        "source_url": IOU_CSV_URL,
        "extracted": str(date.today()),
        "backfill": "Genuine-gap ZIPs (in the CEC ZIP universe, absent from both OpenEI "
                    "files) whose ZIP-3 prefix maps unambiguously to one of our utilities are "
                    "inferred and listed in 'inferred_zips'. Real munis/coops (incl. CCSF/SF, "
                    "LADWP, SMUD) are NOT backfilled — they resolve to the CA average fallback.",
        "note": "Keys beginning with '_' are metadata. Values are lists of utility ids; "
                "multiple ids mean the ZIP spans territories (resolver disambiguates).",
    }

    if not check:
        ELEC_JSON.write_text(
            json.dumps({"_meta": {**meta, "id_type": "EIA-861 electric utility number",
                                  "inferred_zips": sorted(inferred_elec)},
                        **dict(sorted(elec_map.items()))}, indent=0), encoding="utf-8")
        GAS_JSON.write_text(
            json.dumps({"_meta": {**meta, "id_type": "EIA-176 gas LDC id",
                                  "derivation": "gas LDC derived from electric IOU territory; "
                                  "muni-electric areas (LADWP, SMUD) and the Central Coast may "
                                  "fall back — see build_zip_utility_map.py",
                                  "inferred_zips": sorted(inferred_gas),
                                  "elec_ids_without_gas_mapping": sorted(gas_missing_elec)},
                        **dict(sorted(gas_map.items()))}, indent=0), encoding="utf-8")
        print(f"\nWrote {ELEC_JSON.relative_to(ROOT)}: {len(elec_map)} ZIPs "
              f"({len(inferred_elec)} inferred)")
        print(f"Wrote {GAS_JSON.relative_to(ROOT)}: {len(gas_map)} ZIPs "
              f"({len(inferred_gas)} inferred)")
    else:
        print(f"  electric: {len(elec_map)} ZIPs ({len(inferred_elec)} inferred) | "
              f"gas: {len(gas_map)} ZIPs ({len(inferred_gas)} inferred)")
    return elec_map, gas_map


def main():
    ap = argparse.ArgumentParser(description="Build ZIP→utility crosswalks.")
    ap.add_argument("--states", nargs="+", default=["CA"], help="state codes (default: CA)")
    ap.add_argument("--check", action="store_true", help="parse cached snapshot only")
    args = ap.parse_args()
    build([s.upper() for s in args.states], check=args.check)


if __name__ == "__main__":
    main()
