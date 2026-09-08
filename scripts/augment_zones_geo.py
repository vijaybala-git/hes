"""scripts/augment_zones_geo.py — Phase 6 WS2 §2b + WS3 §3e climate-DB augmentation.

Adds two inert, display-only blocks to each CEC zone in data/climate/tmy3_zones.json, read
straight from the committed TMYx EPW headers (the same station files build_climate_db.py used):

  §2b  latitude / longitude          — LOCATION header (canonical PVWatts site geometry)
  §3e  heating_design_temp_f / cooling_design_temp_f
                                      — DESIGN CONDITIONS header (ASHRAE 99% heating / 1% cooling
                                        dry-bulb), for the auto-sized HVAC tonnage label

This is a ONE-OFF augmentation, NOT a rebuild: it only ADDS keys and never touches the HDD/CDD /
water / UA numbers, so the simulation output is unchanged (golden-safe by construction). It
asserts the HDD/CDD payload is byte-identical before/after. Re-runnable (idempotent).

Usage:  python scripts/augment_zones_geo.py
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ZONES = REPO / "data" / "climate" / "tmy3_zones.json"
TMYX_DIR = REPO / "data" / "climate" / "sources" / "tmyx"

# Keys this script owns (added/overwritten); everything else is preserved untouched.
_ADDED = ("latitude", "longitude", "heating_design_temp_f", "cooling_design_temp_f")
# HDD/CDD/water keys that MUST be identical before and after (the golden-safety invariant).
_FROZEN = ("annual_hdd_65f", "annual_cdd_65f", "monthly_hdd_65f", "monthly_cdd_65f",
           "monthly_inlet_water_f", "monthly_avg_temp_f")


def _c_to_f(c: float) -> float:
    return round(c * 9.0 / 5.0 + 32.0, 1)


def _read_epw_header(zip_path: Path) -> tuple[float, float, float, float]:
    """Return (lat, lon, heating_99pct_db_f, cooling_1pct_db_f) from an EPW's first two lines."""
    with zipfile.ZipFile(zip_path) as zf:
        epw = next(n for n in zf.namelist() if n.lower().endswith(".epw"))
        with zf.open(epw) as f:
            text = io.TextIOWrapper(f, encoding="latin-1")
            loc = text.readline().strip().split(",")
            design = text.readline().strip().split(",")

    lat, lon = float(loc[6]), float(loc[7])

    # DESIGN CONDITIONS record (ASHRAE HOF). Heating block: after 'Heating' → [coldest_month,
    # 99.6% DB, 99% DB, ...]; Cooling block: after 'Cooling' → [hottest_month, DB_range,
    # 0.4% DB, 0.4% MCWB, 1% DB, ...]. We take heating 99% DB and cooling 1% DB.
    h = design.index("Heating")
    c = design.index("Cooling")
    heating_99_c = float(design[h + 3])
    cooling_1_c = float(design[c + 5])
    return lat, lon, _c_to_f(heating_99_c), _c_to_f(cooling_1_c)


def main():
    data = json.loads(ZONES.read_text(encoding="utf-8"))
    frozen_before = {z: {k: data[z].get(k) for k in _FROZEN}
                     for z in data if z.startswith("CA_CZ")}

    n = 0
    for zone, entry in data.items():
        if not zone.startswith("CA_CZ"):
            continue
        zip_name = Path(entry["source_zip"]).name
        zip_path = TMYX_DIR / zip_name
        if not zip_path.exists():
            raise FileNotFoundError(f"{zone}: EPW source missing: {zip_path}")
        lat, lon, heat_f, cool_f = _read_epw_header(zip_path)
        entry["latitude"] = lat
        entry["longitude"] = lon
        entry["heating_design_temp_f"] = heat_f
        entry["cooling_design_temp_f"] = cool_f
        n += 1

    # Golden-safety invariant: HDD/CDD/water payload unchanged.
    frozen_after = {z: {k: data[z].get(k) for k in _FROZEN}
                    for z in data if z.startswith("CA_CZ")}
    assert frozen_before == frozen_after, "HDD/CDD payload changed — augmentation must be additive!"

    meta = data.get("_meta", {})
    meta["geo_augmentation"] = {
        "added_keys": list(_ADDED),
        "source": "TMYx EPW LOCATION + DESIGN CONDITIONS headers (ASHRAE 99% heating / 1% cooling DB)",
        "note": ("Inert display-only fields (Phase 6 WS2 §2b lat/lon for PVWatts; WS3 §3e design "
                 "temps for the HVAC tonnage label). No device reads them; HDD/CDD untouched."),
    }
    data["_meta"] = meta

    ZONES.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"augmented {n} zones with {_ADDED} (HDD/CDD unchanged)")
    cz4 = data["CA_CZ4"]
    print(f"  CZ4 check: lat={cz4['latitude']} lon={cz4['longitude']} "
          f"heat={cz4['heating_design_temp_f']}F cool={cz4['cooling_design_temp_f']}F")


if __name__ == "__main__":
    main()
