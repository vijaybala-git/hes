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

Starting rate (Phase 7 §4.1, the "current energy rate" for projection methods): every record
also carries a `starting_rate` block for STARTING_YEAR, the year the projection curves start
(2025). The legacy fields (`current_rate`, `base_year` = 2024, CAGR) are left exactly as they
were — they drive "My Utility", which stays the golden default through Phase 7.
  • Electricity: EIA-861M sales_ult_cust_<STARTING_YEAR>.xlsx (per utility) and the
    Monthly-States sheet (state blend) — observed.
  • Gas: EIA-176 per-LDC data for STARTING_YEAR is published late in the following year. Until
    it is, each LDC's BASE_YEAR rate is BRIDGED by the state's residential gas price ratio
    (EIA natural-gas price series N3010<ST>3, annual) and flagged `"method": "bridged_state_ratio"`.

USAGE (run from project root):
    python scripts/build_eia_rates.py --states CA      # default state is CA
    python scripts/build_eia_rates.py --check          # parse cached snapshots, no download
    python scripts/build_eia_rates.py --offline        # rebuild the JSON from cached snapshots

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
STARTING_YEAR = 2025   # projection curves start here (whywatt_rate_projection.json base year)
MCF_TO_THERM = 10.37   # 1 Mcf natural gas ≈ 10.37 therms (HHV ~1037 Btu/cf)

# ── Source URLs ────────────────────────────────────────────────────────────────
ELEC_UTIL_URL = ("https://www.eia.gov/electricity/data/eia861m/archive/xls/"
                 f"sales_ult_cust_{BASE_YEAR}.xlsx")
ELEC_STATE_URL = "https://www.eia.gov/electricity/data/eia861m/xls/sales_revenue.xlsx"
ELEC_UTIL_START_URL = ("https://www.eia.gov/electricity/data/eia861m/archive/xls/"
                       f"sales_ult_cust_{STARTING_YEAR}.xlsx")
NGQS = "https://www.eia.gov/naturalgas/ngqs/data/report"
# State residential natural-gas price, annual ($/Mcf) — the gas bridge (see module docstring).
NG_STATE_PRICE_URL = "https://www.eia.gov/dnav/ng/hist/n3010{st}3a.htm"

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


# ── Starting rate (STARTING_YEAR) ───────────────────────────────────────────────
def _elec_starting(state: str, sel: dict, provenance: dict, fetch: bool) -> tuple[dict, dict]:
    """Observed STARTING_YEAR electricity rates: ({utility number: rate}, state blend block)."""
    name = f"eia861m_sales_ult_cust_{STARTING_YEAR}.xlsx"
    if fetch:
        _snapshot(name, _get(ELEC_UTIL_START_URL), ELEC_UTIL_START_URL, provenance)
    udf = pd.read_excel(SOURCES / name, sheet_name="Sales Ultimate Cust. -States", header=2)
    rev_c, sales_c = udf.columns[7], udf.columns[8]
    per_util = {}
    for num in sel["electric"]:
        sub = udf[udf["Utility Number"] == num]
        months = sub["Month"].nunique()
        if months != 12:
            raise SystemExit(f"EIA-861M {STARTING_YEAR}: utility {num} has {months} months")
        rev = pd.to_numeric(sub[rev_c], errors="coerce").sum()
        sales = pd.to_numeric(sub[sales_c], errors="coerce").sum()
        per_util[str(num)] = round(float(rev / sales), 4)

    sdf = pd.read_excel(SOURCES / "eia861m_sales_revenue.xlsx", sheet_name="Monthly-States",
                        header=2)
    sdf.columns = [str(c).strip() for c in sdf.columns]
    st = sdf[(sdf["State"] == state) & (sdf["Year"] == STARTING_YEAR)]
    if st["Month"].nunique() != 12:
        raise SystemExit(f"EIA-861M state sheet: {state} {STARTING_YEAR} is not a full year")
    rev = pd.to_numeric(st[sdf.columns[4]], errors="coerce").sum()
    sales = pd.to_numeric(st[sdf.columns[5]], errors="coerce").sum()
    blend = round(float(rev / sales), 4)
    print(f"  electric {state} {STARTING_YEAR}: blend {blend:.4f} $/kWh; "
          + ", ".join(f"{k} {v:.4f}" for k, v in per_util.items()))
    return per_util, blend


def _ng_state_prices(state: str, provenance: dict, fetch: bool) -> dict[int, float]:
    """{year: $/Mcf} from the EIA state residential gas price page (annual history table)."""
    import re
    name = f"eia_ng_n3010{state.lower()}3_annual.htm"
    url = NG_STATE_PRICE_URL.format(st=state.lower())
    if fetch:
        _snapshot(name, _get(url), url, provenance)
    html = (SOURCES / name).read_text(encoding="utf-8", errors="ignore")
    text = re.sub(r"<[^>]+>", " ", html).replace("&nbsp;", " ")
    out: dict[int, float] = {}
    # Rows read "2020's  14.14  16.34 ..." — decade label then Year-0..Year-9 values.
    for m in re.finditer(r"(\d{3})0's((?:\s+[\d.]+|\s+NA|\s+-{1,2}|\s+W)+)", text):
        decade = int(m.group(1)) * 10
        for i, tok in enumerate(m.group(2).split()):
            try:
                out[decade + i] = float(tok)
            except ValueError:
                pass
    return out


def _gas_starting(state: str, sel: dict, per_ldc: dict, state_avg: dict,
                  provenance: dict, fetch: bool) -> tuple[dict, dict]:
    """STARTING_YEAR gas rates: ({ldc: block}, state block). Bridged by the state price ratio
    until EIA-176 publishes STARTING_YEAR per-LDC data."""
    prices = _ng_state_prices(state, provenance, fetch)
    if BASE_YEAR not in prices or STARTING_YEAR not in prices:
        raise SystemExit(f"EIA NG state price for {state}: missing {BASE_YEAR}/{STARTING_YEAR}")
    ratio = prices[STARTING_YEAR] / prices[BASE_YEAR]
    src = (f"EIA-176 {BASE_YEAR} × CA residential gas price ratio {STARTING_YEAR}/{BASE_YEAR} "
           f"(${prices[STARTING_YEAR]:.2f} / ${prices[BASE_YEAR]:.2f} per Mcf)")
    per = {cid: {"year": STARTING_YEAR, "rate": round(u["rate"] * ratio, 4),
                 "method": "bridged_state_ratio", "bridge_ratio": round(ratio, 4),
                 "source": src} for cid, u in per_ldc.items()}
    blend = {"year": STARTING_YEAR, "rate": round(prices[STARTING_YEAR] / MCF_TO_THERM, 4),
             "method": "observed",
             "source": f"EIA natural gas price series N3010{state}3 (annual, $/Mcf ÷ {MCF_TO_THERM})"}
    print(f"  gas {state} {STARTING_YEAR}: bridge ratio {ratio:.4f}; blend {blend['rate']:.4f} $/therm")
    return per, blend


def _elec_start_block(rate: float, what: str) -> dict:
    return {"year": STARTING_YEAR, "rate": rate, "method": "observed",
            "source": f"EIA-861M {STARTING_YEAR} {what} (revenue ÷ sales)"}


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


def build(states: list[str], check: bool, offline: bool = False):
    fetch = not (check or offline)
    # Cached-snapshot runs keep the recorded provenance of the files they re-read.
    prov_file = SOURCES / "provenance.json"
    provenance: dict = (json.loads(prov_file.read_text()) if prov_file.exists() else {})
    db = {"electric_utilities": {}, "gas_ldcs": {}, "state_average": {}}
    for state in states:
        sel = STATE_UTILITIES.get(state)
        if sel is None:
            print(f"  WARN: no utility selection for {state!r}; skipping", file=sys.stderr)
            continue
        print(f"[{state}]")
        e_util, e_avg = _build_electric(state, sel, provenance, not fetch)
        g_ldc, g_avg = _build_gas(state, sel, provenance, not fetch)
        e_start, e_start_blend = _elec_starting(state, sel, provenance, fetch)
        g_start, g_start_blend = _gas_starting(state, sel, g_ldc, g_avg, provenance, fetch)
        for num, u in e_util.items():
            db["electric_utilities"][num] = _elec_record(u["name"], state, u)
            db["electric_utilities"][num]["starting_rate"] = _elec_start_block(
                e_start[num], "per utility")
        for cid, u in g_ldc.items():
            db["gas_ldcs"][cid] = _gas_record(u["name"], state, u)
            db["gas_ldcs"][cid]["starting_rate"] = g_start[cid]
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
        db["state_average"][state]["electricity"]["starting_rate"] = _elec_start_block(
            e_start_blend, "state aggregate")
        db["state_average"][state]["gas"]["starting_rate"] = g_start_blend

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
        "starting_year": STARTING_YEAR,
        "starting_rate_note": "`starting_rate` = the record's STARTING_YEAR rate — the current "
                        "energy rate that projection methods scale (Phase 7 §4.1). Legacy "
                        "`current_rate`/`base_year` are unchanged and drive My Utility. Gas "
                        "starting rates are bridged from BASE_YEAR by the state price ratio "
                        "until EIA-176 publishes STARTING_YEAR.",
        "sources": provenance,
        "note": "Keys '_meta' aside: electric_utilities keyed by EIA-861 utility number; "
                "gas_ldcs by EIA-176 company id; state_average is the ZIP-unresolved fallback.",
    }

    if not check:
        OUT_JSON.write_text(json.dumps(db, indent=2), encoding="utf-8")
        print(f"\nWrote {OUT_JSON.relative_to(ROOT)}")
        # provenance sidecar
        prov_file.write_text(json.dumps(provenance, indent=2))
    _write_doc_fragment(db)
    return db


def main():
    ap = argparse.ArgumentParser(description="Build EIA per-utility rate database.")
    ap.add_argument("--states", nargs="+", default=["CA"], help="state codes (default: CA)")
    ap.add_argument("--check", action="store_true",
                    help="parse cached snapshots only; no download, no JSON write")
    ap.add_argument("--offline", action="store_true",
                    help="rebuild the JSON from cached snapshots (no download)")
    args = ap.parse_args()
    build([s.upper() for s in args.states], check=args.check, offline=args.offline)


if __name__ == "__main__":
    main()
