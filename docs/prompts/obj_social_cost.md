# WhyWatt Phase 3 — Social & Health Cost of Gas (§6)

## Context

WhyWatt is a home electrification cost simulator (Python 3.11+, Mesa 3.x, Solara,
Matplotlib). Run with `.venv/Scripts/solara.exe run src/app.py`. Tests:
`.venv/Scripts/python.exe -m pytest tests/`. (Use the `.venv` interpreter — system
Python lacks mesa/solara.)

Read `docs/Phase3_Spec.md` §6 before starting. This adds a "Social & Health Cost of Gas"
panel and overlays those costs on two charts. It is the last objective before
Evaluator Release 1.

**Prior objectives committed on `main`:** Obj 1 (help system), Obj "panel" (ElectricalSpec
+ Panel Assessment). Tag `phase2` marks Phase 2.

This objective changes **how gas social cost is displayed**, not the underlying energy/cost
simulation. Market-rate cost, kWh, and therms outputs must stay identical.

---

## Resolved Decisions (override the spec where they differ)

1. **Re-run model on slider change (spec-literal §6.4).** `SocialCostConfig` is a field on
   `HESModel`; social $ is exposed as DataCollector columns; the 4 new reactives are added
   to the `run_simulation` memo dependency list (every change re-runs the sim, consistent
   with all other controls).

2. **Charts: JC-2 and JC-4 only.** Add social cost to:
   - **JC-2** = `make_cumulative_opex` (cumulative line chart) — dashed "incl. social" lines.
   - **JC-4** = `make_cost_breakdown` (cumulative stacked AREA, dual-pane) — two extra
     stacked layers (climate, health).
   - **Do NOT** touch `make_annual_cost` (the bar chart) — skipped to limit clutter.
   - Scenario A only (JC-4 is already labeled "Scenario A"); no Scenario B social series.

3. **Gas therms come from the real API, not the spec pseudocode.** There is no
   `slot.current_device.fuel`. Track gas therms correctly (see Deliverable 1).

4. **Do NOT pollute `cost_history_by_category`.** Store gas therms in a dedicated
   `gas_therms_history` list on `JourneyHome`; derive social $ from it. The
   `social_climate/health/total` keys from spec §6.3 are NOT added to
   `cost_history_by_category`.

---

## What to Build

### Deliverable 1 — Gas therms tracking (`src/journey.py`)

**In `DeviceSlot.step()`**, after the `for active in active_list` loop that accumulates
`step_cost`, record this slot's gas therms for the year:

```python
self._last_gas_therms = sum(
    a.history["consumption"][-1]
    for a in active_list
    if a.fuel_type == "gas"
)
```
(Gas device `monthly_consumption().sum()` is in therms, already appended to
`history["consumption"]` by `active.step()`.) Initialize `self._last_gas_therms = 0.0`
at the top of `step()` alongside `_last_active_device`.

**In `JourneyHome.__init__`**, add:
```python
self.gas_therms_history: list = []
```

**In `JourneyHome.step()`**, accumulate across slots and append once per step
(sum-then-append, Phase 2 hard rule §4). Inside the existing `for slot in self.slots:`
loop add `year_gas_therms += getattr(slot, "_last_gas_therms", 0.0)` (init
`year_gas_therms = 0.0` near `year_opex = 0.0`), then after the loop:
```python
self.gas_therms_history.append(year_gas_therms)
```

This is pure physics — independent of social-cost rates. No energy/cost math changes.

### Deliverable 2 — `src/social_cost.py`

```python
from dataclasses import dataclass

@dataclass
class SocialCostConfig:
    climate_enabled: bool  = True
    climate_rate:    float = 1.07   # $/therm — EPA 2023 SC-CO2 + 2% CH4 leakage
    health_enabled:  bool  = True
    health_rate:     float = 1.23   # $/therm — CPUC D.24-07-015 / E3 2022

    @property
    def climate_eff(self) -> float:
        return self.climate_rate if self.climate_enabled else 0.0

    @property
    def health_eff(self) -> float:
        return self.health_rate if self.health_enabled else 0.0

    @property
    def total_rate(self) -> float:
        return self.climate_eff + self.health_eff
```

### Deliverable 3 — Wire into `HESModel` (`src/model.py`)

- Add `social_cost_config: SocialCostConfig | None = None` to `HESModel.__init__`;
  default to `SocialCostConfig()` when None; store as `self.social_cost_config`.
- Add DataCollector reporters (Scenario A homes only):
  ```python
  "Journey Social Climate":  lambda m: m.journey_home.gas_therms_history[-1]  * m.social_cost_config.climate_eff,
  "Journey Social Health":   lambda m: m.journey_home.gas_therms_history[-1]  * m.social_cost_config.health_eff,
  "Baseline Social Climate": lambda m: m.baseline_home.gas_therms_history[-1] * m.social_cost_config.climate_eff,
  "Baseline Social Health":  lambda m: m.baseline_home.gas_therms_history[-1] * m.social_cost_config.health_eff,
  ```
  (Guard against empty history defensively if needed, but `collect` runs after `step`,
  so `[-1]` is valid.)

### Deliverable 4 — Reactive state + run_simulation (`src/app.py`)

Add reactives near other rate controls:
```python
social_climate_enabled = solara.reactive(True)
social_climate_rate    = solara.reactive(1.07)
social_health_enabled  = solara.reactive(True)
social_health_rate     = solara.reactive(1.23)
```
Add matching `_DEFAULTS` entries and `reset_to_defaults` lines. Add all four to the
`run_simulation` memo dependency list.

In `run_simulation()`, build and pass the config:
```python
from social_cost import SocialCostConfig
...
m = HESModel(
    ...,
    social_cost_config=SocialCostConfig(
        climate_enabled=social_climate_enabled.value,
        climate_rate=social_climate_rate.value,
        health_enabled=social_health_enabled.value,
        health_rate=social_health_rate.value,
    ),
)
```

### Deliverable 5 — `SocialCostPanel` UI (`src/app.py`)

Add a collapsible panel component mirroring the existing panel style
(`JourneyPlannerPanel` / `EnergyPricesPanel` grey-header pattern). Place it **below
`EnergyPricesPanel`** in the controls column (find where `EnergyPricesPanel()` is invoked
in the layout and add `SocialCostPanel()` right after).

Contents:
- Grey header row: "♻ Social & Health Cost of Gas" + `HelpButton("social_cost")`
  (right-aligned via `flex:1` on the title text).
- **Climate Cost** row: a `solara.Checkbox`/switch bound to `social_climate_enabled`
  + a `SliderWithDefault`/`solara.SliderFloat` bound to `social_climate_rate`
  (min 1.00, max 2.00, step 0.01, label `$/therm`). When disabled, show the slider
  greyed/disabled (or hide it) — disabled state means $0 is used (handled by config).
  Show anchor labels "$1.00" … "$2.00".
- **Health Cost** row: switch → `social_health_enabled`; slider → `social_health_rate`
  (min 0.50, max 2.00, step 0.01). Anchors "$0.50" … "$2.00".
- A live readout: "Total social cost: $X.XX/therm" using the same effective logic
  (climate_eff + health_eff).
- Disclosure footer (always shown):
  *"These costs do not appear on your utility bill. They represent damage to public
  health and the climate caused by burning natural gas."* + a "Learn more →" that calls
  `open_help("social_cost.html")`.

Reuse existing styling helpers/patterns; keep it compact.

### Deliverable 6 — JC-2 chart overlay (`make_cumulative_opex`)

In `make_cumulative_opex(df, model, n)`, after the existing baseline/journey cumulative
lines are drawn, if `model.social_cost_config.total_rate > 0`, add two dashed lines:

```python
cfg = model.social_cost_config
if cfg.total_rate > 0:
    j_social_cum = np.cumsum(df["Journey Social Climate"].values
                             + df["Journey Social Health"].values)
    b_social_cum = np.cumsum(df["Baseline Social Climate"].values
                             + df["Baseline Social Health"].values)
    j_incl = df["Journey Cum Cost"].values  + j_social_cum
    b_incl = df["Baseline Cum Cost"].values + b_social_cum
    ax.plot(x, b_incl, color=C_BASE, lw=1.6, linestyle=(0,(4,2)),
            alpha=0.9, label="Do nothing + social")
    ax.plot(x, j_incl, color=C_ELEC, lw=1.6, linestyle=(0,(4,2)),
            alpha=0.9, label="Your journey + social")
```
Keep the existing solid market lines unchanged. Ensure the legend still fits (fontsize 8).
This must work in both single and comparison modes (comparison mode already adds B lines;
social lines are Scenario A only — fine).

### Deliverable 7 — JC-4 chart overlay (`make_cost_breakdown`)

In the per-home loop (`for ax, (home, title_sub, palette_idx) in zip(axes, homes)`), after
the `CATEGORY_ORDER` stack is drawn (after `bottom` is finalized), add climate + health
as two more stacked layers from the home's gas therms × config rates:

```python
cfg = model.social_cost_config
therms = np.array(home.gas_therms_history[:n], dtype=float)
if cfg.climate_eff > 0:
    cum = np.cumsum(therms * cfg.climate_eff)
    ax.fill_between(x, bottom, bottom + cum, color="#FB8C00", alpha=0.80,
                    label="Climate cost")
    bottom = bottom + cum
if cfg.health_eff > 0:
    cum = np.cumsum(therms * cfg.health_eff)
    ax.fill_between(x, bottom, bottom + cum, color="#C62828", alpha=0.80,
                    label="Health cost")
    bottom = bottom + cum
```
Place the social layers visually above the market categories (they are, since added last).
Legend already present; the two new labels join it.

### Deliverable 8 — Help content

Edit `docs/help/help_content.md` §13 so its `@keys` line is:
```
@keys: social_cost
```
(Leave the existing §13 `@popup` and body content as-is — they already cover the topic.)
Then run `.venv/Scripts/python.exe scripts/build_help.py` to regenerate
`social_cost.html` and `src/help_content.py`. Do not hand-edit `src/help_content.py`.

---

## Hard Rules

1. **No change to market-rate energy/cost math.** kWh, therms, market $ outputs, and all
   existing chart series must be identical to before. Social cost is purely additive
   display derived from gas therms × rate.
2. `gas_therms_history` is pure physics — it must not depend on `SocialCostConfig`.
3. Do not add social keys to `cost_history_by_category`.
4. All 4 new reactives must be in `_DEFAULTS`, `reset_to_defaults`, and the
   `run_simulation` memo deps.
5. When both toggles are off (`total_rate == 0`), charts must render exactly as before
   (no dashed lines, no social layers).
6. Run the app (`.venv/Scripts/solara.exe run src/app.py`) and confirm it boots before
   committing.

## Tests — `tests/test_social_cost.py`

- `SocialCostConfig`: defaults total_rate == 2.30; climate disabled → total 1.23;
  both disabled → 0.0; health disabled → 1.07.
- `gas_therms_history`: build a small `HESModel` (default slots) and assert
  `len(journey_home.gas_therms_history) == n_years` and year-1 value > 0 (gas furnace +
  gas WH present at start) and that a fully-electrified later year has lower gas therms.
- Multi-gas slot correctness: a slot with `[GasFurnace, CentralAC]` baseline contributes
  only the furnace therms (AC is electricity) to `_last_gas_therms`.
- DataCollector columns exist and equal `gas_therms × rate`:
  `df["Baseline Social Health"][0] == baseline_home.gas_therms_history[0] * 1.23`
  (within float tolerance), with default config.

## Acceptance Criteria

- [ ] `social_cost.py` with `SocialCostConfig` (climate_eff/health_eff/total_rate)
- [ ] `gas_therms_history` on JourneyHome; `_last_gas_therms` summed over ALL gas devices
      in a slot (furnace+AC case correct); appended once per step
- [ ] `HESModel.social_cost_config` + 4 DataCollector columns (Scenario A)
- [ ] 4 reactives wired: defaults, reset, memo deps; config built in run_simulation
- [ ] `SocialCostPanel` below Energy & Prices: two enable switches + sliders
      (climate 1.00–2.00 default 1.07; health 0.50–2.00 default 1.23), total readout,
      disclosure footer, `HelpButton("social_cost")`
- [ ] JC-2 cumulative chart: dashed "incl. social" lines for both scenarios (A); hidden
      when total_rate == 0
- [ ] JC-4 category chart: climate + health stacked layers per home; hidden when each
      component's effective rate is 0
- [ ] JC-1 (annual bar chart) untouched
- [ ] help_content.md §13 keys = `social_cost`; build_help.py re-run; social_cost.html +
      help_content.py regenerated
- [ ] `tests/test_social_cost.py` passes
- [ ] All pre-existing passing tests still pass (the 3 known dual_scenario failures remain
      pre-existing/unrelated); market-rate outputs unchanged
- [ ] App boots cleanly
