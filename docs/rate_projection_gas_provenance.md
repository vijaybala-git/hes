# Gas rate provenance & source verification

> Verification pass, 2026-09-09. Confirms exactly which CEC workbook / sheet / column /
> scenario each gas number in `notebooks/rate_projection_review.ipynb` comes from, and
> reconciles the ">$20/therm" figures against the lower-looking CEC filing tn=269887.

## TL;DR

1. **We read the correct column.** Our gas scenarios come from CEC efiling **tn=264063**,
   sheet **`PG&E Res`**, column **H "Delivered Price"**, filtered to the three
   **`Planning Area Demand × {Pruning | Front Load | Flat} RR`** scenarios. Every value in
   `data/rates/projection/cec_gas_rate.json` matches the source workbook to ±0.00005 $/therm.
2. **The >$20/therm is real CEC data, not a harvest error.** It comes from *scenario
   selection*, not the wrong column: reduced (Planning-Area) demand + full/front-loaded
   cost recovery = the CEC's own managed-decline / BAU **death-spiral** cases.
3. **tn=269887 is a different product.** It is the **CED 2025 Baseline** demand forecast
   (single central case, ends 2045, ~$8.65/therm), which corresponds to tn=264063's
   *`Base Demand Constant Growth RR`* case (~$8.92 in 2045), **not** to what we plot as
   moderate/stress.
4. **Units (resolved 2026-09-09):** tn=264063 is in **2024$ (real)**, not nominal. The model,
   notebook, benchmarks and exporter now treat all rates on a single basis — **real 2024$** —
   fixing a gas double-deflation. The >$20/therm figures are unchanged (they were always correct
   in real terms). See "Resolved — canonical basis is real 2024$" below.

---

## Source-of-record for the gas panels

| Field | Value |
|---|---|
| Publisher | California Energy Commission (CEC) |
| Docket | 25-IEPR-03 (Electricity & Gas Demand Forecast) |
| Document (TN) | **264063** — "2025 IEPR Gas Rate Forecast" workbook |
| URL | https://efiling.energy.ca.gov/GetDocument.aspx?tn=264063 |
| Sheet | **`PG&E Res`** (PG&E residential) |
| Basis | **2024$ per therm (real)** — see units note |
| Local harvest | `data/rates/projection/cec_gas_rate.json` (all 18 scenarios) |
| Consumed by | `src/rate_projection/projected_rate_model.py` → `_cec_gas_index()` |

### `PG&E Res` column map (row 1 headers)

| Col | Header | Used as | Where |
|---|---|---|---|
| A | Year | year key (2025–2050) | — |
| B | Scenario | scenario filter (18 blocks × 26 yrs) | `scenarios{}` keys |
| C | Sector | (Residential — constant) | — |
| D | Utility | (PG&E — constant) | — |
| E | City | (San Francisco — constant) | — |
| F | Commodity Price | `commodity` | decomposition |
| G | Transportation Rate | `transportation` | decomposition |
| **H** | **Delivered Price** | **`delivered`** → the retail shape we escalate | `_cec_gas_index()` |
| I | Demand | `demand` → `sales_index()` (spiral denominator) | "why gas spirals" panel |
| J | Revenue Requirement | `revenue_requirement` → `rr_index()` | "why gas spirals" panel |

### Scenario → WhyWatt mapping (advocate choice, 2026-08-26)

All three use the **Planning Area Demand** case (aggressive-electrification demand path);
they differ only on the CEC **RR-recovery axis** (`RR Growth rate` sheet):

| WhyWatt scenario | tn=264063 scenario (col B) | RR-recovery meaning | 2050 delivered (2024$) |
|---|---|---|---|
| conservative | `Planning Area Demand Pruning RR` | curtail gas investment (managed decline) | $17.81 |
| moderate | `Planning Area Demand Front Load RR` | accelerated cost recovery | $33.05 |
| stress | `Planning Area Demand Flat RR` | BAU investment → full death spiral | $84.89 |

WhyWatt then **rebases** the CEC delivered *shape* onto the WhyWatt base rate
($2.08/therm G-1, vs the CEC's $2.5886 base), so the headline WhyWatt gas rates are
~0.80× the CEC delivered price: 2050 moderate ≈ $26.6, stress ≈ $68 on that base.

---

## Why the >$20/therm — the death-spiral driver (verified from the source)

PG&E **Planning-Area residential demand collapses** as customers electrify, while the
revenue requirement is still recovered from those who remain:

| Year | Demand (Planning Area, col I) | Delivered $/therm (Pruning) |
|---|---|---|
| 2025 | 1718 | $2.59 |
| 2035 | 809 | $8.50 |
| 2040 | 321 | $19.60 |
| 2045 | 238 | $22.00 |

An **86% demand drop 2025→2045** over a fixed cost base is what produces the >$20 (and,
under Flat RR, >$80) figures. This is the CEC's own arithmetic, not ours.

---

## Reconciling tn=269887 ("looks much lower")

tn=269887 is **not** the gas-rate scenario forecast. It is:

| | tn=269887 | tn=264063 (ours) |
|---|---|---|
| Product | **CED 2025 Baseline Natural Gas Forecast** (corrected May 2026) | 2025 IEPR **Gas Rate Forecast** |
| Sheet | `Rates Form 2.3` → col **`PGE_residential`** | `PG&E Res` → col H `Delivered Price` |
| What it is | single **central** demand forecast rate | **18-scenario** matrix (demand × RR-recovery) |
| Horizon | 2000–**2045** | 2025–**2050** |
| Basis | **2024$ per therm** (stated on sheet) | **2024$ per therm** (see units note) |
| PG&E res 2045 | **$8.648** | Base Constant-Growth $8.92 / Planning-Area cases much higher |
| Caveat on sheet | *"updated gas rates … **not used in the forecast**"* | scenario forecast |

**So the two are consistent.** tn=269887's ~$8.65 corresponds to tn=264063's *baseline*
demand case (`Base Demand Constant Growth RR`, $8.92 @2045 / $12.39 @2050). WhyWatt does
**not** plot that baseline as moderate/stress — it plots the reduced-demand ×
front-loaded/flat-recovery **death-spiral** cases, which are the legitimate high end of the
same CEC workbook. tn=269887 does not contradict our numbers; it is the low (central-demand)
end of the same forecast family.

---

## ✓ Resolved — canonical basis is real 2024$ (2026-09-09)

Proof that tn=264063 is **2024$ real**, not nominal:
- The `Commodity Prices` sheet header is literally **"2024$/Therm"**, and those values are
  identical to `PG&E Res` column F — so the delivered price built from them is 2024$ real.
- tn=264063 `Base Demand Constant Growth RR` @2045 = **$8.92** ≈ tn=269887's explicitly
  "2024$" baseline @2045 = **$8.65**. If tn=264063 were nominal they would differ by ~55%
  over 20 years, not 3%.

**Decision (from `docs/OfflineRateProjection_Plan.md` §2.1, "the comparison now defaults to
real 2024$"):** all rates are reported in **real 2024$**, matching every CEC anchor (electric
tn=268239, gas tn=264063, both real 2024$).

**What was wrong before the fix:**
- `projected_rate_model._cec_gas_index()` indexed the **real** delivered price as if it were
  nominal. Electricity is built from `pge_residential_nominal`, so `retail("elec")` was nominal
  but `retail("gas")` was real — the two fuels sat on different internal bases.
- The notebook `BASIS='real'` view then ran `to_real()` over the already-real gas series →
  **double-deflated** gas; the death-spiral bar chart mixed real and nominal bars.

**What changed (labeling + one consistency fix; the >$20 real figures are unchanged):**
- `projected_rate_model._cec_gas_index()` now **inflates** the real-2024$ delivered price to
  nominal (GDP deflator, base 2024) before indexing, so **both fuels are nominal internally**
  (matching `mc`, which is nominal), and `to_real(base_year=2024)` reports the canonical real
  2024$. Added `to_nominal()` as the inverse. `v = mc + r` stays consistent.
- `scripts/export_rate_projection.py` inflates the CEC gas benchmark (`cec_gas_extreme`) to
  nominal so the exported bundle (`basis: nominal` + deflator) is internally consistent; the
  consumer renders real via the deflator.
- Labels: `cec_gas_rate.json` and `benchmarks/cec_2025_iepr_gas.json` now state `basis: real
  2024$` (+ column map); the notebook defaults to `BASIS='real'`, tags the CEC gas benchmark
  `native="real_2024"`, and titles read "real 2024$".
- Tests updated to compare gas against the EIA floor / CEC ceiling in real 2024$. Full suite
  (341 tests) green; the bundle was re-exported.

**Reported gas rate, real 2024$ (unchanged by the fix — they were always correct in real terms):**
conservative **$14.0**, moderate **$25.9**, stress **$66.7** per therm in 2050. Electric moderate
tracks the CEC real-flat line (37.7¢ → 32.3¢).
