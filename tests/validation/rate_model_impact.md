# Rate-model impact — validation snapshot

_Generated 2026-09-08T03:34:19Z._  
Rate-model impact snapshot (Phase 6 WS1). Non-default projection paths are exercised deliberately — this is not the golden. sim_start_year=2025; 20-year horizon (app default) except where a scenario sets `years`; HVAC swap 2027, WH swap 2029.

Deltas are vs the reference run **`legacy_default_cagr`** (current app default). `opex_delta` = do-nothing − journey (positive = the journey saves money).

## hvac2027_wh2029

HVAC swap 2027 + Water Heater swap 2029 only (the requested scenario).

Peak load 78 A → panel status **yellow**.

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

Peak load 119 A → panel status **green**.

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

## full_electrification_solar

Full electrification + rooftop solar (NEM3); 200 A panel (case 02 style).

Peak load 119 A → panel status **green**.

| Rate model | Journey $ | Do-nothing $ | Savings (Δopex) | Payback | Savings vs ref | Do-nothing vs ref |
|---|--:|--:|--:|:--:|--:|--:|
| Legacy default (CAGR-flat, EIA per-utility) | 38,852 | 132,000 | 93,148 | 1 | +0 | +0 |
| Legacy ACC (PG&E/CPUC base) | 46,482 | 129,420 | 82,938 | 1 | -10,210 | -2,580 |
| WhyWatt Conservative | 24,281 | 164,850 | 140,569 | 1 | +47,421 | +32,850 |
| WhyWatt Moderate | 25,907 | 183,385 | 157,478 | 1 | +64,330 | +51,385 |
| WhyWatt Stress | 28,702 | 242,441 | 213,739 | 1 | +120,591 | +110,441 |
| CEC 2025 IEPR (elec) + CEC 2025 BAU-invest (gas) | 28,594 | 223,091 | 194,497 | 1 | +101,349 | +91,091 |
| US EIA national average | 14,306 | 67,077 | 52,771 | 1 | -40,377 | -64,923 |
| EIA AEO Pacific | 18,594 | 78,613 | 60,019 | 1 | -33,129 | -53,387 |

## panel_upgrade_100A

Full electrification on a 100 A service — forces a panel upgrade (case 07).

Peak load 119 A → panel status **red**.

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

## hvac2027_wh2029_30yr

HVAC 2027 + WH 2029 only, 30-year horizon (projection holds flat past 2050).

Peak load 78 A → panel status **yellow**.

| Rate model | Journey $ | Do-nothing $ | Savings (Δopex) | Payback | Savings vs ref | Do-nothing vs ref |
|---|--:|--:|--:|:--:|--:|--:|
| Legacy default (CAGR-flat, EIA per-utility) | 293,765 | 273,133 | -20,633 | — | +0 | +0 |
| Legacy ACC (PG&E/CPUC base) | 301,495 | 277,569 | -23,926 | — | -3,293 | +4,436 |
| WhyWatt Conservative | 164,087 | 290,320 | 126,233 | 7 | +146,866 | +17,187 |
| WhyWatt Moderate | 185,851 | 380,790 | 194,939 | 7 | +215,572 | +107,657 |
| WhyWatt Stress | 244,999 | 673,928 | 428,929 | 9 | +449,562 | +400,795 |
| CEC 2025 IEPR (elec) + CEC 2025 BAU-invest (gas) | 261,019 | 844,978 | 583,958 | 6 | +604,591 | +571,845 |
| US EIA national average | 108,483 | 106,160 | -2,323 | — | +18,310 | -166,973 |
| EIA AEO Pacific | 125,580 | 126,615 | 1,034 | 11 | +21,667 | -146,518 |
