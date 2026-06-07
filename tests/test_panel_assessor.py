"""
Tests for src/panel_assessor.py — Phase 3 §5 (Panel Load Assessment).

Covers the NEC Article 220 general/appliance load math, status thresholds,
and the journey-home timeline (active-device resolution per year).
"""
import pytest

from panel_assessor import (
    PanelAssessor, PanelLoadYear, _status,
    RANGE_DEMAND_VA, DRYER_MIN_VA, EV_CONTINUOUS_FACTOR, SERVICE_VOLTS,
)


# ── Lightweight device stubs ────────────────────────────────────────────────────

class _Dev:
    """Stand-in for an EnergyConsumer with electrical nameplate."""
    def __init__(self, name, fuel, volts=0, amps=0, continuous=False):
        self._name = name
        self.fuel_type = fuel
        self.circuit_volts = volts
        self.circuit_amps = amps
        self.continuous = continuous

    @property
    def rated_va(self):
        return float(self.circuit_volts * self.circuit_amps)


def _named(name, fuel="electricity", volts=240, amps=0, continuous=False):
    """Create a stub whose type name matches a real device class for branch logic."""
    cls = type(name, (_Dev,), {})
    return cls(name, fuel, volts, amps, continuous)


def _hp_hvac(amps=30):       return _named("HeatPumpHVAC", amps=amps, continuous=True)
def _hpwh(amps=15):          return _named("HeatPumpWaterHeater", amps=amps)
def _ev(amps=32):            return _named("PhysicsEVCharger", amps=amps, continuous=True)
def _induction(amps=40):     return _named("InductionCooktop", amps=amps)
def _hp_dryer(amps=30):      return _named("HeatPumpDryer", amps=amps)
def _central_ac(amps=20):    return _named("CentralAC", amps=amps)
def _gas_furnace():          return _named("GasFurnace", fuel="gas", volts=0, amps=0)
def _lights():               return _named("LightsAndPlugs", volts=0, amps=0)


# ── General load (Step 1) ───────────────────────────────────────────────────────

def test_general_demand_va_under_threshold():
    # 1800 sqft: 1800*3 + 3000 + 1500 = 9900 (<= 10000 → no demand factor)
    pa = PanelAssessor(1800, 200)
    assert pa.general_demand_va() == pytest.approx(9900.0)


def test_general_demand_va_with_demand_factor():
    # 3000 sqft: 9000 + 3000 + 1500 = 13500 → 10000 + 3500*0.4 = 11400
    pa = PanelAssessor(3000, 200)
    assert pa.general_demand_va() == pytest.approx(11400.0)


# ── Appliance load (Step 2) ─────────────────────────────────────────────────────

def test_appliance_va_full_electrification():
    pa = PanelAssessor(1800, 200)
    devices = [_hp_hvac(30), _ev(32), _hpwh(15), _induction(40), _hp_dryer(30)]
    # HVAC 7200 + EV 7680*1.25=9600 + HPWH 3600 + Induction(fixed)8000 + Dryer max(5000,7200)=7200
    expected = 7200 + 9600 + 3600 + RANGE_DEMAND_VA + 7200
    assert pa.appliance_va(devices) == pytest.approx(expected)
    assert expected == pytest.approx(35600.0)


def test_gas_device_contributes_zero():
    pa = PanelAssessor(1800, 200)
    assert pa.appliance_va([_gas_furnace()]) == 0.0


def test_lights_excluded_from_appliance_va():
    pa = PanelAssessor(1800, 200)
    assert pa.appliance_va([_lights()]) == 0.0


def test_ev_continuous_factor():
    pa = PanelAssessor(1800, 200)
    # 240*32 = 7680, ×1.25 = 9600
    assert pa.appliance_va([_ev(32)]) == pytest.approx(7680 * EV_CONTINUOUS_FACTOR)


def test_dryer_min_floor_applies():
    pa = PanelAssessor(1800, 200)
    # small dryer 240*15=3600 → floor 5000
    assert pa.appliance_va([_hp_dryer(15)]) == pytest.approx(DRYER_MIN_VA)


def test_induction_uses_fixed_range_allowance_not_nameplate():
    pa = PanelAssessor(1800, 200)
    # 50A nameplate would be 12000, but NEC fixed allowance is 8000
    assert pa.appliance_va([_induction(50)]) == pytest.approx(RANGE_DEMAND_VA)


# ── Total service amps (Step 3) ─────────────────────────────────────────────────

def test_nec_load_amps_worked_example():
    pa = PanelAssessor(1800, 200)
    devices = [_hp_hvac(30), _ev(32), _hpwh(15), _induction(40), _hp_dryer(30)]
    # (9900 + 35600) / 240 = 189.583...
    assert pa.nec_load_amps(devices) == pytest.approx(45500 / SERVICE_VOLTS)
    assert pa.nec_load_amps(devices) == pytest.approx(189.583, abs=0.01)


# ── Status thresholds (Step 4) ──────────────────────────────────────────────────

@pytest.mark.parametrize("util,expected", [
    (69, "green"), (70, "yellow"), (89.9, "yellow"),
    (90, "orange"), (100, "orange"), (100.1, "red"), (130, "red"),
])
def test_status_thresholds(util, expected):
    assert _status(util) == expected


# ── Journey timeline (active-device resolution) ─────────────────────────────────

class _Slot:
    def __init__(self, name, starting_state, baseline_devices,
                 electric_device, swap_year):
        self.name = name
        self.starting_state = starting_state
        self.baseline_devices = baseline_devices
        self.electric_device = electric_device
        self.swap_year = swap_year


class _JourneyStub:
    def __init__(self, slots):
        self.slots = slots


def test_timeline_ev_appears_from_swap_year():
    # EV slot: starts "none", added year 5
    ev_slot = _Slot("EV Charger", "none", [], _ev(32), swap_year=5)
    journey = _JourneyStub([ev_slot])
    pa = PanelAssessor(1800, 200)
    tl = pa.journey_load_timeline(journey, 8)

    # Years 1-4: no EV load → only general load 9900/240 = 41.25A
    assert tl[0].service_amps == pytest.approx(9900 / 240, abs=0.01)
    assert tl[3].service_amps == pytest.approx(9900 / 240, abs=0.01)
    assert tl[3].new_device is None
    # Year 5: EV active, new_device flagged
    assert tl[4].new_device == "EV Charger"
    assert tl[4].service_amps > tl[3].service_amps
    # Year 6+: EV still active (no new_device)
    assert tl[5].new_device is None
    assert tl[5].service_amps == pytest.approx(tl[4].service_amps)


def test_timeline_existing_ac_counts_every_year():
    # Gas furnace + existing AC, no HVAC swap planned → AC counts all years
    hvac_slot = _Slot("HVAC", "gas",
                      [_gas_furnace(), _central_ac(20)],
                      _hp_hvac(30), swap_year=None)
    journey = _JourneyStub([hvac_slot])
    pa = PanelAssessor(1800, 200)
    tl = pa.journey_load_timeline(journey, 5)
    # AC VA = 4800; load = (9900 + 4800)/240 every year
    expected = (9900 + 4800) / 240
    assert tl[0].service_amps == pytest.approx(expected, abs=0.01)
    assert tl[4].service_amps == pytest.approx(expected, abs=0.01)


def test_timeline_electric_start_counts_from_year_one():
    slot = _Slot("Water Heater", "electric", [], _hpwh(15), swap_year=None)
    journey = _JourneyStub([slot])
    pa = PanelAssessor(1800, 200)
    tl = pa.journey_load_timeline(journey, 3)
    expected = (9900 + 3600) / 240
    assert tl[0].service_amps == pytest.approx(expected, abs=0.01)


def test_upgrade_needed_years_detects_overload():
    tl = [
        PanelLoadYear(1, 90, 90, "orange", None),
        PanelLoadYear(2, 210, 105, "red", "EV Charger"),
    ]
    pa = PanelAssessor(1800, 200)
    assert pa.upgrade_needed_years(tl) == [2]
