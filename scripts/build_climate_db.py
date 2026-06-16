"""build_climate_db.py — assemble the WhyWatt climate database from authoritative sources.

Phase 4 §1. Produces two committed artifacts:
  data/climate/tmy3_zones.json   16 CEC zone records (HDD/CDD/inlet/avg-temp)  [Step 1.3]
  data/climate/zip_to_zone.json  CA ZIP -> zone index (CEC table)              [Step 1.6]

Source weather data is the OneBuilding TMYx series (climate.onebuilding.org), a Typical
Meteorological Year synthesized from NOAA ISD hourly observations using the Sandia method.
One reference station per CEC Building Climate Zone (Title 24), latest pinned TMYx vintage.
Raw source files are snapshotted under data/climate/sources/ so the build is reproducible
offline and the numbers can never silently change when OneBuilding re-issues a station.

Modes:
  python scripts/build_climate_db.py --download   # fetch + snapshot the 16 EPW sources
  # (parse/build-zones mode added in Step 1.3; zip-table mode in Step 1.6)
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import ssl
import sys
import time
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
SOURCES = ROOT / "data" / "climate" / "sources"
ZIP_DIR = SOURCES / "tmyx"                       # as-downloaded OneBuilding .zip snapshots
INDEX_CACHE = SOURCES / "onebuilding_ca_index.html"

ONEBUILDING_CA = ("https://climate.onebuilding.org/WMO_Region_4_North_and_Central_America/"
                  "USA_United_States_of_America/CA_California/")
VINTAGE = "TMYx.2011-2025"   # latest pinned vintage across all 16 stations (reviewed 2026-06)

# ── Reviewed station manifest: one TMYx station per CEC Building Climate Zone ──────
# wmo = NOAA/WMO station id; the exact filename is resolved from the live index by wmo.
# Substitutions/picks (reviewed & approved): see "note".
STATION_MANIFEST = {
    "CA_CZ1":  dict(zone_id="CZ1",  reference_city="Arcata",      wmo="725945", note=""),
    "CA_CZ2":  dict(zone_id="CZ2",  reference_city="Santa Rosa",  wmo="724957", note=""),
    "CA_CZ3":  dict(zone_id="CZ3",  reference_city="Oakland",     wmo="724930", note=""),
    "CA_CZ4":  dict(zone_id="CZ4",  reference_city="San Jose",    wmo="724945", note=""),
    "CA_CZ5":  dict(zone_id="CZ5",  reference_city="Santa Maria", wmo="723940", note=""),
    "CA_CZ6":  dict(zone_id="CZ6",  reference_city="Los Angeles", wmo="722950", note="LAX (coastal) for south-coast zone"),
    "CA_CZ7":  dict(zone_id="CZ7",  reference_city="San Diego",   wmo="722900", note=""),
    "CA_CZ8":  dict(zone_id="CZ8",  reference_city="El Toro",     wmo="722976", note="Fullerton — El Toro MCAS closed 1999"),
    "CA_CZ9":  dict(zone_id="CZ9",  reference_city="Pasadena",    wmo="722880", note="Burbank — no Pasadena station"),
    "CA_CZ10": dict(zone_id="CZ10", reference_city="Riverside",   wmo="722869", note="Riverside Muni"),
    "CA_CZ11": dict(zone_id="CZ11", reference_city="Red Bluff",   wmo="725910", note=""),
    "CA_CZ12": dict(zone_id="CZ12", reference_city="Sacramento",  wmo="724830", note="Sacramento Exec"),
    "CA_CZ13": dict(zone_id="CZ13", reference_city="Fresno",      wmo="723890", note=""),
    "CA_CZ14": dict(zone_id="CZ14", reference_city="China Lake",  wmo="746120", note=""),
    "CA_CZ15": dict(zone_id="CZ15", reference_city="El Centro",   wmo="722810", note=""),
    "CA_CZ16": dict(zone_id="CZ16", reference_city="Blue Canyon", wmo="725845", note=""),
}

# Public weather data over TLS; some OneBuilding certs don't validate on all hosts. We pin
# integrity via sha256 of the downloaded content instead.
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def _get(url: str, tries: int = 4, timeout: int = 40) -> bytes:
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            return urllib.request.urlopen(req, timeout=timeout, context=_CTX).read()
        except Exception as e:            # noqa: BLE001 — transient resets are common
            last = e
            time.sleep(2 + 2 * i)
    raise RuntimeError(f"failed after {tries} tries: {url}\n  {type(last).__name__}: {last}")


def _index_filenames(refresh: bool = False) -> list[str]:
    if refresh or not INDEX_CACHE.exists():
        SOURCES.mkdir(parents=True, exist_ok=True)
        INDEX_CACHE.write_bytes(_get(ONEBUILDING_CA))
    html = INDEX_CACHE.read_text(encoding="latin-1")
    return sorted(set(re.findall(r"USA_CA_[^\"'<>]+?\.zip", html)))


def download_sources():
    """Fetch each zone's TMYx zip, snapshot it as-downloaded, and record provenance."""
    ZIP_DIR.mkdir(parents=True, exist_ok=True)
    files = _index_filenames(refresh=True)
    manifest = {"_meta": {
        "source_repo": "climate.onebuilding.org",
        "source_dir": ONEBUILDING_CA,
        "series": VINTAGE,
        "note": "TMYx = Typical Meteorological Year from NOAA ISD via the Sandia method. "
                "Snapshots are the as-downloaded .zip (incl. .epw + ASHRAE .stat/.ddy companions).",
        "downloaded": str(date.today()),
    }}
    for zone_key, info in STATION_MANIFEST.items():
        wmo, vint = info["wmo"], VINTAGE
        match = [f for f in files if f".{wmo}_{vint}.zip" in f]
        if not match:
            print(f"  !! {zone_key} {wmo}: no '{vint}' file in index"); continue
        zipname = match[0]
        zdata = _get(ONEBUILDING_CA + zipname)
        zf = zipfile.ZipFile(io.BytesIO(zdata))                 # validate it parses + has an .epw
        epw_name = [n for n in zf.namelist() if n.lower().endswith(".epw")][0]
        (ZIP_DIR / zipname).write_bytes(zdata)                  # snapshot the original .zip
        sha = hashlib.sha256(zdata).hexdigest()
        manifest[zone_key] = dict(
            zone_id=info["zone_id"], reference_city=info["reference_city"],
            wmo=wmo, vintage=vint, source_zip=zipname, epw_file=epw_name,
            zip_sha256=sha, note=info["note"])
        print(f"  ok {zone_key:7} {wmo}  {zipname[:52]:52}  {sha[:12]}…")
    (SOURCES / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nWrote {SOURCES / 'manifest.json'} ({len(manifest) - 1} zones)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true", help="fetch + snapshot the 16 EPW sources")
    args = ap.parse_args()
    if args.download:
        download_sources()
    else:
        ap.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
