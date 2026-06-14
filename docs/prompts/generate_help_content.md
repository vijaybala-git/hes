# WhyWatt — Help Content Generator (run per phase)

> Reusable prompt. Run after each Phase to regenerate `docs/help/help_content.md` so the
> in-app help matches the current specs **and** the current code. The output is a first
> draft for the "try the panel → read the help → comment" review loop — not a final.

## How to run

Set `PHASE = N` (the phase you just finished). Feed this prompt to Claude with read/write
access to the repo at the WhyWatt root. Claude produces an updated `help_content.md` plus a
short review report.

## What you are doing

You are the technical writer for WhyWatt. Regenerate the master help file
`docs/help/help_content.md` — a homeowner/advocate-facing user guide — so that every panel,
control, chart, and scenario in the app has accurate, plain-English help. A build script
turns this file into the `docs/help/*.html` pages, so your output must follow its format
exactly.

---

## Read these first (in order)

1. **`docs/help/help_content.md`** — the CURRENT help. **This is your voice and format
   exemplar.** Preserve its tone and any content that is still accurate. You are *updating*,
   not rewriting from scratch.
2. **`src/help_content.py`** — the `HELP_POPUPS` dict. **Its keys are the authoritative list
   of every `[?]` target in the UI.** Every key must end up covered by exactly one section;
   every section's `@keys:` must be real keys. This is your completeness check.
3. **`docs/Phase{N}_Spec.md`** (newest) plus earlier `Phase*_Spec.md` for context — the
   source of truth for WHAT each feature is: its parameters, defaults, ranges, and the
   data sources / citations behind every number.
4. **The code under `src/`** — especially `src/devices/`, `src/*config*.py`,
   `src/*_loader.py`, `src/panel_assessor.py`, and `app.py` — the source of truth for HOW it
   actually works: real defaults, real formulas, real ranges, and what is actually
   implemented versus only specced.

---

## The one rule that makes this trustworthy: code is ground truth

The spec describes intent; the code describes what the user will actually experience. When
they disagree, **describe what the code does**, and list the discrepancy in your report.
Never publish a number the code does not produce.

If a feature is specced but not yet implemented (common right after a phase split — e.g.,
something specced in Phase 4 but not yet coded), describe it as "coming in a future release,"
the way the existing file already does for SCE/SDG&E and Monte Carlo. Do **not** describe it
as live.

---

## List every default value — and where defaults live

Each help page must explicitly state the out-of-the-box default for every control it
documents, so a reader knows exactly what the app starts with before they touch anything.
Pull each default from the code's authoritative source, using the FIRST source below that
applies. Never invent or infer a value the code does not set.

1. **`_DEFAULTS` dict in `src/app.py`** — the canonical default for every user-facing
   reactive control: sliders, checkboxes, dropdowns, number inputs. This is the primary
   registry; most page defaults live here (e.g., `transport_mpg`, `solar_panels`,
   `external_ev_price_per_kwh`, `social_climate_rate`). Match the dict key to the control.
2. **JSON data files under `data/`** — defaults the UI loads rather than hard-codes:
   published rates (`data/rates/*.json`), climate constants (`data/climate/*.json`), and the
   default home/appliance/slot configs (`data/homes/*.json`, `data/appliances/*.json`).
3. **Dataclass field defaults and function-signature defaults in `src/`** — e.g.,
   `HomeConfig`, `SolarBatteryConfig`, device `__init__` parameters, and `HESModel.__init__`.
   These cover physics/engine defaults that are not exposed as a reactive control.
4. **Module-level constants** — conversion factors and lookup tables (e.g., the
   bedroom-scaling table, `KWH_PER_THERM`).

Rules:
- A page lists the defaults for the controls *that page documents* — no more, no less.
- If the same default is defined in more than one place, the values **must agree**. When
  they don't, state the one the user actually gets (the `_DEFAULTS`/JSON value) and flag the
  mismatch in your report.
- Use one uniform line format for every default so pages read consistently:
  `Control name — value unit (where to change it)`.
  Example: `Gasoline price — $4.50/gal (Energy & Prices → detail)`.
- Defaults are user-facing values, not code identifiers: write "Heat-pump heating
  efficiency — 3.5" not "`hp_cop_heating` = 3.5".

---

## Output format (the build script depends on this)

Reproduce the existing structure exactly. Keep the editor-instructions header block at the
top of the file unchanged. Do not alter lines beginning with `@`, `##`, or `###`, except to
add genuinely new sections — and call those out in your report.

```
## §N · <Human Title>
@file: <name>.html
@keys: <comma-separated keys that open this page — MUST match keys in src/help_content.py>
@popup: <2–3 sentences. The single most important thing to know. Runs until the next blank line.>

### What this means for you
<plain English, homeowner framing, no math, no jargon>

### How we calculate it          (include only where there is a calculation)
<the actual formula in readable notation, taken from the CODE; then a plain-English gloss>

### Key assumptions
<the defaults, and what to change if they don't fit this household>

### Default values
<every control this page documents, one per line, in the uniform format
"Control name — value unit (where to change it)". Values come from the authoritative
source per "List every default value" above. Include this section on any page that has at
least one adjustable control; omit it only for pure explainer pages with no controls.>

### Data sources
<every quantitative claim traced to a real source: CPUC, EPA, EIA, NOAA/NREL, PVWatts, AGA, ENERGY STAR, NEC, FHWA>
```

Notes:
- `@popup:` text may wrap across lines; it ends at the first blank line. Keep it to 2–3
  sentences.
- Under `###` headings, write plain paragraphs. Simple `-` bullet lists are fine. No bold,
  no tables, no nested formatting — the converter expects plain prose.

---

## Voice — match the existing file

- Second person ("your home," "you choose"), warm, plain English, lightly encouraging.
- Concrete numbers from the real defaults, with a brief real-world example where it helps
  (the existing §1 "swap year" and §4 HVAC examples are the target quality).
- Expand every acronym on first use: COP, UEF, SEER, AFUE, ACC, NEM, NBT, NEC, VMT, HDD/CDD.
- **No code identifiers, ever** — never write `SolarBatteryConfig`, `monthly_consumption()`,
  `DeviceSlot`, `self_consumption_fraction`, etc.

Good: "A home battery stores your midday solar so you can use it at night, instead of
selling it back to the grid for a fraction of what you'd pay to buy it."

Bad: "The `SolarBatteryConfig` derives `self_consumption_fraction` from `battery_kwh`."

---

## Process

1. Read the four inputs above.
2. **Build the coverage checklist:** the union of (a) every key in `src/help_content.py`
   and (b) every `[?]` target listed in the Phase spec's help inventory. That is the full
   set of targets that need a section.
3. For each target: update the existing section if it is still accurate, or draft a new one.
   Formulas and defaults come from the **code**; framing and data sources come from the
   **spec**; voice comes from the **existing file**.
4. **Self-check before emitting:**
   - Every key in `src/help_content.py` is covered by exactly one section's `@keys`.
   - No section's `@keys` references a key that does not exist in the code.
   - Every number matches a code default or a cited source.
   - No code identifiers and no unexpanded acronyms leaked into user-facing text.
   - Any specced-but-unimplemented feature is marked "future release," not described as live.
   - Every page with at least one control has a `### Default values` block, and every
     control documented on the page appears in it with a value that matches its authoritative
     source (`_DEFAULTS` / JSON / dataclass / constant). No listed default is one the code
     does not set.
5. Write the full updated `docs/help/help_content.md`.
6. Produce a short **review report** (in chat, not in the file):
   - Sections added / updated / left unchanged.
   - Coverage gaps: keys in code with no help, or `@keys` with no matching code key.
   - Spec↔code discrepancies you resolved in favor of the code.
   - Any numbers you could not verify against code or a source — flag these for the author
     to confirm.
   - Defaults coverage: any control whose default you could not locate in the code, and any
     default that conflicts between `_DEFAULTS`, JSON data files, and dataclass/function
     signatures (state which value you published and why).

---

## Per-phase note

Most of the file usually stays valid from one phase to the next — focus your edits on what
Phase {N}'s spec introduced or changed. But verify the whole file stays internally
consistent: when one model changes, sections that reference it often need a touch too. For
example, when solar moved from a "% coverage" slider to a "panels × kW" model, the EV, ACC,
and chart sections that mention solar also needed updating.

---

## Reviewer instructions (paste into the feedback request)

> Open the app, click into the panel/scenario, then open its `[?]` help. For each page, tell
> us: (1) anything that's wrong or doesn't match what the app shows, (2) anything confusing
> or jargon-y, (3) anything missing you wanted explained. Don't worry about wording polish —
> we want accuracy and clarity gaps.
