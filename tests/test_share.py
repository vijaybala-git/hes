"""Tests for ui/share.py — stateless "Share My Scenario" links (Phase 1).

Covers the delta diff, the encode/decode round-trip, the security guards in decode()
(corrupt blob, oversize, decompression bomb), and ?s= param parsing.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import base64
import gzip

import pytest

import ui.state as S
from ui import share, config


@pytest.fixture(autouse=True)
def _restore_state():
    yield
    S.reset_to_defaults()


# ── Delta ──────────────────────────────────────────────────────────────────────

def test_delta_empty_at_factory():
    assert share.scenario_delta() == {}


def test_delta_only_changed_keys():
    S.zip_code.set("90001")
    S.num_bedrooms.set(4)
    d = share.scenario_delta()
    assert d == {"zip_code": "90001", "num_bedrooms": 4}


def test_delta_excludes_transient_keys():
    """Toggling a panel-open flag must NOT enter the share payload."""
    S.hvac_expanded.set(True)
    S.detail_open.set("hvac")
    assert share.scenario_delta() == {}


def test_delta_float_tolerance():
    """Setting a value to its float-equal default is not a 'change'."""
    S.num_bedrooms.set(3.0)            # default is int 3
    assert "num_bedrooms" not in share.scenario_delta()


def test_delta_excludes_zip_derived_cagr():
    """The auto-seeded CAGR keys (ZIP-derived) never enter the share delta, even when set
    to a non-default value — they re-derive from zip_code on the recipient's load."""
    for k in config.SHARE_DERIVED:
        getattr(S, k).set(99)
    d = share.scenario_delta()
    assert all(k not in d for k in config.SHARE_DERIVED)


def test_slider_can_represent_documented_climate_cost():
    """Regression guard for the phantom-delta fix: the gasoline climate-rate slider step must
    keep the documented default (1.69) a stable snap point, so it doesn't drift to 1.70 and
    masquerade as a user change. Mirrors slider snap: round(v/step)*step within _eq tolerance."""
    default = config.factory_defaults()["gasoline_climate_cost_per_gallon"]
    step = 0.01                                    # must match panels.py climate-rate SliderSpec
    snapped = round(default / step) * step
    assert share._eq(snapped, default)


# ── Round-trip ──────────────────────────────────────────────────────────────────

def test_encode_decode_round_trip():
    S.zip_code.set("94110")
    S.years.set(25)
    S.solar_planned.set(True)
    blob = share.current_blob()
    out = share.decode(blob)
    assert out["zip_code"] == "94110"
    assert out["years"] == 25
    assert out["solar_planned"] is True


def test_full_apply_round_trip():
    """End-to-end: share link restores the scenario in a reset session."""
    S.zip_code.set("90001"); S.num_bedrooms.set(5); S.hvac_swap_year.set(7)
    blob = share.current_blob()
    S.reset_to_defaults()
    S.apply_config(share.decode(blob))
    assert S.zip_code.value == "90001"
    assert S.num_bedrooms.value == 5
    assert S.hvac_swap_year.value == 7


def test_blob_is_url_safe():
    S.zip_code.set("90001")
    blob = share.current_blob()
    assert "=" not in blob and "+" not in blob and "/" not in blob


# ── decode() security guards ─────────────────────────────────────────────────────

def test_decode_garbage_returns_empty():
    assert share.decode("!!!not-base64!!!") == {}
    assert share.decode("") == {}
    assert share.decode("YWJj") == {}            # valid base64 but not gzip


def test_decode_oversize_blob_rejected():
    assert share.decode("A" * (share._MAX_BLOB + 1)) == {}


def test_decode_decompression_bomb_rejected():
    """A tiny blob that gunzips to >64 KB must be refused, not expanded into memory."""
    bomb = gzip.compress(b"0" * (share._MAX_DECOMPRESSED + 1024))
    blob = base64.urlsafe_b64encode(bomb).decode().rstrip("=")
    assert share.decode(blob) == {}


def test_decode_tampered_values_sanitized():
    """decode() runs sanitize(): an out-of-range value is clamped, junk key dropped."""
    blob = share.encode({"years": 999999, "__evil__": 1})
    out = share.decode(blob)
    assert out["years"] == 30
    assert "__evil__" not in out


# ── ?s= param parsing ────────────────────────────────────────────────────────────

def test_share_base_default_and_env_override(monkeypatch):
    monkeypatch.delenv("WHYWATT_SHARE_BASE", raising=False)
    assert share.share_base() == share.CANONICAL_BASE
    monkeypatch.setenv("WHYWATT_SHARE_BASE", "https://example.org/")
    assert share.share_base() == "https://example.org"   # trailing slash stripped


def test_share_param_extraction():
    assert share.share_param("s=abc123") == "abc123"
    assert share.share_param("x=1&s=abc&y=2") == "abc"
    assert share.share_param("x=1") == ""
    assert share.share_param("") == ""
    assert share.share_param(None) == ""


# ── Phase 5.5 Fix 3 — guarded applier never wipes on a bad blob ─────────────────

def test_apply_share_blob_ignores_bad_blobs_without_wiping():
    """A blank/corrupt/truncated blob is a no-op — it must NOT reset in-progress edits."""
    from ui.layout import _apply_share_blob
    S.reset_to_defaults()
    S.square_footage.set(2600)          # user's in-progress scenario
    S.num_bedrooms.set(5)
    for bad in ("", "!!!not-base64!!!", "YWJj", "A" * (share._MAX_BLOB + 1)):
        assert _apply_share_blob(bad) is False
    # Untouched — no wipe to factory
    assert S.square_footage.value == 2600
    assert S.num_bedrooms.value == 5


def test_apply_share_blob_applies_a_real_scenario():
    """A valid blob is decoded and applied, returning True."""
    from ui.layout import _apply_share_blob
    S.reset_to_defaults()
    S.num_bedrooms.set(4)
    S.zip_code.set("90001")
    blob = share.current_blob()
    S.reset_to_defaults()               # simulate a fresh recipient session
    assert _apply_share_blob(blob) is True
    assert S.num_bedrooms.value == 4
    assert S.zip_code.value == "90001"


# ── Phase 5.5 Fix 6 — a scenario reproduces verbatim (CAGR + hot water captured) ─

def test_manual_cagr_is_captured_in_the_link():
    """A manually-overridden CAGR travels in the share link (no longer SHARE_DERIVED)."""
    S.reset_to_defaults()
    S.gas_cagr_pct_a.set(15)
    assert share.scenario_delta().get("gas_cagr_pct_a") == 15


def test_manual_cagr_survives_share_and_is_not_reseeded():
    """A shared manual CAGR restores exactly, and the seeder does NOT clobber it on load."""
    from ui.layout import _apply_share_blob
    from ui.sim import _seed_eia_cagr
    S.reset_to_defaults()
    S.gas_cagr_pct_a.set(15)
    blob = share.current_blob()

    S.reset_to_defaults()                 # fresh recipient
    assert _apply_share_blob(blob) is True
    assert S.gas_cagr_pct_a.value == 15   # restored verbatim
    _seed_eia_cagr()                      # seeder runs on the same context → must be suppressed
    assert S.gas_cagr_pct_a.value == 15   # not clobbered


def test_export_load_preserves_manual_cagr():
    """Export → Load reproduces a manual CAGR (apply_config marks the context; seeder skips)."""
    from ui.sim import _seed_eia_cagr
    S.reset_to_defaults()
    S.gas_cagr_pct_a.set(15)
    snap = S.export_config()
    S.reset_to_defaults()
    S.apply_config(snap["values"])
    _seed_eia_cagr()
    assert S.gas_cagr_pct_a.value == 15


def test_hw_override_round_trips():
    """A custom daily-hot-water setting (value + override flag) survives a share round-trip."""
    from ui.layout import _apply_share_blob
    S.reset_to_defaults()
    S.hw_daily_gallons.set(100)
    S.hw_gallons_user_override.set(True)
    blob = share.current_blob()
    S.reset_to_defaults()
    assert _apply_share_blob(blob) is True
    assert S.hw_daily_gallons.value == 100
    assert S.hw_gallons_user_override.value is True


def test_seeder_still_runs_for_a_fresh_session():
    """Determinism must not disable the interactive seed: with no scenario loaded, seeding
    runs and (at the default ZIP) matches the aligned factory default → empty delta."""
    from ui.sim import _seed_eia_cagr, _rate_info
    S.reset_to_defaults()
    _seed_eia_cagr()                                   # not suppressed — no load happened
    zip_gas = round(_rate_info(S.zip_code.value, "auto").gas.cagr * 100)
    assert S.gas_cagr_pct_a.value == zip_gas           # seeded
    assert share.scenario_delta() == {}                # factory aligned → still an empty link
