"""RateResolver — resolve a ZIP to its electric utility and gas LDC (Phase 4 §2).

Reads three committed JSON tables (no network):
  data/rates/eia_rates_by_utility.json     per-utility rates + state_average fallback
  data/rates/zip_to_electric_utility.json  ZIP -> [EIA-861 utility numbers]
  data/rates/zip_to_gas_ldc.json           ZIP -> [EIA-176 gas LDC ids]

Each fuel resolves independently to one of:
  "matched"   — ZIP found directly in the OpenEI crosswalk
  "inferred"  — ZIP backfilled from its ZIP-prefix (lower confidence)
  "fallback"  — ZIP not resolvable → CA statewide average
  "selected"  — user explicitly chose the statewide average

The UI shows the picked utility name and flags inferred/fallback (Energy & Prices panel).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_DATA = Path(__file__).parent.parent / "data"
_RATES_FILE = _DATA / "rates" / "eia_rates_by_utility.json"
_ELEC_ZIP_FILE = _DATA / "rates" / "zip_to_electric_utility.json"
_GAS_ZIP_FILE = _DATA / "rates" / "zip_to_gas_ldc.json"

_DEFAULT_STATE = "CA"


@dataclass
class FuelResolution:
    fuel: str                # "electricity" | "gas"
    utility_id: str | None   # None when fallback / statewide
    name: str                # utility/LDC name, or "California average"
    rate: float              # base rate in `unit`
    unit: str                # "$/kWh" | "$/therm"
    cagr: float              # EIA historical 10-yr CAGR (data-grounded escalation)
    base_year: int           # rate basis year (e.g. 2024)
    provenance: str          # matched | inferred | fallback | selected

    @property
    def is_exact(self) -> bool:
        return self.provenance == "matched"

    @property
    def is_fallback(self) -> bool:
        return self.provenance in ("fallback", "selected")


@dataclass
class RateResolution:
    zip_code: str
    source: str                      # "auto" | "ca_average"
    electricity: FuelResolution
    gas: FuelResolution

    @property
    def any_fallback(self) -> bool:
        return self.electricity.is_fallback or self.gas.is_fallback

    @property
    def any_inferred(self) -> bool:
        return self.electricity.provenance == "inferred" or self.gas.provenance == "inferred"


class RateResolver:
    """Resolve ZIP -> (electric utility, gas LDC) with provenance, from local tables."""

    def __init__(self, rates_file: Path = _RATES_FILE,
                 elec_zip_file: Path = _ELEC_ZIP_FILE,
                 gas_zip_file: Path = _GAS_ZIP_FILE,
                 default_state: str = _DEFAULT_STATE):
        self._rates = json.loads(rates_file.read_text(encoding="utf-8"))
        self._elec_zip = json.loads(elec_zip_file.read_text(encoding="utf-8"))
        self._gas_zip = json.loads(gas_zip_file.read_text(encoding="utf-8"))
        self._elec_inferred = set(self._elec_zip.get("_meta", {}).get("inferred_zips", []))
        self._gas_inferred = set(self._gas_zip.get("_meta", {}).get("inferred_zips", []))
        self._default_state = default_state

    @property
    def data_vintage(self) -> str:
        """Short data-vintage string for the UI, e.g. 'EIA 2024 · revenue ÷ sales'."""
        meta = self._rates.get("_meta", {})
        return f"EIA {meta.get('base_year', '')} · revenue ÷ sales/volume"

    # ── helpers ────────────────────────────────────────────────────────────────
    def _state_avg(self, fuel: str) -> dict:
        return self._rates["state_average"][self._default_state][fuel]

    def _fallback(self, fuel: str, selected: bool) -> FuelResolution:
        rec = self._state_avg(fuel)
        label = self._rates["state_average"][self._default_state].get("label", self._default_state)
        return FuelResolution(
            fuel=fuel, utility_id=None, name=f"{label} average",
            rate=rec["current_rate"], unit=rec["unit"],
            cagr=rec["historical_cagr_10yr"], base_year=rec["base_year"],
            provenance="selected" if selected else "fallback")

    def _resolve_fuel(self, fuel: str, zipcode: str,
                      zip_map: dict, db_key: str, inferred: set) -> FuelResolution:
        ids = zip_map.get(str(zipcode).strip())
        if ids:
            db = self._rates[db_key]
            candidates = [i for i in ids if i in db]       # only utilities we price
            if candidates:
                uid = sorted(candidates)[0]                # deterministic pick
                rec = db[uid]
                prov = "inferred" if str(zipcode).strip() in inferred else "matched"
                return FuelResolution(
                    fuel=fuel, utility_id=uid, name=rec["name"], rate=rec["current_rate"],
                    unit=rec["unit"], cagr=rec["historical_cagr_10yr"],
                    base_year=rec["base_year"], provenance=prov)
        return self._fallback(fuel, selected=False)

    # ── public ─────────────────────────────────────────────────────────────────
    def resolve(self, zipcode: str, source: str = "auto") -> RateResolution:
        if source == "ca_average":
            return RateResolution(
                zip_code=str(zipcode), source=source,
                electricity=self._fallback("electricity", selected=True),
                gas=self._fallback("gas", selected=True))
        elec = self._resolve_fuel("electricity", zipcode, self._elec_zip,
                                  "electric_utilities", self._elec_inferred)
        gas = self._resolve_fuel("gas", zipcode, self._gas_zip,
                                 "gas_ldcs", self._gas_inferred)
        return RateResolution(zip_code=str(zipcode), source=source,
                              electricity=elec, gas=gas)
