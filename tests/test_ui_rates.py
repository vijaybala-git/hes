"""U2 display helpers (Phase 7 §4.1): current energy rate lines + the utilities line."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

import ui.state as S  # noqa: E402
from ui import sim  # noqa: E402


@pytest.fixture
def zip_state():
    def _set(z):
        S.zip_code.set(z)
    yield _set
    S.reset_to_defaults()


@pytest.mark.parametrize("zip_code,head,kind,detail_has", [
    ("95112", "PG&E · E-TOU-C", "urdb", "peak 4pm–9pm"),
    ("90001", "SCE · EIA 2025", "eia_utility", "plan data under review"),
    ("10001", "EIA — Pacific", "eia_region", "no utility found"),
])
def test_projection_shows_the_current_energy_rate(zip_state, zip_code, head, kind, detail_has):
    zip_state(zip_code)
    h, d, k = sim._current_rate_display("electricity", "whywatt_moderate")
    assert (h, k) == (head, kind) and detail_has in d


def test_gas_current_rate_is_bridged_eia(zip_state):
    zip_state("95112")
    h, d, k = sim._current_rate_display("gas", "eia_pacific")
    assert h == "PG&E · EIA 2025" and k == "eia_utility" and "carried to 2025" in d


def test_legacy_methods_show_their_own_start(zip_state):
    zip_state("95112")
    assert sim._current_rate_display("electricity", "cagr_flat")[2] == "legacy"
    assert "My Utility" in sim._current_rate_display("electricity", "cagr_flat")[1]
    assert sim._current_rate_display("gas", "ca_average")[0] == "California average"


def test_utilities_line():
    assert "PG&amp;E" in sim._utilities_html("95112") or "PG&E" in sim._utilities_html("95112")
    assert "SoCalGas" in sim._utilities_html("90001")
    assert "not found" in sim._utilities_html("10001")


def test_every_primary_projection_button_is_a_known_method():
    from projected_rate_source import PROJECTION_LABELS
    assert all(k in PROJECTION_LABELS for k, _ in sim.PROJECTION_BUTTONS)
    assert [k for k, _ in sim.LEGACY_METHODS["electricity"]][0] == "cagr_flat"
