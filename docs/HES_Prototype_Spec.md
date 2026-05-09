# Phase: Prototype - Home Electrification Simulator (HES)

## 1. Project Overview
The HES Prototype aims to demonstrate the viability of using **Python + Mesa + Solara** for modeling the Total Cost of Ownership (TCO) and Opex Delta between baseline gas-powered homes and all-electric homes in the Bay Area.

## 2. Core Simulation Objectives
* **Demonstrate Opex Delta:** Calculate and visualize the cumulative cost difference between a gas-based baseline and an electrified system over a 5–25 year horizon.
* **Interactive Variable Control:** Provide a UI to adjust equipment efficiency (COP/SEER/AFUE) and fuel pricing volatility.
* **Seasonality Foundation:** Implement synthetic monthly weighting to illustrate heating/cooling spikes, setting the stage for future weather-based modeling.

## 3. Input Matrix (The 20 Variables)
### System Specifications
* **Baseline Equipment:**
    * Furnace AFUE (0.8–0.98)
    * AC SEER (13–18)
    * Water Heater UEF (0.6–0.9)
* **Electrified Equipment:**
    * Heat Pump COP (3.0–4.5)
    * HPWH UEF (2.0–4.0)

### Economic & Volatility Drivers
* **Fuel Escalation Rates:**
    * Electricity Escalation (Annual % change)
    * Natural Gas Escalation (Annual % change)
* **Volatility "Shock" Factors:**
    * Simulated year-specific price spikes.

## 4. Technical Architecture
* **Engine (Mesa):** Performs annual/monthly Opex calculations based on energy consumption profiles and defined escalation rates.
* **Frontend (Solara):** Reactive UI built on Python, allowing real-time updates to calculations without full page refreshes.
* **Data Handling:** * Use of **synthetic seasonality vectors** to distribute annual loads into 12-month increments.

## 5. UI/Visualization Specs
* **Dashboard Layout:** Sidebar for sliders (grouped by System Specs, Economic Drivers).
* **Visualizations:**
    * **Primary Chart:** Cumulative Opex Delta (Line Chart) showing the savings/cost curve over 25 years.
    * **Secondary Chart:** Monthly Opex (Stacked Bar Chart) showing the electricity/gas breakdown across a 12-month cycle.

## 6. Next Steps
1.  **Environment Setup:** Initialize VS Code workspace with `mesa` and `solara` dependencies.
2.  **Mesa Core:** Build the `Model` and `Agent` classes with the feedback loops.
3.  **Solara UI:** Connect reactive variables to the Mesa Engine for real-time visualization.
