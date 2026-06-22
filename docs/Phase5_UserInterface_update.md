# WhyWatt — Phase 5 Development Spec: User Interface Update

**Status:** 🟡 OPEN — scoping/iterating.
**Follows:** Phase 4.5 (UI relocation, JC.1 simplification, gasoline social cost).
**Last updated:** 2026-06-22 — §3 vertical compression + §2 sticky topline band **delivered**
(§1 unified slider and §4 Plotly migration already closed in prior sessions).
**Driver:** Real advocates are now running sessions with the tool. The live simulation is
landing as the selling point; the friction is *interaction speed* and *vertical density*.

---

## 0. Why this phase exists

User feedback (advocates running homeowner sessions):

1. The **dynamic simulation** — topline metrics + graphs updating as you tune — is the
   selling point. **Preserve it at all costs.**
2. **"Your Electrification Journey"** and **"Solar + Battery"** are the most-tuned panels,
   but their size forces scrolling, and scrolling pushes the topline/charts out of view —
   so the user loses sight of (1) exactly when they're changing inputs. "Collapse all"
   helps but isn't enough.
3. Sliders work, but some users want to **type an exact number** — the slider is fiddly to
   land on a precise value.

Developer pain:

1. **Too much whitespace** around buttons and fields. The charts especially: the
   bottom legends (`_legend_below`, [charts.py:48](../src/ui/charts.py)) grow figure height
   by a band per legend row, exploding the page's vertical length.
2. Sliders feel **sluggish** (even with one user) and the slider design is **inconsistent**
   across panels (bare `SliderInt`/`SliderFloat`, `SliderWithDefault`, raw `InputInt`).

### Root-cause note (carry into design)

Every chart is **matplotlib → `solara.FigureMatplotlib`**. On each input change the server
recomputes *and* re-renders every visible figure to a PNG, then ships the raster over the
websocket. This is simultaneously (a) a chunk of the sluggishness and (b) the vertical-space
problem (legend band height). A future migration to `solara.FigurePlotly` (client-side
vector rendering, overlaid compact legends) is the highest-leverage fix for **both** the
sluggishness *and* the vertical bloat. It is therefore pulled **into this phase as step 2**
(before the holistic vertical-space review), because the charts are a dominant vertical
consumer and the page's total height — plus the sticky-band "do both charts fit?" decision —
can only be measured correctly once the charts are at their final Plotly height.

---

## Scope of THIS phase

Ordered as confirmed with the user:

| Order | § | Workstream | In this phase? |
|-------|---|------------|----------------|
| 1 | §1 | Unified slider: **debounce first**, then iterate design on ONE slider ("Climate Cost"), then roll out type-in + consistent component | ✅ **Done** |
| 2 | §4 | **Plotly chart migration** — sets charts to their final (shorter) height + improves responsiveness; must precede the vertical-space review | ✅ **Done** (11/17 charts) |
| 3 | §3 | Vertical-space compression + §2 sticky band — measured **after** Plotly: remove redundant lines, collapse headers, tighten gaps, accent borders, pin topline | ✅ **Done** |
| — | §2 | Sticky topline band — keep metrics (+ both charts) visible while tuning | ✅ **Done** (masthead + cockpit + both charts pinned) |
| ✔ | — | **Keep 2 charts side by side** (cost × consumption comparison) | ✅ Hard constraint — preserved |
| ✗ | — | Separate React front-end | ❌ Dropped for now |

> **Why Plotly before the vertical review:** the charts (×2, side by side) are a dominant
> vertical consumer. Matplotlib inflates height via the `_legend_below` band and a fixed PNG
> aspect ratio; Plotly overlays the legend in-plot and lets us set an exact container height.
> Reviewing total page height before the charts reach final height would mean measuring twice.
> Debounce (§1) stays first — it's chart-independent and the cheapest high-value win.

**Guard rails — do not break:**
- The live `use_memo(run_simulation, …)` reactivity in [layout.py:903](../src/ui/layout.py)
  must keep updating topline metrics + charts on input change. (Selling point #1.)
- **Keep the two charts side by side** ([layout.py:1158](../src/ui/layout.py)). The dual pane
  is a *key feature* — it lets the user compare along two axes at once (e.g. **cost** vs.
  **consumption**). Do not collapse to a single chart. This resolves the earlier "one hero
  chart vs. both" open question in favor of **both**.
- All existing `data/` contracts, model internals, and tests unchanged — this is a
  presentation-layer phase only.
- `grep -r "MMBtu"` stays empty; no device touches data files. (CLAUDE.md hard rules.)

---

## §1 — Unified slider component (debounce + type-in + consistency)

### 1.1 Problem

- **Sluggish:** every drag tick triggers a full `run_simulation` + re-render of all visible
  matplotlib figures. Dragging from 1→20 fires ~20 full recomputes.
- **Inconsistent:** the codebase mixes `SliderWithDefault` ([panels.py:30](../src/ui/panels.py)),
  bare `solara.SliderInt`/`SliderFloat`, and standalone `solara.InputInt`/`InputFloat`
  across panels. No single look or behavior.
- **No type-in:** users can't land an exact value quickly.

### 1.2 Deliverable — `SliderWithInput`

Build **one** reusable component and route *every* tunable numeric input through it. Use the
existing `SliderWithDefault` ([panels.py:30](../src/ui/panels.py)) as the structural template
(it already draws the default-tick marker and delta sub-line).

Required features:

1. **Slider + adjacent number box**, bound to the same reactive value. Slider for feel,
   number box for precision. Number box is compact (≤ ~64px), right-aligned, no spinner
   clutter.
2. **Commit-on-release / debounce.** The recompute must fire on **slider release** (or a
   ~150 ms debounce), NOT on every intermediate tick. While dragging, only the *label*
   updates locally; the model reruns once when the user lets go.
   - Implementation options to evaluate (pick the one that keeps reactivity clean):
     - A local "draft" reactive that mirrors the slider live, and a `on_end`/blur handler
       (or `use_effect` debounce) that pushes draft → the real reactive that
       `run_simulation` depends on.
     - Solara/ipyvuetify slider `continuous_update=False` if it reliably suppresses
       intermediate events in this version.
   - **Acceptance:** dragging a slider from min→max produces **one** `run_simulation` call,
     verified via a counter/log, not N calls.
3. **Type-to-set:** typing a number in the box and pressing Enter/blur sets the value
   (clamped to `[min, max]`, snapped to `step`) and triggers exactly one recompute.
4. **Default tick + delta** carried over from `SliderWithDefault` (keep `show_delta` flag).
5. **Consistent styling** — same height, label position, and spacing everywhere. Kill the
   per-call ad-hoc `style=` strings.

### 1.3 Design iteration — use ONE slider as the test bed

Before rolling `SliderWithInput` across the app, **iterate on the design using a single
slider**: the **"Climate Cost"** slider. Get debounce, the number box, spacing, and the
default-tick/delta presentation right on that one control — review it live — then freeze the
component and roll it out (§1.4). This keeps the visual iteration cheap and contained.

> Target: `social_climate_rate` / gasoline `climate_cost_per_gallon` Climate Cost control.
> (Confirm exact reactive when building — it lives in the Social & Health / gasoline panels,
> [panels.py](../src/ui/panels.py).)

### 1.4 Rollout

Replace, in [panels.py](../src/ui/panels.py) and [layout.py](../src/ui/layout.py), the
current call sites (non-exhaustive — grep `SliderInt|SliderFloat|InputInt|InputFloat`):
swap-year sliders (HVAC/WH/EV/panel/solar), model-length slider, solar panel count, amps
inputs, install/rebate cost inputs. Where a control is *pure* type-in (e.g. install $),
the number-only variant of the same component is used so the visual language stays uniform.

**Acceptance for §1:**
- One `SliderWithInput` (and a number-only sibling) is the only numeric-input primitive.
- Dragging any slider = 1 recompute on release.
- Every numeric field can be typed into directly.
- Visual: identical height/spacing across all panels.

> The unified component itself is fully specified in the companion
> **WhyWatt — Unified Slider Component Spec** (`WhyWattSlider` / `SliderSpec`,
> `src/ui/slider.py`). §1.5 below is the codebase audit that maps the *existing* sliders
> onto it and records the decisions made before coding.

---

## §1.5 — Migration audit: existing sliders → `WhyWattSlider`

Audit of every slider call site in the app, classified against the unified spec. Done
before implementation so the schema is frozen with the real edge cases in view.

### Inventory (what's actually in the app)

| Class | Sites | Maps how |
|---|---|---|
| **Detail floats** via `_DSl` → `SliderWithDefault` | **55 calls** ([panels.py:152](../src/ui/panels.py)) | Cleanest — already title/value/default-tick/delta. `dtype="number"`. The bulk. |
| **Standalone floats** | `wh_inlet_temp_f` (995), `wh_setpoint_f` (999), `solar_scf` (1557), `hvac_tonnage` (884) | `number` + unit (°F, %, ton). Direct. |
| **Gated rate floats** | `social_climate_rate` (1883), `social_health_rate` (1901) — checkbox-gated `SliderWithDefault` | `gated` layout + the **Climate Cost** design test bed. Clean. |
| **Model timeline** | `years` (803, 1747), `min=5` | `number`. Direct. |
| **Year sliders** (`dtype="year"`) | hvac/wh/ev/cooktop/dryer/baseload/panel swap-years + `solar_install_year` (~10 sites, some rendered 2–4×) | §3.4 year mode. Display flips from `Yr 3 (2029)` → `+3 yr · 2029 / now`. |

### The 4 outliers + resolutions

1. **`hw_daily_gallons`** ([panels.py:990](../src/ui/panels.py)) — `on_value=_set_gal` is a
   **side effect** that flips a second reactive (`hw_gallons_user_override=True`).
   → **Add optional `on_change` callback to the contract.**
2. **`solar_panels`** ([panels.py:718](../src/ui/panels.py), 1507) — label embeds a
   **derived readout** `Panels: 12 (4.8 kW)`. → **Add an optional `derived`/secondary slot**
   (or demote it to the faint unit position).
3. **`cagr` / `acc_cagr` rate sliders** ([panels.py:1724](../src/ui/panels.py), 1730) —
   **dynamic max** (`cagr_max`), no default tick today, long annotated titles.
   → **DECIDED: trim the title to fit**; the annotation ("EIA default — editable",
   "ACC shape applied on top") moves to the hover/help. **These gain a default tick.**
4. **`acc_shape_year`** ([layout.py:172](../src/ui/layout.py)) — year slider, base year =
   reactive `sim_start_year`, ungated, under a chart.
   → **DECIDED: max = the model timeline (`years.value`); it never exceeds the timeline.**
   `base_year` accepts the reactive `sim_start_year`.

### Two structural notes (state once, don't re-litigate)

- **Compound gating on year sliders.** Swap-year sliders show only when
  `state != "electric"` **AND** `*_swap_planned` is checked ([panels.py:875](../src/ui/panels.py)) —
  not a single checkbox. Resolution: **the caller computes `enabled`** (compound condition)
  and passes it in; `gate_label`'s built-in checkbox is reserved for the simple single-gate
  cases (the rate sliders).
- **Same reactive, multiple widths.** `ev_swap_year` renders in 4 places (356/416/481/1119)
  at different widths — a built-in stress test that the component must be width-agnostic
  across `stack`/`inline`/`gated`.

### Token mapping — spec `--ww-*` tokens don't exist yet

`SLIDER_TOKENS` names `--ww-*` vars that aren't in the CSS. The app namespace
([styles_redesign.css](../src/styles_redesign.css)) is `--ink`, `--ink-2/3/4`, `--journey*`,
`--mono`, `--accent*`. Map (no new hexes except the track):

| Spec token | Existing var |
|---|---|
| `title --ww-text-muted` | `--ink-3` |
| `value --ww-text-ink` | `--ink` (+ `--mono`) |
| `unit --ww-text-faint` | `--ink-4` |
| `delta --ww-text-muted` | `--ink-3` |
| `fill --ww-journey-blue-300` | `--journey-soft` / `--journey` |
| `thumb_border --ww-journey-blue-600` | `--journey-ink` |
| `tick --ww-text-faint` | `--ink-4` |
| `track --ww-track` | **no equivalent — add a `--track` var** (`--border-soft` as fallback) |

### Resolved spec ambiguities

- **`value` double-declared** (schema field §2 + contract param §5) → **contract param holds
  the reactive; the schema carries metadata only.**
- **Delta epsilon** → **`step/2`** (hide the delta when `abs(value−default) < step/2`).
  This is the *hide/show* threshold (the "is it changed?" test), NOT delta formatting —
  the displayed delta is still rounded to `decimals`. `step/2` gives clean "one step from
  default ⇒ delta appears" semantics and resists float-equality flicker that `step*0.01`
  is prone to.
- **Year-mode base** → `base_year` accepts the reactive `sim_start_year`, not a hardcoded
  2026.

### Iteration order (one representative per class, hardest last)

1. **Climate Cost** (`social_climate_rate`, gated float) — the test bed. Locks tokens, the
   `gated` layout, default-tick/delta, and the §5 thumb-alignment math.
2. **A plain `_DSl` float** (e.g. furnace AFUE) — validates the 55-case bulk + `stack`/`inline`.
3. **One swap-year** (`hvac_swap_year`) — validates `year` mode + compound gating + multi-width.
4. **The 4 outliers** — let them finalize the optional fields (`on_change`, `derived`,
   dynamic max, reactive `base_year`).

### Decisions locked during build (`src/ui/slider.py` — `WhyWattSlider` / `SliderSpec`)

Implemented and verified live on two test beds: **Climate Cost** (gated float) and **HVAC
swap year** (non-gated year). These supersede the earlier draft where they conflict.

- **Debounce = commit-on-settle via a context-carrying timer.** Slider + value field drive a
  live `draft` reactive (cheap label re-render per tick); the model reactive is committed
  ~180 ms after the last change, so a whole drag/type gesture = **one** `run_simulation`.
  The timer fires on a bare thread, so it re-attaches the session's kernel context
  (`solara.server.kernel_context.set_context_for_thread`) before `value.set()` — without this
  the per-virtual-kernel reactive never re-renders. Verified: dragging/typing updates the
  topline once on release.
- **Editable value field (the type-in half of §1).** Every value renders as an editable input
  (`solara.InputFloat`/`InputInt`, `continuous_update=False` → commit on blur/Enter), routed
  through the same debounce. A `disp` reactive holds the shown number; both slider and field
  write `draft`, and the slider reads `draft` as its thumb position, so **typing a value moves
  the thumb** and dragging updates the number. Entries are clamped to range and snapped to
  step. Styling: **light shaded fill, no box** (faint journey tint, deepens on hover/focus).
- **Gated layout = 3 lines:** `[circular checkbox + title]` / `[value … delta]` / `[track]`.
  The title gets its own line so it can be fuller (e.g. "Add CO₂ + Methane Cost"). Gate uses
  the app's circular `mdi-check-circle`. (⅓-width panels can't center the value beside the
  label without overlap — hence the dedicated value line.)
- **Year mode:** value shows the **calendar year** (e.g. `2027`); the field accepts a typed
  calendar year and converts to the internal 1–25 index (`base_year` = live `sim_start_year`).
  The delta chip is **shown** on the right edge as whole years from default (e.g. `+3 yr`,
  tooltip "from default (2027)"). *This overrides the earlier "suppress delta on year rows"
  note.*
- **Inline layout (detail panels):** `[label fixed-width, ellipsis + title tooltip]`
  `[track flex]` `[editable value]`. The **fixed label width is what aligns every track to the
  same start/length** down a column. Delta chip omitted in inline (the default tick on the
  track carries the "changed" cue). Long labels are shortened (e.g. "Central AC SEER" →
  "AC SEER") so they fit without truncation. Applied to **HVAC detail first** as the test bed.
- **Tokens:** `track` → `--border-soft`; value shade → faint journey tint; the rest per the
  §1.5 token table.

### ✅ Rollout complete (every slider on `WhyWattSlider`)

Final taxonomy — **3 layouts × 2 value types**, plus the gated variant:

| Layout | Used by |
|---|---|
| **gated** (3-line: checkbox+title / value · delta / track) | Climate, Health, gasoline Climate/Health externalities |
| **stack** (2-line: `title: value … delta` / track) | swap/install **year** sliders (summary + detail), via `_YSl` |
| **inline** (1-line: `label \| track \| value`, fixed-width label aligns tracks) | all detail number sliders, via the `_DSl` helper (now renders inline); CAGR escalation |

Helpers: `_DSl` (inline number, decimals derived from legacy `fmt`), `_HSl` (HVAC inline,
explicit decimals), `_YSl` (year), `_hp_size` (HVAC). Component gained an **`on_change`**
callback (used by `hw_daily_gallons` to set its override flag).

Exception resolutions as built:
- **`solar_panels`** — derived system size in the value **suffix** (`12 ≈ 4.8 kW`).
- **CAGR** (elec + gas) — inline `Escalation … %/yr`; **tick = per-fuel factory default**
  (`_DEFAULTS["{elec|gas}_cagr_pct_a"]`, resolved inside `_fuel_model_block` by fuel).
- **`acc_shape_year`** (chart, `layout.py`) — year slider, **dynamic max = model timeline**.
- **`hw_daily_gallons`** — inline + `on_change` override flag.

Alignment: a **label-shortening pass** (`EV miles/yr today → EV miles now`,
`Charging efficiency → Charge eff`, `After-upgrade always-on → After upgrade`, …) keeps every
inline track aligned with no truncation (96px label column, ellipsis + `title` tooltip as the
safety net).

**Exception left untouched:** Model Timeline (×2) keeps its 1-line raw `SliderInt` look,
per decision.

**Dead code removed:** the legacy `SliderWithDefault` component (and its raw
`SliderInt`/`SliderFloat` wrappers) deleted — no remaining callers. Only Model Timeline still
uses raw `solara.SliderInt`.

---

## §2 — Sticky topline band (preserve the selling point while scrolling)

### 2.1 Problem

Page order today ([layout.py:1151+](../src/ui/layout.py)):
`Masthead → Cockpit (topline) → dual charts → series-key strip → BottomZone (Setup + Journey)`.
The tuning panels (Journey, Solar) live in `BottomZone`, **below** the charts. Scrolling down
to tune scrolls the Cockpit + charts off-screen → the user can't see the impact of their
change. This is the #1 user complaint.

### 2.2 Deliverable

Keep the **Cockpit topline metrics + one hero chart** pinned in view while the user scrolls
the tuning panels.

- Wrap the Cockpit topline metrics in a **sticky container**
  (`position: sticky; top: 0; z-index:` above the scroll body) so the savings/payback numbers
  stay at the top of the viewport as `BottomZone` scrolls underneath.
- **The two side-by-side charts are preserved** (see guard rails). Decide during build whether
  the sticky band carries *both* charts too, or *metrics only* with the dual charts scrolling
  just below — driven by how much height §3 compression frees up. **Default lean:** metrics +
  both charts sticky if they fit a compact 1080p viewport; otherwise metrics-only sticky and
  the two charts immediately below. **Never** drop one of the two charts to make room.
- On short viewports, the band must not eat the whole screen — cap its height; let the chart
  figures shrink (easier once §4/Plotly lands; for now, a fixed compact matplotlib height).

### 2.3 Iteration notes (decide during build, with screenshots)

- Sticky band = **metrics + both charts** vs. **metrics only** (both charts scroll just
  below). Tension with §3 vertical budget — resolve with screenshots. Both charts always stay;
  the only question is what's pinned.
- Does the series-key strip belong in the sticky band or get removed entirely (see §3.1)?
- Confirm sticky behavior works inside Solara's column flow (may need an explicit scroll
  container rather than page-level scroll).

**Acceptance for §2:** while tuning a Journey/Solar control near the bottom of the page, the
topline savings/payback numbers and the hero chart remain visible and update live.

### ✅ Delivered (2026-06-22)

- **Sticky band = Masthead + Cockpit + BOTH charts**, wrapped in a `.sticky-top`
  container ([layout.py](../src/ui/layout.py), `position:sticky; top:0; z-index:50`,
  solid `--bg` background + soft bottom shadow). Both charts pinned (the user chose full
  charts over metrics-only). Reactivity unchanged — the pinned charts update live as panels
  below are tuned.
- **Scroll context confirmed:** the page scrolls inside an inner `overflow:auto` container,
  not page-level. The `.app` flex column is nested inside that scroller and spans full content
  height, so a sticky child pins correctly to the scroller viewport (verified: after scrolling,
  `.sticky-top` top = 0).
- **Band height ≈ 591px** at 1366×900 (masthead 59 + cockpit 124 + both charts + gaps).
  Comfortable on 1080p+ (the real target); on a 900px laptop it leaves ~310px of panel scroll.
  Capping/shrinking charts when pinned is left as a future option if small screens matter.
- **Detail-dock visibility fix (new issue surfaced during build):** the `DetailDock` renders
  in one fixed spot just below the charts, but its triggers live in panels far down the scroll.
  Opening one while scrolled left the editor hidden behind/above the taller sticky band.
  Fix = a small **`_DockScroller` anywidget** mounted inside the dock, **keyed to the open
  device** so it fires once per open (not on every slider re-render); on mount it smooth-scrolls
  the dock to sit ~12px below the pinned band. Verified: opens into view; does **not** re-scroll
  on slider re-renders.
- **Series-key strip** decision (§3.1) resolved in favor of removal — the in-plot Plotly A/B
  legend carries the key.

---

## §3 — Vertical compression (iterate with screenshots)

Goal: reclaim vertical space without losing legibility. Make panels **denser** and
**delineate** them with accented borders instead of relying on whitespace separation.

### 3.1 Remove / merge redundant lines

- **Series-key strip** ("● Do nothing (A)  ● Your journey (A)  …  *Adjust the scenario
  below*", [layout.py:1192](../src/ui/layout.py)). The same legend is (or will be) inside the
  chart. **Decision needed:** remove it entirely, or fold the scenario eyebrow into a chart
  corner. Default recommendation: **remove**, rely on the in-chart legend. (Confirm once
  Plotly legends land; for matplotlib, ensure the chart still carries the A/B key before
  removing the strip.)

### 3.2 Collapse "Setup your home" + panel headers to a single line

- The Setup group header ([layout.py:839](../src/ui/layout.py)) currently renders a full
  row: icon + "Setup your home" + a long `<span class='scope'>—  Home, Panel & Solar,
  Energy & Prices, Social & Health collapse together</span>` + Collapse-all button.
  - **Shorten the scope text** (it's a full sentence). A short hint or a tooltip suffices.
  - When **all collapsed**, the group should compress to a **single chip-row line**
    (the `collapsed-all` CSS path already exists, [layout.py:827](../src/ui/layout.py)) — make
    that the genuine 1-line state: header + three collapsed chips inline.
- Per-card `_SetupCard` headers ([layout.py:790](../src/ui/layout.py)) and the `JourneyGrid`
  header ([layout.py:866](../src/ui/layout.py)): tighten `card-hd` padding; the chevron +
  help button row should be a single tight line (currently 14px h3 + padding).

### 3.3 Tighten inter-component spacing

Audit and reduce the vertical gaps (do NOT make it cramped — target consistent ~6–8px):

- Top-level page column `gap="10px"` ([layout.py:963](../src/ui/layout.py)) → evaluate 6–8px.
- `_HomeBody`/`_EnergyBody` `gap="8px"`, `jbody`, `card-bd` paddings.
- Vuetify form-margin suppressors already exist ([layout.py:996+](../src/ui/layout.py)) —
  extend the same `margin:0` treatment anywhere new whitespace shows.
- The `SliderWithInput` from §1 must itself be vertically compact (the current
  `SliderWithDefault` adds a 6px tick div + a delta sub-line — keep but tighten).

### 3.4 Accented panel borders

Replace whitespace-based separation with **visible delineation**:

- Give each card (`.card`, `.setup-group`, `.jgrid` cells) a slightly stronger border /
  left accent stripe (tie to existing theme colors — `C_NAVY`, accent-soft) so panels read as
  distinct blocks even when packed tightly.
- Define in [styles_redesign.css](../src/styles_redesign.css) /
  [layout_v2.css](../src/layout_v2.css) — keep CSS in the stylesheets, not inline, where
  practical.

### 3.5 Iteration protocol

This section is explicitly **iterative**. For each change:
1. Make the edit.
2. Run the app (`solara run src/app.py`) and capture a before/after screenshot via the
   preview tooling.
3. Review density vs. legibility with the user; adjust.

**Acceptance for §3:** measurable reduction in total page height (target: the
Cockpit + charts + at least the Journey panel header visible without scrolling on a
1080p viewport), panels clearly delineated, nothing cramped or clipped.

### ✅ Delivered (2026-06-22)

Done in reviewable steps (screenshot-evaluated by the user between each). All edits in
[layout.py](../src/ui/layout.py) inline CSS + [layout_v2.css](../src/layout_v2.css).

- **§3.1 — series-key strip removed.** The redundant `● Do nothing (A) ● Your journey (A) …
  Adjust the scenario below` row deleted; the migrated Plotly comparison charts carry the
  in-plot A/B legend.
- **§3.2 — Setup header + card headers.** Scope sentence → short hint `— your starting
  assumptions` (full text in a tooltip); `setup-group` padding `16 → 12/14`, gap `14 → 10`.
  **All-collapsed is now a true single line** (header + 3 chips inline; group `120 → 80px`) —
  required `flex-direction:row` keyed off `.setup-group.collapsed-all` (note: the element is
  `.v-sheet`, **not** `.v-col`, so the inline `.v-col.*` overrides were dead). Global
  `card-hd` padding `13/16 → 8/14`, icon `26 → 24` → every card header `53 → 41px`.
- **§3.3 — spacing pass.** Page column gap `10 → 7`; `card-bd` padding `16 → 11/13`; Journey
  `jbody` padding `16 → 9/11` and row-gap `12 → 7` (the row-gap needed `gap="7px"` on the
  `solara.Column` — Solara injects a default inline `gap:12px` that beat the stylesheet).
- **§3.4 — delineation.** All card borders `--border → --border-strong`; **bold grey 4px left
  accent stripe** (`--ink-2`, via a `lstripe` class) on the two most-tuned blocks — the
  Journey card and the Setup group.
- **Journey panel labels folded (user request).** In-body `Major Loads` / `Other Appliances`
  jrow-labels removed; `Major Loads` reframed as a light-grey `— Configure Major Loads`
  subtitle in the panel header. (`.jrow-label` CSS now dead — optional future cleanup.)

**Net:** full page height **2240px → 2077px (−163px, ≈7%)** at 1366-wide, measured before the
§2 sticky band; panels clearly delineated, nothing cramped.

> **Tooling note for future CSS work:** `layout_v2.css` / `styles_redesign.css` are read **once
> at Python import** ([theme.py:17](../src/ui/theme.py)). A browser reload alone uses the stale
> copy — a `.css`-only edit needs a Solara module reload (touch a `.py`) or server restart to
> take effect. `.py` edits hot-reload normally.

---

## §4 — Plotly migration (IN THIS PHASE — step 2, before the vertical review)

Port `make_*(df, model, n)` builders in [charts.py](../src/ui/charts.py) to
`solara.FigurePlotly`. Client-side vector rendering, legend overlaid inside the plot
(reclaims the `_legend_below` vertical band — §0 / §3), explicit compact heights. Dual-pane
stays ([layout.py](../src/ui/layout.py)); reactivity unchanged (ChartPane rebuilds the figure
on every committed input change).

### Where the vertical whitespace comes from (the target)

1. **`_legend_below`** ([charts.py](../src/ui/charts.py)) — used by **13 of 17 charts**; it
   *grows the figure height* by `0.50 + 0.26·nrow` inches to park the legend below the axes.
2. **Tall fixed figsizes** to make room for it — JC.1 `6×4.3`, **R.3 `7×6`**, JC.5 `9.5×4.2`.

### Chart inventory & complexity

| Code | Chart | Builder | Type | Bucket |
|---|---|---|---|---|
| **JC.1** | Cumulative Energy Costs | `make_cumulative_opex` | multi-line + payback + fill | ✅ **migrated (pilot)** |
| JC.2 | Annual Cost by Year | `make_annual_cost` | bars/line | Easy |
| JC.3 | Cost Breakdown by Category | `make_cost_breakdown` | stacked bar | Moderate |
| JC.4 | Equipment Replacements (CapEx) | `make_capex_v2` | marker timeline | Moderate |
| JC.5 | Journey Timeline | `make_journey_timeline_v2` | custom year-rail + connectors | **Hard** |
| JC.6 | Estimated Electrical Load | `make_panel_load_timeline` | line/area | Easy–Mod |
| EU.1/2 | Energy Cost / Use by Device | `render_device_chart` | grouped bars + device legend | Moderate |
| EU.3/4 | Annual kWh / Gas by Device | `make_annual_kwh` / `make_annual_gas` | bars | Easy |
| (—) | Annual Gasoline by Vehicle | `make_annual_gasoline` | bars | Easy |
| EU.6 | Energy Mix Timeline | `make_energy_mix_timeline` | stacked area | Moderate |
| EU.7 | HVAC Monthly Energy | `make_hvac_monthly` | monthly bars | Easy |
| R.1/R.2 | Electric / Gas CAGR Projection | `make_elec_price` / `make_gas_price` | line | Easy |
| R.3 | ACC Rate Projection | `make_rate_trajectory` | multi-subplot + bands | **Hard** (tallest) |
| R.4 | Electricity Rate Shape | `make_acc_rate_shape` | band + seasonal lines | Moderate |

### House style — LOCKED by the JC.1 pilot

Helpers in [charts.py](../src/ui/charts.py), reused by every chart:
- **`_pl_layout(height, ytitle, xtitle, money_y)`** — transparent paper/plot bg, tight margins
  (`l58 r14 t16 b34`), `hovermode="x unified"`, grid only on y (`_CC_GRID`), `$`-prefixed
  money y-axis, ticks at 10px.
- **`_rgba(hex, a)`** — theme hex → translucent fill (e.g. the savings band).
- **Legend = compact *vertical* legend in the empty top-left corner** (semi-transparent
  `rgba(255,255,255,0.55)`, 9px). *Deviation from the original "horizontal top" idea:* a
  horizontal top legend **clipped** with 4 series and overlapped the high lines at top-right,
  so vertical-top-left is the locked default. Per-chart override allowed where the corner
  holds data.
- **Height 300px** for JC.1 (down from ~490px raster + band). Per-chart heights set explicitly.
- **`solara.FigurePlotly`** requires **`anywidget`** — both added + pinned in
  [requirements.txt](../requirements.txt) (`plotly>=6.0`, `anywidget>=0.9`).
- **Mixed rendering during rollout:** **`_render_fig(fig)`** in
  [layout.py](../src/ui/layout.py) dispatches Plotly vs matplotlib by `fig.__class__.__module__`,
  so charts migrate one at a time with no big-bang switch.

### Rollout order / status

1. ✅ **JC.1 Cumulative Energy Costs** (line pilot) — height 300px, savings fill, payback
   marker, A/B + social series. Every-year ticks (`xdtick=1`), centered x-title, app font.
2. ✅ **JC.5 Journey Timeline** (Hard #1) — custom year-rail: marker+text badges (filled
   journey / open do-nothing), dashed connectors, positioned cost/side annotations, hidden
   y-axis, device legend, native hover. Reused the infra with no new plumbing.
3. ✅ **JC.4 Equipment Replacements** (bar pilot) — grouped **and** stacked bars
   (`offsetgroup` + `barmode="stack"`), hatched do-nothing (`marker.pattern`) vs solid
   journey. **Legends + net banner rendered as an HTML header above the bars**, not Plotly
   legends (see pattern note below).
4. ✅ **Easy (8):** JC.2 (grouped+stacked bars), JC.6 (step line `line_shape="hv"` + fill +
   capacity hline + activation markers/labels), R.1 / R.2 (price lines, `$`-prefixed
   `.2f` axis), EU.3 / EU.4 (per-device stacked bars + empty-state), Annual Gasoline
   (bars + empty-state), EU.7 (month-**category** x-axis, stacked heat/cool + title).
   All smoke-tested headless + verified rendering, fitting the pane, no errors.
   Helper added: `_pl_empty(msg)` for placeholder figures.
5. ⬜ **LEFT FOR MANUAL ITERATION (the 3 hard features, 6 charts):**
   - **Stacked area** → JC.3 (Cost Breakdown), EU.1 / EU.2 (device cost/use), EU.6 (Energy Mix)
   - **Subplots** → R.3 (ACC Rate Projection)
   - **Heatmap + colorbar** → R.4 (Electricity Rate Shape)

   These remain matplotlib and render fine via the `_render_fig` dispatcher (mixed
   Plotly/matplotlib coexistence verified). **11 of 17 charts are now Plotly.**

**Patterns now proven** across the three pilots: lines (fill, vline+annotation, A/B),
custom-marker timelines (badges, connectors, annotations, hidden axis), and grouped+stacked
bars (patterns, multi-part legend, stats banner). Everything remaining is a combination of
these.

### Hard-won layout rules (apply to all charts)

- **Responsive sizing:** Plotly's `FigureWidget` pins to ~700px and clips; `_FigurePlotlyResponsive`
  + the `_PlotFitter` anywidget observer fit every plot to its pane. (Done; automatic.)
- **Narrow ⅓-panes → vertical corner legends, NOT horizontal strips.** Horizontal legends
  *wrap* in the narrow pane, and Plotly's automargin then grows the top margin and **squishes
  the plot** (seen on JC.1 and JC.4). Use vertical overlay legends in a corner.
- **Rich legend/banner layouts → render as an HTML header above the Plotly figure**
  (JC.4 = `make_capex_header()` in [charts.py](../src/ui/charts.py) + a ChartPane branch in
  [layout.py](../src/ui/layout.py); the Plotly figure is bars-only). HTML/CSS stacks the
  stacked legends + full-width bordered banner cleanly and stays responsive, where Plotly's
  own legend/annotation placement fights the narrow pane. **Reusable for JC.3 / EU.6** if they
  want the same treatment.

Open polish items: x-axis ticks every year may crowd at n=30 (acceptable per decision);
JC.1 legend lists dotted `+soc` lines before the solid ones (could reorder).

### Dropped for now — separate React front-end

Revisit a separate React front-end **only** if Plotly-in-Solara proves insufficient — for
now it's high-cost / low-marginal-benefit (would require a new API layer and reimplementing
the live reactivity that is the product's selling point).

---

## Build order (confirmed)

1. **§1 debounce** — implement commit-on-release first (biggest perceived-speed win,
   logic-isolated, low risk).
2. **§1 slider design iteration on the "Climate Cost" slider** — get the number box, spacing,
   tick/delta right on that one control, review live, then freeze `SliderWithInput`.
3. **§1 rollout** — apply the frozen component (+ type-in) across all panels.
4. **§4 Plotly migration** — pilot one chart, lock the house style, roll out chart-by-chart.
   Both charts stay side by side; set explicit compact heights. This brings the charts to
   their **final height** so the next step can be measured once.
5. **§3 vertical compression + §2 sticky band** — now done against final chart sizes:
   - §3.1 / §3.2 — remove/merge redundant series strip (de-risked: Plotly now carries the
     in-plot A/B legend), collapse "Setup your home" + headers to single lines.
   - §2 sticky topline band — pin metrics (+ both charts if they now fit). **Two charts side
     by side preserved throughout.**
   - §3.3 / §3.4 — final spacing pass + accented panel borders, iterating with screenshots.
6. React — **dropped for now.**

> Chart-independent §3 tidy-ups (collapsing the "Setup your home" header, panel gaps) may be
> pulled forward opportunistically if you want visible progress before Plotly lands — but the
> *total* vertical-space review and the sticky-band sizing wait until after step 4.

---

## Definition of done (Phase 5 core)

- [x] Dragging any slider triggers exactly one `run_simulation` (verified). *(§1)*
- [x] Every numeric input is directly type-able; all sliders share one component + style. *(§1)*
- [x] Topline metrics (and the dual charts where height allows) remain visible while tuning
      Journey/Solar panels. *(§2 — masthead + cockpit + both charts pinned)*
- [x] The two charts stay side by side (cost × consumption comparison preserved).
- [x] Redundant series-key strip resolved (removed). *(§3.1)*
- [x] "Setup your home" collapses to a true single line; panel headers are single-line tight.
      *(§3.2)*
- [x] Page height measurably reduced (−163px / ≈7%); panels delineated by accented borders +
      grey accent stripes, not whitespace. *(§3.3 / §3.4)*
- [ ] Live simulation reactivity intact; existing tests green; no `MMBtu`; data contracts
      unchanged. *(reactivity verified live; run test suite before phase close)*
