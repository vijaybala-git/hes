# WhyWatt — Phase 4.5 Development Spec

**Status:** 🔵 PLANNED — refactor-only, no behavior change.
**Follows:** Phase 4 §2 (per-utility EIA rate modeling). Phase 4.5 is a structural refactor, not a feature phase.
**Last updated:** 2026-06-18 — initial plan.

---

## Goal

Break up `src/app.py` (currently **5,329 lines**) into a cohesive `src/ui/` package, with
`app.py` reduced to a thin entry point. **This is a pure refactor: zero behavior change,
zero new features, no logic rewrites.** The app must look and behave identically before and
after each step.

## Motivation

`app.py` has grown to 5,329 lines / 50 `@solara.component`s / **149 module-level
`solara.reactive(...)` globals**. It is hard to navigate, review, and reason about. Two
blocks dominate:

- **Chart helpers** — ~1,060 lines (≈ lines 1136–2196), the `make_*` functions.
- **§25 Summary + Detail UI** — ~1,960 lines (≈ 2582–4543), summary cards + detail windows.

## The central constraint (read before starting)

The 149 reactive globals are a shared-state hub that all components read via `.value`. Solara
idiomatically uses module-level reactive state, so the **enabling move is to give that state
its own module** (`state.py`); component extraction is blocked until it exists.

Mitigating factor: the chart functions are already **data-parameterized**
(`make_cumulative_opex(df, model, n)` etc.) — only a few reach into globals (e.g.
`solar_planned.value`), so most bulk is extractable once state has a home.

## Invariants (must hold after every step)

1. **One reactive instance, shared.** Every module imports the *same* reactive objects from
   `state.py`. Never redefine a `solara.reactive(...)` in two modules — components would
   read/write different cells and silently desync.
2. **Strict one-directional import layering** (no cycles):
   `state / theme / icons` (leaf) → `charts / helpers` → `cards / details` → `layout` → `app`.
   `state.py` imports no UI module.
3. **`solara run src/app.py` still exposes `Page`** — keep `Page` defined or re-exported in
   `app.py`.
4. **No behavior change.** Same components, same reactive wiring, same output. Refactor moves
   code; it does not edit logic.
5. **Explicit imports.** Prefer `import state as S` / `S.zip_code` (greppable) over
   `from state import *`.

## Phased plan (lowest-risk first; one commit per phase)

**Phase 1 — Leaf modules, zero reactive coupling (~600 lines out).**
- `ui/theme.py` ← CSS + color palette + chart design tokens (≈ 49–164)
- `ui/icons.py` ← SVG icon strings/dicts (card / panel / device icons)
- `ui/estimators.py` ← display-only consumption estimators (≈ 165–213, already pure)

**Phase 2 — Centralize state (the unlock).**
- `ui/state.py` ← all 149 reactives + `_DEFAULTS` + `reset_to_defaults()`.
- Convert call sites to `import state as S` / `S.<name>`.

**Phase 3 — Charts (~1,000 lines out).**
- `ui/charts.py` ← the `make_*` functions (≈ 1136–2196). The few that read globals take a
  param or `import state`.
- `ui/sim.py` (optional) ← `run_simulation`, climate/rate resolution helpers (≈ 978–1136).

**Phase 4 — §25 Summary + Detail UI (~1,960 lines, biggest payoff, trickiest).**
- `ui/card_helpers.py`, `ui/summary_cards.py`, `ui/detail_panels.py`.
- Move one component-group at a time; smoke-check between moves.

**Phase 5 — Layout + thin entry.**
- `ui/layout.py` ← masthead, cockpit, setup group, journey grid, Main Page (≈ 4626–5329).
- `app.py` collapses to a ~100-line shim: imports + `Page` + run entry.

### Target structure
```
src/
  app.py                 # thin entry: imports + Page + run
  ui/
    __init__.py
    state.py             # reactives, defaults, reset
    theme.py             # CSS, colors, chart tokens
    icons.py
    estimators.py
    sim.py               # run_simulation + climate/rate resolution
    charts.py            # make_* chart builders
    card_helpers.py
    summary_cards.py
    detail_panels.py
    layout.py            # masthead, cockpit, setup group, Main Page
```

## Verification (no UI tests exist — this is the safety net)

After **every** move:
1. `python -c "import ast; ast.parse(open('src/app.py',encoding='utf-8').read())"` (and the
   new module) — parse check.
2. Import check (`python -c "import app"` from `src/`).
3. `pytest tests -q` stays green (currently **208 passing**) — guards the non-UI modules.
4. `preview_start` + screenshot — behavior must be visually identical. Toggle a couple of
   reactives (ZIP, rate source) to confirm shared-state wiring survived the move.

## Out of scope / non-goals

- No behavior, layout, or styling changes.
- No new features; no logic rewrites; no renaming of reactives or components beyond moving them.
- No changes to `model.py`, `rate_loader.py`, `rate_resolver.py`, device modules, or data.
- ACC / rate / climate logic untouched.

## Workflow

- Land all pending Phase 4 work on `main` first (after a few more tests).
- Do Phase 4.5 on a dedicated branch (e.g. `phase4.5-app-split`), one commit per phase so any
  step is trivially reversible.

---

# Phase 4.5b — Configuration & Startup (externalized defaults)

**Status:** 🔵 PLANNED — follows the app.py refactor; builds on the now-isolated `ui/state.py`.
**Added:** 2026-06-18.

## Motivation

After the refactor, all reactive state lives in `ui/state.py`, but the defaults are still
**hardcoded in two parallel places**: the `_DEFAULTS` dict (144 keys) *and* the reactive
initial literals (`zip_code = solara.reactive("95112")`). They currently agree but are kept in
sync by hand — any one-sided edit silently drifts. Beyond the cleanup, we want **configs that
can be loaded at startup, swapped, shared, and re-loaded.**

## Use cases (driving the design)

1. **Startup** loads a base config (`whywatt_default`) so the app starts in a known state.
2. **Developers ship alternate configs** — for a state, a city, a demo, or even a single
   parameter changed — and a user loads one of them.
3. A config can be **exported, shared, and re-loaded**, reproducing the same state.

## Design principles

- **Single source of truth** — reactives initialize *from* the loaded config; `_DEFAULTS` is
  the loaded base, not a second hand-written copy.
- **Self-describing, versioned** — every config (base and shared) carries `schema_version`
  so it survives sharing across app builds.
- **Load = REPLACE** (decided) — `effective = factory ⊕ config.values`; any key absent from
  the config resets to factory. Deterministic and reproducible regardless of prior on-screen
  state. (An "overlay/patch" mode may be added later, but is not the default.)
- **Export** captures the current persistent reactives into a shareable config.
- **Transient UI reactives are excluded** from configs/export: `setup_collapsed`,
  `_panel_state`, `_baseload_state`, `hw_gallons_user_override`.

## Config file format (JSON, versioned envelope)

```json
{
  "schema_version": 1,
  "name": "whywatt_default",
  "description": "Factory defaults — San Jose / PG&E baseline",
  "based_on": null,
  "values": { "zip_code": "95112", "num_bedrooms": 3, "...": "...144 keys..." }
}
```

- **Base** (`whywatt_default.json`): full `values`, `based_on: null`.
- **Profile / shared config**: same envelope; `values` may be a **delta** (a few keys, e.g. a
  city or single-parameter config) or a **full snapshot**. The loader treats both identically
  because it always merges onto the factory base.

## Loader API — `src/ui/config.py`

```python
FACTORY = "whywatt_default"
CONFIG_DIR = <repo>/data/config

def load_config(source) -> dict        # source = bundled name | file path | dict  (point 2 & 3)
def factory_defaults() -> dict          # the base `values` (point 1)
def merge(values) -> dict               # factory ⊕ values  (REPLACE semantics)
def validate(cfg) -> list[str]          # unknown keys / type / range -> warnings (safe loads)
def apply_config(cfg) -> None           # set reactives = merge(cfg["values"])    (point 2 & 3)
def export_config(name, desc) -> dict   # snapshot current persistent reactives    (point 3)
```

`load_config` accepts **any source** (not just bundled names), so user-shared files load too.

## `ui/state.py` becomes single-source

```python
from ui.config import factory_defaults
_DEFAULTS = factory_defaults()                       # loaded once at import
zip_code  = solara.reactive(_DEFAULTS["zip_code"])   # init FROM config, never a literal
...
def reset_to_defaults():  apply_config(factory)      # unchanged behavior
```

Add a **drift-proof test**: `assert set(_DEFAULTS) == {names of the resettable reactives}` —
this *enforces* the single source of truth so the two can never silently diverge again.

## Versioning (decided)

- `schema_version` lives on the base file **and** every exported config.
- Loader is tolerant: same version → load; older → fill missing keys from factory + warn;
  unknown keys → ignore + warn. Shared configs therefore survive app upgrades.

## Migration path (two layers)

- **Layer 1 — cleanup (behavior-preserving, do first):** generate `whywatt_default.json` *from*
  the current `_DEFAULTS` (identical values → zero behavior change), add `ui/config.py`
  (`factory_defaults`, `merge`, `apply_config`), rewire `state.py` to init from it, add the
  drift test. Verified with the same scan + preview discipline as Phase 4.5.
- **Layer 2 — the feature (when ready):** add `load_config(any source)`, `export_config`,
  `validate`, and the versioned envelope. The UI to pick/upload/share configs is deferred —
  the architecture above already supports it.

## Out of scope / deferred

- UI for choosing/uploading/sharing configs (the data model supports it; the widget is later).
- Moving option enumerations (`_CZ_OPTIONS`, `_BR_OPTIONS`, `CHART_OPTIONS`) into config —
  optional follow-up; these are static valid-value lists, not user defaults.
