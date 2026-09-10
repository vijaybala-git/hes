"""scripts/build_impact_report_charts.py — bar charts for the rate-model impact report.

Reads tests/validation/rate_model_impact.json and renders one savings bar chart per
impact scenario (journey vs do-nothing, plus 20-yr net savings), into
docs/reports/assets/. Referenced from docs/reports/RateModel_Impact_Report.md.

Usage:  .venv/Scripts/python.exe scripts/build_impact_report_charts.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "tests" / "validation" / "rate_model_impact.json"
OUT = REPO / "docs" / "reports" / "assets"
OUT.mkdir(parents=True, exist_ok=True)

# Rate models in a fixed narrative order: references first, WhyWatt band, CEC, EIA.
MODEL_ORDER = [
    ("legacy_default_cagr", "Legacy\nCAGR-flat"),
    ("legacy_acc",          "Legacy\nACC"),
    ("whywatt_conservative","WhyWatt\nConservative"),
    ("whywatt_moderate",    "WhyWatt\nModerate"),
    ("whywatt_stress",      "WhyWatt\nStress"),
    ("cec_deathspiral",     "CEC IEPR\n+ BAU gas"),
    ("eia_national",        "EIA\nNational"),
    ("eia_pacific",         "EIA\nPacific"),
]

POS = "#2E7D32"   # savings (green)
NEG = "#C62828"   # net cost (red)
JOURNEY = "#1565C0"
DONOTHING = "#9E9E9E"


def _fmt_k(x, _pos=None):
    return f"${x/1000:.0f}k"


def savings_chart(scen_key, scen):
    runs = scen["runs"]
    keys = [k for k, _ in MODEL_ORDER if k in runs]
    labels = [lab for k, lab in MODEL_ORDER if k in runs]
    deltas = [runs[k]["opex_delta"] for k in keys]
    paybacks = [runs[k]["payback_year"] for k in keys]
    colours = [POS if d >= 0 else NEG for d in deltas]

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(labels, deltas, color=colours, width=0.66)
    ax.axhline(0, color="#333", lw=0.9)
    ax.set_ylabel("20-yr net savings from electrifying  ($, do-nothing − journey)")
    ax.set_title(f"{scen['description']}", fontsize=10.5, fontweight="bold", pad=26)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(_fmt_k))
    ax.grid(axis="y", alpha=0.3)
    ax.margins(y=0.16)

    for bar, d, pb in zip(bars, deltas, paybacks):
        h = bar.get_height()
        va = "bottom" if h >= 0 else "top"
        off = 0.01 * (ax.get_ylim()[1] - ax.get_ylim()[0])
        ax.text(bar.get_x() + bar.get_width() / 2, h + (off if h >= 0 else -off),
                f"${d/1000:+.0f}k", ha="center", va=va, fontsize=8, fontweight="bold")
        pb_txt = f"payback\nyr {pb}" if pb else "no\npayback"
        ax.text(bar.get_x() + bar.get_width() / 2, 0, pb_txt,
                ha="center", va="center", fontsize=6.8, color="#fff",
                bbox=dict(boxstyle="round,pad=0.18", fc="#00000055", ec="none"))

    fig.text(0.5, 0.015,
             "Green = the electrification journey costs less over 20 years than doing nothing. "
             "Red = the journey costs more. Same house, same choices — only the rate assumption changes.",
             ha="center", fontsize=7.5, color="#555")
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    p = OUT / f"impact_{scen_key}.png"
    fig.savefig(p, dpi=140, facecolor="white")
    plt.close(fig)
    print(f"wrote {p.relative_to(REPO)}")


def journey_vs_donothing_chart(scen_key, scen):
    runs = scen["runs"]
    keys = [k for k, _ in MODEL_ORDER if k in runs]
    labels = [lab for k, lab in MODEL_ORDER if k in runs]
    journey = [runs[k]["journey_cumulative_opex"] for k in keys]
    donothing = [runs[k]["baseline_cumulative_opex"] for k in keys]

    x = np.arange(len(keys))
    w = 0.38
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(x - w / 2, journey, w, color=JOURNEY, label="Your journey (electrify)")
    ax.bar(x + w / 2, donothing, w, color=DONOTHING, label="Do nothing (stay on gas)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Cumulative energy bill over the horizon  ($)")
    ax.set_title(f"{scen['description']}", fontsize=10.5, fontweight="bold")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(_fmt_k))
    ax.grid(axis="y", alpha=0.3)
    ax.legend(fontsize=8.5, loc="upper right")
    fig.tight_layout()
    p = OUT / f"bills_{scen_key}.png"
    fig.savefig(p, dpi=140, facecolor="white")
    plt.close(fig)
    print(f"wrote {p.relative_to(REPO)}")


def main():
    data = json.loads(SRC.read_text())
    for scen_key, scen in data["scenarios"].items():
        savings_chart(scen_key, scen)
    # One bill-level chart for the headline scenario (full electrification + solar).
    journey_vs_donothing_chart("full_electrification_solar",
                               data["scenarios"]["full_electrification_solar"])
    journey_vs_donothing_chart("hvac2027_wh2029",
                               data["scenarios"]["hvac2027_wh2029"])


if __name__ == "__main__":
    main()
