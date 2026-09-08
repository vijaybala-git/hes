# Rate-model impact — validation snapshot

_Generated 2026-09-08T02:39:31Z._  
Rate-model impact snapshot (Phase 6 WS1). Non-default projection paths are exercised deliberately — this is not the golden. sim_start_year=2025, 20-year horizon (app default); HVAC swap 2027, WH swap 2029.

Deltas are vs the reference run **`legacy_default_cagr`** (current app default). `opex_delta` = do-nothing − journey (positive = the journey saves money).

## hvac2027_wh2029

HVAC swap 2027 + Water Heater swap 2029 only (the requested scenario).

| Rate model | Journey $ | Do-nothing $ | Savings (Δopex) | Payback | Savings vs ref | Do-nothing vs ref |
|---|--:|--:|--:|:--:|--:|--:|
| Legacy default (CAGR-flat, EIA per-utility) | 140,731 | 132,000 | -8,731 | — | +0 | +0 |
| Legacy ACC (PG&E/CPUC base) | 143,040 | 129,420 | -13,620 | — | -4,889 | -2,580 |
| WhyWatt Conservative | 102,333 | 164,850 | 62,516 | 7 | +71,247 | +32,850 |
| WhyWatt Moderate | 108,459 | 183,385 | 74,926 | 7 | +83,657 | +51,385 |
| WhyWatt Stress | 123,083 | 242,441 | 119,358 | 9 | +128,089 | +110,441 |
| CEC 2025 IEPR (elec) + CEC 2025 BAU-invest (gas) | 118,680 | 223,091 | 104,410 | 6 | +113,141 | +91,091 |
| US EIA national average | 68,431 | 67,077 | -1,354 | — | +7,377 | -64,923 |
| EIA AEO Pacific | 78,045 | 78,613 | 567 | 11 | +9,298 | -53,387 |

## full_electrification_2027_29

HVAC 2027 + WH 2029 + dryer/cooktop/EV planned; 200 A panel (case 01 style).

| Rate model | Journey $ | Do-nothing $ | Savings (Δopex) | Payback | Savings vs ref | Do-nothing vs ref |
|---|--:|--:|--:|:--:|--:|--:|
| Legacy default (CAGR-flat, EIA per-utility) | 171,298 | 132,000 | -39,298 | 2 | +0 | +0 |
| Legacy ACC (PG&E/CPUC base) | 167,634 | 129,420 | -38,214 | 2 | +1,084 | -2,580 |
| WhyWatt Conservative | 85,588 | 164,850 | 79,262 | 2 | +118,560 | +32,850 |
| WhyWatt Moderate | 91,659 | 183,385 | 91,726 | 2 | +131,024 | +51,385 |
| WhyWatt Stress | 102,221 | 242,441 | 140,220 | 2 | +179,518 | +110,441 |
| CEC 2025 IEPR (elec) + CEC 2025 BAU-invest (gas) | 99,215 | 223,091 | 123,876 | 2 | +163,174 | +91,091 |
| US EIA national average | 50,861 | 67,077 | 16,216 | 2 | +55,514 | -64,923 |
| EIA AEO Pacific | 64,700 | 78,613 | 13,913 | 2 | +53,211 | -53,387 |
