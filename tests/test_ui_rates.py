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
    ("95814", "SMUD · EIA 2025", "eia_utility", "no plan data yet"),
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
    assert "SMUD" in sim._utilities_html("95814")                 # municipal (issue 6)
    assert "Silicon Valley Power" in sim._utilities_html("95050")


def test_every_primary_projection_button_is_a_known_method():
    from projected_rate_source import PROJECTION_LABELS
    assert all(k in PROJECTION_LABELS for k, _ in sim.PROJECTION_BUTTONS)
    assert [k for k, _ in sim.LEGACY_METHODS["electricity"]][0] == "cagr_flat"


# ── §4.2 Battery card: the Phase 7 "installed with solar" limitation ──────────

def test_battery_card_states_the_linked_install():
    from ui import panels
    try:
        S.solar_planned.set(False)
        assert "add solar" in panels._battery_link_note()
        S.solar_planned.set(True)
        S.solar_install_year.set(3)
        note = panels._battery_link_note()
        assert "Installed with solar in" in note and str(S.sim_start_year.value + 2) in note
        assert panels._battery_is_default()                 # factory = Powerwall 3
        S.solar_battery_kwh.set(10.0)
        assert not panels._battery_is_default()
    finally:
        S.reset_to_defaults()


# ── §4.2 step 2 — unified Plan row ────────────────────────────────────────────

def test_plan_row_mirrors_the_cards_plan_state():
    from ui import panels
    try:
        S.reset_to_defaults()
        assert panels.plan_status("hvac") == "planned"            # factory: HVAC + WH swaps
        assert panels.plan_status("cooktop") == "unplanned"
        assert panels.plan_status("battery") == "locked"          # no solar → no battery
        S.solar_planned.set(True)
        assert panels.plan_status("battery") == "planned"         # battery on by default
        S.cooktop_starting_state.set("electric")
        assert panels.plan_status("cooktop") == "done"            # already electric
        assert "unplanned" not in panels._device_classes("cooktop")
        assert "unplanned" in panels._device_classes("dryer")
        keys = [k for k, *_ in panels._plan_items()]
        assert keys == ["hvac", "water_heater", "ice", "cooktop", "dryer", "baseload",
                        "solar", "battery", "panel"]
    finally:
        S.reset_to_defaults()
