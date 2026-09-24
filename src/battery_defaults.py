"""Default home battery (Phase 7 §2) — Tesla Powerwall 3 datasheet values.

Read once from data/appliances/battery_defaults.json (built by
scripts/build_battery_defaults.py from the manufacturer datasheet). BatteryConfig takes its
defaults from here; data/config/whywatt_default.json carries the same numbers for the UI and
a test keeps the two in step.
"""
from __future__ import annotations

import json
from pathlib import Path

_FILE = Path(__file__).parent.parent / "data" / "appliances" / "battery_defaults.json"


def _load() -> dict:
    doc = json.loads(_FILE.read_text(encoding="utf-8"))
    return {"model": doc["default_model"], **doc["models"][doc["default_model"]]}


DEFAULT_BATTERY: dict = _load()
