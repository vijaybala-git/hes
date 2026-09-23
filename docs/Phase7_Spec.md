# WhyWatt — Phase 7 Development Spec

**Status:** 🔵 PLANNED — the data-pipeline + golden-rebaseline phase. Flow new simulation data
through the model, and adopt the CEC projected-rate escalation as the default.
**Follows:** Phase 6 (`docs/Phase6_Spec.md`) — Solar/Battery split, inert roof-geometry inputs, and
the **non-default `cec_projection` rate hand-off interface** (evaluated but not switched). Offline
PVWatts/URDB data is harvested and validated separately in `docs/OfflineSolarData_Plan.md`.
**Last updated:** 2026-09-22 — folded the URDB interface contract into §3 (`RateStructure` +
`period_fractions`/`price_month`, coverage gate, ZIP→baseline crosswalk; offline half DONE per
`OfflineURDB_Plan.md`) and added §5.1 (projection scoped to PG&E; SCE/SDG&E escalate on EIA Pacific
until their projection markets are harvested post-P7). Prior: 2026-09-07 reconciled with the Phase 6
collapse (added §5). Original plan: 2026-06-23.

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
  **intra-day solar shape** harvested in `OfflineSolarData_Plan.md` §4a.

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
3. **Solar placement uses the offline intra-day shape** (`OfflineSolarData_Plan.md` §4a) —
   accurate solar-window vs peak-tail split per zone/month.

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

- **Data:** already harvested, validated, and committed in `OfflineSolarData_Plan.md` §4a
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

> **The offline half is DONE** and committed (`docs/OfflineURDB_Plan.md`, branch
> `feat/urdb-offline-harvest`). CA's three IOUs (PG&E, SCE, SDG&E) are harvested — 19 flagship
> plans, TOU defaults, real per-tariff peak windows, per-territory baselines — plus the coverage
> gate and the ZIP→baseline crosswalk. Phase 7 is now **only the sim-side wiring** against the
> interface below (folded here from `OfflineURDB_Plan.md` §5). **URDB is electricity only — gas
> stays on the EIA path** (`therms × single gas_rate`, no TOU, §0).

**The interface — a source-agnostic `RateStructure`, two methods (§0.1 seam).** The sim codes
against Layer 2 (the normalized structure), never against raw URDB. URDB is the first producer; the
EIA-flat fallback emits the *same* object.

```python
class URDBRateStructure:                       # rate_loader.py
    @classmethod
    def for_utility(cls, eiaid, tariff_label=None) -> "URDBRateStructure":
        # tariff_label=None -> utilities[eiaid].default_label (the whywatt_default, a TOU plan)

    def period_fractions(self, month, load_shape_24h) -> dict:   # per-device, pure geometry, no $
        # {"peak": Σ shape over THIS tariff's peak_hours, "offpeak": remainder}

    def price_month(self, month, peak_kwh, offpeak_kwh) -> float:  # called ONCE on the home aggregate
        # walk daily-baseline tiers on the monthly total (max_kwh_day × days_in_month), split each
        # tier's kWh peak/off-peak in proportion, price at that tier's peak/off-peak rate, + fixed charge
```
- **Consumption split** uses each tariff's **real `peak_hours`** (4–9pm, 5–8pm, EV windows all
  differ — baked per tariff) dotted with `data/rates/device_load_shapes.json` — the existing ACC
  hourly machinery. Per device, no dollars, so tiers/solar can't leak into a device.
- **Pricing** (`price_month`) is the only place tiers apply, and runs **once on the home aggregate**
  (the marginal tier depends on total home import, §0.1). Solar (§1) + battery (§2) reduce the
  **peak** bucket first. Per-device $ for charts comes from the §0.2 allocation helper.
- A **flat tariff** (`is_tou:false` — e.g. tiered legacy E-1) has empty `peak_hours` and
  `peak==offpeak`, so it collapses to the revenue-neutral flat case (Invariant 4).

**Level + daily + seasonality all come from URDB; ACC is NOT applied on this path.** The URDB
`by_month` structure already carries seasonal (summer/winter) rates, so multiplying by the ACC
monthly shape would double-count. ACC is **retained** as its own selectable rate mode and for the
flat-EIA fallback + NEM export, but the URDB retail path uses `urdb_rate × escalation(year)` only
(escalation from §5). Tier **thresholds (kWh) do not escalate**; only $/kWh does.

**Baseline territory (per-ZIP tier threshold).** `price_month`'s tier cutoff is the utility's
baseline allowance, which varies by climate territory (PG&E 5.9–19.2 kWh/day). Resolve it
`ZIP → CEC climate zone → territory → kWh/day` via `data/rates/urdb_baseline_crosswalk.json` +
`region_baselines` in `urdb_tou.json` (SDG&E exact, PG&E approximate; SCE's TOU default is flat, no
baseline). Rates are territory-invariant; only the allowance moves.

**Coverage gate + fallback ladder ("can we USE a URDB rate?").** `for_utility(eiaid)` consults
`data/rates/urdb_coverage.json` (OpenEI's ~114 annually-maintained utilities):
- maintained **and** harvested → the URDB TOU structure (`whywatt_default` or the chosen label);
- maintained but not harvested (`harvest_candidate`) → **flat** structure from the EIA per-utility rate;
- not maintained, or ZIP unresolved → **flat** structure (EIA per-utility, else CA average).
Flat = `peak==offpeak`, one tier, with ACC restoring seasonality. No path throws.

**ZIP → tariff picker.** Entering a ZIP resolves the utility and offers its `tariffs{}` set (grouped
by `plan_kind`, legacy plans flagged) with the TOU default pre-selected; the sim rebuilds the
`URDBRateStructure` for the chosen label. Both scenarios ("do nothing"/"your journey") price on the
selected tariff.

### §4 — UI / charts / outputs

- New/updated charts: monthly solar generation curve; peak vs non-peak consumption + cost
  split; battery self-consumption vs export. Update Help (`solar.html`, rate help) to describe
  the new model.
- Home Profile roof-geometry inputs (inert in P6) become **live**.
- Rate-model selector gains a **URDB TOU** option alongside today's EIA/ACC/CAGR modes and the
  `cec_projection` option added (non-default) in Phase 6 — which §5 now promotes to the default.
- **Plan-button consolidation (Spec 5.6 #6)** lands here, alongside the Solar/Battery/Panel UI
  work, when a unified plan-row can be coherent (it was deferred from 5.6 for exactly this moment).

---

### §5 — Adopt the CEC projected-rate escalation as the default (Phase 6 WS1 → live)

Phase 6 built `cec_projection` as a **non-default** rate model (a `ProjectedRateSource` reading
`data/rates/projection/whywatt_rate_projection.json`) and produced a difference evaluation
(`notebooks/rate_switch_review.ipynb`) quantifying what switching would change. Phase 7 makes the
switch.

This is a **separate rate axis from §3** and can be its own commit + its own golden re-baseline:
§3 changes the rate *structure* (adds the peak/non-peak TOU dimension); §5 changes the rate
*escalation* (today's single CAGR → the CEC-driven trajectory: electricity real-flat, gas spiral).
Sequence them independently so each golden diff is attributable to one cause.

- **Default switch.** Flip the factory defaults in `data/config/whywatt_default.json` from
  `cagr_flat` to `cec_projection` (per fuel / scenario slot), guided by the Phase 6 evaluation.
- **Extend the scope beyond retail.** Phase 6 fed only retail `get_rate`. Phase 7 decides whether
  the projection also drives the **NEM export path** (`get_nem3_export_rates`, which today consumes
  ACC × CAGR) and the **time-varying social overlay** (`social_cost.py`, today a flat $1.07/therm).
  Each extension is an intentional, separately-baselined output change.
- **Golden re-baseline** with the diff explained — the escalation change is expected to move
  numbers materially (Invariant 5).
- **Gas social overlay.** The gas carbon/methane/health layer the projection deliberately left to
  the live sim (`OfflineRateProjection_Plan.md` §8c) is applied here; the CO₂/methane params are
  already harvested in `data/rates/projection/acc_marginal_gas.json`.

#### §5.1 — Projection coverage: PG&E full at end of P7; SCE/SDG&E projection deferred (DECIDED)

The rate *structure* (§3, URDB) covers all three CA IOUs, but the rate *projection* bundle
(`whywatt_rate_projection.json`) currently has **only the `CA_PGE` market** — and building a market
requires the offline "Rate Projections" harvest, which includes a **manual spreadsheet edit** step.
So Phase 7 scopes projection to PG&E and defers SCE/SDG&E:

- **PG&E area:** full pipeline — URDB starting rate (§3) escalated by the `cec_projection`/Moderate
  trajectory (the `CA_PGE` market). This is the "fully working" end-state for Phase 7.
- **SCE / SDG&E (and any non-PG&E CA ZIP):** the URDB **starting rate still applies** (structure works
  CA-wide), but there is no per-utility projection yet, so the escalation **falls back to the
  `EIA AEO Pacific` trajectory** (already in the bundle's benchmarks). Utility-specific starting
  level, generic Pacific escalation.
- **Post-Phase-7 effort (separate validation):** extend the offline rate-projection harvest with
  `CA_SCE` and `CA_SDGE` markets (the manual-spreadsheet flow), then flip those ZIPs off the EIA
  Pacific fallback. Tracked as its own validation task, not gating Phase 7 close.

**Design for whole-CA now.** The projection hand-off is **market-keyed** (the bundle already is;
`ProjectedRateSource` selects a market): resolve `eiaid → market` (`14328→CA_PGE`,
`17609→CA_SCE`, `16609→CA_SDGE`), and when the market is absent, use the `eia_pacific` benchmark as
the escalation. Adding SCE/SDG&E later is then a **data drop** (new markets), no code change — the
selector and the EIA-Pacific fallback are built once, now.

**Acceptance (§5):** `cec_projection` is the PG&E default; non-PG&E CA ZIPs escalate on EIA Pacific
via the market selector; the golden is re-baselined in a dedicated commit whose diff matches the
Phase 6 evaluation; NEM/social extension decisions are recorded.

---

## Module / data deltas (Phase 7 target state)

```
src/
  journey.py            SolarConfig → monthly yield; BatteryConfig → dispatch physics
  rate_loader.py        URDBRateStructure.for_utility / period_fractions / price_month (§3);
                        coverage gate (urdb/harvest_candidate/eia_fallback) + baseline resolver
  projected_rate_source.py  market selector: eiaid → market, EIA-Pacific fallback for non-PG&E (§5.1)
  model.py              wire peak/non-peak split + solar/battery reduction order; home-level bill
  ui/sim.py, panels.py  roof geometry live; URDB TOU rate-model option + per-utility tariff picker
  ui/charts.py          solar-monthly / peak-offpeak / battery-dispatch charts
  data/config/whywatt_default.json   default rate model cagr_flat → cec_projection (§5)
data/
  solar/pvwatts_zones.json     (from OfflineSolarData_Plan) now CONSUMED by SolarConfig
  rates/urdb_tou.json          (from OfflineURDB_Plan, DONE) now CONSUMED by URDBRateStructure
  rates/urdb_coverage.json     (from OfflineURDB_Plan, DONE) the "can we use URDB?" gate
  rates/urdb_baseline_crosswalk.json (from OfflineURDB_Plan, DONE) ZIP→territory baselines
  rates/projection/whywatt_rate_projection.json  now the DEFAULT rate source (§5); CA_PGE only —
                        add CA_SCE/CA_SDGE markets post-P7 (§5.1)
scripts/
  build_urdb*.py / build_baseline_crosswalk.py  (OfflineURDB, DONE; re-run to add utilities)
tests/
  test_solar_pvwatts.py (NEW) monthly yield, orientation correction, coverage
  test_battery.py       (NEW) dispatch physics, self-consumption vs export
  test_urdb_rates.py    (NEW) URDBRateStructure: period_fractions + price_month + tier slabs + fallback
  regression/golden.json  re-baselined (output changes intentionally)
```

## Resolved at kickoff (see §0)

- ✅ Battery dispatch fidelity → **3-period representative-day**, scaled by days-in-month.
- ✅ Battery charge source → **solar only**; stored energy reserved for peak.
- ✅ Tiered slabs → apply on the **monthly grid-import total** (billing-accurate).
- ✅ Solar placement into periods → **offline intra-day shape** (PVWatts hourly, `OfflineSolarData_Plan.md` §4a).
- ✅ Per-device $ allocation for charts → **gross period-priced grid-cost share** (§0.2).
- ✅ URDB interface → **`RateStructure` + `period_fractions`/`price_month`**, coverage gate + baseline
  crosswalk (offline DONE, §3); rate-model selector maps ZIP → utility → tariff picker.
- ✅ Projection coverage → **PG&E full; SCE/SDG&E escalate on EIA Pacific** via the market selector
  until their projection markets are harvested post-P7 (§5.1).

## Still open (resolve during Phase 7)

- Orientation correction: analytical factor vs a small baked tilt/azimuth adjustment table.
- Round-trip efficiency value + whether a battery charge-rate (kW) cap matters at this grain.
- Mid-day "super-off-peak" period (SCE/SDG&E) is folded into off-peak by the 2-rate model — confirm
  acceptable, or extend to 3 billing periods later.

## Post-Phase-7 (separate efforts, not gating close)

- **SCE/SDG&E rate-projection markets** — extend the offline "Rate Projections" harvest (manual
  spreadsheet step) with `CA_SCE`/`CA_SDGE`, then flip those ZIPs off the EIA-Pacific fallback (§5.1).
- URDB coverage beyond CA (national ZIP crosswalk + harvest of maintained utilities).

## Definition of done

- [ ] PVWatts per-zone monthly yields baked + committed with provenance; Solar device emits (12,).
- [ ] Battery dispatch physics produce self-consumption/export from real load.
- [ ] URDB `RateStructure` consumed: `period_fractions` split via real per-tariff peak hours,
      `price_month` slabs on the home aggregate, coverage gate + ZIP→baseline resolved (offline DONE).
- [ ] **PG&E area fully working** end-to-end (URDB rate × `cec_projection`); SCE/SDG&E use URDB rates
      with **EIA-Pacific escalation** via the market selector (§5.1); all CA ZIPs degrade gracefully.
- [ ] `cec_projection` promoted to the default rate model for PG&E (§5); NEM/social extension recorded.
- [ ] Golden re-baselined with documented diff — escalation switch (§5) and TOU structure (§3) as
      separate, attributable commits; full `pytest` green.
- [ ] Charts + Help updated; roof geometry live.
- [ ] CLAUDE.md updated: Phase 7 closed.
