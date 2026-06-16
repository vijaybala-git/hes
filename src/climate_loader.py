"""ClimateLoader + ClimateData — ZIP-driven climate with a per-year trend trajectory.

Phase 4 §1 / §1.9 (Option B). The full ``(n_years, 12)`` HDD/CDD trajectory is
precomputed once at construction; the simulation advances ``current_year`` each tick and
devices read the live ``monthly_hdd`` / ``monthly_cdd`` / ``monthly_inlet`` properties
instead of a frozen array. With ``trend_scenario="none"`` (CAGR == 0) every year's row
equals the base year, so the static TMY3 baseline reproduces exactly.

Two-file lookup (data/climate/):
  zip_to_zone.json   ZIP -> zone key (e.g. "95110" -> "CA_CZ4")
  tmy3_zones.json    zone key -> climate record (monthly HDD/CDD/inlet/avg-temp + CAGRs)

No network calls — both files are committed and read locally.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_DATA = Path(__file__).parent.parent / "data"
_ZONES_FILE = _DATA / "climate" / "tmy3_zones.json"
_ZIP_FILE = _DATA / "climate" / "zip_to_zone.json"

TREND_SCENARIOS = ("none", "rcp45", "rcp85")
_DEFAULT_FALLBACK_ZONE = "CA_CZ4"


@dataclass
class ClimateData:
    """Live, per-year view over a precomputed climate trajectory (spec §1.9.4).

    ``current_year`` is advanced by HESModel.step(); the ``monthly_*`` properties return
    the slice for that year. HDD/CDD carry the trend; inlet water and avg temp are static
    in Phase 4 (only HDD/CDD are trended — §1.7).
    """

    zone_key: str
    zone_label: str                # e.g. "CZ4 — San Jose"
    zone_id: str                   # e.g. "CZ4"
    reference_city: str            # e.g. "San Jose"
    trend_scenario: str
    annual_hdd_65f: float
    annual_cdd_65f: float
    hdd_cagr: float                # resolved annual CAGR for the chosen scenario (0 for "none")
    cdd_cagr: float
    fallback: bool                 # True when the ZIP was not found and we used the default zone
    hdd_traj: np.ndarray           # (n_years, 12) — base * (1 + hdd_cagr) ** year
    cdd_traj: np.ndarray           # (n_years, 12)
    inlet: np.ndarray              # (12,) static
    avg_temp: np.ndarray           # (12,) static base-year monthly avg dry-bulb (reserved for §4)
    current_year: int = 0

    @property
    def n_years(self) -> int:
        return int(self.hdd_traj.shape[0])

    @property
    def monthly_hdd(self) -> np.ndarray:
        return self.hdd_traj[self.current_year]

    @property
    def monthly_cdd(self) -> np.ndarray:
        return self.cdd_traj[self.current_year]

    @property
    def monthly_inlet(self) -> np.ndarray:
        return self.inlet

    @property
    def monthly_avg_temp(self) -> np.ndarray:
        return self.avg_temp

    def advance_to(self, year: int) -> None:
        """Point the live view at simulation year ``year`` (clamped to the horizon)."""
        self.current_year = max(0, min(int(year), self.n_years - 1))


class ClimateLoader:
    """Resolves a ZIP to a CEC climate zone and builds a trended ClimateData trajectory."""

    def __init__(self, zones_file: Path = _ZONES_FILE, zip_file: Path = _ZIP_FILE):
        with open(zones_file) as f:
            zones_raw = json.load(f)
        with open(zip_file) as f:
            zip_raw = json.load(f)
        # '_'-prefixed keys are metadata (schema_version, status, fallback_zone, ...).
        self._zones = {k: v for k, v in zones_raw.items() if not k.startswith("_")}
        self._zip = {k: v for k, v in zip_raw.items() if not k.startswith("_")}
        self._fallback_zone = zip_raw.get("_meta", {}).get(
            "fallback_zone", _DEFAULT_FALLBACK_ZONE)

    # ── Lookup ────────────────────────────────────────────────────────────────
    def resolve_zone(self, zipcode: str) -> tuple[str, bool]:
        """Return (zone_key, fallback_flag). Unknown ZIP -> (fallback zone, True)."""
        zone = self._zip.get(str(zipcode).strip())
        if zone is not None and zone in self._zones:
            return zone, False
        return self._fallback_zone, True

    def get_climate(self, zipcode: str, n_years: int = 25,
                    trend_scenario: str = "none") -> ClimateData:
        if trend_scenario not in TREND_SCENARIOS:
            raise ValueError(
                f"trend_scenario must be one of {TREND_SCENARIOS}, got {trend_scenario!r}")

        zone_key, fallback = self.resolve_zone(zipcode)
        rec = self._zones[zone_key]

        base_hdd = np.asarray(rec["monthly_hdd_65f"], dtype=float)
        base_cdd = np.asarray(rec["monthly_cdd_65f"], dtype=float)
        hdd_cagr = float(rec.get("hdd_cagr_by_scenario", {}).get(trend_scenario, 0.0))
        cdd_cagr = float(rec.get("cdd_cagr_by_scenario", {}).get(trend_scenario, 0.0))

        years = np.arange(n_years)
        hdd_traj = base_hdd[None, :] * (1.0 + hdd_cagr) ** years[:, None]
        cdd_traj = base_cdd[None, :] * (1.0 + cdd_cagr) ** years[:, None]

        return ClimateData(
            zone_key=zone_key,
            zone_label=f"{rec['zone_id']} — {rec['reference_city']}",
            zone_id=rec["zone_id"],
            reference_city=rec["reference_city"],
            trend_scenario=trend_scenario,
            annual_hdd_65f=float(rec["annual_hdd_65f"]),
            annual_cdd_65f=float(rec["annual_cdd_65f"]),
            hdd_cagr=hdd_cagr,
            cdd_cagr=cdd_cagr,
            fallback=fallback,
            hdd_traj=hdd_traj,
            cdd_traj=cdd_traj,
            inlet=np.asarray(rec["monthly_inlet_water_f"], dtype=float),
            avg_temp=np.asarray(rec["monthly_avg_temp_f"], dtype=float),
        )
