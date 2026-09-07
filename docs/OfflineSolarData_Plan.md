# Offline Solar & TOU-Rate Data — Harvest & Analysis Plan

**Status:** 🟢 ACTIVE build plan for a standalone, offline sub-project.
**Type:** Python + Jupyter data-harvest + analysis effort. **No** changes to the live WhyWatt
model; the golden is untouched by construction because none of this is imported by `src/`.
**Prepared:** 2026-09-07.
**Relationship to other docs:**
- Sibling offline effort (the pattern this mirrors): `docs/OfflineRateProjection_Plan.md` (CLOSED).
- Live consumption of this data is **Phase 7** — see `docs/Phase7_Spec.md` (PVWatts solar
  generation, battery dispatch, URDB peak/non-peak TOU). Phase 6 (`docs/Phase6_Spec.md`) carries
  only the **inert** roof-geometry inputs + per-zone lat/lon that this harvest keys off.

> **Why this is its own doc.** It was originally Phase 6 §3. Phase 6 has been recentered on the
> *simulation* (the rate hand-off interface + Solar/Battery split). This purely-offline data work —
> like the rate-projection sub-project before it — lives on its own track and does not gate the
> Phase 6 sim work. It is a prerequisite for **Phase 7**, not Phase 6.

---

## 1. Objective

Collect the **real** PVWatts and URDB datasets now, with provenance, and review them in notebooks +
tests, so Phase 7 is "wire in data we've already seen and trust" rather than "harvest + wire + debug
at once." CA-first, but every file schema is **geo-general** — keyed so out-of-CA stations/tariffs
add without a schema change.

Two datasets:

| Dataset | Source | What it anchors for Phase 7 |
|---|---|---|
| **PVWatts v8** (NREL) | per-CEC-zone per-kW monthly yield + intra-day shape | solar *generation* vector (replaces scalar `specific_yield=1500`) |
| **URDB v8** (OpenEI) | residential TOU tariffs: peak/off-peak rates, slabs, 12×24 schedule | the peak/non-peak *rate interface* + consumption split |

The datasets are committed but **read by no sim code** (Invariant below). They exist to be
reviewed, not yet to drive output.

---

## 2. Decisions locked (carried from the prior Phase 6 plan)

1. **Bake offline, never call live.** Matches the climate/EIA/ACC/rate-projection pipeline; keeps
   the UI synchronous. Scripts run manually with API keys, never in CI.
2. **PVWatts geo granularity: per CEC zone, single default orientation.** Smallest data; roof
   tilt/azimuth become Phase 7 correction factors on top of the default-orientation yield.
3. **Peak/non-peak split is fully Phase 7.** This harvest *collects and validates* the TOU data;
   Phase 7 flows it through the model. Phase 6 keeps one monthly consumption stream.
4. **Targeted, region-at-a-time harvest.** Validate one region end-to-end before broadening. The
   region → (zones, utilities, tariff ids) mapping lives in a small table (`scripts/regions.py`),
   so adding a region is a data edit, not new code.

API keys (free NREL + OpenEI) are read from env vars (`NREL_API_KEY`, `URDB_API_KEY`), never
committed.

### Region schedule

| Target | Region | Utilities | CEC zones (core) | TOU tariffs (verify labels in URDB at harvest) |
|---|---|---|---|---|
| **1 (now)** | Bay Area | PG&E | CZ3 (coast), CZ4 (South Bay, default), CZ2 (inland N. Bay) | PG&E E-TOU-C, E-ELEC, EV2-A |
| **2 (next)** | SoCal | SCE, SDG&E | CZ6/CZ8 (LA basin), CZ9/CZ10 (inland), CZ7 (San Diego), CZ14 (desert) | SCE TOU-D-4-9PM, TOU-D-PRIME; SDG&E TOU-DR1, EV-TOU-5 |

---

## 3. Prerequisite carried by Phase 6 (not this doc)

PVWatts keys off **per-CEC-zone lat/lon**. Phase 6 WS2 adds lat/lon to
`data/climate/tmy3_zones.json` (each zone already names its `tmy3_station`; the trend fit already
used station lat/lon — surface it into the record). This harvest **consumes** that; it does not add
it. If Phase 6 has not yet landed lat/lon, a one-off augmentation in this script's setup is
acceptable, but the canonical home for lat/lon is the climate DB.

---

## 4. Harvest plan

Each object writes JSON + snapshots the raw source with sha256 under `sources/`, exactly like the
existing `data/rates/sources/provenance.json` and the rate-projection sub-project.

**§4a — PVWatts batch harvest (`scripts/build_pvwatts.py --region bayarea`):**
- For each CEC-zone reference station in the region (lat/lon from the climate DB), call PVWatts v8
  with `system_capacity=1`, default orientation (`array_type=fixed_roof`, `module_type=standard`,
  `tilt=20`, `azimuth=180`, `losses=14`).
- Append `ac_monthly` (the **per-kW monthly yield vector**), `ac_annual`, the request params, and
  `sha256(raw_response)` to `data/solar/pvwatts_zones.json` (keyed by zone, additive across
  regions); snapshot raw responses under `data/solar/sources/`.
- **Also request `timeframe=hourly`** and derive a **normalized intra-day solar shape** per month
  per zone — the fraction of each month's generation that falls in the solar-window / peak /
  off-peak periods (a 12×24 normalized shape, or the collapsed 12×3 period fractions). Store as
  `intraday_shape` in the zone record. Phase 7's dispatch engine needs this to place monthly
  generation into the three daily periods (it can't be recovered from `ac_monthly` alone). This is
  the only reason hourly output is fetched; the monthly totals still drive sizing.

**§4b — URDB batch harvest (`scripts/build_urdb.py --region bayarea`):**
- For the region's curated residential TOU tariffs, fetch URDB v8 `detail=full` and parse
  `energyratestructure` (tiered slabs: `{max, rate, adj, sell}`) + `energyweekdayschedule` /
  `energyweekendschedule` (12×24 period grid) into the simplified schema `{tariff_id, utility,
  region, peak_rate, offpeak_rate, peak_hours (12×24 period index or bool grid), tiers,
  fixed_charge}` → `data/rates/urdb_tou.json` (additive across regions); snapshot raw responses with
  sha256 under `data/rates/sources/`.

---

## 5. Analysis notebooks + validation tests (the point of doing this offline)

**Jupyter notebooks** (`notebooks/pvwatts_review.ipynb`, `notebooks/urdb_review.ipynb`) read the
committed JSON and produce the data review:
- *PVWatts:* per-zone monthly yield curves, a cross-zone annual-yield bar, and a Bay-Area vs SoCal
  coastal/inland comparison; a table comparing each zone's annual per-kW yield against today's
  scalar `specific_yield=1500`.
- *URDB:* a 12×24 **peak-hour heatmap** per tariff (confirm the ~4–9pm peak window), a
  peak-vs-offpeak rate bar with tier-threshold overlays, and a table of each tariff's load-weighted
  flat-equivalent vs the EIA per-utility rate already in the model.
- These notebooks are the human review surface — run them, eyeball the figures, sanity-check the
  numbers from both APIs before Phase 7 trusts them.

**Automated tests** (`tests/test_pvwatts_data.py`, `tests/test_urdb_data.py`) encode the same checks
as a CI gate, independent of the notebooks: each yield vector is length-12, summer-peaked, with
annual sum in a sane CA band (~1,300–1,750 kWh/kW/yr, coastal < inland) and CZ4 default-orientation
annual ≈ `specific_yield=1500`; URDB schedules parse to 12×24 with every hour mapped to a defined
period, tier `max` thresholds ascend, and each tariff's load-weighted flat-equivalent lands within
tolerance of the matching EIA per-utility rate.

---

## 6. Isolation guarantee

Nothing under `data/solar/` or `data/rates/urdb_tou.json` is imported by live sim code. A grep gate
keeps it honest (same discipline as the rate-projection sub-project):

```bash
git grep -nE "data/solar/|urdb_tou" -- src/ ':!src/**/*.md'
# must return zero (review-only until Phase 7)
```

---

## 7. Repo layout (deltas)

```
scripts/
  regions.py            (NEW) region → (CEC zones, utilities, tariff ids) mapping
  build_pvwatts.py      (NEW, run offline) PVWatts batch harvest --region → pvwatts_zones.json
  build_urdb.py         (NEW, run offline) URDB batch harvest --region → urdb_tou.json
data/
  solar/pvwatts_zones.json   (NEW, baked) per-zone per-kW monthly yield + intraday_shape + provenance
  solar/sources/             (NEW) raw PVWatts JSON snapshots (sha256)
  rates/urdb_tou.json        (NEW, baked) simplified peak/offpeak + slabs per tariff
  rates/sources/             (append) raw URDB JSON snapshots (sha256)
notebooks/
  pvwatts_review.ipynb  (NEW) yield curves / cross-zone + Bay-vs-SoCal / specific_yield table
  urdb_review.ipynb     (NEW) 12×24 peak-hour heatmap / rate bars / EIA cross-check table
tests/
  test_pvwatts_data.py  (NEW) yield-vector shape/plausibility + CZ4 sanity bridge
  test_urdb_data.py     (NEW) schedule parse + slab order + EIA cross-source sanity
```

---

## 8. Task checklist (build order)

- [ ] `scripts/regions.py` — Bay Area region table (zones, PG&E, tariff ids).
- [ ] **§4a PVWatts** Bay Area harvest → `pvwatts_zones.json` + `intraday_shape` + snapshots.
- [ ] **§4b URDB** Bay Area PG&E TOU tariffs → `urdb_tou.json` + snapshots.
- [ ] `pvwatts_review.ipynb` + `urdb_review.ipynb` run top-to-bottom and render figures.
- [ ] `test_pvwatts_data.py` + `test_urdb_data.py` green.
- [ ] Isolation grep-gate green (no `src/` code reads the new data files).
- [ ] SoCal region (optional/second) once Bay Area validates end-to-end.

## 9. Definition of done

- Bay Area PVWatts + URDB datasets committed with provenance (SoCal optional/second).
- Validation tests green; both review notebooks run top-to-bottom and render their figures.
- `git grep` confirms no `src/` model/rate code imports `data/solar/` or `data/rates/urdb_tou.json`.
- Phase 7 consumes what survives review.
