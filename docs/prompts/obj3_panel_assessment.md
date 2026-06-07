# WhyWatt Phase 3 — Objective 3: ElectricalSpec + Panel Load Assessment

## Context

WhyWatt is a home electrification cost simulator (Python 3.11+, Mesa 3.x, Solara,
Matplotlib). Run with `solara run src/app.py`. Tests use pytest (`tests/conftest.py`
provides a `mock_model` fixture; run with `python -m pytest tests/`).

Read these spec sections before starting:
- `docs/Phase3_Spec.md` §2.5 (Electrical Specifications)
- `docs/Phase3_Spec.md` §5 (Panel Load Assessment)

This is **Objective 3 of 6**. It adds electrical nameplate data to devices and a NEC
panel-load assessment. It does **not** change any energy or cost math — simulation
results (kWh, therms, $) must be byte-identical to before.

**Tag `phase2` marks Phase 2. Objective 1 (help system) is already committed on `main`.**

---

## Resolved Design Decisions (these override the spec where they differ)

1. **Electrical attributes live on the device classes.** Add `circuit_volts`,
   `circuit_amps`, and `continuous` to the `EnergyConsumer` base class (default 0/0/False
   → `rated_va = 0` for any device that doesn't set them, i.e. all gas devices).
   Electric device defaults come from `data/appliances/electrical_defaults.json`, threaded
   through `_make_device()`. `PanelAssessor` reads `device.rated_va` etc. off the active device.

2. **Device sizing follows a tiered rule:**
   - **NEC general load** is *derived* from the existing `square_footage` input
     (`3 VA/sqft`) — no new control.
   - **HVAC tonnage** has no sqft→tonnage formula built yet, so it gets a **slider**
     (2.0–5.0 ton, step 0.5, default 3.0). Tonnage maps to amps by `amps = tonnage × 10`
     (so VA = tonnage × 10 × 240). Table: 2.0t=20A, 2.5t=25A, 3.0t=30A, 3.5t=35A,
     4.0t=40A, 4.5t=45A, 5.0t=50A.
   - **EV charger amps** = a **selector** (32A standard / 48A fast home), default 32A.
   - **Induction, HPWH, Dryer amps** = editable numeric input in their detail panel,
     prefilled with the JSON default (induction 40A, HPWH 15A, dryer 30A).
   - This **supersedes the "read-only in Phase 3" note** in §2.5.2 — base variables are editable.

3. **Panel assessment covers the JOURNEY HOME ONLY**, never the do-nothing baseline.
   - Walk the journey home's actual active electric devices **each year** (year 1 → n_years).
   - Existing central AC counts whenever present (journey keeps it until/unless HVAC is
     electrified; if no HVAC swap is planned, AC counts every year).
   - Already-electric appliances count from year 1. "none" appliances (EV) count only
     after their swap year.
   - `CentralAC` therefore needs an electrical spec: default 240V × 20A = 4,800 VA.

4. **Cooktop in the NEC calc uses the fixed 8,000 VA range allowance** (NEC 220.55),
   NOT the induction nameplate. The induction nameplate (9,600 VA at 40A) is shown in
   the **detail panel display only**. These are two different numbers for two purposes.

5. **Solar is excluded** from the load sum entirely (it's a source, not a load — §5.4).

6. **Baseload "Effective A"** display is informational only and does NOT feed the
   PanelAssessor (which uses the NEC 3 VA/sqft general-load formula).

---

## What to Build

### Deliverable 1 — Electrical attributes on devices

**`src/devices/base.py`** — add three optional kwargs to `EnergyConsumer.__init__`:

```python
def __init__(self, model, *, lifespan=15, installation_cost=0.0, age=0,
             circuit_volts: int = 0, circuit_amps: int = 0, continuous: bool = False):
    ...
    self.circuit_volts = circuit_volts
    self.circuit_amps  = circuit_amps
    self.continuous    = continuous

@property
def rated_va(self) -> float:
    return float(self.circuit_volts * self.circuit_amps)
```

Gas devices never set these → `rated_va == 0`. No subclass changes needed unless a class
wants a different default; the values flow in from JSON via `_make_device()`.

**`src/model.py` `_make_device()`** — pass `circuit_volts`, `circuit_amps`, `continuous`
through to every device constructor when present in the device config dict. (Find
`_make_device` and add these to the kwargs it forwards — they are accepted by the base
class so all device classes accept them.)

### Deliverable 2 — `data/appliances/electrical_defaults.json`

```json
{
  "HeatPumpHVAC":        {"circuit_volts": 240, "circuit_amps": 30, "continuous": true},
  "CentralAC":           {"circuit_volts": 240, "circuit_amps": 20, "continuous": false},
  "HeatPumpWaterHeater": {"circuit_volts": 240, "circuit_amps": 15, "continuous": false},
  "PhysicsEVCharger":    {"circuit_volts": 240, "circuit_amps": 32, "continuous": true},
  "EVCharger":           {"circuit_volts": 240, "circuit_amps": 32, "continuous": true},
  "InductionCooktop":    {"circuit_volts": 240, "circuit_amps": 40, "continuous": false},
  "HeatPumpDryer":       {"circuit_volts": 240, "circuit_amps": 30, "continuous": false}
}
```

Gas devices and `LightsAndPlugs` are intentionally absent → no electrical spec.

`_build_slot_configs()` in `app.py` (and `_build_slots`/model defaults) should merge these
defaults into each electric device's config dict, but **UI-set values take precedence**
(see Deliverable 5). Suggested approach: a small helper `_electrical_defaults(class_name)`
that loads the JSON once and returns the dict, merged into the device config unless the
reactive UI value overrides it.

### Deliverable 3 — `src/panel_assessor.py`

```python
from dataclasses import dataclass

# NEC constants
GENERAL_VA_PER_SQFT   = 3
SMALL_APPLIANCE_VA    = 3000   # two 1500 VA circuits
LAUNDRY_VA            = 1500
DEMAND_THRESHOLD_VA   = 10000
DEMAND_FACTOR_ABOVE   = 0.40
EV_CONTINUOUS_FACTOR  = 1.25
DRYER_MIN_VA          = 5000
RANGE_DEMAND_VA       = 8000   # NEC 220.55 single range allowance
SERVICE_VOLTS         = 240

@dataclass
class PanelLoadYear:
    year: int               # 1-indexed simulation year
    service_amps: float
    utilization_pct: float
    status: str             # "green" | "yellow" | "orange" | "red"
    new_device: str | None  # name of device activated this year, if any

def _status(util_pct: float) -> str:
    if util_pct < 70:   return "green"
    if util_pct < 90:   return "yellow"
    if util_pct <= 100: return "orange"
    return "red"

class PanelAssessor:
    def __init__(self, floor_area_sqft: int, panel_amps: int):
        self.floor_area_sqft = floor_area_sqft
        self.panel_amps = panel_amps

    def general_demand_va(self) -> float:
        g = (self.floor_area_sqft * GENERAL_VA_PER_SQFT
             + SMALL_APPLIANCE_VA + LAUNDRY_VA)
        if g <= DEMAND_THRESHOLD_VA:
            return g
        return DEMAND_THRESHOLD_VA + (g - DEMAND_THRESHOLD_VA) * DEMAND_FACTOR_ABOVE

    def appliance_va(self, active_devices: list) -> float:
        """Sum named-appliance VA for the given active electric devices.
        active_devices: list of EnergyConsumer instances active in a given year
        (electricity fuel_type only; gas devices contribute 0 via rated_va==0)."""
        total = 0.0
        for d in active_devices:
            if d.fuel_type != "electricity":
                continue
            cls = type(d).__name__
            if cls in ("InductionCooktop",):
                total += RANGE_DEMAND_VA               # NEC fixed range allowance
            elif cls in ("HeatPumpDryer",):
                total += max(DRYER_MIN_VA, d.rated_va)  # NEC 220.54
            elif cls in ("PhysicsEVCharger", "EVCharger"):
                factor = EV_CONTINUOUS_FACTOR if d.continuous else 1.0
                total += d.rated_va * factor
            elif cls == "LightsAndPlugs":
                continue                                # covered by general load
            else:
                total += d.rated_va                     # HVAC, HPWH, CentralAC, etc.
        return total

    def nec_load_amps(self, active_devices: list) -> float:
        total_va = self.general_demand_va() + self.appliance_va(active_devices)
        return total_va / SERVICE_VOLTS

    def journey_load_timeline(self, journey_home, n_years: int) -> list[PanelLoadYear]:
        """One PanelLoadYear per simulation year for the JOURNEY home only.
        Determine each year's active electric devices by replicating DeviceSlot
        swap logic (see below)."""
        ...

    def upgrade_needed_years(self, timeline: list[PanelLoadYear]) -> list[int]:
        return [t.year for t in timeline if t.utilization_pct > 100]
```

**Determining active devices per year** (the core of `journey_load_timeline`): for each
year `y` in `1..n_years`, for each `slot` in `journey_home.slots`, decide which device is
active using the same rules as `DeviceSlot.step()`:
- `starting_state == "electric"` → `slot.electric_device` active every year
- `starting_state in ("gas","none")` and `swap_year` set and `y >= swap_year` →
  `slot.electric_device` active
- otherwise → `slot.baseline_devices` active (gas furnace contributes 0 VA; an existing
  `CentralAC` in `baseline_devices` DOES contribute its VA)

Collect the active electric devices across all slots for that year, call
`nec_load_amps(...)`, build the `PanelLoadYear`. Record `new_device` = the slot name when
a slot's electric device becomes active exactly in year `y`.

Do **not** step the model or mutate any device — read configuration only. This keeps the
assessment a pure, side-effect-free read over `journey_home.slots`.

### Deliverable 4 — `HomeConfig` + reactive state

**`src/home_config.py`** — add two fields:
```python
floor_area_sqft: int = 1800   # NOTE: square_footage already exists — see below
panel_amps:      int = 200
```
`square_footage` already exists and is the floor area — **reuse it**, do NOT add a
duplicate `floor_area_sqft`. Only add `panel_amps`. (The spec wrote `floor_area_sqft`
generically; in this codebase it maps to the existing `square_footage`.)

**`src/app.py`** — add reactive + default + reset wiring for `panel_amps`:
```python
panel_amps = solara.reactive(200)          # near other home reactives
"panel_amps": 200,                          # in _DEFAULTS
panel_amps.set(_DEFAULTS["panel_amps"])     # in reset_to_defaults
```
Add `panel_amps=panel_amps.value` to the `HomeConfig(...)` call in `run_simulation()`.

Also add reactives for the new sizing controls:
```python
hvac_tonnage      = solara.reactive(3.0)    # slider 2.0–5.0 step 0.5
ev_charger_amps   = solara.reactive(32)     # selector 32 / 48
induction_amps    = solara.reactive(40)     # editable input
hpwh_amps         = solara.reactive(15)     # editable input
dryer_amps        = solara.reactive(30)     # editable input
```
with matching `_DEFAULTS` entries and reset wiring, and add them to the
`run_simulation` memo dependency list so the sim re-runs when they change.

### Deliverable 5 — Wire electrical values into slot configs

In `_build_slot_configs()` (`app.py`), add electrical fields to each electric device dict:
```python
# HVAC electric_device:
"circuit_volts": 240,
"circuit_amps":  int(hvac_tonnage.value * 10),
"continuous":    True,
# Water Heater electric_device:
"circuit_volts": 240, "circuit_amps": hpwh_amps.value, "continuous": False,
# Dryer electric_device:
"circuit_volts": 240, "circuit_amps": dryer_amps.value, "continuous": False,
# Cooktop electric_device (InductionCooktop):
"circuit_volts": 240, "circuit_amps": induction_amps.value, "continuous": False,
# EV electric_device (PhysicsEVCharger):
"circuit_volts": 240, "circuit_amps": ev_charger_amps.value, "continuous": True,
# CentralAC in hvac_baseline (when has_ac): add electrical fields
"circuit_volts": 240, "circuit_amps": 20, "continuous": False,
```
Gas baseline devices and `LightsAndPlugs` get nothing.

### Deliverable 6 — Detail panel "Electrical" rows

Add a read-display + editable-input "Electrical" row to each electric appliance detail
panel. Reuse the existing `_DSl`/`SliderWithDefault` and `solara.InputInt` patterns.

- **`HVACDetail()`** — add a **tonnage slider** (2.0–5.0, step 0.5) labeled "Heat pump size".
  Below it show: `Electrical: 240 V · {amps} A · {amps×240:,} VA` where `amps = tonnage×10`.
- **`WaterHeaterDetail()`** — `Electrical:` row with editable `hpwh_amps` input + VA display.
- **`DryerDetail()`** — `Electrical:` row with editable `dryer_amps` input + VA display.
- **`CooktopDetail()`** — `Electrical:` row with editable `induction_amps` input + VA display.
- **`EVDetail()`** — `Electrical:` row with 32/48A **selector** + VA display.
- **`BaseloadDetail()`** — "Effective A" display: `120 V · ~{eff_a:.0f} A effective
  (avg across all circuits)` where `eff_a = annual_baseload_kwh × 1000 / 8760 / 120`.
  Informational only.
- Gas-state appliances (no electric swap) still show the electric replacement's spec,
  consistent with how the detail panel already shows "Replacement: Heat Pump …".
- These rows appear only for the electric device; pure-gas devices show nothing electrical.

### Deliverable 7 — Top-line "Estimated Electrical Load" callout

Add a callout **above the chart row** in `Page()` (after `SummaryStats`, before the dual
chart panes). Build a `PanelAssessor` from `model.home_config.square_footage` and
`model.home_config.panel_amps`, compute the timeline over `model.journey_home`, then render:

```
Estimated Electrical Load                                    [?]
Year 1:  94A   ████████░░░░░░░░  47% of 200A panel  ✅
Peak:   163A   ████████████████  82% of 200A panel  ⚠   (Year 8, induction)
```
- Year 1 = `timeline[0]`; Peak = max by `service_amps`.
- Color the bar/badge by `status` (green/yellow/orange/red → e.g. #2E7D32 / #F9A825 / #FB8C00 / #C62828).
- If `upgrade_needed_years` is non-empty, show a red note: *"Panel upgrade likely needed
  by year {first} — consider adding a Panel Upgrade to your journey."*
- `[?]` → `HelpButton("panel_assessment")` (add this popup key — see Deliverable 9).

### Deliverable 8 — Journey timeline (compact, under the callout)

A small per-year strip (text or thin bars) showing `service_amps / panel_amps` and the
status color for each year a device is added (years where `new_device is not None`), plus
year 1 and the peak year. Keep it compact — this sits under the top-line callout, not a
full Matplotlib chart. A simple HTML/flex row per milestone year is fine.

### Deliverable 9 — Help content

Edit `docs/help/help_content.md` §11 (Electrical Panel & Panel Upgrade) so its `@keys`
line includes the new popup key, and add the callout's short popup text:
```
@keys: panel_upgrade, panel_assessment
```
Then run `python scripts/build_help.py` to regenerate `panel.html` and `help_content.py`.
(Do not hand-edit `src/help_content.py` — it is generated.)

---

## Hard Rules

1. **No energy/cost math changes.** Charts, kWh, therms, $ must be identical to before.
   Verify: existing tests pass and a spot-check run matches prior cumulative cost.
2. The electrical attributes are inert — they never affect `monthly_consumption()`,
   `step()`, or any rate/cost path.
3. `PanelAssessor` is **read-only** over `journey_home.slots` — it must not step the
   model or mutate devices.
4. Reuse `square_footage`; do not add a duplicate `floor_area_sqft` field.
5. Gas devices and `LightsAndPlugs` must have `rated_va == 0` and contribute nothing
   to the NEC appliance load.
6. All new reactives must be added to the `run_simulation` memo dependency list **and**
   to `_DEFAULTS` + `reset_to_defaults`.
7. Run `solara run src/app.py` and confirm the app starts with no errors before committing.

## Tests — `tests/test_panel_assessor.py`

Write pytest cases:
- `general_demand_va`: 1800 sqft → `1800×3 + 3000 + 1500 = 9900` (≤10k, no demand factor) → 9,900 VA.
- A 3000 sqft home → `9000+4500=13500` → `10000 + 3500×0.4 = 11,400` VA (demand factor applied).
- `appliance_va`: a HeatPumpHVAC@7200 + PhysicsEVCharger@7680(×1.25=9600) + HeatPumpWaterHeater@3600
  + InductionCooktop(→8000 fixed) + HeatPumpDryer@7200(max(5000,7200)=7200) = 35,600 VA.
- `nec_load_amps` for that set at 1800 sqft: (9900 + 35600)/240 = 189.6 A.
- `journey_load_timeline`: build a tiny JourneyHome-like stub (or a real one) with one
  slot swapping in year 5; assert the EV VA appears only from year 5 onward and
  `new_device` is set in year 5.
- `_status` thresholds: 69→green, 70→yellow, 90→orange, 101→red.
- Gas device contributes 0: a GasFurnace in active list adds nothing.

## Acceptance Criteria

- [ ] `EnergyConsumer` has `circuit_volts/amps/continuous` + `rated_va` property; gas → 0
- [ ] `electrical_defaults.json` created; values flow through `_make_device()`
- [ ] `panel_assessor.py` with `PanelAssessor`, `PanelLoadYear`, `_status` — read-only
- [ ] `HomeConfig.panel_amps` added; `square_footage` reused (no duplicate field)
- [ ] New reactives (`panel_amps`, `hvac_tonnage`, `ev_charger_amps`, `induction_amps`,
      `hpwh_amps`, `dryer_amps`) wired: defaults, reset, memo deps
- [ ] Electrical rows in HVAC/WH/Dryer/Cooktop/EV detail panels; tonnage slider on HVAC;
      32/48A selector on EV; "Effective A" on Baseload
- [ ] Top-line "Estimated Electrical Load" callout above charts with Year 1 + Peak,
      color-coded, with `[?]` help and upgrade-needed note
- [ ] Compact journey timeline of milestone years under the callout
- [ ] `help_content.md` §11 updated; `build_help.py` re-run; `panel.html` regenerated
- [ ] `tests/test_panel_assessor.py` passes (`python -m pytest tests/test_panel_assessor.py`)
- [ ] All pre-existing tests still pass; simulation cost/energy outputs unchanged
- [ ] App launches cleanly with `solara run src/app.py`
