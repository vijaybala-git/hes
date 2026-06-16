"""Render climate-lookup verification graphs (Phase 4 §1, Step 2c).

Standalone — does NOT touch the Solara app. Produces PNGs proving:
  1. ZIP/zone lookup yields contrasting climates (annual + monthly HDD/CDD per zone).
  2. The Option-B trend trajectory works (annual HDD/CDD over the horizon, None/RCP4.5/RCP8.5).

Run:  python scripts/preview_climate.py
Out:  build/climate_preview/*.png
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from climate_loader import ClimateLoader  # noqa: E402

OUT = Path(__file__).parent.parent / "build" / "climate_preview"
OUT.mkdir(parents=True, exist_ok=True)

MONTHS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]
ZONE_ZIPS = {"95110": "San Jose (CZ4)", "93720": "Fresno (CZ13)", "96161": "Blue Canyon (CZ16)"}
_HDD_C, _CDD_C = "#1565C0", "#D85A30"


def fig_zone_contrast(loader: ClimateLoader) -> Path:
    climates = {label: loader.get_climate(z) for z, label in ZONE_ZIPS.items()}
    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(12, 4.6), dpi=120)

    # (a) annual HDD/CDD grouped bars
    labels = list(climates)
    x = np.arange(len(labels))
    hdd = [c.annual_hdd_65f for c in climates.values()]
    cdd = [c.annual_cdd_65f for c in climates.values()]
    ax_a.bar(x - 0.2, hdd, 0.4, label="Annual HDD", color=_HDD_C)
    ax_a.bar(x + 0.2, cdd, 0.4, label="Annual CDD", color=_CDD_C)
    ax_a.set_xticks(x); ax_a.set_xticklabels(labels, fontsize=10)
    ax_a.set_ylabel("degree-days / yr (base 65°F)")
    ax_a.set_title("Annual heating vs. cooling load by zone", fontsize=12, fontweight="bold")
    ax_a.legend(fontsize=10)
    for xi, (h, c) in enumerate(zip(hdd, cdd)):
        ax_a.text(xi - 0.2, h + 40, f"{h:,.0f}", ha="center", fontsize=8)
        ax_a.text(xi + 0.2, c + 40, f"{c:,.0f}", ha="center", fontsize=8)

    # (b) monthly HDD (solid) + CDD (dashed) profiles
    mx = np.arange(12)
    for label, c in climates.items():
        line, = ax_b.plot(mx, c.monthly_hdd, marker="o", ms=4, label=f"{label} HDD")
        ax_b.plot(mx, c.monthly_cdd, marker="s", ms=4, ls="--", color=line.get_color())
    ax_b.set_xticks(mx); ax_b.set_xticklabels(MONTHS, fontsize=9)
    ax_b.set_ylabel("monthly degree-days")
    ax_b.set_title("Monthly profile — HDD (solid) · CDD (dashed)", fontsize=12, fontweight="bold")
    ax_b.legend(fontsize=8, ncol=1)
    ax_b.grid(alpha=0.25)

    fig.tight_layout()
    p = OUT / "zone_contrast.png"
    fig.savefig(p); plt.close(fig)
    return p


def fig_trend_trajectory(loader: ClimateLoader, zipcode="93720", n_years=25) -> Path:
    label = ZONE_ZIPS.get(zipcode, zipcode)
    scenarios = {"none": ("None (static)", "#888780"),
                 "rcp45": ("RCP 4.5 (moderate)", "#1D9E75"),
                 "rcp85": ("RCP 8.5 (high)", "#C0392B")}
    fig, (ax_h, ax_c) = plt.subplots(1, 2, figsize=(12, 4.6), dpi=120)
    yrs = np.arange(1, n_years + 1)
    for scn, (name, color) in scenarios.items():
        c = loader.get_climate(zipcode, n_years=n_years, trend_scenario=scn)
        ax_h.plot(yrs, c.hdd_traj.sum(axis=1), color=color, lw=2, label=name)
        ax_c.plot(yrs, c.cdd_traj.sum(axis=1), color=color, lw=2, label=name)
    ax_h.set_title(f"Annual HDD over horizon — {label}", fontsize=12, fontweight="bold")
    ax_c.set_title(f"Annual CDD over horizon — {label}", fontsize=12, fontweight="bold")
    for ax, ylab in ((ax_h, "HDD / yr (warmer winters ↓)"), (ax_c, "CDD / yr (hotter summers ↑)")):
        ax.set_xlabel("simulation year"); ax.set_ylabel(ylab)
        ax.legend(fontsize=9); ax.grid(alpha=0.25)
    fig.tight_layout()
    p = OUT / "trend_trajectory.png"
    fig.savefig(p); plt.close(fig)
    return p


def main():
    loader = ClimateLoader()
    paths = [fig_zone_contrast(loader), fig_trend_trajectory(loader)]
    for p in paths:
        print(f"wrote {p}")


if __name__ == "__main__":
    main()
