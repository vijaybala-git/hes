"""
ProjectedRateModel — the offline retail-rate projection (methodology §3, §5).

Retail is reconstructed ADDITIVELY (methodology §3.1): v = mc + r.
  mc(y)  — marginal BILL cost, empirical from the ACC harvest (bill_mc path). ~flat for electricity.
  r̄(y)   — residual (the majority of the bill). Base = the PLUG r̄(0) = v_retail(0) − mc(0).

TWO residual drivers, one per fuel (docs/OfflineRateProjection_Plan.md §2.1 + the CEC-driven update):

  ELECTRICITY — driven directly by the CEC 2025 IEPR per-year PG&E residential rate
    (data/rates/projection/cec_electric_rate.json, workbook tn=260210, 2024→2050). The `moderate`
    scenario reproduces the CEC trajectory exactly, rebased to WhyWatt's base rate:
        retail_elec_moderate(y) = BASE_RETAIL[elec] · CEC_rate(y)/CEC_rate(0)
        residual_moderate(y)    = retail_moderate(y) − mc(y)
    conservative / stress scale that residual by a small annual deviation (a band around CEC).
    This automatically inherits CEC's real-flat shape AND its features (e.g. the 2026 step-down as
    the Wildfire Mitigation revenue-requirement bucket winds down). The CEC's own revenue-requirement
    buckets (sheet 4) are exposed via rr_index()/sales_index() for the "why flat" decomposition.

  GAS — ALSO CEC-driven, from the 2025 IEPR gas rate workbook (cec_gas_rate.json, tn=264063). Each
    WhyWatt scenario maps to a CEC "Planning Area Demand × RR-recovery" case (advocate choice, 2026-08-26):
      conservative → Pruning RR (curtail gas investment — managed decline)
      moderate     → Front Load RR (accelerated cost recovery)
      stress       → Flat RR (business-as-usual investment → death spiral)
    Retail follows the CEC delivered-price shape rebased to WhyWatt's base; the residual is implied.
    The CEC scenario's own Revenue Requirement and Demand columns feed rr_index()/sales_index() —
    so the gas death spiral (RR ÷ FALLING demand) is real CEC data, not a preset.
    NOTE the tn=264063 delivered price is published in REAL 2024$ (its 'Commodity Prices' sheet is
    headed "2024$/Therm"); _cec_gas_index() inflates it to nominal with the GDP deflator before
    indexing, so gas shares the same NOMINAL internal footing as electricity and mc.

BASIS — everything is computed in NOMINAL $ (mc and the retail anchors are nominal), because the
additive v = mc + r reconstruction needs one consistent basis. The CANONICAL REPORTING basis is
REAL 2024$: callers wrap retail()/decompose() in to_real(series, base_year=2024). The CEC anchors
(electric tn=268239, gas tn=264063) are themselves real 2024$, so the real-reported curves track
them directly. to_nominal() is the inverse, for an explicit nominal view.
Imported by NO live sim code — analysis only.
"""

from __future__ import annotations

import json
from pathlib import Path

from .escalation import segmented_path

# Base-year retail anchors (URDB/tariff level, methodology §3.2). PG&E 2025, per CLAUDE.md.
# NOTE: elec base is the E-1 schedule ($0.386); the CEC blended residential average is ~$0.408.
# The electricity path follows the CEC *growth shape* rebased to this base (a ~6% level offset).
BASE_YEAR = 2025
BASE_RETAIL = {"elec": 0.386, "gas": 2.08}     # $/kWh, $/therm (nominal)

# Scenarios. Electricity: a residual deviation around the CEC-driven central path (moderate = CEC
# exactly). Gas: each maps to a CEC "Planning Area Demand" case on the RR-recovery axis.
SCENARIO_PRESETS = {
    "conservative": {"elec_residual_dev": -0.010,
                     "gas_scenario": "Planning Area Demand Pruning RR"},
    "moderate":     {"elec_residual_dev":  0.000,
                     "gas_scenario": "Planning Area Demand Front Load RR"},
    "stress":       {"elec_residual_dev": +0.015,
                     "gas_scenario": "Planning Area Demand Flat RR"},
}

_MC_FILE = {"elec": "acc_marginal_electric.json", "gas": "acc_marginal_gas.json"}
_MC_KEY  = {"elec": "bill_mc_kwh", "gas": "bill_mc_therm"}
_SOCIAL_KEY = {"elec": "social_mc_kwh"}
_CEC_TOTAL_RR = "Total UDC Area Revenue Requirement"


class ProjectedRateModel:
    def __init__(self, data_dir="data/rates/projection", base_year=BASE_YEAR, horizon_end=2050):
        self.dir = Path(data_dir)
        self.base_year = base_year
        self.years = list(range(base_year, horizon_end + 1))
        self._mc = {}
        self._social = {}
        self._deflator = {}
        self._cec_rate = {}     # elec $/kWh nominal, per year
        self._cec_rr = {}        # elec total revenue requirement ($B), per year
        self._cec_gas = {}       # gas scenarios (delivered/demand/RR), per year
        self._load()

    # ── loading ──────────────────────────────────────────────────────────────
    def _load(self):
        for fuel, fname in _MC_FILE.items():
            d = json.loads((self.dir / fname).read_text())
            self._mc[fuel] = {int(y): float(v) for y, v in d[_MC_KEY[fuel]].items()}
            if fuel in _SOCIAL_KEY and _SOCIAL_KEY[fuel] in d:
                self._social[fuel] = {int(y): float(v) for y, v in d[_SOCIAL_KEY[fuel]].items()}
        self._deflator = {int(y): float(v) for y, v in
                          json.loads((self.dir / "gdp_deflator.json").read_text())["deflator"].items()}
        cec = json.loads((self.dir / "cec_electric_rate.json").read_text())
        self._cec_rate = {int(y): float(v) for y, v in cec["pge_residential_nominal"].items()}
        rr = cec["pge_rr_buckets_billions"].get(_CEC_TOTAL_RR, {})
        self._cec_rr = {int(y): float(v) for y, v in rr.items() if v is not None}
        self._cec_gas = json.loads((self.dir / "cec_gas_rate.json").read_text())["scenarios"]

    def _gas_scn(self, scenario, field):
        """A CEC gas scenario field ({year:val}) as ints, extended flat past the data."""
        sc = SCENARIO_PRESETS[scenario]["gas_scenario"]
        d = {int(y): float(v) for y, v in self._cec_gas[sc][field].items() if v is not None}
        last = max(d)
        return {y: d.get(y, d[last]) for y in self.years}

    # ── marginal ──────────────────────────────────────────────────────────────
    def mc(self, fuel: str) -> dict:
        src = self._mc[fuel]
        last = max(src)
        return {y: src.get(y, src[last]) for y in self.years}

    def residual_base(self, fuel: str) -> float:
        return BASE_RETAIL[fuel] - self._mc[fuel][self.base_year]

    # ── CEC-driven electricity index ──────────────────────────────────────────
    def _cec_rate_index(self) -> dict:
        """CEC PG&E residential rate as an index (base year = 1.0), extended flat past the data."""
        last = max(self._cec_rate)
        b = self._cec_rate[self.base_year]
        return {y: self._cec_rate.get(y, self._cec_rate[last]) / b for y in self.years}

    # ── residual ──────────────────────────────────────────────────────────────
    def rr_index(self, fuel: str, scenario: str) -> dict:
        """Revenue-requirement index (base=1.0), from the CEC data for both fuels."""
        if fuel == "elec":
            if not self._cec_rr:
                return {y: 1.0 for y in self.years}
            last = max(self._cec_rr)
            b = self._cec_rr[self.base_year]
            return {y: self._cec_rr.get(y, self._cec_rr[last]) / b for y in self.years}
        rr = self._gas_scn(scenario, "revenue_requirement")
        b = rr[self.base_year]
        return {y: rr[y] / b for y in self.years}

    def sales_index(self, fuel: str, scenario: str) -> dict:
        """Sales/throughput index (base=1.0), from the CEC data. Elec rises; gas falls."""
        if fuel == "elec":
            rr, rate = self.rr_index("elec", scenario), self._cec_rate_index()
            return {y: rr[y] / rate[y] for y in self.years}   # rate = RR/Sales → Sales = RR/rate
        dem = self._gas_scn(scenario, "demand")
        b = dem[self.base_year]
        return {y: dem[y] / b for y in self.years}

    def _cec_gas_index(self, scenario: str) -> dict:
        """CEC gas delivered price as a NOMINAL index (base year = 1.0).

        tn=264063 delivered price is REAL 2024$, so inflate to nominal with the GDP
        deflator (base 2024) before indexing — this keeps gas on the same nominal
        internal basis as electricity and mc. to_real() reports it back in real 2024$.
        """
        deliv = self._gas_scn(scenario, "delivered")            # real 2024$
        d24 = self._deflator[2024]
        nominal = {y: deliv[y] * self._deflator[y] / d24 for y in self.years}
        b = nominal[self.base_year]
        return {y: nominal[y] / b for y in self.years}

    def residual(self, fuel: str, scenario: str) -> dict:
        # Both fuels: central retail follows the CEC rate shape, rebased to WhyWatt's base.
        idx = self._cec_rate_index() if fuel == "elec" else self._cec_gas_index(scenario)
        mc = self.mc(fuel)
        central = {y: BASE_RETAIL[fuel] * idx[y] - mc[y] for y in self.years}
        if fuel == "elec":
            dev = SCENARIO_PRESETS[scenario]["elec_residual_dev"]
            return {y: central[y] * (1.0 + dev) ** (y - self.base_year) for y in self.years}
        return central   # gas scenario already IS the conservative/moderate/stress case

    def retail(self, fuel: str, scenario: str) -> dict:
        mc, r = self.mc(fuel), self.residual(fuel, scenario)
        return {y: round(mc[y] + r[y], 6) for y in self.years}

    def decompose(self, fuel: str, scenario: str) -> dict:
        mc, r = self.mc(fuel), self.residual(fuel, scenario)
        return {y: {"mc": round(mc[y], 6), "residual": round(r[y], 6),
                    "retail": round(mc[y] + r[y], 6)} for y in self.years}

    # ── reporting helpers ────────────────────────────────────────────────────
    def to_real(self, series: dict, base_year: int | None = None) -> dict:
        """Nominal → real: express a nominal series in constant `base_year` dollars."""
        b = base_year or self.base_year
        d0 = self._deflator[b]
        return {y: round(v * d0 / self._deflator[y], 6) for y, v in series.items()
                if y in self._deflator}

    def to_nominal(self, series: dict, base_year: int | None = None) -> dict:
        """Real → nominal: inverse of to_real(), for an explicit nominal view of a real series."""
        b = base_year or self.base_year
        d0 = self._deflator[b]
        return {y: round(v * self._deflator[y] / d0, 6) for y, v in series.items()
                if y in self._deflator}

    def cec_electric_retail(self) -> dict:
        """The raw CEC PG&E residential rate path ($/kWh nominal) — the electricity benchmark itself."""
        last = max(self._cec_rate)
        return {y: self._cec_rate.get(y, self._cec_rate[last]) for y in self.years}

    def social_elec(self) -> dict:
        src = self._social.get("elec", {})
        if not src:
            return {}
        last = max(src)
        return {y: src.get(y, src[last]) for y in self.years}
