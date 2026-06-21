"""tests/test_regression.py — the pre-deploy regression gate.

Per the Phase 4.5 decisions:
  • Snapshot layer is a HARD gate — any base-case metric that drifts from the committed
    tests/regression/golden.json fails the build. Intended changes must be re-blessed with
    `python scripts/run_regression.py --update` (which records *why* in the commit).
  • Trend layer is WARN-ONLY — a predicted slider move going the wrong direction emits a
    loud pytest warning but does NOT fail. (It still fails loudly in run_regression's report.)

Determinism is also asserted: the model is deterministic, so a case run twice is identical.
"""
import sys
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

import pytest
import run_regression as R


@pytest.fixture(scope="module")
def results():
    """Run the 12 base cases + 24 trend offsets ONCE for the whole module."""
    base = R.run_all_base()
    trends = R.run_trends(base)
    return base, trends


@pytest.fixture(autouse=True)
def _restore_state():
    yield
    import ui.state as S
    S.reset_to_defaults()


def test_golden_exists():
    assert R.GOLDEN_PATH.exists(), (
        "No golden snapshot. Bless one first:\n"
        "    python scripts/run_regression.py --update")


def test_base_cases_match_golden(results):
    """HARD GATE: every base-case metric must equal the golden snapshot exactly."""
    base, _ = results
    golden = R._load_json(R.GOLDEN_PATH)
    diffs = R.compare_to_golden(golden, base)
    if diffs:
        lines = [f"  {d['case']} · {d['metric']}: golden={d['golden']} current={d['current']}"
                 for d in diffs]
        pytest.fail(
            f"{len(diffs)} regression metric(s) drifted from golden.json:\n"
            + "\n".join(lines)
            + "\n\nIf this change is DESIGNED, re-bless with:\n"
              "    python scripts/run_regression.py --update\n"
            "Otherwise it is a regression — fix the code.")


def test_trend_directions_warn_only(results):
    """WARN-ONLY: predicted slider moves should go the right way, but a miss does not
    fail the gate (it surfaces loudly in run_regression's report instead)."""
    _, trends = results
    warns = [r for r in trends if r["status"] == "WARN"]
    if warns:
        msg = "; ".join(f"{r['name']}/{r['metric']} "
                        f"({r['base']}->{r['offset']}, expected {r['expected']})"
                        for r in warns)
        warnings.warn(f"{len(warns)} trend prediction(s) went the wrong way: {msg}",
                      stacklevel=2)
    assert True  # never fails — trends are warn-only by design


def test_run_is_deterministic():
    """The same case run twice yields byte-identical metrics (no hidden nondeterminism)."""
    case = next(iter(R.discover_cases().values()))
    m1 = R.run_values(case["values"])
    m2 = R.run_values(case["values"])
    assert m1 == m2
