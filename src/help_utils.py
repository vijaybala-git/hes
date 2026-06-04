"""
help_utils.py — Help system utilities for WhyWatt.

Provides:
  open_help(page, anchor)  — open a docs/help/*.html page in the browser
  HelpButton(topic_key)    — small circular [?] button
  HelpPopupOverlay()       — single overlay instance; place once in Page()
  ChartHelpButton(chart_name_reactive)  — [?] for chart title bars (key from chart name)
"""
import os
import webbrowser
import solara
from help_content import HELP_POPUPS, CHART_NAME_TO_HELP_KEY

# Absolute path to docs/help/ directory
_HELP_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "docs", "help")
)

# ── Reactive state — key of currently open popup ("" = none open) ─────────────
help_open = solara.reactive("")


# ── open_help() ───────────────────────────────────────────────────────────────

def open_help(page: str, anchor: str = "") -> None:
    """Open a help HTML page in the default browser (file:/// URL, offline-safe)."""
    path = os.path.join(_HELP_DIR, page)
    url  = "file:///" + path.replace(os.sep, "/")
    if anchor:
        url += f"#{anchor}"
    webbrowser.open(url)


def _open_topic(learn_more: str) -> None:
    """Parse 'page.html' or 'page.html#anchor' and open it."""
    if "#" in learn_more:
        page, anchor = learn_more.split("#", 1)
        open_help(page, anchor)
    else:
        open_help(learn_more)


# ── HelpButton ────────────────────────────────────────────────────────────────

@solara.component
def HelpButton(topic_key: str, style: str = ""):
    """Small circular '?' button — opens the popup for topic_key."""
    if topic_key not in HELP_POPUPS:
        return

    def on_click():
        help_open.set(topic_key)

    solara.Button(
        "?",
        on_click=on_click,
        style=(
            "min-width:20px; width:20px; height:20px; padding:0;"
            " border-radius:50%; font-size:0.72em; font-weight:700;"
            " background:transparent; color:#5C6BC0;"
            " border:1.5px solid #9FA8DA; cursor:pointer;"
            " line-height:20px; flex-shrink:0;" + style
        ),
    )


# ── ChartHelpButton ───────────────────────────────────────────────────────────

@solara.component
def ChartHelpButton(chart_name: str):
    """[?] button for a chart title bar — looks up topic key from chart name."""
    key = CHART_NAME_TO_HELP_KEY.get(chart_name, "")
    if not key:
        return
    HelpButton(key, style="margin-left:6px")


# ── HelpPopupOverlay ──────────────────────────────────────────────────────────

@solara.component
def HelpPopupOverlay():
    """
    Single overlay instance — place once near the top of Page().
    Renders the popup card for whichever topic_key is in help_open.
    Dismissed by clicking ✕ or anywhere outside (v-dialog backdrop).
    """
    key = help_open.value
    is_open = bool(key and key in HELP_POPUPS and not key.startswith("_"))

    def close():
        help_open.set("")

    def on_v_model(v):
        if not v:
            close()

    # Always render the dialog; v_model controls visibility
    with solara.v.Dialog(
        v_model=is_open,
        on_v_model=on_v_model,
        max_width="380px",
        overlay_opacity=0.0,
    ):
        if not is_open:
            return

        text, learn_more = HELP_POPUPS[key]
        # Human-readable title from the key
        title = key.replace("chart_", "").replace("_", " ").title()

        with solara.v.Card(elevation=6, style_="border-radius:8px; overflow:hidden"):
            # Title row
            with solara.v.CardTitle(
                style_=(
                    "padding:10px 14px 6px;"
                    " background:#E8EAF6;"
                    " font-size:0.88rem;"
                    " font-weight:600;"
                    " color:#283593;"
                    " display:flex;"
                    " align-items:center;"
                    " justify-content:space-between;"
                )
            ):
                solara.v.Html(tag="span", children=[title])
                solara.Button(
                    "✕",
                    on_click=close,
                    style=(
                        "min-width:22px; width:22px; height:22px; padding:0;"
                        " background:transparent; color:#78909C;"
                        " border:none; cursor:pointer; font-size:0.85em;"
                        " border-radius:50%;"
                    ),
                )
            # Body
            with solara.v.CardText(style_="padding:10px 14px; font-size:0.84rem; color:#37474F; line-height:1.55"):
                solara.v.Html(tag="p", children=[text], style_="margin:0 0 10px 0")
                solara.Button(
                    "Learn more →",
                    on_click=lambda: (_open_topic(learn_more), close()),
                    style=(
                        "background:transparent; color:#3F51B5;"
                        " border:none; padding:0; font-size:0.82em;"
                        " cursor:pointer; text-decoration:underline;"
                        " font-weight:600;"
                    ),
                )
