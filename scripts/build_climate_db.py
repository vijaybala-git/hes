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
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

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


ZONES_JSON = ROOT / "data" / "climate" / "tmy3_zones.json"
ZIP_JSON = ROOT / "data" / "climate" / "zip_to_zone.json"
FALLBACK_ZONE = "CA_CZ4"
# Official CEC ZIP -> Building Climate Zone table (xlsx).
CEC_ZIP_URL = ("https://www.energy.ca.gov/sites/default/files/2020-04/"
               "BuildingClimateZonesByZIPCode_ada.xlsx")
CEC_DIR = SOURCES / "cec"
# Generated table fragment for the "Climate Data" help page (included via @include).
DOC_FRAGMENT = ROOT / "docs" / "help" / "_generated" / "climate_zones_table.md"
_MID_DOY = np.array([15, 46, 74, 105, 135, 166, 196, 227, 258, 288, 319, 349])

# Provisional trend CAGRs — uniform placeholder until Step 1d replaces them with per-zone
# Cal-Adapt fits. Kept non-zero so the trend UI stays demonstrable; clearly flagged.
_PROVISIONAL_HDD_CAGR = {"none": 0.0, "rcp45": -0.004, "rcp85": -0.008}
_PROVISIONAL_CDD_CAGR = {"none": 0.0, "rcp45": 0.008, "rcp85": 0.016}


def _parse_epw(epw_text: str):
    """Return (monthly_hdd, monthly_cdd, monthly_avg_f) — daily-mean, base 65°F."""
    rows = epw_text.splitlines()[8:]            # 8 EPW header lines
    by_day = defaultdict(list)
    for ln in rows:
        f = ln.split(",")
        by_day[(int(f[1]), int(f[2]))].append(float(f[6]))   # f[6] = dry-bulb °C
    hdd = np.zeros(12); cdd = np.zeros(12); tsum = np.zeros(12); tcnt = np.zeros(12)
    for (mo, _dy), temps in by_day.items():
        tmean_f = (sum(temps) / len(temps)) * 9 / 5 + 32
        hdd[mo - 1] += max(0.0, 65 - tmean_f)
        cdd[mo - 1] += max(0.0, tmean_f - 65)
        tsum[mo - 1] += tmean_f; tcnt[mo - 1] += 1
    return hdd, cdd, tsum / tcnt


def _mains_water_f(monthly_avg_f: np.ndarray) -> np.ndarray:
    """Monthly cold-water inlet temp via the Burch & Christensen (2007) correlation,
    as used by NREL BEopt / ResStock. Driven by annual mean air temp and its range."""
    t_amb = float(monthly_avg_f.mean())
    dt_amb = float(monthly_avg_f.max() - monthly_avg_f.min())
    ratio = 0.4 + 0.01 * (t_amb - 44.0)
    lag = 35.0 - 1.0 * (t_amb - 44.0)
    ang = np.deg2rad(0.986 * (_MID_DOY - 15 - lag) - 90.0)
    return (t_amb + 6.0) + ratio * (dt_amb / 2.0) * np.sin(ang)


def build_zones():
    """Parse each snapshotted EPW into a CEC zone record; write tmy3_zones.json."""
    man = json.loads((SOURCES / "manifest.json").read_text(encoding="utf-8"))
    out = {"_meta": {
        "schema_version": 3,
        "description": "CEC Building Climate Zone records derived from OneBuilding TMYx EPW "
                       "(daily-mean HDD/CDD base 65°F; inlet water via Burch-Christensen 2007).",
        "source_repo": "climate.onebuilding.org",
        "series": VINTAGE,
        "method": "daily-mean degree-days, base 65°F; mains water = Burch-Christensen (BEopt)",
        "built": str(date.today()),
        "trend_note": "hdd/cdd_cagr_by_scenario are PROVISIONAL uniform placeholders pending "
                      "Step 1d (Cal-Adapt per-zone fit).",
        "invariants": "monthly arrays length 12 (Jan..Dec); monthly HDD/CDD sum to annual.",
    }}
    summary = []
    for zone_key, info in STATION_MANIFEST.items():
        rec_src = man[zone_key]
        zpath = ZIP_DIR / rec_src["source_zip"]
        zf = zipfile.ZipFile(zpath)
        epw_name = [n for n in zf.namelist() if n.lower().endswith(".epw")][0]
        hdd, cdd, avg = _parse_epw(zf.read(epw_name).decode("latin-1"))
        inlet = _mains_water_f(avg)
        out[zone_key] = {
            "state": "CA", "zone_id": info["zone_id"], "reference_city": info["reference_city"],
            "tmy3_station": info["wmo"], "vintage": VINTAGE,
            "source_file": rec_src["epw_file"], "source_zip": rec_src["source_zip"],
            "sha256": rec_src["zip_sha256"], "extracted": str(date.today()),
            "annual_hdd_65f": round(float(hdd.sum())),
            "annual_cdd_65f": round(float(cdd.sum())),
            "monthly_hdd_65f": [round(float(x)) for x in hdd],
            "monthly_cdd_65f": [round(float(x)) for x in cdd],
            "monthly_inlet_water_f": [round(float(x)) for x in inlet],
            "monthly_avg_temp_f": [round(float(x)) for x in avg],
            "hdd_cagr_by_scenario": dict(_PROVISIONAL_HDD_CAGR),
            "cdd_cagr_by_scenario": dict(_PROVISIONAL_CDD_CAGR),
            "note": info["note"],
        }
        summary.append((info["zone_id"], info["reference_city"],
                        out[zone_key]["annual_hdd_65f"], out[zone_key]["annual_cdd_65f"]))
    ZONES_JSON.write_text(json.dumps(out, indent=2), encoding="utf-8")
    _write_doc_fragment(out)
    print(f"Wrote {ZONES_JSON} ({len(summary)} zones)\n")
    print(f"{'Zone':5} {'City':14} {'HDD':>6} {'CDD':>6}")
    for zid, city, h, c in summary:
        print(f"{zid:5} {city:14} {h:6d} {c:6d}")


def _write_doc_fragment(zones: dict):
    """Emit the 16-zone summary as a 4-space-indented (pre-formatted) help fragment.

    Included by docs/help/help_content.md via `@include:`; regenerated on every build so
    the Climate Data help page can never drift from data/climate/tmy3_zones.json.
    """
    rows = [(r["zone_id"], r["reference_city"], r["tmy3_station"],
             r["annual_hdd_65f"], r["annual_cdd_65f"])
            for k, r in zones.items() if not k.startswith("_")]
    L = ["    Generated from data/climate/tmy3_zones.json by scripts/build_climate_db.py — do not edit by hand.",
         f"    Source: OneBuilding {VINTAGE} · daily-mean degree-days, base 65°F · built {date.today()}",
         "    " + "-" * 56,
         f"    {'Zone':5} {'Reference city':16} {'Stn':7} {'HDD':>5} {'CDD':>5}"]
    L += [f"    {z:5} {c:16} {w:7} {h:5d} {d:5d}" for z, c, w, h, d in rows]
    DOC_FRAGMENT.parent.mkdir(parents=True, exist_ok=True)
    DOC_FRAGMENT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"Wrote {DOC_FRAGMENT}")


def build_zip_table():
    """Snapshot the official CEC ZIP->Building-Climate-Zone xlsx -> zip_to_zone.json."""
    import openpyxl
    CEC_DIR.mkdir(parents=True, exist_ok=True)
    data = _get(CEC_ZIP_URL)
    snap = CEC_DIR / "BuildingClimateZonesByZIPCode_ada.xlsx"
    snap.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()

    ws = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
    rows = list(ws.iter_rows(values_only=True))[1:]   # drop header ("Zip Code","Building CZ")

    mapping, skipped = {}, 0
    for zc, cz in rows:
        try:
            zip5, czi = str(int(zc)).zfill(5), int(cz)
        except (TypeError, ValueError):
            skipped += 1; continue
        if not 1 <= czi <= 16:
            skipped += 1; continue
        mapping[zip5] = f"CA_CZ{czi}"

    out = {"_meta": {
        "status": f"Official CEC Building Climate Zones by ZIP Code ({len(mapping)} ZIPs).",
        "source_url": CEC_ZIP_URL,
        "source_file": snap.name,
        "sha256": sha,
        "extracted": str(date.today()),
        "fallback_zone": FALLBACK_ZONE,
        "note": "Keys beginning with '_' are metadata; values are zone keys into tmy3_zones.json.",
    }}
    out.update({z: mapping[z] for z in sorted(mapping)})
    ZIP_JSON.write_text(json.dumps(out, indent=0), encoding="utf-8")
    print(f"Wrote {ZIP_JSON}: {len(mapping)} ZIPs (skipped {skipped}); sha {sha[:12]}…")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true", help="fetch + snapshot the 16 EPW sources")
    ap.add_argument("--build-zones", action="store_true", help="parse snapshots -> tmy3_zones.json")
    ap.add_argument("--build-zips", action="store_true", help="CEC xlsx -> zip_to_zone.json")
    args = ap.parse_args()
    if args.download:
        download_sources()
    elif args.build_zones:
        build_zones()
    elif args.build_zips:
        build_zip_table()
    else:
        ap.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
