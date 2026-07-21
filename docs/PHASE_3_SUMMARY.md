# Phase 3 Summary — Session Map, Rehydration, Multi-Turn Integrity

BUILD.md called this "the hard phase." Six tasks: Tasks 1–2 built the
session map and name allocator in isolation; Task 3 wired ingress
recognition into the request path; Task 4 built the rehydration engine
and wired the response path; Task 5 built the rehydration-fidelity
harness; Task 6 is this closeout — verifying every Phase 3 DoD item
explicitly, closing the two proofs earlier tasks flagged as belonging
to "the final integration task," and recording the documentation this
phase owes.

## What was built

### Task 1 — Session Store Core

| File(s) | Purpose |
|---|---|
| `src/core/clock.py` | Injected `Clock` protocol + `FakeClock`-style testability, replacing any inline `datetime.now()` |
| `src/session/session.py` | `Session` — per-session state, its own lock, sliding TTL, the known-surrogate registry |
| `src/session/store.py` | `SessionStore` — lifecycle only (create/lookup/evict), lazy TTL eviction, LRU capacity cap, two independent locks that are never held together |
| `src/session/known_surrogate.py` | `KnownSurrogate` — typed metadata a session records about a surrogate it minted (never about a real value) |

### Task 2 — Name Allocator

| File(s) | Purpose |
|---|---|
| `src/session/names.py` | `DEFAULT_NAME_CANDIDATES` — a small, explicitly-placeholder finite name list (Phase 4 replaces it with a production-sized one) |
| `Session.allocate_or_lookup_name()` / `lookup_real_name()` (`session.py`) | One atomic, locked check-existing/shuffle/probe/commit sequence; collision-avoidance at assignment time |
| `NameListExhaustedError` (`src/core/exceptions.py`) | Real, immediate-caller exception for a genuinely exhausted candidate list |

### Task 3 — Ingress Surrogate Recognition

| File(s) | Purpose |
|---|---|
| `src/detect/cascade.py` | `ResolvedSpan`, session-aware `detect()` — marks a span as `is_ingress_surrogate` if this session already minted it |
| `src/pipeline/sanitize.py` | Never re-encrypts an ingress-recognised span; records every newly-substituted surrogate into the session |
| `src/proxy/routes.py` | Required `X-Session-Id` header, fail-closed if missing; `SessionStore` wired in as a process-wide FastAPI dependency |

### Task 4 — Rehydration Engine + Response Path Wiring

| File(s) | Purpose |
|---|---|
| `src/pipeline/rehydrate.py` | `rehydrate()` (streaming) / `rehydrate_body()` (non-streaming) — exact-substring rehydration against a session's known-surrogate registry; `REQUIRED_WINDOW_LOOKAHEAD` derived from real domain/name data |
| `src/pipeline/sliding_window.py` | `transform` seam — applied to the *retained buffer*, before the release-length check, so a match split across arbitrary chunks is still caught whole |
| `src/proxy/routes.py` | Wires `rehydrate`/`rehydrate_body` into both response paths; fixes a real `Content-Length` staleness bug the rehydrated non-streaming body exposed |
| `src/surrogate/domain.py` + all 6 domain files | `max_surrogate_length` — each domain's own cited maximum output length |
| `src/surrogate/registry.py` | `max_registered_surrogate_length()` |
| `src/session/session.py` | `known_surrogate_snapshot()` |
| `src/core/exceptions.py` | `RehydrationError` — a real, immediate-caller invariant-violation type |

### Task 5 — Rehydration-Fidelity Harness

| File(s) | Purpose |
|---|---|
| `rehydration_fidelity/runner/taxonomy.py` | BUILD.md's 7 named response-form categories, each a deterministic surrogate transform |
| `rehydration_fidelity/runner/run.py` | Runs every category against a sample of `PERSON` surrogates, writes the committed, commit-stamped artifact |
| `rehydration_fidelity/results/latest.json` | The measured result (see below) |
| `tasks.ps1` | New `rehydration-fidelity` task |

### Task 6 — Integration & Closeout

| File(s) | Purpose |
|---|---|
| `tests/integration/test_phase_3_gate.py` | The two proofs earlier tasks deferred: 50-concurrent-HTTP-request, one-session; the literal 5-turn, chunked, decorated/partial-name gate scenario |
| `docs/LIMITATIONS.md` | Two new entries: session continuity is process-local; session ids are routing keys, not credentials |
| `docs/DECISIONS.md` | Explicit "oracle tradeoff" decision entry (BUILD.md's own named DoD item) |
| `src/proxy/routes.py` | Module docstring now points at both new `LIMITATIONS.md` entries where the session header is handled |

**Scale at the end of Phase 3:** 63 source files under `src/`, `app/`,
and `rehydration_fidelity/`; 53 test files; 465 tests passing.

## Key design decisions and why

Full reasoning for each lives in `docs/DECISIONS.md`; this is the index
for Phase 3's entries specifically.

- **Two independent locks, never held together** (Task 1): `SessionStore`'s
  own lock protects only its `dict`; each `Session`'s own lock protects
  only that session's state — so a burst of requests on *different*
  sessions never serialises behind one session's work.
- **Lazy-only eviction + a deterministic LRU capacity cap** (Task 1):
  no background sweeper (forbidden by this phase's own architectural
  decision); a hard cap bounds worst-case memory from unbounded unique
  session ids, which lazy TTL alone cannot.
- **One atomic `allocate_or_lookup_name()`, not two separately-locked
  calls** (Task 2): splitting "check free" from "claim it" reopens the
  exact collision race the DoD forbids.
- **Ingress recognition lives in the detection cascade, not a
  pipeline-level wrapper** (Task 3): ARCHITECTURE.md's own Detection
  Pipeline component already names this as its responsibility.
- **`X-Session-Id`: required, fail-closed, no derived fallback**
  (Task 3): matches this project's "no silent security defaults"
  pattern, applied to the one piece of required request-level
  configuration Phase 3 introduces.
- **Transform-in-buffer, not transform-on-fragment** (Task 4): the
  correctness argument for why rehydration must run on the *retained*
  sliding-window buffer, never on an already-released fragment — the
  single most load-bearing decision in this phase.
- **Non-streaming responses are rehydrated too, and the stale
  `Content-Length` bug that surfaced while wiring it** (Task 4): a real
  gap (and a real bug) caught during implementation, not scoped in by
  BUILD.md's own SSE-focused framing.
- **Window lookahead derived from real domain/name data, not a guess**
  (Task 4): `SurrogateDomain.max_surrogate_length` + the name list's own
  max, recomputed automatically if either source changes.
- **`rehydration_fidelity/` as a new top-level directory** (Task 5):
  mirrors `benchmarks/`/`adversarial/`'s own established pattern for a
  first-class, committed measurement artifact — flagged and confirmed
  before implementation, since BUILD.md's Repository Conventions tree
  named neither directory nor scope for it.
- **The rehydration-oracle tradeoff, recorded as its own decision, not
  left implicit** (Task 6): BUILD.md's Phase 3 DoD names this as its
  own checklist item; ARCHITECTURE.md already held the position, but it
  had never been written down as a Phase 3 decision in its own right
  until this closeout.

## Measured result: the rehydration-fidelity harness

`rehydration_fidelity/results/latest.json` (regenerate with
`.\tasks.ps1 rehydration-fidelity`):

| Category | Hit rate |
|---|---|
| exact | 100% |
| decorated | 100% |
| case_shifted | 0% |
| partial | 0% |
| abbreviated | 0% |
| transliterated | 0% |
| reasoned_about | 0% |

This is the honest, expected shape of a conservative, exact-substring
matcher (see the oracle-tradeoff decision above) — reported as a
finding, not tuned to look better, per CLAUDE.md's "honest measurement
over favourable measurement."

## Manual verification gate

A full 5-turn scripted conversation is impractical to replay reliably
by hand via `curl`/`Invoke-RestMethod` — this phase's actual gate proof
is the automated integration test below, which is the stronger,
repeatable equivalent of a manual walkthrough (same principle Phase 2's
summary already applied: an automated test that proves the scenario is
more credible than a report that a human ran it once).

```powershell
# Terminal 1 — mock upstream
copy .env.example .env
# edit .env: set FPE_KEY, SESSION_TTL, FAIL_MODE (FAIL_MODE=closed recommended)
.\tasks.ps1 mock

# Terminal 2 — gateway
.\tasks.ps1 run

# Terminal 3 — a quick single-turn smoke test: real Aadhaar in, real Aadhaar
# back out, never plaintext to the mock (watch Terminal 1's log line).
$body = @'
{
  "model": "gpt-4",
  "messages": [{"role": "user", "content": "My Aadhaar is 234567890124"}],
  "stream": false
}
'@
Invoke-RestMethod -Uri http://127.0.0.1:8080/v1/chat/completions -Method Post `
    -Headers @{"X-Session-Id" = "manual-check-1"} -ContentType "application/json" -Body $body
```

**Expected:** the JSON response's `choices[0].message.content` reads
`My Aadhaar is 234567890124` — the real value — while Terminal 1's mock
upstream log line shows a *different* 12-digit value in the body it
actually received.

**The full gate — 5 turns, forced 3-way chunking, decorated and partial
name forms, 50-concurrent-request proof:**

```powershell
.\venv\Scripts\python.exe -m pytest tests\integration\test_phase_3_gate.py -v
```

**Expected:** both tests pass —
`test_fifty_concurrent_requests_on_one_session_lose_no_surrogate_mapping`
and
`test_five_turn_conversation_with_forced_chunking_and_decorated_partial_names`.

**Also verify the full suite and the fidelity harness:**

```powershell
.\tasks.ps1 check                    # ruff + mypy --strict src + pytest
.\tasks.ps1 rehydration-fidelity     # regenerates rehydration_fidelity/results/latest.json
```

**Expected:** `ruff` reports "All checks passed!"; `mypy --strict src`
reports "Success: no issues found in 57 source files"; `pytest` reports
465 passed; the fidelity harness reprints the same seven category
rates shown above, and `results/latest.json` is unchanged (deleting and
regenerating it must reproduce the same numbers, per CLAUDE.md).

## Definition of Done

- [x] Concurrency test: 50 parallel requests on one session, no
      duplicate/lost mappings — Session-level:
      `tests/unit/test_session_names.py::test_concurrent_allocation_of_distinct_real_values_loses_nothing_and_collides_nothing`,
      `tests/unit/test_session.py::test_concurrent_record_surrogate_calls_lose_nothing`.
      HTTP-level (Task 6):
      `tests/integration/test_phase_3_gate.py::test_fifty_concurrent_requests_on_one_session_lose_no_surrogate_mapping`
- [x] Collision test with a forced 3-name list: no two entities share a
      surrogate —
      `tests/unit/test_session_names.py::test_collision_forced_tiny_list_no_two_real_values_ever_share_a_surrogate`
- [x] Split-surrogate rehydration passes across 1/2/3/N chunk splits —
      `tests/unit/test_sliding_window.py::test_transform_catches_a_match_split_across_n_chunks_before_any_of_it_is_released`
      (n=1,2,3,5,10,25),
      `tests/integration/test_rehydrate_integration.py::test_streaming_response_rehydrates_a_surrogate_forced_across_n_chunks`
      (n=1,2,3,12)
- [x] Multi-turn test: 5-turn conversation, no double-encryption, no
      corruption (Task 6) —
      `tests/integration/test_phase_3_gate.py::test_five_turn_conversation_with_forced_chunking_and_decorated_partial_names`
- [x] Rehydration-fidelity harness runs and emits per-category numbers
      to an artifact —
      `rehydration_fidelity/results/latest.json`,
      `tests/unit/test_rehydration_fidelity.py`
- [x] Session TTL eviction tested; map is empty after expiry —
      `tests/unit/test_session_store.py::test_get_or_create_replaces_an_expired_session_with_a_fresh_empty_one`
- [x] Oracle tradeoff written into DECISIONS.md (Task 6) —
      `docs/DECISIONS.md`, 2026-07-21, "The rehydration-oracle tradeoff:
      conservative exact-match matching, chosen explicitly, recorded as
      its own decision"
- [x] Summary + state updated — this document; `PROJECT_STATE.md`
      remains intentionally absent per the Phase 0 decision

**Gate:** verified — see Manual verification gate above.

## Known limitations / deliberately deferred

Full detail in `docs/LIMITATIONS.md`. Summary, Phase 3's own additions:

- Rehydration is exact-match only — measured at 100% for exact/decorated
  forms, 0% for case-shifted/partial/abbreviated/transliterated/
  reasoned-about. A deliberate, documented tradeoff (the rehydration
  oracle), not a defect.
- Session continuity holds only within a single gateway process —
  `uvicorn --workers N` or any multi-instance deployment silently
  breaks it. Out of scope; would require its own non-persistent shared
  backend and its own threat-model review.
- `X-Session-Id` is a routing key, not a credential — nothing
  authenticates who presents it. Not being fixed in this phase: the
  gateway has no caller-identity model at all yet for a session id to
  meaningfully bind to.
- Everything already carried over from Phase 2 that Phase 3 didn't
  touch: canonical-form-only detection (Phase 6), no unstructured
  (Tier 2) detection yet (Phase 4), the Aadhaar reserved-range residual.

## What Phase 4 will do

Tier 2 Detection (GLiNER):

- A GLiNER-class model, CPU, for `PERSON` / `ORG` / `ADDRESS`
- Wired into the cascade behind Tier 1 (Tier 1 wins on overlap, per the
  Phase 2 precedence rule)
- Name surrogates from a *real*, production-sized candidate list via
  the session map this phase built — `DEFAULT_NAME_CANDIDATES`
  (`src/session/names.py`) is explicitly a placeholder and needs
  replacing
- Cold start warmed at startup, measured and reported separately from
  steady-state latency
- Tier-hit instrumentation: which tier resolved each span

Everything Phase 3 built for `PERSON`/`ORG`/`ADDRESS` ahead of a real
detector existing — `Session.allocate_or_lookup_name()`, the rehydration
engine's name-map branch, the fidelity harness — needs no changes for
Phase 4 to land; only the *source* of those spans changes, from direct
test/harness seeding to a real detector's output.

## What you must do manually

- Personally re-run the Manual verification gate above before treating
  Phase 3 as closed
- Source a properly-sized, responsibly-curated production name list
  before Phase 4 starts wiring real Tier-2 detection to
  `allocate_or_lookup_name()` — `src/session/names.py`'s own docstring
  already flags this as deferred, explicitly, to whoever picks up
  Phase 4
- Push these commits to `origin/main`
- Decide when to tag `v0.4.0`
