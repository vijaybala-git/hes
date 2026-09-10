"""
scripts/export_rate_projection.py
─────────────────────────────────
Emit the PORTABLE rate-projection bundle that WhyWatt core will consume.

This is the hand-off artifact between the offline projection sub-project and the live sim: a single,
self-contained, versioned JSON that the core reads as plain data — it must NOT need to import any
`src/rate_projection/` code. The two rate graphs (electricity + gas) and the cost calculation both
draw from this file. The consuming interface itself is designed in Phase 6; this script just fixes
the schema and content.

Contents:
  - WhyWatt scenario retail curves (conservative/moderate/stress) per fuel, per year (nominal).
  - Benchmark curves (US EIA national, EIA AEO Pacific, CEC electric, CEC gas extreme, E3 gas) for
    the comparison chart — interpolated to every year.
  - The GDP deflator index, so the consumer can render nominal OR real without any other input.
  - base rates, units, provenance, and how to apply the monthly (seasonal) shape.

Output: data/rates/projection/whywatt_rate_projection.json
Run:    .venv/Scripts/python.exe scripts/export_rate_projection.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO / "src"))
from rate_projection import ProjectedRateModel, SCENARIO_PRESETS      # noqa: E402
from rate_projection.projected_rate_model import BASE_RETAIL          # noqa: E402

PROJ = REPO / "data" / "rates" / "projection"
BENCH = PROJ / "benchmarks"
OUT = PROJ / "whywatt_rate_projection.json"
SCHEMA_VERSION = "2.0"   # 2.0 = market-keyed (multi-utility / multi-geography ready)

# How a market's scenarios were built. The schema holds either kind identically (retail per
# scenario/fuel/year); only the derivation and richness differ.
PROVIDER_TYPES = {
    "CEC-IOU": ("California IOUs. Electricity from the CEC IEPR rate workbook, gas from the CEC IEPR "
                "gas workbook, marginal cost from the CPUC ACC. Rich scenarios (RR-recovery: "
                "pruning / front-load / flat) and a modeled gas death spiral. `decomposition` present."),
    "EIA-regional": ("Other states (not yet built). EIA AEO census-division residential prices only "
                     "— a reference path ± a band for the three scenarios; no utility-specific "
                     "death-spiral detail and (usually) no `decomposition`. This is the known, "
                     "obtainable path for expanding to other geographies."),
}

# Extension points — documented, NOT built. Space in the schema for the markets that are coming.
PLANNED_MARKETS = {
    "CA_SCE":  {"label": "SCE (California)", "provider": "CEC-IOU",
                "utilities": {"electric": "SCE", "gas": "SoCalGas"},
                "geography": {"state": "CA", "census_division": "Pacific (9)"}},
    "CA_SDGE": {"label": "SDG&E / SoCalGas (California)", "provider": "CEC-IOU",
                "utilities": {"electric": "SDG&E", "gas": "SoCalGas or SDG&E"},
                "geography": {"state": "CA", "census_division": "Pacific (9)"}},
    "US_<census_division>": {"label": "Other states via EIA regional", "provider": "EIA-regional",
                             "utilities": {"electric": "state IOU", "gas": "state LDC"},
                             "geography": {"state": "<XX>", "census_division": "<EIA region>"}},
}

SCENARIO_META = {
    "conservative": {"label": "Conservative",
                     "elec": "CEC 2025 electricity trajectory, ~1%/yr below (real-declining)",
                     "gas":  "CEC Planning-Area demand, 'Pruning' cost recovery (managed decline)"},
    "moderate":     {"label": "Moderate (default)",
                     "elec": "CEC 2025 electricity trajectory (central)",
                     "gas":  "CEC Planning-Area demand, 'Front-Load' cost recovery"},
    "stress":       {"label": "Stress",
                     "elec": "CEC 2025 electricity trajectory, ~1.5%/yr above",
                     "gas":  "CEC Planning-Area demand, 'Flat/BAU' cost recovery (death spiral)"},
}


def _fill(series: dict, years) -> dict:
    """Log-linear interpolate/extend a {year:val} series to every year in `years`."""
    ax = sorted(int(y) for y in series)
    ay = np.log([float(series[str(y)] if str(y) in series else series[y]) for y in ax])
    return {str(y): round(float(np.exp(np.interp(y, ax, ay))), 6) for y in years}


def _load(name):
    return json.loads((BENCH / name).read_text())


def _real2024_to_nominal(filled, m, base=2024):
    """Inflate a real-2024$ per-year series to the bundle's nominal basis via the GDP deflator."""
    d0 = m._deflator[base]
    return {y: round(v * m._deflator[int(y)] / d0, 6)
            for y, v in filled.items() if int(y) in m._deflator}


def main():
    m = ProjectedRateModel()
    years = m.years
    Y = [str(y) for y in years]

    # WhyWatt scenario curves (nominal), + decomposition for transparency.
    scenarios = {}
    for sc, meta in SCENARIO_META.items():
        d_e, d_g = m.decompose("elec", sc), m.decompose("gas", sc)
        scenarios[sc] = {
            "label": meta["label"],
            "elec_case": meta["elec"], "gas_case": meta["gas"],
            "retail": {
                "elec": {str(y): m.retail("elec", sc)[y] for y in years},
                "gas":  {str(y): m.retail("gas", sc)[y] for y in years},
            },
            "decomposition": {   # optional: bill marginal vs residual (nominal)
                "elec": {str(y): {"mc": d_e[y]["mc"], "residual": d_e[y]["residual"]} for y in years},
                "gas":  {str(y): {"mc": d_g[y]["mc"], "residual": d_g[y]["residual"]} for y in years},
            },
        }

    # Benchmark curves for the comparison chart (interpolated to every year).
    eia = _load("eia_aeo.json")
    cec_e = json.loads((PROJ / "cec_electric_rate.json").read_text())
    cec_g = _load("cec_2025_iepr_gas.json")
    e3 = _load("e3_pathways_2020.json")
    benchmarks = {
        "eia_national": {"label": "US EIA national avg", "role": "neutral anchor (default)",
                         "elec": _fill(eia["electric"]["series"], years),
                         "gas": _fill(eia["gas"]["series"], years)},
        "eia_pacific": {"label": "EIA AEO Pacific", "role": "federal regional reference",
                        "elec": _fill(eia["pacific_aeo2026"]["electric"]["series"], years),
                        "gas": _fill(eia["pacific_aeo2026"]["gas"]["series"], years)},
        "cec_electric": {"label": "CEC 2025 (PG&E residential avg)", "role": "CA electricity authority",
                         "elec": _fill(cec_e["pge_residential_nominal"], years)},
        "cec_gas_extreme": {"label": "CEC extreme (GT AAFS, Flat RR)", "role": "gas death-spiral upper bound",
                            # cec_2025_iepr_gas.json (tn=264063) is REAL 2024$; inflate to the bundle's nominal basis
                            "gas": _real2024_to_nominal(_fill(cec_g["gas"]["series"], years), m)},
        "e3_gas": {"label": "E3 2020 (managed high-electrification)", "role": "independent gas high case",
                   "gas": _fill(e3["gas"]["nominal_therm_approx"], years)},
    }

    deflator = json.loads((PROJ / "gdp_deflator.json").read_text())

    # ── One market: PG&E / California. Others (§PLANNED_MARKETS) slot in beside it. ──
    ca_pge = {
        "label": "PG&E (California)",
        "provider": "CEC-IOU",
        "geography": {"state": "CA", "area": "SF Bay Area / South Bay",
                      "climate_zone": "CZ4", "census_division": "Pacific (9)"},
        "utilities": {"electric": "PG&E (E-1)", "gas": "PG&E (G-1)"},
        "base_retail": {"elec": BASE_RETAIL["elec"], "gas": BASE_RETAIL["gas"]},
        "base_retail_note": ("Anchored to the PG&E E-1/G-1 tariff. Scenario curves follow the CEC "
                             "trajectory but sit ~7% below the CEC blended-residential line by this "
                             "base choice, not a growth difference."),
        "default_scenario": "moderate",
        "monthly_shape": {
            "note": ("ANNUAL rate levels. Apply the existing ACC monthly (seasonal) shape to "
                     "distribute within the year, as the live sim already does."),
            "elec_shape_file": "data/rates/acc_electric_shape_pge_2024.json",
            "gas_shape_file": "data/rates/acc_gas_shape_pge_2024.json",
        },
        "scenarios": scenarios,      # each scenario carries retail + (CEC-IOU) decomposition
        "benchmarks": benchmarks,
        "provenance": {
            "electricity": "CEC 2025 IEPR Electricity Rate Forecast, efiling tn=268239 (PG&E residential)",
            "gas": "CEC 2025 IEPR Gas Rate Forecast, efiling tn=264063 (PG&E residential, Planning-Area demand)",
            "marginal_cost": "CPUC 2024 Avoided Cost Calculator (built by E3), CZ4",
            "benchmarks": "US EIA (EPM 5.6.A, NG Monthly, AEO 2026 Pacific), E3 2020 'Challenge of Retail Gas'",
        },
    }

    bundle = {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "description": ("Portable rate-projection bundle for WhyWatt core. Read as plain data — no "
                        "dependency on src/rate_projection/. Phase 6 designs the consuming interface. "
                        "Market-keyed so other utilities and geographies slot in beside PG&E."),
        # ── shared across all markets ──
        "base_year": m.base_year,
        "horizon": [years[0], years[-1]],
        "years": years,
        "fuels": ["elec", "gas"],
        "units": {"elec": "$/kWh", "gas": "$/therm"},
        "basis": "nominal",
        "scenario_keys": list(scenarios),   # same three keys across every market
        "deflator": {
            "index_base_year": deflator["index_base_year"],
            "note": "real(y) = nominal(y) * deflator[b] / deflator[y]; pick b for the real base year.",
            "index": deflator["deflator"],
        },
        # ── the extension axis: markets, and how each is sourced ──
        "provider_types": PROVIDER_TYPES,
        "default_market": "CA_PGE",
        "markets": {"CA_PGE": ca_pge},
        "planned_markets": PLANNED_MARKETS,   # documented, not yet built — schema space only
        "provenance": {
            "deflator": "CEC 2023 IEPR GDP deflator",
            "built_by": "scripts/export_rate_projection.py from data/rates/projection/*",
        },
    }
    OUT.write_text(json.dumps(bundle, indent=2))
    print(f"Wrote {OUT}")
    print(f"  schema {SCHEMA_VERSION} | markets {list(bundle['markets'])} "
          f"(+{len(PLANNED_MARKETS)} planned) | {len(years)} years {years[0]}-{years[-1]}")
    print(f"  CA_PGE moderate elec 2050 ${scenarios['moderate']['retail']['elec']['2050']}/kWh | "
          f"gas 2050 ${scenarios['moderate']['retail']['gas']['2050']}/therm")


if __name__ == "__main__":
    main()
