# Rate Model Impact Report — Phase 7 re-run: what changed (for review)

> Re-run 2026-09-24 on branch `fix/gas-rate-base-review` (Phase 7 closed + gas curves on the CEC
> delivered price). Data: `tests/validation/rate_model_impact.json` (regenerated; the pre-Phase-7
> snapshot was 2026-09-10). Charts in `docs/reports/assets/` are regenerated. This file lists every
> claim, whether it still holds, and the proposed rewrite.
>
> **Applied 2026-09-24** — all rewrites approved as proposed and applied to
> `RateModel_Impact_Report.md`; HTML rebuilt; the hand-exported `.docx` dropped;
> `notebooks/rate_switch_review.ipynb` re-run.

## Why the numbers moved

| Cause | Effect on the report |
|---|---|
| **Phase 7 §4.1 — projections = current rate × curve growth.** Phase 6 priced each projection method at the curve's *own* level (e.g. EIA national electricity ≈ $0.17/kWh, gas ≈ $1.25/therm; WhyWatt gas from $2.08). Now every method starts from the home's own current rate (PG&E E-TOU-C plan; gas $2.66 EIA) and only the *growth* comes from the curve. | The biggest change. EIA "anchors" no longer mean "national price levels"; WhyWatt / CEC gas starts ~28 % higher (so do-nothing costs rise and paybacks come earlier). |
| **Gas curves follow the CEC** (this branch). | Section 3 levels only (the model uses shape). |
| **NEM 3.0 export credit = hourly ACC** and **Powerwall 3 defaults** (Phase 7). | Solar scenario, all models, a few %. |
| **Unchanged:** legacy CAGR-flat and legacy ACC in the non-solar scenarios (identical to the dollar); avoided social cost ($19.9k / $42.4k / $31.4k); peak amps and panel status. | — |

(The re-run pins the Social & Health toggles on, as the regression cases do — they default to off
in the app since 2026-09-23.)

## Claim by claim

Legend: ✅ holds, numbers identical · 🔢 holds, numbers change · ⚠️ **conclusion changes**

### Section 1 — Introduction
| Claim | Status | Proposed change |
|---|---|---|
| "PG&E's own published tariffs are the ground-truth *starting point* — today's E-1 electric and G-1 gas rates — that every projection must be anchored to." | ⚠️ | "…the ground-truth *starting point*: the home's own current rate — its utility's time-of-use plan (URDB) or, where there is none, its EIA effective rate — which every projection grows from." (The $2.08 "G-1" figure was the CARE baseline rate.) |

### Section 2 — Method
| Claim | Status | Proposed change |
|---|---|---|
| §2.1 "each anchored to today's real PG&E rate and grown using published … forecasts" | 🔢 | Keep; add "— the curves supply only the *growth*; the level is the home's own current rate". |
| §2.4 table, row "Base-year anchor & backcast — PG&E published tariffs (E-1, G-1, 2018→2025)" | ⚠️ | Split: "Current rate — URDB plan (PG&E E-TOU-C) / EIA-861M & EIA-176 per utility (2025)" and "Electricity curve anchor — PG&E E-1 (backcast)"; gas curve = CEC delivered price, no anchor. |
| §2.4 row "Neutral anchor — US EIA … the recommended default anchor" | ⚠️ | "Federal reference — US EIA national + AEO Pacific: their *growth* applied to your current rate (a near-flat real outlook)". See the anchor thesis below. |

### Section 3 — Rate projection results
| Claim | Old | New | Status |
|---|---|---|---|
| "today ≈ $2.08/therm" | $2.08 | ≈ $2.59 (2024$) / $2.65 (2025 nominal) | 🔢 |
| 2050 gas, real 2024$: Conservative / Moderate / Stress | ~$14 / ~$26 / ~$67 | ~$18 / ~$33 / ~$85 | 🔢 |
| CEC extreme ~$103 "(~50×)" | ~50× | ~40× | 🔢 |
| "Moderate ≈ $46/therm nominal" | $46 | ≈ $58.5 | 🔢 |
| Figure 1 caption "Anchored to the PG&E E-1/G-1 tariff" | — | "Electricity anchored to PG&E E-1; gas = the CEC delivered price" | 🔢 |
| **The anchor thesis:** "run the analysis at the conservative US EIA national average (electricity ~18¢/kWh, gas ~$1.25/therm — about half of California's rates) … even at those modest national rates, electrification plus solar still comes out ahead." | national *price levels* | the tool no longer prices at national levels — "EIA national" = *your current rate, growing at the federal (near-flat real) pace* | ⚠️ **mechanism changes; the claim survives in a stronger, more honest form:** "Even if your prices only follow the federal outlook — roughly flat after inflation, no California gas spiral — electrification plus solar saves **$76k** (national) / **$72k** (Pacific) over 20 years." Drop the "half of California's rates" framing. |

### Section 4.1 — HVAC 2027 + WH 2029 (20 yr)
| Claim | Old | New | Status |
|---|---|---|---|
| "Under the flat-rate legacy and EIA models the partial journey is roughly break-even to mildly negative (−$14k to +$1k, no clean payback except EIA Pacific's year-11 crossing)" | legacy −$8.7k / −$13.6k; EIA −$1.4k / +$0.6k, payback —/11 | legacy **unchanged**; EIA **+$6.4k / +$4.9k, payback year 3** | ⚠️ EIA flips to **mildly positive**. Proposed: "Under the legacy fixed-%/yr models the partial journey loses money (−$9k to −$14k, no payback). Under the federal EIA outlook it is mildly positive (+$5k to +$6k)." |
| "…any CEC-grounded path, the same two swaps save **$95k–$180k** (payback in years 5–7)" | $95k–$180k, yr 5–7 | **$138k–$251k**, **year 3** | 🔢 (bigger, earlier) |
| "The do-nothing baseline … from $132k under flat rates to $313k under Stress." | $132k → $313k | $132k → **$388k** | 🔢 |
| "A partial electrification's case is made or broken entirely by the gas-rate outlook." | — | legacy: negative; federal: small positive; CEC: large positive | 🔢 still true — the *size* of the case is decided by the gas outlook; only the legacy fixed-% models (which escalate electricity as fast as gas) make it negative. |

### Section 4.2 — Full electrification, 200 A (and 4.4, identical)
| Claim | Old | New | Status |
|---|---|---|---|
| Avoided social cost ~$20k → ~$42k | same | same | ✅ |
| "under every gas-rising model, drives net savings to **$117k–$211k**" | $117k–$211k | **$166k–$293k** | 🔢 |
| Legacy "slightly negative (−$38k to −$39k)" + year-2 transient payback | same | same | ✅ |
| "Even the neutral EIA national and Pacific anchors turn positive here (+$16k / +$14k)" | +$16.2k / +$13.9k | **+$5.9k / +$6.2k** | 🔢 still positive, smaller |
| "…at worst break-even-to-positive under the neutral federal anchor." | — | +$6k | ✅ holds |
| 4.4: identical to 4.2; red panel status | same | same | ✅ |

### Section 4.3 — Full electrification + solar (the headline)
| Claim | Old | New | Status |
|---|---|---|---|
| "wins under every single rate model, without exception" | yes | yes | ✅ |
| legacy flat-rate case "+$93k" | +$93.1k | **+$94.6k** | 🔢 |
| "both neutral EIA anchors (+$53k national, +$60k Pacific)" | +$52.8k / +$60.0k | **+$75.6k / +$72.3k** | 🔢 (stronger) |
| "Payback is year 1 everywhere" | yes | yes | ✅ |
| "journey's cumulative bill collapses to $14k–$46k while do-nothing runs $67k–$313k" | $14k–$46k / $67k–$313k | **$25k–$45k / $98k–$388k** | 🔢 |
| "*it pays even at flat national rates*" | national levels | ⚠️ rephrase with the anchor thesis: "it pays even if prices only follow the federal outlook" |

### Section 4.5 — HVAC + WH, 30 yr
| Claim | Old | New | Status |
|---|---|---|---|
| Do-nothing Stress **$1.02M**, CEC extreme **$1.34M** | $1.02M / $1.34M | **$1.28M / $1.35M** | 🔢 |
| Net savings Stress **$721k**, CEC **$1.01M** | $721k / $1.01M | **$961k / $1.03M** | 🔢 |
| "the flat-rate models stay near break-even, exactly as at 20 years" | legacy −$21k / −$24k; EIA −$2k / +$1k | legacy unchanged; EIA **+$11k / +$9k** | ⚠️ minor: "legacy fixed-%/yr models stay negative (−$21k to −$24k); the federal outlook is mildly positive (+$9k to +$11k)" |

### Section 5 — Conclusion
| # | Old | Proposed | Status |
|---|---|---|---|
| 1 | "HVAC + water heater alone is **break-even under flat rates** and a **$95k–$180k** winner under any California-grounded gas outlook." | "HVAC + water heater alone **loses money under the legacy fixed-%/yr rates** (−$9k to −$14k), is **mildly positive under the federal outlook** (+$5k to +$6k), and is a **$138k–$251k** winner under any California-grounded gas outlook." | ⚠️ |
| 2 | "Full electrification … saves **$117k–$211k** … at the neutral federal anchor it is break-even to positive." | "…saves **$166k–$293k** over 20 years, and under the federal outlook it is still positive (+$6k)." | 🔢 |
| 3 | "Solar makes the answer unanimous … every rate model … year-1 payback." | unchanged wording (numbers above) | ✅ |
| 4 | "30-year savings reach ~$0.7M–$1.0M under the stress and CEC cases" | "~$1.0M under the stress and CEC cases ($961k / $1.03M)" | 🔢 |
| close | "anchor to the neutral US EIA average and add solar — the answer is still yes." | "assume prices only follow the federal outlook and add solar — the answer is still yes (+$72k–$76k over 20 years)." | ⚠️ (wording, per the anchor thesis) |

### Also to update (mechanical)
- Header: "Prepared 2026-09-09 · Phase 6 WS1" → re-run date, Phase 7 + gas-rate base review; keep "DRAFT".
- §4 intro "the snapshot deliberately exercises non-default projection paths" — still true.
- Rebuild `public/help/RateModel_Impact_Report.html` (`build_impact_report_html.py`) after the text is approved; the `.docx` has no generator script (hand export) — re-export by hand, or drop it.
- `notebooks/rate_switch_review.ipynb` — re-run with the report.

## Summary for the reviewer

- **Conclusions that change (⚠️):** the EIA "anchor" now means *federal growth on your own rate*,
  not national price levels — the anchor thesis is reworded, not dropped; under that federal outlook
  the partial journey flips from "roughly break-even / negative" to **mildly positive** (+$5k to
  +$6k, payback year 3); the §1 / §2.4 "anchored to E-1 / G-1 tariffs" statements.
- **Conclusions that hold, stronger:** solar is unanimous and every EIA solar case is larger
  (+$72k–$76k); California-grounded savings grow ~40 % with paybacks in year 3 (was 5–7), because
  gas now starts from what PG&E households actually pay ($2.66, not $2.08).
- **Unchanged:** legacy results, social cost, panel status, the 4.4 panel story.
