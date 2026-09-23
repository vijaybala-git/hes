"""Hourly solar + battery + utility energy balance — two battery modes (Phase 7 §0/§2).

Pure and deterministic: arrays in, flows out. No model, UI or file access, so each mode can be
run and tested on its own.

For one month's representative day (24 CLOCK hours):
  G[h]  solar generation (kWh in hour h)          L[h]  home electric load (kWh in hour h)

Two standard battery modes (the settings home batteries ship with):

  "self"  Self-powered — solar → home; surplus → battery → export; the battery covers any
          shortfall at any hour; the utility covers the rest.
  "cost"  Cost-saving — keep just enough charge (the reserve R) to cover the peak window;
          off-peak, solar fills the battery up to R before serving the home; if solar leaves
          it short of R at peak start and grid charging pays (η·r_peak > r_offpeak), the
          utility tops it up in the hours just before the peak; the battery discharges only
          during the peak.
  "auto"  run both, keep the lower bill (tie → self). A flat tariff (no peak window) or no
          battery runs self only — cost-saving has nothing to aim at.

Steady state: the day is repeated until the battery's start-of-day charge equals its
end-of-day charge, so no energy appears from an arbitrary initial state. Round-trip efficiency
η is split √η on charge and √η on discharge.

Identities (hold exactly per mode, tested):
  G = solar_direct + charge_solar + export
  L = solar_direct + discharge + grid_to_home
  grid_import = grid_to_home + charge_grid
  (charge_solar + charge_grid)·η = discharge          (steady state)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

import numpy as np

HOURS = 24
_MAX_PASSES = 200
_TOL = 1e-10


@dataclass(frozen=True)
class BatteryParams:
    cap_kwh: float = 0.0          # usable capacity; 0 = no battery
    round_trip_eff: float = 0.90
    power_kw: float = 5.0         # charge / discharge limit (kWh per hour)
    grid_charging: bool = True    # cost-saving mode may top up from the grid when it pays


@dataclass
class DayFlows:
    """One representative day (kWh). Arrays are per clock hour."""
    mode: str
    solar_direct: np.ndarray
    charge_solar: np.ndarray
    charge_grid: np.ndarray
    discharge: np.ndarray
    export: np.ndarray
    grid_to_home: np.ndarray
    soc_start: float = 0.0

    @property
    def grid_import(self) -> np.ndarray:
        return self.grid_to_home + self.charge_grid

    @property
    def self_consumed(self) -> float:
        """Solar that ended up serving the home, directly or via the battery."""
        return float(self.solar_direct.sum() + self.discharge.sum())

    @property
    def losses(self) -> float:
        return float(self.charge_solar.sum() + self.charge_grid.sum() - self.discharge.sum())

    def totals(self) -> dict:
        return {k: float(getattr(self, k).sum()) for k in
                ("solar_direct", "charge_solar", "charge_grid", "discharge", "export",
                 "grid_to_home")}


@dataclass
class MonthResult:
    """Chosen mode for the month, scaled to days-in-month, plus the per-mode bills."""
    mode: str
    days: int
    day: DayFlows
    bills: dict = field(default_factory=dict)      # mode → monthly bill ($), for every mode run

    def total(self, name: str) -> float:
        """Monthly kWh for a flow (e.g. "export", "discharge", "grid_import")."""
        v = getattr(self.day, name)
        return float(np.sum(v)) * self.days


def _peak_mask(peak_hours: Sequence[int]) -> np.ndarray:
    mask = np.zeros(HOURS, dtype=bool)
    for h in peak_hours:
        mask[int(h)] = True
    return mask


def _self_day(G, L, b: BatteryParams, soc0: float) -> DayFlows:
    sq = np.sqrt(b.round_trip_eff)
    z = lambda: np.zeros(HOURS)                                  # noqa: E731
    f = DayFlows("self", z(), z(), z(), z(), z(), z(), soc_start=soc0)
    soc = soc0
    for h in range(HOURS):
        direct = min(G[h], L[h])
        surplus, deficit = G[h] - direct, L[h] - direct
        charge = min(surplus, max(b.cap_kwh - soc, 0.0) / sq, b.power_kw) if b.cap_kwh else 0.0
        soc += charge * sq
        discharge = min(deficit, soc * sq, b.power_kw) if b.cap_kwh else 0.0
        soc -= discharge / sq
        f.solar_direct[h], f.charge_solar[h], f.export[h] = direct, charge, surplus - charge
        f.discharge[h], f.grid_to_home[h] = discharge, deficit - discharge
    f._soc_end = soc
    return f


def _cost_day(G, L, b: BatteryParams, peak: np.ndarray, reserve: float,
              grid_plan: np.ndarray, soc0: float) -> DayFlows:
    sq = np.sqrt(b.round_trip_eff)
    z = lambda: np.zeros(HOURS)                                  # noqa: E731
    f = DayFlows("cost", z(), z(), z(), z(), z(), z(), soc_start=soc0)
    soc = soc0
    for h in range(HOURS):
        if peak[h]:
            direct = min(G[h], L[h])
            surplus, deficit = G[h] - direct, L[h] - direct
            discharge = min(deficit, soc * sq, b.power_kw)
            soc -= discharge / sq
            charge = min(surplus, max(b.cap_kwh - soc, 0.0) / sq, b.power_kw)
            soc += charge * sq
            f.solar_direct[h], f.charge_solar[h], f.export[h] = direct, charge, surplus - charge
            f.discharge[h], f.grid_to_home[h] = discharge, deficit - discharge
            continue
        # off-peak: solar fills the battery up to the reserve first, then serves the home
        first = min(G[h], max(reserve - soc, 0.0) / sq, b.power_kw)
        soc += first * sq
        direct = min(G[h] - first, L[h])
        leftover = G[h] - first - direct
        more = min(leftover, max(b.cap_kwh - soc, 0.0) / sq, b.power_kw - first)
        soc += more * sq
        grid_in = min(grid_plan[h], max(b.cap_kwh - soc, 0.0) / sq, b.power_kw - first - more)
        grid_in = max(grid_in, 0.0)
        soc += grid_in * sq
        f.solar_direct[h], f.charge_solar[h] = direct, first + more
        f.export[h], f.charge_grid[h] = leftover - more, grid_in
        f.grid_to_home[h] = L[h] - direct
    f._soc_end = soc
    return f


def _steady(run) -> DayFlows:
    soc = 0.0
    for _ in range(_MAX_PASSES):
        day = run(soc)
        if abs(day._soc_end - soc) < _TOL:
            return day
        soc = day._soc_end
    return day


def run_day(G, L, battery: BatteryParams, mode: str, peak_hours: Sequence[int] = (),
            r_peak: float = 0.0, r_offpeak: float = 0.0) -> DayFlows:
    """Steady-state representative day for one mode ("self" | "cost")."""
    G = np.asarray(G, dtype=float)
    L = np.asarray(L, dtype=float)
    if G.shape != (HOURS,) or L.shape != (HOURS,):
        raise ValueError("G and L must be 24-hour arrays")
    if mode == "self":
        return _steady(lambda soc: _self_day(G, L, battery, soc))
    if mode != "cost":
        raise ValueError(f"unknown mode {mode!r}")

    peak = _peak_mask(peak_hours)
    sq = np.sqrt(battery.round_trip_eff)
    need = np.minimum(np.maximum(L - G, 0.0), battery.power_kw)[peak].sum()
    reserve = min(battery.cap_kwh, need / sq)
    grid_ok = (battery.grid_charging and peak.any()
               and battery.round_trip_eff * r_peak > r_offpeak)
    plan = np.zeros(HOURS)
    day = _steady(lambda soc: _cost_day(G, L, battery, peak, reserve, plan, soc))
    if grid_ok and peak.any():
        start = int(np.argmax(peak))                              # first peak hour
        # stored energy at peak start = soc_start + net charging over hours before it
        for _ in range(_MAX_PASSES):
            soc_at_peak = day.soc_start + sq * (day.charge_solar[:start].sum()
                                                + day.charge_grid[:start].sum())
            short = reserve - soc_at_peak
            if short <= _TOL:
                break
            need_in = short / sq
            for h in range(start - 1, -1, -1):                    # latest hour first
                room = battery.power_kw - day.charge_solar[h] - plan[h]
                add = min(max(room, 0.0), need_in)
                plan[h] += add
                need_in -= add
                if need_in <= _TOL:
                    break
            new = _steady(lambda soc: _cost_day(G, L, battery, peak, reserve, plan, soc))
            if np.allclose(new.charge_grid, day.charge_grid, atol=_TOL):
                day = new
                break
            day = new
    return day


def month_bill(day: DayFlows, days: int, peak_hours: Sequence[int], r_peak: float,
               r_offpeak: float, export_rate: float,
               price_fn: Callable[[float, float], float] | None = None) -> float:
    """Monthly electricity bill ($) for a representative day, net of export credit.

    price_fn(grid_peak_kwh, grid_offpeak_kwh) → $ lets the caller apply tiers/fixed charges
    (URDB price_month, §3); by default the two flat period rates are used.
    """
    peak = _peak_mask(peak_hours)
    gi = day.grid_import
    g_peak, g_off = float(gi[peak].sum()) * days, float(gi[~peak].sum()) * days
    energy = price_fn(g_peak, g_off) if price_fn else g_peak * r_peak + g_off * r_offpeak
    return energy - float(day.export.sum()) * days * export_rate


def dispatch_month(G, L, battery: BatteryParams, *, days: int, mode: str = "auto",
                   peak_hours: Sequence[int] = (), r_peak: float = 0.0,
                   r_offpeak: float = 0.0, export_rate: float = 0.0,
                   price_fn: Callable[[float, float], float] | None = None) -> MonthResult:
    """Run one mode (or "auto": both, keep the cheaper) for a month's representative day."""
    if mode not in ("self", "cost", "auto"):
        raise ValueError(f"unknown mode {mode!r}")
    candidates = ["self", "cost"] if mode == "auto" else [mode]
    if mode == "auto" and (not peak_hours or battery.cap_kwh <= 0):
        candidates = ["self"]
    days_flows, bills = {}, {}
    for m in candidates:
        days_flows[m] = run_day(G, L, battery, m, peak_hours, r_peak, r_offpeak)
        bills[m] = month_bill(days_flows[m], days, peak_hours, r_peak, r_offpeak,
                              export_rate, price_fn)
    chosen = min(candidates, key=lambda m: (bills[m] - (1e-9 if m == "self" else 0.0)))
    return MonthResult(mode=chosen, days=days, day=days_flows[chosen], bills=bills)


_MODE_LABEL = {"self": "Self-powered", "cost": "Cost-saving"}
_MON = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def battery_mode_summary(modes: Sequence[str]) -> str:
    """12 per-month modes → "Self-powered all year" | "Cost-saving Jan–Mar, Nov–Dec · Self-powered Apr–Oct"."""
    if not modes:
        return ""
    if len(set(modes)) == 1:
        return f"{_MODE_LABEL.get(modes[0], modes[0])} all year"
    parts = []
    for mode in dict.fromkeys(modes):                       # first-seen order
        runs, start = [], None
        for i, m in enumerate(list(modes) + [None]):
            if m == mode and start is None:
                start = i
            elif m != mode and start is not None:
                runs.append(_MON[start] if i - 1 == start else f"{_MON[start]}–{_MON[i - 1]}")
                start = None
        parts.append(f"{_MODE_LABEL.get(mode, mode)} {', '.join(runs)}")
    return " · ".join(parts)
