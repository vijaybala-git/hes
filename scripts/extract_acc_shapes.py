"""
scripts/extract_acc_shapes.py
─────────────────────────────
One-time extraction of ACC shape arrays from the 2024 CPUC ACC Excel workbooks.

═══════════════════════════════════════════════════════════════════════════
METHODOLOGY — How spreadsheet values become simulation $/kWh and $/therm
═══════════════════════════════════════════════════════════════════════════

SOURCE DATA
───────────
The 2024 CPUC Avoided Cost Calculator (ACC), published by Energy + Environmental
Economics (E3) on behalf of the California Public Utilities Commission.
Download: https://www.ethree.com/public_proceedings/energy-efficiency-calculator/

The ACC represents the long-run marginal cost of supplying (or avoiding) one
additional unit of electricity or gas to the grid at a specific hour and month.
It is used in California to value demand-side resources (efficiency, electrification,
demand response) in cost-effectiveness tests.

ELECTRIC MODEL  (2024-ACC-Electric-Model-v1b.xlsb)
────────────────────────────────────────────────────
Sheet:    "Detailed Output"
Column:   "Total Levelized Value" ($/MWh at the meter)
Rows:     8,760 hourly rows — one per hour of a representative year
Config:   IOU = PG&E, Climate Zone = CZ12 (Sacramento Valley proxy for Bay Area),
          Start Year = 2024, Number of Years = 20
Data year: 2018 (the base meteorological year used by the workbook)

The "Total Levelized Value" column sums all ACC components:
  Generation Capacity + Transmission Capacity + Distribution Capacity
  + Energy (wholesale) + Avoided AS Procurement + Losses
  + GHG Adder (Marginal Emissions) + GHG Cap and Trade
  + GHG Portfolio Rebalancing + Methane Leakage + Air Quality Adder
The result is in $/MWh at the meter — i.e., already adjusted for T&D losses,
so it represents the full societal avoided cost for one kWh of end-use load.

EXTRACTION STEPS — ELECTRIC
  1. Read all 8,760 rows; decode the Excel date serial to (month, hour).
     Excel serial = days since 1899-12-30; fractional part × 24 = hour-of-day.
  2. For each (month 1-12, hour 0-23) cell, average all days in that month.
     Result: 12×24 matrix of average $/MWh values.
  3. Convert $/MWh → $/kWh by dividing by 1,000.  (Not done here — shape only.)
  4. Normalise each month's row to mean = 1.0:
       shape[m, h] = raw_avg[m, h] / mean(raw_avg[m, :])
     This produces a dimensionless multiplier. A device running at hour h in month m
     faces an effective rate of:
       effective_rate[m] = retail_cagr_rate[m] × dot(device_load_profile_24h, shape[m, :])
     For a flat (uniform) device profile the dot product equals 1.0, so the effective
     rate equals the base CAGR rate — the ACC shape is revenue-neutral for flat loads.

WHY NORMALISE?
  The ACC $/MWh absolute values encode a specific policy scenario and discount rate
  chosen by E3/CPUC. By normalising to a shape (relative multiplier), we decouple
  the time-of-use pattern from the rate level. The rate level comes from the user's
  chosen CAGR escalation or a future absolute ACC trajectory (Phase 3). This keeps
  the simulation auditable: the shape captures "when is it expensive?" while the
  CAGR captures "how fast are rates rising overall?"

KNOWN ANOMALIES
  April/May overnight hours (0–4am) show elevated shape values (~1.6–2.1×) that
  exceed winter overnight values, which is physically implausible for Bay Area.
  This is a 2018 base-year artifact — that year had an unusually cold spring in
  California. The values are preserved as-is (official CPUC model output).
  Multi-year averaging in Phase 3 will smooth this anomaly.

GAS MODEL  (2024-ACC-Gas-Model-v1b_October-Update.xlsx)
────────────────────────────────────────────────────────
Sheet:    "Output" (dashboard layout — sparse, not a data table)
Location: Rows 16–27 (January–December), column B = levelized monthly $/therm
Config:   Utility = PG&E, Class = Residential, End Use = Small Boiler
          Start Year = 2024, Levelization Period = 1 year
Column C: Annual average $/therm (same value repeated — used as cross-check)

The gas ACC values represent the avoided cost of one therm of natural gas not
consumed, including commodity, T&D, and GHG components.
Units: $/therm (already at the meter).

EXTRACTION STEPS — GAS
  1. Read 12 monthly $/therm values directly from rows 16–27, column B.
     Verified: mean of 12 values matches the annual average in column C.
  2. Normalise to annual mean = 1.0:
       shape[m] = monthly_value[m] / mean(monthly_values)
     Annual mean = $1.7634/therm for PG&E residential 2024.
  3. In simulation: effective_gas_rate[m] = retail_cagr_rate[m] × shape[m]
     Winter months (Jan/Dec) shape ≈ 1.20 (20% premium)
     Summer months (Jun–Aug) shape ≈ 0.87 (13% discount)
     Pattern: mirrors NYMEX gas seasonal forward curve.

OUTPUTS
  acc_electric_shape_pge_2024.json
    shape_24h_by_month: 12 × 24 array, each row mean = 1.0
    Used by ACCRateLoader to compute per-device effective monthly rates.

  acc_gas_shape_pge_2024.json
    monthly_shape: 12 values, mean = 1.0
    Applied uniformly to all gas devices regardless of end-use type.

SIMULATION USAGE (src/rate_loader.py — ACCRateLoader)
  Electric effective rate for device category C in month m:
    rate[m] = retail_cagr_rate[m] × Σ_h ( load_profile_C[h] × shape[m,h] )
  Gas effective rate in month m:
    rate[m] = retail_cagr_rate[m] × gas_shape[m]
  Where retail_cagr_rate comes from RateLoader (PG&E E-1 / G-1 historical +
  CAGR projection). Device load profiles are in data/rates/device_load_shapes.json.

═══════════════════════════════════════════════════════════════════════════

PRE-CONDITION — Electric model must be recalculated for PG&E / CZ12:
  1. Open downloads/2024-ACC-Electric-Model-v1b.xlsb in Excel
  2. On the "Dashboard Viewer" sheet, set:
       IOU        → PG&E
       Climate Zone → CZ12
       Start Year → 2024  (leave as-is)
  3. Save the file (Ctrl+S) — Excel recalculates "Detailed Output"
  4. Close Excel, then run this script

Downloads needed (place in downloads/ at repo root):
  2024-ACC-Electric-Model-v1b.xlsb   (84 MB)
  2024-ACC-Gas-Model-v1b_October-Update.xlsx

Source: https://www.ethree.com/public_proceedings/energy-efficiency-calculator/

Outputs (written to data/rates/):
  acc_electric_shape_pge_2024.json   12×24 hourly shape, each row normalised to mean=1.0
  acc_gas_shape_pge_2024.json        12 monthly shape factors, normalised to annual mean=1.0

Usage:
  cd <repo root>
  pip install pandas openpyxl pyxlsb
  python scripts/extract_acc_shapes.py
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent
DOWNLOADS = REPO_ROOT / "downloads"
OUT_DIR   = REPO_ROOT / "data" / "rates"

OUT_ELEC  = OUT_DIR / "acc_electric_shape_pge_2024.json"
OUT_GAS   = OUT_DIR / "acc_gas_shape_pge_2024.json"

# ── Electric model — sheet structure (confirmed from workbook inspection) ─────
#
#  "Detailed Output" sheet layout:
#    Row 1:  config — Start Year, IOU (e.g. "PG&E")
#    Row 2:  config — Number of Years, CZ (e.g. "CZ12")
#    Row 4:  section titles (merged cells)
#    Row 5:  column headers — "Date/Hour", component names, "Total Levelized Value", ...
#    Row 6:  units row ("$/MWh") + annual averages — SKIP
#    Row 7:  blank — SKIP
#    Rows 8+: 8,760 hourly data rows
#
#  "Date/Hour" = Excel date serial with fractional hour (e.g. 45292.0417 = Jan 1 2025 01:00)
#  "Total Levelized Value" = sum of all components in $/MWh
#
ELEC_SHEET       = "Detailed Output"
ELEC_HEADER_ROW  = 5    # 0-based pandas header= argument
ELEC_SKIP_ROWS   = [6, 7]   # units row + blank row after header
ELEC_DATE_COL    = "Date/Hour"
ELEC_VALUE_COL   = "Total Levelized Value"

# Expected IOU/CZ in config rows (for validation only — extraction uses cached data)
EXPECTED_IOU = "PG&E"
EXPECTED_CZ  = "CZ12"

# ── Gas model constants ───────────────────────────────────────────────────────

GAS_SHEET         = "Monthly Values"
GAS_IOU_COL       = "IOU"
GAS_IOU_VALUE     = "PG&E"
GAS_SECTOR_COL    = "Customer Class"
GAS_SECTOR_VALUE  = "Residential Core"
GAS_YEAR_COL      = "Year"
GAS_YEAR_VALUE    = 2025
GAS_MONTH_COL     = "Month"
GAS_VALUE_COL     = "Total Levelized Value"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _die(msg: str):
    print(f"\nERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _find_file(downloads: Path, label: str, extensions: list) -> Path:
    candidates = []
    for ext in extensions:
        candidates.extend(downloads.glob(f"*{ext}"))
    if not candidates:
        _die(
            f"{label} not found in {downloads}/\n"
            f"  Expected a file with extension: {extensions}\n"
            f"  Download from https://www.ethree.com/public_proceedings/energy-efficiency-calculator/"
        )
    if len(candidates) > 1:
        print(f"  WARNING: multiple {label} candidates: {[c.name for c in candidates]}")
        print(f"  Using: {candidates[0].name}")
    return candidates[0]


def _excel_serial_to_month_hour(serial):
    """Convert Excel date serial (with fractional hour) to (month 1-12, hour 0-23)."""
    day_int  = int(serial)
    fraction = serial - day_int
    dt       = date(1899, 12, 30) + timedelta(days=day_int)
    hour     = round(fraction * 24)
    if hour == 24:          # midnight rounding
        hour = 0
    return dt.month, hour


# ── Electric extraction ───────────────────────────────────────────────────────

def extract_electric():
    path = _find_file(DOWNLOADS, "Electric ACC model", [".xlsb"])
    print(f"\nElectric model: {path.name}")

    # Validate config rows (IOU / CZ) before reading full data
    try:
        cfg = pd.read_excel(path, sheet_name=ELEC_SHEET, engine="pyxlsb",
                            header=None, nrows=6)
    except Exception as e:
        _die(f"Could not open {path.name}: {e}")

    # Flatten all config rows into one set for flexible searching
    all_cfg_vals = {str(v).strip() for v in cfg.values.flatten() if str(v) not in ("nan", "")}
    print(f"  Config values found (rows 1-6): {all_cfg_vals}")

    # Fuzzy IOU check
    iou_ok = any("PG" in v.upper() or "PACIFIC" in v.upper() for v in all_cfg_vals)
    if not iou_ok:
        _die(
            f"File does not appear to be configured for PG&E.\n"
            f"  Values found: {all_cfg_vals}\n"
            f"  Open the .xlsb in Excel → Dashboard Viewer → set IOU to 'PG&E' → Save."
        )

    # Fuzzy CZ check — accept CZ04 or CZ12; skip bare "CZ" which is just a column header
    found_cz = next((v for v in all_cfg_vals
                     if v.startswith("CZ") and len(v) > 2 and v[2:].isdigit()), None)
    if found_cz not in ("CZ12", "CZ04"):
        _die(
            f"File is not configured for CZ12 or CZ04 (found: {found_cz!r}).\n"
            f"  Open the .xlsb in Excel → Dashboard Viewer → set Climate Zone to 'CZ12' → Save."
        )

    found_iou = next((v for v in all_cfg_vals if "PG" in v.upper() or "PACIFIC" in v.upper()), "?")
    print(f"  Config check passed: IOU={found_iou!r}, CZ={found_cz!r} ✓")
    print(f"  Reading 8,760 hourly rows (this may take 30–60 s) ...")

    df = pd.read_excel(
        path,
        sheet_name=ELEC_SHEET,
        engine="pyxlsb",
        header=ELEC_HEADER_ROW,
        skiprows=ELEC_SKIP_ROWS,
    )

    print(f"  Loaded {len(df):,} rows.")

    if ELEC_DATE_COL not in df.columns:
        _die(
            f"Column '{ELEC_DATE_COL}' not found.\n"
            f"  Available: {list(df.columns[:20])}"
        )
    if ELEC_VALUE_COL not in df.columns:
        _die(
            f"Column '{ELEC_VALUE_COL}' not found.\n"
            f"  Available: {list(df.columns[:20])}"
        )

    # Drop rows where Date/Hour is not a number (units row or blank rows that snuck in)
    df = df[pd.to_numeric(df[ELEC_DATE_COL], errors="coerce").notna()].copy()
    df[ELEC_DATE_COL] = pd.to_numeric(df[ELEC_DATE_COL])
    df[ELEC_VALUE_COL] = pd.to_numeric(df[ELEC_VALUE_COL], errors="coerce")
    df = df.dropna(subset=[ELEC_VALUE_COL])
    print(f"  After cleaning: {len(df):,} numeric rows.")

    if len(df) < 8700:
        _die(f"Expected ~8,760 hourly rows, got {len(df)}. Check configuration.")

    # Decode month and hour from Excel date serial
    decoded = df[ELEC_DATE_COL].apply(_excel_serial_to_month_hour)
    df["_month"] = decoded.apply(lambda x: x[0])
    df["_hour"]  = decoded.apply(lambda x: x[1])

    # Spot-check date range
    first_date = date(1899, 12, 30) + timedelta(days=int(df[ELEC_DATE_COL].iloc[0]))
    last_date  = date(1899, 12, 30) + timedelta(days=int(df[ELEC_DATE_COL].iloc[-1]))
    print(f"  Date range: {first_date} → {last_date}  (year = {first_date.year})")

    # Build 12×24 array: mean of all days in each (month, hour) cell
    shape = np.zeros((12, 24), dtype=float)
    for mo in range(1, 13):
        for hr in range(24):
            mask = (df["_month"] == mo) & (df["_hour"] == hr)
            vals = df.loc[mask, ELEC_VALUE_COL]
            if len(vals) == 0:
                print(f"  WARNING: no data for month={mo} hour={hr}")
            else:
                shape[mo - 1, hr] = vals.mean()

    # Normalise each month's row to mean = 1.0
    for mo in range(12):
        row_mean = shape[mo].mean()
        if row_mean > 0:
            shape[mo] /= row_mean
        else:
            print(f"  WARNING: month {mo+1} mean is zero")

    result = {
        "source": f"2024 CPUC ACC Electric Model v1b, PG&E residential, CZ12, normalised to monthly mean",
        "note":   f"Extracted by scripts/extract_acc_shapes.py from {path.name}",
        "data_year": first_date.year,
        "shape_24h_by_month": [list(np.round(row, 4)) for row in shape],
    }
    OUT_ELEC.write_text(json.dumps(result, indent=2))
    print(f"\n  Written: {OUT_ELEC}")

    # Validate monthly means
    ok = all(abs(np.mean(result["shape_24h_by_month"][m]) - 1.0) < 0.01 for m in range(12))
    print(f"  Validation: all monthly means ≈ 1.0 — {'✓ PASSED' if ok else '✗ FAILED'}")

    # Duck-curve spot check: July
    july = np.array(result["shape_24h_by_month"][6])
    print(f"\n  Duck-curve check (July):")
    print(f"    Overnight hr 1-5:   {july[1:6].mean():.3f}  (expect < 1.0)")
    print(f"    Midday    hr 11-14: {july[11:15].mean():.3f}  (expect < 1.0 in summer)")
    print(f"    Evening   hr 18-21: {july[18:22].mean():.3f}  (expect > 1.2)")


# ── Gas extraction ────────────────────────────────────────────────────────────

def extract_gas():
    path = _find_file(DOWNLOADS, "Gas ACC model", [".xlsx", ".xls"])
    print(f"\nGas model: {path.name}")

    xl = pd.ExcelFile(path, engine="openpyxl")
    print(f"  Sheets: {xl.sheet_names}")

    if GAS_SHEET not in xl.sheet_names:
        # Try to find a sheet with monthly data
        monthly_sheets = [s for s in xl.sheet_names if "month" in s.lower() or "output" in s.lower()]
        if monthly_sheets:
            print(f"  Sheet '{GAS_SHEET}' not found. Trying '{monthly_sheets[0]}'")
            sheet = monthly_sheets[0]
        else:
            print(f"  Available sheets: {xl.sheet_names}")
            _die(
                f"Sheet '{GAS_SHEET}' not found.\n"
                f"  Update GAS_SHEET constant at top of script."
            )
    else:
        sheet = GAS_SHEET

    # Read entire sheet without headers
    raw = pd.read_excel(path, sheet_name=sheet, engine="openpyxl", header=None)
    print(f"  Sheet size: {raw.shape[0]} rows × {raw.shape[1]} cols")

    # Layout (confirmed by inspection):
    #   col 1 = month name (January … December)
    #   col 2 = levelized monthly $/therm value
    #   col 3 = annual average (same for all rows — used as normalisation check)
    # Find the row where "January" first appears
    month_names = ["January","February","March","April","May","June",
                   "July","August","September","October","November","December"]
    jan_row = None
    for r in range(raw.shape[0]):
        if str(raw.iloc[r, 1]).strip() == "January":
            jan_row = r
            break
    if jan_row is None:
        _die("Could not find 'January' in column 1 of gas Output sheet.")

    print(f"  Found monthly data starting at row {jan_row}")

    # Extract 12 monthly values from col 2
    monthly_vals = []
    for i, mo in enumerate(month_names):
        r = jan_row + i
        label = str(raw.iloc[r, 1]).strip()
        val   = raw.iloc[r, 2]
        if label != mo:
            _die(f"Expected '{mo}' at row {r} col 1, got '{label}'")
        monthly_vals.append(float(val))
        print(f"    {mo:>10s}: {val:.4f} $/therm")

    # Cross-check: annual average should equal mean of monthly values
    annual_avg_cell = float(raw.iloc[jan_row, 3])
    computed_mean   = np.mean(monthly_vals)
    print(f"  Annual average (cell): {annual_avg_cell:.4f}   computed: {computed_mean:.4f}")
    if abs(annual_avg_cell - computed_mean) > 0.01:
        print(f"  WARNING: annual average mismatch — check sheet layout")

    monthly = np.array(monthly_vals)

    annual_mean = monthly.mean()
    shape = monthly / annual_mean

    result = {
        "source": "2024 CPUC ACC Gas Model v1b, PG&E residential core, normalised to annual mean = 1.0",
        "note":   f"Extracted by scripts/extract_acc_shapes.py from {path.name}",
        "monthly_shape": list(np.round(shape, 4)),
    }
    OUT_GAS.write_text(json.dumps(result, indent=2))
    print(f"\n  Written: {OUT_GAS}")
    print(f"  Shape: {[round(v,3) for v in shape]}")
    print(f"  Annual mean: {shape.mean():.4f}  (should be 1.0)")
    print(f"  Expect Jan/Dec > 1.0, Jun-Aug < 1.0")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("ACC Shape Extraction — 2024 CPUC ACC Models")
    print("=" * 60)

    extract_electric()
    extract_gas()

    print("\n" + "=" * 60)
    print("Done. Commit the JSON files in data/rates/")
    print("Do NOT commit the Excel source files (downloads/ is gitignored).")
    print("=" * 60)
