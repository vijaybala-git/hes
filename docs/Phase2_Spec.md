# WhyWatt — Phase 2 Development Spec

**Status:** Phase 2 implemented through Objective 6; §9 bug fixes, §10 rate decoupling, §11 per-device charts, §12 baseload formula, §13 appliance detail expand/collapse, §14-17 v2.7 additions
**Follows:** Phase 1 complete (Mesa + Solara, 42 unit tests, dual-home simulation)
**Project rename:** HES → **WhyWatt?** (update all UI titles, headers, doc references)
**Last updated:** §14 EV physics, §15 Panel Upgrade, §16 Baseload as full slot, §17 Solar+Battery (Phase 2.7)

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

## 11. Per-Device Stacked Charts (Phase 2.5)

Two new chart pairs added to the existing chart selector. Each pair shows the
same x-axis (simulation years) with two vertically stacked charts:
1. Annual cost ($/yr) by device
2. Annual consumption (kWh-equivalent/yr) by device

The charts are rendered for each home separately — "Do nothing" and "Your journey"
— accessed via a tab toggle within the chart panel.

---

### 11.1 Design Decisions

**Stacked area chart** (not bar) — smooth filled areas with `tension: 0.25`.
Shows cumulative total at any year by reading the top of the stack.

**Vertical pair, shared x-axis** — cost chart on top, consumption chart directly
below. Same year labels, same annotations. Users can visually correlate cost and
consumption at the same point in time without eye movement between separate panels.

**Swap year annotations** — vertical dashed lines with labels ("HVAC swap",
"WH swap" etc.) on the journey charts only. Powered by
`chartjs-plugin-annotation`. Do-nothing charts have no annotations.
Annotations use the same colour as the device being swapped.

**Consumption conversion** — gas consumption (therms) is converted to kWh-equivalent
for display on the consumption chart only. The conversion is display-only;
no internal simulation values change:
```python
KWH_PER_THERM = 29.3   # 1 therm = 29.3 kWh (higher heating value)
```
This conversion makes the efficiency gain of heat pumps visible:
a gas furnace using 286 therms = 8,380 kWh-equivalent, while a heat pump
doing the same job uses ~2,100 kWh — a 4× reduction on the consumption chart.

**Tab toggle** — "Do nothing" / "Your journey" tabs switch which home's chart
pair is displayed. Both sets of charts are rendered at page load; only visibility
changes on tab click.

---

### 11.2 Device Colour Assignment

Consistent across both cost and consumption charts, both homes:

| Device | Background (70% opacity) | Border |
|--------|--------------------------|--------|
| HVAC | `rgba(13,71,161,0.70)` | `#0D47A1` navy |
| Water heater | `rgba(21,101,192,0.60)` | `#1565C0` mid-blue |
| Dryer | `rgba(208,48,45,0.55)` | `#D0302D` red |
| Cooktop | `rgba(236,155,30,0.55)` | `#EC9B1E` amber |
| Baseload | `rgba(120,144,156,0.45)` | `#78909C` slate |

Device order in stack (bottom to top): HVAC, Water heater, Dryer, Cooktop, Baseload.
HVAC is anchored at the bottom because it is the largest single item and the
most important swap story to tell.

---

### 11.3 Data Source — JourneyHome

The per-device cost data already exists in `JourneyHome.cost_history_by_category`
(one list per category, `n_years` entries). The chart builds on this:

```python
# Already collected in model — no new simulation work needed
jh = model.journey_home
bh = model.baseline_home

cost_by_device_journey = {
    "HVAC":        jh.cost_history_by_category["HVAC_Heating"],
    "Water Heater":jh.cost_history_by_category["WaterHeating"],
    "Dryer":       jh.cost_history_by_device["Dryer"],    # see §11.4
    "Cooktop":     jh.cost_history_by_device["Cooktop"],
    "Baseload":    jh.cost_history_by_category["Baseload"],
}
```

**Problem:** `cost_history_by_category` aggregates all Baseload devices together
(dryer + cooktop + lights + EV charger). We need per-device cost history to plot
dryer and cooktop separately.

**Fix — add `cost_history_by_slot` to `JourneyHome`:**

```python
# In JourneyHome.__init__:
self.cost_history_by_slot: dict[str, list[float]] = {
    slot.name: [] for slot in self.slots
}

# In JourneyHome.step(), after existing category aggregation:
for slot in self.slots:
    self.cost_history_by_slot[slot.name].append(
        slot.active_device_cost_this_step   # float set during slot.step()
    )
```

Each slot accumulates its own annual cost list of length `n_years`.
The chart reads from `cost_history_by_slot` for device-level granularity.

**For consumption** — need `consumption_history_by_slot`:
```python
self.consumption_history_by_slot: dict[str, list[float]] = {
    slot.name: [] for slot in self.slots
}
# Populated same way as cost — native unit (kWh or therms)
# Chart layer converts therms → kWh-eq before rendering
```

---

### 11.4 app.py Chart Implementation

**Chart selector update** — two separate entries, each independently selectable:

```python
CHART_OPTIONS = [
    ("cumulative",          "Cumulative cost"),
    ("annual",              "Annual cost"),
    ("category",            "Cost by category"),
    ("price_trend",         "Price trends"),
    ("capex",               "Equipment costs"),
    ("journey_timeline",    "Journey timeline"),
    ("device_cost",         "Cost by device"),         # ← new
    ("device_consumption",  "Energy use by device"),   # ← new
]
```

Each chart type renders independently. Both use the same home tab toggle
(`device_chart_home` reactive) and the same colour/annotation scheme.
The two are separate chart options — the user picks one from the dropdown.

**Shared render helper — one function, `chart_type` parameter:**

```python
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

KWH_PER_THERM = 29.3

DEVICE_ORDER  = ["HVAC", "Water Heater", "Dryer", "Cooktop", "Lights and Appliances"]
DEVICE_LABELS = ["HVAC", "Water heater", "Dryer", "Cooktop", "Baseload"]
DEVICE_COLORS = ["#0D47A1", "#1565C0", "#D0302D", "#EC9B1E", "#78909C"]
DEVICE_ALPHAS = [0.70,      0.60,       0.55,      0.55,      0.45]


def render_device_chart(model, home: str = "journey",
                        chart_type: str = "device_cost") -> plt.Figure:
    """
    Render a single stacked area chart.
    chart_type: "device_cost"        → annual cost ($/yr) by device
                "device_consumption" → annual energy (kWh-eq/yr) by device
    home:       "journey" | "baseline"
    """
    jh = model.journey_home if home == "journey" else model.baseline_home
    cal_years = [model.sim_start_year + y for y in range(model.n_years)]

    fig, ax = plt.subplots(figsize=(8, 3.8))

    stack = np.zeros(model.n_years)
    patches = []

    for i, name in enumerate(DEVICE_ORDER):
        if chart_type == "device_cost":
            data = np.array(
                jh.cost_history_by_slot.get(name, [0] * model.n_years),
                dtype=float
            )
            y_label   = "$/yr"
            y_fmt     = lambda v, _: f"${v/1000:.0f}k"
            tip_unit  = "$"
            tip_suffix = ""

        else:  # device_consumption
            raw  = np.array(
                jh.consumption_history_by_slot.get(name, [0] * model.n_years),
                dtype=float
            )
            fuel = jh.fuel_history_by_slot.get(name, ["electricity"] * model.n_years)
            data = np.where(
                np.array(fuel) == "gas",
                raw * KWH_PER_THERM,
                raw
            )
            y_label   = "kWh-eq / yr"
            y_fmt     = lambda v, _: f"{v/1000:.0f}k"
            tip_unit  = ""
            tip_suffix = " kWh"

        ax.fill_between(cal_years, stack, stack + data,
                        color=DEVICE_COLORS[i], alpha=DEVICE_ALPHAS[i],
                        linewidth=0)
        ax.plot(cal_years, stack + data,
                color=DEVICE_COLORS[i], linewidth=1.2)
        patches.append(mpatches.Patch(color=DEVICE_COLORS[i],
                                      label=DEVICE_LABELS[i]))
        stack += data

    # ── Swap annotations (journey only) ──────────────────────────────────
    SWAP_COLORS = {"HVAC": "#0D47A1", "Water Heater": "#1565C0",
                   "Dryer": "#D0302D", "Cooktop": "#EC9B1E"}
    if home == "journey":
        for slot in jh.slots:
            if slot.swap_year is None:
                continue
            cal = model.sim_start_year + slot.swap_year - 1
            color = SWAP_COLORS.get(slot.name, "#78909C")
            ax.axvline(cal, color=color, linewidth=1.2,
                       linestyle=(0, (4, 3)), alpha=0.7)
            ax.text(cal + 0.15, ax.get_ylim()[1] * 0.94,
                    slot.name, fontsize=8, color=color, va="top")

    # ── Styling ────────────────────────────────────────────────────────
    ax.set_ylabel(y_label, fontsize=9, color="#78909C")
    ax.set_xlabel("Year", fontsize=9, color="#78909C")
    ax.tick_params(axis="both", labelsize=8, colors="#78909C")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(y_fmt))
    ax.grid(axis="y", color="#78909C", alpha=0.12, linewidth=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(handles=patches, loc="upper left",
              fontsize=8, framealpha=0.9, ncol=len(DEVICE_ORDER))

    home_label = "Your journey" if home == "journey" else "Do nothing"
    chart_label = "Annual cost by device" if chart_type == "device_cost" \
                  else "Annual energy use by device (kWh-equivalent)"
    ax.set_title(f"{home_label} — {chart_label}",
                 fontsize=10, fontweight=500, loc="left", pad=8)

    plt.tight_layout()
    return fig
```

**In `app.py`, render section:**

```python
# Reactive for device chart home selector (shared by both device chart types)
device_chart_home = solara.reactive("journey")  # "journey" | "baseline"

# Inside render_chart() or equivalent:
if chart_type.value in ("device_cost", "device_consumption"):
    with solara.Row():
        solara.ToggleButtonsSingle(
            value=device_chart_home,
            values=[("journey", "Your journey"), ("baseline", "Do nothing")]
        )
    fig = render_device_chart(
        model,
        home=device_chart_home.value,
        chart_type=chart_type.value
    )
    solara.FigureMatplotlib(fig)
    plt.close(fig)
```

The home tab toggle (`Your journey` / `Do nothing`) persists across both chart
types — switching from cost to consumption remembers which home was selected.

---

### 11.5 JourneyHome Changes — New History Dictionaries

Three new per-slot history dicts added to `JourneyHome`:

```python
# Added to JourneyHome.__init__:
self.cost_history_by_slot:        dict[str, list[float]] = {s.name: [] for s in slots}
self.consumption_history_by_slot: dict[str, list[float]] = {s.name: [] for s in slots}
self.fuel_history_by_slot:        dict[str, list[str]]   = {s.name: [] for s in slots}
```

Populated in `JourneyHome.step()` after the existing per-slot step call:

```python
for slot in self.slots:
    slot_cost = slot.step(current_year, elec_r, gas_r, self.is_baseline_home)
    ...
    # New — record per-slot detail
    self.cost_history_by_slot[slot.name].append(slot_cost)

    active_dev = slot._last_active_device   # set by DeviceSlot.step()
    if active_dev is not None:
        self.consumption_history_by_slot[slot.name].append(
            active_dev.history["consumption"][-1])
        self.fuel_history_by_slot[slot.name].append(
            active_dev.fuel_type)
    else:
        self.consumption_history_by_slot[slot.name].append(0.0)
        self.fuel_history_by_slot[slot.name].append("electricity")
```

`DeviceSlot.step()` stores a `_last_active_device` reference so `JourneyHome`
can read the fuel type without duplicating the active-device logic:

```python
# In DeviceSlot.step():
self._last_active_device = active_list[0] if active_list else None
```

---

### 11.6 Tooltip Behaviour

Matplotlib does not have Chart.js-style interactive hover tooltips by default.
For the Solara prototype, we use static tooltips via `mplcursors`:

```python
import mplcursors  # add to requirements.txt

# After building the chart, attach cursor
cursor = mplcursors.cursor(ax_cost, hover=True)
@cursor.connect("add")
def on_add(sel):
    yr = int(sel.target[0])
    sel.annotation.set_text(f"Year {yr}\nTotal: ${cost_stack[yr-1]:,.0f}")
```

If `mplcursors` causes rendering issues in Solara, fall back to static annotations
at swap years only (no hover). Defer full interactive tooltip to Phase 3.

---

### 11.7 Tests

Add to `tests/test_journey.py`:

```python
def test_cost_history_by_slot_length():
    """Each slot has exactly n_years entries in cost_history_by_slot."""
    model = HESModel(n_years=10)
    model.run_all()
    for slot in model.journey_home.slots:
        h = model.journey_home.cost_history_by_slot[slot.name]
        assert len(h) == 10, f"{slot.name}: expected 10, got {len(h)}"

def test_consumption_history_by_slot_fuel_type():
    """Before swap year, fuel is gas. After swap year, fuel is electricity."""
    model = HESModel(n_years=10)
    model.run_all()
    jh = model.journey_home
    hvac_slot = next(s for s in jh.slots if s.name == "HVAC")
    fuels = jh.fuel_history_by_slot["HVAC"]
    swap = hvac_slot.swap_year  # default 3
    if swap:
        assert all(f == "gas"         for f in fuels[:swap-1])
        assert all(f == "electricity" for f in fuels[swap-1:])

def test_kwh_equivalent_drops_at_swap():
    """Total kWh-equivalent consumption drops at HVAC swap year (COP > 1)."""
    model = HESModel(n_years=10)
    model.run_all()
    jh = model.journey_home
    raw  = jh.consumption_history_by_slot["HVAC"]
    fuel = jh.fuel_history_by_slot["HVAC"]
    kwh_eq = [r*29.3 if f=="gas" else r for r,f in zip(raw, fuel)]
    hvac_slot = next(s for s in jh.slots if s.name == "HVAC")
    swap = hvac_slot.swap_year
    if swap and swap < 10:
        pre_swap_avg  = sum(kwh_eq[:swap])   / swap
        post_swap_avg = sum(kwh_eq[swap:]) / (10-swap)
        assert post_swap_avg < pre_swap_avg, \
            "Heat pump must use less kWh-equivalent than gas furnace"
```

---

### 11.8 Claude Code Prompt — Per-Device Charts

```
Implement §11 (Per-Device Stacked Charts) of docs/Phase2_Spec.md.
Apply in two steps.

Step 1 — journey.py:
  Add three new per-slot history dicts to JourneyHome.__init__:
    cost_history_by_slot, consumption_history_by_slot, fuel_history_by_slot
  Populate them in JourneyHome.step() after each slot.step() call.
  Add _last_active_device attribute to DeviceSlot — set during step().
  Add tests from §11.7 to tests/test_journey.py.
  Run pytest — all must pass before Step 2.

Step 2 — app.py:
  Add these two entries to CHART_OPTIONS (append after existing entries):
    ("device_cost",        "Cost by device")
    ("device_consumption", "Energy use by device")
  Add device_chart_home = solara.reactive("journey") to reactive state.
  Implement render_device_chart(model, home, chart_type) per §11.4:
    - Single subplot (figsize 8×3.8)
    - Stacked area chart for the requested chart_type
    - device_cost: $/yr per device, y-axis ${n}k
    - device_consumption: kWh-eq/yr per device, y-axis {n}k
      gas therms converted via KWH_PER_THERM = 29.3 using fuel_history_by_slot
    - Device order and colours per §11.2
    - Swap year vertical dashed annotations on journey home only
    - Legend in top-left (ncol=5)
    - Chart title: "{home_label} — {chart_label}"
  When chart_type.value in ("device_cost", "device_consumption"):
    - Render ToggleButtonsSingle (Your journey / Do nothing)
    - Call render_device_chart() with matching chart_type
    - Display with solara.FigureMatplotlib(); plt.close(fig) after
  Add mplcursors to requirements.txt.
  Run solara run src/app.py and verify:
    - Both new options appear in chart dropdown
    - Each renders independently as a single stacked area chart
    - Journey/baseline toggle works for both
    - Swap annotations appear on journey charts only
    - Switching between the two chart types remembers the home selection
```

---

## 12. Baseload Formula + Efficiency Journey Slot (Phase 2.5)

Replaces the bedroom-scaling lookup table with a physics-grounded formula.
Adds a baseload efficiency improvement as a first-class journey slot in the
Journey Planner — so LED upgrades and smart plug investments appear alongside
HVAC and water heater swaps with their own cost, rebate, and payback story.

---

### 12.1 Formula

```
baseload_kwh = (sq_ft × intensity) + (bedrooms × per_bedroom) + constant
```

| Term | Symbol | Default | Source |
|------|--------|---------|--------|
| Floor area intensity | `intensity` | 0.45 kWh/sqft/yr | EIA RECS 2020 CA |
| Per-bedroom occupancy load | `per_bedroom` | 200 kWh/bedroom/yr | DOE occupancy proxy |
| Always-on constant (before) | `constant_before` | 500 kWh/yr | Fridge + standby + router |
| Always-on constant (after) | `constant_after` | 300 kWh/yr | LED + smart plugs applied |

`intensity` and `per_bedroom` are fixed constants in Phase 2 (Phase 3 sliders).
`constant_before` and `constant_after` are user-controlled via sliders.

**Validation for 3BR, 1,800 sqft, default constants:**
```
before: (1800 × 0.45) + (3 × 200) + 500 = 810 + 600 + 500 = 1,910 kWh/yr
after:  (1800 × 0.45) + (3 × 200) + 300 = 810 + 600 + 300 = 1,710 kWh/yr
savings: 200 kWh/yr ≈ $77/yr at $0.386/kWh
```

**Replaces bedroom scaling:** `BEDROOM_SCALING` dict and `baseload_multiplier`
are removed from `home_config.py`. `HESModel.__init__` computes `baseload_kwh`
directly from the formula. Hot water gallons scaling is retained separately
(still bedroom-driven, unrelated to baseload).

---

### 12.2 Two-State Baseload Journey Slot

The baseload slot becomes a proper journey slot with a before and after state.
Both states are electric — the “swap” is efficiency improvement, not fuel change.

**Updated slot in `journey_slots_default.json`:**

```json
{
  "name": "Lights and Appliances",
  "category": "Baseload",
  "starting_state": "electric",
  "baseline_devices": [
    {"class": "LightsAndPlugs", "annual_kwh": "FORMULA_BEFORE", "lifespan": 15}
  ],
  "electric_device": {
    "class": "LightsAndPlugs", "annual_kwh": "FORMULA_AFTER", "lifespan": 15
  },
  "swap_year": null,
  "install_cost": 400,
  "rebate": 0
}
```

Note: `"FORMULA_BEFORE"` and `"FORMULA_AFTER"` are placeholders — `HESModel`
computes the actual kWh values at init and injects them into the device
constructors. The JSON schema carries the slot structure; the formula runs
in Python.

**Slot behaviour:**

| State | Journey home | Do-nothing baseline |
|-------|-------------|---------------------|
| Before swap year (or no swap planned) | `LightsAndPlugs(kwh=formula_before)` | `LightsAndPlugs(kwh=formula_before)` |
| On and after swap year | `LightsAndPlugs(kwh=formula_after)` | `LightsAndPlugs(kwh=formula_before)` |

The do-nothing baseline always runs `formula_before` — no efficiency investment.
The journey home transitions to `formula_after` at `swap_year`.

**CapEx at swap year:** `install_cost - rebate` logged, same as other slots.
Default `install_cost = 400` (LED + smart plug kit), `rebate = 0`.

---

### 12.3 `home_config.py` Changes

**Remove:**
```python
# Delete entirely:
BEDROOM_SCALING = { 1: {"baseload_multiplier": ...}, ... }
```

**Add:**
```python
# Baseload formula constants (Phase 2 fixed; Phase 3 makes sliders)
BASELOAD_INTENSITY_KWH_PER_SQFT = 0.45   # EIA RECS 2020 CA
BASELOAD_PER_BEDROOM_KWH        = 200.0  # DOE occupancy proxy

def compute_baseload_kwh(sq_ft: int, bedrooms: int, constant: float) -> float:
    """Return annual baseload kWh from formula."""
    return (
        sq_ft * BASELOAD_INTENSITY_KWH_PER_SQFT
        + bedrooms * BASELOAD_PER_BEDROOM_KWH
        + constant
    )
```

**`HomeConfig` gains two new fields:**
```python
@dataclass
class HomeConfig:
    ...existing fields...
    baseload_constant_before: float = 500.0  # always-on kWh/yr (current)
    baseload_constant_after:  float = 300.0  # always-on kWh/yr (post LED/smart plugs)
    baseload_swap_year:       int | None = None  # year of efficiency upgrade
    baseload_install_cost:    float = 400.0
    baseload_rebate:          float = 0.0
```

**Hot water scaling retained** — bedroom-based daily gallons remain in a
separate small lookup (hot water is occupancy-driven, not sqft-driven):
```python
HOT_WATER_GAL_PER_DAY = {1: 30, 2: 50, 3: 65, 4: 75, 5: 85}
# Source: DOE/ENERGY STAR; 3BR = TMY3 reference 65 gal/day
```

---

### 12.4 `model.py` Changes

**`HESModel.__init__` — replace bedroom scaling block:**

```python
# REMOVE:
br = BEDROOM_SCALING[home_config.num_bedrooms]
baseload_kwh = 1200 * br["baseload_multiplier"]
hw_gallons   = br["hot_water_gal_per_day"]

# REPLACE WITH:
from home_config import compute_baseload_kwh, HOT_WATER_GAL_PER_DAY

baseload_before = compute_baseload_kwh(
    home_config.square_footage,
    home_config.num_bedrooms,
    home_config.baseload_constant_before
)
baseload_after = compute_baseload_kwh(
    home_config.square_footage,
    home_config.num_bedrooms,
    home_config.baseload_constant_after
)
hw_gallons = HOT_WATER_GAL_PER_DAY[home_config.num_bedrooms]
```

**Slot construction — inject formula values into `LightsAndPlugs` devices:**

```python
# When building the Lights and Appliances slot:
for cfg in slot_configs:
    if cfg["name"] == "Lights and Appliances":
        # Override annual_kwh with formula output
        for dev in cfg.get("baseline_devices", []):
            if dev["class"] == "LightsAndPlugs":
                dev["annual_kwh"] = baseload_before
        if cfg.get("electric_device", {}).get("class") == "LightsAndPlugs":
            cfg["electric_device"]["annual_kwh"] = baseload_after
        # Apply swap year and costs from HomeConfig
        cfg["swap_year"]    = home_config.baseload_swap_year
        cfg["install_cost"] = home_config.baseload_install_cost
        cfg["rebate"]       = home_config.baseload_rebate
```

This keeps the JSON schema clean (no formula logic in JSON) while injecting
the computed values before slot construction.

---

### 12.5 UI — Journey Planner Baseload Row

The Lights and Appliances row in the Journey Planner expands to show the
two-state configuration. It sits below the other device rows, visually
separated by a thin divider with the label **“Baseload efficiency”**.

**New reactive state:**

```python
# Baseload formula inputs (flow into HomeConfig)
baseload_constant_before = solara.reactive(500)   # kWh/yr, slider 0–1500
baseload_constant_after  = solara.reactive(300)   # kWh/yr, slider 0–1500
baseload_swap_planned    = solara.reactive(False)
baseload_swap_year       = solara.reactive(2)     # default year 2 if planned
baseload_install_cost    = solara.reactive(400)
baseload_rebate          = solara.reactive(0)
```

**Derived display reactive (computed, read-only):**
```python
@solara.computed
def baseload_kwh_before():
    return compute_baseload_kwh(
        square_footage.value,
        num_bedrooms.value,
        baseload_constant_before.value
    )

@solara.computed
def baseload_kwh_after():
    return compute_baseload_kwh(
        square_footage.value,
        num_bedrooms.value,
        baseload_constant_after.value
    )
```

**UI panel layout (appended to Journey Planner, below divider):**

```
──────────────────────────────────────────────────────────────────
💡 Baseload efficiency

Current always-on load:
  Always-on appliances    [───●───────] 500 kWh/yr
  (fridge, standby, router, misc)
  → Estimated total baseload: 1,910 kWh/yr
     (1,800 sqft × 0.45 + 3 bed × 200 + 500)

[ ] Planning a baseload efficiency upgrade (LED, smart plugs, etc.)
    [when checked, reveals:]
    Upgrade in year         [───●───────] 2   (2027)
    After-upgrade constant  [──●────────] 300 kWh/yr
    → Estimated total after: 1,710 kWh/yr
    Install cost            $400
    Rebate                  $0
    Net cost                $400
    → Annual saving: ~200 kWh/yr ≈ $77/yr
    → Simple payback: ~5.2 yrs
──────────────────────────────────────────────────────────────────
```

**Design notes:**
- The formula breakdown `(sqft × 0.45 + bedrooms × 200 + constant)` is shown
  inline below each constant slider so the user understands what drives the number.
  It updates live as sq_ft or bedrooms change in the Home Profile panel.
- The payback estimate is computed inline in the UI:
  `payback = install_cost / (annual_saving × elec_rate)` using current elec_rate.
- The always-on constant slider uses `C_NAVY` accent for both before/after.
- When upgrade is not planned, only the "current" constant slider is visible.

---

### 12.6 `_build_home_config()` Changes in `app.py`

The function that assembles `HomeConfig` from reactive state gains the new fields:

```python
def _build_home_config() -> HomeConfig:
    return HomeConfig(
        zip_code           = zip_code.value,
        climate_zone       = climate_zone.value,
        num_bedrooms       = num_bedrooms.value,
        square_footage     = square_footage.value,
        year_built         = year_built.value,
        insulation_quality = insulation_quality.value,
        # Baseload formula
        baseload_constant_before = baseload_constant_before.value,
        baseload_constant_after  = baseload_constant_after.value,
        baseload_swap_year    = baseload_swap_year.value
                               if baseload_swap_planned.value else None,
        baseload_install_cost = baseload_install_cost.value,
        baseload_rebate       = baseload_rebate.value,
    )
```

---

### 12.7 HomeInfoBar Update

Add computed baseload to the info bar chip row:

```
📍 San Jose 95112  ·  3 bed  ·  1,800 sqft  ·  Built 1985  ·
  Average insulation  ·  Baseload ~1,910 kWh/yr
```

The baseload chip updates live when sqft, bedrooms, or constant slider changes.

---

### 12.8 Tests

Add to `tests/test_journey.py`:

```python
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

def test_baseload_efficiency_swap_reduces_cost():
    """After swap year, baseload cost drops to formula_after level."""
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
    # Year 1 cost (before swap) should exceed year 3 cost (after swap)
    baseload_yr1 = jh.cost_history_by_slot["Lights and Appliances"][0]
    baseload_yr3 = jh.cost_history_by_slot["Lights and Appliances"][2]
    assert baseload_yr3 < baseload_yr1, \
        "Post-swap baseload cost must be lower than pre-swap"

def test_baseline_home_always_uses_formula_before():
    """Do-nothing baseline never applies the efficiency upgrade."""
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
    # All years should use formula_before (no swap in baseline)
    costs = bh.cost_history_by_slot["Lights and Appliances"]
    # Costs should escalate monotonically (electricity rising, same kwh)
    assert all(costs[i] <= costs[i+1] for i in range(len(costs)-1)), \
        "Baseline baseload costs must rise monotonically (no efficiency drop)"

def test_hot_water_gallons_still_bedroom_based():
    """Hot water scaling uses bedroom lookup, not baseload formula."""
    from home_config import HOT_WATER_GAL_PER_DAY
    assert HOT_WATER_GAL_PER_DAY[3] == 65
    assert HOT_WATER_GAL_PER_DAY[1] == 30
    assert HOT_WATER_GAL_PER_DAY[5] == 85
```

---

### 12.9 Claude Code Prompt — Baseload Formula

```
Implement §12 (Baseload Formula + Efficiency Journey Slot) of docs/Phase2_Spec.md.
Apply in three steps — run pytest after each.

Step 1 — home_config.py:
  Remove BEDROOM_SCALING dict and baseload_multiplier entirely.
  Add compute_baseload_kwh(sq_ft, bedrooms, constant) function per §12.3.
  Add HOT_WATER_GAL_PER_DAY dict (bedroom → gallons, unchanged values).
  Add four new fields to HomeConfig dataclass per §12.3:
    baseload_constant_before = 500.0
    baseload_constant_after  = 300.0
    baseload_swap_year: int | None = None
    baseload_install_cost = 400.0
    baseload_rebate = 0.0
  Add tests from §12.8 (formula tests only) to tests/test_journey.py.
  Run pytest — all must pass.

Step 2 — model.py:
  Replace bedroom-scaling block with formula block per §12.4.
  Inject formula values into LightsAndPlugs device constructors
    for both baseline_devices and electric_device in the slot.
  Apply baseload_swap_year, install_cost, rebate from HomeConfig to the slot.
  Add remaining tests from §12.8 to tests/test_journey.py.
  Run pytest — all must pass.

Step 3 — app.py:
  Add new reactive state per §12.5:
    baseload_constant_before, baseload_constant_after,
    baseload_swap_planned, baseload_swap_year,
    baseload_install_cost, baseload_rebate
  Add baseload_kwh_before and baseload_kwh_after as computed values
    (call compute_baseload_kwh from home_config.py).
  Append the Baseload efficiency section to Journey Planner per §12.5:
    - Always-on constant slider (0–1500, default 500, C_NAVY accent)
    - Inline formula breakdown showing sqft × 0.45 + beds × 200 + constant
    - Computed total kWh displayed below slider, updates live
    - "Planning an efficiency upgrade" checkbox
    - When checked: reveal upgrade year slider, after-constant slider,
      install cost, rebate, net cost, annual saving, simple payback
  Update _build_home_config() per §12.6 to pass new fields.
  Update HomeInfoBar to show baseload kWh chip per §12.7.
  Run solara run src/app.py and verify:
    - Baseload section visible at bottom of Journey Planner
    - Total kWh updates live when sqft or bedrooms change
    - Efficiency upgrade checkbox reveals/hides the upgrade controls
    - With upgrade planned, journey home shows baseload cost drop at swap year
    - Baseline (do nothing) baseload costs rise monotonically
    - HomeInfoBar shows updated baseload chip
```

---

## 13. Appliance Detail Expand/Collapse + Slider Default Markers (Phase 2.5)

Surfaces all hidden assumptions by making each appliance row expandable.
No new simulation variables — existing reactive state is reorganised into
a cleaner expand/collapse UI. Slider default markers give advocates confidence
that they understand what has and hasn't been changed.

---

### 13.1 Design Overview

**Expand/collapse trigger:** Click anywhere on the top-level slot row to toggle.
A chevron `▶ / ▼` rotates to indicate state. Click again to collapse.

**Top row (always visible):**
```
▼ HVAC  |  Gas ▾  |  ☑ Plan swap  |  Yr 3 (2027)  |  $10,500 net
```

**Expanded panel — three sub-sections:**
1. **Estimated consumption** (first, always shown, read-only display)
2. **Current appliance specs** (sliders/inputs for existing device)
3. **Replacement appliance specs** (shown only when swap is planned)

**Collapse:** Click the row again. The chevron rotates back to `▶`.

---

### 13.2 Expand/Collapse Reactive State

One boolean reactive per slot. Stored in `_DEFAULTS` and reset by `reset_to_defaults()`:

```python
# Expand state per slot — False = collapsed (default)
hvac_expanded    = solara.reactive(False)
wh_expanded      = solara.reactive(False)
dryer_expanded   = solara.reactive(False)
cooktop_expanded = solara.reactive(False)
ev_expanded      = solara.reactive(False)
```

Add to `_DEFAULTS`:
```python
"hvac_expanded":    False,
"wh_expanded":      False,
"dryer_expanded":   False,
"cooktop_expanded": False,
"ev_expanded":      False,
```

Add to `reset_to_defaults()`:
```python
hvac_expanded.set(_DEFAULTS["hvac_expanded"])
wh_expanded.set(_DEFAULTS["wh_expanded"])
dryer_expanded.set(_DEFAULTS["dryer_expanded"])
cooktop_expanded.set(_DEFAULTS["cooktop_expanded"])
ev_expanded.set(_DEFAULTS["ev_expanded"])
```

---

### 13.3 Appliance Detail Panels — Per-Appliance Spec

Each panel has three sub-sections in fixed order:
1. Estimated consumption (read-only, always first)
2. Current appliance specs
3. Replacement appliance specs (conditional on swap planned)

**No new simulation variables are added.** All sliders in the detail panels
control existing reactives that already flow into `run_simulation()`.

---

#### 13.3.1 HVAC

**Estimated consumption (current device):**
```
Heating: ~286 therms/yr   (~8,380 kWh-eq)     [computed from GasFurnace formula]
Cooling: n/a (no central AC)                  [when hvac_has_cooling = False]
         ~291 kWh/yr cooling                  [when hvac_has_cooling = True, CentralAC]
```

**Current appliance specs:**
```
Type:        Gas Furnace
AFUE         [default tick: 0.80]   [=======●===] 0.80
Age (yrs)    [default tick: 10 ]   [====●=======] 10
[ ] Has central AC in baseline
    If checked:
    Central AC SEER  [default tick: 14]   [===●=======] 14
    AC age (yrs)     [default tick: 7 ]   [===●=======] 7
```

**Replacement appliance specs** (shown when `hvac_swap_planned = True`):
```
Type:        Heat Pump HVAC (replaces furnace + adds/replaces AC)
Heating COP  [default tick: 3.5]   [=====●=====] 3.5
Cooling SEER [default tick: 22 ]   [=======●===] 22
Install $    [14000]
Rebate $     [3500]
Net cost     $10,500

Estimated electric consumption:
Heating: ~1,930 kWh/yr
Cooling: ~185 kWh/yr
Total:   ~2,115 kWh/yr
```

**New reactives needed:**
```python
# HVAC current device age (currently hardcoded in slot JSON)
hvac_furnace_age  = solara.reactive(10)    # years, range 0-30
hvac_ac_seer      = solara.reactive(14)    # existing CentralAC SEER
hvac_ac_age       = solara.reactive(7)     # years
```
Add to `_DEFAULTS`: `"hvac_furnace_age": 10, "hvac_ac_seer": 14, "hvac_ac_age": 7`

---

#### 13.3.2 Water Heater

**Estimated consumption (current device):**
```
~184 therms/yr   (~5,390 kWh-eq)   [computed from GasWH formula, 65 gal/day]
```

**Current appliance specs:**
```
Type:           Gas Water Heater
UEF             [default tick: 0.65]  [=====●=====] 0.65
Age (yrs)       [default tick: 5   ]  [==●========] 5
Daily hot water [default tick: 65  ]  [======●====] 65 gal/day
                (default from bedroom count: 3 bed → 65 gal/day)
```

**Replacement appliance specs** (when `wh_swap_planned = True`):
```
Type:            Heat Pump Water Heater
UEF              [default tick: 3.5]  [========●==] 3.5
Install $        [2500]
Rebate $         [500]
Net cost         $2,000

Estimated electric consumption:
~1,050 kWh/yr
```

**New reactives needed:**
```python
wh_gas_age        = solara.reactive(5)     # years, range 0-20
hw_daily_gallons  = solara.reactive(65)    # gal/day, range 20-120
                                           # default auto-set from bedroom count
                                           # user can override
```
Add to `_DEFAULTS`: `"wh_gas_age": 5, "hw_daily_gallons": 65`

**Important:** `hw_daily_gallons` overrides the bedroom-lookup default when the
user has manually changed it. `_build_home_config()` passes it to `HomeConfig`;
`HESModel` uses it instead of the lookup when explicitly set.

`HomeConfig` gains one new field:
```python
hot_water_daily_gallons: int | None = None
# None = use bedroom lookup; int = user-specified override
```

**Auto-populate on bedroom change:**
When `num_bedrooms` reactive changes, if the user has NOT manually set
`hw_daily_gallons` (i.e. it still equals the bedroom-lookup default for the
*previous* bedroom count), update it to the new bedroom-lookup default.
If the user *has* manually changed it, leave it alone.

Implement with a simple flag:
```python
hw_gallons_user_override = solara.reactive(False)
# Set True when user moves the gallons slider
# Reset to False when reset_to_defaults() is called
```

---

#### 13.3.3 Dryer

**Estimated consumption (current device):**
```
~57 therms/yr  (~1,670 kWh-eq)   [GasDryer, 0.22 therms/cycle × 5 loads/wk]
```

**Current appliance specs:**
```
Type:           Gas Dryer
Therms/cycle    [default tick: 0.22]   [=====●=====] 0.22
Loads/week      [default tick: 5   ]   [====●======] 5
```

**Replacement appliance specs** (when `dryer_swap_planned = True`):
```
Type:           Heat Pump Dryer
kWh/cycle       [default tick: 1.8]   [======●====] 1.8
Loads/week      [default tick: 5  ]   [====●======] 5
Install $       [1200]
Rebate $        [0]
Net cost        $1,200

Estimated electric consumption:
~468 kWh/yr
```

**New reactives needed:**
```python
dryer_gas_therms_per_cycle = solara.reactive(0.22)   # range 0.15-0.35
dryer_loads_per_week       = solara.reactive(5)       # range 1-14
dryer_hp_kwh_per_cycle     = solara.reactive(1.8)     # range 1.2-2.5
```
Add to `_DEFAULTS`.

---

#### 13.3.4 Cooktop

**Estimated consumption (current device):**
```
~36 therms/yr  (~1,055 kWh-eq)   [GasCooktop, 0.05 therms/meal × 14 meals/wk]
```

**Current appliance specs:**
```
Type:           Gas Cooktop
Therms/meal     [default tick: 0.05]   [=====●=====] 0.05
Meals/week      [default tick: 14  ]   [=======●===] 14
```

**Replacement appliance specs** (when `cooktop_swap_planned = True`):
```
Type:           Induction Cooktop
kWh/meal        [default tick: 0.9]   [=======●===] 0.9
Meals/week      [default tick: 14 ]   [=======●===] 14
Install $       [1500]
Rebate $        [0]
Net cost        $1,500

Estimated electric consumption:
~655 kWh/yr
```

**New reactives needed:**
```python
cooktop_gas_therms_per_meal   = solara.reactive(0.05)   # range 0.03-0.10
cooktop_meals_per_week        = solara.reactive(14)      # range 3-21
cooktop_induction_kwh_per_meal = solara.reactive(0.9)   # range 0.6-1.4
```
Add to `_DEFAULTS`.

---

#### 13.3.5 EV Charger

**Estimated consumption (current device):**
```
~3,540 kWh/yr   [ScheduleDevice flat default: 295 kWh/month]
                (starting_state = "none" — absent from baseline)
```

**Current appliance specs:**
```
Type:           None (not in baseline)
                [only visible when starting_state = "none"]
```

**Replacement appliance specs** (when `ev_swap_planned = True`):
```
Type:           L2 EV Charger
Monthly kWh     [default tick: 295]   [=======●===] 295 kWh/month
                (annual: ~3,540 kWh/yr)
Install $       [800]
Rebate $        [0]
Net cost        $800

Estimated annual consumption:
~3,540 kWh/yr
```

**New reactive needed:**
```python
ev_monthly_kwh = solara.reactive(295)   # kWh/month, range 50-600
```
Add to `_DEFAULTS`: `"ev_monthly_kwh": 295`

---

### 13.4 Estimated Consumption Display Helper

Each expanded panel computes estimated consumption live from current slider values.
This is a display-only calculation — does NOT run the simulation. Uses the same
formulas as the physics devices but evaluated inline in Python:

```python
def _est_gas_furnace(afue: float, ua: int, annual_hdd: int = 1910) -> float:
    """Estimated therms/yr from GasFurnace formula."""
    return annual_hdd * 24 * ua / (afue * 100_000)

def _est_hp_hvac_heating(cop: float, ua: int, annual_hdd: int = 1910) -> float:
    """Estimated kWh/yr heating from HeatPumpHVAC formula."""
    return annual_hdd * 24 * ua / (cop * 3412)

def _est_hp_hvac_cooling(seer: float, ua: int, annual_cdd: int = 340) -> float:
    """Estimated kWh/yr cooling from HeatPumpHVAC formula."""
    return annual_cdd * 24 * ua / (seer * 1000)

def _est_gas_wh(uef: float, daily_gal: int,
               avg_inlet_f: float = 60.0, setpoint_f: float = 120.0) -> float:
    """Estimated therms/yr from GasWH formula."""
    delta_t = setpoint_f - avg_inlet_f
    return daily_gal * 365 * 8.33 * delta_t * 0.00001 / uef

def _est_hpwh(uef: float, daily_gal: int,
             avg_inlet_f: float = 60.0, setpoint_f: float = 120.0) -> float:
    """Estimated kWh/yr from HPWH formula."""
    delta_t = setpoint_f - avg_inlet_f
    return daily_gal * 365 * 8.33 * delta_t * 0.000293 / uef

def _est_gas_dryer(therms_per_cycle: float, loads_per_week: int) -> float:
    return therms_per_cycle * loads_per_week * 52

def _est_hp_dryer(kwh_per_cycle: float, loads_per_week: int) -> float:
    return kwh_per_cycle * loads_per_week * 52

def _est_gas_cooktop(therms_per_meal: float, meals_per_week: int) -> float:
    return therms_per_meal * meals_per_week * 52

def _est_induction(kwh_per_meal: float, meals_per_week: int) -> float:
    return kwh_per_meal * meals_per_week * 52

KWH_PER_THERM = 29.3

def _kwh_eq(therms: float) -> float:
    return therms * KWH_PER_THERM
```

UA value resolved from `insulation_quality.value` via:
```python
UA_MAP = {"poor": 650, "average": 500, "good": 350}
ua = UA_MAP[insulation_quality.value]
```

These functions are called inline inside the expanded panel component and their
results displayed as read-only markdown. They do not affect the simulation.

---

### 13.5 Slider Default Markers — Style A

**Style A:** Always show a small tick mark on the slider track at the default position,
visible even when the slider is at default. When the slider has been moved from default,
also show a delta label beneath the slider.

**Implementation in Solara:** Solara's `SliderFloat` / `SliderInt` does not natively
support track markers. Implement using a wrapper component `SliderWithDefault`:

```python
@solara.component
def SliderWithDefault(
    label: str,
    value: solara.Reactive,
    default: float | int,
    min: float | int,
    max: float | int,
    step: float | int = 1,
    unit: str = "",
    fmt: str = "{v}",   # format string for value display
):
    """
    Slider with:
    - Default tick mark on the track (HTML datalist via unsafe_innerHTML)
    - Delta label below when value != default
    - Current value shown in the label
    """
    v = value.value
    at_default = abs(v - default) < (step * 0.01)   # float-safe equality
    delta = v - default

    # Tick position as percentage of range
    tick_pct = int(100 * (default - min) / (max - min)) if max != min else 50

    # Slider label with current value
    display_label = f"{label}: {fmt.format(v=v)}{unit}"

    with solara.Column(gap="0px"):
        # The slider itself
        solara.SliderFloat(
            display_label, value=value, min=min, max=max, step=step
        ) if isinstance(default, float) else solara.SliderInt(
            display_label, value=value, min=min, max=max, step=int(step)
        )

        # Default tick mark — CSS overlay on the track
        solara.HTML(
            tag="div",
            unsafe_innerHTML=(
                f"<div style='"
                f"  position:relative; height:6px; margin:-4px 0 2px 0;"
                f"  pointer-events:none;'"
                f">"
                f"  <div style='"
                f"    position:absolute;"
                f"    left:{tick_pct}%;"
                f"    top:0; bottom:0;"
                f"    width:2px;"
                f"    background:#0D47A1;"
                f"    opacity:0.5;"
                f"    border-radius:1px;"
                f"  '></div>"
                f"  <div style='"
                f"    position:absolute;"
                f"    left:{tick_pct}%;"
                f"    top:50%;"
                f"    transform:translate(-50%, -50%);"
                f"    width:6px; height:6px;"
                f"    background:#0D47A1;"
                f"    opacity:0.5;"
                f"    border-radius:50%;"
                f"  '></div>"
                f"</div>"
            ),
        )

        # Delta label — only shown when not at default
        if not at_default:
            sign = "+" if delta > 0 else ""
            delta_str = f"{fmt.format(v=delta)}{unit}"
            color = "#D0302D" if delta < 0 else "#2E7D32"
            solara.HTML(
                tag="div",
                unsafe_innerHTML=(
                    f"<div style='font-size:0.75em; color:{color}; "
                    f"margin-top:1px; padding-left:2px;'>"
                    f"{sign}{delta_str} from default ({fmt.format(v=default)}{unit})"
                    f"</div>"
                ),
            )
```

**Usage example (HVAC AFUE slider):**
```python
SliderWithDefault(
    label="Furnace AFUE",
    value=furnace_afue,
    default=_DEFAULTS["furnace_afue"],    # 0.80
    min=0.70, max=0.95, step=0.01,
    fmt="{v:.2f}",
)
```

**Apply `SliderWithDefault` to all device spec sliders:**

| Slider | Default | Min | Max | Step | Unit |
|--------|---------|-----|-----|------|------|
| Furnace AFUE | 0.80 | 0.70 | 0.95 | 0.01 | |
| Furnace age | 10 | 0 | 30 | 1 | yrs |
| Central AC SEER | 14 | 10 | 22 | 1 | |
| Central AC age | 7 | 0 | 20 | 1 | yrs |
| Gas WH UEF | 0.65 | 0.55 | 0.70 | 0.01 | |
| Gas WH age | 5 | 0 | 20 | 1 | yrs |
| Daily hot water | 65 | 20 | 120 | 5 | gal/day |
| HP COP | 3.5 | 2.5 | 4.5 | 0.1 | |
| HP SEER | 22 | 16 | 28 | 1 | |
| HPWH UEF | 3.5 | 2.5 | 4.0 | 0.1 | |
| Gas dryer therms/cycle | 0.22 | 0.15 | 0.35 | 0.01 | |
| Dryer loads/week | 5 | 1 | 14 | 1 | /wk |
| HP dryer kWh/cycle | 1.8 | 1.2 | 2.5 | 0.1 | |
| Cooktop therms/meal | 0.05 | 0.03 | 0.10 | 0.01 | |
| Cooktop meals/week | 14 | 3 | 21 | 1 | /wk |
| Induction kWh/meal | 0.9 | 0.6 | 1.4 | 0.1 | |
| EV monthly kWh | 295 | 50 | 600 | 5 | kWh/mo |
| Gas esc %/yr | 8 | 0 | 20 | 1 | %/yr |
| Elec esc %/yr | 7 | 0 | 15 | 1 | %/yr |
| Baseload constant before | 500 | 0 | 1500 | 50 | kWh/yr |
| Baseload constant after | 300 | 0 | 1500 | 50 | kWh/yr |

**Sliders in the existing Home Profile panel** (insulation, sq ft, bedrooms) do NOT
need `SliderWithDefault` since they are not device physics parameters — they are
home profile facts unlikely to be mis-set.

---

### 13.6 Updated SlotRow Component

Replace the current `SlotRow` component with `ExpandableSlotRow` that supports
the click-to-expand pattern:

```python
@solara.component
def ExpandableSlotRow(
    name: str,
    state_rv, swap_planned_rv, swap_year_rv,
    install_cost_rv, rebate_rv,
    expanded_rv,
    detail_component,     # callable: detail_component() renders the expanded panel
):
    state   = state_rv.value
    planned = swap_planned_rv.value
    yr      = swap_year_rv.value
    net     = install_cost_rv.value - rebate_rv.value
    cal_yr  = sim_start_year.value + yr - 1
    expanded = expanded_rv.value

    chevron = "▼" if expanded else "▶"
    show_swap = (state in ("gas", "none")) and planned

    # ── Top row — clickable ──────────────────────────────────────────────
    with solara.Row(
        gap="8px",
        style=(
            "align-items:center; flex-wrap:wrap; padding:6px 0;"
            " border-bottom:1px solid #EEEEEE; cursor:pointer;"
        ),
        on_click=lambda: expanded_rv.set(not expanded),
    ):
        solara.Text(chevron, style="color:#78909C; font-size:0.9em; flex-shrink:0")

        with solara.Column(style="min-width:100px; max-width:100px"):
            solara.Text(name, style="font-weight:500; font-size:0.9em")

        with solara.Column(style="min-width:90px; max-width:90px"):
            solara.Select("", value=state_rv, values=["gas", "electric", "none"])

        with solara.Column(style="min-width:60px; max-width:60px"):
            if state != "electric":
                solara.Checkbox(label="Plan", value=swap_planned_rv)

        if show_swap:
            with solara.Column(style="min-width:160px"):
                solara.SliderInt(
                    f"Yr {yr} ({cal_yr})",
                    value=swap_year_rv, min=1, max=25,
                )
            with solara.Column(style="min-width:90px"):
                solara.InputInt("Install $", value=install_cost_rv)
            with solara.Column(style="min-width:70px"):
                solara.InputInt("Rebate", value=rebate_rv)
            with solara.Column(style="min-width:65px"):
                solara.Text(
                    f"Net ${net:,}",
                    style="color:#1976D2; font-weight:600; font-size:0.85em",
                )
        elif state == "electric":
            solara.Text("✓ Done", style="color:#2E7D32; font-weight:600; font-size:0.85em")
        else:
            solara.Text("—", style="color:#BBBBBB; font-size:1.2em")

    # ── Expanded detail panel ────────────────────────────────────────────
    if expanded:
        with solara.Column(
            style=(
                "margin:0 0 8px 24px; padding:10px 14px;"
                " background:#F8F9FA; border-radius:8px;"
                " border-left:3px solid #C5CAE9;"
            )
        ):
            detail_component()
```

---

### 13.7 Per-Appliance Detail Components

Each appliance gets a dedicated detail component function. Pattern is identical:
1. Estimated consumption section (read-only)
2. Current device section (sliders)
3. Replacement section (conditional, sliders + cost)

```python
@solara.component
def HVACDetail():
    ua = UA_MAP[insulation_quality.value]
    is_gas = hvac_starting_state.value == "gas"

    # ── 1. Estimated consumption ─────────────────────────────────────────
    solara.Markdown("**Estimated consumption**")
    if is_gas:
        therms = _est_gas_furnace(furnace_afue.value, ua)
        solara.Markdown(
            f"|  | Current (gas) |\n|--|--|\n"
            f"| Heating | {therms:.0f} therms/yr  (~{_kwh_eq(therms):,.0f} kWh-eq) |\n"
            + (f"| Cooling (AC) | ~{_est_hp_hvac_cooling(hvac_ac_seer.value, ua):.0f} kWh/yr |\n"
               if hvac_has_cooling.value else "")
        )
    else:  # electric
        heat_kwh = _est_hp_hvac_heating(hp_cop_heating.value, ua)
        cool_kwh = _est_hp_hvac_cooling(hp_seer_cooling.value, ua)
        solara.Markdown(
            f"|  | Current (electric) |\n|--|--|\n"
            f"| Heating | {heat_kwh:.0f} kWh/yr |\n"
            f"| Cooling | {cool_kwh:.0f} kWh/yr |\n"
            f"| Total   | {heat_kwh + cool_kwh:.0f} kWh/yr |\n"
        )

    solara.Markdown("---")

    # ── 2. Current device specs ──────────────────────────────────────────
    if is_gas:
        solara.Markdown("**Current: Gas Furnace**")
        SliderWithDefault(
            "Furnace AFUE", furnace_afue,
            _DEFAULTS["furnace_afue"], 0.70, 0.95, 0.01
        )
        SliderWithDefault(
            "Furnace age", hvac_furnace_age,
            _DEFAULTS["hvac_furnace_age"], 0, 30, 1, unit=" yrs"
        )
        solara.Checkbox(
            label="Has central AC in baseline",
            value=hvac_has_cooling,
        )
        if hvac_has_cooling.value:
            SliderWithDefault(
                "Central AC SEER", hvac_ac_seer,
                _DEFAULTS["hvac_ac_seer"], 10, 22, 1
            )
            SliderWithDefault(
                "Central AC age", hvac_ac_age,
                _DEFAULTS["hvac_ac_age"], 0, 20, 1, unit=" yrs"
            )
    else:
        solara.Markdown("**Current: Heat Pump HVAC**")
        SliderWithDefault(
            "Heating COP", hp_cop_heating,
            _DEFAULTS["hp_cop_heating"], 2.5, 4.5, 0.1
        )
        SliderWithDefault(
            "Cooling SEER", hp_seer_cooling,
            _DEFAULTS["hp_seer_cooling"], 16, 28, 1
        )

    # ── 3. Replacement specs ─────────────────────────────────────────────
    if hvac_swap_planned.value and hvac_starting_state.value == "gas":
        solara.Markdown("---")
        solara.Markdown("**Replacement: Heat Pump HVAC**")
        heat_kwh = _est_hp_hvac_heating(hp_cop_heating.value, ua)
        cool_kwh = _est_hp_hvac_cooling(hp_seer_cooling.value, ua)
        solara.Markdown(
            f"Est. consumption: {heat_kwh:.0f} kWh/yr heating + "
            f"{cool_kwh:.0f} kWh/yr cooling = **{heat_kwh + cool_kwh:.0f} kWh/yr total**"
        )
        SliderWithDefault(
            "Heating COP", hp_cop_heating,
            _DEFAULTS["hp_cop_heating"], 2.5, 4.5, 0.1
        )
        SliderWithDefault(
            "Cooling SEER", hp_seer_cooling,
            _DEFAULTS["hp_seer_cooling"], 16, 28, 1
        )
        solara.InputInt("Install cost $", value=hvac_install_cost)
        solara.InputInt("Rebate $",       value=hvac_rebate)
        solara.Text(
            f"Net cost: ${hvac_install_cost.value - hvac_rebate.value:,}",
            style="color:#1976D2; font-weight:600",
        )
```

Same pattern for `WaterHeaterDetail`, `DryerDetail`, `CooktopDetail`, `EVDetail`.
Each follows: consumption table → `---` → current specs → `---` → replacement specs.

---

### 13.8 Wiring into JourneyPlannerPanel

Replace existing `SlotRow` calls with `ExpandableSlotRow`:

```python
@solara.component
def JourneyPlannerPanel():
    with solara.Card("🗺️ Your Electrification Journey", margin=0, elevation=1):

        # Column headers
        with solara.Row(gap="8px",
                        style="padding:2px 0 4px 0; font-size:0.76em; color:#999"):
            solara.Text(" ",        style="min-width:16px")   # chevron column
            solara.Text("Appliance",  style="min-width:100px; font-weight:600")
            solara.Text("State",      style="min-width:90px")
            solara.Text("Plan swap?", style="min-width:60px")
            solara.Text("Year / Cost", style="flex:1")

        ExpandableSlotRow(
            "HVAC",
            hvac_starting_state, hvac_swap_planned,
            hvac_swap_year, hvac_install_cost, hvac_rebate,
            hvac_expanded,
            lambda: HVACDetail()
        )
        ExpandableSlotRow(
            "Water Heater",
            wh_starting_state, wh_swap_planned,
            wh_swap_year, wh_install_cost, wh_rebate,
            wh_expanded,
            lambda: WaterHeaterDetail()
        )
        ExpandableSlotRow(
            "Dryer",
            dryer_starting_state, dryer_swap_planned,
            dryer_swap_year, dryer_install_cost, dryer_rebate,
            dryer_expanded,
            lambda: DryerDetail()
        )
        ExpandableSlotRow(
            "Cooktop",
            cooktop_starting_state, cooktop_swap_planned,
            cooktop_swap_year, cooktop_install_cost, cooktop_rebate,
            cooktop_expanded,
            lambda: CooktopDetail()
        )
        ExpandableSlotRow(
            "EV Charger",
            ev_starting_state, ev_swap_planned,
            ev_swap_year, ev_install_cost, ev_rebate,
            ev_expanded,
            lambda: EVDetail()
        )

        # ... (baseload efficiency section unchanged)
```

**The existing Home Profile panel is simplified:** Remove the device spec sliders
(`furnace_afue`, `gas_wh_uef`, `hp_cop_heating`, `hp_seer_cooling`, `hpwh_uef`)
from the Home Profile card since they now live in the expanded detail panels.
Home Profile retains only: ZIP, climate zone, bedrooms, sq ft, year built, insulation.

---

### 13.9 Pass New Reactives into Simulation

`_build_slot_configs()` updated to use the new per-appliance reactives:

```python
def _build_slot_configs() -> list:
    has_ac = hvac_has_cooling.value
    hvac_baseline = [
        {"class": "GasFurnace",
         "afue": furnace_afue.value,
         "age": hvac_furnace_age.value}          # ← was hardcoded 10
    ]
    if has_ac:
        hvac_baseline.append({
            "class": "CentralAC",
            "seer_cooling": hvac_ac_seer.value,  # ← was hardcoded 14
            "age": hvac_ac_age.value,             # ← was hardcoded 7
            "installation_cost": 5000
        })
    return [
        {
            "name": "HVAC", ...
            "baseline_devices": hvac_baseline,
            "electric_device": {
                "class": "HeatPumpHVAC",
                "cop_heating":  hp_cop_heating.value,
                "seer_cooling": hp_seer_cooling.value,
            }, ...
        },
        {
            "name": "Water Heater", ...
            "baseline_devices": [{
                "class": "GasWaterHeater",
                "uef": gas_wh_uef.value,
                "age": wh_gas_age.value,           # ← was hardcoded 5
                "daily_gallons_override": (
                    hw_daily_gallons.value
                    if hw_gallons_user_override.value else None
                ),
            }], ...
        },
        {
            "name": "Dryer", ...
            "baseline_devices": [{
                "class": "GasDryer",
                "therms_per_cycle": dryer_gas_therms_per_cycle.value,
                "cycles_per_week":  dryer_loads_per_week.value,
            }],
            "electric_device": {
                "class": "HeatPumpDryer",
                "kwh_per_cycle":   dryer_hp_kwh_per_cycle.value,
                "cycles_per_week": dryer_loads_per_week.value,
            }, ...
        },
        {
            "name": "Cooktop", ...
            "baseline_devices": [{
                "class": "GasCooktop",
                "therms_per_meal": cooktop_gas_therms_per_meal.value,
                "meals_per_week":  cooktop_meals_per_week.value,
            }],
            "electric_device": {
                "class": "InductionCooktop",
                "kwh_per_meal":  cooktop_induction_kwh_per_meal.value,
                "meals_per_week": cooktop_meals_per_week.value,
            }, ...
        },
        {
            "name": "EV Charger", ...
            "electric_device": {
                "class": "EVCharger",
                "monthly_kwh_override": ev_monthly_kwh.value,  # ← overrides default
            }, ...
        },
        # Lights and Appliances slot unchanged
    ]
```

---

### 13.10 Tests

Add to `tests/test_journey.py`:

```python
def test_slot_uses_configured_furnace_afue():
    """Changing AFUE in slot config changes furnace consumption."""
    model_80 = HESModel(slot_configs=_slots_with("GasFurnace", afue=0.80))
    model_95 = HESModel(slot_configs=_slots_with("GasFurnace", afue=0.95))
    model_80.run_all()
    model_95.run_all()
    # Higher AFUE = more efficient = lower gas consumption
    hvac_therms_80 = model_80.baseline_home.consumption_history_by_slot["HVAC"][0]
    hvac_therms_95 = model_95.baseline_home.consumption_history_by_slot["HVAC"][0]
    assert hvac_therms_95 < hvac_therms_80

def test_slot_uses_configured_dryer_loads():
    """Dryer loads/week drives annual therms proportionally."""
    model_5  = HESModel(slot_configs=_slots_with("GasDryer", cycles_per_week=5))
    model_10 = HESModel(slot_configs=_slots_with("GasDryer", cycles_per_week=10))
    model_5.run_all()
    model_10.run_all()
    dryer_5  = model_5.baseline_home.consumption_history_by_slot["Dryer"][0]
    dryer_10 = model_10.baseline_home.consumption_history_by_slot["Dryer"][0]
    assert abs(dryer_10 / dryer_5 - 2.0) < 0.05   # should be exactly 2×

def test_hot_water_gallons_override():
    """daily_gallons_override in slot config overrides bedroom default."""
    model_65  = HESModel(slot_configs=_slots_with("GasWaterHeater", daily_gallons_override=65))
    model_100 = HESModel(slot_configs=_slots_with("GasWaterHeater", daily_gallons_override=100))
    model_65.run_all()
    model_100.run_all()
    wh_65  = model_65.baseline_home.consumption_history_by_slot["Water Heater"][0]
    wh_100 = model_100.baseline_home.consumption_history_by_slot["Water Heater"][0]
    assert wh_100 > wh_65
```

---

### 13.11 Claude Code Prompt — Appliance Detail Panels

```
Implement §13 (Appliance Detail Expand/Collapse + Slider Default Markers)
of docs/Phase2_Spec.md.
Apply in three steps.

Step 1 — New reactive state + _build_slot_configs() updates:
  Add these new reactives to app.py (see §13.2 and §13.3):
    hvac_expanded, wh_expanded, dryer_expanded, cooktop_expanded, ev_expanded
    hvac_furnace_age, hvac_ac_seer, hvac_ac_age
    wh_gas_age, hw_daily_gallons, hw_gallons_user_override
    dryer_gas_therms_per_cycle, dryer_loads_per_week, dryer_hp_kwh_per_cycle
    cooktop_gas_therms_per_meal, cooktop_meals_per_week, cooktop_induction_kwh_per_meal
    ev_monthly_kwh
  Add all new reactives to _DEFAULTS and reset_to_defaults().
  Update _build_slot_configs() per §13.9 to use new reactives.
  Update HomeConfig to add hot_water_daily_gallons: int | None = None.
  Run pytest — all existing tests must still pass.

Step 2 — SliderWithDefault component + estimation helpers:
  Add _est_* helper functions per §13.4 (display-only, no simulation).
  Add SliderWithDefault component per §13.5.
  Add UA_MAP = {"poor": 650, "average": 500, "good": 350} to app.py constants.
  Do not change any simulation code.

Step 3 — ExpandableSlotRow + detail components:
  Add ExpandableSlotRow component per §13.6.
  Add HVACDetail, WaterHeaterDetail, DryerDetail, CooktopDetail, EVDetail
  components per §13.7 pattern:
    - First item: estimated consumption table (read-only)
    - Second item: current device specs (SliderWithDefault)
    - Third item: replacement specs (conditional, SliderWithDefault + costs)
  Replace SlotRow calls in JourneyPlannerPanel with ExpandableSlotRow per §13.8.
  Remove device spec sliders from HomeProfilePanel
    (furnace_afue, gas_wh_uef, hp_cop, hp_seer, hpwh_uef now live in detail panels).
  HomeProfilePanel retains: ZIP, climate zone, bedrooms, sq ft, year built, insulation.
  Add tests from §13.10.
  Run solara run src/app.py and verify:
    - Clicking a row expands the detail panel; clicking again collapses it
    - Chevron rotates correctly
    - Estimated consumption shows as first item in every expanded panel
    - SliderWithDefault shows default tick mark on all device spec sliders
    - Delta label appears (green/red) when slider moves from default
    - Delta label disappears when slider returns to default
    - Current specs section: sliders match starting_state (gas shows furnace,
      electric shows heat pump)
    - Replacement section hidden when swap not planned; shown when planned
    - Changing AFUE slider updates simulation results in real time
    - Changing loads/week on dryer changes cost charts in real time
    - HomeProfilePanel no longer shows device spec sliders
```

---

## 14. EV Charger Physics Model (Phase 2.7)

Replaces the flat `ScheduleDevice` monthly default with a physics-grounded formula
driven by annual miles and vehicle efficiency. Surfaces all assumptions as sliders
with default markers (§13.5 pattern).

---

### 14.1 Formula

```
annual_kWh = miles_per_year × kwh_per_mile / charging_efficiency
```

| Parameter | Symbol | Default | Range | Markers |
|-----------|--------|---------|-------|---------|
| Annual miles driven | `miles_per_year` | 7,000 | 1,000–30,000 | — (continuous) |
| Vehicle efficiency | `kwh_per_mile` | 0.30 | 0.23–0.45 | Low=0.23, Mid=0.30, High=0.45 |
| Charging efficiency | `charging_efficiency` | 0.90 | 0.80–0.98 | fixed default tick only |

**Vehicle efficiency marker labels:**
- `0.23 kWh/mile` — Efficient EV (e.g. Tesla Model 3, Chevy Bolt)
- `0.30 kWh/mile` — Average EV (e.g. Tesla Model Y, Hyundai Ioniq 5)
- `0.45 kWh/mile` — Larger/older EV (e.g. Rivian R1T, older Leaf)

**Validation at defaults (7,000 miles, 0.30 kWh/mi, 0.90 efficiency):**
```
annual_kWh = 7,000 × 0.30 / 0.90 = 2,333 kWh/yr
```
Compare to old flat default: 3,540 kWh/yr. The physics model is lower because
7,000 miles is a moderate California driver; the old default assumed ~10 sessions/night
which implied much higher mileage.

---

### 14.2 Device Changes

**`EVCharger` upgrades from `ScheduleDevice` to a new `PhysicsEVCharger` subclass
that generates its own 12-element monthly array from the formula:**

```python
class PhysicsEVCharger(ElectricalConsumer):
    """
    EV charger with physics-based annual consumption.
    Monthly profile: flat with slight summer uptick (more driving May-Sep).
    """
    SEASONALITY = np.array(
        [0.94, 0.88, 0.94, 0.91, 0.97, 1.00, 1.03, 1.03, 0.97, 0.94, 0.91, 0.94],
        dtype=float
    )  # sums to 12.0 — multiply by annual/12 to get monthly

    def __init__(self, ...,
                 miles_per_year: int = 7000,
                 kwh_per_mile: float = 0.30,
                 charging_efficiency: float = 0.90):
        self.miles_per_year        = miles_per_year
        self.kwh_per_mile          = kwh_per_mile
        self.charging_efficiency   = charging_efficiency

    @property
    def annual_kwh(self) -> float:
        return self.miles_per_year * self.kwh_per_mile / self.charging_efficiency

    def monthly_consumption(self) -> np.ndarray:
        monthly_base = self.annual_kwh / 12
        return monthly_base * self.SEASONALITY
```

**Backward compatibility:** `EVCharger(ScheduleDevice)` is retained for any code
that supplies a `monthly_values` list directly. `PhysicsEVCharger` is the new default
for the UI. The `journey_slots_default.json` is updated to use `PhysicsEVCharger`.

---

### 14.3 UI — EV Charger Detail Panel

Replaces the `monthly_kwh` slider in §13.3.5 with the physics parameters.
Same `ExpandableSlotRow` pattern — only the `EVDetail` component changes.

**Estimated consumption (first, read-only):**
```
Est. annual consumption: ~2,333 kWh/yr
(7,000 miles × 0.30 kWh/mi ÷ 0.90 charging eff.)
```

**Replacement appliance specs (when `ev_swap_planned = True`):**
```
Type:                L2 EV Charger

Annual miles         [──────●────────────] 7,000 mi/yr

Vehicle efficiency   [────────●──────] 0.30 kWh/mi
                     ● Efficient (0.23)  ● Average (0.30)  ● Large (0.45)
                     [preset buttons — populate slider; user can fine-tune]

Charging efficiency  [──────────●────] 0.90

Est. consumption:    ~2,333 kWh/yr  (updates live)

Install $            [800]
Rebate $             [0]
Net cost             $800
```

**New reactives (replace `ev_monthly_kwh`):**
```python
ev_miles_per_year       = solara.reactive(7000)   # range 1000-30000, step 500
ev_kwh_per_mile         = solara.reactive(0.30)   # range 0.23-0.45, step 0.01
ev_charging_efficiency  = solara.reactive(0.90)   # range 0.80-0.98, step 0.01
```
Add to `_DEFAULTS`. Remove `ev_monthly_kwh` from `_DEFAULTS` and `reset_to_defaults()`.

**Efficiency preset buttons:**
```python
def _apply_ev_efficiency_preset(label: str):
    presets = {"Efficient": 0.23, "Average": 0.30, "Large": 0.45}
    ev_kwh_per_mile.set(presets[label])
```

**Estimation helper:**
```python
def _est_ev_kwh(miles: int, kwh_per_mile: float,
               charging_eff: float = 0.90) -> float:
    return miles * kwh_per_mile / charging_eff
```

**`_build_slot_configs()` update:**
```python
{
    "name": "EV Charger",
    "electric_device": {
        "class": "PhysicsEVCharger",
        "miles_per_year":       ev_miles_per_year.value,
        "kwh_per_mile":         ev_kwh_per_mile.value,
        "charging_efficiency":  ev_charging_efficiency.value,
    }, ...
}
```

---

### 14.4 Tests

Add to `tests/test_devices.py`:

```python
def test_physics_ev_charger_formula():
    """Annual kWh = miles × kWh/mile / efficiency."""
    ev = PhysicsEVCharger(miles_per_year=7000, kwh_per_mile=0.30,
                          charging_efficiency=0.90)
    expected = 7000 * 0.30 / 0.90   # = 2333.3
    assert abs(ev.annual_consumption() - expected) < 1.0

def test_physics_ev_charger_monthly_shape():
    ev = PhysicsEVCharger(miles_per_year=7000, kwh_per_mile=0.30,
                          charging_efficiency=0.90)
    monthly = ev.monthly_consumption()
    assert monthly.shape == (12,)
    assert abs(monthly.sum() - ev.annual_consumption()) < 0.1   # sums to annual

def test_physics_ev_charger_higher_miles_higher_kwh():
    ev_low  = PhysicsEVCharger(miles_per_year=5000,  kwh_per_mile=0.30)
    ev_high = PhysicsEVCharger(miles_per_year=15000, kwh_per_mile=0.30)
    assert ev_high.annual_consumption() > ev_low.annual_consumption()

def test_physics_ev_charger_efficient_vehicle_lower_kwh():
    ev_efficient = PhysicsEVCharger(miles_per_year=7000, kwh_per_mile=0.23)
    ev_large     = PhysicsEVCharger(miles_per_year=7000, kwh_per_mile=0.45)
    assert ev_efficient.annual_consumption() < ev_large.annual_consumption()
```

---

### 14.5 Claude Code Prompt — EV Charger Physics

```
Implement §14 (EV Charger Physics Model) of docs/Phase2_Spec.md.

Step 1 — src/devices/schedule.py:
  Add PhysicsEVCharger class per §14.2.
  SEASONALITY constant = [0.94, 0.88, 0.94, 0.91, 0.97, 1.00,
                          1.03, 1.03, 0.97, 0.94, 0.91, 0.94]
  formula: annual_kwh = miles_per_year × kwh_per_mile / charging_efficiency
  monthly_consumption() = annual_kwh / 12 × SEASONALITY
  Add tests from §14.4 to tests/test_devices.py.
  Run pytest — all must pass.

Step 2 — app.py:
  Replace ev_monthly_kwh reactive with:
    ev_miles_per_year, ev_kwh_per_mile, ev_charging_efficiency
  Add _apply_ev_efficiency_preset() helper.
  Add _est_ev_kwh() estimation helper.
  Update EVDetail component per §14.3:
    - Estimated consumption line (formula inline, updates live)
    - Annual miles slider (1000-30000, step 500)
    - kWh/mile slider + Efficient/Average/Large preset buttons
    - Charging efficiency slider (0.80-0.98)
    - All use SliderWithDefault with default tick marks
  Update _build_slot_configs() to use PhysicsEVCharger with new params.
  Update _DEFAULTS and reset_to_defaults().
  Run solara run src/app.py and verify:
    - EV detail panel shows physics formula result
    - Preset buttons populate kWh/mile slider
    - Changing miles or efficiency updates estimated kWh live
    - Simulation results change when EV params change
```

---

## 15. Electrical Panel Upgrade (Phase 2.7)

Adds a standalone CapEx-only slot for electrical panel upgrades. No energy
consumption modelling — pure install cost amortised over 25 years.

---

### 15.1 Design

The panel upgrade is an optional checkbox item, not a default slot. Many Bay Area
homes already have 200A panels and don’t need an upgrade. When checked, it adds a
CapEx event in the simulation at the chosen year.

**No device consumption.** The panel upgrade slot has `baseline_device = None` and
`electric_device = None`. It contributes only to `capex_by_year` and the Journey
Timeline chart — never to opex.

**Implementation:** A new `CapExOnlySlot` dataclass (thin wrapper, no device stepping):

```python
@dataclass
class CapExOnlySlot:
    name: str
    category: str          = "Infrastructure"
    install_cost: float    = 3000.0
    rebate: float          = 0.0
    lifespan: int          = 25             # years — for end-of-life replacement calc
    install_year: int | None = None         # year of install; None = not planning

    @property
    def net_install_cost(self) -> float:
        return self.install_cost - self.rebate

    def step(self, current_year: int, **_):
        """
        Logs CapEx at install_year. No consumption, no opex.
        End-of-life replacement logged at install_year + lifespan (if within horizon).
        """
        if current_year == self.install_year:
            self.capex_events.append((current_year, self.net_install_cost))
        eol = (self.install_year or 0) + self.lifespan
        if current_year == eol:
            self.capex_events.append((current_year, self.install_cost))  # replacement at full cost
```

`JourneyHome` iterates `CapExOnlySlot` items separately after device slots —
they contribute to `capex_by_year` but not to `cost_history_by_category`.

**Baseline home:** Panel upgrade is absent from baseline home — this is a proactive
choice the homeowner makes as part of their journey, not something that happens in
the “do nothing” scenario.

---

### 15.2 UI — Panel Upgrade Section

Sits below the EV Charger row in the Journey Planner, above the Baseload Efficiency
divider. Styled as a compact optional row (no expand/collapse needed — few fields):

```
─────────────────────────────────────────────────────────────────
🔌 Electrical Panel Upgrade   (optional — not needed for all homes)

[ ] Planning a panel upgrade
    Install in year  [───●──────────] 1   (2026 — recommended before EV or HP install)
    Install cost $   [──────●───────] 3,000   (range $2,000–$10,000)
    Rebate $         [0        ]   (check local utility incentives)
    Net cost         $3,000
    Lifespan         25 years
─────────────────────────────────────────────────────────────────
```

**Note in UI:** “Often required when adding EV charger (L2) or heat pump to older
homes with 100A panels. Check with your electrician.”

**New reactives:**
```python
panel_upgrade_planned    = solara.reactive(False)
panel_upgrade_year       = solara.reactive(1)       # install in year 1 by default if planned
panel_upgrade_cost       = solara.reactive(3000)    # slider 2000-10000, step 500
panel_upgrade_rebate     = solara.reactive(0)
```
Add to `_DEFAULTS` and `reset_to_defaults()`.

**`_build_slot_configs()` update:**
```python
# Add CapExOnlySlot when panel upgrade is planned
if panel_upgrade_planned.value:
    capex_only_slots.append(CapExOnlySlot(
        name="Electrical Panel",
        install_cost=panel_upgrade_cost.value,
        rebate=panel_upgrade_rebate.value,
        lifespan=25,
        install_year=panel_upgrade_year.value,
    ))
```

---

### 15.3 Chart Integration

**Journey Timeline:** Panel upgrade appears as a vertical marker on the timeline,
styled differently from device swaps (uses a grey `⚡` marker, not a coloured device marker).

**Equipment Replacements (CapEx) chart:** Panel upgrade CapEx appears as a bar
in the journey home column at `install_year`. End-of-life replacement appears at
`install_year + 25` if within the simulation horizon.

**Cumulative cost chart:** Not directly shown — panel upgrade affects only the
capex bars, not the opex lines.

---

### 15.4 Tests

Add to `tests/test_journey.py`:

```python
def test_panel_upgrade_capex_at_install_year():
    """Panel upgrade CapEx fires at install_year, not before or after."""
    slot = CapExOnlySlot(name="Electrical Panel",
                         install_cost=3000, rebate=0,
                         lifespan=25, install_year=1)
    model = HESModel(n_years=10, capex_only_slots=[slot])
    model.run_all()
    assert model.journey_home.capex_by_year[1] >= 3000
    assert model.journey_home.capex_by_year[2] == 0

def test_panel_upgrade_absent_from_baseline():
    """Panel upgrade does not appear in baseline home CapEx."""
    slot = CapExOnlySlot(name="Electrical Panel",
                         install_cost=3000, install_year=1)
    model = HESModel(n_years=10, capex_only_slots=[slot])
    model.run_all()
    assert model.baseline_home.capex_by_year.get(1, 0) == 0

def test_panel_upgrade_eol_replacement():
    """End-of-life replacement fires at install_year + lifespan."""
    slot = CapExOnlySlot(name="Electrical Panel",
                         install_cost=3000, lifespan=5, install_year=1)
    model = HESModel(n_years=10, capex_only_slots=[slot])
    model.run_all()
    assert model.journey_home.capex_by_year.get(6, 0) >= 3000  # yr 1 + lifespan 5
```

---

### 15.5 Claude Code Prompt — Panel Upgrade

```
Implement §15 (Electrical Panel Upgrade) of docs/Phase2_Spec.md.

Step 1 — journey.py:
  Add CapExOnlySlot dataclass per §15.1.
  HESModel accepts optional capex_only_slots: list[CapExOnlySlot] = None.
  JourneyHome iterates capex_only_slots after device slots —
    logs CapEx events to capex_by_year only (no opex, no cost_history_by_category).
  Baseline home does NOT step CapExOnlySlots.
  Add tests from §15.4.
  Run pytest — all must pass.

Step 2 — app.py:
  Add panel_upgrade_planned, panel_upgrade_year,
    panel_upgrade_cost, panel_upgrade_rebate reactives.
  Add panel upgrade section to JourneyPlannerPanel per §15.2:
    - Checkbox to enable
    - When checked: year slider, cost slider (2000-10000, step 500,
      SliderWithDefault tick at 3000), rebate input, net cost display
    - Tooltip: "Often required when adding EV charger or heat pump"
  Update _build_slot_configs() to pass CapExOnlySlot when planned.
  Update Journey Timeline chart to show panel upgrade as grey marker.
  Update _DEFAULTS and reset_to_defaults().
  Run solara run src/app.py and verify:
    - Panel upgrade section visible below EV Charger row
    - Checkbox reveals/hides year and cost controls
    - CapEx chart shows panel upgrade bar at install year
    - Panel upgrade absent from baseline home CapEx
```

---

## 16. Baseload Efficiency — Promote to Full Journey Slot (Phase 2.7)

Moves the “Baseload efficiency” section from its current position below a divider
into the main Journey Planner table as a first-class slot row, identical in structure
to HVAC/WH/Dryer/Cooktop rows.

---

### 16.1 Change

**Before (Phase 2.5):** The baseload efficiency upgrade was a separate section below
a `───` divider, styled differently from the appliance rows above.

**After (Phase 2.7):** It becomes a standard `ExpandableSlotRow` in the Journey
Planner table:

```
▶ Lights & Appliances  |  Electric  |  [☐ Plan upgrade]  |  ———  |  —  |  —
```

When expanded:
```
▼ Lights & Appliances  |  Electric  |  [☑ Plan upgrade]  |  Yr 2  |  $400  |  $400

  Est. consumption (current):   1,910 kWh/yr
  (1,800 sqft × 0.45 + 3 bed × 200 + 500 always-on)
  ──────────────────────────────────────────
  Always-on load (before)  [───●──────────] 500 kWh/yr
  ──────────────────────────────────────────
  Upgrade: LED + smart plugs
  After-upgrade load       [──●───────────] 300 kWh/yr
  Est. consumption (after):   1,710 kWh/yr
  → Annual saving: ~200 kWh/yr ≈ $77/yr
  → Simple payback: ~5.2 yrs
  Install $400    Rebate $0    Net $400
```

**The `starting_state` is always `"electric"`** for this slot (both homes always
have electricity for lights). The “plan” checkbox triggers the upgrade — not a
fuel swap. The slot’s “plan swap” label in the column header should read
**“Plan upgrade?”** for this row specifically.

---

### 16.2 Implementation

**New `BaseloadDetail` component** following the §13.7 pattern:

```python
@solara.component
def BaseloadDetail():
    # 1. Estimated consumption (current)
    kwh_before = compute_baseload_kwh(
        square_footage.value, num_bedrooms.value, baseload_constant_before.value)
    solara.Markdown(
        f"**Estimated consumption (current)**\n\n"
        f"~{kwh_before:,.0f} kWh/yr  "
        f"({square_footage.value:,} sqft × 0.45 + {num_bedrooms.value} bed × 200 "
        f"+ {baseload_constant_before.value} always-on)"
    )
    solara.Markdown("---")

    # 2. Current: always-on constant slider
    solara.Markdown("**Current appliances**")
    SliderWithDefault(
        "Always-on load", baseload_constant_before,
        _DEFAULTS["baseload_constant_before"], 0, 1500, 50, unit=" kWh/yr"
    )

    # 3. Upgrade section (shown when planned)
    if baseload_swap_planned.value:
        solara.Markdown("---")
        solara.Markdown("**Upgrade: LED + smart plugs**")
        SliderWithDefault(
            "After-upgrade load", baseload_constant_after,
            _DEFAULTS["baseload_constant_after"], 0, 1500, 50, unit=" kWh/yr"
        )
        kwh_after = compute_baseload_kwh(
            square_footage.value, num_bedrooms.value, baseload_constant_after.value)
        annual_saving = kwh_before - kwh_after
        elec_rate = elec_cagr_pct_a.value / 100.0   # proxy for current rate
        saving_dollars = annual_saving * 0.386
        payback = (
            (baseload_install_cost.value - baseload_rebate.value) / saving_dollars
            if saving_dollars > 0 else float("inf")
        )
        solara.Markdown(
            f"Est. consumption (after): ~{kwh_after:,.0f} kWh/yr  "
            f"\u2192 Annual saving: ~{annual_saving:.0f} kWh/yr ≈ "
            f"${saving_dollars:.0f}/yr  "
            f"\u2192 Simple payback: ~{payback:.1f} yrs"
        )
        solara.InputInt("Install cost $", value=baseload_install_cost)
        solara.InputInt("Rebate $",       value=baseload_rebate)
        net = baseload_install_cost.value - baseload_rebate.value
        solara.Text(f"Net cost: ${net:,}", style="color:#1976D2; font-weight:600")
```

**Updated `JourneyPlannerPanel`** — add `BaseloadDetail` as the last `ExpandableSlotRow`
before the footer note. Remove the old divider + separate baseload section.

**Add `baseload_expanded` reactive:**
```python
baseload_expanded = solara.reactive(False)
```
Add to `_DEFAULTS` and `reset_to_defaults()`.

**Column header adjustment:** The “Plan swap?” column header can stay as-is —
the checkbox label within the `BaseloadDetail` row reads “Plan upgrade?” implicitly
through context.

---

### 16.3 Claude Code Prompt — Baseload Full Slot

```
Implement §16 (Baseload as Full Journey Slot) of docs/Phase2_Spec.md.

In app.py:
  Add baseload_expanded = solara.reactive(False) to reactive state.
  Add to _DEFAULTS and reset_to_defaults().
  Add BaseloadDetail component per §16.2.
  Replace the old divider + standalone baseload section in JourneyPlannerPanel
    with an ExpandableSlotRow for "Lights & Appliances":
      state_rv = a synthetic reactive that always shows "Electric"
      swap_planned_rv = baseload_swap_planned
      swap_year_rv = baseload_swap_year
      install_cost_rv = baseload_install_cost
      rebate_rv = baseload_rebate
      expanded_rv = baseload_expanded
      detail_component = lambda: BaseloadDetail()
  The top row should show:
    - "Electric" state (non-editable dropdown or static label)
    - "Plan upgrade?" checkbox = baseload_swap_planned
    - When planned: swap year slider + install cost + rebate + net
    - When not planned: "--" placeholder
  Run solara run src/app.py and verify:
    - Baseload row appears in the main table (not below a divider)
    - Click to expand shows estimation + slider + upgrade controls
    - Formula breakdown updates live with sqft/bedrooms changes
    - Remove old divider section — no duplicate baseload UI
```

---

## 17. Solar + Battery (Phase 2.7)

Adds a Solar + Battery section as a dedicated collapsible panel in the UI.
Phase 2.7 uses a simplified `% coverage` model: solar + battery offset a user-specified
percentage of total electric opex, modelled as a reduction in electricity costs.
Detailed physics (PVWatts, NEM3, hourly dispatch) deferred to Phase 3.

---

### 17.1 Design Philosophy

**What the % coverage model captures correctly:**
- CapEx and rebate (install cost, IRA tax credit, local incentives)
- Opex reduction (covered % of electricity is effectively $0 marginal cost)
- Payback story (net capex ÷ annual savings)
- Compounding benefit: as electric appliances are added to the journey, the solar
  savings grow proportionally (more electric load = more offset)

**What it deliberately simplifies:**
- Solar production is seasonal; battery sizing matters for nighttime loads
- NEM3 export value (~$0.05/kWh) is much lower than import rate ($0.386/kWh)
- A detailed Phase 3 model will feed a more accurate coverage % from PVWatts

**The `% coverage` slider is the interface between v2.7 and Phase 3** — Phase 3
replaces the slider with a computed value from the detailed model, while the
simulation engine below stays identical.

---

### 17.2 Simulation Model

**Solar reduces electricity opex proportionally:**

```python
# In JourneyHome.step(), after computing annual_opex:
if solar_coverage_pct > 0:
    # Reduce only the electric portion of opex
    elec_opex_this_year = sum(
        slot.elec_cost_this_step for slot in self.slots
    )
    solar_saving = elec_opex_this_year * (solar_coverage_pct / 100.0)
    self.annual_opex -= solar_saving
    self.solar_savings_history.append(solar_saving)
else:
    self.solar_savings_history.append(0.0)
```

**Solar CapEx** is logged at `solar_install_year` as a `CapExOnlySlot` (same mechanism
as the panel upgrade — no device stepping, pure CapEx).

**Applied to journey home only.** The “do nothing” baseline has no solar.

**Coverage escalation:** Solar coverage stays constant year-over-year in Phase 2.7
(panel degrades ~0.5%/yr, not modelled yet). Phase 3 adds degradation.

---

### 17.3 CapEx Items — Clickable Buttons

The Solar + Battery panel uses clickable buttons to add cost components. Each
button adds a line item with its own cost and rebate input. The user can add
multiple items; the total net cost is summed and passed as the solar CapEx.

**Default cost items (pre-populated, user can edit):**

| Button | Default gross cost | Notes |
|--------|-------------------|-------|
| Solar panels (10 kW) | $25,000 | ~3,000 kWh/yr per installed kW in Bay Area |
| Battery storage (13.5 kWh) | $12,000 | One Tesla Powerwall or equivalent |
| Installation & permitting | $3,000 | Electrical, permits, interconnection |

**Rebate items (pre-populated):**

| Button | Default rebate | Notes |
|--------|---------------|-------|
| IRA Federal Tax Credit (30%) | auto-calculated | 30% of gross solar cost |
| SVCE/MCE local rebate | $1,500 | Community choice aggregator incentive |
| SGIP battery rebate | $2,500 | CA Self-Generation Incentive Program |

**UI layout:**

```
☀️🔋 Solar + Battery

[ ] Adding solar + battery to my journey
    [when checked, reveals:]

    Install in year  [───●───────────] 1   (2026)

    % of electricity covered  [───────●───] 60 %
    (Phase 3 will compute this from system size + usage)

    ── Cost items ──────────────────────────────────────────────
    [ + Solar panels (10 kW) ]   $25,000
    [ + Battery storage ]         $12,000
    [ + Installation ]            $3,000
    ── Rebates ───────────────────────────────────────────────
    [ + IRA 30% credit ]         -$12,000  (auto: 30% of solar panels)
    [ + SVCE/MCE rebate ]         -$1,500
    [ + SGIP battery rebate ]     -$2,500
    ───────────────────────────────────────────────
    Gross cost:     $40,000
    Total rebates:  -$16,000
    Net cost:        $24,000    Lifespan: 25 years

    Est. annual saving: $1,004/yr
    (60% × ~$1,673 electric opex at current rates)
    Est. simple payback: ~23.9 yrs
    (Note: payback improves as electric rates rise over time)
```

**Button behaviour:** Each button is a toggle. Clicking adds the item (shows cost
and rebate inputs). Clicking again removes it. The IRA 30% credit is auto-calculated
when the solar panels item is present: `rebate = 0.30 × solar_panels_cost`.

---

### 17.4 Reactive State

```python
# Solar + Battery
solar_planned           = solara.reactive(False)
solar_install_year      = solara.reactive(1)
solar_coverage_pct      = solara.reactive(60)     # %, range 0-100, step 5

# Cost items (toggle booleans + editable amounts)
solar_include_panels    = solara.reactive(True)
solar_panels_cost       = solara.reactive(25000)
solar_include_battery   = solara.reactive(False)
solar_battery_cost      = solara.reactive(12000)
solar_include_install   = solara.reactive(True)
solar_install_cost_item = solara.reactive(3000)

# Rebate items
solar_include_ira       = solara.reactive(True)     # auto-calc: 30% of panels cost
solar_include_local     = solara.reactive(False)
solar_local_rebate      = solara.reactive(1500)
solar_include_sgip      = solara.reactive(False)
solar_sgip_rebate       = solara.reactive(2500)
```

Add all to `_DEFAULTS` and `reset_to_defaults()`.

**Derived computations (read-only, inline in UI):**
```python
# Gross cost
gross_cost = (
    (solar_panels_cost.value if solar_include_panels.value else 0)
    + (solar_battery_cost.value if solar_include_battery.value else 0)
    + (solar_install_cost_item.value if solar_include_install.value else 0)
)

# IRA credit auto-calc: 30% of panels cost
ira_credit = (
    int(0.30 * solar_panels_cost.value)
    if solar_include_ira.value and solar_include_panels.value else 0
)

# Total rebates
total_rebates = (
    ira_credit
    + (solar_local_rebate.value if solar_include_local.value else 0)
    + (solar_sgip_rebate.value if solar_include_sgip.value else 0)
)

net_solar_cost = gross_cost - total_rebates
```

---

### 17.5 `_build_slot_configs()` Update

```python
# Solar CapEx as a CapExOnlySlot
if solar_planned.value:
    capex_only_slots.append(CapExOnlySlot(
        name="Solar + Battery",
        category="Infrastructure",
        install_cost=gross_cost,
        rebate=total_rebates,
        lifespan=25,
        install_year=solar_install_year.value,
    ))

# Pass coverage pct to HESModel for opex reduction
solar_coverage = solar_coverage_pct.value if solar_planned.value else 0
```

**`HESModel.__init__` gains:**
```python
solar_coverage_pct: float = 0.0   # 0-100; reduces elec opex in JourneyHome only
```

---

### 17.6 Chart Integration

**Cumulative cost chart:** When solar is planned, add a third line:
- “Your journey + Solar” (solid teal `#00897B`) showing the further reduction
  from solar coverage
- “Your journey” (solid blue) remains visible for comparison

This gives advocates a three-line chart: Do nothing / Journey / Journey + Solar.

**Journey Timeline:** Solar appears as a ☀️ marker at `solar_install_year`.

**Equipment Replacements (CapEx):** Solar CapEx bar shown at `install_year`.

---

### 17.7 Tests

Add to `tests/test_journey.py`:

```python
def test_solar_reduces_elec_opex():
    """Solar coverage reduces journey home electric opex proportionally."""
    model_no_solar = HESModel(solar_coverage_pct=0,  n_years=5)
    model_solar    = HESModel(solar_coverage_pct=50, n_years=5)
    model_no_solar.run_all()
    model_solar.run_all()
    df_ns = model_no_solar.datacollector.get_model_vars_dataframe()
    df_s  = model_solar.datacollector.get_model_vars_dataframe()
    # Solar home should have lower cumulative journey cost
    assert df_s["Journey Cum Cost"].iloc[-1] < df_ns["Journey Cum Cost"].iloc[-1]

def test_solar_does_not_affect_baseline():
    """Solar coverage only affects journey home, not do-nothing baseline."""
    model = HESModel(solar_coverage_pct=80, n_years=5)
    model.run_all()
    df = model.datacollector.get_model_vars_dataframe()
    model_ns = HESModel(solar_coverage_pct=0, n_years=5)
    model_ns.run_all()
    df_ns = model_ns.datacollector.get_model_vars_dataframe()
    # Baseline costs must be identical with and without solar
    assert np.allclose(
        df["Baseline Cum Cost"].values,
        df_ns["Baseline Cum Cost"].values,
        rtol=0.001
    )

def test_solar_capex_at_install_year():
    """Solar CapEx fires at install_year in journey home."""
    solar_slot = CapExOnlySlot(
        name="Solar + Battery",
        install_cost=40000, rebate=16000, lifespan=25, install_year=1)
    model = HESModel(n_years=5, capex_only_slots=[solar_slot],
                     solar_coverage_pct=60)
    model.run_all()
    assert model.journey_home.capex_by_year[1] >= 24000  # net = 40k - 16k
```

---

### 17.8 Claude Code Prompt — Solar + Battery

```
Implement §17 (Solar + Battery) of docs/Phase2_Spec.md.

Step 1 — model.py + journey.py:
  Add solar_coverage_pct: float = 0.0 parameter to HESModel.__init__().
  Pass it to JourneyHome (not BaselineHome).
  In JourneyHome.step(), after computing annual_opex:
    elec_opex = sum of elec-fuel slot costs this step
    annual_opex -= elec_opex × (solar_coverage_pct / 100)
    append to solar_savings_history
  Add DataCollector reporter: "Solar Saving" per year.
  Add tests from §17.7.
  Run pytest — all must pass.

Step 2 — app.py:
  Add all solar reactives from §17.4.
  Add Solar + Battery collapsible section to the UI — place it after the
  Journey Planner card and before the Home Profile card:
    - [ ] Planning solar checkbox
    - When checked: install year slider, coverage % slider
    - Cost items: toggle buttons for panels, battery, install
      Each button adds an editable cost input when active
    - Rebate items: toggle buttons for IRA (auto-calc), local, SGIP
      Each button adds an editable rebate input when active
    - IRA credit = 30% × panels cost when both enabled (auto-computed)
    - Summary: gross cost, total rebates, net cost, est. annual saving, payback
  Update _build_slot_configs() per §17.5 to pass solar CapExOnlySlot.
  Update HESModel call to pass solar_coverage_pct.
  Update cumulative cost chart per §17.6:
    - Add third line "Journey + Solar" when solar_planned = True
    - Color: teal #00897B, solid line
  Update Journey Timeline to show solar marker.
  Update _DEFAULTS and reset_to_defaults().
  Run solara run src/app.py and verify:
    - Solar section visible as collapsible panel
    - Cost buttons toggle line items
    - IRA credit auto-computes from panels cost
    - Net cost and payback update live
    - Cumulative cost chart shows 3 lines when solar planned
    - Changing coverage % moves the "Journey + Solar" line
    - Baseline line is unaffected by solar
```


---

## 18. UI Polish — Phase 2.7

Cosmetic and layout improvements to sharpen the interface. No simulation logic changes.

---

### 18.1 Chart Panel Title Highlighting

**Problem:** The two chart panels (Left Chart, Right Chart) have plain text titles that
are easy to overlook. The chart selector dropdowns sit inside each panel but there is
no visual treatment distinguishing the panel header from the chart content below it.

**Change:** Apply a grey background highlight to the title bar of each of the two chart
panels. The title bar is the strip containing the chart selector dropdown (e.g.
"Cumulative Cost", "Annual Cost by Device", etc.).

**Visual spec:**
```
┌─────────────────────────────────────────────┐
│  Left Chart  [ Cumulative Cost        ▾ ]   │  ← grey title bar (#F0F0F0)
├─────────────────────────────────────────────┤
│                                             │
│   (chart renders here)                      │
│                                             │
└─────────────────────────────────────────────┘
```

**Implementation:**
- Apply `background-color: #F0F0F0` (light grey) to the title bar container of each
  chart panel via an inline style or a shared CSS class `chart-panel-title`.
- The highlight covers the full width of the panel header strip — not just the
  dropdown label text.
- Both Left Chart and Right Chart panels get identical treatment.
- No change to font, dropdown behaviour, or chart rendering below the title bar.

**Solara pattern:**
```python
with solara.Row(
    style="background-color: #F0F0F0; padding: 6px 12px; border-radius: 4px 4px 0 0;"
):
    solara.Select(label="Left Chart", values=CHART_OPTIONS, value=left_chart_selection)
```

---

### 18.2 Home Profile Panel — Collapse Secondary Details

**Problem:** The Home Profile card currently shows all fields flat (ZIP, Climate Zone,
Bedrooms, Square Footage, Year Built, Building Performance/Insulation, Baseline device
specs). This makes the left column tall and visually heavy, especially once the Solar +
Battery panel is added below it (§18.3).

**Change:** Wrap the secondary home details in a collapsible section within the Home
Profile card. ZIP code, Bedrooms, and Square footage remain always visible. Climate
Zone, Year Built, and Building Performance/Insulation are hidden by default behind a
"More details…" toggle.

**Always visible (never hidden):**
```
🏠 Home Profile
  ZIP code       [ 95112 ]
  Bedrooms       [ 3 ▾ ]
  Square footage [ 1,800 ]
  ▶ More details...
```

**Collapsed (default state):** The "More details…" toggle is shown closed (▶).
Climate Zone, Year Built, and Building Performance are hidden.

**Expanded:**
```
  ▼ More details...
  Climate zone        [ CZ12 ▾ ]
  Year built          [ 1985   ]
  Building Performance
    Insulation   ( Poor )  (● Average )  ( Good )
```

**Reactive state:**
```python
home_profile_details_expanded = solara.reactive(False)
```
Add to `_DEFAULTS` and `reset_to_defaults()`.

**What moves into the dropdown vs. stays visible:**

| Field | Always visible | In dropdown |
|---|---|---|
| ZIP code | ✓ | |
| Bedrooms | ✓ | |
| Square footage | ✓ | |
| Climate zone | | ✓ |
| Year built | | ✓ |
| Building Performance / Insulation | | ✓ |

**Rationale:** ZIP, Bedrooms, and Square Footage are the fields most users touch in a
community engagement session. Climate Zone, Year Built, and Insulation are set-and-forget
for most users. Hiding them reduces visual clutter without removing the capability.

---

### 18.3 Solar + Battery Panel — Position in Home Profile Column

**Change from §17.8:** Move the Solar + Battery panel from its §17.8 position
("after Journey Planner card, before Home Profile card") to sit **below the Home
Profile card** in the left/home-profile column.

**Left column layout after this change:**
```
Left column (home config)
──────────────────────────────────────────────────
Journey Planner card
Energy & Prices card
Home Profile card
  ZIP | Bedrooms | Sq Ft          ← always visible
  ▶ More details...               ← collapsed by default
    Climate Zone, Year Built,
    Building Performance
──────────────────────────────────────────────────
☀️🔋 Solar + Battery card
  [ ] Adding solar + battery...  ← collapsed by default
```

**Right column layout (unchanged):**
```
Right column (charts)
──────────────────────────────────────────────────
Left Chart panel   [grey title bar]
Right Chart panel  [grey title bar]
```

**Behaviour:** Solar + Battery card is a separate card sitting directly below Home
Profile. It uses the existing §17 collapsible design (checkbox "Adding solar + battery
to my journey" reveals all inputs). Default state: collapsed/unchecked.

**Why this position:** Solar + Battery is a home-level infrastructure decision (a fixed
install, not an annual operating parameter), so it belongs visually alongside the home
configuration inputs. Placing it below Home Profile keeps it discoverable while
preserving the primary journey-planning flow at the top of the column.

---

### 18.4 Claude Code Prompt — UI Polish

```
Implement §18 (UI Polish) of docs/Phase2_Spec.md.

Step 1 — Chart panel title highlighting (§18.1):
  In app.py, locate the two chart panel containers (Left Chart, Right Chart).
  Wrap each panel's title/selector row in a solara.Row with:
    style="background-color: #F0F0F0; padding: 6px 12px; border-radius: 4px 4px 0 0;"
  Both panels get identical treatment.
  No changes to chart logic, dropdown options, or chart rendering.

Step 2 — Home Profile collapsible details (§18.2):
  Add home_profile_details_expanded = solara.reactive(False).
  Add to _DEFAULTS and reset_to_defaults().
  In HomeProfilePanel:
    Always visible: ZIP code, Bedrooms, Square footage.
    Add clickable "▶ / ▼ More details..." toggle row below Square footage.
    Collapsed (default): Climate zone, Year built, Building Performance hidden.
    Expanded: show Climate zone, Year built, Building Performance / Insulation.
  Use same chevron-rotate pattern as §13 ExpandableSlotRow.

Step 3 — Solar + Battery panel relocation (§18.3):
  Move the Solar + Battery card from its current position (between Journey Planner
  and Home Profile) to below the Home Profile card in the same column.
  No changes to Solar + Battery internals — §17 logic is unchanged.

Run solara run src/app.py and verify:
  - Both chart panel title bars have a light grey (#F0F0F0) background strip.
  - Home Profile shows only ZIP, Bedrooms, Sq Ft by default.
  - Clicking "More details..." expands Climate Zone, Year Built, Insulation.
  - Solar + Battery card sits directly below Home Profile card in the left column.
  - All existing §17 solar functionality (cost buttons, IRA auto-calc, 3-line chart)
    works unchanged.
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
