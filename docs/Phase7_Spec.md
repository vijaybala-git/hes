# WhyWatt — Phase 7 Development Spec

**Status:** 🔵 PLANNED — the data-pipeline + golden-rebaseline phase. Flow new simulation data
through the model, and adopt the CEC projected-rate escalation as the default.
**Follows:** Phase 6 (`docs/Phase6_Spec.md`) — Solar/Battery split, inert roof-geometry inputs, and
the **non-default `cec_projection` rate hand-off interface** (evaluated but not switched). Offline
PVWatts/URDB data is harvested and validated separately in `docs/OfflineSolarData_Plan.md`.
**Last updated:** 2026-09-22 — solar **simulation interface** decided: `SolarResourceLoader` →
`SolarResource` (clock time) as `HomeConfig.solar_resource`, `SolarConfig` = user choices only (§1);
`scf` retired for an **hourly Solar → Battery → Utility energy balance** with export of excess (§0,
§2 — revises two kickoff decisions: 3-period → hourly, reserved-for-peak → greedy); landing as
three commits A/B/C. Earlier 2026-09-22: §1 re-scoped to **per-ZIP** PVWatts yield at a single default
orientation, harvested by CCA region; scalar `specific_yield` retired (roof geometry stays inert) per the revised
`OfflineSolarData_Plan.md`. Earlier 2026-09-22: folded the URDB interface contract into §3 (`RateStructure` +
`period_fractions`/`price_month`, coverage gate, ZIP→baseline crosswalk; offline half DONE per
`OfflineURDB_Plan.md`) and added §5.1 (projection scoped to PG&E; SCE/SDG&E escalate on EIA Pacific
until their projection markets are harvested post-P7). Prior: 2026-09-07 reconciled with the Phase 6
collapse (added §5). Original plan: 2026-06-23.

---

## Goal

Replace the simplified placeholders Phase 6 left in place with **real, offline-baked
simulation data** from two new sources, and add a **peak / non-peak** dimension to consumption
and pricing:

1. **Solar generation from PVWatts** — per-ZIP monthly per-kW yield vectors (zone fallback)
   replace the scalar `specific_yield`. The Solar device emits a **(12,) monthly generation array**.
2. **Battery charge physics** — a real charge/discharge model self-consumes generation against
   the home's load instead of a flat `scf` fraction: load is served Solar → Battery → Utility,
   excess solar is exported, and self-consumption becomes an output (§0, §2).
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
| Solar production | `system_kw × specific_yield` (scalar/yr) | `system_kw × pvwatts_monthly_yield[12]` (per ZIP, zone fallback) |
| Roof geometry | carried, inert | **still inert** — default orientation (tilt 20°, south); correction deferred |
| Self-consumption | flat `scf` fraction (user slider) | **output** of an hourly Solar → Battery → Utility energy balance; `scf` retired |
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

**Representative-day-per-month spine.** For each month *m* we build **one representative day**
of **24 clock hours**, run the energy balance hour by hour, then multiply by days-in-month and sum
over 12 months (12 × 24 = 288 steps per simulated year). This is required because a battery
(~13.5 kWh) only makes sense against a *daily* cycle, not a monthly kWh total.

**Three sources, one fixed order (revised 2026-09-22 — replaces the flat `scf`).** Load is served
**Solar → Battery → Utility**; solar in excess of load charges the battery, and whatever the
battery cannot take is **exported**:

```
for each month m, representative day, clock hour h = 0..23:
  G[h] = system_kw × ac_monthly[m] / days[m] × shape_clock[m][h]      # solar generation (§1)
  L[h] = Σ_devices kWh[m] / days[m] × load_shape_d[h]                  # home electric load
  direct    = min(G[h], L[h])                                          # 1. solar → load
  surplus   = G[h] − direct ;  deficit = L[h] − direct
  charge    = min(surplus, (cap − soc) / √η, p_max)                    #    solar → battery
  soc      += charge × √η
  export    = surplus − charge                                         #    excess → grid
  discharge = min(deficit, soc × √η, p_max)                            # 2. battery → load
  soc      -= discharge / √η
  grid      = deficit − discharge                                      # 3. utility → load
```
- **Steady state:** the representative day is run twice and the second pass is kept, so the
  battery's start-of-day charge equals its end-of-day charge (no free energy from an initial SOC).
- **Battery parameters:** `cap = battery_kwh` (usable), `η` = round-trip efficiency (default 0.90,
  split √η on charge and discharge), `p_max` = charge/discharge power cap (default 5 kW —
  Powerwall-class). No battery → `cap = 0`, and the balance reduces to solar → load → export.
- **Outputs per month:** `direct`, `discharge`, `export`, `grid[h]` (24-vector). `grid[h]` is
  what §3 prices; `export` is what earns the NEM credit.

**Locked decisions (Phase 7 kickoff, revised 2026-09-22):**
1. **Battery charges from solar only** — no grid→battery arbitrage (revisit only for
   battery-without-solar cases).
2. **Hourly representative day** (24 clock hours × 12 months) — *replaces* the original
   3-period granularity. Both inputs are already hourly (the 24-h device load shapes and the
   PVWatts 12×24 solar shape), so collapsing to 3 periods only threw information away.
3. **Greedy self-consumption order Solar → Battery → Utility** — *replaces* "battery reserved for
   peak". The battery discharges whenever solar falls short, which in practice is the evening
   4–9pm peak first (matches a home battery's default self-powered mode). A peak-reserve /
   TOU-arbitrage mode is a possible later option, not Phase 7.
4. **Solar placement uses the offline intra-day shape** (`OfflineSolarData_Plan.md` §4b),
   converted to clock time once by the loader (§1).

**Net cost assembly (electricity):**
```
grid_peak_kWh[m]    = days[m] × Σ_{h ∈ tariff.peak_hours[m]} grid[m][h]
grid_offpeak_kWh[m] = days[m] × Σ_{h ∉ tariff.peak_hours[m]} grid[m][h]
net_elec = Σ_m price_month(m, grid_peak_kWh[m], grid_offpeak_kWh[m])   # SLABS on the monthly total (§3)
         − Σ_m days[m] × export[m] × export_credit[m]
```
- **Slabs tier on the monthly grid-import total** (tier 1 → tier 2 …), a whole-home quantity —
  not per device, not per day.
- **Gas is separate and outside this engine:** `therms × single gas_rate`. No TOU, no battery,
  no solar interaction.

#### §0.1 — Per-device consumption vs. home-level cost (the seam)

What a device can and cannot "own" splits cleanly into three tiers:

1. **kWh is per-device, exact.** Every electric device's monthly kWh is spread over the 24 clock
   hours of the representative day by its 24-h load shape (`data/rates/device_load_shapes.json`).
   No allocation, pure physics. (Gas devices carry monthly therms only — no hourly split.) The
   home load `L[h]` in §0 is the sum over devices.

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

### §1 — PVWatts solar generation (offline-baked per-ZIP yield)

- **Data:** harvested, validated, and committed per `OfflineSolarData_Plan.md`
  (`data/solar/pvwatts_zip.json` — per-site per-kW `ac_monthly[12]` + 12×24 `intraday_shape`,
  default orientation, provenance). Built up region by region (SVCE → PCE + SJCE → …); Phase 7
  *consumes* whatever waves exist. No runtime network.
- **Resolution — always a table, never a scalar:** `zips[zip].site` (harvested region), else the
  ZIP's CEC-zone station table (`zones[zone].site`, all 16 baked in wave 0), else the CZ4 default
  table. Never throws; the resolved level (`zip` / `zone` / `default`) is surfaced for display.
  **No address is ever collected.**
- **The interface (decided 2026-09-22).** Location data and user choices are kept apart:

  ```
  data/solar/pvwatts_zip.json        baked, committed; _meta.schema_version checked at load
          │  read once per process
          ▼
  SolarResourceLoader                src/solar_loader.py — module singleton (like _CLIMATE_LOADER);
          │  .resolve(zip)           ZIP → zone → default; validates shapes; converts to clock time
          ▼
  SolarResource  (frozen)            location data only — never user-edited, never serialized
          │
  HomeConfig.solar_resource          derived read-only property from zip_code (like climate_zone);
          │                          not a dataclass field → never in share links / saved configs
          ▼
  JourneyHome solar step             production[m] = SolarConfig.system_kw × resource.ac_monthly[m]
  ```

  ```python
  @dataclass(frozen=True)
  class SolarResource:
      ac_monthly:     np.ndarray  # (12,)   kWh AC per kW DC
      intraday_shape: np.ndarray  # (12,24) CLOCK time (Mar–Oct shifted +1 h for DST); rows sum to 1
      level:    str               # "zip" | "zone" | "default"
      zip_code: str; zone_key: str; site_key: str
      label:    str               # "PVWatts · ZIP 94040" | "PVWatts · CZ4 zone estimate"
      source:   str               # "PVWatts v8 · NSRDB tmy-2020 · built 2026-09-22"
      @property
      def ac_annual(self) -> float: ...
  ```
  - **`SolarConfig` holds user choices only** (panels, kW/panel, NEM mode, NBC) — it is what share
    links and saved configs carry. `specific_yield` and `scf` both leave it (§1, §2).
  - **`HomeConfig.solar_resource`** is the single place the home's location becomes solar data
    (Hard rule 6). It is a property, not a field: always consistent with `zip_code`, never
    persisted. Devices still never read files (Hard rule 2) — only the loader does.
  - **Clock time is applied once, in the loader.** The file keeps PVWatts' native local standard
    time; the loader shifts March–October by +1 h so every consumer (dispatch, URDB peak hours,
    charts) sees the same clock hours. Month-level DST approximation, same as the review notebook.
  - **Missing/corrupt file or unknown `schema_version` is a hard error** (the file is committed;
    a gap is a bug, caught by tests). Unknown/out-of-state ZIPs are *not* errors → `level="default"`.
- **Model:** production `(12,)` = `system_kw × ac_monthly` (**monthly variation**), with
  `system_kw = panels × kw_per_panel`. `intraday_shape` (**daily variation**) spreads each month's
  generation over the §0 representative day.
- **Retire `specific_yield` / `solar_specific_yield` entirely** — no scalar default, no per-home
  override. Remove it from `SolarConfig` + `SolarBatteryConfig` (`src/journey.py`, incl. the
  `system_kw × specific_yield` production line), `src/ui/state.py`, `config.py` bounds,
  `panels.py` (the yield input + the "annual kWh" estimate, which now reads Σ `ac_monthly`),
  `layout.py`, `sim.py`, and `data/config/whywatt_default.json`. Old share links / saved configs
  carrying `solar_specific_yield` are **ignored** (dropped on load, not an error). The UI shows the
  resolved yield read-only: *"≈ 1,5xx kWh/kW/yr — PVWatts, ZIP 95014"* (or *"… zone CZ4
  estimate"* when on fallback).
- **Tests to rework:** `tests/test_journey.py` (`SolarBatteryConfig` round-trips that pass
  `specific_yield=1650.0`) and regression offset `tests/regression/offsets/04__sunnier_site.json`
  (`solar_specific_yield: 1700`) — re-express "sunnier site" as a **ZIP change** to a sunnier
  zone (e.g., an inland/desert ZIP resolving to its zone-station table).
- **Roof geometry:** stays **inert** (single default orientation: fixed roof, tilt 20°,
  azimuth 180°, 14% losses). Orientation correction is deferred past Phase 7 — the advocacy
  message ("even ~4 kW + battery is a big win") does not depend on it.
- **Validation:** CZ4 default table annual in 1,500–1,750 (wave 0 measured **1,644** — the retired
  1,500 under-stated San José by ~10%, so expect solar savings to rise in the golden re-baseline);
  zone range 1,350 (Arcata) – 1,840 (China Lake) kWh/kW/yr; `grep -rn specific_yield
  src/ data/ tests/` returns zero.

### §2 — Battery charge/discharge physics

- **Retire `scf` (the self-consumption fraction) entirely.** It was a stand-in for physics we now
  have: with three sources consumed in order **Solar → Battery → Utility** and excess exported
  (§0), self-consumption is an *output*, not an input. Remove `SolarConfig.scf`, the UI "Self-use"
  slider and its 80/35 battery snap (`src/ui/panels.py`, `state.py`, `config.py`, `layout.py`,
  `sim.py`), and `solar_scf` from `whywatt_default.json`; stale share-link values are dropped.
- **Battery config becomes live physics:** `BatteryConfig(battery_enabled, battery_kwh,
  round_trip_eff=0.90, power_kw=5.0)`. `battery_enabled=False` ⇒ `cap = 0`. The
  `SolarBatteryConfig` shim is retired; `HESModel` takes `SolarConfig` + `BatteryConfig` directly.
- **Outputs** keep the existing history arrays, now physically derived and reported as an
  energy balance that closes exactly:
  `production = solar_direct + battery_charge + export` and
  `load = solar_direct + battery_discharge + grid_import`, with
  `battery_discharge = battery_charge × η` (steady state). `solar_self_consumed_history` =
  `solar_direct + battery_discharge`; self-consumption rises with battery size and with
  evening-heavy load.
- Deterministic (no Monte Carlo). Granularity and order are §0's hourly representative day.

### Landing sequence — three commits, one golden-baseline diff each (decided 2026-09-22)

| Commit | Change | Golden diff attributable to |
|---|---|---|
| **A — data source** | `SolarResourceLoader` + `HomeConfig.solar_resource`; `specific_yield` retired; production = `system_kw × Σ ac_monthly`, still priced with today's annual-average rates and today's `scf` | ZIP-specific yield only (CZ4 ≈ +10%: 1,644 vs 1,500) |
| **B — monthly pricing** | production `(12,)` × monthly retail / export rates; `scf` still applied per month | seasonal alignment (summer-heavy solar × summer rates) |
| **C — energy balance** | §0 hourly Solar → Battery → Utility dispatch; `scf` retired; battery physics live | self-consumption from physics + battery |

`scf` survives A and B *on purpose*, so neither diff mixes in the dispatch change. §3 (URDB TOU
pricing of `grid[h]`) and §5 (escalation) land after C as their own commits.

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
  (the marginal tier depends on total home import, §0.1). It prices the **post-dispatch** hourly
  grid import `grid[h]` from §0 — solar and battery have already reduced load hour by hour, so
  whichever hours they cover (mostly the evening peak, for the battery) drop out of the bill
  naturally. Per-device $ for charts comes from the §0.2 allocation helper.
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
- Home Profile roof-geometry inputs **remain inert** (default orientation, §1). The yield field
  shows the ZIP's PVWatts annual and its source (ZIP / zone fallback), read from
  `HomeConfig.solar_resource`.
- **Solar/Battery panel:** the "Self-use" slider (`scf`) and its 80/35 battery snap are removed;
  self-consumption is now *reported* (from the §0 balance), not entered. Battery inputs are size
  (kWh) and on/off, with round-trip efficiency and power cap under Details.
- New energy-balance readout / chart per year: solar → home, solar → battery → home, export,
  grid import (the four flows of §0).
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
  solar_loader.py       (NEW) SolarResourceLoader + SolarResource — ZIP → zone → default, clock time
  home_config.py        HomeConfig.solar_resource (derived property from zip_code; not serialized)
  journey.py            SolarConfig = user choices only (no specific_yield, no scf);
                        BatteryConfig live (round_trip_eff, power_kw); SolarBatteryConfig retired;
                        hourly representative-day energy balance (§0)
  rate_loader.py        URDBRateStructure.for_utility / period_fractions / price_month (§3);
                        coverage gate (urdb/harvest_candidate/eia_fallback) + baseline resolver
  projected_rate_source.py  market selector: eiaid → market, EIA-Pacific fallback for non-PG&E (§5.1)
  model.py              wire peak/non-peak split + solar/battery reduction order; home-level bill
  ui/sim.py, panels.py  roof geometry live; URDB TOU rate-model option + per-utility tariff picker
  ui/charts.py          solar-monthly / peak-offpeak / battery-dispatch charts
  data/config/whywatt_default.json   default rate model cagr_flat → cec_projection (§5)
data/
  solar/pvwatts_zip.json       (from OfflineSolarData_Plan) now CONSUMED via SolarResourceLoader
  rates/urdb_tou.json          (from OfflineURDB_Plan, DONE) now CONSUMED by URDBRateStructure
  rates/urdb_coverage.json     (from OfflineURDB_Plan, DONE) the "can we use URDB?" gate
  rates/urdb_baseline_crosswalk.json (from OfflineURDB_Plan, DONE) ZIP→territory baselines
  rates/projection/whywatt_rate_projection.json  now the DEFAULT rate source (§5); CA_PGE only —
                        add CA_SCE/CA_SDGE markets post-P7 (§5.1)
scripts/
  build_urdb*.py / build_baseline_crosswalk.py  (OfflineURDB, DONE; re-run to add utilities)
tests/
  test_solar_loader.py  (NEW) ZIP→zone→default, schema_version gate, clock-time shift (rows still
                        sum to 1; July output moves +1 h, Jan does not), production = system_kw×ac_annual,
                        two ZIPs → two different model outputs, no-scalar grep gate
  test_battery.py       (NEW) energy balance closes exactly (production & load identities), steady-state
                        SOC, cap=0 ⇒ solar→load→export only, power cap binds, η losses = charge×(1−η)
  test_urdb_rates.py    (NEW) URDBRateStructure: period_fractions + price_month + tier slabs + fallback
  regression/golden.json  re-baselined (output changes intentionally)
```

## Resolved at kickoff (see §0)

- ✅ Battery dispatch fidelity → **hourly representative day** (24 clock h × 12 months), scaled by
  days-in-month — *revised 2026-09-22 from 3-period*.
- ✅ Consumption order → **Solar → Battery → Utility**, excess solar exported; `scf` retired —
  *revised 2026-09-22 from "battery reserved for peak"*.
- ✅ Battery charge source → **solar only** (no grid arbitrage).
- ✅ Solar data interface → `SolarResourceLoader` → `SolarResource` (frozen, clock time) exposed as
  `HomeConfig.solar_resource`; `SolarConfig` = user choices only (§1).
- ✅ Landing → **three commits A/B/C**, one golden diff each (§2 landing sequence).
- ✅ Tiered slabs → apply on the **monthly grid-import total** (billing-accurate).
- ✅ Solar placement into periods → **offline intra-day shape** (PVWatts hourly, `OfflineSolarData_Plan.md` §4b).
- ✅ Solar geo granularity → **per ZIP** (ZCTA centroid), zone-station fallback; no address, no
  live API. Orientation correction → **deferred** (default orientation). Scalar `specific_yield` → **retired**.
- ✅ Per-device $ allocation for charts → **gross period-priced grid-cost share** (§0.2).
- ✅ URDB interface → **`RateStructure` + `period_fractions`/`price_month`**, coverage gate + baseline
  crosswalk (offline DONE, §3); rate-model selector maps ZIP → utility → tariff picker.
- ✅ Projection coverage → **PG&E full; SCE/SDG&E escalate on EIA Pacific** via the market selector
  until their projection markets are harvested post-P7 (§5.1).

## Still open (resolve during Phase 7)

- Confirm battery defaults (round-trip 0.90, 5 kW power cap) against a current spec sheet; the
  hourly grain makes the power cap meaningful, so it stays in the model.
- Mid-day "super-off-peak" period (SCE/SDG&E) is folded into off-peak by the 2-rate model — confirm
  acceptable, or extend to 3 billing periods later.

## Post-Phase-7 (separate efforts, not gating close)

- **SCE/SDG&E rate-projection markets** — extend the offline "Rate Projections" harvest (manual
  spreadsheet step) with `CA_SCE`/`CA_SDGE`, then flip those ZIPs off the EIA-Pacific fallback (§5.1).
- URDB coverage beyond CA (national ZIP crosswalk + harvest of maintained utilities).
- **Solar orientation correction** — make roof tilt/azimuth live (baked per-zone orientation
  factors + orientation-specific intra-day shapes; west-facing shifts output toward peak).

## Definition of done

- [ ] PVWatts tables consumed (ZIP → zone → default, never a scalar); `specific_yield` removed from model/UI/config; Solar device emits (12,).
- [ ] Hourly Solar → Battery → Utility energy balance produces self-consumption/export from real
      load; balance identities close; `scf` removed from model/UI/config.
- [ ] URDB `RateStructure` consumed: `period_fractions` split via real per-tariff peak hours,
      `price_month` slabs on the home aggregate, coverage gate + ZIP→baseline resolved (offline DONE).
- [ ] **PG&E area fully working** end-to-end (URDB rate × `cec_projection`); SCE/SDG&E use URDB rates
      with **EIA-Pacific escalation** via the market selector (§5.1); all CA ZIPs degrade gracefully.
- [ ] `cec_projection` promoted to the default rate model for PG&E (§5); NEM/social extension recorded.
- [ ] Golden re-baselined with documented diff — escalation switch (§5) and TOU structure (§3) as
      separate, attributable commits; full `pytest` green.
- [ ] Charts + Help updated (roof geometry remains inert — default orientation).
- [ ] CLAUDE.md updated: Phase 7 closed.
