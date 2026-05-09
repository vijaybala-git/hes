---
title: Home Electrification Simulator
emoji: 🏠
colorFrom: blue
colorTo: gray
sdk: docker
pinned: false
---

# Home Electrification Simulator (HES)

An interactive tool comparing the long-run energy costs of a **gas home** vs. a fully **electrified home** in the Bay Area.

Built with [Mesa](https://mesa.readthedocs.io/) + [Solara](https://solara.dev/). Developed as a resource for climate and electrification advocates helping consumers make informed appliance choices.

## What it does

- Models heating, cooling, water heating, and baseload electricity over a user-selected time horizon (5–25 years)
- Applies compounding gas and electricity price escalation
- Tracks appliance replacement costs (CapEx) when devices reach end of life
- Shows results as cumulative costs, annual costs, category breakdowns, and price trends

## How to use

Adjust the sliders in the three control panels at the bottom:
- **Gas Home** — usage levels and replacement timing for the furnace, A/C, and water heater
- **Electric Home** — heat pump and heat pump water heater settings; raise baseload to model EVs or induction cooking
- **Energy Prices** — how fast gas and electricity prices rise per year, and how many years to look ahead

Select any two charts from the dropdowns above the chart area.
