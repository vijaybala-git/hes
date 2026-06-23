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

def test_share_param_extraction():
    assert share.share_param("s=abc123") == "abc123"
    assert share.share_param("x=1&s=abc&y=2") == "abc"
    assert share.share_param("x=1") == ""
    assert share.share_param("") == ""
    assert share.share_param(None) == ""
