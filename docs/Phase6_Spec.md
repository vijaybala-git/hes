# WhyWatt — Phase 6 Development Spec (Mesa Simulation: Rate Hand-off Interface + Seams)

**Status:** 🔵 PLANNED — simulation-focused preparation phase. Build the rate hand-off *interface*
and the Phase 7 seams; **no default output changes** (golden bit-for-bit).
**Follows:** Post Phase 2 user-testing line + the closed offline sub-projects
(`OfflineRateProjection_Plan.md`). **Sits ahead of** Phase 7 (default rate switch + golden
re-baseline, Solar/Battery physics, URDB TOU rates).
**Last updated:** 2026-09-07 — recentered on the simulation; folded in Spec 5.6 items; the rate
hand-off interface is now the lead deliverable.

> **What changed from the 2026-06-23 draft.** The original Phase 6 mixed a large offline PVWatts/URDB
> harvest into the phase. That harvest is now its own track (`docs/OfflineSolarData_Plan.md`), and
> Phase 6 is about the **simulation**: standing up the interface that lets the model consume the
> now-complete rate-projection bundle (`whywatt_rate_projection.json`) **without** switching the
> default. This supersedes `docs/Phase5.6_Spec.md` (items folded into WS3) and the wire-in portion of
> `docs/Phase6_RateProjection_Plan.md` (the *default switch* remains Phase 7).

---

## Goal

Make the projected-rate bundle *consumable by the simulation* — and *evaluable against today's
formula rates* — while the default user-visible output stays byte-for-byte unchanged. Concretely,
three work-streams in priority order:

1. **WS1 (lead) — Rate hand-off interface.** Add a new, **non-default** rate model
   (`cec_projection`) backed by a `ProjectedRateSource` that reads
   `data/rates/projection/whywatt_rate_projection.json`. Leave every default `rate_model` untouched
   so the golden passes bit-for-bit. Ship an **end-of-phase difference evaluation** that quantifies
   what Phase 7 will change when the switch is flipped.
2. **WS2 — Phase 7 seams (output-preserving).** Split `Solar + Battery` into two independently
   simulated devices (same arithmetic), and add the inert PVWatts inputs (roof geometry + per-zone
   lat/lon) that `OfflineSolarData_Plan.md` keys off.
3. **WS3 — Minor folds from Spec 5.6 + old Phase 6 §4.** SC-CH₄ citations & slider anchors; direct
   CO₂/CO₂e emissions chart; per-state grid-mix Help table; independent per-pane scenario toggle;
   HVAC design-temperature groundwork.

## The central constraint (read before starting)

**No new data source may change a number the user sees by default.** Phase 6 is a seam + interface
phase. The regression golden (`tests/regression/golden.json`) is the gate: it must pass bit-for-bit
after Phase 6 (Invariant 1). New rate paths, config fields, and datasets are accepted, sanitized,
shared, and persisted — but the **default** simulation path is unchanged.

The one deliberate evolution from the original Phase 6: the rate-projection bundle moves from
*"committed but wholly unconsumed"* to *"consumable via a non-default rate model, guarded by a
golden-neutrality test."* This is still golden-safe (see Invariant 5). PVWatts/URDB data stays
wholly unconsumed (that's the offline-solar track).

## Decisions locked for Phase 6/7 (do not re-litigate)

| Decision | Choice | Reason |
|---|---|---|
| Rate interface vs rate switch | **Interface in Phase 6, default switch in Phase 7** | Lets us *evaluate the difference* before re-baselining the golden |
| Which consumers the projection feeds (Phase 6) | **Retail `get_rate` escalation only** | Cleanest diff; isolates the CAGR-vs-CEC effect; NEM export + social overlay stay on legacy |
| Projection integration mode | **Read the baked JSON bundle only** | Core never imports `src/rate_projection/` (the offline package's portability rule) |
| Scenario mapping | **1:1 by label** (`conservative`/`moderate`/`stress`) | The bundle's `scenario_keys` already match the sim's scenarios exactly |
| API integration mode (solar/TOU) | **Bake offline, never call live** | Matches climate/EIA/ACC/rate pipeline; keeps UI synchronous |
| PVWatts geo granularity | **Per CEC zone, single default orientation** | Roof tilt/azimuth become Phase 7 correction factors |
| Peak/non-peak split location | **Fully in Phase 7** | Phase 6 keeps one monthly consumption stream |
| Solar vs Battery | **Two devices, independent simulation** | Generation and storage are physically distinct; enables Phase 7 dispatch |

## Invariants (must hold after every step)

1. **Default golden output is unchanged.** `python scripts/run_regression.py` passes against the
   existing `tests/regression/golden.json` with **zero** diffs after Phase 6.
2. **The projected-rate path is off by default.** `cec_projection` is a new value in the rate-model
   enum; no default config selects it. A test asserts the factory-default config produces the golden.
3. **New HomeConfig fields are inert.** `roof_tilt`, `roof_azimuth`, `array_type`, `module_type`,
   `system_losses`, per-zone lat/lon are carried, sanitized, shared, and reset — but no device or
   rate code reads them (precedent: `panel_amps`, `year_built`).
4. **`monthly_consumption()` still returns shape `(12,)`.** No peak/non-peak dimension yet.
5. **Core reads the bundle as data, never imports the offline package.** `git grep` confirms no
   `src/` file imports `src/rate_projection/`. The bundle JSON may be read only by the
   `ProjectedRateSource` behind the `cec_projection` branch. PVWatts/URDB data stays unconsumed.
6. **Hard rules from CLAUDE.md still hold** — no MMBtu; devices never read data files;
   `cost_history_by_category` appends once per step; logo `os.path.exists` guard; `HomeConfig` is the
   only home-detail carrier.

---

## WS1 — Rate hand-off interface (lead deliverable)

### The seam already exists

`src/model.py:_make_loader(base_rl, rate_model, fuel, fuel_res)` already dispatches on a `rate_model`
string; the allowed values live in `src/ui/config.py:_RATE_MODELS = {"cagr_flat", "ca_average",
"acc_shaped", "acc_seasonal"}`, selected per fuel and per scenario slot
(`elec_rate_model_a/b`, `gas_rate_model_a/b`). Defaults today: `elec/gas_rate_model_a = "cagr_flat"`,
`elec_rate_model_b = "acc_shaped"`, `gas_rate_model_b = "acc_seasonal"`.

So WS1 is **additive**: add one branch, one enum value, one adapter. No existing path is rewired.

### §1a — `ProjectedRateSource` adapter

- New pure reader (e.g. `src/rate_loader.py` or `src/projected_rate_source.py`) that loads
  `data/rates/projection/whywatt_rate_projection.json`, selects `markets.<default_market>` (CA_PGE)
  and a scenario by **label** (`conservative`/`moderate`/`stress` — a 1:1 map to the sim's scenario),
  and exposes the **same interface `get_rate(fuel, year, month, scenario)` uses today**: an annual
  retail level × the bundle's `monthly_shape`. Base year and monthly resolution match the current
  `get_annual_monthly_rates` contract, so the model's monthly sub-calculation is unaffected.
- **Reads the bundle as plain data.** It must not import `src/rate_projection/` (Invariant 5).
- Base-year sanity: the bundle anchors to the same PG&E tariff ($0.386/kWh, $2.08/therm) as
  CLAUDE.md, so `cec_projection` ≈ the formula path at `year 0` and diverges only via escalation —
  which is exactly the quantity WS1 exists to measure.

### §1b — Wire it as a non-default `rate_model`

- Add `"cec_projection"` to `_RATE_MODELS` and a branch in `_make_loader` that returns the new
  adapter. **Do not change any default** in `data/config/whywatt_default.json`.
- **Scope: retail `get_rate` only** (locked decision). The NEM export path
  (`get_nem3_export_rates`, `model.py:474`) and the social overlay stay on their existing sources in
  Phase 6 — even when `cec_projection` is selected — so the diff isolates retail escalation and the
  known output-leak surfaces (RateProjection_Plan §3.6 b/c) stay closed.
- Round-trip the new enum value through Share links / saved configs (it's already covered by the
  `ENUMS` machinery once added to `_RATE_MODELS`).

### §1c — End-of-Phase-6 difference evaluation (the payoff)

- **Notebook** `notebooks/rate_switch_review.ipynb`: run the sim (or the rate series directly) under
  the default formula path vs `cec_projection`, per fuel and per scenario, and report the headline
  deltas — e.g. 25-yr do-nothing gas cost, 25-yr journey electricity cost, and total lifetime
  savings — nominal and real. This is the "what Phase 7 will change" chart for stakeholder sign-off.
  - Expected shape of the finding: today's `moderate` formula escalates elec **+7%/yr** and gas
    **+8%/yr** flat; the bundle's CEC-driven `moderate` is elec **real-flat (~+2.2%/yr nominal)** and
    gas **spiral** — so switching lowers projected electricity cost and reshapes gas materially.
- **Test** `tests/test_projected_rate_source.py`: (a) the factory-default config still reproduces the
  golden (Invariant 2); (b) `cec_projection` loads, returns shape-`(12,)` monthly rates, base-year
  matches the tariff, and each scenario is monotonic-sane; (c) `git grep` gate — no `src/` import of
  `src/rate_projection/`.

**Acceptance (WS1):** golden bit-for-bit with defaults; `cec_projection` selectable and correct;
`rate_switch_review.ipynb` renders the difference; the Phase 7 default-switch decision has a number
behind it.

---

## WS2 — Phase 7 seams (output-preserving)

### §2a — Split Solar + Battery into two devices

Today `journey.py:SolarBatteryConfig` is one dataclass; the solar block in `JourneyHome.step()`
computes `production = system_kw × specific_yield`, splits it by a single `scf` self-consumption
fraction, prices the split against retail + export rates, and caps at electricity spend. Battery
presence only nudges `scf`.

Refactor to two configs with independent step hooks, **same arithmetic**:

```
SolarConfig    panels, kw_per_panel, specific_yield → annual_production_kwh = system_kw × specific_yield
               scf ("Self-use %") → self_consumed = production × scf; exported = rest
               nem_mode, nbc (export credit rule)
               (Phase 7: specific_yield → per-zone monthly yield vector from pvwatts_zones.json)
BatteryConfig  battery_enabled, battery_kwh → labels/sizes the "Solar + Battery" capex slot
               (Phase 7: battery_kwh + round-trip eff → dispatch physics that COMPUTES self-use)
```

- Keep `SolarBatteryConfig` as a thin composition/back-compat shim, or migrate `model.py`/`ui/sim.py`
  wiring to pass both configs. Either way `solar_savings_history`, `solar_production_kwh_history`,
  `solar_self_consumed_history`, `solar_exported_kwh_history` must be **numerically identical**.
- **`scf` stays a single fraction owned by `SolarConfig`.** No "solar base + battery boost"
  decomposition — Phase 7's dispatch model will *compute* self-consumption and supersede the slider.
- **The battery→self-use link stays a UI default-snap, not a sim coupling.** Preserve `_on_battery`
  (`panels.py:1532`): toggling Battery sets `solar_scf` to 80/35; slider stays user-editable; the sim
  still reads only `scf`. `battery_enabled` drives the capex slot only.
- The single `CapExOnlySlot` "Solar + Battery" stays one install event (Hard Rule 9 analog).

**Acceptance:** golden unchanged; `test_journey.py` solar assertions unchanged; new tests assert
`SolarConfig`/`BatteryConfig` reproduce `SolarBatteryConfig` for the default and solar-only configs.

### §2b — Home Profile inputs for PVWatts (inert)

Add to `home_config.py:HomeConfig` (CA defaults), wired through `ui/state.py`, `ui/config.py`
(`INT_KEYS`/`ENUMS`/`RANGES`/sanitize), the Home Profile panel, and `reset_to_defaults()`:

| Field | Type | Default | Allowed / range | PVWatts param |
|---|---|---|---|---|
| `roof_tilt` | int (deg) | 20 | 0–60 | `tilt` |
| `roof_azimuth` | int (deg) | 180 | 0–359 | `azimuth` |
| `array_type` | enum | `"fixed_roof"` | fixed_roof / fixed_open / tracking_1ax / tracking_2ax | `array_type` |
| `module_type` | enum | `"standard"` | standard / premium / thin_film | `module_type` |
| `system_losses` | float (%) | 14.0 | 0–99 | `losses` |

- Add **lat/lon per CEC zone** to `data/climate/tmy3_zones.json` (surface it from the station
  lat/lon the trend fit already used, via `scripts/build_climate_db.py` or a one-off augmentation).
  This is the canonical source `OfflineSolarData_Plan.md` keys off.
- Fields round-trip through Share links + saved configs. **No device reads them** — add a test that
  toggling each leaves the regression output unchanged.

---

## WS3 — Minor folds (Spec 5.6 + old Phase 6 §4)

All display / documentation / UI-state only. Zero simulation output change; golden unaffected.

### §3a — SC-CH₄ explicit citation + slider anchors (old Phase 6 §4)

- Split the `SocialCostConfig` docstring into cited sub-components: **SC-CO₂ combustion** $0.97/therm
  (EIA 5.306 kg CO₂/therm × EPA 2023 central $190/tCO₂; Rennert et al. 2022; EPA SC-GHG 2023) and
  **SC-CH₄ leakage adder** $0.10/therm (EPA SC-CH₄ 2023 ~$1,600/short ton × 2% pipeline leakage).
  Total stays **$1.07/therm** — no numeric change, citation made explicit.
- Change the `panels.py` gate label "Add CO₂ + Methane Cost" → **"Add SC-CO₂ + SC-CH₄ (EPA)"**.
- Extend `SliderSpec` (`ui/slider.py`) with an optional `anchors: list[tuple[float,str]]`; `_track()`
  renders each as a labelled `.ww-tick`. Four anchors for the climate-rate slider ($1.00–$2.00):
  EPA CO₂ $1.00 · **EPA+CH₄ $1.07 (default)** · +CH₄ 3.7% $1.15 (Alvarez et al. 2018) · High-Urgency
  $1.80 (EPA 2023 Tech Report App. 3B, 1.5% discount). Each tick shows a source tooltip; the help
  page (`public/help/social_cost.html`) gains a 4-model citation table.

### §3b — Direct CO₂ / CO₂e emissions chart (Spec 5.6 #2)

Display-only view over existing `gas_therms_history` / `gasoline_gallons_history` (journey +
baseline). New menu entry "Direct Emissions (CO₂ / CO₂e)"; Journey↔Do-nothing toggle (reuse
`device_chart_home` pattern); CO₂/CO₂e metric toggle; stacked bars by source; y-axis metric tons
CO₂e/yr. Factors as named constants: gas 5.30 kg CO₂/therm (EPA), CO₂e ≈ 6.5 kg/therm (combustion +
2.3% leakage × GWP100 28); gasoline 8.89 kg/gal. **Electricity excluded, with the mandatory caveat
footnote** — journey electricity that replaced gas/gasoline carries an uncounted grid-carbon
footprint, so the true net reduction is smaller (grid-carbon modeling is Phase 7).

### §3c — Per-state electricity-mix Help table (Spec 5.6 #3)

Static reference table in Help (CA first) so users can interpret the "electricity not counted"
caveat from §3b. Generated fragment (`docs/help/_generated/grid_mix.md`) from a committed
`data/grid/state_mix.json`; columns clean/carbon-free % vs fossil % + year + source. **Lead with the
CEC Power Content Label** (consumption-based, includes imports — the honest "behind my plug"
figure), corroborate with CAISO in-state. Not wired into the model.

### §3d — Independent per-pane scenario toggle (Spec 5.6 #4)

Split the global `device_chart_home` reactive (`state.py:185`) into
`device_chart_home_left`/`device_chart_home_right` (+ reset), add the two keys to
`whywatt_default.json`, swap them into `SHARE_EXCLUDE` (`config.py`), and give `ChartPane` a
`home_rv` param (`layout.py`) so left/right pass their own reactive. No chart-builder/model/data
change. Optional nicety: default the right pane to `"baseline"`.

### §3e — HVAC tonnage groundwork (Spec 5.6 #1)

Auto-size HVAC tonnage from home size for a credibility/narrative number (tonnage does **not** affect
annual degree-day energy; it's a design-day concept). The rigorous form `tons = UA × design_ΔT /
12,000` reuses existing `UA` but needs a **per-zone design temperature** (99% heating / 1% cooling)
that `tmy3_zones.json` lacks. This is the only WS3 item touching the climate pipeline — add design
temps alongside the WS2 lat/lon augmentation of `build_climate_db.py`. Display/label only; no energy
math change.

### Not in Phase 6

- **Spec 5.6 #5 (match y-axis scales across panes)** — tabled; marginal payoff.
- **Spec 5.6 #6 (consolidate "Plan" buttons into one row)** — **Phase 7**, alongside the
  Solar/Battery/Panel redesign, when a unified plan-row can be coherent.

---

## Module / data deltas (Phase 6 target state)

```
src/
  rate_loader.py / projected_rate_source.py  (NEW) ProjectedRateSource reads whywatt_rate_projection.json
  model.py              _make_loader: + "cec_projection" branch (non-default)
  ui/config.py          _RATE_MODELS: + "cec_projection"
  journey.py            SolarBatteryConfig → SolarConfig + BatteryConfig (+ shim)
  home_config.py        + roof_tilt, roof_azimuth, array_type, module_type, system_losses
  ui/state.py           + 5 solar-geometry reactives; split device_chart_home → left/right (§3d)
  ui/sim.py             pass SolarConfig + BatteryConfig (or shim) to HESModel
  ui/panels.py          Home Profile roof geometry (inert); SC-CH₄ gate label (§3a); Direct Emissions (§3b)
  ui/slider.py          SliderSpec.anchors + labelled tick rendering (§3a)
  ui/layout.py          ChartPane home_rv param (§3d); Direct Emissions menu entry (§3b)
  social_cost.py        SC-CH₄ explicit citation in docstring (§3a)
public/help/social_cost.html   4-model SCC citation table (§3a)
data/
  climate/tmy3_zones.json     + per-zone lat/lon (§2b) + design temps (§3e)
  config/whywatt_default.json + solar-geometry defaults; device_chart_home_left/right (§3d)
  grid/state_mix.json         (NEW) per-state clean/fossil mix, CA first (§3c)
notebooks/
  rate_switch_review.ipynb    (NEW) formula vs cec_projection difference eval (§1c)
tests/
  test_projected_rate_source.py  (NEW) default=golden; cec_projection sanity; import gate (§1c)
  test_journey.py                + Solar/Battery split equivalence
  test_config.py                 + new-field round-trip + inertness; cec_projection round-trip
docs/
  Phase6_Spec.md        this file
  OfflineSolarData_Plan.md   the offline PVWatts/URDB harvest (separate track)
  Phase7_Spec.md        default rate switch + golden re-baseline; TOU; solar/battery dispatch
```

## Definition of done

- [ ] `ProjectedRateSource` reads the bundle; `cec_projection` selectable as a **non-default**
      `rate_model`; retail `get_rate` only; core imports no `src/rate_projection/` code.
- [ ] `rate_switch_review.ipynb` runs top-to-bottom and reports the formula-vs-projection deltas.
- [ ] `SolarConfig` + `BatteryConfig` reproduce `SolarBatteryConfig` numerics (golden unchanged).
- [ ] 5 roof-geometry fields + per-zone lat/lon land, round-trip through Share/save, and are inert.
- [ ] WS3 folds landed: SC-CH₄ citations + 4 anchors; Direct Emissions chart; grid-mix Help table;
      per-pane scenario toggle; HVAC design-temps in the climate DB (display/label only).
- [ ] `python scripts/run_regression.py` → **zero diffs** with factory defaults; full `pytest` green.
- [ ] CLAUDE.md updated: Phase 6 closed, Phase 7 entered (default rate switch + golden re-baseline).

> **Deferred to Phase 7** (the golden-rebaseline moment): make `cec_projection` the default; extend
> it to the NEM export path and the time-varying social overlay; PVWatts/URDB consumption + the
> peak/non-peak rate interface; Solar/Battery dispatch physics; plan-button consolidation.
