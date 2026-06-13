"""Tests for §3 Transportation — GasolineVehicle, ElectricVehicle, DeviceSlot routing."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np
import pytest

from unittest.mock import MagicMock
from devices.vehicle import GasolineVehicle, ElectricVehicle
from journey import DeviceSlot, JourneyHome
from model import HESModel


def _mock_model():
    m = MagicMock()
    m.steps = 1
    m.next_id.return_value = 1
    return m


# ── GasolineVehicle ────────────────────────────────────────────────────────────

def test_gasoline_vehicle_annual_gallons():
    """12,000 mi at 28 MPG → ~428.6 gallons/yr."""
    m = _mock_model()
    v = GasolineVehicle(m, miles_per_year=12_000, mpg=28.0)
    gallons = v.monthly_consumption().sum()
    assert abs(gallons - 12_000 / 28.0) < 0.01


def test_gasoline_vehicle_shape():
    """monthly_consumption must return shape (12,)."""
    m = _mock_model()
    v = GasolineVehicle(m, miles_per_year=10_000, mpg=30.0)
    assert v.monthly_consumption().shape == (12,)


def test_gasoline_vehicle_fuel_type():
    m = _mock_model()
    v = GasolineVehicle(m)
    assert v.fuel_type == "gasoline"


def test_gasoline_vehicle_cost_via_step():
    """With $4.50/gal flat rate, cost = gallons × 4.50."""
    m = _mock_model()
    v = GasolineVehicle(m, miles_per_year=12_000, mpg=28.0)
    rates = np.full(12, 4.50)
    v.step(rates)
    expected = (12_000 / 28.0) * 4.50
    assert abs(v.history["cost"][-1] - expected) < 0.50


# ── ElectricVehicle ────────────────────────────────────────────────────────────

def test_electric_vehicle_wall_kwh():
    """12,000 mi at 3.5 mi/kWh, 0.88 efficiency → ~3896 wall-kWh/yr."""
    m = _mock_model()
    v = ElectricVehicle(m, miles_per_year=12_000, ev_eff_mi_per_kwh=3.5,
                        charging_efficiency=0.88)
    wall_kwh = v.monthly_consumption().sum()
    expected = (12_000 / 3.5) / 0.88
    assert abs(wall_kwh - expected) < 0.1


def test_electric_vehicle_shape():
    m = _mock_model()
    v = ElectricVehicle(m)
    assert v.monthly_consumption().shape == (12,)


def test_electric_vehicle_fuel_type():
    m = _mock_model()
    v = ElectricVehicle(m)
    assert v.fuel_type == "electricity"


def test_charging_efficiency_increases_wall_kwh():
    """Lower charging efficiency → more wall-kWh for same miles."""
    m = _mock_model()
    v88 = ElectricVehicle(m, miles_per_year=10_000, ev_eff_mi_per_kwh=3.5,
                          charging_efficiency=0.88)
    v70 = ElectricVehicle(m, miles_per_year=10_000, ev_eff_mi_per_kwh=3.5,
                          charging_efficiency=0.70)
    assert v70.monthly_consumption().sum() > v88.monthly_consumption().sum()


# ── DeviceSlot gasoline routing ────────────────────────────────────────────────

def test_device_slot_routes_gasoline_to_gasoline_rates():
    """DeviceSlot with GasolineVehicle must use gasoline_rates, not gas_rates."""
    m = _mock_model()
    gasoline_vehicle = GasolineVehicle(m, miles_per_year=12_000, mpg=28.0)
    slot = DeviceSlot(
        name="Transportation",
        category="Transportation",
        starting_state="gas",
        baseline_devices=[gasoline_vehicle],
        style_key="ice",
    )
    elec_rates = np.full(12, 0.386)
    gas_rates  = np.full(12, 2.08)
    gasoline_rates = np.full(12, 4.50)

    slot.step(1, elec_rates, gas_rates, is_baseline_home=False,
              gasoline_rates=gasoline_rates)

    expected_cost = (12_000 / 28.0) * 4.50
    assert abs(gasoline_vehicle.history["cost"][-1] - expected_cost) < 0.50


def test_device_slot_tracks_gasoline_gallons():
    """_last_gasoline_gallons must be set after stepping a gasoline slot."""
    m = _mock_model()
    v = GasolineVehicle(m, miles_per_year=12_000, mpg=28.0)
    slot = DeviceSlot(
        name="Transportation",
        category="Transportation",
        starting_state="gas",
        baseline_devices=[v],
        style_key="ice",
    )
    elec_rates    = np.full(12, 0.386)
    gas_rates     = np.full(12, 2.08)
    gasoline_rates = np.full(12, 4.50)

    slot.step(1, elec_rates, gas_rates, is_baseline_home=False,
              gasoline_rates=gasoline_rates)

    assert abs(slot._last_gasoline_gallons - 12_000 / 28.0) < 0.1


# ── HESModel integration ───────────────────────────────────────────────────────

def test_hesmodel_transportation_slot():
    """HESModel with a transportation slot runs without error and tracks gallons."""
    transport_slot_cfg = {
        "name": "Transportation",
        "category": "Transportation",
        "style_key": "ice",
        "starting_state": "gas",
        "has_cooling_baseline": False,
        "baseline_devices": [{"class": "GasolineVehicle", "miles_per_year": 12_000,
                               "mpg": 28.0, "lifespan": 25, "installation_cost": 0}],
        "existing_age": 0,
        "electric_device": {"class": "ElectricVehicle", "miles_per_year": 12_000,
                            "ev_eff_mi_per_kwh": 3.5, "charging_efficiency": 0.88,
                            "lifespan": 25, "installation_cost": 0},
        "swap_year": None,
        "install_cost": 0,
        "rebate": 0,
    }
    m = HESModel(
        n_years=5,
        slot_configs=[transport_slot_cfg],
        gasoline_price_per_gallon=4.50,
        gasoline_escalation_pct=0.02,
    )
    m.run_all()

    # Journey should have 5 years of gasoline_gallons_history
    assert len(m.journey_home.gasoline_gallons_history) == 5
    assert len(m.baseline_home.gasoline_gallons_history) == 5

    # Annual gallons ≈ 12000/28 ≈ 428.6
    expected_gallons = 12_000 / 28.0
    for g in m.journey_home.gasoline_gallons_history:
        assert abs(g - expected_gallons) < 1.0


def test_hesmodel_ev_switch_drops_gasoline():
    """After swap year, journey home gasoline gallons drop to 0."""
    transport_slot_cfg = {
        "name": "Transportation",
        "category": "Transportation",
        "style_key": "ice",
        "starting_state": "gas",
        "has_cooling_baseline": False,
        "baseline_devices": [{"class": "GasolineVehicle", "miles_per_year": 12_000,
                               "mpg": 28.0, "lifespan": 25, "installation_cost": 0}],
        "existing_age": 0,
        "electric_device": {"class": "ElectricVehicle", "miles_per_year": 12_000,
                            "ev_eff_mi_per_kwh": 3.5, "charging_efficiency": 0.88,
                            "lifespan": 25, "installation_cost": 0},
        "swap_year": 3,   # switch to EV at year 3
        "install_cost": 0,
        "rebate": 0,
    }
    m = HESModel(
        n_years=5,
        slot_configs=[transport_slot_cfg],
        gasoline_price_per_gallon=4.50,
    )
    m.run_all()

    # Years 1 and 2: ICE — gallons should be nonzero
    assert m.journey_home.gasoline_gallons_history[0] > 0
    assert m.journey_home.gasoline_gallons_history[1] > 0
    # Years 3, 4, 5: EV — gallons should be zero
    assert m.journey_home.gasoline_gallons_history[2] == 0.0
    assert m.journey_home.gasoline_gallons_history[3] == 0.0
    assert m.journey_home.gasoline_gallons_history[4] == 0.0

    # Baseline always ICE — gallons always nonzero
    for g in m.baseline_home.gasoline_gallons_history:
        assert g > 0


def test_hesmodel_gasoline_externalities_in_datacollector():
    """DataCollector must report Journey Gasoline Climate and Health columns."""
    transport_slot_cfg = {
        "name": "Transportation",
        "category": "Transportation",
        "style_key": "ice",
        "starting_state": "gas",
        "has_cooling_baseline": False,
        "baseline_devices": [{"class": "GasolineVehicle", "miles_per_year": 12_000,
                               "mpg": 28.0, "lifespan": 25, "installation_cost": 0}],
        "existing_age": 0,
        "electric_device": {"class": "ElectricVehicle", "miles_per_year": 12_000,
                            "ev_eff_mi_per_kwh": 3.5, "charging_efficiency": 0.88,
                            "lifespan": 25, "installation_cost": 0},
        "swap_year": None,
        "install_cost": 0,
        "rebate": 0,
    }
    m = HESModel(
        n_years=3,
        slot_configs=[transport_slot_cfg],
        gasoline_climate_enabled=True,
        gasoline_climate_cost_per_gallon=1.69,
        gasoline_health_enabled=True,
        gasoline_health_cost_per_gallon=0.75,
    )
    m.run_all()
    df = m.datacollector.get_model_vars_dataframe()

    assert "Journey Gasoline Climate" in df.columns
    assert "Journey Gasoline Health" in df.columns

    # Climate cost ≈ gallons × 1.69
    expected_climate = (12_000 / 28.0) * 1.69
    assert abs(df["Journey Gasoline Climate"].iloc[0] - expected_climate) < 1.0
