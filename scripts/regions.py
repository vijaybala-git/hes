#!/usr/bin/env python3
"""regions.py — the region / utility / flagship-tariff table that drives the offline URDB harvest.

Adding a state or utility is a DATA edit here — `build_urdb.py`, the schema, the loader, and the
tests are all parameterized off this table (see docs/OfflineURDB_Plan.md §1.3, §4).

Two things live here:
  1. FAMILY_PATTERNS — how a raw URDB tariff *name* maps to a WhyWatt `plan_kind` + flagship family.
     URDB has hundreds of records per IOU (historical + per-baseline-region + closed variants);
     these patterns pick out the small set of current, recognizable residential plans (§4.2a).
  2. REGIONS / UTILITIES — which EIA ids to harvest, and which family is each utility's TOU default.

CA-first, but nothing here is CA-only: a new state is another `Utility(...)` row.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Flagship family classification ───────────────────────────────────────────────
# (plan_kind, family_key, name-regex). ORDER MATTERS — first match wins, so the more
# specific EV2 pattern precedes the generic EV one. plan_kind ∈ {tou, tiered_legacy, ev_tou}.
FAMILY_PATTERNS: list[tuple[str, str, str]] = [
    # PG&E (14328)
    ("ev_tou",        "EV2",         r"^Electric Vehicle EV2|^EV2"),
    ("ev_tou",        "EV",          r"^Electric Vehicle EV\b|^EV(?![0-9-])"),
    ("tou",           "E-TOU-C",     r"^E-TOU-C"),
    ("tou",           "E-TOU-D",     r"^E-TOU-D"),
    ("tou",           "E-ELEC",      r"^E-ELEC"),
    ("tiered_legacy", "E-1",         r"^E-1\b"),
    # SCE (17609)
    ("ev_tou",        "TOU-D-TEV",   r"TOU-D-TEV|Electric Vehicle Charging"),
    ("tou",           "TOU-D-PRIME", r"TOU-D-PRIME"),
    ("tou",           "TOU-D-4-9PM", r"TOU-D-4-9PM"),
    ("tou",           "TOU-D-5-8PM", r"TOU-D-5-8PM"),
    ("tou",           "TOU-D-A",     r"TOU-D-A\b"),
    ("tiered_legacy", "SCE-D",       r"^Domestic Service"),
    # SDG&E (16609) — put -1/-2 before the base TOU-DR (first match wins), EV before DR
    ("ev_tou",        "EV-TOU-5",    r"EV-TOU-5"),
    ("ev_tou",        "EV-TOU-2",    r"EV-TOU-2"),
    ("ev_tou",        "EV-TOU",      r"^EV-TOU\b"),
    ("tou",           "TOU-ELEC",    r"TOU-ELEC"),
    ("tou",           "TOU-DR-1",    r"TOU-DR-1"),
    ("tou",           "TOU-DR-2",    r"TOU-DR-2"),
    ("tou",           "TOU-DR",      r"^TOU-DR\b"),
    ("tiered_legacy", "SDGE-DR",     r"^DR\b"),
]

# region after ("Baseline Region X/5") OR before ("Coastal Baseline Region")
_BASELINE_AFTER = re.compile(r"Baseline Region (\w+)")
_BASELINE_BEFORE = re.compile(r"(\w+) Baseline Region")
_CLOSED_RE = re.compile(r"closed", re.IGNORECASE)
# Out of scope for now (§4.2a): income-qualified, medical, critical-peak overlays, solar/NEM variants.
_EXCLUDE_RE = re.compile(
    r"\b(CARE|FERA|Medical|Life ?line|CPP|DR-LI|-LI\b|SES|NEM)\b", re.IGNORECASE)


def classify(name: str) -> tuple[str | None, str | None]:
    """(plan_kind, family_key) for a URDB tariff name, or (None, None) if not a flagship plan."""
    if _EXCLUDE_RE.search(name or ""):
        return None, None
    for plan_kind, family, pat in FAMILY_PATTERNS:
        if re.search(pat, name or ""):
            return plan_kind, family
    return None, None


def baseline_region(name: str) -> str | None:
    """PG&E 'Baseline Region X', SCE 'Baseline Region 5', SDG&E 'Coastal Baseline Region'."""
    m = _BASELINE_AFTER.search(name or "")
    if m:
        return m.group(1)
    m = _BASELINE_BEFORE.search(name or "")
    return m.group(1) if m else None


def is_all_electric(name: str) -> bool:
    return "All Elect" in (name or "")


def is_closed(name: str) -> bool:
    return bool(_CLOSED_RE.search(name or ""))


# ── Utility / region table ───────────────────────────────────────────────────────
@dataclass(frozen=True)
class Utility:
    eiaid: int
    name: str
    default_family: str                 # which flagship family is the whywatt_default (a TOU plan)
    representative_region: str | None = None  # baseline region to pick as the family representative


@dataclass(frozen=True)
class Region:
    key: str
    state: str
    utilities: list[Utility] = field(default_factory=list)


REGIONS: dict[str, Region] = {
    "ca_pge": Region("ca_pge", "CA", [
        Utility(eiaid=14328, name="Pacific Gas & Electric",
                default_family="E-TOU-C", representative_region="X"),
    ]),
    "ca_sce": Region("ca_sce", "CA", [
        Utility(eiaid=17609, name="Southern California Edison",
                default_family="TOU-D-4-9PM", representative_region=None),
    ]),
    "ca_sdge": Region("ca_sdge", "CA", [
        Utility(eiaid=16609, name="San Diego Gas & Electric",
                default_family="TOU-DR-1", representative_region="Coastal"),
    ]),
}


def utilities_for_state(state: str) -> list[Utility]:
    seen, out = set(), []
    for reg in REGIONS.values():
        if reg.state != state:
            continue
        for u in reg.utilities:
            if u.eiaid not in seen:
                seen.add(u.eiaid)
                out.append(u)
    return out


def utility_by_eiaid(eiaid: int) -> Utility | None:
    for reg in REGIONS.values():
        for u in reg.utilities:
            if u.eiaid == eiaid:
                return u
    return None
