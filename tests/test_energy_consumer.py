"""
Tests for EnergyConsumer (Phase 1 — Objective 1).
Updated for Objective 5: MinimalModel now provides monthly price arrays.
"""

import pytest
import numpy as np
import mesa
from energy_consumer import EnergyConsumer


class MinimalModel(mesa.Model):
    """Bare-minimum Mesa model for unit tests."""
    def __init__(self, elec_rate=70.0, gas_rate=15.0):
        super().__init__()
        # Provide flat 12-element arrays matching the EnergyPrice interface
        self.current_monthly_elec_prices = np.full(12, elec_rate)
        self.current_monthly_gas_prices  = np.full(12, gas_rate)


FLAT_SEASONALITY    = [1/12] * 12
WINTER_SEASONALITY  = [0.2, 0.15, 0.1, 0.05, 0.0, 0.0, 0.0, 0.0, 0.0, 0.05, 0.15, 0.3]
SUMMER_SEASONALITY  = [0.0, 0.0, 0.0, 0.0, 0.1, 0.25, 0.3, 0.25, 0.1, 0.0, 0.0, 0.0]


def make_gas_device(model, annual_load=12.0, efficiency=0.8,
                    lifespan=15, current_age=0, installation_cost=4500):
    return EnergyConsumer(
        model=model, name="Gas Furnace", category="HVAC_Heating",
        annual_load=annual_load, seasonality=WINTER_SEASONALITY,
        fuel_mix={"gas": 1.0}, efficiency=efficiency,
        installation_cost=installation_cost,
        lifespan=lifespan, current_age=current_age,
    )


def make_elec_device(model, annual_load=8.0, efficiency=1.0,
                     lifespan=15, current_age=0):
    return EnergyConsumer(
        model=model, name="Baseload", category="Baseload",
        annual_load=annual_load, seasonality=FLAT_SEASONALITY,
        fuel_mix={"electricity": 1.0}, efficiency=efficiency,
        lifespan=lifespan, current_age=current_age,
    )


# ---------------------------------------------------------------------------
# 1. Validation
# ---------------------------------------------------------------------------

class TestValidation:

    def test_seasonality_must_have_12_values(self):
        model = MinimalModel()
        with pytest.raises(ValueError, match="12 values"):
            EnergyConsumer(model=model, name="Bad", category="Test",
                           annual_load=10.0, seasonality=[0.5, 0.5],
                           fuel_mix={"gas": 1.0})

    def test_seasonality_must_sum_to_one(self):
        model = MinimalModel()
        with pytest.raises(ValueError, match="sum to 1.0"):
            EnergyConsumer(model=model, name="Bad", category="Test",
                           annual_load=10.0, seasonality=[0.1] * 12,
                           fuel_mix={"gas": 1.0})

    def test_seasonality_tolerance_accepted(self):
        model = MinimalModel()
        device = EnergyConsumer(model=model, name="D", category="Test",
                                annual_load=10.0, seasonality=FLAT_SEASONALITY,
                                fuel_mix={"electricity": 1.0})
        assert device is not None

    def test_zero_efficiency_raises(self):
        model = MinimalModel()
        with pytest.raises(ValueError, match="efficiency must be > 0"):
            EnergyConsumer(model=model, name="Bad", category="Test",
                           annual_load=10.0, seasonality=FLAT_SEASONALITY,
                           fuel_mix={"gas": 1.0}, efficiency=0.0)

    def test_negative_efficiency_raises(self):
        model = MinimalModel()
        with pytest.raises(ValueError, match="efficiency must be > 0"):
            EnergyConsumer(model=model, name="Bad", category="Test",
                           annual_load=10.0, seasonality=FLAT_SEASONALITY,
                           fuel_mix={"gas": 1.0}, efficiency=-1.0)


# ---------------------------------------------------------------------------
# 2. Consumption calculation
# ---------------------------------------------------------------------------

class TestConsumptionCalculation:

    def test_gas_device_annual_consumption(self):
        model = MinimalModel()
        device = make_gas_device(model, annual_load=12.0, efficiency=0.8)
        monthly = device.calculate_consumption()
        assert monthly.shape == (12,)
        assert np.isclose(monthly.sum(), 12.0 / 0.8, rtol=1e-6)

    def test_seasonality_distribution(self):
        model = MinimalModel()
        device = make_gas_device(model, annual_load=12.0, efficiency=0.8)
        monthly = device.calculate_consumption()
        np.testing.assert_allclose(monthly / monthly.sum(),
                                   np.array(WINTER_SEASONALITY), rtol=1e-6)

    def test_higher_cop_reduces_consumption(self):
        model = MinimalModel()
        low  = make_gas_device(model, annual_load=12.0, efficiency=1.0)
        high = make_gas_device(model, annual_load=12.0, efficiency=3.5)
        assert high.calculate_consumption().sum() < low.calculate_consumption().sum()

    def test_electric_only_device_has_no_gas(self):
        model = MinimalModel()
        device = make_elec_device(model)
        device.step()
        assert np.all(device.monthly_gas_consumption == 0.0)
        assert np.sum(device.monthly_elec_consumption) > 0.0

    def test_gas_only_device_has_no_electricity(self):
        model = MinimalModel()
        device = make_gas_device(model)
        device.step()
        assert np.all(device.monthly_elec_consumption == 0.0)
        assert np.sum(device.monthly_gas_consumption) > 0.0


# ---------------------------------------------------------------------------
# 3. Cost calculation — monthly price arrays
# ---------------------------------------------------------------------------

class TestCostCalculation:

    def test_gas_cost_uses_monthly_price_array(self):
        """Cost = monthly_consumption * monthly_price (element-wise)."""
        model = MinimalModel(gas_rate=15.0)
        device = make_gas_device(model, annual_load=12.0, efficiency=0.8)
        device.step()
        expected = device.history['gas_consumption'][-1] * 15.0
        np.testing.assert_allclose(device.history['gas_cost'][-1], expected, rtol=1e-6)

    def test_elec_cost_uses_monthly_price_array(self):
        model = MinimalModel(elec_rate=70.0)
        device = make_elec_device(model, annual_load=8.0)
        device.step()
        expected = device.history['elec_consumption'][-1] * 70.0
        np.testing.assert_allclose(device.history['elec_cost'][-1], expected, rtol=1e-6)

    def test_non_uniform_monthly_prices_produce_correct_cost(self):
        """Varying monthly prices produce month-specific costs."""
        model = MinimalModel()
        # Double price in January; use flat seasonality so all months consume equally
        prices = np.full(12, 15.0)
        prices[0] = 30.0
        model.current_monthly_elec_prices = prices
        device = make_elec_device(model, annual_load=12.0, efficiency=1.0)
        device.step()
        # With flat seasonality, consumption is equal every month.
        # January cost should be exactly double February cost (2x price only).
        jan_cost = device.history['elec_cost'][-1][0]
        feb_cost = device.history['elec_cost'][-1][1]
        assert np.isclose(jan_cost / feb_cost, 30.0 / 15.0, rtol=0.01)

    def test_annual_cost_helpers(self):
        model = MinimalModel(elec_rate=70.0)
        device = make_elec_device(model, annual_load=8.0)
        device.step()
        expected = float(np.sum(device.history['elec_cost'][0]))
        assert np.isclose(device.annual_elec_cost(0), expected)
        assert np.isclose(device.annual_gas_cost(0), 0.0)


# ---------------------------------------------------------------------------
# 4. Lifespan and CapEx
# ---------------------------------------------------------------------------

class TestLifespanAndCapex:

    def test_no_capex_before_end_of_life(self):
        model = MinimalModel()
        device = make_gas_device(model, lifespan=15, current_age=0)
        for year in range(14):
            model.steps = year
            device.step()
        assert len(device.capex_events) == 0

    def test_capex_fires_at_lifespan(self):
        model = MinimalModel()
        device = make_gas_device(model, lifespan=15, current_age=14, installation_cost=4500)
        model.steps = 0
        device.step()
        assert len(device.capex_events) == 1
        assert device.capex_events[0] == (0, 4500)

    def test_age_resets_to_zero_after_replacement(self):
        model = MinimalModel()
        device = make_gas_device(model, lifespan=15, current_age=14)
        model.steps = 0
        device.step()
        assert device.age == 0

    def test_second_replacement_fires_after_full_lifespan(self):
        model = MinimalModel()
        device = make_gas_device(model, lifespan=15, current_age=14, installation_cost=4500)
        model.steps = 0
        device.step()
        assert len(device.capex_events) == 1
        for year in range(1, 15):
            model.steps = year
            device.step()
        assert len(device.capex_events) == 1
        model.steps = 15
        device.step()
        assert len(device.capex_events) == 2
        assert device.capex_events[1][0] == 15

    def test_capex_event_records_correct_year(self):
        model = MinimalModel()
        device = make_gas_device(model, lifespan=10, current_age=0)
        for year in range(15):
            model.steps = year
            device.step()
        # age 0, lifespan 10: fires at step 9 (age goes 1..10)
        assert device.capex_events[0][0] == 9


# ---------------------------------------------------------------------------
# 5. History and state
# ---------------------------------------------------------------------------

class TestHistory:

    def test_history_grows_one_entry_per_step(self):
        model = MinimalModel()
        device = make_gas_device(model)
        for year in range(5):
            model.steps = year
            device.step()
        assert len(device.history['gas_cost']) == 5

    def test_monthly_arrays_reset_each_step(self):
        model = MinimalModel()
        device = make_gas_device(model)
        device.step()
        assert np.all(device.monthly_elec_consumption == 0.0)

    def test_inactive_device_records_zeros(self):
        model = MinimalModel()
        device = make_gas_device(model)
        device.is_active = False
        device.step()
        np.testing.assert_array_equal(device.history['gas_cost'][-1], np.zeros(12))

    def test_inactive_device_does_not_age(self):
        model = MinimalModel()
        device = make_gas_device(model, current_age=5)
        device.is_active = False
        device.step()
        assert device.age == 5

    def test_rate_change_affects_only_future_history(self):
        model = MinimalModel(gas_rate=15.0)
        device = make_gas_device(model, annual_load=12.0, efficiency=0.8)
        model.steps = 0
        device.step()
        first_year = device.history['gas_cost'][0].copy()
        model.current_monthly_gas_prices = np.full(12, 30.0)
        model.steps = 1
        device.step()
        np.testing.assert_allclose(device.history['gas_cost'][1], first_year * 2, rtol=1e-6)
