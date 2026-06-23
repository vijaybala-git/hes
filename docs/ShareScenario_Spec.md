# WhyWatt — "Share My Scenario" Feature Spec

**Status:** 📋 PROPOSED — not yet scheduled.
**Builds on:** Phase 4.5b "Export & Load" (the `export_config` / `apply_config` / envelope layer).
**Deployment context:** HuggingFace Space (Docker, ephemeral filesystem, behind `*.hf.space` proxy).
**Last updated:** 2026-06-22 — initial draft.

---

## 1. Overview

Let an advocate capture the current scenario as a **link** they can paste into an email, a chat,
or printed material. Opening the link restores the exact scenario in a fresh browser.

This is delivered in **two phases that share one payload format**, so Phase 1 is never thrown away:

| Phase | Feature | Store | Identity | Link looks like |
|-------|---------|-------|----------|-----------------|
| **1** | Share via URL (stateless) | none — state lives *in* the URL | none | `…/?s=H4sIAAAA…` (long) |
| **2** | Short URL + Save scenarios | Supabase (Postgres) | **none** — the link *is* the key | `…/?s=ab12cd` (short) |

The **only** difference between the two phases is the transport: Phase 1 stuffs the payload into
the URL; Phase 2 stores the same payload server-side and puts a short slug in the URL. The
encode/decode/apply logic is identical. Phase 2 is a backend swap behind a stable interface,
not a rewrite.

> **No-identity principle (applies to both phases).** "Save my scenarios" does **not** mean
> accounts, login, or per-user data. A saved scenario is just a short link the user keeps. Whoever
> holds the link can open it. There is no concept of "my" scenarios beyond the links a user
> chooses to keep. This keeps us out of auth, PII, and GDPR scope entirely.

---

## 2. What already exists (do not rebuild)

| Piece | Location | Role in this feature |
|-------|----------|----------------------|
| `export_config()` | `src/ui/state.py:392` | snapshot persistent reactives → values dict |
| `apply_config()` | `src/ui/state.py:384` | apply values dict → reactives (REPLACE semantics) |
| `merge()` | `src/ui/config.py:29` | `factory ⊕ values` — a *delta* applies like a full snapshot |
| `factory_defaults()` | `src/ui/config.py:21` | the baseline to diff against |
| `make_envelope()` | `src/ui/config.py:79` | versioned wrapper (`schema_version`, `name`, `values`) |
| `validate()` | `src/ui/config.py:73` | flags unknown keys (forward-compat safety) |
| Export/Load dialogs | `src/ui/layout.py:593–655` | existing ⚙ Settings menu; Share UI lives beside these |
| Proxy headers | `Dockerfile:11–12` | `UVICORN_PROXY_HEADERS` + `FORWARDED_ALLOW_IPS` already set |

---

## 3. The payload (shared by both phases)

### 3.1 Delta, not full snapshot

Encode **only keys whose value differs from `factory_defaults()`**:

```python
def scenario_delta() -> dict:
    base = factory_defaults()
    cur  = export_config()["values"]         # already scoped to _DEFAULTS
    return {k: v for k, v in cur.items() if not _eq(v, base[k])}
```

Rationale (decided in evaluation, do not re-litigate):
- **Short URLs** — a typical scenario changes a handful of sliders → a few hundred chars encoded.
- **Forward-compatible** — keys added in a later phase are absent from old links, so they pick up
  the *new* factory default instead of pinning a stale value.
- **Self-healing** — `apply_config()` already filters to `k in _DEFAULTS`; removed/renamed keys in
  an old link are ignored, never crash.

### 3.2 Encode / decode pipeline

```
delta → make_envelope(delta) → json.dumps → gzip → urlsafe_b64encode → "?s=<blob>"
"?s=<blob>" → urlsafe_b64decode → gunzip → json.loads → apply_config(merge(env["values"]))
```

All stdlib (`json`, `gzip`, `base64`). No new dependency in Phase 1.

### 3.3 Edge cases to handle in the delta diff (`_eq`)

- **Float normalization** — `65.0` vs `65` must NOT register as a diff. Normalize numeric
  equality (e.g. compare `round(float(a), 6)`), not raw `!=`.
- **Transient reactives must not leak.** Before building, audit `_DEFAULTS` for UI-only keys
  (`detail_open`, `*_expanded`, `chart_left/right`, `device_chart_home`). If any are in
  `_DEFAULTS`, exclude them from the share payload via an explicit `SHARE_EXCLUDE` set so a
  shared link doesn't carry "I had the dryer panel open." **(First task — verify this.)**
- **`zip_code` / climate** — *belongs* in the payload (it changes reference city + climate). Confirm
  it stays included.
- **Derived / auto-seeded reactives produce PHANTOM deltas** (found during the Phase-1
  prototype). Even with zero user edits, `scenario_delta()` currently reports 2 changes because
  the live "effective" state diverges from the static factory JSON:
  - `gas_cagr_pct_a` (and the elec/`_b` CAGR siblings): `_seed_eia_cagr()` (`ui/sim.py`) overwrites
    the JSON default on load with the **ZIP's utility CAGR** (PG&E → 7 vs JSON 8). It is
    *ZIP-derived*, so it's redundant in the delta whenever `zip_code` is already present — and
    re-seeding on the recipient's load can race with the applied value (the ordering hazard).
  - `gasoline_climate_cost_per_gallon`: the slider (`step=0.05, min=0.50`) **snaps** the JSON
    default `1.69` → `1.70` on first render, so it looks changed.

  The link still round-trips correctly (these re-derive/re-snap identically on the recipient), but
  the "N changed settings" count is wrong and links carry junk. **Decision needed** (see §3.3a).

### 3.3a Choosing the delta baseline (open decision)

Two viable fixes for the phantom-delta problem:

| Option | What | Trade-off |
|--------|------|-----------|
| **A. Effective baseline** (recommended) | Capture the baseline once at startup *after* the app's onload seeding/snapping has run on the default ZIP, and diff against that. | Most correct; but the seeded CAGR is ZIP-dependent, so the baseline must be recomputed per ZIP or the CAGR keys special-cased. |
| **B. Exclude derived keys** ✅ **APPLIED** | Added `SHARE_DERIVED` (`elec_cagr_pct_a/b`, `gas_cagr_pct_a/b`) to `config.py`; `share.scenario_delta()` omits `SHARE_EXCLUDE | SHARE_DERIVED`. Fixed the snap mismatch by setting the gasoline climate-rate slider `step` `0.05 → 0.01` so it represents the documented `1.69` (config + regression masters unchanged). | Simple; loses *manual* CAGR overrides from the link (acceptable — rare, and the value re-seeds close). |

**Result (verified live):** a fresh default scenario now reports **0 changed settings** and an
empty `{}` payload. Covered by `test_delta_excludes_zip_derived_cagr` and
`test_slider_can_represent_documented_climate_cost` in `tests/test_share.py`.

### 3.4 Versioning

The envelope already carries `schema_version` (currently `1`). Decode must tolerate a missing or
higher version gracefully (apply what it can via `validate()`, surface a soft warning, never crash).

---

## 4. Module layout

New module `src/ui/share.py` — pluggable store behind a stable interface so Phase 2 is a drop-in:

```python
# src/ui/share.py
def scenario_delta() -> dict: ...
def encode(delta: dict) -> str: ...        # delta → url-safe blob
def decode(blob: str) -> dict: ...         # blob → values dict (already merged-ready)

class ShareStore(Protocol):
    def put(self, delta: dict) -> str:     # returns the "?s=" param value
    def get(self, key: str) -> dict | None # param value → values dict

class InlineStore:   # Phase 1 — payload IS the key (no backend)
    def put(self, delta): return encode(delta)
    def get(self, key):   return decode(key)

class SupabaseStore: # Phase 2 — slug ↔ row; falls back to InlineStore on any error
    ...
```

UI/router wiring reads `?s=` once on mount and calls `apply_config(merge(store.get(param)))`.
The active store is selected by env (`SHARE_STORE=inline|supabase`), defaulting to `inline`.

---

## 5. Phase 1 — Share via URL (stateless)

### 5.1 Scope

- `src/ui/share.py` with `scenario_delta` / `encode` / `decode` / `InlineStore`.
- **Share button + dialog** next to the existing Export… in the ⚙ Settings menu
  (`src/ui/layout.py` Masthead, ~line 699). Dialog shows the full URL in a read-only field +
  a **Copy** button (clipboard via a small JS injection; `navigator.clipboard.writeText`).
- **Router read on load:** in `Page()` (`src/ui/layout.py:978`), use `solara.use_router()` to read
  `router.search`, and if `s=` is present, decode + apply **exactly once** before first render.

### 5.2 The one risky part — call it out

Solara is server-side over a websocket. Reading the *initial* query string and applying it exactly
once (no flicker, no re-apply loop on every rerender) is the only genuinely fiddly task.
**Prototype this first**, before building the dialog. Use a one-shot guard (`solara.use_memo` /
a "consumed" reactive) so the apply fires once per page load.

### 5.3 Constraints / decisions

- Use **query (`?s=`)**, never fragment (`#…`) — the server cannot see the fragment.
- URL length: delta keeps it small; cap encoded length and, if exceeded, show "scenario too large
  to link" (should never happen in practice; guards against a pathological full-diff).
- No backend, no storage, no secrets. Links are self-contained and never expire.

### 5.4 Acceptance criteria

1. Change ≥5 controls → Share → copy link → open in a clean/incognito browser → **every changed
   control matches**, and untouched controls sit at factory default.
2. A bare URL with no `?s=` loads normally (no error).
3. A corrupt/truncated `?s=` value shows a non-fatal message and loads factory defaults.
4. A link generated before adding a new reactive still opens; the new control shows its default.
5. Round-trips through the **HuggingFace** deployment (proxy), not just `solara run` locally.

---

## 6. Phase 2 — Short URL + Save Scenarios (Supabase)

### 6.1 Scope

All three behaviors, same payload:

1. **Short URL** — `SupabaseStore.put(delta)` inserts a row, returns a slug → `?s=ab12cd`.
2. **Save my scenarios** — a "saved" scenario is *just a short link the user keeps*. Optionally a
   client-side "My links" list stored in `localStorage` (name + slug), so a user sees scenarios
   they saved on *this device* — still **no server-side identity**.
3. **Open by slug** — `SupabaseStore.get(slug)` reads the row → apply.

### 6.2 Store schema (Supabase / Postgres)

```sql
create table scenarios (
  id         text primary key,        -- random 6–8 char slug
  payload    jsonb not null,          -- the delta envelope (same as Phase 1 blob, decoded)
  name       text,                    -- optional user label
  created_at timestamptz default now()
);
```

- **Slug:** random url-safe 6–8 chars; retry on unique-constraint collision. Never auto-increment
  (leaks volume, guessable).
- **Access:** secrets in **HuggingFace Space secrets** (`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`),
  read via `os.environ`. Because Solara runs server-side, the key never reaches the browser.
  Talk to PostgREST with `requests` (no async/SDK friction with Solara's loop).

### 6.3 Risks / required mitigations

- **RLS / abuse.** Public insert is a spam/storage vector. Enable Row-Level Security: insert-only,
  select-by-id only. Add a **payload size cap** and a lightweight **rate limit**. Low traffic
  expected, but do not ship with RLS off.
- **Free-tier pause.** Supabase free projects pause after ~7 days of inactivity; they resume on
  first request. Any live traffic keeps it warm. **Document this** as an operational note.
- **Dependency / link durability.** Once short links exist, they depend on the Supabase project
  staying alive. If the project is deleted or rotated, **every short link breaks** — whereas
  Phase 1 inline links are immortal. Therefore: **`SupabaseStore.get` falls back to treating the
  param as an inline blob** if it isn't a known slug, so Phase 1 links keep working forever and a
  store outage degrades (long links still shareable) rather than 500s.

### 6.4 Acceptance criteria

1. Share → short link (`?s=<≤8 chars>`) → opens in clean browser → scenario restored.
2. A Phase 1 long inline link **still opens** after Phase 2 ships (fallback path).
3. With Supabase unreachable, Share gracefully falls back to an inline long link (no crash).
4. Slug collision path covered by a test (forced duplicate → retry → success).
5. "My links" list (if built) persists across reloads on the same device and never appears on
   another device (proves no server identity).

---

## 6b. Security & input validation — IMPLEMENTED ✅

A shared link changes the threat model: a tampered payload is attacker-crafted and
victim-clickable. The Load path was already safe from **code execution** (JSON-only;
`apply_config` whitelists keys to `_DEFAULTS` — no `eval`/`pickle`/attribute injection).
The gap was **bad data**: no type or range checks. That is now closed by a sanitize layer.

**`config.sanitize(values) -> (clean, warnings)`** (`src/ui/config.py`, Layer 3) is the gate
every untrusted payload passes through. `apply_config()` now calls it automatically, so both
the existing file-drop Load **and** the future share-URL load are protected. Rules:

| Check | Action |
|-------|--------|
| `len(values) > MAX_KEYS` (200) | reject whole payload (front-line DoS guard) |
| Unknown key (not in `_DEFAULTS`) | drop |
| Transient UI key (`SHARE_EXCLUDE`: `*_expanded`, `chart_*`, `detail_open`, …) | drop — a link can't hijack the recipient's view |
| Wrong type (bool/number/string mismatch vs factory default) | drop |
| Non-finite number (`NaN`/`Inf`) | drop |
| Number out of `RANGES[k]` | **clamp** (e.g. `years` pinned to ≤30 — kills the array-sizing DoS) |
| String > `MAX_STR_LEN` (64), bad enum value, or non-5-digit `zip_code` | drop |

A dropped/clamped key reverts to its factory value via `merge()`, so a partially-bad payload
still loads a coherent scenario; `warnings` lets the UI say "some settings were ignored"
without ever crashing. **`years` is the key DoS field** (it sizes the simulation arrays) and is
clamped to `[1, 30]`. Decode-side caps (base64 input length + gunzip output size, the
decompression-bomb guard) live in the Phase-1 `share.py` decode and are listed in §5.1.

Covered by `tests/test_share_validation.py` (15 tests): the critical invariant is
`test_factory_defaults_pass_clean` — every legitimate factory/profile value survives sanitize
unchanged, proving the ranges never reject a valid config.

---

## 7. Architecture decisions (do not re-litigate)

| Decision | Choice | Reason |
|----------|--------|--------|
| Payload | **Delta** vs factory, not full snapshot | short URLs, forward-compatible, self-healing |
| Transport param | **Query `?s=`**, not fragment | server must read it (Solara is server-side) |
| Encoding | `gzip` + `urlsafe_b64`, stdlib | no new dep in Phase 1 |
| Store interface | `put/get` Protocol, env-selected | Phase 2 is a drop-in, not a refactor |
| Identity | **None, ever** | a saved scenario = a link; no accounts/PII/auth |
| Phase 2 store | Supabase (Postgres + PostgREST) | free tier, REST = no async friction, RLS available |
| Secrets | HF Space secrets, server-side only | key never reaches browser |
| Back-compat | Supabase `get` falls back to inline decode | Phase 1 links immortal; store outage degrades |
| Versioning | reuse envelope `schema_version` | old links self-heal via `validate()` |
| Untrusted input | `sanitize()` in `apply_config` (drop/clamp, never raise) | shared link is attacker-crafted; bad data must not crash/DoS recipient |
| Out-of-range numbers | **clamp** (not reject) | keeps near-miss intent; pins DoS fields like `years` |
| Transient keys on import | always dropped (`SHARE_EXCLUDE`) | a link must not hijack the recipient's open panels / charts |

---

## 8. Recommended order of work

1. ~~**Audit `_DEFAULTS`** for transient/derived keys → define `SHARE_EXCLUDE`~~ ✅ **Done** —
   `SHARE_EXCLUDE` defined in `config.py` (8 `*_expanded` + `chart_left`/`chart_right`/
   `device_chart_home`/`detail_open`); `sanitize()` drops them on import.
2. ~~**Input validation layer** (`sanitize()` + tests)~~ ✅ **Done** — see §6b.
3. **Prototype the Solara router read** — apply `?s=` once on load on the real HF deploy (§5.2).
4. Build `share.py` (`scenario_delta`/`encode`/`decode`/`InlineStore`) + unit tests (round-trip,
   float-normalize, corrupt blob, forward-compat with an unknown key). Decode must cap base64
   input length + gunzip output size (decompression-bomb guard) before `json.loads`.
4. Share dialog + Copy button in the ⚙ Settings menu.
5. Ship Phase 1. Gather usage. Only then start Phase 2.
6. Phase 2: `SupabaseStore` + schema + RLS + slug/collision tests + inline fallback.

---

## 9. Out of scope

- User accounts, login, OAuth — explicitly excluded by the no-identity principle.
- Editing/deleting shared scenarios after creation (links are immutable snapshots).
- Multi-utility / income-qualified rebates and other Phase 3 items — orthogonal.
