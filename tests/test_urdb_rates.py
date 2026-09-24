"""URDB TOU pricing at runtime (Phase 7 §3): coverage gate, baseline tiers, price_month, wiring."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from urdb_rates import RateStructure, Tier, get_urdb, peak_hours_label  # noqa: E402

PGE, SDGE, SCE = "14328", "16609", "17609"


# ── Coverage gate ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("eiaid,expected", [
    (PGE, "urdb"), (SDGE, "urdb"), (SCE, "quarantined"), (None, "eia_fallback"),
    ("99999", "eia_fallback"),
])
def test_coverage_decision(eiaid, expected):
    assert get_urdb().decision(eiaid) == expected


def test_quarantined_utility_resolves_to_none_with_reason():
    u = get_urdb()
    assert u.resolve("90001", SCE) is None
    assert "0.58" in u.fallback_reason(SCE)


def test_unknown_label_falls_back_to_default():
    rs = get_urdb().resolve("95112", PGE, "not-a-label")
    assert rs.family == "E-TOU-C" and rs.is_tou and rs.peak_hours == (16, 17, 18, 19, 20)


def test_tariff_options_default_first():
    opts = get_urdb().tariff_options(PGE)
    assert opts[0]["is_default"] and opts[0]["family"] == "E-TOU-C"
    assert {"E-ELEC", "EV2", "E-1"} <= {o["family"] for o in opts}


# ── Baseline allowance follows the ZIP's territory ────────────────────────────

@pytest.mark.parametrize("zip_code,region,jan_t1,jul_t1", [
    ("95112", "X", 9.7, 9.8),     # San José (CZ4) — the record's own territory
    ("93720", "W", 9.8, 19.2),    # Fresno (CZ13) — hot inland summer allowance
    ("94103", "T", 7.5, 6.5),     # San Francisco (CZ3) — coastal
])
def test_pge_baseline_by_zip(zip_code, region, jan_t1, jul_t1):
    rs = get_urdb().resolve(zip_code, PGE)
    assert rs.baseline_region == region
    assert rs.peak_ladders[0][0].max_kwh_day == pytest.approx(jan_t1)
    assert rs.peak_ladders[6][0].max_kwh_day == pytest.approx(jul_t1)
    assert rs.offpeak_ladders[6][0].max_kwh_day == pytest.approx(jul_t1)


def test_untiered_plan_has_no_thresholds():
    ev2 = next(o for o in get_urdb().tariff_options(PGE) if o["family"] == "EV2")
    rs = get_urdb().resolve("95112", PGE, ev2["label"])
    assert all(t.max_kwh_day is None for t in rs.peak_ladders[6])


# ── price_month ───────────────────────────────────────────────────────────────

def test_price_month_hand_check_etouc_july():
    """95112 July, 250 peak + 450 off-peak kWh: tier 1 = 9.8×31 kWh, rest tier 2, + $/day."""
    rs = get_urdb().resolve("95112", PGE)
    total, share, t1 = 700.0, 250 / 700, 9.8 * 31
    expected = (t1 * (share * 0.441 + (1 - share) * 0.318)
                + (total - t1) * (share * 0.5224 + (1 - share) * 0.3994)
                + 0.79343 * 31)
    assert rs.price_month(6, 250, 450, 31) == pytest.approx(expected, rel=1e-6)
    assert rs.price_month(6, 250, 450, 31, escalation=1.5) == pytest.approx(expected * 1.5)


def _flat_structure(rate=0.30, fixed=0.0):
    ladder = tuple((Tier(None, rate),) for _ in range(12))
    return RateStructure(eiaid="x", utility="u", label="l", name="flat", family="FLAT",
                         plan_kind="tiered_legacy", is_tou=False, peak_hours=(),
                         peak_ladders=ladder, offpeak_ladders=ladder,
                         fixed_amount=fixed, fixed_unit="$/day", baseline_region=None,
                         baseline_confidence="not_applicable")


def test_flat_tariff_is_revenue_neutral():
    """Invariant 4: peak == off-peak, one tier → kWh × rate (+ fixed)."""
    rs = _flat_structure(0.30, fixed=0.5)
    assert rs.price_month(3, 120.0, 380.0, 30) == pytest.approx(500 * 0.30 + 0.5 * 30)
    assert rs.period_fractions(3, np.ones(24)) == {"peak": 0.0, "offpeak": 1.0}


def test_period_fractions_and_effective_rate():
    rs = get_urdb().resolve("95112", PGE)
    pf = rs.period_fractions(6, np.ones(24))
    assert pf["peak"] == pytest.approx(5 / 24)
    rp, ro = rs.tier1_rates(6)
    assert rs.effective_rate(6, np.ones(24)) == pytest.approx(5 / 24 * rp + 19 / 24 * ro)


def test_peak_hours_label():
    assert peak_hours_label((16, 17, 18, 19, 20)) == "4pm–9pm"
    assert peak_hours_label(()) == "no peak window"


# ── Wiring into the model ─────────────────────────────────────────────────────

def _run(zip_code, rate_model, label=None, solar=True):
    """Short run; a projection method on a URDB-covered utility prices off the plan (§4.1)."""
    from home_config import HomeConfig
    from journey import CapExOnlySlot, SolarBatteryConfig
    from model import HESModel
    kw = dict(home_config=HomeConfig(zip_code=zip_code), n_years=3,
              elec_rate_model_a=rate_model, elec_tariff_label=label)
    if solar:
        kw.update(solar_config=SolarBatteryConfig(panels=4),
                  capex_only_slots=[CapExOnlySlot(name="Solar + Battery", install_cost=0,
                                                  install_year=1)])
    m = HESModel(**kw)
    m.run_all()
    return m


def test_quarantined_zip_prices_off_the_eia_current_rate():
    """SCE is quarantined: a projection method starts from SCE's EIA 2025 rate instead."""
    m = _run("90001", "whywatt_moderate")
    assert m.rate_structure_a is None and m.urdb_decision == "quarantined"
    st = m.starting_rate_elec
    assert st.kind == "eia_utility" and st.utility_id == SCE and st.year == 2025


def test_urdb_home_bill_is_price_month_on_home_load():
    """The home's electric bill = Σ price_month over its own hourly load (tiers + fixed on the
    aggregate), and the category costs absorb the difference so the home total stays exact."""
    m = _run("95112", "whywatt_moderate", solar=False)
    rs, esc = m.rate_structure_a, m.rate_escalation_a
    days = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    peak = rs.peak_mask()
    for home in (m.baseline_home, m.journey_home):
        for y in range(3):
            loads = home.home_load_hourly_history[y]
            expected = sum(rs.price_month(mo, loads[mo][peak].sum() * days[mo],
                                          loads[mo][~peak].sum() * days[mo], days[mo], esc[y])
                           for mo in range(12))
            assert home.home_elec_bill_history[y] == pytest.approx(expected, rel=1e-9)
    # Grown by the projection curve from the plan's effective year (2026): 2025 back-scales.
    from starting_rates import projection_index
    assert rs.family == "E-TOU-C" and rs.effective_year == 2026
    assert esc == pytest.approx(projection_index("whywatt_moderate", "electricity",
                                                 [2025, 2026, 2027], 2026))
    assert esc[1] == pytest.approx(1.0)


def test_eia_path_keeps_no_hourly_bill():
    m = _run("95112", "cagr_flat", solar=False)
    assert m.rate_structure_a is None
    assert all(x is None for x in m.baseline_home.home_load_hourly_history)


def test_ev_plan_picks_cost_saving_in_winter_for_electrified_home():
    """Regression case 02 (PG&E, fully electrified, 6.3 kW + 13.5 kWh) on the EV2 plan under
    WhyWatt Moderate: winter solar can't cover the evening peak, so Cost-saving wins Jan and
    Dec; summer stays Self-powered."""
    import json
    import ui.state as S
    from ui import config, sim
    ev2 = next(o for o in get_urdb().tariff_options(PGE) if o["family"] == "EV2")
    case = json.loads((ROOT / "tests/regression/cases/02_pge_solar.json").read_text())["values"]
    try:
        S.reset_to_defaults()
        S.apply_config(config.merge({**case, "elec_rate_model_a": "whywatt_moderate",
                                     "elec_tariff_label": ev2["label"]}))
        m, _ = sim.run_simulation()
    finally:
        S.reset_to_defaults()
    # Year 10, not the final year: export credits still grow at the retail CAGR (7%/yr) while a
    # projection grows retail far slower, so late in the run exporting outpays self-use and
    # summer months flip to Cost-saving too (Phase7_Spec §4.1 issue 12, decision pending).
    modes = m.journey_home.battery_mode_history[10]
    assert m.rate_structure_a.family == "EV2"
    assert modes[0] == "cost" and modes[11] == "cost"
    assert modes[6] == "self"


def test_retired_urdb_tou_key_migrates_to_whywatt_moderate():
    """`urdb_tou` was a rate source offered as a model (§3); old links migrate (§4.1)."""
    from ui import config
    clean, warn = config.sanitize({"elec_rate_model_a": "urdb_tou",
                                   "elec_rate_model_b": "urdb_tou",
                                   "gas_rate_model_a": "urdb_tou"})
    assert clean["elec_rate_model_a"] == clean["elec_rate_model_b"] == "whywatt_moderate"
    assert "gas_rate_model_a" not in clean
    assert any("retired" in w for w in warn)


def test_model_accepts_retired_key_as_alias():
    m = _run("95112", "urdb_tou", solar=False)
    assert m.elec_rate_model_a == "whywatt_moderate" and m.rate_structure_a is not None
