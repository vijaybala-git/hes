#!/usr/bin/env python3
"""build_load_profiles.py — offline NREL ResStock end-use load-profile harvest (Phase 7 §6).

→ data/loads/end_use_profiles.json  +  data/loads/sources/manifest.json

See docs/NREL_LoadProfiles_Plan.md. Source: ResStock 2025 Release 1, AMY2018, on the OEDI
data lake (anonymous S3). For each CEC Building Climate Zone this script:
  1. samples N single-family-detached, occupied, successfully-simulated California buildings
     per run (seeded; `in.cec_climate_zone` from the metadata), where a run is the baseline
     (upgrade 0) or one of the ResStock upgrades that installs the device we need
     (4 = ducted ASHP, 9 = HPWH, 22 = managed L2 EV, 20 = unmanaged L2 EV);
  2. reads only the needed 15-min end-use columns of each building (column-subset parquet read),
     shifts the timestamps from NREL's Eastern Standard Time (end-of-interval) to Pacific
     STANDARD time, and reduces them to a (12 month × 24 hour) kWh table per end-use group —
     cached per building under data/loads/.cache/ (git-ignored), so a re-run reads nothing;
  3. sums the kWh over the sample (the stock-aggregate shape) and normalises each month's row
     to 1. A month where an end use is ~0 (heating in August) takes that end use's annual shape.

The file stores local STANDARD time, like data/solar/pvwatts_zip.json; src/load_profiles.py
applies the same month-level daylight-saving shift as the solar loader, so loads and solar
share one clock.

NOTHING here is imported by src/. Needs pyarrow (build-time only).

USAGE (from project root):
    .venv/Scripts/python.exe scripts/build_load_profiles.py            # full build
    .venv/Scripts/python.exe scripts/build_load_profiles.py --dry-run  # sample counts only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).parent.parent
LOADS = ROOT / "data" / "loads"
OUT_JSON = LOADS / "end_use_profiles.json"
MANIFEST = LOADS / "sources" / "manifest.json"
CACHE = LOADS / ".cache"                               # git-ignored

RELEASE = "resstock_amy2018_release_1"
BUCKET = "oedi-data-lake"
PREFIX = f"nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/2025/{RELEASE}"
HTTP = f"https://{BUCKET}.s3.amazonaws.com/{PREFIX}"
META_KEY = "metadata_and_annual_results/by_state/full/csv/state=CA/CA_upgrade{u}.csv.gz"
TS_KEY = "timeseries_individual_buildings/by_state/upgrade={u}/state=CA/{b}-{u}.parquet"

SCHEMA_VERSION = 1            # bump on any breaking change; src/load_profiles.py checks it
SHAPE_DP = 5
TZ_SHIFT_H = -3               # NREL timestamps are EST (UTC−5) → PST (UTC−8)
MIN_MONTH_SHARE = 0.002       # a month below this share of the annual kWh → annual shape
MIN_BUILDINGS = 30            # an end use with fewer contributing buildings in a zone → statewide
ZONES = [str(z) for z in range(1, 17)]

_E = "out.electricity.{}.energy_consumption..kwh".format
# end-use group → (run upgrade, NREL end-use columns, metadata filter on the baseline home)
GROUPS: dict[str, tuple[int, list[str], tuple[str, str] | None]] = {
    "lights_plugs":  (0, [_E(c) for c in (
        "lighting_interior", "lighting_exterior", "lighting_garage", "plug_loads", "television",
        "refrigerator", "freezer", "ceiling_fan", "clothes_washer")], None),
    "cooking":       (0, [_E("range_oven")], ("in.cooking_range", "Electric")),
    "clothes_dryer": (0, [_E("clothes_dryer")], ("in.clothes_dryer", "Electric")),
    "dishwasher":    (0, [_E("dishwasher")], None),
    "hvac_heating":  (4, [_E(c) for c in ("heating", "heating_fans_pumps", "heating_hp_bkup")], None),
    "hvac_cooling":  (4, [_E(c) for c in ("cooling", "cooling_fans_pumps")], None),
    "water_heating": (9, [_E("hot_water")], None),
    "ev_managed":    (22, [_E("ev_charging")], None),
    "ev_unmanaged":  (20, [_E("ev_charging")], None),
}
RUNS = sorted({g[0] for g in GROUPS.values()})
RUN_NAMES = {0: "Baseline", 4: "Typical Cold Climate Ducted Air Source Heat Pump",
             9: "Heat Pumps Water Heater", 20: "Electric Vehicle Adoption with Level 2 Charging",
             22: "Electric Vehicle Adoption with Level 2 Charging and Demand Flexibility"}

CITATION = ("Parker, A., et al. (2025). ResStock 2025 Release 1 [Dataset]. Open Energy Data "
            "Initiative (OEDI). National Laboratory of the Rockies (NLR).")
ATTRIBUTION = ("Data includes information from the ResStock™ dataset developed by the National "
               "Laboratory of the Rockies (NLR) with funding from the U.S. Department of Energy (DOE).")


# ── metadata ────────────────────────────────────────────────────────────────────
def _fetch(url: str, dest: Path) -> Path:
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            tmp = dest.with_suffix(dest.suffix + ".part")
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
            tmp.replace(dest)
    return dest


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_metadata(u: int) -> pd.DataFrame:
    """CA metadata for run `u`, indexed by bldg_id. The baseline carries the home filters."""
    p = _fetch(f"{HTTP}/{META_KEY.format(u=u)}", CACHE / "meta" / f"CA_upgrade{u}.csv.gz")
    want = {"completed_status", "applicability", "in.cec_climate_zone",
            "in.geometry_building_type_recs", "in.vacancy_status",
            "in.cooking_range", "in.clothes_dryer"}
    df = pd.read_csv(p, usecols=lambda c: c in want or c.startswith("CA_upgrade") or c == "bldg_id",
                     low_memory=False)
    id_col = "bldg_id" if "bldg_id" in df else df.columns[0]   # the CSV's first header is mangled
    df["bldg_id"] = pd.to_numeric(df[id_col], errors="coerce")
    df = df.dropna(subset=["bldg_id"]).astype({"bldg_id": int}).set_index("bldg_id")
    return df


def eligible(base: pd.DataFrame, run_meta: pd.DataFrame) -> pd.DataFrame:
    """Baseline homes (SFD, occupied, simulated OK) where run `u` applied and succeeded."""
    b = base[(base["in.geometry_building_type_recs"] == "Single-Family Detached")
             & (base["in.vacancy_status"] == "Occupied")
             & (base["completed_status"] == "Success")]
    ok = run_meta["completed_status"] == "Success"
    if "applicability" in run_meta:
        ok &= run_meta["applicability"].astype(str).str.lower() == "true"
    b = b[b.index.isin(run_meta.index[ok])]
    b = b.assign(zone=pd.to_numeric(b["in.cec_climate_zone"], errors="coerce"))
    b = b.dropna(subset=["zone"])
    return b.assign(zone=b["zone"].astype(int).astype(str))


def sample(elig: pd.DataFrame, n: int, seed: int) -> dict[str, list[int]]:
    out = {}
    for z in ZONES:
        ids = np.sort(elig.index[elig["zone"] == z].to_numpy())
        rng = np.random.default_rng([seed, int(z)])
        out[z] = sorted(int(i) for i in (ids if len(ids) <= n else rng.choice(ids, n, replace=False)))
    return out


# ── timeseries ──────────────────────────────────────────────────────────────────
_FS = None


def _fs():
    global _FS
    if _FS is None:
        import pyarrow.fs as pafs
        _FS = pafs.S3FileSystem(anonymous=True, region="us-west-2")
    return _FS


def reduce_building(u: int, b: int) -> dict:
    """{group: (12,24) kWh in PST} for building b in run u — cached."""
    cache = CACHE / f"up{u:02d}" / f"{b}.npz"
    groups = [g for g, (run, _, _) in GROUPS.items() if run == u]
    if cache.exists():
        z = np.load(cache)
        return {"tables": {g: z[g] for g in groups}, "etag": str(z["_etag"]), "size": int(z["_size"])}
    import pyarrow.parquet as pq
    key = TS_KEY.format(u=u, b=b)
    cols = sorted({c for g in groups for c in GROUPS[g][1]})
    pf = pq.ParquetFile(f"{BUCKET}/{PREFIX}/{key}", filesystem=_fs())
    present = [c for c in cols if c in pf.schema_arrow.names]
    t = pf.read(columns=["timestamp", *present]).to_pandas()
    start = t["timestamp"] - pd.Timedelta(minutes=15) + pd.Timedelta(hours=TZ_SHIFT_H)
    mo = start.dt.month.to_numpy() - 1
    hr = start.dt.hour.to_numpy()
    idx = mo * 24 + hr
    tables = {}
    for g in groups:
        v = sum((t[c].to_numpy(dtype=float) for c in GROUPS[g][1] if c in present),
                np.zeros(len(t)))
        tables[g] = np.bincount(idx, weights=v, minlength=288).reshape(12, 24)
    head = requests.head(f"{HTTP}/{key}", timeout=60)
    head.raise_for_status()
    etag, size = head.headers.get("ETag", "").strip('"'), int(head.headers.get("Content-Length", 0))
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez(cache, _etag=etag, _size=size, **tables)
    return {"tables": tables, "etag": etag, "size": size}


def reduce_with_retry(u: int, b: int, tries: int = 5) -> dict:
    """reduce_building, retrying transient network errors (S3 connection resets)."""
    for i in range(tries):
        try:
            return reduce_building(u, b)
        except (OSError, requests.RequestException):
            if i == tries - 1:
                raise
            time.sleep(2 ** i)


def harvest(samples: dict[int, dict[str, list[int]]], workers: int) -> dict:
    jobs = [(u, b) for u, per_zone in samples.items() for ids in per_zone.values() for b in ids]
    results, t0 = {}, time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(reduce_with_retry, u, b): (u, b) for u, b in jobs}
        for i, f in enumerate(as_completed(futs), 1):
            results[futs[f]] = f.result()
            if i % 250 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)} buildings  ({time.time() - t0:.0f}s)", flush=True)
    return results


# ── aggregation ─────────────────────────────────────────────────────────────────
def normalise(kwh: np.ndarray) -> tuple[np.ndarray, list[int]]:
    """(12,24) kWh → rows summing to 1; near-empty months take the annual shape."""
    annual = kwh.sum(axis=0)
    annual = annual / annual.sum()
    tot = kwh.sum()
    out, fallback = np.empty_like(kwh), []
    for m in range(12):
        if kwh[m].sum() < MIN_MONTH_SHARE * tot:
            out[m] = annual
            fallback.append(m + 1)
        else:
            out[m] = kwh[m] / kwh[m].sum()
    return out, fallback


def aggregate(samples, base, results) -> tuple[dict, dict]:
    profiles, notes = {}, {}
    pooled: dict[str, np.ndarray] = {}
    per_zone: dict[tuple[str, str], tuple[np.ndarray, int]] = {}
    for g, (u, _, filt) in GROUPS.items():
        pooled[g] = np.zeros((12, 24))
        for z in ZONES:
            ids = samples[u][z]
            if filt:
                col, prefix = filt
                ids = [b for b in ids if str(base.at[b, col]).startswith(prefix)]
            acc = np.zeros((12, 24))
            for b in ids:
                acc += results[(u, b)]["tables"][g]
            per_zone[(g, z)] = (acc, len(ids))
            pooled[g] += acc
    for z in ZONES:
        zone_key = f"CA_CZ{z}"
        profiles[zone_key] = {}
        for g in GROUPS:
            acc, n = per_zone[(g, z)]
            src = "zone"
            if n < MIN_BUILDINGS or acc.sum() <= 0:
                acc, src = pooled[g], "statewide"
            shape, fb = normalise(acc)
            profiles[zone_key][g] = np.round(shape, SHAPE_DP).tolist()
            notes.setdefault(zone_key, {})[g] = {"buildings": n, "source": src,
                                                 "annual_shape_months": fb}
    return profiles, notes


# ── main ────────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, default=150, help="buildings per zone per run")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--dry-run", action="store_true", help="print sample counts; read no timeseries")
    a = ap.parse_args()

    print("metadata …")
    metas = {u: load_metadata(u) for u in RUNS}
    base = metas[0]
    samples = {u: sample(eligible(base, metas[u]), a.n, a.seed) for u in RUNS}
    for u in RUNS:
        print(f"  upgrade {u:>2}: " + " ".join(f"{z}:{len(samples[u][z])}" for z in ZONES))
    if a.dry_run:
        return 0

    print(f"timeseries ({RELEASE}) …")
    results = harvest(samples, a.workers)
    profiles, notes = aggregate(samples, base, results)

    built = date.today().isoformat()
    out = {
        "_meta": {
            "schema_version": SCHEMA_VERSION,
            "description": ("Hourly end-use load shapes per CEC Building Climate Zone: "
                            "{zone: {end_use: 12 months × 24 hours}}, each month's row sums to 1. "
                            "Hours are local STANDARD time (hour h = h:00–h:59 PST); the loader "
                            "applies daylight saving (Mar–Oct +1 h), like the PVWatts data."),
            "source": f"NREL/NLR ResStock 2025 Release 1 (AMY2018), {HTTP}/",
            "citation": CITATION,
            "attribution": ATTRIBUTION,
            "sample": (f"single-family detached, occupied, completed_status=Success; seeded random "
                       f"{a.n} per zone per run (seed {a.seed}); kWh summed over the sample"),
            "runs": {str(u): RUN_NAMES[u] for u in RUNS},
            "end_uses": {g: {"run": u, "columns": cols, "filter": filt}
                         for g, (u, cols, filt) in GROUPS.items()},
            "timestamps": ("source is end-of-interval Eastern Standard Time (UTC−5); shifted "
                           f"{TZ_SHIFT_H} h to PST, verified by the CA rooftop-PV and lighting peaks"),
            "fallbacks": {"annual_shape_below_month_share": MIN_MONTH_SHARE,
                          "statewide_below_buildings": MIN_BUILDINGS},
            "built": built,
            "builder": "scripts/build_load_profiles.py",
            "notes": notes,
        },
        "profiles": profiles,
    }
    LOADS.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    manifest = {
        "release": RELEASE, "bucket": BUCKET, "prefix": PREFIX, "built": built,
        "retrieved_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ"),
        "metadata": {f"upgrade{u}": {"key": META_KEY.format(u=u),
                                     "sha256": _sha256(CACHE / "meta" / f"CA_upgrade{u}.csv.gz")}
                     for u in RUNS},
        "columns_read": sorted({c for _, cols, _ in GROUPS.values() for c in cols}),
        "tz_shift_hours": TZ_SHIFT_H,
        "buildings": {str(u): {z: [[b, results[(u, b)]["etag"], results[(u, b)]["size"]]
                                   for b in samples[u][z]] for z in ZONES} for u in RUNS},
        "buildings_format": "[bldg_id, S3 ETag, bytes] — key = "
                            + TS_KEY.replace("{u}", "<run>").replace("{b}", "<bldg_id>"),
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=0) + "\n", encoding="utf-8")
    print(f"wrote {OUT_JSON.relative_to(ROOT)} and {MANIFEST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
