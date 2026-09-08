"""scripts/validate_rate_models.py — Phase 6 WS1 rate-impact validation harness.

Runs a fixed electrification scenario (HVAC swap 2027, Water Heater swap 2029) through the
REAL headless pipeline (ui.sim.run_simulation / extract_metrics) under every rate model —
the legacy defaults (CAGR-flat / ACC) AND the new projection models (WhyWatt / EIA / CEC) —
and saves a structured snapshot + a readable table.

Purpose: a stable, committed output the team can diff "as we move" and use offline to write up
the *impact of the new rate modeling*. This is NOT the golden gate (that's run_regression.py);
it deliberately exercises the non-default projection paths, which are expected to change numbers.

Usage:
  python scripts/validate_rate_models.py            # run + write JSON + MD
  python scripts/validate_rate_models.py --print     # also echo the table to the console
"""
from __future__ import annotations

import sys
import json
import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

OUT_DIR = REPO / "tests" / "validation"
OUT_JSON = OUT_DIR / "rate_model_impact.json"
OUT_MD = OUT_DIR / "rate_model_impact.md"

# ── Scenarios (the home + plan; rate model is applied on top per run) ───────────
# HVAC swap year 3 = 2027, WH swap year 5 = 2029 (sim_start_year 2025, year 1 = 2025).
_HVAC_WH = {
    "hvac_swap_planned": True, "hvac_swap_year": 3,     # 2027
    "wh_swap_planned":   True, "wh_swap_year":   5,     # 2029
    "dryer_swap_planned": False, "cooktop_swap_planned": False, "ev_swap_planned": False,
}
SCENARIOS: dict[str, dict] = {
    "hvac2027_wh2029": {
        "description": "HVAC swap 2027 + Water Heater swap 2029 only (the requested scenario).",
        "values": dict(_HVAC_WH),
    },
    # Suggested extra combo (from regression case 01): the full electrification journey, so the
    # report can show how the rate model impact scales with more electrified load.
    "full_electrification_2027_29": {
        "description": "HVAC 2027 + WH 2029 + dryer/cooktop/EV planned; 200 A panel (case 01 style).",
        "values": {**_HVAC_WH, "dryer_swap_planned": True, "cooktop_swap_planned": True,
                   "ev_swap_planned": True, "panel_amps": 200},
    },
}

# ── Rate-model matrix (elec model, gas model) applied to each scenario ──────────
# The projection models are fuel-aware: cec_iepr is elec-only, cec_bau/e3_gas are gas-only.
RATE_RUNS: dict[str, dict] = {
    "legacy_default_cagr":  {"label": "Legacy default (CAGR-flat, EIA per-utility)",
                             "elec": "cagr_flat",  "gas": "cagr_flat"},
    "legacy_acc":           {"label": "Legacy ACC (PG&E/CPUC base)",
                             "elec": "acc_shaped", "gas": "acc_seasonal"},
    "whywatt_conservative": {"label": "WhyWatt Conservative",
                             "elec": "whywatt_conservative", "gas": "whywatt_conservative"},
    "whywatt_moderate":     {"label": "WhyWatt Moderate",
                             "elec": "whywatt_moderate",     "gas": "whywatt_moderate"},
    "whywatt_stress":       {"label": "WhyWatt Stress",
                             "elec": "whywatt_stress",       "gas": "whywatt_stress"},
    "cec_deathspiral":      {"label": "CEC 2025 IEPR (elec) + CEC 2025 BAU-invest (gas)",
                             "elec": "cec_iepr",   "gas": "cec_bau"},
    "eia_national":         {"label": "US EIA national average",
                             "elec": "eia_national", "gas": "eia_national"},
    "eia_pacific":          {"label": "EIA AEO Pacific",
                             "elec": "eia_pacific",  "gas": "eia_pacific"},
}

# Baseline run each scenario's deltas are measured against (the current app default).
_REF_RUN = "legacy_default_cagr"


def _run(scenario_values: dict, elec_model: str, gas_model: str) -> dict:
    from run_regression import run_values      # reuses reset_to_defaults + apply_config + run
    values = {**scenario_values,
              "elec_rate_model_a": elec_model, "gas_rate_model_a": gas_model}
    return run_values(values)


def build() -> dict:
    out = {
        "generated_utc": datetime.datetime.now(datetime.timezone.utc)
                           .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": ("Rate-model impact snapshot (Phase 6 WS1). Non-default projection paths are "
                 "exercised deliberately — this is not the golden. sim_start_year=2025, "
                 "20-year horizon (app default); HVAC swap 2027, WH swap 2029."),
        "reference_run": _REF_RUN,
        "scenarios": {},
    }
    for sname, sdef in SCENARIOS.items():
        runs = {}
        for rname, rdef in RATE_RUNS.items():
            m = _run(sdef["values"], rdef["elec"], rdef["gas"])
            c = m["cockpit"]
            runs[rname] = {
                "label": rdef["label"],
                "elec_model": rdef["elec"], "gas_model": rdef["gas"],
                "journey_cumulative_opex":  c["journey_cumulative_opex"],
                "baseline_cumulative_opex": c["baseline_cumulative_opex"],
                "opex_delta":               c["opex_delta"],          # baseline - journey
                "payback_year":             c["payback_year"],
                "net_social_cost_avoided":  c["net_social_cost_avoided"],
            }
        # deltas vs the reference (legacy default) — the "impact of new rate modeling"
        ref = runs[_REF_RUN]
        for rname, r in runs.items():
            r["opex_delta_vs_reference"] = r["opex_delta"] - ref["opex_delta"]
            r["baseline_vs_reference"] = (r["baseline_cumulative_opex"]
                                          - ref["baseline_cumulative_opex"])
        out["scenarios"][sname] = {"description": sdef["description"], "runs": runs}
    return out


def to_markdown(out: dict) -> str:
    L = ["# Rate-model impact — validation snapshot", "",
         f"_Generated {out['generated_utc']}._  ", out["note"], "",
         f"Deltas are vs the reference run **`{out['reference_run']}`** (current app default). "
         "`opex_delta` = do-nothing − journey (positive = the journey saves money).", ""]
    for sname, sdef in out["scenarios"].items():
        L += [f"## {sname}", "", sdef["description"], "",
              "| Rate model | Journey $ | Do-nothing $ | Savings (Δopex) | Payback | "
              "Savings vs ref | Do-nothing vs ref |",
              "|---|--:|--:|--:|:--:|--:|--:|"]
        for rname, r in sdef["runs"].items():
            pb = r["payback_year"] if r["payback_year"] is not None else "—"
            L.append(
                f"| {r['label']} | {r['journey_cumulative_opex']:,} | "
                f"{r['baseline_cumulative_opex']:,} | {r['opex_delta']:,} | {pb} | "
                f"{r['opex_delta_vs_reference']:+,} | {r['baseline_vs_reference']:+,} |")
        L.append("")
    return "\n".join(L)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = build()
    OUT_JSON.write_text(json.dumps(out, indent=2), encoding="utf-8")
    md = to_markdown(out)
    OUT_MD.write_text(md, encoding="utf-8")
    print(f"wrote {OUT_JSON.relative_to(REPO)}")
    print(f"wrote {OUT_MD.relative_to(REPO)}")
    if "--print" in sys.argv:
        print("\n" + md)


if __name__ == "__main__":
    main()
