"""
scripts/build_rate_projection.py
────────────────────────────────
OFFLINE harvest for the rate-projection sub-project (docs/OfflineRateProjection_Plan.md).
Run MANUALLY, never in CI. Nothing here is imported by the live WhyWatt sim (src/).

What this differs from scripts/extract_acc_shapes.py:
  extract_acc_shapes.py pulls the ACC *monthly shape* (12x24, mean=1.0) and a single
  20-yr LEVELIZED value. This script instead pulls the per-year ANNUAL marginal-cost
  PATH mc(y), 2024..2054, decomposed into bill vs social components — the input the
  segmented-escalation model needs (methodology Energy_Rate_Projection_Spec.md §5.1).

═══════════════════════════════════════════════════════════════════════════════════
ELECTRIC ANNUAL mc(y) — "Detailed Output" sheet, per-year columns (CONFIRMED LAYOUT)
═══════════════════════════════════════════════════════════════════════════════════
To the right of "Total Levelized Value" the sheet repeats 14 year-blocks (headers
2023..2054). Block 0 (no suffix) is the TOTAL nominal $/MWh path; blocks .1...12 are
the components; block .13 duplicates the total's first component and is ignored.
Verified: Total(y) == sum(.1..12)(y) at every year (block .13 excluded).

Component block map (confirmed by matching each block's sign/magnitude/trajectory to
the labeled left-column levelized values AND to the standalone "Energy" sheet):

  .1  GHG Cap and Trade (Marginal Emissions)   BILL   (compliance carbon — consumer pays it)
  .2  GHG Adder (Marginal Emissions)           SOCIAL (damage carbon — externality)
  .3  GHG Portfolio Rebalancing                SOCIAL
  .4  Energy                                    BILL   (== "Energy" sheet annual, exact)
  .5  Generation Capacity                       BILL
  .6  Transmission                              BILL
  .7  Distribution                              BILL
  .8  Avoided AS Procurement                    BILL
  .9  Losses                                    BILL
  .10 Methane Leakage                           SOCIAL
  .11 Air Quality Adder (~0 in this vintage)    SOCIAL
  .12 (unused / zero)                           —

  bill_mc(y)   = .1 + .4 + .5 + .6 + .7 + .8 + .9      (the marginal cost on the bill)
  social_mc(y) = .2 + .3 + .10 + .11                  (feeds the social overlay, NOT the bill)

KEY RESULT this decomposition exposes: bill_mc is nearly FLAT (~$0.086 -> $0.122/kWh,
2024->2045) while the ACC Total triples — because the Total is dominated by rising SCC
damage carbon. Confirms the methodology: retail growth comes from the residual, not mc.

CLIMATE ZONE: the workbook cache is whatever was last saved from Excel (config rows on
"Detailed Output" record it). Distribution/capacity components are zone-specific, so the
FINAL CZ4 artifact requires opening the .xlsb in Excel, setting Climate Zone = CZ4 on the
Dashboard, saving (recalc), then re-running this script. Output is tagged with the CZ found.

Outputs (data/rates/projection/):
  acc_marginal_electric.json   annual mc(y) path + components, $/kWh, tagged with CZ + sha256
  gdp_deflator.json            CEC 2023 IEPR GDP deflator (nominal<->real bridge)

Usage:
  .venv/Scripts/python.exe scripts/build_rate_projection.py
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).parent.parent
DOWNLOADS = REPO_ROOT / "downloads"
OUT_DIR   = REPO_ROOT / "data" / "rates" / "projection"
SRC_DIR   = OUT_DIR / "sources"

ELEC_XLSB = DOWNLOADS / "2024-ACC-Electric-Model-v1b.xlsb"
GAS_XLSX  = DOWNLOADS / "2024-ACC-Gas-Model-v1b_October-Update.xlsx"

MWH_TO_KWH = 1.0 / 1000.0   # $/MWh -> $/kWh

# Confirmed block -> (name, bucket) map. Block suffix ".N" -> component.
COMPONENT_MAP = [
    (".1",  "ghg_cap_and_trade",   "bill"),
    (".2",  "ghg_adder_damage",    "social"),
    (".3",  "ghg_portfolio_rebal", "social"),
    (".4",  "energy",              "bill"),
    (".5",  "generation_capacity", "bill"),
    (".6",  "transmission",        "bill"),
    (".7",  "distribution",        "bill"),
    (".8",  "avoided_as",          "bill"),
    (".9",  "losses",              "bill"),
    (".10", "methane_leakage",     "social"),
    (".11", "air_quality_adder",   "social"),
    # .12 is zero/unused; .13 duplicates a block and is excluded.
]
YEARS = list(range(2024, 2055))   # forecast horizon present in the workbook


def _die(msg):
    print(f"\nERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _detect_cz(df_head: pd.DataFrame) -> str:
    """Find the CZ token (e.g. 'CZ12'/'CZ04') in the Detailed Output config rows."""
    vals = {str(v).strip() for v in df_head.values.flatten()}
    for v in vals:
        if v.startswith("CZ") and len(v) > 2 and v[2:].isdigit():
            return v
    return "UNKNOWN"


def extract_electric():
    if not ELEC_XLSB.exists():
        _die(f"Missing {ELEC_XLSB}")
    print(f"Reading {ELEC_XLSB.name} (Detailed Output, ~30-60s)...")

    cfg = pd.read_excel(ELEC_XLSB, sheet_name="Detailed Output", engine="pyxlsb",
                        header=None, nrows=6)
    cz = _detect_cz(cfg)
    print(f"  Climate zone in cache: {cz}")

    df = pd.read_excel(ELEC_XLSB, sheet_name="Detailed Output", engine="pyxlsb", header=5)
    df = df[pd.to_numeric(df["Date/Hour"], errors="coerce").notna()].copy()
    n = len(df)
    print(f"  Hourly rows: {n:,}")
    if n < 8700:
        _die(f"Expected ~8760 hourly rows, got {n}")

    def block_annual(suffix):
        """Mean $/MWh across all hours, per forecast year, for one year-block."""
        out = {}
        for y in YEARS:
            key = y if suffix == "" else f"{y}{suffix}"
            if key in df.columns:
                out[y] = float(pd.to_numeric(df[key], errors="coerce").mean())
        return out

    total = block_annual("")
    components = {name: block_annual(suf) for suf, name, _ in COMPONENT_MAP}

    # Validate: Total(y) == sum(components)(y)
    max_err = 0.0
    for y in YEARS:
        s = sum(components[name].get(y, 0.0) for name in components)
        max_err = max(max_err, abs(total.get(y, 0.0) - s))
    print(f"  Reconstruction check: max |Total - sum(components)| = {max_err:.4f} $/MWh")
    if max_err > 0.05:
        _die(f"Component blocks do not reconstruct the Total (max err {max_err}). "
             f"Block mapping may be wrong for this workbook vintage.")

    bill_names   = [name for _, name, b in COMPONENT_MAP if b == "bill"]
    social_names = [name for _, name, b in COMPONENT_MAP if b == "social"]

    def group_path(names):
        return {y: round(sum(components[nm].get(y, 0.0) for nm in names) * MWH_TO_KWH, 6)
                for y in YEARS}

    bill_mc   = group_path(bill_names)
    social_mc = group_path(social_names)
    total_kwh = {y: round(total[y] * MWH_TO_KWH, 6) for y in YEARS}

    # Normalize the zone number so "CZ4" and "CZ04" both count as the CZ4 target.
    try:
        cz_num = int("".join(ch for ch in cz if ch.isdigit()))
    except ValueError:
        cz_num = -1
    result = {
        "object": "acc_marginal_electric",
        "status": ("CZ4 (final)" if cz_num == 4 else
                   "PROVISIONAL — cache is %s; the plan default is CZ4. Re-run after "
                   "recalculating the workbook at CZ4 in Excel." % cz),
        "climate_zone": cz,
        "utility": "PG&E",
        "unit": "$/kWh at the meter (nominal)",
        "years": YEARS,
        "provenance": {
            "source_file": ELEC_XLSB.name,
            "sha256": _sha256(ELEC_XLSB),
            "sheet": "Detailed Output",
            "extraction": ("Per-year hourly blocks (headers 2024..2054) averaged over all "
                           "8760 hours. Block 0 = Total; blocks .1..12 = components; "
                           ".13 excluded (duplicate). Total == sum(components) verified."),
            "publisher": "CPUC Avoided Cost Calculator 2024 (built by E3)",
            "url": "https://www.ethree.com/public_proceedings/energy-efficiency-calculator/",
        },
        "bill_mc_kwh":   bill_mc,     # marginal cost that belongs on the utility bill
        "social_mc_kwh": social_mc,   # damage carbon etc. — feeds the social overlay, NOT the bill
        "total_acc_kwh": total_kwh,   # bill + social (the raw ACC Total; do NOT use as retail mc)
        "components_kwh": {
            name: {y: round(components[name].get(y, 0.0) * MWH_TO_KWH, 6) for y in YEARS}
            for name in components
        },
        "bucket_map": {name: b for _, name, b in COMPONENT_MAP},
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "acc_marginal_electric.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"  Written: {out}")
    print(f"  bill_mc:   2024=${bill_mc[2024]:.4f}  2030=${bill_mc[2030]:.4f}  2045=${bill_mc[2045]:.4f} /kWh")
    print(f"  social_mc: 2024=${social_mc[2024]:.4f}  2030=${social_mc[2030]:.4f}  2045=${social_mc[2045]:.4f} /kWh")
    print(f"  total_acc: 2024=${total_kwh[2024]:.4f}  2030=${total_kwh[2030]:.4f}  2045=${total_kwh[2045]:.4f} /kWh")


def extract_gas():
    """
    Gas annual bill marginal cost path, $/therm nominal — NOT climate-zone specific.
      bill_mc_gas(y) = commodity(y) + marginal_T&D(y)
        commodity: "Commodity" sheet, "CA Gas Price Forecast ($/MMBtu)", 12 monthly rows x year
                   columns 2023..2054; annual mean x 0.1 (MMBtu->therm).
        T&D:       "T&D" sheet, PG&E Residential marginal transport ($/therm), years 2022..2054.
    Plus the social-overlay inputs (applied later with an external SCC(y) path):
        co2 combustion factor (flat tCO2/therm) + methane leak adders/rates + GWP horizon.
    """
    if not GAS_XLSX.exists():
        _die(f"Missing {GAS_XLSX}")
    print(f"Reading {GAS_XLSX.name} (Commodity, T&D, Emissions, Methane)...")

    # ── Commodity: 12 monthly rows, year columns ──────────────────────────────
    com = pd.read_excel(GAS_XLSX, sheet_name="Commodity", engine="openpyxl", header=None)
    com_year_cols = {int(com.iloc[3, c]): c for c in range(com.shape[1])
                     if isinstance(com.iloc[3, c], (int, float)) and 2000 < com.iloc[3, c] < 2100}
    commodity_therm = {}   # $/therm nominal, annual mean
    for y in YEARS:
        if y in com_year_cols:
            c = com_year_cols[y]
            vals = pd.to_numeric(com.iloc[4:16, c], errors="coerce").dropna()  # 12 monthly rows
            commodity_therm[y] = float(vals.mean()) * 0.1   # $/MMBtu -> $/therm

    # ── T&D: PG&E Residential marginal transport, $/therm ─────────────────────
    td = pd.read_excel(GAS_XLSX, sheet_name="T&D", engine="openpyxl", header=None)
    td_year_cols = {int(td.iloc[3, c]): c for c in range(td.shape[1])
                    if isinstance(td.iloc[3, c], (int, float)) and 2000 < td.iloc[3, c] < 2100}
    pge_res_row = next(r for r in range(td.shape[0])
                       if str(td.iloc[r, 1]).strip() == "PG&E" or
                       (str(td.iloc[r, 1]).strip().startswith("PG&E") and "Res" in str(td.iloc[r, 2])))
    # The PG&E block: col1 == 'PG&E', col2 == 'Residential' on the same row.
    for r in range(td.shape[0]):
        if str(td.iloc[r, 1]).strip() == "PG&E" and str(td.iloc[r, 2]).strip() == "Residential":
            pge_res_row = r
            break
    td_therm = {y: float(pd.to_numeric(td.iloc[pge_res_row, c], errors="coerce"))
                for y, c in td_year_cols.items() if y in YEARS}

    bill_mc_gas = {y: round(commodity_therm[y] + td_therm[y], 6)
                   for y in YEARS if y in commodity_therm and y in td_therm}

    # ── Emissions: flat CO2 combustion factor (Residential Furnace, Uncontrolled) ──
    em = pd.read_excel(GAS_XLSX, sheet_name="Emissions", engine="openpyxl", header=None)
    co2_tonnes_therm = None
    for r in range(em.shape[0]):
        if (str(em.iloc[r, 1]).strip() == "Residential Furnace" and
                str(em.iloc[r, 2]).strip() == "Uncontrolled"):
            co2_tonnes_therm = float(pd.to_numeric(em.iloc[r, 6], errors="coerce"))
            break

    # ── Methane leakage params ────────────────────────────────────────────────
    me = pd.read_excel(GAS_XLSX, sheet_name="Methane Leakage", engine="openpyxl", header=None)
    def _methane(label):
        for r in range(me.shape[0]):
            if str(me.iloc[r, 1]).strip() == label:
                return float(pd.to_numeric(me.iloc[r, 2], errors="coerce"))
        return None
    gwp_horizon = None
    for r in range(me.shape[0]):
        if str(me.iloc[r, 1]).strip() == "Active GWP time horizon":
            gwp_horizon = str(me.iloc[r, 2]).strip()
            break

    result = {
        "object": "acc_marginal_gas",
        "status": "OK — gas is not climate-zone specific (system-wide commodity + utility T&D).",
        "utility": "PG&E",
        "class": "Residential",
        "unit": "$/therm (nominal)",
        "years": [y for y in YEARS if y in bill_mc_gas],
        "provenance": {
            "source_file": GAS_XLSX.name,
            "sha256": _sha256(GAS_XLSX),
            "sheets": ["Commodity", "T&D", "Emissions", "Methane Leakage"],
            "extraction": ("bill_mc_gas = commodity (Commodity sheet annual mean, $/MMBtu x 0.1) "
                           "+ PG&E Residential marginal T&D (T&D sheet, $/therm)."),
            "publisher": "CPUC Avoided Cost Calculator 2024 Gas Model (built by E3)",
            "url": "https://www.ethree.com/public_proceedings/energy-efficiency-calculator/",
        },
        "bill_mc_therm":  bill_mc_gas,                       # commodity + T&D (the bill marginal)
        "commodity_therm": {y: round(commodity_therm[y], 6) for y in bill_mc_gas},
        "td_therm":        {y: round(td_therm[y], 6) for y in bill_mc_gas},
        "social_params": {
            "note": "Combined with an external SCC(y) path in the model: "
                    "damage_carbon = SCC(y) * co2_tonnes_per_therm; methane per ACC adders.",
            "co2_tonnes_per_therm": co2_tonnes_therm,        # flat combustion factor
            "gwp_time_horizon": gwp_horizon,                 # GWP-20 vs GWP-100 (open decision)
            "upstream_methane_leak_adder": _methane("Upstream methane leakage adder"),
            "upstream_methane_leak_rate":  _methane("Upstream methane leakage rate"),
            "residential_btm_methane_adder": _methane("Residential behind-the-meter methane leakage adder"),
            "residential_btm_methane_rate":  _methane("Residential behind-the-meter methane leakage rate"),
        },
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "acc_marginal_gas.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"  Written: {out}")
    ys = result["years"]
    print(f"  bill_mc_gas: 2024=${bill_mc_gas[2024]:.4f}  2030=${bill_mc_gas[2030]:.4f}  "
          f"2045=${bill_mc_gas[2045]:.4f} /therm   (commodity+T&D)")
    print(f"  co2={co2_tonnes_therm} tCO2/therm  GWP={gwp_horizon}")


def extract_gdp_deflator():
    """CEC 2023 IEPR GDP deflator, embedded in the ACC gas workbook — the nominal<->real bridge."""
    if not GAS_XLSX.exists():
        _die(f"Missing {GAS_XLSX}")
    raw = pd.read_excel(GAS_XLSX, sheet_name="GDP Deflator", engine="openpyxl", header=None)
    base_year = int(pd.to_numeric(raw.iloc[3, 2]))   # header cell for the deflator base
    series = {}
    for r in range(4, raw.shape[0]):
        yr = pd.to_numeric(raw.iloc[r, 1], errors="coerce")
        val = pd.to_numeric(raw.iloc[r, 2], errors="coerce")
        if pd.notna(yr) and pd.notna(val):
            series[int(yr)] = round(float(val), 4)
    result = {
        "object": "gdp_deflator",
        "note": "CEC 2023 IEPR GDP deflator. Divide a nominal $ by (deflator[y]/deflator[base]) "
                "to express it in base-year real $.",
        "index_base_year": base_year,
        "provenance": {
            "source_file": GAS_XLSX.name,
            "sha256": _sha256(GAS_XLSX),
            "sheet": "GDP Deflator",
            "publisher": "CEC 2023 IEPR",
        },
        "deflator": series,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "gdp_deflator.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"  Written: {out}  ({len(series)} years, base {base_year})")


if __name__ == "__main__":
    print("=" * 68)
    print("Offline rate-projection harvest — 2024 CPUC ACC (built by E3)")
    print("=" * 68)
    extract_electric()
    print()
    extract_gas()
    print()
    extract_gdp_deflator()
    print("\nDone. Review data/rates/projection/*.json")
    print("NOTE: if the electric 'status' says PROVISIONAL, recalc the .xlsb at CZ4 and re-run "
          "(see script header).")
