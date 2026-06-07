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
  parallel so you can see the cost difference year by year over 20 years.

### What this means for you

The Journey Planner shows what happens to your energy costs if you swap gas
appliances for electric alternatives one by one, on a schedule you choose —
compared to doing nothing for 20 years. You set which appliances to replace
and in which year; WhyWatt does the math.

The result is two cost curves on the same chart: Your Journey and Do Nothing.
The gap between them — and the year they cross — is your payback.

### The two scenarios

Your Journey home starts with your current appliances. In each year you've
scheduled a swap, the old appliance is replaced:

- A one-time install cost appears (minus any rebate you enter)
- From that year forward, the new appliance's operating cost replaces the old one
- All other appliances remain unchanged until their own swap year

Do Nothing runs in parallel automatically. It uses exactly the same starting
appliances — including any that are already electric — and keeps them for the
full 20 years. No swaps, no upgrades, no rebates.

### What "swap year" means

Example: You schedule the HVAC swap in Year 3. In simulation year 3, the model
applies the install cost ($14,000 minus $3,500 rebate = $10,500 net). From year
4 onward, the heat pump's electricity cost replaces the gas furnace's gas cost.
Years 1-2 still use the gas furnace.

The calendar year label next to the slider (e.g., "Yr 3 (2028)") is derived
from the current calendar year when you run the simulation.

### Key assumptions

- The simulation is deterministic — no randomness, no uncertainty bands.
  The same inputs always produce the same outputs.
- Appliance lifespans and end-of-life replacement costs are not modeled beyond
  your planned swaps.
- Energy consumption is based on your home profile and appliance efficiency
  ratings — not your actual meter readings.
- Rate escalation is applied uniformly each year at your chosen scenario rate.

---

## §2 · Home & Climate
@file: climate.html
@keys: home_profile, zip_code
@popup: Home details — size, insulation quality, and location — affect how much
  energy each appliance uses. Your ZIP code sets the climate zone, which drives
  the heating and cooling calculations.

### What this means for you

Your home profile tells WhyWatt how much energy your appliances use. A larger
home needs more heating and cooling. Better insulation (lower UA value) means
the HVAC works less hard. Your ZIP code determines which California climate zone
your home is in, which sets the monthly heating and cooling degree-days.

### Climate zones

California uses 16 official CEC Building Climate Zones for building energy codes.
Every HVAC permit and utility rebate program uses these zones. WhyWatt maps your
ZIP code to the correct zone automatically.

- CZ1 Arcata — cool foggy north coast
- CZ3 Oakland — mild Bay Area coast
- CZ4 San Jose — warm Bay Area interior
- CZ12 Sacramento — hot central valley
- CZ13 Fresno — hot/dry central valley
- CZ16 Blue Canyon — mountain/snow

### Insulation quality

The UA value (BTU/hr/°F) measures how fast your home loses heat:

- Poor insulation: UA = 650 (older home, single-pane windows)
- Average insulation: UA = 500 (typical 1980s-2000s home)
- Good insulation: UA = 350 (well-sealed, double-pane windows)

### Key assumptions

- Climate data comes from NOAA TMY3 (1991-2005 composite) — a multi-year
  statistical average, not any single year.
- Floor area and bedroom count scale the baseload (lights and plugs) consumption.

### Data sources

- CEC Title 24 ZIP-to-climate-zone table
- NOAA TMY3 station data (NREL)

---

## §3 · Energy Rates
@file: rates.html
@keys: energy_prices, rates, chart_r1
@popup: Energy prices are based on current PG&E tariff rates with a projected
  escalation rate applied each year. You can adjust the escalation scenario
  in the Rate details panel.

### What this means for you

WhyWatt uses real PG&E tariff rates as the starting point and projects them
forward using three escalation scenarios. The scenario you choose has a large
effect on the 20-year cost totals — higher escalation makes electrification
look better because gas prices rise faster.

### Escalation scenarios

- Conservative: electricity +4%/yr, gas +4%/yr
- Moderate (default): electricity +7%/yr, gas +8%/yr — matches 10-year historical average
- Stress (CEC): electricity +10%/yr, gas +12%/yr

### Base rates (2025)

- Electricity (PG&E E-1): $0.386/kWh (Cal Advocates Q2 2025 report)
- Gas (PG&E G-1): $2.08/therm (PG&E Advice Letter 5014-G1, Jan 2025)

### Key assumptions

- Rates escalate at a constant annual rate — actual utility rate changes
  may differ year to year.
- All homes in the simulation use PG&E rates. Other California utilities
  (SCE, SDG&E) will be supported in a future release.

### Data sources

- PG&E E-1 tariff: Cal Advocates Q2 2025 report
- PG&E G-1 tariff: PG&E Advice Letter 5014-G1, January 2025
- Historical CAGR: EIA retail electricity and gas price series, 2014-2024

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

  annual kWh = HDD × UA × 24 / (COP × 1000)

Heat pump cooling:

  annual kWh = CDD × UA × 24 / (SEER/1000 × 1000)  [approximate]

Where:
- HDD = heating degree-days (base 65°F) for your climate zone
- CDD = cooling degree-days (base 65°F)
- UA = home heat loss rate (BTU/hr/°F) — set by insulation quality
- AFUE = furnace efficiency (e.g., 0.80 = 80%)
- COP = heat pump heating efficiency (e.g., 3.5 means 3.5x more heat than electricity used)
- SEER = heat pump cooling efficiency rating

### Key assumptions

- Bay Area default: 1,910 HDD and 340 CDD (NOAA TMY3, San Jose Mineta)
- UA classes: Poor = 650, Average = 500, Good = 350 BTU/hr/°F
- Default heat pump: COP 3.5 heating, SEER 22 cooling
- Default gas furnace: AFUE 0.80

### Data sources

- Climate data: NOAA TMY3 (NREL), 1991-2005 composite
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
HVAC. A heat pump water heater (HPWH) uses roughly one-third the energy
of a gas water heater for the same amount of hot water.

### How we calculate it

  heat load = daily_gallons × 8.34 × (120°F - inlet_temp°F)  [BTU/day]

Gas water heater:
  annual therms = heat_load × 365 / (UEF × 100,000)

Heat pump water heater:
  annual kWh = heat_load × 365 / (UEF × 3,412)

Where inlet temperature varies monthly with your climate zone.

### Key assumptions

- Default daily hot water use: 65 gallons (DOE reference household)
- Scales with bedrooms: 1BR=30 gal, 2BR=50 gal, 3BR=65 gal, 4BR=75 gal, 5BR=85 gal
- Default gas UEF: 0.65
- Default HPWH UEF: 3.5
- Target water temperature: 120°F

### Data sources

- DOE/ENERGY STAR occupancy and hot water use data
- Monthly inlet water temperatures: NOAA TMY3

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

### Data sources

- ENERGY STAR clothes dryer specification and reference data (2024)

---

## §7 · Cooktop — Gas vs. Induction
@file: cooktop.html
@keys: cooktop
@popup: Cooking energy is estimated from daily cook time. Gas burners
  convert only about 40% of combustion energy to heat; induction
  transfers about 85% directly to the cookware.

### What this means for you

Induction cooktops are significantly more efficient than gas — not just
because electricity is cleaner, but because induction transfers heat
directly to the pan using electromagnetism, wasting very little energy.
Gas burners heat the air around the pan as much as the pan itself.

### How we calculate it

Cook time model (both fuel types use the same daily cook time input):

Induction:
  annual kWh = cook_hours/day × 1.5 kW × 365 × 0.85

Gas:
  annual therms = cook_hours/day × 7,500 BTU/hr × 365 / 100,000 / 0.40

Where:
- 1.5 kW = average power of two active induction burners
- 0.85 = induction efficiency factor (accounts for warm-up overhead)
- 7,500 BTU/hr = average output of two active gas burners
- 0.40 = gas burner thermal efficiency (fraction reaching the cookware)

Default: 1 hour 0 minutes per day → ~466 kWh/yr induction, ~68 therms/yr gas.

### Key assumptions

- Two burners active on average during cooking sessions
- Oven is not separately modeled in the cooktop slot

### Data sources

- American Gas Association (AGA) residential cooking reference data
- ENERGY STAR cooking efficiency reference

---

## §8 · EV Charger
@file: ev.html
@keys: ev_charger
@popup: EV charging energy is estimated from your average daily miles
  driven and your vehicle's efficiency. Level 2 home charging
  (240V) is assumed.

### What this means for you

Adding an EV to an electrified home increases electricity use but
eliminates gasoline costs entirely. WhyWatt models the electricity
cost of home charging — it does not currently model gasoline savings
(the financial case for an EV is in the vehicle purchase decision,
not the home energy decision).

### How we calculate it

  annual kWh = miles_per_day × 365 / vehicle_efficiency (mi/kWh)

Vehicle efficiency presets:
- Efficient (e.g., Tesla Model 3 LR): 4.5 mi/kWh
- Average (e.g., F-150 Lightning): 3.5 mi/kWh
- Less efficient (large SUV/truck): 2.8 mi/kWh

Default: 37 miles/day (US average vehicle miles traveled), average efficiency.

### Key assumptions

- Level 2 charger (240V, 32A) assumed — most common home installation
- Charging efficiency loss (~15%) is absorbed into the vehicle efficiency figure
- The EV charger slot models home charging only, not workplace or public charging

### Data sources

- US average VMT: Federal Highway Administration (FHWA) 2024
- Vehicle efficiency: EPA fuel economy data (2024)

---

## §9 · Solar & Battery
@file: solar.html
@keys: solar
@popup: Solar savings are modeled as a reduction in net electricity
  purchased from the grid each year. Battery storage shifts solar
  generation to evening hours.

### What this means for you

Solar panels reduce your electricity bill by generating power on-site.
WhyWatt models solar as a percentage of your annual electricity use that
you no longer buy from the grid. Battery storage lets you use solar energy
at night instead of sending it back to the grid at a lower NEM export rate.

### How we calculate it

Solar savings are applied as a coverage percentage of total annual
electricity consumption:

  annual_savings_kWh = total_electricity_kWh × solar_coverage_pct / 100
  annual_savings_$ = annual_savings_kWh × electricity_rate

Battery is modeled as an incremental improvement to coverage — shifting
self-consumption from daytime to evening, improving the effective rate
at which solar offsets purchased electricity.

### Key assumptions

- Solar coverage percentage is user-set (e.g., 80% means solar covers 80%
  of your annual electricity use)
- Degradation, shading, and panel orientation are not separately modeled
- NEM (net energy metering) export credit is not separately calculated —
  coverage percentage captures the net effect

### Data sources

- Typical residential solar system sizing: NREL PVWatts tool
- Battery storage modeling: simplified from CEC self-consumption analysis

---

## §10 · Baseload — Lights & Plugs
@file: baseload.html
@keys: baseload
@popup: Baseload covers lights, outlets, refrigerator, and other
  always-on electricity uses. It scales with the number of
  bedrooms using DOE occupancy data.

### What this means for you

Baseload is the electricity your home uses regardless of your heating,
cooling, cooking, or EV decisions — refrigerator, lighting, TV, computer,
small appliances, and similar loads. It's always present and always electric.

### How we calculate it

  annual kWh = bedroom_scale × (1,200 kWh/yr + constant_always_on)

Bedroom scaling (DOE/ENERGY STAR occupancy proxy):
- 1 bedroom: 0.50× → 600 kWh/yr
- 2 bedrooms: 0.83× → 996 kWh/yr
- 3 bedrooms: 1.00× → 1,200 kWh/yr (reference)
- 4 bedrooms: 1.17× → 1,404 kWh/yr
- 5 bedrooms: 1.33× → 1,596 kWh/yr

An additional always-on constant (default 500 kWh/yr) covers equipment
that doesn't scale with bedrooms (e.g., home office, always-on networking).
A baseload upgrade (LED lighting, efficient appliances) reduces this constant.

### Key assumptions

- 3-bedroom home is the DOE reference household
- Baseload is always electric — gas is not used for lights or plugs

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

Most pre-1980s homes have 100-amp electrical service. Adding a heat pump
(30A), an EV charger (32A), and an induction range (40A) can push a 100A
panel to or beyond its limit. A 200A panel upgrade costs $3,000-$8,000
and requires a licensed electrician and utility coordination.

The good news: California has active programs to help — TECH+ rebates,
simplified permit processes, and utility co-funding in some territories.

### How we estimate panel load (NEC Article 220)

This is the same calculation an electrician uses to size a service entrance:

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

### Data sources

- NEC Article 220 Standard Method for Dwelling Units
- CEC and CPUC panel upgrade program documentation (2024-2025)

---

## §12 · ACC — Avoided Cost of Carbon
@file: acc.html
@keys: chart_r2
@popup: The ACC (Avoided Cost of Carbon) seasonal shape shows how the
  effective electricity rate varies by month under the CPUC's
  avoided-cost framework. Summer peak hours carry the highest rate.

### What this means for you

The Avoided Cost Calculator (ACC) is a CPUC/E3 framework that estimates
the true value of electricity at different times of day and year, based
on what it would cost to avoid generating that electricity from fossil fuels.
Summer afternoon peak hours are the most expensive — that's when gas peaker
plants run and carbon costs are highest.

WhyWatt uses the ACC seasonal shape to apply a more realistic monthly rate
pattern to electricity costs, rather than a flat annual average.

### How the ACC shape works

The ACC produces a ratio for each month (e.g., July = 1.35× average,
January = 0.78× average). WhyWatt multiplies the base electricity rate
by these monthly ratios to get a seasonal rate profile.

This affects the cost of running appliances differently across the year —
air conditioning in July costs more per kWh than heating in January.

### Key assumptions

- ACC shape is from E3's 2024 Avoided Cost Calculator, Electric CZ12 (PG&E territory)
- ACC shape is only available when PG&E is selected as the rate source
- The base rate (before ACC adjustment) is still the PG&E E-1 tariff

### Data sources

- CPUC/E3 Avoided Cost Calculator 2024 (E3 Energy and Environmental Economics)
- CPUC Resolution E-5328 (November 2024)

---

## §13 · Social & Health Cost of Gas
@file: social_cost.html
@keys:
@popup: These costs represent damage to public health and the climate
  caused by burning natural gas — costs that do not appear on your
  utility bill but are real and quantified by official sources.

### What this means for you

The utility bill only shows the market price of gas. It does not show the
cost that gas combustion imposes on public health (air quality damage,
respiratory illness) and on the global climate (CO2 and methane emissions).

At the default settings, these hidden costs total about $2.30 per therm —
nearly equal to the $2.08/therm market price. The "true" cost of a therm
of natural gas is roughly double what appears on the bill.

These costs do not appear on your utility bill. This panel is informational —
advocates can use it to show homeowners the full picture.

### Climate cost ($1.07/therm default)

Based on EPA 2023 Social Cost of CO2 ($190/tonne CO2) applied to the EIA
combustion emission factor (5.3 kg CO2/therm), plus an allowance for
upstream methane leakage at a 2% pipeline leakage rate.

Slider range: $1.00 (EPA SC-CO2 only, no leakage) to $2.00 (high leakage + high scenario).

### Health cost ($1.23/therm default)

Based on CPUC Decision D.24-07-015 (July 2024), using E3's "Quantifying
Air Quality Impacts of Decarbonization" report. Computed using the EPA
COBRA tool with California population and pollution data. Covers outdoor
air quality damage (NO2, PM2.5) from building gas combustion.

Slider range: $0.50 (conservative/skeptical) to $2.00 (includes indoor
air quality — NO2 and benzene exposure not yet in the CPUC figure).

### Important caveats

- The EPA 2023 SC-CO2 figure has uncertain federal regulatory status as of 2025-2026.
  California's CPUC adopted the lower IWG 2021 value ($51/tonne = $0.27/therm)
  for regulatory proceedings.
- The health adder covers outdoor air quality only — indoor health effects
  from gas stove NO2 and benzene are additional and not yet officially monetized.
- Gas cars are not included in this calculation (Phase 4 candidate).

### Data sources

- EPA Social Cost of Greenhouse Gases, Final Report (December 2023)
- IWG Technical Support Document: Social Cost of Carbon (February 2021)
- CPUC Decision D.24-07-015 (July 2024)
- E3: Quantifying Air Quality Impacts of Decarbonization (2022)
- EIA emission factor: 5.306 kg CO2/therm (EPA/EIA 2024)

---

## §14 · Charts Reference
@file: charts.html
@keys: chart_jc1, chart_jc2, chart_jc3, chart_jc4, chart_eu1, chart_eu2
@popup: Charts are organized into three groups — Journey Costs (JC),
  Rates (R), and Energy Use (EU). Select any chart from the dropdown
  in each chart panel.

### Journey Costs (JC)

JC-1 Annual Cost — Your Journey vs. Do Nothing
Shows the total energy bill (electricity + gas) for each year of the
simulation, for both scenarios side by side. The gap in a given year
is your annual saving or cost.

JC-2 Cumulative Cost & Payback Crossover
Adds up every year's total bill from year 1 onward. The crossover point
— where the Journey line dips below Do Nothing — is your payback year.
This is often the most compelling chart to show homeowners.

JC-3 20-Year Summary Bar
A single side-by-side bar showing total 20-year spend for each scenario.
The difference is your estimated lifetime savings from electrification.

JC-4 Annual Cost Breakdown by Appliance
A stacked bar where each segment is one appliance's share of the annual
energy bill. Watch across years to see which swaps have the biggest impact.

### Rates (R)

R-1 Rate Projection
Electricity and gas rates projected forward from today's PG&E tariff
using your chosen escalation scenario (conservative / moderate / stress).

R-2 ACC Seasonal Rate Shape
Monthly variation in the effective electricity rate under the CPUC
Avoided Cost Calculator framework. Summer afternoon peak hours carry
the highest effective rate.

### Energy Use (EU)

EU-1 Annual Energy Consumption by Fuel
Total annual energy in physical units — kWh for electricity, therms for
gas. Shows energy quantity before pricing is applied.

EU-2 Per-Appliance Energy Breakdown
Stacked breakdown of energy consumption by appliance. Compare journey vs.
do-nothing to see which swaps reduce energy use most.

---

## §15 · About WhyWatt
@file: about.html
@keys:
@popup: WhyWatt is a home electrification cost simulator for California
  community advocates, showing the 20-year cost of an electrification
  journey vs. doing nothing.

### What WhyWatt is

WhyWatt is a home electrification cost simulator for California community
advocates. It shows the long-term cost of an electrification journey —
replacing gas appliances with electric alternatives over time — compared
to doing nothing for 20 years.

The primary audience is electrification advocates running sessions with
homeowners: people who want to show, with real numbers, what switching to
heat pumps, induction, and electric vehicles actually costs and saves.

### What it models

WhyWatt simulates a single home running two scenarios in parallel:
- Your Journey — you choose which appliances to swap, and in which year
- Do Nothing — all current appliances stay in place for 20 years

For each year WhyWatt calculates energy consumption, utility costs with
escalation, capital expenditure for appliance swaps, and solar savings.

### Data sources

- PG&E electricity rate (E-1): Cal Advocates Q2 2025, $0.386/kWh
- PG&E gas rate (G-1): PG&E Advice Letter 5014-G1 Jan 2025, $2.08/therm
- ACC rate shape: CPUC/E3 Avoided Cost Calculator 2024
- Climate data: NOAA TMY3, San Jose Mineta (Station 724945), 1991-2005 composite
- Appliance efficiency: ENERGY STAR and AGA reference data (2024)
- Bedroom scaling: DOE/ENERGY STAR occupancy proxy

### Limitations

- Appliance end-of-life replacement is not modeled beyond scheduled swaps
- Income-qualified rebate programs are coming in a future release
- Monte Carlo uncertainty bands are coming in a future release
- Only PG&E rates are currently supported (SCE, SDG&E in a future release)

### Disclaimer

WhyWatt is a planning tool, not a financial guarantee. Actual costs depend
on your specific appliances, usage patterns, utility rate changes, local
rebate availability, and many other factors. Consult a licensed contractor
before making purchasing decisions. Energy rate projections are scenarios,
not predictions.

### Team

Developed with support from the Electrification Collaboration (ECHo) —
helping California communities make the switch.
