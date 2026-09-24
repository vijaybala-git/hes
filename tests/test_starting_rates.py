"""Current energy rate × projection growth (Phase 7 §4.1): data, resolver, index, wiring."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from starting_rates import (  # noqa: E402
    IndexedRateSource, get_starting_rates, market_for, projection_index)

RATES = ROOT / "data" / "rates"
PGE, SCE, SDGE = "14328", "17609", "16609"


def _eia():
    return json.loads((RATES / "eia_rates_by_utility.json").read_text(encoding="utf-8"))


# ── Data ──────────────────────────────────────────────────────────────────────

def test_every_eia_record_has_a_2025_starting_rate():
    db = _eia()
    assert db["_meta"]["starting_year"] == 2025
    recs = list(db["electric_utilities"].values()) + list(db["gas_ldcs"].values())
    recs += [db["state_average"]["CA"][f] for f in ("electricity", "gas")]
    for r in recs:
        assert r["starting_rate"]["year"] == 2025 and r["starting_rate"]["rate"] > 0


def test_legacy_my_utility_fields_unchanged():
    """My Utility (the golden default) still prices off the 2024 base-year values."""
    db = _eia()
    pge = db["electric_utilities"][PGE]
    assert pge["base_year"] == 2024 and pge["current_rate"] == pytest.approx(0.3962)
    assert db["gas_ldcs"]["17610617"]["current_rate"] == pytest.approx(2.3147)


def test_electric_2025_is_observed_and_gas_is_bridged():
    db = _eia()
    assert db["electric_utilities"][PGE]["starting_rate"]["rate"] == pytest.approx(0.3991)
    assert db["electric_utilities"][PGE]["starting_rate"]["method"] == "observed"
    g = db["gas_ldcs"]["17610617"]["starting_rate"]
    assert g["method"] == "bridged_state_ratio"
    # CA residential gas $19.14 → $22.01 per Mcf, 2024 → 2025
    assert g["bridge_ratio"] == pytest.approx(22.01 / 19.14, abs=1e-4)
    assert g["rate"] == pytest.approx(2.3147 * g["bridge_ratio"], abs=5e-4)   # rounding


def test_region_file_matches_bundle_eia_pacific():
    reg = json.loads((RATES / "starting_rates.json").read_text(encoding="utf-8"))
    bundle = json.loads((RATES / "projection" / "whywatt_rate_projection.json")
                        .read_text(encoding="utf-8"))
    bench = bundle["markets"]["CA_PGE"]["benchmarks"]["eia_pacific"]
    pac = reg["regions"][reg["default_region"]]
    assert pac["electricity"]["rate"] == pytest.approx(bench["elec"]["2025"])
    assert pac["gas"]["rate"] == pytest.approx(bench["gas"]["2025"])
    assert pac["electricity"]["year"] == pac["gas"]["year"] == 2025


# ── Resolver: by what the ZIP resolves to ─────────────────────────────────────

def test_urdb_covered_utility_starts_from_the_plan():
    st = get_starting_rates().resolve("electricity", PGE, "95112")
    assert st.kind == "urdb" and st.structure.family == "E-TOU-C"
    assert st.year == 2026 and st.label == "PG&E · E-TOU-C"


def test_quarantined_utility_starts_from_its_eia_rate():
    st = get_starting_rates().resolve("electricity", SCE, "90001")
    assert st.kind == "eia_utility" and st.year == 2025
    assert st.rate == pytest.approx(0.3296) and st.label == "SCE · EIA 2025"


def test_no_utility_starts_from_eia_pacific():
    for fuel, rate in (("electricity", 0.24181), ("gas", 1.987)):
        st = get_starting_rates().resolve(fuel, None, "10001")
        assert st.kind == "eia_region" and st.label == "EIA — Pacific"
        assert st.rate == pytest.approx(rate) and st.year == 2025


def test_gas_never_uses_urdb():
    st = get_starting_rates().resolve("gas", "17610617", "95112")
    assert st.kind == "eia_utility" and st.method == "bridged_state_ratio"


# ── Projection index ──────────────────────────────────────────────────────────

def test_index_is_one_at_the_anchor_and_holds_after_2050():
    idx = projection_index("whywatt_moderate", "electricity", [2025, 2026, 2050, 2054], 2026)
    assert idx[1] == pytest.approx(1.0)
    assert idx[0] == pytest.approx(0.386 / 0.400089, rel=1e-5)   # 2025 back-scales
    assert idx[3] == pytest.approx(idx[2])


def test_market_proxy_outside_pge():
    assert market_for("electricity", PGE) == ("CA_PGE", False)
    assert market_for("electricity", SCE) == ("CA_PGE", True)
    assert market_for("gas", None) == ("CA_PGE", True)


def test_indexed_source_is_start_times_curve_growth():
    start = get_starting_rates().resolve("electricity", SCE, "90001")
    src = IndexedRateSource(start, "eia_pacific")
    idx = projection_index("eia_pacific", "electricity", range(2025, 2030), 2025)
    got = src.get_annual_monthly_rates("electricity", 2025, 5)
    assert np.allclose(got, (start.rate * idx)[:, None])


# ── Model wiring ──────────────────────────────────────────────────────────────

def _model(zip_code, elec, gas="cagr_flat", **kw):
    from home_config import HomeConfig
    from model import HESModel
    return HESModel(home_config=HomeConfig(zip_code=zip_code), n_years=4,
                    elec_rate_model_a=elec, gas_rate_model_a=gas, **kw)


def test_projection_on_eia_start_prices_start_times_index():
    m = _model("90001", "whywatt_stress", "whywatt_stress", project_acc_shape=False)
    for fuel, rates, st in (("electricity", m.elec_rates, m.starting_rate_elec),
                            ("gas", m.gas_rates, m.starting_rate_gas)):
        idx = projection_index("whywatt_stress", fuel, range(2025, 2029), st.year)
        assert np.allclose(rates, (st.rate * idx)[:, None])


def test_projection_level_no_longer_uses_the_curve_price():
    """Phase 6 priced at the curve's own level (PG&E Moderate $0.386 everywhere); now the
    level is the home's current rate — an out-of-area ZIP starts at EIA — Pacific."""
    m = _model("10001", "whywatt_moderate", project_acc_shape=False)
    assert m.elec_rates[0, 0] == pytest.approx(0.24181 * 0.386 / 0.386)


def test_scenarios_share_the_current_rate_but_not_the_projection():
    m = _model("95112", "whywatt_moderate", comparison_mode=True,
               elec_rate_model_b="whywatt_stress", gas_rate_model_b="cagr_flat")
    assert m.rate_structure_a is m.rate_structure_b            # one plan for the home
    assert not np.allclose(m.rate_escalation_a, m.rate_escalation_b)


def test_legacy_modes_ignore_the_current_rate():
    a = _model("95112", "cagr_flat")
    assert a.rate_structure_a is None and a.rate_escalation_a is None
