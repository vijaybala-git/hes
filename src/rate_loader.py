"""
RateLoader — maps (fuel, year, month) to $/kWh or $/therm.

Historical periods: published CPUC/PG&E rates by effective date range.
Future periods: base_rate × (1 + cagr)^(year - base_year), scenario-driven.
"""
import json
from pathlib import Path

import numpy as np

_RATES_DIR = Path(__file__).parent.parent / "data" / "rates"

_FUEL_FILES = {
    "electricity": "pge_elec_e1.json",
    "gas":         "pge_gas_g1.json",
}

_VALID_SCENARIOS = {"conservative", "moderate", "stress"}


class RateLoader:
    def __init__(self):
        self._data: dict[str, dict] = {}
        for fuel, filename in _FUEL_FILES.items():
            with open(_RATES_DIR / filename, encoding="utf-8") as f:
                self._data[fuel] = json.load(f)

    def _fuel_data(self, fuel: str) -> dict:
        if fuel not in self._data:
            raise ValueError(f"Unknown fuel: {fuel!r}. Expected one of {list(_FUEL_FILES)!r}.")
        return self._data[fuel]

    def get_rate(self, fuel: str, year: int, month: int,
                 scenario: str = "moderate",
                 custom_cagr: float | None = None) -> float:
        """Return $/kWh (electricity) or $/therm (gas) for the given year+month.

        custom_cagr: when provided, overrides the scenario CAGR for projection years.
        Historical period lookup is unchanged regardless of custom_cagr.
        """
        data = self._fuel_data(fuel)

        key = year * 12 + month
        for period in data["periods"]:
            s_yr, s_mo = map(int, period["start"].split("-"))
            e_yr, e_mo = map(int, period["end"].split("-"))
            if s_yr * 12 + s_mo <= key <= e_yr * 12 + e_mo:
                return period["rate"]

        # Beyond last historical period — use CAGR projection
        proj = data["projection"]
        if custom_cagr is not None:
            cagr = custom_cagr
        else:
            if scenario not in _VALID_SCENARIOS:
                raise ValueError(
                    f"Unknown scenario: {scenario!r}. Expected one of {sorted(_VALID_SCENARIOS)!r}."
                )
            cagr = proj[f"cagr_{scenario}"]
        return proj["base_rate"] * (1 + cagr) ** (year - proj["base_year"])

    def get_annual_monthly_rates(self, fuel: str, sim_start_year: int,
                                  n_years: int, scenario: str = "moderate",
                                  custom_cagr: float | None = None) -> np.ndarray:
        """
        Return shape (n_years, 12) — one rate per month per simulation year.
        Row 0 = sim_start_year, row 1 = sim_start_year+1, etc.
        Historical months use published rates; future months use CAGR projection.

        custom_cagr: when provided, overrides the scenario CAGR for projection years.
        """
        if scenario not in _VALID_SCENARIOS:
            raise ValueError(
                f"Unknown scenario: {scenario!r}. Expected one of {sorted(_VALID_SCENARIOS)!r}."
            )
        rates = np.empty((n_years, 12), dtype=float)
        for yr_idx in range(n_years):
            year = sim_start_year + yr_idx
            for mo in range(1, 13):
                rates[yr_idx, mo - 1] = self.get_rate(fuel, year, mo, scenario, custom_cagr)
        return rates
