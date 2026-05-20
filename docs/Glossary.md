# WhyWatt? — Glossary & Data Dictionary

This document defines the key variables, terminology, and units used throughout the
WhyWatt? codebase, JSON data files, and UI.  Updated for Phase 2.

---

## 1. Device Interface (`EnergyConsumer` & subclasses)

**`monthly_consumption()`**
- Returns a `(12,)` NumPy array of energy consumed in each calendar month.
- Unit: **kWh** for electrical devices · **therms** for gas devices.
- Never MMBtu — Phase 2 uses native units throughout.

**`annual_consumption()`**
- Sum of `monthly_consumption()`.  Convenience method, not stored separately.

**`fuel_type`**
- String: `"electricity"` or `"gas"`.  Set by each device subclass.

**`lifespan`**
- Expected operational life before replacement.  Unit: years.

**`age`**
- Current age of the device.  Incremented each simulation step.  Unit: years.

**`installation_cost`**
- Capital expenditure to purchase and install the device.  Unit: USD.

**`history`**
- Dict with keys `"consumption"` and `"cost"`: one float appended per annual step.
- Units: kWh or therms (consumption); USD (cost).

---

## 2. Device Computation Families

**`SeasonalDevice`**
- Distributes a fixed annual total across months using a seasonality weight array.
- Good for: dryer, cooktop, lights — flat week-to-week usage.

**`PhysicsDevice`**
- Derives monthly consumption from climate formulas (HDD/CDD/water temp).
- Climate constants are injected at construction — devices never read files.
- Good for: HVAC, water heating — strongly weather-driven.

**`ScheduleDevice`**
- Returns an exact 12-element monthly array supplied at construction.
- Good for: EV charger, solar PV — data-driven or custom profiles.

---

## 3. Journey Model

**`DeviceSlot`**
- Dataclass representing one appliance position in a home.
- Fields: `name`, `category`, `starting_state`, `baseline_devices`, `electric_device`,
  `swap_year`, `install_cost`, `rebate`.

**`starting_state`**
- `"gas"` — slot currently runs gas device(s); may swap to electric at `swap_year`.
- `"electric"` — already electrified before simulation start; both homes use electric device.
- `"none"` — absent from baseline (e.g. EV charger add); zero cost until `swap_year`.

**`swap_year`**
- Simulation year (1-indexed) when the electric device replaces the baseline device(s).
- `None` means never swap.

**`net_install_cost`**
- `install_cost − rebate`.  Applied as a CapEx event at `swap_year`.

**`JourneyHome`**
- Mesa agent that owns a list of `DeviceSlot` objects and steps them annually.
- Tracks `annual_opex`, `cumulative_opex`, `capex_by_year`, `cost_history_by_category`.

**`cost_history_by_category`**
- Dict keyed by category string; each value is a list of annual costs.
- Length equals the number of simulation steps (sum-then-append pattern).

---

## 4. Home & Climate Configuration

**`HomeConfig`**
- Dataclass carrying all home-specific parameters injected into `HESModel`.
- Active in Phase 2: `num_bedrooms` (scales baseload + hot water), `insulation_quality` (→ UA).

**`BEDROOM_SCALING`**
- Dict mapping bedroom count (1–5) to `baseload_multiplier` and `hot_water_gal_per_day`.
- 3BR is the DOE/ENERGY STAR TMY3 reference: 65 gal/day, 1200 kWh/yr baseload.

**`ua_by_insulation`** (`poor` / `average` / `good`)
- Thermal conductance of the building envelope in BTU/hr/°F.
- Values: poor = 650, average = 500, good = 350 (Bay Area TMY3 defaults).

---

## 5. Rate System

**`RateLoader`**
- Maps `(fuel, year, month, scenario)` → $/kWh or $/therm.
- Historical periods use CPUC/PG&E published tariff rates.
- Future periods use `base_rate × (1 + cagr)^(year − base_year)`.

**`scenario`**
- `"conservative"`: elec +4%/yr, gas +4%/yr.
- `"moderate"`: elec +7%/yr, gas +8%/yr (default; matches 10-yr historical).
- `"stress"`: elec +10%/yr, gas +12%/yr (CEC high-gas scenario).

**`get_annual_monthly_rates(fuel, sim_start_year, n_years, scenario)`**
- Returns shape `(n_years, 12)` array of $/kWh or $/therm.
- `sim_start_year` maps simulation year 1 to a real calendar year.

---

## 6. System-Specific Efficiency Metrics

**`AFUE`** (Annual Fuel Utilization Efficiency)
- Seasonal efficiency of gas furnaces.  AFUE 0.80 → 80% of fuel becomes useful heat.

**`SEER`** (Seasonal Energy Efficiency Ratio)
- Cooling efficiency of a heat pump or air conditioner.

**`COP`** (Coefficient of Performance)
- Ratio of useful heating output to electrical energy input.
- COP 3.5 → 1 kWh electricity delivers 3.5 kWh of heat.

**`UEF`** (Uniform Energy Factor)
- Standard efficiency rating for water heaters.

---

## 7. Simulation Output

**`capex_events`** (on `DeviceSlot`)
- List of `(year, cost)` tuples: swap install events and end-of-life replacements.

**`capex_by_year`** (on `JourneyHome`)
- Dict mapping simulation year → total CapEx spend in that year.

**`Opex Delta`** (DataCollector reporter)
- `Baseline Cum Cost − Journey Cum Cost` at each step.
- Positive = journey has saved money relative to doing nothing.

---

## 8. Unit Conversion (display only)

```
1 therm = 29.3 kWh
```

Used only when converting gas consumption to kWh for combined energy charts.
Never used in simulation internals — all calculations stay in native units.
