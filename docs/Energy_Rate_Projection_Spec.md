# WhyWatt — Energy Rate Projection Methodology (v1.1)

**Type:** Methodology specification (sources + math). No implementation code.
**Intended use:** input to Claude Code, which will reconcile this against the existing
WhyWatt codebase (current ACC usage, consumption model, rate module) and produce an
implementation plan.
**Supersedes:** `escalation_methodology.md` (v0.1), which this subsumes and extends.
**Reconciliation:** reviewed against the codebase in `docs/Phase6_RateProjection_Plan.md`;
the clarifications in this v1.1 come from that review.

**Changelog v1.0 → v1.1** (clarity fixes; no methodology change):
- §3: stated the marginal→retail bridge in plain words — it is **additive** (`v = mc + r`),
  **not** a retail multiplier; added the source division-of-labour table and one-line assembly.
- §5.1: `mc` (and its segmented CAGR) is the **marginal** component only, not the retail rate;
  added the ACC annual-path extraction contract (per-year `mc(y)` at CZ4).
- §5.2 / §9-V3: base residual is a **plug**, `r̄(0) = v_URDB(0) − mc_ACC(0)` — not a bottom-up
  bucket sum; `RR` buckets inform *growth* and *scenario surgery* only.
- §7 / §9-V1: flagged the "2025 LSC Hourly Factors" fixture as **not yet in the repo** (blocker).
- §8: `Sales_f(y)` is an **exogenous scenario input**, not sim-derived; pinned unit consistency.
- §10: WhyWatt keeps labels `conservative / moderate / stress`, each now a **three-curve
  scenario object** (not a single CAGR); `moderate` = Central = default.

---

## 1. Purpose & scope

Produce **projected rate schedules** — not forecasts of an individual bill — that, when
multiplied by an externally-supplied monthly consumption model, yield the projected
**total cost to a consumer = utility bill + social cost** over a multi-decade horizon.

- Consumption `q_f(y,m)` (kWh, therms) is **given** — modeled elsewhere, monthly, per
  end use. This document does not model consumption.
- The deliverable of this methodology is the set of **rates**: volumetric `$/unit`,
  fixed `$/month`, and social `$/unit`, each resolved by month and projection year.
- "Project, not predict": outputs are scenario-conditional trajectories with explicit
  assumptions, not point predictions.

Notation: fuel `f ∈ {elec, gas}`; projection year `y = 0…Y` (`y=0` = base year, default
2026; `Y` = 25); month `m = 1…12`.

---

## 2. Projection target (top-level identity)

For each `(y, m)` and household:

```
Total(y,m)  = Bill(y,m) + Social(y,m)

Bill(y,m)   = Σ_f [ F_f(y) + v_f(y,m) · q_f(y,m) ]          # fixed + volumetric

Social(y,m) = Σ_f [ s_f(y,m) · q_f(y,m) ]                   # externality overlay
```

- `F_f(y)`  — fixed monthly charge (`$/month`), policy-dependent.
- `v_f(y,m)` — volumetric rate (`$/unit`).
- `s_f(y,m)` — social cost rate (`$/unit`).

Everything below defines these three objects and their time paths.

---

## 3. Rate architecture (decomposition)

```
v_f(y,m)  =  mc_f(y,m)          ( marginal, from ACC — carries intra-year shape )
           + r_f(y,m)          ( residual volumetric — revenue requirement not in fixed )

F_f(y)    =  fixed-charge policy scenario  ( recovers the complementary residual share )

s_f(y,m)  =  carbon damages + methane + health   ( net of any in-bill compliance )
```

Two independent policy axes govern the residual and are modeled separately:

| Axis | Governs | Lever / source | Enters the math via |
|---|---|---|---|
| **A — Residual size** | how much non-marginal cost is recovered at all | GRC revenue requirement, wildfire, capex; CPUC disallowance / securitization | `RR_f(y)` |
| **B — Allocation** | fixed vs volumetric split of a *given* residual | AB 205 fixed charge; shift to state budget | `φ_f(y)` (fixed share) |

Holding `RR` fixed and moving `φ` is *reallocation* (the Haas/Next10 reform frame);
changing `RR` is *cost containment* (a distinct lever). WhyWatt needs both.

### 3.1 — The marginal→retail bridge is ADDITIVE, not a multiplier

Retail is reconstructed **additively**: `v = mc + r`. We deliberately do **not** scale ACC by a
retail-markup multiplier — the residual `r` supplies the gap, and it moves **independently** of
`mc`. Two facts make this mandatory, not stylistic:

- **Magnitude.** ACC marginal is only a few ¢/kWh (it is the level we already use as the NEM
  export credit); retail is ≈ $0.386/kWh. So `r` is the **majority** of the bill, not a small
  adder.
- **Direction.** `mc` flattens then *falls* after ~2045 (grid decarbonization) while retail
  *rises* (wildfire / `RR` on a shrinking sales base — the death spiral). A **fixed** multiplier
  would drag retail *down* with `mc` — backwards. A *time-varying* multiplier is just the residual
  re-encoded, so we model the residual directly.

A calibrated **base-year** multiplier is permitted only as an explicit, clearly-labelled **v1
shortcut** while the `RR`/`Sales`/`φ` harvest is in flight (see §11). "The curve out of ACC"
always means **ACC + residual reconstruction** — ACC-marginal alone is *lower* than EIA, never the
retail rate.

### 3.2 — Division of labour: which source sets *base* vs *growth*

| Object | Source | Sets… |
|---|---|---|
| `v_f(0,m)`, `F_f(0)` | **URDB** (today's tariff: `$/kWh`, `$/therm`, slabs, `fixed_charge`) | the **base-year retail level only** — not growth, not `RR` (URDB is a *rate*, not a revenue requirement) |
| `mc_f(0,m)`, `κ_f(m)`, `g_mc^{seg}` | **ACC** | the **marginal** base level, monthly shape, and **marginal** growth curve |
| `RR_f(y)`, `φ_f(y)`, `Sales_f(y)` | GRC / E3 tool / CEC-IEPR / AB 205 | the **residual** growth and the fixed/volumetric split |

**Base-year residual is a plug, not a bucket sum:** `r̄_f(0) = v_URDB(0) − mc_ACC(0)` (auto-satisfies
the §9-V3 backcast). The retail growth curve is **emergent** — `mc` (slow/flat, may fall) **+**
residual (fast-rising) — so no single retail CAGR is ever read off ACC. Full assembly:

```
Retail(y,m) = mc(0)·κ_ACC(m)·Π(1+g_mc^seg)                 [ACC: level + shape + marginal growth]
            + r̄(0)·κ^r(m) · [growth from RR(y)/Sales(y), split by φ(y)]   [residual, own growth]
            + F(y)                                          [fixed charge; F(0) from URDB]
   where r̄(0) = v_URDB(0) − mc_ACC(0)                       [base residual = plug]
```

---

## 4. The escalation primitive (how everything moves through time)

Every time-varying scalar `X` (a rate component, price, emission intensity, revenue
requirement, or sales level) is expressed as a base value times a **horizon-segmented
compound growth**:

```
X(y) = X(0) · Π_{t=1}^{y} ( 1 + g_X^{seg(t)} )

seg(t) = near   if t ≤ T1
         mid    if T1 < t ≤ T2
         long   if t > T2
```

- Default boundaries `T1 = 5` (≈2030), `T2 = 15` (≈2045).
- **Structural-knot variant (recommended):** anchor at calendar years {2026, 2030, 2045,
  2050} and derive `g` by log-linear interpolation between anchors — boundaries then
  track the forecasts' own joints (2030 = GRC horizon; 2045 = SB 100 endpoint).
- Each component owns its own `{X(0), g_near, g_mid, g_long}` (or anchor set). Growth
  may be **negative** (e.g., electricity carbon intensity).

**Monthly shape is separate from escalation.** A quantity is `annual level × monthly
shape factor κ(m)`, where escalation acts on the annual level and `κ` on the within-year
profile. Marginal-cost shape comes from ACC; residual defaults to flat; social shape
follows the emissions profile.

---

## 5. Utility bill

### 5.1 Marginal volumetric — `mc_f(y,m)` (from ACC)

```
mc_f(y,m) = Σ_{c} a_{c,f}(y,m)
```

Components `c` from the CPUC Avoided Cost Calculator (marginal avoided cost):

- **Electric:** generation energy, losses, generation capacity, ancillary services,
  transmission capacity, distribution capacity.
- **Gas:** commodity (border/burnertip) + gas marginal T&D, from the ACC Gas Model.

ACC provides **hourly** values → aggregate to monthly for `κ` and annual mean for the
escalation base. ACC publishes to ~2045; beyond, extrapolate with the `long` segment.
**Note:** ACC is *marginal* cost — it is **not** the retail rate (§3.1). It is the correct
source for `mc`, for intra-year shape `κ`, and for the **marginal** growth curve `g_mc^{seg}` —
and nothing else on the bill. The segmented CAGR fitted here escalates `mc` **only**; the retail
rate's growth is emergent (`mc` + residual), never read off ACC.

**Extraction contract (what Phase 6 actually harvests).** Today's committed extract is a single
20-yr *levelized* value at **CZ12, met-year 2018** — insufficient. The harvest must pull the
**per-year `mc_f(y)` path, 2026→~2045, at CZ4** (South Bay default; other CA zones additive),
naming the workbook sheet/column used and the ACC vintage (§11). Years beyond the ACC horizon use
the `long` segment. The output is a per-zone annual `mc(y)` series plus the 12×24 monthly shape
`κ`.

### 5.2 Residual volumetric — `r_f(y,m)`

```
r_f(y,m) = r̄_f(y) · κ^r_f(m)

r̄_f(y)  = ( 1 − φ_f(y) ) · RR_f(y) / Sales_f(y)
```

- `RR_f(y)` — residual (non-marginal) revenue requirement for the residential class
  (Axis A). Buckets: embedded T&D, wildfire mitigation + victim compensation, legacy
  above-market renewable & power contracts, public-purpose programs, CARE/FERA
  cross-subsidy, NEM cost shift.
- `φ_f(y)` — share of `RR` recovered through the fixed charge (Axis B), `∈ [0,1]`.
- `Sales_f(y)` — residential-class annual throughput (per-customer or class-total,
  consistent with `RR` — see unit note below).
- `κ^r_f(m)` — monthly allocation, default flat (Σ preserves annual).

**Base year is a plug, not a bucket sum.** Do **not** reconstruct the base-year residual by
summing GRC buckets (they rarely foot to the tariff exactly). Instead:

```
r̄_f(0) = v_URDB(0) − mc_ACC(0)          # base residual = today's retail (URDB) − marginal (ACC)
```

The named `RR` buckets then serve **only** two purposes: (1) informing *how* the residual grows
(bucket-specific segment rates — wildfire fast, embedded T&D slow), and (2) scenario surgery
(e.g. the "state-budget shift" scenario removes the wildfire bucket). The base **level** always
comes from the URDB − ACC plug, which auto-satisfies the §9-V3 backcast.

**Unit consistency (must be pinned before calibration).** `RR` is *dollars*; `r̄` and `v` are
`$/unit`. `RR` (class-total vs per-customer $) and `Sales` (class-total vs per-customer
throughput) must be on the **same basis**, and the fixed-charge formula needs a matching
customer-count series `Cust_f(y)` (§5.3). Mixing bases silently scales the rate by ~10⁶.

**Death-spiral mechanism is explicit here:** as `Sales_f(y)` falls (electrification /
grid defection) with `RR_f(y)` ~fixed or rising, `r̄_f(y)` rises. For gas this dominates:
a roughly fixed pipeline revenue requirement over a shrinking therm base. Note the base level is
still pinned by the plug; the death spiral acts on the **growth** of `r̄` after year 0.

### 5.3 Fixed charge — `F_f(y)` (policy scenario)

Fixed-charge revenue and volumetric residual are complementary shares of the same `RR`:

```
Fixed revenue_f(y) = φ_f(y) · RR_f(y)

F_f(y) = φ_f(y) · RR_f(y) / ( 12 · Cust_f(y) )       # per-customer monthly
```

Parameterize a scenario **either** by the share `φ_f(y)` **or** by the charge `F_f(y)`
directly (the other follows). Fixed charge and volumetric residual "may depend on other
things" (income tier, climate zone, customer class) — those enter as modifiers on
`φ`/`F` and `κ^r`, modeled independently of Axis A.

### 5.4 Bill assembly

```
Bill(y,m) = Σ_f [ F_f(y) + ( mc_f(y,m) + r_f(y,m) ) · q_f(y,m) ]
```

---

## 6. Social cost overlay

```
s_f(y,m) = carbon_f(y,m) + methane_f(y) + health_f(y)
```

### 6.1 Carbon — with the double-count guard

Distinguish **compliance carbon** (cap-and-trade, a real cost the consumer *pays*, so it
belongs in the bill via `mc`) from **damage carbon** (SCC, the externality).

```
# default: NET societal externality (avoids double-counting internalized carbon)
carbon_f(y,m) = max( 0,  SCC(y) · ε^{CO2}_f(y)  −  comp_f(y,m) )

# gross variant (full damages; then compliance is a transfer inside Bill, not re-added here)
carbon_f(y,m) = SCC(y) · ε^{CO2}_f(y)
```

- `SCC(y)` — social cost of carbon by **emission year** (rises by construction).
- `ε^{CO2}_f(y)` — emission intensity. **Fuel-specific and time-varying:**
  - `ε^{CO2}_elec(y)` **declines** toward ~0 by 2045 (grid decarbonization / SB 100) →
    electricity's carbon term flattens then falls even as `SCC` rises.
  - `ε^{CO2}_gas(y)` ≈ **constant** combustion factor → monotonic increase with `SCC`.
- `comp_f(y,m)` — cap-and-trade compliance already embedded in the bill (from ACC GHG
  component / CARB allowance forecast).

This asymmetry is a second, independent death-spiral channel: gas gains carbon cost while
electricity sheds it.

### 6.2 Methane — `methane_f(y)`

```
methane_gas(y) = leak_rate · GWP · SCC_CH4(y)      # gas only; elec ≈ 0
```

Upstream leakage × global warming potential (IPCC AR6, choose GWP-20 or GWP-100 —
a modeling decision) × a CH₄ damage price. Escalates **with** the carbon price.

### 6.3 Health — `health_f(y)`

Criteria-pollutant damages per unit (ACC air-permit component or EPA benefit-per-ton),
`≈ flat in real terms` (inflation only). Fixed-real is defensible here.

---

## 7. Data sources (master table)

| Object | Symbol | Primary source | Extract | Escalation basis |
|---|---|---|---|---|
| Marginal elec | `mc_elec` | CPUC ACC 2024 (adopted) / 2026 (draft) | hourly→monthly avoided cost, 6 components | ACC to 2045; extrapolate `long` |
| Marginal gas | `mc_gas` | CPUC ACC **Gas Model** | monthly avoided gas cost | ACC gas forecast |
| Residual RR (elec) | `RR_elec` | **E3 "Fixed Charge Design Tool" / CPUC "Public Tool"** + PG&E GRC | residential-class residual buckets | GRC near; wildfire+capex mid/long (Axis A) |
| Residual RR (gas) | `RR_gas` | PG&E gas GRC / CPUC | gas distribution fixed revenue requirement | fixed RR ÷ declining therms |
| Sales / throughput | `Sales_f` | CEC IEPR **CED 2025** forecast (to 2045/2050) | residential elec & gas sales | managed forecast; electrification-adjusted |
| Fixed-charge policy | `φ`, `F` | AB 205 **D.24-05-028** + scenarios | $24.15 / $12 / $6 tiers; future tiers | scenario trajectory (Axis B) |
| Compliance carbon | `comp_f` | CARB cap-and-trade; ACC GHG component | allowance-price forecast (IRP-consistent) | escalating |
| Damage carbon | `SCC` | EPA 2023 SCC (IWG lineage) | $/tCO₂ by emission year | year-indexed, rising |
| Emission intensity elec | `ε^{CO2}_elec` | ACC hourly marginal emissions; CARB/CEC | gCO₂/kWh path (declining) | → ~0 by 2045 |
| Emission intensity gas | `ε^{CO2}_gas` | EPA combustion factor | ~5.3 kgCO₂/therm | flat |
| Methane | `leak_rate,GWP,SCC_CH4` | leakage studies; IPCC AR6 GWP | leak % × GWP × price | with carbon |
| Health | `health_f` | ACC air-permit / EPA benefit-per-ton | criteria-pollutant $/unit | flat-real |
| Levelization anchor | — | **2025 LSC Hourly Factors** ⚠️ *not yet in repo — see note* | CZ4 levelized $/kWh, $/therm | 3% real, 30-yr |
| Floor / near cross-check | — | EIA AEO; PG&E 2027–2030 GRC | escalation bounds | — |

> ⚠️ **LSC fixture blocker (V1).** The "2025 LSC Hourly Factors" file is referenced here and in
> §9-V1 / §12 but is **not committed to the repo**, and the acronym "LSC" is not expanded. Before
> V1 can be built, either (a) name the exact source, expand "LSC", and commit it with provenance
> (sha256) at `data/rates/projection/lsc_2025_levelized.json`; or (b) restate V1 against an
> obtainable source (e.g. published 2025 PG&E levelized figures) and drop the $6.70/kWh /
> $119/therm targets if they cannot be traced. Owner + resolution TBD.

---

## 8. Residual policy-scenario infrastructure

A residual scenario is fully specified by three independent trajectories:

1. `RR_f(y)` — revenue-requirement path (Axis A). Note the base **level** of the residual is the
   §5.2 plug (`v_URDB(0) − mc_ACC(0)`); these trajectories drive its **growth** from year 0.
2. `φ_f(y)` **or** `F_f(y)` — fixed/volumetric split (Axis B).
3. `Sales_f(y)` — throughput path (denominator). **This is an exogenous scenario input**, a
   grid-aggregate assumption the user/scenario *selects* (CEC IEPR managed forecast,
   electrification-adjusted). WhyWatt models a **single home** and does **not** derive `Sales`
   from its own consumption simulation — the death spiral is an input the advocate chooses, not an
   emergent output.

Because `r̄_f = (1−φ)·RR / Sales` and `F = φ·RR/(12·Cust)`, *every* residual policy —
current, hypothetical, or future — reduces to choosing these three curves plus any tier/
zone modifiers. No policy-specific code paths are required; new policies are new curves.

Reference points to seed scenarios:
- **Status quo (pre-2026):** `φ ≈ 0` (all residual volumetric).
- **AB 205 (current):** `F_elec ≈ $24.15/mo` (CARE $6, FERA $12) → volumetric cut ≈
  5–7 ¢/kWh; `RR` unchanged.
- **Expanded IGFC:** `F` toward $50–70/mo (or income-graduated) → larger volumetric cut.
- **State-budget shift:** remove wildfire / public-purpose buckets from `RR` entirely.

---

## 9. Validation & consistency checks

- **V1 — Aggregate re-levelization.** Build `v_f + adders`, take NPV at 3% real over 30
  yrs, confirm it reproduces the CZ4 levelized magnitudes in the 2025 LSC file
  (electricity ≈ $6.70/kWh, gas ≈ $119/therm) within tolerance. The file pins the
  aggregate; this methodology supplies the shape. **⚠️ Blocked until the LSC fixture is committed
  or V1 is restated** — see the §7 LSC note.
- **V2 — Bound ordering.** 25-yr cumulative multipliers: EIA (floor) ≤ central ≤
  death-spiral, per fuel.
- **V3 — Backcast.** Calibrate `X(0)` to actual 2025 PG&E residential rates; check the
  2019→2025 trajectory against published history where available. **In practice V3 is satisfied
  by construction** for the base year: URDB *is* the 2025 retail anchor, and `r̄(0) = v_URDB(0) −
  mc_ACC(0)` (§5.2). V3's remaining work is the 2019→2025 *trajectory* check, not the base level.
- **V4 — Cross-fuel parity.** Implied heat-pump break-even COP from `v_elec / v_gas` over
  time — sanity against known ~2.8 COP parity today; the crossover should emerge in mid/
  long horizons.

---

## 10. Scenario matrix

| Scenario (methodology) | WhyWatt label | Axis A: `RR` growth | Axis B: fixed policy | Throughput `Sales` | Social `s` |
|---|---|---|---|---|---|
| **Conservative** | `conservative` | low (aggressive disallowance) | status-quo mix | flat | net, low SCC |
| **Central** *(default)* | **`moderate`** | GRC-consistent | current AB 205 ($24.15) | IEPR managed | net, central SCC |
| **Death-spiral** | `stress` | high (wildfire + capex) | frozen volumetric recovery | aggressive gas decline | gross, high SCC |

**Scenario semantics changed (v1.1).** WhyWatt keeps its existing labels
`conservative / moderate / stress`, but each is now a **three-curve scenario object**
(`RR(y)`, `φ(y)`, `Sales(y)`) plus social settings — **not** the single per-fuel CAGR the current
`SCENARIO_PRESETS` carries. `moderate` = Central is the **default** and represents the central CA
reconstruction (which runs *above* EIA because of the rising residual, even though ACC-marginal
alone is below EIA). `SCENARIO_PRESETS` in `model.py` therefore changes shape: from a CAGR pair to
a scenario object.

---

## 11. Open decisions (resolve before calibration)

**Resolved in v1.1** (folded above): marginal→retail bridge = additive residual, not a multiplier
(§3.1); scenario labels/semantics (§10); ACC re-sourced at **CZ4** (§5.1); base residual = URDB −
ACC plug (§5.2). A base-year multiplier is allowed only as a labelled v1 shortcut.

**Still open — these gate calibration:**
- Segment boundaries: fixed 5/15 vs structural 2030/2045 knots.
- Nominal vs real reporting; the inflation assumption harmonizing all sources.
- Social cost: net-of-compliance (default) vs gross; whether `s` may go negative; **and how it
  reconciles with the existing flat $1.07/therm in `social_cost.py`** (is $1.07 the `y=0` anchor
  of a rising `s_gas(y)`?).
- Methane GWP horizon: GWP-20 vs GWP-100.
- Residual monthly shape `κ^r`: flat vs mirror current TOU/tiered design.
- Per-fuel fixed charge: gas fixed/minimum charge modeled alongside electric?
- ACC **vintage**: 2024 adopted (stable) vs 2026 draft (current). *(Zone resolved → CZ4.)*
- Class allocation / **customer-count series `Cust_f(y)`** for `RR → per-customer` (the unit-basis
  requirement in §5.2).
- **LSC / V1 fixture** ownership and resolution (§7 note).

---

## 12. Handoff note for implementation

See `docs/Phase6_RateProjection_Plan.md` for the codebase reconciliation, scope, and the
Phase-6-vs-Phase-7 split. Under Phase 6's constraint this methodology lands **offline / unwired**
(a `ProjectedRateModel` class read by no sim code, plus review notebooks); the live model keeps
EIA + single CAGR until a later phase deliberately re-baselines the golden.

Claude Code should: (a) inventory current ACC ingestion and confirm which components are
already loaded and at what resolution (today: a single levelized 12×24 *shape* at CZ12, plus a
`monthly_avg_acc_kwh` used for NEM export — **not** an annual `mc(y)` path); (b) locate where the
existing code applies a single escalation rate (`RateLoader.get_rate`) and, in the new unwired
model, replace it with the §4 primitive; (c) introduce the §3 decomposition (`mc + r`, `F`, `s`)
with the **URDB − ACC plug** for the residual base (§5.2) and the source division-of-labour of
§3.2, without disturbing the consumption model interface; (d) implement the §8 three-curve residual
scenario infra with `Sales` as an exogenous input (§8.3); (e) wire the §9 validation checks as
tests — **V1 is blocked until the LSC fixture is committed or restated** (§7 note), V3 base level
is satisfied by the plug.