"""Validation gate for the offline PVWatts harvest (docs/OfflineSolarData_Plan.md §5).

Reads only the committed data/solar/pvwatts_zip.json — no network, no src/ imports.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parent.parent
PV_JSON = ROOT / "data" / "solar" / "pvwatts_zip.json"
ZIP_TO_ZONE = ROOT / "data" / "climate" / "zip_to_zone.json"
ZONES_JSON = ROOT / "data" / "climate" / "tmy3_zones.json"
REGIONS_JSON = ROOT / "data" / "solar" / "regions.json"
SIZE_BUDGET_BYTES = 3 * 1024 * 1024
NIGHT_HOURS = [0, 1, 2, 3, 22, 23]          # local standard time; no CA sun at these hours

sys.path.insert(0, str(ROOT / "scripts"))
import solar_regions as SR  # noqa: E402

pytestmark = pytest.mark.skipif(not PV_JSON.exists(), reason="pvwatts_zip.json not harvested yet")


@pytest.fixture(scope="module")
def pv():
    return json.loads(PV_JSON.read_text(encoding="utf-8"))


def _resolve(pv, zip_to_zone, zip_code):
    """ZIP → zone station → default; every level a site with a full table."""
    if zip_code in pv["zips"]:
        return pv["zips"][zip_code]["site"]
    zone = zip_to_zone.get(zip_code)
    if zone in pv["zones"]:
        return pv["zones"][zone]["site"]
    return pv["default"]["site"]


def test_all_zone_stations_and_default_present(pv):
    zones = {z for z in json.loads(ZONES_JSON.read_text(encoding="utf-8")) if not z.startswith("_")}
    assert set(pv["zones"]) == zones
    assert pv["default"]["zone"] == SR.DEFAULT_ZONE
    for ref in [*pv["zones"].values(), pv["default"]]:
        assert ref["site"] in pv["sites"]


def test_every_ca_zip_resolves_to_a_table(pv):
    zip_to_zone = {k: v for k, v in json.loads(ZIP_TO_ZONE.read_text(encoding="utf-8")).items()
                   if not k.startswith("_")}
    for z in [*zip_to_zone, "00000"]:                      # plus an unknown ZIP → default
        site = pv["sites"][_resolve(pv, zip_to_zone, z)]
        assert len(site["ac_monthly"]) == 12 and len(site["intraday_shape"]) == 12


def test_harvested_regions_are_complete(pv):
    """Every ZIP a harvested region lists (data/solar/regions.json) has a direct ZIP-level table."""
    regions = json.loads(REGIONS_JSON.read_text(encoding="utf-8")) if REGIONS_JSON.exists() else {}
    for r in pv["_meta"]["regions"]:
        if r["tag"] == SR.ZONE_STATIONS_REGION:
            continue
        listed = regions[r["tag"]]["zips"]
        assert listed, r["tag"]
        for z in listed:
            assert z in pv["zips"], f"{r['tag']}: ZIP {z} missing"
            assert pv["zips"][z]["region"] == r["tag"]


def test_zip_entries_consistent(pv):
    zip_to_zone = json.loads(ZIP_TO_ZONE.read_text(encoding="utf-8"))
    for z, e in pv["zips"].items():
        assert e["zone"] == zip_to_zone[z], z
        assert e["site"] in pv["sites"], z


@pytest.mark.parametrize("field", ["ac_monthly", "intraday_shape"])
def test_shapes(pv, field):
    for key, s in pv["sites"].items():
        arr = np.asarray(s[field])
        assert arr.shape == ((12,) if field == "ac_monthly" else (12, 24)), key


def test_monthly_yield_plausible(pv):
    for key, s in pv["sites"].items():
        m = np.asarray(s["ac_monthly"])
        assert (m > 0).all(), key
        assert int(np.argmax(m)) in range(3, 9), f"{key}: peak month {np.argmax(m) + 1}"  # Apr–Sep
        assert m.sum() == pytest.approx(s["ac_annual"], abs=0.1), key
        assert 1_150 <= s["ac_annual"] <= 1_900, f"{key}: {s['ac_annual']} kWh/kW/yr"


def test_intraday_shape_normalized_and_dark_at_night(pv):
    for key, s in pv["sites"].items():
        sh = np.asarray(s["intraday_shape"])
        assert np.allclose(sh.sum(axis=1), 1.0, atol=1e-6), key
        assert (sh >= 0).all(), key
        assert sh[:, NIGHT_HOURS].max() < 1e-3, key
        assert int(np.argmax(sh.mean(axis=0))) in range(10, 15), key   # solar noon-ish


def test_cz4_continuity_with_retired_scalar(pv):
    """CZ4 default table sits in a band around the retired specific_yield=1500.

    Wave 0 measured 1,644 (+9.6%): the old scalar under-stated San José at the default orientation.
    """
    annual = pv["sites"][pv["default"]["site"]]["ac_annual"]
    assert 1_500 <= annual <= 1_750


def test_north_coast_lowest_desert_highest(pv):
    """Robust geographic ordering. (Not bay-vs-Central-Valley: Oakland ≈ Sacramento — tule fog.)"""
    zones = {z: pv["sites"][r["site"]]["ac_annual"] for z, r in pv["zones"].items()}
    ranked = sorted(zones, key=zones.get)
    assert ranked[0] == "CA_CZ1"                                   # Arcata — north-coast fog
    assert set(ranked[-2:]) == {"CA_CZ14", "CA_CZ15"}              # China Lake, El Centro — desert


def test_provenance(pv):
    meta = pv["_meta"]
    assert meta["request_params"]["system_capacity"] == 1
    assert meta["request_params"]["timeframe"] == "hourly"
    for key, s in pv["sites"].items():
        assert len(s["raw_sha256"]) == 64, key


def test_size_budget():
    assert PV_JSON.stat().st_size <= SIZE_BUDGET_BYTES
