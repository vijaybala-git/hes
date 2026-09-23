# Offline URDB Rate Harvest — Implementation Plan (electric TOU + tiered)

**Status:** 🟢 ALL 3 CA IOUs BUILT & VALIDATED (2026-09-22) — PG&E + SCE + SDG&E harvested live
(19 plans), parsed, tested (13 green), reviewed, ZIP-attached, coverage-gated, and explorable in an
interactive notebook. Remaining: ZIP→baseline-region crosswalk + national expansion + Technical
Report (§8). The detailed build spec for the URDB half of
`docs/OfflineSolarData_Plan.md` §4b, expanded from a hand-picked tariff list into a
**ZIP / state / utility-parameterized sweep with a tagged default per utility**.
**Type:** Offline Python data-harvest sub-project. No `src/` consumption until Phase 7 (Invariant 1
of `docs/Phase7_Spec.md`). Mirrors the climate-DB / EIA / rate-projection harvest pattern.
**Prepared:** 2026-09-21.
**Supersedes:** the URDB paragraph of `OfflineSolarData_Plan.md` §4b (the PVWatts half of that doc
is unaffected). Feeds `docs/Phase7_Spec.md` §3 (peak/non-peak TOU rates).

---

## 0. TL;DR — what the deep-dive into the URDB API established

Three questions were posed for the review. Answers first, evidence in §1–§2.

| # | Question | Answer |
|---|---|---|
| 1 | Are **both gas and electric** rates available in URDB? | **Electric: yes. Gas: no.** URDB is an *electricity* rate database (≈3,700 utilities, ~70% of US load). It carries **no natural-gas tariff structures** — the OpenEI tools ship a fixed PG&E/SoCalGas example as a stand-in. **Gas therefore stays on the existing EIA path** (`eia_rates_by_utility.json` → `gas_ldcs`); this pipeline touches electricity only. |
| 2 | CA coverage (our starting point)? | Strong. PG&E, SCE, SDG&E, plus munis (SMUD, LADWP) and CCAs all have residential + TOU tariffs in URDB, each tagged with its **EIA-861 utility id** — the same key our `zip_to_electric_utility.json` already uses. |
| 3 | Broad coverage of other states + parameterizable? | Yes. URDB is national. Adding a state is a **data edit** (a row in `scripts/regions.py`) — no schema or code change. The harvest keys off `state` / `eiaid` / `ratesforutility`, all state-agnostic. |

**Consequence for the design:** this is an **electric-only** rate axis. The word "rates" in the
kickoff goal splits into two tracks that must not be conflated:

- **Electricity** → new URDB source. It supplies the **starting level** (replacing the EIA
  per-utility average where a tariff exists) **and the daily peak/off-peak shape**. ACC still
  supplies the **monthly** shape; projection still supplies the **escalation** (§5.2 rate stack).
- **Gas** → EIA `gas_ldcs` stays the base and the *only* gas source (decided §9); no free "URDB for
  gas" exists and no curated gas table is added. No URDB involvement, ever.

**"One tagged default":** URDB exposes an `is_default` flag, but it is sparse and not always the
residential tariff we want. We therefore compute our own **`whywatt_default: true`** per
(utility) during the harvest, via a deterministic selection policy (§4.3), so the sim can pick a
tariff with zero user input while still allowing an explicit tariff override later.

---

## 1. Coverage findings (the review)

### 1.1 Gas is not in URDB — and how we handle it

The URDB schema and API have **no gas tariffs**. Confirmed against the OpenEI wiki and the IES-VE
tariff-tool docs: OpenEI "doesn't have a utility gas rate structure," so downstream tools use a
single hard-coded PG&E / SoCalGas example. There is no `fuel` or `commodity` field to filter on;
every record is electric.

**Design response — do not force gas through URDB.** WhyWatt already prices gas well: EIA-176
per-LDC revenue÷volume with a 10-yr CAGR, resolved by ZIP in `RateResolver`. Phase 7 §0 already
declares gas *outside* the TOU/battery engine (`therms × single gas_rate`, no TOU). So:

- The URDB loader implements the **electricity** side of `get_peak_offpeak_rates()`.
- Gas keeps `RateLoader.from_eia_utility(gas_ldc_id, "gas")` untouched.
- `RateResolution.gas` is **not modified** by this work.

#### Is there a better gas source than EIA (by ZIP / utility)?

Researched. Summary: **for a free, national, utility-granular source, EIA-176 (already in use) is
the best available** — there is no free "URDB for gas."

| Option | Granularity | Level quality | Cost | Verdict |
|---|---|---|---|---|
| **EIA-176 per-LDC** (current) | per gas LDC (utility), by ZIP via `zip_to_gas_ldc.json` | revenue ÷ volume = all-in "what households pay" | free | **Keep as the base/fallback.** Best free per-utility source. |
| **EIA state residential price** | state | all-in average | free | already the fallback tier. |
| **Hand-curated CA LDC tariff sheets** (PG&E G-1, SoCalGas GR-1, SDG&E) | per utility | actual current published tariff (the gas analogue of what URDB gives for electric) | free, manual | **Recommended for a "current level" upgrade in CA** — only ~3 gas LDCs, so a tiny curated table gives a fresher level than the lagging EIA blend, exactly mirroring the electric URDB idea. |
| **RateAcuity API** | per utility, by ZIP/state, JSON | full gas tariff schedules (residential/commercial/industrial) | **paid** | the only "URDB-equivalent for gas," but commercial. Consider only if we go national and want tariff-grade gas without hand-curation. |
| **Genability** | mostly electric | — | paid | gas coverage thin; not worth it for gas. |

**Decision (§9): gas stays EIA-176 only.** No curated gas-tariff table. Rationale: EIA-176 is
already the best free per-utility gas source, gas is outside the TOU/battery engine (Phase 7 §0),
and adding a hand-curated table is scope the goal (a full *electricity* TOU estimate) doesn't need.
The RateAcuity option is noted only for a future national, tariff-grade gas push.

### 1.2 Electric coverage — CA and national

- **National:** ~3,700 utilities, ~70% of US retail load; residential, commercial, industrial,
  lighting sectors. Quality-controlled by NREL, updated at least annually; each rate has an
  `approved` (expert-verified) flag.
- **CA (target 1):** all three IOUs have current residential flat + TOU tariffs (PG&E E-TOU-C,
  E-ELEC, EV2-A; SCE TOU-D-4-9PM, TOU-D-PRIME; SDG&E TOU-DR1, EV-TOU-5), plus munis/CCAs.
- **The join that makes this usable:** every URDB rate carries an **`eiaid`** (EIA-861 utility
  number). That is *exactly* the id space `zip_to_electric_utility.json` and
  `eia_rates_by_utility.json["electric_utilities"]` are keyed on (e.g. PG&E = `14328`). So a URDB
  tariff can be attached to the utility our ZIP resolver already picks — **no new ZIP→utility
  crosswalk is needed**. This is the linchpin of the whole interface (§5).

### 1.3 Parameterization for more states

The harvest never hard-codes CA. A region/state table drives it:

```python
# scripts/regions.py  (extends the table OfflineSolarData_Plan.md §4 introduces)
REGIONS = {
  "bayarea": Region(state="CA", eiaids=[14328],            # PG&E
                    curated={"14328": "E-TOU-C"}),          # optional named default
  "socal":   Region(state="CA", eiaids=[17609, 16609],     # SCE, SDG&E
                    curated={"17609": "TOU-D-4-9PM", "16609": "TOU-DR1"}),
  # adding e.g. Texas is one row:
  # "austin": Region(state="TX", eiaids=[...], curated={...}),
}
```

Adding a state = append EIA ids (or just a `state=` sweep) + optional curated default names. The
build script, schema, loader, and tests are unchanged.

---

## 2. URDB API reference (as used here)

**Base:** `GET https://api.openei.org/utility_rates`
**Auth:** free OpenEI API key in `URDB_API_KEY` env var (never committed). Same key namespace as the
NREL/PVWatts key but a *separate* key.

### 2.1 Request parameters we use

| Param | Value we send | Purpose |
|---|---|---|
| `version` | `latest` (pin to `8` in provenance) | API/schema version |
| `format` | `json` | response format |
| `api_key` | `$URDB_API_KEY` | auth |
| `detail` | `full` | **required** — `minimal` omits `energyratestructure` + schedules |
| `sector` | `Residential` | residential only |
| `approved` | `true` | expert-verified rates only (quality gate) |
| `ratesforutility` **or** `eia` | utility name / EIA id | scope to one utility |
| `limit` / `offset` | `500` / paged | paging (max 500/page) |
| `orderby` / `direction` | `startdate` / `desc` | newest first (default-selection input) |
| `getpage` | a rate `label` | fetch **one** rate by id (re-pull / provenance) |

We deliberately scope by utility (`eia`/`ratesforutility`), **not** by `address`/`lat`/`lon`/
`radius`, because our ZIP→utility mapping is already authoritative and the geo search returns noisy
multi-utility sets.

### 2.2 Response fields we parse (per rate object, `detail=full`)

| Field | Meaning | Use |
|---|---|---|
| `label` | unique rate id (stable) | primary key / `getpage` re-pull |
| `eiaid` | EIA-861 utility number | **the join key to our utility DB** |
| `utility`, `name` | utility + tariff name | display / curation |
| `sector`, `approved`, `is_default` | classification flags | filtering + default hint |
| `startdate`, `enddate` | epoch validity window | recency ranking; drop expired |
| `energyratestructure` | list of tiers; each tier a list of periods `{rate, adj, sell, max, unit}` | tiered slabs + per-period $/kWh |
| `energyweekdayschedule` / `energyweekendschedule` | 12×24 arrays of period indices into `energyratestructure` | peak/off-peak hour map |
| `fixedchargefirstmeter`, `fixedchargeunits` | fixed monthly charge | carried for reference (not in TOU math yet) |
| `flatdemandstructure`, `demandratestructure` | demand charges | residential: usually absent; ignored |
| `energycomments`, `uri` | notes + human URL | provenance |

**Structure semantics (important):** `energyratestructure[i]` is **tier list** for *period i*; each
element is a tier `{max, rate, adj, sell}` where `rate+adj` is $/kWh up to `max` kWh. The 12×24
schedules map each (month, hour) → a **period index** `i`. So "peak vs off-peak" is derived by
grouping period indices, and "tiers/slabs" come from the tier list within a period. Both dimensions
coexist; our simplified schema (§3) flattens them for the 3-period WhyWatt engine.

### 2.3 Rate limits / etiquette

Offline, manual runs only (never CI/runtime). Respect OpenEI rate limits (~1000/hr on the free key):
the sweep is a few hundred calls for all of CA, so a small `time.sleep` between pages suffices.

---

## 3. Target baked schema — `data/rates/urdb_tou.json`

Additive across regions; one entry per **selected** tariff, plus every utility gets exactly one
`whywatt_default`. Keyed by `eiaid` so the loader joins on the id our resolver already produces.

```jsonc
{
  "_meta": {
    "status": "URDB residential TOU + tiered, states ['CA'].",
    "urdb_version": "8",
    "built": "2026-09-21",
    "sector": "Residential",
    "approved_only": true,
    "sources_sha256": { "<label>.json": "<sha256 of raw response>" }
  },
  "utilities": {
    "14328": {                         // EIA-861 id — the join key
      "utility": "Pacific Gas & Electric",
      "state": "CA",
      "default_label": "69de...E-TOU-C", // which tariff below is the sim default
      // NOTE: one utility → MANY tariffs. `tariffs` is the curated set (§4.2a), not a single plan.
      "tariffs": {
        "69de...E-TOU-C": {
          "label": "69de...E-TOU-C",
          "name": "E-TOU-C Residential Time of Use Baseline Region X",
          "family": "E-TOU-C",
          "plan_kind": "tou",            // tou | tiered_legacy | ev_tou  (§4.2a)
          "baseline_region": "X",        // PG&E territory that sets the baseline allowance
          "all_electric": false,
          "closed_to_enrollment": false,
          "whywatt_default": true,
          "is_urdb_default": false,      // URDB's own flag, for audit (unreliable → we curate)
          "approved": true,
          "startdate": "2026-03-27",
          "n_variants": 20,              // baseline-region + all-electric variants collapsed
          "variant_baseline_regions": ["P","Q","R","S","T","V","W","X","Y","Z"],
          "is_tou": true,                // false ⇒ flat: peak==offpeak every month
          "effective_level": 0.3541,     // all-in $/kWh @ rep_kwh — CROSS-CHECK/HEADLINE ONLY, not billed (§5.2)
          "rep_kwh_month": 500,
          "peak_hours": [16,17,18,19,20],// 4–9pm; weekend all off-peak
          "fixed_charge": {"value": 0.79343, "unit": "$/day"},
          // ── the billed structure: per-month peak/offpeak BASELINE-TIER LADDERS ──
          // tier `max_kwh_day` is the DAILY baseline allowance (×days = monthly slab); last tier open.
          "by_month": [                  // 12 entries; summer/winter differ (URDB carries seasonality)
            { "peak_period": 2, "offpeak_period": 3,
              "peak":    [{"max_kwh_day": 9.7, "rate": 0.31617}, {"max_kwh_day": null, "rate": 0.39757}],
              "offpeak": [{"max_kwh_day": 9.7, "rate": 0.28617}, {"max_kwh_day": null, "rate": 0.36757}] },
            /* … Feb–Dec … Jul example: peak [0.441, 0.5224], offpeak [0.318, 0.3994] … */
          ],
          "provenance": { "label": "69de...", "uri": "https://apps.openei.org/IURDB/rate/view/69de...", "eiaid": 14328 }
        }
        // ... E-1 (tiered_legacy), E-TOU-D, E-ELEC, EV, EV2 — kept for the picker (§5.6)
      }
    }
  }
}
```

Notes (reflecting the real PG&E parse):
- **Tiers are a DAILY baseline** (`max_kwh_day`, `unit: "kWh daily"` in URDB) with fixed charge in
  **`$/day`** — the pricing layer multiplies by days-in-month. Peak and off-peak share the same
  baseline threshold (so the whole-home slab in §5.2 is well-defined).
- **Seasonality lives in `by_month`** — summer (Jun–Sep) uses different URDB period indices/rates than
  winter, so no ACC monthly shape is applied on this path (§5.3).
- A **flat** tariff has `is_tou: false` and `peak == offpeak` every month, one tier — the
  revenue-neutral fallback (Phase 7 Invariant 4) falls out for free.
- **Baseline-region multiplicity:** E-TOU-C/E-1 have ~20 variants (10 regions × standard/all-electric)
  collapsed to one representative (`representative_region`, regions.py); the rest are recorded in
  `variant_baseline_regions`. **ZIP→baseline-region is the one crosswalk still missing** for
  per-ZIP-exact baselines (rates are identical across regions; only the allowance differs).
- The curated flagship raws are snapshotted under `data/rates/sources/urdb/<eiaid>_flagship_raw.json`
  with sha256 in `_meta.sources_sha256` (Invariant
  2 of Phase 7).

---

## 4. Harvest pipeline — `scripts/build_urdb.py`

`python scripts/build_urdb.py --region bayarea` (or `--state CA` to sweep every EIA id we price in
that state). Steps:

### 4.1 Enumerate target utilities
From `regions.py` (explicit `eiaids`) or, for `--state CA`, from the union of ids present in
`eia_rates_by_utility.json["electric_utilities"]` with `state == "CA"`. This guarantees we only
harvest tariffs for utilities the ZIP resolver can actually land on.

### 4.2 Fetch residential tariffs per utility
For each EIA id: page `utility_rates?eia=<id>&sector=Residential&approved=true&detail=full`
(limit 500). Snapshot each raw rate response under `sources/urdb/`. A single IOU commonly returns
**dozens** of residential records — this multiplicity is expected and must be handled, not assumed
away.

### 4.2a Taming multiplicity — N raw records → a curated selectable set (per utility)
**The core requirement: one (ZIP→)utility maps to *many* rate plans.** The harvest keeps more than
one per utility (the picker needs them), but not all of them. Deterministic curation, per utility:

1. **Drop non-usable:** expired (`enddate` in the past), empty `energyratestructure`, non-residential
   leftovers, `sector != Residential`, lighting/standby/street-light, and net-metering/DG-only rate
   sheets that aren't a consumption tariff.
2. **Exclude out-of-scope programs (for now):** income-qualified (CARE / FERA — consistent with the
   Phase 3 deferral of income-qualified rebates in `CLAUDE.md`) and medical-baseline. Detect by
   name/`energycomments` match; recorded in `_meta` so the choice is auditable and reversible.
3. **Classify what remains** into a small set of **plan kinds** the consumer would recognize:
   `tou` (E-TOU-C, TOU-D-4-9PM…), `tiered_legacy` (E-1-style, often *closed to new enrollment* but a
   consumer may still be on it — **kept, selectable, never default**), `ev_tou` (EV2-A, EV-TOU-5).
4. **Dedup + collapse variants:** many records are seasonal/territory sub-variants of the same plan;
   collapse by normalized plan name, keeping the newest `startdate`. Tag each survivor with its
   `plan_kind` and a `closed_to_enrollment` bool (from name/comments) for the picker.
5. **Cap:** keep at most ~6 plans per utility (the recognizable set); everything filtered is listed
   in `_meta.dropped[eiaid]` with the reason, so nothing vanishes silently.

The survivors are the `tariffs{}` set in §3; §4.3 then tags exactly one as `whywatt_default`.

### 4.3 Select the one `whywatt_default` per utility (layered policy)
Deterministic, auditable, in priority order:
1. **Curated name match** — if `regions.py` names a tariff (e.g. PG&E → `E-TOU-C`) and it exists,
   use it. (Human judgment wins for the flagship utilities.)
2. **URDB `is_default: true`** among residential TOU tariffs, newest `startdate`.
3. **Heuristic** — newest `approved` residential tariff whose name matches a TOU pattern
   (`TOU|E-TOU|TOU-D|EV`); else newest general residential tariff (flat).
Exactly one tariff gets `whywatt_default: true`; ties break on newest `startdate`, then `label`
(stable). The chosen policy tier is recorded in `_meta` per utility for the review notebook.

### 4.4 Parse URDB structure → simplified schema
- **Peak/off-peak split:** classify each period index as peak vs off-peak. Rule: the period(s)
  active during ~16:00–21:00 weekdays are "peak"; everything else "off-peak". (Solar-window is a
  Phase 7 dispatch concept, not a billing rate — it bills at off-peak, so it is *not* a separate
  URDB rate.) Fold `energyweekdayschedule` into `periods.peak`/`periods.offpeak` hour lists per
  month; collapse weekend into off-peak (residential weekend is off-peak on all three CA IOUs —
  assert and warn if a tariff violates this).
- **Tiers/slabs:** take tier `max`/`rate+adj` from `energyratestructure` for the peak and off-peak
  periods; emit the `tiers[]` list (whole-home monthly kWh thresholds).
- Emit `peak_offpeak_by_month` (12×2) at tier 1 for the quick path; keep full `tiers[]` for the
  slab-accurate home-level bill (Phase 7 §0).
- **Compute `effective_level`** (§5.2 nuance): blend the energy tiers at `rep_kwh_month` + add
  `fixed_charge_monthly ÷ rep_kwh_month`, so the level that replaces the EIA `current_rate` is
  all-in comparable. Store `rep_kwh_month` used.

### 4.5 Write + provenance
Merge into `urdb_tou.json` (additive by `eiaid`), write `_meta.sources_sha256`, snapshot raws.
Idempotent: re-running a region replaces only that region's utilities.

---

## 5. Interface architecture — raw URDB → RateStructure → Mesa sim

**This is the primary Phase 7 design work.** The offline half (this doc) extracts the *structure*;
this section defines the *contract* the simulation codes against. Three layers with hard boundaries,
so the sim never sees a raw URDB record and a non-URDB source can feed the same interface:

```
 raw URDB JSON  ──build_urdb.py (offline, this doc)──▶  normalized RateStructure  (urdb_tou.json, §3)
                                                                    │  loaded by
                                                        URDBRateStructure (runtime object, §5.2)
                                                                    │  two methods
        model.py aggregates each device's period-kWh to the HOME level, then prices once (§0.1 seam)
                                                                    ▼
                                            annual electricity bill  ($/year, by month)
```

The boundary that matters: **Layer 2 (the normalized `RateStructure`) is source-agnostic.** URDB is
the first producer; the EIA-flat fallback and any future source produce the *same* object. The sim
depends only on Layer 2, never on URDB field names.

### 5.1 Layer 1→2 — the normalized `RateStructure` (the contract)
The §3 schema *is* this contract. Its invariants (what the sim may assume):
- **period map** `(month, hour) → {peak | offpeak}` — carries **seasonality** (summer/winter windows
  and rates differ; that variation lives *inside* this map, see §5.3).
- **tiers** — ascending monthly-kWh thresholds, each with a `peak` and `offpeak` $/kWh.
- **fixed_charge_monthly**.
- **flat degrades cleanly** — a non-TOU/non-tiered tariff is `peak == offpeak`, one tier (Invariant 4).

### 5.2 Layer 2→3 — the runtime object and the *two* methods the sim calls
The whole interface is two methods, matching the §0.1 seam (consumption is per-device; the bill is
home-level):

```python
class URDBRateStructure:
    @classmethod
    def for_utility(cls, eiaid: str, tariff_label: str | None = None) -> "URDBRateStructure":
        # tariff_label=None -> utilities[eiaid].default_label (the whywatt_default)

    # (a) CONSUMPTION side — per device, pure geometry, no $ (§0.1 tier 1)
    def period_fractions(self, month: int, load_shape_24h) -> dict:
        # {"peak": Σ shape over peak hours, "offpeak": remainder}  -> device peak/offpeak kWh

    # (b) PRICING side — called ONCE on the home aggregate (§0.1 tier 3)
    def price_month(self, month: int, peak_kwh: float, offpeak_kwh: float) -> float:
        # total = peak_kwh + offpeak_kwh
        # walk ascending tiers on `total`; within each tier price its kWh split peak/offpeak
        # in proportion to (peak_kwh, offpeak_kwh); + fixed_charge_monthly.  Returns $ for the month.
```
- `period_fractions` is the existing `dot(load_shape_24h, mask)` machinery (the ACC loader already
  does this) — it is per-device and carries **no** pricing, so tiers/solar can't leak into a device.
- `price_month` is the **only** place tiers are applied, and it is called on the **home aggregate**,
  because the marginal tier depends on total home import (§0.1). Per-device $ for charts comes later
  from the §0.2 allocation helper — never from this method.

> **⚠ Tier↔period allocation convention (advocacy-grade simplification).** A kWh is physically in a
> period (peak/offpeak) but a tier is a whole-home billing construct. WhyWatt convention: walk tiers
> on the monthly **total**; the kWh in each tier is split peak/offpeak **in proportion** to the
> month's peak/offpeak totals, and priced at that tier's peak/offpeak rate. Documented, deterministic,
> and exact at the home total. (Real utilities vary — some apply a baseline *credit* rather than
> volumetric tiers; this is the one modeling liberty we take, flagged for the review notebook.)

*This `RateStructure` + `period_fractions`/`price_month` interface **refines** the single
`get_peak_offpeak_rates()` sketch in `Phase7_Spec.md` §3 — it splits that into the source-agnostic
structure (Layer 2) plus the home-level pricing method the §0.1 seam actually needs. Fold this naming
back into Phase7_Spec §3 when Phase 7 opens.*

### 5.3 Composition over sim years — seasonality is URDB's, escalation is the projection's
**Correction to the earlier "rate stack".** Under approach B the full URDB structure carries the
**monthly/seasonal** variation itself (the 12×24 schedule encodes summer vs winter periods and their
rates). Therefore:

| Factor | Owner under approach B | Note |
|---|---|---|
| Level (this year) | **URDB tier rates** | not a scalar — the tiers *are* the level (§5.1 box). |
| Daily peak/off-peak | **URDB** | in the period map + tier rates. |
| **Monthly seasonality** | **URDB** (was: ACC) | URDB's 12×24 already varies by month → **do not** also apply `acc_monthly_shape` to URDB tariffs, or it **double-counts**. |
| Escalation | **projection / CAGR** (Phase 7 §5) | URDB is a single-year snapshot. |

So the per-year composition is simply:
`rate[year, m, period, tier] = urdb_rate[m, period, tier] × escalation(year, scenario)`
— tier **thresholds (kWh) do not escalate**; only $/kWh does. The `× acc_monthly_shape[m]` term is
*removed* from the URDB retail path (URDB owns seasonality there).

**ACC is retained, not dropped (decided).** ACC keeps three roles: (1) it stays a **selectable
rate-model option** in its own right (the existing `acc_shaped` / `acc_seasonal` modes) — `urdb_tou`
is added *alongside* it, not in place of it; (2) it supplies seasonality on the **flat-EIA fallback**
path (§5.5), which has none of its own; (3) it drives the **NEM export credit**
(`get_nem3_export_rates`, avoided cost, not a retail tariff). Only the *combination* "URDB level ×
ACC monthly shape" is disallowed (double-count). ACC is a **candidate for future retirement** once
URDB coverage is broad enough, but that is out of scope now.

> **⚠ Why "the level" isn't a single stored number.** A tiered TOU tariff has **no scalar level** —
> the effective $/kWh depends on *how much* is used (which slab) and *when* (which period). That is
> exactly why the interface passes *usage* into `price_month` rather than reading a rate out. URDB
> stores the *structure*; EIA's `current_rate` is a derived all-in *average*. The scalar
> `effective_level` (§3) exists **only** for the §6 EIA cross-check and a UI headline — never billed.

### 5.4 Home-level wiring (`model.py`, Phase 7 — designed here)
Per sim year, per month:
1. each electric device → monthly kWh × `period_fractions(m, its 24h shape)` → device peak/offpeak kWh;
2. subtract solar self-consumption + battery discharge from **peak** first (Phase 7 §2);
3. aggregate to home `peak_kwh[m]`, `offpeak_kwh[m]`;
4. `price_month(m, peak, offpeak) × escalation(year)` → month electricity bill;
5. per-device $ for charts via the §0.2 allocation helper (presentation only — changes no total).

`RateResolver.resolve(zip)` already returns `RateResolution.electricity.utility_id` (an EIA id);
`URDBRateStructure.for_utility(eiaid)` keys off exactly that — no new ZIP→utility crosswalk.

### 5.5 Gas untouched / fallback ladder
- **Gas:** `RateResolution.gas` + `RateLoader.from_eia_utility(gas_id, "gas")` unchanged. The UI's
  "URDB TOU" option affects electricity only.
- **Electric fallback ladder — coverage-driven (§5.7).** `for_utility(eiaid)` consults the URDB
  *maintained-utility* list first: (1) maintained **and** harvested → its `whywatt_default`/explicit
  URDB label; (2) maintained but not yet harvested → **flat** EIA structure now, flagged as a
  harvest candidate; (3) not maintained, or ZIP unresolved → **flat** EIA structure (URDB not
  trusted). Flat = peak==offpeak, one tier, `× acc_monthly_shape` restored for seasonality. No path
  throws (Phase 7 Invariant 4).

### 5.7 "Can we USE a URDB rate?" — the coverage gate
OpenEI publishes and keeps current the ~114 utilities whose URDB rates are **updated annually**
(~70% of US load), stating plainly that *"rates for any utilities not listed should not be assumed
to reflect current tariffs."* We bake that list (`data/rates/urdb_coverage.json`, keyed by **EIA id**
— joins directly to the resolver) and gate on it, so the URDB-vs-EIA choice is **data-driven and
self-updating**, not "did we happen to harvest it":

| resolved utility (eiaid) | on the maintained list? | harvested here? | decision |
|---|---|---|---|
| e.g. PG&E 14328 | yes | yes | **`urdb`** — price off the URDB TOU structure |
| e.g. SCE 17609 (before harvest) | yes | no | **`harvest_candidate`** — trustworthy; run `build_urdb.py` |
| e.g. a small muni | no | — | **`eia_fallback`** — URDB may be stale → use EIA |
| ZIP unresolved | — | — | **`eia_fallback`** |

`scripts/urdb_coverage.py` implements `decide(eiaid) → {urdb, harvest_candidate, eia_fallback}` and
`can_use_urdb(eiaid)`; Phase 7 folds the same two-set check (maintained ∩ harvested) into the loader.
The coverage list is **national**; today's ZIP→utility crosswalk is CA-only, so out-of-CA ZIPs
currently resolve to the CA average and gate to `eia_fallback` until a national ZIP crosswalk lands.

### 5.6 ZIP → tariff choice (default + selection)
The goal — a *full TOU cost estimate* — means TOU rides in with the `RateStructure` automatically:
importing a URDB tariff *is* importing its TOU schedule. Given a ZIP:
1. `RateResolver.resolve(zip)` → `eiaid`.
2. `urdb_tou.json["utilities"][eiaid]["tariffs"]` → the **set** of residential tariffs on file (this
   is why §4.2 keeps *all* of them, not only the default).
3. The UI offers that set as a picker with `default_label` (`whywatt_default`, a TOU tariff)
   pre-selected — "what did you sign up for?" The consumer can switch (e.g. E-TOU-C ↔ EV2-A ↔ a flat
   legacy tariff); the sim rebuilds the `URDBRateStructure` for the chosen `label`.
4. No URDB tariffs for the utility → picker hidden, flat fallback used (§5.5).

Both scenarios ("do nothing", "your journey") price on the **selected** tariff — the swap changes the
tariff for the whole home, not per device. This is the electric analogue of today's rate-model
selector, but keyed to real per-utility tariffs instead of one shared PG&E base.

**Two multiplicities, both handled:**
- *utility → many plans* (the main case): the picker lists the curated `tariffs{}` set (§4.2a),
  grouped by `plan_kind`, legacy/closed plans flagged but still selectable.
- *ZIP → possibly many utilities*: `zip_to_electric_utility.json` values are already lists; the
  resolver picks one deterministically today. If a ZIP genuinely spans two utilities' territories,
  Phase 7 may surface a utility choice *above* the tariff picker (noted for the wiring phase — the
  data already supports it since tariffs are keyed by `eiaid`).

---

## 6. Validation + review (offline, before Phase 7 trusts it)

**`tests/test_urdb_data.py`:**
- every selected tariff parses to a 12×24 schedule with every (month,hour) mapped to a defined period;
- tier `max` thresholds strictly ascend; `rate+adj > 0`;
- **multiplicity:** a utility may carry ≥1 tariff; **exactly one** has `whywatt_default: true`; every
  `label` unique; `default_label` resolves into `tariffs`; every `plan_kind` ∈ {tou, tiered_legacy,
  ev_tou}; the default's `plan_kind == "tou"` (the full-TOU-estimate goal); no `whywatt_default` on a
  `closed_to_enrollment` plan;
- **cross-source sanity:** each default tariff's load-weighted flat-equivalent (dot with the `flat`
  device shape) lands within tolerance (say ±25%) of the matching `eia_rates_by_utility.json`
  per-utility rate — catches a mis-parsed tariff;
- flat tariffs collapse to `peak == offpeak` (fallback invariant).

**`notebooks/urdb_review.ipynb`:** 12×24 peak-hour heatmap per default tariff (confirm ~4–9pm),
peak-vs-offpeak bar with tier overlays, and the URDB-flat-equivalent vs EIA table.

**Isolation gate (until Phase 7):**
```bash
git grep -nE "urdb_tou|URDBRateStructure" -- src/ ':!src/**/*.md'   # must be empty pre-Phase 7
```

## 7. Repo layout (deltas)

```
scripts/
  regions.py            (extend) add eiaids + curated default tariff names per region
  build_urdb.py         (NEW) per-utility residential harvest -> urdb_tou.json + default tagging
  build_urdb_coverage.py(NEW) bake OpenEI's annually-maintained utility list -> urdb_coverage.json
  urdb_coverage.py      (NEW) the "Can we USE URDB?" gate: decide(eiaid) + can_use_urdb()
  build_baseline_crosswalk.py (NEW) CEC-zone -> baseline territory tables -> urdb_baseline_crosswalk.json
  urdb_baseline.py      (NEW) baseline_for_zip(eiaid, zip): ZIP -> CEC zone -> territory -> kWh/day
data/
  rates/urdb_tou.json   (NEW, baked) per-eiaid tariffs + whywatt_default + tiers + region_baselines
  rates/urdb_coverage.json (NEW, baked) ~114 URDB-maintained utilities, keyed by EIA id
  rates/urdb_baseline_crosswalk.json (NEW, baked) CEC zone -> baseline territory, per utility
  rates/sources/urdb/   (NEW) raw URDB JSON snapshots + coverage wikitext (sha256)
notebooks/
  urdb_rate_check.ipynb (NEW) advocate ZIP-check tool (ipywidgets, WhyWatt (venv) kernel): enter a
                        ZIP -> plain-English verdict (which rate + why: matched / no-URDB / CA-avg),
                        example-ZIP outcomes table, and the plans/rates behind a ZIP
docs/reports/
  URDB_Rate_Report      (NEW) published Technical Report — methodology, CA coverage, tariff tables
tests/
  test_urdb_data.py     (NEW) schedule parse + slab order + default tagging + EIA cross-check
```

## 8. Build order — first deliverable is the offline pipeline + a Technical Report

The immediate goal is **not** sim wiring. It is: harvest the CA URDB data offline, validate it in a
notebook, and **publish it as a Technical Report** (the pattern of `docs/reports/
RateModel_Impact_Report`), review-only behind the isolation gate. Sim consumption follows in
Phase 7 proper against the §5 interface.

- [x] `regions.py` — CA/PG&E `14328`, curated default TOU `E-TOU-C`, representative region `X`.
- [x] `build_urdb.py` — fetch (DEMO_KEY / `URDB_API_KEY`) or `--from-cache` → curate 500→6 flagship →
      tag TOU default → parse `by_month` structure → `urdb_tou.json` + raw snapshot (sha256).
- [x] `test_urdb_data.py` **green (11 passed)** — schedule parse, ascending daily-baseline tiers,
      one TOU default, seasonality present, EIA cross-check (E-TOU-C 0.354 vs EIA 0.396, ratio 0.89),
      ZIP-attachment smoke.
- [x] `notebooks/urdb_rate_check.ipynb` — **single advocate ZIP-check tool** (consolidates the earlier
      review + explorer notebooks): enter a ZIP → plain-English verdict of which rate the sim will use
      and *why* (matched URDB / not-maintained → EIA avg / muni → CA average), a fidelity rating, an
      example-ZIP outcomes table, and the plans/rates behind a resolved ZIP. `WhyWatt (venv)` kernel.
- [x] Isolation grep-gate green (no `src/` reads `urdb_tou.json`).
- [x] **ZIP attachment proven:** San Jose/Palo Alto/Fresno → PG&E (matched) → E-TOU-C + 6-plan set;
      LA → SCE → flat fallback. Uses the existing `eiaid` resolver, no new crosswalk.
- [x] **Coverage gate built (§5.7):** `build_urdb_coverage.py` → `urdb_coverage.json` (114 maintained
      utilities, all 4 CA IOUs/munis present); `urdb_coverage.py decide()` → San Jose `urdb`, LA
      `harvest_candidate`, out-of-CA `eia_fallback`. 2 coverage tests green (13 total).
- [x] **ZIP→baseline-region crosswalk built** — via the authoritative ZIP→CEC-climate-zone backbone
      (`zip_to_zone.json`) → per-utility CEC-zone→territory tables (`urdb_baseline_crosswalk.json`) →
      per-territory baselines baked in `urdb_tou.json` (`region_baselines`). `urdb_baseline.py
      baseline_for_zip()` resolves it. Confidence: SDG&E **high** (zones = CEC boundaries), PG&E
      **approximate** (territories climate-matched, verified vs harvested baselines), SCE **n/a**
      (flat TOU default has no baseline). PG&E baseline spread is 3.3× (5.9–19.2 kWh/day) so this
      matters. 2 crosswalk tests green (15 total).
  - [ ] *Optional upgrade:* replace the PG&E approximate CEC→territory table with an authoritative
        parse of PG&E's published territory definitions (by community/county/elevation).
- [x] **Technical Report written** — `docs/reports/URDB_Rate_Report.md` + self-contained `.html`
      (+ `public/help/` copy) via `scripts/build_urdb_report.py`. Title *"How the starting electricity
      and gas rates are determined"*: §1 ZIP→utility, §2 URDB + 3 CA utilities + full peak/off-peak
      rate table, §3 daily+seasonal bar, §4 starting-rate→Moderate-projection vs EIA Pacific.
  - [ ] *Remaining:* add the Help → Technical Reports link in `src/ui/layout.py` (mirrors the impact
        report link) so the app surfaces it.
- [x] **SoCal harvested live** (user's `URDB_API_KEY`): SCE `17609` → 5 plans (TOU-D-4-9PM default,
      eff $0.291); SDG&E `16609` → 8 plans (TOU-DR-1 Coastal default, eff $0.338). All 3 CA IOUs now
      in `urdb_tou.json` (19 plans total). Robust evening-peak detection handles 4-9pm vs 5-8pm windows.
- [ ] Interface hand-off: fold the §5 `RateStructure`/`price_month` naming + ACC-seasonality
      correction into `Phase7_Spec.md` §3 for the wiring phase.

---

## 9. Decisions (all resolved)

- ✅ **Gas stays EIA-176 only.** URDB is electric-only; gas is entirely the existing EIA `gas_ldcs`
  path. No curated gas-tariff table.
- ✅ **Approach B — full structure, no assumed band in the bill (§5.2).** URDB tariffs carry their
  full tier + TOU structure into the sim; the home's *real* aggregate monthly kWh selects the tier
  in the Phase 7 §0 slab engine. `effective_level` at a fixed `rep_kwh_month` (~500 kWh/mo) is
  emitted only for the EIA cross-check + UI headline, never billed.
- ✅ **URDB owns level + daily + seasonality; projection owns escalation; ACC retained as an option
  (§5.3).** URDB's 12×24 schedule already carries seasonality, so `acc_monthly_shape` is *not*
  applied on the URDB path (would double-count). ACC is **kept**, not dropped: it remains a
  selectable rate-model mode (`acc_shaped`/`acc_seasonal`), supplies seasonality to the flat-EIA
  fallback, and drives NEM export credit. Candidate for future retirement once URDB coverage is
  broad — not now.
- ✅ **Default is TOU — the whole goal is a full TOU cost estimate (§4.3).** The `whywatt_default`
  per utility is a residential **TOU** tariff (curated name → URDB `is_default` → newest approved
  TOU). "Do nothing" and "Your journey" are *both* priced on the TOU structure — that is the point
  of Phase 7. (A flat legacy tariff can still be *offered* in the picker, but is not the default.)
- ✅ **ZIP → tariff choice, with a default (§5.6).** Entering a ZIP resolves the utility; if URDB
  tariff(s) exist for it, the UI offers the **set of residential tariffs** (what a consumer may have
  signed up for) with the `whywatt_default` pre-selected. This is why the harvest keeps *all*
  residential tariffs per utility (§4.2), not just the default.
- ✅ **First deliverable = the offline pipeline + published data as a Technical Report (§8).** Like
  the existing `docs/reports/RateModel_Impact_Report`. Sim wiring is Phase 7 proper and stays behind
  the isolation gate until then. **CA first** (PG&E, then SCE/SDG&E); schema state-parameterized for
  later expansion.
- ✅ **Per-region starting rate replaces the single PG&E base (§5.4).** Today the `acc_shaped`
  default path prices every region off one hardcoded PG&E/CPUC base (`ACCRateLoader(RateLoader())`,
  `model.py:72,84`); only projection selection varies. Phase 7's URDB import makes the starting rate
  **ZIP/utility-specific** via the resolver that already exists — the projection-selection axis is
  unchanged.

*No open questions remain for the offline build. Phase-7-proper wiring items (new `urdb_tou` rate-
model option; how the tariff picker surfaces in the UI) are tracked in `Phase7_Spec.md` §3/§4.*
```
