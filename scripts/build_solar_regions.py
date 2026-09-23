#!/usr/bin/env python3
"""build_solar_regions.py — derive a solar region's ZIP list + ZCTA centroids → data/solar/regions.json.

See docs/OfflineSolarData_Plan.md §2b/§3. Membership rules live in solar_regions.py; this script
applies them to the Census 2020 ZCTA relationship files so the ZIP list is reproducible and every
ZIP carries the reason it was selected (reviewable in the committed JSON).

A ZCTA is selected when ≥ `min_in_county` of its land is in the region's county AND either
  * a member or enclave place covers ≥ `min_place_share` of its land, or
  * (include_unincorporated) ≥ `min_unincorporated` of its land is outside incorporated places
    (no place, or a CDP) and each `exclude_places` place covers < `max_excluded_share`.
ZCTAs already claimed by an earlier-wave region are skipped (a ZIP is harvested once). Only ZIPs
present in data/climate/zip_to_zone.json are kept.

Inputs (download once to scripts/downloads/, git-ignored; sha256 recorded in the output):
  2020_Gaz_zcta_national.txt            (unzipped from 2020_Gaz_zcta_national.zip)
  tab20_zcta520_place20_natl.txt
  tab20_zcta520_county20_natl.txt
from https://www2.census.gov/geo/docs/maps-data/data/{gazetteer/2020_Gazetteer,rel2020/zcta520}/

USAGE:  .venv/Scripts/python.exe scripts/build_solar_regions.py --region svce
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import solar_regions as SR  # noqa: E402

ROOT = Path(__file__).parent.parent
DL = ROOT / "scripts" / "downloads"
OUT_JSON = ROOT / "data" / "solar" / "regions.json"
ZIP_TO_ZONE = ROOT / "data" / "climate" / "zip_to_zone.json"
CENSUS = "https://www2.census.gov/geo/docs/maps-data/data/"
FILES = {
    "gazetteer": ("2020_Gaz_zcta_national.txt", CENSUS + "gazetteer/2020_Gazetteer/2020_Gaz_zcta_national.zip"),
    "zcta_place": ("tab20_zcta520_place20_natl.txt", CENSUS + "rel2020/zcta520/tab20_zcta520_place20_natl.txt"),
    "zcta_county": ("tab20_zcta520_county20_natl.txt", CENSUS + "rel2020/zcta520/tab20_zcta520_county20_natl.txt"),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(name: str) -> pd.DataFrame:
    df = pd.read_csv(DL / name, sep="|", dtype=str, encoding="utf-8-sig")
    df = df[df.GEOID_ZCTA5_20.notna()].copy()
    df["share"] = df.AREALAND_PART.astype(float) / df.AREALAND_ZCTA5_20.astype(float)
    return df


def select_zips(region: SR.SolarRegion, claimed: set[str], ca_zips: set[str]) -> dict[str, dict]:
    cty = _rel(FILES["zcta_county"][0])
    in_cty = cty[(cty.GEOID_COUNTY_20 == region.county_geoid) & (cty.share >= region.min_in_county)]
    cand = sorted(set(in_cty.GEOID_ZCTA5_20))
    pl = _rel(FILES["zcta_place"][0])
    pl = pl[pl.GEOID_ZCTA5_20.isin(cand)]
    gaz = pd.read_csv(DL / FILES["gazetteer"][0], sep="\t", dtype={"GEOID": str})
    gaz.columns = [c.strip() for c in gaz.columns]
    gaz = gaz.set_index("GEOID")

    out = {}
    for z in cand:
        if z in claimed or z not in ca_zips:
            continue
        parts = pl[pl.GEOID_ZCTA5_20 == z]
        by_place = parts[parts.NAMELSAD_PLACE_20.notna()].groupby("NAMELSAD_PLACE_20").share.sum()
        incorporated = sum(s for p, s in by_place.items() if not p.endswith(" CDP"))
        uninc = 1.0 - incorporated
        reason = None
        hits = [(p, s) for p, s in by_place.items()
                if p in region.member_places + region.enclave_places and s >= region.min_place_share]
        if hits:
            p, s = max(hits, key=lambda t: t[1])
            kind = "enclave" if p in region.enclave_places else "member"
            reason = f"{kind}: {p} {s:.0%}"
        elif (region.include_unincorporated and uninc >= region.min_unincorporated
              and all(by_place.get(p, 0.0) < region.max_excluded_share for p in region.exclude_places)):
            reason = f"unincorporated {uninc:.0%}"
        if reason:
            g = gaz.loc[z]
            out[z] = {"lat": round(float(g.INTPTLAT), 6), "lon": round(float(g.INTPTLONG), 6),
                      "reason": reason}
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")          # Windows console: allow → in help/labels
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--region", required=True,
                    choices=sorted(t for t in SR.REGIONS if t != SR.ZONE_STATIONS_REGION))
    args = ap.parse_args()
    region = SR.REGIONS[args.region]
    for key, (name, url) in FILES.items():
        if not (DL / name).exists():
            raise SystemExit(f"missing scripts/downloads/{name} — download from {url}")

    doc = json.loads(OUT_JSON.read_text(encoding="utf-8")) if OUT_JSON.exists() else {"_meta": {}}
    claimed = {z for t, r in doc.items() if not t.startswith("_") and t != region.tag
               and SR.REGIONS[t].wave < region.wave for z in r["zips"]}
    ca_zips = {k for k in json.loads(ZIP_TO_ZONE.read_text(encoding="utf-8")) if not k.startswith("_")}
    zips = select_zips(region, claimed, ca_zips)

    doc["_meta"] = {
        "status": "Derived solar harvest regions (ZIP lists + ZCTA centroids). A region is a harvest "
                  "grouping, not a statement of service territory. See docs/OfflineSolarData_Plan.md §2b.",
        "sources": {k: {"file": n, "url": u, "sha256": _sha256(DL / n)} for k, (n, u) in FILES.items()},
        "built": date.today().isoformat(),
    }
    doc[region.tag] = {
        "name": region.name, "wave": region.wave, "source_url": region.source_url,
        "rules": {"county_geoid": region.county_geoid, "member_places": list(region.member_places),
                  "enclave_places": list(region.enclave_places),
                  "include_unincorporated": region.include_unincorporated,
                  "exclude_places": list(region.exclude_places),
                  "min_in_county": region.min_in_county, "min_place_share": region.min_place_share,
                  "min_unincorporated": region.min_unincorporated,
                  "max_excluded_share": region.max_excluded_share},
        "zips": zips,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"{region.tag}: {len(zips)} ZIPs -> {OUT_JSON.relative_to(ROOT)}")
    for z, v in zips.items():
        print(f"  {z}  {v['lat']:>10.5f} {v['lon']:>11.5f}  {v['reason']}")


if __name__ == "__main__":
    main()
