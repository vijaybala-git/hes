"""WhyWatt? — Solara entry point (Phase 4.5).

The application lives under src/ui/. This thin module keeps `solara run src/app.py`
working by re-exporting the Page component defined in ui/layout.py.
"""
from ui.layout import Page  # noqa: F401 — Solara renders the `Page` component
