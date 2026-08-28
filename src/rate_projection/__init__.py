"""
Offline rate-projection library (docs/OfflineRateProjection_Plan.md).

PURE, UNWIRED analysis code — imported ONLY by notebooks/ and tests/test_rate_projection.py,
NEVER by the live WhyWatt simulation (src/model.py, src/rate_loader.py, etc.). Keeping it out
of the sim path is what lets this land without touching the golden output (see the plan's
isolation grep-gate).
"""

from .escalation import segmented_path
from .projected_rate_model import ProjectedRateModel, SCENARIO_PRESETS

__all__ = ["segmented_path", "ProjectedRateModel", "SCENARIO_PRESETS"]
