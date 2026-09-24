"""Phase 7 §4.3 charts: R.1 / R.2 projection curves, EU.9 monthly solar, EU.10 energy balance,
R.6 peak vs off-peak — data checks + every figure builds (presentation only)."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ui import charts  # noqa: E402


def _run(elec="whywatt_conservative", gas="whywatt_conservative", solar=True, n=20,
         install=1, zip_code="95112"):
    from home_config import HomeConfig
    from journey import CapExOnlySlot, SolarBatteryConfig
    from model import HESModel
    kw = dict(home_config=HomeConfig(zip_code=zip_code), n_years=n,
              elec_rate_model_a=elec, gas_rate_model_a=gas)
    if solar:
        kw.update(solar_config=SolarBatteryConfig(),
                  capex_only_slots=[CapExOnlySlot(name="Solar + Battery", install_cost=0,
                                                  install_year=install)])
    m = HESModel(**kw)
    m.run_all()
    return m, m.datacollector.get_model_vars_dataframe()


@pytest.fixture(scope="module")
def urdb_run():
    return _run()


# ── R.1 / R.2 ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("fuel", ["electricity", "gas"])
def test_in_use_curve_equals_the_model_rate_every_year(urdb_run, fuel):
    m, _ = urdb_run
    curves = charts.projection_curves(m, fuel, 20)
    rates = m.elec_rates if fuel == "electricity" else m.gas_rates
    assert np.allclose(curves["whywatt_conservative"], rates.mean(axis=1), rtol=1e-12)
    assert set(curves) == {"whywatt_conservative", "whywatt_moderate", "whywatt_stress",
                           "eia_pacific"}


def test_curves_share_the_current_rate_at_their_anchor(urdb_run):
    """Gas (EIA start, anchor 2025): all four curves start at the same price. Electricity (URDB
    plan, anchor 2026): all four pass through the same price in 2026."""
    m, _ = urdb_run
    g = charts.projection_curves(m, "gas", 20)
    assert np.allclose([c[0] for c in g.values()], g["whywatt_conservative"][0])
    e = charts.projection_curves(m, "electricity", 20)
    assert m.starting_rate_elec.year == 2026
    assert np.allclose([c[1] for c in e.values()], e["whywatt_conservative"][1])


def test_fixed_rate_method_keeps_curves_as_reference():
    m, df = _run(elec="cagr_flat", gas="cagr_flat", solar=False, n=5)
    fig = charts.make_elec_price(df, m, 5)
    names = [t.name for t in fig.data]
    assert any("in use" in n and "my utility" in n.lower() for n in names)
    assert sum("in use" in n for n in names) == 1
    assert len(fig.data) == 5                                    # 4 curves + the in-use line


# ── R.6 ───────────────────────────────────────────────────────────────────────

def test_price_month_parts_sum_to_price_month():
    from urdb_rates import get_urdb
    rng = np.random.default_rng(7)
    u = get_urdb()
    for o in u.tariff_options("14328"):
        rs = u.resolve("95112", "14328", o["label"])
        for m in range(12):
            pk, op = rng.uniform(0, 600, 2)
            assert sum(rs.price_month_parts(m, pk, op, 30, 1.2)) == pytest.approx(
                rs.price_month(m, pk, op, 30, 1.2), rel=1e-12)


def test_cost_parts_reconcile_with_the_net_bill(urdb_run):
    """peak + off-peak + fixed − the export credit used = the home bill − the solar saving.
    The credit used is capped so the year's bill never goes below zero (the model caps the solar
    saving at the year's electricity bill — early years of a mostly-gas home hit the cap)."""
    m, _ = urdb_run
    jh = m.journey_home
    capped = 0
    for y in range(20):
        p = jh.elec_cost_parts_history[y]
        buy = p["peak"] + p["offpeak"] + p["fixed"]
        capped += p["export_credit"] > buy
        net = buy - min(p["export_credit"], buy)
        assert net == pytest.approx(jh.home_elec_bill_history[y] - jh.solar_savings_history[y],
                                    abs=0.01)
    assert 0 < capped < 20                     # the cap binds early on, not once electrified


def test_r6_empty_without_a_time_of_use_plan():
    m, df = _run(elec="cagr_flat", solar=False, n=3)
    fig = charts.make_peak_offpeak(df, m, 3)
    assert not fig.data and "no peak window" in fig.layout.annotations[0].text


# ── EU.9 / EU.10 ──────────────────────────────────────────────────────────────

def test_eu9_year_selector_clamps_to_install_and_final_year():
    m, df = _run(install=4, n=10)
    assert charts.solar_install_index(m) == 4
    early = charts.make_monthly_solar(df, m, 10, year=1)          # before install → install
    assert str(m.sim_start_year + 3) in early.layout.annotations[0].text
    final = charts.make_monthly_solar(df, m, 10)                  # default → final year
    assert str(m.sim_start_year + 9) in final.layout.annotations[0].text
    assert list(final.data[1].y) == pytest.approx(list(m.journey_home.home_elec_kwh_monthly_history[9]))


def test_eu10_flows_close_the_energy_balance(urdb_run):
    """load = solar → home + battery → home + grid → home, and grid import = grid → home +
    grid → battery (§0 identities), every year."""
    m, _ = urdb_run
    jh = m.journey_home
    for y in range(20):
        load = float(np.sum(jh.home_elec_kwh_monthly_history[y]))
        grid_home = load - jh.solar_direct_history[y] - jh.battery_discharge_history[y]
        assert grid_home >= -1e-6
        assert jh.grid_import_kwh_history[y] == pytest.approx(
            grid_home + jh.battery_charge_grid_history[y], rel=1e-9, abs=1e-6)


def test_solar_charts_empty_without_solar():
    m, df = _run(solar=False, n=3)
    assert not charts.make_monthly_solar(df, m, 3).data
    assert not charts.make_energy_balance(df, m, 3).data


@pytest.mark.parametrize("name", ["Electricity Price Projection", "Gas Price Projection",
                                  "Monthly Solar Generation", "Solar & Battery Energy Balance",
                                  "Peak vs Off-Peak Electricity"])
def test_every_new_chart_builds_and_is_registered(urdb_run, name):
    from ui.theme import CHART_CODES, CHART_OPTIONS
    m, df = urdb_run
    fig = charts.CHART_FNS[name](df, m, 20)
    assert fig.data
    assert name in CHART_OPTIONS and name in CHART_CODES
