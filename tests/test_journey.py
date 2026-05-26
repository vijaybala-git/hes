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
# HomeConfig baseload formula + hot water scaling — injected into HESModel devices
# ═════════════════════════════════════════════════════════════════════════════

def test_1br_lights_annual_kwh_uses_formula():
    """1BR/1800sqft home: LightsAndPlugs receives formula value (1800×0.45 + 1×200 + 300 = 1310)."""
    from home_config import HomeConfig, compute_baseload_kwh
    from model import HESModel

    m = HESModel(home_config=HomeConfig(num_bedrooms=1), n_years=1)

    lights_slot = next(s for s in m.journey_home.slots if s.name == "Lights and Appliances")
    annual_kwh = lights_slot.electric_device.annual_consumption()
    expected = compute_baseload_kwh(1800, 1, 300)   # formula_after for default HomeConfig
    assert np.isclose(annual_kwh, expected), f"Expected {expected:.1f} kWh, got {annual_kwh:.1f}"


def test_4br_hot_water_gallons_per_day():
    """4BR home: GasWaterHeater receives 75 gal/day (HOT_WATER_GAL_PER_DAY[4])."""
    from home_config import HomeConfig
    from model import HESModel

    m = HESModel(home_config=HomeConfig(num_bedrooms=4), n_years=1)

    wh_slot = next(s for s in m.journey_home.slots if "Water" in s.name)
    wh_dev = wh_slot.baseline_devices[0]   # GasWaterHeater
    assert wh_dev.daily_gallons == 75, f"Expected 75 gal/day, got {wh_dev.daily_gallons}"


def test_formula_baseload_consistent_across_both_homes():
    """Both journey_home and baseline_home receive same formula-based electric_device values."""
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


# ═════════════════════════════════════════════════════════════════════════════
# §11.7 — per-slot history dicts
# ═════════════════════════════════════════════════════════════════════════════

def test_cost_history_by_slot_length():
    """Each slot has exactly n_years entries in cost_history_by_slot."""
    from model import HESModel
    model = HESModel(n_years=10)
    model.run_all()
    for slot in model.journey_home.slots:
        h = model.journey_home.cost_history_by_slot[slot.name]
        assert len(h) == 10, f"{slot.name}: expected 10, got {len(h)}"


def test_consumption_history_by_slot_fuel_type():
    """Before swap year, HVAC fuel is gas; at and after swap year, fuel is electricity."""
    from model import HESModel
    model = HESModel(n_years=10)
    model.run_all()
    jh = model.journey_home
    hvac_slot = next(s for s in jh.slots if s.name == "HVAC")
    fuels = jh.fuel_history_by_slot["HVAC"]
    swap = hvac_slot.swap_year   # default 3
    if swap:
        assert all(f == "gas"         for f in fuels[:swap - 1])
        assert all(f == "electricity" for f in fuels[swap - 1:])


def test_kwh_equivalent_drops_at_swap():
    """Total kWh-equivalent HVAC consumption drops at swap year (COP > 1)."""
    from model import HESModel
    model = HESModel(n_years=10)
    model.run_all()
    jh = model.journey_home
    raw  = jh.consumption_history_by_slot["HVAC"]
    fuel = jh.fuel_history_by_slot["HVAC"]
    kwh_eq = [r * 29.3 if f == "gas" else r for r, f in zip(raw, fuel)]
    hvac_slot = next(s for s in jh.slots if s.name == "HVAC")
    swap = hvac_slot.swap_year
    if swap and swap < 10:
        pre_avg  = sum(kwh_eq[:swap])    / swap
        post_avg = sum(kwh_eq[swap:]) / (10 - swap)
        assert post_avg < pre_avg, "Heat pump must use less kWh-equivalent than gas furnace"


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


# ── §12.8 Baseload formula tests ──────────────────────────────────────────────

def test_baseload_formula_replaces_bedroom_scaling():
    """Formula output matches hand calculation."""
    from home_config import compute_baseload_kwh
    result = compute_baseload_kwh(sq_ft=1800, bedrooms=3, constant=500)
    expected = 1800 * 0.45 + 3 * 200 + 500   # = 1910
    assert abs(result - expected) < 1.0


def test_baseload_formula_varies_with_sqft():
    """Larger home has higher baseload."""
    from home_config import compute_baseload_kwh
    small = compute_baseload_kwh(sq_ft=1000, bedrooms=2, constant=500)
    large = compute_baseload_kwh(sq_ft=2500, bedrooms=2, constant=500)
    assert large > small


def test_hot_water_gallons_still_bedroom_based():
    """Hot water scaling uses bedroom lookup, not baseload formula."""
    from home_config import HOT_WATER_GAL_PER_DAY
    assert HOT_WATER_GAL_PER_DAY[3] == 65
    assert HOT_WATER_GAL_PER_DAY[1] == 30
    assert HOT_WATER_GAL_PER_DAY[5] == 85


def test_baseload_efficiency_swap_reduces_cost():
    """At swap year, journey baseload cost drops vs baseline (same rates, fewer kWh)."""
    from model import HESModel
    from home_config import HomeConfig
    config = HomeConfig(
        square_footage=1800, num_bedrooms=3,
        baseload_constant_before=500,
        baseload_constant_after=300,
        baseload_swap_year=2,
        baseload_install_cost=400,
    )
    model = HESModel(home_config=config, n_years=10)
    model.run_all()
    jh = model.journey_home
    bh = model.baseline_home
    # Compare same year (year 3) — journey uses formula_after, baseline uses formula_before
    journey_yr3  = jh.cost_history_by_slot["Lights and Appliances"][2]
    baseline_yr3 = bh.cost_history_by_slot["Lights and Appliances"][2]
    assert journey_yr3 < baseline_yr3, \
        "Journey baseload cost (formula_after) must be less than baseline (formula_before) at same rates"


def test_baseline_home_always_uses_formula_before():
    """Do-nothing baseline never applies the efficiency upgrade."""
    from model import HESModel
    from home_config import HomeConfig
    config = HomeConfig(
        square_footage=1800, num_bedrooms=3,
        baseload_constant_before=500,
        baseload_constant_after=300,
        baseload_swap_year=2,
    )
    model = HESModel(home_config=config, n_years=10)
    model.run_all()
    bh = model.baseline_home
    costs = bh.cost_history_by_slot["Lights and Appliances"]
    assert all(costs[i] <= costs[i + 1] for i in range(len(costs) - 1)), \
        "Baseline baseload costs must rise monotonically (no efficiency drop)"


# ── §13.10 Appliance detail spec tests ────────────────────────────────────────

import copy as _copy

def _default_slot_configs():
    """Load the default slot configs from JSON."""
    import json, pathlib
    path = pathlib.Path(__file__).parent.parent / "data/homes/journey_slots_default.json"
    return json.loads(path.read_text())


def _slots_with(device_class: str, **overrides) -> list:
    """Return default slot configs with overrides applied to the named device class."""
    configs = _copy.deepcopy(_default_slot_configs())
    for slot in configs:
        for dev in slot.get("baseline_devices", []):
            if dev.get("class") == device_class:
                dev.update(overrides)
        ed = slot.get("electric_device") or {}
        if ed.get("class") == device_class:
            ed.update(overrides)
    return configs


def test_slot_uses_configured_furnace_afue():
    """Changing AFUE in slot config changes furnace consumption."""
    from model import HESModel
    model_80 = HESModel(slot_configs=_slots_with("GasFurnace", afue=0.80))
    model_95 = HESModel(slot_configs=_slots_with("GasFurnace", afue=0.95))
    model_80.run_all()
    model_95.run_all()
    hvac_80 = model_80.baseline_home.consumption_history_by_slot["HVAC"][0]
    hvac_95 = model_95.baseline_home.consumption_history_by_slot["HVAC"][0]
    assert hvac_95 < hvac_80, "Higher AFUE furnace must use less gas"


def test_slot_uses_configured_dryer_loads():
    """Dryer loads/week drives annual therms proportionally."""
    from model import HESModel
    model_5  = HESModel(slot_configs=_slots_with("GasDryer", cycles_per_week=5))
    model_10 = HESModel(slot_configs=_slots_with("GasDryer", cycles_per_week=10))
    model_5.run_all()
    model_10.run_all()
    dryer_5  = model_5.baseline_home.consumption_history_by_slot["Dryer"][0]
    dryer_10 = model_10.baseline_home.consumption_history_by_slot["Dryer"][0]
    assert abs(dryer_10 / dryer_5 - 2.0) < 0.05, "Double loads must double therms"


def test_hot_water_gallons_override():
    """daily_gallons_override in slot config overrides bedroom default."""
    from model import HESModel
    model_65  = HESModel(slot_configs=_slots_with("GasWaterHeater", daily_gallons_override=65))
    model_100 = HESModel(slot_configs=_slots_with("GasWaterHeater", daily_gallons_override=100))
    model_65.run_all()
    model_100.run_all()
    wh_65  = model_65.baseline_home.consumption_history_by_slot["Water Heater"][0]
    wh_100 = model_100.baseline_home.consumption_history_by_slot["Water Heater"][0]
    assert wh_100 > wh_65, "More gallons/day must mean higher gas consumption"


# ── §15.4 Panel Upgrade (CapExOnlySlot) tests ────────────────────────────────

def test_panel_upgrade_capex_at_install_year():
    """Panel upgrade CapEx fires at install_year, not before or after."""
    from journey import CapExOnlySlot
    from model import HESModel

    slot = CapExOnlySlot(name="Electrical Panel",
                         install_cost=3000, rebate=0,
                         lifespan=25, install_year=1)
    model = HESModel(n_years=10, capex_only_slots=[slot])
    model.run_all()
    assert model.journey_home.capex_by_year.get(1, 0) >= 3000
    assert model.journey_home.capex_by_year.get(2, 0) == 0


def test_panel_upgrade_absent_from_baseline():
    """Panel upgrade does not appear in baseline home CapEx."""
    from journey import CapExOnlySlot
    from model import HESModel

    slot = CapExOnlySlot(name="Electrical Panel",
                         install_cost=3000, install_year=1)
    model = HESModel(n_years=10, capex_only_slots=[slot])
    model.run_all()
    assert model.baseline_home.capex_by_year.get(1, 0) == 0


def test_panel_upgrade_eol_replacement():
    """End-of-life replacement fires at install_year + lifespan."""
    from journey import CapExOnlySlot
    from model import HESModel

    slot = CapExOnlySlot(name="Electrical Panel",
                         install_cost=3000, lifespan=5, install_year=1)
    model = HESModel(n_years=10, capex_only_slots=[slot])
    model.run_all()
    assert model.journey_home.capex_by_year.get(6, 0) >= 3000  # yr 1 + lifespan 5
