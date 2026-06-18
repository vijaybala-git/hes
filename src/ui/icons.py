"""ui/icons.py — inline SVG icon strings + the device→help-key map.

Phase 4.5 leaf module: pure string/dict constants extracted verbatim from app.py.
"""

# Icon-only SVG extracted from whywatt_logo.svg paths (house + bar elements).
# ViewBox crops to the icon area (x 0-88, y 0-92); fills turned white so the
# icon renders cleanly on the .brand-mark gradient background.
_WHYWATT_ICON_SVG = (
    '<svg viewBox="0 0 88 92" xmlns="http://www.w3.org/2000/svg">'
    '<path d="M8 84 L8 44 L44 8 L80 44 L80 84 Z"'
    ' fill="rgba(255,255,255,0.18)" stroke="rgba(255,255,255,0.85)"'
    ' stroke-width="3.5" stroke-linejoin="round"/>'
    '<rect x="30.973" y="44.513" width="8" height="18" rx="4" fill="#fff"/>'
    '<rect x="49.895" y="47.27" width="8" height="13" rx="4" fill="#fff"/>'
    '<path d="M40.487 67 L40.487 72 C43.154 75.333 45.82 75.333 48.487 72'
    ' L48.487 67 Z" fill="#fff"/>'
    '</svg>'
)

_DEVICE_ICONS = {
    "hvac":         ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<path d='M12 3v18M3 12h18M5.6 5.6l12.8 12.8M18.4 5.6 5.6 18.4'/>"
                     "<circle cx='12' cy='12' r='2.4' fill='currentColor' stroke='none'/></svg>"),
    "water_heater": ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<rect x='6' y='3' width='12' height='18' rx='3'/>"
                     "<path d='M9 8h6M12 13v4'/></svg>"),
    "ice":          ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<path d='M2 17V9a2 2 0 012-2h9l4 4v6'/>"
                     "<path d='M1 17h18'/><circle cx='5' cy='17.5' r='1.5'/>"
                     "<circle cx='14' cy='17.5' r='1.5'/>"
                     "<path d='M9 7V3M9 3h4'/></svg>"),
    "ev":           ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<path d='M3 17V8a2 2 0 012-2h7a2 2 0 012 2v9'/>"
                     "<path d='M2 17h13'/><circle cx='5.5' cy='17.5' r='1.6'/>"
                     "<circle cx='11.5' cy='17.5' r='1.6'/><path d='M14 9h2.5L19 12v5h-5'/></svg>"),
    "cooktop":      ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<path d='M12 2c0 6-6 6-6 12a6 6 0 1012 0c0-6-6-6-6-12z'/></svg>"),
    "dryer":        ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<path d='M20.38 3.46 16 2a4 4 0 01-8 0L3.62 3.46a2 2 0 00-1.34 2.23l.58 3.57"
                     "a1 1 0 00.99.84H6v10c0 1.1.9 2 2 2h8a2 2 0 002-2V10h2.15a1 1 0 00.99-.84"
                     "l.58-3.57a2 2 0 00-1.34-2.23z'/></svg>"),
    "panel":        ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<path d='M13 2 4 14h6l-1 8 9-12h-6l1-8z'/></svg>"),
    "baseload":     ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<path d='M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 006 8"
                     "c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5'/>"
                     "<path d='M9 18h6M10 22h4'/></svg>"),
    "home":         ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<path d='M3 11.5 12 4l9 7.5'/><path d='M5 10.5V20h14v-9.5'/></svg>"),
    "solar":        ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<circle cx='12' cy='12' r='4'/>"
                     "<path d='M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2'/>"
                     "</svg>"),
    "rates":        ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<path d='M3 3v18h18'/><path d='M7 14l3-4 3 2 4-6'/></svg>"),
}

# ── Card-level header icons (accent-soft .ic chip in .card-hd) ────────────────
_CARD_IC = {
    "journey": ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                " stroke-linecap='round' stroke-linejoin='round'>"
                "<path d='M4 19V5a2 2 0 012-2h9l5 5v11a2 2 0 01-2 2H6a2 2 0 01-2-2z'/>"
                "<path d='M8 8h5M8 12h8M8 16h8'/></svg>"),
    "home":    ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                " stroke-linecap='round' stroke-linejoin='round'>"
                "<path d='M3 11.5 12 4l9 7.5'/><path d='M5 10.5V20h14v-9.5'/></svg>"),
    "energy":  ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                " stroke-linecap='round' stroke-linejoin='round'>"
                "<path d='M3 3v18h18'/><path d='M7 14l3-4 3 2 4-6'/></svg>"),
}

# ── Panel sub-header icons (smaller .ic chip in .panel-hd) ────────────────────
_PANEL_IC = {
    "home_profile": ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<path d='M3 11.5 12 4l9 7.5'/><path d='M5 10.5V20h14v-9.5'/></svg>"),
    "solar":        ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<circle cx='12' cy='12' r='4'/>"
                     "<path d='M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2'/>"
                     "</svg>"),
    "rates":        ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<path d='M3 17l5-5 4 3 7-8'/><path d='M21 7v5h-5'/></svg>"),
    "social":       ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
                     " stroke-linecap='round' stroke-linejoin='round'>"
                     "<path d='M12 22C6.5 22 2 17.5 2 12S6.5 2 12 2s10 4.5 10 10-4.5 10-10 10z'/>"
                     "<path d='M8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01'/></svg>"),
}

_DEVICE_HELP_KEY = {
    "hvac":         "hvac",
    "water_heater": "water_heater",
    "ice":          "transportation",
    "ev":           "ev_charger",
    "cooktop":      "cooktop",
    "dryer":        "dryer",
    "panel":        "panel_upgrade",
    "baseload":     "baseload",
    "home":         "home_profile",
    "solar":        "solar",
    "rates":        "rates",
}

_SOCIAL_IC = ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'"
              " stroke-linecap='round' stroke-linejoin='round'>"
              "<path d='M12 22C6.5 22 2 17.5 2 12S6.5 2 12 2s10 4.5 10 10-4.5 10-10 10z'/>"
              "<path d='M8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01'/></svg>")
