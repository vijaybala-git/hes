"""scripts/run_regression.py — WhyWatt golden-master regression harness.

Runs every case in tests/regression/cases/ through the REAL headless pipeline
(ui.sim.run_simulation), snapshots the user-visible numbers (ui.sim.extract_metrics),
and:

  • compares the 12 base cases against the committed golden.json (exact at the rounded
    precision — zero tolerance, per Regression_Test_Spec); and
  • runs the 24 trend offsets and checks each moved its metric in the PREDICTED direction
    (a metamorphic / "trend" check that survives golden re-blessing).

Layering (per the user's decisions):
  • golden.json snapshots BASE CASES ONLY.
  • the snapshot diff is the HARD gate (test_regression.py fails on it);
  • the trend layer is WARN-ONLY here and in the report — a wrong-direction offset is
    shouted loudly but does not fail the build.

Usage:
  python scripts/run_regression.py            # run + compare + write report.md
                                              # (first run with no golden auto-blesses it)
  python scripts/run_regression.py --update   # re-bless golden.json from the current run
  python scripts/run_regression.py --quiet     # report only, terse console
"""
from __future__ import annotations

import sys
import json
import argparse
import datetime
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

# Windows consoles default to cp1252 — make Unicode (box chars, arrows) safe.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

REG_DIR     = REPO / "tests" / "regression"
CASES_DIR   = REG_DIR / "cases"
OFFSETS_DIR = REG_DIR / "offsets"
GOLDEN_PATH = REG_DIR / "golden.json"
REPORT_PATH = REG_DIR / "report.md"
SCHEMA_VERSION = 1

# ── ANSI (best-effort; disabled when not a tty) ────────────────────────────────
_TTY = sys.stdout.isatty()
def _c(s, code):  return f"\033[{code}m{s}\033[0m" if _TTY else s
def green(s):  return _c(s, "32")
def red(s):    return _c(s, "31")
def yellow(s): return _c(s, "33")
def bold(s):   return _c(s, "1")


# ── Discovery ──────────────────────────────────────────────────────────────────

def _load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))

def discover_cases() -> dict:
    """{case_stem: envelope} for every cases/*.json, sorted by filename."""
    return {p.stem: _load_json(p) for p in sorted(CASES_DIR.glob("*.json"))}

def discover_offsets() -> list:
    """[{slug, ...envelope}] for every offsets/*.json, sorted by filename."""
    out = []
    for p in sorted(OFFSETS_DIR.glob("*.json")):
        doc = _load_json(p)
        doc["slug"] = p.stem
        out.append(doc)
    return out


# ── Running ────────────────────────────────────────────────────────────────────

def run_values(values: dict) -> dict:
    """Apply a config delta to the shared reactives and run one headless simulation.

    REPLACE semantics: apply_config merges `values` onto the factory base, so the run is
    fully determined by `values` regardless of prior on-screen state (deterministic)."""
    import ui.state as S
    from ui.sim import run_simulation, extract_metrics
    S.reset_to_defaults()
    S.apply_config(values)
    model, df = run_simulation()
    return extract_metrics(model, df)


def get_metric(metrics: dict, dotted: str):
    """Look up a dotted metric path, e.g. 'cockpit.opex_delta' or
    'devices.Water Heater.journey_final_consumption'. Returns None if absent."""
    cur = metrics
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def run_all_base() -> dict:
    """Run the 12 base cases → {case_stem: metrics}."""
    return {stem: run_values(env["values"]) for stem, env in discover_cases().items()}


def run_trends(base_metrics: dict) -> list:
    """Run each offset on top of its base case and evaluate the predicted direction.

    Returns a flat list of check rows:
      {slug, name, base_case, metric, base, offset, expected, status}
    status ∈ {"PASS","WARN"}  (WARN = wrong direction / missing metric)."""
    cases = discover_cases()
    rows = []
    for off in discover_offsets():
        base_case = off["base"]
        base_values = cases[base_case]["values"]
        merged = {**base_values, **off["values"]}
        off_metrics = run_values(merged)
        base_m = base_metrics[base_case]
        for path, expected in off["expect"].items():
            bv, ov = get_metric(base_m, path), get_metric(off_metrics, path)
            status = _check_direction(bv, ov, expected)
            rows.append({"slug": off["slug"], "name": off["name"], "base_case": base_case,
                         "metric": path, "base": bv, "offset": ov,
                         "expected": expected, "status": status})
    return rows


def _check_direction(base, offset, expected) -> str:
    """PASS/WARN for one predicted move. '+'/'-'/'0' are directional; any other string
    is an exact-value expectation on the OFFSET run (e.g. peak_status -> 'green')."""
    if base is None or offset is None:
        return "WARN"
    if expected == "+":
        return "PASS" if offset > base else "WARN"
    if expected == "-":
        return "PASS" if offset < base else "WARN"
    if expected == "0":
        return "PASS" if offset == base else "WARN"
    return "PASS" if offset == expected else "WARN"   # literal expected value


# ── Golden compare ─────────────────────────────────────────────────────────────

def _flatten(metrics: dict, prefix="") -> dict:
    """{dotted_path: value} over the nested metrics dict."""
    out = {}
    for k, v in metrics.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out


def compare_to_golden(golden: dict, current: dict) -> list:
    """Exact diff of base-case metrics vs golden. Returns rows:
      {case, metric, golden, current, kind}  kind ∈ {changed, new_case, new_metric}."""
    diffs = []
    gcases = golden.get("cases", {})
    for case, metrics in current.items():
        if case not in gcases:
            diffs.append({"case": case, "metric": "(entire case)", "golden": None,
                          "current": "…", "kind": "new_case"})
            continue
        gflat, cflat = _flatten(gcases[case]), _flatten(metrics)
        for path, cval in cflat.items():
            gval = gflat.get(path, "∅")
            if gval == "∅":
                diffs.append({"case": case, "metric": path, "golden": None,
                              "current": cval, "kind": "new_metric"})
            elif gval != cval:
                diffs.append({"case": case, "metric": path, "golden": gval,
                              "current": cval, "kind": "changed"})
    return diffs


def build_snapshot(base_metrics: dict) -> dict:
    return {"schema_version": SCHEMA_VERSION,
            "generated": datetime.date.today().isoformat(),
            "app_commit": _git_sha(),
            "cases": base_metrics}


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=str(REPO), text=True).strip()
    except Exception:
        return "unknown"


# ── Report ─────────────────────────────────────────────────────────────────────

def write_report(snapshot, diffs, trend_rows, golden_existed) -> None:
    L = []
    L.append("# WhyWatt — Regression Report\n")
    L.append(f"- **Generated:** {snapshot['generated']}")
    L.append(f"- **App commit:** `{snapshot['app_commit']}`")
    L.append(f"- **Cases:** {len(snapshot['cases'])}  ·  **Trend offsets:** "
             f"{len({r['slug'] for r in trend_rows})}\n")

    # Golden comparison (the hard gate)
    L.append("## Golden comparison (base cases — exact)\n")
    if not golden_existed:
        L.append("> 🟦 **No prior golden — this run blessed a new `golden.json`.** "
                 "All base-case numbers below are the new baseline; review them for sanity.\n")
    elif not diffs:
        L.append("✅ **No drift.** Every base-case metric matches golden exactly.\n")
    else:
        L.append(f"⚠️ **{len(diffs)} metric(s) changed** vs golden — classify each as "
                 "*designed* (then `--update`) or *regression* (then fix the code).\n")
        L.append("| Case | Metric | Golden | Current | Δ |")
        L.append("|------|--------|-------:|--------:|---|")
        for d in diffs:
            delta = _num_delta(d["golden"], d["current"])
            L.append(f"| {d['case']} | `{d['metric']}` | {_fmt(d['golden'])} | "
                     f"{_fmt(d['current'])} | {delta} |")
        L.append("")

    # Trend checks (warn-only)
    warns = [r for r in trend_rows if r["status"] == "WARN"]
    L.append("## Trend checks (offsets — directional, warn-only)\n")
    if not warns:
        L.append(f"✅ All {len(trend_rows)} predicted moves went the right way.\n")
    else:
        L.append(f"⚠️ **{len(warns)} predicted move(s) went the WRONG way** — investigate "
                 "(a sign/wiring bug, or a stale prediction to update).\n")
    L.append("| Offset | Base case | Metric | Base | Offset | Δ | Expect | Result |")
    L.append("|--------|-----------|--------|-----:|-------:|---|:------:|:------:|")
    for r in trend_rows:
        delta = _num_delta(r["base"], r["offset"])
        mark = "✅ PASS" if r["status"] == "PASS" else "🔴 **WARN**"
        L.append(f"| {r['name']} | {r['base_case']} | `{r['metric']}` | "
                 f"{_fmt(r['base'])} | {_fmt(r['offset'])} | {delta} | "
                 f"`{r['expected']}` | {mark} |")
    L.append("")

    REPORT_PATH.write_text("\n".join(L), encoding="utf-8")


def _fmt(v):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:,.1f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)

def _num_delta(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        d = b - a
        arrow = "▲" if d > 0 else ("▼" if d < 0 else "·")
        return f"{arrow} {d:+,.1f}" if isinstance(d, float) else f"{arrow} {d:+,}"
    return "→" if a != b else "·"


# ── Console + CLI ──────────────────────────────────────────────────────────────

def _print_console(diffs, trend_rows, golden_existed, quiet):
    print(bold("\nWhyWatt regression\n" + "─" * 40))
    if not golden_existed:
        print(yellow("golden: NEW (blessed this run)"))
    elif not diffs:
        print(green(f"golden: PASS — no drift across base cases"))
    else:
        print(red(f"golden: {len(diffs)} metric(s) changed:"))
        for d in diffs[: None if not quiet else 0]:
            print(f"   {d['case']:32} {d['metric']:42} "
                  f"{_fmt(d['golden'])} → {_fmt(d['current'])}")
    warns = [r for r in trend_rows if r["status"] == "WARN"]
    if not warns:
        print(green(f"trends: PASS — {len(trend_rows)} predicted moves all correct"))
    else:
        print(yellow(f"trends: {len(warns)} WRONG-DIRECTION (warn-only):"))
        for r in warns:
            print(yellow(f"   {r['name']:34} {r['metric']:40} "
                         f"{_fmt(r['base'])} → {_fmt(r['offset'])} (expected {r['expected']})"))
    print(f"\nreport: {REPORT_PATH.relative_to(REPO)}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="WhyWatt regression harness")
    ap.add_argument("--update", action="store_true",
                    help="re-bless golden.json from this run")
    ap.add_argument("--quiet", action="store_true", help="terse console output")
    args = ap.parse_args(argv)

    base_metrics = run_all_base()
    snapshot = build_snapshot(base_metrics)
    trend_rows = run_trends(base_metrics)

    golden_existed = GOLDEN_PATH.exists()
    if not golden_existed or args.update:
        GOLDEN_PATH.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
        diffs = []
        if args.update and golden_existed:
            golden_existed = True   # report as a compare that we just re-blessed
            diffs = []
    else:
        golden = _load_json(GOLDEN_PATH)
        diffs = compare_to_golden(golden, base_metrics)

    write_report(snapshot, diffs, trend_rows, golden_existed and not args.update)
    _print_console(diffs, trend_rows, golden_existed and not args.update, args.quiet)
    # The harness itself never "fails" — test_regression.py is the gate. Exit 0 always.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
