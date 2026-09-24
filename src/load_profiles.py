"""LoadProfileLoader + LoadProfiles — NREL ResStock hourly end-use load shapes (Phase 7 §6).

Reads ``data/loads/end_use_profiles.json`` (built offline by ``scripts/build_load_profiles.py``;
see docs/NREL_LoadProfiles_Plan.md): per CEC Building Climate Zone × end use, a (12 months ×
24 hours) shape whose rows sum to 1. The energy balance spreads each electric device's monthly
kWh over its month's row.

Resolution: ZIP → CEC zone (data/climate/zip_to_zone.json) → that zone's profiles, else the
CZ4 (San José) default. The file stores local STANDARD time; the loader shifts to CLOCK time
once, with the same month-level daylight-saving rule as the PVWatts solar data
(solar_loader.to_clock_time), so loads, solar and TOU peak hours share one clock.

Location data only: never user-edited or serialized. HomeConfig exposes it as the derived
``load_profiles`` property; devices never read the file (Hard rule 2).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from solar_loader import to_clock_time

_DATA = Path(__file__).parent.parent / "data"
_PROFILE_FILE = _DATA / "loads" / "end_use_profiles.json"
_ZIP_FILE = _DATA / "climate" / "zip_to_zone.json"

SCHEMA_VERSION = 1
DEFAULT_ZONE = "CA_CZ4"

# Heat-pump HVAC is split into these two parts by JourneyHome (the device reports both).
HP_HEATING = "HeatPumpHVAC.heating"
HP_COOLING = "HeatPumpHVAC.cooling"

# Device class (or heat-pump part) → NREL end-use group in the file.
DEVICE_END_USE: dict[str, str] = {
    "LightsAndPlugs":      "lights_plugs",
    "InductionCooktop":    "cooking",
    "ElectricOven":        "cooking",
    "HeatPumpDryer":       "clothes_dryer",
    "Dishwasher":          "dishwasher",
    "CentralAC":           "hvac_cooling",
    HP_HEATING:            "hvac_heating",
    HP_COOLING:            "hvac_cooling",
    "HeatPumpWaterHeater": "water_heating",
    "EVCharger":           "ev_managed",
    "PhysicsEVCharger":    "ev_managed",
    "ElectricVehicle":     "ev_managed",
}
FALLBACK_END_USE = "lights_plugs"   # any other electric device


def _readonly(a) -> np.ndarray:
    arr = np.array(a, dtype=float)
    arr.flags.writeable = False
    return arr


@dataclass(frozen=True, eq=False)
class LoadProfiles:
    """One zone's end-use shapes, in clock time. Arrays are read-only."""

    zone_key: str                        # e.g. "CA_CZ4"
    level: str                           # "zone" | "default"
    end_uses: dict                       # {end use: (12, 24) clock-time shape}
    source: str

    def end_use_for(self, key: str) -> str:
        return DEVICE_END_USE.get(key, FALLBACK_END_USE)

    def shape(self, key: str, month: int) -> np.ndarray:
        """(24,) clock-hour shape summing to 1 for a device class / heat-pump part; month 0–11."""
        return self.end_uses[self.end_use_for(key)][month]

    def heat_pump_shape(self, month: int, heating_share: float) -> np.ndarray:
        """Whole heat pump in one month: its heating and cooling shapes blended by energy."""
        h = float(np.clip(heating_share, 0.0, 1.0))
        return h * self.shape(HP_HEATING, month) + (1.0 - h) * self.shape(HP_COOLING, month)


class LoadProfileLoader:
    """ZIP → LoadProfiles over the committed ResStock tables. Load once per process."""

    def __init__(self, profile_file: Path = _PROFILE_FILE, zip_file: Path = _ZIP_FILE):
        if not profile_file.exists():
            raise FileNotFoundError(f"load profiles missing: {profile_file} "
                                    "(committed file — run scripts/build_load_profiles.py)")
        doc = json.loads(profile_file.read_text(encoding="utf-8"))
        meta = doc.get("_meta", {})
        version = meta.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(f"{profile_file.name}: schema_version {version!r}, "
                             f"loader expects {SCHEMA_VERSION}")
        self._profiles = doc["profiles"]
        self._source = f"NREL ResStock 2025.1 (AMY2018) · built {meta.get('built', '')}"
        zip_raw = json.loads(zip_file.read_text(encoding="utf-8"))
        self._zip_to_zone = {k: v for k, v in zip_raw.items() if not k.startswith("_")}
        self._cache: dict[str, LoadProfiles] = {}
        self._validate()

    def _validate(self) -> None:
        if DEFAULT_ZONE not in self._profiles:
            raise ValueError(f"default zone {DEFAULT_ZONE} missing")
        needed = set(DEVICE_END_USE.values()) | {FALLBACK_END_USE}
        for zone, uses in self._profiles.items():
            missing = needed - set(uses)
            if missing:
                raise ValueError(f"{zone}: missing end uses {sorted(missing)}")
            for name, rows in uses.items():
                a = np.asarray(rows, dtype=float)
                if a.shape != (12, 24) or (a < 0).any() or not np.allclose(a.sum(axis=1), 1.0, atol=1e-3):
                    raise ValueError(f"{zone}/{name}: must be 12×24, non-negative, rows summing to 1")

    def for_zone(self, zone_key: str | None) -> LoadProfiles:
        z = zone_key if zone_key in self._profiles else DEFAULT_ZONE
        level = "zone" if z == zone_key else "default"
        key = f"{z}|{level}"
        if key not in self._cache:
            uses = {}
            for name, rows in self._profiles[z].items():
                a = to_clock_time(np.asarray(rows, dtype=float))
                uses[name] = _readonly(a / a.sum(axis=1, keepdims=True))   # exact after rounding
            self._cache[key] = LoadProfiles(zone_key=z, level=level, end_uses=uses,
                                            source=self._source)
        return self._cache[key]

    def resolve(self, zipcode: str) -> LoadProfiles:
        """ZIP → its CEC zone's profiles, else the CZ4 default. Never raises for a bad ZIP."""
        return self.for_zone(self._zip_to_zone.get(str(zipcode).strip()))


_LOADER: LoadProfileLoader | None = None


def get_loader() -> LoadProfileLoader:
    """Process-wide loader (lazy, like solar_loader.get_loader)."""
    global _LOADER
    if _LOADER is None:
        _LOADER = LoadProfileLoader()
    return _LOADER
