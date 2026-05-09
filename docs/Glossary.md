# Home Electrification Simulator (HES) - Glossary & Data Dictionary

This document defines the key variables, terminology, and units used throughout the Home Electrification Simulator (HES) codebase, JSON configurations, and UI.

## 1. Equipment & Energy Variables (`EnergyConsumer` & JSON Configs)

*   **`annual_load`**
    *   **Definition:** The base amount of useful energy required by the equipment or household need over the course of a full year (before accounting for equipment efficiency). 
    *   **Unit:** MMBtu (Million British Thermal Units). *Note: Baseloads like lights/computers might logically be evaluated in kWh, but the current simulation standardizes around MMBtu for load.*
*   **`efficiency`**
    *   **Definition:** A factor representing how effectively the equipment converts input fuel into useful output (`Energy Consumed = Load / Efficiency`). For electric resistance or standard baseloads, this is typically `1.0`. For heat pumps, it represents the COP (e.g., `3.5`).
    *   **Unit:** Dimensionless (Ratio or Percentage).
*   **`seasonality`**
    *   **Definition:** An array of 12 values representing the fraction of the `annual_load` that occurs in each month of the year (January through December). The sum of all 12 values must equal `1.0`.
    *   **Unit:** Dimensionless (Fraction).
*   **`fuel_mix`**
    *   **Definition:** A dictionary defining the proportion of different energy sources used by the device to meet its load. (e.g., `{"gas": 1.0}`, `{"electricity": 1.0}`, or a hybrid mix).
    *   **Unit:** Dimensionless (Fraction).
*   **`lifespan`**
    *   **Definition:** The expected operational life of the equipment before it requires replacement.
    *   **Unit:** Years.
*   **`current_age`**
    *   **Definition:** The current age of the equipment at the start of the simulation. Used to calculate when the first replacement (CapEx event) will occur.
    *   **Unit:** Years.
*   **`installation_cost`**
    *   **Definition:** The capital expenditure (CapEx) required to purchase and install the equipment.
    *   **Unit:** USD ($).

## 2. System-Specific Efficiency Metrics

*   **`AFUE` (Annual Fuel Utilization Efficiency)**
    *   **Definition:** The seasonal efficiency of gas furnaces. An AFUE of 0.90 means 90% of the fuel becomes heat, and 10% escapes via the chimney.
*   **`SEER` (Seasonal Energy Efficiency Ratio)**
    *   **Definition:** The cooling efficiency of an air conditioner or heat pump. In the model, SEER is roughly converted to COP by dividing by 3.412.
*   **`COP` (Coefficient of Performance)**
    *   **Definition:** The ratio of useful heating/cooling provided to work required. A COP of 3.5 means 1 unit of electricity provides 3.5 units of heat.
*   **`UEF` (Uniform Energy Factor)**
    *   **Definition:** The standard measurement of water heater overall efficiency.

## 3. Economic & Environmental Drivers

*   **`gas_esc` / `elec_esc`**
    *   **Definition:** The projected annual escalation (inflation) rate of natural gas and electricity prices.
    *   **Unit:** Decimal (e.g., `0.03` represents 3% annual growth).
*   **`gas_price_per_mmbtu` / `elec_price_per_mmbtu`**
    *   **Definition:** The starting cost of energy before annual escalation is applied.
    *   **Unit:** USD per MMBtu ($/MMBtu).

## 4. Simulation Output & Tracking

*   **`capex_events`**
    *   **Definition:** A historical log of equipment replacement events triggered when a device reaches the end of its `lifespan`.
    *   **Unit:** Tuple containing `(Simulation Year, Cost in USD)`.
*   **`opex_delta`**
    *   **Definition:** The cumulative operational expenditure savings (or loss) when comparing the evaluation home (electrified) against the baseline home.
    *   **Unit:** USD ($).
*   **`history`**
    *   **Definition:** A dictionary attached to each `EnergyConsumer` agent that tracks its specific consumption and costs month-by-month over the simulation horizon.
    *   **Unit:** Arrays of MMBtu (consumption) and USD (cost).