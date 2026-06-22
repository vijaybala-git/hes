"""ui/slider.py — WhyWatt unified slider (Phase 5 §1).

One reusable slider, two zones, no third line:

    ZONE 1 (header)  Title: 1.43 $/therm                    +0.36
    ZONE 2 (track)   ●━━━━━━━━━━┿━━━━━━━━━━━━━━━━○

`WhyWattSlider` commits on drag-*release* via a short debounce, so a full drag gesture
triggers exactly one model recompute instead of one per tick (the Phase 5 §1 "debounce"
deliverable). The locked visual spec + token map live in
docs/Phase5_UserInterface_update.md (§1 / §1.5). This is the Climate Cost test bed; the
component is rolled out to the rest of the app only after evaluation.

Module-level reactives in ui/state.py are global singletons, so the debounce timer can set
them from its background thread and the bound components re-render.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional

import solara
from solara.server import kernel_context as _kctx

# ── Token map — spec `--ww-*` names onto existing brand vars (§1.5 token table) ──
SLIDER_TOKENS = dict(
    title="--ink-3",          # muted label
    value="--ink",            # ink, monospace
    unit="--ink-4",           # faint tertiary, smaller
    delta="--ink-3",          # NEUTRAL grey — sign carries direction, no valence
    track="--border-soft",    # neutral track  (no --ww-track equivalent yet)
    fill="--journey",         # filled portion
    thumb_border="--journey-ink",
    tick="--ink-4",           # default marker, neutral
    thumb_px=16,              # MUST match the alignment math below
)

_DEBOUNCE_S = 0.18  # commit this long after the last drag tick → ~1 recompute / gesture


@dataclass
class SliderSpec:
    """One slider's declarative config (Phase 5 §2 schema)."""
    key: str
    title: str
    minimum: float
    maximum: float
    step: float
    default: float
    unit: str = ""
    decimals: int = 2
    dtype: str = "number"          # "number" | "year"
    base_year: int = 2026          # for dtype="year"; pass the live sim_start_year
    gate_label: Optional[str] = None
    layout: str = "stack"          # "stack" | "inline"  (gated auto when gate_label)


# ── small format helpers ────────────────────────────────────────────────────────

def _fmt(spec: SliderSpec, v: float) -> str:
    return f"{v:.{spec.decimals}f}" if spec.decimals > 0 else f"{int(round(v))}"


def _pct(spec: SliderSpec, v: float) -> float:
    span = spec.maximum - spec.minimum
    return 0.0 if span == 0 else (v - spec.minimum) / span


def _delta_html(spec: SliderSpec, v: float) -> str:
    """Neutral-grey ±delta chip, shown only off-default. Full detail on hover."""
    if spec.dtype == "year":                        # delta in whole years from default
        d = int(round(v)) - int(round(spec.default))
        if d == 0:
            return ""
        sign = "+" if d > 0 else "−"
        dcal = spec.base_year + int(round(spec.default)) - 1
        tip = f"{sign}{abs(d)} yr from default ({dcal})"
        return f"<span class='ww-delta' title=\"{tip}\">{sign}{abs(d)} yr</span>"
    delta = v - spec.default
    if abs(delta) < spec.step / 2:                  # §1.5: hide threshold = step/2
        return ""
    sign = "+" if delta >= 0 else "−"
    face = f"{sign}{_fmt(spec, abs(delta))}"
    tip = (f"{sign}{_fmt(spec, abs(delta))} {spec.unit} from default "
           f"({_fmt(spec, spec.default)} {spec.unit})").strip()
    return (f"<span class='ww-delta' title=\"{tip}\">{face}</span>")


def _to_disp(spec: SliderSpec, v: float):
    """Underlying value → the number shown/typed in the editable value field."""
    if spec.dtype == "year":
        return spec.base_year + int(round(v)) - 1       # calendar year
    if spec.decimals == 0:
        return int(round(v))                            # integer — no trailing .0
    return round(v, spec.decimals)


def _from_disp(spec: SliderSpec, d: float) -> float:
    """Typed value field → underlying value (clamped to range, snapped to step)."""
    if spec.dtype == "year":
        v = float(d) - spec.base_year + 1
    else:
        v = float(d)
    v = min(max(v, spec.minimum), spec.maximum)
    v = round(v / spec.step) * spec.step
    return float(int(round(v))) if spec.dtype == "year" else v


# ── one-time scoped CSS ─────────────────────────────────────────────────────────

_T = SLIDER_TOKENS
_CSS = f"""
.ww-slider {{ display:flex; flex-direction:column; gap:5px; margin:2px 0; }}
.ww-slider .ww-hd {{ display:flex; align-items:baseline; gap:6px; min-height:18px; }}
.ww-slider .ww-title {{ font-size:13px; color:var({_T['title']}); }}
.ww-slider .ww-val   {{ font-family:var(--mono); font-size:14px; font-weight:500;
                        font-variant-numeric:tabular-nums; color:var({_T['value']}); }}
.ww-slider .ww-unit  {{ font-family:var(--mono); font-size:12px;
                        color:var({_T['unit']}); margin-left:3px; }}
.ww-slider .ww-spacer {{ flex:1; }}
.ww-slider .ww-delta {{ font-family:var(--mono); font-size:12px; font-weight:500;
                        color:var({_T['delta']}); cursor:default; }}
.ww-slider .ww-gate {{ display:flex; align-items:center; gap:4px; flex:1; min-width:0; }}

/* gated layout (3 lines): checkbox+title / value·unit … delta / track */
.ww-slider .ww-hd-gated {{ display:flex; align-items:center; gap:6px; min-height:26px; }}
.ww-slider .ww-hd-gated .ww-gate {{ flex:1; min-width:0; }}
.ww-slider .ww-hd-gated .ww-gate label {{ white-space:nowrap; }}
.ww-slider .ww-valrow {{ display:flex; align-items:center;
                         justify-content:space-between; gap:8px; margin:1px 0 2px; }}

/* editable value field — compact, mono, sized to content */
.ww-slider .ww-val-input {{ flex:0 0 auto; width:122px; }}
.ww-slider .ww-vi-year {{ width:78px; }}
.ww-slider .ww-val-input .v-input {{ margin:0!important; padding:0!important;
                                     font-size:14px; }}
.ww-slider .ww-val-input input {{ font-family:var(--mono); font-size:14px; font-weight:500;
        font-variant-numeric:tabular-nums; color:var({_T['value']}); text-align:center;
        padding:2px 0!important; }}
.ww-slider .ww-val-input .v-text-field__suffix {{ font-family:var(--mono); font-size:11px;
        color:var({_T['unit']}); padding-left:3px; }}
/* light shading instead of a box — no border, faint fill, a touch more on focus */
.ww-slider .ww-val-input .v-input__slot {{ min-height:26px!important;
        border:none!important; box-shadow:none!important; border-radius:5px!important;
        background:rgba(13,71,161,0.05)!important; padding:0 6px!important;
        transition:background .12s ease; }}
.ww-slider .ww-val-input .v-input__slot:hover {{ background:rgba(13,71,161,0.08)!important; }}
.ww-slider .ww-val-input .v-input--is-focused .v-input__slot,
.ww-slider .ww-val-input .v-input__slot:focus-within {{
        background:rgba(13,71,161,0.10)!important; }}

/* inline layout (detail panels) — label | track | value, one line, tracks aligned */
.ww-slider .ww-hd-inline {{ display:flex; align-items:center; gap:10px; }}
.ww-slider .ww-ilabel {{ flex:0 0 96px; width:96px; white-space:nowrap; overflow:hidden;
        text-overflow:ellipsis; font-size:13px; color:var({_T['title']}); }}
.ww-slider .ww-hd-inline .ww-track {{ flex:1 1 auto; min-width:60px; }}
.ww-slider .ww-hd-inline .ww-val-input {{ width:76px; }}

/* Zone 2 — thin restyled vuetify slider + absolute default tick overlay */
.ww-slider .ww-track {{ position:relative; padding:0 0 2px; }}
.ww-slider .ww-track .v-slider {{ margin:0; }}
.ww-slider .ww-track .v-input__slot {{ margin:0; }}
.ww-slider .ww-track .v-slider__track-container {{ height:4px; }}
.ww-slider .ww-track .v-slider__track-background {{ background:var({_T['track']})!important; }}
.ww-slider .ww-track .v-slider__track-fill {{ background:var({_T['fill']})!important; }}
.ww-slider .ww-track .v-slider__thumb {{ width:{_T['thumb_px']}px; height:{_T['thumb_px']}px;
        left:-{_T['thumb_px']//2}px; background:#fff!important;
        border:2px solid var({_T['thumb_border']}); box-shadow:0 1px 2px rgba(0,0,0,.18); }}
.ww-slider .ww-track .v-slider__thumb::before {{ display:none; }}
/* default tick: 2×12px neutral mark, aligned under the thumb via the §5 calc formula */
.ww-slider .ww-tick {{ position:absolute; top:50%; transform:translate(-50%,-50%);
        width:2px; height:12px; background:var({_T['tick']}); border-radius:1px;
        pointer-events:none; }}
"""


def _capture_ctx():
    """Grab the current kernel context during render (in-context); None if headless."""
    try:
        return _kctx.get_current_context()
    except Exception:
        return None


@solara.component
def _SliderCSS():
    solara.Style(_CSS)


# ── the component ───────────────────────────────────────────────────────────────

@solara.component
def WhyWattSlider(
    spec: SliderSpec,
    value: solara.Reactive,
    enabled: Optional[solara.Reactive] = None,
    on_change=None,
):
    """Unified slider. `enabled` (required iff spec.gate_label) gates the track:
    when its checkbox is unchecked the unit collapses to checkbox + title only.
    `on_change(value)` fires once per committed change (for slot side-effects such
    as a 'user override' flag).
    """
    _SliderCSS()

    # The slider and the editable value field both drive a live `draft`; the slider
    # reads `draft` as its position, so typing a value moves the thumb. `disp` is the
    # number shown in the field (calendar year for year-mode, raw value otherwise).
    # The model recompute is committed draft→value once dragging/typing settles.
    draft = solara.use_reactive(value.value)
    disp = solara.use_reactive(_to_disp(spec, value.value))
    holder = solara.use_memo(lambda: {"timer": None}, [])

    # Capture this session's kernel context. The debounce timer fires on a bare
    # thread that does NOT inherit the contextvar, so without re-attaching the
    # context, `value.set()` would target no session and never re-render. (Solara
    # reactives are per-virtual-kernel — a reload resets them to default.)
    ctx = solara.use_memo(_capture_ctx, [])

    # keep draft synced when value changes externally (reset / load settings)
    def _sync():
        if draft.value != value.value:
            draft.set(value.value)
    solara.use_effect(_sync, [value.value])

    # keep the value field in step with the slider (and any external change)
    def _sync_disp():
        nd = _to_disp(spec, draft.value)
        if disp.value != nd:
            disp.set(nd)
    solara.use_effect(_sync_disp, [draft.value])

    # cancel any pending commit on unmount
    def _cleanup():
        def _c():
            t = holder["timer"]
            if t is not None:
                t.cancel()
        return _c
    solara.use_effect(_cleanup, [])

    def _commit(val):
        if ctx is None:                              # headless / no session — direct
            value.set(val)
            if on_change is not None:
                on_change(val)
            return
        th = threading.current_thread()
        _kctx.set_context_for_thread(ctx, th)
        try:
            value.set(val)
            if on_change is not None:
                on_change(val)
        finally:
            _kctx.clear_context_for_thread(th)

    def _schedule_commit(v):
        t = holder["timer"]
        if t is not None:
            t.cancel()
        nt = threading.Timer(_DEBOUNCE_S, lambda val=v: _commit(val))
        nt.daemon = True
        holder["timer"] = nt
        nt.start()

    def _on_draft(v):                                # slider drag → live draft
        v = float(v)
        draft.set(v)
        _schedule_commit(v)

    def _on_input(d):                                # typed field (commit on blur/enter)
        if d is None:
            return
        v = _from_disp(spec, d)
        if v != draft.value:
            draft.set(v)                             # moves the slider thumb
        _schedule_commit(v)

    is_gated = spec.gate_label is not None and enabled is not None
    on = (enabled.value if is_gated else True)

    def _value_input():
        use_int = spec.dtype == "year" or spec.decimals == 0
        cls = ["ww-val-input"] + (["ww-vi-year"] if spec.dtype == "year" else [])
        suffix = None if spec.dtype == "year" else (spec.unit or None)
        if use_int:
            solara.InputInt("", value=disp, on_value=_on_input, dense=True,
                            hide_details=True, classes=cls, suffix=suffix)
        else:
            solara.InputFloat("", value=disp, on_value=_on_input, dense=True,
                              hide_details=True, classes=cls, suffix=suffix)

    def _track():
        with solara.Div(classes=["ww-track"]):
            solara.v.Slider(
                v_model=draft.value, on_v_model=_on_draft,
                min=spec.minimum, max=spec.maximum, step=spec.step,
                dense=True, hide_details=True, thumb_label=False,
            )
            solara.HTML(tag="div", classes=["ww-tick"], unsafe_innerHTML="",
                        style=f"left:calc({_T['thumb_px']//2}px + "
                              f"{_pct(spec, spec.default):.4f}*(100% - {_T['thumb_px']}px))")

    with solara.Div(classes=["ww-slider"]):
        if is_gated:
            # gated layout: [checkbox+title] / [value … delta] / [track]
            with solara.Div(classes=["ww-hd", "ww-hd-gated"]):
                with solara.Div(classes=["ww-gate"]):
                    solara.v.Checkbox(                      # circular check, app style
                        v_model=enabled.value, on_v_model=enabled.set,
                        label=spec.gate_label, dense=True, hide_details=True,
                        ripple=False, color="#3B6FD4",
                        off_icon="mdi-checkbox-blank-circle-outline",
                        on_icon="mdi-check-circle",
                    )
            if on:
                with solara.Div(classes=["ww-valrow"]):     # line 2: value … delta
                    _value_input()
                    solara.HTML(tag="span", unsafe_innerHTML=_delta_html(spec, draft.value))
                _track()                                     # line 3: track
        elif spec.layout == "inline":
            # inline layout: [label fixed-w] [track flex] [editable value] — one line.
            # The fixed label width aligns every track down a column.
            with solara.Div(classes=["ww-hd-inline"]):
                solara.HTML(tag="span", classes=["ww-ilabel"],
                            attributes={"title": spec.title}, unsafe_innerHTML=spec.title)
                _track()
                _value_input()
        else:
            # stack layout: title: value … delta / track
            with solara.Div(classes=["ww-hd"]):
                solara.HTML(tag="span", classes=["ww-title"],
                            unsafe_innerHTML=f"{spec.title}:")
                _value_input()
                solara.HTML(tag="span", classes=["ww-spacer"], unsafe_innerHTML="")
                solara.HTML(tag="span", unsafe_innerHTML=_delta_html(spec, draft.value))
            _track()
