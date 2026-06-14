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
    """NEC Article 220 dwelling load calculation.

    Two methods are supported (selected via ``method``):

      "optional" (default, NEC 220.82) — the general lighting/receptacle load plus
        ALL non-HVAC appliance loads are pooled and reduced by the Table 220.42
        demand factor (first 10 kVA at 100%, remainder at 40%); space-conditioning
        (HVAC) is then added at 100% per 220.82(C). This is the method Bay Area
        permit offices use (matches the City of Mountain View / local worksheets)
        and is what lets a fully-electrified home fit under a smaller service.

      "standard" (NEC 220.42/220.52) — the demand factor applies ONLY to general
        lighting + small-appliance + laundry; every named appliance (HVAC included)
        is added at 100%. Always yields a higher number; offered for comparison.
    """

    # Space-conditioning device classes — added at 100% under the optional method.
    HVAC_CLASSES = {"HeatPumpHVAC", "CentralAC", "GasFurnace"}

    def __init__(self, floor_area_sqft: int, panel_amps: int,
                 method: str = "optional"):
        self.floor_area_sqft = floor_area_sqft
        self.panel_amps = panel_amps
        self.method = method

    # ── General load ───────────────────────────────────────────────────────────
    def general_nameplate_va(self) -> float:
        """General lighting + small-appliance + laundry, before any demand factor."""
        return float(self.floor_area_sqft * GENERAL_VA_PER_SQFT
                     + SMALL_APPLIANCE_VA + LAUNDRY_VA)

    @staticmethod
    def _demand_factored(va: float) -> float:
        """Table 220.42: first 10 kVA at 100%, remainder at 40%."""
        if va <= DEMAND_THRESHOLD_VA:
            return float(va)
        return DEMAND_THRESHOLD_VA + (va - DEMAND_THRESHOLD_VA) * DEMAND_FACTOR_ABOVE

    def general_demand_va(self) -> float:
        """Standard-method general bucket (demand factor on general load only)."""
        return self._demand_factored(self.general_nameplate_va())

    # ── Per-device nameplate VA ────────────────────────────────────────────────
    def _device_va(self, d) -> float:
        """NEC nameplate VA for one device. Gas → 0; lights folded into general."""
        if getattr(d, "fuel_type", None) != "electricity":
            return 0.0
        cls = type(d).__name__
        if cls == "InductionCooktop":
            return RANGE_DEMAND_VA                              # NEC 220.55 fixed
        if cls == "HeatPumpDryer":
            return max(DRYER_MIN_VA, d.rated_va)                # NEC 220.54
        if cls in ("PhysicsEVCharger", "EVCharger", "ElectricVehicle"):
            factor = EV_CONTINUOUS_FACTOR if d.continuous else 1.0
            return d.rated_va * factor                          # NEC 625.42 / 210.20
        if cls == "LightsAndPlugs":
            return 0.0                                          # in general load
        return d.rated_va                                      # HPWH, HVAC, etc.

    def _split_va(self, active_devices: list) -> tuple[float, float]:
        """Return (hvac_va, other_appliance_va) for the active electric devices."""
        hvac = other = 0.0
        for d in active_devices:
            va = self._device_va(d)
            if va == 0.0:
                continue
            if type(d).__name__ in self.HVAC_CLASSES:
                hvac += va
            else:
                other += va
        return hvac, other

    def appliance_va(self, active_devices: list) -> float:
        """Total named-appliance VA at 100% (HVAC + others). Standard-method Step 2."""
        hvac, other = self._split_va(active_devices)
        return hvac + other

    # ── Total service load ─────────────────────────────────────────────────────
    def nec_load_va(self, active_devices: list) -> float:
        hvac, other = self._split_va(active_devices)
        if self.method == "optional":
            pooled = self._demand_factored(self.general_nameplate_va() + other)
            return pooled + hvac
        return self.general_demand_va() + hvac + other

    def nec_load_amps(self, active_devices: list) -> float:
        return self.nec_load_va(active_devices) / SERVICE_VOLTS

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
                # Only flag swaps that actually add electrical load — an ICE→ICE
                # (gasoline) or gas→gas swap changes nothing on the panel.
                if (year == slot.swap_year
                        and getattr(slot.electric_device, "fuel_type", None)
                        == "electricity"):
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
