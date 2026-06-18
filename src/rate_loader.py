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
import functools
import json
from pathlib import Path

import numpy as np

_RATES_DIR = Path(__file__).parent.parent / "data" / "rates"

# TODO(Phase 4 cleanup): the hardcoded PG&E/CPUC rate files below are no longer used as a
# primary rate source — the EIA per-utility / CA-average modes replaced the old "CAGR" option
# in the UI (Phase 4 §2). They are now consumed ONLY as the base for ACCRateLoader. Once the
# ACC base is re-sourced (or ACC retired), remove these files and the default __init__ path.
_FUEL_FILES = {
    "electricity": "pge_elec_e1.json",
    "gas":         "pge_gas_g1.json",
}

_EIA_RATES_FILE = _RATES_DIR / "eia_rates_by_utility.json"

_VALID_SCENARIOS = {"conservative", "moderate", "stress"}


@functools.lru_cache(maxsize=1)
def _eia_db() -> dict:
    """The committed EIA per-utility rate database (Phase 4 §2). Cached."""
    with open(_EIA_RATES_FILE, encoding="utf-8") as f:
        return json.load(f)


class RateLoader:
    def __init__(self):
        self._data: dict[str, dict] = {}
        # Per-fuel monthly seasonal shape. PG&E/CPUC loaders are flat (×1); the EIA
        # factories may carry a real shape. Applied in get_annual_monthly_rates.
        self._seasonal_shape: dict[str, np.ndarray] = {}
        for fuel, filename in _FUEL_FILES.items():
            with open(_RATES_DIR / filename, encoding="utf-8") as f:
                self._data[fuel] = json.load(f)
            self._seasonal_shape[fuel] = np.ones(12)

    # ── EIA per-utility factories (Phase 4 §2.6) ────────────────────────────────
    @classmethod
    def from_eia_utility(cls, util_id: str, fuel: str) -> "RateLoader":
        """Build a loader from a resolved EIA utility/LDC id (revenue-÷-sales rate)."""
        key = "electric_utilities" if fuel == "electricity" else "gas_ldcs"
        return cls._from_eia_record(fuel, _eia_db()[key][str(util_id)])

    @classmethod
    def from_eia_state(cls, state: str, fuel: str) -> "RateLoader":
        """Build a loader from the statewide-average EIA series (ZIP-unresolved fallback)."""
        return cls._from_eia_record(fuel, _eia_db()["state_average"][state][fuel])

    @classmethod
    def _from_eia_record(cls, fuel: str, rec: dict) -> "RateLoader":
        self = cls.__new__(cls)
        self._data = {}
        self._seasonal_shape = {}
        cagr = float(rec["historical_cagr_10yr"])
        # No historical periods — the 2024 base is projected forward for every sim year.
        # The named scenarios all map to the EIA historical CAGR; the user CAGR slider
        # still overrides via custom_cagr (§2.2).
        self._data[fuel] = {
            "periods": [],
            "projection": {
                "base_rate": float(rec["current_rate"]),
                "base_year": int(rec["base_year"]),
                "cagr_conservative": cagr, "cagr_moderate": cagr, "cagr_stress": cagr,
            },
        }
        self._seasonal_shape[fuel] = np.asarray(rec["monthly_seasonal_shape"], dtype=float)
        return self

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
        shape = self._seasonal_shape.get(fuel, np.ones(12))
        rates = np.empty((n_years, 12), dtype=float)
        for yr_idx in range(n_years):
            year = sim_start_year + yr_idx
            for mo in range(1, 13):
                rates[yr_idx, mo - 1] = (
                    self.get_rate(fuel, year, mo, scenario, custom_cagr) * shape[mo - 1])
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

        # Pre-normalisation monthly average ACC values in $/kWh — used as NEM 3.0
        # solar export credit rates. These are absolute avoided-cost values, NOT
        # scaled by retail rate. Shape: (12,).
        self.monthly_avg_acc_kwh: np.ndarray = np.array(
            elec_data["monthly_avg_acc_kwh"], dtype=float
        )
        assert self.monthly_avg_acc_kwh.shape == (12,), \
            f"Expected (12,) monthly_avg_acc_kwh, got {self.monthly_avg_acc_kwh.shape}"

        prof_path = _RATES_DIR / "device_load_shapes.json"
        with open(prof_path) as f:
            prof_data = json.load(f)
        self._profiles: dict[str, np.ndarray] = {
            k: np.array(v, dtype=float)
            for k, v in prof_data["profiles"].items()
        }

    def get_nem3_export_rates(self, sim_start_year: int, n_years: int,
                              scenario: str = "moderate",
                              custom_cagr: float | None = None) -> np.ndarray:
        """Return shape (n_years, 12) NEM 3.0 export credit rates in $/kWh.

        Based on the pre-normalisation ACC monthly averages, escalated by the same
        CAGR as consumption rates (scenario-driven). These are absolute $/kWh values
        — do NOT multiply by retail rate.
        """
        base_year = sim_start_year
        # Derive the CAGR to apply: use the same projection block as the base loader.
        # get_rate returns the projected retail rate; we compute the year-0 ACC baseline
        # and then apply the same growth factor rather than calling get_rate (which would
        # mix retail levels with ACC levels).
        proj = self._base._fuel_data("electricity")["projection"]
        cagr = custom_cagr if custom_cagr is not None else proj.get(
            f"cagr_{scenario}", proj["cagr_moderate"]
        )

        rates = np.empty((n_years, 12), dtype=float)
        for yr_idx in range(n_years):
            growth = (1.0 + cagr) ** yr_idx
            for mo in range(12):
                rates[yr_idx, mo] = float(self.monthly_avg_acc_kwh[mo]) * growth
        return rates

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
