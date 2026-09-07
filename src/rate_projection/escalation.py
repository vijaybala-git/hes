"""
The escalation primitive (methodology Energy_Rate_Projection_Spec.md §4).

Every time-varying scalar is a base value times a horizon-segmented compound growth:

    X(y) = X(0) * prod_{t=base+1..y} (1 + g_seg(t))

Segments are chosen by CALENDAR YEAR (the structural-knot variant, §4 recommended):
    near : year <= knot_mid   (default 2030 — GRC horizon)
    mid  : knot_mid < year <= knot_long   (default 2045 — SB 100 endpoint)
    long : year > knot_long

Growth may be negative (e.g. electricity carbon intensity). This is the single
generalization of the live model's one-line `base * (1+cagr)**(y-base)`.
"""

from __future__ import annotations

DEFAULT_KNOT_MID = 2030
DEFAULT_KNOT_LONG = 2045


def _segment_rate(year: int, growth: dict, knot_mid: int, knot_long: int) -> float:
    if year <= knot_mid:
        return growth["near"]
    if year <= knot_long:
        return growth["mid"]
    return growth["long"]


def segmented_path(
    base_value: float,
    base_year: int,
    years,
    growth: dict,
    knot_mid: int = DEFAULT_KNOT_MID,
    knot_long: int = DEFAULT_KNOT_LONG,
) -> dict:
    """
    Return {year: value} for every year in `years`, compounding `growth` segment by segment
    from base_year. `growth` = {"near": g, "mid": g, "long": g} (decimals, e.g. 0.06).
    Years before base_year are returned at base_value (no back-projection here).
    """
    years = sorted(years)
    out = {}
    # Walk year-by-year from base_year so each year compounds on the previous.
    val = base_value
    y = base_year
    out[base_year] = base_value
    last = max(years[-1], base_year)
    while y < last:
        y += 1
        val *= 1.0 + _segment_rate(y, growth, knot_mid, knot_long)
        out[y] = val
    return {yr: out.get(yr, base_value) for yr in years}
