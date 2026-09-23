"""SolarResourceLoader / HomeConfig.solar_resource / model wiring (Phase 7 §1, commit A)."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from solar_loader import (SolarResourceLoader, get_loader, to_clock_time,  # noqa: E402
                          DST_MONTHS, SCHEMA_VERSION)
from home_config import HomeConfig  # noqa: E402

PV_JSON = ROOT / "data" / "solar" / "pvwatts_zip.json"
PV = json.loads(PV_JSON.read_text(encoding="utf-8"))


# ── Resolution order: ZIP → zone → default ────────────────────────────────────

def test_zip_level_table():
    r = get_loader().resolve("94040")                      # SVCE, harvested
    assert r.level == "zip" and not r.is_fallback
    assert r.site_key == "zip:94040" and r.zone_key == "CA_CZ4"
    assert r.ac_annual == pytest.approx(PV["sites"]["zip:94040"]["ac_annual"], abs=0.01)
    assert "ZIP 94040" in r.label


def test_zone_fallback_for_unharvested_zip():
    r = get_loader().resolve("90001")                      # LA — CZ8, not harvested yet
    assert r.level == "zone" and r.is_fallback
    assert r.site_key == "zone:CA_CZ8"
    assert "CZ8 zone estimate" in r.label


def test_default_for_unknown_zip():
    r = get_loader().resolve("73301")                      # Austin, TX — out of state
    assert r.level == "default"
    assert r.site_key == PV["default"]["site"] and r.zone_key == "CA_CZ4"


def test_whitespace_and_caching():
    ld = get_loader()
    assert ld.resolve(" 94040 ") is ld.resolve("94040")


# ── Clock time ────────────────────────────────────────────────────────────────

def test_clock_time_shift_preserves_rows_and_moves_dst_months():
    lst = np.array(PV["sites"]["zip:94040"]["intraday_shape"])
    clk = get_loader().resolve("94040").intraday_shape
    assert np.allclose(clk.sum(axis=1), lst.sum(axis=1))
    hours = np.arange(24)
    for m in range(12):
        centroid_shift = (clk[m] * hours).sum() - (lst[m] * hours).sum()
        assert centroid_shift == pytest.approx(1.0 if DST_MONTHS[m] else 0.0, abs=1e-6), m
    assert np.allclose(to_clock_time(lst)[0], lst[0])     # January untouched
    assert np.allclose(to_clock_time(lst)[6], np.roll(lst[6], 1))  # July +1 h


def test_resource_arrays_are_read_only():
    r = get_loader().resolve("94040")
    with pytest.raises(ValueError):
        r.ac_monthly[0] = 0.0
    with pytest.raises(ValueError):
        r.intraday_shape[0, 12] = 0.0


# ── File contract ─────────────────────────────────────────────────────────────

def test_schema_version_gate(tmp_path):
    bad = dict(PV, _meta=dict(PV["_meta"], schema_version=SCHEMA_VERSION + 1))
    f = tmp_path / "pv.json"
    f.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version"):
        SolarResourceLoader(solar_file=f)


def test_missing_file_is_a_hard_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        SolarResourceLoader(solar_file=tmp_path / "nope.json")


# ── HomeConfig + model wiring ─────────────────────────────────────────────────

def test_home_config_property_tracks_zip_and_is_not_a_field():
    from dataclasses import asdict
    hc = HomeConfig(zip_code="94040")
    assert hc.solar_resource.level == "zip"
    hc.zip_code = "90001"
    assert hc.solar_resource.zone_key == "CA_CZ8"
    assert "solar_resource" not in asdict(hc)              # never persisted / shared


def _solar_run(zip_code, panels=10):
    from journey import CapExOnlySlot, SolarBatteryConfig
    from model import HESModel
    slot = CapExOnlySlot(name="Solar + Battery", install_cost=0, install_year=1)
    cfg = SolarBatteryConfig(panels=panels, kw_per_panel=0.40)
    m = HESModel(home_config=HomeConfig(zip_code=zip_code), n_years=3,
                 solar_config=cfg, capex_only_slots=[slot])
    m.run_all()
    return m, cfg


def test_production_is_system_kw_times_zip_table():
    m, cfg = _solar_run("95140")
    expected = cfg.system_kw * m.solar_resource.ac_annual
    assert m.journey_home.solar_production_kwh_history[0] == pytest.approx(expected)


def test_two_zips_same_zone_give_different_solar():
    """95112 (CZ4 zone table) vs 95140 (ZIP table, +6.6%): same utility + climate, only solar moves."""
    a, _ = _solar_run("95112", panels=2)   # small system: stays under the elec-bill cap
    b, _ = _solar_run("95140", panels=2)
    pa = a.journey_home.solar_production_kwh_history[0]
    pb = b.journey_home.solar_production_kwh_history[0]
    assert pb / pa == pytest.approx(1752 / 1644, rel=0.01)
    assert b.journey_home.solar_savings_history[0] > a.journey_home.solar_savings_history[0]


def test_solar_config_without_resource_is_rejected():
    import mesa
    from journey import JourneyHome, SolarBatteryConfig
    with pytest.raises(ValueError, match="solar_resource"):
        JourneyHome(mesa.Model(), [], np.zeros((1, 12)), np.zeros((1, 12)),
                    solar_config=SolarBatteryConfig())


def test_no_scalar_yield_left():
    """The retired scalar must not come back (Phase 7 §1 validation)."""
    out = subprocess.run(["git", "grep", "-n", "specific_yield", "--", "src/", "data/"],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.stdout.strip() == "", out.stdout


# ── Commit B: monthly pricing ─────────────────────────────────────────────────

def test_solar_is_priced_month_by_month():
    """Savings = Σ_m self[m]·retail[m] + Σ_m export[m]·export_rate[m] — not annual averages.

    Today's rate models are flat within a year, so the golden barely moves; this test forces a
    seasonal retail curve (summer-high) to prove the monthly weighting is actually applied."""
    from journey import CapExOnlySlot, SolarBatteryConfig, interim_scf
    from model import HESModel
    cfg = SolarBatteryConfig(panels=2, kw_per_panel=0.40)            # small: stays under the cap
    m = HESModel(home_config=HomeConfig(zip_code="95140"), n_years=2, solar_config=cfg,
                 capex_only_slots=[CapExOnlySlot(name="Solar + Battery", install_cost=0,
                                                 install_year=1)])
    seasonal = np.array([0.30] * 5 + [0.60] * 4 + [0.30] * 3)       # Jun–Sep at double rate
    jh = m.journey_home
    jh._elec_rates = np.tile(seasonal, (2, 1))
    m.run_all()

    prod = cfg.system_kw * m.solar_resource.ac_monthly
    scf = interim_scf(cfg.battery_enabled)
    exp_rates = jh._solar_export_rates[0]
    expected = (prod * scf) @ seasonal + (prod * (1 - scf)) @ exp_rates
    averaged = (prod * scf).sum() * seasonal.mean() + (prod * (1 - scf)).sum() * exp_rates.mean()
    assert jh.solar_savings_history[0] == pytest.approx(expected, rel=1e-9)
    assert expected > averaged * 1.02          # summer-heavy solar earns more than the average says
