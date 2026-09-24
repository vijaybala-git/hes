# Rate-model impact — validation snapshot

_Generated 2026-09-24T20:31:48Z._  
Rate-model impact snapshot (Phase 6 WS1). Non-default projection paths are exercised deliberately — this is not the golden. sim_start_year=2025; 20-year horizon (app default) except where a scenario sets `years`; HVAC swap 2027, WH swap 2029.

Deltas are vs the reference run **`legacy_default_cagr`** (current app default). `opex_delta` = do-nothing − journey (positive = the journey saves money).

## hvac2027_wh2029

HVAC swap 2027 + Water Heater swap 2029 only (the requested scenario).

Peak load 78 A → panel status **yellow**.

| Rate model | Journey $ | Do-nothing $ | Savings (Δopex) | Payback | Savings vs ref | Do-nothing vs ref |
|---|--:|--:|--:|:--:|--:|--:|
| Legacy default (CAGR-flat, EIA per-utility) | 140,731 | 132,000 | -8,731 | — | +0 | +0 |
| Legacy ACC (PG&E/CPUC base) | 143,040 | 129,420 | -13,620 | — | -4,889 | -2,580 |
| WhyWatt Conservative | 109,006 | 246,975 | 137,969 | 3 | +146,700 | +114,975 |
| WhyWatt Moderate | 116,480 | 280,402 | 163,923 | 3 | +172,654 | +148,402 |
| WhyWatt Stress | 136,710 | 387,698 | 250,989 | 3 | +259,720 | +255,698 |
| CEC 2025 IEPR (elec) + CEC 2025 BAU-invest (gas) | 118,293 | 292,813 | 174,520 | 3 | +183,251 | +160,813 |
| US EIA national average | 96,571 | 102,976 | 6,405 | 3 | +15,136 | -29,024 |
| EIA AEO Pacific | 93,115 | 98,060 | 4,945 | 3 | +13,676 | -33,940 |

## full_electrification_2027_29

HVAC 2027 + WH 2029 + dryer/cooktop/EV planned; 200 A panel (case 01 style).

Peak load 119 A → panel status **green**.

| Rate model | Journey $ | Do-nothing $ | Savings (Δopex) | Payback | Savings vs ref | Do-nothing vs ref |
|---|--:|--:|--:|:--:|--:|--:|
| Legacy default (CAGR-flat, EIA per-utility) | 171,298 | 132,000 | -39,298 | 2 | +0 | +0 |
| Legacy ACC (PG&E/CPUC base) | 167,634 | 129,420 | -38,214 | 2 | +1,084 | -2,580 |
| WhyWatt Conservative | 80,888 | 246,975 | 166,087 | 2 | +205,385 | +114,975 |
| WhyWatt Moderate | 85,845 | 280,402 | 194,558 | 2 | +233,856 | +148,402 |
| WhyWatt Stress | 94,402 | 387,698 | 293,296 | 2 | +332,594 | +255,698 |
| CEC 2025 IEPR (elec) + CEC 2025 BAU-invest (gas) | 85,625 | 292,813 | 207,188 | 2 | +246,486 | +160,813 |
| US EIA national average | 97,047 | 102,976 | 5,929 | 2 | +45,227 | -29,024 |
| EIA AEO Pacific | 91,884 | 98,060 | 6,176 | 2 | +45,474 | -33,940 |

## full_electrification_solar

Full electrification + rooftop solar (NEM3); 200 A panel (case 02 style).

Peak load 119 A → panel status **green**.

| Rate model | Journey $ | Do-nothing $ | Savings (Δopex) | Payback | Savings vs ref | Do-nothing vs ref |
|---|--:|--:|--:|:--:|--:|--:|
| Legacy default (CAGR-flat, EIA per-utility) | 37,433 | 132,000 | 94,567 | 1 | +0 | +0 |
| Legacy ACC (PG&E/CPUC base) | 45,418 | 129,420 | 84,002 | 1 | -10,565 | -2,580 |
| WhyWatt Conservative | 24,784 | 246,975 | 222,191 | 1 | +127,624 | +114,975 |
| WhyWatt Moderate | 25,901 | 280,402 | 254,501 | 1 | +159,934 | +148,402 |
| WhyWatt Stress | 27,757 | 387,698 | 359,941 | 1 | +265,374 | +255,698 |
| CEC 2025 IEPR (elec) + CEC 2025 BAU-invest (gas) | 25,682 | 292,813 | 267,132 | 1 | +172,565 | +160,813 |
| US EIA national average | 27,342 | 102,976 | 75,634 | 1 | -18,933 | -29,024 |
| EIA AEO Pacific | 25,753 | 98,060 | 72,307 | 1 | -22,260 | -33,940 |

## panel_upgrade_100A

Full electrification on a 100 A service — forces a panel upgrade (case 07).

Peak load 119 A → panel status **red**.

| Rate model | Journey $ | Do-nothing $ | Savings (Δopex) | Payback | Savings vs ref | Do-nothing vs ref |
|---|--:|--:|--:|:--:|--:|--:|
| Legacy default (CAGR-flat, EIA per-utility) | 171,298 | 132,000 | -39,298 | 2 | +0 | +0 |
| Legacy ACC (PG&E/CPUC base) | 167,634 | 129,420 | -38,214 | 2 | +1,084 | -2,580 |
| WhyWatt Conservative | 80,888 | 246,975 | 166,087 | 2 | +205,385 | +114,975 |
| WhyWatt Moderate | 85,845 | 280,402 | 194,558 | 2 | +233,856 | +148,402 |
| WhyWatt Stress | 94,402 | 387,698 | 293,296 | 2 | +332,594 | +255,698 |
| CEC 2025 IEPR (elec) + CEC 2025 BAU-invest (gas) | 85,625 | 292,813 | 207,188 | 2 | +246,486 | +160,813 |
| US EIA national average | 97,047 | 102,976 | 5,929 | 2 | +45,227 | -29,024 |
| EIA AEO Pacific | 91,884 | 98,060 | 6,176 | 2 | +45,474 | -33,940 |

## hvac2027_wh2029_30yr

HVAC 2027 + WH 2029 only, 30-year horizon (projection holds flat past 2050).

Peak load 78 A → panel status **yellow**.

| Rate model | Journey $ | Do-nothing $ | Savings (Δopex) | Payback | Savings vs ref | Do-nothing vs ref |
|---|--:|--:|--:|:--:|--:|--:|
| Legacy default (CAGR-flat, EIA per-utility) | 293,765 | 273,133 | -20,633 | — | +0 | +0 |
| Legacy ACC (PG&E/CPUC base) | 301,495 | 277,569 | -23,926 | — | -3,293 | +4,436 |
| WhyWatt Conservative | 182,891 | 484,531 | 301,640 | 3 | +322,273 | +211,398 |
| WhyWatt Moderate | 216,934 | 671,207 | 454,273 | 3 | +474,906 | +398,074 |
| WhyWatt Stress | 318,938 | 1,280,200 | 961,262 | 3 | +981,895 | +1,007,067 |
| CEC 2025 IEPR (elec) + CEC 2025 BAU-invest (gas) | 316,402 | 1,347,851 | 1,031,449 | 3 | +1,052,082 | +1,074,718 |
| US EIA national average | 155,557 | 166,992 | 11,435 | 3 | +32,068 | -106,141 |
| EIA AEO Pacific | 151,162 | 160,012 | 8,851 | 3 | +29,484 | -113,121 |
