"""
RateLoader — maps (fuel, year, month) to $/kWh or $/therm.

Historical periods: published CPUC/PG&E rates by effective date range.
Future periods: base_rate × (1 + cagr)^(year - base_year), scenario-driven.

ACCRateLoader wraps a RateLoader and applies ACC shape factors:
  Electric: retail_rate[m] × dot(device_load_profile, acc_hourly_shape[m])
  Gas:      retail_rate[m] × acc_monthly_shape[m]

Revenue-neutral: a flat (uniform) device profile returns the same annual cost as
the base RateLoader — devices that run off-peak cost less, peak devices cost more.
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
                                  custom_cagr: float | None = None,
                                  device_category: str = "flat") -> np.ndarray:
        """
        Return shape (n_years, 12) — one rate per month per simulation year.
        Row 0 = sim_start_year, row 1 = sim_start_year+1, etc.
        Historical months use published rates; future months use CAGR projection.

        custom_cagr: when provided, overrides the scenario CAGR for projection years.
        device_category: accepted for API compatibility with ACCRateLoader; ignored here.
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


class ACCRateLoader:
    """
    Wraps RateLoader and applies 2024 CPUC ACC shape factors to produce
    device-specific effective monthly rates.

    Electric: retail_rate[m] × dot(device_load_profile[24h], acc_shape[m, 24h])
    Gas:      retail_rate[m] × acc_monthly_gas_shape[m]

    custom_cagr is intentionally ignored — ACC uses the base scenario CAGR from
    the underlying RateLoader; the user-selected CAGR % does not apply to ACC mode.
    """

    def __init__(self, base_loader: RateLoader):
        self._base = base_loader

        elec_path = _RATES_DIR / "acc_electric_shape_pge_2024.json"
        with open(elec_path) as f:
            elec_data = json.load(f)
        self._elec_shape = np.array(elec_data["shape_24h_by_month"], dtype=float)
        assert self._elec_shape.shape == (12, 24), \
            f"Expected (12,24) ACC electric shape, got {self._elec_shape.shape}"

        gas_path = _RATES_DIR / "acc_gas_shape_pge_2024.json"
        with open(gas_path) as f:
            gas_data = json.load(f)
        self._gas_shape = np.array(gas_data["monthly_shape"], dtype=float)
        assert self._gas_shape.shape == (12,), \
            f"Expected (12,) ACC gas shape, got {self._gas_shape.shape}"

        prof_path = _RATES_DIR / "device_load_shapes.json"
        with open(prof_path) as f:
            prof_data = json.load(f)
        self._profiles: dict[str, np.ndarray] = {
            k: np.array(v, dtype=float)
            for k, v in prof_data["profiles"].items()
        }

    def get_annual_monthly_rates(self, fuel: str, sim_start_year: int,
                                  n_years: int,
                                  device_category: str = "flat",
                                  scenario: str = "moderate",
                                  custom_cagr: float | None = None) -> np.ndarray:
        """
        Return shape (n_years, 12) ACC-weighted effective rates for the given device category.
        custom_cagr is ignored — ACC uses the scenario CAGR from the base loader.
        """
        rates = np.empty((n_years, 12), dtype=float)
        profile = self._profiles.get(device_category, self._profiles["flat"])
        for yr_idx in range(n_years):
            year = sim_start_year + yr_idx
            for mo in range(1, 13):
                retail = self._base.get_rate(fuel, year, mo, scenario, custom_cagr)
                if fuel == "gas":
                    rates[yr_idx, mo - 1] = retail * float(self._gas_shape[mo - 1])
                else:
                    weighted = float(np.dot(profile, self._elec_shape[mo - 1]))
                    rates[yr_idx, mo - 1] = retail * weighted
        return rates
