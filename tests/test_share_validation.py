"""Tests for the config sanitize() security boundary (ui/config.py, Layer 3).

sanitize() is the gate every UNTRUSTED config payload passes through — a shared link or a
.json a user received from someone else. It must (a) never reject a legitimate config, and
(b) neutralize tampered payloads: wrong types, out-of-range numbers, junk keys, oversized
payloads, NaN/Inf, and transient-UI keys that would otherwise hijack the recipient's view.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

import ui.state as S
from ui import config


@pytest.fixture(autouse=True)
def _restore_state():
    yield
    S.reset_to_defaults()


# ── The core invariant: legitimate configs survive untouched ───────────────────

def test_factory_defaults_pass_clean():
    """Every non-transient factory value must survive sanitize unchanged, with NO clamps
    or type drops. This is the guard that our RANGES/ENUMS never reject a valid config."""
    clean, warnings = config.sanitize(config.factory_defaults())
    expected = {k: v for k, v in config.factory_defaults().items()
                if k not in config.SHARE_EXCLUDE}
    assert clean == expected
    # Only transient keys may be mentioned — never a clamp/drop of a real setting.
    assert all("transient key ignored" in w for w in warnings)


def test_factory_values_preserve_numeric_type():
    """int defaults stay int, float defaults stay float (no precision loss on round-trip)."""
    clean, _ = config.sanitize(config.factory_defaults())
    base = config.factory_defaults()
    for k, v in clean.items():
        if isinstance(base[k], bool) or base[k] is None:
            continue
        assert type(v) is type(base[k]), f"{k}: {type(v)} != {type(base[k])}"


def test_bundled_profiles_pass_clean():
    """Shipped configs must sanitize without any real setting being dropped/clamped.
    (The full factory envelope carries transient UI keys; those notes are expected.)"""
    for c in config.list_configs():
        values = config.load_config(c["key"])
        _, warnings = config.sanitize(values)
        offenders = [w for w in warnings if "transient key ignored" not in w]
        assert offenders == [], f"{c['key']} produced warnings: {offenders}"


# ── Adversarial payloads ───────────────────────────────────────────────────────

def test_oversized_years_is_clamped():
    """The DoS vector: years sizes the sim arrays. A huge value must be pinned, not applied."""
    clean, warnings = config.sanitize({"years": 1_000_000})
    assert clean["years"] == 30
    assert any("years" in w and "clamped" in w for w in warnings)


def test_wrong_type_is_dropped_not_applied():
    clean, warnings = config.sanitize({"square_footage": "drop-table", "num_bedrooms": 4})
    assert "square_footage" not in clean          # bad type dropped
    assert clean["num_bedrooms"] == 4             # good neighbor survives
    assert any("square_footage" in w for w in warnings)


def test_unknown_key_dropped():
    clean, warnings = config.sanitize({"zip_code": "92101", "__import__": "os"})
    assert clean == {"zip_code": "92101"}
    assert any("__import__" in w for w in warnings)


def test_transient_keys_cannot_be_injected():
    """A crafted link must not be able to force a recipient's panels open / swap charts."""
    clean, warnings = config.sanitize({"hvac_expanded": True, "detail_open": "hvac"})
    assert clean == {}
    assert all("transient" in w for w in warnings)


def test_nan_and_inf_dropped():
    clean, _ = config.sanitize({"furnace_afue": float("nan"),
                                "hp_cop_heating": float("inf")})
    assert clean == {}


def test_too_many_keys_rejects_whole_payload():
    payload = {f"junk_{i}": i for i in range(config.MAX_KEYS + 1)}
    clean, warnings = config.sanitize(payload)
    assert clean == {}
    assert warnings and "too many keys" in warnings[0]


def test_overlong_and_bad_enum_strings_dropped():
    clean, _ = config.sanitize({
        "zip_code": "9" * 100,                    # over-long + not 5-digit
        "insulation_quality": "diamond",          # not an allowed enum value
        "hvac_starting_state": "plasma",          # not gas/electric/none
    })
    assert clean == {}


def test_bad_zip_dropped_good_zip_kept():
    assert config.sanitize({"zip_code": "1234"})[0] == {}        # too short
    assert config.sanitize({"zip_code": "abcde"})[0] == {}       # non-digit
    assert config.sanitize({"zip_code": "94110"})[0] == {"zip_code": "94110"}


def test_non_dict_payload_rejected():
    assert config.sanitize([1, 2, 3]) == ({}, ["payload is not an object"])


def test_negative_cost_clamped_to_zero():
    clean, warnings = config.sanitize({"hvac_install_cost": -5000})
    assert clean["hvac_install_cost"] == 0
    assert any("clamped" in w for w in warnings)


# ── Wiring: apply_config now goes through sanitize ─────────────────────────────

def test_apply_config_clamps_and_returns_warnings():
    warnings = S.apply_config({"years": 99999, "zip_code": "92101"})
    assert S.years.value == 30                    # clamped, not applied raw
    assert S.zip_code.value == "92101"            # valid override applied
    assert any("years" in w for w in warnings)


def test_apply_config_round_trips_a_real_snapshot():
    """A genuine export must reload identically through the sanitized apply path."""
    S.zip_code.set("90001"); S.num_bedrooms.set(4); S.years.set(25)
    snap = S.export_config(name="snap")
    S.reset_to_defaults()
    warnings = S.apply_config(snap["values"])
    assert S.zip_code.value == "90001" and S.num_bedrooms.value == 4 and S.years.value == 25
    assert all("transient" in w for w in warnings)   # only transient-key notes, nothing else
