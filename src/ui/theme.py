"""ui/theme.py — design tokens, color palette, chart constants, and CSS strings.

Phase 4.5 leaf module: pure constants extracted verbatim from app.py (no behavior change,
no reactive coupling). Imported back into app.py by name so existing references are unchanged.
"""
from pathlib import Path

_SRC = Path(__file__).parent.parent   # src/ — CSS files live here

# ── CSS injected once via solara.Style in Page ──────────────────────────────────
try:
    _REDESIGN_CSS = (_SRC / "styles_redesign.css").read_text(encoding="utf-8")
except OSError:
    _REDESIGN_CSS = ""

try:
    _LAYOUT_V2_CSS = (_SRC / "layout_v2.css").read_text(encoding="utf-8")
except OSError:
    _LAYOUT_V2_CSS = ""

# ── Color palette ─────────────────────────────────────────────────────────────
C_NAVY  = "#0D47A1"
C_SKY   = "#50BDF8"
C_RED   = "#D0302D"
C_BASE  = C_RED
C_ELEC  = C_NAVY
# Rate model UI colors — distinct from journey Red/Blue
C_RATE_ELEC = "#0288D1"   # light blue — electricity rate
C_RATE_GAS  = "#E65100"   # deep orange — gas rate

# ── Chart design tokens (D6 — design system series colors + transparent bg) ───
_CC_J    = "#3B6FD4"   # journey series (design token)
_CC_B    = "#D2785F"   # baseline series (design token)
_CC_GRID = "#EBEDF1"
_CC_TICK = "#5A6273"
_CC_SOLAR = "#00897B"

CATEGORY_COLORS = {
    "Baseload":       ("#BDBDBD", "#BBDEFB"),
    "WaterHeating":   ("#9E9E9E", C_SKY),
    "HVAC_Cooling":   ("#757575", "#1E88E5"),
    "HVAC_Heating":   ("#424242", C_NAVY),
    "Transportation": ("#6D4C41", "#7B1FA2"),
}

CHART_OPTIONS = [
    "Cumulative Energy Costs",
    "Annual Cost by Year",
    "Cost Breakdown by Category",
    "Equipment Replacements (CapEx)",
    "Estimated Electrical Load",
    "Electric CAGR Projection",
    "Gas CAGR Projection",
    "ACC Electrical Rate Projection",
    "ACC Gas Rate Projection",
    "ACC Electrical Rate Shape",
    "Journey Timeline",
    "Home Energy Cost by Device",
    "Home Energy Use by Device",
    "Annual kWh by Device",
    "Annual Gas by Device",
    "HVAC Monthly Energy",
    "Energy Mix Timeline",
]

# Reference codes shown in chart titles and headers — used in help files
CHART_CODES = {
    "Cumulative Energy Costs":        "JC.1",
    "Annual Cost by Year":            "JC.2",
    "Cost Breakdown by Category":     "JC.3",
    "Equipment Replacements (CapEx)": "JC.4",
    "Journey Timeline":               "JC.5",
    "Estimated Electrical Load":      "JC.6",
    "Home Energy Cost by Device":     "EU.1",
    "Home Energy Use by Device":      "EU.2",
    "Annual kWh by Device":           "EU.3",
    "Annual Gas by Device":           "EU.4",
    "HVAC Monthly Energy":            "EU.7",
    "Energy Mix Timeline":            "EU.6",
    "Electric CAGR Projection":       "R.1",
    "Gas CAGR Projection":            "R.2",
    "ACC Electrical Rate Projection": "R.3",
    "ACC Gas Rate Projection":        "R.4",
    "ACC Electrical Rate Shape":      "R.5",
}

# Per-slot color palette (consistent across EU.3 / EU.4 / cost charts)
_SLOT_COLORS = {
    "HVAC":                  "#1565C0",
    "Water Heater":          "#0288D1",
    "Dryer":                 "#D32F2F",
    "Cooktop":               "#F57C00",
    "EV Charger":            "#388E3C",
    "Transportation":        "#C0392B",
    "EV Driving":            "#388E3C",
    "Lights and Appliances": "#78909C",
}

KWH_PER_THERM = 29.3
KWH_PER_GALLON_GASOLINE = 33.7   # EPA energy content of gasoline (MPGe basis), display only

UA_MAP = {"poor": 650, "average": 500, "good": 350}

_SLOT_DISPLAY_ORDER = ["HVAC", "Water Heater", "Dryer", "Cooktop", "EV Driving", "Lights and Appliances"]
DEVICE_LABELS = ["HVAC", "Water Heater", "Dryer", "Cooktop", "EV Charging", "Baseload"]
DEVICE_COLORS = ["#0D47A1", "#1565C0", "#D0302D", "#EC9B1E", "#388E3C", "#78909C"]
DEVICE_ALPHAS = [0.70,      0.60,       0.55,      0.55,      0.55,       0.45]
