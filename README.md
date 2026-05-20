---
title: WhyWatt?
emoji: ⚡
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# WhyWatt?

An interactive tool showing the long-run cost of a user-defined **home electrification journey** vs. doing nothing — built for California community advocates.

Built with [Mesa](https://mesa.readthedocs.io/) + [Solara](https://solara.dev/).

## What it does

- Models a household's electrification journey: swapping HVAC, water heater, dryer, cooktop, and adding an EV charger over time
- Runs a parallel "do nothing" baseline automatically — gas devices stay gas, prices escalate, end-of-life replacements fire
- Applies real PG&E/CPUC rate data with historically-calibrated escalation scenarios (conservative / moderate / stress)
- Shows results as cumulative costs, annual costs, category breakdowns, and equipment replacement timelines

## How to run

```bash
solara run src/app.py
```

## Phase status

- **Phase 1:** Complete — Mesa agent framework, dual JSON home configs, Solara UI, 42 unit tests.
- **Phase 2:** In progress — Journey model, physics-based devices, real CPUC rate data.

See `docs/Phase2_Spec.md` for full Phase 2 scope.
