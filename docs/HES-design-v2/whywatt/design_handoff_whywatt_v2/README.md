# Handoff: WhyWatt? Dashboard — v2 Layout (Solara implementation)

## Overview
WhyWatt? is a single-page **home electrification cost calculator**. A homeowner enters their home profile, sequences appliance upgrades (HVAC, water heater, EV charger, cooktop, dryer), tunes energy-price and social-cost assumptions, and sees the long-horizon cumulative cost of *electrifying* vs *doing nothing* — plus payback, cost breakdowns, and electrical-panel guidance.

This bundle is the **v2 layout** of the redesigned UI. The component design system (tokens, cards, inputs, sliders, segmented controls, modal, help popover) is **unchanged from the previous handoff** — what changed is the **page layout**. The target is the existing **Solara + Python** app: this is a layout restructure on top of the same reskin, with all simulation logic, reactive state, and Plotly charts kept intact.

---

## PRIMARY CHANGES (v1 → v2) — implement these
These six changes are the point of this handoff. Everything else carries over from the previous design.

1. **Merged top panel ("cockpit").** The two former top panels — *Payback / verdict band* and *Estimated Electrical Load* — are now **compressed into one single-row card** (`.cockpit`) with three zones: payback call-out · comparison bars · electrical panel guidance. See section B below.
2. **Charts remain the same.** The two chart cards (*Cumulative Energy Costs*, *Cost Breakdown by Category*) are unchanged in content, styling, and behavior. Keep the existing Plotly figures and card shells.
3. **New "Setup your home" group** (`.setup-group`): the three assumption panels — **Home & Solar**, **Energy & Prices**, **Social & Health** — sit in a tinted group container with a group header and are **collapsible**, individually (chevron per card) and together ("Collapse all" button). See section D.
4. **Appliances laid out in 2 rows** inside *Your Electrification Journey*: row 1 "MAJOR LOADS" = HVAC · HPWH · EV Charger; row 2 "OTHER APPLIANCES" = Cooktop · Dryer · Panel/Baseload. **Each appliance sub-panel (HVAC, HPWH, EV, Cooktop, Dryer) keeps its existing internal design** — same fields, controls, and ⋮ detail button.
5. **Half-width sub-panels for Electrical Panel and Baseload.** The third cell of row 2 is one device card split vertically into two half-width sub-panels (`.split2 > .subpanel`): *Electrical Panel* and *Baseload*, each with an input + ⋮ details button + "Plan" checkbox + `?` help.
6. **Retain the logos top and bottom** exactly as in the code: the **WhyWatt? brand mark + wordmark** in the masthead, and the footer line **"This website runs on Solara"** (linked).

---

## About the Design Files
The files in this bundle (`index.html`, `styles.css`, `layout-v2.css`, `charts.js`, `detail.js`, `help.js`, `app.jsx`, `tweaks-panel.jsx`) are **design references created in HTML/CSS/vanilla-JS** — prototypes showing the intended look, layout, and behavior. **They are not production code to ship directly.**

Your task is to **recreate this layout in the existing Solara (Python) app**, keeping all reactive variables, callbacks, the cost model, and Plotly charts identical. Specifically:
- `styles.css` is the **design system** (tokens + every component class). `layout-v2.css` is the **v2 layout layer** added on top — cockpit, setup group + collapse, 2-row appliance grid, split panel. Inject both via `solara.Style`.
- The charts in `charts.js` are hand-drawn SVG mocks that mimic the real charts — keep your **real Plotly figures**, matching only the styling (colors, transparent bg, fonts).
- Sliders/inputs in the prototype are mostly presentational; in production they stay bound to the existing model state.
- Treat copy, layout, spacing, and color as **high-fidelity spec**.

## Fidelity
**High-fidelity (hifi).** Final colors, typography, spacing, radii, shadows, and interaction states. Recreate pixel-faithfully; all values live as CSS custom properties in `styles.css` (tokens summarized at the end of this doc).

---

## Page Layout (top to bottom)
Centered column, `max-width: 1320px`, page padding `22px 26px 64px`, cool off-white background (`--bg`). Vertical rhythm `--gap` (16px).

### A. Masthead (unchanged — retain logo)
Single-line flex row, bottom border, `padding-bottom:16px; margin-bottom:18px`.
- **Brand (RETAIN):** 42×42 gradient mark (`160deg, --journey → --journey-ink`, radius 11px) with inline SVG — white house + knocked-in lightning bolt — and wordmark **"WhyWatt?"** ("Why" in `--ink`, "Watt?" in `--journey-ink`, 20px/800).
- **Context strip:** bordered white pill (height 40px) with 📍 "San Jose, CA" · `ZIP 95112` · `CZ 12` · `3 bed` · `1,800 sq ft` · `Built 1985` · `Baseload 1,910 kWh/yr`, thin 1px dividers, values in mono 12.5px. One line, clips on overflow.
- **Actions:** "Reset to defaults" (secondary `.btn`) + "Help" (primary `.btn.primary`, `data-help="about"`).

### B. Cockpit — merged results bar (`.cockpit`) ★ CHANGE 1
One `.card` with `padding:0`, laid out as **grid `auto minmax(210px,1fr) auto`**, zones separated by inset 1px vertical rules (`top/bottom: 14px`). Each zone: `padding:14px 20px`, vertically centered column. Stacks to 1 column ≤820px (rules become top borders).

1. **`.ck-call` — Payback call-out** (leftmost, tinted `--positive-soft` background):
   - Eyebrow `PAYBACK · YR 1 (2025)` — 10px/800 uppercase, letter-spacing .08em, `--positive-ink`.
   - Big figure `+$41,644` — mono 30px/600, `--positive-ink`, letter-spacing −0.02em.
   - Foot "net social cost avoided +$18,627" — 11.5px `--ink-3`.
   - **State:** when the verdict is negative ("no payback"), swap the tint/ink to the baseline (terracotta) tokens — same structure.
2. **`.ck-bars` — comparison bars** (center, flexible): two compact rows (gap 10px), each = 92px right-aligned label ("Your journey" / "Do nothing", 12px; no subtitle in v2) + a 24px-tall bar track (`--surface-3`, radius `--r-sm`). Fills: journey = blue gradient at 50% width, value `$42,259`; baseline = terracotta gradient at 100% width, value `$83,904`. Values mono 12px, white, right-aligned inside the fill. **Bar widths are proportional to the two cumulative cost totals (max = 100%).**
3. **`.ck-guide` — Electrical Panel Guidance** (rightmost): micro-title `ELECTRICAL PANEL GUIDANCE` (9.5px/800 uppercase `--ink-3`), then a flex row (`.guide-metrics`, gap 16px) of two metric blocks (`.gm`: 9px uppercase key + 19px mono number + 11px unit "A") — **Current 41 A** and **Peak 86 A** — plus the status badge (`.peak-badge`) "✓ Within 200 A". The badge may wrap to 2 lines (max-width 92px) so the bars can compress.
   - **Threshold behavior (unchanged logic):** badge + peak value reflect model peak amps — `peak-ok` (green) < 100 A, `peak-warn` (amber) ≥ 100 A, `peak-danger` (red/terracotta) ≥ 200 A.

### C. Charts row (unchanged) ★ CHANGE 2
Grid `1fr 1fr` (held side-by-side down to 821px), gap 16px. Two `.card`s with identical header pattern (icon chip + h3 + view-mode dropdown button + `?` help):
- **"Cumulative Energy Costs"** — line chart, dropdown "Cumulative", `data-help="chart-cumulative"`.
- **"Cost Breakdown by Category"** — stacked-area small multiples, dropdown "Stacked area", `data-help="chart-breakdown"`.
Keep the existing Plotly implementation; transparent paper/plot bg, journey `#3B6FD4` / baseline `#D2785F`, grid `#EBEDF1`, IBM Plex Mono numerals.

Below the charts, the thin **series key** strip: "● Do nothing" (baseline) · "● Your journey" (journey) · right-aligned eyebrow "ADJUST THE SCENARIO BELOW".

### D. "Setup your home" group (`.setup-group`) ★ CHANGE 3
A tinted group container: `--surface-2` background, 1px `--border`, radius `--r-xl`, padding 16px, column gap 14px.
- **Group header (`.sg-hd`):** 28×28 journey-soft icon chip (house) + h3 "Setup your home" (15px/700) + muted scope note ("— Home & Solar, Energy & Prices, Social & Health collapse together", 11.5px `--ink-3`) + spacer + **"Collapse all" button** (`.collapse-all`: 32px pill, white, `--border-strong`, chevron that rotates 180° when collapsed; label toggles to "Expand all").
- **Grid (`.setup-grid`):** 3 equal columns, gap 16px, `align-items:start`. Three standard `.card`s, each header now carrying a **chevron collapse button** (`.chev-btn`) in addition to the `?` help button:
  1. **Home & Solar** — "Home Profile" panel (ZIP, Bedrooms, Square feet, Climate zone, Insulation segmented Poor/Average/Good) + "Solar & Battery" panel ("Add rooftop solar" checkbox + empty-state note).
  2. **Energy & Prices** — "Rate Scenarios" panel: Electricity rate model (CAGR/ACC segmented + caption `+7%/yr`), Gas rate model (CAGR/ACC + `+8%/yr`), Model horizon slider (5–30, value 20 yrs).
  3. **Social & Health** — "Cost of Gas" panel: Climate cost checkbox (checked) + slider (1.00–2.00 $/therm, value 1.74, delta note "+0.67 $/therm above default (1.07)" + min/max scale) + Health cost checkbox (checked).

**Collapse behavior (replicate in Solara state):**
- Per-card chevron toggles `is-collapsed` on that card: body hides, header stays, chevron rotates −90°, header bottom border removed.
- "Collapse all" sets all three collapsed; when **all** are collapsed the group enters `collapsed-all` mode: the grid becomes a flex row of equal-width **title-only chips** on a single line, and the button reads "Expand all" with flipped chevron.
- State is derived: `collapsed-all` ⇔ every card is collapsed (collapsing the last card manually also triggers it).

### E. Your Electrification Journey — 2-row appliance grid ★ CHANGES 4 & 5
One `.card.jcard` with the standard header (document icon + h3 "Your Electrification Journey" + count pill "6 devices" + `?` help `data-help="journey"`). Body (`.jbody`): column, gap 14px, with two labeled rows. Row labels (`.jrow-label`): 10.5px/800 uppercase, letter-spacing .09em, `--ink-4`.

**Row 1 — `MAJOR LOADS`** (`.jgrid`: 3 equal columns, gap 14px, align start):
- **HVAC** (`.device`) — header (icon + name + ⋮ → `openDetail('HVAC')`), Fuel select ("Gas → Heat pump"), Plan year slider (2025–2044, 2027) with mono caption, "Include in plan" checkbox (checked), 3-up row: Install $ `14,000` · Rebate $ `3,500` · **Net pill** `$10,500`.
- **HPWH** — identical structure: Fuel select, Plan year 2029, include checked, Install `2,500` / Rebate `500` / Net `$2,000`.
- **EV Charger** — Vehicle profile segmented (Efficient / **Average** / SUV-Truck), Charger select ("None planned"), Miles/yr input `7,000`, "Include in plan" checkbox (unchecked).
- ★ **These sub-panels are unchanged from the previous design — reuse the existing device-card components as-is.**

**Row 2 — `OTHER APPLIANCES`** (same `.jgrid`):
- **Cooktop** (`.device.minor`) — header + ⋮, Fuel select ("Gas (keep)" / "Gas → Induction"), "Plan swap" checkbox, muted status line "No swap planned".
- **Dryer** (`.device.minor`) — same pattern ("Gas (keep)" / "Gas → Heat pump").
- **Panel & Baseload split card** ★ CHANGE 5 — one `.device` containing `.split2` (grid `1fr 1fr`, 1px vertical divider between, each half `.subpanel` padded 14px inner-side only, column gap 11px):
  - **Electrical Panel:** name row (15px journey-ink icon + "Electrical Panel" 13px/700) · input `200 A panel` + 34×34 ⋮ button → `openDetail('Panel Upgrade')` · bottom row: "Plan" checkbox + spacer + small 22px `?` help (`data-help="load"`).
  - **Baseload:** same structure — input `1,910 kWh/yr`, ⋮ → `openDetail('Baseload')`, "Plan" checkbox + `?` help.

### F. Footer (unchanged — retain) ★ CHANGE 6
Left: "Estimates are illustrative — adjust assumptions to match your home." Right: **"This website runs on Solara"** with "Solara" as a link. Keep both.

### Responsive
- ≤920px: `.setup-grid` and `.jgrid` → 2 columns. ≤620px: → 1 column.
- ≤820px: cockpit stacks to 1 column (zone dividers become top borders).
- Charts stay 2-up ≥821px.

---

## Overlay surfaces (unchanged from previous handoff)
- **Device Details editor** (`detail.js`): centered modal (min(840px), `--r-xl`, blurred scrim) opened by every ⋮ button. Header = icon + title + subtitle + green "✓ Done" + ✕. Body = starting-state select + plan-swap year slider, sizing slider, ELECTRICAL spec line, two-column Current-vs-Replacement compare (baseline/journey underlines), extra checkbox, COSTS & REBATES panel with live Net = install − rebate. Closes on Done/✕/scrim/Esc. **v2 adds two detail keys:** `Panel Upgrade` and `Baseload` (reuse the same modal shell; define their stat content from the model).
- **Help popover** (`help.js`): anchored tooltip-card (min(420px)) opened by any `[data-help]` trigger; positions below-right of trigger, flips/clamps to viewport; accent header band + body copy + "LEARN MORE →" button; closes on outside-click/✕/Esc. Content registry keys: `load`, `chart-cumulative`, `chart-breakdown`, `journey`, `home`, `energy`, `about`.

## State Management (deltas only)
All previous state carries over (home profile, devices, rates, social costs, solar, model outputs, open-modal / open-help keys). **New in v2:**
- `setup_collapsed: dict[str, bool]` for the three setup cards + derived `all_collapsed` (drives the chip-row mode and the button label).
- Cooktop and Dryer device state: fuel choice + plan-swap flag (+ plan year & costs once a swap is planned).
- Electrical Panel and Baseload as editable inputs (panel amps, baseload kWh/yr) with their own "Plan" flags and detail-modal entries.
- Cockpit derives from existing model outputs: payback figure + sign (drives green vs terracotta tinting), two cumulative totals (drive bar widths, proportional to max), current/peak amps + threshold class.

## Design Tokens (unchanged — summary)
Authored in OKLCH in `styles.css :root`; sRGB hexes for Plotly:
- **Journey blue** `#3B6FD4` (ink `#2A55B0`, soft `#EAF0FB`) · **Baseline terracotta** `#D2785F` (ink `#BC5742`, soft `#FAEDE9`) · **Positive green** `#2E9E73` (ink `#1F805C`, soft `#E5F4EC`) · **Warn amber** `#D69A3C`.
- Ink scale `#2A3140 / #5A6273 / #838B99 / #A6ABB5`; bg `#F7F8FA`; borders `#E2E5EA` / `#EBEDF1`; grid `#EBEDF1`.
- Radii 6/8/11/14/18 · padding & gaps 16px (cards), 12–14px (fields/grids) · shadows xs→lg per `styles.css`.
- Type: **Schibsted Grotesk** (UI, 400–800) + **IBM Plex Mono** (every numeral, tabular figures). Base 14px.

## Assets
- **Logo mark:** inline SVG in `index.html` (`.brand-mark`) — no external file. Retain as-is.
- **Icons:** inline 24×24 stroke SVGs throughout (stroke-width ~2) — no icon library.
- **Fonts:** Google Fonts (Schibsted Grotesk, IBM Plex Mono) — self-host if needed.

## Files
- `index.html` — v2 dashboard markup (incl. the collapse-behavior script at the bottom — port that logic to Python state, not JS).
- `styles.css` — design system: tokens + all components. **Primary reference.**
- `layout-v2.css` — v2 layout layer: `.cockpit`, `.setup-group` + collapse rules, `.jgrid`/`.jrow-label`, `.split2`/`.subpanel`. **Read this for every v2 measurement.**
- `charts.js` — SVG chart mocks (visual reference only; keep Plotly).
- `detail.js` / `help.js` — modal + popover systems (per-device data, anchoring logic, help copy).
- `app.jsx` / `tweaks-panel.jsx` — optional design-review theming layer (palette/tone/density). Not core product; skip unless you want runtime theming.
- `screenshots/` — reference captures of the prototype (captured at ~910px viewport, so the masthead context strip clips; the layout spec above is authoritative at full width):
  - `01-dashboard-top-cockpit-charts.png` — masthead + merged **cockpit** + charts row.
  - `02-setup-your-home.png` — Setup your home group, expanded.
  - `03-journey-2-row-grid.png` — Electrification Journey, 2-row appliance grid.
  - `04-panel-baseload-split-footer.png` — split Panel/Baseload card + footer (Solara credit).
  - `05-setup-collapsed-all.png` — Setup group in **collapsed-all** chip-row mode.
  - `06-detail-modal-hvac.png` — Device Details modal (HVAC).
  - `07-help-popover.png` — anchored Help popover (header Help trigger).

---

## Solara Implementation Guide

### Strategy
Inject `styles.css` **and** `layout-v2.css` once via `solara.Style` at the app root. Keep Python state and the cost model untouched. Build bespoke layout sections (cockpit, setup group shell, split panel) with `solara.HTML`; use Solara/Vuetify components where they cooperate, raw-HTML controls (already styled by `styles.css`) where Vuetify fights you (sliders, checkboxes, segmented controls, selects).

```python
import solara
from pathlib import Path

CSS = (Path(__file__).with_name("styles.css").read_text()
       + Path(__file__).with_name("layout-v2.css").read_text())

@solara.component
def Page():
    solara.Style(CSS)
    # ...layout...
```
Load the Google Fonts `<link>` in the app's HTML template rather than relying on the CSS `@import`.

### Section mapping
| Section | Approach | Notes |
|---|---|---|
| Masthead + brand | `solara.HTML` | Pure presentation; logo is inline SVG. Buttons via `solara.Button(classes=["btn", ...])`. |
| **Cockpit** | `solara.HTML` (one component) | Render the 3 zones from model values: payback figure + tint class, two bar widths (`width:{pct}%`), amps + `peak-ok/warn/danger` class. No Vuetify equivalent — raw HTML is simplest. |
| Charts | `solara.FigurePlotly` in `.card` shells | Unchanged from current app; custom HTML headers. |
| **Setup group** | container `solara.HTML`/`Column(classes=["setup-group"])`; collapse state in Python | Per-card `collapsed` reactive bools; render `is-collapsed` / `collapsed-all` classes from state. Chevron + Collapse-all = `solara.Button` or HTML buttons with `on_click`. Don't port the prototype's JS — it's just class toggling, trivially reproduced reactively. |
| Setup cards' controls | Same mappings as before | Raw `<select class="selectbox">`, `<input type="range" class="slider">`, `.seg` button groups, `.check` checkboxes — bound to reactive vars via events; or Vuetify components with override CSS if preferred. |
| **Journey grid** | `solara.HTML` shells per row + existing device components | `.jrow-label` spans + `.jgrid` wrappers; device cards reuse your existing per-device component (unchanged internals). |
| **Split Panel/Baseload** | one `solara.HTML` device card | Two `.subpanel` halves; inputs bound to panel-amps / baseload vars; ⋮ buttons set the open-detail reactive key. |
| Detail modal | `solara.v.Dialog` (or existing modal) | Same as previous handoff; add `Panel Upgrade` and `Baseload` entries to the detail registry. |
| Help popover | `solara.v.Menu` styled as `.help-pop`, or ported anchor logic | Same as previous handoff. |
| Footer | `solara.HTML` | Retain the Solara credit line. |

### Suggested build order
1. Inject both stylesheets; restructure the top of the page into the **cockpit** fed by existing model outputs (this also deletes the two old panels).
2. Verify the **charts** still render in their cards (no changes needed).
3. Wrap the three assumption cards into the **setup group** and wire collapse state.
4. Rebuild the journey section as the **2-row grid**, reusing existing device components; add Cooktop/Dryer minor cards and the **split Panel/Baseload** card.
5. Confirm masthead logo + footer credit survived the restructure; add the two new detail-modal entries.
