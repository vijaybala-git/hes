#!/usr/bin/env python3
"""build_nbt_export.py — NEM 3.0 (Net Billing Tariff) export credit values, hourly, per year.

Phase 7 §4.1 issue 12. PG&E Schedule NBT: "exported electricity will be multiplied by the
hourly avoided costs values calculated by the Avoided Cost Calculator (Export Compensation
Rates)", and "The Export Compensation Rates for a given installation vintage of customers in
a given calendar year are based on the applicable vintage of ACC forecast of values for that
year." The rates include ALL ACC components — generation (Energy, Generation Capacity, Cap and
Trade, Ancillary Services, Losses) and delivery (Distribution, Transmission, GHG Adder, GHG
Rebalancing, Methane Leakage). The customer keeps its install vintage for 9 years.

WhyWatt has one ACC vintage (2024), so the export credit in calendar year y is the 2024 ACC's
forecast for y — the same during and after the 9-year legacy period. (A later ACC vintage is a
data drop: add it here, and pick the vintage by install year.)

Source: 2024-ACC-Electric-Model-v1b.xlsb, sheet "Detailed Output" (cached for CZ4 — the same
cache as data/rates/projection/acc_marginal_electric.json), the per-year TOTAL hourly block
(headers 2024..2054, $/MWh at the meter). Each year's 8,760 hours are averaged by (month, hour)
into a 12 × 24 representative day, then shifted from standard time to clock time (+1 h in
Mar–Oct) to match the energy balance.

Hour convention: the workbook's first row is 00:00 on Jan 1 of its weather year (2018) — rows
are hour-BEGINNING, so row "hh:00" is hour hh (checked at build time).

Output: data/rates/nbt_export_acc.json  (12 × 24 $/kWh per year, clock time)

Usage:
    .venv/Scripts/python.exe scripts/build_nbt_export.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
from solar_loader import to_clock_time  # noqa: E402

XLSB = ROOT / "downloads" / "2024-ACC-Electric-Model-v1b.xlsb"
OUT = ROOT / "data" / "rates" / "nbt_export_acc.json"
YEARS = list(range(2024, 2055))
EXPECTED_CZ = "CZ4"
SCHEMA_VERSION = 1


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _detect_cz(head: pd.DataFrame) -> str:
    for v in {str(x).strip() for x in head.values.flatten()}:
        if v.startswith("CZ") and v[2:].isdigit():
            return f"CZ{int(v[2:])}"
    return "UNKNOWN"


def _month_hour(serial: float) -> tuple[int, int]:
    """Hour-beginning Excel serial → (month 1-12, hour 0-23)."""
    day = int(np.floor(serial + 1e-9))
    hour = int(round((serial - day) * 24)) % 24
    return (date(1899, 12, 30) + timedelta(days=day)).month, hour


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not XLSB.exists():
        raise SystemExit(f"Missing {XLSB} (download from the CPUC ACC page; see script docstring)")
    print(f"Reading {XLSB.name} (Detailed Output, ~1 min)…")
    head = pd.read_excel(XLSB, sheet_name="Detailed Output", engine="pyxlsb", header=None,
                         nrows=6)
    cz = _detect_cz(head)
    if cz != EXPECTED_CZ:
        raise SystemExit(f"Workbook cache is {cz}, expected {EXPECTED_CZ} — set the Climate "
                         "Zone on the Dashboard, save, and re-run")
    df = pd.read_excel(XLSB, sheet_name="Detailed Output", engine="pyxlsb", header=5)
    df = df[pd.to_numeric(df["Date/Hour"], errors="coerce").notna()].copy()
    if len(df) < 8700:
        raise SystemExit(f"Expected ~8760 hourly rows, got {len(df)}")
    serial = pd.to_numeric(df["Date/Hour"])
    first = float(serial.iloc[0])
    if abs(first - int(first)) > 1e-6:
        raise SystemExit(f"First row {first} is not 00:00 — hour convention changed")
    mh = [_month_hour(float(s)) for s in serial]
    df["_m"] = [m for m, _ in mh]
    df["_h"] = [h for _, h in mh]

    by_year, annual = {}, {}
    for y in YEARS:
        if y not in df.columns:
            raise SystemExit(f"No per-year total column {y}")
        v = pd.to_numeric(df[y], errors="coerce") / 1000.0          # $/MWh → $/kWh
        grid = (v.groupby([df["_m"], df["_h"]]).mean().unstack().reindex(
            index=range(1, 13), columns=range(24)).to_numpy())
        if np.isnan(grid).any():
            raise SystemExit(f"{y}: missing month-hour cells")
        by_year[str(y)] = np.round(to_clock_time(grid), 5).tolist()
        annual[str(y)] = round(float(v.mean()), 6)

    doc = {
        "_meta": {
            "schema_version": SCHEMA_VERSION,
            "built": str(date.today()),
            "built_by": "scripts/build_nbt_export.py",
            "role": "NEM 3.0 (NBT) export credit $/kWh by calendar year × month × clock hour "
                    "(Phase 7 §4.1 issue 12)",
            "acc_vintage": 2024,
            "climate_zone": cz,
            "utility": "PG&E",
            "components": "ACC total — all components (PG&E Schedule NBT: generation = Energy, "
                          "Generation Capacity, Cap and Trade, Ancillary Services, Losses; "
                          "delivery = Distribution, Transmission, GHG Adder, GHG Rebalancing, "
                          "Methane Leakage)",
            "time_basis": "clock time (workbook standard time, +1 h in Mar–Oct)",
            "hour_convention": "hour-beginning 0–23 (workbook first row = Jan 1 00:00)",
            "not_included": "ACC Plus adder (first-5-year NBT customers); CCA customers receive "
                            "the generation part from their CCA, not PG&E",
            "source_file": XLSB.name,
            "source_sha256": _sha256(XLSB),
            "source_url": "https://www.ethree.com/public_proceedings/energy-efficiency-calculator/",
            "unit": "$/kWh at the meter (nominal)",
        },
        "annual_mean_kwh": annual,
        "by_year": by_year,
    }
    OUT.write_text(json.dumps(doc, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"  {cz}; annual mean $/kWh: 2024 {annual['2024']:.4f} · 2025 {annual['2025']:.4f} · "
          f"2035 {annual['2035']:.4f} · 2050 {annual['2050']:.4f}")
    print(f"Wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
