# Rate-model impact — validation snapshot

_Generated 2026-09-10T01:14:49Z._  
Rate-model impact snapshot (Phase 6 WS1). Non-default projection paths are exercised deliberately — this is not the golden. sim_start_year=2025; 20-year horizon (app default) except where a scenario sets `years`; HVAC swap 2027, WH swap 2029.

Deltas are vs the reference run **`legacy_default_cagr`** (current app default). `opex_delta` = do-nothing − journey (positive = the journey saves money).

## hvac2027_wh2029

HVAC swap 2027 + Water Heater swap 2029 only (the requested scenario).

Peak load 78 A → panel status **yellow**.

| Rate model | Journey $ | Do-nothing $ | Savings (Δopex) | Payback | Savings vs ref | Do-nothing vs ref |
|---|--:|--:|--:|:--:|--:|--:|
| Legacy default (CAGR-flat, EIA per-utility) | 140,731 | 132,000 | -8,731 | — | +0 | +0 |
| Legacy ACC (PG&E/CPUC base) | 143,040 | 129,420 | -13,620 | — | -4,889 | -2,580 |
| WhyWatt Conservative | 107,993 | 202,832 | 94,839 | 6 | +103,570 | +70,832 |
| WhyWatt Moderate | 115,266 | 229,171 | 113,905 | 6 | +122,636 | +97,171 |
| WhyWatt Stress | 133,590 | 313,396 | 179,806 | 7 | +188,537 | +181,396 |
| CEC 2025 IEPR (elec) + CEC 2025 BAU-invest (gas) | 128,801 | 290,650 | 161,849 | 5 | +170,580 | +158,650 |
| US EIA national average | 68,431 | 67,077 | -1,354 | — | +7,377 | -64,923 |
| EIA AEO Pacific | 78,045 | 78,613 | 567 | 11 | +9,298 | -53,387 |

## full_electrification_2027_29

HVAC 2027 + WH 2029 + dryer/cooktop/EV planned; 200 A panel (case 01 style).

Peak load 119 A → panel status **green**.

| Rate model | Journey $ | Do-nothing $ | Savings (Δopex) | Payback | Savings vs ref | Do-nothing vs ref |
|---|--:|--:|--:|:--:|--:|--:|
| Legacy default (CAGR-flat, EIA per-utility) | 171,298 | 132,000 | -39,298 | 2 | +0 | +0 |
| Legacy ACC (PG&E/CPUC base) | 167,634 | 129,420 | -38,214 | 2 | +1,084 | -2,580 |
| WhyWatt Conservative | 85,878 | 202,832 | 116,954 | 2 | +156,252 | +70,832 |
| WhyWatt Moderate | 91,950 | 229,171 | 137,221 | 2 | +176,519 | +97,171 |
| WhyWatt Stress | 102,504 | 313,396 | 210,892 | 2 | +250,190 | +181,396 |
| CEC 2025 IEPR (elec) + CEC 2025 BAU-invest (gas) | 99,715 | 290,650 | 190,935 | 2 | +230,233 | +158,650 |
| US EIA national average | 50,861 | 67,077 | 16,216 | 2 | +55,514 | -64,923 |
| EIA AEO Pacific | 64,700 | 78,613 | 13,913 | 2 | +53,211 | -53,387 |

## full_electrification_solar

Full electrification + rooftop solar (NEM3); 200 A panel (case 02 style).

Peak load 119 A → panel status **green**.

| Rate model | Journey $ | Do-nothing $ | Savings (Δopex) | Payback | Savings vs ref | Do-nothing vs ref |
|---|--:|--:|--:|:--:|--:|--:|
| Legacy default (CAGR-flat, EIA per-utility) | 38,852 | 132,000 | 93,148 | 1 | +0 | +0 |
| Legacy ACC (PG&E/CPUC base) | 46,482 | 129,420 | 82,938 | 1 | -10,210 | -2,580 |
| WhyWatt Conservative | 24,571 | 202,832 | 178,261 | 1 | +85,113 | +70,832 |
| WhyWatt Moderate | 26,198 | 229,171 | 202,973 | 1 | +109,825 | +97,171 |
| WhyWatt Stress | 28,985 | 313,396 | 284,411 | 1 | +191,263 | +181,396 |
| CEC 2025 IEPR (elec) + CEC 2025 BAU-invest (gas) | 29,094 | 290,650 | 261,556 | 1 | +168,408 | +158,650 |
| US EIA national average | 14,306 | 67,077 | 52,771 | 1 | -40,377 | -64,923 |
| EIA AEO Pacific | 18,594 | 78,613 | 60,019 | 1 | -33,129 | -53,387 |

## panel_upgrade_100A

Full electrification on a 100 A service — forces a panel upgrade (case 07).

Peak load 119 A → panel status **red**.

| Rate model | Journey $ | Do-nothing $ | Savings (Δopex) | Payback | Savings vs ref | Do-nothing vs ref |
|---|--:|--:|--:|:--:|--:|--:|
| Legacy default (CAGR-flat, EIA per-utility) | 171,298 | 132,000 | -39,298 | 2 | +0 | +0 |
| Legacy ACC (PG&E/CPUC base) | 167,634 | 129,420 | -38,214 | 2 | +1,084 | -2,580 |
| WhyWatt Conservative | 85,878 | 202,832 | 116,954 | 2 | +156,252 | +70,832 |
| WhyWatt Moderate | 91,950 | 229,171 | 137,221 | 2 | +176,519 | +97,171 |
| WhyWatt Stress | 102,504 | 313,396 | 210,892 | 2 | +250,190 | +181,396 |
| CEC 2025 IEPR (elec) + CEC 2025 BAU-invest (gas) | 99,715 | 290,650 | 190,935 | 2 | +230,233 | +158,650 |
| US EIA national average | 50,861 | 67,077 | 16,216 | 2 | +55,514 | -64,923 |
| EIA AEO Pacific | 64,700 | 78,613 | 13,913 | 2 | +53,211 | -53,387 |

## hvac2027_wh2029_30yr

HVAC 2027 + WH 2029 only, 30-year horizon (projection holds flat past 2050).

Peak load 78 A → panel status **yellow**.

| Rate model | Journey $ | Do-nothing $ | Savings (Δopex) | Payback | Savings vs ref | Do-nothing vs ref |
|---|--:|--:|--:|:--:|--:|--:|
| Legacy default (CAGR-flat, EIA per-utility) | 293,765 | 273,133 | -20,633 | — | +0 | +0 |
| Legacy ACC (PG&E/CPUC base) | 301,495 | 277,569 | -23,926 | — | -3,293 | +4,436 |
| WhyWatt Conservative | 179,333 | 393,502 | 214,170 | 6 | +234,803 | +120,369 |
| WhyWatt Moderate | 209,307 | 539,820 | 330,513 | 6 | +351,146 | +266,687 |
| WhyWatt Stress | 295,447 | 1,016,556 | 721,109 | 7 | +741,742 | +743,423 |
| CEC 2025 IEPR (elec) + CEC 2025 BAU-invest (gas) | 334,075 | 1,340,616 | 1,006,540 | 5 | +1,027,173 | +1,067,483 |
| US EIA national average | 108,483 | 106,160 | -2,323 | — | +18,310 | -166,973 |
| EIA AEO Pacific | 125,580 | 126,615 | 1,034 | 11 | +21,667 | -146,518 |
