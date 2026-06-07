"""
panel_assessor.py — NEC Article 220 panel load assessment (Phase 3 §5).

Pure, read-only analysis over a JourneyHome's slots. Never steps the model or mutates
devices. Assesses the journey home only (never the do-nothing baseline) — a panel is
sized for the home you are building toward.
"""
from __future__ import annotations

from dataclasses import dataclass

# ── NEC constants ──────────────────────────────────────────────────────────────
GENERAL_VA_PER_SQFT  = 3       # general lighting load
SMALL_APPLIANCE_VA   = 3000    # two 1500 VA small-appliance circuits (NEC minimum)
LAUNDRY_VA           = 1500    # laundry circuit
DEMAND_THRESHOLD_VA  = 10000   # first 10 kVA at 100%, remainder at 40% (Table 220.42)
DEMAND_FACTOR_ABOVE  = 0.40
EV_CONTINUOUS_FACTOR = 1.25    # NEC 210.20 continuous load factor
DRYER_MIN_VA         = 5000    # NEC 220.54 — 5000 VA or nameplate, whichever larger
RANGE_DEMAND_VA      = 8000    # NEC 220.55 — single range ≤12 kW demand allowance
SERVICE_VOLTS        = 240     # single-phase residential service


@dataclass
class PanelLoadYear:
    year: int                  # 1-indexed simulation year
    service_amps: float
    utilization_pct: float
    status: str                # "green" | "yellow" | "orange" | "red"
    new_device: str | None     # slot name whose electric device activated this year


def _status(util_pct: float) -> str:
    if util_pct < 70:
        return "green"
    if util_pct < 90:
        return "yellow"
    if util_pct <= 100:
        return "orange"
    return "red"


class PanelAssessor:
    """NEC Article 220 standard-method load calculation for a dwelling."""

    def __init__(self, floor_area_sqft: int, panel_amps: int):
        self.floor_area_sqft = floor_area_sqft
        self.panel_amps = panel_amps

    # ── Step 1 — general load with demand factor ───────────────────────────────
    def general_demand_va(self) -> float:
        g = (self.floor_area_sqft * GENERAL_VA_PER_SQFT
             + SMALL_APPLIANCE_VA + LAUNDRY_VA)
        if g <= DEMAND_THRESHOLD_VA:
            return float(g)
        return DEMAND_THRESHOLD_VA + (g - DEMAND_THRESHOLD_VA) * DEMAND_FACTOR_ABOVE

    # ── Step 2 — named appliance load (no demand factor) ───────────────────────
    def appliance_va(self, active_devices: list) -> float:
        """Sum named-appliance VA for the active electric devices in a given year.

        Gas devices contribute 0 (rated_va == 0). LightsAndPlugs is covered by the
        general load. Cooktop uses the NEC fixed range allowance, not its nameplate.
        """
        total = 0.0
        for d in active_devices:
            if getattr(d, "fuel_type", None) != "electricity":
                continue
            cls = type(d).__name__
            if cls == "InductionCooktop":
                total += RANGE_DEMAND_VA                       # NEC 220.55 fixed
            elif cls == "HeatPumpDryer":
                total += max(DRYER_MIN_VA, d.rated_va)         # NEC 220.54
            elif cls in ("PhysicsEVCharger", "EVCharger"):
                factor = EV_CONTINUOUS_FACTOR if d.continuous else 1.0
                total += d.rated_va * factor                   # NEC 210.20
            elif cls == "LightsAndPlugs":
                continue                                       # in general load
            else:
                total += d.rated_va                            # HVAC, HPWH, CentralAC
        return total

    # ── Step 3 — total service amps ────────────────────────────────────────────
    def nec_load_amps(self, active_devices: list) -> float:
        total_va = self.general_demand_va() + self.appliance_va(active_devices)
        return total_va / SERVICE_VOLTS

    # ── Active-device resolution (replicates DeviceSlot.step swap logic) ────────
    @staticmethod
    def _active_devices_for_year(slots: list, year: int) -> tuple[list, list[str]]:
        """Return (active_devices, slot_names_activated_this_year) for a 1-indexed year.

        Mirrors DeviceSlot.step() for the JOURNEY home (is_baseline_home=False):
          - "electric" start  → electric_device active every year
          - "gas"/"none" with swap_year and year >= swap_year → electric_device active
          - otherwise → baseline_devices active (gas furnace → 0 VA; CentralAC → VA)
        """
        active: list = []
        newly: list[str] = []
        for slot in slots:
            ss = slot.starting_state
            if ss == "electric":
                if slot.electric_device is not None:
                    active.append(slot.electric_device)
            elif (slot.swap_year is not None
                  and year >= slot.swap_year
                  and ss in ("gas", "none")):
                if slot.electric_device is not None:
                    active.append(slot.electric_device)
                if year == slot.swap_year:
                    newly.append(slot.name)
            else:
                active.extend(slot.baseline_devices)
        return active, newly

    # ── Full timeline over the journey home ────────────────────────────────────
    def journey_load_timeline(self, journey_home, n_years: int) -> list[PanelLoadYear]:
        timeline: list[PanelLoadYear] = []
        for year in range(1, n_years + 1):
            active, newly = self._active_devices_for_year(journey_home.slots, year)
            amps = self.nec_load_amps(active)
            util = amps / self.panel_amps * 100 if self.panel_amps else 0.0
            timeline.append(PanelLoadYear(
                year=year,
                service_amps=amps,
                utilization_pct=util,
                status=_status(util),
                new_device=newly[0] if newly else None,
            ))
        return timeline

    def upgrade_needed_years(self, timeline: list[PanelLoadYear]) -> list[int]:
        return [t.year for t in timeline if t.utilization_pct > 100]
