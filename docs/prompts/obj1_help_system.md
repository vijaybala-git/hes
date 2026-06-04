# WhyWatt Phase 3 — Objective 1: Help System Skeleton

## Context

WhyWatt is a home electrification cost simulator built with Python 3.11+, Mesa 3.x,
Solara, and Matplotlib. Run with `solara run src/app.py`. The full Phase 3 spec is in
`docs/Phase3_Spec.md` — read §4 (Help / Documentation System) before starting.

This is Objective 1 of 6 in Phase 3. It is **purely additive** — no simulation code,
no device logic, no `HomeConfig` changes. Every deliverable is either a new file or
a new UI element bolted onto existing components.

**Tag `phase2` marks the clean starting point.** All work goes on `main`.

---

## What to Build

### Deliverable 1 — `src/help_content.py`

Create a new file `src/help_content.py`. This is the single source of truth for all
inline popup card text. No popup text lives in `app.py`.

```python
"""
help_content.py — Short-form popup text for every [?] button in the WhyWatt UI.
Each entry: (popup_text: str, learn_more_url: str)
learn_more_url is a relative path from docs/help/ (e.g. "hvac.html" or "rates.html#projection")
"""

HELP_POPUPS: dict[str, tuple[str, str]] = {
    # ── Main panel headers ────────────────────────────────────────────────────
    "journey_planner": (
        "The Journey Planner lets you schedule when each gas appliance gets replaced "
        "with an electric alternative. A 'Do Nothing' baseline runs in parallel so you "
        "can see the cost difference year by year over 20 years.",
        "journey.html",
    ),
    "home_profile": (
        "Home details — size, insulation quality, solar, and location — affect how much "
        "energy each appliance uses. Better insulation means less heating and cooling energy.",
        "climate.html",
    ),
    "energy_prices": (
        "Energy prices are based on current PG&E tariff rates with a projected escalation "
        "rate applied each year. You can adjust the escalation scenario in the Rate details.",
        "rates.html",
    ),

    # ── Device sub-panel rows ─────────────────────────────────────────────────
    "hvac": (
        "Heating and cooling energy is calculated from monthly degree-days for your "
        "climate zone, your home's insulation level, and the heat pump's efficiency "
        "rating (COP for heating, SEER for cooling).",
        "hvac.html",
    ),
    "water_heater": (
        "Water heating energy depends on how much hot water your household uses, the "
        "temperature of incoming cold water (varies by season and location), and the "
        "appliance's efficiency rating (UEF).",
        "water_heating.html",
    ),
    "dryer": (
        "Dryer energy is based on loads per week and energy per load. Heat pump dryers "
        "use roughly one-third the energy of gas dryers for the same number of loads.",
        "dryer.html",
    ),
    "cooktop": (
        "Cooking energy is estimated from daily cook time. Gas burners convert only "
        "about 40% of combustion energy to heat; induction transfers about 85% directly "
        "to the cookware.",
        "cooktop.html",
    ),
    "ev_charger": (
        "EV charging energy is estimated from your average daily miles driven and your "
        "vehicle's efficiency. Level 2 home charging is assumed.",
        "ev.html",
    ),
    "solar": (
        "Solar savings are modeled as a reduction in net electricity purchased from the "
        "grid each year. Battery storage shifts solar generation to evening hours.",
        "solar.html",
    ),
    "baseload": (
        "Baseload covers lights, outlets, refrigerator, and other always-on electricity "
        "uses. It scales with the number of bedrooms using DOE occupancy data.",
        "baseload.html",
    ),
    "panel_upgrade": (
        "A panel upgrade may be needed when adding high-draw appliances like a heat pump "
        "or EV charger to an older 100A service. The Panel Load callout above shows "
        "whether your planned journey requires one.",
        "panel.html",
    ),

    # ── Chart title bars ──────────────────────────────────────────────────────
    "chart_jc1": (
        "Annual cost is the total energy bill for that simulation year — electricity plus "
        "gas — for your journey home vs. the do-nothing baseline. The gap between the "
        "lines is your annual saving (or cost) in that year.",
        "charts.html#jc1",
    ),
    "chart_jc2": (
        "Cumulative cost adds up every year's bill from year 1 onward. The crossover "
        "point — where the journey line dips below do-nothing — is your payback year.",
        "charts.html#jc2",
    ),
    "chart_jc3": (
        "The summary bar shows total 20-year spend for each scenario side by side. "
        "The difference is your estimated lifetime savings from electrification.",
        "charts.html#jc3",
    ),
    "chart_jc4": (
        "Each segment shows one appliance's share of the annual energy bill. Watching "
        "this chart across years shows which swaps have the biggest cost impact.",
        "charts.html#jc4",
    ),
    "chart_r1": (
        "Rates are projected forward from today's PG&E tariff using a compound annual "
        "growth rate (CAGR). You can choose conservative, moderate, or stress scenarios.",
        "rates.html#projection",
    ),
    "chart_r2": (
        "The ACC (Avoided Cost of Carbon) seasonal shape shows how the effective "
        "electricity rate varies by month under the CPUC's avoided-cost framework. "
        "Summer peak hours carry the highest effective rate.",
        "acc.html",
    ),
    "chart_eu1": (
        "Annual energy consumption in physical units — kilowatt-hours for electricity "
        "and therms for gas. This shows how much energy is used before applying rates.",
        "charts.html#eu1",
    ),
    "chart_eu2": (
        "Each segment shows one appliance's share of total energy consumption. "
        "Compare journey vs. do-nothing to see which swaps reduce energy use most.",
        "charts.html#eu2",
    ),

    # ── Input field inline icons ──────────────────────────────────────────────
    "zip_code": (
        "Your ZIP code determines your CEC Building Climate Zone, which sets the "
        "monthly heating and cooling degree-days used in the HVAC calculation. "
        "California uses 16 official climate zones for building energy codes.",
        "climate.html",
    ),
}
```

---

### Deliverable 2 — `src/help_utils.py`

Create a new file `src/help_utils.py` with the `open_help()` function and the
Solara popup component. Keep this separate from `app.py` for testability.

```python
"""
help_utils.py — Help system utilities for WhyWatt.
"""
import os
import webbrowser
import solara

# Path to the docs/help/ directory, relative to this file's location
_HELP_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "help")


def open_help(topic: str, anchor: str = "") -> None:
    """Open a help HTML page in the default browser (file:/// URL, offline-safe)."""
    path = os.path.abspath(os.path.join(_HELP_DIR, topic))
    url = f"file:///{path.replace(os.sep, '/')}"
    if anchor:
        url += f"#{anchor}"
    webbrowser.open(url)


def _learn_more_url(learn_more: str) -> str:
    """Convert a relative help page reference to an absolute file:/// URL."""
    path = os.path.abspath(os.path.join(_HELP_DIR, learn_more))
    return f"file:///{path.replace(os.sep, '/')}"
```

Then add a `HelpPopup` Solara component to `src/help_utils.py`:

```python
# Reactive state — key of the currently open popup ("" = none open)
help_open = solara.reactive("")


@solara.component
def HelpButton(topic_key: str, style: str = ""):
    """Small circular '?' button that opens the popup for topic_key."""
    from help_content import HELP_POPUPS
    if topic_key not in HELP_POPUPS:
        return
    def on_click():
        help_open.set(topic_key)
    solara.Button(
        "?",
        on_click=on_click,
        style=(
            "min-width:20px; width:20px; height:20px; padding:0;"
            " border-radius:50%; font-size:0.75em; font-weight:700;"
            " background:transparent; color:#5C6BC0;"
            " border:1.5px solid #9FA8DA; cursor:pointer;"
            " line-height:1; flex-shrink:0;" + style
        ),
    )


@solara.component
def HelpPopupOverlay():
    """
    Single overlay instance — place once near the top of Page().
    Renders the popup card for whichever topic_key is in help_open.
    Dismissed by clicking ✕ or the 'Learn more' link.
    """
    import solara.lab
    from help_content import HELP_POPUPS

    key = help_open.value
    if not key or key not in HELP_POPUPS:
        return

    text, learn_more = HELP_POPUPS[key]

    def close():
        help_open.set("")

    def on_learn_more():
        # Parse anchor from learn_more (e.g. "charts.html#jc1")
        if "#" in learn_more:
            page, anchor = learn_more.split("#", 1)
            open_help(page, anchor)
        else:
            open_help(learn_more)
        close()

    with solara.v.Dialog(
        v_model=True,
        on_v_model=lambda v: close() if not v else None,
        max_width="360px",
        overlay_color="transparent",
    ):
        with solara.Card(margin=0, elevation=4):
            with solara.Row(style="align-items:center; justify-content:space-between; padding:8px 12px 4px"):
                solara.Text(key.replace("_", " ").title(),
                            style="font-weight:600; font-size:0.9em; color:#37474F")
                solara.Button("✕", on_click=close,
                              style="min-width:24px; width:24px; height:24px; padding:0;"
                                    " background:transparent; color:#78909C;"
                                    " border:none; cursor:pointer; font-size:0.9em;")
            with solara.Column(style="padding:4px 12px 12px"):
                solara.Text(text, style="font-size:0.85em; color:#546E7A; line-height:1.5")
                solara.Button(
                    "Learn more →",
                    on_click=on_learn_more,
                    style=(
                        "margin-top:10px; background:transparent; color:#3F51B5;"
                        " border:none; padding:0; font-size:0.82em;"
                        " cursor:pointer; text-decoration:underline;"
                    ),
                )
```

---

### Deliverable 3 — `docs/help/` directory and HTML pages

Create the directory `docs/help/` and the following files.

#### `docs/help/_template.html` (not served — developer reference only)

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>WhyWatt Help — TOPIC</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
           max-width: 760px; margin: 2rem auto; padding: 0 1.5rem;
           color: #222; line-height: 1.65; }
    header { display: flex; align-items: center; gap: 1rem;
             border-bottom: 2px solid #E8EAF6; padding-bottom: 1rem; margin-bottom: 1rem; }
    header img { height: 40px; }
    header h1 { margin: 0; font-size: 1.4rem; color: #1A237E; }
    nav { font-size: 0.88rem; margin-bottom: 1.5rem; }
    nav a { color: #3F51B5; margin-right: 1.2rem; text-decoration: none; }
    nav a:hover { text-decoration: underline; }
    h2 { margin-top: 2rem; padding-bottom: 0.3rem;
         border-bottom: 1px solid #E8EAF6; color: #283593; font-size: 1.1rem; }
    p  { margin: 0.6rem 0; }
    code { background: #F5F5F5; padding: 0.1em 0.35em; border-radius: 3px;
           font-size: 0.9em; }
    .note { background: #FFF8E1; border-left: 4px solid #FFC107;
            padding: 0.6rem 1rem; margin: 1rem 0; border-radius: 0 4px 4px 0; }
    .formula { background: #F3F4F6; border-left: 4px solid #9FA8DA;
               padding: 0.6rem 1rem; margin: 1rem 0; font-family: monospace;
               font-size: 0.88em; border-radius: 0 4px 4px 0; }
    footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #E8EAF6;
             font-size: 0.78rem; color: #9E9E9E; }
    footer a { color: #9E9E9E; }
  </style>
</head>
<body>
  <header>
    <img src="../assets/whywatt_logo.svg" alt="WhyWatt"
         onerror="this.style.display='none'">
    <h1>TOPIC NAME</h1>
  </header>
  <nav>
    <a href="index.html">← Help Index</a>
    <!-- add relevant cross-links here -->
  </nav>
  <main>
    <h2 id="what-this-means">What this means for you</h2>
    <p><!-- plain-English paragraph — no jargon --></p>

    <h2 id="how-it-works">How we calculate it</h2>
    <p><!-- readable formulas, not code --></p>

    <h2 id="assumptions">Key assumptions</h2>
    <p><!-- what we assume and why --></p>

    <h2 id="sources">Data sources</h2>
    <p><!-- links to CPUC, ENERGY STAR, EIA, NOAA, CEC --></p>
  </main>
  <footer>
    WhyWatt v3.0 · Data vintage: 2025 · <a href="about.html">About this tool</a>
  </footer>
</body>
</html>
```

#### `docs/help/index.html` — Help table of contents

Write a full index page with:
- WhyWatt logo (with `onerror` fallback), heading "WhyWatt Help"
- Brief intro: "This help system explains how WhyWatt models your home's electrification journey."
- Sections matching the three chart groups (Journey Costs, Rates, Energy Use) plus
  Appliances, Home & Climate, About
- Each link goes to its topic page
- Use the `_template.html` CSS (inline in `<style>`)

#### `docs/help/about.html` — About WhyWatt

Content:
- **What WhyWatt is:** A home electrification cost simulator for California community
  advocates. Shows long-term cost of an electrification journey vs. doing nothing.
- **What it models:** Energy costs (electricity + gas), appliance swap CapEx, rebates,
  solar + battery savings, over a 20-year simulation horizon.
- **Data vintage:** PG&E tariff data from 2025 CPUC filings. Climate data from NOAA TMY3
  (1991–2005 composite). Appliance specs from ENERGY STAR and AGA reference data.
- **Disclaimer:** "WhyWatt is a planning tool, not a financial guarantee. Actual costs
  depend on your specific appliances, usage patterns, utility rate changes, and many
  other factors. Consult a licensed contractor before making purchasing decisions."
- **Team:** Placeholder — "Developed with support from [organization name]."
- Use template CSS.

#### `docs/help/journey.html` — The Journey Model

Content:
- **What this means for you:** The Journey Planner shows what happens if you swap
  appliances on a schedule you choose — one by one, year by year — vs. doing nothing.
- **How the do-nothing baseline works:** Your current appliances continue operating with
  their current fuel type and efficiency throughout all 20 years.
- **What "swap year" means:** In the year you schedule a swap, the new appliance's
  install cost (minus rebate) appears as a one-time CapEx, and from that year forward
  the new appliance's operating cost replaces the old one.
- **Assumptions:** Appliance lifespans and replacement costs are not modeled beyond the
  journey swaps you configure. The simulation is deterministic — no randomness.
- Use template CSS. Cross-link to `hvac.html`, `rates.html`.

#### Stub pages — create these with minimal content (title + "Full content coming soon")

Create the following as stubs using the template structure. Each stub has:
- Correct `<title>`, logo header, nav with `← Help Index`, `<h1>` topic name
- One paragraph: "Detailed documentation for this topic will be available in a future
  release. Use the [?] popup in the app for a quick summary."
- Footer

Stub files to create:
`hvac.html`, `water_heating.html`, `dryer.html`, `cooktop.html`, `ev.html`,
`solar.html`, `baseload.html`, `rates.html`, `acc.html`, `climate.html`,
`panel.html`, `social_cost.html`, `charts.html`

> **Note on `charts.html`:** Add anchor tags for each chart ID so "Learn more →" links
> from popups resolve correctly even in stub form:
> `<h2 id="jc1">JC-1 — Annual Cost</h2>`,
> `<h2 id="jc2">JC-2 — Cumulative Cost & Payback</h2>`, etc. through `eu2`.

---

### Deliverable 4 — `app.py` changes

Make the following targeted changes to `src/app.py`. Read the file before editing.
Make surgical edits — do not restructure anything.

#### 4a — Import the help utilities at the top of app.py

After the existing imports, add:
```python
from help_utils import HelpButton, HelpPopupOverlay, open_help
```

#### 4b — Add "Help" button next to "Reset to defaults"

In `Page()`, locate the existing `solara.Button("↺ Reset to defaults", ...)`.
The Reset button is the last element in the header row. Add the Help button
**immediately after** the Reset button, inside the same row:

```python
solara.Button(
    "Help 📖",
    on_click=lambda: open_help("index.html"),
    style=(
        "background:transparent; color:#5C6BC0;"
        " border:1.5px solid #9FA8DA;"
        " border-radius:6px; padding:5px 12px;"
        " font-size:0.80em; cursor:pointer;"
        " white-space:nowrap; flex-shrink:0;"
        " transition:all 0.15s; margin-left:6px;"
    ),
)
```

#### 4c — Place `HelpPopupOverlay()` once in `Page()`

Inside `Page()`, immediately after `solara.Title("WhyWatt?")` and before any
layout content, add:
```python
HelpPopupOverlay()
```
This is the single popup instance reused for all topics.

#### 4d — Add `HelpButton` to each main panel header

Each main panel (`JourneyPlannerPanel`, `HomeProfilePanel`, `EnergyPricesPanel`) has
a grey title row:
```python
with solara.Row(style="background-color:#F0F0F0; ..."):
    solara.Text("🗺️ Your Electrification Journey", style="font-weight:600; ...")
```

Add a `HelpButton` at the end of each such row, right-aligned, using
`style="margin-left:auto"` to push it to the far right:

```python
# JourneyPlannerPanel header row:
with solara.Row(style="background-color:#F0F0F0; padding:6px 12px; ..."):
    solara.Text("🗺️ Your Electrification Journey", style="font-weight:600; font-size:0.95em")
    HelpButton("journey_planner", style="margin-left:auto")

# HomeProfilePanel header row:
with solara.Row(style="background-color:#F0F0F0; padding:6px 12px; ..."):
    solara.Text("🏠 Home + Solar", style="font-weight:600; font-size:0.95em")
    HelpButton("home_profile", style="margin-left:auto")

# EnergyPricesPanel header row:
with solara.Row(style="background-color:#F0F0F0; padding:6px 12px; ..."):
    solara.Text("📈 Energy & Prices", style="font-weight:600; font-size:0.95em")
    HelpButton("energy_prices", style="margin-left:auto")
```

#### 4e — Add `HelpButton` to each device sub-panel row

Each device summary card (`HVACSummaryCard`, `WHSummaryCard`, `EVSummaryCard`,
`CooktopSummaryCard`, `DryerSummaryCard`, `PanelSummaryCard`, `BaseloadSummaryCard`,
`SolarSummaryCard`) has a clickable header row with the device name and the `⋮` expand
button. Add a `HelpButton` between the device name text and the `⋮` button.

Read each SummaryCard component carefully before editing to find the exact row
structure. The `HelpButton` must not break the existing expand/collapse behavior.

Topic keys to use per device:
- `HVACSummaryCard` → `"hvac"`
- `WHSummaryCard` → `"water_heater"`
- `EVSummaryCard` → `"ev_charger"`
- `CooktopSummaryCard` → `"cooktop"`
- `DryerSummaryCard` → `"dryer"`
- `PanelSummaryCard` → `"panel_upgrade"`
- `BaseloadSummaryCard` → `"baseload"`
- `SolarSummaryCard` → `"solar"`

#### 4f — Add `HelpButton` to each chart title bar

Each chart is rendered with a title bar. Find the chart title rendering code for
each of the 8 charts (JC-1 through EU-2) and add `HelpButton("chart_jc1")` etc.
at the right end of the title row.

Read the chart rendering code to find the exact pattern before editing.
Chart topic keys: `chart_jc1`, `chart_jc2`, `chart_jc3`, `chart_jc4`,
`chart_r1`, `chart_r2`, `chart_eu1`, `chart_eu2`.

---

## Hard Rules for This Objective

1. **No simulation code changes.** Do not touch `src/model.py`, `src/journey.py`,
   `src/rate_loader.py`, `src/devices/`, or `src/home_config.py`.
2. **No changes to existing reactive state** — do not add to or modify `_DEFAULTS`.
3. The `help_open` reactive in `help_utils.py` is the only new reactive state.
4. All HTML pages must work as `file:///` URLs — no `http://` references,
   no external CSS/JS/font CDN calls anywhere in any help file.
5. The logo `<img>` tag must include `onerror="this.style.display='none'"` in every
   HTML page so a missing logo file does not break the page layout.
6. Run `solara run src/app.py` and verify the app starts without errors before committing.
7. Click every `[?]` button and verify: popup appears, ✕ closes it, "Learn more →"
   opens the correct HTML page in a browser window.

---

## Acceptance Criteria

- [ ] `src/help_content.py` exists with all `HELP_POPUPS` entries listed above
- [ ] `src/help_utils.py` exists with `open_help()`, `HelpButton`, `HelpPopupOverlay`
- [ ] Top-bar "Help 📖" button opens `docs/help/index.html` in a browser window
- [ ] `HelpPopupOverlay()` renders inline without crashing when `help_open` is empty
- [ ] Clicking `[?]` on any main panel header shows the correct popup text
- [ ] Clicking `[?]` on any device sub-panel shows the correct popup text
- [ ] Clicking `[?]` on any chart title shows the correct popup text
- [ ] "Learn more →" in every popup opens the correct HTML file (stub is fine)
- [ ] ✕ button and click-outside both dismiss the popup
- [ ] `docs/help/index.html` loads correctly as a `file:///` URL
- [ ] `docs/help/about.html` has real content (not a stub)
- [ ] `docs/help/journey.html` has real content (not a stub)
- [ ] All 13 stub pages exist with correct anchors in `charts.html`
- [ ] Simulation results (charts, numbers) are **identical** to Phase 2 — no regressions
- [ ] `git diff --stat phase2` shows only additions to `src/` and `docs/help/`
