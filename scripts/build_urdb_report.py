#!/usr/bin/env python3
"""build_urdb_report.py — render the "Starting Rates" Technical Report (charts + HTML).

Reads the baked offline data (urdb_tou.json, urdb_baseline_crosswalk.json, the rate projection
bundle) and the prose in docs/reports/URDB_Rate_Report.md, generates the report charts into
docs/reports/assets/, injects the rate table, and writes a self-contained HTML report (+ a served
copy under public/help/ so Help -> Technical Reports can link it), mirroring build_impact_report_html.

Usage:  .venv/Scripts/python.exe scripts/build_urdb_report.py
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import markdown

ROOT = Path(__file__).resolve().parent.parent
RATES = ROOT / "data" / "rates"
REPORTS = ROOT / "docs" / "reports"
ASSETS = REPORTS / "assets"
MD = REPORTS / "URDB_Rate_Report.md"
HTML = REPORTS / "URDB_Rate_Report.html"
PUBLIC = ROOT / "public" / "help" / "URDB_Rate_Report.html"

UTIL_ORDER = ["14328", "17609", "16609"]
UTIL_SHORT = {"14328": "PG&E", "17609": "SCE", "16609": "SDG&E"}
CMAP = {"14328": "#2e7d32", "17609": "#f9a825", "16609": "#c62828"}


def _db():
    return json.loads((RATES / "urdb_tou.json").read_text())["utilities"]


def _default(u):
    return u["tariffs"][u["default_label"]]


# ── §2 rate table (markdown) ──────────────────────────────────────────────────────
def rate_table_md() -> str:
    db = _db()
    head = ("| Utility | Plan | Kind | Summer peak | Summer off-peak | Winter peak | "
            "Winter off-peak | Fixed $/mo | Default |\n"
            "|---|---|---|--:|--:|--:|--:|--:|:--:|\n")
    rows = []
    for uid in UTIL_ORDER:
        u = db[uid]
        for lab, t in u["tariffs"].items():
            s, w = t["by_month"][6], t["by_month"][0]
            fc = t["fixed_charge"]
            fmo = (fc["value"] or 0) * 30.4 if (fc["unit"] or "").startswith("$/day") else (fc["value"] or 0)
            rows.append((UTIL_SHORT[uid], t["family"], t["plan_kind"],
                         s["peak"][0]["rate"], s["offpeak"][0]["rate"],
                         w["peak"][0]["rate"], w["offpeak"][0]["rate"], fmo,
                         "★" if t["whywatt_default"] else ""))
    body = "\n".join(
        f"| {r[0]} | {r[1]} | {r[2]} | ${r[3]:.3f} | ${r[4]:.3f} | ${r[5]:.3f} | ${r[6]:.3f} | ${r[7]:.2f} | {r[8]} |"
        for r in rows)
    return head + body


# ── §3 daily + seasonal chart ──────────────────────────────────────────────────────
def chart_daily_seasonal():
    db = _db()
    defs = [(UTIL_SHORT[uid], _default(db[uid])) for uid in UTIL_ORDER]
    import numpy as np
    x = np.arange(len(defs)); w = 0.2
    series = [("Summer peak", 6, "peak", "#c0392b"), ("Summer off-peak", 6, "offpeak", "#e59866"),
              ("Winter peak", 0, "peak", "#1f6aa5"), ("Winter off-peak", 0, "offpeak", "#7fb3d5")]
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    for i, (lbl, mo, side, col) in enumerate(series):
        vals = [d[1]["by_month"][mo][side][0]["rate"] for d in defs]
        bars = ax.bar(x + (i - 1.5) * w, vals, w, label=lbl, color=col)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.2f}", ha="center", va="bottom", fontsize=7)
    ax.set_xticks(x); ax.set_xticklabels([f"{n}\n{d['family']}" for n, d in defs])
    ax.set_ylabel(r"\$/kWh"); ax.legend(fontsize=8, ncol=2)
    ax.set_title("Default residential TOU plan — peak vs off-peak, summer vs winter")
    ax.spines[["top", "right"]].set_visible(False); ax.grid(axis="y", alpha=.25)
    fig.tight_layout(); fig.savefig(ASSETS / "urdb_daily_seasonal.png", dpi=130); plt.close(fig)


# ── §4 starting-rate + projection chart ────────────────────────────────────────────
def chart_projection():
    db = _db()
    proj = json.loads((RATES / "projection" / "whywatt_rate_projection.json").read_text())
    m = proj["markets"]["CA_PGE"]
    mod = m["scenarios"]["moderate"]["retail"]["elec"]     # {year: $/kWh}
    years = [y for y in proj["years"] if 2026 <= y <= 2045]
    base = mod[str(2026)]
    growth = {y: mod[str(y)] / base for y in years}        # moderate shape, normalized to 2026
    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    for uid in UTIL_ORDER:
        eff = _default(db[uid])["effective_level"]         # URDB starting rate (2026)
        curve = [eff * growth[y] for y in years]
        ax.plot(years, curve, "-o", ms=3, color=CMAP[uid],
                label=f"{UTIL_SHORT[uid]} {_default(db[uid])['family']} (start ${eff:.3f})")
    ax.set_ylabel(r"\$/kWh (real 2024\$)"); ax.set_xlabel("year")
    ax.set_title("Starting URDB rate → WhyWatt Moderate projection, by utility")
    ax.legend(fontsize=8); ax.spines[["top", "right"]].set_visible(False); ax.grid(alpha=.25)
    fig.tight_layout(); fig.savefig(ASSETS / "urdb_projection.png", dpi=130); plt.close(fig)


# ── HTML render (self-contained, inline images) ────────────────────────────────────
CSS = """
:root { color-scheme: light dark; }
body { max-width: 900px; margin: 0 auto; padding: 2.2rem 1.4rem 4rem;
  font: 16px/1.65 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; color:#1a1a1a; background:#fafafa; }
h1 { font-size:1.9rem; line-height:1.2; margin:0 0 .3rem; }
h2 { font-size:1.4rem; margin:2.4rem 0 .8rem; padding-bottom:.3rem; border-bottom:2px solid #e0e0e0; }
h3 { font-size:1.15rem; margin:1.6rem 0 .5rem; }
p,li { margin:.5rem 0; } code { background:#eee; padding:.1rem .3rem; border-radius:3px; }
img { max-width:100%; height:auto; display:block; margin:1.2rem auto; border:1px solid #e5e5e5; border-radius:6px; background:#fff; }
table { border-collapse:collapse; width:100%; margin:1rem 0; font-size:.86rem; display:block; overflow-x:auto; }
th,td { border:1px solid #d5d5d5; padding:.35rem .55rem; text-align:left; white-space:nowrap; }
th { background:#f0f0f0; } blockquote { border-left:4px solid #bbb; margin:1rem 0; padding:.3rem 1rem; color:#444; background:#f3f3f3; }
@media (prefers-color-scheme: dark){ body{background:#1a1a1a;color:#e8e8e8;} th{background:#333;} img{background:#222;} blockquote{background:#242424;color:#bbb;} code{background:#333;} }
"""


def build_html():
    text = MD.read_text(encoding="utf-8").replace("<!--RATE_TABLE-->", rate_table_md())
    html_body = markdown.markdown(text, extensions=["tables", "fenced_code", "toc"])
    # inline images as data URIs
    for img in ASSETS.glob("urdb_*.png"):
        uri = "data:image/png;base64," + base64.b64encode(img.read_bytes()).decode()
        html_body = html_body.replace(f'src="assets/{img.name}"', f'src="{uri}"')
    doc = f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><style>{CSS}</style></head><body>{html_body}</body></html>"
    HTML.write_text(doc, encoding="utf-8")
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_text(doc, encoding="utf-8")
    print(f"wrote {HTML.relative_to(ROOT)} ({HTML.stat().st_size//1024} KB) + {PUBLIC.relative_to(ROOT)}")


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    chart_daily_seasonal()
    chart_projection()
    print("charts -> assets/urdb_daily_seasonal.png, urdb_projection.png")
    build_html()


if __name__ == "__main__":
    main()
