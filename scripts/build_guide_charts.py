"""scripts/build_guide_charts.py — render the rate-projection curves for the help guide.

Reads the committed projection bundle via the core ProjectedRateSource (the exact series the
sim prices off) and plots every selectable rate model, per fuel, 2025-2050, to a PNG served
with the methodology guide (public/help/rate_projection_curves.png). Referenced from
docs/help/rate_projection_guide.md. Regenerate whenever the bundle changes.

Usage:  python scripts/build_guide_charts.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from projected_rate_source import ProjectedRateSource, PROJECTION_LABELS, _bundle

OUT = REPO / "public" / "help" / "rate_projection_curves.png"

YEARS = list(range(2025, 2051))          # bundle horizon 2025-2050

# (model_key, colour, linestyle) per fuel — the models a user can actually select.
_ELEC = [("whywatt_conservative", "#2E7D32", "-"),
         ("whywatt_moderate",     "#F9A825", "-"),
         ("whywatt_stress",       "#C62828", "-"),
         ("cec_iepr",             "#1565C0", "--"),
         ("eia_pacific",          "#00838F", ":"),
         ("eia_national",         "#757575", ":")]
_GAS  = [("whywatt_conservative", "#2E7D32", "-"),
         ("whywatt_moderate",     "#F9A825", "-"),
         ("whywatt_stress",       "#C62828", "-"),
         ("cec_bau",              "#6A1B9A", "--"),
         ("eia_pacific",          "#00838F", ":"),
         ("eia_national",         "#757575", ":")]


def _series(model_key: str, fuel: str) -> np.ndarray:
    src = ProjectedRateSource(model_key, fuel)
    return np.array([src.get_rate(fuel, y, 1) for y in YEARS])


def main():
    b = _bundle()
    base = b["markets"][b["default_market"]]["base_retail"]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    for ax, fuel, unit, models, logy in [
            (axes[0], "electricity", "$/kWh", _ELEC, False),
            (axes[1], "gas", "$/therm", _GAS, True)]:
        for mk, colour, ls in models:
            ax.plot(YEARS, _series(mk, fuel), ls, color=colour, lw=2,
                    label=PROJECTION_LABELS[mk])
        ax.set_title(f"{fuel.title()}  ({unit})", fontsize=11, fontweight="bold")
        ax.set_xlabel("Year"); ax.set_ylabel(unit)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7.5, loc="upper left")
        if logy:
            ax.set_yscale("log")
            ax.set_ylabel(unit + "  (log scale)")

    anchor = (f"Anchored to the PG&E tariff (elec ${base['elec']:.3f}/kWh, "
              f"gas ${base['gas']:.2f}/therm at 2025). Nominal $. "
              "Source: whywatt_rate_projection.json (CEC 2025 IEPR / EIA AEO).")
    fig.suptitle("WhyWatt projected retail rates — selectable rate models, 2025–2050",
                 fontsize=12.5, fontweight="bold")
    fig.text(0.5, 0.005, anchor, ha="center", fontsize=7.5, color="#555")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=120, facecolor="white")
    plt.close(fig)
    print(f"wrote {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
