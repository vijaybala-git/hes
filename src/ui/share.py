"""ui/share.py — stateless "Share My Scenario" links (Phase 1).

A scenario is captured as the DELTA from factory defaults (only keys the user changed),
gzipped, base64url-encoded, and carried in the URL as `?s=<blob>`. Opening the link decodes
the blob, runs it through the config sanitize() boundary, and applies it. No backend, no
storage — the link is fully self-contained and never expires.

See docs/ShareScenario_Spec.md (Phase 1) for the design and threat model.
"""
import base64
import gzip
import io
import json
import os
from urllib.parse import parse_qs

from ui.config import factory_defaults, sanitize, SHARE_EXCLUDE, SHARE_DERIVED
from ui.state import export_config

# Canonical public URL the app is reached at. The app is embedded in an iframe on
# hes.whywatt.org, so window.location inside the iframe is the *.hf.space origin — and
# cross-origin policy blocks reading the parent URL. So we configure the pretty base here
# rather than letting the iframe guess. Override per-deploy with WHYWATT_SHARE_BASE; the
# JS skips it on localhost so local-dev links stay local.
CANONICAL_BASE = "https://hes.whywatt.org"

# Keys never carried in a share link: transient UI state + ZIP-derived seeded values.
_OMIT = SHARE_EXCLUDE | SHARE_DERIVED

PARAM = "s"                       # URL query key: ?s=<blob>
_MAX_BLOB = 8000                  # cap encoded length (URL sanity / pre-decode guard)
_MAX_DECOMPRESSED = 64 * 1024     # decompression-bomb guard (bounded gunzip)


def _eq(a, b) -> bool:
    """Value equality for the delta diff. Floats compared with tolerance so 65 vs 65.0
    (or slider float artifacts) don't register as a change; bools compared by identity
    so True != 1."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) < 1e-9
    return a == b


def scenario_delta() -> dict:
    """The current scenario as overrides vs factory: only keys whose value differs.

    Transient UI keys and ZIP-derived seeded keys (`_OMIT`) are never included — a shared
    link restores a scenario, not someone's open panels, chart selection, or values the app
    re-derives on load anyway.
    """
    base = factory_defaults()
    cur = export_config()["values"]
    return {k: v for k, v in cur.items()
            if k not in _OMIT and not _eq(v, base[k])}


def encode(delta: dict) -> str:
    """delta dict → url-safe blob (gzip + base64url, padding stripped)."""
    raw = json.dumps(delta, separators=(",", ":"), sort_keys=True).encode("utf-8")
    packed = gzip.compress(raw, compresslevel=9)
    return base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")


def _safe_gunzip(packed: bytes, limit: int) -> bytes | None:
    """Decompress at most `limit` bytes; return None if the stream exceeds it (bomb guard)."""
    with gzip.GzipFile(fileobj=io.BytesIO(packed)) as gz:
        raw = gz.read(limit + 1)
    return None if len(raw) > limit else raw


def decode(blob: str) -> dict:
    """blob → sanitized values dict ready for apply_config(). Returns {} on ANY problem
    (bad base64, bad gzip, oversized, non-JSON). Never raises — a corrupt/tampered link
    must degrade to factory defaults, not crash the recipient's session."""
    if not blob or len(blob) > _MAX_BLOB:
        return {}
    try:
        packed = base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4))
        raw = _safe_gunzip(packed, _MAX_DECOMPRESSED)
        if raw is None:
            return {}
        data = json.loads(raw.decode("utf-8"))
    except Exception:                      # noqa: BLE001 — any decode failure → factory
        return {}
    clean, _ = sanitize(data)              # the security boundary (types/ranges/enums)
    return clean


def share_param(search: str | None) -> str:
    """Extract the `?s=` blob from a router search string (e.g. 's=ab12&x=1'). '' if absent."""
    if not search:
        return ""
    vals = parse_qs(search).get(PARAM)
    return vals[0] if vals else ""


def current_blob() -> str:
    """Convenience: encode the live scenario delta into a shareable blob."""
    return encode(scenario_delta())


def share_base() -> str:
    """The canonical public origin for share links (no trailing slash). Env override
    WHYWATT_SHARE_BASE wins; falls back to CANONICAL_BASE. The browser ignores this on
    localhost so local dev links point at the dev server."""
    return os.environ.get("WHYWATT_SHARE_BASE", CANONICAL_BASE).rstrip("/")
