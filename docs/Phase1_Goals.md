# Phase 1 Goals: Home Electrification Simulator (HES)

**Status:** Planning  
**Follows:** HES Prototype (Mesa + Solara confirmed working)  
**Stack:** Python + Mesa + Solara  

---

## Overview

Phase 1 moves the HES from a working proof-of-concept to a structurally sound first version. The prototype established that Mesa + Solara is the right foundation. Phase 1 firms up the data model, cleans up the simulation architecture, and delivers an EN-ROADS-inspired UI with selectable graph panels and grouped control panels.

The six objectives below are ordered roughly by dependency: the device framework (1–3) must be solid before the price model (5) and UI (6) can be built on top.

---

## Objective 1: EnergyConsumer Class — Review & Testing

**Status:** Prototype code exists; needs review, unit clarification, and tests.

### Design Decisions

**Units — single internal unit (MMBtu), dollar-only UI:**  
Phase 1 keeps the prototype's single internal unit (MMBtu) for all energy quantities. Splitting into kWh vs. MMBtu is deferred until the core simulation is stable.

More importantly: the target audience is the **general public**, not engineers. The UI must never expose MMBtu, kWh, AFUE, SEER, COP, or UEF to users. All visible outputs are in **dollars ($)**. Control panel sliders use plain-language labels (e.g., "Heat Pump Efficiency" not "COP"). This is the primary design constraint for the Solara UI.

| Layer | Unit | Notes |
|-------|------|-------|
| Internal simulation | MMBtu | Consistent with prototype; hidden from users |
| UI outputs | $ (USD) | Monthly cost, annual cost, cumulative savings |
| UI inputs | Plain-language sliders | Labeled descriptively, not with technical acronyms |

**Appliance Lifespan & CapEx:**  
- `age` increments by 1 each annual step.  
- When `age > lifespan`, the device resets to `age = 0` and logs a CapEx event: `(simulation_year, installation_cost)`.  
- Efficiency degradation over time is **deferred to Phase 2**.

**CapEx Tracking:**  
- Each `EnergyConsumer` maintains its own `capex_events` list of `(simulation_year, cost)` tuples.  
- `HomeSimulator` aggregates these into a `capex_by_year` dict for the CapEx chart.  
- Phase 1 CapEx simply reports **when a replacement is expected to occur** based on `current_age` and `lifespan` — it does not dynamically model condition-based replacement.  
- CapEx and OpEx remain **separate tracked quantities**. Combining into a single TCO metric is deferred to Phase 2.

**Step Model — annual steps, confirmed:**  
Each `model.step()` represents **one year**. Monthly granularity comes from the 12-element `seasonality` vector applied inside each step. This is clean, already working, and sufficient through Phase 2. True monthly stepping (where each `step()` = one month) is only needed when device interactions such as solar net metering are introduced in Phase 3+. No change from the prototype.

### Testing Targets
- Unit tests for `calculate_consumption()` across gas-only, electric-only, and mixed `fuel_mix` scenarios.
- Verify that CapEx events fire correctly at end-of-lifespan and on replacement.
- Verify that inactive devices record zero consumption in history.
- Verify that seasonality vectors sum to 1.0 (validation on load).

---

## Objective 2: Two Home Configuration Files

Replace the single `sample_home.json` (which the prototype mutated in Python to simulate two homes) with two self-describing, independent JSON files.

### `baseline_home.json`
A typical Bay Area home with conventional gas appliances.

| Device | Category | Fuel | Notes |
|--------|----------|------|-------|
| Gas Furnace | HVAC_Heating | gas | AFUE ~0.80 |
| Central AC | HVAC_Cooling | electricity | SEER ~14 |
| Gas Water Heater | WaterHeating | gas | UEF ~0.65 |
| Baseload (lights, computers) | Baseload | electricity | flat seasonality |

### `electrified_home.json`
The same home with gas appliances replaced by electric equivalents.

| Device | Category | Fuel | Notes |
|--------|----------|------|-------|
| Heat Pump — Heating | HVAC_Heating | electricity | COP ~3.5; winter seasonality |
| Heat Pump — Cooling | HVAC_Cooling | electricity | COP ~3.5; summer seasonality |
| Heat Pump Water Heater | WaterHeating | electricity | UEF ~3.0 |
| Baseload (lights, computers) | Baseload | electricity | flat seasonality; same as baseline |

**Note:** The Heat Pump is split into two device entries (Heating and Cooling) to keep seasonality vectors clean and independent. An EV charger device is **deferred to Phase 2**.

### JSON Schema Additions
Both files will include a top-level `"home_type"` field (`"baseline"` or `"electrified"`) and a `"description"` field for display in the UI.

---

## Objective 3: Two-Home Instantiation in HESModel

**Status:** Prototype works but uses a fragile mutation hack — loads one JSON, then overwrites device attributes in Python to simulate the electrified home.

### What Changes
- `HESModel.__init__()` loads `baseline_home.json` and `electrified_home.json` as two separate configs.
- No post-load device mutation. Each home's devices are fully described by its own JSON.
- The hardcoded efficiency parameters (`furnace_afue`, `hp_cop`, etc.) passed into `HESModel.__init__()` are **removed** from the constructor. In Phase 1, all device specs come from JSON. UI sliders that let the user tweak efficiency values will be added to the control panels (Objective 6) and will modify device attributes at runtime via the Solara reactive layer.

---

## Objective 4: Simulation Timeline (5–25 Years)

**Status:** Already implemented in the prototype. Carry forward unchanged.

- `years = solara.reactive(15)` with a slider (`min=5, max=25, step=1`).
- The main simulation loop runs `model.step()` for `years.value` iterations.
- Exposed in the bottom control panel (Objective 6).

---

## Objective 5: Energy Price Model Class

**Status:** Prototype has inline price logic in `HESModel.step()`. Phase 1 extracts this into a proper, extensible `EnergyPrice` class.

### Design

```
EnergyPrice
  fuel_type: str              # "electricity" or "gas"
  monthly_base_prices: [12]   # 2025 average price, one value per month
  annual_escalation_rate: float   # e.g., 0.03 for 3% per year

  get_monthly_price(month: int, year: int) -> float
    # Applies simple compound escalation: base_price[month] * (1 + rate)^year
```

`HESModel` will hold one `EnergyPrice` instance for electricity and one for gas. Each annual step, the model calls `get_price()` and passes the resulting monthly rates to `EnergyConsumer` agents.

### 2025 Baseline Prices (Bay Area / PG&E starting point)

| Fuel | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec |
|------|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|
| Electricity ($/kWh) | 0.31 | 0.31 | 0.30 | 0.30 | 0.31 | 0.33 | 0.35 | 0.35 | 0.33 | 0.31 | 0.30 | 0.31 |
| Gas ($/MMBtu) | 18.0 | 17.0 | 15.0 | 13.0 | 11.0 | 10.0 | 10.0 | 10.0 | 11.0 | 13.0 | 16.0 | 18.0 |

*These are reasonable starting estimates. The UI will expose +/- % sliders to adjust them.*

### Extensibility (Phase 2+)
The class is designed so that future subclasses can override `get_monthly_price()` to implement:
- Volatility / price shock events
- State- or utility-specific rate schedules (e.g., SCE, SDG&E)
- Time-of-use (TOU) rate structures

---

## Objective 6: Solara UI — EN-ROADS-Inspired Layout

**Inspiration:** The [EN-ROADS climate simulator](https://en-roads.climateinteractive.org) — two large graph panels on top, multiple grouped control panels on the bottom with labeled sliders.

### Layout

```
┌─────────────────────────────────────────────────────┐
│  HES — Home Electrification Simulator               │
├──────────────────────────┬──────────────────────────┤
│  GRAPH PANEL A           │  GRAPH PANEL B           │
│  [chart selector ▼]      │  [chart selector ▼]      │
│                          │                          │
│  (chart renders here)    │  (chart renders here)    │
│                          │                          │
├────────────┬─────────────┴──────────┬───────────────┤
│ ENERGY     │ BASELINE HOME          │ ELECTRIFIED   │
│ PRICING    │                        │ HOME          │
│            │                        │               │
│ Elec +/-%  │ Furnace AFUE slider    │ Heat Pump COP │
│ Gas  +/-%  │ AC SEER slider         │ HPWH UEF      │
│            │ WH UEF slider          │               │
│ Timeline   │                        │               │
│ 5–25 yrs   │                        │               │
└────────────┴────────────────────────┴───────────────┘
```

*Note: Three control panels on the bottom (not two) — this better matches the EN-ROADS layout and cleanly separates the three configuration concerns.*

### Graph Panel — Selectable Charts (Phase 1)

Each graph panel has a dropdown allowing the user to choose which chart to display. The four available charts in Phase 1 are:

| Chart | Type | Description |
|-------|------|-------------|
| Electricity Pricing | Line (12 months × N years) | Monthly electricity price trajectory over the simulation horizon |
| Gas Pricing | Line (12 months × N years) | Monthly gas price trajectory over the simulation horizon |
| Cumulative OpEx | Line | Running total of OpEx: Baseline vs. Electrified, with the delta highlighted |
| CapEx by Year | Bar | Annual capital replacement costs for each home side-by-side |

### Bottom Control Panels

All slider labels use plain language. Technical terms (AFUE, SEER, COP, UEF, MMBtu) are hidden from users. The underlying simulation still uses these values internally.

**Panel 1 — Energy Pricing**
- "How fast will electricity prices rise?" — annual % slider (0–10%)
- "How fast will gas prices rise?" — annual % slider (0–10%)
- "Years to simulate" — 5–25 years slider

**Panel 2 — Your Current Home (Gas)**
- "Gas Furnace Efficiency" — maps to AFUE (0.80–0.98)
- "Air Conditioner Efficiency" — maps to AC SEER (13–18)
- "Water Heater Efficiency" — maps to WH UEF (0.60–0.90)

**Panel 3 — Electrified Home**
- "Heat Pump Efficiency" — maps to COP (3.0–4.5); applies to both heating and cooling
- "Heat Pump Water Heater Efficiency" — maps to HPWH UEF (2.0–4.0)

---

## What Is Deferred

| Feature | Deferred To |
|---------|-------------|
| Efficiency degradation over appliance lifetime | Phase 2 |
| EV charger device | Phase 2 |
| TCO (combined OpEx + CapEx single metric) | Phase 2 |
| Price shock / volatility events | Phase 2 |
| State/utility-specific rate schedules | Phase 2 |
| Solar panel device & net metering interactions | Phase 3 |
| Weather-driven load (NOAA HDD/CDD integration) | Phase 3 |
| Co-benefit modules (carbon cost, PM2.5 health) | Phase 3 |

---

## File Structure After Phase 1

```
hes/
├── src/
│   ├── energy_consumer.py     # Reviewed, unit-corrected, tested
│   ├── energy_price.py        # New: EnergyPrice class
│   ├── model.py               # Cleaned up: loads two JSONs, no mutation hack
│   └── app.py                 # New EN-ROADS-style UI
├── data/
│   ├── baseline_home.json     # New
│   └── electrified_home.json  # New
├── tests/
│   └── test_energy_consumer.py  # New
├── docs/
│   ├── HES_Prototype_Spec.md
│   ├── Phase1_Goals.md        # This document
│   └── Glossary.md            # To be updated with new units
├── requirements.txt
└── Dockerfile
```

---

## Primary Use Case (added after first UI review)

### Target User

**Climate and electrification advocates** who work directly with homeowners — e.g., building performance contractors, energy coaches, community organizations, and utility program staff. These users are energy-literate but are helping a *consumer* audience make decisions.

> "I want to show a homeowner what it actually costs — and saves — to switch from gas appliances to electric, in their specific situation."

### Primary Interaction Pattern

1. **Advocate opens the simulator** with default Bay Area assumptions already loaded.
2. **Advocate adjusts the home's profile** — what appliances it has, roughly how old they are, and usage levels — to match the homeowner's actual situation.
3. **Charts update live** as sliders move, making the cost and savings story visible in real time.
4. **Advocate explores scenarios** ("what if gas prices rise faster?" / "what if you get a more efficient heat pump?") to give the consumer a range of outcomes.
5. **Key numbers are legible at a glance** — no technical jargon, dollar figures only in the output area.

### What the Tool Is NOT (Phase 1 scope boundary)

- Not a bill calculator (no utility rate schedules, TOU pricing, or demand charges yet)
- Not a financing tool (no loan payments, rebates, or tax credits yet)
- Not a multi-home comparison (one baseline vs. one electrified scenario per session)
- Not a carbon or emissions calculator (Phase 2 candidate)

### Feedback Loop

After advocates use the tool with homeowners, they will provide structured feedback on:
- Which sliders they actually reach for
- Which numbers / chart views are most persuasive
- What's confusing or missing

This feedback will directly shape Phase 2 priorities.

