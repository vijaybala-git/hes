#!/usr/bin/env python3
"""build_eia_rates.py — assemble WhyWatt per-utility rate data from authoritative EIA sources.

Phase 4 §2 (EIA-Based Rate Modeling). Resolves a state's residential electricity and
natural-gas rates at the *utility* level (not just a statewide blend), so a PG&E home is
priced off PG&E's own effective rate rather than a CA average diluted by cheap munis.

Sources (snapshotted with sha256 under data/rates/sources/ for reproducibility):
  • Electricity, per-utility : EIA-861M  sales_ult_cust_<year>.xlsx  (revenue ÷ sales)
  • Electricity, state blend : EIA-861M  sales_revenue.xlsx (Monthly-States) — also the
                               10-yr historical CAGR
  • Natural gas, per-LDC     : EIA-176 via the NGQS JSON API (revenue ÷ volume), report
                               RPC items 1010VL/1010CS; company names from report RP6

Effective-rate method: total residential revenue ÷ total residential sales. This folds in
fixed monthly service charges that a commodity tariff rate alone misses — it is "what
households actually pay."

Monthly seasonal shape: FLAT in v1 (see S2.0 spike). The raw revenue÷sales monthly ratio
embeds tiered-pricing/true-up artifacts; multiplying it onto the model's already-seasonal
consumption would double-count. Seasonal variation therefore comes from consumption, and the
rate is constant across months. Per-LDC gas shaping from EIA NG-Monthly is a future option.

USAGE (run from project root):
    python scripts/build_eia_rates.py --states CA      # default state is CA
    python scripts/build_eia_rates.py --check          # parse cached snapshots, no download

OUTPUT:
    data/rates/eia_rates_by_utility.json               # the rate database (committed)
    data/rates/sources/                                # raw snapshots + provenance.json
    docs/help/_generated/rate_tables.md                # help fragment for the reference page
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import ssl
import sys
import urllib.request
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
RATES = ROOT / "data" / "rates"
SOURCES = RATES / "sources"
OUT_JSON = RATES / "eia_rates_by_utility.json"
DOC_FRAGMENT = ROOT / "docs" / "help" / "_generated" / "rate_tables.md"

BASE_YEAR = 2024
MCF_TO_THERM = 10.37   # 1 Mcf natural gas ≈ 10.37 therms (HHV ~1037 Btu/cf)

# ── Source URLs ────────────────────────────────────────────────────────────────
ELEC_UTIL_URL = ("https://www.eia.gov/electricity/data/eia861m/archive/xls/"
                 f"sales_ult_cust_{BASE_YEAR}.xlsx")
ELEC_STATE_URL = "https://www.eia.gov/electricity/data/eia861m/xls/sales_revenue.xlsx"
NGQS = "https://www.eia.gov/naturalgas/ngqs/data/report"

# ── Per-state utility selections (EIA ids). Extend to add states. ───────────────
# Electric utility numbers (EIA-861) and gas LDC ids (EIA-176, with state suffix).
STATE_UTILITIES: dict[str, dict] = {
    "CA": {
        "label": "California",
        "electric": {  # EIA-861 utility number -> friendly name
            14328: "Pacific Gas & Electric",
            17609: "Southern California Edison",
            16609: "San Diego Gas & Electric",
        },
        "gas": {  # EIA-176 company id (with CA suffix) -> friendly name
            "17610617CA": "Pacific Gas & Electric",
            "17621931CA": "Southern California Gas",
            "17611927CA": "San Diego Gas & Electric",
        },
        "cagr_years": (2014, 2024),
    },
}

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


# ── Download + snapshot ─────────────────────────────────────────────────────────
def _get(url: str, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=timeout, context=_CTX).read()


def _snapshot(name: str, data: bytes, url: str, provenance: dict) -> Path:
    """Write raw bytes under sources/, record sha256 + url in provenance."""
    SOURCES.mkdir(parents=True, exist_ok=True)
    path = SOURCES / name
    path.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    provenance[name] = {"url": url, "sha256": sha, "bytes": len(data),
                        "downloaded": str(date.today())}
    print(f"  snapshot {name}: {len(data):,} bytes  sha {sha[:12]}…")
    return path


# ── CAGR fit (log-linear over annual points) ────────────────────────────────────
def _fit_cagr(years: list[int], values: list[float]) -> float:
    yrs = np.asarray(years, dtype=float)
    vals = np.asarray(values, dtype=float)
    mask = vals > 0
    if mask.sum() < 2:
        return 0.0
    slope = np.polyfit(yrs[mask], np.log(vals[mask]), 1)[0]
    return float(np.exp(slope) - 1.0)


# ── Electricity (EIA-861M) ──────────────────────────────────────────────────────
def _monthly_observed(sub: pd.DataFrame, rev_c, sales_c) -> list:
    """12 observed monthly effective rates (rev_m ÷ sales_m), Jan..Dec; None where missing.

    Retained for transparency/inspection only — NOT applied in the simulation (the model
    uses a flat monthly_seasonal_shape; this raw shape embeds tier/true-up artifacts that
    would double-count the model's already-seasonal consumption — see S2.0 spike)."""
    s = sub.copy()
    s["_rev"] = pd.to_numeric(s[rev_c], errors="coerce")
    s["_sales"] = pd.to_numeric(s[sales_c], errors="coerce")
    bm = s.groupby("Month")[["_rev", "_sales"]].sum()
    out = []
    for mo in range(1, 13):
        if mo in bm.index and bm.loc[mo, "_sales"]:
            out.append(round(float(bm.loc[mo, "_rev"] / bm.loc[mo, "_sales"]), 4))
        else:
            out.append(None)
    return out


def _normalized_shape(monthly: list | None) -> list | None:
    """Normalize observed monthly rates to mean 1.0 (the seasonal shape), or None."""
    if not monthly:
        return None
    vals = [m for m in monthly if m]
    if not vals:
        return None
    mean = sum(vals) / len(vals)
    return [round(m / mean, 4) if m else None for m in monthly]


def _build_electric(state: str, sel: dict, provenance: dict, check: bool) -> tuple[dict, dict]:
    """Return (per_utility_dict, state_average_dict) for electricity, $/kWh."""
    # Per-utility file (one base year)
    util_name = f"eia861m_sales_ult_cust_{BASE_YEAR}.xlsx"
    state_name = "eia861m_sales_revenue.xlsx"
    if not check:
        _snapshot(util_name, _get(ELEC_UTIL_URL), ELEC_UTIL_URL, provenance)
        _snapshot(state_name, _get(ELEC_STATE_URL), ELEC_STATE_URL, provenance)

    udf = pd.read_excel(SOURCES / util_name,
                        sheet_name="Sales Ultimate Cust. -States", header=2)
    # Residential block: Revenue (k$) idx 7, Sales (MWh) idx 8
    rev_c, sales_c = udf.columns[7], udf.columns[8]
    per_util: dict[str, dict] = {}
    for num, name in sel["electric"].items():
        sub = udf[udf["Utility Number"] == num]
        rev = pd.to_numeric(sub[rev_c], errors="coerce").sum()       # thousand $
        sales = pd.to_numeric(sub[sales_c], errors="coerce").sum()   # MWh
        # $/kWh = (rev*1000 $) / (sales*1000 kWh) = rev / sales
        rate = float(rev / sales) if sales else 0.0
        per_util[str(num)] = {"name": name, "rate": round(rate, 4),
                              "monthly": _monthly_observed(sub, rev_c, sales_c)}

    # State-average blend + 10-yr CAGR from the aggregate Monthly-States sheet
    sdf = pd.read_excel(SOURCES / state_name, sheet_name="Monthly-States", header=2)
    sdf.columns = [str(c).strip() for c in sdf.columns]
    res_rev, res_sales = sdf.columns[4], sdf.columns[5]  # Residential Revenue(k$), Sales(MWh)
    ca = sdf[sdf["State"] == state].copy()
    ca["_rev"] = pd.to_numeric(ca[res_rev], errors="coerce")
    ca["_sales"] = pd.to_numeric(ca[res_sales], errors="coerce")
    by_year = ca.groupby("Year").agg(rev=("_rev", "sum"), sales=("_sales", "sum"))
    by_year["price"] = by_year["rev"] / by_year["sales"]
    base_price = float(by_year.loc[BASE_YEAR, "price"])
    lo, hi = sel["cagr_years"]
    yrs = [int(y) for y in by_year.index if lo <= int(y) <= hi]
    cagr = _fit_cagr(yrs, [float(by_year.loc[y, "price"]) for y in yrs])

    # Attach the state CAGR as each utility's default escalation (per-utility CAGR = future)
    for u in per_util.values():
        u["cagr"] = round(cagr, 4)

    ca_base = ca[ca["Year"] == BASE_YEAR]
    state_avg = {"rate": round(base_price, 4), "cagr": round(cagr, 4),
                 "monthly": _monthly_observed(ca_base, res_rev, res_sales)}
    print(f"  electric {state}: blend {base_price:.4f} $/kWh, 10yr CAGR {cagr*100:.1f}%")
    return per_util, state_avg


# ── Natural gas (EIA-176 via NGQS) ──────────────────────────────────────────────
def _ngqs_rpc(year1: int, year2: int) -> list[dict]:
    url = f"{NGQS}/RPC/data/{year1}/{year2}/ACI/all/1010VL/1010CS"
    return json.loads(_get(url))["data"]


def _build_gas(state: str, sel: dict, provenance: dict, check: bool) -> tuple[dict, dict]:
    """Return (per_ldc_dict, state_average_dict) for gas, $/therm."""
    state_full = sel["label"]
    lo, hi = sel["cagr_years"]
    rpc_name = f"eia176_ngqs_rpc_{lo}_{hi}.json"
    if not check:
        raw = _get(f"{NGQS}/RPC/data/{lo}/{hi}/ACI/all/1010VL/1010CS")
        _snapshot(rpc_name, raw, f"{NGQS}/RPC/data/{lo}/{hi}/ACI/all/1010VL/1010CS", provenance)
    rows = json.loads((SOURCES / rpc_name).read_text())["data"]

    yr_key = lambda y: f"y{y}"

    def price_therm(company_id: str, year: int) -> float | None:
        cid = company_id.strip()
        vol = rev = None
        for r in rows:
            if str(r.get("b")).strip() != cid:
                continue
            if str(r.get("a")).strip() != state_full:
                continue
            c = r.get("c")
            v = r.get(yr_key(year))
            if c == "Residential Sales Volume":
                vol = v
            elif c == "Residential Sales Revenue":
                rev = v
        if vol and rev and vol > 0:
            return (rev / vol) / MCF_TO_THERM   # ($/Mcf) → $/therm
        return None

    per_ldc: dict[str, dict] = {}
    for cid, name in sel["gas"].items():
        base = price_therm(cid, BASE_YEAR)
        years = [y for y in range(lo, hi + 1)]
        series = [(y, price_therm(cid, y)) for y in years]
        series = [(y, p) for y, p in series if p]
        cagr = _fit_cagr([y for y, _ in series], [p for _, p in series])
        per_ldc[cid.replace("CA", "")] = {
            "name": name, "rate": round(base, 4) if base else 0.0,
            "cagr": round(cagr, 4)}

    # CA state blend = "Total of All Companies" / California
    base = price_therm(" Total of All Companies", BASE_YEAR)
    tot_series = [(y, price_therm(" Total of All Companies", y)) for y in range(lo, hi + 1)]
    tot_series = [(y, p) for y, p in tot_series if p]
    cagr = _fit_cagr([y for y, _ in tot_series], [p for _, p in tot_series])
    state_avg = {"rate": round(base, 4) if base else 0.0, "cagr": round(cagr, 4)}
    print(f"  gas {state}: blend {base:.4f} $/therm, 10yr CAGR {cagr*100:.1f}%")
    return per_ldc, state_avg


# ── Help fragment ───────────────────────────────────────────────────────────────
def _write_doc_fragment(db: dict):
    """Emit the per-utility rate tables as a 4-space-indented help fragment.

    Included by docs/help/help_content.md via `@include:`; regenerated on every build so the
    rate reference page can never drift from data/rates/eia_rates_by_utility.json.
    """
    L = [f"    Generated from data/rates/eia_rates_by_utility.json by scripts/build_eia_rates.py "
         f"— do not edit by hand.",
         f"    Source: EIA-861M (electricity) · EIA-176/NGQS (gas) · base year {BASE_YEAR} "
         f"· built {date.today()}",
         "    " + "-" * 60]
    ca = db["state_average"]["CA"]
    # Electricity
    L += ["    ELECTRICITY — residential effective rate ($/kWh)",
          f"    {'Utility':30} {'$/kWh':>7} {'vs blend':>9}"]
    blend_e = ca["electricity"]["current_rate"]
    for rec in db["electric_utilities"].values():
        d = (rec["current_rate"] / blend_e - 1.0) * 100
        L.append(f"    {rec['name']:30} {rec['current_rate']:7.3f} {d:+8.0f}%")
    L.append(f"    {'California average (fallback)':30} {blend_e:7.3f} {'—':>9}")
    # Gas
    L += ["",
          "    NATURAL GAS — residential effective rate ($/therm)",
          f"    {'Utility':30} {'$/therm':>7} {'vs blend':>9}"]
    blend_g = ca["gas"]["current_rate"]
    for rec in db["gas_ldcs"].values():
        d = (rec["current_rate"] / blend_g - 1.0) * 100
        L.append(f"    {rec['name']:30} {rec['current_rate']:7.3f} {d:+8.0f}%")
    L.append(f"    {'California average (fallback)':30} {blend_g:7.3f} {'—':>9}")
    DOC_FRAGMENT.parent.mkdir(parents=True, exist_ok=True)
    DOC_FRAGMENT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"  wrote {DOC_FRAGMENT.relative_to(ROOT)}")


# ── Assemble ────────────────────────────────────────────────────────────────────
FLAT_SHAPE = [1.0] * 12


def _elec_record(name: str, state: str, u: dict) -> dict:
    monthly = u.get("monthly")
    return {"name": name, "state": state, "unit": "$/kWh", "base_year": BASE_YEAR,
            "current_rate": u["rate"], "historical_cagr_10yr": u["cagr"],
            # APPLIED in the simulation:
            "monthly_seasonal_shape": FLAT_SHAPE, "shape_method": "flat",
            # RETAINED for reference, NOT applied (EIA-861M actual monthly rates):
            "monthly_rate_observed": monthly,
            "monthly_shape_observed": _normalized_shape(monthly),
            "source": f"EIA-861M {BASE_YEAR} (revenue ÷ sales)"}


def _gas_record(name: str, state: str, u: dict) -> dict:
    return {"name": name, "state": state, "unit": "$/therm", "base_year": BASE_YEAR,
            "current_rate": u["rate"], "historical_cagr_10yr": u["cagr"],
            "monthly_seasonal_shape": FLAT_SHAPE, "shape_method": "flat",
            # EIA-176 is annual only — no per-LDC monthly rates to retain.
            "monthly_rate_observed": None, "monthly_shape_observed": None,
            "source": f"EIA-176/NGQS {BASE_YEAR} (revenue ÷ volume)"}


def build(states: list[str], check: bool):
    provenance: dict = {}
    db = {"electric_utilities": {}, "gas_ldcs": {}, "state_average": {}}
    for state in states:
        sel = STATE_UTILITIES.get(state)
        if sel is None:
            print(f"  WARN: no utility selection for {state!r}; skipping", file=sys.stderr)
            continue
        print(f"[{state}]")
        e_util, e_avg = _build_electric(state, sel, provenance, check)
        g_ldc, g_avg = _build_gas(state, sel, provenance, check)
        for num, u in e_util.items():
            db["electric_utilities"][num] = _elec_record(u["name"], state, u)
        for cid, u in g_ldc.items():
            db["gas_ldcs"][cid] = _gas_record(u["name"], state, u)
        db["state_average"][state] = {
            "label": sel["label"],
            "electricity": {"unit": "$/kWh", "base_year": BASE_YEAR,
                            "current_rate": e_avg["rate"],
                            "historical_cagr_10yr": e_avg["cagr"],
                            "monthly_seasonal_shape": FLAT_SHAPE, "shape_method": "flat",
                            "monthly_rate_observed": e_avg.get("monthly"),
                            "monthly_shape_observed": _normalized_shape(e_avg.get("monthly")),
                            "source": f"EIA-861M {BASE_YEAR} state aggregate"},
            "gas": {"unit": "$/therm", "base_year": BASE_YEAR,
                    "current_rate": g_avg["rate"], "historical_cagr_10yr": g_avg["cagr"],
                    "monthly_seasonal_shape": FLAT_SHAPE, "shape_method": "flat",
                    "monthly_rate_observed": None, "monthly_shape_observed": None,
                    "source": f"EIA-176/NGQS {BASE_YEAR} state total"},
        }

    db["_meta"] = {
        "schema_version": 1,
        "base_year": BASE_YEAR,
        "built": str(date.today()),
        "shape_method": "flat — seasonal variation comes from consumption; per-LDC gas "
                        "shaping from EIA NG-Monthly is a deferred enhancement (S2.0 spike)",
        "monthly_rate_observed_note": "Electric records also carry the actual EIA-861M "
                        "monthly rates (monthly_rate_observed) and their normalized shape "
                        "(monthly_shape_observed), RETAINED for reference but NOT applied — "
                        "applying them onto already-seasonal consumption would double-count "
                        "tier/true-up effects. Gas (EIA-176) is annual-only: null.",
        "effective_rate_method": "residential revenue ÷ residential sales (elec) / volume (gas)",
        "mcf_to_therm": MCF_TO_THERM,
        "sources": provenance,
        "note": "Keys '_meta' aside: electric_utilities keyed by EIA-861 utility number; "
                "gas_ldcs by EIA-176 company id; state_average is the ZIP-unresolved fallback.",
    }

    if not check:
        OUT_JSON.write_text(json.dumps(db, indent=2), encoding="utf-8")
        print(f"\nWrote {OUT_JSON.relative_to(ROOT)}")
        # provenance sidecar
        (SOURCES / "provenance.json").write_text(json.dumps(provenance, indent=2))
    _write_doc_fragment(db)
    return db


def main():
    ap = argparse.ArgumentParser(description="Build EIA per-utility rate database.")
    ap.add_argument("--states", nargs="+", default=["CA"], help="state codes (default: CA)")
    ap.add_argument("--check", action="store_true",
                    help="parse cached snapshots only; no download, no JSON write")
    args = ap.parse_args()
    build([s.upper() for s in args.states], check=args.check)


if __name__ == "__main__":
    main()
