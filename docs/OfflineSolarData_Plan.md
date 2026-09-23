# Offline Solar Data (PVWatts) — Harvest & Analysis Plan

**Status:** 🟢 ACTIVE build plan for a standalone, offline sub-project.
**Type:** Python + Jupyter data-harvest + analysis effort. **No** changes to the live WhyWatt
model; the golden is untouched by construction because none of this is imported by `src/`.
**Prepared:** 2026-09-07. **Revised:** 2026-09-22 — re-scoped from *per-CEC-zone* to **per-ZIP**
yield (monthly + hourly-derived intra-day shape) at a single default orientation, harvested
**incrementally by CCA territory** (SVCE first, §2b). Every fallback is a full table — the scalar
`specific_yield` is retired in Phase 7. Address-level and live-API options rejected (§2a). URDB
half removed — superseded by `docs/OfflineURDB_Plan.md` (DONE).
**Relationship to other docs:**
- Sibling offline efforts (the pattern this mirrors): `docs/OfflineURDB_Plan.md` (DONE),
  `docs/OfflineRateProjection_Plan.md` (CLOSED).
- Live consumption of this data is **Phase 7 §1** — see `docs/Phase7_Spec.md` (PVWatts solar
  generation feeding the §0 battery dispatch).

---

## 1. Objective

Collect **real PVWatts v8 (NREL)** solar yield **per ZIP**, region by region (§2b), with
provenance, and review it in a notebook + tests, so Phase 7 is "wire in data we've already seen and
trust." This data **replaces** the scalar `specific_yield` (1,500 kWh/kW/yr) outright — Phase 7
removes that field from the model, config and UI. Solar output is always driven by a monthly +
intra-day table, never a single number.

Per site, at a fixed default orientation and **per 1 kW DC**:

| Field | Anchors (Phase 7) |
|---|---|
| `ac_monthly[12]` — kWh/kW per month | **monthly variation** — the solar generation vector; × `system_kw` (panels × kW/panel, already a model input) |
| `intraday_shape[12][24]` — normalized hourly shape per month | **daily variation** — places each month's generation into the §0 dispatch periods (solar-window / peak / off-peak) |

**The message this has to carry:** *even a small system (~4 kW) + battery is a big win.* That
depends on realistic seasonal yield and on how much generation lands in the peak tail — both of
which location sets. It does **not** need address-level precision (§2a).

---

## 2. Decisions locked

1. **Bake offline, never call live.** Matches the climate/EIA/ACC/URDB pipeline; keeps the UI
   synchronous and working at an event with no network. Scripts run manually with an API key
   (`NREL_API_KEY` env var, never committed), never in CI.
2. **Geo granularity: per ZIP** (ZCTA centroid lat/lon). **Every level of the fallback ladder is a
   full table** (`ac_monthly[12]` + `intraday_shape[12][24]`) — no scalar anywhere:
   1. **ZIP site** — the ZIP's region has been harvested (§2b);
   2. **CEC-zone station table** — the ZIP's zone reference station (via `zip_to_zone.json`), for
      not-yet-harvested regions and PO-box/unique ZIPs with no centroid;
   3. **Default table** — the CZ4 (San José) zone-station table, for an unknown/out-of-state ZIP.

   Wave 0 harvests all 16 zone stations, so levels 2–3 cover **every** CA ZIP from day one; each
   later wave only upgrades ZIPs from zone-level to ZIP-level.
3. **Single default orientation** — `array_type=1` (fixed roof mount), `module_type=0` (standard),
   `tilt=20`, `azimuth=180`, `losses=14`, `dataset=nsrdb`. Roof tilt/azimuth stay **inert**
   through Phase 7 (orientation correction deferred — the advocacy message doesn't need it).
   System size is the model's existing `panels × kw_per_panel` tunable.
4. **Hourly is fetched once per ZIP** (`timeframe=hourly`) and **reduced** to the 12×24 normalized
   shape + the monthly totals. The 8760 series itself is not committed (§4c).

### 2a. Options considered and rejected

| Option | Why not |
|---|---|
| **Street address → PVWatts** | PVWatts snaps any lat/lon to a ~4 km NSRDB weather cell; a ZIP centroid lands in the same or adjacent cell, so the yield difference is negligible. Home-to-home variance is dominated by roof orientation, shading and system size — not location. Also: never collecting an address is a stronger privacy promise than "we don't store it." |
| **Live PVWatts pull at the event** | Violates Phase 7 Invariant 1 (no runtime network); fails exactly when event Wi-Fi does. We cannot promise NREL doesn't log requests (API key, caller IP, query). If only the ZIP centroid were sent, the result equals the pre-baked value — no gain. |
| **Advocate-contributed zip-tagged baseline files** | Unnecessary — advocates send a **region request** (CCA / city / ZIP list) instead of data; the developer adds it to `scripts/solar_regions.py` and runs the harvest. One reviewed pipeline, one provenance trail. |
| **Keep a scalar `specific_yield` (as default or per-home override)** | One annual number carries neither the seasonal curve nor the intra-day timing the §0 battery dispatch needs. Retired in Phase 7; every fallback is a table. |

### 2b. Harvest waves — by CCA territory, Bay Area first

Harvest is built up **slowly, one region per run**, grouped by **Community Choice Aggregator
(CCA)** territory — how the advocate network is organized. The CCA is only a *harvest and review
grouping*; yield is pure location physics (a CCA boundary changes nothing).

| Wave | Region tag | Territory | Notes |
|---|---|---|---|
| **0** | `ca_zone_stations` | 16 CEC zone reference stations | the table fallback for all CA (§2 #2); 16 calls |
| **1** | `svce` | **Silicon Valley Clean Energy** — Campbell, Cupertino, Gilroy, Los Altos, Los Altos Hills, Los Gatos, Milpitas, Monte Sereno, Morgan Hill, Mountain View, Saratoga, Sunnyvale, unincorporated Santa Clara County | pilot; review end-to-end before wave 2 |
| **2** | `pce`, `sjce` | **Peninsula Clean Energy** (San Mateo County) · **San José Clean Energy** (City of San José) | |
| 3+ | e.g. `ava`, `mce`, `cleanpowersf`, `scp` | other Bay Area CCAs (Ava Community Energy, MCE, CleanPowerSF, Sonoma Clean Power …) | then the rest of CA, on request |

- **Region table:** `scripts/solar_regions.py` maps `region tag → {name, member jurisdictions,
  zips[], source_url}`. ZIP lists are **curated from each CCA's published member list** (re-verify
  membership at harvest time — CCAs add cities). ZIPs straddling a boundary are included; an extra
  ZIP costs one API call and can't be physically wrong. Adding a region is a data edit, not code.
- **Enclaves:** Palo Alto (CPAU) and the City of Santa Clara (Silicon Valley Power) sit inside
  SVCE's footprint but are municipal utilities. Their ZIPs still get the same sun — harvest them
  with the wave that covers them geographically.
- **Additive output:** each run merges into `pvwatts_zip.json` and never rewrites other regions;
  `_meta.regions[]` records tag, ZIP count and harvest date per wave.
- *Aside, out of scope here:* CCA customers pay CCA generation rates, not PG&E bundled — a possible
  future refinement on the URDB rate side, not solar.

---

## 3. Inputs

- **ZIP → lat/lon:** US Census **2020 ZCTA Gazetteer** (public domain) — download to
  `scripts/downloads/` (gitignored), record URL + sha256 in the output `_meta`. Filter to the ZIPs
  in `zip_to_zone.json`.
- **ZIP → CEC zone:** `data/climate/zip_to_zone.json` (2,694 ZIPs, already committed).
- **Zone fallback site:** `latitude`/`longitude` per zone in `data/climate/tmy3_zones.json`
  (added by `scripts/augment_zones_geo.py`, Phase 6 WS2).

---

## 4. Harvest plan — `scripts/build_pvwatts.py`

**§4a — Calls.** `python scripts/build_pvwatts.py --region svce` — one PVWatts v8 call per
**unique site** in the region: each ZIP's ZCTA centroid (wave 0: the 16 zone stations).
`system_capacity=1`, default orientation (§2 #3), `timeframe=hourly`.
- **Rate limit:** NREL default is 1,000 req/hr — a CCA wave (tens of ZIPs) takes minutes; even all
  of CA (~1,700 centroids) would be ~2 hours. The script is
  **resumable**: each response is cached locally by site key; re-runs skip cached sites. Throttle
  + retry with backoff on 429/5xx.
- Record per site the `station_info` PVWatts returns (NSRDB cell lat/lon, distance) so the
  notebook can show which ZIPs share a weather cell.

**§4b — Reduce.** From each hourly response (`ac`, W per hour, 8760):
- `ac_monthly[m]` = Σ hourly ac in month *m* / 1000 → kWh/kW. Cross-check against PVWatts'
  own `ac_monthly` (must agree to rounding).
- `intraday_shape[m][h]` = Σ over days in *m* of ac at hour *h*, normalized so each month's 24
  values sum to 1. (Hours are local standard time as PVWatts reports them — note it in `_meta`;
  the Phase 7 dispatch maps periods to these hours, DST-shifted for summer TOU windows.)
- `ac_annual` = Σ `ac_monthly`.

**§4c — Output + provenance.**
- `data/solar/pvwatts_zip.json` (committed, compact JSON) —
  ```
  _meta:   source, api version, request params, dataset, gazetteer url+sha256, build date,
           hour convention, fallback rules, site count
  sites:   { <site_key>: { lat, lon, nsrdb_station{lat,lon,distance}, ac_monthly[12],
                           ac_annual, intraday_shape[12][24], raw_sha256 } }
  zips:    { <zip>: { zone, region, site: <site_key> } }        # harvested ZIPs only
  zones:   { <zone>: { site: <zone_station_site_key> } }        # fallback level 2 (all 16)
  default: { zone: "CA_CZ4", site: <cz4_station_site_key> }     # fallback level 3
  ```
  Sites are keyed separately so ZIPs that share a site (and zone fallbacks) don't duplicate the
  12×24 shape. Unharvested ZIPs are simply absent from `zips` and resolve via `zip_to_zone.json` →
  `zones`. **Size budget:** ≲ 3 MB even at full CA (≈1,700 sites × 300 floats at 4 dp); the test
  enforces it.
- **Raw snapshots:** hourly responses are a few hundred KB each — **too large to commit** at scale.
  Commit raw JSON for the **16 zone stations** under `data/solar/sources/`; keep the per-ZIP raw
  cache local (gitignored `data/solar/sources/cache/`) and record each response's `raw_sha256` in
  the baked file. This is a deliberate, documented relaxation of Phase 7 Invariant 2 — the build
  is reproducible by re-running the script.

---

## 5. Analysis notebook + validation tests

**`notebooks/pvwatts_review.ipynb`** (the human review surface):
- Annual kWh/kW by ZIP for the harvested regions (scatter on lat/lon, coloured by zone / region) —
  coastal vs inland gradient.
- **ZIP vs zone-station delta** — for each harvested ZIP, how far its table is from the zone
  fallback it replaced (annual and peak-window share). Shows what each wave actually buys.
- Monthly yield curves for a handful of ZIPs per zone; intra-day shape heatmaps (12×24) for a
  coastal vs inland ZIP.
- Table: zone-station annual vs the retired scalar `specific_yield=1500` (continuity).
- **The message check:** annual production of a **4 kW** system per ZIP, and the fraction of
  generation falling in the ~4–9pm peak window by month (what the battery has to shift).

**`tests/test_pvwatts_data.py`** (CI gate, reads only the committed JSON):
- Every ZIP in `zip_to_zone.json` resolves to a **table** (ZIP → zone → default); all 16 zones and
  the default have a site; every ZIP listed for a harvested region in `solar_regions.py` has a
  direct `zips` entry (a wave is complete or it isn't).
- `ac_monthly` length 12, all > 0, summer-peaked (max in May–Aug); annual in a sane CA band
  (~1,250–1,850 kWh/kW/yr).
- `intraday_shape` is 12×24, each month sums to 1 (±1e-6), ~zero at night hours.
- Σ `ac_monthly` ≈ Σ hourly-derived total (the reduction is consistent).
- CZ4 zone-station annual in 1,500–1,750 (continuity with the retired `specific_yield=1500`).
- Geographic ordering: Arcata (CZ1) lowest, the desert stations (CZ14, CZ15) the top two.
- File size within budget.

---

## 6. Isolation guarantee

Nothing under `data/solar/` is imported by live sim code until Phase 7:

```bash
git grep -nE "data/solar/|pvwatts_zip" -- src/ ':!src/**/*.md'
# must return zero (review-only until Phase 7)
```

---

## 7. Repo layout (deltas)

```
scripts/
  solar_regions.py        (NEW) region tag → CCA member jurisdictions → ZIP list (+ source URL)
  build_pvwatts.py        (NEW, run offline) --region → sites → PVWatts hourly → reduce → merge into pvwatts_zip.json
data/
  solar/pvwatts_zip.json  (NEW, baked) per-site monthly yield + 12×24 shape; ZIP + zone index
  solar/sources/          (NEW) raw PVWatts JSON for the 16 zone stations (committed)
  solar/sources/cache/    (NEW, gitignored) per-ZIP raw responses — resumable harvest cache
notebooks/
  pvwatts_review.ipynb    (NEW) ZIP yield map / within-zone spread / shapes / 4 kW message check
tests/
  test_pvwatts_data.py    (NEW) coverage + shape + plausibility + CZ4 bridge + size budget
.gitignore                (append) data/solar/sources/cache/
```

---

## 8. Task checklist (build order)

- [ ] Download 2020 ZCTA Gazetteer (centroids).
- [x] `build_pvwatts.py`: resumable hourly harvest → reduce → additive merge + zone-station snapshots.
- [x] **Wave 0** — 16 zone stations + CZ4 default (the table fallback for all CA). Done 2026-09-22 (§10).
- [ ] `solar_regions.py` — `svce` ZIP list from SVCE's member communities.
- [ ] **Wave 1 — SVCE**; notebook review + tests green before moving on.
- [ ] **Wave 2 — PCE + SJCE.**
- [ ] `pvwatts_review.ipynb` runs top-to-bottom; `test_pvwatts_data.py` green; isolation grep-gate green.
- [ ] Later waves (other Bay Area CCAs, rest of CA) as advocates request them.

## 9. Definition of done

- Waves 0–2 committed with provenance: every CA ZIP resolves to a table — ZIP-level for SVCE, PCE
  and SJCE; zone-level elsewhere. Later waves are additive and don't gate Phase 7.
- Tests green; the review notebook runs and records the ZIP-vs-zone delta and the 4 kW finding.
- `git grep` confirms no `src/` code reads `data/solar/`.
- Phase 7 §1 consumes what survives review.

## 10. Results log

### Wave 0 — CEC zone stations (2026-09-22)

16/16 stations harvested (PVWatts v8, `developer.nlr.gov` — NREL was renamed the National
Laboratory of the Rockies and `developer.nrel.gov` no longer resolves; key from
`secrets/nrel_api_key`, see `secrets/README.md`). `pvwatts_zip.json` 36 KB; trimmed raw snapshots
836 KB under `data/solar/sources/zone_stations/`. `test_pvwatts_data.py` 11/11 green; API key
verified absent from every harvested file.

| Zone | Station | kWh/kW/yr | Jun/Dec | 4 kW system kWh/yr | Jul output in 4–9pm |
|---|---|---:|---:|---:|---:|
| CZ1 | Arcata | 1,350 | 2.8 | 5,400 | 21.8% |
| CZ2 | Santa Rosa | 1,558 | 2.6 | 6,232 | 19.7% |
| CZ3 | Oakland | 1,624 | 2.2 | 6,497 | 19.8% |
| **CZ4** | **San José (default)** | **1,644** | 2.2 | 6,576 | 18.5% |
| CZ5 | Santa Maria | 1,692 | 1.7 | 6,767 | 18.1% |
| CZ6 | Los Angeles | 1,673 | 1.4 | 6,690 | 16.8% |
| CZ7 | San Diego | 1,599 | 1.4 | 6,397 | 15.5% |
| CZ8 | El Toro | 1,680 | 1.6 | 6,719 | 16.5% |
| CZ9 | Pasadena | 1,719 | 1.6 | 6,877 | 16.5% |
| CZ10 | Riverside | 1,694 | 1.6 | 6,777 | 14.9% |
| CZ11 | Red Bluff | 1,518 | 2.6 | 6,070 | 18.8% |
| CZ12 | Sacramento | 1,621 | 2.4 | 6,484 | 18.0% |
| CZ13 | Fresno | 1,667 | 2.2 | 6,667 | 16.3% |
| CZ14 | China Lake | 1,840 | 1.6 | 7,359 | 15.2% |
| CZ15 | El Centro | 1,778 | 1.5 | 7,111 | 13.6% |
| CZ16 | Blue Canyon | 1,546 | 2.2 | 6,184 | 17.8% |

(4–9pm is clock time — PDT in July, i.e. local-standard hours 15–19. January peak share is 1.5–3%.)

**Findings.**
- **The retired scalar under-stated solar:** CZ4 is 1,644 vs `specific_yield=1500` (+9.6%) at the
  default orientation. Expect solar savings to rise in the Phase 7 golden re-baseline.
- **Spread is narrower than the old "coast ~1,400 / inland ~1,650" rule of thumb:** only the north
  coast (Arcata) is truly low; Oakland ≈ Sacramento (tule fog). Coastal-vs-inland *within* the Bay
  Area is a wave 1+ question (ZIP level), not answerable from one station per zone.
- **Only ~15–22% of summer output lands in the 4–9pm peak** (and ~2–3% in winter) — the battery is
  what moves solar value into the peak, which is the "4 kW + battery" message.
