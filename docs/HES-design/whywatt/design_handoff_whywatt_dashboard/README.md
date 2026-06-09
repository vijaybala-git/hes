# Handoff: WhyWatt? — Home Electrification Dashboard (Redesign)

## Overview
WhyWatt? is a single-page **home electrification cost calculator**. A homeowner enters their home profile, sequences appliance upgrades (HVAC, water heater, EV charger), tunes energy-price and social-cost assumptions, and sees the 20-year cumulative cost of *electrifying* vs *staying on gas* — plus payback, cost breakdowns, and the electrical-panel load their plan will draw.

This bundle is the **redesigned UI**: one dashboard screen plus two overlay surfaces — a **Device Details editor** (modal) and a **Help popover** (anchored tooltip-card).

---

## About the Design Files
The files in this bundle (`index.html`, `styles.css`, `charts.js`, `detail.js`, `help.js`, `app.jsx`) are **design references created in HTML/CSS/vanilla-JS** — prototypes showing the intended look, layout, and behavior. **They are not production code to ship directly.**

Your task is to **recreate these designs in the target codebase's existing environment** (React, Vue, Svelte, etc.), using its established component patterns, state management, and charting library. If no front-end environment exists yet, choose an appropriate one (React + a charting lib such as Plotly/Recharts/visx is a natural fit, since the real app already used Plotly).

Specifically:
- The **charts** here (`charts.js`) are lightweight hand-drawn SVGs that *mimic* the real charts' intent. Re-implement them with your real charting library and real model data — match the **styling** (colors, axes, two-series language, stacked areas), not the fake curves.
- The **sliders/inputs** in the prototype are mostly presentational (a couple have live JS). In production they must be bound to real state and the model.
- Treat copy, layout, spacing, and color as **high-fidelity spec**.

---

## Fidelity
**High-fidelity (hifi).** Final colors, typography, spacing, radii, shadows, and interaction states are all specified below and in `styles.css` (which is built entirely on CSS custom properties / design tokens). Recreate the UI pixel-faithfully using your codebase's libraries, porting the tokens in the **Design Tokens** section.

---

## Screens / Views

### 1. Main Dashboard (`#app`, `[data-screen-label="Main"]`)
Centered column, `max-width: 1320px`, page padding `22px 26px 64px`, on a cool off-white background (`--bg`). Vertical rhythm between major sections is `--gap` (16px). Top-to-bottom order:

**A. Masthead (header) — single line, no wrap**
- Flex row, `align-items:center; gap:16px`, bottom border, `padding-bottom:16px; margin-bottom:18px`.
- **Brand** (left, fixed): 42×42 logo mark (`border-radius:11px`, gradient `160deg, --journey → --journey-ink`, `--shadow-sm`) containing a 23×23 SVG — a **solid white house with a knocked-in lightning bolt** (bolt filled `--journey-ink`). Next to it the wordmark **"WhyWatt?"** — "Why" in `--ink`, "Watt?" in `--journey-ink`, weight 800, `font-size:20px`, `letter-spacing:-0.02em`, single line (the old two-line tagline was removed).
- **Context strip** (center, `flex:1`): a bordered pill (`height:40px`, `padding:0 14px`, `--surface`, `--border-soft`, `--shadow-xs`) holding inline spec items separated by thin 1px dividers, **forced to one line** (`flex-wrap:nowrap; overflow:hidden`). Items: 📍 "San Jose, CA" (location, weight 600) · `ZIP 95112` · `CZ 12` · `3 bed` · `1,800 sq ft` · `Built 1985` · `Baseload 1,910 kWh/yr`. Bold/numeric values use the mono font at 12.5px.
- **Actions** (right, fixed): two buttons — "Reset to defaults" (`.btn`, secondary) and "Help" (`.btn.primary`, blue accent; carries `data-help="about"`).

**B. Verdict band (hero result) — `.verdict`**
- Grid `1fr 248px`, rounded `--r-lg`, `--surface`, border, overflow hidden.
- **Left (`.verdict-bars`, padding 22×26):** two comparison rows. Each row = right-aligned label block (`142px`: title + small subtitle) + a horizontal bar track (`--surface-3`, `height:38px`, `border-radius:--r-sm`) with a filled bar showing a `$` value (mono, white). Row 1 "Your Electrification Journey / 20-yr cumulative energy cost" → blue gradient fill (`--journey → --journey-ink`), width 78%, value `$88,400`. Row 2 "Do-Nothing Baseline / Keep gas appliances" → red gradient (`--baseline → --baseline-ink`), width 64%, value `$84,500`.
- **Right (`.verdict-call`, padding 22×24):** soft red panel (`--baseline-soft`), left border. Eyebrow "PAYBACK" (`--baseline-ink`, uppercase, 11px/700). Headline "No payback within 20 yrs" (19px/700). Big mono figure "−$3,937" (34px/600, `--baseline-ink`). Foot "net position over 20 years".

**C. Electrical Load strip — `.load-strip` / `.load-line` (COMPACT, single line)**
- A card rendered as one horizontal row (`padding:11px 16px`, `gap:22px`). **No chart.** Order:
  1. **Title group:** 26×26 accent-soft icon chip (lightning bolt) + h3 "Estimated Electrical Load" + a `?` help button (`data-help="load"`).
  2. **Metrics (`.load-metrics`, flex):** two metric blocks separated by a vertical 1px divider. Each metric = uppercase micro-label (`.lm-k`, 10.5px/700, `letter-spacing:.07em`, `--ink-3`) + big mono value (`.lm-v`, 18px/600) + context.
     - **Current Load:** `41 A` · sub "21% of 200 A panel".
     - **Journey Peak Load:** `86 A` + a **status badge** (`.peak-badge`, pill) + sub "peaks Yr 5 · Water Heater".
  3. A trailing `?`/help affordance.
- **Peak threshold highlighting (important behavior):** the peak block carries a state class that drives both the value color and the badge:
  - `< 100 A` → `.peak-ok` — green badge (`--positive-soft`/`--positive-ink`) with a check icon, label "Within 200 A panel".
  - `≥ 100 A` → `.peak-warn` — amber value + amber badge (`oklch(0.95 0.05 75)` bg / `oklch(0.5 0.13 75)` text), e.g. "Approaching panel limit".
  - `≥ 200 A` → `.peak-danger` — red value (`--baseline-ink`) + red badge (`--baseline-soft`), e.g. "Exceeds 200 A — panel upgrade". 
  - In production, compute the class from the model's peak amperage. Current sample (86 A) = `peak-ok`.

**D. Charts row — `.charts`**
- Grid `1fr 1fr`, gap 16px. Two `.card`s, each with a header (icon chip + h3 + a "select" dropdown button + `?` help):
  - **"Cumulative Energy Costs"** — line chart; dropdown "Cumulative"; `data-help="chart-cumulative"`. Shows journey vs baseline solid lines plus dotted "with social cost" variants, $k y-axis (0–120k), 0–20yr x-axis.
  - **"Cost Breakdown by Category"** — small-multiples stacked-area ("Do Nothing" vs "Your Journey"); dropdown "Stacked area"; `data-help="chart-breakdown"`.
- *(In production, replace the SVG mocks with your charting library; keep the two-series color language and axis styling.)*

**E. Series key — `.series-key`**
- Thin legend strip: "● Do nothing" (`--baseline`) · "● Your journey" (`--journey`) · right-aligned eyebrow "ADJUST THE SCENARIO BELOW".

**F. Control deck — `.deck`** (grid `1.08fr 0.92fr 1fr`, gap 16px; collapses to 1 column ≤1080px). Three columns, each a `.card`:
  - **Col 1 — "Your Electrification Journey":** three `.device` cards (HVAC, Water Heater, EV Charger). Each device = header (icon + name + `⋮` button that opens the **Device Details editor**), fuel `<select>`, "Plan year" slider with mono caption, "Include in plan" checkbox, and (HVAC/WH) a 3-up Install $ / Rebate $ / **Net** pill row. EV instead has an "Efficient / Average / SUV-Truck" segmented control + charger select + miles input.
  - **Col 2 — "Home & Solar":** "Home Profile" sub-panel (ZIP, Bedrooms, Square feet, Climate zone, Insulation segmented control) + "Solar & Battery" sub-panel ("Add rooftop solar" checkbox + empty-state note).
  - **Col 3 — "Energy & Prices":** "Rate Scenarios" (Electricity & Gas each: CAGR/ACC segmented control + rate caption; Model horizon slider) + "Social & Health Cost of Gas" (Climate cost checkbox + labeled slider with delta + scale; Health cost checkbox).
  - Each control card header carries a `?` help button: `data-help="journey" | "home" | "energy"`.

**G. Footer — `.foot`** Left: "Estimates are illustrative — adjust assumptions to match your home." Right: "This website runs on Solara".

---

### 2. Device Details editor (modal) — `detail.js` + `.modal.modal-lg`
Opened by `openDetail(name)` from each device's `⋮` button. Scrim overlay (`--ink`-tinted, `backdrop-filter: blur(3px)`), centered card `width:min(840px,100%)`, `max-height:86vh`, scrollable, `--r-xl`, `--shadow-lg`. Configured for **HVAC**, **Water Heater**, **EV Charger** (data table in `detail.js`).

**Header (`.modal-hd`, sticky):** device icon chip (32×32, accent-soft) + title ("HVAC — Heating & Cooling") + subtitle ("Gas furnace → Heat pump") + a green **"✓ Done"** button (`.btn.done`, `--positive`) + an `✕` icon button. Both Done and ✕ close.

**Body (`.modal-bd`, gap 18px):**
1. **`.detail-top`** (flex, align-end): "Starting state" `<select>` (max 230px) + **`.plan-swap`** ("Plan swap" checkbox + a year range slider with mono caption "Yr N · YYYY").
2. **Primary sizing slider** (`.dslider.sizing`, dashed top/bottom rules): label with inline mono value, e.g. "Heat pump size — **3.0 ton**".
3. **`.elec-line`:** eyebrow "ELECTRICAL" + mono spec "240 V · 30 A · 7,200 VA".
4. **`.compare`** (grid `1fr 1fr`, divider between; stacks ≤620px): two columns —
   - **Current** (`.cmp-head.baseline`, red underline): heading "Current: Gas Furnace", summary "~**286 therms/yr** heating", two efficiency sliders (Furnace AFUE 0.80, Furnace age 10 yrs).
   - **Replacement** (`.cmp-head.journey`, blue underline): "Replacement: Heat Pump HVAC", summary "~**1919 kWh/yr** heat + **185 kWh/yr** cool = **2105 kWh/yr**", sliders (Heating COP 3.5, Cooling SEER 22).
5. **Extra checkbox** — e.g. "Has central AC (baseline)".
6. **`.costs-panel`** (bordered, `--surface-2`): eyebrow "COSTS & REBATES" + a grid `1fr 1fr auto` of Install cost $ input, Rebate $ input, and a **Net** pill.

**Live behaviors (already wired in `detail.js`, replicate in your state layer):**
- Every slider updates its inline value label on `input` (formatted via `dec`/`suf`; the year slider formats as "Yr N · YYYY", N = year − 2024).
- **Net** recomputes on `input` as `install − rebate`, comma-formatted; shows `−$` when negative.
- `Esc` closes the modal (and any open help popover).

---

### 3. Help popover — `help.js` + `.help-pop`
A small **anchored tooltip-card** opened by clicking **any `[data-help]` trigger** (the `?` buttons + header Help). Sized to overlay the primary content: `width:min(420px, 100vw−24px)`.

- A transparent full-screen `.help-overlay` (z 95) catches outside-clicks to close; the card itself sits above it.
- **Positioning:** anchored to the trigger — preferentially **below, right-aligned** to the button; flips above if it would overflow the bottom; clamped to the viewport with a 12px margin. (Computed from the trigger's `getBoundingClientRect()`.)
- **Card:** header band (`--accent-soft`) = round "?" badge (`--accent`, white) + title (`--accent-ink`, 13.5px/700) + round `✕`. Body = explanatory paragraph (13px, line-height 1.58, `--ink-2`). Footer = an outlined **"LEARN MORE →"** button (uppercase, 12px/700, arrow icon).
- **Content registry** (in `help.js`, keyed by `data-help`): `load`, `chart-cumulative`, `chart-breakdown`, `journey`, `home`, `energy`, `about`. Copy is in the file — treat as final, editable by product.
- Closes on outside-click, `✕`, or `Esc`. Only one open at a time.
- **Implementation note:** the prototype's entrance keyframe was made opacity-independent (base `opacity:1`, animation transforms only) so the card is never invisible if CSS animations are throttled. Keep visibility independent of the entrance animation.

---

## Interactions & Behavior
- **Open device editor:** `⋮` on a device → modal (per-device config).
- **Open help:** any `?` / header Help → anchored popover for that key.
- **Close:** Done / ✕ / scrim / `Esc` (modal); ✕ / outside / `Esc` (popover).
- **Sliders:** live inline value labels; in production also re-run the model + re-render charts on change.
- **Net pill:** live `install − rebate`.
- **Transitions:** buttons/inputs ~.13–.14s ease on color/border/shadow; slider thumb scales 1.12 on hover; modal scrim blur; popover entrance .14s transform.
- **Responsive:** `.deck`, `.charts`, `.verdict` → 1 column ≤1080px; `.compare` → 1 column and `.costs-row` → 2 columns ≤620px. Masthead context strip stays one line (clips on overflow).
- **Theming hooks (optional, from `app.jsx`):** root `data-palette` (`default|electric|ink`), `data-tone` (`cool|neutral|warm`), `data-density` (`regular|compact`) swap token sets live. Charts re-read CSS variables on theme change.

## State Management
Recreate with your app's state layer. Core state:
- **Home profile:** zip, bedrooms, sqft, climate zone, insulation, baseload.
- **Devices** (HVAC / Water Heater / EV): startingState, includeInPlan (bool), planYear, sizing value, efficiency params (current + replacement sliders), install $, rebate $, derived net, extra flag (e.g. hasCentralAC). EV also: vehicle profile, charger type, miles/yr.
- **Energy & prices:** elec rate model (CAGR/ACC) + rate, gas rate model + rate, model horizon (yrs), climate cost ($/therm) on/off, health cost on/off.
- **Solar:** enabled (+ sizing when on).
- **Derived/model outputs:** journey vs baseline cumulative cost series, payback (or "no payback"), net 20-yr position, category breakdown series, **current load (A)** and **journey peak load (A)** + which year/device drives the peak.
- **UI:** open modal (which device), open help (which key), theme tweaks.
- **Transitions:** any input change → recompute model → update verdict band, charts, and the load strip (incl. recomputing the peak threshold class).

## Design Tokens
Ported verbatim from `:root` in `styles.css` (authored in **OKLCH**; sRGB hex approximations in parentheses for tools without OKLCH/P3).

**Surfaces (cool neutral, default tone)**
- `--bg` `oklch(0.983 0.004 240)` (#F7F8FA) · `--surface` `#FFFFFF` · `--surface-2` `oklch(0.974 0.005 240)` (#F3F4F7) · `--surface-3` `oklch(0.96 0.006 240)` (#EEF0F3)
- `--border` `oklch(0.916 0.006 240)` (#E2E5EA) · `--border-soft` `oklch(0.944 0.005 240)` (#EBEDF1) · `--border-strong` `oklch(0.85 0.012 248)` (#CDD2DA)

**Ink scale**
- `--ink` `oklch(0.28 0.022 258)` (#2A3140) · `--ink-2` `oklch(0.47 0.018 258)` (#5A6273) · `--ink-3` `oklch(0.62 0.014 258)` (#838B99) · `--ink-4` `oklch(0.74 0.01 258)` (#A6ABB5)

**Two-series + semantic**
- `--journey` `oklch(0.55 0.13 252)` (#3B6FD4) · `--journey-ink` `oklch(0.45 0.135 252)` (#2A55B0) · `--journey-soft` `oklch(0.95 0.035 252)` (#EAF0FB) · `--journey-line` `oklch(0.5 0.14 252)` (#3461C6)
- `--baseline` `oklch(0.66 0.12 32)` (#D2785F) · `--baseline-ink` `oklch(0.55 0.14 32)` (#BC5742) · `--baseline-soft` `oklch(0.955 0.028 32)` (#FAEDE9) · `--baseline-line` `oklch(0.62 0.15 32)` (#C96247)
- `--positive` `oklch(0.58 0.11 158)` (#2E9E73) · `--positive-ink` `oklch(0.48 0.1 158)` (#1F805C) · `--positive-soft` `oklch(0.95 0.045 158)` (#E5F4EC)
- `--warn` `oklch(0.72 0.13 75)` (#D69A3C) · warn-soft used inline `oklch(0.95 0.05 75)` (#F6ECD8), warn-ink `oklch(0.5 0.13 75)` (#9A6B1E)
- `--accent`/`--accent-ink`/`--accent-soft` alias the journey tokens.

**Alternate palettes** (`[data-palette="electric"|"ink"]`) and **tones** (`[data-tone="warm"|"neutral"]`) redefine the above — see `styles.css` lines ~62–101.

**Radii:** `--r-xs 6` · `--r-sm 8` · `--r 11` · `--r-lg 14` · `--r-xl 18` (px).

**Shadows:**
- `--shadow-xs` `0 1px 2px rgba(20,28,46,.05)`
- `--shadow-sm` `0 1px 2px rgba(20,28,46,.04), 0 1px 3px rgba(20,28,46,.06)`
- `--shadow-md` `0 2px 4px rgba(20,28,46,.04), 0 8px 20px rgba(20,28,46,.07)`
- `--shadow-lg` `0 14px 38px rgba(20,28,46,.12), 0 2px 8px rgba(20,28,46,.06)`

**Spacing:** `--pad 16` / `--gap 16` / `--card-gap 12` (compact density: 13 / 12 / 9).

**Typography:**
- Sans: **Schibsted Grotesk** (400–800) — `--font`. Mono: **IBM Plex Mono** (400–600) — `--mono`, with `font-feature-settings:"tnum" 1` for tabular numerals. Both loaded via the Google Fonts `@import` at the top of `styles.css`.
- Base body 14px / line-height 1.45. Key sizes: h3 14/700; card eyebrow 10.5–11/700 uppercase; wordmark 20/800; verdict big 34/600 mono; metric value 18/600 mono; payback headline 19/700.

## Assets
- **Logo mark:** inline SVG in `index.html` (`.brand-mark`) — white house + `--journey-ink` bolt on a journey gradient. No external file. *(A dedicated, more distinctive wordmark/logo is flagged as a separate design effort.)*
- **All other icons:** inline stroke SVGs (24×24 viewBox, `stroke-width` ~2) — house, bolt, gear/HVAC, water tank, EV, charts, sun, etc. No icon library/font; swap for your icon set if preferred, matching stroke weight and size (~13–18px rendered).
- **Fonts:** Google Fonts (Schibsted Grotesk, IBM Plex Mono). Self-host if your build requires.
- **Charts:** no image assets — SVG drawn in `charts.js` (replace with real charting lib).

## Files
In `whywatt/` (and copied into this handoff folder):
- `index.html` — dashboard markup + script includes.
- `styles.css` — **the design system** (tokens + every component). Primary reference.
- `charts.js` — SVG chart mocks (line + stacked-area). Re-implement with a real lib.
- `detail.js` — Device Details editor (per-device data + live slider/net logic).
- `help.js` — Help popover system (anchored positioning + content registry).
- `app.jsx` — optional theming "Tweaks" layer (palette/tone/density) — not core to the product.

---

## Solara Implementation Guide
The production app runs on **Solara** (solara.dev) — a Python reactive framework rendering through **ipyvuetify / Vuetify 2**. This design is therefore a **reskin, not a logic rewrite**: keep your Python state and cost model, keep Plotly for charts, and apply this design system as injected CSS + a mix of styled Solara components and raw-HTML components.

### Strategy in one line
Inject `styles.css` once via `solara.Style`, attach the design's class names to Solara components where Vuetify's DOM cooperates, and hand-build the bespoke sections (hero, load strip, segmented controls, popover internals) with `solara.HTML`. For a few controls, raw HTML is *less* work than overriding Vuetify.

### 1. Global CSS injection (do this once, app root)
```python
import solara
from pathlib import Path

CSS = Path(__file__).with_name("styles.css").read_text()

@solara.component
def Page():
    solara.Style(CSS)          # tokens + all component classes, global
    # ...app layout...
```
`solara.Style` adds the stylesheet globally. The `@import` for Google Fonts at the top of `styles.css` works, but prefer adding a `<link>` in the app's `index.html` template (or self-host) so fonts aren't gated on CSS parse. All `:root` tokens, `[data-tone]`, `[data-palette]`, `[data-density]` variants come along for free — set them by toggling an attribute on a wrapping `solara.HTML` container if you keep the theming layer.

### 2. Section-by-section mapping

| Design section | Solara approach | Notes |
|---|---|---|
| **App shell** (`.app`) | `solara.Column(classes=["app"])` | Or a `solara.HTML(tag="div")` wrapper. |
| **Masthead** | `solara.HTML` for brand + context strip; `solara.Button` for actions | The context pill and inline spec dividers are pure presentation → raw HTML. Logo is inline SVG. |
| **Verdict band** | `solara.HTML` (custom) | No Vuetify equivalent — bars are styled `<div>`s with width %. Feed widths/values from model. |
| **Load strip** + threshold badges | `solara.HTML` (custom) | Compute `peak-ok/warn/danger` class in Python from peak amps; render the class into the HTML string. |
| **Charts** | `solara.FigurePlotly(fig)` | Keep Plotly. Style traces with the token hexes (journey `#3B6FD4`, baseline `#D2785F`); set paper/plot bg transparent, gridcolor `#EBEDF1`, font IBM Plex Mono. Wrap each in `solara.Card(classes=["card"])` with a custom HTML header. |
| **Series key** | `solara.HTML` | Trivial flex strip. |
| **Control deck — selects** | `solara.Select(..., classes=["selectbox"])` | Vuetify select markup differs from a native `<select>`; you'll likely add scoped CSS overriding `.selectbox .v-input__slot`. If exact match matters, a raw `<select class="selectbox">` inside `solara.HTML` bound via a small JS/event is closest — but the Vuetify `Select` with override CSS is the pragmatic choice. |
| **Sliders** (device plan year, sizing, efficiency, horizon, social cost) | `solara.SliderFloat` / `SliderInt` | Vuetify slider ≠ this custom track/thumb. Either (a) override `.v-slider` heavily, or (b) build a raw `<input type="range" class="slider">` in `solara.HTML` and wire `on_value` via an event. The inline mono value label + live update is straightforward in Python (reactive). |
| **Checkboxes** ("Include in plan", solar, social cost) | `solara.Checkbox(..., classes=["check"])` | Vuetify checkbox has its own box SVG; to match the custom `.check .box`, raw HTML is cleaner. |
| **Segmented controls** (Insulation, vehicle profile, CAGR/ACC) | `solara.HTML` with buttons, or `solara.ToggleButtonsSingle` | `ToggleButtonsSingle` is the closest component but needs CSS to read like `.seg`. Raw HTML buttons + a reactive value is simplest. |
| **Install/Rebate inputs + Net pill** | `solara.InputText(..., classes=["input"])`; Net via `solara.HTML` | Net recompute = a derived reactive value in Python (no JS needed). |
| **Footer** | `solara.HTML` | — |

### 3. Device Details editor (modal)
Use a Vuetify dialog: `solara.lab.ConfirmationDialog` is too opinionated — prefer `with solara.v.Dialog(v_model=open, max_width="840"):` (raw vuetify) or `solara.Card` inside a dialog. Build the **inner body** (`.detail-top`, `.compare` two-column, `.costs-panel`) as styled Solara `Column/Row` + the same control mappings above. The green **Done** button = `solara.Button(classes=["btn","done"])`. Live behaviors (slider value labels, Net = install − rebate) become **reactive derived values** in Python — no client JS. Open state per device is a reactive var holding the active device key (`None` = closed).

### 4. Help popover (anchored card)
This is the one piece with no clean Vuetify match. Two options:
- **Simplest:** a Vuetify menu/tooltip — `solara.v.Menu` activated by the `?` button, with the card as its content slot. Vuetify handles anchored positioning/flip automatically. Style the slot with `.help-pop` classes.
- **Exact match:** port `help.js` as a small **custom Solara component** that mounts the same overlay + `getBoundingClientRect` positioning (Solara can include a JS snippet via `solara.HTML(unsafe_innerHTML=...)` or a Reacton custom element). Keep the content registry in Python (a dict keyed by `data-help`) and pass title/body/learn-more into the component.
Either way: store "open help key" as a reactive var; close on outside-click / ✕ / Esc.

### 5. Reusing `styles.css` against Vuetify — practical gotchas
- **Specificity:** Vuetify ships scoped styles with high specificity. Your overrides may need slightly more specific selectors or a scoping wrapper class; avoid `!important` sprawl by targeting `.your-wrapper .v-...`.
- **Where Vuetify fights you** (sliders, checkboxes, selects, segmented), prefer **raw HTML controls** styled by the existing `.slider` / `.check` / `.seg` / `.selectbox` rules — they already exist in `styles.css` and render identically to the prototype. Bind them to Python state through Solara events/reactive vars.
- **Charts:** drive Plotly colors from the same hex tokens so theme/palette switches stay consistent; if you keep the `data-palette`/`data-tone` theming, re-build the figure (or update layout colors) when the attribute changes.
- **Density/theme:** the `[data-density="compact"]` and tone/palette variants are pure CSS — expose them as toggles that set an attribute on the root wrapper; nothing else changes.

### 6. Suggested build order
1. Inject `styles.css`; render the static **masthead + verdict band + load strip** as `solara.HTML` fed by model values → validates tokens/fonts in Vuetify.
2. Wire **Plotly** charts into `.card` shells.
3. Build the **control deck** with raw-HTML controls bound to reactive state; confirm the model recomputes verdict/charts/load-strip (incl. peak threshold class).
4. Add the **details modal**, then the **help popover** last.
