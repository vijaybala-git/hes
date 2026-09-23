#!/usr/bin/env python3
"""build_pvwatts.py — offline PVWatts v8 solar-yield harvest → data/solar/pvwatts_zip.json.

See docs/OfflineSolarData_Plan.md. For each site in a region (solar_regions.py) this script:
  1. calls PVWatts v8 once at 1 kW DC, the single default orientation, timeframe=hourly — or reuses
     the local cache (data/solar/sources/cache/, git-ignored) so a re-run makes no API calls;
  2. reduces the 8760 hourly AC output to `ac_monthly[12]` (kWh/kW) and a normalized
     `intraday_shape[12][24]` (each month's 24 values sum to 1), cross-checked against PVWatts'
     own ac_monthly;
  3. merges the sites into pvwatts_zip.json additively — other regions are never rewritten.

Wave 0 (`--region ca_zone_stations`) also commits a trimmed raw snapshot per station under
data/solar/sources/zone_stations/ (the full response's sha256 is recorded in the baked file).

NOTHING here is imported by src/ (isolation gate, §6) until Phase 7.

USAGE (from project root, with the venv interpreter):
    .venv/Scripts/python.exe scripts/build_pvwatts.py --region ca_zone_stations
The API key: --api-key > NREL_API_KEY env > secrets/nrel_api_key > URDB key > DEMO_KEY (secrets/README.md).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import requests

sys.path.insert(0, str(Path(__file__).parent))
import solar_regions as SR  # noqa: E402
from build_urdb import KEY_FILE, _read_key_file  # noqa: E402  (shared key file + tolerant reader)

ROOT = Path(__file__).parent.parent
SOLAR = ROOT / "data" / "solar"
OUT_JSON = SOLAR / "pvwatts_zip.json"
CACHE = SOLAR / "sources" / "cache"                  # git-ignored full raw responses
SNAPSHOTS = SOLAR / "sources" / "zone_stations"      # committed, trimmed raw (wave 0 only)
ZONES_JSON = ROOT / "data" / "climate" / "tmy3_zones.json"
NREL_KEY_FILE = ROOT / "secrets" / "nrel_api_key"    # git-ignored; see secrets/README.md
REGIONS_JSON = SOLAR / "regions.json"                # ZIP regions, from build_solar_regions.py
ZIP_TO_ZONE = ROOT / "data" / "climate" / "zip_to_zone.json"

# NREL is now the National Laboratory of the Rockies; developer.nrel.gov no longer resolves (2026-09).
PVWATTS_URL = "https://developer.nlr.gov/api/pvwatts/v8.json"
# Single default orientation (plan §2 #3). Roof tilt/azimuth stay inert through Phase 7.
DEFAULT_PARAMS = {
    "system_capacity": 1, "module_type": 0, "array_type": 1, "tilt": 20, "azimuth": 180,
    "losses": 14, "dataset": "nsrdb", "timeframe": "hourly",
}
HOURS_PER_MONTH = [d * 24 for d in (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)]  # 8760 TMY
SHAPE_DP = 5
MIN_INTERVAL_S = 4.0          # ≤ 900 req/hr — under NREL's default 1,000/hr


def resolve_api_key(cli_key: str | None) -> tuple[str, str]:
    """(key, source): --api-key > NREL_API_KEY > secrets/nrel_api_key > URDB key (env/file) > DEMO_KEY.

    The URDB key is only a fallback — the developer networks share a key namespace (secrets/README.md).
    """
    if cli_key:
        return cli_key, "--api-key"
    for var, path in (("NREL_API_KEY", NREL_KEY_FILE), ("URDB_API_KEY", KEY_FILE)):
        if os.environ.get(var):
            return os.environ[var], var
        if path.exists() and (key := _read_key_file(path)):
            return key, str(path.relative_to(ROOT))
    return "DEMO_KEY", "DEMO_KEY"


# ── Sites ────────────────────────────────────────────────────────────────────────
def region_sites(tag: str) -> list[dict]:
    """[{site_key, lat, lon, zone, zip}] for a region."""
    if tag == SR.ZONE_STATIONS_REGION:
        zones = json.loads(ZONES_JSON.read_text(encoding="utf-8"))
        return [{"site_key": f"zone:{z}", "lat": float(v["latitude"]), "lon": float(v["longitude"]),
                 "zone": z, "zip": None, "label": f"{v['reference_city']} ({v['tmy3_station']})"}
                for z, v in zones.items() if not z.startswith("_")]
    regions = json.loads(REGIONS_JSON.read_text(encoding="utf-8")) if REGIONS_JSON.exists() else {}
    if tag not in regions:
        raise SystemExit(f"region {tag!r} not in {REGIONS_JSON.relative_to(ROOT)} — run "
                         f"scripts/build_solar_regions.py --region {tag} first")
    zip_to_zone = json.loads(ZIP_TO_ZONE.read_text(encoding="utf-8"))
    return [{"site_key": f"zip:{z}", "lat": v["lat"], "lon": v["lon"], "zone": zip_to_zone[z],
             "zip": z, "label": f"ZIP {z} ({v['reason']})"}
            for z, v in regions[tag]["zips"].items()]


# ── Fetch (cached) ───────────────────────────────────────────────────────────────
def _cache_path(site_key: str) -> Path:
    return CACHE / (site_key.replace(":", "_") + ".json")


def fetch_site(site: dict, api_key: str, last_call: list[float]) -> tuple[dict, bool]:
    """Return (raw response, from_cache). Throttled, retried on 429/5xx."""
    path = _cache_path(site["site_key"])
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")), True
    params = {**DEFAULT_PARAMS, "lat": site["lat"], "lon": site["lon"], "api_key": api_key}
    for attempt in range(5):
        wait = MIN_INTERVAL_S - (time.monotonic() - last_call[0])
        if wait > 0:
            time.sleep(wait)
        last_call[0] = time.monotonic()
        try:
            r = requests.get(PVWATTS_URL, params=params, timeout=60)
        except requests.RequestException as e:           # never echo the key-bearing URL
            raise RuntimeError(f"{site['site_key']}: {type(e).__name__} — "
                               f"{str(e).replace(api_key, '****')}") from None
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(10 * (attempt + 1))
            continue
        if not r.ok:
            raise RuntimeError(f"{site['site_key']}: HTTP {r.status_code} — "
                               f"{r.text[:300].replace(api_key, '****')}")
        raw = r.json()
        if isinstance(raw.get("inputs"), dict):          # the echoed request must never carry the key
            raw["inputs"].pop("api_key", None)
        if raw.get("errors"):
            raise RuntimeError(f"{site['site_key']}: PVWatts errors {raw['errors']}")
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw), encoding="utf-8")
        return raw, False
    raise RuntimeError(f"{site['site_key']}: PVWatts failed after retries (last HTTP {r.status_code})")


# ── Reduce ───────────────────────────────────────────────────────────────────────
def reduce_hourly(raw: dict) -> dict:
    """8760 hourly AC (W, per 1 kW DC) → ac_monthly[12] kWh/kW + intraday_shape[12][24]."""
    ac = np.asarray(raw["outputs"]["ac"], dtype=float)
    if ac.shape != (8760,):
        raise ValueError(f"expected 8760 hourly values, got {ac.shape}")
    ac_monthly, shape, start = [], [], 0
    for n in HOURS_PER_MONTH:
        month = ac[start:start + n].reshape(-1, 24)          # days × 24 (local standard time)
        start += n
        by_hour = month.sum(axis=0)
        total = by_hour.sum()
        ac_monthly.append(total / 1000.0)
        shape.append(by_hour / total)
    # consistency with PVWatts' own monthly totals (kWh)
    pv_monthly = np.asarray(raw["outputs"]["ac_monthly"], dtype=float)
    if not np.allclose(ac_monthly, pv_monthly, rtol=1e-3, atol=0.05):
        raise ValueError(f"hourly-derived monthly {np.round(ac_monthly, 2)} != PVWatts {pv_monthly}")
    shape = [[round(float(x), SHAPE_DP) for x in row] for row in shape]
    for row in shape:                                        # re-normalize after rounding
        row[int(np.argmax(row))] = round(row[int(np.argmax(row))] + 1.0 - sum(row), SHAPE_DP)
    return {
        "ac_monthly": [round(float(x), 3) for x in ac_monthly],
        "ac_annual": round(float(sum(ac_monthly)), 2),
        "intraday_shape": shape,
    }


def _sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode("utf-8")).hexdigest()


def _snapshot(site_key: str, raw: dict, raw_sha: str) -> None:
    """Committed, trimmed raw: everything except the bulky non-AC hourly arrays."""
    keep = {"ac", "ac_monthly", "ac_annual", "solrad_monthly", "poa_monthly", "dc_monthly",
            "capacity_factor", "solrad_annual"}
    trimmed = {k: v for k, v in raw.items() if k != "outputs"}
    trimmed["outputs"] = {k: v for k, v in raw["outputs"].items() if k in keep}
    trimmed["_full_response_sha256"] = raw_sha
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    (SNAPSHOTS / (site_key.split(":", 1)[1] + ".json")).write_text(
        json.dumps(trimmed, separators=(",", ":")), encoding="utf-8")


# ── Merge + write ────────────────────────────────────────────────────────────────
def load_existing() -> dict:
    if OUT_JSON.exists():
        return json.loads(OUT_JSON.read_text(encoding="utf-8"))
    return {"_meta": {}, "sites": {}, "zips": {}, "zones": {}, "default": {}}


def write(doc: dict) -> None:
    SOLAR.mkdir(parents=True, exist_ok=True)
    # compact sites (bulky shapes), readable top level
    body = ",\n".join(f"{json.dumps(k)}: {json.dumps(v, separators=(',', ':'), sort_keys=True)}"
                      for k, v in doc.items())
    OUT_JSON.write_text("{\n" + body + "\n}\n", encoding="utf-8")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")          # Windows console: allow → in help/labels
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--region", required=True, choices=sorted(SR.REGIONS))
    ap.add_argument("--api-key", default=None)
    args = ap.parse_args()
    region = SR.REGIONS[args.region]
    api_key, key_source = resolve_api_key(args.api_key)
    print(f"region={region.tag} (wave {region.wave})  key from {key_source}")

    doc = load_existing()
    sites = region_sites(region.tag)
    last_call = [0.0]
    fetched = cached = 0
    for s in sites:
        raw, from_cache = fetch_site(s, api_key, last_call)
        cached += from_cache
        fetched += not from_cache
        raw_sha = _sha256(raw)
        red = reduce_hourly(raw)
        st = raw.get("station_info", {})
        doc["sites"][s["site_key"]] = {
            "label": s["label"], "lat": s["lat"], "lon": s["lon"], "zone": s["zone"],
            "nsrdb_station": {k: st.get(k) for k in ("lat", "lon", "elev", "tz", "distance",
                                                      "solar_resource_file")},
            **red, "raw_sha256": raw_sha,
        }
        if region.tag == SR.ZONE_STATIONS_REGION:
            doc["zones"][s["zone"]] = {"site": s["site_key"]}
            _snapshot(s["site_key"], raw, raw_sha)
        else:
            doc["zips"][s["zip"]] = {"zone": s["zone"], "region": region.tag, "site": s["site_key"]}
        print(f"  {s['site_key']:<16} {s['label']:<28} annual {red['ac_annual']:7.1f} kWh/kW"
              f"{'  (cache)' if from_cache else ''}")

    if region.tag == SR.ZONE_STATIONS_REGION:
        doc["default"] = {"zone": SR.DEFAULT_ZONE, "site": f"zone:{SR.DEFAULT_ZONE}"}

    meta = doc["_meta"]
    meta.update({
        "status": "Offline-baked PVWatts v8 solar yield, per 1 kW DC, single default orientation. "
                  "Review-only until Phase 7 (docs/OfflineSolarData_Plan.md).",
        "source": "NREL PVWatts v8 API", "source_url": PVWATTS_URL,
        "request_params": {k: v for k, v in DEFAULT_PARAMS.items()},
        "units": {"ac_monthly": "kWh AC per kW DC per month", "ac_annual": "kWh/kW/yr",
                  "intraday_shape": "fraction of the month's AC energy in each local-standard-time "
                                    "hour 0-23; each month's 24 values sum to 1"},
        "hour_convention": "PVWatts hourly TMY output, local standard time (no DST), non-leap 8760",
        "fallback": "zips[zip] -> zones[zip_to_zone[zip]] -> default; every level is a full table",
        "built": date.today().isoformat(),
    })
    regions_meta = [r for r in meta.get("regions", []) if r["tag"] != region.tag]
    regions_meta.append({"tag": region.tag, "name": region.name, "wave": region.wave,
                         "sites": len(sites), "source": region.source_url,
                         "harvested": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")})
    meta["regions"] = sorted(regions_meta, key=lambda r: (r["wave"], r["tag"]))
    meta["site_count"] = len(doc["sites"])
    write(doc)
    print(f"wrote {OUT_JSON.relative_to(ROOT)}  ({fetched} fetched, {cached} cached, "
          f"{OUT_JSON.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
