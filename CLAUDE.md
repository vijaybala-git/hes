# WhyWatt — Project Brain (Claude Code reads this automatically)

> Keep this file current after each phase. Last updated: 2026-09-24 — **Phase 7 closed** (real solar,
> battery physics, URDB time-of-use pricing, projection methods). §6 NREL load profiles and the
> gas-rate base review done → next: Beta release.

---

## What this project is

**WhyWatt?** — A home electrification cost simulator for California community advocates.
Shows the long-term cost of a user-defined electrification journey vs. doing nothing.
Primary audience: electrification advocates running sessions with homeowners.

**Former name:** HES (Home Electrification Simulator).
**Stack:** Python 3.11+, Mesa 3.x, Solara, Matplotlib, NumPy, Pandas.
**Run with:** `solara run src/app.py`

---

## Current phase: PHASE 7 CLOSED → Beta prep

Phase 7 is **complete and closed** as of 2026-09-24. See `docs/Phase7_Spec.md` (Definition of done,
"Landed" notes per section) for the full delivery record.

Before the Beta release (each on its own branch off `main`):
- ✅ **§6 NREL End-Use Load Profiles** (branch `feat/nrel-end-use-load-profiles`,
  `docs/NREL_LoadProfiles_Plan.md`) — the hourly energy balance and URDB per-device rates use NREL
  ResStock 2025.1 shapes per CEC zone × end use × month × 24 clock hours; heat pump split into
  heating + cooling; EV = managed L2 charging. `device_load_shapes.json` now feeds legacy ACC only.
  Golden re-baselined (< 2 % moves, no sign / payback change).
- ✅ **Gas-rate base review** (branch `fix/gas-rate-base-review`, `docs/GasRateBase_Review_Plan.md`)
  — the $2.08 "G-1" figure was PG&E's CARE baseline charge; the WhyWatt gas curves now follow the CEC
  delivered price ($2.649 nominal 2025, ≈ EIA's $2.66). Model results unchanged (shape only).

- ✅ **Default → WhyWatt Conservative** (branch `feat/default-projection-method`, 2026-09-24):
  journey A's electricity + gas default to the WhyWatt Conservative projection on the home's current
  rate (PG&E → URDB E-TOU-C). Solar / battery stay unplanned; only HVAC + water heater planned;
  Social & Health off. Regression case 01 pins My Utility (`cagr_flat`) for coverage; golden
  re-baselined.

Other post-Phase-7 items (not gating Beta): independent battery, SCE re-harvest, `SolarBatteryConfig` shim retirement, solar wave 2 (PCE /
SJCE), beyond-CA data.

---

## Completed phases

- **Phase 1:** Mesa agent framework, dual JSON home configs, EnergyPrice class,
  Solara EN-ROADS-style UI, 6 chart types, 42 unit tests. Internal unit: MMBtu (now eliminated).
- **Phases 2–6:** see `docs/Phase2_Spec.md` … `docs/Phase6_Spec.md` (journey model, ZIP-driven
  climate, EIA per-utility rates, UI redesign, regression harness, share links, rate-projection
  hand-off).
- **Phase 7 (closed 2026-09-24):** offline PVWatts per-ZIP solar (zone fallback, clock time);
  hourly representative-day energy balance with two battery modes (Self-powered / Cost-saving,
  cheaper per month); Tesla Powerwall 3 battery defaults; URDB time-of-use plans (PG&E, SDG&E;
  SCE quarantined) priced with tiers + fixed charge; "current energy rate × projection growth"
  (WhyWatt Conservative / Moderate / Stress, EIA Pacific) with EIA 2025 starting rates; NEM 3.0
  export credit = hourly ACC by calendar year; municipal utilities resolved by geography; UI:
  utilities line, Current Energy Rate / Projection Method cards, Solar / Battery / Panel cards in
  the Journey, unified Plan row; charts R.1/R.2 (four projection curves), EU.9, EU.10, R.6;
  regression suite 32 base cases (PG&E plans × projections, gas-isolation set).

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
| Home config | HomeConfig dataclass injected into HESModel | single source of truth; Phase 3 JSON persistence |
| DeviceSlot baseline | baseline_devices: list (not single device) | HVAC can have furnace + AC as separate aging units |
| Starting state | "gas" / "electric" / "none" per slot | models already-done swaps; "do nothing" preserves them |
| Bedroom scaling | Multiplier table in BEDROOM_SCALING dict | DOE proxy; 3BR is TMY3 reference |
| HVAC compound | has_cooling_baseline flag per slot | Bay Area default is no AC; adding heat pump is a clean add |

---

## Key data constants

**Climate — ZIP-driven CEC zones (Phase 4 §1).** The model resolves `zip_code` → CEC
Building Climate Zone → monthly HDD/CDD/inlet-water from OneBuilding **TMYx 2011-2025** EPW
files (16 reference stations). Built offline by `scripts/build_climate_db.py` into
`data/climate/tmy3_zones.json`; raw sources snapshotted (with sha256) under
`data/climate/sources/`. CZ4 (San Jose, station 724945) is the default zone:
```
CZ4 annual_hdd_65f: 2242   annual_cdd_65f: 554   (TMYx 2011-2025, daily-mean base 65°F)
setpoint_water_f: 120   daily_hot_water_gal: 65 (3BR)
UA_poor: 650   UA_average: 500   UA_good: 350   BTU/hr/°F  @ 1,800 sq ft (home_config.UA_BY_INSULATION)
```

> **UA scales with home size (Phase 5.5 Fix 1).** The UA_BY_INSULATION values above are the
> reference-size figures; the live model uses `compute_ua(quality, sq_ft) = base × sq_ft /
> UA_REFERENCE_SQFT` (UA_REFERENCE_SQFT = 1,800). So furnace/AC energy now tracks square
> footage, and a 1,800 sq ft "average" home still resolves to UA 500 (defaults unchanged).
> `tests/test_devices.py` still injects UA directly, so the formula regression targets below
> are unaffected.

> **Re-baselined in Phase 4.** Phase 2's hardcoded "Bay Area HDD = 1,910 / CDD = 340" was an
> undocumented hand estimate — no real San Jose weather file produces it (NREL TMY3 ≈ 2,501;
> TMYx 2011-2025 = 2,242). The live model now uses authoritative per-zone TMYx data. The
> legacy `data/climate/bayarea_tmy3.json` (1,910 HDD) is kept ONLY as a fixed reference
> climate for the device-formula regression tests in `tests/test_devices.py` — it validates
> the consumption *formulas* at a stable input, and is no longer "Bay Area actual."

**Bedroom scaling (BEDROOM_SCALING dict, 3BR = reference):**
```
bedrooms:  1      2      3      4      5
baseload:  0.50×  0.83×  1.00×  1.17×  1.33×   of 1200 kWh/yr
hw_gal:    30     50     65     75     85       gal/day
```
Source: DOE/ENERGY STAR occupancy proxy. Applied by HESModel at init; devices receive injected scalars.

**PG&E 2025 base rates:**
```
Electricity (E-1):  $0.386/kWh   (Cal Advocates Q2 2025 report)
Gas (G-1):          $2.08/therm  ⚠ NOT the typical rate — this "G-1" series (pge_gas_g1.json,
                    used only by the legacy ACC mode) is PG&E's CARE baseline charge without the
                    public-purpose surcharge. PG&E's 2025 bundled residential average is $2.885
                    non-CARE / $2.275 CARE (AL 5014-G1); EIA-176 effective $2.66; CEC delivered
                    $2.649 (the projection curves' base since 2026-09-24).
```

**Rate model (current):** the default is the **WhyWatt Conservative** projection method (since
2026-09-24; before that My Utility — `cagr_flat`: EIA per-utility 2024 rate × fixed %/yr, still
selectable and pinned in regression case 01). Scenario B defaults stay ACC. Projection
methods price *current energy rate × S[y]/S[anchor]*: current rate = URDB plan (PG&E E-TOU-C,
effective 2026) → utility EIA 2025 (PG&E elec $0.3991/kWh; gas $2.66/therm = EIA-176 2024 × CA
ratio 1.1499, bridged) → EIA Pacific ($0.242 / $1.99) when no utility. Battery default = Tesla
Powerwall 3 (13.5 kWh, 89%, 5 kW charge / 11.5 kW discharge). NEM 3.0 export = hourly ACC 2024
(CZ4) for each calendar year (`data/rates/nbt_export_acc.json`).

**Escalation scenarios (legacy fixed-%/yr presets):**
```
conservative:  elec +4%/yr,  gas +4%/yr
moderate:      elec +7%/yr,  gas +8%/yr   ← default (matches 10-yr historical)
stress (CEC):  elec +10%/yr, gas +12%/yr
```

---

## Validation targets (tests must verify these)

> These validate the consumption **formulas** at a fixed reference climate (HDD=1910 /
> CDD=340, the legacy `bayarea_tmy3.json`), independent of the live ZIP-driven zone data
> (Phase 4). `tests/test_devices.py` uses this fixed reference so formula regressions stay
> stable; the live model uses real per-zone TMYx values (e.g., CZ4 = 2242/554).

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
  home_config.py      HomeConfig dataclass + BEDROOM_SCALING dict
  rate_loader.py      RateLoader — CPUC published periods + CAGR projection
  journey.py          DeviceSlot dataclass + JourneyHome Mesa agent
  model.py            HESModel — accepts HomeConfig, two JourneyHome instances, dual scenario
  app.py              Solara UI — Journey Planner, Home Profile, WhyWatt branding
data/
  rates/
    pge_elec_e1.json      historical E-1 periods + projection config
    pge_gas_g1.json       historical G-1 periods + projection config
  climate/
    bayarea_tmy3.json     monthly HDD, CDD, water temps, UA map, bedroom_scaling table
  appliances/
    electrical_defaults.json
    gas_defaults.json
    ev_schedule_default.json
  homes/
    journey_slots_default.json   default DeviceSlot configs (with starting_state)
    home_config_default.json     default HomeConfig values (Phase 3: user save/load)
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

**Added in Phase 7** (see `docs/Phase7_Spec.md` → Module / data deltas):
```
src/  solar_loader.py  dispatch.py  urdb_rates.py  starting_rates.py  nbt_export.py
      battery_defaults.py
data/ solar/pvwatts_zip.json  rates/urdb_tou.json  rates/starting_rates.json
      rates/nbt_export_acc.json  appliances/battery_defaults.json
scripts/ build_pvwatts.py  build_urdb*.py  build_starting_rates.py  build_nbt_export.py
      build_battery_defaults.py  ca_munis.py (+ muni rule in build_zip_utility_map.py)
§6:   src/load_profiles.py (HomeConfig.load_profiles)  data/loads/end_use_profiles.json
      data/loads/sources/manifest.json  scripts/build_load_profiles.py (needs pyarrow from requirements-build.txt;
      cache data/loads/.cache/ git-ignored)
```
Interpreter: `.venv/Scripts/python.exe` (the base `python` has no deps). Regression:
`scripts/run_regression.py` (`--update` re-blesses golden).

**Architecture explainer** (`docs/explainer/`, static site → www.whywatt.org/explainer/): its charts
read JS snapshots in `docs/explainer/assets/` — refresh with `scripts/build_explainer_data.py` after
rebuilding climate / PVWatts / NREL / projection / URDB / ACC data; publish with
`scripts/publish-explainer.ps1` (dry run; `-Push` commits + pushes the Pages repo clone).

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
6. `HomeConfig` is the only object that carries home details — no loose parameters alongside it
7. `starting_state` is always preserved when constructing the "do nothing" baseline —
   never reset already-electric slots to gas
8. `baseline_devices` is always a list (even if length 1) — never a single device reference
9. HVAC install cost covers the full heat pump (heating + cooling) as one event — never split

---

## UI design decisions (resolved for Objective 6)

| Question | Decision |
|---|---|
| Swap year control | Slider (year 1–25), shows calendar year label |
| "Not planning to swap" | Checkbox disables slider; row collapses cost fields |
| Gas cooktop in Phase 2 | Yes — included as a slot with `starting_state="gas"` |
| EV charger display | Always shown; `starting_state="none"` renders as "—" / "Add" |
| Income-qualified rebates | Deferred to Phase 3 |
| HVAC cooling in baseline | `has_cooling_baseline` toggle (default false for Bay Area) |
| Baseline home label | "Do nothing" (not "Gas home") |
| Journey home label | "Your journey" (not "Electric home") |
