"""Tests for RateResolver — ZIP → utility resolution with provenance (Phase 4 §2)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rate_resolver import RateResolver

_RATES = Path(__file__).parent.parent / "data" / "rates"


@pytest.fixture(scope="module")
def resolver():
    return RateResolver()


def test_matched_pge_both_fuels(resolver):
    """San Jose (95112) resolves directly to PG&E for electricity and gas."""
    res = resolver.resolve("95112")
    assert res.electricity.provenance == "matched"
    assert "Pacific Gas" in res.electricity.name
    assert res.electricity.unit == "$/kWh"
    assert res.gas.provenance == "matched"
    assert "Pacific Gas" in res.gas.name
    assert res.gas.unit == "$/therm"
    assert not res.any_fallback


def test_matched_la_sce_socalgas(resolver):
    """LA (90001) is SCE for electricity and SoCalGas for gas (separate keyspaces)."""
    res = resolver.resolve("90001")
    assert "Southern California Edison" in res.electricity.name
    assert "Southern California Gas" in res.gas.name


def test_fallback_unresolved_zip(resolver):
    """SF 94103 is a municipal (CCSF) ZIP we have no rate for → CA average fallback."""
    res = resolver.resolve("94103")
    assert res.electricity.provenance == "fallback"
    assert res.gas.provenance == "fallback"
    assert "average" in res.electricity.name.lower()
    assert res.any_fallback
    # Fallback uses the statewide-average numbers
    state_e = json.loads((_RATES / "eia_rates_by_utility.json").read_text())
    assert res.electricity.rate == state_e["state_average"]["CA"]["electricity"]["current_rate"]


def test_bogus_zip_falls_back(resolver):
    res = resolver.resolve("00000")
    assert res.electricity.provenance == "fallback"
    assert res.gas.provenance == "fallback"


def test_explicit_ca_average_is_selected(resolver):
    """Choosing the statewide source marks provenance 'selected', not 'fallback'."""
    res = resolver.resolve("95112", source="ca_average")
    assert res.electricity.provenance == "selected"
    assert res.gas.provenance == "selected"
    assert res.electricity.is_fallback  # selected counts as a non-utility source


def test_inferred_zip_flagged(resolver):
    """A backfilled (prefix-inferred) ZIP resolves with provenance 'inferred'."""
    inferred = json.loads(
        (_RATES / "zip_to_electric_utility.json").read_text())["_meta"]["inferred_zips"]
    assert inferred, "expected at least one inferred ZIP from the gap backfill"
    res = resolver.resolve(inferred[0])
    assert res.electricity.provenance == "inferred"
    assert res.electricity.utility_id is not None


def test_resolution_carries_rate_and_cagr(resolver):
    res = resolver.resolve("95112")
    assert res.electricity.rate > 0
    assert 0 < res.electricity.cagr < 0.5
