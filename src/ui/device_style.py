"""Single source of truth for device color / code / label across ALL charts."""
from __future__ import annotations

from matplotlib.lines import Line2D

DEVICE_STYLE: dict[str, dict] = {
    "hvac":    {"label": "HVAC",                "code": "HV", "color": "#D85A30", "color_dark": "#F0997B"},
    "wh":      {"label": "Water heater",        "code": "WH", "color": "#2E86C1", "color_dark": "#7FB3D3"},
    "dryer":   {"label": "Dryer",               "code": "DR", "color": "#7F77DD", "color_dark": "#AFA9EC"},
    "cooktop": {"label": "Cooktop",             "code": "CK", "color": "#C9821C", "color_dark": "#FAC775"},
    "ice":     {"label": "ICE vehicle",          "code": "IC", "color": "#C0392B", "color_dark": "#E8706A"},
    "ev":      {"label": "EV charger",          "code": "EV", "color": "#639922", "color_dark": "#97C459"},
    "lights":  {"label": "Lights & appliances", "code": "LA", "color": "#378ADD", "color_dark": "#85B7EB"},
    "solar":   {"label": "Solar + battery",     "code": "SB", "color": "#1D9E75", "color_dark": "#5DCAA5"},
    "panel":   {"label": "Electrical panel",    "code": "EP", "color": "#888780", "color_dark": "#B4B2A9"},
}

# Stable stacking / legend order — big-ticket end uses first, infra last.
DEVICE_ORDER: list[str] = ["hvac", "wh", "dryer", "cooktop", "ice", "ev", "lights", "solar", "panel"]


def dstyle(key: str) -> dict:
    """Lookup with a safe fallback so an unmapped key never crashes a chart."""
    return DEVICE_STYLE.get(
        key,
        {"label": key.title(), "code": key[:2].upper(), "color": "#888780", "color_dark": "#B4B2A9"},
    )


def device_legend_handles(keys: list[str]) -> list:
    """Return matplotlib Line2D legend handles for the given style keys."""
    return [
        Line2D(
            [0], [0],
            marker="o", linestyle="",
            markerfacecolor=dstyle(k)["color"],
            markeredgecolor=dstyle(k)["color"],
            markersize=8,
            label=dstyle(k)["label"],
        )
        for k in keys
    ]
