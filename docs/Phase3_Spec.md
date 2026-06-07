# WhyWatt — Phase 3 Development Spec

**Status:** 🔵 DRAFTING — brainstorm / requirements phase as of 2026-06-02.
**Follows:** Phase 2 complete (journey model, physics devices, ACC rate model, summary charts)
**Last updated:** 2026-06-02 — all six sections drafted; deferred items renumbered §7–§9

---

## Phase 3 Goals (Overview)

Phase 2 grounded the simulation in real physics and real PG&E/CPUC rate data for the
Bay Area. Phase 3 broadens the tool's reach, deepens its accuracy, and adds two
high-visibility features that no comparable consumer simulator currently provides.

### Core Simulation Improvements

1. **Climate Lookup by ZIP (§1)** — ZIP-code-driven HDD/CDD replaces the hardcoded
   Bay Area TMY3 constants. California uses 16 CEC Building Climate Zones as the
   authoritative mapping (ZIP → CEC zone → TMY3 reference city). Every CA climate zone
   gets accurate HVAC and water-heating physics. Infrastructure supports adding other
   states by re-running a build script — no code changes required.
   `ClimateData` carries latent `hdd_cagr` / `cdd_cagr` fields (zero by default) for
   Phase 4 climate trend modeling via Cal-Adapt projections.

2. **Better Appliance Physics (§2)** — Five targeted improvements:
   - **HVAC:** two-point COP curve (`cop_47` / `cop_17`) for temperature-dependent
     heating efficiency; matters in mountain and valley climate zones
   - **Cooktop:** both gas and induction promoted to cook-time physics model
     (`hours + minutes per day`); induction becomes a standalone DeviceSlot
   - **Dryer:** `loads_per_week` slider surfaces the existing model parameter in the UI
   - **EV Charger:** `miles_per_day` + vehicle efficiency tier replaces fixed schedule
   - **Electrical specs:** `ElectricalSpec` (V, A, rated VA) attached to every electric
     DeviceSlot; displayed in each appliance's Detail panel; enables §5

3. **Rate Modeling — EIA State Data (§3)** — EIA residential electricity and gas rates
   added as a selectable source alongside PG&E CPUC data. CA only for Phase 3; build
   script supports `--states TX` etc. to add states without code changes. Rate source
   is user-selected (not auto-detected). ACC shape remains PG&E-only.

4. **Help / Documentation System (§4)** — Contextual `[?]` icons throughout the UI
   open inline popup cards (2–4 sentences + "Learn more →"). Full HTML reference pages
   in `docs/help/` open in a browser window. Works fully offline (`file:///`).
   Charts organized into three groups: **JC** (Journey Costs), **R** (Rates),
   **EU** (Energy Use). Top-bar "Help" button opens the help index.

### New High-Visibility Features

5. **Panel Load Assessment (§5)** — NEC Article 220 electrical load calculation driven
   by each appliance's `ElectricalSpec`. Shows "Estimated Electrical Load: 142A / 200A"
   as a top-line callout with color-coded utilization status. Year-by-year journey
   timeline shows when panel headroom tightens as devices are added. Flags years where
   a panel upgrade is likely needed and links to the existing Panel Upgrade DeviceSlot.
   Directly relevant to CA's CEC/CPUC panel upgrade programs (TECH+, etc.).
   *No comparable consumer electrification simulator currently shows this.*

6. **Social & Health Cost of Gas (§6)** — A dedicated panel below "Energy & Prices"
   quantifying costs of residential gas combustion not reflected in the utility bill:
   - **Climate cost:** EPA 2023 SC-CO2 + upstream CH4 leakage = $1.07/therm default
     (slider $1.00–$2.00; backed by EPA and IWG data in help file)
   - **Health cost:** CPUC Decision D.24-07-015 air quality adder = $1.23/therm default
     (slider $0.50–$2.00; backed by E3 2022 report and CARB data in help file)
   - Each component has an independent enable toggle
   - When enabled, costs appear as distinct stacked layers in JC-1 (annual), JC-2
     (cumulative — payback year shifts left), and JC-4 (cost by category)
   - Not shown in per-device or energy-quantity charts
   - At defaults: $2.30/therm total — nearly equal to the $2.08/therm market rate,
     illustrating that the "true" cost of gas is roughly double the utility bill
   *No comparable consumer electrification simulator currently shows this.*

### Carried Forward from Phase 2 Deferred List

- Income-qualified rebates (§7 — deferred to Phase 4)
- Monte Carlo uncertainty bands (§8 — deferred to Phase 4)
- HomeConfig JSON save/load (§9 — deferred to Phase 4)
- Multi-utility support SCE/SDG&E (absorbed into §3; CPUC tariffs deferred to Phase 3.5)

---

## §1 — Climate Lookup by ZIP Code

### 1.1 Motivation

Phase 2 hardcoded Bay Area TMY3 constants (San Jose Mineta, Station 724945: 1,910 HDD,
340 CDD). A home in Fresno (3,200 HDD, 2,800 CDD) or Tahoe (6,800 HDD, 100 CDD) produces
wildly different HVAC consumption. ZIP-level climate is the single biggest source of
modeling error for non-Bay-Area users.

### 1.2 Data Sources

**Primary weather data — NOAA TMY3 (Typical Meteorological Year 3)**
- The same dataset used for building energy codes, ENERGY STAR, and Title 24 compliance
- TMY3 is a *statistical composite*, not a single calendar year: NREL selected the most
  "typical" month from the 1991–2005 record for each calendar month and spliced them
  together. This makes it the right "current snapshot" baseline for a deterministic
  simulation — it already represents a long-run average, not any one anomalous year.
- Provides hourly dry-bulb temperatures from which monthly HDD/CDD are derived
- Also provides monthly average ground/inlet water temperatures (used by HPWH model)
- Source: https://rredc.nrel.gov/solar/old_data/nsrdb/1991-2005/tmy3/ (NREL, free)

**California ZIP mapping — CEC Building Climate Zones (authoritative CA method)**

California Title 24 energy code defines 16 official **CEC Building Climate Zones**.
Every CA HVAC permit, ENERGY STAR certification, and utility rebate program uses these
zones. The CEC publishes an official ZIP-to-zone lookup table.

Each zone has a designated **reference city** with a TMY3 weather file:

| Zone | Reference City    | Character                        |
|------|-------------------|----------------------------------|
| CZ1  | Arcata            | Cool/foggy north coast           |
| CZ2  | Santa Rosa        | Mild coastal valley              |
| CZ3  | Oakland           | Mild Bay Area coast              |
| CZ4  | San Jose          | Warm Bay Area interior           |
| CZ5  | Santa Maria       | Central coast                    |
| CZ6  | Los Angeles       | South coast                      |
| CZ7  | San Diego         | South coast inland               |
| CZ8  | El Toro           | Transitional LA basin            |
| CZ9  | Pasadena          | LA basin warm                    |
| CZ10 | Riverside         | Inland empire                    |
| CZ11 | Red Bluff         | Hot north valley                 |
| CZ12 | Sacramento        | Hot central valley               |
| CZ13 | Fresno            | Hot/dry central valley           |
| CZ14 | China Lake        | High desert                      |
| CZ15 | El Centro         | Low desert (extreme heat)        |
| CZ16 | Blue Canyon       | Mountain/snow                    |

**Why CEC zones rather than nearest-TMY3-station (Haversine distance):**
- CEC zones are the authoritative CA standard — our HVAC numbers match what a Title 24
  compliance tool produces for the same home, giving advocates a defensible reference
- Nearest-station geometry fails at terrain boundaries: a coastal ZIP and a valley ZIP
  can be 5 miles apart but belong to different climate zones (e.g., Half Moon Bay vs.
  Redwood City)
- The CEC ZIP table is maintained by a state agency and handles these edge cases

### 1.3 Offline Data Pipeline

A one-time build script (`scripts/build_climate_db.py`) will:

1. Read the CEC ZIP→Climate Zone CSV (downloaded from CEC Title 24 reference data)
2. For each of the 16 CEC zones, parse the designated TMY3 EPW file
3. Compute monthly HDD (base 65°F) and CDD (base 65°F) from hourly dry-bulb temps
4. Extract monthly average ground/inlet water temperature
5. Write zone climate records to `data/climate/tmy3_zones.json` (16 records)
6. Write ZIP→zone index to `data/climate/zip_to_zone.json` (~1,700 CA ZIP entries)

**Two-file design** (compact and auditable):

```json
// data/climate/tmy3_zones.json
{
  "CA_CZ4": {
    "state": "CA", "zone_id": "CZ4", "reference_city": "San Jose",
    "tmy3_station": "724945",
    "annual_hdd_65f": 1910, "annual_cdd_65f": 340,
    "monthly_hdd_65f": [420, 340, 260, 140, 50, 10, 0, 0, 10, 80, 220, 380],
    "monthly_cdd_65f": [0, 0, 0, 5, 20, 60, 90, 85, 55, 20, 5, 0],
    "monthly_inlet_water_f": [54, 54, 55, 57, 60, 63, 65, 66, 65, 62, 58, 55]
  }
}

// data/climate/zip_to_zone.json
{
  "94105": "CA_CZ3",
  "95110": "CA_CZ4",
  "93720": "CA_CZ13"
}
```

`ClimateLoader` does a two-step lookup: ZIP → zone key → zone data. Both files are
committed to the repo. No network calls at runtime.

**Adding a new state in the future:**

```
python scripts/build_climate_db.py --states TX
```

For states without a CEC-equivalent zone system, the script falls back to
**nearest TMY3 station** (ZIP centroid → Haversine distance to station lat/lon,
using Census ZCTA centroids). TX output appends to both JSON files using NOAA station
IDs as zone keys (e.g., `TX_722540`). `ClimateLoader` is unaware of which mapping
method was used — it reads the same two files regardless.

**Per-state mapping method is recorded in the script itself:**

```python
# scripts/build_climate_db.py
STATE_MAPPING = {
    "CA": {"method": "cec_zones",    "source": "CEC Title 24 ZIP table"},
    "TX": {"method": "nearest_tmy3", "source": "ZCTA centroids + NOAA TMY3"},
    # Add new states here. Document the mapping choice and source.
}
```

This is a developer-time decision, made once per state, version-controlled in code.

### 1.4 Runtime Lookup

A new module `src/climate_loader.py` wraps the two JSON files:

```python
@dataclass
class ClimateData:
    zone_key: str                        # e.g. "CA_CZ4"
    zone_label: str                      # e.g. "CZ4 — San Jose"
    monthly_hdd_65f: list[float]         # (12,) array
    monthly_cdd_65f: list[float]         # (12,) array
    monthly_inlet_water_f: list[float]   # (12,) array
    annual_hdd_65f: float
    annual_cdd_65f: float
    # --- Latent fields for Phase 4 climate trend (no-ops in Phase 3) ---
    hdd_cagr: float = 0.0   # annual change rate for HDD (<0 = warming winters)
    cdd_cagr: float = 0.0   # annual change rate for CDD (>0 = hotter summers)

class ClimateLoader:
    def get_climate(self, zipcode: str) -> ClimateData:
        # Step 1: zip_to_zone.json lookup → zone_key (e.g. "CA_CZ4")
        # Step 2: tmy3_zones.json lookup → ClimateData
        # Fallback: if ZIP not found → return CA_CZ4 (Bay Area) with a warning flag
```

`ClimateData` is injected into `HomeConfig`. Devices receive it at construction
(injection pattern unchanged from Phase 2). The `hdd_cagr` / `cdd_cagr` fields default
to 0.0 — the simulation loop reads them but multiplies by zero, so Phase 3 behavior is
identical to today. Phase 4 fills them from Cal-Adapt projections without any device
or simulation code changes.

**How the simulation uses `hdd_cagr` in Phase 4 (preview):**
```python
# In HESModel.step(), year n of the simulation:
effective_hdd = climate.monthly_hdd_65f * (1 + climate.hdd_cagr) ** n
```
The HVAC device receives `effective_hdd` instead of the static array. One-line change,
no architecture impact — the latent fields make this a drop-in extension.

### 1.5 UI Changes

- **Home Profile panel:** Add a ZIP code text field (5 digits).
  - On valid CA ZIP: show resolved zone as confirmation chip —
    e.g., `📍 CZ4 — San Jose  |  HDD 1,910 · CDD 340`
  - On ZIP not found in database: show warning —
    `⚠ ZIP not recognized — using Bay Area defaults (CZ4)`
  - The zone label and HDD/CDD summary give advocates an immediate sanity check
    ("yes, that's right for Fresno" / "wait, that looks wrong")
- **No network calls at runtime.** All lookups are local JSON reads.
- **Help link** next to the ZIP field → `climate.html` explaining CEC zones and TMY3

### 1.6 Impact on Existing Devices

| Device | Impact |
|--------|--------|
| GasFurnace | Monthly HDD drives consumption — high impact |
| HeatPumpHVAC (heating) | Monthly HDD + COP curve — high impact |
| HeatPumpHVAC (cooling) | Monthly CDD — high impact |
| GasWaterHeater | Monthly inlet water temp — low-to-medium impact |
| HeatPumpWaterHeater | Monthly inlet water temp — low impact |
| Dryer, Induction, EV, LightsAndPlugs | No impact |

### 1.7 Decisions Made / Open Questions

- [x] **Scope: California-only for Phase 3.** Script supports `--states` flag; new state = run script + commit JSON.
- [x] **ZIP mapping method: CEC Climate Zones for CA; nearest-TMY3 fallback for other states.**
      Method is documented per-state in `STATE_MAPPING` dict in the build script.
- [x] **Weather data: static TMY3 for Phase 3.** `hdd_cagr` / `cdd_cagr` fields are latent no-ops.
- [x] **EPW format** for TMY3 source files (universal standard, parseable without NREL tools).
- [x] **Two-file JSON design:** `tmy3_zones.json` (16 zone records) + `zip_to_zone.json` (ZIP index).

**Climate trend roadmap (Phase 4):**
The simulation is already wired for trend via the latent `hdd_cagr` / `cdd_cagr` fields.
Phase 4 will populate these from **Cal-Adapt** (https://cal-adapt.org/) — CEC/LBNL's
official CA climate projection dataset, which provides county-level HDD/CDD trends under
RCP 4.5 (moderate) and RCP 8.5 (high-emissions) scenarios through 2100. Directional
expectation for CA: HDD declining (warmer winters), CDD increasing (hotter summers).
Over a 20-year simulation, this effect is non-trivial in inland and mountain zones but
is less significant on the coast.

---

## §2 — Better Appliance Physics

### 2.1 Heat Pump HVAC — Temperature-Dependent COP

**Current model:** constant COP for heating (e.g., 3.5), constant SEER for cooling.

**Problem:** Heat pump COP drops significantly in cold weather. A COP 3.5 unit at 47°F
may deliver COP 2.0 at 17°F. This matters for mountain ZIPs (Tahoe, Big Bear) and
cold-snap months.

**Proposed model:** A simple two-point COP curve:
- `cop_47` — rated COP at 47°F (AHRI standard rating condition, user-facing)
- `cop_17` — rated COP at 17°F (AHRI cold-climate rating, user-facing)
- Monthly effective COP interpolated from average monthly temperature (derived from HDD/CDD)

This matches NEEP ASHP performance data methodology and is defensible.

**Cooling:** SEER remains a constant (EER degradation in extreme heat is second-order for
California).

**UI change:** In the HVAC detail panel, expose `cop_47` and `cop_17` sliders alongside
the existing SEER slider.

### 2.2 Clothes Dryer — Load-Count Model

**Current model:** `cycles_per_week × kWh_per_cycle × 52` (or therms equivalent for gas).

**Current UI:** No user controls — defaults assumed.

**Proposed changes:**
- Add a `loads_per_week` slider to the Dryer detail panel (range 1–14, default 5)
- Keep `kWh_per_cycle` (electric) and `therms_per_cycle` (gas) as advanced sliders
  (collapsible, with ENERGY STAR defaults pre-filled)
- Annual consumption = `loads_per_week × 52 × energy_per_cycle`

This is the same formula — just exposing the load count as a user control.

**No physics change to the device class** — just surface existing parameters in the UI.

### 2.3 Cooktop — Cook-Time Physics Model (Gas and Induction)

**Decision (resolved):** Both gas and induction cooktops get physics-based consumption
computed from actual daily cook time. The same `cook_minutes_per_day` parameter drives
both fuel types. Induction is promoted from the LightsAndPlugs baseload bucket to a
standalone `DeviceSlot`.

#### User input

- `cook_hours` + `cook_minutes` — two integer inputs (hours: 0–4, minutes: 0–59)
  that combine to a fractional `cook_time_per_day` in hours.
  Default: 1 hr 0 min (= 1.0 hr/day).
- This is more natural than a decimal slider ("1 hr 15 min" vs "1.25 hrs").

#### Induction cooktop physics

```
cook_time_per_day = cook_hours + cook_minutes / 60        # hours/day
annual_kWh = cook_time_per_day × avg_burner_kW × 365 × efficiency_factor
```

Constants (fixed, not user-facing):
- `avg_burner_kW` = 1.5 kW  (weighted average: ~2 active burners × ~750 W each)
- `efficiency_factor` = 0.85 (accounts for warm-up overhead and partial-power use)

Validation: 1.0 hr/day → 1.0 × 1.5 × 365 × 0.85 = **466 kWh/yr** ✓ (ENERGY STAR ref)

#### Gas cooktop physics

```
annual_therms = cook_time_per_day × avg_burner_btuh × 365 / 100_000 / burner_efficiency
```

Constants (fixed, not user-facing):
- `avg_burner_btuh` = 7,500 BTU/hr  (weighted average: ~2 active burners × ~3,750 BTU/hr each)
- `burner_efficiency` = 0.40  (fraction of combustion heat that reaches cookware; AGA data)

Validation: 1.0 hr/day → 1.0 × 7,500 × 365 / 100,000 / 0.40 = **68 therms/yr**

> Note: The gas figure (~68 therms/yr) is higher than the ~26 therms/yr figure in the
> original spec draft. The earlier figure used a lower average burner output (3,000 BTU/hr)
> appropriate for a single small burner. 7,500 BTU/hr reflects typical combined output of
> two simultaneously active burners, which is the more realistic daily cooking scenario.
> If field data suggests the lower estimate is more accurate for the target households,
> `avg_burner_btuh` can be adjusted; it is a named constant not a formula change.

#### Implementation notes

- `GasCooktop` and `InductionCooktop` are new device classes in `src/devices/seasonal.py`
  (seasonal in the sense that the annual total is spread flat across months — no seasonal
  variation for cooking)
- Both receive `cook_hours: int` and `cook_minutes: int` at construction
- `monthly_consumption()` returns a flat (12,) array: `annual / 12` each month
- The existing LightsAndPlugs baseload is reduced by a fixed offset (≈466 kWh/yr) when an
  InductionCooktop slot is active, to avoid double-counting

#### UI changes

- Cooktop detail panel shows two numeric inputs: **"Cook time per day"** `[ 1 ] hr [ 0 ] min`
- Same input drives both gas baseline and induction journey slot
- Help link → `cooktop.html`

### 2.4 EV Charger — Miles-per-Day Model

**Current model:** Fixed weekly schedule with assumed kWh/session.

**Proposed enhancement:**
- Add a `miles_per_day` input (range 0–100, default 37 — US average VMT)
- `annual_kWh = miles_per_day × 365 / vehicle_efficiency_mi_per_kWh`
- `vehicle_efficiency_mi_per_kWh`: user-selectable from a small dropdown:
  - Efficient (4.5 mi/kWh — e.g., Tesla Model 3 LR)
  - Average (3.5 mi/kWh — e.g., F-150 Lightning)
  - Less efficient (2.8 mi/kWh — e.g., large SUV/truck)

This is more intuitive than kWh/session for most users.

**Retain** the existing schedule-based model as the `ScheduleDevice` backend;
miles_per_day simply sets the total annual kWh which distributes across the existing
time-of-use schedule.

### 2.5 Electrical Specifications — V, A, and Rated VA per Appliance

**Motivation:** Tracking voltage and amperage alongside kWh enables panel load assessment
(§5) without changing the energy simulation at all. These are *nameplate* electrical
properties of the appliance — infrastructure facts, not consumption quantities.

#### 2.5.1 The `ElectricalSpec` Dataclass

Every electric `DeviceSlot` carries an `ElectricalSpec`. Gas devices carry `None`.

```python
@dataclass
class ElectricalSpec:
    circuit_volts: int     # 120 or 240 — determines outlet type and wiring run
    circuit_amps:  int     # dedicated circuit breaker size (nameplate)
    rated_va:      float   # volts × amps — used for NEC load calculation
    continuous:    bool    # True if load runs >3 hrs (NEC 125% factor applies)
    # derived (not stored): rated_kw = rated_va / 1000
```

**Why VA and kWh must remain separate:**

| Device | Rated VA (nameplate) | Typical annual kWh | What the gap means |
|--------|---------------------|-------------------|-------------------|
| Heat Pump HVAC (3-ton) | 240V × 30A = 7,200 VA | ~1,930 kWh | Runs at full draw only on coldest/hottest days |
| Heat Pump Water Heater | 240V × 15A = 3,600 VA | ~1,050 kWh | Compressor cycles briefly, not continuously |
| EV Charger L2 (32A) | 240V × 32A = 7,680 VA | ~3,540 kWh | Runs ~1.5 hrs/day average |
| Induction Cooktop | 240V × 40A = 9,600 VA | ~466 kWh | Rarely all burners at full power |
| Heat Pump Dryer | 240V × 30A = 7,200 VA | ~468 kWh | ~45 min/load, not continuous |

VA sizes the wire and breaker. kWh determines the utility bill. They cannot be swapped.

**Gas devices:** `ElectricalSpec = None`. Gas appliances (furnace, water heater, dryer,
cooktop) have trivial 120V control circuits that do not materially affect panel load.
Nothing is displayed in their detail panel for electrical specs.

#### 2.5.2 Where Electrical Specs Are Displayed

**Every electric appliance's Detail panel** shows a compact read-only row:

```
  ┌──────────────────────────────────────────────┐
  │ Heat Pump Water Heater          [collapse ▲] │
  │ ...  (existing kWh / cost fields) ...        │
  │ ─────────────────────────────────────────── │
  │ Electrical   240 V · 15 A · 3,600 VA        │
  └──────────────────────────────────────────────┘
```

- Label: **"Electrical"**
- Format: `{volts} V · {amps} A · {rated_va:,.0f} VA`
- **Editable in Phase 3** (decision resolved): base nameplate variables get inputs.
  HVAC uses a **tonnage slider** (2.0–5.0 ton, default 3.0) that derives amps via
  `amps = tonnage × 10` (so 3.0 ton → 30 A → 7,200 VA). EV charger uses a **32/48 A
  selector**. Induction / HPWH / Dryer use an editable amps input prefilled with the
  JSON default. VA recalculates automatically from volts × amps.
- Gas devices: this row is omitted entirely.

#### 2.5.3 Baseload (LightsAndPlugs) — "Effective A" Treatment

The `LightsAndPlugs` slot is a *composite* of many 120V circuits — lighting, outlets,
small electronics, refrigerator, etc. There is no single nameplate circuit. Instead we
display an **Effective A** derived from the simulated annual kWh:

```python
# In LightsAndPlugs.electrical_spec (property, not stored):
avg_watts       = annual_kwh * 1000 / 8760   # average continuous draw
effective_amps  = avg_watts / 120            # at 120V
```

Detail panel display for baseload:

```
  ┌──────────────────────────────────────────────┐
  │ Baseload (Lights & Plugs)       [collapse ▲] │
  │ ...  (existing kWh / cost fields) ...        │
  │ ─────────────────────────────────────────── │
  │ Electrical   120 V · ~8 A effective          │
  │              (avg across all circuits)       │
  └──────────────────────────────────────────────┘
```

- Label: **"Electrical"**
- Format: `120 V · ~{effective_amps:.0f} A effective`
- Sub-label: `(avg across all circuits)` — sets expectation that this is not a single breaker
- The `~` tilde prefix signals it is a derived estimate, not a nameplate rating
- This value is **informational only** — `PanelAssessor` uses the NEC general lighting
  formula (§5.2 Step 1) for baseload, not this derived number

#### 2.5.4 Reference Electrical Defaults

Defaults stored in `data/appliances/electrical_defaults.json`:

| Device | Volts | Amps | Rated VA | Continuous? |
|--------|-------|------|---------|-------------|
| Heat Pump HVAC — 2-ton | 240 | 20 | 4,800 | Yes |
| Heat Pump HVAC — 3-ton | 240 | 30 | 7,200 | Yes |
| Heat Pump HVAC — 4-ton | 240 | 40 | 9,600 | Yes |
| Heat Pump Water Heater | 240 | 15 | 3,600 | No |
| EV Charger L2 (standard) | 240 | 32 | 7,680 | Yes |
| EV Charger L2 (fast home) | 240 | 48 | 11,520 | Yes |
| Induction Cooktop (full range) | 240 | 50 | 12,000 | No |
| Induction Cooktop (standalone) | 240 | 40 | 9,600 | No |
| Heat Pump Dryer | 240 | 30 | 7,200 | No |
| Solar Inverter (typical) | 240 | 30 | 7,200 | Yes |
| LightsAndPlugs (baseload) | 120 | *derived* | *derived* | — |

Loaded into each `DeviceSlot` at construction. The `LightsAndPlugs` row has no fixed
values — its effective amps are recomputed each simulation step from the current kWh.

**Storage decision (resolved):** electrical attributes live on the **device classes**
(`circuit_volts`, `circuit_amps`, `continuous` on the `EnergyConsumer` base; `rated_va`
is a derived property). Defaults come from `data/appliances/electrical_defaults.json`,
threaded through `_make_device()`. `PanelAssessor` reads them off the active device. Gas
devices never set them → `rated_va == 0`.

**HVAC tonnage → breaker amps table** (used by the tonnage slider; `amps = tonnage × 10`):

| Tonnage | Breaker A | Rated VA (×240) |
|---------|-----------|-----------------|
| 2.0 | 20 | 4,800 |
| 2.5 | 25 | 6,000 |
| 3.0 | 30 | 7,200 |
| 3.5 | 35 | 8,400 |
| 4.0 | 40 | 9,600 |
| 4.5 | 45 | 10,800 |
| 5.0 | 50 | 12,000 |

`CentralAC` (existing baseline AC, when `has_cooling_baseline`) also carries an electrical
spec: 240 V × 20 A = 4,800 VA. It contributes to the panel load whenever it is active
(see §5.3 scope decision).

### 2.6 Heat Pump Water Heater — Inlet Temperature Sensitivity

**Current model:** UEF-based annual kWh, with inlet water temp already driving heat load.

**Assessment:** Already well-modeled. The inlet temperature from the climate ZIP (§1)
feeds directly into the existing HPWH physics. No physics change needed.

**Minor enhancement:** Expose `uef` and `tank_size_gal` as sliders in the HPWH detail
panel (currently hardcoded). Lets users model older or non-standard units.

### 2.7 Validation Targets (updated for §2 changes)

| Device | Config | Expected | Tolerance |
|--------|--------|---------|-----------|
| HeatPumpHVAC heating | UA=500, cop_47=3.5, cop_17=2.0, HDD=1910 | ~1,930 kWh/yr | ±5% |
| HeatPumpHVAC heating | UA=500, cop_47=3.5, cop_17=2.0, HDD=6800 (Tahoe) | ~6,800 kWh/yr | ±10% |
| Induction cooktop | 1 hr 0 min/day | ~466 kWh/yr | ±5% |
| Gas cooktop | 1 hr 0 min/day, 2 burners avg 7,500 BTU/hr total, eff=0.40 | ~68 therms/yr | ±5% |
| EV charger | 37 mi/day, 3.5 mi/kWh | ~3,862 kWh/yr | ±5% |
| HeatPumpDryer | 5 loads/wk, 1.8 kWh/load | ~468 kWh/yr | ±2% |

---

## §3 — EIA-Based Rate Modeling

### 3.1 Motivation and Decision

Phase 2 rate data is PG&E-specific (CPUC filings, PG&E Advice Letters). Users outside
PG&E territory see incorrect rates. Phase 3 adds EIA state-level rates as a selectable
option alongside the existing PG&E data.

**Decisions (resolved):**
- PG&E CPUC data stays as-is and remains a selectable rate source (not replaced).
- EIA state data is a second selectable rate source — starting with California only.
- The rate source is a user choice in the UI, not auto-detected from ZIP.
- The infrastructure (build script + data schema) supports adding any US state by
  running the script for that state. No code changes needed to add a new state.

### 3.2 Rate Source Options (Phase 3)

| Source | Label in UI | Coverage | Accuracy |
|--------|------------|----------|----------|
| PG&E CPUC | "PG&E (CPUC tariff)" | PG&E territory only | Highest — actual tariff filings |
| EIA California | "California average (EIA)" | All CA ZIPs | Medium — statewide average across all utilities |

The user selects the rate source via a dropdown in the Rate/Projection panel. Default:
PG&E CPUC (unchanged from Phase 2).

When EIA California is selected, the simulation uses EIA's residential average rate and
historical CAGR. The ACC shape (from Phase 2 §18–23) is only available for the PG&E
source; with EIA source, ACC is disabled and a flat seasonal shape is used instead.

### 3.3 Data Source

**EIA Open Data API (free, no key required for bulk downloads):**
- Electricity: EIA-861 / EIA Form 861M — monthly state-level residential retail rate (¢/kWh)
- Natural gas: EIA Natural Gas Monthly — monthly state-level residential rate ($/Mcf, converted to $/therm)

Both series go back to 2001. The build script downloads once and snapshots the data.

### 3.4 Offline Data Pipeline

A build script (`scripts/build_eia_rates.py`) will:

1. Accept a `--states` argument (default: `CA`; accepts multiple: `--states CA TX NY`)
2. Download EIA bulk electricity and gas rate series for residential sector
3. Filter to the requested state(s)
4. Compute the 10-year historical CAGR for each state (used as the default escalation scenario)
5. Compute a monthly seasonal shape (12-month ratio array) from multi-year averages
6. Merge results into `data/rates/eia_rates_by_state.json` (append-safe)

Schema (per state):
```json
{
  "CA": {
    "label": "California",
    "electricity": {
      "unit": "$/kWh",
      "current_rate": 0.312,
      "historical_cagr_10yr": 0.071,
      "monthly_seasonal_shape": [0.95, 0.93, 0.97, 1.00, 1.03, 1.08, 1.12, 1.10, 1.05, 1.00, 0.97, 0.95]
    },
    "gas": {
      "unit": "$/therm",
      "current_rate": 1.74,
      "historical_cagr_10yr": 0.063,
      "monthly_seasonal_shape": [1.10, 1.08, 1.02, 0.97, 0.93, 0.90, 0.90, 0.92, 0.96, 1.00, 1.06, 1.10]
    },
    "source": "EIA-861 and EIA Natural Gas Monthly, 2024 annual average",
    "extracted": "2026-06-02"
  }
}
```

**Adding a new state in the future:**
```
python scripts/build_eia_rates.py --states TX
# → appends TX to data/rates/eia_rates_by_state.json, commit the file
# → TX becomes available in the UI rate source dropdown automatically
```

### 3.5 Integration with Existing Rate Framework

The existing `RateLoader` class interface is unchanged. A new factory method is added:

```python
RateLoader.from_eia(state: str, fuel: str) -> RateLoader
# Reads from data/rates/eia_rates_by_state.json
# fuel: "electricity" | "gas"
# Uses EIA current_rate as base_rate, historical_cagr_10yr as default escalation
```

The `RateLoader.from_pge(fuel)` factory (implicit in Phase 2 code) is made explicit to
match the pattern. Both factories return the same `RateLoader` type — the simulation
code is unaware of which source was used.

### 3.6 UI Changes

- **Rate panel:** Add a **"Rate source"** dropdown:
  - "PG&E (CPUC tariff)" ← default
  - "California average (EIA)"
  - _(future states appear here as their data files are added)_
- **Source label:** Below the dropdown, show data vintage:
  e.g., "EIA data: 2024 annual average, extracted 2026-06-02"
- **ACC note:** When EIA source is selected, the ACC section shows:
  "ACC shape available for PG&E only — using flat seasonal shape"
- **Manual override** (carried from initial draft): allow user to enter a custom
  base rate ($/kWh, $/therm) for cases where neither source matches their bill

### 3.7 Resolved / Open Questions

- [x] **PG&E CPUC data retained and selectable** — not replaced.
- [x] **EIA is a selectable option, not auto-detected** — user picks rate source explicitly.
- [x] **CA-only for Phase 3; add-state workflow defined** — run script, commit JSON, done.
- [x] **Residential sector rates** — not blended with commercial.
- [x] **Rate basis: most recent 12-month average** — more stable than single-month.
- [ ] Should the EIA dropdown dynamically populate from available states in the JSON,
      or be a hardcoded list? (Recommendation: dynamic — reads `data/rates/eia_rates_by_state.json` keys)

---

## §4 — Help / Documentation System

### 4.1 Motivation

WhyWatt makes quantitative claims ("your journey saves $47,000 over 20 years") that
users will — and should — question. Contextual help explains the methodology,
assumptions, and data sources behind each number. This is a trust-building tool for
advocates presenting to skeptical homeowners, and a self-service reference for users
exploring on their own.

---

### 4.2 Chart Organization

Charts are grouped into three named sections. Each chart has a group prefix and
sequential number within its group. This numbering is used in the UI title bar,
in help popup headers, and in the full HTML help pages.

#### Group JC — Journey Costs
Answers: *"What will this cost, and is the journey worth it?"*

| ID | Chart Title |
|----|-------------|
| JC-1 | Annual Cost — Your Journey vs. Do Nothing |
| JC-2 | Cumulative Cost & Payback Crossover |
| JC-3 | 20-Year Summary — Total Spend & Savings |
| JC-4 | Annual Cost Breakdown by Appliance |

#### Group R — Rates
Answers: *"Where do the energy prices come from, and how do they change?"*

| ID | Chart Title |
|----|-------------|
| R-1 | Electricity & Gas Rate Projection |
| R-2 | ACC Seasonal Rate Shape (PG&E only) |

#### Group EU — Energy Use
Answers: *"How much energy does each appliance actually use?"*

| ID | Chart Title |
|----|-------------|
| EU-1 | Annual Energy Consumption by Fuel (kWh + therms) |
| EU-2 | Per-Appliance Energy Breakdown |

Each chart title bar in the UI shows the ID and title:
```
┌──────────────────────────────────────────────────────────┐
│  JC-1  Annual Cost — Your Journey vs. Do Nothing    [?]  │
└──────────────────────────────────────────────────────────┘
```

---

### 4.3 Help UI — Two-Tier Pattern

**Tier 1 — Inline popup card** (stays in the app)
Triggered by any `[?]` icon in the UI. Shows 3–5 lines of plain-English context
plus a **"Learn more →"** link. Dismissed by clicking the card's ✕ or anywhere outside.

```
  User clicks [?] on HVAC sub-panel header
       ↓
  ┌──────────────────────────────────────────────────┐
  │  Heat Pump HVAC                              [✕] │
  │                                                  │
  │  Heating and cooling energy is calculated from   │
  │  monthly degree-days for your ZIP code's CEC     │
  │  climate zone, your home's insulation level,     │
  │  and the heat pump's COP rating.                 │
  │                                                  │
  │                              Learn more →        │
  └──────────────────────────────────────────────────┘
```

**Tier 2 — Full HTML help page** (opens in a new browser window)
Triggered by:
- The top-bar **"Help"** button → opens `help/index.html`
- **"Learn more →"** inside any popup card → opens the relevant topic page

```python
import webbrowser, os

def open_help(topic: str, anchor: str = ""):
    path = os.path.abspath(f"docs/help/{topic}.html")
    url  = f"file:///{path}"
    if anchor:
        url += f"#{anchor}"
    webbrowser.open(url)
```

No web server required. Works fully offline. All `file:///` URLs.

**Solara implementation of popup card:**
A `solara.v.Dialog` (or equivalent overlay) anchored near the triggering button.
State is a reactive `help_open: str` variable (holds the topic key of the open card,
empty string = none open). One popup instance in the component tree, re-used for all
topics — content swaps based on `help_open`.

---

### 4.4 "?" Icon Placement — Full Inventory

#### Top bar
| Element | Icon | Behavior |
|---------|------|----------|
| "Help" button (right of "Reset to Defaults") | `[Help 📖]` button | Opens `index.html` in browser |

#### Main panel headers
| Panel | Icon position | Popup topic | Learn more → |
|-------|--------------|-------------|--------------|
| Home Profile | right of header, before `[▼]` | "How home details affect the simulation" | `climate.html` |
| Journey Planner | right of header, before `[▼]` | "What the journey model means" | `journey.html` |
| Rate & Projection | right of header, before `[▼]` | "Where energy rates come from" | `rates.html` |
| Solar & Battery | right of header, before `[▼]` | "How solar savings are modeled" | `solar.html` |
| Panel Load callout (§5) | `[?]` in callout header | "How electrical load is estimated" | `panel.html` |

#### Device sub-panel rows (inside Journey Planner)
`[?]` at the far right of the row title, before `[▼]`. No electrical spec `?` needed —
the spec values are informational display only inside the detail panel.

| Device row | Popup topic | Learn more → |
|------------|-------------|--------------|
| HVAC | COP, HDD/CDD, heating vs. cooling | `hvac.html` |
| Water Heater | UEF, inlet water temp | `water_heating.html` |
| Clothes Dryer | Loads/week, kWh/load | `dryer.html` |
| Cooktop | Cook-time model, gas vs. induction efficiency | `cooktop.html` |
| EV Charger | Miles/day, vehicle efficiency tiers | `ev.html` |
| Solar + Battery | Net-of-solar, payback | `solar.html` |
| Baseload | What's included, bedroom scaling | `baseload.html` |
| Panel Upgrade | When an upgrade is needed, cost range | `panel.html` |

#### Chart title bars
`[?]` at the right end of each chart title bar.

| Chart | Popup topic | Learn more → |
|-------|-------------|--------------|
| JC-1 Annual Cost | "Annual cost is the total utility bill for that year" | `charts.html#jc1` |
| JC-2 Cumulative / Payback | "Payback is the year cumulative journey cost dips below do-nothing" | `charts.html#jc2` |
| JC-3 20-Year Summary | "How the savings bar is computed" | `charts.html#jc3` |
| JC-4 Cost by Appliance | "Each bar is one appliance's share of the annual bill" | `charts.html#jc4` |
| R-1 Rate Projection | "CAGR escalation applied to the base rate each year" | `rates.html#projection` |
| R-2 ACC Seasonal Shape | "ACC is the avoided cost of electricity from the grid" | `acc.html` |
| EU-1 Energy by Fuel | "kWh and therms shown on separate axes" | `charts.html#eu1` |
| EU-2 Energy by Appliance | "Physical energy, before rate conversion" | `charts.html#eu2` |

#### Input fields in Home Profile
| Field | Icon position | Popup topic |
|-------|--------------|-------------|
| ZIP code field | inline `[?]` after field | "What ZIP is used for: CEC climate zone lookup" → `climate.html` |
| Rate source dropdown | inline `[?]` after dropdown | "PG&E vs. EIA — what each means" → `rates.html#source` |

---

### 4.5 Help Page Inventory

| File | Contents | Triggered from |
|------|----------|---------------|
| `index.html` | Table of contents, navigation to all topics | Top-bar Help button |
| `journey.html` | Journey model, do-nothing baseline, swap years | Journey Planner `?` |
| `hvac.html` | HVAC physics, HDD/CDD, COP curve, temperature correction | HVAC row, JC-1, EU-1 |
| `water_heating.html` | UEF, inlet water temp, HPWH vs. gas | Water Heater row |
| `dryer.html` | Loads/week model, ENERGY STAR data | Dryer row |
| `cooktop.html` | Cook-time model, gas/induction physics, efficiency constants | Cooktop row |
| `ev.html` | Miles/day model, vehicle efficiency tiers, charging schedule | EV row |
| `solar.html` | Net-of-solar calculation, battery, payback | Solar row, JC-2 |
| `baseload.html` | LightsAndPlugs composition, bedroom scaling, what's included | Baseload row |
| `rates.html` | PG&E CPUC tariff, EIA state data, CAGR escalation, ACC | Rate panel, R-1 |
| `acc.html` | What ACC is, E3 CPUC 2024 methodology, seasonal shape | R-2 |
| `climate.html` | CEC climate zones, TMY3, ZIP lookup, HDD/CDD definition | ZIP field |
| `panel.html` | NEC load calc, panel sizes, upgrade cost range, CA programs | Panel callout |
| `charts.html` | One anchored section per chart (JC-1…EU-2) explaining the axes | All chart `?` |
| `about.html` | Project overview, data vintage, methodology disclaimer, team | Help index |

---

### 4.6 Help Page Template

All pages use the same self-contained template. No external CSS, no JavaScript,
no CDN calls. Must render correctly as `file:///` URLs in any modern browser.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>WhyWatt Help — [Topic]</title>
  <style>
    body { font-family: sans-serif; max-width: 760px; margin: 2rem auto;
           padding: 0 1rem; color: #222; line-height: 1.6; }
    header { display: flex; align-items: center; gap: 1rem;
             border-bottom: 2px solid #eee; padding-bottom: 1rem; }
    nav    { margin: 1rem 0; font-size: 0.9rem; }
    nav a  { margin-right: 1rem; color: #0066cc; }
    h2     { margin-top: 2rem; border-bottom: 1px solid #eee; }
    code   { background: #f5f5f5; padding: 0.1em 0.3em; border-radius: 3px; }
    .note  { background: #fffbe6; border-left: 4px solid #f0c040;
             padding: 0.5rem 1rem; margin: 1rem 0; }
  </style>
</head>
<body>
  <header>
    <img src="../assets/whywatt_logo.png" alt="WhyWatt" height="40"
         onerror="this.style.display='none'">
    <h1>[Topic Name]</h1>
  </header>
  <nav>
    <a href="index.html">← Help Index</a>
    <!-- topic-specific cross-links -->
  </nav>
  <main>
    <h2 id="what-this-means">What this means for you</h2>
    <!-- plain-English paragraph first — no jargon -->

    <h2 id="how-it-works">How we calculate it</h2>
    <!-- formulas in readable notation, not code -->

    <h2 id="assumptions">Key assumptions</h2>
    <!-- what we assume and why; what to change if it doesn't fit -->

    <h2 id="sources">Data sources</h2>
    <!-- links to CPUC filings, ENERGY STAR, EIA, NOAA, CEC -->
  </main>
  <footer style="margin-top:3rem; font-size:0.8rem; color:#888;
                 border-top:1px solid #eee; padding-top:1rem;">
    WhyWatt v[VERSION] · Data vintage: [YEAR] ·
    <a href="about.html">About this tool</a>
  </footer>
</body>
</html>
```

---

### 4.7 Popup Card Content — Short-Form Text

Each `[?]` popup card needs 2–4 sentences of plain English. These are authored in
`src/help_content.py` as a dict (not in HTML), so they stay close to the UI code:

```python
HELP_POPUPS = {
    "hvac": (
        "Heating and cooling energy is calculated from monthly degree-days "
        "for your ZIP code's CEC climate zone, your home's insulation class, "
        "and the heat pump's efficiency rating (COP for heating, SEER for cooling).",
        "hvac.html"   # "Learn more →" target
    ),
    "chart_jc1": (
        "Annual cost is the total energy bill for that simulation year — "
        "electricity plus gas — for your journey home vs. the do-nothing baseline. "
        "The gap between the lines is your annual saving (or cost) in that year.",
        "charts.html#jc1"
    ),
    # ... one entry per ? target
}
```

This keeps all short-form help text in one file, easy to review and update without
touching HTML.

---

### 4.8 Decisions Made

- [x] **Global "Help" button** right of "Reset to Defaults" → browser window, `index.html`
- [x] **Chart groups**: JC (Journey Costs), R (Rates), EU (Energy Use)
- [x] **Two-tier help**: inline popup card (dismiss on click) + "Learn more →" to browser
- [x] **Electrical spec in detail panel**: display only, no separate `?` icon needed
- [x] **Popup text stored in `src/help_content.py`**: one dict, easy to maintain
- [x] **No external dependencies in HTML pages**: `file:///` compatible, offline-safe

---

## §5 — Panel Load Assessment

### 5.1 Motivation

Panel capacity is one of the most concrete barriers to home electrification in California.
A 100-amp panel — still common in pre-1980s homes — may not have headroom to add an EV
charger, a heat pump, and an induction range without an upgrade. Panel upgrades run
$3,000–$8,000 and require permits, an electrician, and often a utility coordination delay.

In 2024–2025, CEC, CPUC, and multiple utilities launched targeted programs to address
this exact problem (TECH+ panel upgrade rebates, rule changes to simplify permits). It is
a live, high-visibility topic for the exact audience WhyWatt serves.

Showing "Estimated Electrical Load: 142A / 200A panel" as a top-line number — alongside
the cost chart — makes this concrete for homeowners and gives advocates a tool no other
consumer simulator currently provides.

### 5.2 What We Calculate

**NEC Article 220 Standard Method for Dwelling Units** — the same calculation an
electrician or permit inspector uses to size a service entrance.

#### Step 1 — General Load (demand factor applies)

```
general_va  = (floor_area_sqft × 3)    # general lighting @ 3 VA/sq ft
            + 3_000                     # two small appliance circuits (NEC minimum)
            + 1_500                     # laundry circuit

# Demand factor (NEC Table 220.42):
if general_va <= 10_000:
    demand_va = general_va
else:
    demand_va = 10_000 + (general_va - 10_000) * 0.40
```

#### Step 2 — Named Appliance Load (no demand factor, added at nameplate)

```
# HVAC: larger of heating OR cooling nameplate (they don't run simultaneously)
hvac_va = max(heating_va, cooling_va)

# EV charger: continuous load → nameplate × 1.25 (NEC 210.20 continuous factor)
ev_va = ev_circuit_va × 1.25

# Dryer: NEC 220.54 — use 5,000 VA or nameplate, whichever is larger
dryer_va = max(5_000, dryer_circuit_va)

# Range/cooktop: NEC Table 220.55 — single unit ≤ 12 kW → 8,000 VA demand load
range_va = 8_000   # fixed NEC demand allowance for a single residential range

# All other dedicated circuits: nameplate VA
wh_va    = water_heater_circuit_va
solar_va = solar_inverter_va   # if present (acts as a source, not load — see §5.4)
```

#### Step 3 — Total Service Load and Panel Utilization

```
total_va      = demand_va + hvac_va + ev_va + dryer_va + range_va + wh_va
service_amps  = total_va / 240          # single-phase 240V residential service
utilization_pct = service_amps / panel_amps × 100
```

#### Step 4 — Panel headroom interpretation

| Utilization | Status | Label color |
|------------|--------|-------------|
| < 70% | Comfortable headroom | Green |
| 70–90% | Getting tight — monitor | Yellow |
| 90–100% | At capacity — upgrade likely | Orange |
| > 100% | Exceeds panel rating | Red |

### 5.3 Data Inputs

**From HomeConfig (user-provided):**
- `floor_area_sqft: int` — new field, default 1,800 sq ft (US median)
- `panel_amps: int` — user-selectable: 100 / 150 / 200 (default 200; user knows this
  from their breaker box cover label)

**From each active device's electrical attributes (§2.5):**
- `circuit_volts`, `circuit_amps`, `rated_va`, `continuous` flag
- Gas devices: `rated_va == 0` → contribute nothing to the NEC calculation
- Slots with `starting_state = "none"` and not yet activated: excluded until their
  journey swap year

**Scope decision (resolved): assess the JOURNEY HOME ONLY — never the do-nothing
baseline.** A panel is sized for the home you are actually building toward, not the
do-nothing case. The assessor walks the journey home's active electric devices each
year (year 1 → n_years):
- Year 1 = today's state (= the do-nothing year-1 state, so the label stays accurate).
- An existing `CentralAC` counts whenever present — the journey keeps it until/unless the
  HVAC slot is electrified. If no HVAC swap is planned, the AC counts every year.
- Already-electric appliances count from year 1; "none" appliances (EV) count only from
  their swap year onward.
- `PanelAssessor` is a pure read over `journey_home.slots` — it never steps the model or
  mutates devices.

### 5.4 Solar Interaction

A solar inverter connected to the panel *exports* current — it reduces net panel demand
during daylight hours but does not reduce the *nameplate service entrance size* needed.
NEC does not allow solar to offset the load calculation for service sizing purposes.

Therefore: solar inverter VA is **not subtracted** from the total. If anything, it
occupies a breaker slot and adds a back-feed breaker requirement. This is noted in the
help page but does not change the arithmetic.

### 5.5 Journey Timeline View

Because devices are added in different years, the panel load changes over the simulation
horizon. The assessment should show a **year-by-year load timeline**:

```
Year 0 (baseline):    94A / 200A  ▓▓▓▓▓▓▓░░░░  47%  ✅
Year 3 (add HP HVAC): 118A / 200A ▓▓▓▓▓▓▓▓▓░░  59%  ✅
Year 5 (add EV):      148A / 200A ▓▓▓▓▓▓▓▓▓▓▓▓  74%  ⚠
Year 8 (add induction):163A/200A  ▓▓▓▓▓▓▓▓▓▓▓▓▓ 82%  ⚠
```

If the user has a 100A panel and adds an EV charger (32A continuous = 40A NEC), the
chart turns red in that year and displays: *"Panel upgrade likely needed before adding
EV charger — add a Panel Upgrade to your journey in year 5."*

The Phase 2 Panel Upgrade `DeviceSlot` is already in the journey planner. This
assessment now gives it a data-driven trigger.

### 5.6 Top-Line Display — "Estimated Electrical Load"

A summary line appears **at the top of the simulation output panel**, above the charts:

```
┌─────────────────────────────────────────────────────────┐
│  Estimated Electrical Load                          [?]  │
│  Year 1:  94A   ████████░░░░░░░░  47% of 200A panel ✅  │
│  Peak:   163A   ████████████████  82% of 200A panel ⚠   │
│  (peak occurs in Year 8 after induction range swap)      │
└─────────────────────────────────────────────────────────┘
```

- **Year 1** = current load before any journey swaps (baseline)
- **Peak** = highest load reached at any point in the 20-year journey
- Color-coded by utilization band (§5.2 Step 4)
- `[?]` help link → `panel.html`

This is the "eye-catcher" callout. An advocate can glance at this and immediately say
"your current panel is fine, but when we add the EV charger in year 5 we'll be at 74%
— you have headroom but should keep an eye on it."

### 5.7 New Module — `src/panel_assessor.py`

```python
class PanelAssessor:
    def __init__(self, home_config: HomeConfig):
        ...

    def nec_load_amps(self, active_slots: list[DeviceSlot]) -> float:
        """
        Full NEC Article 220 calculation for the given set of active slots.
        Returns required service amperage.
        """

    def journey_load_timeline(self, journey: JourneyHome) -> list[PanelLoadYear]:
        """
        Returns one PanelLoadYear per simulation year.
        PanelLoadYear: year, service_amps, utilization_pct, status, new_device_added
        """

    def upgrade_needed_years(self, journey: JourneyHome) -> list[int]:
        """
        Returns years where load crosses panel_amps threshold.
        Used to trigger the yellow/red warning and the panel-upgrade suggestion.
        """
```

`PanelAssessor` is instantiated in `HESModel` and called after each simulation step.
Its output is passed to the UI alongside `cost_history_by_category`.

### 5.8 Help Page

`docs/help/panel.html` — contents:
- What the NEC load calculation is and why it matters
- How to find your panel size (breaker box label)
- What "panel upgrade" involves and roughly what it costs in CA
- Links to CEC TECH+ rebate program and utility panel upgrade programs
- Disclaimer: "This is an estimate — a licensed electrician must verify before any work"

---

## §6 — Social & Health Cost of Gas Combustion

### 6.1 Motivation

The utility bill only shows the market price of gas. It does not show the cost that gas
combustion imposes on public health (air quality damage, respiratory illness) and on the
global climate (CO2 and methane emissions). For California homes transitioning away from
gas, this "hidden cost" is substantial — and quantified by official regulatory bodies.

Research basis (see `docs/help/social_cost.html` for full citations):
- **Climate cost:** EPA 2023 SC-CO2 central estimate × EIA emission factor + upstream
  methane leakage SC-CH4 = **~$1.07/therm** (combustion CO2 + 2% pipeline leakage)
- **Health cost:** CPUC Decision D.24-07-015 (July 2024), computed by E3 from their
  "Quantifying Air Quality Impacts of Decarbonization" report = **$1.23/therm**
  This is California-regulatory-adopted, computed using EPA COBRA tool and California
  population/pollution data. It covers outdoor air quality damage (NO2, PM2.5).

At defaults, total social + health cost = **~$2.30/therm**, nearly equal to the
$2.08/therm PG&E market rate. The "true" cost of a therm is roughly double the bill.

This panel is informational — these costs do not appear on the utility bill. They are
shown separately from the market-rate cost charts, but *added into* the JC cost charts
when enabled (see §6.5).

---

### 6.2 UI Panel — "Social & Health Cost of Gas"

Panel is placed **below the "Energy & Prices" section**, collapsible, default expanded.

```
┌─────────────────────────────────────────────────────────────────┐
│  Social & Health Cost of Gas Combustion                    [?]  │
│  ───────────────────────────────────────────────────────────    │
│                                                                 │
│  Climate Cost     [● Enable]    ──●──────  $1.07 /therm        │
│                                  $1.00          $2.00          │
│                                                                 │
│  Health Cost      [● Enable]    ─────●───  $1.23 /therm        │
│                                  $0.50          $2.00          │
│                                                                 │
│  ───────────────────────────────────────────────────────────    │
│  These costs do not appear on your utility bill.               │
│  They represent damage to public health and the climate        │
│  caused by burning natural gas.          Learn more →          │
└─────────────────────────────────────────────────────────────────┘
```

**Controls:**

| Control | Type | Range | Default | Notes |
|---------|------|-------|---------|-------|
| Climate Cost enable | Toggle (on/off) | — | On | When off, slider grays out; $0/therm used |
| Climate Cost rate | Slider | $1.00–$2.00/therm | $1.07 | $1.07 = EPA 2023 central + 2% leakage |
| Health Cost enable | Toggle (on/off) | — | On | When off, slider grays out; $0/therm used |
| Health Cost rate | Slider | $0.50–$2.00/therm | $1.23 | $1.23 = CPUC D.24-07-015 / E3 2022 |

**Slider low/high anchor labels (shown below each slider):**

- Climate: `$1.00` (left) · `$2.00` (right)
  - $1.00 ≈ EPA 2023 SC-CO2 combustion only, no leakage
  - $2.00 ≈ high leakage (3%) + high-discount-rate SCC scenario
- Health: `$0.50` (left) · `$2.00` (right)
  - $0.50 ≈ conservative / skeptical lower bound
  - $1.23 ≈ CPUC-adopted outdoor air quality adder (default)
  - $2.00 ≈ includes indoor air quality health costs (NO2, benzene — not yet in CPUC figure)

The slider ranges are intentionally narrow — these are not open-ended assumptions but
ranges bracketed by official and peer-reviewed sources. The help file documents what
each endpoint represents.

---

### 6.3 Computation — How Annual Cost Is Calculated

Social costs apply to **total annual gas consumption** across all gas devices in each
scenario, not per-device. This is intentional: gas is fungible — the harm is from the
combustion regardless of which appliance burned it.

```python
# Per simulation year, per scenario (journey or do-nothing baseline):

annual_therms_gas = sum(
    device.monthly_consumption().sum()
    for slot in active_slots
    if slot.current_device.fuel == "gas"
)
# monthly_consumption() returns therms/month for gas devices

social_climate_cost = annual_therms_gas × climate_rate  if climate_enabled else 0.0
social_health_cost  = annual_therms_gas × health_rate   if health_enabled  else 0.0
social_total_cost   = social_climate_cost + social_health_cost
```

These three values are appended to `cost_history_by_category` each step under the keys:
- `"social_climate"` — climate cost for this year
- `"social_health"` — health cost for this year
- `"social_total"` — combined (convenience; = climate + health)

The existing `sum-then-append` pattern (Phase 2 hard rule §4) is preserved.
Social costs are computed after all device costs, in a single pass at the model level.

---

### 6.4 New `SocialCostConfig` Dataclass

```python
@dataclass
class SocialCostConfig:
    climate_enabled: bool  = True
    climate_rate:    float = 1.07   # $/therm — EPA 2023 central + 2% CH4 leakage
    health_enabled:  bool  = True
    health_rate:     float = 1.23   # $/therm — CPUC D.24-07-015 / E3 2022

    @property
    def total_rate(self) -> float:
        return (self.climate_rate if self.climate_enabled else 0.0) \
             + (self.health_rate  if self.health_enabled  else 0.0)
```

`SocialCostConfig` is a top-level field on `HESModel`, alongside `HomeConfig`. It is
**not** injected into devices — social cost is a model-level calculation, not a device
property. The UI binds to it directly via reactive state.

---

### 6.5 Chart Integration

Social costs are added to three JC-group charts when at least one cost component is
enabled. They appear as a **distinct stacked layer** above the market-rate gas cost,
clearly labeled so users understand it is not part of their bill.

#### JC-1 — Annual Cost (line chart)
- Two new lines added: "Journey — including social cost" and "Do Nothing — including
  social cost" (dashed, same color as market lines but dashed)
- The original market-rate lines remain; social cost lines stack on top
- Legend clearly labels: "— market cost  - - market + social/health cost"

#### JC-2 — Cumulative Cost & Payback
- Two additional cumulative lines (dashed) including social cost
- The payback crossover year may shift left when social costs are included —
  this is an intentional insight: electrification pays back faster when the
  full cost of gas is counted

#### JC-4 — Annual Cost by Category (stacked bar chart)
- Two new stacked bar segments added per scenario:
  - `social_climate` — labeled "Climate cost" (distinct color, e.g., warm orange)
  - `social_health` — labeled "Health cost" (distinct color, e.g., red-orange)
- These segments sit **above** the existing gas cost segment in the bar
- A visual separator (thin white line) distinguishes social cost segments from
  market-cost segments
- When both components are disabled, segments vanish; bar returns to market-only

**NOT included:**
- EU-1 (Energy by Fuel) — energy quantities, not costs; social cost is irrelevant here
- EU-2 (Energy by Appliance) — same
- Per-device breakdown — social cost is fuel-level, not appliance-level (by design)

---

### 6.6 Disclosure Footer (in panel and in help)

The panel always shows a one-line disclosure:

> *"These costs do not appear on your utility bill. They represent damage to public
> health and the climate that is not reflected in current energy prices."*

The help page (`social_cost.html`) provides full methodology, citations, and caveats:
- EPA 2023 SC-CO2 regulatory status (uncertain under current administration)
- CPUC-adopted value vs. EPA estimate — which this tool uses and why
- What the health adder does and does not cover (outdoor air quality only; indoor
  health costs from NO2/benzene are not included in the CPUC figure)
- Upstream leakage rate assumptions and uncertainty range
- Note that gas cars are not included in Phase 3 (potential Phase 4 addition)

---

### 6.7 Decisions Made

- [x] **Separate enable toggles** for climate and health — users can accept one and
      not the other; skeptics can disable both without losing the rest of the simulation
- [x] **Per-therm rates, applied at fuel level** — not per-device; gas is fungible
- [x] **Added to JC-1, JC-2, JC-4** charts as distinct stacked/dashed layers
- [x] **Not in per-device or energy-quantity charts** (EU-1, EU-2)
- [x] **SocialCostConfig is a model-level object**, not injected into devices
- [x] **Defaults both on** — social costs are real; the default should reflect that;
      users may disable if presenting to a skeptical audience
- [x] **Gas cars excluded** from Phase 3; documented as Phase 4 candidate in help file

---

## §7 — Income-Qualified Rebates (Deferred, Outline Only)

Carried from Phase 2 deferred list. TECH+ and HEAR program rebates vary by income
qualification tier and utility. This requires:
- Income-qualification input (AMI tier or income range)
- Per-device rebate lookup table (IQ-specific)
- Rebate applied to CapEx in year of swap

**Not in scope for Phase 3.** Placeholder section for Phase 4.

---

## §8 — Monte Carlo Uncertainty Bands (Deferred, Outline Only)

Carried from Phase 2 deferred list. Deterministic model produces single-value outputs.
Monte Carlo would add ±1σ bands to the annual cost chart and the summary savings figure.

**Not in scope for Phase 3.** Placeholder section for Phase 4.

---

## §9 — HomeConfig JSON Save/Load (Deferred, Outline Only)

Carried from Phase 2 deferred list. Allows advocates to save a homeowner session and
resume it later, or share a configuration by file.

**Not in scope for Phase 3.** Placeholder section for Phase 4.

---

## Appendix A — Implementation Sequence

### Guiding principles
1. **Additive before architectural** — features that add alongside the simulation ship
   before features that change device construction or simulation internals.
2. **Two evaluator release points** — working builds for feedback before numbers change.
3. **Help pages ship with each objective** — every feature arrives with its help content.
4. **Bay Area defaults preserved** — after Objective 4, a user who never enters a ZIP
   sees identical results to Phase 2 (CZ4 default = Bay Area TMY3 constants).

---

### Objective 1 — Help System Skeleton (§4 partial)

**Risk:** Zero — all new files and UI buttons, no simulation code touched.

Deliverables:
- `docs/help/` directory with HTML template
- `src/help_content.py` — `HELP_POPUPS` dict skeleton, one entry per `[?]` target
- Top-bar **"Help"** button → opens `index.html` in browser
- `[?]` popup cards wired on all main panel headers and device sub-panel rows
- Initial help pages authored: `index.html`, `about.html`, `journey.html`
- Remaining pages added as stubs (title + "coming soon") — filled in each subsequent objective

Why first: zero risk, gives evaluators the infrastructure immediately, and every
later objective just drops its help page into an already-working system.

---

### Objective 2 — ElectricalSpec + Panel Assessment (§2.5 + §5)

**Risk:** Zero simulation change — new dataclass and new module, additive only.

Deliverables:
- `ElectricalSpec` dataclass + `data/appliances/electrical_defaults.json`
- Read-only "Electrical: 240 V · 15 A · 3,600 VA" row in each device's Detail panel
- "Effective A" display for LightsAndPlugs baseload
- `src/panel_assessor.py` — `PanelAssessor`, NEC Article 220 calculation
- `HomeConfig` extended: `floor_area_sqft` (default 1,800) + `panel_amps` (default 200)
- Top-line **"Estimated Electrical Load"** callout — Year 1 load + Peak load, color-coded
- Panel load timeline (year-by-year progress bar)
- Help pages: `panel.html`; `[?]` wired on panel callout

Natural pairing with Obj 1: ElectricalSpec enables Panel Assessment; both are additive.

---

### Objective 3 — Social & Health Cost of Gas (§6)

**Risk:** Minimal — adds new category keys to `cost_history_by_category` without
changing existing keys or values. Existing chart behavior is unchanged when both
toggles are off.

Deliverables:
- `src/social_cost.py` — `SocialCostConfig` dataclass
- **"Social & Health Cost of Gas"** panel below "Energy & Prices" — two enable
  toggles + sliders (climate $1.00–$2.00 default $1.07; health $0.50–$2.00 default $1.23)
- `cost_history_by_category` keys: `"social_climate"`, `"social_health"`, `"social_total"`
- Chart integration: dashed lines in JC-1, cumulative lines in JC-2, stacked segments in JC-4
- Help page: `social_cost.html` with full citations and caveats

---

### ✅ Evaluator Release 1 — after Objective 3

**Simulation results: identical to Phase 2.** Bay Area home, PG&E rates, all existing
charts unchanged. New features visible to evaluators:
- Help system with `[?]` icons and popup cards throughout the UI
- Estimated Electrical Load callout and panel timeline
- Social & Health Cost panel with toggle/slider controls
- Social cost layers in JC-1, JC-2, JC-4 charts

Evaluators can stress-test the new panels and give feedback before any simulation
numbers change. Ideal checkpoint for advocate user testing.

---

### Objective 4 — Climate Infrastructure (§1)

**Risk:** Medium — first architectural change. Touches `HomeConfig` and all device
constructors. Mitigated by: default ZIP = Bay Area CZ4, which reproduces Phase 2
constants exactly for any user who doesn't enter a ZIP.

Deliverables:
- `scripts/build_climate_db.py` — reads CEC ZIP table + 16 TMY3 EPW files
- `data/climate/tmy3_zones.json` (16 CEC zone records) + `data/climate/zip_to_zone.json`
- `src/climate_loader.py` — `ClimateLoader` + `ClimateData` dataclass (latent
  `hdd_cagr`/`cdd_cagr` fields default 0.0 — no-ops in Phase 3)
- `HomeConfig` extended: `climate: ClimateData` field
- All physics devices updated to receive `ClimateData` at construction
- ZIP code text field in Home Profile UI + CEC zone confirmation chip
- Fallback: unknown ZIP → CZ4 (Bay Area) + warning banner
- `PanelAssessor` picks up updated `HomeConfig` automatically (uses `floor_area_sqft`)
- Help page: `climate.html`; `[?]` wired on ZIP field
- Tests: `test_climate_loader.py` — ZIP lookup, CA coverage, fallback, CZ16 Tahoe case

---

### Objective 5 — Physics Improvements (§2.1–2.4, §2.6)

**Risk:** Low-medium — changes device class behavior. Numbers will differ for non-Bay-Area
ZIPs. Bay Area CZ4 defaults produce results within ±2% of Phase 2 (COP interpolation
at Bay Area temperatures ≈ constant COP assumption).

Order within this objective (independent → climate-dependent last):
1. §2.2 Dryer `loads_per_week` slider — UI only, no physics change, ship first
2. §2.4 EV `miles_per_day` + vehicle efficiency dropdown
3. §2.6 HPWH expose `uef` + `tank_size_gal` sliders
4. §2.3 Cooktop: `GasCooktop` + `InductionCooktop` new classes; baseload offset
5. §2.1 HVAC `cop_47`/`cop_17` two-point COP curve (requires §1 climate data)

Deliverables:
- All five physics changes above
- Updated `data/appliances/gas_defaults.json` + `electrical_defaults.json`
- Help pages: `hvac.html`, `cooktop.html`, `dryer.html`, `ev.html`, `water_heating.html`
- Updated validation tests; CZ16 (Tahoe) HVAC test case for COP curve
- Tests: `test_devices_phase3.py`

---

### ✅ Evaluator Release 2 — after Objective 5

**Full Phase 3 simulation.** ZIP-aware climate, improved physics, all high-visibility
panels live. Advocates can run sessions with real CA ZIPs. Numbers differ from Phase 2
for non-Bay-Area homes as expected.

---

### Objective 6 — EIA Rate Modeling (§3)

**Risk:** Zero simulation change — new factory method alongside existing `RateLoader`;
existing PG&E default unchanged.

Saved for last because: independent of everything else, lowest user-impact improvement,
and the build script requires a one-time EIA data pull that can be done any time.

Deliverables:
- `scripts/build_eia_rates.py` — EIA bulk download → `data/rates/eia_rates_by_state.json` (CA)
- `RateLoader.from_eia(state, fuel)` factory method
- Rate source dropdown in Rate panel: "PG&E (CPUC tariff)" | "California average (EIA)"
- ACC unavailable note when EIA source selected
- Updated `rates.html` help page with EIA section
- Tests: `test_rate_loader_eia.py`

---

### Summary Table

| Obj | Features | Sections | Sim change? | Release point |
|-----|----------|----------|-------------|---------------|
| 1 | Help system skeleton | §4 partial | No | — |
| 2 | ElectricalSpec + Panel Assessment | §2.5, §5 | No | — |
| 3 | Social & Health Cost | §6 | Additive only | **Release 1** |
| 4 | Climate infrastructure | §1 | Yes (architecture) | — |
| 5 | Physics improvements | §2.1–2.4, §2.6 | Yes (numbers) | **Release 2** |
| 6 | EIA rate modeling | §3 | No | Phase 3 complete |

---

## Appendix B — Build Scripts

| Script | Purpose | Output | Re-run to extend |
|--------|---------|--------|-----------------|
| `scripts/build_climate_db.py` | NOAA TMY3 → ZIP-keyed JSON | `data/climate/tmy3_by_zip.json` | `--states TX` appends TX ZIPs |
| `scripts/build_eia_rates.py` | EIA bulk download → state-keyed JSON | `data/rates/eia_rates_by_state.json` | `--states TX` appends TX rates |

Note: `build_zip_utility_map.py` (ZIP → utility territory) is deferred — rate source is now
user-selected rather than auto-detected from ZIP, so this mapping is not needed in Phase 3.

These scripts are run by developers, not users. Outputs are committed to the repo.
Scripts are idempotent (safe to re-run; overwrite outputs).

---

## Appendix B — Phase 3 Module Map (Target State)

```
src/
  climate_loader.py     ClimateLoader + ClimateData dataclass (hdd/cdd_cagr latent fields)
  rate_loader.py        RateLoader (extended: from_eia() factory)
  panel_assessor.py     PanelAssessor + PanelLoadYear + ElectricalSpec dataclass  ← NEW
  devices/
    base.py             EnergyConsumer (unchanged interface)
    physics.py          HeatPumpHVAC (cop_47/cop_17 curve)
                        GasCooktop (new — cook-time physics)
                        InductionCooktop (new — cook-time physics)
    seasonal.py         HeatPumpDryer / GasDryer (loads_per_week exposed)
    schedule.py         EVCharger (miles_per_day model)
  social_cost.py        SocialCostConfig dataclass
  home_config.py        HomeConfig (extended: climate: ClimateData,
                                              floor_area_sqft: int,
                                              panel_amps: int)
  help_content.py       HELP_POPUPS dict — short-form text + "Learn more" targets
  app.py                ZIP field, utility label, [?] buttons wired to HELP_POPUPS,
                        Estimated Electrical Load top-line callout,
                        panel load timeline chart
data/
  climate/
    tmy3_zones.json          (new — 16 CEC zone records, built by script)
    zip_to_zone.json         (new — CA ZIP → zone key index, built by script)
  rates/
    eia_rates_by_state.json  (new — built by script; CA on init; add states by re-running)
  appliances/
    electrical_defaults.json (updated — adds ElectricalSpec defaults per device type)
docs/
  help/
    index.html           help table of contents
    journey.html         journey model explanation
    hvac.html            HVAC physics, COP, HDD/CDD
    water_heating.html   UEF, inlet temp, HPWH vs. gas
    dryer.html           loads/week model
    cooktop.html         cook-time physics, gas vs. induction
    ev.html              miles/day model, efficiency tiers
    solar.html           net-of-solar, payback
    baseload.html        LightsAndPlugs, bedroom scaling
    rates.html           PG&E, EIA, CAGR escalation
    acc.html             Avoided Cost of Carbon methodology
    climate.html         CEC zones, TMY3, HDD/CDD
    panel.html           NEC load calc, upgrade programs
    social_cost.html     SCC methodology, CPUC health adder, caveats, citations
    charts.html          all chart explanations (JC-1…EU-2, anchored)
    about.html           project overview, disclaimer
scripts/
  build_climate_db.py   (new — CEC zones for CA; nearest-TMY3 fallback for other states)
  build_eia_rates.py    (new — EIA bulk download; --states flag for expansion)
tests/
  test_climate_loader.py     (new — ZIP→zone lookup, CA coverage, fallback behavior)
  test_devices_phase3.py     (new — cooktop physics, COP curve, loads/wk, miles/day)
  test_rate_loader_eia.py    (new — EIA factory, CAGR, seasonal shape, source selection)
  test_panel_assessor.py     (new — NEC calculation, journey timeline, upgrade detection)
  test_social_cost.py        (new — per-therm calc, enable/disable flags, chart category keys)
```
