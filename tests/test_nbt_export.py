"""NEM 3.0 export credit = hourly ACC values by calendar year (Phase 7 §4.1 issue 12)."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from nbt_export import nbt_export_rates  # noqa: E402

DATA = ROOT / "data" / "rates"


def _doc():
    return json.loads((DATA / "nbt_export_acc.json").read_text(encoding="utf-8"))


def test_table_is_cz4_acc_total_with_all_components():
    meta = _doc()["_meta"]
    assert meta["climate_zone"] == "CZ4" and meta["acc_vintage"] == 2024
    assert "GHG Adder" in meta["components"] and "Methane Leakage" in meta["components"]


def test_annual_means_match_the_acc_marginal_harvest():
    """Same workbook, same CZ4 cache: the 8760-hour mean equals acc_marginal_electric total."""
    doc = _doc()
    acc = json.loads((DATA / "projection" / "acc_marginal_electric.json")
                     .read_text(encoding="utf-8"))["total_acc_kwh"]
    for y in ("2024", "2025", "2035", "2050"):
        assert doc["annual_mean_kwh"][y] == pytest.approx(acc[y], abs=5e-5)


def test_shape_and_horizon_hold():
    r = nbt_export_rates(2050, 8)                       # 2050..2057; ACC ends 2054
    assert r.shape == (8, 12, 24)
    assert np.array_equal(r[4], r[7])                   # 2054 held after the horizon
    early = nbt_export_rates(2020, 1)
    assert np.array_equal(early[0], nbt_export_rates(2024, 1)[0])


def test_evening_is_worth_more_than_midday():
    """Summer 7pm (net peak) ≫ noon (solar surplus) — why exports must be priced by the hour."""
    july = nbt_export_rates(2025, 1)[0, 6]
    assert july[19] > 5 * july[12]


def test_export_credit_does_not_follow_the_retail_rate_model():
    from home_config import HomeConfig
    from journey import CapExOnlySlot, SolarBatteryConfig
    from model import HESModel

    def rates(model, cagr):
        m = HESModel(home_config=HomeConfig(), n_years=5, elec_rate_model_a=model,
                     elec_cagr_a=cagr, solar_config=SolarBatteryConfig(panels=10),
                     capex_only_slots=[CapExOnlySlot(name="Solar + Battery", install_cost=0,
                                                     install_year=1)])
        return m.journey_home._solar_export_rates
    base = rates("cagr_flat", 0.03)
    assert np.array_equal(base, rates("cagr_flat", 0.10))
    assert np.array_equal(base, rates("whywatt_stress", None))
    assert np.array_equal(base, nbt_export_rates(2025, 5))


def test_hourly_export_rate_in_the_monthly_bill():
    from dispatch import BatteryParams, dispatch_month
    G = np.zeros(24); G[10:15] = 4.0
    L = np.full(24, 0.5)
    x = np.zeros(24); x[12] = 1.0                       # only noon exports earn
    mr = dispatch_month(G, L, BatteryParams(cap_kwh=0.0), days=30, export_rate=x)
    flat = dispatch_month(G, L, BatteryParams(cap_kwh=0.0), days=30, export_rate=0.0)
    assert flat.bills["self"] - mr.bills["self"] == pytest.approx(
        float(mr.day.export[12]) * 30)
