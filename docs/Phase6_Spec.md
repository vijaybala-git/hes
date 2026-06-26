# WhyWatt — Phase 6 Development Spec

**Status:** 🔵 PLANNED — preparation phase. Build the seams; no new data source touches output.
**Follows:** Post Phase 2 user-testing line; sits ahead of Phase 7 (Solar/Battery physics + TOU rates).
**Last updated:** 2026-06-23 — initial plan.

---

## Goal

Prepare the codebase for the large Phase 7 data-pipeline changes (PVWatts solar generation,
battery charge physics, URDB peak/non-peak TOU rates) **without adding any new data source
that affects final output**. Phase 6 creates the structural seams so Phase 7 is a data swap,
not a rewrite.

Three deliverables:

1. **Split `Solar + Battery` into two independently-simulated devices** — a Solar
   *generation* unit and a Battery *storage* unit — preserving today's formulas so output is
   unchanged.
2. **Add the PVWatts-relevant inputs to `HomeConfig` + Home Profile UI** (roof tilt, azimuth,
   array type, module type, system losses) plus per-zone lat/lon — **carried but inert**,
   exactly as `panel_amps` was introduced ahead of the panel assessor.
3. **Harvest the full offline datasets** from PVWatts and URDB (CA-first, but with a
   geo-general schema), commit them with provenance, and add **validation tests + diagnostic
   graphs** to review data quality and build intuition for the Phase 7 mechanics — but **do
   not wire the data into the model** (output stays unchanged).

## The central constraint (read before starting)

**No new data source may change a number the user sees.** Phase 6 is a refactor + plumbing
phase. The Solar/Battery device split must keep the exact same production, self-consumption,
export, and savings math the single `SolarBatteryConfig` produces today. The regression
golden (`tests/regression/golden.json`) is the gate: **it must pass bit-for-bit after Phase 6**
(see Invariant 1). New config fields are accepted, sanitized, shared, and persisted, but never
read by the simulation.

## Decisions locked for Phase 6/7 (do not re-litigate)

| Decision | Choice | Reason |
|---|---|---|
| API integration mode | **Bake offline, never call live** | Matches climate/EIA/ACC pipeline; keeps UI synchronous |
| PVWatts geo granularity | **Per CEC zone, single default orientation** | Smallest data; tilt/azimuth become Phase 7 correction factors |
| Peak/non-peak split location | **Fully in Phase 7** | Phase 6 keeps one monthly consumption stream; output stays stable |
| Solar vs Battery | **Two devices, independent simulation** | Generation and storage are physically distinct; enables Phase 7 dispatch model |

## Invariants (must hold after every step)

1. **Golden output is unchanged.** `python scripts/run_regression.py` passes against the
   existing `tests/regression/golden.json` with **zero** diffs after Phase 6. If a refactor
   forces an unavoidable rounding change, it must be justified and the golden re-baselined in
   its own commit with the diff explained.
2. **New HomeConfig fields are inert.** `roof_tilt`, `roof_azimuth`, `array_type`,
   `module_type`, `system_losses`, lat/lon are carried, sanitized, shared, and reset — but no
   device or rate code reads them. (Precedent: `panel_amps`, `year_built`.)
3. **`monthly_consumption()` still returns shape `(12,)`.** No peak/non-peak dimension yet.
4. **Hard rules from CLAUDE.md still hold** — no MMBtu; devices never read data files;
   `cost_history_by_category` appends once per step; logo `os.path.exists` guard; `HomeConfig`
   is the only home-detail carrier.
5. **Harvested data is committed but unconsumed.** `scripts/build_pvwatts.py` / `build_urdb.py`
   are real and run offline (manually — they need API keys, not in CI); their output JSON is
   committed with provenance. But **no device or rate code in Phase 6 reads these files**, so
   the golden is unaffected (Invariant 1). The data exists to be reviewed, not yet to drive output.

---

## Work breakdown

### §1 — Split Solar + Battery into two devices (output-preserving)

Today `journey.py:SolarBatteryConfig` is one dataclass; the solar block in
`JourneyHome.step()` (≈ lines 370–412) computes `production = system_kw × specific_yield`,
splits it by a single `scf` self-consumption fraction, prices the split against retail +
export rates, and caps at electricity spend. Battery presence only nudges `scf`.

**Refactor to two configs with independent step hooks, same arithmetic:**

```
SolarConfig          # generation + self-use + export pricing (the "system")
  panels, kw_per_panel, specific_yield   →  annual_production_kwh = system_kw × specific_yield
  scf            (the "Self-use %" slider) → self_consumed = production × scf; exported = rest
  nem_mode, nbc  (export credit rule)      → grid property of the system
  (Phase 7: specific_yield → per-zone monthly yield vector; roof geometry applied)

BatteryConfig        # cost + lifetime ONLY — energy-inert in Phase 6
  battery_enabled, battery_kwh           →  labels/sizes the "Solar + Battery" capex slot
  (Phase 7: battery_kwh + round-trip eff → dispatch physics that COMPUTES self-use,
            superseding SolarConfig.scf)
```

- Keep `SolarBatteryConfig` as a thin composition/back-compat shim **or** migrate
  `model.py`/`ui/sim.py` wiring to pass both configs. Either way, the computed
  `solar_savings_history`, `solar_production_kwh_history`, `solar_self_consumed_history`,
  `solar_exported_kwh_history` arrays must be **numerically identical** to today.
- **Self-use (`scf`) stays a single fraction owned by `SolarConfig`** — it is the only input
  the self-consumption math reads. `BatteryConfig` carries **no** energy behavior in Phase 6.
  We deliberately do **not** decompose self-use into a "solar base + battery boost"; Phase 7's
  dispatch model will *compute* self-consumption and supersede the slider, so a decomposition
  would only have to be unwound.
- **The battery→self-use link stays a UI default-snap, not a sim coupling.** Preserve the
  existing `_on_battery` callback ([panels.py:1532](../src/ui/panels.py)): toggling Battery
  sets `solar_scf` to 80 (on) / 35 (off); the slider remains user-editable. The simulation
  still reads only `scf`, so output is bit-identical. `battery_enabled` continues to drive the
  capex slot only.
- The single `CapExOnlySlot` named `"Solar + Battery"` stays one install event for now
  (Hard Rule analog: one capex event). Whether to visually split the slot is a Phase 7 UI call.

**Acceptance:** golden unchanged; `test_journey.py` solar assertions unchanged; new unit
tests assert `SolarConfig`/`BatteryConfig` reproduce `SolarBatteryConfig` for the default
config and for a solar-only (battery off) config.

### §2 — Home Profile inputs for PVWatts (inert)

Add to `home_config.py:HomeConfig` (with sensible CA defaults), wire through
`ui/state.py` reactives, `ui/config.py` (`INT_KEYS`/`ENUMS`/`RANGES`/sanitize), the Home
Profile panel, and `reset_to_defaults()`:

| Field | Type | Default | Allowed / range | PVWatts param |
|---|---|---|---|---|
| `roof_tilt` | int (deg) | 20 | 0–60 | `tilt` |
| `roof_azimuth` | int (deg) | 180 | 0–359 | `azimuth` |
| `array_type` | enum | `"fixed_roof"` | fixed_roof / fixed_open / tracking_1ax / tracking_2ax | `array_type` |
| `module_type` | enum | `"standard"` | standard / premium / thin_film | `module_type` |
| `system_losses` | float (%) | 14.0 | 0–99 | `losses` |

- Add **lat/lon per CEC zone** to `data/climate/tmy3_zones.json` (each zone already names its
  `tmy3_station`; the trend fit already used station lat/lon — surface it into the record via
  `scripts/build_climate_db.py` or a one-off augmentation). Phase 7 PVWatts precompute keys
  off this.
- These fields must round-trip through Share links and saved configs (extend
  `whywatt_default.json` `values`, `ENUMS`, `RANGES`, `INT_KEYS`).
- **No device reads them.** Add a test asserting that toggling each new field leaves the
  regression output unchanged.

### §3 — Full offline data harvest + validation (committed, unconsumed)

Collect the **real** PVWatts and URDB datasets now, so Phase 7 is "wire in data we've already
seen and trust." The data is committed but no model code reads it (Invariant 5). **CA-first,
but the file schema is geo-general** — keyed so out-of-CA stations/tariffs add without a schema
change (no CA-only assumptions baked into the structure).

**Targeted, region-at-a-time harvest.** Rather than grabbing all 16 CEC zones at once, the
batch scripts take a `--region` and we validate one region end-to-end before broadening:

| Target | Region | Utilities | CEC zones (core) | TOU tariffs (verify labels in URDB at harvest) |
|---|---|---|---|---|
| **1 (now)** | Bay Area | PG&E | CZ3 (coast), CZ4 (South Bay, default), CZ2 (inland N. Bay) | PG&E E-TOU-C, E-ELEC, EV2-A |
| **2 (next)** | SoCal | SCE, SDG&E | CZ6/CZ8 (LA basin), CZ9/CZ10 (inland), CZ7 (San Diego), CZ14 (desert) | SCE TOU-D-4-9PM, TOU-D-PRIME; SDG&E TOU-DR1, EV-TOU-5 |

The region→(zones, utilities, tariff ids) mapping lives in a small table in each build script
(or a shared `scripts/regions.py`), so adding a region is a data edit, not new code.

API keys (free NREL + OpenEI) are read from env vars (`NREL_API_KEY`, `URDB_API_KEY`), never
committed. Scripts are run manually offline, not in CI.

**§3a — PVWatts batch harvest (`scripts/build_pvwatts.py --region bayarea`):**
- For each CEC-zone reference station in the region (lat/lon from §2), call PVWatts v8 with
  `system_capacity=1`, default orientation (`array_type=fixed_roof`, `module_type=standard`,
  `tilt=20`, `azimuth=180`, `losses=14`).
- Append `ac_monthly` (the **per-kW monthly yield vector**), `ac_annual`, the request params,
  and `sha256(raw_response)` to `data/solar/pvwatts_zones.json` (keyed by zone, additive across
  regions); snapshot raw responses under `data/solar/sources/`.
- **Also request `timeframe=hourly`** and derive a **normalized intra-day solar shape** per
  month per zone — the fraction of each month's generation that falls in the solar-window /
  peak / off-peak periods (a 12×24 normalized shape, or the collapsed 12×3 period fractions).
  Store as `intraday_shape` in the zone record. Phase 7's dispatch engine needs this to place
  monthly generation into the three daily periods (it can't be recovered from `ac_monthly`
  alone). This is the only reason hourly output is fetched; the monthly totals still drive sizing.

**§3b — URDB batch harvest (`scripts/build_urdb.py --region bayarea`):**
- For the region's curated residential TOU tariffs, fetch URDB v8 `detail=full` and parse
  `energyratestructure` (tiered slabs: `{max, rate, adj, sell}`) + `energyweekdayschedule` /
  `energyweekendschedule` (12×24 period grid) into the simplified schema `{tariff_id, utility,
  region, peak_rate, offpeak_rate, peak_hours (12×24 period index or bool grid), tiers,
  fixed_charge}` → `data/rates/urdb_tou.json` (additive across regions); snapshot raw responses
  with sha256 under `data/rates/sources/`.

**§3c — Analysis notebooks + validation tests (the point of doing this in Phase 6):**
- **Jupyter notebooks** (`notebooks/pvwatts_review.ipynb`, `notebooks/urdb_review.ipynb`) read
  the committed JSON and produce the data review:
  - *PVWatts:* per-zone monthly yield curves, a cross-zone annual-yield bar, and a Bay-Area vs
    SoCal coastal/inland comparison; a table comparing each zone's annual per-kW yield against
    today's scalar `specific_yield=1500`.
  - *URDB:* a 12×24 **peak-hour heatmap** per tariff (confirm the ~4–9pm peak window), a
    peak-vs-offpeak rate bar with tier-threshold overlays, and a table of each tariff's
    load-weighted flat-equivalent vs the EIA per-utility rate already in the model.
  - These notebooks are the human review surface — run them, eyeball the figures, sanity-check
    the numbers from both APIs before Phase 7 trusts them. (Add `notebook` + `nbconvert` to a
    dev/analysis requirements pin; numpy/pandas/matplotlib/plotly are already in `requirements.txt`.)
- **Automated tests** (`tests/test_pvwatts_data.py`, `tests/test_urdb_data.py`) encode the same
  checks as a CI gate, independent of the notebooks: each yield vector is length-12,
  summer-peaked, with annual sum in a sane CA band (~1,300–1,750 kWh/kW/yr, coastal < inland)
  and CZ4 default-orientation annual ≈ `specific_yield=1500`; URDB schedules parse to 12×24 with
  every hour mapped to a defined period, tier `max` thresholds ascend, and each tariff's
  load-weighted flat-equivalent lands within tolerance of the matching EIA per-utility rate.

**Acceptance:** Bay Area datasets committed with provenance (SoCal optional/second); validation
tests green; both review notebooks run top-to-bottom and render their figures; `git grep`
confirms **no `src/` model/rate code imports `data/solar/` or `data/rates/urdb_tou.json`** (data
is review-only in Phase 6).

> **Deferred to Phase 7:** the peak/non-peak *rate interface* (`get_peak_offpeak_rates`) and the
> consumption split. Phase 6 collects and validates the data; Phase 7 flows it through the model.

---

## Module / data deltas (Phase 6 target state)

```
src/
  journey.py            SolarBatteryConfig → SolarConfig + BatteryConfig (+ shim)
  home_config.py        + roof_tilt, roof_azimuth, array_type, module_type, system_losses
  ui/state.py           + 5 solar-geometry reactives
  ui/config.py          + INT_KEYS / ENUMS / RANGES / sanitize entries
  ui/sim.py             pass SolarConfig + BatteryConfig (or shim) to HESModel
  ui/panels.py          Home Profile: roof geometry inputs (inert)
data/
  climate/tmy3_zones.json     + per-zone lat/lon
  config/whywatt_default.json + new solar-geometry default values
  solar/pvwatts_zones.json    (NEW, baked) per-zone per-kW monthly yield + provenance
  solar/sources/              (NEW) raw PVWatts JSON snapshots (sha256)
  rates/urdb_tou.json         (NEW, baked) simplified peak/offpeak + slabs per tariff
  rates/sources/              (NEW) raw URDB JSON snapshots (sha256)
scripts/
  regions.py            (NEW) region → (CEC zones, utilities, tariff ids) mapping
  build_pvwatts.py      (NEW, run offline) PVWatts batch harvest --region → pvwatts_zones.json
  build_urdb.py         (NEW, run offline) URDB batch harvest --region → urdb_tou.json
notebooks/
  pvwatts_review.ipynb  (NEW) yield curves / cross-zone + Bay-vs-SoCal / specific_yield table
  urdb_review.ipynb     (NEW) 12×24 peak-hour heatmap / rate bars / EIA cross-check table
tests/
  test_journey.py       + Solar/Battery split equivalence tests
  test_config.py        + new-field round-trip + inertness tests
  test_pvwatts_data.py  (NEW) yield-vector shape/plausibility + CZ4 sanity bridge
  test_urdb_data.py     (NEW) schedule parse + slab order + EIA cross-source sanity
docs/
  Phase6_Spec.md        this file
  Phase7_Spec.md        the follow-on data-flow phase
```

## Definition of done

- [ ] `SolarConfig` + `BatteryConfig` reproduce `SolarBatteryConfig` numerics (golden unchanged).
- [ ] 5 roof-geometry fields + per-zone lat/lon land, round-trip through Share/save, and are inert.
- [ ] PVWatts harvested for **Bay Area** zones (SoCal optional/second) → `pvwatts_zones.json` + snapshots.
- [ ] URDB harvested for **Bay Area** PG&E TOU tariffs (SoCal optional/second) → `urdb_tou.json` + snapshots.
- [ ] Validation tests green; `pvwatts_review.ipynb` / `urdb_review.ipynb` run top-to-bottom and render figures.
- [ ] `git grep` confirms no `src/` code reads the new data files (review-only in Phase 6).
- [ ] `python scripts/run_regression.py` → zero diffs; full `pytest` green.
- [ ] CLAUDE.md updated: Phase 6 closed, Phase 7 entered.
