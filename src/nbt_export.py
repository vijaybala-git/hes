"""NEM 3.0 (Net Billing Tariff) export credit — hourly ACC values by calendar year.

Phase 7 §4.1 issue 12. Exports are credited at the Avoided Cost Calculator's hourly values for
the calendar year, from the ACC vintage in effect at install (kept for 9 years). WhyWatt has one
vintage (ACC 2024), so the credit in calendar year y is ACC 2024's forecast for y, all
components included (PG&E Schedule NBT). It does NOT follow the retail projection method or
any retail CAGR — export value is a grid value, not a retail price.

Built offline by scripts/build_nbt_export.py → data/rates/nbt_export_acc.json (clock time).
Years outside the ACC horizon (2024–2054) hold the nearest endpoint.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

import numpy as np

_FILE = Path(__file__).parent.parent / "data" / "rates" / "nbt_export_acc.json"


@functools.lru_cache(maxsize=1)
def _table() -> tuple[dict[int, np.ndarray], int, int]:
    doc = json.loads(_FILE.read_text(encoding="utf-8"))
    by_year = {int(y): np.asarray(v, dtype=float) for y, v in doc["by_year"].items()}
    for y, a in by_year.items():
        if a.shape != (12, 24):
            raise ValueError(f"{_FILE.name}: year {y} is {a.shape}, expected (12, 24)")
    return by_year, min(by_year), max(by_year)


def nbt_export_rates(sim_start_year: int, n_years: int) -> np.ndarray:
    """(n_years, 12, 24) export credit $/kWh — month × clock hour for each simulated year."""
    by_year, lo, hi = _table()
    return np.stack([by_year[min(max(sim_start_year + i, lo), hi)] for i in range(n_years)])
