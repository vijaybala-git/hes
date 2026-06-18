"""Tests for the externalized UI config (Phase 4.5b, Layer 1).

Enforces the single-source-of-truth invariant: every reactive default comes from
data/config/whywatt_default.json, so the dict and the reactive initial values can never drift.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import ui.state as S
from ui import config

# Module-level reactives that are intentionally NOT config-driven (ephemeral UI state).
_TRANSIENT = {"setup_collapsed", "_panel_state", "_baseload_state", "hw_gallons_user_override"}


def test_config_file_has_versioned_envelope():
    env = config._load_envelope(config.FACTORY)
    assert env["schema_version"] == config.SCHEMA_VERSION
    assert env["name"] == "whywatt_default"
    assert env["based_on"] is None
    assert isinstance(env["values"], dict) and env["values"]


def test_defaults_loaded_from_config():
    assert S._DEFAULTS == config.factory_defaults()


def test_reactives_init_from_defaults_no_drift():
    """Every default key has a reactive initialized to exactly that value."""
    for k, v in S._DEFAULTS.items():
        rv = getattr(S, k, None)
        assert rv is not None, f"_DEFAULTS key {k!r} has no matching reactive"
        assert rv.value == v, f"{k}: reactive {rv.value!r} != config {v!r}"


def test_every_persistent_reactive_is_in_config():
    """A new persistent reactive must be externalized — it can't be added without a config key."""
    react = {n for n in dir(S) if hasattr(getattr(S, n), "value") and not n.startswith("__")}
    persistent = react - _TRANSIENT
    assert persistent == set(S._DEFAULTS), (
        f"persistent reactives missing from config: {persistent - set(S._DEFAULTS)}; "
        f"config keys with no reactive: {set(S._DEFAULTS) - persistent}")


def test_merge_replace_semantics():
    m = config.merge({"zip_code": "90001"})
    assert m["zip_code"] == "90001"                              # override applied
    assert m["num_bedrooms"] == S._DEFAULTS["num_bedrooms"]      # absent key keeps factory
    assert set(m) == set(S._DEFAULTS)                            # all keys present (replace)
