# WhyWatt Phase 3 — UI Redesign (Reskin)

## Context

WhyWatt is a home electrification cost simulator (Python 3.11+, Mesa 3.x, Solara
/ ipyvuetify-Vuetify2, Matplotlib). Run: `.venv/Scripts/solara.exe run src/app.py`.
Tests: `.venv/Scripts/python.exe -m pytest tests/`.

This objective applies a **high-fidelity visual redesign** to the existing UI. It is a
**reskin, not a logic rewrite**. The simulation engine and all computation stay byte-identical.

**Design source (read first):**
`docs/HES-design/whywatt/design_handoff_whywatt_dashboard/`
- `README.md` — full spec + a Solara implementation guide (read fully)
- `styles.css` — the design system (tokens + every component class) — **primary reference**
- `index.html` — dashboard markup / structure
- `detail.js` — device-details modal content + behaviors
- `help.js` — help popover positioning + content registry
- `charts.js` — SVG chart *mocks* (do NOT port; restyle our real charts instead)

**Branch:** all work on `phase3-ui-redesign` (already created). `main` stays shippable.

---

## Locked Decisions (override the handoff where they differ)

1. **Keep Matplotlib — do NOT migrate to Plotly.** The handoff repeatedly says "keep
   Plotly" — that is **wrong for this codebase**; our 8 charts use
   `solara.FigureMatplotlib`. Restyle the existing Matplotlib figures with the design's
   color tokens and typography (see Deliverable 6). No chart logic rewrite.

2. **Adopt the modal for Device Details.** Replace the current inline "bottom-zone" detail
   (`BottomZone` swapping deck ↔ `DetailView`) with a centered modal dialog
   (`solara.v.Dialog`) opened by each device's `⋮` button; the control deck stays visible
   behind a scrim. Reuse the existing `*Detail()` content components inside the dialog.

3. **Preserve the existing logo.** Use `docs/assets/whywatt_logo.svg` (via the existing
   `_read_svg(_WHYWATT_LOGO)`) in the masthead brand slot — do NOT use the handoff's
   inline house-bolt SVG. Keep the "Why**Watt?**" wordmark text beside it per the design.

4. **Keep the existing help pipeline.** `help_content.md` → `build_help.py` →
   `help_content.py` + HTML pages stays. Our `HELP_POPUPS` keys are a superset of the
   handoff's 7 keys. Only restyle the popover card (Deliverable 8); do not replace the
   content system. Map design `data-help` keys to our keys (see Deliverable 8).

5. **Do not touch** `model.py`, `journey.py`, `devices/`, `rate_loader.py`,
   `panel_assessor.py`, `social_cost.py`, `home_config.py`. All reactive state and
   `run_simulation()` stay; only presentation components change.

---

## Build Order & Deliverables

Follow the handoff's suggested order. Commit after each deliverable.

### Deliverable 1 — Inject the design system CSS

- Copy `styles.css` to `src/styles_redesign.css` (or read from the design folder at a
  stable path). Inject once at the top of `Page()`:
  ```python
  from pathlib import Path
  _CSS = Path(__file__).with_name("styles_redesign.css").read_text(encoding="utf-8")
  @solara.component
  def Page():
      solara.Style(_CSS)
      ...
  ```
- Fonts: keep the Google Fonts `@import` in the CSS (acceptable; falls back to system
  fonts offline). Optional: self-host later.
- Wrap the app body in a container that can carry theme attributes if you keep the
  optional theming layer (`data-tone`/`data-palette`/`data-density`) — otherwise omit
  the theming layer (it's "not core to the product" per the handoff).
- After this step, the page may look partially restyled where class names already match;
  that's expected. Verify the app still boots.

### Deliverable 2 — Masthead

Replace the current header row with the design `.app` → masthead structure
(`index.html` lines for `.brand`, `.context`, actions):
- **Brand:** existing `whywatt_logo.svg` in the `.brand-mark` slot + "Why**Watt?**"
  wordmark (`.brand-name`). Single line.
- **Context strip:** the bordered one-line pill with spec items fed from `HomeConfig`
  (location, ZIP, CZ, beds, sqft, year built, baseload). Build via `solara.HTML`. Reuse
  the existing `HomeInfoBar` data; render into the `.context` markup.
- **Actions:** "Reset to defaults" (`.btn`) + "Help" (`.btn.primary`, `data-help="about"`).
  Keep the existing `reset_to_defaults` and `open_help("index.html")` wiring; restyle.

### Deliverable 3 — Verdict band (hero)

New `solara.HTML` section (`.verdict`) fed by the same numbers `SummaryStats` computes:
- Two bars: "Your Electrification Journey" (journey gradient) and "Do-Nothing Baseline"
  (baseline gradient), widths proportional to the two 20-yr cumulative costs, `$` values
  in mono.
- Right `.verdict-call` panel: PAYBACK eyebrow + headline ("Payback year N (YYYY)" or
  "No payback within N yrs") + big net figure (`+$X` green / `−$X` red) + foot line.
- Compute payback/net exactly as `SummaryStats` already does (reuse that logic; you may
  refactor `SummaryStats` into a data function + this HTML view).

### Deliverable 4 — Electrical Load strip (single line)

Restyle the existing `PanelLoadCallout` into the `.load-strip`/`.load-line` single-row
layout:
- Title chip + "Estimated Electrical Load" + `?` (`data-help="load"` → our `panel_assessment` key).
- Two metric blocks: **Current Load** (`Year 1` amps + "% of NNN A panel") and
  **Journey Peak Load** (peak amps + status badge + "peaks Yr N · Device").
- **Threshold class** from peak amps: `<100A` → `peak-ok` (green), `≥100A` → `peak-warn`
  (amber), `≥200A` → `peak-danger` (red). Compute in Python; render the class into the HTML.
- Data comes from the existing `PanelAssessor.journey_load_timeline(...)`.

### Deliverable 5 — Control deck (3 columns)

Restyle the existing `SummaryView` 3-column deck to the `.deck`/`.card`/`.device` design:
- **Col 1 "Your Electrification Journey":** device cards (HVAC, Water Heater, EV — and keep
  Cooktop, Dryer, Panel, Baseload as the codebase has them; the design shows 3 but our app
  has more — keep all, styled as `.device` cards). Each: header + `⋮` (opens modal),
  fuel `<select>`, plan-year slider, include checkbox, Install/Rebate/Net row.
- **Col 2 "Home & Solar":** Home Profile inputs + Solar & Battery sub-panel.
- **Col 3 "Energy & Prices":** Rate Scenarios + the Social & Health Cost panel (already
  built — restyle into this column).
- Each card header gets a `?` (`data-help` → our keys: `journey`/`home`/`energy` map to
  `journey_planner`/`home_profile`/`energy_prices`).
- **Controls:** per the handoff gotchas, prefer **raw-HTML controls** (`.slider`, `.check`,
  `.seg`, `.selectbox`) bound to existing reactives where Vuetify fights the styling; or
  apply `classes=[...]` to Solara components with scoped overrides. Either way, **bind to
  the existing reactive variables** — do not introduce parallel state.

### Deliverable 6 — Charts (restyle Matplotlib, keep selectors)

Keep the two-pane dropdown chart selectors and all 8 chart functions. Restyle each figure:
- Figure/axes backgrounds **transparent** (`fig.patch.set_alpha(0)`, `ax.set_facecolor("none")`).
- Series colors: journey `#3B6FD4`, baseline `#D2785F`; social overlays keep their
  current orange/red. Grid `#EBEDF1`, spines off (top/right already off), tick/label
  color `#5A6273`, mono font where practical (`font-family` via rcParams or per-text).
- Wrap each chart pane in the `.card` shell with the design's header (icon chip + h3 +
  the existing dropdown + `?`).
- Keep `solara.FigureMatplotlib`. No Plotly.

### Deliverable 7 — Device Details modal

Convert detail display from inline bottom-zone to modal:
- Replace `BottomZone`'s deck↔detail swap: always render `SummaryView`; render a
  `solara.v.Dialog(v_model=(detail_open.value is not None), max_width="840")` containing
  the existing `DetailView(detail_open.value, model)` body.
- Style the dialog to `.modal.modal-lg`: sticky header (`.modal-hd`) with device icon +
  title + subtitle + green "✓ Done" (`.btn.done`) + `✕`; scrollable `.modal-bd`.
- Both Done and ✕ set `detail_open.set(None)`. Add Esc-to-close if practical.
- The detail body components (`HVACDetail`, etc.) are reused as-is, restyled with
  `.detail-top`, `.dslider.sizing`, `.elec-line`, `.compare`, `.costs-panel` classes.
- The `⋮` buttons in `_card_header` already set `detail_open` — keep that wiring.

### Deliverable 8 — Help popover (anchored card)

Restyle `HelpPopupOverlay` from a centered dialog to the anchored `.help-pop` card:
- Simplest acceptable: a `solara.v.Menu` anchored to the `?` button with the card content
  styled `.help-pop` (header band, ? badge, title, body, "LEARN MORE →"). Vuetify handles
  anchoring/flip.
- Keep the existing `help_open` reactive and `HELP_POPUPS` content. Map any design
  `data-help` keys to ours: `load`→`panel_assessment`, `chart-cumulative`→`chart_jc2`,
  `chart-breakdown`→`chart_jc4`, `journey`→`journey_planner`, `home`→`home_profile`,
  `energy`→`energy_prices`, `about`→ open `index.html`.
- "LEARN MORE →" keeps calling `open_help(page)`.

### Deliverable 9 — Footer

Restyle to `.foot`: left "Estimates are illustrative — adjust assumptions to match your
home." Right: keep the ECHo support line / "runs on Solara". Preserve the existing ECHo
logo rendering (`_read_svg(_ECHO_LOGO)`).

---

## Hard Rules

1. **No engine changes.** `model.py`, `journey.py`, `devices/`, `rate_loader.py`,
   `panel_assessor.py`, `social_cost.py`, `home_config.py` are untouched. All existing
   tests must still pass unchanged.
2. **No new/renamed reactive state.** Bind the redesigned controls to the *existing*
   reactives and `_DEFAULTS`/`reset_to_defaults`. (Cosmetic-only new reactives, e.g. a
   theme toggle, are allowed but optional.)
3. **Preserve `whywatt_logo.svg`** in the masthead (do not substitute the handoff's
   inline SVG).
4. **Keep the help_content.md → build_help.py pipeline** and all current help keys.
5. App must boot (`solara run`) with no console errors after each deliverable.
6. The simulation outputs (verdict numbers, chart data, load amps) must match the
   pre-redesign values for the same inputs — only presentation changes.

## Verification

- `.venv/Scripts/python.exe -m pytest tests/` → same pass set as before (the 3
  pre-existing `dual_scenario` failures remain; everything else passes).
- Boot the app; sanity-check with a screenshot at each major deliverable.
- Manually confirm: masthead logo renders; verdict numbers match old SummaryStats;
  load strip threshold color flips correctly at 100A/200A (set panel to 100A + full
  electrification); each `⋮` opens the modal; each `?` opens the popover with correct
  copy + working "Learn more"; Reset and Help buttons work; charts render with new colors.

## Acceptance Criteria

- [ ] `styles.css` injected once via `solara.Style`; fonts load
- [ ] Masthead: existing whywatt_logo.svg + wordmark + one-line context pill + Reset/Help
- [ ] Verdict band with two proportional bars + payback/net panel (numbers match SummaryStats)
- [ ] Single-line Electrical Load strip with correct peak threshold class/badge
- [ ] 3-column control deck restyled; all existing controls bound to existing reactives
- [ ] All 8 Matplotlib charts restyled (token colors, transparent bg) in `.card` shells; selectors kept
- [ ] Device Details shown as a modal dialog (Done/✕/scrim/Esc close); existing detail bodies reused
- [ ] Help popover restyled as anchored card; all keys resolve; Learn-more works
- [ ] Footer restyled; ECHo logo preserved
- [ ] App boots clean; all pre-existing tests still pass; simulation outputs unchanged
