"""Tests for ClimateLoader / ClimateData (Phase 4 §1 / §1.9).

Covers: ZIP->zone lookup, fallback, trajectory shape, CAGR==0 reproducibility,
trend direction (warming), per-year advance, and zone contrast.
"""
import numpy as np
import pytest

from climate_loader import ClimateLoader, ClimateData, TREND_SCENARIOS


@pytest.fixture
def loader():
    return ClimateLoader()


# ── Lookup & fallback ─────────────────────────────────────────────────────────

def test_known_zip_resolves_to_zone(loader):
    assert loader.resolve_zone("95110") == ("CA_CZ4", False)
    assert loader.resolve_zone("93720") == ("CA_CZ13", False)
    assert loader.resolve_zone("96161") == ("CA_CZ16", False)


def test_zip_whitespace_is_stripped(loader):
    assert loader.resolve_zone("  95110 ") == ("CA_CZ4", False)


def test_unknown_zip_falls_back_to_cz4_with_flag(loader):
    zone, fallback = loader.resolve_zone("00000")
    assert zone == "CA_CZ4"
    assert fallback is True
    c = loader.get_climate("00000")
    assert c.fallback is True
    assert c.zone_key == "CA_CZ4"


def test_get_climate_sets_label_and_annuals(loader):
    c = loader.get_climate("93720")
    assert c.zone_label == "CZ13 — Fresno"
    assert c.annual_hdd_65f == 1903    # TMYx 2011-2025 (Fresno is cooling-dominated)
    assert c.annual_cdd_65f == 2485
    assert c.fallback is False


# ── Shapes ────────────────────────────────────────────────────────────────────

def test_trajectory_and_monthly_shapes(loader):
    c = loader.get_climate("95110", n_years=25)
    assert c.hdd_traj.shape == (25, 12)
    assert c.cdd_traj.shape == (25, 12)
    assert c.monthly_hdd.shape == (12,)
    assert c.monthly_cdd.shape == (12,)
    assert c.monthly_inlet.shape == (12,)
    assert c.monthly_avg_temp.shape == (12,)


# ── Reproducibility: trend "none" == static TMY3 ──────────────────────────────

def test_trend_none_is_flat_across_years(loader):
    c = loader.get_climate("93720", n_years=25, trend_scenario="none")
    # every year equals the base year
    assert np.allclose(c.hdd_traj[0], c.hdd_traj[24])
    assert np.allclose(c.cdd_traj[0], c.cdd_traj[24])


def test_base_year_matches_zone_record_and_annual(loader):
    c = loader.get_climate("95110", trend_scenario="none")
    assert c.monthly_hdd.sum() == pytest.approx(c.annual_hdd_65f)
    assert c.monthly_cdd.sum() == pytest.approx(c.annual_cdd_65f)


# ── Trend direction: warming (HDD down, CDD up) ───────────────────────────────

@pytest.mark.parametrize("scenario", ["rcp45", "rcp85"])
def test_warming_trend_hdd_falls_cdd_rises(loader, scenario):
    c = loader.get_climate("93720", n_years=25, trend_scenario=scenario)
    assert c.hdd_traj[24].sum() < c.hdd_traj[0].sum()   # warmer winters
    assert c.cdd_traj[24].sum() > c.cdd_traj[0].sum()   # hotter summers


def test_rcp85_diverges_more_than_rcp45(loader):
    c45 = loader.get_climate("93720", n_years=25, trend_scenario="rcp45")
    c85 = loader.get_climate("93720", n_years=25, trend_scenario="rcp85")
    assert c85.cdd_traj[24].sum() > c45.cdd_traj[24].sum()
    assert c85.hdd_traj[24].sum() < c45.hdd_traj[24].sum()


# ── Live per-year view ────────────────────────────────────────────────────────

def test_advance_to_returns_correct_year_slice(loader):
    c = loader.get_climate("93720", n_years=25, trend_scenario="rcp85")
    c.advance_to(0)
    assert np.allclose(c.monthly_hdd, c.hdd_traj[0])
    c.advance_to(10)
    assert np.allclose(c.monthly_hdd, c.hdd_traj[10])


def test_advance_to_clamps_to_horizon(loader):
    c = loader.get_climate("95110", n_years=25)
    c.advance_to(999)
    assert c.current_year == 24
    c.advance_to(-5)
    assert c.current_year == 0


# ── Zone contrast (the whole point of ZIP lookup) ─────────────────────────────

def test_zone_contrast_inland_hotter_mountain_colder(loader):
    sj = loader.get_climate("95110")     # CZ4 mild
    fr = loader.get_climate("93720")     # CZ13 hot inland
    bc = loader.get_climate("96161")     # CZ16 cold mountain
    assert fr.annual_cdd_65f > sj.annual_cdd_65f      # Fresno far hotter summers
    assert bc.annual_hdd_65f > sj.annual_hdd_65f      # Blue Canyon far colder winters
    assert bc.annual_hdd_65f > fr.annual_hdd_65f


# ── Validation ────────────────────────────────────────────────────────────────

def test_invalid_trend_scenario_raises(loader):
    with pytest.raises(ValueError):
        loader.get_climate("95110", trend_scenario="rcp99")


def test_trend_scenarios_constant_complete():
    assert TREND_SCENARIOS == ("none", "rcp45", "rcp85")
