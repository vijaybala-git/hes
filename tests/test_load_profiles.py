"""NREL ResStock end-use load profiles (Phase 7 §6) — data file, loader, and energy-balance wiring."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from load_profiles import (DEVICE_END_USE, HP_COOLING, HP_HEATING, LoadProfileLoader,  # noqa: E402
                           get_loader)
from solar_loader import DST_MONTHS  # noqa: E402

DOC = json.loads((ROOT / "data/loads/end_use_profiles.json").read_text(encoding="utf-8"))
ZONES = [f"CA_CZ{z}" for z in range(1, 17)]
PEAK = np.zeros(24, bool)
PEAK[16:21] = True                     # 4–9 pm clock time (PG&E E-TOU-C)
JAN, JUL = 0, 6


# ── the committed file ────────────────────────────────────────────────────────
def test_file_has_every_zone_and_end_use():
    uses = set(DEVICE_END_USE.values())
    assert set(DOC["profiles"]) == set(ZONES)
    for z in ZONES:
        assert uses <= set(DOC["profiles"][z]), z


@pytest.mark.parametrize("zone", ZONES)
def test_every_row_sums_to_one(zone):
    for name, rows in DOC["profiles"][zone].items():
        a = np.asarray(rows)
        assert a.shape == (12, 24), name
        assert (a >= 0).all(), name
        np.testing.assert_allclose(a.sum(axis=1), 1.0, atol=1e-3, err_msg=f"{zone}/{name}")


def test_provenance_is_recorded():
    meta = DOC["_meta"]
    assert meta["schema_version"] == 1
    assert "ResStock 2025 Release 1" in meta["source"]
    assert "National Laboratory of the Rockies" in meta["attribution"]
    man = json.loads((ROOT / "data/loads/sources/manifest.json").read_text(encoding="utf-8"))
    assert man["tz_shift_hours"] == -3
    assert all(len(v["sha256"]) == 64 for v in man["metadata"].values())
    n = sum(len(ids) for run in man["buildings"].values() for ids in run.values())
    assert n > 5000


# ── the loader (clock time) ───────────────────────────────────────────────────
def test_zip_resolves_to_its_zone_and_unknown_zip_to_cz4():
    ld = get_loader()
    assert ld.resolve("95112").zone_key == "CA_CZ4"
    assert ld.resolve("92262").zone_key == "CA_CZ15"          # Palm Springs
    bad = ld.resolve("00000")
    assert bad.zone_key == "CA_CZ4" and bad.level == "default"


def test_every_device_class_resolves_in_every_zone():
    ld = get_loader()
    for z in ZONES:
        lp = ld.for_zone(z)
        for key in [*DEVICE_END_USE, "SomeFutureDevice"]:
            for m in range(12):
                s = lp.shape(key, m)
                assert s.shape == (24,)
                assert abs(s.sum() - 1.0) < 1e-9


def test_loader_shifts_to_clock_time_in_dst_months():
    lp = get_loader().for_zone("CA_CZ4")
    raw = np.asarray(DOC["profiles"]["CA_CZ4"]["lights_plugs"])
    for m in range(12):
        expect = np.roll(raw[m], 1) if DST_MONTHS[m] else raw[m]
        np.testing.assert_allclose(lp.shape("LightsAndPlugs", m), expect / expect.sum(), atol=1e-12)


def test_loader_rejects_a_bad_schema(tmp_path):
    bad = dict(DOC, _meta=dict(DOC["_meta"], schema_version=99))
    f = tmp_path / "p.json"
    f.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version"):
        LoadProfileLoader(profile_file=f)


# ── the shapes are physically sensible (spec §6 validation) ───────────────────
@pytest.mark.parametrize("zone", ZONES)
def test_everyday_load_is_evening_heavy(zone):
    """Lights & plugs put more than the flat 5/24 (21 %) into 4–9 pm."""
    lp = get_loader().for_zone(zone)
    for m in range(12):
        assert lp.shape("LightsAndPlugs", m)[PEAK].sum() > 5 / 24 + 0.02


def test_lighting_evening_peak_is_in_the_evening_clock_time():
    """Guards the EST→PST shift: the everyday-load peak falls between 18:00 and 22:00 clock."""
    lp = get_loader().for_zone("CA_CZ4")
    for m in (JAN, JUL):
        assert 18 <= int(np.argmax(lp.shape("LightsAndPlugs", m))) <= 22


@pytest.mark.parametrize("zone", ["CA_CZ4", "CA_CZ10", "CA_CZ12", "CA_CZ13", "CA_CZ15"])
def test_summer_cooling_peaks_in_the_afternoon(zone):
    s = get_loader().for_zone(zone).shape(HP_COOLING, JUL)
    assert 13 <= int(np.argmax(s)) <= 19
    assert s[13:20].sum() > s[0:7].sum()


def test_winter_heating_is_not_an_afternoon_load():
    s = get_loader().for_zone("CA_CZ4").shape(HP_HEATING, JAN)
    assert s[5:10].sum() > s[12:17].sum()          # morning warm-up beats mid-afternoon


def test_managed_ev_avoids_the_peak_more_than_unmanaged():
    lp = get_loader().for_zone("CA_CZ4")
    managed = lp.end_uses["ev_managed"][JUL][PEAK].sum()
    unmanaged = lp.end_uses["ev_unmanaged"][JUL][PEAK].sum()
    assert managed < unmanaged


def test_heat_pump_blend_is_the_energy_weighted_mix():
    lp = get_loader().for_zone("CA_CZ4")
    b = lp.heat_pump_shape(JUL, 0.25)
    np.testing.assert_allclose(b, 0.25 * lp.shape(HP_HEATING, JUL) + 0.75 * lp.shape(HP_COOLING, JUL))
    assert abs(b.sum() - 1) < 1e-9


# ── wiring: the energy balance uses the zone's shapes and the heat-pump split ──
def test_heat_pump_is_split_into_heating_and_cooling_parts():
    from journey import _load_parts

    class HeatPumpHVAC:                             # stand-in with the device's interface
        def monthly_heating(self):
            return np.array([300.0] * 3 + [0.0] * 6 + [300.0] * 3)

        def monthly_cooling(self):
            return np.array([0.0] * 5 + [100.0] * 3 + [0.0] * 4)

    home = np.full(12, 90.0)
    parts = dict(_load_parts(HeatPumpHVAC(), home))
    assert set(parts) == {HP_HEATING, HP_COOLING}
    np.testing.assert_allclose(parts[HP_HEATING] + parts[HP_COOLING], home)
    assert parts[HP_COOLING][JUL] == 90 and parts[HP_HEATING][JAN] == 90


def test_model_energy_balance_closes_with_nrel_shapes():
    from home_config import HomeConfig
    from model import HESModel

    m = HESModel(home_config=HomeConfig(zip_code="95112"), n_years=3)
    assert m.load_profiles.zone_key == "CA_CZ4"
    for _ in range(3):
        m.step()
    home = m.journey_home
    loads = home.home_load_hourly_history[-1]
    if loads is not None:
        days = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
        total = float((np.asarray(loads).sum(axis=1) * days).sum())
        assert total == pytest.approx(float(np.sum(home.home_elec_kwh_monthly_history[-1])), rel=1e-6)
