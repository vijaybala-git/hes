# WhyWatt — Phase 7 Development Spec

**Status:** 🔵 PLANNED — the data-pipeline phase. Flow new simulation data through the model.
**Follows:** Phase 6 (seams built: Solar/Battery split, roof-geometry inputs, offline build
skeletons, peak/non-peak rate interface).
**Last updated:** 2026-06-23 — initial plan.

---

## Goal

Replace the simplified placeholders Phase 6 left in place with **real, offline-baked
simulation data** from two new sources, and add a **peak / non-peak** dimension to consumption
and pricing:

1. **Solar generation from PVWatts** — per-CEC-zone monthly per-kW yield vectors replace the
   scalar `specific_yield`. The Solar device emits a **(12,) monthly generation array**.
2. **Battery charge physics** — a real charge/discharge model self-consumes generation against
   the home's load instead of a flat `scf` fraction.
3. **URDB peak / non-peak TOU rates with tiered slabs** — each device's monthly kWh is split
   into peak vs non-peak (via the existing 24-hour load shapes) and priced against
   peak/non-peak rates with slabs.

**End-state output model:** `cost = Σ_period (peak_kWh × peak_rate_slabs +
offpeak_kWh × offpeak_rate_slabs)`, with solar generation and battery dispatch reducing the
priced load. **CA-first, but no CA-only assumptions** — the data schemas and code cover the
full US footprint of PVWatts + URDB; CA zones/tariffs are simply baked and validated first.

## What changes vs. Phase 6

| Concern | Phase 6 (placeholder) | Phase 7 (real data) |
|---|---|---|
| Solar production | `system_kw × specific_yield` (scalar/yr) | `system_kw × pvwatts_monthly_yield[12]` (per zone) |
| Roof geometry | carried, inert | applied as orientation correction to the per-zone yield |
| Self-consumption | flat `scf` fraction | battery charge/discharge dispatch vs hourly/monthly load |
| Rates | EIA flat / ACC effective monthly | URDB peak + non-peak, tiered slabs |
| Consumption shape | one monthly stream `(12,)` | peak + non-peak split via 24h device shapes |
| Data sources | harvested + reviewed (unconsumed) | the same baked files now **consumed** by the model |

## Invariants

1. **Still no live API calls at runtime.** PVWatts and URDB are consumed **only** through
   committed JSON produced by `scripts/build_pvwatts.py` / `scripts/build_urdb.py`. The running
   model never touches the network.
2. **Provenance is mandatory.** Every baked file records source params + sha256 of the raw API
   response + build date, snapshotted under `data/.../sources/` (the climate-DB pattern).
3. **`monthly_consumption()` contract is preserved at the device level** — devices still
   produce `(12,)` native consumption; the **peak/non-peak split is applied by the model/rate
   layer** using the 24h load shapes, not pushed into every device.
4. **Revenue-neutral fallback.** A device/utility with no TOU data (peak == offpeak) reproduces
   the flat-rate cost — entire-US coverage degrades gracefully to flat pricing where URDB lacks
   a curated TOU tariff.
5. **Golden is intentionally re-baselined** in a dedicated commit, with the diff explained
   (this is the phase where output is *expected* to change).

---

## Work breakdown

### §0 — Core modeling flow (the dispatch engine)

This is the spine §1–§3 plug into. It makes the net-cost calculation transparent and auditable.

**Representative-day-per-month spine.** For each month *m* we build **one representative day**,
compute energy + cost, then multiply by days-in-month and sum over 12 months. This is required
because a battery (~13.5 kWh) only makes sense against a *daily* cycle, not a monthly kWh total.

**Three daily periods** (CA TOU has three meaningful ones, not two — solar generates in a
window that is mostly *off*-peak, which is what makes the battery valuable):

| Period | Typical hours | Role |
|---|---|---|
| **Solar window** | midday | solar serves load → charges battery → exports surplus |
| **Peak** | ~4–9pm | battery discharges to load → grid covers shortfall at **peak slab** |
| **Off-peak** | overnight/morning | grid serves load at **off-peak rate**; battery reserved for peak |

**How the inputs land in periods (per representative day in month m):**
- Each device's monthly kWh splits into the three periods via its 24-h **load shape**
  (`period_frac = Σ shape over that period's hours`).
- **HDD/CDD** (monthly) ÷ days-in-month → representative-day HVAC energy, distributed across
  hours by the `hvac_heat` / `hvac_cool` shapes.
- **Solar**: `daily_gen[m] = ac_monthly[m] / days`, placed into periods by the
  **intra-day solar shape** harvested in Phase 6 §3a.

**Dispatch waterfall** (locked decisions in brackets):
```
SOLAR WINDOW:  solar → load;  surplus → battery [charge from SOLAR ONLY];  remainder → export
PEAK:          battery → load (discharge);  shortfall → grid @ peak slab
OFF-PEAK:      grid → load @ off-peak;  [grid→battery arbitrage OFF by default]
               battery energy is RESERVED for peak (max bill savings)
```

**Locked decisions (Phase 7 kickoff):**
1. **Battery charges from solar only** — off-peak grid arbitrage is off by default (the dashed
   path); revisit only for battery-without-solar cases.
2. **3-period representative-day granularity** — not 24-h or 8760-h. Transparent and cheap;
   loses within-period timing detail (acceptable for an advocacy simulator).
3. **Solar placement uses the Phase 6 intra-day shape** — accurate solar-window vs peak-tail
   split per zone/month.

**Net cost assembly (electricity):**
```
net_elec = Σ_m days[m] × ( grid_peak_kWh[m]    × peak_rate (with SLABS on the monthly total)
                         + grid_offpeak_kWh[m] × offpeak_rate )
         − Σ_m days[m] ×   export_kWh[m]       × export_credit[m]
```
- **Slabs tier on the monthly grid-import total** (tier 1 → tier 2 …), a whole-home quantity —
  not per device, not per day.
- **Gas is separate and outside this engine:** `therms × single gas_rate`. No TOU, no battery,
  no solar interaction.

#### §0.1 — Per-device consumption vs. home-level cost (the seam)

What a device can and cannot "own" splits cleanly into three tiers:

1. **kWh is per-device, exact.** Every electric device carries a **3-way monthly split** of its
   kWh — solar-window / peak / off-peak — derived from its 24-h load shape
   (`period_frac = Σ shape over that period's hours`). No allocation, pure physics. (Gas
   devices carry monthly therms only — no period split.)
   - *3 buckets for the dispatch, 2 rates for the bill:* solar-window and off-peak grid import
     are both billed at the **off-peak rate**; the solar-window bucket is tracked separately
     only because solar/battery can serve it directly (overnight load can't get that).

2. **Gross cost is per-device only when nothing whole-home interferes.** With flat-per-period
   rates and no solar/battery, `cost = peak_kWh×peak_rate + offpeak_bucket_kWh×offpeak_rate` is
   an exact per-device number (the same effective-rate collapse the ACC loader does today).

3. **Net cost is HOME-level**, because **two whole-home effects** break per-device pricing:
   - **Tiered slabs** — the marginal tier depends on the *aggregate* monthly grid import. Which
     device's kWh sits in tier 2 has no physical answer; it depends on stacking order.
   - **Solar + battery credit** — self-consumption and battery discharge reduce grid import at
     the home level (the generalization of today's `solar_saving` line). Which device the
     credit "offset" is not physically defined.

   So the authoritative electricity bill is computed **once at the home level**: aggregate all
   devices' period kWh → run the §0 dispatch → apply slabs on the aggregate → subtract export
   credit.

#### §0.2 — Per-device dollar allocation for charts (presentation only)

When a chart needs "$ by device" or "$ by category", split the home net electricity bill back
to devices — **this changes no total, dispatch, or physics**. Convention:

> **Allocate the home net electricity bill in proportion to each device's gross period-priced
> grid cost** — i.e. its share of `Σ (peak_kWh×peak_rate + offpeak_bucket_kWh×offpeak_rate)`
> taken across all electric devices. Peak-heavy devices thus bear a larger share of both the
> slab premium and the solar/battery credit.

- Chosen over plain kWh-volume pro-rata because it keeps the peak-vs-off-peak cost signal (a
  device that runs at peak should carry more of the bill).
- **Known approximation:** it does not perfectly trace *which period* the solar/battery credit
  offset (the credit mostly lands on peak); for a category/device chart this is acceptable and
  the home total stays exact. Gas $ is unaffected (already per-device).
- Implementation: a single presentation helper, downstream of the model — never inside the
  dispatch or the bill.

### §1 — PVWatts solar generation (offline-baked monthly yield)

- **Data:** already harvested, validated, and committed in **Phase 6 §3a**
  (`data/solar/pvwatts_zones.json` — per-zone per-kW monthly yield + provenance). Phase 7
  *consumes* it; no re-harvest unless the curated zone list expands.
- **Model:** `SolarConfig.monthly_production_kwh()` = `system_kw × zone_yield[12]`. The Solar
  device now emits a real seasonal generation curve (summer-peaked).
- **Roof geometry:** apply `roof_tilt`/`roof_azimuth`/`array_type`/`module_type` as a
  correction on the default-orientation per-zone vector (analytical factor or a small baked
  orientation-adjustment table). `system_losses` scales output.
- **Validation:** annual sum of monthly yields ≈ today's `specific_yield` for CZ4 default
  orientation (sanity); CA coastal vs inland zones differ as expected (~1,400 vs ~1,650
  kWh/kW/yr).

### §2 — Battery charge/discharge physics

- **Replace flat `scf`** with a dispatch model over the home's load. Inputs:
  `battery_kwh` (usable capacity), round-trip efficiency, monthly generation (§1), and the
  home's monthly + peak/non-peak load (§3). Discharge preferentially offsets **peak** load;
  surplus generation that can't be stored is **exported**.
- Output the same history arrays (`solar_self_consumed_history`, `solar_exported_kwh_history`)
  but now physically derived. Self-consumption rises with battery size and with peak-aligned
  loads.
- Keep the model deterministic (no Monte Carlo — still deferred). Granularity is the **3-period
  representative-day** dispatch from §0 (solar-window / peak / off-peak), scaled by days-in-month
  — not 24-h or 8760-h. Battery charges from **solar only** and its stored energy is **reserved
  for peak**.

### §3 — Peak / non-peak consumption split + URDB TOU rates

- **Data:** the curated residential TOU tariffs (PG&E E-TOU-C / E-ELEC, SCE TOU-D, SDG&E …)
  were fetched, parsed into the simplified `{peak_rate, offpeak_rate, peak_hours, tiers}`
  schema, and validated in **Phase 6 §3b** (`data/rates/urdb_tou.json`). Phase 7 consumes it;
  expand the curated list (toward full US) as needed.
- **Consumption split:** reuse `data/rates/device_load_shapes.json` 24h profiles —
  `peak_fraction[device] = Σ(profile over peak hours)`; `peak_kWh = monthly_kWh × peak_fraction`,
  `offpeak_kWh = remainder`. This is the existing ACC hourly machinery repurposed (already does
  `dot(profile_24h, shape_24h)`), so no new per-device data is needed.
- **Pricing:** introduce `get_peak_offpeak_rates()` on the rate layer, returning real split
  rates from URDB; apply tiered slabs against the split kWh. Utilities/loaders without TOU data
  implement it as a single-period passthrough (peak == offpeak). Solar generation (§1) and
  battery discharge (§2) reduce the **peak** load first.
- **Coverage fallback:** utilities without a curated TOU tariff use a single-period
  (peak == offpeak) URDB or the existing EIA flat rate — keeps full-US coverage working.

### §4 — UI / charts / outputs

- New/updated charts: monthly solar generation curve; peak vs non-peak consumption + cost
  split; battery self-consumption vs export. Update Help (`solar.html`, rate help) to describe
  the new model.
- Home Profile roof-geometry inputs (inert in P6) become **live**.
- Rate-model selector gains a **URDB TOU** option alongside today's EIA/ACC/CAGR modes.

---

## Module / data deltas (Phase 7 target state)

```
src/
  journey.py            SolarConfig → monthly yield; BatteryConfig → dispatch physics
  rate_loader.py        URDBRateLoader (peak/non-peak + slabs); get_peak_offpeak_rates real
  model.py              wire peak/non-peak split + solar/battery reduction order
  ui/sim.py, panels.py  roof geometry live; URDB TOU rate-model option
  ui/charts.py          solar-monthly / peak-offpeak / battery-dispatch charts
data/
  solar/pvwatts_zones.json     (from Phase 6) now CONSUMED by SolarConfig
  rates/urdb_tou.json          (from Phase 6) now CONSUMED by URDBRateLoader
  (curated lists may expand toward full-US coverage; re-run the Phase 6 build scripts)
scripts/
  build_pvwatts.py / build_urdb.py   (from Phase 6; re-run only to add zones/tariffs)
tests/
  test_solar_pvwatts.py (NEW) monthly yield, orientation correction, coverage
  test_battery.py       (NEW) dispatch physics, self-consumption vs export
  test_urdb_rates.py    (NEW) schedule parse, slab pricing, peak/offpeak split
  regression/golden.json  re-baselined (output changes intentionally)
```

## Resolved at kickoff (see §0)

- ✅ Battery dispatch fidelity → **3-period representative-day**, scaled by days-in-month.
- ✅ Battery charge source → **solar only**; stored energy reserved for peak.
- ✅ Tiered slabs → apply on the **monthly grid-import total** (billing-accurate).
- ✅ Solar placement into periods → **Phase 6 intra-day shape** (PVWatts hourly).
- ✅ Per-device $ allocation for charts → **gross period-priced grid-cost share** (§0.2).

## Still open (resolve during Phase 7)

- URDB tariff curation list beyond CA, and how the rate-model selector maps ZIP → tariff.
- Orientation correction: analytical factor vs a small baked tilt/azimuth adjustment table.
- Round-trip efficiency value + whether a battery charge-rate (kW) cap matters at this grain.

## Definition of done

- [ ] PVWatts per-zone monthly yields baked + committed with provenance; Solar device emits (12,).
- [ ] Battery dispatch physics produce self-consumption/export from real load.
- [ ] URDB TOU peak/non-peak + slabs baked; consumption split via 24h shapes; pricing applied.
- [ ] CA validated first; out-of-CA degrades gracefully to flat pricing.
- [ ] Golden re-baselined with documented diff; full `pytest` green.
- [ ] Charts + Help updated; roof geometry live.
- [ ] CLAUDE.md updated: Phase 7 closed.
