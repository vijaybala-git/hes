"""
Tests for Social & Health Cost of Gas (Phase 3 §6).

Covers SocialCostConfig math, gas_therms_history tracking (incl. furnace+AC slot),
and the DataCollector social-cost columns.
"""
import json
import numpy as np
import pytest

from social_cost import SocialCostConfig


# ── SocialCostConfig ────────────────────────────────────────────────────────────

def test_defaults_total_rate():
    cfg = SocialCostConfig()
    assert cfg.total_rate == pytest.approx(2.30)


def test_climate_disabled():
    cfg = SocialCostConfig(climate_enabled=False)
    assert cfg.climate_eff == 0.0
    assert cfg.total_rate == pytest.approx(1.23)


def test_health_disabled():
    cfg = SocialCostConfig(health_enabled=False)
    assert cfg.health_eff == 0.0
    assert cfg.total_rate == pytest.approx(1.07)


def test_both_disabled():
    cfg = SocialCostConfig(climate_enabled=False, health_enabled=False)
    assert cfg.total_rate == 0.0


def test_custom_rates():
    cfg = SocialCostConfig(climate_rate=1.5, health_rate=0.8)
    assert cfg.total_rate == pytest.approx(2.30)


# ── gas_therms_history (integration) ────────────────────────────────────────────

def _model(slot_configs=None, n_years=20, **kw):
    from model import HESModel
    from home_config import HomeConfig
    m = HESModel(home_config=HomeConfig(), n_years=n_years,
                 slot_configs=slot_configs, **kw)
    m.run_all()
    return m


def test_gas_therms_history_length_and_positive():
    m = _model(n_years=20)
    jh = m.journey_home
    assert len(jh.gas_therms_history) == 20
    # Default home starts with gas furnace + gas WH → year 1 gas therms > 0
    assert jh.gas_therms_history[0] > 0


def test_gas_therms_drop_after_electrification():
    # Default slots electrify HVAC (yr3) and WH (yr5) → later gas therms < year 1
    m = _model(n_years=20)
    jh = m.journey_home
    assert jh.gas_therms_history[-1] < jh.gas_therms_history[0]


def test_baseline_keeps_gas_flat():
    # Do-nothing baseline never swaps → gas therms roughly constant across years
    m = _model(n_years=20)
    bh = m.baseline_home
    assert bh.gas_therms_history[0] > 0
    # last year within 1% of first (no swaps; only seasonal/age effects ~ none)
    assert bh.gas_therms_history[-1] == pytest.approx(bh.gas_therms_history[0], rel=0.01)


def test_furnace_plus_ac_counts_only_furnace_therms():
    # HVAC slot with gas furnace + electric CentralAC baseline.
    # gas_therms must reflect furnace only (AC is electricity, 0 therms).
    slots = [{
        "name": "HVAC", "category": "HVAC_Heating", "starting_state": "gas",
        "has_cooling_baseline": True,
        "baseline_devices": [
            {"class": "GasFurnace", "afue": 0.80, "age": 5, "lifespan": 20,
             "installation_cost": 6000},
            {"class": "CentralAC", "seer_cooling": 14, "age": 5,
             "installation_cost": 5000},
        ],
        "electric_device": {"class": "HeatPumpHVAC", "cop_heating": 3.5,
                            "seer_cooling": 22, "lifespan": 15,
                            "installation_cost": 14000},
        "swap_year": None, "install_cost": 14000, "rebate": 0,
    }]
    m = _model(slot_configs=slots, n_years=3)
    jh = m.journey_home
    # Compare to a furnace-only model with identical params
    slots_furnace_only = [dict(slots[0])]
    slots_furnace_only[0] = {**slots[0], "has_cooling_baseline": False,
                             "baseline_devices": [slots[0]["baseline_devices"][0]]}
    m2 = _model(slot_configs=slots_furnace_only, n_years=3)
    assert jh.gas_therms_history[0] == pytest.approx(
        m2.journey_home.gas_therms_history[0])


# ── DataCollector social columns ────────────────────────────────────────────────

def test_datacollector_social_columns():
    m = _model(n_years=5)  # default config: climate 1.07, health 1.23
    df = m.datacollector.get_model_vars_dataframe()
    for col in ("Journey Social Climate", "Journey Social Health",
                "Baseline Social Climate", "Baseline Social Health"):
        assert col in df.columns
    bh = m.baseline_home
    # year 1 health column == gas therms[0] * 1.23
    assert df["Baseline Social Health"].iloc[0] == pytest.approx(
        bh.gas_therms_history[0] * 1.23)
    assert df["Baseline Social Climate"].iloc[0] == pytest.approx(
        bh.gas_therms_history[0] * 1.07)


def test_disabled_config_zeroes_columns():
    m = _model(n_years=3,
               social_cost_config=SocialCostConfig(climate_enabled=False,
                                                   health_enabled=False))
    df = m.datacollector.get_model_vars_dataframe()
    assert (df["Journey Social Climate"] == 0).all()
    assert (df["Baseline Social Health"] == 0).all()


def test_market_outputs_unchanged_by_social_config():
    # Social cost must not affect market cumulative cost
    m_on  = _model(n_years=10)
    m_off = _model(n_years=10,
                   social_cost_config=SocialCostConfig(climate_enabled=False,
                                                       health_enabled=False))
    assert (m_on.journey_home.cumulative_opex
            == pytest.approx(m_off.journey_home.cumulative_opex))
