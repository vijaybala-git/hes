"""
Tests for dual pricing scenarios (HESModel comparison_mode) — Objective 5.
Covers: lazy instantiation, independent trajectories, stress > moderate,
        identical scenarios produce identical costs.
"""
from __future__ import annotations

import numpy as np
import pytest


# ═════════════════════════════════════════════════════════════════════════════
# Lazy instantiation — _b attributes absent when comparison_mode=False
# ═════════════════════════════════════════════════════════════════════════════

def test_comparison_mode_false_no_b_homes():
    """comparison_mode=False: journey_home_b and baseline_home_b must not exist."""
    from model import HESModel
    m = HESModel(n_years=3, comparison_mode=False)
    assert not hasattr(m, "journey_home_b")
    assert not hasattr(m, "baseline_home_b")


def test_comparison_mode_false_no_b_rates():
    """comparison_mode=False: elec_rates_b and gas_rates_b must not exist."""
    from model import HESModel
    m = HESModel(n_years=3, comparison_mode=False)
    assert not hasattr(m, "elec_rates_b")
    assert not hasattr(m, "gas_rates_b")


def test_comparison_mode_false_no_b_current_rates():
    """comparison_mode=False: current_elec_rates_b must not exist."""
    from model import HESModel
    m = HESModel(n_years=3, comparison_mode=False)
    assert not hasattr(m, "current_elec_rates_b")
    assert not hasattr(m, "current_gas_rates_b")


def test_comparison_mode_false_datacollector_has_no_b_columns():
    """comparison_mode=False: DataCollector has no Scenario B columns."""
    from model import HESModel
    m = HESModel(n_years=3, comparison_mode=False)
    m.run_all()
    df = m.datacollector.get_model_vars_dataframe()
    assert "Journey Cum Cost B"  not in df.columns
    assert "Baseline Cum Cost B" not in df.columns
    assert "Gas Rate B"          not in df.columns
    assert "Elec Rate B"         not in df.columns


# ═════════════════════════════════════════════════════════════════════════════
# Scenario B homes exist when comparison_mode=True
# ═════════════════════════════════════════════════════════════════════════════

def test_comparison_mode_true_b_homes_exist():
    """comparison_mode=True: journey_home_b and baseline_home_b are created."""
    from model import HESModel
    m = HESModel(n_years=3, comparison_mode=True)
    assert hasattr(m, "journey_home_b")
    assert hasattr(m, "baseline_home_b")


def test_comparison_mode_true_b_rates_exist():
    """comparison_mode=True: elec_rates_b and gas_rates_b are present with correct shape."""
    from model import HESModel
    m = HESModel(n_years=5, comparison_mode=True)
    assert m.elec_rates_b.shape == (5, 12)
    assert m.gas_rates_b.shape  == (5, 12)


def test_comparison_mode_true_datacollector_has_b_columns():
    """comparison_mode=True: DataCollector includes Scenario B reporters."""
    from model import HESModel
    m = HESModel(n_years=3, comparison_mode=True)
    m.run_all()
    df = m.datacollector.get_model_vars_dataframe()
    assert "Journey Cum Cost B"  in df.columns
    assert "Baseline Cum Cost B" in df.columns
    assert "Gas Rate B"          in df.columns
    assert "Elec Rate B"         in df.columns


def test_comparison_mode_true_b_homes_are_independent():
    """B homes produce independent state — stepping A does not affect B."""
    from model import HESModel
    m = HESModel(n_years=5, comparison_mode=True,
                 scenario_a="moderate", scenario_b="stress")
    m.run_all()
    # With different scenarios the B homes will have different costs
    # (stress gas rate > moderate gas rate, so baseline_home_b > baseline_home)
    assert m.baseline_home_b.cumulative_opex != m.baseline_home.cumulative_opex


def test_b_homes_stepped_by_run_all():
    """After run_all(), _b homes have been stepped n_years times."""
    from model import HESModel
    from journey import CATEGORY_ORDER
    n = 6
    m = HESModel(n_years=n, comparison_mode=True)
    m.run_all()
    for cat in CATEGORY_ORDER:
        assert len(m.journey_home_b.cost_history_by_category[cat])  == n
        assert len(m.baseline_home_b.cost_history_by_category[cat]) == n


# ═════════════════════════════════════════════════════════════════════════════
# Stress > moderate cumulative cost (gas-heavy baseline)
# ═════════════════════════════════════════════════════════════════════════════

def test_stress_baseline_exceeds_moderate_baseline():
    """
    Stress scenario has a higher gas CAGR (12%) than moderate (8%).
    Since the default config keeps all devices on gas (swap_year=None),
    baseline_home_b (stress) must accumulate more opex than baseline_home (moderate).
    """
    from model import HESModel
    m = HESModel(n_years=20,
                 scenario_a="moderate",
                 scenario_b="stress",
                 comparison_mode=True)
    m.run_all()
    assert m.baseline_home_b.cumulative_opex > m.baseline_home.cumulative_opex, (
        f"Stress baseline {m.baseline_home_b.cumulative_opex:.0f} should exceed "
        f"moderate baseline {m.baseline_home.cumulative_opex:.0f}"
    )


def test_stress_elec_rate_exceeds_moderate_elec_rate():
    """Scenario B (stress) electricity rates must exceed Scenario A (moderate) at year 20."""
    from model import HESModel
    m = HESModel(n_years=20,
                 scenario_a="moderate",
                 scenario_b="stress",
                 comparison_mode=True)
    m.run_all()
    df = m.datacollector.get_model_vars_dataframe()
    assert df["Elec Rate B"].iloc[-1] > df["Elec Rate"].iloc[-1]


def test_stress_gas_rate_exceeds_moderate_gas_rate():
    """Scenario B (stress) gas rates must exceed Scenario A (moderate) at year 20."""
    from model import HESModel
    m = HESModel(n_years=20,
                 scenario_a="moderate",
                 scenario_b="stress",
                 comparison_mode=True)
    m.run_all()
    df = m.datacollector.get_model_vars_dataframe()
    assert df["Gas Rate B"].iloc[-1] > df["Gas Rate"].iloc[-1]


def test_conservative_baseline_below_moderate_baseline():
    """Conservative baseline must accumulate less opex than moderate (lower CAGR)."""
    from model import HESModel
    m = HESModel(n_years=20,
                 scenario_a="conservative",
                 scenario_b="moderate",
                 comparison_mode=True)
    m.run_all()
    assert m.baseline_home.cumulative_opex < m.baseline_home_b.cumulative_opex


# ═════════════════════════════════════════════════════════════════════════════
# Identical scenarios A==B produce identical four trajectories
# ═════════════════════════════════════════════════════════════════════════════

def test_identical_scenarios_produce_identical_trajectories():
    """When scenario_a == scenario_b, all four homes produce the same costs."""
    from model import HESModel
    m = HESModel(n_years=10,
                 scenario_a="moderate",
                 scenario_b="moderate",
                 comparison_mode=True)
    m.run_all()

    np.testing.assert_allclose(
        m.journey_home.cumulative_opex,
        m.journey_home_b.cumulative_opex,
        rtol=1e-9,
        err_msg="journey_home and journey_home_b differ with identical scenarios",
    )
    np.testing.assert_allclose(
        m.baseline_home.cumulative_opex,
        m.baseline_home_b.cumulative_opex,
        rtol=1e-9,
        err_msg="baseline_home and baseline_home_b differ with identical scenarios",
    )


def test_identical_scenarios_datacollector_matches():
    """DataCollector Scenario A and B columns are equal when scenarios are identical."""
    from model import HESModel
    m = HESModel(n_years=5,
                 scenario_a="conservative",
                 scenario_b="conservative",
                 comparison_mode=True)
    m.run_all()
    df = m.datacollector.get_model_vars_dataframe()

    np.testing.assert_allclose(
        df["Journey Cum Cost"].values,
        df["Journey Cum Cost B"].values,
        rtol=1e-9,
    )
    np.testing.assert_allclose(
        df["Baseline Cum Cost"].values,
        df["Baseline Cum Cost B"].values,
        rtol=1e-9,
    )
    np.testing.assert_allclose(
        df["Gas Rate"].values,
        df["Gas Rate B"].values,
        rtol=1e-9,
    )


# ═════════════════════════════════════════════════════════════════════════════
# Scenario A homes unaffected by comparison_mode flag
# ═════════════════════════════════════════════════════════════════════════════

def test_scenario_a_costs_same_regardless_of_comparison_mode():
    """Enabling comparison_mode must not change Scenario A trajectories."""
    from model import HESModel

    m_single = HESModel(n_years=10, scenario_a="moderate", comparison_mode=False)
    m_single.run_all()

    m_dual = HESModel(n_years=10, scenario_a="moderate", comparison_mode=True)
    m_dual.run_all()

    np.testing.assert_allclose(
        m_single.journey_home.cumulative_opex,
        m_dual.journey_home.cumulative_opex,
        rtol=1e-9,
    )
    np.testing.assert_allclose(
        m_single.baseline_home.cumulative_opex,
        m_dual.baseline_home.cumulative_opex,
        rtol=1e-9,
    )


def test_datacollector_row_count_with_comparison_mode():
    """comparison_mode=True: DataCollector still has exactly n_years rows."""
    from model import HESModel
    m = HESModel(n_years=7, comparison_mode=True)
    m.run_all()
    df = m.datacollector.get_model_vars_dataframe()
    assert len(df) == 7
