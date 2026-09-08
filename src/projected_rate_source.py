"""
ProjectedRateSource — Phase 6 WS1 rate hand-off interface.

Reads the offline rate-projection bundle (data/rates/projection/whywatt_rate_projection.json)
as PLAIN DATA and exposes the same read interface RateLoader.get_rate() uses today. Each
selectable rate model is one standalone annual $/unit series from the bundle:

    whywatt_conservative / whywatt_moderate / whywatt_stress  (markets.<m>.scenarios[*].retail)
    eia_national         (US EIA national avg)   markets.<m>.benchmarks.eia_national
    eia_pacific          (EIA AEO Pacific)       markets.<m>.benchmarks.eia_pacific
    cec_iepr             (CEC 2025 IEPR, PG&E)   markets.<m>.benchmarks.cec_electric   [ELEC only]
    cec_bau              (CEC 2025 BAU invest)   markets.<m>.benchmarks.cec_gas_extreme [GAS only]
    e3_gas               (E3 2020 high case)     markets.<m>.benchmarks.e3_gas          [GAS only]

Design decisions (docs/Phase6_Spec.md WS1, refined 2026-09-07):
  • Each series STANDS ON ITS OWN — the bundle carries annual retail levels and is used
    verbatim. This adapter adds nothing: it ignores `scenario` and `custom_cagr` (the
    rate-model enum already picks the curve). Compare ACC mode, which also ignores custom_cagr.
  • The monthly (seasonal) shape is layered ON TOP in the core by wrapping this adapter in
    ACCRateLoader (see model._make_loader). This adapter itself returns flat months — its
    get_annual_monthly_rates is only used when the ACC overlay is disabled for testing.
  • Reads the bundle as data ONLY. It MUST NOT import src/rate_projection/ (Phase 6 Invariant 5).
  • Out-of-horizon years hold the nearest endpoint flat (base 2025 / final 2050).

Fuel naming matches the rest of the sim: "electricity" | "gas".
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

import numpy as np

_BUNDLE_PATH = (Path(__file__).parent.parent / "data" / "rates" / "projection"
                / "whywatt_rate_projection.json")

# Bundle fuel keys differ from the sim's fuel names.
_FUEL_KEY = {"electricity": "elec", "gas": "gas"}

# model_key -> where its series lives in the bundle market, per fuel.
#   ("scenario", <scenario_key>)   -> market["scenarios"][key]["retail"][fuel_key]
#   ("benchmark", <benchmark_key>) -> market["benchmarks"][key][fuel_key]
# A fuel absent from a model's map is unsupported for that fuel (e.g. cec_iepr has no gas).
_MODEL_SOURCES: dict[str, dict[str, tuple[str, str]]] = {
    "whywatt_conservative": {"electricity": ("scenario", "conservative"),
                             "gas":         ("scenario", "conservative")},
    "whywatt_moderate":     {"electricity": ("scenario", "moderate"),
                             "gas":         ("scenario", "moderate")},
    "whywatt_stress":       {"electricity": ("scenario", "stress"),
                             "gas":         ("scenario", "stress")},
    "eia_national":         {"electricity": ("benchmark", "eia_national"),
                             "gas":         ("benchmark", "eia_national")},
    "eia_pacific":          {"electricity": ("benchmark", "eia_pacific"),
                             "gas":         ("benchmark", "eia_pacific")},
    "cec_iepr":             {"electricity": ("benchmark", "cec_electric")},
    "cec_bau":              {"gas":         ("benchmark", "cec_gas_extreme")},
    "e3_gas":               {"gas":         ("benchmark", "e3_gas")},
}

# UI display names (single source of truth for buttons + resolved-rate lines).
PROJECTION_LABELS: dict[str, str] = {
    "whywatt_conservative": "WhyWatt Conservative",
    "whywatt_moderate":     "WhyWatt Moderate",
    "whywatt_stress":       "WhyWatt Stress",
    "eia_national":         "US EIA",
    "eia_pacific":          "EIA Pacific",
    "cec_iepr":             "CEC 2025 IEPR",
    "cec_bau":              "CEC 2025 (BAU invest)",
    "e3_gas":               "E3 2020 high",
}

# The three headline scenarios shown as the primary row; the rest are reference/testing
# models shown behind an expander (docs/Phase6_Spec.md WS1 UI, refined 2026-09-07).
PROJECTION_PRIMARY = ("whywatt_conservative", "whywatt_moderate", "whywatt_stress")

# The projection-backed rate models, split by the fuel each one supports. ui/config.py
# imports these so the sanitize enum is fuel-aware (an elec-only model can't be set on gas).
PROJECTION_ELEC_MODELS = frozenset(
    k for k, m in _MODEL_SOURCES.items() if "electricity" in m)
PROJECTION_GAS_MODELS = frozenset(
    k for k, m in _MODEL_SOURCES.items() if "gas" in m)
PROJECTION_MODELS = PROJECTION_ELEC_MODELS | PROJECTION_GAS_MODELS


@functools.lru_cache(maxsize=1)
def _bundle() -> dict:
    """The committed rate-projection bundle. Read once, cached. Plain data."""
    with open(_BUNDLE_PATH, encoding="utf-8") as f:
        return json.load(f)


def supports(model_key: str, fuel: str) -> bool:
    """True if `model_key` carries a series for `fuel` in the bundle."""
    return fuel in _MODEL_SOURCES.get(model_key, {})


class ProjectedRateSource:
    """One standalone annual rate series from the bundle, for one fuel.

    Implements the get_rate / get_annual_monthly_rates read interface so it can either be
    consumed directly (flat months, ACC overlay off) or wrapped in ACCRateLoader (overlay on).
    """

    def __init__(self, model_key: str, fuel: str, market: str | None = None):
        if not supports(model_key, fuel):
            raise ValueError(
                f"Rate model {model_key!r} has no {fuel} series in the projection bundle. "
                f"Supported fuels: {sorted(_MODEL_SOURCES.get(model_key, {}))!r}.")
        self.model_key = model_key
        self.fuel = fuel

        bundle = _bundle()
        self.market = market or bundle["default_market"]
        mkt = bundle["markets"][self.market]

        kind, key = _MODEL_SOURCES[model_key][fuel]
        fk = _FUEL_KEY[fuel]
        node = mkt["scenarios"][key]["retail"] if kind == "scenario" else mkt["benchmarks"][key]
        series = node[fk]                       # {"2025": rate, ...}

        # Store as an int-keyed dict plus its clamped endpoints for out-of-horizon holds.
        self._by_year: dict[int, float] = {int(y): float(v) for y, v in series.items()}
        self._min_year = min(self._by_year)
        self._max_year = max(self._by_year)

    def _level(self, year: int) -> float:
        """Annual $/unit level for `year`, holding the nearest endpoint out of horizon."""
        y = min(max(year, self._min_year), self._max_year)
        return self._by_year[y]

    def get_rate(self, fuel: str, year: int, month: int,
                 scenario: str = "moderate", custom_cagr: float | None = None) -> float:
        """Annual $/unit level for the year. `month`, `scenario`, `custom_cagr` are ignored:
        the model_key already fixed the curve, and the bundle carries no within-year shape
        (that is layered on by ACCRateLoader in the core)."""
        if fuel != self.fuel:
            raise ValueError(
                f"{type(self).__name__}({self.model_key!r}) built for {self.fuel!r}, "
                f"asked for {fuel!r}.")
        return self._level(year)

    def get_annual_monthly_rates(self, fuel: str, sim_start_year: int, n_years: int,
                                  scenario: str = "moderate",
                                  custom_cagr: float | None = None,
                                  device_category: str = "flat") -> np.ndarray:
        """Shape (n_years, 12) — flat within each year (annual level in every month).

        Used only when the ACC overlay is disabled (testing). In normal operation the model
        wraps this source in ACCRateLoader, whose own get_annual_monthly_rates applies the
        monthly/seasonal shape on top of get_rate(). `device_category` is accepted for
        interface parity and ignored here."""
        rates = np.empty((n_years, 12), dtype=float)
        for yr_idx in range(n_years):
            rates[yr_idx, :] = self._level(sim_start_year + yr_idx)
        return rates
