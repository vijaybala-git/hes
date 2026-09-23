"""Validation for the offline URDB harvest — data/rates/urdb_tou.json (docs/OfflineURDB_Plan.md §6).

These gate the *baked data + parser*, independent of the review notebook. They do NOT import any
src/ code (isolation until Phase 7) beyond the ZIP resolver used for the attachment smoke test.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
URDB = ROOT / "data" / "rates" / "urdb_tou.json"
EIA = ROOT / "data" / "rates" / "eia_rates_by_utility.json"

pytestmark = pytest.mark.skipif(not URDB.exists(), reason="run scripts/build_urdb.py first")

VALID_KINDS = {"tou", "tiered_legacy", "ev_tou"}


@pytest.fixture(scope="module")
def db():
    return json.loads(URDB.read_text())


@pytest.fixture(scope="module")
def utilities(db):
    return db["utilities"]


def _all_tariffs(utilities):
    for uid, u in utilities.items():
        for label, t in u["tariffs"].items():
            yield uid, u, label, t


# ── file / meta ────────────────────────────────────────────────────────────────
def test_meta_and_utilities_present(db):
    assert db["_meta"]["approved_only"] is True
    assert db["_meta"]["peak_hours"] == list(range(16, 21))
    assert db["utilities"], "no utilities harvested"


def test_pge_harvested(utilities):
    assert "14328" in utilities, "PG&E (14328) should be harvested"


# ── multiplicity + default (§4.2a / §4.3) ────────────────────────────────────────
def test_one_tou_default_per_utility(utilities):
    for uid, u in utilities.items():
        defaults = [t for t in u["tariffs"].values() if t["whywatt_default"]]
        assert len(defaults) == 1, f"{uid}: expected exactly one whywatt_default"
        d = defaults[0]
        assert u["default_label"] in u["tariffs"]
        assert u["tariffs"][u["default_label"]] is d
        assert d["plan_kind"] == "tou", f"{uid}: default must be a TOU plan (full-TOU goal)"
        assert d["closed_to_enrollment"] is False, f"{uid}: default must be open to enrollment"


def test_labels_unique_and_kinds_valid(utilities):
    labels = [label for _, _, label, _ in _all_tariffs(utilities)]
    assert len(labels) == len(set(labels)), "duplicate tariff labels"
    for _, _, _, t in _all_tariffs(utilities):
        assert t["plan_kind"] in VALID_KINDS


def test_multiple_plans_available(utilities):
    # the whole point: a utility offers a *set* of plans to pick from
    assert len(utilities["14328"]["tariffs"]) >= 3


# ── structure / parser invariants (§3) ───────────────────────────────────────────
def test_by_month_shape(utilities):
    for uid, _, label, t in _all_tariffs(utilities):
        assert len(t["by_month"]) == 12, f"{label}: by_month must be length 12"
        # peak window sits in the afternoon/evening for TOU plans; empty for flat/tiered plans
        if t["is_tou"]:
            # a proper subset of the day (not empty, not all 24h), all valid hours
            assert 0 < len(t["peak_hours"]) < 24, f"{label}: TOU peak window {t['peak_hours']} invalid"
            assert all(0 <= h <= 23 for h in t["peak_hours"]), f"{label}: bad peak hour"
        else:
            assert t["peak_hours"] == [], f"{label}: flat plan should have no peak window"
        for m, bm in enumerate(t["by_month"]):
            for side in ("peak", "offpeak"):
                assert bm[side], f"{label} m{m}: empty {side} ladder"
                assert all(tier["rate"] > 0 for tier in bm[side]), f"{label} m{m}: non-positive rate"


def test_tier_ladders_ascend(utilities):
    for uid, _, label, t in _all_tariffs(utilities):
        for m, bm in enumerate(t["by_month"]):
            for side in ("peak", "offpeak"):
                caps = [tier["max_kwh_day"] for tier in bm[side]]
                # all but the last tier are capped; caps strictly ascend; last is open (None)
                assert caps[-1] is None, f"{label} m{m} {side}: last tier must be open-ended"
                finite = [c for c in caps if c is not None]
                assert finite == sorted(finite), f"{label} m{m} {side}: tier caps must ascend"


def test_flat_tariff_collapses(utilities):
    # a non-TOU tariff (is_tou False) must have peak == offpeak every month (fallback invariant 4)
    for uid, _, label, t in _all_tariffs(utilities):
        if not t["is_tou"]:
            for bm in t["by_month"]:
                assert bm["peak"] == bm["offpeak"], f"{label}: flat tariff must have peak==offpeak"


def test_seasonality_present_in_tou(utilities):
    # a real CA TOU tariff must have summer != winter somewhere (URDB carries seasonality)
    d = utilities["14328"]["tariffs"][utilities["14328"]["default_label"]]
    jan = d["by_month"][0]["peak"][0]["rate"]
    jul = d["by_month"][6]["peak"][0]["rate"]
    assert jul > jan, "summer peak should exceed winter peak (PG&E E-TOU-C)"


# ── cross-source sanity vs EIA (§6) ──────────────────────────────────────────────
def test_effective_level_near_eia(utilities):
    eia = json.loads(EIA.read_text())["electric_utilities"]
    for uid, u in utilities.items():
        if uid not in eia:
            continue
        d = u["tariffs"][u["default_label"]]
        ratio = d["effective_level"] / eia[uid]["current_rate"]
        assert 0.6 <= ratio <= 1.4, f"{uid}: URDB effective {d['effective_level']} vs EIA " \
                                    f"{eia[uid]['current_rate']} (ratio {ratio:.2f}) out of band"


# ── ZIP attachment smoke (the interface seam) ────────────────────────────────────
def test_zip_attaches_to_urdb(utilities):
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from rate_resolver import RateResolver
    res = RateResolver().resolve("95112")            # San Jose -> PG&E
    assert str(res.electricity.utility_id) in utilities, "San Jose ZIP should attach to a URDB utility"


# ── coverage gate: "Can we USE URDB?" (data-driven fallback) ──────────────────────
COVERAGE = ROOT / "data" / "rates" / "urdb_coverage.json"


@pytest.mark.skipif(not COVERAGE.exists(), reason="run scripts/build_urdb_coverage.py first")
def test_coverage_lists_ca_iou():
    cov = json.loads(COVERAGE.read_text())["utilities"]
    for eid in ("14328", "17609", "16609"):          # PG&E, SCE, SDG&E must be maintained
        assert eid in cov, f"URDB coverage missing EIA {eid}"
    assert len(cov) > 50, "coverage list looks truncated"


@pytest.mark.skipif(not COVERAGE.exists(), reason="run scripts/build_urdb_coverage.py first")
def test_coverage_decision_logic():
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import urdb_coverage as c
    maintained, harvested = c.maintained_ids(), c.harvested_ids()
    assert c.decide("14328", maintained, harvested) == "urdb"            # PG&E: maintained+harvested
    # a maintained-but-not-harvested utility -> harvest_candidate
    not_harvested = sorted(maintained - harvested)
    if not_harvested:
        assert c.decide(not_harvested[0], maintained, harvested) == "harvest_candidate"
    assert c.decide("9999999", maintained, harvested) == "eia_fallback"  # unknown id
    assert c.decide(None, maintained, harvested) == "eia_fallback"       # unresolved ZIP


# ── ZIP -> baseline territory crosswalk ──────────────────────────────────────────
CROSSWALK = ROOT / "data" / "rates" / "urdb_baseline_crosswalk.json"


@pytest.mark.skipif(not CROSSWALK.exists(), reason="run scripts/build_baseline_crosswalk.py first")
def test_crosswalk_regions_have_baselines(utilities):
    cw = json.loads(CROSSWALK.read_text())["utilities"]
    for eid, c in cw.items():
        mapped = set(c["cec_zone_to_region"].values())
        rb = set(utilities[eid]["tariffs"][utilities[eid]["default_label"]].get("region_baselines", {}))
        if rb:  # utilities whose default plan has baselines
            assert mapped <= rb, f"{eid}: crosswalk maps to regions without a baseline: {mapped - rb}"


@pytest.mark.skipif(not CROSSWALK.exists(), reason="run scripts/build_baseline_crosswalk.py first")
def test_baseline_for_zip_climate_gradient():
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import urdb_baseline as b
    sj = b.baseline_for_zip("14328", "95112")     # San Jose (CZ4 -> X)
    fresno = b.baseline_for_zip("14328", "93704")  # Fresno (CZ13 -> W, hot)
    assert sj.region == "X" and sj.summer_kwh_day == 9.8
    assert fresno.region == "W"
    assert fresno.summer_kwh_day > sj.summer_kwh_day, "hot inland baseline should exceed coastal"
    # SDG&E coastal < desert
    coastal = b.baseline_for_zip("16609", "92101")
    desert = b.baseline_for_zip("16609", "92004")
    assert coastal.summer_kwh_day < desert.summer_kwh_day
    # SCE flat TOU default -> no baseline
    assert b.baseline_for_zip("17609", "90001").source == "flat_no_baseline"
