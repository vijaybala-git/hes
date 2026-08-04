# Phase 5.5 — Fixups Spec (post-Phase 5)

> **Status:** Implemented (app-side). Fixes 1–6 landed on `main` (Fix 6 supersedes Fix 5's
> mechanism). The only remaining work is the **parent-wrapper snippet in §3.3**, which lives in
> the separate `hes.whywatt.org` repo (hand-off below) — and it turned out to already be in
> place, so the app just needs a redeploy.
> **Type:** Maintenance / correctness fixes surfaced during live user testing.
> **Scope:** Five defects. Phase 6 and Phase 7 remain unscoped and untouched.
> Last updated: 2026-08-04.

---

## 0. Why this phase exists

Three issues surfaced during real advocate sessions. None is a new feature — each is a
place where the model or UI does not behave the way a user reasonably expects:

1. **Furnace & AC size ignore home size.** Heating/cooling energy is identical for a
   900 sq ft and a 3,500 sq ft home at the same insulation level.
2. **The Water-Heater "Tank size" dropdown does nothing.** It looks live but never
   changes therms/yr — it was shipped as a stored-only placeholder.
3. **Shared "Load / Share my Scenario" links open to factory defaults.** The scenario
   in the link never reaches the app.
4. **Panel previews use a fixed reference climate, not the ZIP's** — and two Water-Heater
   sliders (inlet, setpoint) don't match the simulation. Surfaced while fixing #1/#2.
5. **The same share link shows different payback in different browsers.** The ZIP-derived
   CAGR is excluded from the link and races the auto-seeder on load. Surfaced during Fix 3
   cross-browser testing.

Each fix is grounded below with root cause, the exact change, and its test/regression
impact. Read this before implementing.

---

## Fix 1 — Furnace & AC scale with square footage

### 1.1 Root cause

HVAC energy is driven by the building heat-loss coefficient `UA` (BTU/hr/°F):

```
GasFurnace   therms[m] = HDD[m] × 24 × UA / (AFUE × 100_000)     src/devices/physics.py:57
HeatPumpHVAC kWh[m]     = HDD[m] × 24 × UA / (COP  × 3412)        src/devices/physics.py:102
             cooling    = CDD[m] × 24 × UA / (SEER × 1000)        src/devices/physics.py:105
CentralAC    kWh[m]     = CDD[m] × 24 × UA / (SEER × 1000)        src/devices/physics.py:199
```

`UA` is resolved once in the model from insulation quality **only**:

```python
# src/model.py:385
ua = float(UA_BY_INSULATION[home_config.insulation_quality])   # {poor:650, average:500, good:350}
```

There is **no square-footage term**. Two homes with the same insulation get the same
`UA`, hence identical furnace therms and identical AC kWh, regardless of size. Baseload
already scales with sq ft (`compute_baseload_kwh`, `src/home_config.py:11`); heating and
cooling do not. The `hvac_tonnage` control (`src/ui/sim.py:162`) feeds only the electrical
panel amps calc — never energy.

### 1.2 The model change

Heat loss through a building envelope scales, to first order, with conditioned floor
area. Make `UA` proportional to square footage, anchored so the current default home
(1,800 sq ft, "average") is unchanged at `UA = 500`:

```
UA = UA_BY_INSULATION[insulation_quality] × (square_footage / UA_REFERENCE_SQFT)
UA_REFERENCE_SQFT = 1800
```

Anchor values (BTU/hr/°F):

| insulation | per-1800 base | 900 sq ft | 1,800 sq ft (default) | 3,000 sq ft |
|------------|---------------|-----------|-----------------------|-------------|
| poor       | 650           | 325       | 650                   | 1,083       |
| average    | 500           | 250       | **500** (unchanged)   | 833         |
| good       | 350           | 175       | 350                   | 583         |

Linear scaling on floor area is the standard simplification for a tool at this fidelity.
Bedrooms are **not** added as a second HVAC factor — occupancy already drives baseload and
hot-water draw; adding it here would double-count.

### 1.3 Files to change

| File | Change |
|------|--------|
| `src/home_config.py` | Add `UA_REFERENCE_SQFT = 1800` and `def compute_ua(insulation_quality: str, sq_ft: int) -> float` returning `UA_BY_INSULATION[q] * sq_ft / UA_REFERENCE_SQFT`. |
| `src/model.py:385` | Replace the flat lookup with `ua = compute_ua(home_config.insulation_quality, home_config.square_footage)`. Import `compute_ua`. |
| `src/ui/panels.py:893` | HVAC detail preview: `ua = compute_ua(insulation_quality.value, square_footage.value)` (was `UA_MAP[insulation_quality.value]`). |
| `src/ui/panels.py:1465` | Same substitution in the second preview site. |
| `CLAUDE.md` | Update the "Key data constants" UA note to state UA scales with sq ft, anchored 1,800 → 500. |

> **Related:** the estimators in `src/ui/estimators.py` use a fixed reference climate
> (HDD 1910 / CDD 340), so the on-screen preview diverges from the ZIP-driven simulation.
> That is addressed in **Fix 4** below.

### 1.4 Test & regression impact

- `tests/test_devices.py` — **unaffected**. Those formula-regression tests inject `UA`
  directly (fixed reference), so the device physics is unchanged.
- Model-level golden master `tests/regression/golden.json` — **will shift** for any case
  whose home is not exactly 1,800 sq ft. Re-baseline via `scripts/run_regression.py` and
  review that the diff is confined to HVAC heating/cooling lines.
- **New test** (`tests/test_journey.py` or `tests/test_devices.py`): two homes differing
  only in `square_footage` yield different furnace therms and AC kWh; a 1,800 sq ft /
  "average" home still resolves to `UA == 500`.

---

## Fix 2 — Water-Heater "Tank size" is inert; wire the parameter that matters

### 2.1 Root cause & history

The "Tank size" dropdown sets `gas_wh_tank_gallons` / `hpwh_tank_gallons`
(`src/ui/panels.py:1044`, `:1055`), threaded into the device spec as `tank_gallons`
(`src/ui/sim.py:183`, `:193`). But neither `GasWaterHeater` nor `HeatPumpWaterHeater`
reads it — it is swallowed by `**kwargs` (`src/devices/physics.py:120`, `:151`).

This is by original design. `docs/Phase2_Spec.md §20.2`:

> "Add `tank_gallons` to `GasWaterHeater.__init__`. **Stored as an attribute for UI
> display and future standby-loss refinement. Physics formula is unchanged.**"

The "future refinement" never happened, so the control shipped looking live while doing
nothing. The `hpwh_ambient_location` toggle (`src/ui/panels.py:1059`) is the same story:
threaded to the spec (`src/ui/sim.py:194`), swallowed by `**kwargs`, never applied —
even though `§20.3` specified an ambient COP degradation for it.

Two UI tooltips currently make **false** claims (`src/ui/panels.py:1063-1067`,
`:1090-1094`): "standby losses are applied in the simulation" and "Ambient COP
degradation ... applied in simulation."

### 2.2 Decision: drop tank size, implement ambient COP

**Gas Water Heater uses UEF, not COP.** The federal Uniform Energy Factor is measured over
a 24-hour simulated-use test that **already includes standby loss**. Our formula divides
delivered energy by UEF (`… / uef`, `src/devices/physics.py:142`), so standby is already
embedded in the rating. Adding a separate tank-size standby term would **double-count**.
For a modern high-UEF tank the marginal standby from tank capacity is sub-5%, and daily
draw (gal/day) is the dominant driver.

Therefore:

- **A. Remove "Tank size" entirely** for both Gas WH and HPWH. Household size scales via
  the existing **Daily hot water (gal/day)** control; we say so in the help copy.
- **B. Implement the HPWH ambient COP degradation** — the one WH parameter that genuinely
  varies energy and was specified but never wired.
- **C. Correct the misleading tooltips.**

### 2.3 A — Remove tank-size controls

Delete every reference to `gas_wh_tank_gallons` and `hpwh_tank_gallons`:

| File | Change |
|------|--------|
| `src/ui/state.py:116-117` | Remove the two reactives. |
| `src/ui/state.py:313-314` | Remove from `reset_to_defaults()`. |
| `data/config/whywatt_default.json` | Remove the two `_DEFAULTS` keys. |
| `src/ui/config.py:189` | Remove the two `RANGES` entries. |
| `src/ui/sim.py:183, :193` | Remove the `"tank_gallons": …` spec keys. |
| `src/ui/panels.py` | Remove the four `solara.Select("Tank size …")` widgets (gas ×1, HPWH ×3). |
| `src/ui/layout.py:1150` | Remove `gas_wh_tank_gallons.value, hpwh_tank_gallons.value` from the `use_memo` deps. |

**Backward compatibility:** old share links / exported `.json` that still carry these keys
degrade gracefully — `sanitize()` (`src/ui/config.py:227`) emits `"unknown key ignored"`
and drops them. No crash, no reset.

### 2.4 B — HPWH ambient COP degradation

Effective heating COP for the heat-pump water heater is scaled by where the tank lives:

```
effective_uef = uef × AMBIENT_COP_FACTOR[ambient_location]
AMBIENT_COP_FACTOR = {"conditioned": 1.00, "unconditioned": 0.85}
```

`0.85` for unconditioned represents a garage/utility-space HPWH pulling from colder
ambient air for much of the year (lower evaporator temperature → lower COP). Confirmed as
the calibration figure for Phase 5.5.

| File | Change |
|------|--------|
| `src/devices/physics.py` | `HeatPumpWaterHeater.__init__` accepts `ambient_location: str = "conditioned"`; store an `AMBIENT_COP_FACTOR` map; divide by `uef × factor` in `monthly_consumption()` (lower factor → more kWh). |
| `src/model.py:152` | Pass `ambient_location=spec.get("ambient_location", "conditioned")` into `HeatPumpWaterHeater(...)`. |
| `src/ui/estimators.py:22` | `_est_hpwh` accepts an ambient factor so the preview moves with the toggle. |
| `src/ui/panels.py` | Pass ambient into `_est_hpwh` at the three HPWH preview sites (`:1050`, `:1075`, `:1103`). |

### 2.5 C — Fix tooltips

- Gas WH (`src/ui/panels.py:1063-1067`): replace the "standby losses are applied" line
  with *"Standby loss is included in the UEF rating. Set household size with the Daily hot
  water (gal/day) control above."*
- HPWH (`:1090-1094` and the equivalent gas-side note): keep the "Ambient COP degradation
  applied in simulation" line — it is now **true**.

### 2.6 Help copy

Add to the Water-Heater help section (`public/help/`): tank capacity does not change annual
energy in this model (standby is captured by UEF); to model a larger household, raise
**Daily hot water (gal/day)**. For the heat-pump water heater, placing the tank in an
**unconditioned** space (garage) lowers its effective efficiency by ~15%.

### 2.7 Test & regression impact

- `golden.json` — **unchanged**. Default `ambient_location` is `"conditioned"` (factor
  1.00) and no regression case overrides it (`tests/regression/cases/` verified); removing
  the inert tank param changes no energy.
- **New test** (`tests/test_devices.py`): a `HeatPumpWaterHeater` with
  `ambient_location="unconditioned"` consumes more kWh than one with `"conditioned"`, all
  else equal, by ~1/0.85.

---

## Fix 3 — Shared links restore the scenario (not factory defaults)

### 3.1 Root cause: cross-origin iframe, not validation

The encode → decode → sanitize round-trip is **correct** (verified: a 7-key delta encodes
to a 191-char blob and decodes back with zero dropped keys). The Load-from-file/bundled
dialog is also clean. The failure is the URL handoff.

The app runs inside a **cross-origin iframe** on `hes.whywatt.org`; `window.location`
inside the frame is the `*.hf.space` origin (`src/ui/share.py:20-25`,
`src/ui/layout.py:596`). Share links are built as
`https://hes.whywatt.org/?s=<blob>` (`share_base()` → `CANONICAL_BASE`,
`src/ui/share.py:25`). The consume path reads `router.search` **from inside the iframe**:

```python
# src/ui/layout.py:1096
blob = share.share_param(getattr(router, "search", None))
if blob:
    apply_config(share.decode(blob))
```

`?s=` lands on the **parent** page. The iframe's own URL has no `?s=` unless the parent
forwards it, and cross-origin policy blocks the iframe from reading the parent URL. So
`router.search` is empty → the guard skips → the recipient sees factory defaults. This is
systematic for every link opened via the pretty domain — matching the "many instances"
report.

Secondary path: if a messaging app truncates the long URL, `decode()` returns `{}` and
`apply_config({})` actively **wipes to factory** (REPLACE semantics). Worth hardening.

### 3.2 App-side fixes (this repo)

**A. Don't let a bad blob wipe state.** In `_consume_share_link`
(`src/ui/layout.py:1096`), apply only when `decode()` returns a **non-empty** dict:

```python
def _consume_share_link():
    blob = share.share_param(getattr(router, "search", None))
    if blob:
        clean = share.decode(blob)
        if clean:                     # empty == corrupt/truncated → leave state as-is
            apply_config(clean)
```

**B. Read the blob independent of Solara's router.** Add a small client-side reader
(anywidget/JS) that, on mount:
  1. reads the iframe's own `window.location.search` for `s=` (works if the parent
     forwards the query into the iframe `src`), **and**
  2. listens for a `postMessage` from the parent carrying `{ whywatt_share: "<blob>" }`,
  and hands whatever it finds to Python, which runs it through the same
  `decode()`-then-apply-if-non-empty guard.

**C. Test** (`tests/test_share.py`): a corrupt/truncated blob applied over a non-default,
in-progress scenario leaves that scenario intact (no factory wipe).

### 3.3 Parent-wrapper fix (separate repo — user-controlled)

The app-side reader (`_ShareLinkReader`, shipped in this repo) understands **two**
delivery contracts. The wrapper on `hes.whywatt.org` needs to implement **either one**
(implementing both is belt-and-suspenders and harmless).

**Option (a) — forward the query string (simplest, recommended).** When the wrapper builds
the iframe URL, append its own query string so `?s=` lands inside the frame. The reader
reads `window.location.search` on mount:

```html
<iframe id="whywatt" title="WhyWatt"></iframe>
<script>
  var APP_URL = "https://<your-space>.hf.space/";   // the app origin, no query
  document.getElementById("whywatt").src = APP_URL + window.location.search;  // carries ?s=
</script>
```

**Option (b) — postMessage handshake (survives in-frame navigation).** The reader posts
`{ whywatt_ready: true }` on mount and listens for `{ whywatt_share: "<blob>" }`. The
wrapper replies with the blob from its own URL:

```html
<iframe id="whywatt" src="https://<your-space>.hf.space/" title="WhyWatt"></iframe>
<script>
  var APP_ORIGIN = "https://<your-space>.hf.space";   // exact origin, for targeted postMessage
  var blob = new URLSearchParams(window.location.search).get("s");
  window.addEventListener("message", function (ev) {
    if (ev.origin === APP_ORIGIN && ev.data && ev.data.whywatt_ready && blob) {
      document.getElementById("whywatt").contentWindow.postMessage(
        { whywatt_share: blob }, APP_ORIGIN);
    }
  });
</script>
```

Either path delivers the blob to `_ShareLinkReader.blob`; Python then decodes and applies
it through the non-empty guard (`_apply_share_blob`), so a blank/corrupt blob is a no-op.
Contract for whoever edits the wrapper:

| Direction | Message | Meaning |
|-----------|---------|---------|
| app → parent | `{ whywatt_ready: true }` | frame mounted; safe to send the blob |
| parent → app | `{ whywatt_share: "<blob>" }` | the `s` value from the pretty URL |

> Share links are still generated as `https://hes.whywatt.org/?s=<blob>` via `CANONICAL_BASE`
> (`src/ui/share.py:25`) — unchanged. This fix only ensures the blob **reaches** the frame.

### 3.4 Test & regression impact

No model change; `golden.json` unaffected. Coverage added per 3.2.C.

---

## Fix 4 — Previews use the ZIP's live climate (and the WH inlet/setpoint stop lying)

### 4.1 Root cause

The display-only estimators (`src/ui/estimators.py`) that render the "~NNN therms/yr" /
"~NNN kWh/yr" figures under each device are hardcoded to a **fixed reference climate**,
while the simulation uses the ZIP-resolved zone:

```python
# src/ui/estimators.py
def _est_gas_furnace(afue, ua, annual_hdd=1910): ...     # fixed 1910 HDD
def _est_hp_hvac_heating(cop, ua, annual_hdd=1910): ...  # fixed 1910 HDD
def _est_hp_hvac_cooling(seer, ua, annual_cdd=340): ...  # fixed 340 CDD
```

The panels pass only `ua`, so the preview always uses 1910/340 regardless of ZIP. The
live model uses the ZIP's real zone (e.g. CZ4 = 2242 HDD / 554 CDD). Result: the number a
user reads in the panel does not match what the simulation charts — worst at hot inland
and cold mountain ZIPs.

The **Water-Heater** preview has a parallel but distinct problem. The sim computes hot-
water energy from the ZIP's **monthly inlet water temperature** (`climate.monthly_inlet`)
and the device's setpoint. But:

- The preview reads the manual **"Cold inlet"** slider (`wh_inlet_temp_f`), not the ZIP
  inlet — and that slider is **inert in the sim**: `_make_device` (`src/model.py:144-158`)
  never passes `inlet_temp_f`, so the sim always uses the ZIP's monthly inlet.
- The **"Setpoint"** slider (`wh_setpoint_f`) is likewise **inert in the sim** —
  `_make_device` never passes `setpoint_f`, so the sim always uses the device default
  120 °F. The preview *does* honor the slider, so preview and sim diverge whenever the
  user moves setpoint off 120.

### 4.2 Decisions

- **HVAC previews** → drive from the ZIP's live annual HDD/CDD.
- **WH inlet** is a climate/location property the ZIP already provides seasonally; a manual
  scalar slider is lower-fidelity and fights the ZIP value. **Remove the "Cold inlet"
  slider**; show the ZIP's mean inlet as read-only context; the preview uses the ZIP inlet
  so it matches the sim.
- **WH setpoint** is a genuine user preference (120 vs 130 °F). **Keep the slider and wire
  it into the sim** so it actually changes energy.

### 4.3 Files to change

**HVAC previews (climate in):**

| File | Change |
|------|--------|
| `src/ui/estimators.py` | `_est_gas_furnace` / `_est_hp_hvac_heating` take `annual_hdd`; `_est_hp_hvac_cooling` takes `annual_cdd` — keep the current values only as *fallback* defaults. (Signatures already accept them; the fix is that callers must pass live values.) |
| `src/ui/panels.py:893, :1465` | Already resolving `_ci = _climate_info(zip_code.value, climate_trend.value)` nearby (`:726`, `:1427`); pass `_ci.annual_hdd_65f` / `_ci.annual_cdd_65f` into the four `_est_hp_hvac_*` / `_est_gas_furnace` calls (`:919`, `:922`, `:941`, `:942`, `:957`, `:958`, `:978`, `:979`). |

**WH inlet — remove the manual slider, use ZIP inlet:**

| File | Change |
|------|--------|
| `src/ui/panels.py:1023` | Remove the "Cold inlet" `_DSl`. Compute `inlet = float(_climate_info(zip_code.value, climate_trend.value).monthly_inlet.mean())` and use it in the `_est_gas_wh` / `_est_hpwh` calls (`:1032`, `:1050`, `:1075`, `:1103`). Optionally render the ZIP inlet as a read-only line. |
| `src/ui/state.py`, `data/config/whywatt_default.json`, `src/ui/config.py`, `src/ui/sim.py:185`, `src/ui/layout.py` deps | Remove the `wh_inlet_temp_f` reactive + default + range + spec key + memo dep (mirrors the tank-size removal in Fix 2.3). Graceful degradation for old links via `sanitize()`. |

**WH setpoint — make it real:**

| File | Change |
|------|--------|
| `src/model.py:144-158` | Pass `setpoint_f=spec.get("setpoint_f", 120)` into both `GasWaterHeater(...)` and `HeatPumpWaterHeater(...)`. (`src/ui/sim.py:184`/`:196` already put `setpoint_f` in the spec.) |

### 4.4 Test & regression impact

- **HVAC previews** are display-only — **no** model/golden change; they now simply read the
  live zone. (Optional preview snapshot test if desired.)
- **WH setpoint wiring** — default setpoint 120 °F equals the device default, and no
  regression case overrides it, so `golden.json` is **unchanged**. Add a test:
  `GasWaterHeater(setpoint_f=130)` consumes more therms than at 120.
- **WH inlet removal** — sim already used ZIP inlet, so **no** golden change; only the dead
  slider and its schema key go away.

---

## Fix 5 — Shared links are deterministic (CAGR re-derived from ZIP)

### 5.1 Root cause

A user reported the **same** `?s=` link showing a different payback in Edge vs Chrome
(~$87.6K vs ~$95.1K). The blob was byte-identical apart from the gzip MTIME header
(a timestamp gzip stamps into every stream — a red herring; both decompress to the same
payload).

The real cause: the price-escalation sliders `elec_cagr_pct_a/b` and `gas_cagr_pct_a/b`
are excluded from the share delta (`SHARE_DERIVED`, `src/ui/config.py:111`) on the theory
that the recipient re-derives them from the ZIP. But two things write those reactives on
load and disagree:

- `_seed_eia_cagr()` (a `use_effect` in `RatesSummaryCard`, `src/ui/panels.py:804`) writes
  the **ZIP-derived** value (gas = **7%** for 95112);
- the share-link `apply_config()` writes the **factory** value (`whywatt_default.json` gas
  CAGR = **8%**, which does not match the ZIP seed).

Whichever effect runs **last** wins, and that order isn't stable across browsers/renders.
Confirmed end-to-end: gas CAGR 7% → net delta **$87,602**; gas CAGR 8% → **$95,059** — the
two reported figures exactly.

### 5.2 Decision & change

Per the "CAGR follows the local utility" design, the ZIP-derived value is authoritative.
Make it **win deterministically** by re-seeding right after any config/share apply, so load
order no longer matters.

| File | Change |
|------|--------|
| `src/ui/layout.py` `_apply_share_blob()` | After `apply_config(clean)`, call `_seed_eia_cagr()`. |
| `src/ui/layout.py` `_SettingsLoadDialog._apply()` | After `apply_config(...)`, call `_seed_eia_cagr()` (same race for bundled/uploaded configs). |

Trade-off (already documented at `config.py:111`): a **manually-overridden** CAGR is not
carried in a link — the recipient re-derives from their ZIP. Accepted; determinism wins.

### 5.3 Test & regression impact

No model change; `golden.json` unaffected. Added `tests/test_share.py`: a link that omits
CAGR re-seeds `gas_cagr_pct_a` to the ZIP value regardless of the pre-load slider state.

> **Superseded by Fix 6.** Fix 5 made Share *deterministic* but by re-deriving CAGR from the
> ZIP — which discards a manually-set CAGR (and doesn't help Export→Load). Fix 6 replaces the
> forced re-seed with faithful capture; the Fix 5 re-seed calls and its test are removed.

---

## Fix 6 — Scenarios reproduce verbatim (capture inputs; seed only interactively)

### 6.1 The principle

A **scenario is the complete set of user inputs**. Save/Share captures them all; Load/Open
restores them **verbatim**. Output = f(model version, inputs); **nothing is re-derived at
load time**. The only allowed source of a different result is a change to the model itself.

Auditing against this invariant surfaced two violations and confirmed there were no others:

- **CAGR** was excluded from the link (`SHARE_DERIVED`) and re-derived from the ZIP on load
  — a manual override was silently dropped, and the re-derivation raced the loader
  (Fix 5's symptom). *(Only load-time race: verified every `use_effect`; the slider syncs
  follow loads without clobbering, and `on_value` handlers fire only on user action.)*
- **`hw_gallons_user_override`** — a bool that gates whether `hw_daily_gallons` overrides the
  bedroom default (`sim.py:146`, `:336`) — affected the sim but was **not captured** (it sat
  in the transient set). A custom hot-water draw was dropped on load. *(The only non-captured
  reactive that feeds the sim; the other six transient reactives are pure view/label state.)*

`climate_zone` is captured but the sim re-derives it from the ZIP, so it can't cause a
mismatch (vestigial display state).

### 6.2 Changes

| File | Change |
|------|--------|
| `src/ui/config.py` | `SHARE_DERIVED` → empty set — CAGR is now captured like any input. |
| `src/ui/state.py` | Capture `hw_gallons_user_override` (init from `_DEFAULTS`, add to reset). Add the seed-suppression guard: `apply_config()` records the loaded rate context (`_loaded_ctx = _seed_ctx()`); `reset_to_defaults()` clears it; expose `_seed_suppressed()`. |
| `src/ui/sim.py` | `_seed_eia_cagr()` returns early when `_seed_suppressed()` — a loaded scenario's CAGR is never clobbered until the user changes the ZIP or a rate model. |
| `src/ui/layout.py` | Remove Fix 5's forced `_seed_eia_cagr()` calls (the `apply_config` mark handles it). |
| `data/config/whywatt_default.json` | Add `hw_gallons_user_override: false`. Align factory `gas_cagr_pct_a/b` **8 → 7** to match the default ZIP's real value (the ACC `acc_gas_cagr_*` sliders are untouched). |

**Why the seed-context guard is robust:** whether the seeder or the loader runs first on
mount, the loaded CAGR wins — after `apply_config` the live context equals `_loaded_ctx`, so
any seeder firing for that context is a no-op. Seeding resumes the moment the user changes
the ZIP or a rate model (context diverges). No widget wiring, no ordering assumptions.

### 6.3 Test & regression impact

- `golden.json` **re-baselined** (designed): aligning factory gas CAGR 8→7 lowers the
  all-gas "do nothing" baseline across the 12 cases (every `baseline_cost` fell, none rose;
  journey costs fell slightly from residual pre-swap gas years; electric unaffected). Trends
  still 37/37. This also *corrects* a latent gap — the harness had been running the default
  at 8% while the live app seeded 7%.
- `tests/test_share.py` (Fix 6): a manual CAGR is captured; it survives Share and Export→Load
  and is not re-seeded; a custom hot-water setting round-trips; a fresh session still seeds
  and (factory now aligned) still yields an empty link.

---

## Sequencing & verification

Land as four reviewable commits, in order:

1. **Fix 1** — UA scaling. Re-baseline `golden.json`; confirm the diff is HVAC-only.
2. **Fix 2** — drop tank size + HPWH ambient COP + tooltips + help. `golden.json`
   unchanged (assert it).
3. **Fix 4** — live-climate previews + remove WH inlet slider + wire WH setpoint into the
   sim. `golden.json` unchanged (assert it). *(Sequenced before Fix 3 because it touches
   the same WH panels/estimators as Fix 2 — keeps the model-layer work together.)*
4. **Fix 3** — app-side share hardening + reader. Hand off the parent-wrapper snippet.

Per commit:
- `pytest` full suite → green.
- `scripts/run_regression.py` → review/commit golden diff (Fix 1 only; assert unchanged for
  Fix 2 and Fix 4).
- Browser smoke via the preview: vary sq ft (furnace/AC move), toggle HPWH ambient (kWh
  moves), confirm the Gas-WH tank dropdown is gone, change ZIP (preview HDD/CDD/inlet track
  the zone), move WH setpoint (therms move), open a `?s=` link (scenario restores).

### Hard-rules compliance (CLAUDE.md)

- No `MMBtu` introduced. ✅
- Devices still receive climate/rates by injection; `compute_ua` runs in the model, not in
  a device reading a file. ✅
- `monthly_consumption()` still returns `(12,)` everywhere. ✅
- `HomeConfig` stays the single carrier of home details; UA derives from its fields. ✅
