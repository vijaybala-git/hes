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

# SVG (vector text), not PNG: Hugging Face pushes binary images through Git-Xet/LFS and
# rejects an untracked one even when small; an SVG is plain text, so it deploys as a normal
# file, stays crisp, and renders in the guide's <img>.
OUT = REPO / "public" / "help" / "rate_projection_curves.svg"

YEARS = list(range(2025, 2051))          # bundle horizon 2025-2050
REAL_BASE = 2024                         # canonical reporting basis: real 2024$ (matches the CEC anchors)

# (model_key, colour, linestyle) per fuel — the models a user can actually select.
# CEC lines are SOLID (a distinct colour) so they don't read as a scenario band; EIA
# references stay dotted. Endpoint labels (below) carry the exact 2050 level.
_ELEC = [("whywatt_conservative", "#2E7D32", "-"),
         ("whywatt_moderate",     "#F9A825", "-"),
         ("whywatt_stress",       "#C62828", "-"),
         ("cec_iepr",             "#1565C0", "-"),
         ("eia_pacific",          "#00838F", ":"),
         ("eia_national",         "#757575", ":")]
_GAS  = [("whywatt_conservative", "#2E7D32", "-"),
         ("whywatt_moderate",     "#F9A825", "-"),
         ("whywatt_stress",       "#C62828", "-"),
         ("cec_bau",              "#6A1B9A", "-"),
         ("eia_pacific",          "#00838F", ":"),
         ("eia_national",         "#757575", ":")]


def _real2024(index: dict):
    """Deflator factor year -> multiply a nominal $ by it to get real 2024$."""
    d0 = float(index[str(REAL_BASE)])
    return {y: d0 / float(index[str(y)]) for y in YEARS if str(y) in index}


def _series(model_key: str, fuel: str, factor: dict) -> np.ndarray:
    """Model rate per year, converted from the bundle's nominal $ to real 2024$."""
    src = ProjectedRateSource(model_key, fuel)
    return np.array([src.get_rate(fuel, y, 1) * factor[y] for y in YEARS])


def _fmt(v: float) -> str:
    return f"${v:,.2f}" if v < 10 else f"${v:,.0f}"


def _esc(s: str) -> str:
    r"""Escape literal $ so matplotlib doesn't treat a pair of them as math mode."""
    return s.replace("$", r"\$")


def main():
    b = _bundle()
    base = b["markets"][b["default_market"]]["base_retail"]
    factor = _real2024(b["deflator"]["index"])

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    xmax = YEARS[-1]
    for ax, fuel, unit, models, logy in [
            (axes[0], "electricity", "$/kWh", _ELEC, False),
            (axes[1], "gas", "$/therm", _GAS, True)]:
        for mk, colour, ls in models:
            ys = _series(mk, fuel, factor)
            ax.plot(YEARS, ys, ls, color=colour, lw=2, label=PROJECTION_LABELS[mk])
            # Endpoint (2050) label — the log gas axis makes exact levels hard to read.
            ax.annotate(_esc(_fmt(float(ys[-1]))), xy=(xmax, ys[-1]), xytext=(4, 0),
                        textcoords="offset points", va="center", ha="left",
                        fontsize=7, fontweight="bold", color=colour)
        ax.set_title(_esc(f"{fuel.title()}  ({unit}, real 2024$)"), fontsize=11, fontweight="bold")
        ax.set_xlabel("Year"); ax.set_ylabel(_esc(unit))
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7.5, loc="upper left")
        ax.set_xlim(2025, xmax + (xmax - 2025) * 0.16)   # room for the endpoint labels
        if logy:
            ax.set_yscale("log")
            ax.set_ylabel(_esc(unit + "  (log scale)"))

    anchor = _esc(f"Anchored to the PG&E tariff (elec ${base['elec']:.3f}/kWh, "
                  f"gas ${base['gas']:.2f}/therm at 2025). Real 2024$ (inflation removed). "
                  "Source: whywatt_rate_projection.json (CEC 2025 IEPR / EIA AEO).")
    fig.suptitle(_esc("WhyWatt projected retail rates — selectable rate models, 2025–2050 (real 2024$)"),
                 fontsize=12.5, fontweight="bold")
    fig.text(0.5, 0.005, anchor, ha="center", fontsize=7.5, color="#555")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, format="svg", facecolor="white")
    plt.close(fig)
    print(f"wrote {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
