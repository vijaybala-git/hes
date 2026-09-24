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

MUNICIPAL UTILITIES (Phase 7 §4.1 issue 6): the OpenEI non-IOU file lists CA munis
(SMUD, LADWP, Silicon Valley Power, …). A ZIP listed under a "full" muni goes to it when at
least half the ZIP's land area lies in the muni's service geography (2020 Census ZCTA↔place /
ZCTA↔county relationship files in scripts/downloads/); a ZIP listed only under a "partial"
muni goes to its host IOU (San Francisco → PG&E). Table + rule: scripts/ca_munis.py. Each
decision is recorded in `_meta.muni_decisions`.

USAGE (run from project root):
    python scripts/build_zip_utility_map.py --states CA
    python scripts/build_zip_utility_map.py --check     # parse cached snapshot, no download
    python scripts/build_zip_utility_map.py --offline   # rebuild from cached snapshots
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

sys.path.insert(0, str(Path(__file__).parent))
from ca_munis import CA_MUNIS, MUNI_SHARE, NEIGHBOUR_MAX_SHARE  # noqa: E402

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
DOWNLOADS = ROOT / "scripts" / "downloads"
ZCTA_PLACE = DOWNLOADS / "tab20_zcta520_place20_natl.txt"     # 2020 Census relationship files
ZCTA_COUNTY = DOWNLOADS / "tab20_zcta520_county20_natl.txt"
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


class MuniGeography:
    """Share of a ZCTA's land area inside a muni's service geography (Census 2020)."""

    def __init__(self, state_fips: str = "06"):
        cols = ["GEOID_ZCTA5_20", "AREALAND_ZCTA5_20", "AREALAND_PART"]
        pl = pd.read_csv(ZCTA_PLACE, sep="|", dtype=str, encoding="utf-8-sig",
                         usecols=cols + ["GEOID_PLACE_20", "NAMELSAD_PLACE_20"])
        pl = pl[pl["GEOID_PLACE_20"].str.startswith(state_fips, na=False)
                & pl["GEOID_ZCTA5_20"].notna()]
        co = pd.read_csv(ZCTA_COUNTY, sep="|", dtype=str, encoding="utf-8-sig",
                         usecols=cols + ["GEOID_COUNTY_20"])
        co = co[co["GEOID_COUNTY_20"].str.startswith(state_fips, na=False)
                & co["GEOID_ZCTA5_20"].notna()]
        self.zcta_land = {z: float(a) for z, a in
                          pd.concat([pl, co])[["GEOID_ZCTA5_20", "AREALAND_ZCTA5_20"]]
                          .drop_duplicates().itertuples(index=False)}
        self.place = {}          # (zcta, place name) -> land part
        self.place_land = {}     # zcta -> land inside any Census place (towns, CDPs)
        for z, n, a in pl[["GEOID_ZCTA5_20", "NAMELSAD_PLACE_20", "AREALAND_PART"]] \
                .itertuples(index=False):
            self.place[(z, n)] = self.place.get((z, n), 0.0) + float(a)
            self.place_land[z] = self.place_land.get(z, 0.0) + float(a)
        self.county = {(z, c): float(a) for z, c, a in
                       co[["GEOID_ZCTA5_20", "GEOID_COUNTY_20", "AREALAND_PART"]]
                       .itertuples(index=False)}
        self.main_county = {}    # zcta -> county holding most of its land
        for (z, c), a in self.county.items():
            if a > self.county.get((z, self.main_county.get(z)), -1.0):
                self.main_county[z] = c
        self.place_names = set(pl["NAMELSAD_PLACE_20"])

    def validate(self, table: dict):
        """Every place named in the muni table exists (catches typos)."""
        missing = []
        for eid, m in table.items():
            names = list(m.get("places", [])) + list((m.get("county") or (None, []))[1])
            missing += [f"{eid}:{n}" for n in names if n not in self.place_names]
        if missing:
            raise SystemExit(f"ca_munis.py: unknown Census places {missing}")

    def has_land(self, zcta: str) -> bool:
        return bool(self.zcta_land.get(zcta))

    def share(self, zcta: str, m: dict) -> float:
        """Share of the ZIP inside the muni's geography: the larger of (a) its land-area share
        and (b) for place-listed munis, its share of the ZIP's *place* land — homes sit in
        towns/CDPs, while an irrigation district's rural land lies outside them (95380
        Turlock: 14% of the land, but nearly all of the town land)."""
        land = self.zcta_land.get(zcta)
        if not land:
            return 0.0
        in_places = sum(self.place.get((zcta, n), 0.0) for n in m.get("places", []))
        part = in_places
        if m.get("county"):
            geoid, excluded = m["county"]
            part += self.county.get((zcta, geoid), 0.0)
            part -= sum(self.place.get((zcta, n), 0.0) for n in excluded)
        area = max(0.0, min(1.0, part / land))
        town = self.place_land.get(zcta, 0.0)
        by_town = (in_places / town) if (town and m.get("places")) else 0.0
        return max(area, min(1.0, by_town))


def _county_ious(elec_map: dict, geo: MuniGeography, share: float = 0.8) -> dict:
    """County → its dominant IOU (≥ `share` of the county's IOU-listed ZIPs)."""
    counts: dict[str, dict[str, int]] = {}
    for z, ids in elec_map.items():
        c = geo.main_county.get(z)
        if c and len(ids) == 1:
            counts.setdefault(c, {}).setdefault(ids[0], 0)
            counts[c][ids[0]] += 1
    out = {}
    for c, byid in counts.items():
        top, n = max(byid.items(), key=lambda kv: kv[1])
        if n >= share * sum(byid.values()):
            out[c] = top
    return out


def _resolve_munis(elec_map: dict, gas_map: dict, non_state: pd.DataFrame,
                   e2g: dict, geo: MuniGeography, prefix_ious: dict) -> dict:
    """Apply the muni rule (scripts/ca_munis.py) in place; return per-ZIP decisions.

    prefix_ious: ZIP-3 → set of IOU ids listed in that prefix (for the sole-muni check)."""
    county_iou = _county_ious(elec_map, geo)
    decisions = {}
    munis_by_zip = non_state.groupby("zip")["eiaid"].apply(
        lambda s: sorted({str(int(e)) for e in s.dropna()}))
    for zc, munis in munis_by_zip.items():
        zip5 = str(zc).zfill(5)
        ious = elec_map.get(zip5, [])
        best, best_share = None, 0.0
        shares = {}
        for mid in munis:
            m = CA_MUNIS.get(mid)
            if m and m["kind"] == "full":
                shares[mid] = round(geo.share(zip5, m), 3)
                if shares[mid] >= MUNI_SHARE and shares[mid] > best_share:
                    best, best_share = mid, shares[mid]
        if best:
            elec_map[zip5] = [best] + [i for i in ious if i != best]
            if zip5 not in gas_map and CA_MUNIS[best]["gas"]:
                gas_map[zip5] = [CA_MUNIS[best]["gas"]]
            why = "muni_share"
        elif ious:
            why = "iou_share" if shares else "iou_listed"
        else:
            hosts = [CA_MUNIS[m]["host"] for m in munis
                     if m in CA_MUNIS and CA_MUNIS[m]["kind"] == "partial"]
            if hosts and not shares:
                host = hosts[0]
                elec_map[zip5] = [host]
                if host in e2g:
                    gas_map[zip5] = [e2g[host]]
                why = "partial_host"
            else:                                   # listed only under munis
                pick = max(shares, key=shares.get) if shares else munis[0]
                pref = prefix_ious.get(zip5[:3], set())
                covers = shares and max(shares.values()) >= NEIGHBOUR_MAX_SHARE
                c_iou = county_iou.get(geo.main_county.get(zip5))
                if shares and not covers and geo.has_land(zip5) and (
                        (len(pref) == 1 and pref <= set(e2g)) or c_iou in e2g):
                    # A real ZIP the muni's geography does not cover (OpenEI lists LADWP for
                    # Santa Monica / Beverly Hills): the prefix's only IOU, else the county's
                    # dominant IOU.
                    iou = next(iter(pref)) if (len(pref) == 1 and pref <= set(e2g)) else c_iou
                    elec_map[zip5] = [iou]
                    gas_map[zip5] = [e2g[iou]]
                    why = "neighbour_iou"
                else:                               # sole provider (or a PO-box ZIP)
                    elec_map[zip5] = [pick]
                    g = (CA_MUNIS.get(pick) or {}).get("gas")
                    if g:
                        gas_map[zip5] = [g]
                    why = "sole_muni"
        decisions[zip5] = {"electric": elec_map[zip5][0], "rule": why,
                           "listed_munis": munis, "listed_ious": ious,
                           **({"muni_share": shares} if shares else {})}
    return decisions


def build(states: list[str], check: bool, offline: bool = False):
    iou_p, non_p, iou_sha, non_sha = _download(check or offline)
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
    muni_decisions: dict = {}
    geo = MuniGeography()
    geo.validate(CA_MUNIS)

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

        # ── 1b. Municipal utilities (Phase 7 §4.1 issue 6) ─────────────────────
        if state == "CA":
            prefix_ious: dict[str, set] = {}
            for zc, grp in sub.groupby("zip"):
                prefix_ious.setdefault(str(zc).zfill(5)[:3], set()).update(
                    str(int(e)) for e in grp["eiaid"].dropna())
            muni_decisions.update(_resolve_munis(
                elec_map, gas_map, non[non["state"] == state], e2g, geo, prefix_ious))

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
                    "inferred and listed in 'inferred_zips'. ZIPs in the non-IOU file are "
                    "never backfilled — the muni rule decides them.",
        "munis": f"OpenEI non-IOU file + scripts/ca_munis.py: a 'full' muni wins a ZIP when "
                 f">= {MUNI_SHARE:.0%} of its land lies in the muni's service geography "
                 "(2020 Census ZCTA-place/county relationship files); a ZIP listed only under "
                 "a 'partial' muni goes to its host IOU (SF -> PG&E). See muni_decisions.",
        "census_sources": {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                           for f in (ZCTA_PLACE, ZCTA_COUNTY)},
        "note": "Keys beginning with '_' are metadata. Values are lists of utility ids, the "
                "serving utility first; the resolver takes the first one it prices.",
    }

    if not check:
        ELEC_JSON.write_text(
            json.dumps({"_meta": {**meta, "id_type": "EIA-861 electric utility number",
                                  "inferred_zips": sorted(inferred_elec),
                                  "muni_decisions": dict(sorted(muni_decisions.items()))},
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
        rules = pd.Series([d["rule"] for d in muni_decisions.values()]).value_counts()
        print("  muni rule:", ", ".join(f"{k} {v}" for k, v in rules.items()))
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
    ap.add_argument("--offline", action="store_true",
                    help="rebuild the JSON from the cached snapshots (no download)")
    args = ap.parse_args()
    build([s.upper() for s in args.states], check=args.check, offline=args.offline)


if __name__ == "__main__":
    main()
