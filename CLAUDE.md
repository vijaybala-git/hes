# WhyWatt — Project Brain (Claude Code reads this automatically)

> Keep this file current after each phase. Last updated: Phase 2 spec finalised.

---

## What this project is

**WhyWatt?** — A home electrification cost simulator for California community advocates.
Shows the long-term cost of a user-defined electrification journey vs. doing nothing.
Primary audience: electrification advocates running sessions with homeowners.

**Former name:** HES (Home Electrification Simulator).
**Stack:** Python 3.11+, Mesa 3.x, Solara, Matplotlib, NumPy, Pandas.
**Run with:** `solara run src/app.py`

---

## Current phase: PHASE 2 — Objective 0 (not started)

See `docs/Phase2_Spec.md` for full scope and Claude Code prompts per objective.
Implement objectives in order: 0 → 1 → 2 → 3 → 4 → 5 → 6.
Do not start Objective N+1 until all tests for N pass.

---

## Completed phases

- **Phase 1:** Mesa agent framework, dual JSON home configs, EnergyPrice class,
  Solara EN-ROADS-style UI, 6 chart types, 42 unit tests. Internal unit: MMBtu (now eliminated).

---

## Core architecture decisions (do not re-litigate)

| Decision | Choice | Reason |
|----------|--------|--------|
| Simulation framework | Mesa annual steps | Working in Phase 1 |
| UI framework | Solara | Python-native, already working |
| Journey model | Two JourneyHome instances | journey vs do-nothing is the core story |
| Device interface | monthly_consumption() → (12,) array | uniform interface, variable fidelity |
| Computation methods | SeasonalDevice / PhysicsDevice / ScheduleDevice | upgrade path without interface change |
| HVAC/WH granularity | Monthly sub-calculation inside annual step | preserves seasonal accuracy |
| Rate data | RateLoader from CPUC/PG&E published periods | historically grounded |
| Future rate projection | CAGR from projection block in rate JSON | auditable, scenario-based |
| Internal units | kWh (electric) / therms (gas) — NO MMBtu anywhere | physical accuracy |
| Display conversion | 1 therm = 29.3 kWh, output only | never in simulation internals |
| Backward compat | None — clean break from Phase 1 | simplicity |
| Dual scenario | Second HESModel instance, lazy | clean separation |
| Uncertainty | Deterministic through Phase 3 | Monte Carlo deferred |

---

## Key data constants

**Bay Area TMY3 monthly values (San Jose Mineta, Station 724945):**
```
monthly_hdd_65f:        [420, 340, 260, 140, 50, 10, 0, 0, 10, 80, 220, 380]  → sum 1910
monthly_cdd_65f:        [0, 0, 0, 5, 20, 60, 90, 85, 55, 20, 5, 0]           → sum 340
monthly_inlet_water_f:  [54, 54, 55, 57, 60, 63, 65, 66, 65, 62, 58, 55]
setpoint_water_f:       120
daily_hot_water_gal:    65
UA_poor:    650 BTU/hr/°F
UA_average: 500 BTU/hr/°F
UA_good:    350 BTU/hr/°F
```

**IMPORTANT:** Annual HDD for Bay Area is 1,910 — NOT 2,600 (that is the national average).
All validation targets in the spec use 1,910.

**PG&E 2025 base rates:**
```
Electricity (E-1):  $0.386/kWh   (Cal Advocates Q2 2025 report)
Gas (G-1):          $2.08/therm  (PG&E Advice Letter 5014-G1, Jan 2025)
```

**Escalation scenarios:**
```
conservative:  elec +4%/yr,  gas +4%/yr
moderate:      elec +7%/yr,  gas +8%/yr   ← default (matches 10-yr historical)
stress (CEC):  elec +10%/yr, gas +12%/yr
```

---

## Validation targets (tests must verify these)

| Device | Config | Expected | Tolerance |
|--------|--------|---------|-----------|
| GasFurnace | UA=500, AFUE=0.80, HDD=1910 | ~286 therms/yr | ±5% |
| HeatPumpHVAC heating | UA=500, COP=3.5, HDD=1910 | ~1,930 kWh/yr | ±5% |
| HeatPumpHVAC cooling | UA=500, SEER=22, CDD=340 | ~550 kWh/yr | ±5% |
| GasWaterHeater | UEF=0.65, 65 gal/day | ~210 therms/yr | ±5% |
| HeatPumpWaterHeater | UEF=3.5, 65 gal/day | ~1,050 kWh/yr | ±5% |
| GasDryer | 0.22 therms/cycle, 5/wk | ~57 therms/yr | ±2% |
| HeatPumpDryer | 1.8 kWh/cycle, 5/wk | ~468 kWh/yr | ±2% |
| EVCharger | default schedule | ~3,540 kWh/yr | ±5% |

---

## Module map (Phase 2 target state)

```
src/
  devices/
    __init__.py
    base.py           EnergyConsumer abstract base — monthly_consumption() interface
    seasonal.py       SeasonalDevice + GasDryer, HeatPumpDryer, LightsAndPlugs etc.
    physics.py        PhysicsDevice + GasFurnace, HeatPumpHVAC, GasWH, HPWH
    schedule.py       ScheduleDevice + EVCharger
  rate_loader.py      RateLoader — CPUC published periods + CAGR projection
  journey.py          DeviceSlot dataclass + JourneyHome Mesa agent
  model.py            HESModel — two JourneyHome instances, dual scenario
  app.py              Solara UI — Journey Planner, WhyWatt branding
data/
  rates/
    pge_elec_e1.json      historical E-1 periods + projection config
    pge_gas_g1.json       historical G-1 periods + projection config
  climate/
    bayarea_tmy3.json     monthly HDD, CDD, water temps, UA map
  appliances/
    electrical_defaults.json
    gas_defaults.json
    ev_schedule_default.json
  homes/
    journey_slots_default.json   default DeviceSlot config for Bay Area home
docs/
  assets/
    whywatt_logo.png    (placeholder)
    group_logo.png      (placeholder)
  Phase2_Spec.md        full spec — read before implementing
  Phase1_Goals.md       history — do not modify
tests/
  test_rate_loader.py   Objective 1
  test_devices.py       Objective 2
  test_journey.py       Objective 3
  test_dual_scenario.py Objective 5
```

**Deleted in Phase 2:**
- src/energy_consumer.py → replaced by src/devices/
- src/energy_price.py    → replaced by src/rate_loader.py
- data/baseline_home.json, data/electrified_home.json → replaced by data/homes/
- tests/test_energy_consumer.py, tests/test_energy_price.py → superseded

---

## Hard rules — enforce always

1. `grep -r "MMBtu" src/ data/ tests/` must return zero results at all times
2. Devices never read data files — climate constants and rates are injected at construction
3. `monthly_consumption()` always returns shape `(12,)` — no exceptions
4. `cost_history_by_category` appends exactly once per step (sum-then-append pattern)
5. Logo files use `os.path.exists()` guard — missing logo must not crash the app

---

## Questions to resolve before Objective 6 UI work

- [ ] Should swap_year UI use a slider or a year-picker dropdown?
- [ ] Should "not planning to swap" be a checkbox or a special "Never" option in the slider?
- [ ] Gas cooktop — add to baseline_home slots or keep just furnace/WH/dryer for Phase 2?
- [ ] EV charger — show in Journey Planner even when not swapping (baseline has no EV)?
- [ ] Income-qualified rebate toggle (CARE / non-CARE affects rebate amounts)?
