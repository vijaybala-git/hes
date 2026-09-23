#!/usr/bin/env python3
"""build_urdb.py — offline URDB residential ELECTRIC tariff harvest → data/rates/urdb_tou.json.

See docs/OfflineURDB_Plan.md. URDB is electric-only (gas stays on the EIA path). This script:
  1. fetches all approved residential tariffs for a utility (EIA id), newest-first, OR reads a
     cached raw response (--from-cache) so a rebuild needs no API calls / no key;
  2. curates the hundreds of raw records down to the current flagship families (regions.py, §4.2a):
     E-1 (tiered_legacy), E-TOU-C / E-TOU-D / E-ELEC (tou), EV / EV2 (ev_tou);
  3. picks one representative per family (a baseline region, non-all-electric) and records the rest;
  4. parses each into the source-agnostic RateStructure schema (§3): per-month peak/offpeak tier
     ladders + peak hours + fixed charge + a cross-check-only effective_level;
  5. tags exactly one whywatt_default (a TOU plan) per utility and writes urdb_tou.json + a raw
     snapshot (sha256) under data/rates/sources/urdb/.

NOTHING here is imported by src/ (isolation gate, §6) until Phase 7.

USAGE (from project root, with the venv interpreter):
    URDB_API_KEY=... .venv/Scripts/python.exe scripts/build_urdb.py --eiaid 14328
    .venv/Scripts/python.exe scripts/build_urdb.py --state CA
    .venv/Scripts/python.exe scripts/build_urdb.py --eiaid 14328 --from-cache <raw.json>
The API key falls back to DEMO_KEY (rate-limited) when URDB_API_KEY is unset.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path

# stdlib-only network so the script has no hard dep beyond requests (already in the venv)
import requests

sys.path.insert(0, str(Path(__file__).parent))
import regions as R  # noqa: E402

ROOT = Path(__file__).parent.parent
RATES = ROOT / "data" / "rates"
SOURCES = RATES / "sources" / "urdb"
OUT_JSON = RATES / "urdb_tou.json"
KEY_FILE = ROOT / "secrets" / "urdb_api_key"      # git-ignored; see secrets/README.md


def resolve_api_key(cli_key: str | None) -> str:
    """--api-key > URDB_API_KEY env > secrets/urdb_api_key file > DEMO_KEY (rate-limited)."""
    if cli_key:
        return cli_key
    if os.environ.get("URDB_API_KEY"):
        return os.environ["URDB_API_KEY"]
    if KEY_FILE.exists():
        key = _read_key_file(KEY_FILE)
        if key:
            return key
    return "DEMO_KEY"


def _read_key_file(path: Path) -> str:
    """Read a key file tolerantly — Windows editors/PowerShell often save UTF-16 with a BOM."""
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):        # UTF-16 LE/BE BOM
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig")                    # strips a UTF-8 BOM if present
    # first non-empty line, minus surrounding quotes/whitespace
    for line in text.splitlines():
        line = line.strip().strip("'\"")
        if line:
            return line
    return ""

URDB_URL = "https://api.openei.org/utility_rates"
URDB_VERSION = "latest"
PEAK_HOURS = list(range(16, 21))          # 4–9pm, the CA TOU peak window
REP_KWH_MONTH = 500                       # fixed basis for effective_level cross-check only (§5.2)
DAYS = [calendar.monthrange(2025, m)[1] for m in range(1, 13)]


# ── Fetch ────────────────────────────────────────────────────────────────────────
def fetch_utility(eiaid: int, api_key: str, max_records: int = 500) -> list[dict]:
    """Newest-first residential, approved, full-detail. One page (500) surfaces all current
    flagship tariffs for CA IOUs; extend with offset paging if a utility needs it."""
    r = requests.get(URDB_URL, params={
        "version": URDB_VERSION, "format": "json", "api_key": api_key,
        "eia": eiaid, "sector": "Residential", "approved": "true", "detail": "full",
        "limit": max_records, "orderby": "startdate", "direction": "desc",
    }, timeout=120)
    r.raise_for_status()
    return r.json().get("items", [])


# ── Curate (§4.2a) ─────────────────────────────────────────────────────────────────
def _is_current(it: dict, now: float) -> bool:
    return bool(it.get("energyratestructure")) and (not it.get("enddate") or it["enddate"] > now)


def curate(items: list[dict], util: R.Utility) -> tuple[dict, list[dict]]:
    """Return (families, dropped). families: family_key -> {representative, variants[], plan_kind}."""
    now = datetime.now(UTC).timestamp()
    families: dict[str, dict] = {}
    dropped: list[dict] = []
    for it in items:
        name = it.get("name", "")
        plan_kind, family = R.classify(name)
        if not family:
            continue                      # excluded / non-flagship (income-qualified, historical, …)
        if not _is_current(it, now):
            dropped.append({"label": it.get("label"), "name": name, "reason": "expired/empty"})
            continue
        fam = families.setdefault(family, {"plan_kind": plan_kind, "variants": []})
        fam["variants"].append(it)

    # pick a representative per family: prefer the configured baseline region, non-all-electric
    for family, fam in families.items():
        variants = fam["variants"]
        def score(it):
            reg = R.baseline_region(it.get("name", ""))
            return (
                0 if reg == util.representative_region else 1,   # prefer configured region
                0 if not R.is_all_electric(it.get("name", "")) else 1,  # prefer standard, not all-elec
                -(it.get("startdate") or 0),                     # newest
            )
        fam["representative"] = sorted(variants, key=score)[0]
    return families, dropped


# ── Parse raw URDB record → normalized RateStructure (§3) ──────────────────────────
def _ladder(period_tiers: list[dict]) -> list[dict]:
    """URDB [{max,rate,adj}] (per period) → [{max_kwh_day, rate}] ascending tier ladder."""
    out = []
    for t in period_tiers:
        out.append({"max_kwh_day": t.get("max"), "rate": round(t.get("rate", 0.0) + t.get("adj", 0.0), 6)})
    return out


def _period_rate(ers: list, pidx: int) -> float:
    t0 = ers[pidx][0]
    return t0.get("rate", 0.0) + t0.get("adj", 0.0)


def parse_tariff(it: dict) -> dict:
    ers = it["energyratestructure"]                 # periods × tiers
    wsched = it["energyweekdayschedule"]            # 12×24 period index
    EVENING = range(16, 22)                         # 4–10pm: the CA peak window (covers 4-9pm & 5-8pm)
    by_month = []
    for m in range(12):
        # peak = the highest-rate period active in the evening window (robust to 4-9 vs 5-8 plans)
        pk = max((wsched[m][h] for h in EVENING), key=lambda p: _period_rate(ers, p))
        op = wsched[m][3]                           # overnight (3am) = the standard off-peak
        # guard: if the overnight period is itself the priciest (odd tariff), fall back to min-rate period
        if _period_rate(ers, op) >= _period_rate(ers, pk):
            all_p = {wsched[m][h] for h in range(24)}
            op = min(all_p, key=lambda p: _period_rate(ers, p))
        by_month.append({
            "peak_period": pk, "offpeak_period": op,
            "peak": _ladder(ers[pk]), "offpeak": _ladder(ers[op]),
        })
    # TOU = the price differs WITHIN a day (peak != off-peak in some month). Seasonal-only variation
    # (a tiered plan whose baseline changes summer/winter) is NOT time-of-use.
    is_tou = any(bm["peak"] != bm["offpeak"] for bm in by_month)
    # actual peak window = hours mapped to the summer peak period (handles 4-9pm vs 5-8pm plans);
    # a flat (non-TOU) tariff has no meaningful peak window -> empty.
    summer_pk = by_month[6]["peak_period"]
    peak_hours = [h for h in range(24) if wsched[6][h] == summer_pk] if is_tou else []
    fc_val = it.get("fixedchargefirstmeter")
    return {
        "peak_hours": peak_hours,
        "is_tou": bool(is_tou),
        "fixed_charge": {"value": fc_val, "unit": it.get("fixedchargeunits")},
        "by_month": by_month,
    }


def _fixed_monthly(fc: dict, days: int) -> float:
    v, u = fc.get("value") or 0.0, (fc.get("unit") or "")
    if u.startswith("$/day"):
        return v * days
    if u.startswith("$/month"):
        return v
    return 0.0


def effective_level(structure: dict) -> float:
    """All-in $/kWh at REP_KWH_MONTH with a flat load — CROSS-CHECK / headline only (never billed).
    Flat load ⇒ ~5/24 of energy in the 5-hour peak window on weekdays (≈5/7 of days)."""
    peak_frac = (len(PEAK_HOURS) / 24.0) * (5.0 / 7.0)
    annual_cost = annual_kwh = 0.0
    for m in range(12):
        bm = structure["by_month"][m]
        kwh = REP_KWH_MONTH
        pk_kwh, op_kwh = kwh * peak_frac, kwh * (1 - peak_frac)
        # price at tier-1 (rep usage assumed near baseline) + fixed charge
        cost = pk_kwh * bm["peak"][0]["rate"] + op_kwh * bm["offpeak"][0]["rate"]
        cost += _fixed_monthly(structure["fixed_charge"], DAYS[m])
        annual_cost += cost
        annual_kwh += kwh
    return round(annual_cost / annual_kwh, 4)


# ── Assemble one utility record ────────────────────────────────────────────────────
def build_utility(items: list[dict], util: R.Utility) -> tuple[dict, list[dict], list[dict]]:
    families, dropped = curate(items, util)
    if not families:
        raise SystemExit(f"No flagship tariffs found for EIA {util.eiaid} — check name patterns.")

    tariffs: dict[str, dict] = {}
    raw_snapshots: list[dict] = []
    default_label = None
    for family, fam in families.items():
        rep = fam["representative"]
        label = rep["label"]
        structure = parse_tariff(rep)
        variant_regions = sorted({R.baseline_region(v["name"]) for v in fam["variants"] if R.baseline_region(v["name"])})
        # per-territory baseline allowances (kWh/day) across ALL variants of this family — the input
        # to the ZIP->baseline-region crosswalk. Empty for non-tiered plans (e.g. SCE flat TOU).
        region_baselines: dict[str, dict] = {}
        for v in fam["variants"]:
            reg = R.baseline_region(v.get("name", ""))
            if not reg or R.is_all_electric(v.get("name", "")):
                continue                       # standard (non-all-electric) territory baseline only
            try:
                vs = parse_tariff(v)
            except Exception:
                continue
            s = vs["by_month"][6]["peak"][0]["max_kwh_day"]      # summer baseline
            w = vs["by_month"][0]["peak"][0]["max_kwh_day"]      # winter baseline
            if s or w:
                region_baselines[reg] = {"summer_kwh_day": s, "winter_kwh_day": w}
        rec = {
            "label": label,
            "name": rep.get("name"),
            "family": family,
            "plan_kind": fam["plan_kind"],
            "baseline_region": R.baseline_region(rep.get("name", "")),
            "all_electric": R.is_all_electric(rep.get("name", "")),
            "closed_to_enrollment": R.is_closed(rep.get("name", "")),
            "whywatt_default": False,
            "is_urdb_default": bool(rep.get("is_default")),
            "approved": bool(rep.get("approved")),
            "startdate": date.fromtimestamp(rep["startdate"]).isoformat() if rep.get("startdate") else None,
            "n_variants": len(fam["variants"]),
            "variant_baseline_regions": variant_regions,
            "region_baselines": region_baselines,
            "effective_level": effective_level(structure),
            "rep_kwh_month": REP_KWH_MONTH,
            **structure,
            "provenance": {"label": label, "uri": rep.get("uri"), "eiaid": rep.get("eiaid")},
        }
        tariffs[label] = rec
        raw_snapshots.append(rep)
        if family == util.default_family:
            default_label = label

    # default policy (§4.3): curated family → else newest TOU → else any
    if default_label is None:
        tou = [(l, r) for l, r in tariffs.items() if r["plan_kind"] == "tou" and not r["closed_to_enrollment"]]
        default_label = (sorted(tou, key=lambda kv: kv[1]["startdate"] or "", reverse=True)[0][0]
                         if tou else next(iter(tariffs)))
    tariffs[default_label]["whywatt_default"] = True

    util_rec = {
        "utility": util.name,
        "state": next((reg.state for reg in R.REGIONS.values() if util in reg.utilities), None),
        "default_label": default_label,
        "tariffs": tariffs,
    }
    return util_rec, raw_snapshots, dropped


# ── Main ───────────────────────────────────────────────────────────────────────────
def _sha256(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description="Offline URDB residential-electric harvest.")
    ap.add_argument("--eiaid", type=int, action="append", help="EIA utility id (repeatable).")
    ap.add_argument("--state", help="Harvest every utility this project prices in the state (regions.py).")
    ap.add_argument("--from-cache", help="Parse this cached raw URDB JSON instead of fetching (single eiaid).")
    ap.add_argument("--api-key", default=None,
                    help="Override the key; otherwise URDB_API_KEY env / secrets/urdb_api_key / DEMO_KEY.")
    args = ap.parse_args()
    cli_key = args.api_key
    args.api_key = resolve_api_key(cli_key)
    if not args.from_cache:
        src = ("--api-key flag" if cli_key else
               "URDB_API_KEY env" if os.environ.get("URDB_API_KEY") else
               "secrets/urdb_api_key" if (KEY_FILE.exists() and KEY_FILE.read_text().strip()) else
               "DEMO_KEY (rate-limited)")
        shown = "DEMO_KEY" if args.api_key == "DEMO_KEY" else "****" + args.api_key[-4:]
        print(f"[key] using {src} ({shown})")

    if args.state:
        targets = R.utilities_for_state(args.state)
    elif args.eiaid:
        targets = [R.utility_by_eiaid(e) or R.Utility(e, f"EIA {e}", "E-TOU-C") for e in args.eiaid]
    else:
        ap.error("give --eiaid and/or --state")

    SOURCES.mkdir(parents=True, exist_ok=True)
    db = json.loads(OUT_JSON.read_text()) if OUT_JSON.exists() else {"_meta": {}, "utilities": {}}
    db.setdefault("utilities", {})
    sources_sha = db["_meta"].get("sources_sha256", {})

    for util in targets:
        if args.from_cache:
            items = json.loads(Path(args.from_cache).read_text()).get("items", [])
            print(f"[cache] {util.name} ({util.eiaid}): {len(items)} raw records")
        else:
            items = fetch_utility(util.eiaid, args.api_key)
            print(f"[fetch] {util.name} ({util.eiaid}): {len(items)} raw records")

        util_rec, raws, dropped = build_utility(items, util)
        # snapshot only the curated flagship raws (small, reproducible)
        snap_name = f"pge_{util.eiaid}_flagship_raw.json" if util.eiaid == 14328 else f"eia_{util.eiaid}_flagship_raw.json"
        snap = {"eiaid": util.eiaid, "harvested": date.today().isoformat(), "records": raws}
        (SOURCES / snap_name).write_text(json.dumps(snap, indent=1))
        sources_sha[snap_name] = _sha256(raws)

        util_rec["dropped_count"] = len(dropped)
        db["utilities"][str(util.eiaid)] = util_rec
        d = util_rec["tariffs"][util_rec["default_label"]]
        print(f"   -> {len(util_rec['tariffs'])} flagship plans; default={d['family']} "
              f"({d['name'][:40]}); effective ~${d['effective_level']}/kWh; dropped {len(dropped)}")

    db["_meta"] = {
        "status": f"URDB residential electric TOU + tiered; utilities {sorted(db['utilities'])}.",
        "urdb_version": "8", "built": date.today().isoformat(),
        "sector": "Residential", "approved_only": True,
        "peak_hours": PEAK_HOURS, "rep_kwh_month": REP_KWH_MONTH,
        "note": "Electric only — gas stays on the EIA path. effective_level is cross-check/headline "
                "only; the bill uses the by_month tier ladders at the home's real usage (approach B).",
        "sources_sha256": sources_sha,
    }
    OUT_JSON.write_text(json.dumps(db, indent=1))
    print(f"\nwrote {OUT_JSON.relative_to(ROOT)} ({OUT_JSON.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
