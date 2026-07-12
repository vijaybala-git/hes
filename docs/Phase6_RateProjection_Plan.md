# Phase 6 × Energy Rate Projection — Reconciliation Plan (for stakeholder review)

**Status:** 🟡 DRAFT for review — not yet folded into `Phase6_Spec.md`.
**Inputs reconciled:** `docs/Phase6_Spec.md` (planned) + `docs/Energy_Rate_Projection_Spec.md` (methodology v1.0).
**Prepared:** 2026-07-07. **Rev:** 2026-07-08 — added §0 (resolved decisions) and §8 (spec clarity fixes).

---

## 0. Decisions resolved in this review cycle (2026-07-08)

These were open questions in the first draft; the team has now settled them. They are folded
into the sections below and struck from §6.

1. **ACC usage expands on three axes (agreed).**
   1. **Keep** today's use — ACC as the normalized *monthly shape*.
   2. **Add** — ACC drives the 20–25 yr *segmented escalation curve* (methodology §4). This is
      the "function instead of a number" the effort is really about.
   3. **Add** — re-source ACC per **CA climate zone** (today only CZ12 is extracted; the default
      home is CZ4). CZ4 becomes the primary; other CA zones follow.

2. **The marginal→retail bridge is ADDITIVE (residual), not a multiplier — confirmed against
   the spec.** `v = mc(ACC) + r(residual)`, with `r̄ = (1−φ)·RR/Sales` (spec §3, §5.2). There is
   **no** multiplier/gross-up anywhere in the mc→retail path (grep-verified). Rationale the spec
   must state explicitly (see §8):
   - The residual is the **majority** of the retail rate (retail ≈ $0.386/kWh vs ACC marginal of
     a few cents — the value we already use as the NEM export credit).
   - A **fixed** multiplier is technically wrong for CA: ACC marginal *flattens/falls* post-2045
     (grid decarbonization) while retail *rises* (wildfire/RR on shrinking sales). A constant `k`
     would drag retail *down* with marginal — backwards. A *time-varying* `k(y)` is just the
     residual re-encoded.
   - **Decision:** additive residual is the target model. A calibrated base-year multiplier is
     allowed only as an explicit **v1 shortcut** (clearly labelled) until the RR/Sales/φ harvest
     lands. "The curve out of ACC" means **ACC + residual**, never ACC-marginal alone.

3. **Scenario names kept, semantics changed (agreed).** Labels stay `conservative / moderate /
   stress`; each becomes a **three-curve scenario object** (RR, φ, Sales), not a single CAGR:

   | Code label (keep) | New meaning | Spec §10 name |
   |---|---|---|
   | conservative | low-RR / aggressive-disallowance floor | Conservative |
   | **moderate (default)** | **ACC + residual central CA reconstruction** (CA worse than EIA) | Central |
   | **stress** | **death spiral** (RR high, frozen φ, aggressive gas decline) | Death-spiral |

   `SCENARIO_PRESETS` in `model.py` therefore changes shape: from "one CAGR pair" to a scenario
   object carrying the three curves + social settings.

4. **The methodology spec is updated *before* implementation.** The concrete clarity fixes are
   listed in §8 below.

---

## 1. What the two documents ask for, and where they collide

**Phase 6** builds *seams* for Phase 7 — Solar/Battery split, roof-geometry inputs, and an
**offline harvest + notebook review** of PVWatts + URDB data — under one hard constraint:
**no number the user sees may change** (golden passes bit-for-bit).

**The Rate Projection methodology** replaces the model's single escalation number with a
**segmented growth *function*** (near / mid / long CAGR) and decomposes the retail rate into
`marginal (ACC) + residual`, a fixed charge, and a social overlay — with an explicit gas
"death-spiral" channel.

The user's intent: **fold the rate-projection work into Phase 6 as offline methodology +
Jupyter notebooks** — build the structure and the analysis surface, do **not** change output yet.
That is consistent with Phase 6's constraint *if and only if* the projection code is unwired,
exactly like the PVWatts/URDB data in §3.

### The core tension: ACC means two different things

| | **How the code uses ACC today** | **What the projection spec wants** |
|---|---|---|
| Role of ACC | Normalized **shape** (mean = 1.0/month), revenue-neutral | Absolute **marginal cost** `mc_f(y,m)` — a dollar level |
| Rate **level** source | EIA retail rate × one CAGR | `v = mc(ACC) + r(residual)` reconstructed from parts |
| Escalation | `base·(1+cagr)^(y−base)` (single number) | `base·Π_t(1+g_seg(t))` (segmented function) |

Confirmed in `src/rate_loader.py` and `scripts/extract_acc_shapes.py`: today ACC is
*deliberately decoupled* from the rate level. The methodology *inverts* this — ACC **becomes**
the level. These cannot be merged silently. **Phase 6's constraint forces the resolution:** the
projection methodology lives **offline only** in Phase 6; the live model keeps EIA + CAGR until a
later phase deliberately re-baselines the golden.

---

## 2. The good news — "a function instead of a number" is a contained change

The user's actual ask (a CAGR that bends over a 20–25 yr horizon) is methodology §4 and is a
*local generalization of one line*:

```
today:      rate = base · (1 + cagr) ** (year - base_year)          # rate_loader.py:118
segmented:  rate = base · Π_t (1 + g_seg(t)),  seg ∈ {near, mid, long}
```

Built as a **new, unwired `ProjectedRateModel` class**, this satisfies Phase 6 discipline
perfectly — same pattern as the committed-but-unconsumed PVWatts/URDB data (Invariant 5).

---

## 3. Issues, risks & blockers found in the codebase

1. **BLOCKER — the V1 validation fixture is not in the repo.** The methodology anchors V1
   (re-levelization) on an "uploaded 2025 LSC Hourly Factors" file (targets ≈ $6.70/kWh,
   $119/therm levelized, 30-yr @ 3% real). A filesystem search finds **no such file** under
   `data/`. Either locate and commit it (with provenance/sha256), or V1 must be restated.
   *Owner action needed before calibration.*

2. **Today's ACC extract is a single 20-yr *levelized* value, not a year-by-year path.** The
   methodology needs `mc_f(y)` annually for 2026→2045. What exists is one levelized number
   (`acc_electric_shape_pge_2024.json`) at **CZ12, base met-year 2018**. The full `mc_f(y)`
   trajectory must be re-harvested from the ACC workbook's annual columns — a new offline step.

3. **Climate-zone mismatch (pre-existing).** ACC shape is extracted at **CZ12** (Sacramento
   proxy); the model's default home is **CZ4** (South Bay). Methodology §7 wants CZ4. Decide
   whether the projection re-sources ACC at CZ4.

4. **The death spiral is an *input*, not an emergent output.** `r̄ = (1−φ)·RR / Sales`, and
   `Sales(y)` is a **grid-aggregate** CEC IEPR curve. WhyWatt models **one home**, so declining
   throughput is a **scenario assumption the advocate selects**, not something the sim derives.
   Stakeholders should agree on this framing before it reaches homeowners.

5. **Two specs now touch social cost with incompatible structures.** Phase 6 §4 adds citations
   to a **flat** $1.07/therm (`social_cost.py`). The methodology wants a **year-indexed rising
   SCC × declining-grid / flat-gas emission intensity** → a gas social cost that *grows over
   time*. Reconcile: is $1.07 the `y=0` anchor of `s_gas(y)`? Any time-varying version stays
   **offline** in Phase 6 (would otherwise change output).

6. **Three silent output-leak risks.** An accidental wire-in breaks the golden via:
   (a) `get_rate` escalation; (b) the **NEM export path**, which *already* consumes absolute ACC
   values × CAGR (`rate_loader.py:get_nem3_export_rates`); (c) `social_cost` application. The new
   projection module must be imported by **no** `src/` sim code — extend the §3 git-grep gate to
   cover `data/rates/projection/` and the new class.

7. **Scenario naming/axis mismatch.** Code: conservative / **moderate** / **stress** (single
   CAGR each, `SCENARIO_PRESETS` in `model.py`). Methodology: conservative / **central** /
   **death-spiral** across *three* axes (RR growth, fixed-charge policy φ, Sales) + social. Needs
   an explicit mapping table before either can drive anything.

8. **Scope roughly doubles.** Phase 6 §3 harvests **2** sources (PVWatts, URDB). The methodology
   adds ~**6–8** more data objects — ACC annual `mc`, residual `RR`, `Sales`, fixed-charge policy
   (AB 205 D.24-05-028), `SCC`, emission-intensity paths, methane params, health — plus the
   §8 three-curve residual infra. This must be a **bounded, explicit new section**, not absorbed.

9. **Base-year inconsistency.** Methodology base year = **2026**; EIA loader base = **2024**;
   CLAUDE.md quotes **2025** base rates. V3 backcast needs one agreed anchor.

---

## 4. Proposed Phase 6 addition — §5 "Rate-Projection Methodology (offline, unconsumed)"

Mirror the discipline of §3 exactly: real data, committed with provenance, validated by tests +
notebooks, but **read by no sim code**.

- **§5a — `ProjectedRateModel` (unwired class).** Implements the §4 segmented-escalation
  primitive and the §3 `mc + r`, `F`, `s` decomposition. Pure library; imported by nothing in
  the sim path. Config schema per component: `{X(0), g_near, g_mid, g_long}` (or the
  {2026,2030,2045,2050} anchor-knot variant).
- **§5b — `scripts/build_rate_projection.py` (offline harvest).** Pulls the new data objects
  (§3 table below), commits to `data/rates/projection/*.json` with raw snapshots + sha256 under
  `data/rates/projection/sources/`. Run manually, never in CI.
- **§5c — Residual 3-curve scenario infra (offline).** The `RR(y)`, `φ(y)`/`F(y)`, `Sales(y)`
  triples from methodology §8. No policy-specific code paths — a policy is just three curves.
- **§5d — Review notebook `notebooks/rate_projection_review.ipynb`** *(the deliverable the user
  asked for)*. Must render:
  - segmented-CAGR rate trajectories per scenario **vs today's single-CAGR line** (the "why a
    function" picture — where the curve bends at the 2030 / 2045 knots);
  - the `mc + r` decomposition stacked by fuel;
  - the **gas death-spiral** curve (`RR` flat ÷ declining `Sales`);
  - the **social overlay** (rising SCC × declining-grid vs flat-gas intensity + methane + health);
  - a **total-cost** panel (`Bill + Social`) so review shows **cost**, not just rates;
  - V1–V4 validation figures (§9 of the methodology) as inline charts.
- **§5e — Validation tests `tests/test_rate_projection.py`.** Encode V1 (re-levelization vs the
  LSC fixture), V2 (bound ordering EIA ≤ central ≤ death-spiral), V3 (backcast to 2025 PG&E
  actual), V4 (cross-fuel COP parity crossover) as a CI gate independent of the notebook.

### Data objects to harvest for §5b (from methodology §7)

| Object | Source | New file |
|---|---|---|
| `mc_elec` annual path | CPUC ACC 2024 (or 2026 draft) electric model, annual columns | `data/rates/projection/acc_marginal.json` |
| `mc_gas` | CPUC ACC Gas Model | ″ |
| `RR_elec` / `RR_gas` | E3 Fixed-Charge tool + PG&E GRC | `.../residual_rr.json` |
| `Sales_f` | CEC IEPR CED 2025 | `.../sales_throughput.json` |
| `φ` / `F` policy | AB 205 D.24-05-028 + scenarios | `.../fixed_charge_policy.json` |
| `SCC`, `ε_elec(y)`, `ε_gas`, methane, health | EPA 2023 SCC, CARB/CEC, EPA factors | `.../social_overlay.json` |
| **V1 anchor** | **2025 LSC Hourly Factors (MISSING — see §3.1)** | `.../lsc_2025_levelized.json` |

---

## 5. Explicitly deferred to Phase 7/8 (the golden-rebaseline moment)

- Replacing EIA + single-CAGR retail with live `mc + r` in `RateLoader.get_rate`.
- Wiring the time-varying social overlay into `social_cost.py`.
- Any change to the NEM export path from the new marginal object.
- These land where output is *expected* to change and the golden is re-baselined in a dedicated,
  diff-explained commit (same protocol as Phase 7 Invariant 5).

---

## 6. Open decisions to bring to stakeholders

*(Resolved in §0 and struck: scenario-name mapping; ACC re-source at CZ4; additive-vs-multiplier
bridge. Remaining:)*

1. **Does Phase 6 own the rate-projection methodology at all**, or is it a separate track that
   only *reuses* Phase 6's offline/notebook machinery? (Scope-doubling risk, §3.8.)
2. **Segment boundaries:** fixed 5/15 years vs structural 2030/2045 knots (methodology §11).
3. **Nominal vs real reporting**, and the single inflation assumption harmonizing all sources
   (affects every comparison against nominal EIA rates).
4. **Social cost:** net-of-compliance (default) vs gross; may `s` go negative? And how does this
   reconcile with Phase 6 §4's flat $1.07/therm (§3.5)?
5. **ACC vintage:** 2024 adopted (stable) vs 2026 draft (current). *(Zone resolved → CZ4, §0.1.iii.)*
6. **Methane GWP horizon:** GWP-20 vs GWP-100.
7. **Who owns finding/committing the 2025 LSC fixture** so V1 is buildable (§3.1).
8. **Is a base-year multiplier an acceptable v1 shortcut** while the RR/Sales/φ harvest is in
   flight, or does the additive residual land before *any* ACC-based curve ships? (§0.2.)

---

## 7. Recommended sequencing

1. Resolve §6 decisions #1, #3, #4, #7 first — they gate everything.
2. Land Phase 6 §1–§4 (Solar/Battery split, roof geometry, PVWatts/URDB harvest, SC-CH₄
   labels) as already specced — **independent of the rate-projection work**, golden untouched.
3. Add §5 as its own commits: harvest → `ProjectedRateModel` → notebook → validation tests.
   Keep the git-grep "no sim code reads it" gate green throughout.
4. Ship the three review notebooks together (`pvwatts_review`, `urdb_review`,
   `rate_projection_review`) as the offline-analysis review surface.
5. Phase 7 consumes what survives review.

---

## 8. Clarity fixes required in `Energy_Rate_Projection_Spec.md` before implementation

The methodology is sound but under-specified in ways that already caused confusion in review.
Fix these in the spec (bump it to v1.1) **before** any code is written against it.

### 8.1 — State the marginal→retail bridge in plain words (highest priority)

The spec never says outright that **ACC does not become retail via a multiplier — the residual
`r` is the bridge, added on top.** A reader expecting a gross-up factor won't find one and can
misread the whole architecture. Add to §3 / §5.1:

- One sentence: *"Retail is reconstructed additively: `v = mc + r`. We deliberately do **not**
  scale ACC by a retail-markup multiplier — the residual `r` supplies the gap, and it moves
  independently of `mc`."*
- The **magnitude** cue: ACC marginal ≈ a few ¢/kWh (the NEM export-credit level); retail ≈
  $0.386/kWh — so `r` is the *majority* of the bill, not a minor adder.
- The **directional** argument: `mc` flattens/falls post-2045 while retail rises, so a fixed
  multiplier is structurally wrong; only an additive (independently-escalating) residual captures
  the CA divergence. State whether a base-year multiplier is an allowed **v1 shortcut** (§6.8).

### 8.2 — Disambiguate "the curve out of ACC"

Clarify everywhere that ACC-marginal **alone is lower than EIA**, not worse. The scenario that is
"worse than EIA" is the **reconstructed retail (`mc + residual`)**, driven by the rising residual.
Rename loose references to "ACC projection" → "ACC-based reconstruction" so no one expects
ACC-marginal by itself to exceed EIA.

### 8.3 — Resolve the LSC / V1 fixture (blocker)

§7 line 225, §9 V1, and §12(e) all lean on an **"uploaded 2025 LSC Hourly Factors"** file that is
**not in the repo** and whose acronym is never expanded. The spec must either:
- name the exact source, expand "LSC", and require it committed with provenance (sha256) at
  `data/rates/projection/lsc_2025_levelized.json`; **or**
- restate V1 against a source that *is* obtainable (e.g. published 2025 PG&E levelized figures),
  and drop the $6.70/kWh / $119/therm targets if they can't be traced.

### 8.4 — Pin the scenario semantics change

§10 should state that WhyWatt keeps the labels `conservative / moderate / stress` but that each is
now a **three-curve scenario object** (RR, φ, Sales) — *not* a single CAGR — mapping to
Conservative / Central / Death-spiral (per §0.3 of this plan). Call out that `moderate` is the
**default** and represents the central CA reconstruction.

### 8.5 — Specify the ACC extraction contract for the annual path

Today's extract is a single 20-yr *levelized* value at **CZ12, met-year 2018**. §5.1 must specify
what Phase 6 actually pulls: **per-year `mc_f(y)` columns (2026→2045) at CZ4** (+ other CA zones),
which workbook sheet/column, and how beyond-2045 uses the `long` segment. Without this the harvest
script has no target schema.

### 8.6 — Close the §11 open decisions that gate calibration

At minimum resolve, in the spec: nominal-vs-real (and the inflation number), net-vs-gross social
cost and its reconciliation with the existing flat $1.07/therm, GWP horizon, and ACC vintage
(2024 vs 2026). Calibration cannot start while these float.

### 8.7 — Clarify Sales(y) is an exogenous scenario input

Make explicit that `Sales_f(y)` (the death-spiral denominator) is a **grid-aggregate assumption
the user/scenario selects**, not something WhyWatt derives from its single-home simulation. The
current wording ("couples to the consumption model's aggregate electrification assumption") reads
as if the sim produces it.

### 8.8 — Division of labour: which source sets *base* vs *growth* (resolves §3.1's plug question)

The spec never states cleanly which source fixes the base year and which sources drive growth.
Reviewers kept conflating "URDB gives the rate" with "URDB gives the revenue requirement." Add a
single table to the spec pinning the division of labour, and adopt the **URDB − ACC plug** for the
residual base level (this resolves the bucket-sum-vs-plug ambiguity of §3.1 / §5.2):

| Object | Source | Sets… |
|---|---|---|
| `v_f(0,m)`, `F_f(0)` | **URDB** (today's tariff: `$/kWh`, `$/therm`, slabs, `fixed_charge`) | the **base-year retail level only** (not growth, not `RR`) |
| `mc_f(0,m)`, `κ_f(m)`, `g_mc^seg` | **ACC** | the **marginal** base level, monthly shape, and **marginal** growth curve |
| `RR_f(y)`, `φ_f(y)`, `Sales_f(y)` | GRC / E3 tool / CEC-IEPR / AB 205 | the **residual** growth (and fixed/volumetric split) |

**Base-year residual = plug, not bucket-sum.** Compute `r̄_f(0) = v_URDB(0) − mc_ACC(0)` directly
(it auto-satisfies the V3 backcast). The `RR` buckets (embedded T&D, wildfire, legacy contracts,
public-purpose, CARE/FERA, NEM shift) then serve **only** two purposes: (1) informing *how* the
residual grows (bucket-specific segment rates — wildfire fast, T&D slow), and (2) scenario surgery
(e.g. "state-budget shift" removes the wildfire bucket). This means the harvest does **not** need a
reconciled bottom-up dollar sum for the base level — a relief, since GRC bucket totals rarely
foot to the tariff exactly.

**Corrections the spec must also make (came up in review):**
- **URDB is a *rate*, not a *revenue requirement*.** `RR` is dollars; `v` is `$/unit`. Do not
  describe URDB as delivering `RR`.
- **The ACC segmented CAGR applies to `mc` only** — *not* to the whole retail rate. The retail
  growth curve is **emergent**: `mc` (slow/flat, may fall post-2045) **+** residual (fast-rising).
  Nobody reads a single retail CAGR off ACC.
- **Unit consistency** between `RR` (class-total vs per-customer $) and `Sales` (class-total vs
  per-customer throughput) must be pinned, and a customer-count series named for `F = φ·RR/(12·Cust)`.

**One-line assembly to add to §3 of the spec:**
```
Retail(y,m) = mc(0)·κ_ACC(m)·Π(1+g_mc^seg)                 [ACC: level+shape+marginal growth]
            + r̄(0)·κ^r(m) · [growth from RR(y)/Sales(y), split by φ(y)]   [residual, own growth]
            + F(y)                                          [fixed charge; F(0) from URDB]
   where r̄(0) = v_URDB(0) − mc_ACC(0)                       [base residual = plug]
```
