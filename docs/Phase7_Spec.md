# WhyWatt — Phase 7 Development Spec

**Status:** 🔵 PLANNED — the data-pipeline + golden-rebaseline phase. Flow new simulation data
through the model, and adopt the CEC projected-rate escalation as the default.
**Follows:** Phase 6 (`docs/Phase6_Spec.md`) — Solar/Battery split, inert roof-geometry inputs, and
the **non-default `cec_projection` rate hand-off interface** (evaluated but not switched). Offline
PVWatts/URDB data is harvested and validated separately in `docs/OfflineSolarData_Plan.md`.
**Last updated:** 2026-09-23 — §4.1 round-2 decisions: My Utility stays default until after P7
(golden unchanged); projections scale the URDB plan from its anchor year; EIA — Pacific for
non-PG&E + new `starting_rates.json`; §5 default flip deferred post-P7. Earlier: added §4.1 UI rework review (utilities in Home Profile; current prices vs projection method; 15 issues incl. municipal-utility ZIP mis-resolution). Earlier 2026-09-23 — §3 URDB TOU pricing landed as an option (`urdb_tou`; SCE
quarantined to EIA; golden unchanged). Earlier 2026-09-23 — added §6 **NREL End-Use Load Profiles** (planned, separate branch
after this one; no interim fix to today's hourly load shapes). 2026-09-22 — solar **simulation interface** decided: `SolarResourceLoader` →
`SolarResource` (clock time) as `HomeConfig.solar_resource`, `SolarConfig` = user choices only (§1);
`scf` retired for an **hourly energy balance with two battery modes** (Self-powered /
Cost-saving, grid charging on by default) where **each month the cheaper mode wins** (§0, §2 —
revises kickoff decisions: 3-period → hourly, reserved-for-peak → two-mode picker, solar-only →
grid charging when it pays); landing as three commits A/B/C. Earlier 2026-09-22: §1 re-scoped to **per-ZIP** PVWatts yield at a single default
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
   the home's load instead of a flat `scf` fraction: two standard battery modes (Self-powered,
   Cost-saving with grid charging) run each month and the cheaper wins; excess solar is exported
   and self-consumption becomes an output (§0, §2).
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
| Self-consumption | flat `scf` fraction (user slider) | **output** of an hourly energy balance (two battery modes, cheaper per month wins); `scf` retired |
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

**Three sources, two battery modes, the cheaper one wins (revised 2026-09-22 — replaces the flat
`scf`).** Every hour, load is met from solar, the battery and the utility; solar the home and battery
can't use is **exported**. *How* the battery is used follows one of two standard modes — the same
two settings home batteries ship with — and **each month the model runs both and keeps the one
with the lower monthly bill.**

Common inputs for month *m* (representative day, clock hours h = 0..23):
```
G[h] = system_kw × ac_monthly[m] / days[m] × shape_clock[m][h]     # solar generation (§1)
L[h] = Σ_devices kWh[m] / days[m] × load_shape_d[h]                 # home electric load (§0.1)
P    = tariff.peak_hours[m]                                          # peak window (§3); empty if flat
```

**Mode 1 — Self-powered** ("use your own solar first"):
```
direct    = min(G[h], L[h])                                          # 1. solar → home
surplus   = G[h] − direct ;  deficit = L[h] − direct
charge    = min(surplus, (cap − soc) / √η, p_max)                    #    solar → battery
export    = surplus − charge                                         #    excess → grid
discharge = min(deficit, soc × √η, p_max)                            # 2. battery → home (any hour)
grid      = deficit − discharge                                      # 3. utility → home
```

**Mode 2 — Cost-saving** ("fill the battery for the peak, empty it only during the peak"):
```
R = min(cap, Σ_{h∈P} min(max(L[h]−G[h], 0), p_max) / √η)    # reserve: just enough to cover peak
OFF-PEAK hours (h ∉ P):
  solar → battery until soc reaches R            # battery first, before the home
  solar → home ; leftover solar → battery (up to cap) → export
  battery does NOT discharge ; utility covers the home
  grid top-up (if grid_charging and η×r_peak > r_offpeak): whatever the solar pass left short
      of R at peak start is charged from the utility in the off-peak hours just before the
      peak (latest hour first, each ≤ p_max) — "top it up before 4pm"
PEAK hours (h ∈ P):
  solar → home ; battery → home ; utility covers the rest ; surplus solar → battery → export
```
`r_peak`, `r_offpeak` = the month's tier-1 peak / off-peak rates (§3). The top-up test is the
**round-trip value of a shifted kWh**, `η × r_peak − r_offpeak > 0`; tiers are *not* reasoned about
here — the monthly bill comparison below captures them (grid charging adds `(1−η)` losses to the
month's import, which can push it up a tier; if that makes Cost-saving dearer, Self-powered wins).

**Choosing the mode (per month):**
```
bill_mode = price_month(m, grid_peak_kWh, grid_offpeak_kWh) − export × export_credit[m]  # tiers incl.
mode[m]   = argmin(bill_self, bill_cost)        # tie → Self-powered
```
- A **flat tariff** (no peak window) runs Self-powered only — Cost-saving has nothing to aim at.
  Until §3 lands (flat/ACC pricing), every month is therefore Self-powered.
- Both modes share: **steady state** (the day is run twice, the second pass kept, so start- and
  end-of-day charge match); **battery parameters** `cap = battery_kwh` (usable), `η` round-trip
  efficiency (default 0.90, √η on charge and on discharge), `p_max` power cap (default 5 kW);
  no battery → `cap = 0` and both modes reduce to solar → home → export.
- **Outputs per month:** `mode`, `direct`, `battery_charge_solar`, `battery_charge_grid`,
  `discharge`, `export`, `grid[h]` (24-vector). `grid[h]` is what §3 prices; `export` earns the
  NEM credit. The mode is shown in the UI ("Battery: Self-powered Nov–Mar, Cost-saving Apr–Oct").
- **Why this and not an optimiser:** two named modes an advocate can explain in one sentence
  ("each month the battery uses whichever of its two standard settings saves you more"), with
  tiers handled exactly by comparing whole bills. An hour-by-hour linear-program optimum is
  computed **offline only** (notebook + test) as a benchmark; the two-mode picker should land
  within a few percent of it — if not, that is the signal to add a smarter mode.

Why it matters — round-trip value of a shifted kWh, `0.9 × peak − off-peak` (URDB harvest):

| Tariff | Jan $/kWh | Jul $/kWh |
|---|---:|---:|
| PG&E E-TOU-C (WhyWatt default) | −0.002 | +0.079 |
| PG&E E-ELEC (all-electric) | +0.004 | +0.163 |
| PG&E EV2 | +0.144 | +0.259 |
| SDG&E TOU-DR-1 (WhyWatt default) | +0.128 | +0.250 |
| SDG&E EV-TOU-5 | +0.349 | +0.585 |

Near zero (PG&E standard plans in winter) → Self-powered is right; large (EV / all-electric /
SDG&E plans) → morning and grid charging pay. The picker handles both without per-tariff rules.

**Locked decisions (Phase 7 kickoff, revised 2026-09-22):**
1. **Battery charging: solar, and the grid when it pays** — grid charging is **on by default**
   in Cost-saving mode (`BatteryConfig.grid_charging = True`), used only when
   `η × r_peak > r_offpeak`; the advocate can switch it off. *Revised from "solar only".*
2. **Hourly representative day** (24 clock hours × 12 months) — *replaces* the original
   3-period granularity. Both inputs are already hourly (the 24-h device load shapes and the
   PVWatts 12×24 solar shape), so collapsing to 3 periods only threw information away.
3. **Two battery modes, cheaper per month wins** — Self-powered and Cost-saving, compared on the
   full monthly bill (tiers included). *Replaces* "battery reserved for peak" and the interim
   single greedy order. Battery-to-grid export for profit (NEM 3.0 evening export spikes) is a
   third mode, deferred past Phase 7.
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
  have: with solar, battery and utility dispatched hour by hour under the cheaper of two battery
  modes and excess exported (§0), self-consumption is an *output*, not an input. Remove `SolarConfig.scf`, the UI "Self-use"
  slider and its 80/35 battery snap (`src/ui/panels.py`, `state.py`, `config.py`, `layout.py`,
  `sim.py`), and `solar_scf` from `whywatt_default.json`; stale share-link values are dropped.
- **Battery config becomes live physics:** `BatteryConfig(battery_enabled, battery_kwh,
  round_trip_eff=0.90, power_kw=5.0, grid_charging=True)`. `battery_enabled=False` ⇒ `cap = 0`.
- **Dispatch is one pure function**, `dispatch_month(G, L, peak_hours, rates, battery, mode)` with
  `mode ∈ {"self", "cost", "auto"}` (`"auto"` = run both, keep the cheaper — what the model uses).
  Pure and deterministic (arrays in, flows out) so tests can run each mode on its own. The
  `SolarBatteryConfig` shim is retired; `HESModel` takes `SolarConfig` + `BatteryConfig` directly.
- **Outputs** keep the existing history arrays, now physically derived and reported as an
  energy balance that closes exactly:
  `production = solar_direct + battery_charge + export` and
  `load = solar_direct + battery_discharge + grid_import`, with
  `battery_discharge = (battery_charge_solar + battery_charge_grid) × η` (steady state), and
  `grid_import` includes `battery_charge_grid`. `solar_self_consumed_history` =
  `solar_direct + battery_discharge`; self-consumption rises with battery size and with
  evening-heavy load.
- Deterministic (no Monte Carlo). Granularity and modes are §0's hourly representative day.
- **Per-mode tests and log (agreed 2026-09-22):** a test runs **each mode separately** — Self-powered,
  Cost-saving with grid charging, Cost-saving without — plus `auto`, over a fixed matrix of sample
  homes (small/large solar, with/without battery, EV/no EV) × tariffs (flat, E-TOU-C, E-ELEC, EV2,
  TOU-DR-1) × months (Jan, Jul), asserts the invariants, and **writes a readable log**
  (`tests/regression/dispatch_modes.md`, regenerated like `report.md`): per case, the four energy
  flows, grid charging, monthly bill per mode, and which mode `auto` chose. The notebook
  `notebooks/battery_dispatch_review.ipynb` shows the same with charts plus the offline LP
  benchmark gap.

### Landing sequence — three commits, one golden-baseline diff each (decided 2026-09-22)

| Commit | Change | Golden diff attributable to |
|---|---|---|
| **A — data source** | `SolarResourceLoader` + `HomeConfig.solar_resource`; `specific_yield` retired; production = `system_kw × Σ ac_monthly`, still priced with today's annual-average rates and today's `scf` | ZIP-specific yield only (CZ4 ≈ +10%: 1,644 vs 1,500) |
| **B — monthly pricing** | production `(12,)` × monthly retail / export rates; `scf` still applied per month | seasonal alignment (summer-heavy solar × summer rates). **Landed 2026-09-22: ≈ −$50 journey opex over the horizon per solar case** — today's retail arrays (CAGR and ACC alike) are flat within a year and only the NEM 3.0 export credit varies ($0.057–0.072/kWh), so the seasonal signal is near-zero until §3's summer/winter URDB rates. A forced-seasonal-rate unit test proves the monthly weighting. |
| **C — energy balance** | §0 hourly energy balance, two battery modes + monthly picker; `scf` retired; battery physics live | self-consumption from physics + battery (all months Self-powered until §3 adds peak windows). **Landed 2026-09-22: journey opex +$7.2k / +$2.1k / +$5.7k over the horizon (cases 02 / 04 / 06)** — physical self-use starts low in a mostly-gas home (case 02 yr 1: 18%) and rises to ~77% once electrified, vs the retired fixed 80%. Per-mode tests: identities close in every mode; the two-mode picker matched the offline LP optimum on all 40 battery cases (two-period tariffs, no tiers). `SolarBatteryConfig` shim kept — its retirement is a pure refactor, deferred. |

`scf` survives A and B *on purpose*, so neither diff mixes in the dispatch change — but **not as a
user input**: the UI "Self-use" slider was removed with commit A (2026-09-22). Until C, `scf` is
fixed by the battery switch via `journey.interim_scf()` — 0.80 with a battery, 0.35 without, the
values the slider used to snap to — so the golden did not move; the `04__self_consumption_down`
trend offset became `04__no_battery`. §3 (URDB TOU
pricing of `grid[h]`) and §5 (escalation) land after C as their own commits.

### §3 — Peak / non-peak consumption split + URDB TOU rates

> **Runtime half LANDED 2026-09-23 as an option (`urdb_tou`), not yet the default** — see
> "Landed" at the end of this section. The golden did not move; flipping the default is its own
> commit.
>
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

**Landed 2026-09-23 (§3 runtime, as an option):**
- `src/urdb_rates.py` (not `rate_loader.py` — kept separate from the EIA/ACC loaders):
  `URDBRates` (coverage gate + tariff options + `resolve(zip, eiaid, label)`) and a frozen
  `RateStructure` with `period_fractions`, `tier1_rates`, `effective_rate` and `price_month`.
- **Quarantine:** SCE (17609) is harvested but routed to EIA. Its URDB TOU-D-4-9PM record shows a
  $0.33/kWh summer on-peak rate (same as winter); SCE publishes ~$0.58. Re-harvest and verify
  against SCE's tariff sheets before lifting it. PG&E and SDG&E price from URDB.
- **Baseline tiers:** the record's thresholds are scaled per month by (home territory baseline ÷
  record territory baseline) for the matching season, so tier 1 = the ZIP's allowance and higher
  tiers keep their ratio (e.g. Fresno summer 19.2 kWh/day vs San José 9.8).
- **Fixed charge:** taken from URDB as-is (PG&E / SDG&E $0.79343/day ≈ $24/month). It raises both
  homes equally and cancels out of savings. *Data note:* SDG&E TOU-DR-1's unit is recorded as
  `$/month` in URDB (almost certainly `$/day`); left as published.
- **Pricing wiring:** each device class is priced at its tier-1 peak-weighted rate (exact without
  tiers); the home-level bill (`price_month` on the aggregate hourly load, tiers + fixed) replaces
  the device sum, and the difference is spread over categories by electric cost (§0.2). Solar /
  battery dispatch uses the tariff's peak window, and the monthly mode picker compares full bills
  via `price_fn`.
- **Escalation (interim):** tariff = start-year level × (1 + EIA CAGR)^year, like My Utility; §5
  swaps in the projection trajectory.
- **UI:** "TOU (URDB)" electricity button (card + detail, scenarios A/B), a Tariff dropdown
  (default first, closed plans flagged), resolved line "E-TOU-C · peak 4pm–9pm" or the fallback
  reason. New config keys: `elec_tariff_label` ("" = default); `urdb_tou` accepted for
  electricity only.
- **Case 02 on URDB** (20 yr, electrified, 6.3 kW + 13.5 kWh): E-TOU-C → Self-powered all year;
  E-ELEC and EV2 → Cost-saving Jan and Dec, Self-powered Feb–Nov.
- Tests: `tests/test_urdb_rates.py` (coverage, quarantine, baselines by ZIP, price_month hand
  check, revenue-neutral flat case, home bill = Σ price_month on the home's own load, EV2 winter
  Cost-saving on case 02). Golden unchanged; 485 tests pass.
- **Not yet:** URDB as the default rate model (next, own golden diff); SCE re-harvest.

### §4 — UI / charts / outputs

- New/updated charts: monthly solar generation curve; peak vs non-peak consumption + cost
  split; battery self-consumption vs export. Update Help (`solar.html`, rate help) to describe
  the new model.
- Home Profile roof-geometry inputs **remain inert** (default orientation, §1). The yield field
  shows the ZIP's PVWatts annual and its source (ZIP / zone fallback), read from
  `HomeConfig.solar_resource`.
- **Solar/Battery panel:** the "Self-use" slider (`scf`) and its 80/35 battery snap are removed;
  self-consumption is now *reported* (from the §0 balance), not entered. Battery inputs are size
  (kWh) and on/off, with round-trip efficiency, power cap and **grid charging (on)** under Details.
  The chosen mode per month is shown ("Battery: Self-powered Nov–Mar, Cost-saving Apr–Oct").
- New energy-balance readout / chart per year: solar → home, solar → battery → home, export,
  grid import (the four flows of §0).
- Rate-model selector gains a **URDB TOU** option alongside today's EIA/ACC/CAGR modes and the
  `cec_projection` option added (non-default) in Phase 6 — which §5 now promotes to the default.
- **Plan-button consolidation (Spec 5.6 #6)** lands here, alongside the Solar/Battery/Panel UI
  work, when a unified plan-row can be coherent (it was deferred from 5.6 for exactly this moment).

---

### §4.1 — UI rework: your utilities, current prices vs projection method (PLANNED — review 2026-09-23)

**Requested (2026-09-23):**
1. **Home Profile** shows, next to the climate-zone line, *your electricity utility* and *your gas
   utility*. A ZIP we don't cover shows the fallback.
2. **Home Energy Prices** splits into two things that today are one "rate model":
   - **Current energy prices** (the *starting* price, per fuel). If we know the utility: a button
     with its name + default plan, e.g. **"PG&E · E-TOU-C"**; clicking it offers the other plans.
     If we don't: an EIA-based price.
   - **Projection method** (how prices *grow*). Primary buttons: **WhyWatt Conservative / Moderate
     / Stress** plus **EIA — Pacific**. **"My Utility" is removed.** **CA Average** and **ACC** move
     to a dropdown under Details, and selecting either shows its escalation slider.
3. EIA — Pacific curves for other regions are a **TODO** for beyond-CA.

**Target model — two independent axes (the core change).** Today one enum (`elec_rate_model_a`
= `cagr_flat` | `ca_average` | `acc_shaped` | `urdb_tou` | projection keys) sets *both* the starting
price and its growth. The rework separates them:

```
StartingRate (per fuel, a HOME fact — shared by scenarios A and B)
  electricity: URDB tariff (utility covered)  → RateStructure (tiers, peak window, fixed charge)
               else EIA per-utility rate      → flat monthly level
               else fallback (see issue 5)
  gas:         EIA-176 per-LDC rate, else fallback            (no URDB for gas)
Projection (per fuel, per scenario)  → escalation index idx[y], idx[0] = 1
  whywatt_{conservative,moderate,stress} | eia_pacific      → series[y] / series[start year]
  ca_average | acc (Details dropdown)                        → (1 + slider CAGR)^y
Price in year y = StartingRate × idx[y]
```

**Issues we will run into (review 2026-09-23):**

| # | Issue | Proposed handling |
|---|---|---|
| 1 | **No starting-rate abstraction.** Loaders (`RateLoader`, `ACCRateLoader`, `ProjectedRateSource`) each return a full `(n_years, 12)` array — level and growth fused. | New `StartingRate` + `Projection` objects; the model multiplies them. Refactor first with numbers unchanged. |
| 2 | **Projection curves are price levels, not growth.** The bundle stores absolute $/kWh (PG&E Moderate starts at $0.386; EIA Pacific at $0.242 — a Pacific-wide average incl. WA/OR). Phase 6 used the level directly. | Use only the *shape*: `idx[y] = series[y] / series[sim start]`. The level comes from the home's own starting rate. Behaviour change vs Phase 6 — document it. |
| 3 | **WhyWatt scenarios exist only for `CA_PGE`.** For SDG&E / SCE / others there is no curve. This conflicts with §5.1 (non-PG&E escalate on EIA Pacific). | **Decision needed:** (a) apply the PG&E index everywhere with a "PG&E-based" badge, or (b) keep §5.1 — WhyWatt buttons enabled for PG&E only, EIA Pacific the default elsewhere. |
| 4 | **EIA Pacific is a single copy inside the `CA_PGE` market** (AEO Pacific census division). Beyond CA needs one curve per EIA region. Gas EIA Pacific *drops* 10% 2025→2026 before rising. | Treat as region-level data (`benchmarks` keyed by EIA region); **TODO beyond CA:** harvest AEO curves for all census divisions. Flag the first-year gas dip in help. |
| 5 | **"EIA — Pacific (default)" mixes a price with a projection.** Today an uncovered ZIP starts from the **California-average EIA price ($0.32/kWh)**, and *out-of-state* ZIPs (e.g. 10001 NYC, 97201 Portland) also get the CA average — wrong outside CA. | Utility label: "Not covered — California average (EIA)"; projection defaults to EIA — Pacific. **TODO beyond CA:** EIA state (or division) average starting prices. |
| 6 | **Municipal utilities resolve to PG&E.** `zip_to_electric_utility.json` holds only the three IOUs; a ZIP with *any* PG&E customers maps to PG&E. SMUD (95814), Silicon Valley Power (95050), Palo Alto CPAU (94301) all show **PG&E** (SMUD's rate is roughly half of PG&E's); LADWP ZIPs fall back to CA average. Becomes very visible once the UI says "Your utility". | Separate fix before/with the UI: add the non-IOU file, resolve multi-utility ZIPs by service share, show "Municipal utility — EIA rate" for munis; flag ambiguous ZIPs. |
| 7 | **CA Average and ACC aren't projections today.** CA Average = CA-average *price* × CAGR; ACC = PG&E CPUC *base level* + ACC *monthly shape* + ACC CAGR. | In the new model both become "constant CAGR" projections (slider shown). ACC's monthly shape must **not** stack on a URDB starting rate (double-counts seasonality, §3) — with URDB, ACC is just a CAGR; with an EIA flat start it may keep its seasonal shape. **Decision needed:** keep the ACC shape at all, or drop it for simplicity? |
| 8 | **Removing "My Utility" moves the default** — the current default is `cagr_flat` (EIA utility price × EIA historical CAGR, +7%/yr). The golden baseline, 12 regression cases, trend offsets (`01__elec_cagr_up`, `08__acc_*`), tests and **share links** all use the old keys. | Keep an internal `eia_historical` projection (not shown) so the refactor is golden-neutral; add a config migration map (old key → start + projection); make the default change its own commit (= §5's default flip). |
| 9 | **Horizon & start year.** Bundle covers 2025–2050; a 30-year run from 2025 reaches 2054 and holds 2050 flat. `sim_start_year` can differ from 2025. | Index relative to `sim_start_year`; after 2050 continue at the last 5-year CAGR (not flat) — or keep flat and say so in help. |
| 10 | **Base-year mismatch.** EIA per-utility prices are 2024; URDB tariffs are 2024–26 vintage; projections start 2025. | Treat the starting rate as the sim-start level; note ±1 year of vintage in help. |
| 11 | **Gas has no URDB and one market.** The gas "button" is just the LDC (PG&E, SoCalGas, SDG&E) with no plan choices; WhyWatt gas scenarios (the gas-spiral curves) are PG&E-market. | Gas button shows the LDC name (no dropdown); same decision as issue 3 for non-PG&E gas. |
| 12 | **NEM export credit escalation.** Today NEM 3.0 export = ACC avoided cost × CAGR, independent of the chosen projection. | Follow the electricity projection index (ties to §5's open "does the projection drive NEM export?"). |
| 13 | **Scenario A/B.** The starting rate / tariff is a fact about the home; only the projection is a what-if. | One tariff picker (shared); projection chosen per scenario. |
| 14 | **Labels.** Data has long names ("Pacific Gas & Electric"); URDB plan names are long. | Short-name map (PG&E, SCE, SDG&E, SoCalGas) + URDB `family` → "PG&E · E-TOU-C". |
| 15 | **SCE is quarantined** (§3). | Button "SCE · EIA rate" (no plan dropdown) with the quarantine note until the re-harvest. |

**Decisions (2026-09-23, round 2) — these narrow the change:**

1. **"My Utility" stays exactly as it is until the end of Phase 7**, moved into the Details
   dropdown. It remains the **default**, so the golden baseline keeps comparing like-for-like;
   switching the default happens **after Phase 7** (so §5's default flip moves post-P7 too).
   → Issue 8 mostly disappears: no default change, no golden move, no migration of the default.
2. **Projections scale the actual plan.** Start from the URDB tariff (peak / off-peak, tiers,
   fixed charge) and scale it by the projection curve's *growth*, anchored at the right year
   (rule below). The curves' absolute levels (built from average rates) are not used as prices.
   → Issue 2 resolved.
3. **PG&E-only WhyWatt curves are an accepted limitation.** Non-PG&E areas default to the
   **EIA — Pacific** curve, with the WhyWatt curves selectable everywhere (labelled
   "PG&E-based" outside PG&E). Where URDB gives **no** current price for a ZIP, the starting price
   comes from a **separate starting-rates data file** (not URDB). → Issues 3, 4 (in CA), 5, 15.
4. **CA Average and ACC stay** as today's fixed-% modes in the Details dropdown with the
   escalation slider. → Issue 7 deferred (no reinterpretation this phase).

**Resulting model — two kinds of rate choice in the same selector:**

| Kind | Options | Where | Starting price | Growth |
|---|---|---|---|---|
| **Projection (new meaning)** | WhyWatt Conservative / Moderate / Stress, EIA — Pacific (+ reference curves in their expander) | primary buttons | the home's **StartingRate** (below) | curve index `S[y] / S[anchor]` |
| **Legacy (unchanged)** | My Utility (default), CA Average, ACC | Details dropdown, slider shown | as today | as today (fixed %) |

So the same config keys carry on (`elec_rate_model_a/b`, `gas_rate_model_a/b`); only the
*projection* keys change meaning — from "the curve's absolute price" (Phase 6) to "starting rate ×
curve growth". `urdb_tou` stops being a separate model: whenever a projection is chosen and the
utility is URDB-covered, the starting price *is* the URDB plan. Legacy modes never touch URDB.

**StartingRate ladder (per fuel, a home fact shared by scenarios A/B):**
- **Electricity:** URDB plan (covered, not quarantined; the Tariff picker) → else the
  starting-rates file.
- **Gas:** always the starting-rates file (no URDB for gas).
- **New file `data/rates/starting_rates.json`** (built offline from data already committed, with
  provenance): for each fuel, per-utility EIA prices (`eia_rates_by_utility.json`, 2024) and a
  regional **EIA — Pacific** price (AEO 2026 Pacific, 2025), each with its **anchor year**.
- **Recommendation to confirm:** use the ladder *URDB → EIA per-utility → EIA — Pacific*, not
  straight to EIA — Pacific. The AEO Pacific level is a Pacific-wide average (includes WA/OR):
  $0.242/kWh in 2025, vs SCE's own EIA rate $0.324 and PG&E's $0.396 — 25–40% low for California
  utilities. The per-utility EIA rate is already harvested and is what "My Utility" uses today.
  EIA — Pacific then only prices ZIPs with no resolved utility (and, TODO beyond CA, would be
  replaced by the ZIP's own EIA region).

**Anchor-year rule ("the right starting year").**
`price(y) = start_price × S[y] / S[anchor]`, where *y* is the calendar year of the simulation
(sim start year + index) and *anchor* is the year the starting price is valid for:
- URDB plan → its **effective year**: PG&E plans 2026 (effective 2026-03-27), SDG&E 2026
  (2026-06-01), SCE 2024 (quarantined anyway). A 2025 simulation start therefore *back-scales*
  the 2026 plan by `S[2025] / S[2026]`.
- Starting-rates file → its data year: EIA per-utility **2024**, EIA — Pacific **2025**.
- The curves start at **2025** (the bundle base year; AEO Pacific has no 2024 value), so an anchor
  before 2025 is **clipped to 2025** — i.e. 2024 prices are treated as 2025 prices. Stated in help.
- After **2050** (a 30-year run reaches 2054) the curve holds its 2050 value, as today — stated
  in help; revisit post-P7.
- Only $ amounts scale (energy rates and the fixed charge); **tier thresholds (kWh) never scale**.

**What changes, narrowed (U1 + U2 only; golden unchanged throughout Phase 7):**
- `scripts/build_starting_rates.py` → `data/rates/starting_rates.json` (+ test).
- `src/starting_rates.py`: StartingRate resolver (URDB `RateStructure` | flat per-utility | flat
  EIA — Pacific) + the projection index from the bundle with the anchor rule.
- `model.py`: projection keys go through *StartingRate × index* (URDB path = today's `urdb_tou`
  wiring with the index as escalation); legacy keys untouched. Retire `urdb_tou` as a key (map
  old links to `whywatt_moderate`).
- UI: Home Profile "Your utilities" line (electric + gas, or the fallback); **Current energy
  prices** card (utility + plan button, e.g. "PG&E · E-TOU-C", opening the plan list; gas shows
  the LDC; fallback shows "EIA rate" / "EIA — Pacific"); **Projection method** card (WhyWatt ×3 +
  EIA — Pacific; Details dropdown: My Utility (default) / CA Average / ACC with the slider).
- NEM export escalation (issue 12) and scenario scope (issue 13: plan shared, projection per
  scenario) as proposed above.
- **Still separate:** municipal-utility ZIP resolution (issue 6 — before the UI says "Your
  utility"), SCE re-harvest, **TODO beyond CA:** EIA regional curves and regional starting prices.
- **Post-Phase-7:** switch the default from My Utility to a projection (with URDB starting
  price); reinterpret CA Average / ACC as pure % projections on the starting rate; drop My Utility.

### §5 — Adopt the CEC projected-rate escalation as the default (Phase 6 WS1 → live)

Phase 6 built `cec_projection` as a **non-default** rate model (a `ProjectedRateSource` reading
`data/rates/projection/whywatt_rate_projection.json`) and produced a difference evaluation
(`notebooks/rate_switch_review.ipynb`) quantifying what switching would change. Phase 7 makes the
switch.

This is a **separate rate axis from §3** and can be its own commit + its own golden re-baseline:
§3 changes the rate *structure* (adds the peak/non-peak TOU dimension); §5 changes the rate
*escalation* (today's single CAGR → the CEC-driven trajectory: electricity real-flat, gas spiral).
Sequence them independently so each golden diff is attributable to one cause.

- **Default switch — DEFERRED to post-Phase-7 (decided 2026-09-23, §4.1).** "My Utility"
  (`cagr_flat`) stays the default through Phase 7 so the golden keeps comparing like-for-like; the
  projection options (starting rate × curve growth, §4.1) ship as selectable choices. Flipping the
  factory default is the first post-P7 step.
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

### §6 — NREL End-Use Load Profiles (planned feature — separate branch)

**Status:** 📋 PLANNED (added 2026-09-23). Built on its own branch (`feat/nrel-end-use-load-profiles`)
**after** `feat/urdb-offline-harvest` is done. **No interim fix** to the current profiles in the
meantime — the next change to hourly load shapes is this one.

**Why.** The §0 energy balance spreads each electric device's monthly kWh over a 24-h profile from
`data/rates/device_load_shapes.json`. That file was built in Phase 2 as a rough *rate-weighting*
aid for the ACC model, not as a load model, and it is now on the critical path for solar
self-use, battery value, and (with §3) the peak / off-peak bill split:

| Gap in today's profiles | Effect on results |
|---|---|
| Everyday use (lights, plugs, cooking, dishwasher, dryer) is **flat, 1/24 per hour** | Too much load at midday (solar covers it directly), too little at 4–9pm → understates battery value and the TOU peak |
| A heat pump uses the **heating** shape all year | Summer cooling is placed at night/morning instead of the afternoon |
| **One shape for every month** (and every day type) | No winter vs summer difference in *when* energy is used |
| **No raw-source snapshot / checksum**; values hand-shaped from cited sources; time basis (clock vs standard) undocumented | Weaker provenance than the PVWatts / URDB data it now sits beside |

**Source.** NREL **End-Use Load Profiles for the U.S. Building Stock** (the residential set is built
from ResStock), published as open data on OEDI: hourly (sub-hourly) electricity by end use —
heating, cooling, water heating, lighting, plug loads, cooking, clothes drying, dishwashing,
refrigeration, … — aggregated by geography. *Verify at planning:* release/version, the geography
we can aggregate to (and how it maps to CEC Building Climate Zones), the exact end-use column
names, whether EV charging is included (if not, keep NREL EVI-Pro for EV), and the timestamp
convention.

**Approach — same offline pattern as PVWatts (§1).**
- `scripts/build_load_profiles.py` (run offline, never at runtime) → `data/loads/end_use_profiles.json`:
  per **CEC zone × end use × month (12) × 24 clock hours**, each row normalised to sum to 1;
  `_meta.schema_version`, source URLs + sha256, build date; trimmed source snapshots committed.
- End use → device class mapping replaces `DEVICE_ACC_CATEGORY`'s role for load shapes: HPWH →
  water heating; heat pump → heating **and** cooling (see below); central AC → cooling; induction /
  oven → cooking; dryer → clothes drying; dishwasher → dishwashing; lights & plugs → a
  lighting + plugs + refrigeration composite weighted by the source's own energy shares; EV → EV
  profile (source TBD above).
- **Heat pump split:** its monthly kWh is divided into heating and cooling parts (from the device's
  own heating/cooling energy if it reports them, else by the month's HDD/CDD share), each spread by
  its own profile.
- **Loader + interface:** `LoadProfileLoader` → a frozen `LoadProfiles` for the home's zone (clock
  time applied once, like `SolarResource`), exposed as a derived `HomeConfig.load_profiles`
  property. `JourneyHome` receives `{device class: (12, 24)}` instead of today's single `(24,)` per
  class and uses row *m* for month *m*. `dispatch.py` is unchanged — it already takes `L[h]`.

**Consumers.** The §0 energy balance (home load `L[h]`) and §3 `period_fractions` (peak share per
device). *Open question:* whether the ACC rate weighting in `rate_loader.py` (the file's original
consumer) also switches, or keeps `device_load_shapes.json` until ACC is revisited.

**Validation.** Tests: every row sums to 1, every device class resolves to a profile in every zone,
peak (4–9pm) share of the lighting/plugs composite > the flat 21%, summer cooling peaks in the
afternoon, the energy balance still closes. Review notebook `notebooks/load_profiles_review.ipynb`:
old vs new profile per device, and the change in self-use / battery discharge / peak import for
the regression cases.

**Golden.** One dedicated re-baseline commit. Expected direction: an evening-peaked everyday load
lowers *direct* solar self-use and raises battery discharge and peak-hour grid import.

**Done when:** profiles harvested with provenance; `device_load_shapes.json` no longer drives the
energy balance; heat pump heating/cooling split live; tests + notebook green; golden re-baselined
with the diff explained.

---

## Module / data deltas (Phase 7 target state)

```
src/
  solar_loader.py       (NEW) SolarResourceLoader + SolarResource — ZIP → zone → default, clock time
  home_config.py        HomeConfig.solar_resource (derived property from zip_code; not serialized)
  journey.py            SolarConfig = user choices only (no specific_yield, no scf);
                        BatteryConfig live (round_trip_eff, power_kw); SolarBatteryConfig retired;
                        hourly representative-day energy balance (§0)
  urdb_rates.py         (NEW, landed) URDBRates + RateStructure: coverage gate (+ SCE quarantine),
                        baseline-scaled tiers, period_fractions / price_month, tariff options (§3)
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
  loads/end_use_profiles.json  (§6, separate branch) NREL End-Use Load Profiles per CEC zone ×
                        end use × month × 24 clock hours — replaces device_load_shapes.json in the
                        energy balance
scripts/
  build_urdb*.py / build_baseline_crosswalk.py  (OfflineURDB, DONE; re-run to add utilities)
tests/
  test_solar_loader.py  (NEW) ZIP→zone→default, schema_version gate, clock-time shift (rows still
                        sum to 1; July output moves +1 h, Jan does not), production = system_kw×ac_annual,
                        two ZIPs → two different model outputs, no-scalar grep gate
  test_battery.py       (NEW) per mode (self / cost / cost-no-grid / auto): energy balance closes
                        exactly, steady-state SOC, cap=0 ⇒ solar→home→export, power cap binds,
                        η losses = charge×(1−η); flat tariff ⇒ auto == self; auto bill ≤ both;
                        no grid charging when η×r_peak ≤ r_offpeak or grid_charging=False;
                        writes tests/regression/dispatch_modes.md (per-mode log)
  test_urdb_rates.py    (NEW) URDBRateStructure: period_fractions + price_month + tier slabs + fallback
  regression/golden.json  re-baselined (output changes intentionally)
```

## Resolved at kickoff (see §0)

- ✅ Battery dispatch fidelity → **hourly representative day** (24 clock h × 12 months), scaled by
  days-in-month — *revised 2026-09-22 from 3-period*.
- ✅ Battery use → **two modes (Self-powered, Cost-saving), the cheaper per month wins** on the full
  monthly bill; excess solar exported; `scf` retired — *revised 2026-09-22 from "battery reserved
  for peak"*.
- ✅ Battery charge source → **solar, plus the grid when `η×r_peak > r_offpeak`** — grid charging
  on by default, switchable — *revised 2026-09-22 from "solar only"*.
- ✅ Validation → per-mode tests + readable log; offline LP benchmark (notebook/test only).
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
- §6 load profiles: does the ACC rate weighting also switch to the NREL profiles, or keep
  `device_load_shapes.json`? NREL source details (version, geography → CEC zone, EV coverage,
  timestamps) to verify at planning.

## Post-Phase-7 (separate efforts, not gating close)

- **SCE/SDG&E rate-projection markets** — extend the offline "Rate Projections" harvest (manual
  spreadsheet step) with `CA_SCE`/`CA_SDGE`, then flip those ZIPs off the EIA-Pacific fallback (§5.1).
- URDB coverage beyond CA (national ZIP crosswalk + harvest of maintained utilities).
- **Solar orientation correction** — make roof tilt/azimuth live (baked per-zone orientation
  factors + orientation-specific intra-day shapes; west-facing shifts output toward peak).

## Definition of done

- [x] PVWatts tables consumed (ZIP → zone → default, never a scalar); `specific_yield` removed from model/UI/config; Solar device emits (12,). *(commits A/B, 2026-09-22)*
- [x] Hourly energy balance with two battery modes and a per-month cheaper-mode picker produces
      self-consumption/export from real load; balance identities close in every mode; per-mode
      log generated; two-mode picker within a few % of the offline LP benchmark; `scf` removed.
      *(commit C, 2026-09-22 — matched the LP optimum on all battery cases)*
- [ ] URDB `RateStructure` consumed: `period_fractions` split via real per-tariff peak hours,
      `price_month` slabs on the home aggregate, coverage gate + ZIP→baseline resolved (offline DONE).
- [ ] **PG&E area fully working** end-to-end as a selectable choice (URDB plan × WhyWatt curve
      growth, §4.1); non-PG&E areas default to EIA — Pacific growth with WhyWatt selectable; ZIPs
      without a URDB price start from `starting_rates.json`; all CA ZIPs degrade gracefully.
- [ ] §4.1 UI rework (U1 + U2): Home Profile utilities, Current energy prices, Projection method;
      My Utility / CA Average / ACC in the Details dropdown. NEM/social extension recorded.
- [ ] Golden unchanged through Phase 7 (My Utility stays the default); full `pytest` green.
- [ ] *(post-Phase-7)* default → projection with URDB starting price (own golden diff).
- [ ] Charts + Help updated (roof geometry remains inert — default orientation).
- [ ] §6 NREL End-Use Load Profiles drive the energy balance (separate branch; own golden re-baseline).
- [ ] CLAUDE.md updated: Phase 7 closed.
