"""ui/config.py — externalized, versioned UI defaults + config load/export (Phase 4.5b).

The factory defaults live in data/config/whywatt_default.json (the single source of truth);
ui/state.py initializes its reactives from factory_defaults(). Layer 2 adds list/load/validate/
envelope helpers here; apply_config()/export_config() (which touch the reactives) live in
ui/state.py to avoid a config<->state import cycle.
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


# ── Layer 2 — list / load / validate / envelope ────────────────────────────────

def list_configs() -> list[dict]:
    """Bundled configs (factory base + everything in profiles/) as {key, name, description},
    base first. `key` is what load_config() accepts."""
    out, files = [], [CONFIG_DIR / f"{FACTORY}.json"]
    pdir = CONFIG_DIR / "profiles"
    if pdir.exists():
        files += sorted(pdir.glob("*.json"))
    for p in files:
        try:
            env = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        key = FACTORY if p.stem == FACTORY else f"profiles/{p.stem}"
        out.append({"key": key, "name": env.get("name", p.stem),
                    "description": env.get("description", "")})
    return out


def load_config(source) -> dict:
    """Return the bare `values` dict from a config source.

    source = bundled key ("whywatt_default" | "profiles/foo") | file path | envelope dict |
    bare values dict. The caller merges the result onto the factory base.
    """
    if isinstance(source, dict):
        env = source
    else:
        s = str(source)
        p = Path(s)
        env = json.loads((p if p.exists() else CONFIG_DIR / f"{s}.json").read_text(encoding="utf-8"))
    return dict(env.get("values", env))


def validate(values: dict) -> list[str]:
    """Warnings for keys not in the factory schema (these are ignored when applied)."""
    known = set(factory_defaults())
    return [f"unknown key ignored: {k!r}" for k in values if k not in known]


def make_envelope(values: dict, name: str, description: str = "", based_on: str = FACTORY) -> dict:
    """Wrap a values dict in the versioned, self-describing envelope (for export/sharing)."""
    return {"schema_version": SCHEMA_VERSION, "name": name, "description": description,
            "based_on": based_on, "values": values}
