# WhyWatt — Regression Test Spec

**Status:** 🔵 PLANNED — living document; reviewed/updated as the suite is built.
**Part of:** Phase 4.5 (see `Phase4.5_Spec.md`). Builds on the externalized config (Phase 4.5b).
**Added:** 2026-06-18.

> Context: the model is at a strong baseline — authoritative per-utility EIA rates, ZIP-driven
> CEC climate, solid device physics — so this is the right point to lock behavior with a
> golden-master suite and detect *unintended* drift from here forward.

---

## Objectives

1. **Detect regressions in results and identify the cause** — after any code change, know
   immediately if a user-visible number moved, and which case/metric.
2. **Pre-deploy confidence** — a quick run of ~a dozen representative cases that confirms
   numbers only change **as designed** before each release.

End goal: on each release, run the suite, **diff against the previous (golden) snapshot**, and
produce a **report** of what changed — a deliberate, auditable "numbers changed as designed."

## This is a different kind of test (vs. the existing unit suite)

| | Existing tests (`tests/test_*.py`, 13 files) | This suite |
|---|---|---|
| Kind | Unit / formula / component | **Golden-master scenario regression** |
| Asks | "Is each piece correct?" (device formulas ±5%, rate periods, panel logic, journey mechanics, config invariants) | "Did the **user-visible** numbers move, and only as designed?" |
| Granularity | One device / loader at fixed inputs | The full `run_simulation` pipeline for ~12 real journeys |

**Complementary, not overlapping.** Unit tests catch a broken formula; this suite catches
*emergent / integration* drift (a refactor, a default change, a wiring bug) that no single unit
test sees. Today nothing runs the full pipeline end-to-end and snapshots the cockpit numbers —
that is the gap this fills.

## Metrics captured (snapshot schema)

Per case, two groups. All values **rounded to a stable precision** (whole `$`, 0.1 kWh/therm)
to eliminate float/platform noise.

**Cockpit (headline numbers):**
- `opex_delta` (journey vs do-nothing — the headline "total cost difference")
- `journey_cumulative_opex`, `baseline_cumulative_opex`, `payback_year`
- `net_social_cost_avoided` (baseline − journey; climate + health)
- Panel: `current_load_amps` (yr-1), `peak_amps`, `peak_status` (green/yellow/orange/red),
  `peak_year` — exactly what `PanelAssessor.journey_load_timeline()` feeds the cockpit

**Per device / slot** (from `cost_history_by_slot` / `consumption_history_by_slot` /
`fuel_history_by_slot` on both `journey_home` and `baseline_home`):
- cumulative cost (journey **and** baseline)
- final-year consumption (kWh or therms) + fuel type

Snapshot sketch:
```json
{
  "schema_version": 1,
  "generated": "2026-06-18",
  "app_commit": "<git sha>",
  "cases": {
    "pge_full_journey": {
      "cockpit": { "opex_delta": 6363, "journey_cumulative_opex": 131626,
                   "baseline_cumulative_opex": 125263, "payback_year": null,
                   "net_social_cost_avoided": 19934,
                   "current_load_amps": 41, "peak_amps": 78, "peak_status": "green", "peak_year": 9 },
      "devices": { "HVAC": { "journey_cost": 12345, "baseline_cost": 9876,
                             "final_year_kwh": 1930.0, "fuel": "electricity" }, "...": {} }
    }
  }
}
```

## Comparison method — exact, with rounding

The model is **deterministic** (Monte Carlo deferred), data files are sha-snapshotted, and
`sim_start_year` is pinned by config. So comparison is **exact at the rounded precision** —
zero tolerance. Any diff means "something changed," which is then classified *designed* vs
*regression*. (Contrast the device tests' ±5%, which validate formulas; regression wants no
slack so nothing slips through.)

## Case matrix

A **"full journey"** = HVAC→heat pump, WH→HPWH, Cooktop→induction, Dryer→HP dryer, + EV
charger, on the default swap timeline.

### Core dozen (the pre-deploy check)

Base (3 ZIPs × {no-solar, default-solar}, default CAGR pricing):
| # | Case | ZIP / rate source |
|---|------|-------------------|
| 1–2 | PG&E — full journey — {no solar, +solar} | 95112 (PG&E) |
| 3–4 | SCE/SoCalGas — full journey — {no solar, +solar} | 90001 (SCE elec / SoCalGas gas) |
| 5–6 | CA average — full journey — {no solar, +solar} | rate source = `ca_average` |

Tricky additions (each exercises a distinct code path the base set misses):
| # | Case | Path it locks |
|---|------|---------------|
| 7 | **Panel-upgrade trigger** — 100 A panel + full electrification | peak exceeds panel → verdict flips (orange/red) + upgrade cost; base cases stay "green" |
| 8 | **ACC rate model** (elec `acc_shaped` + gas `acc_seasonal`) | the ACC pricing engine (load shapes, avoided cost, NEM 3 export) — base cases are all CAGR |
| 9 | **Do-nothing baseline only** (all gas, no swaps) | isolates the baseline numbers from the journey |
| 10 | **Out-of-state ZIP → CA-average *fallback*** (e.g. TX 73301) | the fallback *trigger* (distinct from *selecting* CA average) |
| 11 | **ICE → EV transport** (the §3 full switch) | gasoline gallons + climate/health externalities (a separate cost stream) |
| 12 | **Hot inland zone** (Fresno 93720) | cooling-dominated climate (base ZIPs are milder) |

> Highest priority if trimming: **7 (panel), 8 (ACC), 9 (baseline)** — cheap, and they cover
> the cockpit's riskiest numbers.

### Extended set (run less often / full regression)
- NEM 2.0 solar (vs the default NBT/NEM 3 export path)
- Climate trend RCP 8.5 (HDD/CDD trajectory → HVAC drifts across years)
- Large home (5 BR / high sq-ft) — baseload + HW + panel scaling
- Partial / staggered-swap-year journey — timeline + capex-event logic

## Cases as config files (Layer 2 consumer)

Each case is naturally a **config delta** on the factory default — making this suite the first
consumer of the Phase 4.5b config system. Cases live as configs (e.g.
`tests/regression/cases/*.json`, the same versioned envelope). Drive each case the faithful
way: **apply the case config to the reactives → `run_simulation()` → extract metrics**. This
exercises the *real* pipeline (`_build_slot_configs` + the model) — what users actually see —
not a hand-built `HESModel` that could diverge from the UI path.

## Step 0 — make the pipeline UI-free

`run_simulation` / `_build_slot_configs` currently live in `ui/layout.py`, so a headless test
would drag in Solara/matplotlib. **Move them to `ui/sim.py` first** (the follow-up flagged
after Phase 5) so the harness has no UI dependency. Small, clean, prerequisite for this suite.

## Architecture

```
ui/sim.py                          # (step 0) run_simulation + _build_slot_configs live here
tests/regression/
  cases/*.json                     # the ~12 case configs (delta envelopes)
  golden.json                      # blessed baseline snapshot (committed)
scripts/run_regression.py          # run cases -> current snapshot + markdown report
tests/test_regression.py           # CI/pre-deploy: FAIL on any unblessed diff
```
- `scripts/run_regression.py` — runs all cases, writes the current snapshot, and a markdown
  **report** (case × metric: `golden | current | Δ`, changes highlighted).
- `--update` re-blesses `golden.json` when a change **is** intended; the commit records **why**
  (linking the code change) — the audit trail.
- `tests/test_regression.py` — the gate: compares current to golden, fails with a clear table
  of what moved.

## Release workflow

```
python scripts/run_regression.py            # snapshot + report
  → review report; classify diffs designed vs regression
  → if designed:  python scripts/run_regression.py --update   # re-bless + commit with rationale
  → if regression: fix the code
pytest tests/test_regression.py             # green gate before deploy
```

## Open items (review as we build)

- **Case 11 semantics** — confirm "EV charger journey" means the full **ICE→EV switch** (with
  gasoline externalities), vs. only the charging-load model. The suite should cover the full
  switch in at least one case.
- Final precision for rounding per metric (whole `$`; kWh/therms to 0.1?).
- Whether to capture intermediate years (e.g., yr-1, yr-5, yr-10, final) or only cumulative +
  final — start minimal, expand if a regression hides between snapshots.

## Out of scope (for now)

- Visual/screenshot regression of the UI (numbers only).
- Monte Carlo / uncertainty bands (deferred; keeps the suite deterministic).
