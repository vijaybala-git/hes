/* WhyWatt? HEX explainer — content + site map.
   Wording lives here, not in the SVG, so a text edit never touches a diagram.
   Loaded as a plain script (not fetched JSON) so pages also work from file://. */

/* Site map. `built:false` pages show as "soon" in the nav and drawer.
   `layers` = which parts of the system map light up in the page's "you are here" locator. */
window.SITE = [
  {grp:'Start', pages:[
    {id:'overview', t:'System map', href:'index.html', built:true},
  ]},
  {grp:'Offline pipelines', pages:[
    {id:'climate',    t:'Climate · TMYx',          href:'pipelines/climate.html',    built:true, layers:['L2']},
    {id:'pvwatts',    t:'Solar · PVWatts',         href:'pipelines/pvwatts.html',    built:true, layers:['L5']},
    {id:'urdb',       t:'Tariffs · URDB',          href:'pipelines/urdb.html',       built:true, layers:['L3']},
    {id:'projection', t:'Rate projection',         href:'pipelines/projection.html', built:true, layers:['L3']},
    {id:'nrel',       t:'Load profiles · NREL',    href:'pipelines/nrel.html',       built:true, layers:['L5']},
  ]},
  {grp:'Engine', pages:[
    {id:'loop',   t:'Two homes & the year loop', href:'engine/loop.html',           built:true, layers:['L4','L6']},
    {id:'hourly', t:'Hourly energy balance',     href:'engine/hourly-balance.html', built:true, layers:['L5']},
  ]},
  {grp:'Appliances', pages:[
    {id:'apps',    t:'All nine appliances', href:'appliances/index.html',        built:true,  layers:['L4']},
    {id:'hvac',    t:'HVAC',           href:'appliances/hvac.html',         built:true,  layers:['L4','L2'], lod:3, swap:'gas furnace → heat pump', method:'Physics · climate-driven', drives:'degree-days × heat loss', eu:'hvac_heating · hvac_cooling'},
    {id:'wh',      t:'Water heater',   href:'appliances/water-heater.html', built:true,  layers:['L4','L2'], lod:3, swap:'gas → heat-pump WH',      method:'Physics · climate-driven', drives:'gallons × water-main temp', eu:'water_heating'},
    {id:'dryer',   t:'Dryer',          href:'appliances/dryer.html',        built:true , layers:['L4'],      lod:1, swap:'gas → heat-pump dryer',   method:'Seasonal · usage-based',   drives:'loads per week', eu:'clothes_dryer'},
    {id:'cooktop', t:'Cooktop',        href:'appliances/cooktop.html',      built:true , layers:['L4'],      lod:1, swap:'gas → induction',         method:'Seasonal · usage-based',   drives:'meals per week', eu:'cooking'},
    {id:'lights',  t:'Lights & plugs', href:'appliances/lights.html',       built:true , layers:['L4'],      lod:1, swap:'always electric',         method:'Seasonal · usage-based',   drives:'floor area + bedrooms', eu:'lights_plugs'},
    {id:'vehicle', t:'Vehicle / EV',   href:'appliances/vehicle.html',      built:true , layers:['L4'],      lod:2, swap:'gasoline → EV',           method:'Schedule · miles & charging', drives:'miles per year', eu:'ev_managed'},
    {id:'pv',      t:'Solar PV',       href:'appliances/solar.html',        built:true , layers:['L5'],      lod:4, swap:'none → PV',               method:'Hourly energy balance',    drives:'sunshine at your ZIP', eu:'— (generates)'},
    {id:'battery', t:'Battery',        href:'appliances/battery.html',      built:true , layers:['L5'],      lod:4, swap:'none → Powerwall 3',      method:'Hourly energy balance',    drives:'solar surplus & TOU peak', eu:'— (stores)'},
    {id:'panel',   t:'Panel',          href:'appliances/panel.html',        built:true , layers:['L4'],      lod:1, swap:'check → upgrade',         method:'Capacity check · CapEx',   drives:'NEC 220 load calc', eu:'— (no energy)'},
  ]},
  {grp:'Outputs', pages:[
    {id:'charts', t:'Charts', href:'charts.html', built:true, layers:['L6']},
  ]},
];

/* Breakout content for each node on the system map. `pg` links a node to its page.
   `c` = code references, shown only when the reader turns on "Show code". */
window.NODES = {
  'in-home':{k:'Your input',pg:'apps',t:'Home profile',p:'Bedrooms, square feet and insulation quality. These set each appliance\'s <b>parameters</b> and nothing else: heat-loss factor UA, hot-water gallons, baseload kWh.',f:'UA = UA_base[insulation] × sq_ft / 1,800\nhot water gal/day = table[bedrooms]  (3BR = 65)',s:['DOE / ENERGY STAR occupancy proxy'],c:['src/home_config.py']},
  'in-journey':{k:'Your input',pg:'loop',t:'Journey plan',p:'For each appliance: its <b>starting state</b> (gas / electric / none), the <b>swap year</b> (or "not planning"), install cost and rebate. The "do nothing" home keeps every starting state.',c:['data/homes/journey_slots_default.json','src/journey.py']},
  'in-zip':{k:'Your input',pg:'climate',t:'ZIP code',p:'The only location input. It resolves to your CEC climate zone (weather, load profiles, solar fallback), your electric and gas utilities (tariffs), and, where harvested, a ZIP-level solar yield.',c:['data/climate/zip_to_zone.json','data/rates/zip_to_electric_utility.json','data/rates/zip_to_gas_ldc.json']},
  'in-solar':{k:'Your input',pg:'pv',t:'Solar · Battery · Panel',p:'System size (kW), install year, battery (defaults to Tesla Powerwall 3: 13.5 kWh, 89% round trip, 5 kW charge / 11.5 kW discharge), panel amps.',s:['Tesla Powerwall 3 datasheet'],c:['src/battery_defaults.py','src/panel_assessor.py']},
  'in-rate':{k:'Your input',pg:'urdb',t:'Rate plan + projection method',p:'Pick a utility plan (e.g. PG&E E-TOU-C) and how prices grow: <b>WhyWatt Conservative / Moderate / Stress</b> or <b>EIA Pacific</b>. The app starts on <b>WhyWatt Conservative</b>; the older <b>My Utility</b> (fixed %/yr) is still offered.'},
  'p-proj':{k:'Offline pipeline',pg:'projection',t:'Rate projection: how prices grow',p:'Each year\'s price is today\'s price scaled by a growth curve built offline from the CEC\'s 2025 rate forecasts. The curve sets only the <b>shape</b>; today\'s rate sets the level.',f:'rate[y] = current_rate × S[y] / S[2025]',s:['CEC 2025 IEPR rate forecasts','CPUC Avoided Cost Calculator 2024','EIA AEO 2026 Pacific'],c:['scripts/build_rate_projection.py','data/rates/projection/whywatt_rate_projection.json','src/projected_rate_source.py']},
  'p-climate':{k:'Offline pipeline',pg:'climate',t:'Climate: how cold, how hot',p:'ZIP → CEC Building Climate Zone (1–16) → monthly heating/cooling degree-days and water-main temperature from a typical-year weather file. CZ4 (San Jose) = <b>2,242 HDD / 554 CDD</b>.',f:'HDD[m] = Σ days max(0, 65°F − T_mean)\n→ monthly_hdd (12,)  monthly_cdd (12,)  inlet_°F (12,)',s:['OneBuilding TMYx 2011–2025 · 16 stations'],c:['scripts/build_climate_db.py','data/climate/tmy3_zones.json','src/climate_loader.py']},
  'p-load':{k:'Offline pipeline',pg:'nrel',t:'Load profiles: when in the day',p:'Spreads each electric appliance\'s monthly kWh across a 24-hour day, which is what makes peak vs off-peak pricing and solar self-use possible. Built from <b>NREL ResStock</b> simulations of ~150 California homes per climate zone, per end use and month. Replaces the older single-shape-per-appliance table.',f:'L[m,h] = Σ_appliances kWh[m] / days[m] × shape[zone, end_use, m, h]',s:['NREL ResStock 2025 Release 1 (AMY2018)'],c:['scripts/build_load_profiles.py','data/loads/end_use_profiles.json','src/load_profiles.py']},
  'p-solar':{k:'Offline pipeline',pg:'pvwatts',t:'Solar yield: PVWatts',p:'NREL PVWatts run offline for each climate-zone station (and, so far, 29 Silicon Valley ZIPs): monthly AC output per kW plus an hourly shape for each month.',f:'G[m,h] = kW × ac_monthly[m] / days[m] × intraday[m,h]',s:['NREL PVWatts v8 · NSRDB'],c:['scripts/build_pvwatts.py','data/solar/pvwatts_zip.json','src/solar_loader.py']},
  'p-rates':{k:'Offline pipeline',pg:'urdb',t:'Current energy rate',p:'The first source that has data wins: <b>URDB time-of-use plan</b> (tiers, fixed charge, peak window) → <b>utility EIA 2025</b> (PG&E $0.3991/kWh, $2.66/therm) → <b>EIA Pacific</b> ($0.242 / $1.99). Gas is always EIA; URDB is electric only.',s:['OpenEI URDB','EIA-861 / EIA-176','CPUC Avoided Cost Calculator 2024'],c:['scripts/build_urdb.py','data/rates/urdb_tou.json','src/rate_resolver.py','src/urdb_rates.py','src/starting_rates.py']},
  'e-homes':{k:'Engine',pg:'loop',t:'Two homes, one model',p:'<b>Do nothing</b> keeps every appliance as it is today. <b>Your journey</b> swaps appliances in the years you choose. Both see the same climate, rates and years, so the only difference between their costs is your plan.',c:['src/model.py · HESModel','src/journey.py · JourneyHome']},
  'e-year':{k:'Loop',pg:'loop',t:'Year loop',p:'One step = one year, 20 years by default. Each year sets that year\'s rates, ages every appliance, and books install costs (CapEx) in swap years.',f:'for y in 1..N:  rates[y]; journey.step(); baseline.step()',c:['src/model.py · HESModel.step']},
  'e-slot':{k:'Loop',pg:'apps',t:'The nine appliances',p:'Each appliance is the <b>baseline</b> (gas) version until its swap year, then the <b>electric</b> replacement. Every one answers the same question: <b>how much energy each month?</b> Always 12 numbers, kWh or therms, at one of four levels of detail.',f:'cost = Σ_m kWh[m]·$elec[m] + therms[m]·$gas[m]',c:['src/journey.py · DeviceSlot','src/devices/base.py · monthly_consumption()','src/devices/physics.py','src/devices/seasonal.py','src/devices/schedule.py']},
  'e-hour':{k:'Process',pg:'hourly',t:'Hourly energy balance (12 × 24)',p:'Only for the home\'s total <b>electric</b> load, once per month: a representative 24-hour day. Solar serves the home first; the battery runs <b>Self-powered</b> or <b>Cost-saving</b>, whichever is cheaper that month; the grid covers the rest; surplus is exported at the NEM 3.0 hourly value.',f:'G = solar_direct + charge + export\nL = solar_direct + discharge + grid\nbill = TOU(peak kWh, off-peak kWh) + fixed',c:['src/dispatch.py','src/journey.py','src/nbt_export.py']},
  'e-cost':{k:'Process',pg:'loop',t:'Cost + accumulate',p:'Appliance costs are summed by category, then recorded <b>once</b> per year. The solar/battery saving is subtracted, capped at that year\'s electric bill (like an annual NEM true-up).',f:'year_cost = Σ appliance costs − solar_saving\ncumulative[y] = Σ_{≤y} (year_cost + capex)'},
  'o-collect':{k:'Output',pg:'charts',t:'Year-by-year record',p:'Per-year history for both homes: cost by category, kWh, therms, gallons, CapEx events, hourly flows. All charts read from here.',c:['src/model.py · datacollector']},
  'o-charts':{k:'Output',pg:'charts',t:'Charts',p:'Cumulative cost (the headline), annual cost, CapEx timeline, rate projection curves (R.1/R.2), energy mix, hourly peak / off-peak purchases (R.6).',c:['src/ui/charts.py']},
};
