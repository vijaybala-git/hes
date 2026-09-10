"""scripts/build_impact_report_html.py — render the impact report to standalone HTML.

Reads docs/reports/RateModel_Impact_Report.md, inlines every referenced chart
(PNG/SVG) as a data URI, and writes a single self-contained HTML file that renders
anywhere with no external assets. Regenerate whenever the .md or charts change.

Usage:  .venv/Scripts/python.exe scripts/build_impact_report_html.py
"""
from __future__ import annotations

import base64
import mimetypes
import re
from pathlib import Path

import markdown

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "docs" / "reports" / "RateModel_Impact_Report.md"
OUT = REPO / "docs" / "reports" / "RateModel_Impact_Report.html"

CSS = """
:root { color-scheme: light dark; }
body { max-width: 900px; margin: 0 auto; padding: 2.2rem 1.4rem 4rem;
  font: 16px/1.65 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  color: #1a1a1a; background: #fafafa; }
h1 { font-size: 1.9rem; line-height: 1.2; margin: 0 0 .3rem; }
h2 { font-size: 1.4rem; margin: 2.4rem 0 .8rem; padding-bottom: .3rem;
  border-bottom: 2px solid #e0e0e0; }
h3 { font-size: 1.15rem; margin: 1.8rem 0 .6rem; }
p, li { margin: .5rem 0; }
img { max-width: 100%; height: auto; display: block; margin: 1rem auto;
  border: 1px solid #e5e5e5; border-radius: 6px; background: #fff; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: .92rem;
  display: block; overflow-x: auto; }
th, td { border: 1px solid #d5d5d5; padding: .4rem .6rem; text-align: left; }
th { background: #f0f0f0; }
td:not(:first-child), th:not(:first-child) { text-align: right; }
code { background: #eee; padding: .1rem .3rem; border-radius: 3px;
  font: .88em ui-monospace, "SF Mono", Consolas, monospace; }
pre { background: #f4f4f4; padding: .9rem 1.1rem; border-radius: 6px; overflow-x: auto;
  border: 1px solid #e5e5e5; }
pre code { background: none; padding: 0; }
blockquote { margin: 1rem 0; padding: .6rem 1rem; border-left: 4px solid #F9A825;
  background: #fff8e6; border-radius: 0 6px 6px 0; }
blockquote strong:first-child { color: #b26a00; }
hr { border: none; border-top: 1px solid #ddd; margin: 2rem 0; }
a { color: #1565C0; }
@media (prefers-color-scheme: dark) {
  body { color: #e6e6e6; background: #1e1e1e; }
  h2 { border-color: #3a3a3a; } h3 { color: #ddd; }
  img { border-color: #333; }
  th, td { border-color: #3a3a3a; } th { background: #2a2a2a; }
  code { background: #333; } pre { background: #262626; border-color: #383838; }
  blockquote { background: #2c2717; border-left-color: #F9A825; }
  blockquote strong:first-child { color: #f0b747; }
  hr { border-color: #3a3a3a; } a { color: #6ab0ff; }
}
"""


def _data_uri(rel_path: str) -> str:
    p = (SRC.parent / rel_path).resolve()
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    if p.suffix.lower() == ".svg":
        mime = "image/svg+xml"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def main():
    md_text = SRC.read_text(encoding="utf-8")

    # Inline every local image reference ![alt](path) → ![alt](data:...)
    def repl(m):
        alt, path = m.group(1), m.group(2)
        if path.startswith(("http://", "https://", "data:")):
            return m.group(0)
        return f"![{alt}]({_data_uri(path)})"

    md_text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", repl, md_text)

    html_body = markdown.markdown(
        md_text, extensions=["tables", "fenced_code", "sane_lists"])
    doc = (f"<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
           f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
           f"<title>WhyWatt — Rate-Model Impact Report</title>\n<style>{CSS}</style>\n"
           f"</head>\n<body>\n{html_body}\n</body>\n</html>\n")
    OUT.write_text(doc, encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)}  ({len(doc)/1024:.0f} KB, self-contained)")


if __name__ == "__main__":
    main()
