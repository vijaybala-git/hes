"""
Tests for DeviceSlot + JourneyHome (journey.py) and HESModel (model.py) — Objective 3.
Covers: starting_state routing, swap logic, CapEx events, category history shape,
        bedroom scaling, datacollector row count.
"""
from __future__ import annotations

import mesa
import numpy as np
import pytest


# ── Climate constants (inline so tests are self-contained) ────────────────────

_HDD    = np.array([420, 340, 260, 140, 50, 10, 0, 0, 10, 80, 220, 380], dtype=float)
_CDD    = np.array([0, 0, 0, 5, 20, 60, 90, 85, 55, 20, 5, 0], dtype=float)
_INLET  = np.array([54, 54, 55, 57, 60, 63, 65, 66, 65, 62, 58, 55], dtype=float)

_FLAT_ELEC = np.full(12, 0.386)   # $/kWh
_FLAT_GAS  = np.full(12, 2.08)    # $/therm


# ── Device factories ──────────────────────────────────────────────────────────

def _furnace(model, **kw):
    from devices.physics import GasFurnace
    return GasFurnace(model, monthly_hdd=_HDD, **kw)

def _hphvac(model, **kw):
    from devices.physics import HeatPumpHVAC
    return HeatPumpHVAC(model, monthly_hdd=_HDD, monthly_cdd=_CDD, **kw)

def _gas_wh(model, **kw):
    from devices.physics import GasWaterHeater
    return GasWaterHeater(model, monthly_inlet_temp_f=_INLET, **kw)

def _lights(model, annual_kwh=1200, **kw):
    from devices.seasonal import LightsAndPlugs
    return LightsAndPlugs(model, annual_kwh=annual_kwh, **kw)

def _gas_dryer(model, **kw):
    from devices.seasonal import GasDryer
    return GasDryer(model, **kw)

def _hp_dryer(model, **kw):
    from devices.seasonal import HeatPumpDryer
    return HeatPumpDryer(model, **kw)

def _ev(model, **kw):
    from devices.schedule import EVCharger
    return EVCharger(model, **kw)


# ── Journey step helpers ──────────────────────────────────────────────────────

def _make_jh(model, slots, n_years=10, *, elec_rate=0.386, gas_rate=2.08,
             is_baseline=False):
    """Construct a JourneyHome with flat rates."""
    from journey import JourneyHome
    e = np.full((n_years, 12), elec_rate)
    g = np.full((n_years, 12), gas_rate)
    return JourneyHome(model, slots, e, g, is_baseline_home=is_baseline)


def _advance(jh, n):
    """Step a JourneyHome n times, manually tracking model.steps."""
    for i in range(1, n + 1):
        jh.model.steps = i
        jh.step()


# ═════════════════════════════════════════════════════════════════════════════
# DeviceSlot — starting_state="gas"
# ═════════════════════════════════════════════════════════════════════════════

def test_gas_slot_uses_baseline_before_swap_year():
    """Gas slot: baseline device is active before swap_year; electric after."""
    from journey import DeviceSlot
    model = mesa.Model()

    furnace  = _furnace(model)
    hpvhac   = _hphvac(model)

    slot = DeviceSlot(
        name="HVAC", category="HVAC_Heating",
        starting_state="gas",
        baseline_devices=[furnace],
        electric_device=hpvhac,
        swap_year=3,
    )

    # Year 1 — gas phase
    slot.step(1, _FLAT_ELEC, _FLAT_GAS)
    assert len(furnace.history["cost"]) == 1
    assert len(hpvhac.history["cost"]) == 0

    # Year 2 — still gas
    slot.step(2, _FLAT_ELEC, _FLAT_GAS)
    assert len(furnace.history["cost"]) == 2
    assert len(hpvhac.history["cost"]) == 0

    # Year 3 — swap year: electric device activates
    slot.step(3, _FLAT_ELEC, _FLAT_GAS)
    assert len(furnace.history["cost"]) == 2   # no new gas step
    assert len(hpvhac.history["cost"]) == 1

    # Year 4 — still electric
    slot.step(4, _FLAT_ELEC, _FLAT_GAS)
    assert len(furnace.history["cost"]) == 2
    assert len(hpvhac.history["cost"]) == 2


def test_gas_slot_no_swap_always_baseline():
    """swap_year=None: gas slot never transitions."""
    from journey import DeviceSlot
    model = mesa.Model()

    furnace = _furnace(model)
    hphvac  = _hphvac(model)

    slot = DeviceSlot(
        name="HVAC", category="HVAC_Heating",
        starting_state="gas",
        baseline_devices=[furnace],
        electric_device=hphvac,
        swap_year=None,
    )

    for yr in range(1, 6):
        slot.step(yr, _FLAT_ELEC, _FLAT_GAS)

    assert len(furnace.history["cost"]) == 5
    assert len(hphvac.history["cost"]) == 0


def test_gas_slot_positive_cost_before_swap():
    """Gas slot returns positive cost before swap_year."""
    from journey import DeviceSlot
    model = mesa.Model()

    slot = DeviceSlot(
        name="HVAC", category="HVAC_Heating",
        starting_state="gas",
        baseline_devices=[_furnace(model)],
        electric_device=_hphvac(model),
        swap_year=10,
    )
    cost = slot.step(1, _FLAT_ELEC, _FLAT_GAS)
    assert cost > 0


# ═════════════════════════════════════════════════════════════════════════════
# DeviceSlot — starting_state="electric"
# ═════════════════════════════════════════════════════════════════════════════

def test_electric_slot_uses_electric_in_journey_home():
    """starting_state=electric: electric device used from year 0 (is_baseline=False)."""
    from journey import DeviceSlot
    model = mesa.Model()
    elec_dev = _lights(model)

    slot = DeviceSlot(
        name="Lights", category="Baseload",
        starting_state="electric",
        baseline_devices=[],
        electric_device=elec_dev,
    )

    cost = slot.step(1, _FLAT_ELEC, _FLAT_GAS, is_baseline_home=False)
    assert cost > 0
    assert len(elec_dev.history["cost"]) == 1


def test_electric_slot_uses_electric_in_baseline_home():
    """starting_state=electric: electric device also used in baseline from year 0."""
    from journey import DeviceSlot
    model = mesa.Model()
    elec_dev = _lights(model)

    slot = DeviceSlot(
        name="Lights", category="Baseload",
        starting_state="electric",
        baseline_devices=[],
        electric_device=elec_dev,
    )

    cost = slot.step(1, _FLAT_ELEC, _FLAT_GAS, is_baseline_home=True)
    assert cost > 0
    assert len(elec_dev.history["cost"]) == 1


# ═════════════════════════════════════════════════════════════════════════════
# DeviceSlot — starting_state="none"
# ═════════════════════════════════════════════════════════════════════════════

def test_none_slot_zero_cost_in_baseline():
    """starting_state=none: baseline home always returns zero cost."""
    from journey import DeviceSlot
    model = mesa.Model()

    slot = DeviceSlot(
        name="EV Charger", category="Baseload",
        starting_state="none",
        baseline_devices=[],
        electric_device=_ev(model),
        swap_year=3,
    )

    for yr in range(1, 6):
        cost = slot.step(yr, _FLAT_ELEC, _FLAT_GAS, is_baseline_home=True)
        assert cost == 0.0, f"year {yr}: expected 0 cost in baseline, got {cost}"


def test_none_slot_zero_before_swap_year_in_journey():
    """starting_state=none: zero cost before swap_year in journey home."""
    from journey import DeviceSlot
    model = mesa.Model()
    ev_dev = _ev(model)

    slot = DeviceSlot(
        name="EV Charger", category="Baseload",
        starting_state="none",
        baseline_devices=[],
        electric_device=ev_dev,
        swap_year=3,
    )

    cost1 = slot.step(1, _FLAT_ELEC, _FLAT_GAS, is_baseline_home=False)
    cost2 = slot.step(2, _FLAT_ELEC, _FLAT_GAS, is_baseline_home=False)
    assert cost1 == 0.0
    assert cost2 == 0.0
    assert len(ev_dev.history["cost"]) == 0


def test_none_slot_electric_after_swap_year_in_journey():
    """starting_state=none: electric device activates at swap_year in journey home."""
    from journey import DeviceSlot
    model = mesa.Model()
    ev_dev = _ev(model)

    slot = DeviceSlot(
        name="EV Charger", category="Baseload",
        starting_state="none",
        baseline_devices=[],
        electric_device=ev_dev,
        swap_year=3,
        install_cost=800,
    )

    slot.step(1, _FLAT_ELEC, _FLAT_GAS, is_baseline_home=False)
    slot.step(2, _FLAT_ELEC, _FLAT_GAS, is_baseline_home=False)
    assert len(ev_dev.history["cost"]) == 0

    slot.step(3, _FLAT_ELEC, _FLAT_GAS, is_baseline_home=False)
    assert len(ev_dev.history["cost"]) == 1


# ═════════════════════════════════════════════════════════════════════════════
# DeviceSlot — compound baseline (has_cooling_baseline)
# ═════════════════════════════════════════════════════════════════════════════

def test_compound_baseline_both_devices_stepped():
    """Multiple baseline devices all get stepped each year."""
    from journey import DeviceSlot
    model = mesa.Model()

    furnace    = _furnace(model, lifespan=20)
    central_ac = _furnace(model, lifespan=15)  # stand-in for CentralAC

    slot = DeviceSlot(
        name="HVAC", category="HVAC_Heating",
        starting_state="gas",
        baseline_devices=[furnace, central_ac],
        electric_device=_hphvac(model),
        swap_year=None,
        has_cooling_baseline=True,
    )

    slot.step(1, _FLAT_ELEC, _FLAT_GAS)
    slot.step(2, _FLAT_ELEC, _FLAT_GAS)

    assert len(furnace.history["cost"])    == 2
    assert len(central_ac.history["cost"]) == 2


def test_compound_baseline_devices_age_independently():
    """Both baseline devices age each step; each triggers its own EOL CapEx."""
    from journey import DeviceSlot
    model = mesa.Model()

    furnace    = _furnace(model, age=4, lifespan=5,  installation_cost=6000)
    central_ac = _furnace(model, age=7, lifespan=10, installation_cost=4000)

    slot = DeviceSlot(
        name="HVAC", category="HVAC_Heating",
        starting_state="gas",
        baseline_devices=[furnace, central_ac],
        electric_device=_hphvac(model),
        swap_year=None,
        has_cooling_baseline=True,
    )

    slot.step(1, _FLAT_ELEC, _FLAT_GAS)   # furnace age 5→EOL; AC age 8, not EOL

    capex_costs = [c for _, c in slot.capex_events]
    assert 6000 in capex_costs
    assert 4000 not in capex_costs
    assert furnace.age == 0   # reset after EOL


# ═════════════════════════════════════════════════════════════════════════════
# DeviceSlot — CapEx events
# ═════════════════════════════════════════════════════════════════════════════

def test_swap_capex_logged_at_swap_year():
    """CapEx event recorded at swap_year with net_install_cost."""
    from journey import DeviceSlot
    model = mesa.Model()

    slot = DeviceSlot(
        name="HVAC", category="HVAC_Heating",
        starting_state="gas",
        baseline_devices=[_furnace(model)],
        electric_device=_hphvac(model),
        swap_year=3,
        install_cost=14000,
        rebate=3500,
    )

    slot.step(1, _FLAT_ELEC, _FLAT_GAS)
    assert len(slot.capex_events) == 0

    slot.step(2, _FLAT_ELEC, _FLAT_GAS)
    assert len(slot.capex_events) == 0

    slot.step(3, _FLAT_ELEC, _FLAT_GAS)
    assert len(slot.capex_events) == 1
    event_yr, event_cost = slot.capex_events[0]
    assert event_yr  == 3
    assert event_cost == pytest.approx(10500.0)   # 14000 - 3500

    slot.step(4, _FLAT_ELEC, _FLAT_GAS)
    assert len(slot.capex_events) == 1   # no second event


def test_eol_capex_logged_when_age_reaches_lifespan():
    """End-of-life CapEx recorded when a baseline device's age equals lifespan."""
    from journey import DeviceSlot
    model = mesa.Model()

    furnace = _furnace(model, age=4, lifespan=5, installation_cost=6000)

    slot = DeviceSlot(
        name="HVAC", category="HVAC_Heating",
        starting_state="gas",
        baseline_devices=[furnace],
        electric_device=None,
        swap_year=None,
    )

    slot.step(1, _FLAT_ELEC, _FLAT_GAS)   # age 4→5: triggers EOL

    assert len(slot.capex_events) == 1
    assert slot.capex_events[0][1] == 6000
    assert furnace.age == 0   # reset after EOL


def test_no_double_capex_swap_year_none():
    """No swap CapEx when swap_year is None — only EOL events apply."""
    from journey import DeviceSlot
    model = mesa.Model()

    furnace = _furnace(model, age=0, lifespan=20)

    slot = DeviceSlot(
        name="HVAC", category="HVAC_Heating",
        starting_state="gas",
        baseline_devices=[furnace],
        electric_device=None,
        swap_year=None,
        install_cost=14000,
        rebate=3500,
    )

    for yr in range(1, 6):
        slot.step(yr, _FLAT_ELEC, _FLAT_GAS)

    assert len(slot.capex_events) == 0   # lifespan=20, no EOL yet


# ═════════════════════════════════════════════════════════════════════════════
# JourneyHome — category history shape
# ═════════════════════════════════════════════════════════════════════════════

def test_journey_home_category_history_length():
    """cost_history_by_category has exactly n_steps entries per category after n steps."""
    from journey import DeviceSlot, JourneyHome, CATEGORY_ORDER
    model  = mesa.Model()
    n_steps = 7

    slots = [
        DeviceSlot(
            name="HVAC", category="HVAC_Heating",
            starting_state="gas",
            baseline_devices=[_furnace(model)],
            electric_device=_hphvac(model),
            swap_year=None,
        ),
        DeviceSlot(
            name="Lights", category="Baseload",
            starting_state="electric",
            baseline_devices=[],
            electric_device=_lights(model),
        ),
    ]

    jh = _make_jh(model, slots, n_years=n_steps)
    _advance(jh, n_steps)

    for cat in CATEGORY_ORDER:
        assert len(jh.cost_history_by_category[cat]) == n_steps, \
            f"Category {cat!r}: expected {n_steps} entries"


def test_journey_home_category_history_sum_then_append():
    """Two slots in same category produce exactly one history entry per step (sum-then-append fix)."""
    from journey import DeviceSlot, JourneyHome
    model  = mesa.Model()

    slots = [
        DeviceSlot(
            name="Dryer",   category="Baseload",
            starting_state="gas",
            baseline_devices=[_gas_dryer(model)],
            electric_device=_hp_dryer(model),
            swap_year=None,
        ),
        DeviceSlot(
            name="Lights", category="Baseload",
            starting_state="electric",
            baseline_devices=[],
            electric_device=_lights(model),
        ),
    ]

    jh = _make_jh(model, slots, n_years=5)
    _advance(jh, 3)

    assert len(jh.cost_history_by_category["Baseload"]) == 3


# ═════════════════════════════════════════════════════════════════════════════
# JourneyHome — identical configs produce same trajectory
# ═════════════════════════════════════════════════════════════════════════════

def test_default_config_journey_diverges_from_baseline():
    """Default slot config has HVAC=year 3, WH=year 5 → journey diverges from baseline."""
    from model import HESModel
    m = HESModel(n_years=5)
    m.run_all()
    # Swap CapEx events mean journey and baseline cumulative costs are not equal
    assert not np.isclose(m.journey_home.cumulative_opex, m.baseline_home.cumulative_opex)


# ═════════════════════════════════════════════════════════════════════════════
# JourneyHome — baseline costs more than journey after swaps
# ═════════════════════════════════════════════════════════════════════════════

def test_baseline_costs_more_than_journey_after_all_swaps():
    """
    With high gas rates and cheap electricity, baseline (gas) accumulates more
    opex than journey (swapped to electric from year 1).
    """
    from journey import DeviceSlot, JourneyHome

    model = mesa.Model()
    n_years = 10
    GAS_RATE  = 5.00   # $/therm — artificially high to guarantee gas > electric
    ELEC_RATE = 0.10   # $/kWh  — artificially low

    def _journey_slots():
        return [DeviceSlot(
            name="Dryer", category="Baseload",
            starting_state="gas",
            baseline_devices=[_gas_dryer(model, therms_per_cycle=0.22, cycles_per_week=5)],
            electric_device=_hp_dryer(model, kwh_per_cycle=1.8, cycles_per_week=5),
            swap_year=1,
        )]

    def _baseline_slots():
        return [DeviceSlot(
            name="Dryer", category="Baseload",
            starting_state="gas",
            baseline_devices=[_gas_dryer(model, therms_per_cycle=0.22, cycles_per_week=5)],
            electric_device=_hp_dryer(model, kwh_per_cycle=1.8, cycles_per_week=5),
            swap_year=None,   # never swap
        )]

    e = np.full((n_years, 12), ELEC_RATE)
    g = np.full((n_years, 12), GAS_RATE)

    from journey import JourneyHome
    jh = JourneyHome(model, _journey_slots(),  e, g, is_baseline_home=False)
    bh = JourneyHome(model, _baseline_slots(), e, g, is_baseline_home=True)

    for i in range(1, n_years + 1):
        model.steps = i
        jh.step()
        bh.step()

    assert bh.cumulative_opex > jh.cumulative_opex, (
        f"Baseline opex {bh.cumulative_opex:.2f} should exceed "
        f"journey opex {jh.cumulative_opex:.2f}"
    )


# ═════════════════════════════════════════════════════════════════════════════
# HomeConfig bedroom scaling — injected into HESModel devices
# ═════════════════════════════════════════════════════════════════════════════

def test_1br_lights_annual_kwh_is_half_reference():
    """1BR home: LightsAndPlugs receives annual_kwh = 600 (0.50 × 1200)."""
    from home_config import HomeConfig
    from model import HESModel

    m = HESModel(home_config=HomeConfig(num_bedrooms=1), n_years=1)

    lights_slot = next(s for s in m.journey_home.slots if s.name == "Lights and Appliances")
    annual_kwh = lights_slot.electric_device.annual_consumption()
    assert np.isclose(annual_kwh, 600.0), f"Expected 600 kWh, got {annual_kwh:.1f}"


def test_4br_hot_water_gallons_per_day():
    """4BR home: GasWaterHeater receives 75 gal/day (BEDROOM_SCALING[4])."""
    from home_config import HomeConfig
    from model import HESModel

    m = HESModel(home_config=HomeConfig(num_bedrooms=4), n_years=1)

    wh_slot = next(s for s in m.journey_home.slots if "Water" in s.name)
    wh_dev = wh_slot.baseline_devices[0]   # GasWaterHeater
    assert wh_dev.daily_gallons == 75, f"Expected 75 gal/day, got {wh_dev.daily_gallons}"


def test_bedroom_scaling_consistent_across_both_homes():
    """Both journey_home and baseline_home receive same bedroom-scaled values."""
    from home_config import HomeConfig
    from model import HESModel

    m = HESModel(home_config=HomeConfig(num_bedrooms=2), n_years=1)

    j_lights = next(s for s in m.journey_home.slots  if s.name == "Lights and Appliances")
    b_lights = next(s for s in m.baseline_home.slots if s.name == "Lights and Appliances")

    assert np.isclose(
        j_lights.electric_device.annual_consumption(),
        b_lights.electric_device.annual_consumption(),
    )


# ═════════════════════════════════════════════════════════════════════════════
# HESModel — DataCollector row count
# ═════════════════════════════════════════════════════════════════════════════

def test_datacollector_has_n_years_rows():
    """DataCollector produces exactly n_years rows after run_all()."""
    from model import HESModel

    m = HESModel(n_years=8)
    m.run_all()
    df = m.datacollector.get_model_vars_dataframe()
    assert len(df) == 8


def test_datacollector_columns_present():
    """DataCollector contains all expected reporter columns."""
    from model import HESModel

    m = HESModel(n_years=3)
    m.run_all()
    df = m.datacollector.get_model_vars_dataframe()

    expected = {
        "Journey Cum Cost", "Baseline Cum Cost",
        "Journey Annual Cost", "Baseline Annual Cost",
        "Opex Delta", "Elec Rate", "Gas Rate",
    }
    assert expected.issubset(set(df.columns))


def test_opex_delta_is_baseline_minus_journey():
    """Opex Delta == Baseline Cum Cost - Journey Cum Cost each step."""
    from model import HESModel

    m = HESModel(n_years=5)
    m.run_all()
    df = m.datacollector.get_model_vars_dataframe()

    computed_delta = df["Baseline Cum Cost"] - df["Journey Cum Cost"]
    np.testing.assert_allclose(df["Opex Delta"], computed_delta, rtol=1e-9)


def test_cumulative_opex_non_decreasing():
    """Cumulative opex only grows (or stays flat) — never shrinks."""
    from model import HESModel

    m = HESModel(n_years=10)
    m.run_all()
    df = m.datacollector.get_model_vars_dataframe()

    j_vals = df["Journey Cum Cost"].values
    b_vals = df["Baseline Cum Cost"].values
    assert all(j_vals[i] <= j_vals[i + 1] for i in range(len(j_vals) - 1))
    assert all(b_vals[i] <= b_vals[i + 1] for i in range(len(b_vals) - 1))
