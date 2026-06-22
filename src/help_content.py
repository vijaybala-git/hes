"""
help_content.py — GENERATED FILE. Do not edit manually.
Source: docs/help/help_content.md
Regenerate: python scripts/build_help.py
"""

HELP_POPUPS: dict[str, tuple[str, str]] = {

    # ── Panel headers & device rows (from help_content.md) ───────────────────
    "journey_planner": (
        "The Journey Planner lets you schedule when each gas appliance gets"
        " replaced with an electric alternative. A \"Do Nothing\" baseline runs in"
        " parallel so you can see the cost difference year by year over the"
        " modeled period.",
        "journey.html",
    ),
    "home_profile": (
        "Home details — size and insulation quality — affect how much energy each"
        " appliance uses. WhyWatt looks up your ZIP code to find your local"
        " climate zone and drives all heating and cooling from that zone's real"
        " degree-day data.",
        "climate.html",
    ),
    "zip_code": (
        "Home details — size and insulation quality — affect how much energy each"
        " appliance uses. WhyWatt looks up your ZIP code to find your local"
        " climate zone and drives all heating and cooling from that zone's real"
        " degree-day data.",
        "climate.html",
    ),
    "energy_prices": (
        "Energy prices start from your utility's current rates — looked up from"
        " your ZIP using federal EIA data — and are projected forward each year."
        " This panel sets electricity, gas, gasoline, and external EV-charging"
        " prices, plus how many years to model.",
        "rates.html",
    ),
    "rates": (
        "Energy prices start from your utility's current rates — looked up from"
        " your ZIP using federal EIA data — and are projected forward each year."
        " This panel sets electricity, gas, gasoline, and external EV-charging"
        " prices, plus how many years to model.",
        "rates.html",
    ),
    "hvac": (
        "Heating and cooling energy is calculated from monthly degree-days for"
        " your climate zone, your home's insulation level, and the heat pump's"
        " efficiency rating (COP for heating, SEER for cooling).",
        "hvac.html",
    ),
    "water_heater": (
        "Water heating energy depends on how much hot water your household uses,"
        " the temperature of incoming cold water (varies by season and location),"
        " and the appliance's efficiency rating (UEF).",
        "water_heating.html",
    ),
    "dryer": (
        "Dryer energy is based on loads per week and energy per load. Heat pump"
        " dryers use roughly one-third the energy of gas dryers for the same"
        " number of loads.",
        "dryer.html",
    ),
    "cooktop": (
        "Cooking energy is estimated from meals cooked per week. Gas burners"
        " convert only about 40% of combustion energy to heat; induction transfers"
        " about 85% directly to the cookware.",
        "cooktop.html",
    ),
    "ev_charger": (
        "Transportation models your driving as gasoline miles and electric miles."
        " Your Journey can add an electric vehicle and a home Level 2 charger,"
        " shifting charging from costly public stations to your home electricity"
        " rate.",
        "ev.html",
    ),
    "solar": (
        "Solar is modeled from your system size and yield. The energy you use on-"
        " site saves at your retail rate; the surplus you export earns a credit. A"
        " battery lets you use more of your own solar instead of exporting it"
        " cheaply.",
        "solar.html",
    ),
    "baseload": (
        "Baseload covers lights, outlets, refrigerator, and other always-on"
        " electricity uses. It scales with floor area and the number of bedrooms"
        " using DOE and EIA reference data.",
        "baseload.html",
    ),
    "panel_upgrade": (
        "The Estimated Electrical Load uses the NEC Article 220 method to size"
        " your service from your home's square footage and the electric appliances"
        " in your journey. A panel upgrade may be needed when high-draw appliances"
        " (heat pump, EV charger, induction) push an older 100A panel past its"
        " limit.",
        "panel.html",
    ),
    "panel_assessment": (
        "The Estimated Electrical Load uses the NEC Article 220 method to size"
        " your service from your home's square footage and the electric appliances"
        " in your journey. A panel upgrade may be needed when high-draw appliances"
        " (heat pump, EV charger, induction) push an older 100A panel past its"
        " limit.",
        "panel.html",
    ),
    "social_cost": (
        "These costs represent damage to public health and the climate caused by"
        " burning natural gas and gasoline — costs that do not appear on your bill"
        " but are real and quantified by official sources.",
        "social_cost.html",
    ),
    "climate_data": (
        "WhyWatt's heating and cooling estimates are driven by real local climate"
        " data — monthly heating and cooling degree-days for your CEC Building"
        " Climate Zone, derived from NOAA weather records. This Technical"
        " Reference documents exactly what we use and how.",
        "climate_data.html",
    ),
    "rates_reference": (
        "WhyWatt prices your bills off your actual utility's residential rate —"
        " not a statewide average — using federal EIA data. This Technical"
        " Reference documents the sources, the effective-rate method, and the per-"
        " utility numbers we use.",
        "rates_reference.html",
    ),

    # ── Chart title bars (stable — not from help_content.md) ─────────────────
    "chart_jc1": (
        "Cumulative energy cost adds up every year's bill from year 1 onward, for"
        " your journey vs. the do-nothing baseline. The crossover — where the"
        " journey line dips below do-nothing — is your payback year, marked on the"
        " chart. Dotted lines add the social & health cost of gas and gasoline"
        " when enabled.",
        "charts.html",
    ),
    "chart_jc2": (
        "Annual cost is the total energy bill for a single simulation year —"
        " electricity, gas, gasoline, and external EV charging — for your journey"
        " vs. do-nothing. The gap in any year is your saving (or extra cost) that"
        " year; social & health costs stack on top when enabled.",
        "charts.html",
    ),
    "chart_jc3": (
        "A stacked view of cumulative cost split by category — heating, cooling,"
        " water heating, baseload, cooking, and transportation — with gas and"
        " gasoline social costs layered on top when enabled. Use the scenario"
        " toggle to switch between your journey and do-nothing.",
        "charts.html",
    ),
    "chart_jc4": (
        "The one-time install costs of each appliance, colored by device and"
        " plotted in the year they occur — your journey (solid bars) beside the"
        " do-nothing wear-out replacements (hatched). The box totals net capital"
        " over the period in today's dollars.",
        "charts.html",
    ),
    "chart_jc5": (
        "A year-by-year map of your electrification journey: each appliance swap"
        " and add-on (solar, panel, EV charger) is a marker on the year it"
        " happens, with its net cost. Do-nothing wear-out replacements appear"
        " below the rail so you can compare the two timelines.",
        "charts.html",
    ),
    "chart_jc6": (
        "Your home's estimated electrical service load, in amps, as each electric"
        " appliance comes online — against your panel's capacity line. It uses the"
        " NEC Article 220 method to flag whether a panel upgrade is needed and in"
        " which year.",
        "charts.html",
    ),
    "chart_eu1": (
        "A stacked area of annual home-energy cost by appliance, year over year."
        " It counts only energy on your home meter — gasoline and external public"
        " EV charging are excluded. Switch scenarios with the toggle to see which"
        " swaps cut cost most.",
        "charts.html",
    ),
    "chart_eu2": (
        "A stacked area of annual home-energy use by appliance in kilowatt-hour-"
        " equivalent terms (gas converted at 29.3 kWh per therm). Like the cost"
        " view, it excludes gasoline and external EV charging — only what lands on"
        " your home meter.",
        "charts.html",
    ),
    "chart_eu3": (
        "Actual electricity used by each appliance per year, in kilowatt-hours,"
        " as stacked bars. For an electric vehicle this counts home charging only.",
        "charts.html",
    ),
    "chart_eu4": (
        "Natural gas used by each appliance per year, in therms, as stacked bars."
        " As gas appliances are swapped for electric ones, these bars shrink"
        " toward zero.",
        "charts.html",
    ),
    "chart_eu6": (
        "A stacked view of where your home's energy comes from each year, in"
        " kilowatt-hour-equivalent terms: natural gas, gasoline, grid electricity,"
        " your own solar, and external EV charging. It tells the decarbonization"
        " story at a glance as gas shrinks and solar grows.",
        "charts.html",
    ),
    "chart_eu7": (
        "The heat pump's energy across the twelve months of the HVAC-swap year,"
        " split into heating (bottom) and cooling (top). Do-nothing gas heating is"
        " shown in kilowatt-hour-equivalent (29.3 kWh per therm) so a gas furnace"
        " and a heat pump sit on the same axis; cooling is omitted for homes that"
        " have none.",
        "charts.html",
    ),
    "chart_r1": (
        "Your electricity price projected forward each year from your utility's"
        " current EIA effective rate, using the escalation you choose. A second"
        " dashed line appears when you compare two scenarios.",
        "rates.html",
    ),
    "chart_r2": (
        "Your natural-gas price projected forward each year from your utility's"
        " current EIA effective rate, using the escalation you choose. A second"
        " dashed line appears when you compare two scenarios.",
        "rates.html",
    ),
    "chart_r3": (
        "Electricity and gas prices projected forward together, with a shaded"
        " band showing the seasonal or hourly range under the CPUC Avoided Cost"
        " Calculator when an ACC rate model is selected. The center line is the"
        " annual average.",
        "acc.html",
    ),
    "chart_r4": (
        "A heatmap of how the effective electricity rate varies by hour of day"
        " and month under the CPUC Avoided Cost Calculator. Summer afternoon and"
        " winter evening peaks carry the highest avoided cost. Shown only when an"
        " ACC-shaped electricity model is selected.",
        "acc.html",
    ),

    # ── Chart name → key mapping (stable) ────────────────────────────────────
    "_chart_name_to_key": {  # type: ignore[assignment]
        "Cumulative Energy Costs": "chart_jc1",
        "Annual Cost by Year": "chart_jc2",
        "Cost Breakdown by Category": "chart_jc3",
        "Equipment Replacements (CapEx)": "chart_jc4",
        "Journey Timeline": "chart_jc5",
        "Estimated Electrical Load": "chart_jc6",
        "Home Energy Cost by Device": "chart_eu1",
        "Home Energy Use by Device": "chart_eu2",
        "Annual kWh by Device": "chart_eu3",
        "Annual Gas by Device": "chart_eu4",
        "Energy Mix Timeline": "chart_eu6",
        "HVAC Monthly Energy": "chart_eu7",
        "Electric CAGR Projection": "chart_r1",
        "Gas CAGR Projection": "chart_r2",
        "ACC Electrical Rate Projection": "chart_r3",
        "ACC Gas Rate Projection": "chart_r3",
        "ACC Electrical Rate Shape": "chart_r4",
    },

}

# Convenience export
CHART_NAME_TO_HELP_KEY: dict[str, str] = HELP_POPUPS["_chart_name_to_key"]  # type: ignore[assignment]
