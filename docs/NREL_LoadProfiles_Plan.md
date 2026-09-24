# NREL End-Use Load Profiles — implementation plan (Phase 7 §6)

> Branch `feat/nrel-end-use-load-profiles` (off `main` @ `74104c1`). Started 2026-09-24.
> Spec: `docs/Phase7_Spec.md` §6. This file records the source verification ("verify at planning")
> and the decisions, then the work steps. One golden re-baseline at the end.

## 1. Source verification (done 2026-09-24)

Checked directly on the OEDI data lake (`s3://oedi-data-lake/nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/`).

| Question (spec §6) | Finding |
|---|---|
| Release | **ResStock 2025 Release 1, AMY2018** (`2025/resstock_amy2018_release_1`, README Nov 2025 / Apr 2026). The newest residential release; the TMY3 alternative (`2024/resstock_tmy3_release_2`) has **no EV** and the older heat-pump model. |
| Geography → CEC zone | Pre-built aggregates exist only by state / Building America zone / IECC zone / ISO — **not** by CEC zone. But every building's metadata carries **`in.cec_climate_zone`** (1–16), so we aggregate **individual buildings** ourselves. CA single-family detached samples per zone: 252 (CZ1) … 5,104 (CZ12); CZ4 = 1,629. |
| End-use columns | `out.electricity.<end_use>.energy_consumption..kwh`, 15-min: `heating`, `heating_fans_pumps`, `heating_hp_bkup`, `cooling`, `cooling_fans_pumps`, `hot_water`, `lighting_interior/exterior/garage`, `plug_loads`, `television`, `refrigerator`, `freezer`, `range_oven`, `clothes_dryer`, `clothes_washer`, `dishwasher`, `ceiling_fan`, `ev_charging`, `pv`, … |
| EV included? | **Yes** — EVs are in the 2025.1 baseline (stochastic home charging) and as upgrades 19–23 (L1 / L2 / L2 + demand flexibility). NREL EVI-Pro is no longer needed. |
| Timestamps | **End-of-interval, Eastern Standard Time (UTC−5), no DST.** Verified empirically: interior lighting peaks at 23:00 and CA rooftop PV peaks at 15:00–16:00 in the file (solar noon ≈ 12:10 PST). The build shifts to **America/Los_Angeles clock time** (DST-aware — same convention as the PVWatts data, §1). |
| Access | Anonymous S3 (`us-west-2`); column-subset parquet reads ≈ 0.6 s per building (only the needed columns cross the wire). Needs `pyarrow` (**build-time only** — added to the offline section of `requirements.txt`, never imported by `src/`). |
| Heat-pump / HPWH homes | Few in the CA baseline (ducted HP ≈ 5 % of SFD). ResStock's own upgrades give every sampled home the device: **upg 4** (variable-speed ducted ASHP, HSPF2 8.5 / SEER2 17.5), **upg 9** (HPWH, UEF ≥ 3.3). |
| Licence / citation | Open data; cite the dataset + Technical Reference Guide and include the NLR attribution line (README §Citation). |

## 2. Decisions (defaults taken to start; ⚑ = confirm)

1. **Sample:** single-family detached, occupied, `completed_status == Success`; a seeded random
   sample of **N = 150 buildings per CEC zone** (all of them when a zone has fewer), the same
   bldg_ids across upgrades. Shapes are normalised per month, so N = 150 is ample for shape
   (ResStock's 1,000-sample guidance is for *magnitudes*). Stock weights are equal within a state,
   so a simple mean.
2. **Which run feeds which end use:**

   | WhyWatt device class | NREL end use(s) | Run |
   |---|---|---|
   | `LightsAndPlugs` | lighting (3) + plug_loads + television + refrigerator + freezer + ceiling_fan + clothes_washer — summed kWh, so the composite is weighted by NREL's own energy shares | upg 0 |
   | `InductionCooktop`, `ElectricOven` | range_oven (homes with electric cooking only) | upg 0 |
   | `HeatPumpDryer` | clothes_dryer (electric dryers only) | upg 0 |
   | `Dishwasher` | dishwasher | upg 0 |
   | `CentralAC` | cooling + cooling_fans_pumps (homes with central AC) | upg 0 |
   | `HeatPumpHVAC` — heating part | heating + heating_fans_pumps + heating_hp_bkup | **upg 4** |
   | `HeatPumpHVAC` — cooling part | cooling + cooling_fans_pumps | **upg 4** |
   | `HeatPumpWaterHeater` | hot_water | **upg 9** |
   | `EVCharger`, `PhysicsEVCharger`, `ElectricVehicle` | ev_charging | **upg 22** (L2, charging suspended on-peak) — confirmed 2026-09-24 |

   ⚑ **EV:** upg 22 matches today's overnight-dominant EVI-Pro shape and a TOU household's
   behaviour; upg 20 (unmanaged L2, plug-in on arrival) would put much more EV load in 4–9 pm.
   Both are harvested; the file carries `ev_managed` (default) and `ev_unmanaged`.
3. **Resolution:** per CEC zone × end use × **month × 24 clock hours**, all days averaged (no
   weekday/weekend split — the model has one representative day per month). Each row sums to 1.
   A month where an end use is ~0 (e.g. heating in August) falls back to that end use's annual
   shape, flagged in `_meta`.
4. **Heat-pump split:** `HeatPumpHVAC` already reports `monthly_heating()` / `monthly_cooling()`;
   the energy balance spreads each part by its own profile (no HDD/CDD proxy needed).
5. ⚑ **ACC rate weighting** (`rate_loader.py`, legacy ACC mode) **keeps** `device_load_shapes.json`
   — ACC is legacy and due its own rework (post-P7 ACC item); switching it would move the ACC
   golden cases for no user-facing gain. The file stays, used by ACC only.
6. **Provenance:** the raw parquet is too large to commit (≈ 6 MB × 2,400 files). Committed
   instead: `data/loads/sources/manifest.json` — the release, the sampled bldg_ids per zone, each
   S3 key + ETag + size, the metadata file's sha256, the columns read, the tz shift and the build
   date — so the build is exactly reproducible and changes upstream are detectable.

## 3. Work steps

1. `scripts/build_load_profiles.py` (offline; reuses a local cache under `data/loads/.cache/`,
   gitignored) → `data/loads/end_use_profiles.json` (`_meta.schema_version`, source, citation,
   profiles `{zone: {end_use: 12×24}}`) + `data/loads/sources/manifest.json`.
2. `src/load_profiles.py`: `LoadProfileLoader` → frozen `LoadProfiles` for a zone
   (`shape(device_class, month) -> (24,)`, heat-pump heating/cooling parts); exposed as
   `HomeConfig.load_profiles` (derived from the resolved CEC zone, like `SolarResource`).
3. `JourneyHome._month_loads` uses row *m* per class; heat pump split into heating + cooling parts.
   §3 `period_fractions` / URDB per-class effective rates take the (12, 24) shapes.
   `dispatch.py` unchanged.
4. Tests (`tests/test_load_profiles.py`): rows sum to 1; every device class resolves in every zone;
   lighting/plugs 4–9 pm share > flat 21 %; summer cooling peaks in the afternoon; energy balance
   still closes; clock-time check (PV-free — lighting evening peak between 18:00 and 22:00).
5. `notebooks/load_profiles_review.ipynb`: old vs new shape per device; change in self-use,
   battery discharge and peak import for the regression cases.
6. Golden: one re-baseline commit, diff explained (expected: less direct solar self-use, more
   battery discharge and peak import).
7. Docs: Phase 7 spec §6 "Landed", CLAUDE.md, help (methodology + data sources), attribution line.

## 4. Status — landed; golden re-baselined (2026-09-24)

- **Harvest:** 11,979 building-runs (16 zones × 150 × 5 runs; CZ1 has 129 heat-pump-eligible
  homes). Every zone × end use came from its own zone (no statewide fallback). Near-zero months
  took the annual shape: heating in summer (CZ11, 13, 15, 16), cooling in Dec–Jan (CZ11–13).
- **Sanity (CZ4, PST):** lights & plugs peak 19–20 h; cooling 16–17 h; heat-pump heating 7 h;
  HPWH 6–7 h; managed EV 21–22 h, unmanaged 17–18 h.
- **Tests:** `tests/test_load_profiles.py` (new) green; two existing tests re-stated:
  - `test_battery.py` — the two-mode picker vs the LP optimum: one case (2 kW, no EV, E-TOU-C,
    Jan) captures 88 % of a battery worth $1.30/mo ($0.16/mo gap); the check now also passes a
    gap under $0.50/mo.
  - `test_urdb_rates.py` — case 02 on EV2: Cost-saving no longer wins Jan/Dec; Self-powered wins
    every month (Jan $176 vs $184) because evening load now meets the battery directly. The test
    now asserts the picker takes the cheaper mode each month (and Self in July).
- **Regression:** 244 metrics move, 60/60 trend checks pass; no sign or payback-year change.
  20-year opex Δ: solar homes −$0.8k to −$1.8k (< 2 %); no-solar TOU homes +$60 to +$1.25k;
  legacy ACC / no-solar flat-rate cases unchanged. `notebooks/load_profiles_review.ipynb` has the
  shapes, the flows (old-shape rerun reproduces the committed golden exactly) and the reading.
- **Found:** before §6 the transportation-slot `ElectricVehicle` had no shape entry and was
  spread flat over the day (midday charging on solar). It now uses the managed-EV profile —
  ~53 % (case 02) to ~74 % (case 13) of the solar-home change.
