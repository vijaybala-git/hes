import sys
import os

# Add src/ to path so tests can import modules directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import json
import pytest
import numpy as np
import mesa
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"


# ── Rate loader ───────────────────────────────────────────────────────────────

@pytest.fixture
def rate_loader():
    from rate_loader import RateLoader
    return RateLoader()


@pytest.fixture
def flat_elec_rates():
    """Flat $0.386/kWh — for cost identity tests."""
    return np.full(12, 0.386)


@pytest.fixture
def flat_gas_rates():
    """Flat $2.08/therm — for cost identity tests."""
    return np.full(12, 2.08)


# ── Climate data ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def bay_area_climate():
    with open(DATA / "climate/bayarea_tmy3.json") as f:
        return json.load(f)


@pytest.fixture
def monthly_hdd(bay_area_climate):
    return np.array(bay_area_climate["monthly_hdd_65f"], dtype=float)


@pytest.fixture
def monthly_cdd(bay_area_climate):
    return np.array(bay_area_climate["monthly_cdd_65f"], dtype=float)


@pytest.fixture
def monthly_inlet_temp(bay_area_climate):
    return np.array(bay_area_climate["monthly_inlet_water_temp_f"], dtype=float)


# ── Mesa model stub for device construction ───────────────────────────────────

@pytest.fixture
def mock_model():
    """Minimal mesa.Model instance — devices need a model ref but don't use it."""
    return mesa.Model()
