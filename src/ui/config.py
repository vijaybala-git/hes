"""ui/config.py — externalized, versioned UI defaults + config loading (Phase 4.5b, Layer 1).

The factory defaults live in data/config/whywatt_default.json (the single source of truth);
ui/state.py initializes its reactives from factory_defaults(). Layer 2 (loading/applying/
exporting shared configs) will build on merge() + the same versioned envelope.
"""
import json
from pathlib import Path

SCHEMA_VERSION = 1
CONFIG_DIR = Path(__file__).parent.parent.parent / "data" / "config"
FACTORY = "whywatt_default"


def _load_envelope(name: str) -> dict:
    """Read a config envelope (schema_version/name/description/based_on/values) by name."""
    return json.loads((CONFIG_DIR / f"{name}.json").read_text(encoding="utf-8"))


def factory_defaults() -> dict:
    """Factory default reactive values — the 'values' block of whywatt_default.json.

    Returns a fresh copy so callers cannot mutate the on-disk baseline.
    """
    return dict(_load_envelope(FACTORY)["values"])


def merge(values: dict) -> dict:
    """REPLACE-semantics merge: start from the factory defaults, override with `values`.

    A key absent from `values` keeps its factory value — so a delta config (a few keys) and a
    full snapshot apply identically (Phase 4.5b). Layer 2 uses this for apply_config().
    """
    return {**factory_defaults(), **values}
