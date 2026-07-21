# Phase 4 Summary — Tier 2 Detection (GLiNER-class) — CLOSED OUT

BUILD.md's Phase 4: `PERSON`/`ORG`/`ADDRESS` detection, wired behind
Tier 1 in the existing cascade, with a real, warmed-at-startup CPU
model. Six tasks: Tasks 1-2 built the Tier-2 seam and integrated the
real GLiNER model; Task 3 wired it into the cascade behind Tier 1;
Task 4 gated Tier-2 failures with `FAIL_MODE`; Task 5 wired all three
Tier-2 types to real session-map surrogates; Task 6 is this closeout —
verifying every Phase 4 DoD item explicitly, closing the one BUILD.md
gate scenario that had no single committed proof, fixing documentation
that had drifted, and recording what this phase cost and left open.

## What was built

### Task 1 — Tier-2 Detector Seam

| File(s) | Purpose |
|---|---|
| `src/detect/tier2/model.py` | `Tier2Model` Protocol + `ModelEntityMatch` — the seam a real model implements; explicitly request-stateless, no caching |
| `src/detect/tier2/detector.py` | `Tier2Detector` — one class, parameterized by `entity_type`, not three near-identical ones; validates a model's offsets before trusting them |
| `src/detect/registry.py` | `get_tier2_detectors(model)` — constructs the three `PERSON`/`ORG`/`ADDRESS` instances, all sharing one injected model |
| `src/core/exceptions.py` | `DetectionError` — real, immediate caller: an out-of-bounds model offset |

Built and fully tested (`tests/unit/test_tier2_detector.py`) against a
fake model — zero dependency on which real model Task 2 would
eventually choose.

### Task 2 — Real Model Integration + Startup Warmup

| File(s) | Purpose |
|---|---|
| `src/detect/tier2/gliner_model.py` | `GLiNERTier2Model` (the real `Tier2Model`) + `get_tier2_model()` DI factory, mirroring `get_key_provider()`'s shape |
| `src/core/config.py` | `NER_MODEL` (defaults to the chosen model), `NER_WARMUP` (defaults `True`) |
| `.env.example`, `requirements.txt` | Documents both new settings; pins `gliner==0.2.27` and `torch==2.13.0+cpu` (CPU-only wheel index, not the default CUDA build) |
| `app/main.py` | A `lifespan` context manager warms the model before the server binds; a load/warm failure propagates and crashes startup, matching this project's existing "fail loudly, before binding" posture for a bad `Settings` value |
| `mypy.ini` | Scoped `ignore_missing_imports` for `gliner` (ships no type stubs) — not a blanket ignore |
| `pytest.ini` | New `real_model` marker, excluded from the default run (`addopts = -m "not real_model"`) |
| `tests/integration/test_tier2_startup_warmup.py` | Fast suite: the lifespan hook's own conditional logic, `_warm_tier2_model` mocked out |
| `tests/integration/test_tier2_real_model.py` | `real_model`-marked: the real model's offsets, empty-input handling, singleton caching, end-to-end with `Tier2Detector`, and the structured startup log line |

**Model selection**, in full in `docs/DECISIONS.md` (2026-07-21, "Tier
2 model selection..."); summarized here because BUILD.md's Phase 4 DoD
names this measurement specifically as something this document must
record.

## Measured result: model selection and the end-to-end memory finding

Three rounds of measurement, each more rigorous than the last, comparing
`gliner_small-v2.1`, `gliner_medium-v2.1`, `gliner_large-v2.1`, and
`gliner_multi_pii-v1` (all Apache-2.0, from the same actively-maintained
`urchade/GLiNER` project).

**Round 1** (one sentence, five candidates, isolated process) ruled out
`gliner_large-v2.1` (slowest, heaviest, not measurably better at
ADDRESS) and surfaced `gliner_multi_pii-v1` as the only candidate to
capture a full multi-component address as one span.

**Round 2** (27-sentence synthetic corpus, gold offsets exact by
construction, `gliner_small-v2.1` vs. `gliner_multi_pii-v1` only):

| Type | `small` exact-match | `multi_pii` exact-match |
|---|---|---|
| PERSON | 15/15 (100%) | 15/15 (100%) |
| ORG | 9/12 (75%) | 11/12 (92%) |
| **ADDRESS** | **0/11 (0%)** | **5/11 (45%)** |

`small` never once produced an exact-match multi-component address in
this corpus (reliable fragmentation); the entire measured aggregate
improvement (exact precision 0.369 -> 0.775; exact recall 0.632 ->
0.816) traces to ADDRESS and, to a lesser extent, ORG — PERSON
detection was already identical between the two. Isolated-process cost:
+78ms warm latency, +491.7MB peak RSS.

**Round 3** (real end-to-end gateway process, `uvicorn app.main:app`,
Windows `Get-Process`, not a script's self-reported number):

| | `gliner_small-v2.1` | `gliner_multi_pii-v1` |
|---|---|---|
| Current (settled) WorkingSet, after warmup | 1279.8 MB | 1533.3 MB |
| **Peak WorkingSet** (transient, during startup only) | 1638.2 MB | 2216.3 MB |
| Private (committed) memory | 1597.0 MB | 2459.3 MB |
| Startup warmup latency | 15.5 s | 24.1 s |

**The full gateway's real peak (2216.3MB) is meaningfully higher than
the model measured in isolation (1678.4MB)** — FastAPI/uvicorn/pydantic
overhead is not negligible on top of the model itself. The steady-state
delta that matters while actually serving traffic is smaller (~253MB);
the larger delta is a one-time transient during the ~15-25s startup
window, not a sustained cost.

**System-context finding, disclosed rather than smoothed over.**
Measured on the actual target machine (7.68GB total RAM), with a
realistic concurrent session (IDE, browser, antivirus, this assistant's
own CLI all running — BUILD.md's "one developer's machine," not an idle
box): only **0.91GB was free system-wide** while the smaller model's
gateway was running. Either candidate's startup transient is genuinely
tight against this — `gliner_small`'s own 1638.2MB peak is already
large relative to 0.91GB free. This reflects the crowded state of a
real, active development session more than a property that uniquely
disqualifies `multi_pii`.

**Decision: continue with `gliner_multi_pii-v1`.** The steady-state RAM
cost is modest (~253MB) and the measured detection-quality improvement
is concentrated and substantial (0% -> 45% exact-match ADDRESS
recovery, more than double exact precision) — exactly the kind of
result CLAUDE.md's "evaluation over feature count" principle exists to
protect. The transient startup-peak finding is real and is not hidden:
it is recorded here, in `docs/DECISIONS.md`, and should be revisited
if Phase 7's real latency/concurrency harness or real deployment
experience shows it to be a genuine problem in practice, not assumed
away now.

### Task 3 — Cascade Wiring

| File(s) | Purpose |
|---|---|
| `src/detect/cascade.py` | `detect()` now takes a required `tier2_model: Tier2Model` and runs `get_tier2_detectors(tier2_model)` alongside Tier 1, through the same, unmodified `precedence.resolve()` |
| `src/pipeline/sanitize.py` | Threads `tier2_model` through `sanitize()` → `_sanitize_region()` → `detect()`, same pattern as `key_provider`/`clock` |
| `src/proxy/routes.py` | `chat_completions()` gains `Depends(get_tier2_model)`, passed to `sanitize()` — reuses Task 2's `@lru_cache`d singleton, no new construction per request |
| `src/detect/tier2/detector.py` | Docstring updated: the "known open item" (same-type overlapping matches) is resolved, not deferred — `precedence.resolve()`'s generic algorithm already handles it correctly |
| `tests/conftest.py` | New autouse fixture overriding the `get_tier2_model` FastAPI dependency with a zero-cost fake for every test — see below |
| `tests/unit/test_cascade.py`, `tests/unit/test_sanitize.py` | Updated for the new required parameter; new coverage for Tier-2-only detection, Tier-1-wins-over-Tier-2 overlap (the BUILD.md gate scenario), same-type Tier-2 overlap resolution, and Tier-2 ingress recognition |
| `tests/integration/test_tier2_real_model.py` | New `real_model`-marked test proving the gate scenario against the actual GLiNER model, not just a fake |

**Scope decision, made explicit before implementing:** this task wires
*detection* only. It does **not** wire real detected `PERSON`/`ORG`/
`ADDRESS` spans to `Session.allocate_or_lookup_name()` — that stays
Phase 4 Task 5's job. Consequence, disclosed rather than discovered
later: any request containing a detectable name/org/address now raises
`SurrogateDomainError` — a clean, existing 500 (`app/main.py`'s
handler), the same failure shape UPI/email already produce today, not
a crash and not a silent leak. Full reasoning and alternatives
considered: `docs/DECISIONS.md`, 2026-07-21, "Tier 2 wired into the
cascade."

**Test-suite fix required by this wiring:** adding
`Depends(get_tier2_model)` to the real route meant every pre-existing
integration test hitting `/v1/chat/completions` through the real `app`
would otherwise load the real GLiNER model at request time — none of
those tests are `real_model`-marked. Fixed with one shared, autouse
`tests/conftest.py` fixture overriding the dependency with a zero-cost
fake; `test_tier2_real_model.py` bypasses FastAPI's DI entirely, so it
is unaffected.

**DoD status this task closes:** "Tier 2 detects names/orgs/addresses"
(cascade now calls it for real), "Cascade precedence tested" (both a
fake-model unit test and a real-model integration test prove Tier 1
wins the BUILD.md gate scenario), "Tier-hit instrumentation" (no new
code needed — `sanitize.py`'s existing `log_event(..., tier=span.tier,
...)` already reports whichever tier resolved a span, and now
genuinely observes `tier=2`).

### Task 4 — FAIL_MODE for Tier-2 Failures

| File(s) | Purpose |
|---|---|
| `src/core/fail_mode.py` | New `get_fail_mode()` — thin `get_settings().fail_mode` factory, mirroring `get_key_provider()`'s shape |
| `src/detect/cascade.py` | `detect()` gains required `fail_mode`/`correlation_id` params; the Tier-2 detection step is wrapped in `try`/`except Exception`, dispatched through `resolve_failure()` — `open` falls back to Tier-1-only spans and logs; `closed` raises `FailClosedError` |
| `src/pipeline/sanitize.py`, `src/proxy/routes.py` | `fail_mode` threaded through, sourced from `Depends(get_fail_mode)` |
| `app/main.py` | New `FailClosedError` → 503 exception handler, fulfilling the mapping `fail_mode.py`'s own docstring named in advance |
| `tests/unit/test_cascade.py`, `tests/unit/test_sanitize.py` | New coverage for both failure shapes (`DetectionError` from a bad offset, and a raw exception from the model call itself — "model unavailable") crossed with both `FAIL_MODE` values |
| `tests/integration/test_chat_completions_route.py` | New HTTP-level tests proving the real 503 (`closed`) and 200 (`open`) status codes |

**The one deliberate exception to "catch the narrowest type you can
name":** the Tier-2 stage is wrapped with a bare `except Exception`,
not a named type — a CPU NER model's own failure modes cannot be
enumerated the way `httpx`'s client-boundary exceptions can. The catch
is kept narrow in scope instead: only the `get_tier2_detectors()` call
is wrapped, nothing else in `detect()`. Full reasoning and alternatives
considered: `docs/DECISIONS.md`, 2026-07-21, "FAIL_MODE gates the
Tier-2 stage."

**DoD status this task closes:** BUILD.md's Phase 4 Task 4 scope —
both named failure shapes ("model unavailable" and a `DetectionError`
from a bad offset) are now gated by `FAIL_MODE`, proven at the cascade
level, the sanitize level, and the real HTTP route (503/200).

### Task 5 — Name-Map Surrogates for PERSON/ORG/ADDRESS

Scope decided explicitly before implementing (per the product owner's
call, not assumed): all three Tier-2 types, not `PERSON` alone —
BUILD.md's Phase 4 gate text names org/address surrogate consistency
explicitly, so this closes Task 3's disclosed gap completely rather
than leaving two of three types permanently unsanitizable.

| File(s) | Purpose |
|---|---|
| `src/session/names.py` | `PERSON` candidates — expanded from Phase 3's 40-entry placeholder to a generated ~5,100-entry pool (72 first names x 71 last names) |
| `src/session/org_names.py` | New — `ORG` candidates, ~4,900 entries (70 root words x 70 suffixes), no real company names |
| `src/session/addresses.py` | New — `ADDRESS` candidates, ~5,040 entries (70 streets x 72 city/states, deterministic house numbers) |
| `src/session/candidates.py` | New registry — `NAME_MAP_ENTITY_TYPES` (shared source of truth, replacing a set `rehydrate.py` used to hardcode alone), `get_candidates()`, `max_candidate_length()` |
| `src/session/rng.py` | New — `get_rng()`, deliberately *not* cached (see below) |
| `src/pipeline/sanitize.py` | Branches surrogate generation by entity type: FF1 (`engine.encrypt` + `record_surrogate`) vs. name-map (`Session.allocate_or_lookup_name()`, which records the `KnownSurrogate` itself) |
| `src/pipeline/rehydrate.py` | Imports `NAME_MAP_ENTITY_TYPES`/`max_candidate_length()` from `candidates.py` instead of its own hardcoded set and `PERSON`-only length; `REQUIRED_WINDOW_LOOKAHEAD` now spans all three pools |
| `src/proxy/routes.py` | `rng: random.Random = Depends(get_rng)`, threaded to `sanitize()` |
| Tests | New: `test_org_names_list.py`, `test_addresses_list.py`, `test_candidates_registry.py`, `test_rng.py`; updated: `test_names_list.py`, `test_sanitize.py` (rng threading, replaced the now-stale `SurrogateDomainError`/"ORG untouched" assumptions with real-surrogate assertions, added a same-session consistency test), `test_chat_completions_route.py` (new PERSON round-trip test) |

**Candidate pools are generated, not hand-typed** — two seed pools
(~70 entries each) combined by cartesian product, the same
"programmatic generation over manual authoring" principle BUILD.md's
benchmark section already mandates. `org_names.py` deliberately excludes
real company names (no Tata/Infosys/Reliance/etc.) and `addresses.py`
uses generic, non-unique street-name patterns — a surrogate that *is* a
specific real entity is a materially worse residual than a low-
probability shape coincidence. Full reasoning: `docs/DECISIONS.md`,
2026-07-21.

**`get_rng()` is deliberately not cached**, unlike every other DI
factory in this codebase (`get_key_provider()`/`get_session_store()`/
`get_tier2_model()`): a shared `random.Random` singleton would be
mutated by concurrent requests on *different* sessions with no lock
protecting it — `Session`'s own lock only covers one session's state. A
fresh instance per call sidesteps the concurrency question at
effectively zero cost.

**A real, if narrow, correctness gap closed along the way:**
`REQUIRED_WINDOW_LOOKAHEAD` was computed from `PERSON`-only candidate
lengths before this task — silently wrong the moment `ADDRESS`
surrogates (structurally longer than "First Last" names) could also
appear on the response path. Now spans all three pools.

**DoD status this task closes:** BUILD.md's Phase 4 bullet "Name
surrogates from the finite name list via the Phase-3 map" — genuinely
true for `PERSON`, `ORG`, and `ADDRESS` now, proven end-to-end
including a real HTTP request/response round trip
(`test_person_span_round_trips_through_the_full_http_request_response_cycle`).

### Task 6 — Integration & Closeout

A repository-wide review before declaring the phase done, the same
checks every prior phase closeout has performed (Phase 3 Task 6):
temporary code, stale comments, duplicated logic, documentation that no
longer matches the code. Three real findings, all fixed rather than
carried forward:

| Finding | Fix |
|---|---|
| BUILD.md's literal Phase 4 gate sentence ("Hinglish sentence with a name, an org, an address, and a PAN...") had no single committed, reproducible test | New `tests/integration/test_phase_4_gate.py`, `real_model`-marked, mirroring `test_phase_3_gate.py`'s own closeout pattern. The Hinglish sentence used was verified against the real model with a throwaway probe *before* the test's assertions were written, not guessed |
| `docs/LIMITATIONS.md`'s UPI/email entry claimed "Resolved in Phase 3" — never true; the entry's own body already said otherwise | Corrected in place, with the correction itself stated, not silently fixed |
| `docs/LIMITATIONS.md`'s "no unstructured-entity detection yet" entry was stale (Phase 4 resolves exactly what it describes) | Marked resolved, kept for history, per this file's own established convention |
| `src/session/session.py`'s `allocate_or_lookup_name()` had a comment claiming "no Tier-2 detector exists yet" to produce a same-value/different-entity_type collision — false as of this phase's own Task 5 | Comment corrected to state the case is now reachable in principle; the underlying engineering call (accept it as a Phase 3 simplification, fix only if it manifests as a real bug) is unchanged |

**Checked and found clean — no fix needed:** no `TODO`/`FIXME`/`XXX`
markers, no `print()`/`breakpoint()` calls, no skipped/`xfail`-marked
tests, no commented-out code, anywhere under `src/`, `app/`, or
`tests/`. `mypy.ini`, `pytest.ini`, `.env.example`, `requirements.txt`
all already reflect Phase 4's additions with no drift. `PROJECT_STATE.md`
remains, correctly, absent — a Phase 0 decision
(`docs/PHASE_0_SUMMARY.md`), reaffirmed at every phase closeout since,
not an oversight of this one.

Full reasoning for all four findings: `docs/DECISIONS.md`, 2026-07-21,
"Phase 4 closeout."

## Manual verification gate

```powershell
# Fast suite (no real model load)
.\tasks.ps1 check                    # ruff --line-length 100 . + mypy --strict src + pytest

# Real-model suite (loads real GLiNER weights - first run downloads them)
.\venv\Scripts\python.exe -m pytest -m real_model -v

# The literal BUILD.md Phase 4 gate, specifically
.\venv\Scripts\python.exe -m pytest -m real_model tests\integration\test_phase_4_gate.py -v
```

**Expected:** `ruff` reports "All checks passed!"; `mypy --strict src`
reports success with zero issues; the fast suite passes in full; the
`real_model` suite passes in full (includes the Phase 4 gate test).

## Definition of Done

- [x] Tier 2 detects names/orgs/addresses in English and Hinglish
      code-switched text — English:
      `tests/integration/test_tier2_real_model.py`; Hinglish, all three
      types in one sentence:
      `tests/integration/test_phase_4_gate.py::test_phase_4_gate_hinglish_name_org_address_and_pan`
      (the sentence was verified against the real model before the test
      was written — see `docs/DECISIONS.md`)
- [x] Cascade precedence tested: a PAN inside a span Tier 2 calls ORG
      resolves per the documented rule — fake-model:
      `tests/unit/test_cascade.py::test_tier1_wins_over_an_overlapping_tier2_span_the_build_md_gate_scenario`;
      real-model:
      `tests/integration/test_tier2_real_model.py::test_cascade_resolves_a_real_tier1_tier2_overlap_tier1_wins`
- [x] Model warms at startup; cold-start cost measured and recorded
      separately — `app/main.py::_warm_tier2_model`, the
      `startup.tier2_model_warmed` log event
      (`tests/integration/test_tier2_real_model.py::test_startup_warmup_logs_a_structured_event_with_positive_latency`);
      measured 15.5s/24.1s warmup, reported separately from steady-state
      RAM (`docs/DECISIONS.md`, Task 2)
- [x] Tier-hit instrumentation emits which tier resolved each span —
      `sanitize.py`'s existing `log_event(..., tier=span.tier, ...)`,
      directly observed for both `tier=1` (PAN) and `tier=2`
      (PERSON/ORG/ADDRESS) in one request by
      `test_phase_4_gate.py`'s own log-record assertions
- [x] Runs on CPU within my RAM budget — measured, not assumed — three
      rounds of measurement culminating in a real end-to-end gateway
      process measurement (`docs/DECISIONS.md`, Task 2). Stated
      honestly, not smoothed: steady-state delta is modest (~253MB),
      but the transient startup peak (~2.2GB) is genuinely tight against
      the measurement machine's available headroom (0.91GB free under a
      realistic concurrent dev session) — disclosed as a real finding,
      with the decision to proceed anyway recorded and reasoned
- [x] Summary + state updated — this document, plus
      `docs/DECISIONS.md` and `docs/LIMITATIONS.md`.
      `PROJECT_STATE.md` remains intentionally absent per the Phase 0
      decision, replaced by phase summaries + `docs/DECISIONS.md` + git
      history, exactly as every prior phase closeout has stated

**Gate:** verified — see Manual verification gate above;
`test_phase_4_gate.py` is the literal, automated equivalent of BUILD.md's
gate sentence, the same "an automated test is the stronger, repeatable
proof" principle Phase 2's and Phase 3's own closeouts already applied.

## Known limitations / deliberately deferred

Full detail in `docs/LIMITATIONS.md`. Summary, Phase 4's own additions
and resolutions:

- **Resolved this phase:** "no unstructured-entity detection" (Phase
  2's gap) — Tier 2 now detects and sanitizes `PERSON`/`ORG`/`ADDRESS`.
- `gliner_multi_pii-v1` misses addresses embedded in Hinglish carrier
  sentences and literal multi-line addresses more often than
  `gliner_small-v2.1` does — a real, measured residual, not hidden.
  Rigorous, dataset-scale measurement of exactly how much is Phase 5's
  job, not this phase's.
- UPI and email still have no surrogate mechanism at all (neither FF1
  nor a name-map candidate pool) — genuinely still open, not resolved
  by any phase so far (a prior version of `docs/LIMITATIONS.md`
  incorrectly claimed otherwise; corrected this phase).
- The name-map candidate pools' generation seed lists (first/last
  names, org roots/suffixes, streets/city-states) are this project's
  own construction, not sourced from an external, independently
  verified dataset — stated plainly.
- A same real-value string submitted under two different `entity_type`s
  within one session silently keeps the first allocation's type
  (`Session.allocate_or_lookup_name()`) — an accepted Phase 3
  simplification, now reachable in principle since real Tier-2 spans
  feed it, not yet observed as a real problem.
- Everything already carried over from Phase 2/3 that Phase 4 didn't
  touch: canonical-form-only Tier-1 detection (Phase 6), the Aadhaar
  reserved-range residual, rehydration's exact-match-only fidelity
  (measured per category in Phase 3), session continuity being
  process-local, session ids being routing keys not credentials.

## What Phase 5 will do

The benchmark (BUILD.md's "first-class deliverable," and the project's
actual contribution — "the proxy is table stakes"). Phase 4 is
functionally complete and closed: Tier 1 + Tier 2 both detect, both
cascade through the documented precedence rule, both are gated by
`FAIL_MODE`, and both have a working surrogate mechanism (FF1 or
name-map) for every entity type this system claims to cover except
UPI/email (a pre-existing, disclosed gap, not a Phase 4 regression).
Nothing built in Phase 4 needs to change for Phase 5 to begin — the
benchmark measures what already exists.

## What you must do manually

- Personally re-run the Manual verification gate above before treating
  Phase 4 as closed
- Push these commits to `origin/main`
- Decide when to tag this milestone (see the suggested tag in the
  closeout report — `v0.4.0` is already taken, tagging Phase 3's own
  closeout commit; this phase's tag is the next one)
