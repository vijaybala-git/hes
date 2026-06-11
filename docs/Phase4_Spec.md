# WhyWatt — Phase 4 Development Spec

**Status:** 🔵 DRAFTING — requirements phase as of 2026-06-10.
**Follows:** Phase 3 (panel load assessment, social/health cost of natural gas, help system, improved appliance physics).
**Last updated:** 2026-06-11 — §8 battery/NEM default resolved: Battery On + NEM 3.0 (NBT) is the factual default for any new CA solar installation (NEM 2.0 closed Apr 2026, battery attach rate ~70%+).

---

## Phase 4 Goals (Overview)

Phase 3 delivered the high-visibility, self-contained features (panel load assessment, true-cost-of-natural-gas, contextual help) on a Bay-Area-accurate physics base. Phase 4 broadens geographic reach, adds climate-trend and transportation modeling, and clears the remaining deferred backlog.

### Geographic & Rate Reach
1. **Climate Lookup by ZIP + Climate Trend (§1)** — ZIP-code-driven HDD/CDD via the 16 CEC Building Climate Zones, replacing hardcoded Bay Area TMY3 constants, plus Cal-Adapt-driven warming trends over the simulation horizon (the latent `hdd_cagr`/`cdd_cagr` fields wired in Phase 3 finally get populated).
2. **EIA-Based Rate Modeling (§2)** — EIA state-level residential electricity and natural gas rates as a selectable source alongside PG&E CPUC data; CA first, add-state-by-script infrastructure.

### New Modeling
3. **Transportation — ICE & Electric Vehicles (§3)** — supersedes the thin Phase 3 EV-charger model. Models the household's vehicles in a Current vs. Plan structure, with gasoline (ICE) and electric energy/cost, charging efficiency, and the climate + health externalities of gasoline combustion (the transportation analogue of Phase 3 §6).
4. **Temperature-Dependent Heat Pump COP (§4)** — the two-point `cop_47`/`cop_17` curve (was Phase 3 §2.1); moved here because it depends on the ZIP-level monthly temperatures introduced in §1.
5. **Solar & Battery (§8)** — system-size solar model (`# panels × kW`, PVWatts specific yield) replacing the Phase 2/3 % slider; battery self-consumption and a single NEM export-rate switch (ACC for NEM 3.0, retail−NBC for NEM 2.0).

### Deferred Backlog (carried from Phase 2 → Phase 3 → here)
5. **Income-Qualified Rebates (§5)**
6. **Monte Carlo Uncertainty Bands (§6)**
7. **HomeConfig JSON Save/Load (§7)**

### Naming convention (Phase 4 onward)
With vehicles entering the model, "gas" is ambiguous. House-side fuel is **natural gas** throughout prose and UI; vehicle-side fuel is **gasoline**, and gasoline-powered vehicles are **ICE (internal combustion engine)** vehicles. Code identifiers from earlier phases (`GasFurnace`, `fuel == "gas"`, `gas_defaults.json`) are unchanged — they refer to natural-gas appliances and remain valid; only human-facing text adopts the new convention.

---

## §1 — Climate Lookup by ZIP Code + Climate Trend

### 1.1 Motivation

Phase 3 hardcoded Bay Area TMY3 constants (San Jose Mineta, Station 724945: 1,910 HDD,
340 CDD). A home in Fresno (3,200 HDD, 2,800 CDD) or Tahoe (6,800 HDD, 100 CDD) produces
wildly different HVAC consumption. ZIP-level climate is the single biggest source of
modeling error for non-Bay-Area users. Phase 4 also layers a multi-decade warming trend
on top of the static baseline, since a 20-year simulation in an inland zone is materially
affected by declining HDD (warmer winters) and rising CDD (hotter summers).

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
    # --- Climate trend fields (populated in Phase 4 from Cal-Adapt) ---
    hdd_cagr: float = 0.0   # annual change rate for HDD (<0 = warming winters)
    cdd_cagr: float = 0.0   # annual change rate for CDD (>0 = hotter summers)

class ClimateLoader:
    def get_climate(self, zipcode: str) -> ClimateData:
        # Step 1: zip_to_zone.json lookup → zone_key (e.g. "CA_CZ4")
        # Step 2: tmy3_zones.json lookup → ClimateData
        # Fallback: if ZIP not found → return CA_CZ4 (Bay Area) with a warning flag
```

`ClimateData` is injected into `HomeConfig`. Devices receive it at construction
(injection pattern unchanged). The `hdd_cagr` / `cdd_cagr` fields were shipped as latent
no-ops in Phase 3; Phase 4 fills them from Cal-Adapt projections without any device or
simulation code changes.

### 1.5 Climate Trend (Cal-Adapt)

The static TMY3 baseline represents 1991–2005 average conditions. Over a 20-year forward
simulation, California's climate shifts measurably. Phase 4 populates the trend fields
from **Cal-Adapt** (https://cal-adapt.org/) — CEC/LBNL's official CA climate projection
dataset, which provides county-level HDD/CDD trends under RCP 4.5 (moderate) and RCP 8.5
(high-emissions) scenarios through 2100.

**How the simulation applies the trend:**
```python
# In HESModel.step(), year n of the simulation:
effective_hdd = climate.monthly_hdd_65f * (1 + climate.hdd_cagr) ** n
effective_cdd = climate.monthly_cdd_65f * (1 + climate.cdd_cagr) ** n
```
The HVAC device receives `effective_hdd` / `effective_cdd` instead of the static arrays.
One-line change per degree-day array; no architecture impact — the latent fields make
this a drop-in extension.

**Build pipeline:** `build_climate_db.py` gains a step that reads Cal-Adapt county-level
HDD/CDD projections, fits a CAGR per CEC zone (zones map to counties), and writes
`hdd_cagr` / `cdd_cagr` into each zone record. Directional expectation for CA: HDD
declining (warmer winters), CDD increasing (hotter summers). The effect is non-trivial in
inland and mountain zones, minor on the coast.

**Scenario selector (UI):** a user-facing choice of trend scenario, consistent with the
transparent-scenario philosophy used elsewhere in WhyWatt:
- **None** — static TMY3, no trend (CAGR = 0; reproduces Phase 3 behavior exactly)
- **Moderate (RCP 4.5)** — default
- **High (RCP 8.5)**

### 1.6 UI Changes

- **Home Profile panel:** Add a ZIP code text field (5 digits).
  - On valid CA ZIP: show resolved zone as confirmation chip —
    e.g., `📍 CZ4 — San Jose  |  HDD 1,910 · CDD 340`
  - On ZIP not found in database: show warning —
    `⚠ ZIP not recognized — using Bay Area defaults (CZ4)`
- **Climate trend selector** in the Rate/Projection panel (None / RCP 4.5 / RCP 8.5).
- **No network calls at runtime.** All lookups are local JSON reads.
- **Help link** next to the ZIP field → `climate.html` explaining CEC zones, TMY3, and the trend scenarios.

### 1.7 Impact on Existing Devices

| Device | Impact |
|--------|--------|
| GasFurnace | Monthly HDD drives consumption — high impact |
| HeatPumpHVAC (heating) | Monthly HDD + COP curve (§4) — high impact |
| HeatPumpHVAC (cooling) | Monthly CDD — high impact |
| GasWaterHeater | Monthly inlet water temp — low-to-medium impact |
| HeatPumpWaterHeater | Monthly inlet water temp — low impact |
| Dryer, Induction, EV, LightsAndPlugs | No impact |

### 1.8 Decisions Made / Open Questions

- [x] **Scope: California-only for the climate DB.** Script supports `--states` flag.
- [x] **ZIP mapping method: CEC Climate Zones for CA; nearest-TMY3 fallback for other states.**
- [x] **EPW format** for TMY3 source files (universal standard, parseable without NREL tools).
- [x] **Two-file JSON design:** `tmy3_zones.json` (16 zone records) + `zip_to_zone.json` (ZIP index).
- [ ] **Cal-Adapt aggregation:** county→CEC-zone mapping method (area-weighted vs. reference-city county). Recommendation: reference-city county, for consistency with the TMY3 baseline choice.
- [ ] **Trend default scenario:** RCP 4.5 (moderate) vs. None. Recommendation: RCP 4.5 default, with a clear in-UI note and a one-click "None" for skeptical audiences.

## §2 — EIA-Based Rate Modeling

### 2.1 Motivation and Decision

Phase 2/3 rate data is PG&E-specific (CPUC filings, PG&E Advice Letters). Users outside
PG&E territory see incorrect rates. Phase 4 adds EIA state-level rates as a selectable
option alongside the existing PG&E data.

**Decisions (resolved):**
- PG&E CPUC data stays as-is and remains a selectable rate source (not replaced).
- EIA state data is a second selectable rate source — starting with California only.
- The rate source is a user choice in the UI, not auto-detected from ZIP.
- The infrastructure (build script + data schema) supports adding any US state by
  running the script for that state. No code changes needed to add a new state.

### 2.2 Rate Source Options

| Source | Label in UI | Coverage | Accuracy |
|--------|------------|----------|----------|
| PG&E CPUC | "PG&E (CPUC tariff)" | PG&E territory only | Highest — actual tariff filings |
| EIA California | "California average (EIA)" | All CA ZIPs | Medium — statewide average across all utilities |

The user selects the rate source via a dropdown in the Rate/Projection panel. Default:
PG&E CPUC (unchanged). When EIA California is selected, the simulation uses EIA's
residential average rate and historical CAGR. The ACC shape is only available for the
PG&E source; with EIA source, ACC is disabled and a flat seasonal shape is used instead.

### 2.3 Data Source

**EIA Open Data API (free, no key required for bulk downloads):**
- Electricity: EIA-861 / EIA Form 861M — monthly state-level residential retail rate (¢/kWh)
- Natural gas: EIA Natural Gas Monthly — monthly state-level residential rate ($/Mcf, converted to $/therm)

Both series go back to 2001. The build script downloads once and snapshots the data.

### 2.4 Offline Data Pipeline

A build script (`scripts/build_eia_rates.py`) will:

1. Accept a `--states` argument (default: `CA`; accepts multiple: `--states CA TX NY`)
2. Download EIA bulk electricity and natural gas rate series for residential sector
3. Filter to the requested state(s)
4. Compute the 10-year historical CAGR for each state (used as the default escalation scenario)
5. Compute a monthly seasonal shape (12-month ratio array) from multi-year averages
6. Merge results into `data/rates/eia_rates_by_state.json` (append-safe)

Schema (per state — JSON field keys are unchanged data identifiers; `"gas"` here is the
natural-gas series):
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

### 2.5 Integration with Existing Rate Framework

The existing `RateLoader` class interface is unchanged. A new factory method is added:

```python
RateLoader.from_eia(state: str, fuel: str) -> RateLoader
# Reads from data/rates/eia_rates_by_state.json
# fuel: "electricity" | "gas"   ("gas" = natural-gas series key, unchanged)
# Uses EIA current_rate as base_rate, historical_cagr_10yr as default escalation
```

The `RateLoader.from_pge(fuel)` factory is made explicit to match the pattern. Both
factories return the same `RateLoader` type — the simulation code is unaware of which
source was used.

### 2.6 UI Changes

- **Rate panel:** Add a **"Rate source"** dropdown:
  - "PG&E (CPUC tariff)" ← default
  - "California average (EIA)"
  - _(future states appear here as their data files are added)_
- **Source label:** Below the dropdown, show data vintage:
  e.g., "EIA data: 2024 annual average, extracted 2026-06-02"
- **ACC note:** When EIA source is selected, the ACC section shows:
  "ACC shape available for PG&E only — using flat seasonal shape"
- **Manual override:** allow user to enter a custom base rate ($/kWh, $/therm) for cases
  where neither source matches their bill

### 2.7 Resolved / Open Questions

- [x] **PG&E CPUC data retained and selectable** — not replaced.
- [x] **EIA is a selectable option, not auto-detected** — user picks rate source explicitly.
- [x] **CA-only initially; add-state workflow defined** — run script, commit JSON, done.
- [x] **Residential sector rates** — not blended with commercial.
- [x] **Rate basis: most recent 12-month average** — more stable than single-month.
- [ ] Should the EIA dropdown dynamically populate from available states in the JSON,
      or be a hardcoded list? (Recommendation: dynamic — reads `data/rates/eia_rates_by_state.json` keys)

---

## §3 — Transportation: ICE & Electric Vehicles

### 3.1 Motivation

Phase 3 modeled the EV charger only as a household electricity load (`miles_per_day` ×
efficiency tier → kWh). It had no notion of the **gasoline (ICE) vehicle being replaced**,
so it could not show the central transportation story: the fuel-cost and externality
delta of moving miles from gasoline to electric. Phase 4 models the household's driving
as a **Current vs. Plan** comparison — the same idiom used for home appliances — and adds
the climate and health externalities of gasoline combustion, the transportation analogue
of the natural-gas social-cost panel (Phase 3 §6).

This section supersedes Phase 3 §2.4 (EV Charger — Miles-per-Day Model).

### 3.2 Model Structure — Current vs. Plan

The household's driving is described by four numbers in each of two states:

| Input | Unit | Meaning |
|-------|------|---------|
| Gasoline miles / year | mi/yr | Annual miles driven on gasoline (ICE) |
| Fuel economy | MPG | ICE vehicle efficiency |
| Electric miles / year | mi/yr | Annual miles driven electric |
| Vehicle efficiency | mi/kWh | EV efficiency (battery-out — see §3.4) |

- **Current State** describes how the household drives today (e.g., 12,000 gasoline mi at
  28 MPG, 0 electric mi).
- **Plan State** (gated by a **"Plan"** checkbox, matching the journey idiom) describes the
  future. The change between states is either a **mode shift** (miles moving from gasoline
  to electric) or an **efficiency change** (a more efficient EV / different ICE), or both —
  all captured by editing the four numbers.
- **Savings** = (Current fuel cost + externality) − (Plan fuel cost + externality), per year,
  feeding the same JC cost charts as the rest of the journey.

### 3.3 ICE (Gasoline) Vehicle — Energy, Cost, Externalities

```
gallons_per_year   = gasoline_miles_per_year / mpg
fuel_cost          = gallons_per_year × gasoline_price_per_gallon
climate_externality= gallons_per_year × co2_kg_per_gallon × scc_per_kg
health_externality = gallons_per_year × health_cost_per_gallon
```

All three transportation externalities key off **gallons/year**, exactly as the natural-gas
social cost keys off therms/year — so the same enable-toggle + slider pattern from Phase 3
§6 applies. Defaults and ranges (documented in `docs/help/transportation.html`):

| Quantity | Default | Basis |
|----------|---------|-------|
| `co2_kg_per_gallon` | 8.887 kg/gal | EPA standard tailpipe CO₂ per gallon of gasoline (fixed constant) |
| `scc_per_ton` | $190/t CO₂ | EPA 2023 SC-CO₂ central (2% discount). Slider $51–$340. **Shared** with the natural-gas climate slider — same SCC drives both. |
| Climate cost (derived) | ~$1.69/gal | 0.008887 t × $190/t. Recomputes live from the SCC slider. |
| `health_cost_per_gallon` | $0.75/gal | Central of tailpipe + upstream PM/ozone mortality (Tessum/Hill/Marshall ~$0.50 floor). Slider $0.40–$3.00. |

> **Do not stack with the "$3.80/gallon true cost" figure.** Widely-cited combined
> estimates (e.g., Shindell/Duke 2015) bundle climate **and** health into one number;
> our two components are deliberately non-overlapping so each is independently defensible
> and independently toggleable. The help page documents this explicitly.

**SCC consistency note:** the social cost of carbon should be a single tool-wide
parameter. The natural-gas climate slider (Phase 3 §6) and this gasoline climate cost
both derive from it — a homeowner shouldn't see two different carbon prices. Implementation
folds the Phase 3 `SocialCostConfig.climate_rate` ($/therm) and this $/gallon figure into a
common `scc_per_ton`, with each fuel applying its own emission factor.

### 3.4 Electric Vehicle — Energy and Charging Efficiency

```
battery_kwh_per_year = electric_miles_per_year / vehicle_eff_mi_per_kwh   # battery-out
wall_kwh_per_year    = battery_kwh_per_year / charging_efficiency         # billed at the wall
ev_electricity_cost  = wall_kwh_per_year × electricity_rate
```

**Charging efficiency** captures wall-to-battery losses (AC→DC conversion, thermal):
- Default `charging_efficiency = 0.88` (Level 2 home charging; Level 1 slightly lower).
- Held **constant across Current and Plan** (it's a property of home charging, not the trip).

**Critical input-basis decision — which mi/kWh the user enters:**
- The input is defined as **battery-out / dashboard efficiency** (what a Tesla/onboard
  display reports as consumption). Charging efficiency is then applied **separately** to
  reach billed wall energy. A tooltip states this.
- This avoids double-counting: the EPA window-sticker / fueleconomy.gov mi/kWh is already
  **wall-to-wheels** (charging loss baked in). If a user enters that number instead,
  applying `charging_efficiency` again would under-count range per kWh. The help page warns
  to use the **dashboard** number, or to set charging efficiency to 1.0 if entering the
  EPA figure.

The `wall_kwh_per_year` total distributes across the existing time-of-use charging
schedule (retained from the Phase 3 `ScheduleDevice` backend) for rate purposes.

### 3.5 The Multi-Vehicle UI Problem

Modeling *n* vehicles with four fields each, across Current and Plan, becomes crowded fast
(3 vehicles × 4 fields × 2 states = 24 inputs). A naive "just enter one blended MPG" has a
correctness trap: **miles add, but MPG does not** — fuel economy combines harmonically, so a
12k-mi 40-MPG car plus a 6k-mi 16-MPG truck is **not** "28 MPG." Aggregation must happen at
the **gallons** (and kWh) level, never by averaging efficiencies.

**Decision — two input modes** (consistent with the conservative/central/detailed philosophy
and the Phase 3 §13 appliance expand/collapse idiom):

- **Simple (default):** total annual miles split gasoline / electric, plus *one*
  representative MPG and one mi/kWh. A tooltip directs users with very different vehicles to
  detailed mode and warns against hand-blending MPG. Good enough for the headline advocacy
  number.
- **Detailed:** 1–3 vehicle slots, each collapsing to a one-line summary, **summed at the
  consumption level** behind the scenes (Σ gallons, Σ kWh). Cap at 3 to bound UI complexity.

A common middle ground covers most households without unbounded UI: a single primary
vehicle plus an optional **"second vehicle"** toggle — the two-car case (efficient EV
commuter + gasoline hauler) is exactly where per-vehicle detail matters most; beyond two,
aggregate.

### 3.6 Chart Integration

Transportation fuel cost and externalities feed the existing **JC** charts on the same
footing as home energy:
- **JC-1 / JC-2:** transportation fuel cost is added to annual and cumulative totals;
  gasoline externalities (when enabled) appear as the same dashed "+ social/health" overlay
  used for natural gas, so the home and transport externalities sum into one true-cost line.
- **JC-4:** new stacked segments — "Gasoline (fuel)", "Gasoline — climate cost",
  "Gasoline — health cost", and "EV charging" — sit alongside the appliance segments.
- **EU charts:** transportation energy may optionally appear as gallons-equivalent and kWh;
  externalities are **not** shown in EU (energy quantities, not costs) — same rule as §6.

### 3.7 New `TransportationConfig` Dataclass (sketch)

```python
@dataclass
class VehicleState:
    gasoline_miles_yr: float = 12_000
    mpg:               float = 28.0
    electric_miles_yr: float = 0.0
    ev_eff_mi_per_kwh: float = 3.5    # battery-out / dashboard basis

@dataclass
class TransportationConfig:
    current: VehicleState = field(default_factory=VehicleState)
    plan:    VehicleState = field(default_factory=VehicleState)
    plan_enabled:        bool  = False   # "Plan" checkbox
    charging_efficiency: float = 0.88    # constant across states
    # Gasoline externalities (mirror SocialCostConfig pattern):
    climate_enabled: bool  = True        # uses tool-wide scc_per_ton
    health_enabled:  bool  = True
    health_cost_per_gallon: float = 0.75
    # detailed mode (optional): list of VehicleState pairs, summed at gallons/kWh level
```

Like `SocialCostConfig`, this is a **model-level** object on `HESModel`, not injected into
devices. The EV's wall-kWh still flows through the existing charging-schedule device for
time-of-use rating; the ICE side is pure cost/externality arithmetic with no device.

### 3.8 Decisions Made / Open Questions

- [x] **Current vs. Plan structure**, gated by a "Plan" checkbox — mirrors the journey idiom.
- [x] **mi/kWh is battery-out/dashboard basis**; charging efficiency applied separately, constant across states.
- [x] **Gasoline externalities split into non-overlapping climate + health**, each toggleable; do not stack with combined "$X/gal true cost" figures.
- [x] **SCC is one tool-wide parameter** shared by natural-gas and gasoline climate costs.
- [x] **Multi-vehicle: simple (default) + detailed (≤3 slots)**; aggregate at gallons/kWh, never average MPG.
- [ ] **Default health cost per gallon:** $0.75 central proposed; confirm vs. $0.50 conservative floor for the default advocacy posture.
- [ ] **CA-specific refinement:** CA gasoline blend (ethanol) and LCFS context — worth a help-page note; not a v1 formula change.

---

# Phase 4 — Unified device legend, Journey Timeline v2, and CapEx recolor

> Append this block to `docs/Phase4_spec.md`. Renumber the `§4.x` headings to
> continue your existing Phase 4 numbering if needed. Three deliverables:
> (1) a single source-of-truth device style map, (2) a redesigned Journey
> Timeline, (3) the Equipment Replacement (CapEx) chart recolored to match.

---

## §4.1 Canonical device style map (single source of truth)

Every chart that references a device must pull color, code, and label from one
dict. No more ad-hoc `C_BASE` / `C_ELEC` two-color scheme for device-aware charts.

Create `src/ui/device_style.py`:

```python
# One source of truth for device color / code / label across ALL charts.
# Colors chosen to be distinct and to read on both light and dark canvases.
# Matplotlib renders on a light bg by default -> use `color`.
# `color_dark` is reserved for a future dark-themed export path.

DEVICE_STYLE = {
    "hvac":    {"label": "HVAC",                "code": "HV", "color": "#D85A30", "color_dark": "#F0997B"},
    "wh":      {"label": "Water heater",        "code": "WH", "color": "#E24B4A", "color_dark": "#F09595"},
    "dryer":   {"label": "Dryer",               "code": "DR", "color": "#7F77DD", "color_dark": "#AFA9EC"},
    "cooktop": {"label": "Cooktop",             "code": "CK", "color": "#C9821C", "color_dark": "#FAC775"},
    "ev":      {"label": "EV charger",          "code": "EV", "color": "#639922", "color_dark": "#97C459"},
    "lights":  {"label": "Lights & appliances", "code": "LA", "color": "#378ADD", "color_dark": "#85B7EB"},
    "solar":   {"label": "Solar + battery",     "code": "SB", "color": "#1D9E75", "color_dark": "#5DCAA5"},
    "panel":   {"label": "Electrical panel",    "code": "EP", "color": "#888780", "color_dark": "#B4B2A9"},
}

# Stable stacking / legend order (big-ticket end uses first, infra last).
DEVICE_ORDER = ["hvac", "wh", "dryer", "cooktop", "ev", "lights", "solar", "panel"]

def dstyle(key: str) -> dict:
    """Lookup with a safe fallback so an unmapped slot never crashes a chart."""
    return DEVICE_STYLE.get(key, {"label": key.title(), "code": key[:2].upper(),
                                  "color": "#888780", "color_dark": "#B4B2A9"})
```

Map each existing slot to a `device_style` key. Add a `style_key` attribute to
`DeviceSlot` and `CapExOnlySlot` (panel -> `"panel"`, baseload -> `"lights"`,
solar -> `"solar"`, etc.) so charts never string-match on display names.

| Slot                 | style_key | Color (light) | Code |
|----------------------|-----------|---------------|------|
| HVAC                 | `hvac`    | `#D85A30`     | HV   |
| Water heater         | `wh`      | `#E24B4A`     | WH   |
| Dryer                | `dryer`   | `#7F77DD`     | DR   |
| Cooktop              | `cooktop` | `#C9821C`     | CK   |
| EV charger           | `ev`      | `#639922`     | EV   |
| Lights & appliances  | `lights`  | `#378ADD`     | LA   |
| Solar + battery      | `solar`   | `#1D9E75`     | SB   |
| Electrical panel     | `panel`   | `#888780`     | EP   |

A shared legend helper used by both charts (and, later, the cost-by-category and
device charts):

```python
from matplotlib.lines import Line2D

def device_legend_handles(keys):
    return [Line2D([0], [0], marker="o", linestyle="",
                   markerfacecolor=dstyle(k)["color"],
                   markeredgecolor=dstyle(k)["color"], markersize=8,
                   label=dstyle(k)["label"]) for k in keys]
```

---

## §4.2 Journey Timeline v2

### 4.2.1 Intent
The current timeline reads as cramped and doesn't answer the user's real
question: **when should I do each replacement?** The redesign puts the year axis
down the middle, the chosen swaps above the line ("Your journey"), and the
forced wear-out replacements below the line ("Do nothing"). A connector ties each
appliance's two events together so the user can see how many years *early* they'd
be acting — and align a swap to a natural wear-out year or (future) a rebate
window.

Two prototypes were built; **implement Prototype A** as the default chart.
Prototype B is captured in §4.2.5 as an optional second view.

### 4.2.2 Data model
Each appliance contributes up to two timeline events:

- **Journey event** — at `slot.install_year` (the swap the user planned). Always
  present for any planned slot. Marker: filled circle in the device color, 2-letter
  code inside, placed ABOVE the axis.
- **Do-nothing event** — the year the *existing* unit forcibly wears out and is
  replaced in-kind. Marker: open/dashed circle in the device color, code inside,
  placed BELOW the axis.

Compute the do-nothing year from the existing unit's remaining life:

```python
do_nothing_year = max(1, slot.lifespan - slot.existing_age)
```

This needs a per-slot `existing_age` (years). If not already modeled, add it as an
optional Home Profile / appliance-detail input (default = `lifespan // 2`, i.e.
"mid-life", so the timeline is sensible before the user customizes). **Open
question flagged in §4.5.**

Add-on slots that have no incumbent (EV charger, electrical panel, solar+battery)
produce a **journey event only** — no do-nothing marker, no connector. Tag them
visually as add-ons.

`gap = do_nothing_year - install_year`:
- `gap > 0` -> acting early (capital retired before end of life). Annotate `"{gap}y early"`.
- `gap == 0` -> swapping at wear-out (most capital-efficient). Annotate `"on time"`.
- `gap < 0` -> swapping after the unit would already have died (annotate `"overdue"`; rare, but handle it).

### 4.2.3 Layout (matplotlib)
- **Bigger figure + fonts.** This is the headline complaint. Target ~`figsize=(9.5, 4.2)`,
  `dpi>=110`. Minimum font sizes: axis tick labels **12**, marker codes **11**,
  side labels ("Your journey"/"Do nothing") **12**, gap annotations **11**,
  legend **10**, title **13** bold. No text below 10pt anywhere on this chart.
- Central spine: draw the year axis as a horizontal rail at `y=0`. Hide the
  y-axis entirely (`ax.get_yaxis().set_visible(False)`, despine top/left/right).
  `ax.set_ylim(-1.25, 1.25)`.
- X axis: integer year ticks `0..N`, `ax.tick_params(labelsize=12)`, label `"year"`.
- Journey markers at `y = +0.62`; stagger to `+0.92` only when two journey events
  share a year (e.g. panel + EV both at year 1) to avoid overlap.
- Do-nothing markers at `y = -0.62` (stagger to `-0.92` on collision).
- Drift connector per paired appliance: dashed line in the device color from the
  journey marker to the do-nothing marker, `lw=1.3, alpha=0.7, zorder=1`. Draw the
  rail and markers at higher `zorder` so the connector reads as passing behind the rail.
- Marker glyph: `ax.scatter` with `s≈260`; journey = filled (`color`), do-nothing =
  open (`facecolors="none"`, `edgecolors=color`, dashed via a thin ring). Put the
  2-letter code centered on the marker with `ax.annotate`, white text on filled,
  device color on open.
- Side labels: `ax.text` "Your journey" just above the rail at the far left
  (year-0 dead zone) and "Do nothing" just below it.
- Gap annotation: small text directly under each do-nothing marker (`"on time"` /
  `"3y early"`), device color.

### 4.2.4 Rebate window (forward-looking, OFF by default)
We have no rebate-timing data yet, so ship this dark. When/if a rebate window is
provided per device or globally, shade it with:

```python
ax.axvspan(rebate_start, rebate_end, color="#EF9F27", alpha=0.12, zorder=0)
ax.text((rebate_start + rebate_end) / 2, 1.15, "rebate window",
        ha="center", fontsize=11, color="#8a6d1a")
```

Gate behind `show_rebate_window: bool = False`. Document in the UI that it is
illustrative until real incentive data is wired in.

### 4.2.5 Prototype B (optional second view — "aligned lanes")
One horizontal lane per appliance against a shared top year axis. In each lane a
bar spans `[install_year, do_nothing_year]` (the runway), with the filled journey
marker and the dashed do-nothing marker at the ends; an aligned swap shows a
single filled marker wrapped in a dashed ring. Add-ons render in a separate
"New add-ons" group with just the filled marker. Trades the literal above/below
mirror for per-appliance scanability. Implement only if we add a chart sub-toggle;
not required for v2.

---

## §4.3 Equipment Replacement (CapEx) chart — recolor to match

Replace the two-color grouped bars (`C_BASE` / `C_ELEC`) with **grouped + stacked
bars colored by device**, so this chart and the timeline share one visual language
when viewed side by side.

- Per year, two bars: **left = do nothing**, **right = your journey** (`width≈0.38`,
  offset `±width/2`).
- Each bar is **stacked by device** using `DEVICE_ORDER`, each segment in the device
  color from `DEVICE_STYLE`.
- Secondary cue (don't rely on color alone to separate the two columns): render
  do-nothing segments **hatched** (`hatch="//"`) with the device color as edge, and
  journey segments **solid**. This mirrors the prototype.
- Shared device legend via `device_legend_handles(...)`, plus a tiny note: "left
  bar (hatched) = do nothing · right bar (solid) = your journey".
- Money formatter on y (`$k`), `tick labelsize >= 11`, title 13 bold.

```python
def make_capex_v2(model, n):
    fig, ax = _new_fig(figsize=(9.5, 4.0))
    yrs = np.arange(1, n + 1)
    w = 0.38
    for grp, sign, hatch in (("baseline", -1, "//"), ("journey", +1, None)):
        home = model.baseline_home if grp == "baseline" else model.journey_home
        bottoms = np.zeros(len(yrs))
        for key in DEVICE_ORDER:
            seg = np.array([home.capex_by_device.get(key, {}).get(int(y), 0) for y in yrs])
            if not seg.any():
                continue
            c = dstyle(key)["color"]
            ax.bar(yrs + sign * w / 2, seg, w, bottom=bottoms,
                   color=("none" if hatch else c),
                   edgecolor=c, hatch=hatch, linewidth=0.6, zorder=3)
            bottoms += seg
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(_money))
    ax.set_xlabel("year"); ax.set_ylabel("replacement cost")
    ax.tick_params(labelsize=11)
    ax.set_title("Equipment replacements (CapEx)", fontsize=13, fontweight="bold")
    keys_present = [k for k in DEVICE_ORDER
                    if any(model.journey_home.capex_by_device.get(k)) or
                       any(model.baseline_home.capex_by_device.get(k))]
    ax.legend(handles=device_legend_handles(keys_present), fontsize=10,
              ncol=2, framealpha=0.85, loc="upper left")
    _style(ax); fig.tight_layout(pad=1.0)
    return fig
```

**Model change required:** the homes currently expose `capex_by_year` (a flat
`{year: total}`). To color CapEx by device, also collect **`capex_by_device`** as
`{style_key: {year: amount}}` on each home during the run. `capex_by_year` stays
for any chart that still wants the total.

---

## §4.4 Shared usage
The cost-by-category and device-breakdown charts should migrate to the same
`DEVICE_STYLE` colors in a follow-up so the entire dashboard is one palette.
Not in scope for this change, but keep the helper generic enough to reuse.

---

## §4.5 Open questions / data we don't have yet
1. **Do-nothing wear-out year.** Needs `existing_age` per slot. Add as an input
   (appliance-detail expander), default `lifespan // 2`. Confirm desired default.
2. **Rebate window.** No incentive-timing data in the model. Shipping the band
   OFF; revisit when we have per-device or program-level windows.
3. **Prototype A vs B.** A ships as default (matches the literal brief). Decide
   later whether B is worth a sub-toggle.
4. **Aligned swaps** (gap == 0) — confirm the "on time" wording vs. something like
   "at end of life".

---

## §4.6 Claude Code prompt

```
Implement §4.1–§4.3 of docs/Phase4_spec.md.

Step 1 — src/ui/device_style.py:
  Add DEVICE_STYLE, DEVICE_ORDER, dstyle(), device_legend_handles() exactly as specced.
  Add a `style_key` attribute to DeviceSlot and CapExOnlySlot; set it for every
  configured slot in _build_slot_configs().

Step 2 — model:
  Add `existing_age` (int years, optional) to device slots; default lifespan // 2.
  Collect capex_by_device = {style_key: {year: amount}} on baseline_home and
  journey_home alongside the existing capex_by_year.
  Add tests: capex_by_device sums per year equal capex_by_year; add-on slots
  (panel/ev/solar) never appear in baseline_home.capex_by_device.

Step 3 — charts (app.py):
  Replace the Journey Timeline renderer with make_journey_timeline_v2 per §4.2:
    central year rail, journey markers above (filled, code), do-nothing markers
    below (open dashed, code), per-device dashed drift connectors, gap annotations,
    side labels, larger fonts (no text < 10pt). Rebate window gated OFF by default.
    Add-on slots: journey marker only, tagged as add-on, no connector.
  Replace make_capex with make_capex_v2 per §4.3: grouped (do nothing / your
    journey) + stacked-by-device, do-nothing hatched, shared device legend.

Step 4 — verify:
  solara run src/app.py
  - Journey Timeline: axis centered, "Your journey" above / "Do nothing" below,
    readable fonts, drift lines link each appliance's swap to its wear-out year,
    EV/panel/solar show no do-nothing marker.
  - CapEx: two bars per year, left hatched (do nothing) / right solid (your
    journey), segments colored per device, legend matches the timeline colors.
  All existing tests still pass.
```

---

## §4.7 Tests (add to tests/test_charts.py)

```python
def test_device_style_covers_all_slots():
    for key in DEVICE_ORDER:
        s = dstyle(key)
        assert s["color"].startswith("#") and len(s["code"]) == 2

def test_do_nothing_year_from_existing_age():
    # lifespan 15, existing_age 9 -> wears out in 6 years
    assert max(1, 15 - 9) == 6

def test_addons_have_no_do_nothing_event(model_with_addons):
    for key in ("ev", "panel", "solar"):
        assert key not in model_with_addons.baseline_home.capex_by_device

def test_capex_by_device_sums_to_capex_by_year(model_run):
    for y, total in model_run.journey_home.capex_by_year.items():
        s = sum(d.get(y, 0) for d in model_run.journey_home.capex_by_device.values())
        assert abs(s - total) < 1e-6
```

## §4 — Temperature-Dependent Heat Pump COP

> Relocated from Phase 3 §2.1. Moved here because it requires the ZIP-level monthly
> temperatures introduced in §1 — in Phase 3, HVAC retains Phase 2's constant COP.

**Phase 2/3 model:** constant COP for heating (e.g., 3.5), constant SEER for cooling.

**Problem:** Heat pump COP drops significantly in cold weather. A COP 3.5 unit at 47°F
may deliver COP 2.0 at 17°F. This matters for mountain ZIPs (Tahoe, Big Bear) and
cold-snap months — and only becomes modelable once §1 provides per-zone monthly temps.

**Proposed model:** A simple two-point COP curve:
- `cop_47` — rated COP at 47°F (AHRI standard rating condition, user-facing)
- `cop_17` — rated COP at 17°F (AHRI cold-climate rating, user-facing)
- Monthly effective COP interpolated from average monthly temperature (derived from HDD/CDD per §1)

This matches NEEP ASHP performance-data methodology and is defensible.

**Cooling:** SEER remains a constant (EER degradation in extreme heat is second-order for California).

**UI change:** In the HVAC detail panel, expose `cop_47` and `cop_17` sliders alongside the existing SEER slider.

**Validation targets (climate-dependent rows that move here with the curve):**

| Device | Config | Expected | Tolerance |
|--------|--------|---------|-----------|
| HeatPumpHVAC heating | UA=500, cop_47=3.5, cop_17=2.0, HDD=1910 (CZ4) | ~1,930 kWh/yr | ±5% |
| HeatPumpHVAC heating | UA=500, cop_47=3.5, cop_17=2.0, HDD=6800 (CZ16 Tahoe) | ~6,800 kWh/yr | ±10% |

---

## §5 — Income-Qualified Rebates

Carried from the Phase 2 → Phase 3 deferred list. TECH+ and HEAR program rebates vary by
income-qualification tier and utility. This requires:
- Income-qualification input (AMI tier or income range)
- Per-device rebate lookup table (IQ-specific)
- Rebate applied to CapEx in year of swap

Still outline-only — promoted to an active Phase 4 candidate but not yet specified in detail.

---

## §6 — Monte Carlo Uncertainty Bands

Carried from the Phase 2 → Phase 3 deferred list. The deterministic model produces
single-value outputs. Monte Carlo would add ±1σ bands to the annual cost chart and the
summary savings figure — sampling over rate-escalation CAGR, SCC, health cost/gallon, COP,
and other key uncertain inputs.

Still outline-only.

---

## §7 — HomeConfig JSON Save/Load

Carried from the Phase 2 → Phase 3 deferred list. Allows advocates to save a homeowner
session and resume it later, or share a configuration by file. With §1–§3 added, the saved
config now spans climate ZIP, rate source, and the transportation model in addition to the
appliance journey.

Still outline-only.

---

## §8 — Solar & Battery (Physics & Net Metering)

> Physics feature — belongs with §3 (Transportation) and §4 (HVAC COP), not the deferred
> backlog; placed here only to avoid renumbering. Supersedes the Phase 2/3 "% coverage"
> slider.

### 8.1 Why replace the "% coverage" slider

A single % input conflates two different things: how much the array *produces* (physics)
and how much it *saves* (economics). They diverge sharply under NEM 3.0, where exported
kWh earn avoided-cost (~5–8 ¢/kWh), not retail. Phase 4 makes system **size** the input and
derives both production and bill offset transparently, so a skeptical homeowner can audit
each step.

### 8.2 Model — size → production → value

```
system_kW           = panels × kW_per_panel
annual_production   = system_kW × specific_yield               # kWh/yr
self_consumed_kWh   = annual_production × self_consumption_fraction
exported_kWh        = annual_production − self_consumed_kWh
annual_bill_savings = self_consumed_kWh × retail_rate
                    + exported_kWh      × export_rate
energy_coverage_%   = annual_production / annual_consumption   # DERIVED, displayed; may exceed 100%
```

`self_consumption_fraction` is **derived** from `battery_kWh` and `system_kW` (§8.3), not
entered raw. `specific_yield` is the single number anchored to PVWatts.

### 8.3 Defaults

**System size & production**

| Parameter | Default | Range | Editable? | Basis |
|---|---|---|---|---|
| `panels` | 15 | 1–20 | **Primary slider (main)** | Maps to roof size / installer quotes; ≈15 = median CA residential |
| `kW_per_panel` | 0.42 | 0.35–0.50 | Advanced (detail) | ~0.40 standard, ~0.50 premium for 2025–26 modules; 0.35 floor = older arrays |
| `specific_yield` (kWh/kW/yr) | 1,500 | 1,300–1,800 | Advanced / PVWatts (detail) | CA PVWatts typical; ~1,400 foggy coast, ~1,650 inland/desert |
| `system_losses` | 14% | — | Fixed | PVWatts default; folded into `specific_yield`, not a separate control |

**Battery & self-consumption**

| Parameter | Default | Range | Editable? | Basis |
|---|---|---|---|---|
| `battery_enabled` | **On** ✓ | on/off | **Primary toggle (main)** | NEM 3.0 battery attach rate ~70%+; NEM 2.0 closed Apr 2026 — any new install is NEM 3.0 + battery |
| `battery_kWh` | 13.5 | 0–40 | Detail | One Powerwall-class unit; range allows 0 to ~3 units |
| `self_consumption` (solar-only) | 35% | 25–45% | Derived (shown) | Midday production vs. evening-skewed electrified load |
| `self_consumption` (with battery) | 80% | 60–90% | Derived (shown) | Battery shifts midday surplus to evening; not 100% (finite capacity) |

**Net metering / export rate**

| Parameter | Default | Range | Editable? | Basis |
|---|---|---|---|---|
| `nem_mode` | NEM 3.0 (NBT) | 3.0 / 2.0 | Toggle (detail) | 3.0 = any new solar (2.0 closed to new PTO since 4/2026); 2.0 = existing pre-2023 solar |
| `export_rate` — NEM 3.0 | = ACC | — | Derived | Reuses Phase 2 ACC shape; ~$0.05–0.08/kWh avg |
| `export_rate` — NEM 2.0 | retail − NBC | — | Derived | Retail TOU (already projected) minus NBC |
| `nbc` (non-bypassable charge) | $0.025/kWh | $0.02–0.03 | Advanced (detail) | CPUC NBC component; NEM 2.0 only |
| `retail_rate` | — | — | From rate model | Not solar-specific; reuses existing PG&E/EIA rate |

> **Default posture — decided:** battery defaults **On**, NEM 3.0 (NBT). This reflects
> the actual market: NEM 2.0 closed to new PTO in April 2026, and battery attach rates on
> new CA solar installs are ~70%+. Any homeowner buying solar today gets NEM 3.0 + battery.
> Users describing a solar-only or legacy NEM 2.0 system can toggle battery off or switch
> the NEM mode in the detail panel.

### 8.4 Net metering — one export-rate switch, not two models

The only thing NEM 2.0 vs 3.0 changes is `export_rate`:
- **NEM 3.0 / NBT** (default, any new solar): `export_rate = ACC` — reuses the Phase 2 ACC
  shape directly. Time-variant; high only on summer evenings, low midday.
- **NEM 2.0** (optional, existing pre-2023 solar): `export_rate = retail_rate − nbc`.

With a battery on (default), self-consumption is ~80%, so the export term is a small
correction regardless of tariff — **no hour-by-hour NEM engine is needed.** NEM 2.0 is a
"describe my existing system" toggle, not part of forward-looking recommendations: it
closed to new PTO in April 2026, and its grandfathering terms are politically contested
(AB 942, 2025). NEM 3.0 also permits oversizing to 150% of current usage when electrifying
— legitimately relevant here, since the journey raises consumption.

### 8.5 UI — main panel vs. detail

**Main (collapsed):** the one sizing lever + the headline. Physical quantities only.
```
┌─────────────────────────────────────┐
│ Solar & Battery                     [?] [▼]  │
│ ──────────────────────────────────── │
│ Panels   ───────●──────  15    ( 6.3 kW )    │
│ Battery  [● On]  13.5 kWh                     │
│                                              │
│ ≈ 9,450 kWh/yr  ·  covers ~72% of your use   │
└─────────────────────────────────────┘
```

**Detail (expanded):** PVWatts knobs, battery size, net metering, and the production split.
```
│ ── Advanced (from PVWatts) ────────────────  │
│ kW per panel     ────●───   0.42 kW           │
│ Specific yield   ───●────   1,500 kWh/kW/yr   │
│                             [ Run PVWatts ↗ ] │
│ Battery size     ──●─────   13.5 kWh          │
│ ── Net metering ─────────────────────────  │
│ Tariff   (●) NEM 3.0 / NBT  (new solar)       │
│          ( ) NEM 2.0        (existing solar)  │
│ Export credit:  ACC  ~$0.06/kWh avg           │
│ ── This year ───────────────────────────  │
│ Production   9,450 kWh                         │
│ Self-used    7,560 kWh  → offsets at retail    │
│ Exported     1,890 kWh  → $113 @ ACC           │
└─────────────────────────────────────┘
```

- `# panels` is the **only** sizing control on main; `kW_per_panel` is in detail so the user
  moves one slider and watches kW update live.
- Main shows **energy coverage %**, labeled "covers ~X% of your use" — never read as dollars.
- Battery on/off on main (big economic lever); battery *size* in detail.
- `[?]` → `solar.html`.

### 8.6 Chart integration

Bill savings flow into the JC cost charts (self-consumed × retail + exported × export_rate),
on the same footing as appliance and transportation costs. The panel itself displays
**physical quantities only** — system kW, annual kWh, energy coverage % — so coverage is
never conflated with bill savings. Not shown in EU energy-quantity charts beyond the
production line.

### 8.7 `SolarBatteryConfig` Dataclass (sketch)

```python
@dataclass
class SolarBatteryConfig:
    enabled:        bool  = True
    panels:         int   = 15
    kw_per_panel:   float = 0.42
    specific_yield: float = 1500.0   # kWh/kW/yr; anchor to PVWatts
    battery_enabled: bool  = True    # On by default — NEM 3.0 + battery is the new-install standard
    battery_kwh:     float = 13.5
    nem_mode:        str   = "nbt"   # "nbt" (NEM 3.0, default) | "nem2" (existing pre-2023 solar)
    nbc:             float = 0.025   # $/kWh, NEM 2.0 only

    @property
    def system_kw(self) -> float:
        return self.panels * self.kw_per_panel

    def self_consumption_fraction(self) -> float:
        # derived from battery_kwh relative to system_kw; ~0.35 solar-only → ~0.80 w/ battery
        ...

    def export_rate(self, retail_rate: float, acc_rate: float) -> float:
        return acc_rate if self.nem_mode == "nbt" else max(0.0, retail_rate - self.nbc)
```

Model-level object on `HESModel` (like `SocialCostConfig` / `TransportationConfig`).
`acc_rate` comes from the existing Phase 2 ACC shape; `retail_rate` from the rate model.

### 8.8 Decisions Made / Open Questions

- [x] **System size is the input** (`# panels × kW/panel`), not a % — % becomes a derived, labeled output.
- [x] **`specific_yield` anchored to PVWatts** (default 1,500 kWh/kW/yr CA).
- [x] **One export-rate switch** (ACC for NEM 3.0, retail−NBC for NEM 2.0); no hour-by-hour NEM engine.
- [x] **Battery raises self-consumption**, making the export term second-order under NEM 3.0.
- [x] **Main panel = `# panels` + kW + battery toggle + coverage line; rest in detail.**
- [x] **Battery default On, NEM 3.0 (NBT) default** — NEM 2.0 closed Apr 2026; any new install is NEM 3.0 + battery. Battery On is the factual market default, not an optimistic assumption. (§8.3)
- [ ] **Per-zone `specific_yield`** — if §1 CEC climate zone is wired, auto-set yield by zone and drop the manual default.

---

## Appendix A — Phase 4 Module / Asset Deltas

New or changed artifacts relative to Phase 3:

```
src/
  climate_loader.py        ClimateLoader + ClimateData (hdd/cdd_cagr now populated)  ← from P3 §1
  rate_loader.py           RateLoader.from_eia() factory                              ← from P3 §3
  transportation.py        TransportationConfig + VehicleState                        ← NEW (§3)
  solar_battery.py         SolarBatteryConfig (size→production→value, NEM export switch)   ← NEW (§8)
  devices/
    physics.py             HeatPumpHVAC cop_47/cop_17 curve                           ← from P3 §2.1
data/
  climate/
    tmy3_zones.json        16 CEC zone records, now incl. hdd_cagr/cdd_cagr
    zip_to_zone.json       CA ZIP → zone key index
  rates/
    eia_rates_by_state.json EIA residential elec + natural-gas rates (CA on init)
docs/
  help/
    climate.html           CEC zones, TMY3, HDD/CDD, Cal-Adapt trend scenarios
    rates.html             (EIA section)
    transportation.html    ICE/EV model, charging efficiency, gasoline externalities  ← NEW
    solar.html             panels/kW, PVWatts yield, battery self-consumption, NEM 2.0/3.0  ← UPDATED
scripts/
  build_climate_db.py      CEC zones + nearest-TMY3 fallback + Cal-Adapt trend fit
  build_eia_rates.py       EIA bulk download; --states flag
tests/
  test_climate_loader.py   ZIP→zone lookup, CA coverage, fallback, trend application
  test_rate_loader_eia.py  EIA factory, CAGR, seasonal shape, source selection
  test_transportation.py   gallons/kWh math, charging-efficiency basis, externality toggles, multi-vehicle aggregation  ← NEW
  test_solar_battery.py    production math, self-consumption vs. battery, NEM export switch  ← NEW
```

Note: the shared social-cost-of-carbon parameter (§3.3) touches the Phase 3 `social_cost.py`
— `SocialCostConfig` and `TransportationConfig` should read a common `scc_per_ton` rather
than each carrying an independent carbon price.
