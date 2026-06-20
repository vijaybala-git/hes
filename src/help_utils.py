"""
help_utils.py — Help system utilities for WhyWatt.

Provides:
  help_url(page, anchor)   — build the served URL for a public/help/*.html page
  HelpLink(label, topic)   — anchor that opens a help page in a new browser tab
  HelpButton(topic_key)    — small circular [?] button
  HelpPopupOverlay()       — single overlay instance; place once in Page()
  ChartHelpButton(chart_name_reactive)  — [?] for chart title bars (key from chart name)

Help HTML pages are served by Solara as static files from the project-root
``public/`` directory, mounted at ``/static/public/``. Links are plain
``<a target="_blank">`` anchors so they open in the user's actual browser tab
(server-side ``webbrowser.open`` does not work once the app is served over HTTP).
"""
import solara
from help_content import HELP_POPUPS, CHART_NAME_TO_HELP_KEY

# URL prefix where Solara serves project-root public/help/*.html
_HELP_URL_BASE = "/static/public/help/"

# ── Reactive state — key of currently open popup ("" = none open) ─────────────
help_open = solara.reactive("")

# Friendlier popup titles for chart keys (otherwise "chart_jc2" → "Jc2").
# Reverse the chart-name→key map — it covers every user-selectable chart, so each
# chart_* key resolves to its exact menu name (chart_jc1 → "Cumulative Energy Costs").
_TOPIC_TITLES: dict[str, str] = {key: name for name, key in CHART_NAME_TO_HELP_KEY.items()}


def _topic_title(key: str) -> str:
    """Human-readable popup title for a help key."""
    if key in _TOPIC_TITLES:
        return _TOPIC_TITLES[key]
    return key.replace("chart_", "").replace("_", " ").title()


# ── help_url() ────────────────────────────────────────────────────────────────

def help_url(page: str, anchor: str = "") -> str:
    """Build the served URL for a help page. ``page`` may already include a
    '#anchor'; an explicit ``anchor`` argument is appended if given."""
    url = _HELP_URL_BASE + page
    if anchor:
        url += f"#{anchor}"
    return url


@solara.component
def HelpLink(label: str, topic: str, classes: list[str] | None = None, style: str = ""):
    """Anchor styled link that opens a help page (``page.html`` or
    ``page.html#anchor``) in a new browser tab — pure client-side navigation."""
    solara.HTML(
        tag="a",
        unsafe_innerHTML=label,
        attributes={"href": help_url(topic), "target": "_blank", "rel": "noopener"},
        classes=classes or [],
        style=style,
    )


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
        max_width="90vw",
        overlay_opacity=0.15,
    ):
        if not is_open:
            return

        text, learn_more = HELP_POPUPS[key]
        title = _topic_title(key)

        with solara.v.Card(elevation=8, style_="border-radius:10px; overflow:hidden"):
            # Title row
            with solara.v.CardTitle(
                style_=(
                    "padding:14px 20px 10px;"
                    " background:#E8EAF6;"
                    " font-size:1rem;"
                    " font-weight:700;"
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
                        "min-width:28px; width:28px; height:28px; padding:0;"
                        " background:transparent; color:#78909C;"
                        " border:none; cursor:pointer; font-size:1em;"
                        " border-radius:50%;"
                    ),
                )
            # Body — min-height ~10 lines at 1.6 line-height × 0.95rem
            with solara.v.CardText(
                style_=(
                    "padding:20px 24px;"
                    " font-size:0.95rem;"
                    " color:#37474F;"
                    " line-height:1.7;"
                    " min-height:17em;"
                )
            ):
                solara.v.Html(tag="p", children=[text], style_="margin:0 0 16px 0")
                solara.HTML(
                    tag="a",
                    unsafe_innerHTML="Learn more →",
                    attributes={"href": help_url(learn_more),
                                "target": "_blank", "rel": "noopener"},
                    style=(
                        "background:transparent; color:#3F51B5;"
                        " padding:0; font-size:0.9em;"
                        " cursor:pointer; text-decoration:underline;"
                        " font-weight:600;"
                    ),
                )


# ── HelpDock ──────────────────────────────────────────────────────────────────

@solara.component
def HelpDock():
    """Inline help panel rendered BELOW the charts (bottom half of the page)
    instead of a centered overlay, so the graphs stay visible. Place once in
    Page() next to DetailDock."""
    key = help_open.value
    if not (key and key in HELP_POPUPS and not key.startswith("_")):
        return

    def close():
        help_open.set("")

    text, learn_more = HELP_POPUPS[key]
    title = _topic_title(key)

    with solara.Column(classes=["card", "dock", "help-dock"]):
        # Header — title (flex:1) pushes ✕ to the right
        with solara.Row(classes=["modal-hd"]):
            solara.HTML(tag="div", style="flex:1; min-width:0", unsafe_innerHTML=(
                f"<div class='modal-title'>❔ {title}</div>"
            ))
            solara.Button(
                "✓ Done",
                on_click=close,
                classes=["btn", "done"],
            )
        # Body
        with solara.Column(classes=["modal-bd"]):
            solara.v.Html(tag="p", children=[text],
                          style_="margin:0 0 14px 0; line-height:1.7; color:#37474F")
            solara.HTML(
                tag="a",
                unsafe_innerHTML="Learn more →",
                attributes={"href": help_url(learn_more),
                            "target": "_blank", "rel": "noopener"},
                style=(
                    "background:transparent; color:#3F51B5;"
                    " padding:0; font-size:0.9em;"
                    " cursor:pointer; text-decoration:underline;"
                    " font-weight:600;"
                ),
            )
