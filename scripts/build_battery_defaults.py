#!/usr/bin/env python3
"""build_battery_defaults.py — home-battery defaults from the manufacturer datasheet.

Phase 7 §2 (decided 2026-09-23): the default battery is a **Tesla Powerwall 3**, the most
common home battery in the Bay Area today. This script reads the official datasheet PDF and
writes the four numbers the energy balance uses, with provenance. The PDF itself is not
committed (scripts/downloads/ is gitignored); its URL and sha256 are.

    usable_kwh      "Nominal Battery Energy 13.5 kWh AC"
    round_trip_eff  "Solar to Battery to Home/Grid Efficiency 89%"   (25 °C, beginning of life)
    discharge_kw    "Nominal Output Power (AC) … 11.5 kW"            (highest on-grid rating)
    charge_kw       "Maximum Continuous Charge Current / Power … / 5 kW" (Powerwall 3 only —
                    the only published charge rating; 8 kW with expansion units)

Output: data/appliances/battery_defaults.json

Usage:
    .venv/Scripts/python.exe scripts/build_battery_defaults.py           # cached PDF
    .venv/Scripts/python.exe scripts/build_battery_defaults.py --fetch   # download first
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
PDF = ROOT / "scripts" / "downloads" / "Powerwall-3-Datasheet.pdf"
URL = ("https://energylibrary.tesla.com/docs/Public/EnergyStorage/Powerwall/3/Datasheet/"
       "en-us/Powerwall-3-Datasheet.pdf")
OUT = ROOT / "data" / "appliances" / "battery_defaults.json"
SCHEMA_VERSION = 1


def _num(pattern: str, text: str, what: str) -> float:
    m = re.search(pattern, text)
    if not m:
        raise SystemExit(f"Datasheet: could not find {what} (pattern {pattern!r})")
    return float(m.group(1))


def extract(text: str) -> dict:
    kwh = _num(r"Nominal Battery Energy\s+([\d.]+)\s*kWh", text, "battery energy")
    eff = _num(r"Solar to Battery to Home/Grid Efficiency\s+([\d.]+)\s*%", text, "efficiency")
    outs = re.search(r"Nominal Output Power \(AC\)((?:\s+[\d.]+\s*kW)+)", text)
    if not outs:
        raise SystemExit("Datasheet: could not find nominal output power")
    discharge = max(float(x) for x in re.findall(r"([\d.]+)\s*kW", outs.group(1)))
    charge = _num(r"Maximum Continuous Charge Current / Power\s+[\d.]+\s*A AC\s*/\s*([\d.]+)\s*kW"
                  r"\s*\n?\s*\(Powerwall 3 only\)", text, "charge power (Powerwall 3 only)")
    edition = re.search(r"\b(20\d\d)\b", text)
    return {"usable_kwh": kwh, "round_trip_eff": round(eff / 100.0, 4),
            "charge_kw": charge, "discharge_kw": discharge,
            "edition": int(edition.group(1)) if edition else None}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fetch", action="store_true", help="download the datasheet first")
    args = ap.parse_args()
    if args.fetch:
        req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
        PDF.parent.mkdir(parents=True, exist_ok=True)
        PDF.write_bytes(urllib.request.urlopen(req, timeout=120).read())
    if not PDF.exists():
        raise SystemExit(f"Missing {PDF} — run with --fetch")
    import pdfplumber
    with pdfplumber.open(PDF) as pdf:
        text = "\n".join((pg.extract_text() or "") for pg in pdf.pages)
    v = extract(text)
    doc = {
        "_meta": {
            "schema_version": SCHEMA_VERSION,
            "built": str(date.today()),
            "built_by": "scripts/build_battery_defaults.py",
            "role": "default home battery for the Phase 7 energy balance (§2)",
            "source_url": URL,
            "source_sha256": hashlib.sha256(PDF.read_bytes()).hexdigest(),
            "datasheet_edition": v["edition"],
            "notes": {
                "round_trip_eff": "Solar → battery → home/grid, 25 °C, beginning of life, "
                                  "3.3 kW; applied as √η on charge and on discharge",
                "discharge_kw": "highest nominal on-grid output rating (5.8 / 7.6 / 10 / 11.5)",
                "charge_kw": "Maximum continuous charge, Powerwall 3 only (8 kW with "
                             "expansion units) — the datasheet's only charge rating",
                "not_modelled": "Solar → home/grid inverter efficiency 97.5% (PVWatts system "
                                "losses already cover the inverter); degradation",
            },
        },
        "default_model": "tesla_powerwall_3",
        "models": {
            "tesla_powerwall_3": {
                "label": "Tesla Powerwall 3",
                "usable_kwh": v["usable_kwh"],
                "round_trip_eff": v["round_trip_eff"],
                "charge_kw": v["charge_kw"],
                "discharge_kw": v["discharge_kw"],
            },
        },
    }
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    m = doc["models"]["tesla_powerwall_3"]
    print(f"  Powerwall 3: {m['usable_kwh']} kWh · {m['round_trip_eff']:.0%} · charge "
          f"{m['charge_kw']} kW · discharge {m['discharge_kw']} kW (edition {v['edition']})")
    print(f"Wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
