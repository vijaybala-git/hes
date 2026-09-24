# Gas-rate base review — implementation plan

> Branch `fix/gas-rate-base-review` (off `main` after Phase 7). Opened 2026-09-24 from the
> Phase 7 Post-Phase-7 note and `docs/rate_projection_gas_provenance.md` "Open review".
> Gate for the Beta release (with §6 NREL load profiles).

## 1. The question

Three 2025 figures for PG&E residential gas disagree:

| Source | 2025 $/therm | Basis | Where it is used |
|---|---|---|---|
| **PG&E G-1** (`data/rates/pge_gas_g1.json`, "Advice Letter 5014-G1") | **$2.08** | one tariff rate, Jan 2025 | the projection bundle's `base_retail.gas` (all WhyWatt gas curve *levels*); the legacy ACC mode's gas base (`RateLoader`) |
| **CEC 2025 IEPR** tn=264063, `PG&E Res`, col H "Delivered Price" | **$2.5886** real 2024$ = **$2.649** nominal 2025 (GDP deflator 107.1608 / 104.7119) | commodity $0.454 + transportation $2.1346 | the *shape* of the WhyWatt gas curves |
| **EIA-176** PG&E, residential revenue ÷ volume | **$2.3147** (2024) → **$2.66** (2025, × CA ratio 1.1499, bridged) | what households actually paid, all-year average | the model's current gas rate (Phase 7 §4.1) and My Utility (2024) |

A spot check of PG&E's own site agreed with ≈ $2.66. The CEC delivered price in nominal 2025
dollars ($2.649) is within **0.5 %** of the EIA figure — the two independent sources agree; the
$2.08 is the outlier.

## 2. What the review found so far (2026-09-24)

1. **The $2.08 enters in one place:** `src/rate_projection/projected_rate_model.py`
   `BASE_RETAIL = {"elec": 0.386, "gas": 2.08}` ("PG&E 2025, per CLAUDE.md"), written to the
   bundle by `scripts/export_rate_projection.py` (`base_retail`, note "Anchored to the PG&E
   E-1/G-1 tariff"). The G-1 series itself is `data/rates/pge_gas_g1.json`.
2. **The rebase is level-only.** Gas retail = `mc + residual`, residual = `BASE × CEC_index − mc`,
   so retail = `BASE × CEC_index(y)` exactly: the CEC shape is kept, only the level is scaled
   (×0.80 of the CEC's nominal delivered price).
3. **Since Phase 7 §4.1 the model uses only the shape.** Projection methods price
   `current rate × S[y] / S[anchor]`; the bundle's absolute level cancels out. So changing the
   base moves **no projection-method result** (regression cases 13–32) — only the published curve
   levels (the bundle, the rate-projection guide and its chart, the Phase 6 notebooks, the
   benchmark comparisons).
4. **The G-1 file is consistently low, not just in 2025** — 12–31 % below EIA-176 every year:

   | Year | G-1 file | EIA-176 PG&E | EIA ÷ G-1 |
   |---|---|---|---|
   | 2019 | 1.18 | 1.377 | 1.17 |
   | 2021 | 1.35 | 1.715 | 1.27 |
   | 2022 | 1.65 | 2.154 | 1.31 |
   | 2023 | 1.85 | 2.067 | 1.12 |
   | 2024 | 1.92 / 1.98 | 2.315 | ≈ 1.19 |

   A systematic gap like this points at a **definition** difference (which components / tier the
   single "G-1 rate" includes), not a one-off data error.
5. **The legacy ACC mode also uses the $2.08** (`RateLoader` → `pge_gas_g1.json`), so ACC-mode gas
   results (regression case 08, offsets `08__acc_*`) sit ~20 % below what PG&E households pay.
6. **Electricity has the same question, milder:** `BASE_RETAIL.elec` $0.386 (E-1) vs EIA 2025
   $0.3991 vs the CEC blended ~$0.408 (the code comment already notes "~6 % level offset").

## 3. Investigation steps (what the $2.08 leaves out)

1. **Trace the $2.08 to its source.** Pull PG&E Advice Letter 5014-G / the G-1 tariff sheets and
   PG&E's residential gas rate tables for Jan 2025: is $2.08 the *baseline* (tier 1)
   procurement + transportation charge only?
2. **Quantify each candidate component** for a typical PG&E residential customer (2024–2025):
   - **tier mix** — baseline vs excess ("above baseline") therms and the excess-tier premium;
   - **Public Purpose Program surcharge** (G-PPPS, billed as a separate line);
   - **seasonal procurement** — the monthly procurement price vs an annual average;
   - **fixed / customer charge** (G-1 has none today — confirm);
   - **franchise fees, taxes** (state / local, e.g. utility users' tax — EIA revenue may or may not
     include them; confirm the EIA-176 revenue definition).
3. **Reconcile:** $2.08 + components ≈ $2.65 (±3 %)? Record the build-up in the provenance doc.
4. **Check the electricity analogue** the same way (E-1 $0.386 vs EIA $0.399 vs CEC $0.408) —
   report; fix in this branch only if the cause is the same and the user agrees.

## 4. Options for the fix (decide after §3)

| Option | Bundle gas base | Pros | Cons |
|---|---|---|---|
| **A — no rebase (recommended)** | the CEC's own delivered price, nominal ($2.649 in 2025) | curve levels = the source; matches EIA within 0.5 %; simplest provenance ("CEC, as published, inflated to nominal") | curve levels no longer tied to a PG&E tariff sheet |
| **B — rebase to EIA effective** | $2.66 (EIA-176 2025, bridged) | same number the model starts from | bridged value until EIA-176 2025 publishes; two sources in one curve |
| **C — keep $2.08, document** | $2.08 | no change | published curves stay ~20 % low |

**Legacy ACC mode** (`pge_gas_g1.json` base) — separate decision:
- *ACC-1:* leave as is (ACC is a legacy fixed-%/yr mode, to be reinterpreted post-P7) and note
  the ~20 % low level in help; golden unchanged.
- *ACC-2:* start ACC gas from the EIA per-utility rate (like My Utility) — moves case 08 and the
  `08__acc_*` offsets (own golden diff).

## 5. Implementation (once options are chosen)

1. `src/rate_projection/projected_rate_model.py`: `BASE_RETAIL["gas"]` per the option (A: derive
   from `cec_gas_rate.json` 2025 delivered × deflator, not a literal); same for elec if §3.4 says so.
2. `scripts/export_rate_projection.py` → rebuild `data/rates/projection/whywatt_rate_projection.json`;
   update `base_retail_note` with the provenance (what the base is and why).
3. Tests: `tests/test_rate_projection.py` / `test_projected_rate_source.py` expected levels; a new
   check that the bundle's 2025 gas base is within 3 % of EIA-176's PG&E effective rate; a
   **projection-invariance test** — model results for every projection case are unchanged (the
   shape is unchanged).
4. Regression: run the harness — **golden must not move** for option A/B with ACC-1 (the model
   uses only the shape). ACC-2 is a separate, explained golden commit.
5. Docs / outputs: `docs/rate_projection_gas_provenance.md` (close the Open review with the
   component build-up); `docs/OfflineRateProjection_Plan.md` (the rebase line); the rate-projection
   guide + its SVG chart (`scripts/build_guide_charts.py`, then `build_help.py` — note the guide
   HTML already had pre-existing drift; regenerate and review the whole diff); `CLAUDE.md` key
   constants ("Gas (G-1): $2.08" → what it is, and the base now used); Phase 7 spec
   Post-Phase-7 item → resolved; help text if it quotes the $2.08.
6. Notebooks that print curve levels (`notebooks/rate_projection_review.ipynb`,
   `rate_switch_review.ipynb`): re-run so their outputs match (or note them as historical).

## 6. Acceptance

- The $2.08's missing components are identified and written down (provenance doc).
- The bundle's 2025 gas base agrees with EIA-176 PG&E within 3 % (options A/B), or the gap is
  documented (C).
- Golden unchanged (A/B + ACC-1); all tests pass; the guide and its chart show the corrected
  levels; CLAUDE.md and the specs no longer quote $2.08 as the PG&E residential gas rate.
