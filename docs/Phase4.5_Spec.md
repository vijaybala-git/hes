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
