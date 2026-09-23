"""URDB time-of-use electricity rates at runtime (Phase 7 §3).

Reads the offline-harvested tariffs (``data/rates/urdb_tou.json``, built by
``scripts/build_urdb.py``; see docs/OfflineURDB_Plan.md) and turns one tariff into a
source-agnostic :class:`RateStructure` the simulation prices against:

  period_fractions(month, shape24)      per device, pure geometry (no $): the share of its
                                        daily energy that falls in this tariff's peak hours
  tier1_rates(month)                    (peak, off-peak) $/kWh of the first tier
  price_month(month, peak_kwh, offpeak_kwh, days, escalation)
                                        the home-level monthly bill: walk the baseline tiers on
                                        the month's total, price each tier's kWh at its peak /
                                        off-peak rate in proportion, add the fixed charge

Coverage gate (``resolve``): a utility is priced from URDB only when OpenEI maintains it
annually (``urdb_coverage.json``), we harvested it (``urdb_tou.json``), and it is not
quarantined for a known data problem. Otherwise ``resolve`` returns ``None`` and the caller
keeps today's EIA rate path — no path throws (Invariant 4).

Baseline allowance: tier-1 thresholds follow the home's baseline territory,
``ZIP → CEC zone → territory`` via ``urdb_baseline_crosswalk.json``. Rates are
territory-invariant; only the kWh/day allowance moves. Tier thresholds never escalate; only
$ amounts do. Peak hours are local clock time (URDB schedules).

Electricity only — gas stays on the EIA path.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

_DATA = Path(__file__).parent.parent / "data"
_TOU_FILE = _DATA / "rates" / "urdb_tou.json"
_COVERAGE_FILE = _DATA / "rates" / "urdb_coverage.json"
_CROSSWALK_FILE = _DATA / "rates" / "urdb_baseline_crosswalk.json"
_ZIP_ZONE_FILE = _DATA / "climate" / "zip_to_zone.json"

# Harvested utilities we must NOT price from URDB yet, with the reason shown to the user.
QUARANTINE: dict[str, str] = {
    "17609": ("SCE's URDB record for TOU-D-4-9PM (effective 2024-06-01) shows a summer on-peak "
              "rate of $0.33/kWh, the same as winter; SCE publishes about $0.58. Priced from EIA "
              "until the record is re-harvested and checked against SCE's tariff sheets."),
}

DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


@dataclass(frozen=True)
class Tier:
    max_kwh_day: float | None        # None = unbounded top tier
    rate: float                      # $/kWh at the tariff's vintage


@dataclass(frozen=True)
class RateStructure:
    eiaid: str
    utility: str
    label: str                       # URDB label
    name: str                        # e.g. "E-TOU-C Residential Time of Use …"
    family: str                      # e.g. "E-TOU-C"
    plan_kind: str                   # "tou" | "ev_tou" | "tiered_legacy"
    is_tou: bool
    peak_hours: tuple                # clock hours; empty for a non-TOU (flat) tariff
    peak_ladders: tuple              # 12 × tuple[Tier]
    offpeak_ladders: tuple           # 12 × tuple[Tier]
    fixed_amount: float              # $ per fixed_unit
    fixed_unit: str                  # "$/day" | "$/month"
    baseline_region: str | None      # territory used for tier-1 thresholds
    baseline_confidence: str         # high | approximate | fallback | not_applicable
    closed_to_enrollment: bool = False

    # ── geometry ──────────────────────────────────────────────────────────────
    def peak_mask(self) -> np.ndarray:
        m = np.zeros(24, dtype=bool)
        for h in self.peak_hours:
            m[int(h)] = True
        return m

    def period_fractions(self, month: int, shape24) -> dict:
        """Share of a 24-h load shape falling in this tariff's peak window (shape need not sum
        to 1 — it is normalised here)."""
        s = np.asarray(shape24, dtype=float)
        total = s.sum()
        peak = float(s[self.peak_mask()].sum() / total) if total > 0 else 0.0
        return {"peak": peak, "offpeak": 1.0 - peak}

    # ── prices ────────────────────────────────────────────────────────────────
    def tier1_rates(self, month: int) -> tuple[float, float]:
        return self.peak_ladders[month][0].rate, self.offpeak_ladders[month][0].rate

    def effective_rate(self, month: int, shape24) -> float:
        """Tier-1 $/kWh for a device with this 24-h shape (peak-weighted, no tiers)."""
        pf = self.period_fractions(month, shape24)["peak"]
        rp, ro = self.tier1_rates(month)
        return pf * rp + (1.0 - pf) * ro

    def fixed_charge(self, days: int) -> float:
        if not self.fixed_amount:
            return 0.0
        return self.fixed_amount * (days if self.fixed_unit == "$/day" else 1.0)

    def price_month(self, month: int, peak_kwh: float, offpeak_kwh: float, days: int,
                    escalation: float = 1.0) -> float:
        """Monthly energy + fixed charge ($) for the home's grid import in this month."""
        peak_kwh, offpeak_kwh = max(peak_kwh, 0.0), max(offpeak_kwh, 0.0)
        total = peak_kwh + offpeak_kwh
        share = peak_kwh / total if total > 0 else 0.0
        pk, op = self.peak_ladders[month], self.offpeak_ladders[month]
        cost, prev = 0.0, 0.0
        for i, tier in enumerate(pk):
            bound = total if tier.max_kwh_day is None else min(total, tier.max_kwh_day * days)
            kwh = max(bound - prev, 0.0)
            off_rate = op[min(i, len(op) - 1)].rate
            cost += kwh * (share * tier.rate + (1.0 - share) * off_rate)
            prev = max(prev, bound)
            if prev >= total:
                break
        return (cost + self.fixed_charge(days)) * escalation


class URDBRates:
    """Coverage gate + tariff builder over the committed URDB files. Load once per process."""

    def __init__(self):
        self._db = json.loads(_TOU_FILE.read_text(encoding="utf-8"))["utilities"]
        cov = json.loads(_COVERAGE_FILE.read_text(encoding="utf-8"))
        self._maintained = set(cov["utilities"])
        self._crosswalk = json.loads(_CROSSWALK_FILE.read_text(encoding="utf-8"))["utilities"]
        zz = json.loads(_ZIP_ZONE_FILE.read_text(encoding="utf-8"))
        self._zip_zone = {k: v for k, v in zz.items() if not k.startswith("_")}

    # ── coverage ──────────────────────────────────────────────────────────────
    def decision(self, eiaid) -> str:
        """'urdb' | 'quarantined' | 'harvest_candidate' | 'eia_fallback'."""
        if eiaid is None:
            return "eia_fallback"
        e = str(eiaid)
        if e not in self._maintained:
            return "eia_fallback"
        if e not in self._db:
            return "harvest_candidate"
        return "quarantined" if e in QUARANTINE else "urdb"

    def fallback_reason(self, eiaid) -> str:
        d = self.decision(eiaid)
        return {
            "urdb": "",
            "quarantined": QUARANTINE.get(str(eiaid), ""),
            "harvest_candidate": "URDB maintains this utility but its tariffs are not harvested yet.",
            "eia_fallback": "No annually-maintained URDB tariff for this utility.",
        }[d]

    def tariff_options(self, eiaid) -> list[dict]:
        """Harvested tariffs for the picker, default first."""
        u = self._db.get(str(eiaid))
        if not u:
            return []
        opts = [{"label": lab, "family": t["family"], "plan_kind": t["plan_kind"],
                 "is_tou": t["is_tou"], "is_default": lab == u["default_label"],
                 "closed": t.get("closed_to_enrollment", False)}
                for lab, t in u["tariffs"].items()]
        return sorted(opts, key=lambda o: (not o["is_default"], o["plan_kind"], o["family"]))

    # ── build ─────────────────────────────────────────────────────────────────
    def resolve(self, zip_code: str, eiaid, tariff_label: str | None = None) -> RateStructure | None:
        """RateStructure for the home's utility and tariff, or None → keep the EIA path."""
        if self.decision(eiaid) != "urdb":
            return None
        e = str(eiaid)
        u = self._db[e]
        label = tariff_label if tariff_label in u["tariffs"] else u["default_label"]
        t = u["tariffs"][label]
        region, conf, scale = self._baseline_scale(e, t, str(zip_code).strip())
        peak, off = [], []
        for m, bm in enumerate(t["by_month"]):
            peak.append(tuple(self._tier(x, scale[m]) for x in bm["peak"]))
            off.append(tuple(self._tier(x, scale[m]) for x in bm["offpeak"]))
        fc = t.get("fixed_charge") or {}
        return RateStructure(
            eiaid=e, utility=u["utility"], label=label, name=t["name"], family=t["family"],
            plan_kind=t["plan_kind"], is_tou=bool(t["is_tou"]),
            peak_hours=tuple(t["peak_hours"]) if t["is_tou"] else (),
            peak_ladders=tuple(peak), offpeak_ladders=tuple(off),
            fixed_amount=float(fc.get("value") or 0.0), fixed_unit=fc.get("unit") or "$/day",
            baseline_region=region, baseline_confidence=conf,
            closed_to_enrollment=bool(t.get("closed_to_enrollment", False)),
        )

    @staticmethod
    def _tier(x: dict, scale: float) -> Tier:
        mx = x.get("max_kwh_day")
        return Tier(None if mx is None else mx * scale, float(x["rate"]))

    def _baseline_scale(self, eiaid: str, t: dict, zip_code: str):
        """(region, confidence, 12 per-month threshold multipliers).

        The harvested record carries one territory's thresholds (``baseline_region``). Scale
        every finite tier threshold by (home territory baseline / record baseline) for the
        matching season, so tier 1 = the home's allowance and higher tiers keep their ratio.
        """
        rb = t.get("region_baselines") or {}
        rec_region = t.get("baseline_region")
        if not rb or rec_region not in rb:
            return None, "not_applicable", [1.0] * 12
        cw = self._crosswalk.get(eiaid, {})
        zone = self._zip_zone.get(zip_code)
        zi = int(zone.replace("CA_CZ", "")) if zone and zone.startswith("CA_CZ") else None
        region = cw.get("cec_zone_to_region", {}).get(str(zi)) if zi is not None else None
        conf = cw.get("confidence", "approximate")
        if region not in rb:
            region, conf = cw.get("representative_region") or rec_region, "fallback"
        rec, home = rb[rec_region], rb[region]
        scale = []
        for bm in t["by_month"]:
            t1 = bm["peak"][0].get("max_kwh_day")
            if t1 is None:
                scale.append(1.0)
                continue
            summer = abs(t1 - rec["summer_kwh_day"]) <= abs(t1 - rec["winter_kwh_day"])
            key = "summer_kwh_day" if summer else "winter_kwh_day"
            scale.append(home[key] / rec[key] if rec[key] else 1.0)
        return region, conf, scale


_RATES: URDBRates | None = None


def get_urdb() -> URDBRates:
    """Process-wide instance (lazy)."""
    global _RATES
    if _RATES is None:
        _RATES = URDBRates()
    return _RATES


def peak_hours_label(hours: Sequence[int]) -> str:
    """(16,17,18,19,20) → "4–9pm"."""
    if not hours:
        return "no peak window"
    fmt = lambda h: f"{(h % 12) or 12}{'am' if h % 24 < 12 else 'pm'}"   # noqa: E731
    return f"{fmt(min(hours))}–{fmt(max(hours) + 1)}"
