"""Phase 6 WS1 — sanity guard for the rate-model impact validation harness.

Not a golden (the projection paths are expected to move as the model evolves). This asserts the
qualitative findings the offline write-up relies on, so a regression in the rate wiring is caught:
gas severity ordering, that aggressive gas projections make the journey pay back, and that the
CA-anchored projections raise the do-nothing gas cost vs the legacy default.
"""
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO / "scripts"))

from validate_rate_models import build, SCENARIOS, RATE_RUNS


@pytest.fixture(scope="module")
def snapshot():
    return build()


def test_all_scenarios_and_runs_present(snapshot):
    assert set(snapshot["scenarios"]) == set(SCENARIOS)
    for sdef in snapshot["scenarios"].values():
        assert set(sdef["runs"]) == set(RATE_RUNS)


def test_gas_severity_ordering(snapshot):
    """Do-nothing (all-gas) cost rises with gas-scenario severity: conservative < moderate < stress."""
    runs = snapshot["scenarios"]["hvac2027_wh2029"]["runs"]
    c = runs["whywatt_conservative"]["baseline_cumulative_opex"]
    m = runs["whywatt_moderate"]["baseline_cumulative_opex"]
    s = runs["whywatt_stress"]["baseline_cumulative_opex"]
    assert c < m < s


def test_ca_projections_raise_do_nothing_vs_legacy(snapshot):
    """The CA-anchored projections (WhyWatt / CEC) reprice a do-nothing home's gas bill UP vs the
    legacy default — the core 'impact of new rate modeling' finding."""
    runs = snapshot["scenarios"]["hvac2027_wh2029"]["runs"]
    for key in ("whywatt_conservative", "whywatt_moderate", "whywatt_stress", "cec_deathspiral"):
        assert runs[key]["baseline_vs_reference"] > 0, key


def test_aggressive_gas_makes_journey_pay_back(snapshot):
    """Under WhyWatt Stress and the CEC death-spiral pairing, the HVAC+WH journey saves money
    (positive opex_delta) and pays back within the horizon."""
    runs = snapshot["scenarios"]["hvac2027_wh2029"]["runs"]
    for key in ("whywatt_stress", "cec_deathspiral"):
        assert runs[key]["opex_delta"] > 0, key
        assert runs[key]["payback_year"] is not None, key


def test_legacy_default_hvac_wh_does_not_pay_back(snapshot):
    """Baseline finding to contrast against: under today's default rates, HVAC+WH alone does not
    pay back over the horizon (documents why the rate model matters)."""
    ref = snapshot["scenarios"]["hvac2027_wh2029"]["runs"]["legacy_default_cagr"]
    assert ref["opex_delta"] < 0
    assert ref["payback_year"] is None


def test_cec_deathspiral_beats_moderate(snapshot):
    """The CEC BAU-invest gas pairing reprices do-nothing higher than WhyWatt Moderate."""
    runs = snapshot["scenarios"]["hvac2027_wh2029"]["runs"]
    assert (runs["cec_deathspiral"]["baseline_cumulative_opex"]
            > runs["whywatt_moderate"]["baseline_cumulative_opex"])


def test_panel_trigger_is_red_only_on_small_service(snapshot):
    """Panel status is rate-independent: the same full-electrification load trips RED on a 100 A
    service but not on 200 A (case 07 trigger). Verify across every rate model."""
    small = snapshot["scenarios"]["panel_upgrade_100A"]["runs"]
    big = snapshot["scenarios"]["full_electrification_2027_29"]["runs"]
    for key in small:
        assert small[key]["peak_status"] == "red", key
        assert big[key]["peak_status"] != "red", key


def test_solar_lowers_journey_cost(snapshot):
    """Adding rooftop solar to the full journey cuts the journey's cumulative opex under every
    rate model (same load, self-supplied)."""
    solar = snapshot["scenarios"]["full_electrification_solar"]["runs"]
    nosolar = snapshot["scenarios"]["full_electrification_2027_29"]["runs"]
    for key in solar:
        assert solar[key]["journey_cumulative_opex"] < nosolar[key]["journey_cumulative_opex"], key


def test_longer_horizon_amplifies_gas_gap(snapshot):
    """The 30-year run widens the do-nothing gas gap vs the 20-year run for the CA gas spiral,
    and preserves the conservative < moderate < stress ordering."""
    long_ = snapshot["scenarios"]["hvac2027_wh2029_30yr"]["runs"]
    short = snapshot["scenarios"]["hvac2027_wh2029"]["runs"]
    for key in ("whywatt_moderate", "whywatt_stress", "cec_deathspiral"):
        assert long_[key]["baseline_cumulative_opex"] > short[key]["baseline_cumulative_opex"], key
    assert (long_["whywatt_conservative"]["baseline_cumulative_opex"]
            < long_["whywatt_moderate"]["baseline_cumulative_opex"]
            < long_["whywatt_stress"]["baseline_cumulative_opex"])
