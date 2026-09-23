"""Hourly energy balance — each battery mode run on its own, plus the auto picker (Phase 7 §0/§2).

Matrix: homes (small/large solar × battery/none × EV/no EV) × tariffs (flat + four URDB TOU plans)
× months (Jan, Jul) × modes (self, cost, cost without grid charging, auto). Every run is checked
against the energy-balance identities, and a readable log is written to
tests/regression/dispatch_modes.md (regenerated each run, git-ignored like report.md).

An offline linear-program optimum is the benchmark: the two-mode picker should capture most of
the battery's achievable value (Phase 7 §0 — "within a few percent", logged per case).
"""
import json
import sys
from itertools import product
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dispatch import (BatteryParams, battery_mode_summary, dispatch_month,  # noqa: E402
                      month_bill, run_day)
from solar_loader import get_loader  # noqa: E402

LOG = ROOT / "tests" / "regression" / "dispatch_modes.md"
DAYS = {0: 31, 6: 31}
EXPORT = 0.06                                         # NEM 3.0-like export credit, $/kWh
ETA = 0.90
TOL = 1e-6

_prof = json.loads((ROOT / "data/rates/device_load_shapes.json").read_text(encoding="utf-8"))
SHAPE = {k: np.asarray(v, float) / np.sum(v) for k, v in _prof["profiles"].items()}
_URDB = json.loads((ROOT / "data/rates/urdb_tou.json").read_text(encoding="utf-8"))["utilities"]


def _tariff(eiaid, family):
    t = next(t for t in _URDB[eiaid]["tariffs"].values() if t["family"] == family)
    return t


def tariff_rates(name, month):
    """(peak_hours, r_peak, r_offpeak) — tier-1 rates for the month."""
    if name == "flat":
        return (), 0.40, 0.40
    eiaid, family = {"E-TOU-C": ("14328", "E-TOU-C"), "E-ELEC": ("14328", "E-ELEC"),
                     "EV2": ("14328", "EV2"), "TOU-DR-1": ("16609", "TOU-DR-1")}[name]
    t = _tariff(eiaid, family)
    bm = t["by_month"][month]
    return tuple(t["peak_hours"]), bm["peak"][0]["rate"], bm["offpeak"][0]["rate"]


def home(solar_kw, month, ev):
    res = get_loader().resolve("95112")
    G = solar_kw * res.ac_monthly[month] / DAYS[month] * res.intraday_shape[month]
    hvac = "hvac_heat" if month == 0 else "hvac_cool"
    L = 12 * SHAPE["baseload"] + 6 * SHAPE[hvac] + 3 * SHAPE["hpwh"] + (10 * SHAPE["ev"] if ev else 0)
    return G, L


HOMES = [(kw, batt, ev) for kw, batt, ev in product((2.0, 7.0), (13.5, 0.0), (False, True))]
TARIFFS = ["flat", "E-TOU-C", "E-ELEC", "EV2", "TOU-DR-1"]
MONTHS = [0, 6]
MODES = [("self", True), ("cost", True), ("cost", False)]           # (mode, grid_charging)


def check_identities(d, G, L, b: BatteryParams):
    assert np.allclose(G, d.solar_direct + d.charge_solar + d.export, atol=TOL)
    assert np.allclose(L, d.solar_direct + d.discharge + d.grid_to_home, atol=TOL)
    for arr in (d.solar_direct, d.charge_solar, d.charge_grid, d.discharge, d.export, d.grid_to_home):
        assert (arr >= -TOL).all()
    assert (d.charge_solar + d.charge_grid <= b.power_kw + TOL).all()
    assert (d.discharge <= b.power_kw + TOL).all()
    stored_in = (d.charge_solar.sum() + d.charge_grid.sum()) * b.round_trip_eff
    assert stored_in == pytest.approx(d.discharge.sum(), abs=1e-6)      # steady state + η
    if b.cap_kwh == 0:
        assert d.charge_solar.sum() == d.charge_grid.sum() == d.discharge.sum() == 0


def lp_optimum(G, L, b: BatteryParams, peak_hours, r_peak, r_off):
    """Best possible daily bill (cyclic battery, same rules: solar or grid charging, no battery
    export). Returns the daily $ bill."""
    from scipy.optimize import linprog
    H, sq = 24, np.sqrt(b.round_trip_eff)
    rate = np.array([r_peak if h in peak_hours else r_off for h in range(H)])
    # variables per hour: direct, cs, cg, dis, exp, gh ; then soc[0..23]
    nv = 6 * H + H
    idx = lambda k, h: k * H + h                                           # noqa: E731
    soc = lambda h: 6 * H + (h % H)                                        # noqa: E731
    c = np.zeros(nv)
    for h in range(H):
        c[idx(5, h)] = rate[h]
        c[idx(2, h)] = rate[h]
        c[idx(4, h)] = -EXPORT
    A_eq, b_eq = [], []
    for h in range(H):
        row = np.zeros(nv); row[[idx(0, h), idx(1, h), idx(4, h)]] = 1; A_eq.append(row); b_eq.append(G[h])
        row = np.zeros(nv); row[[idx(0, h), idx(3, h), idx(5, h)]] = 1; A_eq.append(row); b_eq.append(L[h])
        row = np.zeros(nv); row[soc(h + 1)] = 1; row[soc(h)] = -1
        row[idx(1, h)] = row[idx(2, h)] = -sq; row[idx(3, h)] = 1 / sq
        A_eq.append(row); b_eq.append(0.0)
    A_ub, b_ub = [], []
    for h in range(H):
        row = np.zeros(nv); row[[idx(1, h), idx(2, h)]] = 1; A_ub.append(row); b_ub.append(b.power_kw)
        row = np.zeros(nv); row[idx(3, h)] = 1; A_ub.append(row); b_ub.append(b.power_kw)
    bounds = [(0, None)] * (6 * H) + [(0, b.cap_kwh)] * H
    if not b.grid_charging:
        for h in range(H):
            bounds[idx(2, h)] = (0, 0)
    r = linprog(c, A_ub=np.array(A_ub), b_ub=b_ub, A_eq=np.array(A_eq), b_eq=b_eq,
                bounds=bounds, method="highs")
    assert r.success, r.message
    return float(r.fun)


def _cases():
    for (kw, cap, ev), tname, month in product(HOMES, TARIFFS, MONTHS):
        yield kw, cap, ev, tname, month


@pytest.fixture(scope="module")
def log_rows():
    rows = []
    yield rows
    head = ("| home | tariff | month | mode | direct | batt→home | grid→batt | export | "
            "grid import | bill $/mo | auto picks | LP $/mo | value captured |")
    lines = ["# Battery dispatch — per-mode log",
             "",
             "Generated by `tests/test_battery.py` (Phase 7 §0/§2). kWh per representative day; "
             "bills per month. *Value captured* = (no-battery bill − auto bill) / (no-battery "
             "bill − LP optimum bill).",
             "", head, "|" + "---|" * 13]
    lines += rows
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.mark.parametrize("kw,cap,ev,tname,month", list(_cases()))
def test_each_mode_and_auto(kw, cap, ev, tname, month, log_rows):
    G, L = home(kw, month, ev)
    P, rp, ro = tariff_rates(tname, month)
    days = DAYS[month]
    label = f"{kw:.0f} kW · {'13.5 kWh' if cap else 'no batt'} · {'EV' if ev else 'no EV'}"
    bills = {}
    for mode, gc in MODES:
        b = BatteryParams(cap_kwh=cap, round_trip_eff=ETA, grid_charging=gc)
        d = run_day(G, L, b, mode, P, rp, ro)
        check_identities(d, G, L, b)
        if mode == "cost" and (not gc or ETA * rp <= ro):
            assert d.charge_grid.sum() == 0                     # no top-up unless it pays + allowed
        if mode == "self":
            assert d.charge_grid.sum() == 0                     # Self-powered never grid-charges
        bill = month_bill(d, days, P, rp, ro, EXPORT)
        key = mode if gc or mode == "self" else "cost-nogrid"
        bills[key] = bill
        log_rows.append(
            f"| {label} | {tname} | {'Jan' if month == 0 else 'Jul'} | {key} | "
            f"{d.solar_direct.sum():.2f} | {d.discharge.sum():.2f} | {d.charge_grid.sum():.2f} | "
            f"{d.export.sum():.2f} | {d.grid_import.sum():.2f} | {bill:,.2f} | | | |")

    b = BatteryParams(cap_kwh=cap, round_trip_eff=ETA, grid_charging=True)
    auto = dispatch_month(G, L, b, days=days, mode="auto", peak_hours=P, r_peak=rp,
                          r_offpeak=ro, export_rate=EXPORT)
    auto_bill = auto.bills[auto.mode]
    assert auto_bill <= min(bills["self"], bills["cost"]) + 1e-9
    if not P or cap == 0:
        assert auto.mode == "self"

    lp_cell = cap_cell = ""
    if cap > 0:
        pytest.importorskip("scipy")
        lp = lp_optimum(G, L, b, P, rp, ro) * days
        none = month_bill(run_day(G, L, BatteryParams(cap_kwh=0.0), "self"), days, P, rp, ro, EXPORT)
        assert lp <= auto_bill + 1e-6                            # the optimum is never worse
        span = none - lp
        captured = (none - auto_bill) / span if span > 1e-6 else 1.0
        lp_cell, cap_cell = f"{lp:,.2f}", f"{captured:.0%}"
        # Two-period tariffs without tiers: the two modes reach the LP optimum (measured 100%
        # on this matrix). Tiers or 3-period tariffs may open a gap — then add a smarter mode.
        assert captured >= 0.99, f"auto captures only {captured:.1%} of the battery value"
    log_rows.append(
        f"| {label} | {tname} | {'Jan' if month == 0 else 'Jul'} | **auto** | | | | | | "
        f"**{auto_bill:,.2f}** | {auto.mode} | {lp_cell} | {cap_cell} |")


def test_mode_summary_text():
    assert battery_mode_summary(["self"] * 12) == "Self-powered all year"
    s = battery_mode_summary(["cost"] * 3 + ["self"] * 7 + ["cost"] * 2)
    assert s == "Cost-saving Jan–Mar, Nov–Dec · Self-powered Apr–Oct"


def test_unknown_mode_rejected():
    G, L = home(2.0, 0, False)
    with pytest.raises(ValueError):
        dispatch_month(G, L, BatteryParams(13.5), days=31, mode="greedy")
