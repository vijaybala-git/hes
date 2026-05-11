# WhyWatt — Phase 2 Development Spec

**Status:** Ready for implementation
**Follows:** Phase 1 complete (Mesa + Solara, 42 unit tests, dual-home simulation)
**Project rename:** HES → **WhyWatt?** (update all UI titles, headers, doc references)
**Last updated:** Journey model + monthly device hierarchy + CPUC rate data model added

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
JourneyHome B — "Do nothing"       all swap_years = None (gas forever)
```

The gap between the two cumulative cost lines IS the value of the journey. The "do nothing"
line is not flat — gas prices escalate and gas appliances trigger CapEx replacements at
end-of-life, making it increasingly expensive to stay on gas. This is the core advocacy
message.

**DeviceSlot — the unit of configuration:**

```python
@dataclass
class DeviceSlot:
    name: str                          # "HVAC", "Water Heater", "Dryer" etc.
    category: str                      # CATEGORY_ORDER key
    baseline_device: EnergyConsumer    # gas or legacy electric device
    electric_device: EnergyConsumer    # replacement electric device
    swap_year: int | None              # year swap occurs; None = never
    install_cost: float                # gross install cost of electric device
    rebate: float                      # rebate amount (IRA, TECH Clean CA etc.)

    @property
    def net_install_cost(self):
        return self.install_cost - self.rebate
```

**Annual step logic per slot:**

```python
def step(self, current_year, monthly_rates):
    if self.swap_year is None or current_year < self.swap_year:
        active = self.baseline_device
    else:
        active = self.electric_device

    active.step(monthly_rates)

    # CapEx: swap event OR end-of-life replacement
    if current_year == self.swap_year:
        self.capex_events.append((current_year, self.net_install_cost))
    elif active.age >= active.lifespan:
        self.capex_events.append((current_year, active.installation_cost))
        active.age = 0
```

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
  "notes": "monthly_hdd + monthly_cdd sum to annual totals above"
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

### 2.5 cost_history_by_category Bug Fix

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

### 2.6 Core Unit Rule

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
- Constructor takes `journey_slots` (list of slot configs) and `scenario` string
- Calls `RateLoader.get_annual_monthly_rates()` at init — passes rate arrays to model
- Instantiates two `JourneyHome` objects:
  - `self.journey_home`: uses `swap_year` from slot configs
  - `self.baseline_home`: same slots but all `swap_year = None`
- Loads climate constants from `data/climate/bayarea_tmy3.json` once at init
- `insulation_quality` parameter maps to UA value via climate constants

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
    "baseline_device": {"class": "GasFurnace",    "afue": 0.80, "age": 10},
    "electric_device": {"class": "HeatPumpHVAC",  "cop_heating": 3.5, "seer_cooling": 22},
    "swap_year": null,
    "install_cost": 14000,
    "rebate": 3500
  },
  {
    "name": "Water Heater",
    "category": "WaterHeating",
    "baseline_device": {"class": "GasWaterHeater",      "uef": 0.65, "age": 5},
    "electric_device": {"class": "HeatPumpWaterHeater", "uef": 3.5},
    "swap_year": null,
    "install_cost": 2500,
    "rebate": 500
  },
  {
    "name": "Dryer",
    "category": "Baseload",
    "baseline_device": {"class": "GasDryer",    "therms_per_cycle": 0.22, "cycles_per_week": 5},
    "electric_device": {"class": "HeatPumpDryer", "kwh_per_cycle": 1.8,   "cycles_per_week": 5},
    "swap_year": null,
    "install_cost": 1200,
    "rebate": 0
  },
  {
    "name": "EV Charger",
    "category": "Baseload",
    "baseline_device": null,
    "electric_device": {"class": "EVCharger"},
    "swap_year": null,
    "install_cost": 800,
    "rebate": 0
  },
  {
    "name": "Lights and Appliances",
    "category": "Baseload",
    "baseline_device": {"class": "LightsAndPlugs", "annual_kwh": 1200},
    "electric_device": {"class": "LightsAndPlugs", "annual_kwh": 1200},
    "swap_year": null,
    "install_cost": 0,
    "rebate": 0
  }
]
```

Note: `baseline_device: null` for EV Charger means the baseline home has no EV —
zero consumption for that slot until `swap_year`.

**Tests `tests/test_journey.py`:**
- `DeviceSlot` uses baseline device before `swap_year`, electric after
- `swap_year = None` always uses baseline device
- CapEx event logged at `swap_year` with `net_install_cost`
- End-of-life CapEx logged when `age >= lifespan` for active device
- `JourneyHome` `cost_history_by_category` has exactly `n_steps` entries per category
- Two homes with identical configs produce identical cost trajectories
- `baseline_home` (all `swap_year=None`) costs more than `journey_home` after
  all swaps complete (with stress gas scenario)
- `HESModel.datacollector.get_model_vars_dataframe()` has `n_years` rows

**Claude Code prompt:**
```
Implement Objective 3 of docs/Phase2_Spec.md.
Create src/journey.py with DeviceSlot and JourneyHome.
Refactor src/model.py: replace HomeSimulator with JourneyHome,
add RateLoader integration, fix cost_history_by_category bug per §2.5.
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

**Scope:** Full Solara UI refactor. New Journey Planner control panel.
WhyWatt branding throughout. Dual scenario chart support.

**Branding:**
- `solara.Title("WhyWatt?")` and `# ⚡ WhyWatt?` header
- Header logo: `docs/assets/whywatt_logo.png` with `os.path.exists()` guard
- Footer: group logo + org name, same guard

**Reactive state — new:**

```python
# Journey planner — one entry per slot
hvac_swap_year    = solara.reactive(3)    # None = "not planning to swap"
wh_swap_year      = solara.reactive(5)
dryer_swap_year   = solara.reactive(None)
ev_swap_year      = solara.reactive(None)

# Device specs (replaces MMBtu sliders)
insulation_quality = solara.reactive("average")   # poor / average / good
furnace_afue       = solara.reactive(0.80)
gas_wh_uef         = solara.reactive(0.65)
hp_cop_heating     = solara.reactive(3.5)
hp_seer_cooling    = solara.reactive(22)
hpwh_uef           = solara.reactive(3.5)

# Pricing
price_scenario_a   = solara.reactive("moderate")
comparison_mode    = solara.reactive(False)
price_scenario_b   = solara.reactive("stress")
years              = solara.reactive(20)
sim_start_year     = solara.reactive(2025)

# Rebates (editable)
hvac_rebate        = solara.reactive(3500)
wh_rebate          = solara.reactive(500)
```

**Journey Planner panel (replaces Gas Home + Electric Home panels):**

Each slot shows as a row:
```
Device          Swap in year    Install cost    Rebate      Net cost
HVAC            [slider 1–25]   $14,000        [$3,500]    $10,500
Water Heater    [slider 1–25]   $2,500         [$500]      $2,000
Dryer           [slider 1–25]   $1,200         [$0]        $1,200
EV Charger      [slider 1–25]   $800           [$0]        $800
                [ ] Not planning to swap  (checkbox disables slider)
```

**Control panels (three, as before):**

- **Journey Planner** — swap year per device, rebate amounts, install costs
- **Home Profile** — insulation quality, device efficiency specs (AFUE, COP, UEF, SEER)
- **Energy & Timeline** — scenario A selector, years, comparison mode toggle,
  scenario B selector (revealed when toggle on)

**Chart updates:**

All 6 existing charts updated to support 4-series output when `comparison_mode=True`.
- Solid lines = Scenario A, dashed = Scenario B
- Blue/grey palette retained

**New chart: Journey Timeline** (add as 7th chart option):
- Horizontal timeline showing swap events as vertical markers
- Annotated with device name and net cost at each swap year
- Gas price trajectory as background colour band to contextualise timing

**Summary stat bar — updated:**
```
Journey savings vs do-nothing (Scenario A):  $X over N years
Journey payback year: Y
[If comparison on] Scenario B savings: $Z over N years
```

**Claude Code prompt:**
```
Implement Objective 6 of docs/Phase2_Spec.md.
Refactor app.py: replace Gas Home / Electric Home panels with Journey Planner.
Add WhyWatt branding with logo guards.
Update all 6 charts to support 4-series (comparison_mode).
Add Journey Timeline as 7th chart type.
Update reactive state as specified in §4 Objective 6.
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
│       └── journey_slots_default.json
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
- [ ] `solara run src/app.py` loads with WhyWatt branding, no errors
- [ ] Journey Planner: setting HVAC swap_year=3 produces CapEx spike at year 3
- [ ] Baseline ("do nothing") cumulative cost exceeds journey cost after all swaps (stress scenario)
- [ ] Comparison mode shows 4-series charts correctly
- [ ] `RateLoader` returns 0.310 for PG&E electricity June 2023
- [ ] Logo placeholder renders without crash when PNG not present

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
