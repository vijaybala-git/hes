# WhyWatt — Phase 2 Development Spec

**Status:** Phase 2 implemented through Objective 6; bug-fix + rate-decoupling patch in progress
**Follows:** Phase 1 complete (Mesa + Solara, 42 unit tests, dual-home simulation)
**Project rename:** HES → **WhyWatt?** (update all UI titles, headers, doc references)
**Last updated:** Physics bug fixes (§9), baseload symmetry fix (§9), independent gas/elec rate sliders (§10) added

---

## 0. Branding Updates (do first, zero logic risk)

- Rename tool to **WhyWatt?** throughout: `app.py` title, page header, `solara.Title()`
- Add logo placeholder: `docs/assets/whywatt_logo.png` — drop-in when final art is ready
- Add group logo placeholder: `docs/assets/group_logo.png` — displayed in UI footer
- In `app.py`: add footer bar with group logo img tag (graceful fallback if file missing)
- Update `README.md` and all doc headers to WhyWatt

---

## 1. Overview

Phase 1 established the simulation architecture: Mesa agents, annual step loop, dual JSON
home configs, Solara UI, 42 unit tests. All energy quantities used MMBtu as a single internal
unit — a deliberate simplification to get the core running.

**Phase 2 has three goals:**

1. **Journey model:** Replace the static two-home comparison with a single home that
   transitions device-by-device over time. Users configure a swap schedule. A "do nothing"
   baseline runs in parallel automatically.

2. **Physical accuracy:** Replace MMBtu internals with natively-typed energy models
   (kWh for electrical, therms for gas) using ENERGY STAR, DOE, and AGA reference data.
   HVAC and water heating use monthly sub-calculations driven by TMY3 climate data.

3. **Real rate data:** Ground energy prices in actual CPUC/PG&E published tariff rates
   with historically-calibrated escalation scenarios.

**What does NOT change:** the Mesa simulation structure, annual step model, Solara UI
layout, and the CapEx replacement model.

**No backward compatibility required.** Phase 2 replaces MMBtu code cleanly. Old JSON
configs, old unit tests, and the `annual_load` / `fuel_mix` fields are all replaced.

---

## 2. Core Architecture

### 2.1 The Journey Model

The central UX insight: homeowners think in terms of a **journey** — swapping appliances
one at a time over years, not flipping a switch to a fully electrified home overnight.

**Two `JourneyHome` instances run in parallel:**

```
JourneyHome A — "Your journey"     swap_years set by user per device slot
JourneyHome B — "Do nothing"       all swap_years = None; starting_state preserved as-is
```

The gap between the two cumulative cost lines IS the value of the journey. The "do nothing"
baseline is not flat — gas prices escalate, gas appliances trigger end-of-life CapEx
replacements, and the baseline cannot revert past decisions: a home that already has an
electric dryer keeps it electric in the "do nothing" home — it does not revert to gas.
This is the core advocacy message.

**DeviceSlot — the unit of configuration:**

```python
@dataclass
class DeviceSlot:
    name: str                              # "HVAC", "Water Heater", "Dryer" etc.
    category: str                          # CATEGORY_ORDER key

    # Starting state drives both homes' year-0 device selection
    starting_state: str                    # "gas" | "electric" | "none"
                                           #   gas      → baseline runs gas device(s) (default)
                                           #   electric → already swapped; both homes use electric_device
                                           #   none     → not in baseline (e.g. EV Charger add)

    baseline_devices: list[EnergyConsumer] # gas/legacy devices — list supports compound baseline
                                           # e.g. [GasFurnace, CentralAC] for HVAC with cooling
    has_cooling_baseline: bool = False     # HVAC only: True if home has central AC as separate unit
    electric_device: EnergyConsumer = None # replacement device (None only when starting_state="none"
                                           # and swap never planned)
    swap_year: int | None = None           # year swap occurs; None = never; ignored if starting_state != "gas"
    install_cost: float = 0.0             # gross install cost of electric device
    rebate: float = 0.0                   # rebate amount (IRA, TECH Clean CA etc.)

    @property
    def net_install_cost(self):
        return self.install_cost - self.rebate
```

**Starting state behaviour:**

| `starting_state` | Journey home | "Do nothing" baseline |
|---|---|---|
| `"gas"` | Runs gas device(s) until `swap_year`, then electric | Runs gas device(s) forever |
| `"electric"` | Runs electric device from year 0 (already done) | Runs electric device from year 0 |
| `"none"` | Adds electric device at `swap_year` (clean add) | Zero consumption — slot absent |

**Annual step logic per slot:**

```python
def step(self, current_year, monthly_rates, is_baseline_home: bool = False):
    if self.starting_state == "electric":
        # Already swapped before sim start — both homes run electric device
        active_list = [self.electric_device]

    elif self.starting_state == "none" and is_baseline_home:
        return  # slot absent from baseline (e.g. EV charger) — zero cost, zero consumption

    elif self.swap_year is None or current_year < self.swap_year:
        active_list = self.baseline_devices  # gas phase: one or more baseline devices

    else:
        active_list = [self.electric_device]  # post-swap: single electric device

    for active in active_list:
        active.step(monthly_rates)

    # CapEx: swap event OR per-device end-of-life replacement
    if self.starting_state == "gas" and current_year == self.swap_year:
        self.capex_events.append((current_year, self.net_install_cost))
    else:
        for active in active_list:
            if active.age >= active.lifespan:
                self.capex_events.append((current_year, active.installation_cost))
                active.age = 0
```

**HVAC compound baseline note:** When `has_cooling_baseline=True` the HVAC slot carries
`baseline_devices = [GasFurnace, CentralAC]`. Each ages and triggers replacement
independently. The heat pump swap replaces both with a single install event. When
`has_cooling_baseline=False` the furnace has no AC companion — the heat pump adds
cooling as a new capability with no prior CapEx history for that function.

**JourneyHome** iterates its list of `DeviceSlot` objects, aggregates costs into
`annual_opex`, `cumulative_opex`, and `capex_by_year`. The `cost_history_by_category`
aggregation uses the sum-then-append pattern (see §2.4).

### 2.2 Device Class Hierarchy — Three Computation Methods

All devices speak the same language to `JourneyHome`: a `(12,)` numpy array of monthly
consumption in native units. The difference is only HOW that array is computed.

```
EnergyConsumer  (abstract base — lifespan, CapEx, history schema)
│
│   REQUIRED interface:
│   monthly_consumption() → np.ndarray shape (12,)   native unit (kWh or therms)
│   annual_consumption()  → float                    sum of monthly array
│   monthly_cost(rates)   → np.ndarray shape (12,)   consumption × monthly_rate
│   fuel_type: str                                   "electricity" or "gas"
│
├── SeasonalDevice                     flat annual total × seasonality weights
│   │  Inputs: annual_total, seasonality[12]
│   │  Good for: dryer, dishwasher, oven, lights — flat week-to-week usage
│   ├── GasDryer                       therms
│   ├── HeatPumpDryer                  kWh
│   ├── Dishwasher                     kWh
│   ├── ElectricOven / InductionCooktop  kWh
│   ├── GasCooktop                     therms
│   └── LightsAndPlugs                 kWh
│
├── PhysicsDevice                      monthly values from climate formula
│   │  Inputs: climate constants (HDD[12], CDD[12], water temps[12])
│   │  Good for: HVAC and water heating — strongly weather-driven
│   ├── GasFurnace                     therms[m] = hdd[m]×24×UA / (AFUE×100k)
│   ├── HeatPumpHVAC                   kWh[m] = hdd[m]×24×UA/(COP×3412)
│   │                                         + cdd[m]×24×UA/(SEER×3412)
│   ├── GasWaterHeater                 therms[m] = gallons×days[m]×8.33×ΔT[m]×0.00001/UEF
│   └── HeatPumpWaterHeater            kWh[m]    = gallons×days[m]×8.33×ΔT[m]×0.000293/UEF
│
└── ScheduleDevice                     monthly values supplied directly
    │  Inputs: monthly_values[12] — flat default, upgradeable to real data
    │  Good for: devices with custom or data-driven monthly profiles
    ├── EVCharger                      kWh[m] — flat default, can use real odometer data
    ├── SolarPV (Phase 3)              kWh[m] from PVWatts — production, not consumption
    └── CustomDevice                   any future device needing arbitrary monthly profile
```

**The upgrade path:** A device starts as `SeasonalDevice` (simple), upgrades to
`PhysicsDevice` or `ScheduleDevice` (accurate) without changing the interface.
`JourneyHome` never needs to know which method was used.

### 2.3 Monthly Rate Architecture — CPUC/PG&E Data

**Key finding:** PG&E publishes rates per effective date range (not calendar months),
changing multiple times per year per CPUC advice letters. Historical data shows:

| Metric | Value | Source |
|--------|-------|--------|
| PG&E residential elec rate Jun 2025 | $0.386/kWh | Cal Advocates Q2 2025 |
| PG&E elec 3-yr CAGR (Jan 2022–Jun 2025) | ~10.4%/yr | Cal Advocates Q2 2025 |
| PG&E elec 10-yr CAGR (Jan 2015–Jun 2025) | ~7.2%/yr | Cal Advocates Q2 2025 |
| PG&E gas Jan 2025 increase | +$0.228/therm (+8.6%) | PG&E Advice Letter 5014-G1 |
| PG&E gas base rate Jan 2025 | ~$2.08/therm (non-CARE) | PG&E rate advisory |

**Data directory structure:**

```
data/
  rates/
    pge_elec_e1.json          # historical E-1 flat rates by effective period
    pge_gas_g1.json           # historical G-1 flat rates by effective period
    rate_loader.py            # maps (year, month) → $/kWh or $/therm
  climate/
    bayarea_tmy3.json         # monthly HDD, CDD, water inlet temps
  appliances/
    electrical_defaults.json  # ENERGY STAR 2024 reference values
    gas_defaults.json         # AGA reference values
    ev_schedule_default.json  # default monthly kWh schedule for EV charger
  homes/
    journey_slots_default.json   # default slot config for Bay Area home
```

**`pge_elec_e1.json` schema:**

```json
{
  "utility": "PGE",
  "schedule": "E-1",
  "unit": "$/kWh",
  "source": "CPUC Advice Letters; Cal Advocates Q2 2025 Electric Rates Report",
  "periods": [
    {"start": "2018-01", "end": "2018-12", "rate": 0.178},
    {"start": "2019-01", "end": "2019-12", "rate": 0.189},
    {"start": "2020-01", "end": "2020-12", "rate": 0.196},
    {"start": "2021-01", "end": "2021-12", "rate": 0.210},
    {"start": "2022-01", "end": "2022-05", "rate": 0.231},
    {"start": "2022-06", "end": "2022-11", "rate": 0.248},
    {"start": "2023-01", "end": "2023-06", "rate": 0.310},
    {"start": "2023-07", "end": "2023-12", "rate": 0.338},
    {"start": "2024-01", "end": "2024-06", "rate": 0.358},
    {"start": "2024-07", "end": "2024-12", "rate": 0.371},
    {"start": "2025-01", "end": "2025-12", "rate": 0.386}
  ],
  "projection": {
    "base_rate": 0.386,
    "base_year": 2025,
    "cagr_conservative": 0.04,
    "cagr_moderate":     0.07,
    "cagr_stress":       0.10
  }
}
```

**`pge_gas_g1.json` schema** (same structure, unit = "$/therm"):

```json
{
  "utility": "PGE",
  "schedule": "G-1",
  "unit": "$/therm",
  "source": "PG&E Advice Letter 5014-G1; CPUC Annual Reports",
  "periods": [
    {"start": "2018-01", "end": "2018-12", "rate": 1.10},
    {"start": "2019-01", "end": "2019-12", "rate": 1.18},
    {"start": "2020-01", "end": "2020-12", "rate": 1.22},
    {"start": "2021-01", "end": "2021-12", "rate": 1.35},
    {"start": "2022-01", "end": "2022-12", "rate": 1.65},
    {"start": "2023-01", "end": "2023-12", "rate": 1.85},
    {"start": "2024-01", "end": "2024-08", "rate": 1.92},
    {"start": "2024-09", "end": "2024-12", "rate": 1.98},
    {"start": "2025-01", "end": "2025-12", "rate": 2.08}
  ],
  "projection": {
    "base_rate": 2.08,
    "base_year": 2025,
    "cagr_conservative": 0.04,
    "cagr_moderate":     0.08,
    "cagr_stress":       0.12
  }
}
```

**`RateLoader` interface:**

```python
class RateLoader:
    """
    Maps (year, month) to $/kWh or $/therm using CPUC published periods
    for historical years, and CAGR projection for future years.
    """
    def get_rate(self, fuel: str, year: int, month: int,
                 scenario: str = "moderate") -> float:
        """Returns $/kWh or $/therm for a specific year+month."""

    def get_annual_monthly_rates(self, fuel: str, sim_start_year: int,
                                  n_years: int, scenario: str) -> np.ndarray:
        """
        Returns shape (n_years, 12) — one rate per month per year.
        Historical months use actual published rates.
        Future months use base_rate × (1 + cagr)^(year - base_year).
        sim_start_year is the real calendar year the simulation begins,
        so historical data is used correctly.
        """
```

`HESModel` calls `get_annual_monthly_rates()` once at init and passes the resulting
arrays to devices. Devices never call `RateLoader` directly.

**Updated escalation scenario defaults (replacing old 3%/4% figures):**

| Scenario | Elec CAGR | Gas CAGR | Label |
|----------|-----------|----------|-------|
| Conservative | 4% | 4% | "Slow price growth" |
| Moderate | 7% | 8% | "Recent trend (default)" |
| Stress (CEC) | 10% | 12% | "High gas cost scenario" |

Rationale: moderate elec CAGR of 7% matches the 10-yr historical average per Cal Advocates.
Gas 8% moderate reflects post-2021 trend plus stranded infrastructure risk.

### 2.4 Climate Data — Monthly TMY3 Constants

Fixed Bay Area constants for Phase 2 (NREL TMY3, San Jose Mineta Airport, Station 724945).
Full EPW weather-file simulation deferred to Phase 3.

**`data/climate/bayarea_tmy3.json`:**

```json
{
  "station": "San Jose Mineta Airport",
  "station_id": "724945",
  "source": "NREL TMY3",
  "base_year": 2024,
  "monthly_hdd_65f": [420, 340, 260, 140, 50, 10, 0, 0, 10, 80, 220, 380],
  "monthly_cdd_65f": [0, 0, 0, 5, 20, 60, 90, 85, 55, 20, 5, 0],
  "monthly_inlet_water_temp_f": [54, 54, 55, 57, 60, 63, 65, 66, 65, 62, 58, 55],
  "setpoint_water_temp_f": 120,
  "daily_hot_water_gallons": 65,
  "ua_by_insulation": {
    "poor":    650,
    "average": 500,
    "good":    350
  },
  "annual_hdd_65f": 1910,
  "annual_cdd_65f": 340,
  "notes": "monthly_hdd + monthly_cdd sum to annual totals above",
  "bedroom_scaling": {
    "1": {"baseload_multiplier": 0.50, "hot_water_gal_per_day": 30},
    "2": {"baseload_multiplier": 0.83, "hot_water_gal_per_day": 50},
    "3": {"baseload_multiplier": 1.00, "hot_water_gal_per_day": 65},
    "4": {"baseload_multiplier": 1.17, "hot_water_gal_per_day": 75},
    "5": {"baseload_multiplier": 1.33, "hot_water_gal_per_day": 85}
  },
  "baseload_kwh_3br": 1200,
  "source_bedroom_scaling": "DOE/ENERGY STAR occupancy proxy; 3BR is TMY3 reference (65 gal/day, 1200 kWh baseload)"
}
```

Note: monthly HDD sums to 1910, not 2600 — the 2600 figure in early spec drafts was the
national average. 1910 is correct for San Jose TMY3. Validation targets updated below.

**Updated PhysicsDevice validation targets:**

| Device | Formula | Expected output |
|--------|---------|----------------|
| GasFurnace (UA=500, AFUE=0.80) | Σ hdd[m]×24×500/(0.80×100k) | ~286 therms/yr |
| HeatPumpHVAC heating (UA=500, COP=3.5) | Σ hdd[m]×24×500/(3.5×3412) | ~1,930 kWh/yr |
| HeatPumpHVAC cooling (UA=500, SEER=22) | Σ cdd[m]×24×500/(22×3412×0.001) | ~550 kWh/yr |
| GasWaterHeater (UEF=0.65, 65 gal/day) | monthly gallons×8.33×ΔT[m]/UEF | ~210 therms/yr |
| HeatPumpWaterHeater (UEF=3.5, 65 gal/day) | same, electric | ~1,050 kWh/yr |

Tolerance: ±5% on all physics devices.

### 2.5 HomeConfig — Home Profile Data Model

`HomeConfig` is a plain dataclass that carries all home-specific parameters through the
stack. `HESModel` accepts one at construction; devices receive only the derived scalar
values they need — they never read `HomeConfig` directly. The object is structured to
serialize to JSON cleanly for Phase 3 session persistence.

```python
@dataclass
class HomeConfig:
    # ── Location ────────────────────────────────────────────────────────────────
    zip_code:           str  = "95112"      # San Jose default
    climate_zone:       str  = "CZ12"      # CA climate zone — Phase 3: auto-derive from zip

    # ── Building ────────────────────────────────────────────────────────────────
    num_bedrooms:       int  = 3            # ✅ Phase 2 active — scales baseload + hot water
    square_footage:     int  = 1800         # carried; drives EPW model in Phase 3
    year_built:         int  = 1985         # carried; future use
    insulation_quality: str  = "average"   # ✅ Phase 2 active — poor / average / good → UA

    # ── Phase 3 carry-forward (unused in Phase 2) ───────────────────────────────
    num_bathrooms:      int  = 2
    stories:            int  = 1
    has_garage:         bool = False
```

**Bedroom scaling** — resolved by `HESModel.__init__`, not by devices:

```python
BEDROOM_SCALING = {
    1: {"baseload_multiplier": 0.50, "hot_water_gal_per_day": 30},
    2: {"baseload_multiplier": 0.83, "hot_water_gal_per_day": 50},
    3: {"baseload_multiplier": 1.00, "hot_water_gal_per_day": 65},   # TMY3 reference
    4: {"baseload_multiplier": 1.17, "hot_water_gal_per_day": 75},
    5: {"baseload_multiplier": 1.33, "hot_water_gal_per_day": 85},
}
# Source: DOE/ENERGY STAR occupancy proxy anchored to 3BR = 65 gal/day, 1200 kWh/yr
```

`HESModel` resolves the multiplier once and injects concrete values:

```python
br = BEDROOM_SCALING[config.num_bedrooms]
baseload_kwh = 1200 * br["baseload_multiplier"]      # → LightsAndPlugs constructor
hw_gallons   = br["hot_water_gal_per_day"]           # → GasWH / HPWH constructors
```

**Phase 3 session config JSON shape** (schema defined now; `json.dump` wired in Phase 3):

```json
{
  "version": "2",
  "home": {
    "zip_code": "95112",
    "climate_zone": "CZ12",
    "num_bedrooms": 3,
    "square_footage": 1800,
    "year_built": 1985,
    "insulation_quality": "average",
    "num_bathrooms": 2,
    "stories": 1,
    "has_garage": false
  },
  "device_specs": {
    "furnace_afue": 0.80,
    "gas_wh_uef": 0.65,
    "hp_cop_heating": 3.5,
    "hp_seer_cooling": 22,
    "hpwh_uef": 3.5,
    "hvac_has_cooling_baseline": false
  },
  "journey_slots": [
    {
      "name": "HVAC",
      "category": "HVAC_Heating",
      "starting_state": "gas",
      "has_cooling_baseline": false,
      "swap_year": 3,
      "install_cost": 14000,
      "rebate": 3500
    }
  ],
  "simulation": {
    "scenario": "moderate",
    "sim_start_year": 2025,
    "years": 20,
    "comparison_mode": false,
    "scenario_b": "stress"
  }
}
```

`home`, `device_specs`, `journey_slots`, and `simulation` are top-level siblings —
each block loads independently. Phase 3 adds load/save buttons; no structural change needed.

---

### 2.6 cost_history_by_category Bug Fix

**Problem (Phase 1):** `HomeSimulator.step()` appends one value per device per step.
Multiple devices in the same category produce a list of length `n_devices × n_steps`
instead of `n_steps`.

**Fix — sum first, append once:**

```python
def step(self):
    year_category_costs = {cat: 0.0 for cat in CATEGORY_ORDER}
    for slot in self.slots:
        slot.step(current_year, monthly_rates)
        cat = slot.category if slot.category in year_category_costs else "Baseload"
        year_category_costs[cat] += slot.active_device.history['cost'][-1]
    for cat, cost in year_category_costs.items():
        self.cost_history_by_category[cat].append(cost)
```

### 2.7 Core Unit Rule

```
Each device stores and computes in its native unit:
  ElectricalConsumer → kWh
  GasConsumer        → therms

Pricing: consumption[m] × rate[m] (element-wise, monthly)

Display conversion for combined charts (output only, never in internals):
  1 therm = 29.3 kWh
```

No MMBtu anywhere after Objective 1. This is a hard rule — enforce in code review.

---

## 3. Reference Data

### 3.1 Electrical Appliances — ENERGY STAR & DOE 2024

Cycle-based: `annual_kWh = kWh_per_cycle × cycles_per_week × 52 × seasonality_factor`

| Appliance | kWh/cycle | Default use | Annual kWh |
|-----------|-----------|-------------|------------|
| Clothes washer | 0.45 | 5/wk | 117 |
| Heat pump dryer | 1.8 | 5/wk | 468 |
| Electric dryer | 3.3 | 5/wk | 858 |
| Dishwasher | 1.2 | 5/wk | 312 |
| Electric oven | 2.0 | 5/wk | 520 |
| Induction cooktop | 0.9/meal | 14 meals/wk | 655 |
| Refrigerator | 1.35 kWh/day | continuous | 493/yr |
| Lights + plug loads | — | continuous | 1,200/yr |

### 3.2 EV Charger — ScheduleDevice Default

```json
{
  "name": "EV Charger (L2)",
  "device_class": "ScheduleDevice",
  "fuel_type": "electricity",
  "monthly_kwh": [290, 270, 290, 280, 300, 310, 320, 320, 300, 290, 280, 290],
  "source": "EPA 2024 avg 10 kWh/session, slight summer uptick from more driving",
  "annual_kwh": 3540,
  "installation_cost": 800,
  "lifespan": 20,
  "upgrade_path": "Replace monthly_kwh with real odometer data or telematics API"
}
```

### 3.3 Gas Appliances — AGA & PG&E Reference

| Appliance | Therms/cycle | Default use | Annual therms |
|-----------|-------------|-------------|---------------|
| Gas dryer | 0.22 | 5/wk | 57 |
| Gas cooktop | 0.05/meal | 14 meals/wk | 36 |
| Gas fireplace | 1.5/use | 2/wk | 156 |

HVAC and water heater use PhysicsDevice formulas — see §2.4.

---

## 4. Implementation Objectives

Ordered by dependency. Each objective must have passing tests before the next begins.
Claude Code prompt template at end of each objective.

---

### Objective 0: Branding + Directory Scaffold

**Scope:** No logic changes. Pure rename and file structure.

- Update `app.py`: `solara.Title("WhyWatt?")`, header markdown, footer with logo placeholder
- Update `README.md`
- Create directory structure:
  ```
  data/rates/     data/climate/     data/appliances/     data/homes/
  docs/assets/    src/devices/
  ```
- Create `docs/assets/whywatt_logo.png` placeholder (1×1 transparent PNG is fine)
- Create `docs/assets/group_logo.png` placeholder

**Tests:** None needed — visual only.

**Claude Code prompt:**
```
Implement Objective 0 of docs/Phase2_Spec.md.
Rename HES to WhyWatt? in app.py title and header only.
Create the directory structure listed. No logic changes whatsoever.
```

---

### Objective 1: Rate Data Files + RateLoader

**Scope:** Create CPUC rate data files and the loader. No simulation changes yet.

**Deliverables:**
- `data/rates/pge_elec_e1.json` — historical periods from spec §2.3
- `data/rates/pge_gas_g1.json` — historical periods from spec §2.3
- `src/rate_loader.py` — `RateLoader` class with `get_rate()` and
  `get_annual_monthly_rates()` methods

**RateLoader behaviour:**
- For `(year, month)` within a historical period → return that period's flat rate
- For `(year, month)` beyond last period → `base_rate × (1 + cagr)^(year - base_year)`
  where `cagr` comes from the scenario key in `projection` block
- `sim_start_year` parameter: the real calendar year simulation year 0 maps to
  (default 2025)

**Tests `tests/test_rate_loader.py`:**
- Historical lookup: `get_rate("electricity", 2023, 6)` → 0.310
- Historical lookup: `get_rate("gas", 2024, 10)` → 1.98
- Projection: `get_rate("electricity", 2030, 1, "moderate")` →
  `0.386 × 1.07^5` ± 0.001
- Boundary: last historical month returns historical rate, next month uses projection
- `get_annual_monthly_rates()` returns shape `(n_years, 12)`
- Scenario "conservative" < "moderate" < "stress" for any future year
- Unknown scenario raises `ValueError`

**Claude Code prompt:**
```
Implement Objective 1 of docs/Phase2_Spec.md.
Create data/rates/pge_elec_e1.json and data/rates/pge_gas_g1.json
using the exact period data in spec §2.3.
Create src/rate_loader.py with the RateLoader class and interface in §2.3.
Write tests/test_rate_loader.py covering all test cases listed.
Do not modify any existing src/ files.
```

---

### Objective 2: Device Class Hierarchy + Climate Data

**Scope:** New `src/devices/` module with abstract base and three computation families.
No changes to `model.py` or `app.py` yet.

**New files:**
- `data/climate/bayarea_tmy3.json` — from spec §2.4
- `src/devices/__init__.py`
- `src/devices/base.py` — `EnergyConsumer` abstract base
- `src/devices/seasonal.py` — `SeasonalDevice` + concrete classes
- `src/devices/physics.py` — `PhysicsDevice` + `GasFurnace`, `HeatPumpHVAC`,
  `GasWaterHeater`, `HeatPumpWaterHeater`
- `src/devices/schedule.py` — `ScheduleDevice` + `EVCharger`

**`EnergyConsumer` abstract base (`src/devices/base.py`):**

```python
class EnergyConsumer(mesa.Agent):
    """Abstract base. Subclasses implement monthly_consumption()."""

    fuel_type: str  # "electricity" or "gas" — set by subclass

    # Lifecycle
    lifespan: int
    age: int
    installation_cost: float
    capex_events: list  # [(year, cost)]

    # History — annual entries, each a float
    history: dict  # {'consumption': [], 'cost': []}

    @abstractmethod
    def monthly_consumption(self) -> np.ndarray:
        """Returns shape (12,) in native unit (kWh or therms)."""

    def annual_consumption(self) -> float:
        return float(self.monthly_consumption().sum())

    def monthly_cost(self, monthly_rates: np.ndarray) -> np.ndarray:
        """monthly_rates shape (12,) in $/kWh or $/therm."""
        return self.monthly_consumption() * monthly_rates

    def step(self, monthly_rates: np.ndarray):
        consumption = self.monthly_consumption()
        cost = self.monthly_cost(monthly_rates)
        self.history['consumption'].append(float(consumption.sum()))
        self.history['cost'].append(float(cost.sum()))
        self.age += 1
```

**`PhysicsDevice` — climate constants injected at construction, not read from file:**

```python
class GasFurnace(PhysicsDevice):
    def __init__(self, ..., afue, ua_btu_hr_f, monthly_hdd):
        # monthly_hdd: np.ndarray shape (12,) — passed in from climate constants
        ...

    def monthly_consumption(self) -> np.ndarray:
        # therms[m] = hdd[m] × 24 × ua / (afue × 100_000)
        return self.monthly_hdd * 24 * self.ua / (self.afue * 100_000)
```

Same pattern for `HeatPumpHVAC` (uses both `monthly_hdd` and `monthly_cdd`),
`GasWaterHeater` and `HeatPumpWaterHeater` (use `monthly_inlet_temp_f`).

**`ScheduleDevice`:**

```python
class ScheduleDevice(EnergyConsumer):
    def __init__(self, ..., monthly_values: list[float], fuel_type: str):
        self._monthly = np.array(monthly_values, dtype=float)
        assert len(self._monthly) == 12

    def monthly_consumption(self) -> np.ndarray:
        return self._monthly.copy()
```

**`EVCharger(ScheduleDevice)`:** loaded from `data/appliances/ev_schedule_default.json`.
Flat default of ~295 kWh/month (3,540 kWh/yr).

**Tests `tests/test_devices.py`:**
- `GasFurnace`: annual therms within ±5% of 286 for Bay Area defaults
- `HeatPumpHVAC` heating: annual kWh within ±5% of 1,930
- `HeatPumpHVAC` cooling: annual kWh within ±5% of 550
- `GasWaterHeater`: annual therms within ±5% of 210
- `HeatPumpWaterHeater`: annual kWh within ±5% of 1,050
- `SeasonalDevice`: annual_consumption() = annual_total / efficiency
- `ScheduleDevice`: monthly_consumption() returns exactly the supplied array
- `EVCharger`: annual kWh ≈ 3,540 within 5%
- All devices: `monthly_consumption()` shape is `(12,)`
- All devices: `monthly_cost(rates).sum()` = `annual_consumption() × mean(rates)`
  (for flat rate array)
- `GasFurnace` with "good" insulation (UA=350) consumes less than "poor" (UA=650)
- `HeatPumpHVAC`: higher COP → lower kWh for same HDD/CDD

**Claude Code prompt:**
```
Implement Objective 2 of docs/Phase2_Spec.md.
Create data/climate/bayarea_tmy3.json from spec §2.4.
Create src/devices/ module with base.py, seasonal.py, physics.py, schedule.py.
Climate constants are passed as constructor arguments — devices never read files.
Write tests/test_devices.py covering all validation targets in §2.4.
Do not modify model.py, app.py, or energy_price.py.
```

---

### Objective 3: DeviceSlot + JourneyHome + HESModel Refactor

**Scope:** Replace `HomeSimulator` with `JourneyHome` using `DeviceSlot` objects.
Update `HESModel` to run two `JourneyHome` instances.
Fix `cost_history_by_category` bug.

**New file:** `src/journey.py` — `DeviceSlot` dataclass and `JourneyHome` class

**`HESModel` changes:**
- Constructor accepts `home_config: HomeConfig` and `scenario: str`
- Loads climate constants from `data/climate/bayarea_tmy3.json` once at init
- Resolves bedroom scaling from `home_config.num_bedrooms` → injects `baseload_kwh`
  and `hw_gallons` into device constructors
- `home_config.insulation_quality` maps to UA value via `ua_by_insulation` climate constants
- Calls `RateLoader.get_annual_monthly_rates()` at init — passes rate arrays to model
- Instantiates two `JourneyHome` objects:
  - `self.journey_home`: uses `swap_year` and `starting_state` from slot configs as-is
  - `self.baseline_home`: same slots with all `swap_year = None`; `starting_state`
    preserved (already-electric slots remain electric in the baseline)

**`DataCollector` reporters:**
```python
{
    "Journey Cum Cost":       lambda m: m.journey_home.cumulative_opex,
    "Baseline Cum Cost":      lambda m: m.baseline_home.cumulative_opex,
    "Journey Annual Cost":    lambda m: m.journey_home.annual_opex,
    "Baseline Annual Cost":   lambda m: m.baseline_home.annual_opex,
    "Opex Delta":             lambda m: m.baseline_home.cumulative_opex
                                        - m.journey_home.cumulative_opex,
    "Elec Rate":              lambda m: float(np.mean(m.current_elec_rates)),
    "Gas Rate":               lambda m: float(np.mean(m.current_gas_rates)),
}
```

**Default slot configuration (`data/homes/journey_slots_default.json`):**

```json
[
  {
    "name": "HVAC",
    "category": "HVAC_Heating",
    "starting_state": "gas",
    "has_cooling_baseline": false,
    "baseline_devices": [{"class": "GasFurnace", "afue": 0.80, "age": 10}],
    "electric_device":   {"class": "HeatPumpHVAC", "cop_heating": 3.5, "seer_cooling": 22},
    "swap_year": null,
    "install_cost": 14000,
    "rebate": 3500
  },
  {
    "name": "Water Heater",
    "category": "WaterHeating",
    "starting_state": "gas",
    "has_cooling_baseline": false,
    "baseline_devices": [{"class": "GasWaterHeater", "uef": 0.65, "age": 5}],
    "electric_device":   {"class": "HeatPumpWaterHeater", "uef": 3.5},
    "swap_year": null,
    "install_cost": 2500,
    "rebate": 500
  },
  {
    "name": "Dryer",
    "category": "Baseload",
    "starting_state": "gas",
    "has_cooling_baseline": false,
    "baseline_devices": [{"class": "GasDryer", "therms_per_cycle": 0.22, "cycles_per_week": 5}],
    "electric_device":   {"class": "HeatPumpDryer", "kwh_per_cycle": 1.8, "cycles_per_week": 5},
    "swap_year": null,
    "install_cost": 1200,
    "rebate": 0
  },
  {
    "name": "Cooktop",
    "category": "Baseload",
    "starting_state": "gas",
    "has_cooling_baseline": false,
    "baseline_devices": [{"class": "GasCooktop", "therms_per_meal": 0.05, "meals_per_week": 14}],
    "electric_device":   {"class": "InductionCooktop", "kwh_per_meal": 0.9, "meals_per_week": 14},
    "swap_year": null,
    "install_cost": 1500,
    "rebate": 0
  },
  {
    "name": "EV Charger",
    "category": "Baseload",
    "starting_state": "none",
    "has_cooling_baseline": false,
    "baseline_devices": [],
    "electric_device":   {"class": "EVCharger"},
    "swap_year": null,
    "install_cost": 800,
    "rebate": 0
  },
  {
    "name": "Lights and Appliances",
    "category": "Baseload",
    "starting_state": "electric",
    "has_cooling_baseline": false,
    "baseline_devices": [],
    "electric_device":   {"class": "LightsAndPlugs", "annual_kwh": 1200},
    "swap_year": null,
    "install_cost": 0,
    "rebate": 0
  }
]
```

Notes:
- `starting_state: "none"` for EV Charger — absent from baseline; zero consumption until user adds it
- `starting_state: "electric"` for Lights — always-on electric load in both homes; `annual_kwh` is
  scaled by bedroom multiplier in `HESModel` before the device is constructed
- `has_cooling_baseline: false` is the Bay Area default (many homes have no central AC);
  set to `true` to add `CentralAC` to `baseline_devices` alongside `GasFurnace`

**Tests `tests/test_journey.py`:**
- `DeviceSlot` (`starting_state="gas"`) uses baseline devices before `swap_year`, electric after
- `swap_year = None` with `starting_state="gas"` always uses baseline devices
- `starting_state="electric"` uses electric device in BOTH journey and baseline home from year 0
- `starting_state="none"` produces zero cost in baseline home; adds electric device after `swap_year` in journey home
- HVAC `has_cooling_baseline=True`: baseline runs `[GasFurnace, CentralAC]`; both age independently
- HVAC `has_cooling_baseline=False`: baseline runs `[GasFurnace]` only; heat pump swap adds cooling
- CapEx event logged at `swap_year` with `net_install_cost`
- End-of-life CapEx logged per device in `baseline_devices` when `age >= lifespan`
- `JourneyHome` `cost_history_by_category` has exactly `n_steps` entries per category
- Two homes with identical configs produce identical cost trajectories
- `baseline_home` (all `swap_year=None`) costs more than `journey_home` after all swaps (stress scenario)
- `HomeConfig` with 1BR → `LightsAndPlugs` annual_kwh ≈ 600 (0.50× of 1200)
- `HomeConfig` with 4BR → hot water gallons/day = 75 (not 65)
- `HomeConfig` bedroom scaling applied consistently across both homes
- `HESModel.datacollector.get_model_vars_dataframe()` has `n_years` rows

**Claude Code prompt:**
```
Implement Objective 3 of docs/Phase2_Spec.md.
Create src/home_config.py with the HomeConfig dataclass and BEDROOM_SCALING dict from §2.5.
Create src/journey.py with DeviceSlot (updated fields per §2.1) and JourneyHome.
Refactor src/model.py: accept HomeConfig, apply bedroom scaling at init,
replace HomeSimulator with JourneyHome, add RateLoader integration,
fix cost_history_by_category bug per §2.6.
Load default slots from data/homes/journey_slots_default.json.
Write tests/test_journey.py. Do not modify app.py.
```

---

### Objective 4: EnergyPrice Retirement + Model Cleanup

**Scope:** `EnergyPrice` is superseded by `RateLoader`. Remove it.
Update all remaining MMBtu references. Verify no MMBtu anywhere.

**Deliverables:**
- Delete `src/energy_price.py`
- Delete `src/energy_consumer.py` (replaced by `src/devices/`)
- Remove all `MMBtu` references from tests and docs
- Update `tests/test_energy_price.py` → archive or delete (superseded)
- Update `Glossary.md` — remove MMBtu, add kWh/therm, add RateLoader, add DeviceSlot
- Run full `pytest tests/` — all must pass

**Grep check (must return zero results):**
```bash
grep -r "MMBtu\|mmbtu\|per_mmbtu\|annual_load\|fuel_mix" src/ data/ tests/
```

**Claude Code prompt:**
```
Implement Objective 4 of docs/Phase2_Spec.md.
Delete src/energy_price.py and src/energy_consumer.py.
Run grep check from spec and fix any remaining MMBtu references.
Update docs/Glossary.md.
Run pytest and confirm all tests pass.
```

---

### Objective 5: Dual Pricing Scenarios

**Scope:** Add Scenario B (stress) as a second `HESModel` instance.
Lazy instantiation — only created when comparison mode enabled.

**`HESModel` additions:**

```python
class HESModel(mesa.Model):
    def __init__(self, ...,
                 scenario_a: str = "moderate",
                 scenario_b: str = "stress",
                 comparison_mode: bool = False):
        ...
        self.elec_rates_a  # shape (n_years, 12)
        self.gas_rates_a   # shape (n_years, 12)

        if comparison_mode:
            self.elec_rates_b = RateLoader().get_annual_monthly_rates(
                "electricity", sim_start_year, n_years, scenario_b)
            self.gas_rates_b  = RateLoader().get_annual_monthly_rates(
                "gas", sim_start_year, n_years, scenario_b)
            self.journey_home_b  = JourneyHome(slots, self.elec_rates_b, self.gas_rates_b)
            self.baseline_home_b = JourneyHome(slots_no_swap, self.elec_rates_b, self.gas_rates_b)
```

**DataCollector adds Scenario B reporters when `comparison_mode=True`:**
```python
"Journey Cum Cost B":   lambda m: m.journey_home_b.cumulative_opex,
"Baseline Cum Cost B":  lambda m: m.baseline_home_b.cumulative_opex,
"Gas Rate B":           lambda m: float(np.mean(m.current_gas_rates_b)),
"Elec Rate B":          lambda m: float(np.mean(m.current_elec_rates_b)),
```

**Tests `tests/test_dual_scenario.py`:**
- `comparison_mode=False`: no `_b` attributes exist on model
- `comparison_mode=True`: `_b` homes exist and have independent cost trajectories
- Stress scenario produces higher cumulative cost than moderate over 20 years
- With identical scenario A==B params, all four trajectories are equal

**Claude Code prompt:**
```
Implement Objective 5 of docs/Phase2_Spec.md.
Add comparison_mode and scenario_b to HESModel.
Lazy-instantiate Scenario B homes only when comparison_mode=True.
Extend DataCollector reporters for Scenario B.
Write tests/test_dual_scenario.py.
```

---

### Objective 6: UI — Journey Planner + WhyWatt Branding

**Scope:** Full Solara UI refactor. Replace the Gas Home / Electric Home control panels
with a Journey Planner. Add Home Profile panel with home details. WhyWatt branding
throughout. Dual scenario chart support.

---

#### Branding

- `solara.Title("WhyWatt?")` and `# ⚡ WhyWatt?` header
- Header logo: `docs/assets/whywatt_logo.png` with `os.path.exists()` guard
- Footer: group logo (`docs/assets/group_logo.png`) + org name, same guard

---

#### Reactive state

```python
# ── Home profile ────────────────────────────────────────────────────────────
zip_code            = solara.reactive("95112")
climate_zone        = solara.reactive("CZ12")
num_bedrooms        = solara.reactive(3)           # scales baseload + hot water
square_footage      = solara.reactive(1800)        # carried, shown in top bar
year_built          = solara.reactive(1985)        # carried, shown in top bar
insulation_quality  = solara.reactive("average")   # poor / average / good → UA

# ── Baseline device specs ────────────────────────────────────────────────────
furnace_afue        = solara.reactive(0.80)
gas_wh_uef          = solara.reactive(0.65)
hvac_has_cooling    = solara.reactive(False)       # True → adds CentralAC to baseline

# ── Electric replacement specs ───────────────────────────────────────────────
hp_cop_heating      = solara.reactive(3.5)
hp_seer_cooling     = solara.reactive(22)
hpwh_uef            = solara.reactive(3.5)

# ── Journey planner — one group per slot ────────────────────────────────────
# starting_state: "gas" | "electric" | "none"
hvac_starting_state   = solara.reactive("gas")
hvac_swap_planned     = solara.reactive(True)
hvac_swap_year        = solara.reactive(3)
hvac_install_cost     = solara.reactive(14000)
hvac_rebate           = solara.reactive(3500)

wh_starting_state     = solara.reactive("gas")
wh_swap_planned       = solara.reactive(True)
wh_swap_year          = solara.reactive(5)
wh_install_cost       = solara.reactive(2500)
wh_rebate             = solara.reactive(500)

dryer_starting_state  = solara.reactive("gas")
dryer_swap_planned    = solara.reactive(False)
dryer_swap_year       = solara.reactive(8)
dryer_install_cost    = solara.reactive(1200)
dryer_rebate          = solara.reactive(0)

cooktop_starting_state = solara.reactive("gas")
cooktop_swap_planned   = solara.reactive(False)
cooktop_swap_year      = solara.reactive(10)
cooktop_install_cost   = solara.reactive(1500)
cooktop_rebate         = solara.reactive(0)

ev_starting_state     = solara.reactive("none")   # not in baseline by default
ev_swap_planned       = solara.reactive(False)
ev_swap_year          = solara.reactive(None)
ev_install_cost       = solara.reactive(800)
ev_rebate             = solara.reactive(0)

# ── Pricing & timeline ───────────────────────────────────────────────────────
price_scenario_a    = solara.reactive("moderate")
comparison_mode     = solara.reactive(False)
price_scenario_b    = solara.reactive("stress")
years               = solara.reactive(20)
sim_start_year      = solara.reactive(2025)
```

---

#### Top bar — HomeInfoBar

Read-only chip row, updates whenever any home profile reactive changes:

```
📍 San Jose, CA 95112  ·  Climate Zone CZ12  ·  3 bed  ·  1,800 sq ft  ·  Built 1985  ·  Average insulation
```

Implementation: `HomeInfoBar` reads all home-profile reactives and renders a styled
`solara.Markdown` row. No model object needed — purely reactive.

---

#### Summary stat bar

```
Journey savings vs do-nothing (Scenario A):  $X over N years  |  Payback: year Y
[comparison_mode=True] Scenario B savings: $Z over N years
```

Payback year = first year where cumulative journey cost < cumulative baseline cost.
If no crossover within the simulation window, show "Not within {N} years".

---

#### Control panels (three cards, same EN-Roads layout)

---

##### Panel 1 — Journey Planner

Each device slot renders as a single row. The row layout adapts to `starting_state`:

**Row anatomy:**

```
[State ▾]  Device name          [Planning? ☐]  Swap yr [slider]  Install $  Rebate [-$]  Net $
```

**State dropdown values and row behaviour:**

| State | Label | Slider | Install/Rebate | Baseline home |
|---|---|---|---|---|
| `"gas"` + planned | `Gas` | enabled | shown | Runs gas device forever |
| `"gas"` + not planned | `Gas` | hidden | hidden | Runs gas device forever |
| `"electric"` | `✓ Done` | hidden | hidden (sunk cost) | Runs electric device |
| `"none"` + planned | `Add` | enabled, label "Add in year" | shown | Zero — absent |
| `"none"` + not planned | `—` | hidden | hidden | Zero — absent |

**Full panel layout:**

```
Your electrification journey
─────────────────────────────────────────────────────────────────────────────
              Starting    Plan?    Swap yr      Install    Rebate    Net
HVAC          [Gas ▾]     [☑]     [===●  ] 3   $14,000   -$3,500   $10,500
              ☐ Has central AC in baseline
Water Heater  [Gas ▾]     [☑]     [=====●] 5   $2,500    -$500     $2,000
Dryer         [Gas ▾]     [☐]     ─────────     ─         ─         ─
Cooktop       [Gas ▾]     [☐]     ─────────     ─         ─         ─
EV Charger    [— ▾]       [☐]     ─────────     ─         ─         ─
─────────────────────────────────────────────────────────────────────────────
ℹ️  "Do nothing" baseline runs automatically: gas devices stay gas;
   already-done devices stay electric; no EV added.
```

HVAC row has a sub-toggle `☐ Has central AC in baseline` — when checked, sets
`hvac_has_cooling=True`, which adds `CentralAC` to the baseline alongside the furnace
(separate aging and replacement cost).

Swap year slider: range 1–25, step 1. Label shows the calendar year:
`Year 3  (2028)` = `sim_start_year + swap_year - 1`.

---

##### Panel 2 — Home Profile

Three sections within one card:

```
🏠 Home Details
  ZIP code         [ 95112     ]   text field  (Phase 3: auto-derive climate zone)
  Climate zone     [ CZ12    ▾ ]   select: CZ3, CZ4, CZ5, CZ12, CZ13, CZ16
  Bedrooms         [  3      ▾ ]   select 1–5  → scales baseload kWh + hot water
  Square footage   [ 1,800     ]   number field  (carried; shown in top bar)
  Year built       [ 1985      ]   number field  (carried; shown in top bar)

🏗️ Building Performance
  Insulation       ( Poor )  (● Average )  ( Good )   radio → UA value

🔥 Baseline device specs     [shown only when relevant slot has starting_state = "gas"]
  Furnace AFUE     ──────●──── 0.80    [slider 0.70–0.95]
  Water heater UEF ────●────── 0.65    [slider 0.55–0.70]

⚡ Electric replacement specs
  Heat pump COP    ───────●─── 3.5     [slider 2.5–4.5]
  Heat pump SEER   ──────●──── 22      [slider 16–28]
  HPWH UEF         ────────●── 3.5     [slider 2.5–4.0]
```

CA climate zones in the selector: CZ3 (SF coast), CZ4 (inland bay), CZ5 (Santa Cruz),
CZ12 (Sacramento/San Jose), CZ13 (Fresno), CZ16 (Tahoe/mountains).
Phase 3: typing a ZIP auto-selects the zone.

---

##### Panel 3 — Energy & Prices

```
📈 Rate scenario
   ( Conservative )  (● Moderate )  ( Stress / CEC )   radio

   Conservative  — Elec +4%/yr, Gas +4%/yr  "Slow price growth"
   Moderate      — Elec +7%/yr, Gas +8%/yr  "Recent trend (default)"
   Stress / CEC  — Elec +10%/yr, Gas +12%/yr "High gas cost scenario"

📅 Years to model     [========●    ] 20    [slider 5–30]

── Scenario comparison ─────────────────────────────────────────────────────
[ ] Compare two rate scenarios
    [when checked, reveals:]
    Scenario A: [Moderate  ▾]    Scenario B: [Stress ▾]
    Charts switch to 4-series (solid = A, dashed = B)
```

Named scenarios replace raw %/year sliders — more meaningful to advocates.

---

#### Chart updates

All 6 existing charts relabelled:
- "Gas home" → **"Do nothing"** (grey, `C_BASE`)
- "Electric home" → **"Your journey"** (blue, `C_ELEC`)

When `comparison_mode=True`, each chart renders 4 series:
- Solid grey = Do nothing, Scenario A
- Solid blue = Your journey, Scenario A
- Dashed grey = Do nothing, Scenario B
- Dashed blue = Your journey, Scenario B

**New chart — Journey Timeline (7th option):**

Horizontal chart, one row per device slot:

```
        0    3    5    8   10   15   20
HVAC    ─────●═══════════════════════   swap yr 3, net $10,500
Water   ──────────●══════════════════   swap yr 5, net $2,000
Dryer   ──────────────────────────────  (no swap — gas + end-of-life replacement at ~yr 10)
Cooktop ──────────────────────────────  (no swap)
EV      ──────────────────────────────  (not adding)

         ░░░░░░░░░░░░░░░░░░░░░░░░░░░░   background = gas price band (low→high)
```

Dashed pre-swap line = gas device running. Solid post-swap line = electric device running.
Vertical marker at swap year annotated with device name + net cost.
Background colour band = normalised gas price trajectory (light orange to deep orange).

---

**Claude Code prompt:**
```
Implement Objective 6 of docs/Phase2_Spec.md.
Refactor app.py completely:
  - Replace Gas Home / Electric Home panels with Journey Planner, Home Profile,
    and Energy & Prices panels as specified in §4 Objective 6.
  - Add HomeInfoBar reading from reactive home-profile state (no model object needed).
  - Add WhyWatt branding with os.path.exists() guards on logo files.
  - Relabel all charts: "Gas home" → "Do nothing", "Electric home" → "Your journey".
  - Update all 6 charts to render 4 series when comparison_mode=True
    (solid A, dashed B; same blue/grey palette).
  - Add Journey Timeline as 7th chart option.
  - Update summary stat bar: savings vs do-nothing + payback year.
  - Update reactive state and run_simulation() to build HomeConfig and pass it to HESModel.
All existing tests must still pass.
```

---

## 5. File Structure After Phase 2

```
hes/
├── CLAUDE.md                          ← always current — update after each objective
├── README.md                          ← WhyWatt name, Phase 2 run instructions
├── requirements.txt
├── Dockerfile
├── src/
│   ├── devices/
│   │   ├── __init__.py
│   │   ├── base.py                    ← EnergyConsumer abstract base
│   │   ├── seasonal.py                ← SeasonalDevice + GasDryer, HeatPumpDryer etc.
│   │   ├── physics.py                 ← PhysicsDevice + GasFurnace, HeatPumpHVAC etc.
│   │   └── schedule.py                ← ScheduleDevice + EVCharger
│   ├── home_config.py                 ← HomeConfig dataclass + BEDROOM_SCALING
│   ├── rate_loader.py                 ← RateLoader (CPUC data + projection)
│   ├── journey.py                     ← DeviceSlot + JourneyHome
│   ├── model.py                       ← HESModel (refactored)
│   └── app.py                         ← Solara UI (WhyWatt, Journey Planner)
├── data/
│   ├── rates/
│   │   ├── pge_elec_e1.json
│   │   └── pge_gas_g1.json
│   ├── climate/
│   │   └── bayarea_tmy3.json
│   ├── appliances/
│   │   ├── electrical_defaults.json
│   │   ├── gas_defaults.json
│   │   └── ev_schedule_default.json
│   └── homes/
│       ├── journey_slots_default.json ← default DeviceSlot configs (starting_state included)
│       └── home_config_default.json   ← default HomeConfig values (Phase 3: user-editable)
├── docs/
│   ├── assets/
│   │   ├── whywatt_logo.png
│   │   └── group_logo.png
│   ├── Glossary.md                    ← updated, no MMBtu
│   ├── Phase1_Goals.md                ← retain for history
│   └── Phase2_Spec.md                 ← this document
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_rate_loader.py            ← Objective 1
    ├── test_devices.py                ← Objective 2
    ├── test_journey.py                ← Objective 3
    └── test_dual_scenario.py          ← Objective 5
```

**Deleted in Phase 2:**
- `src/energy_consumer.py` — replaced by `src/devices/`
- `src/energy_price.py` — replaced by `src/rate_loader.py`
- `data/baseline_home.json` — replaced by `data/homes/journey_slots_default.json`
- `data/electrified_home.json` — replaced by same
- `tests/test_energy_consumer.py` — superseded by `test_devices.py`
- `tests/test_energy_price.py` — superseded by `test_rate_loader.py`

---

## 6. Phase 2 Done Criteria

- [ ] `pytest tests/` passes — all objectives
- [ ] `grep -r "MMBtu" src/ data/ tests/` returns zero results
- [ ] `GasFurnace` produces 270–300 therms for Bay Area defaults (±5% of 286)
- [ ] `HeatPumpHVAC` produces 1,830–2,030 kWh heating (±5% of 1,930)
- [ ] `GasWaterHeater` produces 200–220 therms (±5% of 210)
- [ ] `HeatPumpWaterHeater` produces 1,000–1,100 kWh (±5% of 1,050)
- [ ] `cost_history_by_category` has exactly `n_steps` entries per category
- [ ] `HomeConfig` with 3BR → 65 gal/day hot water and 1,200 kWh baseload
- [ ] `HomeConfig` with 1BR → ~600 kWh baseload (0.50× multiplier)
- [ ] `starting_state="electric"` slot: baseline home runs electric device from year 0
- [ ] HVAC `has_cooling_baseline=True`: baseline models furnace + AC aging separately
- [ ] `solara run src/app.py` loads with WhyWatt branding, no errors
- [ ] HomeInfoBar displays zip, climate zone, bedrooms, sq ft, year built from reactive state
- [ ] Journey Planner: HVAC swap_year=3 produces CapEx spike at year 3
- [ ] Journey Planner: `starting_state="electric"` row renders as greyed "✓ Done" with no slider
- [ ] Journey Planner: `starting_state="none"` row renders as "—" / "Add" with plan checkbox
- [ ] Baseline ("do nothing") cumulative cost exceeds journey cost after all swaps (stress scenario)
- [ ] Comparison mode shows 4-series charts (solid A, dashed B)
- [ ] Journey Timeline chart renders swap markers with device name and net cost annotations
- [ ] `RateLoader` returns 0.310 for PG&E electricity June 2023
- [ ] Logo placeholder renders without crash when PNG files are absent

---

## 8. Test & Validation Strategy

This section defines the full testing approach for Phase 2. Tests are written alongside each
objective — not after. The five layers work together: unit tests catch formula bugs,
integration tests catch wiring bugs, directional tests catch sign/unit errors, snapshot tests
catch regressions, and the debug export + validation notebook provide human-readable audits.

---

### 8.1 Layer 1 — Unit Tests

**What they catch:** formula errors, wrong constants, shape violations, boundary conditions.
**Speed:** < 1 second total. Run on every save.

Each test file is gated to its objective:

| File | Objective | Covers |
|------|-----------|--------|
| `tests/test_rate_loader.py` | 1 | RateLoader historical lookup, CAGR projection, scenario ordering |
| `tests/test_devices.py` | 2 | All PhysicsDevice outputs within ±5%, shape (12,), SeasonalDevice, EVCharger |
| `tests/test_journey.py` | 3 | DeviceSlot swap logic, CapEx events, cost_history_by_category length |
| `tests/test_dual_scenario.py` | 5 | Scenario A vs B independence, stress > moderate over 20 years |

**Key unit test cases (beyond the ±5% physics targets in §2.4):**

```python
# Shape contract — every device, always
assert device.monthly_consumption().shape == (12,)

# Cost identity for flat rates
rates = np.full(12, 0.386)
assert np.isclose(device.monthly_cost(rates).sum(),
                  device.annual_consumption() * 0.386, rtol=1e-6)

# Rate loader boundaries
assert rate_loader.get_rate("electricity", 2025, 12) == 0.386   # last historical
assert rate_loader.get_rate("electricity", 2026, 1) > 0.386     # projection kicks in

# Unknown scenario raises
with pytest.raises(ValueError):
    rate_loader.get_rate("electricity", 2030, 1, scenario="unknown")
```

---

### 8.2 Layer 2 — Integration / Scenario Tests

**What they catch:** wiring bugs — rates not passed through, baseline inheriting swap years,
CapEx double-counted, DataCollector reporters returning stale data.
**Location:** `tests/test_journey.py` and `tests/test_dual_scenario.py`

Key scenario-level assertions:

```python
# After all swaps, journey home must cost less than baseline (stress scenario)
model = HESModel(scenario="stress", years=20, all_swap_years_set=True)
model.run_all()
assert model.baseline_home.cumulative_opex > model.journey_home.cumulative_opex

# DataCollector has exactly n_years rows
df = model.datacollector.get_model_vars_dataframe()
assert len(df) == model.n_years

# cost_history_by_category has exactly n_steps entries per category
for cat, history in model.journey_home.cost_history_by_category.items():
    assert len(history) == model.n_years

# CapEx spike appears only at swap_year, not before or after
capex = model.journey_home.capex_by_year
assert capex[3] > 0     # swap at year 3
assert capex[2] == 0    # nothing before
assert capex[4] == 0    # nothing after (unless end-of-life coincides)

# comparison_mode=False: no _b attributes
model_single = HESModel(comparison_mode=False)
assert not hasattr(model_single, 'journey_home_b')
```

---

### 8.3 Layer 3 — Physics Sanity / Directional Tests

**What they catch:** sign errors and unit confusion that still pass the ±5% absolute check
by coincidence. These assert the *direction* of physical relationships, not absolute values.

```python
# More HDD → more heating consumption
furnace_cold = GasFurnace(ua=500, afue=0.80, monthly_hdd=hdd_cold)
furnace_mild = GasFurnace(ua=500, afue=0.80, monthly_hdd=hdd_mild)
assert furnace_cold.annual_consumption() > furnace_mild.annual_consumption()

# Better insulation → lower consumption
furnace_good = GasFurnace(ua=350, afue=0.80, monthly_hdd=hdd)
furnace_poor = GasFurnace(ua=650, afue=0.80, monthly_hdd=hdd)
assert furnace_good.annual_consumption() < furnace_poor.annual_consumption()

# Higher COP → lower kWh for same climate
hp_efficient = HeatPumpHVAC(ua=500, cop=4.0, seer=22, ...)
hp_standard  = HeatPumpHVAC(ua=500, cop=3.0, seer=22, ...)
assert hp_efficient.annual_consumption() < hp_standard.annual_consumption()

# Warmer inlet water → less water heating energy (smaller ΔT)
wh_summer = GasWaterHeater(uef=0.65, monthly_inlet_temp=[65]*12, ...)
wh_winter = GasWaterHeater(uef=0.65, monthly_inlet_temp=[54]*12, ...)
assert wh_summer.annual_consumption() < wh_winter.annual_consumption()

# Stress scenario rates exceed moderate in every future year
for year in range(2026, 2046):
    assert rate_loader.get_rate("gas", year, 6, "stress") > \
           rate_loader.get_rate("gas", year, 6, "moderate")
```

---

### 8.4 Layer 4 — Debug / Audit Export

**What it catches:** errors invisible to automated tests — seasonal profiles that look flat
when they should peak in winter, monthly costs that are right annually but wrong by month,
a CapEx event that fires in the wrong year. Also the primary tool for stakeholder review.

**Implementation:** `JourneyHome.export_debug_csv(path)` called from the UI or a test
fixture. Controlled by a `debug=True` flag on `HESModel` or called explicitly.

**Per-device monthly export** — one row per (year, device, month):

```
year, device,       fuel,        month, consumption, unit,   rate,  cost,  is_electric, device_age
2025, HVAC,         gas,         1,     28.4,         therms, 2.08,  59.07, False,       11
2025, HVAC,         gas,         2,     23.0,         therms, 2.08,  47.84, False,       11
...
2028, HVAC,         electricity, 1,     160.8,        kWh,    0.451, 72.52, True,        1
2028, Water Heater, electricity, 1,     87.5,         kWh,    0.451, 39.46, True,        1
```

**CapEx event export** — one row per event:

```
year, device,       event_type,    cost
2028, HVAC,         swap,          10500
2035, Water Heater, end_of_life,   2500
```

**Model-level annual summary** (always produced, not just in debug mode):

```
year, journey_opex, baseline_opex, opex_delta, journey_capex, baseline_capex,
      elec_rate_avg, gas_rate_avg, scenario
```

**Review workflow:**
1. Run `model.export_debug_csv("debug_run.csv")`
2. Open in Excel → pivot by device/year → chart monthly profiles
3. Cross-check HVAC monthly therms against `HDD[m] × formula` by hand for one month
4. Verify swap-year rows show transition from gas → electric mid-series
5. Confirm seasonal shape: HVAC peaks in Jan/Feb, water heating peaks in winter

---

### 8.5 Layer 5 — Snapshot / Regression Tests

**What they catch:** silent regressions — a refactor that shifts costs by 0.3% across all
years, or a rate-loading change that only shows up in year 15.

**Approach:** After Objective 3 produces a trusted reference run, save the `DataCollector`
output as a JSON fixture. CI compares future runs against it within a tight tolerance.

```python
# tests/test_regression.py
FIXTURE = "tests/fixtures/reference_run_moderate_20yr.json"

def test_regression_moderate_20yr():
    model = HESModel(scenario="moderate", years=20, sim_start_year=2025,
                     insulation_quality="average")
    model.run_all()
    df = model.datacollector.get_model_vars_dataframe()
    reference = pd.read_json(FIXTURE)

    # Cumulative cost must match within 0.5%
    assert np.allclose(df["Journey Cum Cost"],   reference["Journey Cum Cost"],   rtol=0.005)
    assert np.allclose(df["Baseline Cum Cost"],  reference["Baseline Cum Cost"],  rtol=0.005)
```

Regenerate fixtures intentionally with `pytest --update-snapshots` (custom flag) after a
deliberate model change. Never auto-regenerate in CI.

---

### 8.6 Validation Notebook

**File:** `notebooks/validation.ipynb`
**Purpose:** Human-readable sanity check before each merge. Run manually, not in CI.

Five sections — build incrementally across objectives:

| Section | Add in | Shows |
|---------|--------|-------|
| 1 — Device physics table | Obj 2 | Actual vs. expected vs. ±5% tolerance for all PhysicsDevices |
| 2 — Rate loader chart | Obj 1 | Historical + projected rates 2018–2050, all three scenarios |
| 3 — 20-year scenario run | Obj 3 | Cumulative cost curves, journey vs. baseline, moderate scenario |
| 4 — Monthly profile chart | Obj 3 | HVAC monthly kWh/therms — confirms winter heating + summer cooling peaks |
| 5 — Debug CSV pivot | Obj 3 | Annual cost by device and fuel, spot-check year 1 against manual calc |

Section 2 catches the most subtle bug: a discontinuity at the 2025/2026 boundary where
historical rates hand off to projected rates. Easy to see in a chart, impossible to see in
a number.

---

### 8.7 Shared Fixtures — conftest.py

`tests/conftest.py` provides shared fixtures to avoid copy-paste across all test files:

```python
# tests/conftest.py
import pytest
import numpy as np
import json
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"

@pytest.fixture
def bay_area_climate():
    with open(DATA / "climate/bayarea_tmy3.json") as f:
        return json.load(f)

@pytest.fixture
def monthly_hdd(bay_area_climate):
    return np.array(bay_area_climate["monthly_hdd_65f"], dtype=float)

@pytest.fixture
def monthly_cdd(bay_area_climate):
    return np.array(bay_area_climate["monthly_cdd_65f"], dtype=float)

@pytest.fixture
def monthly_inlet_temp(bay_area_climate):
    return np.array(bay_area_climate["monthly_inlet_water_temp_f"], dtype=float)

@pytest.fixture
def flat_elec_rates():
    """Flat $0.386/kWh — for cost identity tests."""
    return np.full(12, 0.386)

@pytest.fixture
def flat_gas_rates():
    """Flat $2.08/therm — for cost identity tests."""
    return np.full(12, 2.08)

@pytest.fixture
def rate_loader():
    from src.rate_loader import RateLoader
    return RateLoader()

@pytest.fixture
def default_slots():
    with open(DATA / "homes/journey_slots_default.json") as f:
        return json.load(f)
```

---

### 8.8 Test Sequencing by Objective

| Objective | Write these | Gate: must pass before next |
|-----------|-------------|----------------------------|
| 0 | None (visual) | — |
| 1 | `test_rate_loader.py` (Layers 1 + 3) | Yes |
| 2 | `test_devices.py` (Layers 1 + 3) | Yes |
| 3 | `test_journey.py` (Layers 1 + 2); `conftest.py`; debug CSV | Yes |
| 4 | Grep check; full `pytest tests/` | Yes — zero MMBtu |
| 5 | `test_dual_scenario.py` (Layer 2) | Yes |
| 6 | Manual UI smoke; regression fixture generation (Layer 5) | Notebook sections 3–5 |

**Running the suite:**

```bash
pytest tests/ -v                    # all tests, verbose
pytest tests/test_devices.py -v     # single file
pytest tests/ -k "furnace"          # filter by name
pytest tests/ --update-snapshots    # regenerate regression fixtures
```

---

## 9. Bug Fixes — Post-Objective-6 Patch

These fixes address issues discovered during UI testing. Apply as a single patch
branch on top of Objective 6. All existing tests must still pass after the patch;
new tests added per §9.4.

---

### 9.1 Physics Bug: HeatPumpHVAC Cooling Formula

**Location:** `src/devices/physics.py`, `HeatPumpHVAC.monthly_consumption()`

**Problem:** The cooling formula divides by `(seer / 10.0) × 3412`, which is
dimensionally inconsistent. SEER is in BTU/Wh — it should be applied directly
as a coefficient against kWh, not scaled by 3412 BTU/kWh.

**Correct formula:**
```
cooling kWh[m] = cdd[m] × 24 × UA / (SEER × 1000)
```

This gives for Bay Area defaults (CDD=340, UA=500, SEER=22):

| Formula | Result |
|---------|--------|
| Old: `cdd×24×UA / ((seer/10)×3412)` | ~543 kWh — looks close but is wrong |
| **Correct: `cdd×24×UA / (seer×1000)`** | **~185 kWh — Bay Area mild climate** |

Note: the original spec target of ~550 kWh was derived using the wrong formula.
The corrected target for Bay Area (CDD=340) is **~185 kWh/yr** — consistent with
a mild climate that rarely needs air conditioning.

**Fix:**
```python
# src/devices/physics.py — HeatPumpHVAC.monthly_consumption()
def monthly_consumption(self) -> np.ndarray:
    heating = self._hdd * 24 * self.ua / (self.cop * 3412)
    cooling = self._cdd * 24 * self.ua / (self.seer * 1000)   # ← corrected
    return heating + cooling
```

Same fix applies to `CentralAC.monthly_consumption()`:
```python
# src/devices/physics.py — CentralAC.monthly_consumption()
def monthly_consumption(self) -> np.ndarray:
    return self._cdd * 24 * self.ua / (self.seer * 1000)   # ← corrected
```

**Updated validation targets:**

| Device | Old target | Corrected target |
|--------|-----------|------------------|
| HeatPumpHVAC cooling (SEER=22, CDD=340) | ~550 kWh | **~185 kWh** |
| CentralAC (SEER=14, CDD=340) | ~860 kWh | **~291 kWh** |

Update `tests/test_devices.py` HeatPumpHVAC cooling test to use 185 kWh ± 10%.
Update `tests/test_devices.py` CentralAC test to use 291 kWh ± 10%.

---

### 9.2 Baseload Symmetry Bug

**Location:** `data/homes/journey_slots_default.json`, `starting_state` of
`"Lights and Appliances"` slot; `JourneyHome` slot stepping logic.

**Problem:** The `LightsAndPlugs` device (baseload electricity) is `starting_state:
"electric"` and correctly runs in both homes. However, validation reveals that the
gas home total is being compared against the electric home total **including** EV
charger load that the gas home does not have — creating an unfair comparison:

- Gas home year-1 opex: ~$1,636 (furnace + WH + dryer + cooktop + baseload)
- Electric home year-1 opex: ~$2,095 (same devices electrified + baseload)

The electric home is correctly more expensive in year 1 at 2025 rates. **This is
not a bug** — it is correct physics. The electric home's higher year-1 cost is
offset by lower escalation (elec +7%/yr vs gas +8%/yr) over the journey horizon.

**The real bug:** The default `journey_slots_default.json` has all `swap_year:
null`, meaning the journey home **never swaps any device** — it runs identical
gas devices as the baseline forever. Both lines are identical and the chart shows
no separation.

**Fix — set sensible default swap years in `journey_slots_default.json`:**

```json
[
  { "name": "HVAC",            "swap_year": 3  },
  { "name": "Water Heater",    "swap_year": 5  },
  { "name": "Dryer",           "swap_year": null },
  { "name": "Cooktop",         "swap_year": null },
  { "name": "EV Charger",      "swap_year": null },
  { "name": "Lights and Appliances", "swap_year": null }
]
```

HVAC at year 3 and WH at year 5 are planned by default so the demo immediately
shows meaningful separation between the journey and do-nothing lines. Users can
adjust all swap years from the Journey Planner panel.

**Also fix in `app.py` reactive defaults:**

```python
hvac_swap_planned  = solara.reactive(True)    # was False
hvac_swap_year     = solara.reactive(3)       # was None
wh_swap_planned    = solara.reactive(True)    # was False
wh_swap_year       = solara.reactive(5)       # was None
```

---

### 9.3 GasWaterHeater Output Below Target

**Problem:** The validation run shows GasWaterHeater at ~184 therms vs. target
~210 therms. This is because the target was computed using `daily_gallons=65`
but the actual default `daily_hot_water_gallons` in `bayarea_tmy3.json` produces
a slightly different result depending on rounding. Re-verify:

```
target = 65 gal/day × avg_days/month × 8.33 lb/gal × avg_ΔT × 0.00001 / 0.65
```

With Bay Area monthly inlet temps [54..66°F] and setpoint 120°F:
- Average ΔT = 120 - 60 = 60°F (approx)
- Annual: 65 × 365 × 8.33 × 60 × 0.00001 / 0.65 = **183.9 therms**

The formula is correct. The target of ~210 therms in the original spec was based
on a higher ΔT assumption (setpoint 125°F or inlet temp 50°F). Update the
validation target to **~184 therms ± 5%** and update `CLAUDE.md`.

**Fix:** Update spec target and test tolerance:
```python
# tests/test_devices.py
assert 175 <= gwh.annual_consumption() <= 195   # ~184 therms, ±5%
```

---

### 9.4 Bug Fix Tests

Add to `tests/test_devices.py`:

```python
def test_hp_hvac_cooling_formula_corrected(monthly_cdd, monthly_hdd, monthly_inlet_temp):
    """Cooling formula uses SEER×1000 not (SEER/10)×3412."""
    hp = HeatPumpHVAC(model=mock_model(), ua_btu_hr_f=500,
                      cop_heating=3.5, seer_cooling=22,
                      monthly_hdd=monthly_hdd, monthly_cdd=monthly_cdd)
    cooling_kwh = (hp._cdd * 24 * hp.ua / (hp.seer * 1000)).sum()
    assert 165 <= cooling_kwh <= 205    # ~185 kWh, Bay Area mild cooling

def test_gas_wh_corrected_target(monthly_inlet_temp):
    """Gas WH target is ~184 therms for Bay Area defaults."""
    gwh = GasWaterHeater(model=mock_model(), uef=0.65, daily_gallons=65,
                         monthly_inlet_temp_f=monthly_inlet_temp)
    assert 175 <= gwh.annual_consumption() <= 195

def test_journey_baseline_diverge_with_defaults():
    """Default swap_years (HVAC=3, WH=5) must produce diverging cost lines."""
    model = HESModel(n_years=20)
    model.run_all()
    df = model.datacollector.get_model_vars_dataframe()
    # By year 20, baseline must exceed journey cost
    assert df["Baseline Cum Cost"].iloc[-1] > df["Journey Cum Cost"].iloc[-1]
    # Lines must diverge — they cannot be identical at year 20
    delta = df["Opex Delta"].iloc[-1]
    assert delta > 0, f"Expected positive savings, got {delta:.0f}"
```

---

### 9.5 Claude Code Prompt — Bug Fix Patch

```
Apply the bug-fix patch described in §9 of docs/Phase2_Spec.md.
Do NOT touch any code outside the three changes listed.

Change 1 — physics.py cooling formula:
  In HeatPumpHVAC.monthly_consumption(), change:
    cooling = self._cdd * 24 * self.ua / ((self.seer / 10.0) * 3412)
  to:
    cooling = self._cdd * 24 * self.ua / (self.seer * 1000)
  Apply the identical fix to CentralAC.monthly_consumption().

Change 2 — journey_slots_default.json swap years:
  Set swap_year to 3 for the HVAC slot.
  Set swap_year to 5 for the Water Heater slot.
  All other slots remain swap_year: null.

Change 3 — app.py reactive defaults:
  Set hvac_swap_planned = solara.reactive(True)
  Set hvac_swap_year    = solara.reactive(3)
  Set wh_swap_planned   = solara.reactive(True)
  Set wh_swap_year      = solara.reactive(5)

After changes:
  Update tests/test_devices.py:
    - HeatPumpHVAC cooling target: 165–205 kWh (was 522–578)
    - CentralAC target: 275–310 kWh
    - GasWaterHeater target: 175–195 therms (was 200–220)
  Add the three new tests from §9.4.
  Run pytest tests/ — all must pass.
  Run: solara run src/app.py
    Verify two diverging lines appear in Cumulative Cost chart by default.
```

---

## 10. Independent Gas / Electricity Rate Sliders

This section replaces the single named-scenario selector in Objective 6 with
independent per-fuel escalation controls. The named presets remain as convenience
buttons but are no longer the only way to set rates.

---

### 10.1 Problem with Coupled Scenarios

The current `scenario_a / scenario_b` string approach ties gas and electricity
to the same named scenario, so:
- `"moderate"` gives elec +7% AND gas +8% — no way to say "moderate gas, conservative elec"
- Advocates often want to explore "what if gas spikes but grid stays flat" without
  being locked to a preset
- The CEC stranded gas analysis specifically calls out **asymmetric** escalation as
  the key risk — the tool should make this explorable

---

### 10.2 RateLoader Change — Add `custom_cagr` Parameter

**File:** `src/rate_loader.py`

Add an optional `custom_cagr` float parameter to `get_annual_monthly_rates()`.
When provided, it overrides the scenario-lookup CAGR for the projection period.
Historical period lookup is unchanged.

```python
def get_annual_monthly_rates(
    self,
    fuel: str,
    sim_start_year: int,
    n_years: int,
    scenario: str = "moderate",
    custom_cagr: float | None = None,   # ← new parameter
) -> np.ndarray:
    """
    Returns shape (n_years, 12).
    If custom_cagr is provided, it overrides the scenario CAGR for projection years.
    Historical period rates are always used as-is regardless of custom_cagr.
    """
    # For projection years: cagr = custom_cagr if provided, else scenario cagr
    ...
```

`get_rate()` also gets `custom_cagr`:
```python
def get_rate(
    self, fuel: str, year: int, month: int,
    scenario: str = "moderate",
    custom_cagr: float | None = None,
) -> float:
    ...
```

Backward compatibility: `custom_cagr=None` → behaviour identical to current
(scenario string drives CAGR). All existing tests pass unchanged.

---

### 10.3 HESModel Change — Accept Independent CAGRs

**File:** `src/model.py`

Replace the `scenario_a / scenario_b` string pair with explicit per-fuel CAGRs.
Keep the scenario strings as optional convenience parameters that pre-fill the CAGRs.

```python
class HESModel(mesa.Model):
    def __init__(self,
                 home_config:      HomeConfig | None = None,
                 # ── Scenario A — explicit CAGRs (takes priority) ──────────
                 elec_cagr_a:      float | None = None,    # e.g. 0.07
                 gas_cagr_a:       float | None = None,    # e.g. 0.08
                 # ── Scenario A — named preset (used when explicit CAGRs absent)
                 scenario_a:       str = "moderate",
                 # ── Scenario B (comparison mode) ─────────────────────────
                 elec_cagr_b:      float | None = None,
                 gas_cagr_b:       float | None = None,
                 scenario_b:       str = "stress",
                 comparison_mode:  bool = False,
                 n_years:          int  = 20,
                 sim_start_year:   int  = 2025,
                 slot_configs:     list | None = None):
```

**CAGR resolution logic (applies to both A and B):**
```python
# Scenario A
elec_cagr_a = elec_cagr_a if elec_cagr_a is not None \
              else SCENARIO_PRESETS[scenario_a]["elec"]
gas_cagr_a  = gas_cagr_a  if gas_cagr_a  is not None \
              else SCENARIO_PRESETS[scenario_a]["gas"]

SCENARIO_PRESETS = {
    "conservative": {"elec": 0.04, "gas": 0.04},
    "moderate":     {"elec": 0.07, "gas": 0.08},
    "stress":       {"elec": 0.10, "gas": 0.12},
}
```

Rate arrays built with explicit CAGRs:
```python
rl = RateLoader()
self.elec_rates = rl.get_annual_monthly_rates(
    "electricity", sim_start_year, n_years,
    scenario=scenario_a, custom_cagr=elec_cagr_a)
self.gas_rates = rl.get_annual_monthly_rates(
    "gas", sim_start_year, n_years,
    scenario=scenario_a, custom_cagr=gas_cagr_a)
```

---

### 10.4 app.py Reactive State Change

Replace the `price_scenario_a / price_scenario_b` string reactives with
independent CAGR sliders. The preset buttons populate both sliders simultaneously
but do not lock them.

**New reactive state (replaces old scenario strings):**

```python
# ── Pricing — independent per-fuel CAGRs ──────────────────────────────────
# Preset radio populates both sliders; user can then fine-tune either independently
gas_cagr_pct_a   = solara.reactive(8)     # integer %/yr, Scenario A
elec_cagr_pct_a  = solara.reactive(7)     # integer %/yr, Scenario A

comparison_mode  = solara.reactive(False)
gas_cagr_pct_b   = solara.reactive(12)    # integer %/yr, Scenario B
elec_cagr_pct_b  = solara.reactive(10)    # integer %/yr, Scenario B

years            = solara.reactive(20)
sim_start_year   = solara.reactive(2025)
```

**Preset buttons** — populate sliders without locking them:
```python
def _apply_preset(preset: str):
    p = SCENARIO_PRESETS[preset]
    gas_cagr_pct_a.set(int(p["gas"] * 100))
    elec_cagr_pct_a.set(int(p["elec"] * 100))
```

**run_simulation() change:**
```python
model = HESModel(
    home_config    = _build_home_config(),
    gas_cagr_a     = gas_cagr_pct_a.value  / 100.0,
    elec_cagr_a    = elec_cagr_pct_a.value / 100.0,
    gas_cagr_b     = gas_cagr_pct_b.value  / 100.0,
    elec_cagr_b    = elec_cagr_pct_b.value / 100.0,
    comparison_mode = comparison_mode.value,
    n_years        = years.value,
    sim_start_year = sim_start_year.value,
    slot_configs   = _build_slot_configs(),
)
```

---

### 10.5 UI Layout — Energy & Prices Panel (Revised)

Replaces the radio-only panel from Objective 6:

```
📈 Energy & Prices

Quick presets:  [ Conservative ]  [● Moderate ]  [ Stress / CEC ]
                (clicking a preset fills both sliders below)

Gas escalation       ───────●──── 8 %/yr    (range 0–20)
Electricity escal.   ──────●───── 7 %/yr    (range 0–15)

💡 Gas typically rises faster than electricity as grid decarbonises.

── Scenario comparison ──────────────────────────────────────────────────
[ ] Compare two rate scenarios
    [when checked, reveals:]
    Scenario B
    Quick presets:  [ Conservative ]  [ Moderate ]  [● Stress / CEC ]
    Gas escalation       ─────────────●── 12 %/yr
    Electricity escal.   ──────────●──── 10 %/yr
    Charts switch to 4-series (solid = A, dashed = B)

📅 Years to model    [========●    ] 20    (5–30)
```

**Visual design notes:**
- Gas slider uses `C_RED` (`#D0302D`) accent — signals risk/cost
- Elec slider uses `C_NAVY` (`#0D47A1`) accent — signals reliability/lower growth
- Preset buttons are a `solara.ToggleButtonsSingle` — visually shows active preset
  or goes to "Custom" if sliders are moved away from preset values
- "Custom" appears automatically when either slider no longer matches a preset:
  ```python
  def _current_preset_label():
      for name, p in SCENARIO_PRESETS.items():
          if (int(p["gas"]*100)  == gas_cagr_pct_a.value and
              int(p["elec"]*100) == elec_cagr_pct_a.value):
              return name.capitalize()
      return "Custom"
  ```

---

### 10.6 Price Trend Chart Updates

The existing Electricity Price Trend and Gas Price Trend charts (chart options 5 and 6)
should be updated to label the trend line with the actual CAGR value, not the scenario name:

```python
# Chart label — show actual CAGR, not just scenario name
label_a = f"Gas (+{gas_cagr_pct_a.value}%/yr)"
label_b = f"Gas Scenario B (+{gas_cagr_pct_b.value}%/yr)"  # when comparison_mode=True
```

---

### 10.7 Tests — Rate Decoupling

Add to `tests/test_rate_loader.py`:

```python
def test_custom_cagr_overrides_scenario(rate_loader):
    """custom_cagr=0.15 overrides moderate (0.07) for future years."""
    rate_default = rate_loader.get_rate("electricity", 2030, 6, "moderate")
    rate_custom  = rate_loader.get_rate("electricity", 2030, 6, "moderate",
                                        custom_cagr=0.15)
    assert rate_custom > rate_default
    # Verify formula: 0.386 × 1.15^5
    expected = 0.386 * (1.15 ** 5)
    assert abs(rate_custom - expected) < 0.001

def test_custom_cagr_does_not_affect_historical(rate_loader):
    """Historical period rates are unaffected by custom_cagr."""
    rate_hist    = rate_loader.get_rate("electricity", 2023, 6, "moderate")
    rate_custom  = rate_loader.get_rate("electricity", 2023, 6, "moderate",
                                        custom_cagr=0.99)
    assert rate_hist == rate_custom == 0.310

def test_gas_elec_cagr_independent(rate_loader):
    """Gas and electricity escalate at different rates when custom_cagr differs."""
    elec = rate_loader.get_annual_monthly_rates(
        "electricity", 2025, 5, custom_cagr=0.03)
    gas  = rate_loader.get_annual_monthly_rates(
        "gas",         2025, 5, custom_cagr=0.12)
    # Year 5 gas rate must be much higher relative to base than elec
    elec_ratio = elec[4].mean() / elec[0].mean()
    gas_ratio  = gas[4].mean()  / gas[0].mean()
    assert gas_ratio > elec_ratio * 1.3   # gas grows at least 30% faster

def test_model_accepts_independent_cagrs():
    """HESModel with explicit gas_cagr=0.12, elec_cagr=0.04 produces
       higher gas rates than electricity in year 20."""
    model = HESModel(gas_cagr_a=0.12, elec_cagr_a=0.04, n_years=20)
    model.run_all()
    df = model.datacollector.get_model_vars_dataframe()
    # Gas rate in year 20 should be much higher than elec rate
    # (in $/therm vs $/kWh, convert both to $/MMBtu equivalent for comparison)
    # Simpler: just verify year-20 gas rate >> year-1 gas rate by ~factor of 9
    # 2.08 × 1.12^20 ≈ $20/therm
    gas_yr20 = df["Gas Rate"].iloc[-1]
    assert gas_yr20 > 10.0, f"Gas rate in year 20 should exceed $10/therm, got {gas_yr20:.2f}"
```

---

### 10.8 Claude Code Prompt — Rate Decoupling

```
Implement §10 (Independent Gas/Electricity Rate Sliders) of docs/Phase2_Spec.md.
Apply in three steps — test after each.

Step 1 — rate_loader.py:
  Add optional custom_cagr: float | None = None parameter to both get_rate()
  and get_annual_monthly_rates().
  When custom_cagr is not None, use it instead of the scenario CAGR for
  projection years only. Historical period lookup is unchanged.
  All existing tests must still pass (custom_cagr=None is backward-compatible).
  Add the four new tests from §10.7 to tests/test_rate_loader.py.

Step 2 — model.py:
  Add elec_cagr_a, gas_cagr_a, elec_cagr_b, gas_cagr_b parameters to
  HESModel.__init__(). Add SCENARIO_PRESETS dict inside model.py.
  Resolve: explicit CAGR takes priority over named scenario string.
  Pass custom_cagr= to RateLoader calls.
  Verify: HESModel(scenario_a="moderate") produces identical output to before
  (backward-compat test using the regression fixture from §8.5).

Step 3 — app.py:
  Replace price_scenario_a / price_scenario_b reactive strings with
  gas_cagr_pct_a, elec_cagr_pct_a, gas_cagr_pct_b, elec_cagr_pct_b integer reactives.
  Add _apply_preset(preset) helper.
  Rebuild the Energy & Prices panel per §10.5:
    - Preset buttons (Conservative / Moderate / Stress) at top
    - Gas slider (0–20%, C_RED accent)
    - Elec slider (0–15%, C_NAVY accent)
    - "Custom" label appears automatically when sliders diverge from a preset
    - Scenario B panel revealed when comparison_mode toggle is on
  Update run_simulation() to pass explicit CAGRs to HESModel.
  Update price trend chart labels to show actual CAGR % (§10.6).
  Run solara run src/app.py and confirm:
    - Preset buttons populate both sliders
    - Moving either slider independently updates charts in real time
    - Gas slider is red-accented, elec slider is navy-accented
    - "Custom" label appears when sliders diverge from a preset
```

---

## 7. Deferred to Phase 3

| Feature | Phase 3 approach |
|---------|-----------------|
| TOU rate structures (E-TOU-C) | Time-of-day dispatch model for HVAC + EV |
| NEM3 / solar net metering | PVWatts API + Net Billing Tariff |
| Rebate database (DSIRE API) | Dynamic rebate lookup by zip + income |
| Carbon / emissions tracking | CAISO marginal emissions factor |
| Health cost model (PM2.5) | RMI/UCSF literature coefficients |
| Full EPW weather-file model | EnergyPlus hourly building load |
| SCE / SMUD rate comparison | Utility selector + rate table DB |
| Financing / loan scenarios | Amortisation overlay on CapEx |
| Monte Carlo uncertainty | Price + efficiency distributions |
| Multi-journey comparison | Two user-defined journeys side by side |
| Session save / load | `json.dump` / `json.load` using §2.5 schema; Load/Save buttons in UI |
| ZIP → climate zone auto-derive | Zip-to-CZ lookup table; auto-populate climate_zone field |
