"""SolarResourceLoader + SolarResource — ZIP-driven PVWatts solar yield (Phase 7 §1).

Reads the offline-baked PVWatts tables in ``data/solar/pvwatts_zip.json`` (built by
``scripts/build_pvwatts.py``; see docs/OfflineSolarData_Plan.md). Every lookup returns a full
table — never a scalar — resolved in this order:

  1. ZIP site     — the ZIP's region has been harvested (``zips[zip]``)
  2. zone station — the ZIP's CEC zone reference station (via data/climate/zip_to_zone.json)
  3. default      — the CZ4 (San José) station, for unknown / out-of-state ZIPs

The file stores PVWatts' native local standard time. This loader converts the intra-day shape
to CLOCK time once (March–October shifted +1 h for daylight saving, month-level
approximation) so every consumer — dispatch, URDB peak hours, charts — sees the same hours.

Location data only: SolarResource is never user-edited or serialized. HomeConfig exposes it
as the derived ``solar_resource`` property; devices never read the file (Hard rule 2).
No network calls — the file is committed and read locally.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_DATA = Path(__file__).parent.parent / "data"
_SOLAR_FILE = _DATA / "solar" / "pvwatts_zip.json"
_ZIP_FILE = _DATA / "climate" / "zip_to_zone.json"

SCHEMA_VERSION = 1
DST_MONTHS = np.array([m in range(3, 11) for m in range(1, 13)])   # Mar–Oct on daylight time


@dataclass(frozen=True, eq=False)
class SolarResource:
    """Per-kW solar yield for one location. Arrays are read-only."""

    ac_monthly: np.ndarray        # (12,)   kWh AC per kW DC per month
    intraday_shape: np.ndarray    # (12,24) fraction of each month's energy per CLOCK hour
    level: str                    # "zip" | "zone" | "default"
    zip_code: str
    zone_key: str                 # e.g. "CA_CZ4"
    site_key: str                 # e.g. "zip:94040" | "zone:CA_CZ4"
    label: str                    # e.g. "PVWatts · ZIP 94040" | "PVWatts · CZ4 zone estimate"
    source: str                   # e.g. "PVWatts v8 · NSRDB PSM V3 GOES tmy-2020 3.2.0 · built …"

    @property
    def ac_annual(self) -> float:
        """kWh AC per kW DC per year."""
        return float(self.ac_monthly.sum())

    @property
    def is_fallback(self) -> bool:
        """True when the ZIP has no ZIP-level table (zone or default estimate)."""
        return self.level != "zip"


def to_clock_time(shape_lst: np.ndarray) -> np.ndarray:
    """Shift a (12,24) local-standard-time shape to clock time (+1 h in DST months).

    np.roll moves hour 23 to hour 0; PVWatts output is zero at those night hours, so no
    energy wraps. Each row's sum is preserved exactly.
    """
    return np.array([np.roll(row, 1) if dst else row
                     for row, dst in zip(shape_lst, DST_MONTHS)])


def _readonly(a) -> np.ndarray:
    arr = np.array(a, dtype=float)
    arr.flags.writeable = False
    return arr


class SolarResourceLoader:
    """ZIP → SolarResource over the committed PVWatts tables. Load once per process."""

    def __init__(self, solar_file: Path = _SOLAR_FILE, zip_file: Path = _ZIP_FILE):
        if not solar_file.exists():
            raise FileNotFoundError(f"PVWatts solar data missing: {solar_file} "
                                    "(committed file — run scripts/build_pvwatts.py)")
        doc = json.loads(solar_file.read_text(encoding="utf-8"))
        meta = doc.get("_meta", {})
        version = meta.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(f"{solar_file.name}: schema_version {version!r}, "
                             f"loader expects {SCHEMA_VERSION}")
        self._sites = doc["sites"]
        self._zips = doc["zips"]
        self._zones = doc["zones"]
        self._default = doc["default"]
        self._built = meta.get("built", "")
        zip_raw = json.loads(zip_file.read_text(encoding="utf-8"))
        self._zip_to_zone = {k: v for k, v in zip_raw.items() if not k.startswith("_")}
        self._cache: dict[str, SolarResource] = {}
        self._validate()

    def _validate(self) -> None:
        for key, s in self._sites.items():
            m = np.asarray(s["ac_monthly"], dtype=float)
            sh = np.asarray(s["intraday_shape"], dtype=float)
            if m.shape != (12,) or (m <= 0).any():
                raise ValueError(f"site {key}: ac_monthly must be 12 positive values")
            if sh.shape != (12, 24) or not np.allclose(sh.sum(axis=1), 1.0, atol=1e-4):
                raise ValueError(f"site {key}: intraday_shape must be 12×24, rows summing to 1")
        refs = [z["site"] for z in self._zips.values()] + [z["site"] for z in self._zones.values()]
        for ref in refs + [self._default["site"]]:
            if ref not in self._sites:
                raise ValueError(f"index points to missing site {ref!r}")

    def resolve(self, zipcode: str) -> SolarResource:
        """ZIP → ZIP site, else zone station, else default. Never raises for a bad ZIP."""
        z = str(zipcode).strip()
        if z not in self._cache:
            self._cache[z] = self._build(z)
        return self._cache[z]

    def _build(self, z: str) -> SolarResource:
        if z in self._zips:
            entry = self._zips[z]
            level, zone, site_key = "zip", entry["zone"], entry["site"]
            label = f"PVWatts · ZIP {z}"
        elif self._zip_to_zone.get(z) in self._zones:
            zone = self._zip_to_zone[z]
            level, site_key = "zone", self._zones[zone]["site"]
            label = f"PVWatts · {zone.split('_')[-1]} zone estimate"
        else:
            zone = self._default["zone"]
            level, site_key = "default", self._default["site"]
            label = f"PVWatts · {zone.split('_')[-1]} (San José) estimate"
        site = self._sites[site_key]
        weather = site.get("nsrdb_station", {}).get("weather_data_source") or "NSRDB"
        return SolarResource(
            ac_monthly=_readonly(site["ac_monthly"]),
            intraday_shape=_readonly(to_clock_time(np.asarray(site["intraday_shape"], dtype=float))),
            level=level, zip_code=z, zone_key=zone, site_key=site_key, label=label,
            source=f"PVWatts v8 · {weather} · built {self._built}",
        )


_LOADER: SolarResourceLoader | None = None


def get_loader() -> SolarResourceLoader:
    """Process-wide loader (lazy, like model._CLIMATE_LOADER)."""
    global _LOADER
    if _LOADER is None:
        _LOADER = SolarResourceLoader()
    return _LOADER
