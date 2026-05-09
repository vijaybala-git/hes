"""
Tests for EnergyPrice (Phase 1 — Objective 5).
"""

import pytest
import numpy as np
from energy_price import (EnergyPrice,
                           DEFAULT_MONTHLY_ELEC_PRICES,
                           DEFAULT_MONTHLY_GAS_PRICES)


FLAT_PRICES = np.full(12, 15.0)


# ---------------------------------------------------------------------------
# 1. Validation
# ---------------------------------------------------------------------------

class TestValidation:

    def test_must_have_12_monthly_prices(self):
        with pytest.raises(ValueError, match="12 values"):
            EnergyPrice("gas", [15.0, 15.0], annual_escalation_rate=0.03)

    def test_escalation_below_minus_one_raises(self):
        with pytest.raises(ValueError, match="escalation_rate must be > -1.0"):
            EnergyPrice("gas", FLAT_PRICES, annual_escalation_rate=-1.5)

    def test_zero_escalation_is_valid(self):
        ep = EnergyPrice("gas", FLAT_PRICES, annual_escalation_rate=0.0)
        assert ep is not None

    def test_negative_escalation_in_range_is_valid(self):
        """Negative escalation (falling prices) should be allowed."""
        ep = EnergyPrice("gas", FLAT_PRICES, annual_escalation_rate=-0.05)
        assert ep is not None


# ---------------------------------------------------------------------------
# 2. Price calculation
# ---------------------------------------------------------------------------

class TestPriceCalculation:

    def test_year_zero_returns_base_prices(self):
        ep = EnergyPrice("gas", FLAT_PRICES, annual_escalation_rate=0.04)
        np.testing.assert_allclose(ep.get_monthly_prices(0), FLAT_PRICES, rtol=1e-9)

    def test_year_one_applies_one_escalation(self):
        ep = EnergyPrice("gas", FLAT_PRICES, annual_escalation_rate=0.04)
        expected = FLAT_PRICES * 1.04
        np.testing.assert_allclose(ep.get_monthly_prices(1), expected, rtol=1e-9)

    def test_compound_escalation_over_multiple_years(self):
        ep = EnergyPrice("gas", FLAT_PRICES, annual_escalation_rate=0.10)
        expected = FLAT_PRICES * (1.10 ** 10)
        np.testing.assert_allclose(ep.get_monthly_prices(10), expected, rtol=1e-9)

    def test_zero_escalation_prices_never_change(self):
        ep = EnergyPrice("gas", FLAT_PRICES, annual_escalation_rate=0.0)
        for year in range(25):
            np.testing.assert_allclose(ep.get_monthly_prices(year), FLAT_PRICES)

    def test_monthly_variation_preserved_under_escalation(self):
        """Escalation scales all months equally; relative ratios unchanged."""
        ep = EnergyPrice("gas", DEFAULT_MONTHLY_GAS_PRICES, annual_escalation_rate=0.05)
        year0 = ep.get_monthly_prices(0)
        year5 = ep.get_monthly_prices(5)
        ratio = year5 / year0
        # All ratios should equal (1.05)^5
        np.testing.assert_allclose(ratio, np.full(12, 1.05 ** 5), rtol=1e-9)

    def test_negative_escalation_lowers_prices(self):
        ep = EnergyPrice("gas", FLAT_PRICES, annual_escalation_rate=-0.05)
        assert ep.get_monthly_prices(1).mean() < FLAT_PRICES.mean()


# ---------------------------------------------------------------------------
# 3. Mean annual price
# ---------------------------------------------------------------------------

class TestMeanAnnualPrice:

    def test_flat_prices_mean_equals_value(self):
        ep = EnergyPrice("gas", FLAT_PRICES, annual_escalation_rate=0.0)
        assert np.isclose(ep.get_mean_annual_price(0), 15.0)

    def test_mean_escalates_correctly(self):
        ep = EnergyPrice("gas", FLAT_PRICES, annual_escalation_rate=0.04)
        assert np.isclose(ep.get_mean_annual_price(1), 15.0 * 1.04)


# ---------------------------------------------------------------------------
# 4. Price series helpers
# ---------------------------------------------------------------------------

class TestPriceSeries:

    def test_price_series_shape(self):
        ep = EnergyPrice("electricity", DEFAULT_MONTHLY_ELEC_PRICES, 0.03)
        series = ep.get_price_series(25)
        assert series.shape == (25, 12)

    def test_price_series_first_row_is_base(self):
        ep = EnergyPrice("electricity", DEFAULT_MONTHLY_ELEC_PRICES, 0.03)
        np.testing.assert_allclose(ep.get_price_series(25)[0],
                                   DEFAULT_MONTHLY_ELEC_PRICES, rtol=1e-9)

    def test_annual_mean_series_length(self):
        ep = EnergyPrice("gas", DEFAULT_MONTHLY_GAS_PRICES, 0.04)
        means = ep.get_annual_mean_series(20)
        assert means.shape == (20,)

    def test_annual_mean_series_increases_with_positive_escalation(self):
        ep = EnergyPrice("gas", FLAT_PRICES, annual_escalation_rate=0.04)
        means = ep.get_annual_mean_series(10)
        # Each year should be larger than the previous
        assert np.all(np.diff(means) > 0)

    def test_default_elec_prices_have_summer_peak(self):
        """July/August electricity prices should exceed January prices."""
        ep = EnergyPrice("electricity", DEFAULT_MONTHLY_ELEC_PRICES, 0.0)
        prices = ep.get_monthly_prices(0)
        assert prices[6] > prices[0]  # July > January

    def test_default_gas_prices_have_winter_peak(self):
        """January gas prices should exceed July gas prices."""
        ep = EnergyPrice("gas", DEFAULT_MONTHLY_GAS_PRICES, 0.0)
        prices = ep.get_monthly_prices(0)
        assert prices[0] > prices[6]  # January > July
