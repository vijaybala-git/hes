"""Phase 6 WS1 — ProjectedRateSource + cec_projection wiring tests.

Covers the WS1 acceptance points (docs/Phase6_Spec.md §1c, refined 2026-09-07):
  (a) the factory-default config selects NO projection model → golden path untouched;
  (b) each projection model loads, base-year matches the bundle, returns shape (12,),
      and the scenarios are monotonic-sane;
  (c) import gate — no src/ module imports src/rate_projection/ (Invariant 5);
  (d) the ACC monthly shape is layered on in core (shaped != flat), revenue-neutrally.
"""
import sys
import json
import re
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from projected_rate_source import (
    ProjectedRateSource, PROJECTION_MODELS, PROJECTION_ELEC_MODELS, PROJECTION_GAS_MODELS,
    PROJECTION_LABELS, supports, _bundle, _BUNDLE_PATH)
from rate_loader import RateLoader, ACCRateLoader
from model import _make_loader, HESModel
from home_config import HomeConfig

_SRC = Path(__file__).parent.parent / "src"
_BUNDLE = json.loads(_BUNDLE_PATH.read_text(encoding="utf-8"))
_MKT = _BUNDLE["markets"][_BUNDLE["default_market"]]


# ── (a) Invariant 2 — the default path selects no projection model ─────────────

def test_factory_default_selects_no_projection_model():
    from ui import config
    d = config.factory_defaults()
    for key in ("elec_rate_model_a", "elec_rate_model_b",
                "gas_rate_model_a", "gas_rate_model_b"):
        assert d[key] not in PROJECTION_MODELS, (
            f"factory default {key}={d[key]!r} is a projection model — would move the golden")


def test_default_rate_models_untouched():
    """The exact legacy defaults (the golden gate lives in test_regression.py)."""
    from ui import config
    d = config.factory_defaults()
    assert d["elec_rate_model_a"] == "cagr_flat"
    assert d["gas_rate_model_a"] == "cagr_flat"
    assert d["elec_rate_model_b"] == "acc_shaped"
    assert d["gas_rate_model_b"] == "acc_seasonal"


# ── (b) Each projection model loads, base year matches, shape (12,), sane ──────

@pytest.mark.parametrize("model_key", sorted(PROJECTION_MODELS))
def test_model_loads_for_each_supported_fuel(model_key):
    for fuel in ("electricity", "gas"):
        if not supports(model_key, fuel):
            with pytest.raises(ValueError):
                ProjectedRateSource(model_key, fuel)
            continue
        src = ProjectedRateSource(model_key, fuel)
        # base year matches the bundle series verbatim
        fk = "elec" if fuel == "electricity" else "gas"
        kind = "scenarios" if model_key.startswith("whywatt_") else "benchmarks"
        skey = model_key.split("whywatt_")[-1] if kind == "scenarios" else {
            "eia_national": "eia_national", "eia_pacific": "eia_pacific",
            "cec_iepr": "cec_electric", "cec_bau": "cec_gas_extreme", "e3_gas": "e3_gas",
        }[model_key]
        node = (_MKT["scenarios"][skey]["retail"] if kind == "scenarios"
                else _MKT["benchmarks"][skey])
        assert src.get_rate(fuel, 2025, 1) == pytest.approx(float(node[fk]["2025"]))
        # positivity + monotone-sane
        for y in _BUNDLE["years"]:
            assert src.get_rate(fuel, y, 6) > 0


def test_get_annual_monthly_rates_shape_12():
    src = ProjectedRateSource("whywatt_moderate", "gas")
    amr = src.get_annual_monthly_rates("gas", 2025, 20)
    assert amr.shape == (20, 12)


def test_out_of_horizon_holds_endpoints():
    src = ProjectedRateSource("whywatt_moderate", "elec".replace("elec", "electricity"))
    assert src.get_rate("electricity", 2019, 1) == src.get_rate("electricity", 2025, 1)
    assert src.get_rate("electricity", 2099, 1) == src.get_rate("electricity", 2050, 1)


def test_gas_death_spiral_is_monotone_and_extreme():
    """cec_bau (CEC 2025 BAU invest) is the death-spiral upper bound: strictly rising, and
    steeper than every other gas curve at 2050."""
    bau = ProjectedRateSource("cec_bau", "gas")
    vals = [bau.get_rate("gas", y, 1) for y in _BUNDLE["years"]]
    assert all(b >= a for a, b in zip(vals, vals[1:]))          # non-decreasing
    others = [k for k in PROJECTION_GAS_MODELS if k != "cec_bau"]
    bau_2050 = bau.get_rate("gas", 2050, 1)
    for k in others:
        assert bau_2050 > ProjectedRateSource(k, "gas").get_rate("gas", 2050, 1)


def test_fuel_specific_membership():
    assert "cec_iepr" in PROJECTION_ELEC_MODELS and "cec_iepr" not in PROJECTION_GAS_MODELS
    assert "cec_bau" in PROJECTION_GAS_MODELS and "cec_bau" not in PROJECTION_ELEC_MODELS
    assert "e3_gas" in PROJECTION_GAS_MODELS and "e3_gas" not in PROJECTION_ELEC_MODELS
    for k in ("whywatt_conservative", "whywatt_moderate", "whywatt_stress",
              "eia_national", "eia_pacific"):
        assert k in PROJECTION_ELEC_MODELS and k in PROJECTION_GAS_MODELS


def test_wrong_fuel_get_rate_raises():
    src = ProjectedRateSource("whywatt_moderate", "gas")
    with pytest.raises(ValueError):
        src.get_rate("electricity", 2025, 1)


def test_every_model_has_a_label():
    for k in PROJECTION_MODELS:
        assert k in PROJECTION_LABELS and PROJECTION_LABELS[k]


# ── (c) Import gate — core never imports the offline package (Invariant 5) ─────

def test_core_does_not_import_rate_projection():
    offenders = []
    for p in _SRC.rglob("*.py"):
        if "rate_projection" in p.parts:
            continue                                   # the offline package itself is exempt
        text = p.read_text(encoding="utf-8")
        if re.search(r"^\s*(from|import)\s+rate_projection\b", text, re.MULTILINE) or \
           re.search(r"^\s*from\s+src\.rate_projection\b", text, re.MULTILINE):
            offenders.append(str(p.relative_to(_SRC)))
    assert not offenders, f"src/ must not import rate_projection: {offenders}"


# ── (d) ACC monthly shape layered on in core, revenue-neutrally ───────────────

def test_make_loader_wraps_in_acc_by_default():
    loader = _make_loader(RateLoader(), "whywatt_stress", "gas", None, project_acc_shape=True)
    assert isinstance(loader, ACCRateLoader)
    bare = _make_loader(RateLoader(), "whywatt_stress", "gas", None, project_acc_shape=False)
    assert isinstance(bare, ProjectedRateSource)


def test_acc_shape_is_seasonal_but_revenue_neutral_for_gas():
    """Gas ACC shape has mean 1.0 → the 12-month average equals the raw annual level, but the
    months are NOT flat (seasonal). The raw (unshaped) source is flat."""
    raw = _make_loader(RateLoader(), "cec_bau", "gas", None, project_acc_shape=False)
    shaped = _make_loader(RateLoader(), "cec_bau", "gas", None, project_acc_shape=True)
    raw_row = raw.get_annual_monthly_rates("gas", 2025, 1)[0]
    shaped_row = shaped.get_annual_monthly_rates("gas", 2025, 1)[0]
    assert np.allclose(raw_row, raw_row[0])                     # raw is flat
    assert not np.allclose(shaped_row, shaped_row[0])           # shaped is seasonal
    assert shaped_row.mean() == pytest.approx(raw_row.mean(), rel=1e-9)  # revenue-neutral


def test_end_to_end_projection_run_with_solar():
    """Death-spiral pairing + NEM3 solar exercises the electric per-class path and the NEM
    export legacy-fallback without crashing; do-nothing must cost far more than the journey."""
    from journey import SolarBatteryConfig
    m = HESModel(home_config=HomeConfig(), n_years=20, sim_start_year=2025,
                 elec_rate_model_a="cec_iepr", gas_rate_model_a="cec_bau",
                 solar_config=SolarBatteryConfig(nem_mode="nbt"))
    m.run_all()
    df = m.datacollector.get_model_vars_dataframe()
    assert df["Baseline Cum Cost"].iloc[-1] > df["Journey Cum Cost"].iloc[-1]
