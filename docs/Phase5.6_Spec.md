# WhyWatt — Spec 5.6 (Feedback Round)

> **⛔ SUPERSEDED (2026-09-07) — folded into `docs/Phase6_Spec.md`.** The 5.6 items now live in
> Phase 6 WS3: #2 (CO₂/CO₂e chart) → §3b, #3 (grid-mix Help table) → §3c, #4 (per-pane scenario
> toggle) → §3d, #1 (HVAC tonnage, needs per-zone design temps) → §3e. #5 (match y-axis scales)
> stays tabled; #6 (consolidate "Plan" buttons) stays deferred to Phase 7. This file is kept as the
> feedback-triage record; do not implement from it — implement from Phase 6.

**Status:** ⛔ SUPERSEDED by `docs/Phase6_Spec.md` (was: 🟡 DRAFT feedback triage ahead of Phase 6).
**Last updated:** 2026-08-20 (superseded 2026-09-07)
**Scope rule:** Minor update. **Do not touch the primary data pipeline** (climate DB, rate
build, model simulation). If an item needs a pipeline change, it is pushed to **Phase 6**.

Primary feedback source: `docs/feedback/richfein-feedback.txt` (Rich Fein, E&E Action Team).

---

## Triage summary

| # | Item | Decision | Target |
|---|------|----------|--------|
| 1 | Auto HVAC tonnage from home size | Needs per-zone design temps in climate pipeline | **Phase 6** |
| 2 | CO₂ / CO₂e emissions graph | Display-only view over existing history arrays | **5.6** |
| 3 | Per-state electricity-mix Help table (clean vs fossil) | Documentation reference, CA first | **5.6** |
| 4 | Independent Do-nothing / Your-journey toggle per graph pane | Simple UI-state scoping fix | **5.6** |
| 5 | Match y-axis scales across the two panes | Tabled — see note | **Not implemented** |
| 6 | Consolidate all "Plan" buttons into one row at top of Journey panel | **Decided: defer to Phase 7 to revisit** | **Phase 7** |

---

## 1 — HVAC tonnage → deferred to Phase 6

Request (feedback line 26): auto-size HVAC "tonnage" from home size so users need not know it.

**Key finding:** In WhyWatt's degree-day model, tonnage (capacity) does **not** affect annual
energy — annual energy = `UA × degree-days / efficiency`; capacity is a peak/design-day
concept. Tonnage would only drive (a) a credibility/narrative number and (b) optionally scaling
HVAC install cost with home size.

**Why Phase 6:** the rigorous derivation is `design load = UA × design_ΔT; tons = load/12,000`,
which reuses the existing `UA` (already scales with sq ft + insulation) but needs a per-zone
**design temperature** (99% heating / 1% cooling). The climate DB (`tmy3_zones.json`) currently
has only monthly HDD/CDD/inlet/avg — **no design temps**. Adding them touches the climate
pipeline → Phase 6 (aligns with its "build the seams for new data" theme).

- AC & Heat Pump HVAC → tons (12,000 BTU/ton), sized on cooling load in mild CA — same table.
- Furnace → BTU/hr output (heating), then ÷ AFUE.

---

## 2 — CO₂ / CO₂e emissions graph (5.6)

Request (feedback lines 19–22): a straight CO₂/CO₂e calculation, not only social cost.

**Data already exists** (per home, journey + baseline): `gas_therms_history`,
`gasoline_gallons_history`. This is a display conversion only — **no simulation change, golden
untouched** (same posture as the kWh-equivalent charts).

**Emission factors (display-only constants):**

| Source | CO₂ (combustion) | CO₂e |
|--------|------------------|------|
| Natural gas | 5.30 kg/therm (EPA) | **combustion + upstream methane leakage** (see below) |
| Gasoline | 8.89 kg/gal (EPA tailpipe) | tailpipe + trace CH₄/N₂O (no upstream refining) |

**Decision — gas CO₂e includes upstream leakage** (directly derivable from therms):
```
combustion 5.30  +  (~1.93 kg CH₄ burned/therm × 2.3% leakage × 28 GWP100 [AR5]) ≈ 1.24
gas CO₂e ≈ 6.5 kg CO₂e/therm
```
Expose **leakage rate (2.3%)** and **GWP100 (28)** as named, documented constants (consistent
with the app's existing "~2% CH4 leakage" social-cost note in `social_cost.py`).

**Known asymmetry (accepted, must be labeled):** gas carries upstream leakage; gasoline stays
tailpipe (no well-to-wheel refining uplift). Revisit if symmetry is wanted later.

**Electricity excluded — with an honest caveat.** The journey home electrifies, so this chart
will trend its emissions toward ~zero while do-nothing stays high. That **overstates** the true
net reduction, because the replacement electricity has an uncounted grid footprint. The chart
must carry: *"Journey electricity that replaced gas/gasoline has a grid-carbon footprint not
counted here — actual net reduction is smaller and depends on grid intensity."* Grid-carbon
modeling of that electricity is **Phase 6/7**.

**Chart design:** new menu entry "Direct Emissions (CO₂ / CO₂e)"; Journey↔Do-nothing toggle
(reuse `device_chart_home` pattern); CO₂/CO₂e metric toggle; stacked bars by source
(Gas + Gasoline); y-axis in metric tons CO₂e/year; grey footnote with the electricity caveat.

---

## 3 — Per-state electricity-mix Help table (5.6)

Version 1: a static reference table in the **Help** docs giving each state's electricity mix
(clean/carbon-free vs fossil), so users can interpret the "electricity not counted" caveat from
item 2. **Start with California.** Not wired into the model.

- Vehicle: generated fragment (e.g. `docs/help/_generated/grid_mix.md`) built from a small
  committed `data/grid/state_mix.json`; CA row first, schema general enough to add states later.
- Columns: Clean/carbon-free % (solar, wind, hydro, nuclear, geothermal, biomass) vs Fossil %
  (natural gas, coal); + year + source.

**OPEN DECISION — source.** Raw **CAISO** fuel-mix is *in-state generation, excludes imports*
(~20–25% of CA supply, dirtier on the margin) → overstates cleanliness. The **CEC Power Content
Label** is *consumption-based, includes imports* — arguably the more honest "behind my plug"
figure. Recommendation: lead with CEC Power Content Label, corroborate with CAISO in-state.
User referenced CAISO; confirm which to headline.

---

## 4 — Independent scenario toggle per graph pane (5.6)

Request (feedback lines 33–35): show the same chart in both panes, one Do-nothing and one
Your-journey. Today both toggles move together.

**Root cause:** one global reactive `device_chart_home` ([state.py:185](../src/ui/state.py))
is read/written by both panes via the shared `ChartPane`. The toggle widget
`_toggle_buttons(active_rv)` is already parameterized.

**Fix (mirror the `chart_left`/`chart_right` twin pattern):**
1. `state.py` — split into `device_chart_home_left` / `device_chart_home_right` (+ reset).
2. `data/config/whywatt_default.json` — add the two keys.
3. `config.py` — swap them into `SHARE_EXCLUDE`.
4. `layout.py` — `ChartPane` gains a `home_rv` param; left/right calls pass their reactive.

No chart-builder / model / data / golden change. **Optional nicety:** default the right pane to
`"baseline"` so the Journey-vs-Do-nothing comparison lands out of the box.

---

## 5 — Match y-axis scales across panes — NOT IMPLEMENTED (tabled)

Request (feedback line 37): make the two panes' vertical scales match for valid comparison.

**Decision: tabled for now; not implemented.** In most cases the scales are already effectively
the same, so the payoff is marginal against the work.

For the record, if revisited: each pane is an independent Plotly figure, and Plotly's native
`yaxis.matches` can't sync across separate figures — matching would require each per-home builder
to compute a common range across *both* homes and fix `yaxis.range`. Feasible and self-contained
(no pipeline/golden impact), touching ~7 per-home builders. Trade-off: fixing to the larger
scenario leaves empty headroom when viewing the smaller (journey) home alone.

---

## 6 — Consolidate "Plan" buttons into one row — DEFERRED to Phase 7

**Decision (2026-08-20): deferred to Phase 7 to revisit** — alongside the Solar/Battery/Panel
redesign, when a unified plan-row can be coherent. Analysis retained below for that revisit.

Request (feedback line 73): put device on/off toggles at the top of the settings so users can
gauge each upgrade's impact without scrolling; open only the selected panels. Use case: simpler
for folks doing only 1–2 upgrades.

**Current mechanism (already exists):** every device has a `*_planned` reactive
(`hvac_swap_planned`, `wh_swap_planned`, `dryer_swap_planned`, `cooktop_swap_planned`,
`ev_swap_planned`, `baseload_swap_planned`, `panel_upgrade_planned`, `solar_planned`). The
`_PlanCheck` circle-checkbox toggles it, which both includes/excludes the device in the sim and
reveals its year+cost sub-fields inline; unplanned cards collapse to "No swap planned." So the
1–2 upgrade case is *already* handled decently.

**Layout facts:** the 6 appliance cards are a tuned 2×3 grid inside the Journey panel
([layout.py:1117](../src/ui/layout.py)); Solar+Battery and Electrical Panel live in a **different
zone** ([panels.py:1842/1858](../src/ui/panels.py)).

**Challenges (all valid):** (1) Phase 7 redesigns Solar/Battery/Panel → wiring them into a unified
row now is throwaway; (2) the only good home is the top of the Journey panel, but Solar/Panel
would have to be relocated across zones to join it; (3) the vertical fit is held by heavy
`!important` CSS + a fixed 2×3 grid — conditional show/hide is the most likely thing to break it.

**Recommendation: defer to Phase 7**, when Solar/Battery/Panel are redesigned and can share the
Journey zone — only then is a unified plan-row coherent. Doing it now yields a split-brain UX
(some devices in the row, three not) plus rework. **Fallback for 5.6 (Option B):** an
appliance-only quick-toggle row bound to the existing `*_planned` reactives; keep all cards
visible (do **not** hide unselected — hurts discoverability and breaks the grid); dim, don't
remove, if emphasis is wanted. Low effort, low risk, no Phase-7 entanglement.
