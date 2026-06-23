# WhyWatt Help — Master Content File
#
# EDITOR WORKFLOW
# ═══════════════════════════════════════════════════════════════════════════
# 1. Open the WhyWatt app and click any [?] button to open a help page
# 2. Look at the footer of the page — it shows the section number
#    e.g.  "§4 · HVAC — Heating & Cooling"
# 3. Find that section below (search for  ## §4 )
# 4. Edit the popup text and/or page content under that section
# 5. git add docs/help/help_content.md
#    git commit -m "Update §4 HVAC help text"
#    git push
# 6. A developer will run the build script and the changes appear in the
#    next release — you are done.
#
# RULES FOR EDITING
# ═══════════════════════════════════════════════════════════════════════════
# • Only edit text — do not change lines starting with @  or  ##  or  ###
# • @popup: text runs until the next blank line — keep it 2-3 sentences
# • Under each ### heading, write plain paragraphs — no special formatting
#   needed. Bullet lists with  -  work fine.
# • Do not add new ## sections — ask a developer to do that
# ═══════════════════════════════════════════════════════════════════════════

---

## §1 · Journey Planner
@file: journey.html
@keys: journey_planner
@popup: The Journey Planner lets you schedule when each gas appliance gets
  replaced with an electric alternative. A "Do Nothing" baseline runs in
  parallel so you can see the cost difference year by year over the modeled period.

### What this means for you

The Journey Planner shows what happens to your energy costs if you swap gas
appliances for electric alternatives one by one, on a schedule you choose —
compared to doing nothing for the full modeled period. You set which appliances
to replace and in which year; WhyWatt does the math.

The result is two cost curves on the same chart: Your Journey and Do Nothing.
The gap between them — and the year they cross — is your payback.

### The two scenarios

Your Journey home starts with your current appliances. In each year you've
scheduled a swap, the old appliance is replaced:

- A one-time install cost appears (minus any rebate you enter)
- From that year forward, the new appliance's operating cost replaces the old one
- All other appliances remain unchanged until their own swap year

Do Nothing runs in parallel automatically. It uses exactly the same starting
appliances — including any that are already electric, and any gas car or existing
electric car you drive today — and keeps them for the full modeled period. No swaps,
no upgrades, no rebates.

### What "swap year" means

Example: You schedule the HVAC swap in Year 3. In simulation year 3, the model
applies the install cost ($14,000 minus $3,500 rebate = $10,500 net). From year
3 onward, the heat pump's electricity cost replaces the gas furnace's gas cost.
Years 1-2 still use the gas furnace.

The calendar year label next to the slider (e.g., "Yr 3 (2028)") is derived
from the simulation start year.

### Saving, loading & resetting your plan

Everything you set up — your home profile, the appliances and swap years, prices, and the
options on every panel — is a single "settings" snapshot you can save and reuse. Three
controls live in the top bar:

- Settings → Export downloads your current setup as a small file you can keep or hand to a
  colleague or homeowner.
- Settings → Load brings a setup back. Pick one of the built-in samples (for example San Diego
  or Los Angeles), or drop in a file you exported earlier. Loading replaces every setting at
  once — anything the file doesn't mention returns to the factory default.
- Reset returns everything to the factory defaults in one click, so you can start fresh.

Loading or resetting changes the whole comparison, so the two cost curves redraw immediately.

### Key assumptions

- The simulation is deterministic — no randomness, no uncertainty bands.
  The same inputs always produce the same outputs.
- Appliance lifespans and end-of-life replacement costs are modeled where you
  set them in the device detail panels; otherwise the planned swaps drive the timeline.
- Energy consumption is based on your home profile and appliance efficiency
  ratings — not your actual meter readings.
- Rate escalation is applied each year at the rate you choose in Energy & Prices.

### Default values

- Modeled period — 20 years (Energy & Prices → Model Timeline)
- Simulation start year — 2025 (Energy & Prices → detail)
- HVAC swap — planned, Year 3 (HVAC card)
- Water heater swap — planned, Year 5 (Water Heater card)
- Dryer swap — not planned, Year 8 if enabled (Dryer card)
- Cooktop swap — not planned, Year 10 if enabled (Cooktop card)
- EV + charger — not planned, Year 2 if enabled (Transportation card)
- Baseload efficiency upgrade — not planned, Year 2 if enabled (Baseload card)

---

## §2 · Home & Climate
@file: climate.html
@keys: home_profile, zip_code
@popup: Home details — size and insulation quality — affect how much energy each
  appliance uses. WhyWatt looks up your ZIP code to find your local climate zone and drives
  all heating and cooling from that zone's real degree-day data.

### What this means for you

Your home profile tells WhyWatt how much energy your appliances use. A larger
home needs more heating and cooling. Better insulation (lower UA value) means
the HVAC works less hard. Heating and cooling are driven by your local climate,
expressed as monthly heating and cooling degree-days (HDD/CDD).

### Climate data

WhyWatt looks up your ZIP code, finds your California Energy Commission (CEC) Building Climate
Zone, and drives heating and cooling from that zone's real monthly degree-day data. The
default ZIP, 95112 (San Jose), maps to Climate Zone 4 — about 2,240 heating degree-days and
550 cooling degree-days a year. Change the ZIP and the whole climate profile changes with it.

California has 16 official climate zones, from the foggy coast to the hot Central Valley and
cold mountains. A ZIP that isn't in the lookup table falls back to Zone 4 (San Jose) with a
note on screen. The full per-zone data and its sources are documented in the Climate Data
technical reference.

### Climate trend (optional)

You can optionally layer a multi-decade warming trend on top of today's climate. Set the
Climate Trend control to a moderate (RCP 4.5) or high (RCP 8.5) emissions path and each future
year gets slightly fewer heating degree-days and more cooling degree-days, so a 20-year run
reflects warmer winters and hotter summers. "None" keeps today's typical-year climate flat.
The per-zone trend rates are documented in the Climate Data reference.

### Insulation quality

The UA value (heat loss rate, in BTU per hour per degree Fahrenheit) measures how
fast your home loses heat:

- Poor insulation: UA = 650 (older home, single-pane windows)
- Average insulation: UA = 500 (typical 1980s-2000s home)
- Good insulation: UA = 350 (well-sealed, double-pane windows)

### Key assumptions

- Climate data is a typical meteorological year (TMYx 2011-2025) — a multi-year
  statistical average for your zone, not any single year.
- Floor area and bedroom count scale the baseload (lights and plugs) consumption.

### Default values

- ZIP code — 95112 (San Jose)
- Climate zone — Zone 4 (resolved from the ZIP; display only)
- Climate trend — None
- Bedrooms — 3
- Floor area — 1,800 sq ft
- Year built — 1985
- Insulation quality — Average (UA = 500)
- Main panel size — 100 amps

### Data sources

- CEC Title 24 Building Climate Zones by ZIP Code table
- TMYx 2011-2025 weather data (climate.onebuilding.org, from NOAA's Integrated Surface Database)
- Cal-Adapt LOCA climate projections (climate trend)

---

## §3 · Energy & Prices
@file: rates.html
@keys: energy_prices, rates, chart_r1, chart_r2
@popup: Energy prices start from your utility's current rates — looked up from your ZIP using
  federal EIA data — and are projected forward each year. This panel sets electricity, gas,
  gasoline, and external EV-charging prices, plus how many years to model.

### What this means for you

WhyWatt prices electricity and gas off your own utility's current rate, looked up from your
ZIP code using federal U.S. Energy Information Administration (EIA) data, and projects them
forward each year. The escalation you choose has a large effect on the long-term totals —
higher escalation makes electrification look better because gas prices rise faster. This is
also where you set how many years the simulation covers.

The panel groups four price streams: home electricity, natural gas, gasoline, and
external (public or workplace) EV charging. Electricity and gas can each be compared
across two scenarios; gasoline and external EV charging are single shared prices that
apply to both scenarios.

### Which rate you pay

Each fuel offers three rate models:

- My Utility (default): your utility's own effective rate — total residential revenue divided
  by total residential energy — from federal EIA data. At the default San Jose ZIP this is
  Pacific Gas & Electric.
- California average: the statewide blended rate, used automatically when a ZIP can't be
  matched to a utility.
- ACC-shaped (electricity) or ACC-seasonal (gas): the CPUC Avoided Cost Calculator rate shape.

WhyWatt currently prices the three large California investor-owned utilities — PG&E, Southern
California Edison (SCE), and San Diego Gas & Electric (SDG&E). The Electricity & Gas Rates
technical reference documents the method, the per-utility numbers, and the fallback in full.

### Escalation scenarios

- Conservative: electricity +4%/yr, gas +4%/yr
- Moderate (default): electricity +7%/yr, gas +8%/yr — matches the 10-year historical average
- Stress (CEC): electricity +10%/yr, gas +12%/yr

### Base rates (PG&E, 2024 EIA)

- Electricity: $0.396/kWh (PG&E residential effective rate, EIA 2024)
- Gas: $2.31/therm (PG&E residential effective rate, EIA 2024)
- Gasoline: $4.50/gallon (California retail average)
- External EV charging: $0.25/kWh (median US public Level 2 rate)

### Key assumptions

- Rates escalate at a constant annual rate — actual utility rate changes
  may differ year to year.
- Gasoline and external EV-charging prices are shared across both comparison
  scenarios; only electricity and gas are scenario-split.
- All three large California utilities are priced (PG&E, SCE, SDG&E); a ZIP outside their
  territory falls back to the California statewide average.

### Default values

- Model timeline — 20 years
- Electricity rate model — My Utility (EIA per-utility), +7%/yr
- Gas rate model — My Utility (EIA per-utility), +8%/yr
- Gasoline price — $4.50/gal, +0%/yr
- External EV charging price — $0.25/kWh, +3%/yr
- Compare two scenarios (A vs B) — off

### Data sources

- Electricity & gas rates: U.S. EIA — Form EIA-861M (electric) and Form EIA-176 (gas), 2024
- ACC rate shape: CPUC/E3 Avoided Cost Calculator 2024
- External EV charging: published public Level 2 charging rates (2024)

---

## §4 · HVAC — Heating & Cooling
@file: hvac.html
@keys: hvac
@popup: Heating and cooling energy is calculated from monthly degree-days for
  your climate zone, your home's insulation level, and the heat pump's
  efficiency rating (COP for heating, SEER for cooling).

### What this means for you

Heating and cooling is usually the largest energy cost in a home. WhyWatt
calculates HVAC energy month by month using your climate zone's actual
heating and cooling degree-days, so the seasonal pattern is realistic —
not just an annual average.

### How we calculate it

Gas furnace heating:

  annual therms = HDD × UA × 24 / (AFUE × 100,000)

Heat pump heating:

  annual kWh = HDD × UA × 24 / (COP × 3,412)

Heat pump cooling:

  annual kWh = CDD × UA × 24 / (SEER × 1,000)  [approximate]

Where:
- HDD = heating degree-days (base 65°F) for your climate zone
- CDD = cooling degree-days (base 65°F)
- UA = home heat loss rate (BTU/hr/°F) — set by insulation quality
- AFUE = furnace efficiency, the annual fuel use efficiency (e.g., 0.80 = 80%)
- COP = coefficient of performance, heat pump heating efficiency (e.g., 3.5 means
  3.5 units of heat per unit of electricity used)
- SEER = seasonal energy efficiency ratio, the heat pump cooling efficiency rating

### Key assumptions

- Climate: heating and cooling degree-days come from your home's resolved climate zone — the
  default San Jose zone is about 2,240 HDD and 550 CDD. Change your ZIP to change the climate.
- UA classes: Poor = 650, Average = 500, Good = 350 BTU/hr/°F
- Most Bay Area homes have no central air conditioning today; adding a heat pump
  brings cooling as a clean addition, modeled as one combined install.

### Default values

- Starting state — Gas
- Heat-pump heating efficiency (COP) — 3.5
- Heat-pump cooling efficiency (SEER) — 22
- Gas furnace efficiency (AFUE) — 0.80
- Has central AC today — off
- Heat-pump size — 3.0 tons
- Swap — planned, Year 3
- Install cost — $14,000
- Rebate — $3,500
- Existing furnace age — 10 years; baseline lifespan — 20 years; replacement cost — $6,000
- Existing central AC efficiency — SEER 14; age — 7 years

### Data sources

- Climate data: TMYx 2011-2025 per CEC climate zone (climate.onebuilding.org / NOAA ISD)
- Efficiency specs: ENERGY STAR and AHRI reference data (2024)

---

## §5 · Water Heater
@file: water_heating.html
@keys: water_heater
@popup: Water heating energy depends on how much hot water your household
  uses, the temperature of incoming cold water (varies by season and
  location), and the appliance's efficiency rating (UEF).

### What this means for you

Water heating is typically the second-largest energy cost in a home after
HVAC. A heat pump water heater uses roughly one-third the energy
of a gas water heater for the same amount of hot water.

### How we calculate it

  heat load = daily_gallons × 8.33 × (120°F - inlet_temp°F)  [BTU/day]

Gas water heater:
  annual therms = heat_load × 365 / (UEF × 100,000)

Heat pump water heater:
  annual kWh = heat_load × 365 / (UEF × 3,412)

Where inlet temperature varies monthly with your climate zone, and UEF is the
uniform energy factor — the appliance's overall water-heating efficiency.

### Key assumptions

- Default daily hot water use: 65 gallons (DOE reference household)
- Scales with bedrooms: 1BR=30 gal, 2BR=50 gal, 3BR=65 gal, 4BR=75 gal, 5BR=85 gal
- Target water temperature: 120°F

### Default values

- Starting state — Gas
- Gas water-heater efficiency (UEF) — 0.65
- Heat-pump water-heater efficiency (UEF) — 3.5
- Daily hot water use — 65 gallons
- Target temperature — 120°F
- Swap — planned, Year 5
- Install cost — $2,500
- Rebate — $500
- Existing water-heater age — 10 years; baseline lifespan — 12 years; replacement cost — $1,200

### Data sources

- DOE/ENERGY STAR occupancy and hot water use data
- Monthly cold-water inlet temperatures: per CEC climate zone (TMYx 2011-2025)

---

## §6 · Clothes Dryer
@file: dryer.html
@keys: dryer
@popup: Dryer energy is based on loads per week and energy per load.
  Heat pump dryers use roughly one-third the energy of gas dryers
  for the same number of loads.

### What this means for you

Clothes dryers are a modest but steady energy user. A heat pump dryer
costs more upfront but uses significantly less electricity than a
conventional electric resistance dryer, and far less than a gas dryer
when you account for the full energy chain.

### How we calculate it

  annual energy = loads_per_week × 52 × energy_per_load

- Gas dryer: 0.22 therms/load (default, ENERGY STAR reference)
- Heat pump dryer: 1.8 kWh/load (default, ENERGY STAR reference)
- Default: 5 loads per week

### Key assumptions

- Gas dryer energy includes the gas used for heat only; the 120V motor
  electricity is negligible and not separately modeled.
- Loads per week can be adjusted in the dryer detail panel.

### Default values

- Starting state — Gas
- Gas energy per load — 0.22 therms
- Heat-pump energy per load — 1.8 kWh
- Loads per week — 5
- Swap — not planned, Year 8 if enabled
- Install cost — $1,200
- Rebate — $0
- Existing dryer age — 10 years; baseline lifespan — 15 years; replacement cost — $800

### Data sources

- ENERGY STAR clothes dryer specification and reference data (2024)

---

## §7 · Cooktop — Gas vs. Induction
@file: cooktop.html
@keys: cooktop
@popup: Cooking energy is estimated from meals cooked per week. Gas burners
  convert only about 40% of combustion energy to heat; induction
  transfers about 85% directly to the cookware.

### What this means for you

Induction cooktops are significantly more efficient than gas — not just
because electricity is cleaner, but because induction transfers heat
directly to the pan using electromagnetism, wasting very little energy.
Gas burners heat the air around the pan as much as the pan itself.

### How we calculate it

Both fuel types use the same meals-per-week input:

  annual energy = energy_per_meal × meals_per_week × 52

- Gas cooktop: 0.05 therms per meal
- Induction cooktop: 0.9 kWh per meal
- Default: 14 meals per week → about 36 therms/yr gas, or 655 kWh/yr induction

The per-meal figures already bake in the efficiency difference between the two: gas
burners lose most of their heat to the surrounding air, while induction transfers energy
directly to the pan.

### Key assumptions

- Energy is estimated per meal, not per minute of cooking — adjust meals per week in the
  cooktop detail panel to match your household.
- The oven is not separately modeled in the cooktop slot.

### Default values

- Starting state — Gas
- Gas energy per meal — 0.05 therms
- Induction energy per meal — 0.9 kWh
- Meals per week — 14
- Swap — not planned, Year 10 if enabled
- Install cost — $1,500
- Rebate — $0
- Existing cooktop age — 10 years; baseline lifespan — 20 years; replacement cost — $1,000

### Data sources

- American Gas Association (AGA) residential cooking reference data
- ENERGY STAR cooking efficiency reference

---

## §8 · Transportation — Driving, EVs & Charging
@file: ev.html
@keys: ev_charger, transportation
@popup: Transportation models your driving as gasoline miles and electric miles. Pick your
  current vehicle mix — Gas, Mixed, Electric, or None — then Your Journey can add an electric
  vehicle and a home Level 2 charger, shifting charging from costly public stations to your
  home electricity rate.

### What this means for you

Transportation captures the cars you drive and how they're fueled. WhyWatt models
two things that move money: the gasoline your gas car burns, and the electricity an
electric vehicle (EV) uses. Both scenarios start from your current driving; in Your
Journey you can add an EV and a home charger.

The core story is the home Level 2 charger. Without one, an EV charges at public or
workplace stations at a higher rate. With one, most charging shifts to your home
electricity rate, which is usually cheaper and far more convenient — and only home
charging can be offset by rooftop solar.

### The two scenarios

Do Nothing keeps your current vehicles every year: your gas car keeps burning
gasoline, and if you already drive an EV today, it keeps charging at public stations.

Your Journey, in the year you choose, can reduce or eliminate your gas miles and add
an EV charging mostly at home. The home charger is a one-time hardware cost; the car
purchase itself is not modeled.

### How we calculate it

Gas car fuel:

  annual gallons = gas_miles_per_year / MPG

EV charging energy (electricity drawn from the wall):

  annual kWh = electric_miles_per_year / efficiency_mi_per_kWh / charging_efficiency

EV charging is then split into two streams:

  home kWh     = annual kWh × percent_charged_at_home
  external kWh = annual kWh × (1 − percent_charged_at_home)

Home charging is billed at your home electricity rate; external charging is billed at
the External EV charging rate set in Energy & Prices. Only the home portion counts as
part of your home electricity bill, so only the home portion can be offset by solar.

### Existing EV today

If you already drive an EV before any home charger, set "EV miles/yr today" above zero.
That EV appears in Do Nothing too, charging entirely at external stations (there is no
home charger in the Do Nothing world). In Your Journey, installing the home charger
shifts it to mostly home charging.

### Key assumptions

- Level 2 home charging (240V) is assumed for the home charger.
- Charging efficiency is modeled explicitly: the wall energy you are billed for is
  higher than the energy that reaches the battery (the difference is lost as heat).
- Gasoline price is set in Energy & Prices; gasoline's health and climate damages are
  shown in the Social & Health panel.

### Default values

- Gas miles per year (today) — 12,000
- Fuel economy — 28 MPG
- Gas miles per year after switch — 0 (fully replaced)
- EV miles per year today — 0 (no EV today)
- EV miles per year after switch — 12,000
- EV efficiency — 3.5 miles/kWh
- Charging efficiency — 0.88 (88%)
- Percent charged at home (after charger) — 85%
- Plan EV + charger — not planned, Year 2 if enabled
- Home charger amperage — 32 A; install cost — $800; rebate — $0
- Gasoline price — $4.50/gal (Energy & Prices)
- External EV charging price — $0.25/kWh (Energy & Prices)

### Data sources

- US average vehicle miles traveled: Federal Highway Administration (FHWA) 2024
- Vehicle efficiency: EPA fuel economy data (2024)
- External charging rate: published public Level 2 charging rates (2024)

---

## §9 · Solar & Battery
@file: solar.html
@keys: solar
@popup: Solar is modeled from your system size and yield. The energy you use on-site
  saves at your retail rate; the surplus you export earns a credit. A battery lets you
  use more of your own solar instead of exporting it cheaply.

### What this means for you

Solar panels reduce your electricity bill by generating power on-site. WhyWatt models
your actual system size — number of panels times kilowatts per panel — and how much it
produces each year. Energy you use the moment it's produced saves you the full retail
rate. Energy you don't use is exported to the grid for a credit, which under today's
rules is worth much less than retail.

A home battery stores your midday solar so you can use it in the evening instead of
selling it back cheaply — raising the share of your own solar you actually consume.

### How we calculate it

System production:

  annual production kWh = system_kW × specific_yield
  system_kW = number_of_panels × kW_per_panel

Self-consumption split:

  self-used kWh = production × self_consumption_fraction
  exported  kWh = production × (1 − self_consumption_fraction)

Yearly savings:

  savings = (self-used kWh × retail_rate) + (exported kWh × export_rate)

Savings are capped at your actual electricity spending that year — solar cannot reduce
your bill below zero.

### Export credit: NEM 3.0 vs NEM 2.0

The export rate depends on your net-metering era:

- NEM 3.0 / NBT (Net Billing Tariff, today's default for new systems): exports earn the
  utility's avoided-cost value, which averages roughly $0.06/kWh — far below retail. This
  is why self-consumption and batteries matter so much under the current rules.
- NEM 2.0 (older systems): exports earn the retail rate minus a small non-bypassable
  charge (about $0.025/kWh).

### Key assumptions

- Self-consumption fraction defaults to 80% with a battery and 35% without — you can
  adjust it directly. The battery default suggests 80% when enabled.
- Degradation, shading, and panel orientation are not separately modeled; specific
  yield (kWh per kW per year) captures local production — roughly 1,400 on the foggy
  coast to 1,650 inland.
- You enter the total installed system cost from a contractor quote, minus any rebate.

### Default values

- Add solar — off
- Install year — 1
- Number of panels — 15
- Kilowatts per panel — 0.42 (about a 6.3 kW system)
- Specific yield — 1,500 kWh per kW per year (about 9,450 kWh/yr)
- Battery storage — on, 13.5 kWh
- Self-consumption — 80%
- Net-metering mode — NEM 3.0 / NBT
- Non-bypassable charge (NEM 2.0) — $0.025/kWh
- Total installed cost — $30,000
- Rebate — $0

### Data sources

- Typical residential solar sizing and yield: NREL PVWatts tool
- NEM 3.0 avoided-cost export values: CPUC Avoided Cost Calculator (2024)
- Non-bypassable charge: PG&E NEM 2.0 tariff

---

## §10 · Baseload — Lights & Plugs
@file: baseload.html
@keys: baseload
@popup: Baseload covers lights, outlets, refrigerator, and other
  always-on electricity uses. It scales with floor area and the number of
  bedrooms using DOE and EIA reference data.

### What this means for you

Baseload is the electricity your home uses regardless of your heating,
cooling, cooking, or EV decisions — refrigerator, lighting, TV, computer,
small appliances, and similar loads. It's always present and always electric.

### How we calculate it

  annual kWh = (floor_area_sqft × 0.45) + (bedrooms × 200) + always_on_constant

- 0.45 kWh per square foot per year (EIA RECS 2020, California)
- 200 kWh per bedroom per year (occupancy proxy)
- always-on constant: 500 kWh/yr by default — covers a home office, networking gear,
  and other loads that don't scale with home size

Example: an 1,800 sq ft, 3-bedroom home →
(1,800 × 0.45) + (3 × 200) + 500 = 1,910 kWh/yr.

A baseload efficiency upgrade (LED lighting, efficient appliances) lowers the always-on
constant — from 500 down to 300 kWh/yr by default.

### Key assumptions

- 3-bedroom home is the DOE reference household
- Baseload is always electric — gas is not used for lights or plugs

### Default values

- Always-on constant (before upgrade) — 500 kWh/yr
- Always-on constant (after upgrade) — 300 kWh/yr
- Efficiency upgrade — not planned, Year 2 if enabled
- Install cost — $400
- Rebate — $0

### Data sources

- DOE/ENERGY STAR residential energy consumption reference data
- RECS (Residential Energy Consumption Survey) 2020

---

## §11 · Electrical Panel & Panel Upgrade
@file: panel.html
@keys: panel_upgrade, panel_assessment
@popup: The Estimated Electrical Load uses the NEC Article 220 method to size
  your service from your home's square footage and the electric appliances in
  your journey. A panel upgrade may be needed when high-draw appliances (heat
  pump, EV charger, induction) push an older 100A panel past its limit.

### What this means for you

Most pre-1980s homes have 100-amp electrical service. Adding a heat pump,
an EV charger, and an induction range can push a 100A panel to or beyond its
limit. A 200A panel upgrade costs $3,000-$8,000 and requires a licensed
electrician and utility coordination.

The good news: California has active programs to help — TECH+ rebates,
simplified permit processes, and utility co-funding in some territories.

### How we estimate panel load (NEC Article 220)

This is the same calculation an electrician uses to size a service entrance,
using the NEC (National Electrical Code) Article 220 standard method:

Step 1 — General load (with demand factor):
  general VA = (floor area sq ft × 3) + 3,000 + 1,500
  First 10,000 VA at 100%, remainder at 40%

Step 2 — Named appliances at nameplate (no demand factor):
  HVAC: larger of heating or cooling VA
  EV charger: nameplate × 1.25 (continuous load rule)
  Dryer: max(5,000 VA, nameplate)
  Range/cooktop: 8,000 VA (NEC Table 220.55 allowance)
  Water heater: nameplate VA

Step 3 — Service amperage:
  total VA / 240V = required service amps

### Panel size guide

- 100A panel: 24,000 VA capacity — typical pre-1980 home
- 150A panel: 36,000 VA capacity — some 1980s-90s homes
- 200A panel: 48,000 VA capacity — standard new construction

### California programs (as of 2025)

- TECH+ Clean Energy Rebate: up to $2,500 for panel upgrades
- PG&E Rule 20: utility-funded service upgrade in some cases
- AB 3236: simplified permit process for EV-related panel work

This estimate is for planning purposes only. A licensed electrician
must verify before any work is performed.

### Default values

- Main panel size — 100 amps
- Panel load method — Optional (NEC 220.82)
- EV charger nameplate — 32 A; induction — 40 A; heat-pump water heater — 15 A; dryer — 30 A
- Plan 200A upgrade — not planned, Year 1 if enabled
- Upgrade cost — $3,000
- Rebate — $0

### Data sources

- NEC Article 220 Standard Method for Dwelling Units
- CEC and CPUC panel upgrade program documentation (2024-2025)

---

## §12 · ACC — Avoided Cost of Carbon
@file: acc.html
@keys: chart_r3, chart_r4, chart_r5
@popup: The ACC (Avoided Cost Calculator) seasonal shape shows how the
  effective electricity rate varies by month under the CPUC's
  avoided-cost framework. Summer peak hours carry the highest rate.

### What this means for you

The Avoided Cost Calculator (ACC) is a CPUC/E3 framework that estimates
the true value of electricity at different times of day and year, based
on what it would cost to avoid generating that electricity from fossil fuels.
Summer afternoon peak hours are the most expensive — that's when gas peaker
plants run and carbon costs are highest.

WhyWatt uses the ACC seasonal shape to apply a more realistic monthly rate
pattern to electricity costs, rather than a flat annual average. The same
avoided-cost values also set the export credit for solar under NEM 3.0.

### How the ACC shape works

The ACC produces a ratio for each month (e.g., July = 1.35× average,
January = 0.78× average). WhyWatt multiplies the base electricity rate
by these monthly ratios to get a seasonal rate profile.

This affects the cost of running appliances differently across the year —
air conditioning in July costs more per kWh than heating in January.

### Key assumptions

- ACC shape is from E3's 2024 Avoided Cost Calculator, Electric CZ12 (PG&E territory)
- ACC-shaped rates apply when you choose the ACC option for electricity or gas
- The base rate (before ACC adjustment) is still the PG&E E-1 tariff

### Default values

- Electricity rate model — CAGR Flat (switch to ACC-Shaped in Energy & Prices)
- Rate-shape preview year — Year 1 (chart slider)

### Data sources

- CPUC/E3 Avoided Cost Calculator 2024 (E3 Energy and Environmental Economics)
- CPUC Resolution E-5328 (November 2024)

---

## §13 · Social & Health Cost of Gas & Gasoline
@file: social_cost.html
@keys: social_cost
@popup: These costs represent damage to public health and the climate caused by
  burning natural gas and gasoline — costs that do not appear on your bill but
  are real and quantified by official sources.

### What this means for you

Your utility bill and the price at the pump show only the market price of fuel.
They do not show the cost that combustion imposes on public health (air quality
damage, respiratory illness) and on the global climate (CO2 and methane emissions).

For natural gas, at the default settings these hidden costs total about $2.30 per
therm — nearly equal to the $2.31/therm market price you actually pay. For gasoline, the
default hidden cost is about $2.44 per gallon on top of the pump price. This panel is
informational: advocates can use it to show homeowners the full picture.

### Natural gas — climate cost ($1.07/therm default)

Based on EPA 2023 Social Cost of CO2 ($190/tonne CO2) applied to the EIA
combustion emission factor (5.3 kg CO2/therm), plus an allowance for
upstream methane leakage at a 2% pipeline leakage rate.

Slider range: $1.00 (EPA SC-CO2 only, no leakage) to $2.00 (high leakage + high scenario).

### Natural gas — health cost ($1.23/therm default)

Based on CPUC Decision D.24-07-015 (July 2024), using E3's "Quantifying
Air Quality Impacts of Decarbonization" report. Computed using the EPA
COBRA tool with California population and pollution data. Covers outdoor
air quality damage (NO2, PM2.5) from building gas combustion.

Slider range: $0.50 (conservative/skeptical) to $2.00 (includes indoor
air quality — NO2 and benzene exposure not yet in the CPUC figure).

### Gasoline externalities

Gasoline combustion in your gas car carries the same kinds of hidden costs:

- Climate cost: $1.69/gallon default — EPA Social Cost of CO2 applied to the
  combustion emission factor of about 8.89 kg CO2 per gallon.
- Health cost: $0.75/gallon default — outdoor air quality damage from tailpipe
  pollution.

Both are added to the modeled gasoline cost only when their checkboxes are on.

### Important caveats

- The EPA 2023 SC-CO2 figure has uncertain federal regulatory status as of 2025-2026.
  California's CPUC adopted the lower IWG 2021 value ($51/tonne = $0.27/therm)
  for regulatory proceedings.
- The health adders cover outdoor air quality only — indoor health effects
  from gas stove NO2 and benzene are additional and not yet officially monetized.

### Default values

- Include natural-gas climate cost — on, $1.07/therm
- Include natural-gas health cost — on, $1.23/therm
- Include gasoline climate cost — on, $1.69/gal
- Include gasoline health cost — on, $0.75/gal

### Data sources

- EPA Social Cost of Greenhouse Gases, Final Report (December 2023)
- IWG Technical Support Document: Social Cost of Carbon (February 2021)
- CPUC Decision D.24-07-015 (July 2024)
- E3: Quantifying Air Quality Impacts of Decarbonization (2022)
- EIA emission factors: 5.306 kg CO2/therm gas, ~8.89 kg CO2/gal gasoline (EPA/EIA 2024)

---

## §14 · Charts Reference
@file: charts.html
@keys: chart_jc1, chart_jc2, chart_jc3, chart_jc4, chart_jc5, chart_jc6, chart_eu1, chart_eu2, chart_eu3, chart_eu4, chart_eu6, chart_eu7
@popup: Charts are organized into three groups — Journey Costs (JC),
  Energy Use (EU), and Rates (R). Pick any chart from the dropdown above
  each chart panel; the code (JC.1, EU.7, R.3 …) appears in the chart's header.

### Journey Costs (JC)

JC.1 · Cumulative Energy Costs
Adds up every year's energy bill from year 1 onward, for Your Journey vs. Do Nothing. The
crossover — where the journey line drops below do-nothing — is your payback year, marked on
the chart. When social and health costs are switched on, dotted lines add those hidden costs.
Often the most compelling chart to show a homeowner.

JC.2 · Annual Cost by Year
The total energy bill for each single year — electricity, gas, gasoline, and external EV
charging — as side-by-side bars for the two scenarios. The gap in any year is your saving or
extra cost that year; social and health costs stack on top when enabled.

JC.3 · Cost Breakdown by Category
A stacked view of cumulative cost split by category — heating, cooling, water heating,
baseload, cooking, and transportation — with gas and gasoline social costs layered on top when
enabled. Use the scenario toggle to switch between Your Journey and Do Nothing.

JC.4 · Equipment Replacements (CapEx)
The one-time install costs of each appliance, colored by device and plotted in the year they
happen — Your Journey (solid bars) beside the Do Nothing wear-out replacements (hatched). A box
totals the net capital difference over the period, in today's dollars.

JC.5 · Journey Timeline
A year-by-year map of your journey: each appliance swap and add-on (solar, panel, EV charger)
is a marker in the year it happens, with its net cost. Do Nothing wear-out replacements appear
below the rail so you can compare the two paths.

JC.6 · Estimated Electrical Load
Your home's estimated electrical service load, in amps, rising as each electric appliance comes
online — against your panel's capacity line. It uses the NEC (National Electrical Code) Article
220 method to flag whether, and when, a panel upgrade is needed.

### Energy Use (EU)

EU.1 · Home Energy Cost by Device
A stacked area of annual home-energy cost by appliance, year over year. It counts only energy
on your home meter — gasoline and public EV charging are excluded. Toggle scenarios to see
which swaps cut cost most.

EU.2 · Home Energy Use by Device
The same stacked view in energy terms — kilowatt-hour-equivalent, with gas converted at 29.3
kWh per therm. Like the cost view, it counts only what lands on your home meter.

EU.3 · Annual kWh by Device
Actual electricity used by each appliance per year, in kilowatt-hours, as stacked bars. For an
electric vehicle this counts home charging only.

EU.4 · Annual Gas by Device
Natural gas used by each appliance per year, in therms, as stacked bars. As gas appliances are
swapped for electric ones, these bars shrink toward zero.

EU.6 · Energy Mix Timeline
A stacked view of where your home's energy comes from each year, in kilowatt-hour-equivalent
terms: natural gas, gasoline, grid electricity, your own solar, and external EV charging. It
tells the decarbonization story at a glance — gas shrinking, solar growing.

EU.7 · HVAC Monthly Energy
The heat pump's energy across the twelve months of the HVAC-swap year, split into heating
(lower bars) and cooling (stacked on top). Do Nothing gas heating is shown in
kilowatt-hour-equivalent (29.3 kWh per therm) so a gas furnace and a heat pump sit on the same
axis; cooling is omitted for homes that have none. Switch the scenario toggle to contrast a gas
furnace against a heat pump month by month.

### Rates (R)

R.1 · Electric CAGR Projection
Your electricity price projected forward each year from your utility's current rate, using the
escalation you chose. A second dashed line appears when you compare two scenarios.

R.2 · Gas CAGR Projection
Your natural-gas price projected forward each year from your utility's current rate, using the
escalation you chose. A second dashed line appears when you compare two scenarios.

R.3 · ACC Electrical Rate Projection
Your electricity price projected forward each year along the selected rate model's
annual-average line, with the CPUC Avoided Cost Calculator's off-peak-to-peak hourly band shaded
around it. A second dashed line appears when you compare two scenarios.

R.4 · ACC Gas Rate Projection
Your natural-gas price projected forward each year along the selected rate model's
annual-average line, with the CPUC Avoided Cost Calculator's summer-to-winter seasonal band
shaded around it. A second dashed line appears when you compare two scenarios.

R.5 · ACC Electrical Rate Shape
A heatmap of how the effective electricity rate varies by hour of day and by month under the
CPUC Avoided Cost Calculator. Summer afternoons and winter evenings carry the highest avoided
cost.

### Default values

- Left chart — Cumulative Energy Costs (JC.1)
- Right chart — Journey Timeline (JC.5)
- Device chart scenario toggle — Your Journey

---

## §15 · About WhyWatt
@file: about.html
@keys:
@popup: WhyWatt is a home electrification cost simulator for California
  community advocates, showing the long-term cost of an electrification
  journey vs. doing nothing.

### What WhyWatt is

WhyWatt is a home electrification cost simulator for California community
advocates. It shows the long-term cost of an electrification journey —
replacing gas appliances with electric alternatives over time, and switching
from gasoline to an electric vehicle — compared to doing nothing.

The primary audience is electrification advocates running sessions with
homeowners: people who want to show, with real numbers, what switching to
heat pumps, induction, and electric vehicles actually costs and saves.

### What it models

WhyWatt simulates a single home running two scenarios in parallel:
- Your Journey — you choose which appliances to swap, and in which year
- Do Nothing — all current appliances and vehicles stay in place for the modeled period

For each year WhyWatt calculates energy consumption, utility and fuel costs with
escalation, capital expenditure for appliance swaps, and solar savings.

### Data sources

- Electricity & gas rates: U.S. EIA per-utility effective rates (2024) — PG&E, SCE, SDG&E
- PG&E example: $0.396/kWh electricity, $2.31/therm gas (EIA 2024)
- ACC rate shape: CPUC/E3 Avoided Cost Calculator 2024
- Climate data: TMYx 2011-2025 per CEC Building Climate Zone (climate.onebuilding.org / NOAA)
- Appliance efficiency: ENERGY STAR and AGA reference data (2024)
- Bedroom scaling: DOE/ENERGY STAR occupancy proxy

### Limitations

- Appliance end-of-life replacement is modeled where you set ages and lifespans;
  otherwise the timeline follows your scheduled swaps
- Income-qualified rebate programs are coming in a future release
- Monte Carlo uncertainty bands are coming in a future release
- Three California investor-owned utilities are priced (PG&E, SCE, SDG&E); a ZIP outside
  their territory falls back to the California statewide average

### Disclaimer

WhyWatt is a planning tool, not a financial guarantee. Actual costs depend
on your specific appliances, usage patterns, utility rate changes, local
rebate availability, and many other factors. Consult a licensed contractor
before making purchasing decisions. Energy rate projections are scenarios,
not predictions.

### Team

Developed with support from the Electrification Collaboration (ECHo) —
helping California communities make the switch.

## §16 · Climate Data
@file: climate_data.html
@keys: climate_data
@popup: WhyWatt's heating and cooling estimates are driven by real local climate data —
  monthly heating and cooling degree-days for your CEC Building Climate Zone, derived from
  NOAA weather records. This Technical Reference documents exactly what we use and how.

### What data we use

Your home's heating and cooling energy depends heavily on local climate. WhyWatt looks up
your ZIP code, finds your California Energy Commission (CEC) Building Climate Zone, and uses
that zone's monthly climate profile to drive the HVAC and water-heater calculations.

For each of the 16 CEC zones we store three monthly profiles — one value per calendar month:

- Heating Degree-Days (HDD, base 65°F) — how cold the winters are
- Cooling Degree-Days (CDD, base 65°F) — how hot the summers are
- Cold-water inlet temperature — how much the water heater must warm incoming water

### Where it comes from

The weather data is the TMYx series from climate.onebuilding.org, the standard public
repository for building-energy weather files, maintained by the authors of the EnergyPlus
weather format. A TMYx file is a Typical Meteorological Year synthesized from NOAA's
Integrated Surface Database (ISD) of hourly observations, using the industry-standard Sandia
method. It represents a typical year — a long-run average — not any single anomalous year.

We use one reference weather station per CEC zone, at the latest available vintage
(TMYx 2011-2025). The raw weather files are downloaded once and stored in the project with
SHA-256 checksums, so the published numbers can never change unexpectedly.

The ZIP-code-to-zone mapping itself is the California Energy Commission's official
"Building Climate Zones by ZIP Code" table — roughly 2,700 California ZIP codes — snapshotted
with a checksum alongside the weather files. A ZIP not found in the table falls back to CZ4
(San Jose) with an on-screen notice.

### How we compute it

Degree-days use the standard NOAA daily-mean definition at a 65°F base:

    For each day:  HDD = max(0, 65 - daily_mean_°F)
                   CDD = max(0, daily_mean_°F - 65)
    Monthly value = sum over that month's days

Cold-water inlet temperature uses the Burch & Christensen (2007) correlation — the same model
used by NREL's BEopt and ResStock — driven by each site's annual mean air temperature and its
seasonal range.

### The 16 climate zones

@include: _generated/climate_zones_table.md

### A note on accuracy

These are typical-year averages, not a forecast for any specific year. Real weather varies — a
cold snap or heat wave pushes a single year above or below these figures. For a long-run cost
comparison, which is what WhyWatt models, typical-year climate is the right basis, and it is
the same class of data used by Title 24 energy-code compliance tools.

One consequence worth noting: a hot inland zone can have fewer heating degree-days than a mild
coastal one. Fresno, for example, has hotter summers but a shorter heating season than San
Jose, so it shows lower HDD and far higher CDD.

### Climate trend

WhyWatt can optionally layer a multi-decade warming trend on top of the static climate (the
Climate Trend control in the Home Profile). Each modeled year, heating degree-days are scaled
down and cooling degree-days up by a small compounding rate, so a 20-year run in an inland or
mountain zone reflects warmer winters and hotter summers rather than a frozen present.

The trend rates are per-zone annual growth rates (CAGR), fitted by log-linear regression to
Cal-Adapt — the CEC/LBNL official California climate-projection dataset. We use the LOCA
32-model ensemble average of annual heating and cooling degree-days over 2025-2054. Two
scenarios are offered: RCP 4.5 (moderate emissions) and RCP 8.5 (high emissions). "None" turns
the trend off and reproduces the static typical-year climate exactly. As with the weather
files, the raw Cal-Adapt series are snapshotted in the project for reproducibility.

@include: _generated/climate_trend_table.md

## §17 · Technical Reference — Electricity & Gas Rates
@file: rates_reference.html
@keys: rates_reference
@popup: WhyWatt prices your bills off your actual utility's residential rate — not a
  statewide average — using federal EIA data. This Technical Reference documents the
  sources, the effective-rate method, and the per-utility numbers we use.

### What rates we use

Your long-term cost depends on the price you pay per unit of energy. WhyWatt looks up your
utility from your ZIP code and prices electricity and natural gas off that utility's own
residential rate. A Pacific Gas & Electric home is priced at PG&E's rate, a Southern
California Edison home at SCE's — not a blended California average that mixes in cheaper
municipal utilities.

We store one residential rate per utility, per fuel:

- Electricity — dollars per kilowatt-hour ($/kWh)
- Natural gas — dollars per therm ($/therm)

### Where it comes from

The rates are from the U.S. Energy Information Administration (EIA), the federal statistical
agency for energy. Two authoritative datasets are used, each snapshotted in the project with
SHA-256 checksums so the published numbers can never change unexpectedly:

- Electricity — Form EIA-861M, the monthly utility report. We use each utility's residential
  revenue and sales for the base year.
- Natural gas — Form EIA-176, the annual report of every gas distribution company, queried
  through EIA's public NGQS system. We use each company's residential revenue and volume.

Both are residential-sector only, and the rate basis is the full base year (2024).

### How we compute the rate — the effective rate

Rather than copying a single line from a tariff sheet, we compute the effective rate that
households actually pay: total residential revenue divided by total residential energy.

    Electricity:  $/kWh   = residential revenue ($) ÷ residential sales (kWh)
    Natural gas:  $/therm  = residential revenue ($) ÷ residential volume (therms)
                  (gas volume is reported in Mcf; 1 Mcf = 10.37 therms)

This matters: the effective rate folds in fixed monthly service charges, tier structures, and
riders that a quoted commodity rate leaves out. For PG&E gas, the effective rate is about
$2.32/therm — higher than the commodity tariff alone — because it includes the fixed charge
every customer pays. The effective rate is the honest "what shows up on the bill."

### Per-utility rates vs. the statewide average

@include: _generated/rate_tables.md

The spread is large and one-directional for our primary audience: a PG&E customer pays about
24% more for electricity and 25% more for gas than the California blend. Using the statewide
average would understate a Bay Area bill substantially. That is why per-utility is the default
and the statewide average is only a fallback.

### Default, fallback, and manual override

WhyWatt resolves your utility from your ZIP code automatically. If the ZIP cannot be matched
to a known utility — an unlisted municipal utility, or a ZIP that maps to several utilities
with no clear choice — it falls back to the California statewide average and says so on screen.
You can always pick a utility manually or enter your own rate from a recent bill.

### How rates grow over time

The base-year rate is escalated into the future using a compound annual growth rate (CAGR)
fitted to the last decade of EIA history for that state — roughly 7%/year for both fuels in
California. You can override this with the conservative / moderate / stress escalation
scenarios or your own percentage; the base year and source data stay the same.

### A note on seasonality and accuracy

WhyWatt applies a single rate across all twelve months. Seasonal swings in your bill come from
seasonal energy use — more heating in winter, more cooling in summer — which the simulation
already models month by month. We deliberately do not also vary the price by month: the raw
monthly effective rate is distorted by tiered pricing and billing true-ups, and layering it on
top of seasonal consumption would double-count the same effect. A future version may add a
clean seasonal price shape for natural gas.

These are real, recent, utility-specific rates from federal data — a substantial improvement
over a single hand-entered number — but they are an annual average, not your exact tariff. For
a precise bill, use the manual override with figures from your own statement.
