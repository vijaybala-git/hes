#!/usr/bin/env python3
"""
build_help.py — Generate WhyWatt help HTML files from help_content.md

USAGE:
    python scripts/build_help.py              # build all pages
    python scripts/build_help.py --check      # parse only, no files written
    python scripts/build_help.py --list       # list sections found

RUN FROM the project root (D:/vijay/MyDocuments/hes).

OUTPUT:
    docs/help/*.html        — one HTML file per section
    src/help_content.py     — regenerated HELP_POPUPS dict

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
CONTENT_MD  = ROOT / "docs" / "help" / "help_content.md"
HELP_DIR    = ROOT / "docs" / "help"
HELP_PY     = ROOT / "src" / "help_content.py"

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

        # Parse ### subsections from body_start onward
        body_lines = lines[body_start:]
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


# ── help_content.py generator ──────────────────────────────────────────────────

# Keys that map chart names to popup keys — not in .md, kept stable here
_CHART_NAME_TO_KEY = {
    "Cumulative Energy Costs":    "chart_jc2",
    "Annual Cost by Year":        "chart_jc1",
    "Cost Breakdown by Category": "chart_jc4",
    "Cost by Device":             "chart_jc4",
    "Summary":                    "chart_jc3",
    "ACC Rate Projection":        "chart_r2",
    "Energy Use by Device":       "chart_eu2",
}

# Extra popup entries not tied to a page section (chart entries use chart keys)
_EXTRA_POPUP_KEYS = {
    "chart_jc1": ("Annual cost is the total energy bill for that simulation year — "
                  "electricity plus gas — for your journey home vs. the do-nothing baseline. "
                  "The gap between the lines is your annual saving (or cost) in that year.",
                  "charts.html#jc1"),
    "chart_jc2": ("Cumulative cost adds up every year's bill from year 1 onward. "
                  "The crossover point — where the journey line dips below do-nothing — "
                  "is your payback year.",
                  "charts.html#jc2"),
    "chart_jc3": ("The summary bar shows total 20-year spend for each scenario side by side. "
                  "The difference is your estimated lifetime savings from electrification.",
                  "charts.html#jc3"),
    "chart_jc4": ("Each segment shows one appliance's share of the annual energy bill. "
                  "Watching this chart across years shows which swaps have the biggest cost impact.",
                  "charts.html#jc4"),
    "chart_r1":  ("Rates are projected forward from today's PG&E tariff using a compound annual "
                  "growth rate (CAGR). You can choose conservative, moderate, or stress scenarios.",
                  "rates.html#projection"),
    "chart_r2":  ("The ACC (Avoided Cost of Carbon) seasonal shape shows how the effective "
                  "electricity rate varies by month under the CPUC's avoided-cost framework. "
                  "Summer peak hours carry the highest effective rate.",
                  "acc.html"),
    "chart_eu1": ("Annual energy consumption in physical units — kilowatt-hours for electricity "
                  "and therms for gas. This shows how much energy is used before applying rates.",
                  "charts.html#eu1"),
    "chart_eu2": ("Each segment shows one appliance's share of total energy consumption. "
                  "Compare journey vs. do-nothing to see which swaps reduce energy use most.",
                  "charts.html#eu2"),
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

    # Write HTML files
    written_html = []
    for section in sections:
        out_path = HELP_DIR / section.html_file
        html = render_html(section)
        out_path.write_text(html, encoding="utf-8")
        written_html.append(section.html_file)
        print(f"  wrote {out_path.relative_to(ROOT)}")

    # Write help_content.py
    py_content = render_help_content_py(sections)
    HELP_PY.write_text(py_content, encoding="utf-8")
    print(f"  wrote {HELP_PY.relative_to(ROOT)}")

    print(f"\nDone. {len(written_html)} HTML files + help_content.py regenerated.")
    print("\nNext steps:")
    print("  1. git add docs/help/*.html src/help_content.py")
    print('  2. git commit -m "Rebuild help from help_content.md"')


if __name__ == "__main__":
    main()
