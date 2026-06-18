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
        " appliance uses. WhyWatt currently uses Bay Area (San Jose) climate data"
        " for every home; ZIP-based climate zone selection is coming in a future"
        " release.",
        "climate.html",
    ),
    "zip_code": (
        "Home details — size and insulation quality — affect how much energy each"
        " appliance uses. WhyWatt currently uses Bay Area (San Jose) climate data"
        " for every home; ZIP-based climate zone selection is coming in a future"
        " release.",
        "climate.html",
    ),
    "energy_prices": (
        "Energy prices start from current PG&E tariff rates and are projected"
        " forward each year. This panel sets electricity, gas, gasoline, and"
        " external EV-charging prices, plus how many years to model.",
        "rates.html",
    ),
    "rates": (
        "Energy prices start from current PG&E tariff rates and are projected"
        " forward each year. This panel sets electricity, gas, gasoline, and"
        " external EV-charging prices, plus how many years to model.",
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
        "Annual cost is the total energy bill for that simulation year —"
        " electricity plus gas — for your journey home vs. the do-nothing"
        " baseline. The gap between the lines is your annual saving (or cost) in"
        " that year.",
        "charts.html#jc1",
    ),
    "chart_jc2": (
        "Cumulative cost adds up every year's bill from year 1 onward. The"
        " crossover point — where the journey line dips below do-nothing — is your"
        " payback year.",
        "charts.html#jc2",
    ),
    "chart_jc3": (
        "The summary bar shows total 20-year spend for each scenario side by"
        " side. The difference is your estimated lifetime savings from"
        " electrification.",
        "charts.html#jc3",
    ),
    "chart_jc4": (
        "Each segment shows one appliance's share of the annual energy bill."
        " Watching this chart across years shows which swaps have the biggest cost"
        " impact.",
        "charts.html#jc4",
    ),
    "chart_r1": (
        "Rates are projected forward from today's PG&E tariff using a compound"
        " annual growth rate (CAGR). You can choose conservative, moderate, or"
        " stress scenarios.",
        "rates.html#projection",
    ),
    "chart_r2": (
        "The ACC (Avoided Cost of Carbon) seasonal shape shows how the effective"
        " electricity rate varies by month under the CPUC's avoided-cost"
        " framework. Summer peak hours carry the highest effective rate.",
        "acc.html",
    ),
    "chart_eu1": (
        "Annual energy consumption in physical units — kilowatt-hours for"
        " electricity and therms for gas. This shows how much energy is used"
        " before applying rates.",
        "charts.html#eu1",
    ),
    "chart_eu2": (
        "Each segment shows one appliance's share of total energy consumption."
        " Compare journey vs. do-nothing to see which swaps reduce energy use"
        " most.",
        "charts.html#eu2",
    ),

    # ── Chart name → key mapping (stable) ────────────────────────────────────
    "_chart_name_to_key": {  # type: ignore[assignment]
        "Cumulative Energy Costs": "chart_jc2",
        "Annual Cost by Year": "chart_jc1",
        "Cost Breakdown by Category": "chart_jc4",
        "Cost by Device": "chart_jc4",
        "Summary": "chart_jc3",
        "ACC Rate Projection": "chart_r2",
        "Energy Use by Device": "chart_eu2",
    },

}

# Convenience export
CHART_NAME_TO_HELP_KEY: dict[str, str] = HELP_POPUPS["_chart_name_to_key"]  # type: ignore[assignment]
