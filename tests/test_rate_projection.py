"""
Validation tests for the offline rate-projection model (docs/OfflineRateProjection_Plan.md §7,
methodology §9). These guard the CORRECTED model (residual = RR/Sales, §2.1 correction).

  V1  base plug + reconstruction  — retail(0) == base retail; retail == mc + residual everywhere.
  V2  bounds / ordering           — conservative < moderate < stress; gas within EIA..CEC;
                                    electric moderate tracks the CEC 2025 IEPR real-flat line.
  V3  backcast base anchor        — base year reproduces the 2025 PG&E tariff (the plug).
  V4  cross-fuel COP parity       — heat-pump break-even COP FALLS over time (gas spirals),
                                    crossing a modern COP before 2050.

Plus escalation-primitive unit checks. This file imports ONLY the offline library; the live sim
is untouched.
"""
import json
from pathlib import Path

import numpy as np
import pytest

from rate_projection import ProjectedRateModel, SCENARIO_PRESETS
from rate_projection.escalation import segmented_path

PROJ = Path(__file__).parent.parent / "data" / "rates" / "projection"
BENCH = PROJ / "benchmarks"
SCENARIOS = ["conservative", "moderate", "stress"]
FUELS = ["elec", "gas"]

# Cross-fuel parity constants (CLAUDE.md display conversion + a modern furnace).
THERM_KWH = 29.3      # 1 therm = 29.3 kWh thermal
AFUE = 0.90           # gas furnace seasonal efficiency
MODERN_HP_COP = 3.5   # a good cold-climate heat pump, seasonal


@pytest.fixture(scope="module")
def m():
    return ProjectedRateModel(data_dir=str(PROJ))


def _bench(name):
    return json.loads((BENCH / name).read_text())


def _interp(anchors, year):
    """Log-linear interpolate {yearstr: val} at `year` (clamped at the ends)."""
    ax = sorted(int(y) for y in anchors)
    ay = [float(anchors[str(y)]) for y in ax]
    return float(np.exp(np.interp(year, ax, np.log(ay))))


def _breakeven_cop(v_elec, v_gas):
    """COP at which a heat pump's heat cost equals a gas furnace's, per useful kWh of heat."""
    gas_heat = v_gas / (AFUE * THERM_KWH)   # $/kWh_heat
    return v_elec / gas_heat                 # = v_elec * AFUE * THERM_KWH / v_gas


# ── V1 — plug + reconstruction ────────────────────────────────────────────────

@pytest.mark.parametrize("fuel", FUELS)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_v1_base_year_equals_retail_anchor(m, fuel, scenario):
    """Base-year retail = mc(0) + plug = the tariff anchor, for every scenario (methodology §5.2)."""
    from rate_projection.projected_rate_model import BASE_RETAIL
    assert m.retail(fuel, scenario)[m.base_year] == pytest.approx(BASE_RETAIL[fuel], rel=1e-9)


@pytest.mark.parametrize("fuel", FUELS)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_v1_retail_reconstructs_from_parts(m, fuel, scenario):
    """retail(y) == mc(y) + residual(y) at every year (additive architecture, §3.1)."""
    d = m.decompose(fuel, scenario)
    for y, parts in d.items():
        assert parts["retail"] == pytest.approx(parts["mc"] + parts["residual"], abs=1e-6)


def test_v1_residual_base_is_plug(m):
    """r̄(0) = v_retail(0) − mc(0), a positive majority of the electric retail rate."""
    from rate_projection.projected_rate_model import BASE_RETAIL
    r0 = m.residual_base("elec")
    assert r0 == pytest.approx(BASE_RETAIL["elec"] - m.mc("elec")[m.base_year], abs=1e-9)
    assert 0.5 < r0 / BASE_RETAIL["elec"] < 0.95   # residual is the majority (≈78%)


# ── V2 — ordering & bounds ────────────────────────────────────────────────────

# Electricity is monotonic by construction (a residual deviation band). Gas maps to CEC RR-recovery
# scenarios that CROSS in the near term (Flat/BAU defers cost recovery, so it is *lowest* early then
# spirals) — so gas ordering is only asserted long-run, where it holds cleanly.
_MONO_YEARS = {"elec": [2030, 2040, 2050], "gas": [2040, 2045, 2050]}

@pytest.mark.parametrize("fuel", FUELS)
def test_v2_scenario_monotonic(m, fuel):
    """conservative <= moderate <= stress, per fuel, at its long-run checkpoints."""
    for year in _MONO_YEARS[fuel]:
        c = m.retail(fuel, "conservative")[year]
        md = m.retail(fuel, "moderate")[year]
        s = m.retail(fuel, "stress")[year]
        assert c <= md <= s, f"{fuel} {year}: {c} {md} {s}"


def test_v2_gas_scenarios_cross_near_term(m):
    """Documents (and guards) the CEC feature: Flat/BAU gas is LOWEST early, then spirals past the
    managed cases — so near-term ordering differs from long-run."""
    assert m.retail("gas", "stress")[2030] <= m.retail("gas", "moderate")[2030]   # cross early
    assert m.retail("gas", "stress")[2050] > m.retail("gas", "moderate")[2050]     # spiral late


def test_v2_gas_within_eia_floor_and_cec_ceiling(m):
    """Gas: EIA floor < our scenarios; our stress stays below the CEC BAU extreme.

    Compared in REAL 2024$ (the canonical basis): both the EIA floor and the CEC ceiling
    (tn=264063, GT AAFS 2.5 Flat RR) are published in real 2024$, so our nominal retail is
    converted with to_real() before the comparison.
    """
    eia_gas_2050 = _interp(_bench("eia_aeo.json")["gas"]["series_real_2024"], 2050)   # ~1.3
    cec_gas_2050 = _interp(_bench("cec_2025_iepr_gas.json")["gas"]["series"], 2050)   # ~102.76 real 2024$
    cons_real = m.to_real(m.retail("gas", "conservative"), base_year=2024)[2050]
    stress_real = m.to_real(m.retail("gas", "stress"), base_year=2024)[2050]
    assert cons_real > eia_gas_2050
    assert stress_real < cec_gas_2050
    # stress should be a genuine spiral — well above the floor
    assert stress_real > 5 * eia_gas_2050


@pytest.mark.parametrize("year", [2030, 2040, 2050])
def test_v2_electric_moderate_tracks_cec(m, year):
    """Electric moderate ≈ CEC 2025 IEPR PG&E (real 2024$), within 15% — the §2.1 calibration."""
    cec = _bench("cec_2025_iepr_electric.json")["electric"]["series_real_2024"]
    cec_real = _interp(cec, year)
    ours_real = m.to_real(m.retail("elec", "moderate"), base_year=2024)[year]
    assert abs(ours_real - cec_real) / cec_real < 0.15


def test_v2_electric_moderate_is_real_flat(m):
    """Electric moderate must be ~real-flat (CEC), NOT a spiral: real CAGR within ±1%/yr."""
    real = m.to_real(m.retail("elec", "moderate"), base_year=2024)
    cagr = (real[2050] / real[2025]) ** (1 / 25) - 1
    assert -0.01 < cagr < 0.01


def test_v2_gas_moderate_really_rises_in_real_terms(m):
    """Gas moderate must rise in real terms (the asymmetry vs electricity)."""
    real = m.to_real(m.retail("gas", "moderate"), base_year=2024)
    assert real[2050] > 1.5 * real[2025]


# ── V3 — backcast base anchor ─────────────────────────────────────────────────

@pytest.mark.parametrize("fuel,expected", [("elec", 0.386), ("gas", 2.08)])
def test_v3_backcast_base_anchor(m, fuel, expected):
    """Base year reproduces the 2025 PG&E tariff by construction (plug auto-satisfies V3)."""
    assert m.retail(fuel, "moderate")[m.base_year] == pytest.approx(expected, rel=1e-9)


# ── V4 — cross-fuel COP parity ────────────────────────────────────────────────

@pytest.mark.parametrize("scenario", ["moderate", "stress"])
def test_v4_breakeven_cop_falls_over_time(m, scenario):
    """As gas spirals faster than electricity, the heat-pump break-even COP DROPS."""
    ve, vg = m.retail("elec", scenario), m.retail("gas", scenario)
    be_2025 = _breakeven_cop(ve[2025], vg[2025])
    be_2050 = _breakeven_cop(ve[2050], vg[2050])
    assert be_2050 < be_2025


def test_v4_crossover_before_2050(m):
    """A modern heat pump (COP 3.5) should become cost-favorable vs gas before 2050 (moderate)."""
    ve, vg = m.retail("elec", "moderate"), m.retail("gas", "moderate")
    cross = [y for y in m.years if _breakeven_cop(ve[y], vg[y]) < MODERN_HP_COP]
    assert cross and cross[0] <= 2050
    # today CA electricity is expensive enough that break-even COP is high (>3.5)
    assert _breakeven_cop(ve[2025], vg[2025]) > MODERN_HP_COP


# ── Escalation primitive ──────────────────────────────────────────────────────

def test_escalation_base_and_monotonic():
    yrs = list(range(2025, 2051))
    p = segmented_path(1.0, 2025, yrs, {"near": 0.05, "mid": 0.03, "long": 0.02})
    assert p[2025] == pytest.approx(1.0)
    for a, b in zip(yrs, yrs[1:]):
        assert p[b] > p[a]  # positive growth → strictly increasing


def test_escalation_segment_boundaries():
    """Near rate to 2030, mid 2031-2045, long after — check the step at the knots."""
    yrs = list(range(2025, 2051))
    p = segmented_path(1.0, 2025, yrs, {"near": 0.10, "mid": 0.00, "long": 0.05})
    assert p[2030] / p[2029] == pytest.approx(1.10)   # still near
    assert p[2031] / p[2030] == pytest.approx(1.00)   # mid kicks in (flat)
    assert p[2046] / p[2045] == pytest.approx(1.05)   # long kicks in


def test_escalation_allows_negative_growth():
    p = segmented_path(1.0, 2025, [2025, 2030], {"near": -0.02, "mid": -0.02, "long": -0.02})
    assert p[2030] < 1.0


# ── Portable export bundle (the Phase 6 hand-off contract) ────────────────────

BUNDLE = PROJ / "whywatt_rate_projection.json"


@pytest.fixture(scope="module")
def bundle():
    if not BUNDLE.exists():
        pytest.skip("run scripts/export_rate_projection.py to build the bundle")
    return json.loads(BUNDLE.read_text())


def test_bundle_schema(bundle):
    """The portable bundle must be self-describing, complete, and MARKET-KEYED (schema 2.0)."""
    for key in ("schema_version", "base_year", "years", "fuels", "units", "basis",
                "scenario_keys", "deflator", "provider_types", "default_market", "markets"):
        assert key in bundle, f"missing top-level key: {key}"
    assert bundle["schema_version"] == "2.0"
    assert bundle["fuels"] == ["elec", "gas"]
    assert bundle["default_market"] in bundle["markets"]
    years = [str(y) for y in bundle["years"]]
    for mk_id, mk in bundle["markets"].items():
        for key in ("provider", "geography", "utilities", "base_retail", "default_scenario",
                    "scenarios", "benchmarks"):
            assert key in mk, f"market {mk_id} missing {key}"
        assert mk["provider"] in bundle["provider_types"], f"{mk_id}: unknown provider"
        assert mk["default_scenario"] in mk["scenarios"]
        for sc in ("conservative", "moderate", "stress"):
            for fuel in ("elec", "gas"):
                assert set(mk["scenarios"][sc]["retail"][fuel]) == set(years), \
                    f"{mk_id}/{sc}/{fuel} year coverage mismatch"


def test_bundle_matches_model(m, bundle):
    """Staleness guard: the committed CA_PGE bundle must equal the live model (re-export if fails)."""
    sc_map = bundle["markets"]["CA_PGE"]["scenarios"]
    for sc in ("conservative", "moderate", "stress"):
        for fuel in ("elec", "gas"):
            for y in (2025, 2035, 2050):
                got = sc_map[sc]["retail"][fuel][str(y)]
                assert got == pytest.approx(m.retail(fuel, sc)[y], abs=1e-6), \
                    f"bundle stale at {sc}/{fuel}/{y} — run scripts/export_rate_projection.py"


def test_bundle_base_year_and_consistency(bundle):
    """Per market: base-year retail = base tariff; decomposition (when present) reconstructs retail."""
    by = str(bundle["base_year"])
    for mk in bundle["markets"].values():
        for fuel in ("elec", "gas"):
            assert mk["scenarios"]["moderate"]["retail"][fuel][by] == \
                pytest.approx(mk["base_retail"][fuel], rel=1e-9)
        for sc in mk["scenarios"].values():
            for fuel in ("elec", "gas"):
                dec = sc.get("decomposition", {}).get(fuel)   # optional (EIA-regional markets omit it)
                if dec:
                    ret = sc["retail"][fuel]
                    for y, parts in dec.items():
                        assert parts["mc"] + parts["residual"] == pytest.approx(ret[y], abs=1e-6)
