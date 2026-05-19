# WhyWatt theme tokens
# Generated from WhyWatt SVG + ECHo Electrification Collaboration logo
# ECHo colors extracted from echorixzontalimage.pdf via pixel sampling
#
# Usage in app.py:
#   from theme import LIGHT, DARK, COLORS
#   current = DARK if dark_mode.value else LIGHT

# ── Shared brand colors ───────────────────────────────────────────────────────

COLORS = {
    # WhyWatt primary (matches ECHo circle navy #005CA2)
    "navy":         "#0D47A1",
    "navy_mid":     "#1565C0",

    # ECHo sky blue — secondary accent, dark mode primary text/logo
    "sky":          "#50BDF8",

    # Shared amber/gold (WhyWatt socket = ECHo solar rays)
    "amber":        "#EC9B1E",

    # ECHo energy red — used for gas/do-nothing lines in charts
    "red_gas":      "#D0302D",

    # Neutral
    "slate":        "#78909C",
    "slate_light":  "#90A4AE",
}

# ── Light theme ───────────────────────────────────────────────────────────────

LIGHT = {
    # Backgrounds
    "bg":               "#F0F4FF",
    "surface":          "#FFFFFF",
    "header_bg":        "#FFFFFF",
    "footer_bg":        "#E8EAF6",
    "sidebar_bg":       "#FFFFFF",

    # Borders
    "border":           "#C5CAE9",

    # Text
    "text_primary":     "#1A1A2E",
    "text_secondary":   "#455A64",
    "text_muted":       "#78909C",

    # Accents
    "accent_primary":   "#0D47A1",   # navy
    "accent_secondary": "#50BDF8",   # sky (hover states, links)
    "accent_amber":     "#EC9B1E",   # payback, swap markers, "?"
    "accent_red":       "#D0302D",   # gas cost lines, warnings

    # Chips / badges
    "chip_bg":          "#E3F2FD",
    "chip_text":        "#0D47A1",
    "badge_bg":         "#0D47A1",
    "badge_text":       "#FFFFFF",

    # Logo file
    "logo_file":        "docs/assets/whywatt_logo.svg",

    # Chart line colors
    "chart_journey":    "#0D47A1",   # journey home line
    "chart_baseline":   "#D0302D",   # do-nothing / gas line
    "chart_scenario_b": "#50BDF8",   # stress scenario B line
    "chart_capex":      "#EC9B1E",   # capex spike markers

    # Chart category colors (stacked bars)
    "cat_hvac":         "#0D47A1",
    "cat_water":        "#1565C0",
    "cat_baseload":     "#78909C",
    "cat_ev":           "#50BDF8",

    # Slider accent
    "slider_color":     "#0D47A1",
}

# ── Dark theme ────────────────────────────────────────────────────────────────

DARK = {
    # Backgrounds
    "bg":               "#080F1E",
    "surface":          "#0D1A30",
    "header_bg":        "#0A1525",
    "footer_bg":        "#0A1525",
    "sidebar_bg":       "#0D1A30",

    # Borders
    "border":           "#1A3050",

    # Text
    "text_primary":     "#E8F4FE",
    "text_secondary":   "#90B4CE",
    "text_muted":       "#546E7A",

    # Accents
    "accent_primary":   "#50BDF8",   # sky blue becomes primary in dark
    "accent_secondary": "#0D47A1",   # navy recedes to secondary
    "accent_amber":     "#EC9B1E",   # unchanged — pops on dark
    "accent_red":       "#EF5350",   # slightly lighter red on dark bg

    # Chips / badges
    "chip_bg":          "#1A3050",
    "chip_text":        "#50BDF8",
    "badge_bg":         "#EC9B1E",
    "badge_text":       "#080F1E",

    # Logo file
    "logo_file":        "docs/assets/whywatt_logo_dark.svg",

    # Chart line colors
    "chart_journey":    "#50BDF8",   # sky for journey on dark bg
    "chart_baseline":   "#EF5350",   # lighter red on dark
    "chart_scenario_b": "#90CAF9",   # lighter blue for scenario B
    "chart_capex":      "#EC9B1E",   # amber unchanged

    # Chart category colors
    "cat_hvac":         "#50BDF8",
    "cat_water":        "#1565C0",
    "cat_baseload":     "#546E7A",
    "cat_ev":           "#90CAF9",

    # Slider accent
    "slider_color":     "#50BDF8",
}

# ── ECHo footer branding ──────────────────────────────────────────────────────

ECHO = {
    "name":         "Electrification Collaboration",
    "logo_file":    "docs/echorixzontalimage.pdf",
    "sky":          "#50BDF8",
    "gold":         "#EC9B1E",
    "red":          "#D0302D",
    "navy":         "#005CA2",
    "tagline":      "Supporting WhyWatt? community tools",
}
