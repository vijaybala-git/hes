#!/usr/bin/env python3
"""
build_help.py — Generate WhyWatt help HTML files from help_content.md

USAGE:
    python scripts/build_help.py              # build all pages
    python scripts/build_help.py --check      # parse only, no files written
    python scripts/build_help.py --list       # list sections found

RUN FROM the project root (D:/vijay/MyDocuments/hes).

SOURCE (the only hand-edited files, under docs/help/):
    help_content.md         — section content (the single source of truth)
    _generated/*.md         — @include fragments (climate/rate tables)
    _template.html          — dev reference for the page layout (not served)

OUTPUT (all generated; Solara serves project-root public/ at /static/public/):
    public/help/*.html      — one HTML file per section + a generated index.html
    public/assets/          — logo copied so served pages render it
    src/help_content.py     — regenerated HELP_POPUPS dict

The app reads public/help/*.html (help_utils._HELP_URL_BASE = /static/public/help/).
Nothing is written under docs/help/ — that directory holds only source.

This script is run by developers after an editor updates help_content.md.
Editors do not run this script themselves.
"""

import re
import os
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).parent.parent
SOURCE_DIR  = ROOT / "docs" / "help"          # hand-edited source (md + includes)
CONTENT_MD  = SOURCE_DIR / "help_content.md"
HELP_PY     = ROOT / "src" / "help_content.py"
# Generated, served output — Solara serves project-root public/ at /static/public/
PUBLIC_HELP   = ROOT / "public" / "help"
PUBLIC_ASSETS = ROOT / "public" / "assets"

# ── CSS shared across all pages ────────────────────────────────────────────────
_CSS = """
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
           max-width: 760px; margin: 2rem auto; padding: 0 1.5rem;
           color: #222; line-height: 1.65; }
    header { display: flex; align-items: center; gap: 1rem;
             border-bottom: 2px solid #E8EAF6; padding-bottom: 1rem; margin-bottom: 1rem; }
    header img { height: 40px; }
    header h1 { margin: 0; font-size: 1.4rem; color: #1A237E; }
    nav { font-size: 0.88rem; margin-bottom: 1.5rem; }
    nav a { color: #3F51B5; margin-right: 1.2rem; text-decoration: none; }
    nav a:hover { text-decoration: underline; }
    h2 { margin-top: 2rem; padding-bottom: 0.3rem;
         border-bottom: 1px solid #E8EAF6; color: #283593; font-size: 1.1rem; }
    p  { margin: 0.6rem 0; }
    ul { margin: 0.4rem 0 0.8rem 0; padding-left: 1.5rem; }
    li { margin: 0.3rem 0; }
    .note { background: #FFF8E1; border-left: 4px solid #FFC107;
            padding: 0.6rem 1rem; margin: 1rem 0; border-radius: 0 4px 4px 0; }
    .formula { background: #F3F4F6; border-left: 4px solid #9FA8DA;
               padding: 0.6rem 1rem; margin: 1rem 0; font-family: monospace;
               font-size: 0.88em; border-radius: 0 4px 4px 0; white-space: pre-wrap; }
    footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #E8EAF6;
             font-size: 0.78rem; color: #9E9E9E; display: flex;
             justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem; }
    .section-tag { background: #E8EAF6; color: #5C6BC0; border-radius: 4px;
                   padding: 2px 8px; font-size: 0.76rem; font-weight: 600;
                   white-space: nowrap; }
""".strip()


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class HelpSection:
    number: int           # e.g. 4
    title: str            # e.g. "HVAC — Heating & Cooling"
    html_file: str        # e.g. "hvac.html"
    keys: list[str]       # e.g. ["hvac"]
    popup: str            # short popup text
    subsections: list[tuple[str, str]] = field(default_factory=list)
    # list of (heading, body_html) pairs


# ── Parser ─────────────────────────────────────────────────────────────────────

def parse_md(path: Path) -> list[HelpSection]:
    """Parse help_content.md into a list of HelpSection objects."""
    text = path.read_text(encoding="utf-8")
    sections: list[HelpSection] = []

    # Split on ## §N markers
    raw_sections = re.split(r"\n(?=## §)", text)

    for raw in raw_sections:
        raw = raw.strip()
        if not raw.startswith("## §"):
            continue

        lines = raw.splitlines()
        header = lines[0]  # e.g. "## §4 · HVAC — Heating & Cooling"
        m = re.match(r"## §(\d+)\s*[·•]\s*(.+)", header)
        if not m:
            print(f"  WARN: unrecognised section header: {header!r}", file=sys.stderr)
            continue

        number = int(m.group(1))
        title  = m.group(2).strip()

        # Parse @key: lines and popup
        html_file = ""
        keys: list[str] = []
        popup_lines: list[str] = []
        in_popup = False
        body_start = 0

        for i, line in enumerate(lines[1:], start=1):
            stripped = line.strip()
            if stripped.startswith("@file:"):
                html_file = stripped[len("@file:"):].strip()
                in_popup = False
            elif stripped.startswith("@keys:"):
                raw_keys = stripped[len("@keys:"):].strip()
                keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
                in_popup = False
            elif stripped.startswith("@popup:"):
                popup_lines = [stripped[len("@popup:"):].strip()]
                in_popup = True
            elif in_popup and stripped.startswith("@"):
                in_popup = False  # another @ directive ends popup
            elif in_popup:
                if stripped == "":
                    in_popup = False
                else:
                    popup_lines.append(stripped)
            elif stripped.startswith("###"):
                body_start = i
                break

        popup = " ".join(popup_lines).strip()

        # Parse ### subsections from body_start onward.
        # Expand `@include: <path>` directives (path relative to docs/help/) so generated
        # fragments — e.g. the climate zone table from build_climate_db.py — splice in.
        body_lines = []
        for bl in lines[body_start:]:
            s = bl.strip()
            if s.startswith("@include:"):
                inc = path.parent / s[len("@include:"):].strip()
                if inc.exists():
                    body_lines.extend(inc.read_text(encoding="utf-8").splitlines())
                else:
                    print(f"  WARN: @include not found: {inc}", file=sys.stderr)
            else:
                body_lines.append(bl)
        subsections: list[tuple[str, str]] = []
        current_heading = ""
        current_body: list[str] = []

        def flush():
            if current_heading:
                subsections.append((current_heading, _lines_to_html(current_body)))

        for line in body_lines:
            if line.startswith("### "):
                flush()
                current_heading = line[4:].strip()
                current_body = []
            else:
                current_body.append(line)

        flush()

        if not html_file:
            print(f"  WARN: §{number} has no @file — skipping", file=sys.stderr)
            continue

        sections.append(HelpSection(
            number=number,
            title=title,
            html_file=html_file,
            keys=keys,
            popup=popup,
            subsections=subsections,
        ))

    return sorted(sections, key=lambda s: s.number)


def _lines_to_html(lines: list[str]) -> str:
    """Convert plain markdown-ish lines to HTML paragraphs and lists."""
    html_parts: list[str] = []
    in_list = False
    in_formula = False
    para_lines: list[str] = []

    def flush_para():
        nonlocal para_lines
        if para_lines:
            text = " ".join(l for l in para_lines if l.strip())
            if text.strip():
                html_parts.append(f"<p>{text.strip()}</p>")
            para_lines = []

    def flush_formula(formula_lines):
        code = "\n".join(formula_lines)
        html_parts.append(f'<div class="formula">{code}</div>')

    formula_buf: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Detect indented formula blocks (4+ spaces or tab indented)
        if line.startswith("    ") or line.startswith("\t"):
            content = line.lstrip()
            if in_list:
                flush_para()
                in_list = False
            flush_para()
            formula_buf.append(content.rstrip())
            in_formula = True
            continue
        else:
            if in_formula and formula_buf:
                flush_formula(formula_buf)
                formula_buf = []
                in_formula = False

        if stripped == "":
            flush_para()
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            continue

        if stripped.startswith("- "):
            flush_para()
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            item = stripped[2:].strip()
            # Bold **text**
            item = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", item)
            html_parts.append(f"<li>{item}</li>")
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            # Bold **text** in paragraphs
            text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", stripped)
            para_lines.append(text)

    if in_formula and formula_buf:
        flush_formula(formula_buf)
    flush_para()
    if in_list:
        html_parts.append("</ul>")

    return "\n".join(html_parts)


# ── HTML generator ─────────────────────────────────────────────────────────────

def _slug(heading: str) -> str:
    """Convert heading to an HTML anchor id."""
    return re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")


def render_html(section: HelpSection) -> str:
    title_safe = section.title.replace("&", "&amp;")
    section_tag = f"§{section.number} · {title_safe}"

    # Build main content
    content_html = ""
    for heading, body in section.subsections:
        slug = _slug(heading)
        heading_safe = heading.replace("&", "&amp;")
        content_html += f'\n    <h2 id="{slug}">{heading_safe}</h2>\n    {body}\n'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>WhyWatt Help — {title_safe}</title>
  <style>
{textwrap.indent(_CSS, "    ")}
  </style>
</head>
<body>
  <header>
    <img src="../assets/whywatt_logo.svg" alt="WhyWatt"
         onerror="this.style.display='none'">
    <h1>{title_safe}</h1>
  </header>
  <nav>
    <a href="index.html">← Help Index</a>
  </nav>
  <main>
{content_html}  </main>
  <footer>
    <span>WhyWatt v3.0 &middot; <a href="about.html" style="color:#9E9E9E">About</a></span>
    <span class="section-tag">{section_tag} &middot; edit help_content.md §{section.number}</span>
  </footer>
</body>
</html>
"""


# ── Index page generator ────────────────────────────────────────────────────────

# Curated grouping for the help index, keyed by html_file so the index never drifts
# from the sections. Any section whose file is not listed here still appears, under a
# "More help" group — so a new section can never silently fall off the index.
_INDEX_GROUPS: list[tuple[str, list[str]]] = [
    ("Getting started",        ["journey.html"]),
    ("Your home",              ["climate.html", "baseload.html", "panel.html"]),
    ("Appliances & vehicles",  ["hvac.html", "water_heating.html", "dryer.html",
                                "cooktop.html", "ev.html", "solar.html"]),
    ("Energy prices",          ["rates.html", "acc.html"]),
    ("Charts",                 ["charts.html"]),
    ("Costs beyond the bill",  ["social_cost.html"]),
    ("Technical reference",    ["climate_data.html", "rates_reference.html"]),
    ("About",                  ["about.html"]),
]

_INDEX_CSS = """
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
           max-width: 760px; margin: 2rem auto; padding: 0 1.5rem;
           color: #222; line-height: 1.65; }
    header { display: flex; align-items: center; gap: 1rem;
             border-bottom: 2px solid #E8EAF6; padding-bottom: 1rem; margin-bottom: 1.5rem; }
    header img { height: 48px; }
    header h1 { margin: 0; font-size: 1.6rem; color: #1A237E; }
    .intro { background: #E8EAF6; border-radius: 6px; padding: 0.8rem 1.2rem;
             margin-bottom: 2rem; font-size: 0.95rem; color: #283593; }
    h2 { margin-top: 2rem; padding-bottom: 0.3rem;
         border-bottom: 1px solid #E8EAF6; color: #283593; font-size: 1.05rem; }
    ul { margin: 0.4rem 0 1rem 0; padding-left: 1.4rem; }
    li { margin: 0.35rem 0; }
    a { color: #3F51B5; text-decoration: none; }
    a:hover { text-decoration: underline; }
    footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #E8EAF6;
             font-size: 0.78rem; color: #9E9E9E; }
    footer a { color: #9E9E9E; }
""".strip()


def render_index(sections: list[HelpSection]) -> str:
    """Generate index.html from the parsed sections — links to each page (never a
    per-chart anchor, which would drift), grouped by _INDEX_GROUPS with a fallback."""
    by_file = {s.html_file: s for s in sections}
    placed: set[str] = set()
    blocks: list[str] = []

    def _li(s: HelpSection) -> str:
        return f'    <li><a href="{s.html_file}">{s.title.replace("&", "&amp;")}</a></li>'

    for group_name, files in _INDEX_GROUPS:
        items = [_li(by_file[f]) for f in files if f in by_file]
        for f in files:
            if f in by_file:
                placed.add(f)
        if items:
            blocks.append(f"  <h2>{group_name}</h2>\n  <ul>\n" + "\n".join(items) + "\n  </ul>")

    leftovers = [s for s in sections if s.html_file not in placed]
    if leftovers:
        items = "\n".join(_li(s) for s in leftovers)
        blocks.append("  <h2>More help</h2>\n  <ul>\n" + items + "\n  </ul>")

    body = "\n\n".join(blocks)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>WhyWatt Help</title>
  <style>
{textwrap.indent(_INDEX_CSS, "    ")}
  </style>
</head>
<body>
  <header>
    <img src="../assets/whywatt_logo.svg" alt="WhyWatt"
         onerror="this.style.display='none'">
    <h1>WhyWatt Help</h1>
  </header>

  <div class="intro">
    This help system explains how WhyWatt models your home's electrification journey —
    where the numbers come from, what assumptions are made, and what the charts mean.
    Click any topic below or use the <strong>[?]</strong> buttons inside the app for
    quick summaries.
  </div>

{body}

  <footer>
    WhyWatt v3.0 &middot; <a href="about.html">About this tool</a>
  </footer>
</body>
</html>
"""


# ── help_content.py generator ──────────────────────────────────────────────────

# Keys that map chart names to popup keys — not in .md, kept stable here.
# Names MUST match CHART_OPTIONS in src/ui/theme.py; keys are aligned to the chart's
# reference code in CHART_CODES (chart_jc1 ↔ JC.1, chart_eu7 ↔ EU.7, chart_r5 ↔ R.5).
_CHART_NAME_TO_KEY = {
    # Journey Costs (JC)
    "Cumulative Energy Costs":        "chart_jc1",
    "Annual Cost by Year":            "chart_jc2",
    "Cost Breakdown by Category":     "chart_jc3",
    "Equipment Replacements (CapEx)": "chart_jc4",
    "Journey Timeline":               "chart_jc5",
    "Estimated Electrical Load":      "chart_jc6",
    # Energy Use (EU)
    "Home Energy Cost by Device":     "chart_eu1",
    "Home Energy Use by Device":      "chart_eu2",
    "Annual kWh by Device":           "chart_eu3",
    "Annual Gas by Device":           "chart_eu4",
    "Energy Mix Timeline":            "chart_eu6",
    "HVAC Monthly Energy":            "chart_eu7",
    # Rates (R)
    "Electric CAGR Projection":       "chart_r1",
    "Gas CAGR Projection":            "chart_r2",
    "ACC Electrical Rate Projection": "chart_r3",
    "ACC Gas Rate Projection":        "chart_r4",
    "ACC Electrical Rate Shape":      "chart_r5",
}

# Extra popup entries not tied to a page section (chart entries use chart keys).
# One per user-selectable chart in CHART_OPTIONS; text describes what the matching
# make_* builder in src/ui/charts.py actually plots. Keep each to 2–3 sentences.
_EXTRA_POPUP_KEYS = {
    # ── Journey Costs (JC) ──────────────────────────────────────────────────────
    "chart_jc1": ("Cumulative energy cost adds up every year's bill from year 1 onward, for "
                  "your journey vs. the do-nothing baseline. The crossover — where the journey "
                  "line dips below do-nothing — is your payback year, marked on the chart. "
                  "Dotted lines add the social & health cost of gas and gasoline when enabled.",
                  "charts.html"),
    "chart_jc2": ("Annual cost is the total energy bill for a single simulation year — "
                  "electricity, gas, gasoline, and external EV charging — for your journey vs. "
                  "do-nothing. The gap in any year is your saving (or extra cost) that year; "
                  "social & health costs stack on top when enabled.",
                  "charts.html"),
    "chart_jc3": ("A stacked view of cumulative cost split by category — heating, cooling, "
                  "water heating, baseload, cooking, and transportation — with gas and gasoline "
                  "social costs layered on top when enabled. Use the scenario toggle to switch "
                  "between your journey and do-nothing.",
                  "charts.html"),
    "chart_jc4": ("The one-time install costs of each appliance, colored by device and plotted "
                  "in the year they occur — your journey (solid bars) beside the do-nothing "
                  "wear-out replacements (hatched). The box totals net capital over the period "
                  "in today's dollars.",
                  "charts.html"),
    "chart_jc5": ("A year-by-year map of your electrification journey: each appliance swap and "
                  "add-on (solar, panel, EV charger) is a marker on the year it happens, with "
                  "its net cost. Do-nothing wear-out replacements appear below the rail so you "
                  "can compare the two timelines.",
                  "charts.html"),
    "chart_jc6": ("Your home's estimated electrical service load, in amps, as each electric "
                  "appliance comes online — against your panel's capacity line. It uses the NEC "
                  "Article 220 method to flag whether a panel upgrade is needed and in which "
                  "year.",
                  "charts.html"),
    # ── Energy Use (EU) ─────────────────────────────────────────────────────────
    "chart_eu1": ("A stacked area of annual home-energy cost by appliance, year over year. It "
                  "counts only energy on your home meter — gasoline and external public EV "
                  "charging are excluded. Switch scenarios with the toggle to see which swaps "
                  "cut cost most.",
                  "charts.html"),
    "chart_eu2": ("A stacked area of annual home-energy use by appliance in kilowatt-hour-"
                  "equivalent terms (gas converted at 29.3 kWh per therm). Like the cost view, "
                  "it excludes gasoline and external EV charging — only what lands on your home "
                  "meter.",
                  "charts.html"),
    "chart_eu3": ("Actual electricity used by each appliance per year, in kilowatt-hours, as "
                  "stacked bars. For an electric vehicle this counts home charging only.",
                  "charts.html"),
    "chart_eu4": ("Natural gas used by each appliance per year, in therms, as stacked bars. As "
                  "gas appliances are swapped for electric ones, these bars shrink toward zero.",
                  "charts.html"),
    "chart_eu6": ("A stacked view of where your home's energy comes from each year, in "
                  "kilowatt-hour-equivalent terms: natural gas, gasoline, grid electricity, your "
                  "own solar, and external EV charging. It tells the decarbonization story at a "
                  "glance as gas shrinks and solar grows.",
                  "charts.html"),
    "chart_eu7": ("The heat pump's energy across the twelve months of the HVAC-swap year, split "
                  "into heating (bottom) and cooling (top). Do-nothing gas heating is shown in "
                  "kilowatt-hour-equivalent (29.3 kWh per therm) so a gas furnace and a heat "
                  "pump sit on the same axis; cooling is omitted for homes that have none.",
                  "charts.html"),
    # ── Rates (R) ───────────────────────────────────────────────────────────────
    "chart_r1":  ("Your electricity price projected forward each year from your utility's "
                  "current EIA effective rate, using the escalation you choose. A second dashed "
                  "line appears when you compare two scenarios.",
                  "rates.html"),
    "chart_r2":  ("Your natural-gas price projected forward each year from your utility's "
                  "current EIA effective rate, using the escalation you choose. A second dashed "
                  "line appears when you compare two scenarios.",
                  "rates.html"),
    "chart_r3":  ("Your electricity price projected forward each year along the selected rate "
                  "model's annual-average line, with the CPUC Avoided Cost Calculator's "
                  "off-peak-to-peak hourly band shaded around it. A second dashed line appears "
                  "when you compare two scenarios.",
                  "acc.html"),
    "chart_r4":  ("Your natural-gas price projected forward each year along the selected rate "
                  "model's annual-average line, with the CPUC Avoided Cost Calculator's "
                  "summer-to-winter seasonal band shaded around it. A second dashed line appears "
                  "when you compare two scenarios.",
                  "acc.html"),
    "chart_r5":  ("A heatmap of how the effective electricity rate varies by hour of day and "
                  "month under the CPUC Avoided Cost Calculator. Summer afternoon and winter "
                  "evening peaks carry the highest avoided cost.",
                  "acc.html"),
}


def render_help_content_py(sections: list[HelpSection]) -> str:
    """Generate src/help_content.py from parsed sections."""
    lines = [
        '"""',
        "help_content.py — GENERATED FILE. Do not edit manually.",
        "Source: docs/help/help_content.md",
        "Regenerate: python scripts/build_help.py",
        '"""',
        "",
        "HELP_POPUPS: dict[str, tuple[str, str]] = {",
        "",
        "    # ── Panel headers & device rows (from help_content.md) ───────────────────",
    ]

    # Keys handled individually in _EXTRA_POPUP_KEYS — skip them from section loop
    _skip_keys = set(_EXTRA_POPUP_KEYS.keys())

    for section in sections:
        if not section.keys:
            continue
        learn_more = section.html_file
        popup_escaped = section.popup.replace('"', '\\"')
        for key in section.keys:
            if key in _skip_keys:
                continue  # handled by _EXTRA_POPUP_KEYS with per-chart text
            lines.append(f'    "{key}": (')
            # Word-wrap popup text to ~80 chars
            wrapped = textwrap.wrap(popup_escaped, width=72)
            if len(wrapped) == 1:
                lines.append(f'        "{wrapped[0]}",')
            else:
                lines.append(f'        "{wrapped[0]}"')
                for part in wrapped[1:-1]:
                    lines.append(f'        " {part}"')
                lines.append(f'        " {wrapped[-1]}",')
            lines.append(f'        "{learn_more}",')
            lines.append("    ),")

    lines += [
        "",
        "    # ── Chart title bars (stable — not from help_content.md) ─────────────────",
    ]
    for key, (text, page) in _EXTRA_POPUP_KEYS.items():
        text_escaped = text.replace('"', '\\"')
        wrapped = textwrap.wrap(text_escaped, width=72)
        lines.append(f'    "{key}": (')
        if len(wrapped) == 1:
            lines.append(f'        "{wrapped[0]}",')
        else:
            lines.append(f'        "{wrapped[0]}"')
            for part in wrapped[1:-1]:
                lines.append(f'        " {part}"')
            lines.append(f'        " {wrapped[-1]}",')
        lines.append(f'        "{page}",')
        lines.append("    ),")

    lines += [
        "",
        "    # ── Chart name → key mapping (stable) ────────────────────────────────────",
        '    "_chart_name_to_key": {  # type: ignore[assignment]',
    ]
    for name, key in _CHART_NAME_TO_KEY.items():
        lines.append(f'        "{name}": "{key}",')
    lines += [
        "    },",
        "",
        "}",
        "",
        "# Convenience export",
        "CHART_NAME_TO_HELP_KEY: dict[str, str] = "
        'HELP_POPUPS["_chart_name_to_key"]  # type: ignore[assignment]',
        "",
    ]
    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    check_only = "--check" in sys.argv
    list_only  = "--list"  in sys.argv

    print(f"Reading {CONTENT_MD.relative_to(ROOT)}")
    sections = parse_md(CONTENT_MD)
    print(f"  Found {len(sections)} sections")

    if list_only:
        for s in sections:
            keys_str = ", ".join(s.keys) if s.keys else "(no keys)"
            print(f"  S{s.number:>2}  {s.title:<40}  -> {s.html_file:<22}  keys: {keys_str}")
        return

    if check_only:
        print("  Parse OK — no files written (--check mode)")
        return

    # Write section HTML directly to the served dir (public/help/).
    PUBLIC_HELP.mkdir(parents=True, exist_ok=True)
    written_html = []
    for section in sections:
        out_path = PUBLIC_HELP / section.html_file
        out_path.write_text(render_html(section), encoding="utf-8")
        written_html.append(section.html_file)
        print(f"  wrote {out_path.relative_to(ROOT)}")

    # Generate the help index (from the sections, so it never drifts).
    (PUBLIC_HELP / "index.html").write_text(render_index(sections), encoding="utf-8")
    print(f"  wrote {(PUBLIC_HELP / 'index.html').relative_to(ROOT)}")

    # Write help_content.py
    py_content = render_help_content_py(sections)
    HELP_PY.write_text(py_content, encoding="utf-8")
    print(f"  wrote {HELP_PY.relative_to(ROOT)}")

    # Copy the logo the served pages reference at ../assets/.
    import shutil
    logo = ROOT / "docs" / "assets" / "whywatt_logo.svg"
    if logo.exists():
        PUBLIC_ASSETS.mkdir(parents=True, exist_ok=True)
        shutil.copy2(logo, PUBLIC_ASSETS / logo.name)
        print(f"  copied logo -> {(PUBLIC_ASSETS / logo.name).relative_to(ROOT)}")

    print(f"\nDone. {len(written_html)} section pages + index.html + help_content.py "
          f"-> public/help/.")
    print("\nNext steps:")
    print("  1. git add public/help/ src/help_content.py docs/help/help_content.md")
    print('  2. git commit -m "Rebuild help from help_content.md"')


if __name__ == "__main__":
    main()
