"""Current energy rate × projection growth (Phase 7 §4.1).

Two separate questions, two separate objects:

  **Current energy rate** (`StartingRate`) — what the home pays *today*, per fuel. A fact about
  the home (shared by scenarios A and B), resolved from the ZIP:
      electricity: URDB plan (utility covered, not quarantined)      kind "urdb"
                   else the utility's EIA rate (`starting_rate`)     kind "eia_utility"
                   else the EIA region (starting_rates.json)         kind "eia_region"
      gas:         the gas utility's EIA rate, else the EIA region   (no URDB for gas)

  **Projection method** — how prices *grow*. A curve from the rate-projection bundle, used
  only for its shape: `index[y] = S[y] / S[anchor]`, where *y* is the calendar year and
  *anchor* is the year the current rate is valid for (URDB plan: its effective year; EIA: the
  data year). Price in year y = current rate × index[y]. The curve's own absolute level (built
  from average rates) is never used as a price.

Projection curves exist only for the PG&E market today. Other utilities (and ZIPs with no
utility) use the default market's curves — flagged `is_proxy` so the UI can say "PG&E-based".
Legacy rate models (My Utility / CA Average / ACC) do not come through here.
"""
from __future__ import annotations

import functools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from projected_rate_source import ProjectedRateSource, _bundle
from urdb_rates import RateStructure, get_urdb

_RATES = Path(__file__).parent.parent / "data" / "rates"
_EIA_FILE = _RATES / "eia_rates_by_utility.json"
_REGION_FILE = _RATES / "starting_rates.json"


# Utility -> rate-projection market. A market absent from the bundle falls back to the
# bundle's default market (a proxy — today every non-PG&E utility).
_MARKETS = {
    "electricity": {"14328": "CA_PGE", "17609": "CA_SCE", "16609": "CA_SDGE"},
    "gas": {"17610617": "CA_PGE", "17621931": "CA_SCE", "17611927": "CA_SDGE"},
}
_UNITS = {"electricity": "$/kWh", "gas": "$/therm"}


@dataclass(frozen=True)
class StartingRate:
    """A home's current energy rate for one fuel."""
    fuel: str                           # "electricity" | "gas"
    kind: str                           # "urdb" | "eia_utility" | "eia_region"
    year: int                           # the year this rate is valid for (projection anchor)
    rate: float                         # flat $/unit (for "urdb": the plan's flat equivalent)
    unit: str
    label: str                          # short UI label, e.g. "PG&E · E-TOU-C"
    source: str
    utility_id: str | None = None
    method: str = "observed"            # observed | bridged_state_ratio | regional
    structure: RateStructure | None = None   # the URDB plan (kind "urdb" only)


def market_for(fuel: str, utility_id: str | None) -> tuple[str, bool]:
    """(bundle market, is_proxy) for a utility — the default market when it has none."""
    bundle = _bundle()
    market = _MARKETS[fuel].get(str(utility_id)) if utility_id else None
    if market in bundle["markets"]:
        return market, False
    return bundle["default_market"], True


def projection_index(model_key: str, fuel: str, years: Sequence[int], anchor_year: int,
                     market: str | None = None) -> np.ndarray:
    """Growth index S[y] / S[anchor] for each calendar year in `years`. Years outside the
    curve's horizon hold its nearest endpoint (e.g. after 2050 the 2050 value)."""
    src = ProjectedRateSource(model_key, fuel, market)
    anchor = src.get_rate(fuel, int(anchor_year), 1)
    return np.array([src.get_rate(fuel, int(y), 1) / anchor for y in years], dtype=float)


class IndexedRateSource:
    """A flat current rate grown by a projection curve — the get_rate read interface, so the
    model can wrap it in ACCRateLoader (monthly shape on top) exactly like Phase 6 did with the
    bare bundle series."""

    def __init__(self, start: StartingRate, model_key: str, market: str | None = None):
        self.start = start
        self.model_key = model_key
        self.fuel = start.fuel
        self._src = ProjectedRateSource(model_key, start.fuel, market)
        self._anchor_level = self._src.get_rate(start.fuel, start.year, 1)

    def get_rate(self, fuel: str, year: int, month: int,
                 scenario: str = "moderate", custom_cagr: float | None = None) -> float:
        """Current rate × S[year] / S[anchor]. `month`, `scenario`, `custom_cagr` are ignored
        (the projection method already fixed the curve)."""
        if fuel != self.fuel:
            raise ValueError(f"IndexedRateSource built for {self.fuel!r}, asked for {fuel!r}.")
        return self.start.rate * self._src.get_rate(fuel, year, 1) / self._anchor_level

    def get_annual_monthly_rates(self, fuel: str, sim_start_year: int, n_years: int,
                                  scenario: str = "moderate",
                                  custom_cagr: float | None = None,
                                  device_category: str = "flat") -> np.ndarray:
        """Shape (n_years, 12), flat within each year (the ACC overlay adds the shape)."""
        rows = [self.get_rate(fuel, sim_start_year + y, 1) for y in range(n_years)]
        return np.repeat(np.asarray(rows, dtype=float)[:, None], 12, axis=1)


class StartingRates:
    """Resolve a home's current energy rate per fuel from the committed data files."""

    def __init__(self, eia_file: Path = _EIA_FILE, region_file: Path = _REGION_FILE):
        self._eia = json.loads(eia_file.read_text(encoding="utf-8"))
        self._regions = json.loads(region_file.read_text(encoding="utf-8"))

    def short_name(self, fuel: str, utility_id: str | None) -> str | None:
        """Display name from the rates data (e.g. "PG&E", "SMUD"), None if not priced."""
        db = self._eia["electric_utilities" if fuel == "electricity" else "gas_ldcs"]
        rec = db.get(str(utility_id)) if utility_id else None
        return (rec.get("short_name") or rec["name"]) if rec else None

    def region(self, fuel: str, region_key: str | None = None) -> StartingRate:
        key = region_key or self._regions["default_region"]
        reg = self._regions["regions"][key]
        rec = reg[fuel]
        return StartingRate(fuel=fuel, kind="eia_region", year=int(rec["year"]),
                            rate=float(rec["rate"]), unit=rec["unit"], label=reg["label"],
                            source=rec["source"], method="regional")

    def resolve(self, fuel: str, utility_id: str | None, zip_code: str,
                tariff_label: str | None = None) -> StartingRate:
        """The current energy rate for `fuel`. `utility_id` is the ZIP's resolved utility
        (RateResolver), None when the ZIP resolved to no utility."""
        uid = str(utility_id) if utility_id else None
        short = self.short_name(fuel, uid)
        if fuel == "electricity" and uid:
            rs = get_urdb().resolve(zip_code, uid, tariff_label)
            if rs is not None:
                flat = float(np.mean([rs.effective_rate(m, np.ones(24)) for m in range(12)]))
                return StartingRate(
                    fuel=fuel, kind="urdb", year=rs.effective_year or int(
                        self._eia["_meta"]["starting_year"]),
                    rate=flat, unit=_UNITS[fuel], label=f"{short or rs.utility} · {rs.family}",
                    source=f"URDB {rs.label} (effective {rs.startdate})",
                    utility_id=uid, structure=rs)
        db_key = "electric_utilities" if fuel == "electricity" else "gas_ldcs"
        rec = self._eia[db_key].get(uid) if uid else None
        if rec is not None and rec.get("starting_rate"):
            sr = rec["starting_rate"]
            return StartingRate(
                fuel=fuel, kind="eia_utility", year=int(sr["year"]), rate=float(sr["rate"]),
                unit=rec["unit"], label=f"{short or rec['name']} · EIA {sr['year']}",
                source=sr["source"], utility_id=uid, method=sr.get("method", "observed"))
        return self.region(fuel)


@functools.lru_cache(maxsize=1)
def get_starting_rates() -> StartingRates:
    """Process-wide StartingRates (reads two committed JSON files once)."""
    return StartingRates()
