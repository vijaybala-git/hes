"""Tests for the externalized UI config (Phase 4.5b, Layer 1).

Enforces the single-source-of-truth invariant: every reactive default comes from
data/config/whywatt_default.json, so the dict and the reactive initial values can never drift.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

import ui.state as S
from ui import config

# Module-level reactives that are intentionally NOT config-driven (ephemeral UI state).
_TRANSIENT = {"setup_collapsed", "_panel_state", "_baseload_state", "hw_gallons_user_override",
              # Phase 5 §5 per-block collapse chevrons — view state, left out of reset/config.
              "cockpit_collapsed", "graphs_collapsed", "journey_collapsed"}


@pytest.fixture(autouse=True)
def _restore_state():
    """Leave the shared reactives at factory after every test (they're process-global)."""
    yield
    S.reset_to_defaults()


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


# ── Layer 2: list / load / apply / export ──────────────────────────────────────

def test_list_configs_includes_factory_and_profiles():
    names = [c["name"] for c in config.list_configs()]
    assert "whywatt_default" in names
    assert any("Diego" in n or "Angeles" in n for n in names)  # bundled profiles present


def test_load_config_from_key_and_dict():
    by_key = config.load_config("profiles/los_angeles")
    assert by_key["zip_code"] == "90001"
    by_dict = config.load_config({"values": {"zip_code": "77777"}})
    assert by_dict == {"zip_code": "77777"}


def test_apply_config_is_replace():
    S.zip_code.set("11111")
    S.num_bedrooms.set(5)
    S.apply_config(config.load_config("profiles/los_angeles"))   # delta = {zip_code: 90001}
    assert S.zip_code.value == "90001"                            # override applied
    assert S.num_bedrooms.value == S._DEFAULTS["num_bedrooms"]    # absent key -> factory (REPLACE)


def test_apply_config_ignores_unknown_keys():
    S.apply_config({"zip_code": "92101", "bogus_key": 123})
    assert S.zip_code.value == "92101"
    assert not hasattr(S, "bogus_key")


def test_export_round_trips():
    S.zip_code.set("90001")
    S.num_bedrooms.set(4)
    snap = S.export_config(name="snap", description="d")
    assert snap["schema_version"] == config.SCHEMA_VERSION
    assert len(snap["values"]) == len(S._DEFAULTS)
    S.reset_to_defaults()
    assert S.zip_code.value != "90001"
    S.apply_config(snap["values"])                 # re-load the snapshot
    assert S.zip_code.value == "90001" and S.num_bedrooms.value == 4
