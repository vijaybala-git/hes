"""
Tests for RateLoader — Objective 1.
Covers: historical lookup, CAGR projection, boundary, shape, scenario ordering, error handling.
"""
import pytest
import numpy as np


# ── Layer 1: historical lookups ───────────────────────────────────────────────

def test_elec_historical_lookup(rate_loader):
    assert rate_loader.get_rate("electricity", 2023, 6) == pytest.approx(0.310)


def test_gas_historical_lookup(rate_loader):
    assert rate_loader.get_rate("gas", 2024, 10) == pytest.approx(1.98)


def test_elec_historical_early_period(rate_loader):
    assert rate_loader.get_rate("electricity", 2018, 6) == pytest.approx(0.178)


def test_gas_historical_early_period(rate_loader):
    assert rate_loader.get_rate("gas", 2021, 1) == pytest.approx(1.35)


def test_elec_mid_period_boundary(rate_loader):
    # 2022 had two sub-periods
    assert rate_loader.get_rate("electricity", 2022, 5) == pytest.approx(0.231)
    assert rate_loader.get_rate("electricity", 2022, 6) == pytest.approx(0.248)


# ── Layer 1: projection ───────────────────────────────────────────────────────

def test_elec_projection_moderate(rate_loader):
    expected = 0.386 * (1.07 ** 5)
    assert rate_loader.get_rate("electricity", 2030, 1, "moderate") == pytest.approx(expected, abs=0.001)


def test_gas_projection_moderate(rate_loader):
    expected = 2.08 * (1.08 ** 1)
    assert rate_loader.get_rate("gas", 2026, 6, "moderate") == pytest.approx(expected, rel=1e-6)


def test_elec_projection_conservative(rate_loader):
    expected = 0.386 * (1.04 ** 3)
    assert rate_loader.get_rate("electricity", 2028, 1, "conservative") == pytest.approx(expected, rel=1e-6)


def test_elec_projection_stress(rate_loader):
    expected = 0.386 * (1.10 ** 5)
    assert rate_loader.get_rate("electricity", 2030, 1, "stress") == pytest.approx(expected, rel=1e-6)


# ── Layer 1: historical/projection boundary ───────────────────────────────────

def test_elec_last_historical_month(rate_loader):
    assert rate_loader.get_rate("electricity", 2025, 12) == pytest.approx(0.386)


def test_elec_first_projected_month(rate_loader):
    rate_2026 = rate_loader.get_rate("electricity", 2026, 1, "moderate")
    assert rate_2026 > 0.386


def test_gas_last_historical_month(rate_loader):
    assert rate_loader.get_rate("gas", 2025, 12) == pytest.approx(2.08)


def test_gas_first_projected_month(rate_loader):
    rate_2026 = rate_loader.get_rate("gas", 2026, 1, "moderate")
    assert rate_2026 > 2.08


# ── Layer 1: get_annual_monthly_rates shape ───────────────────────────────────

def test_annual_monthly_rates_shape(rate_loader):
    rates = rate_loader.get_annual_monthly_rates("electricity", 2025, 20, "moderate")
    assert rates.shape == (20, 12)


def test_annual_monthly_rates_shape_gas(rate_loader):
    rates = rate_loader.get_annual_monthly_rates("gas", 2025, 15, "stress")
    assert rates.shape == (15, 12)


def test_annual_monthly_rates_historical_rows(rate_loader):
    rates = rate_loader.get_annual_monthly_rates("electricity", 2023, 5, "moderate")
    # Row 0 = 2023, first period is 0.310 (Jan–Jun) then 0.338 (Jul–Dec)
    assert rates[0, 0] == pytest.approx(0.310)   # Jan 2023
    assert rates[0, 6] == pytest.approx(0.338)   # Jul 2023


def test_annual_monthly_rates_all_positive(rate_loader):
    rates = rate_loader.get_annual_monthly_rates("gas", 2025, 20, "conservative")
    assert np.all(rates > 0)


# ── Layer 1: error handling ───────────────────────────────────────────────────

def test_unknown_scenario_raises(rate_loader):
    with pytest.raises(ValueError):
        rate_loader.get_rate("electricity", 2030, 1, scenario="unknown")


def test_unknown_fuel_raises(rate_loader):
    with pytest.raises(ValueError):
        rate_loader.get_rate("propane", 2025, 1)


def test_unknown_scenario_in_annual_rates_raises(rate_loader):
    with pytest.raises(ValueError):
        rate_loader.get_annual_monthly_rates("electricity", 2025, 10, "bogus")


# ── Layer 3: scenario ordering (directional) ──────────────────────────────────

def test_elec_scenario_ordering_future(rate_loader):
    conservative = rate_loader.get_rate("electricity", 2030, 6, "conservative")
    moderate     = rate_loader.get_rate("electricity", 2030, 6, "moderate")
    stress       = rate_loader.get_rate("electricity", 2030, 6, "stress")
    assert conservative < moderate < stress


def test_gas_scenario_ordering_future(rate_loader):
    conservative = rate_loader.get_rate("gas", 2035, 1, "conservative")
    moderate     = rate_loader.get_rate("gas", 2035, 1, "moderate")
    stress       = rate_loader.get_rate("gas", 2035, 1, "stress")
    assert conservative < moderate < stress


def test_gas_stress_exceeds_moderate_every_future_year(rate_loader):
    for year in range(2026, 2046):
        stress   = rate_loader.get_rate("gas", year, 6, "stress")
        moderate = rate_loader.get_rate("gas", year, 6, "moderate")
        assert stress > moderate, f"stress not > moderate for gas in year {year}"


def test_elec_rates_increase_over_time_moderate(rate_loader):
    rate_2026 = rate_loader.get_rate("electricity", 2026, 1, "moderate")
    rate_2030 = rate_loader.get_rate("electricity", 2030, 1, "moderate")
    assert rate_2030 > rate_2026


def test_gas_rates_increase_over_time_stress(rate_loader):
    rate_2026 = rate_loader.get_rate("gas", 2026, 1, "stress")
    rate_2040 = rate_loader.get_rate("gas", 2040, 1, "stress")
    assert rate_2040 > rate_2026


# ── §10.7: custom_cagr parameter ─────────────────────────────────────────────

def test_custom_cagr_overrides_scenario(rate_loader):
    """custom_cagr=0.15 overrides moderate (0.07) for future years."""
    rate_default = rate_loader.get_rate("electricity", 2030, 6, "moderate")
    rate_custom  = rate_loader.get_rate("electricity", 2030, 6, "moderate",
                                        custom_cagr=0.15)
    assert rate_custom > rate_default
    expected = 0.386 * (1.15 ** 5)
    assert abs(rate_custom - expected) < 0.001


def test_custom_cagr_does_not_affect_historical(rate_loader):
    """Historical period rates are unaffected by custom_cagr."""
    rate_hist   = rate_loader.get_rate("electricity", 2023, 6, "moderate")
    rate_custom = rate_loader.get_rate("electricity", 2023, 6, "moderate",
                                       custom_cagr=0.99)
    assert rate_hist == rate_custom == 0.310


def test_gas_elec_cagr_independent(rate_loader):
    """Gas and electricity escalate at different rates when custom_cagr differs."""
    elec = rate_loader.get_annual_monthly_rates(
        "electricity", 2025, 5, custom_cagr=0.03)
    gas  = rate_loader.get_annual_monthly_rates(
        "gas",         2025, 5, custom_cagr=0.12)
    elec_ratio = elec[4].mean() / elec[0].mean()
    gas_ratio  = gas[4].mean()  / gas[0].mean()
    assert gas_ratio > elec_ratio * 1.3


def test_model_accepts_independent_cagrs():
    """HESModel with explicit gas_cagr=0.12, elec_cagr=0.04 produces
       gas rate > $10/therm in year 20."""
    from model import HESModel
    model = HESModel(gas_cagr_a=0.12, elec_cagr_a=0.04, n_years=20)
    model.run_all()
    df = model.datacollector.get_model_vars_dataframe()
    gas_yr20 = df["Gas Rate"].iloc[-1]
    assert gas_yr20 > 10.0, f"Gas rate in year 20 should exceed $10/therm, got {gas_yr20:.2f}"
