# Phase 1 Summary — Mock Provider + Streaming-Correct Passthrough (No Detection)

> **This document was reconstructed after the fact** from the implementation, commit history, tests, architecture documentation, and other repository evidence. Unlike later phase summaries, it was not written contemporaneously during Phase 1 — no `docs/PHASE_1_SUMMARY.md` was produced at the time, and no record of that omission or its cause survives in `docs/DECISIONS.md` or elsewhere. This gap was found and disclosed during the Phase 7 consistency audit (`docs/DECISIONS.md`, 2026-07-23).
>
> Every claim below is backed by one of: a commit's diff/message, a currently-passing test, `BUILD.md`'s own Phase 1 specification, or a `docs/DECISIONS.md` entry dated within Phase 1's timeframe (2026-07-18). Where a later phase summary's convention (e.g. "What you must do manually") calls for information that leaves no trace in the repository — what a human actually ran, what they were told to do — that section is marked as not reconstructable rather than filled in with a plausible guess. Nothing below describes a conversation, a motivation, or a design discussion that isn't directly evidenced this way.

## What was built

Six numbered tasks. The task numbers below are directly evidenced for Tasks 2, 4, 5, and 6 (cited verbatim in later commit messages and one `docs/DECISIONS.md` entry, below); Tasks 1 and 3 are inferred by commit order and elimination, not found stated explicitly anywhere, and are marked as such.

### Task 1 (number inferred by position) — Exception hierarchy, correlation IDs, FAIL_MODE dispatch

Commit `45f7b98`, 2026-07-18.

| File(s) | Purpose |
|---|---|
| `src/core/exceptions.py` | `GatewayError`/`UpstreamError` — the root of the typed exception hierarchy later phases extend |
| `src/core/fail_mode.py` | `resolve_failure()` — the `FAIL_MODE` open/closed dispatch mechanism, in `core` rather than `pipeline` (see Key design decisions) |
| `src/core/types.py` | `CorrelationId` (`NewType`) |
| `tests/unit/test_exceptions.py`, `tests/unit/test_fail_mode.py` | Direct tests for both |

### Task 2 — Sliding-window scaffold and pathological chunking

Commit `8f7bc22`, 2026-07-18. Number confirmed by commit `3b7fc03`'s message ("composing SSEEventParser, SlidingWindow, and chat_stream (Tasks 2 and 4)").

| File(s) | Purpose |
|---|---|
| `src/core/chunking.py` | `split_into_n_chunks` — shared splitting logic, reused later by the mock upstream (Task 3) rather than reimplemented |
| `src/pipeline/sliding_window.py` | `SlidingWindow` — buffers response text, releases only what's provably outside the lookahead margin. No substitution logic yet, per `BUILD.md`'s explicit Phase 1 scope ("No substitution logic yet, but the seam exists and is tested") |
| `tests/unit/test_chunking.py`, `tests/unit/test_sliding_window.py` | Chunk-boundary torture tests: 1/2/3/N-way splits, zero-content chunks |

### Task 3 (number inferred by position) — Mock upstream

Commit `27cdefa`, 2026-07-18.

| File(s) | Purpose |
|---|---|
| `src/mock_upstream/main.py` | Standalone FastAPI app serving `/v1/chat/completions`, streaming and non-streaming, echoing the last message's content back |
| `src/mock_upstream/chunking.py` | Mock-only `chunking.n` request field driving exact N-way pathological splits (via `core.chunking`); a real OpenAI SDK call never sends this field and gets a word-ish default split instead |
| `tests/fixtures/openai_stream_capture.jsonl`, `.md` | A hand-built SSE fixture the mock's shape is validated against — the commit message states explicitly this is "not a live capture — no paid key used anywhere" |
| `tests/integration/test_mock_upstream.py`, `tests/integration/test_mock_upstream_fixture_shape.py`, `tests/unit/test_mock_chunking.py` | Direct tests |

### Task 4 — SSE parsing and re-serialization

Commit `f01696e`, 2026-07-18. Number confirmed by commit `3b7fc03`'s message (see Task 2 above).

| File(s) | Purpose |
|---|---|
| `src/proxy/sse_framing.py` | Generic WHATWG SSE line/event parsing, correct under arbitrary fragmentation (including a `\r\n` pair split exactly across two `feed()` calls) |
| `src/proxy/chat_stream.py` | OpenAI chat-completion-chunk semantics on top of raw SSE: `parse_event()` extracts `delta.content`, raising `UpstreamError` only for genuinely malformed top-level data — never for a chunk that legitimately carries no content; `serialize_content_delta()` re-serializes a possibly-different string back into the original envelope without mutating it |
| `tests/unit/test_chat_stream.py`, `tests/unit/test_sse_framing.py`, `tests/integration/test_sse_window_integration.py` | Unit tests for both layers plus an integration test composing them with `SlidingWindow` under arbitrary fragmentation |

The commit message documents a named, deliberate Phase 1 simplification, quoted directly: *"a known Phase 1 simplification (carrier-envelope selection for re-buffered text) rather than solving the general span-attribution problem, which is Phase 3's."*

### Task 5 — The gateway's real `/v1/chat/completions` route

Commit `3b7fc03`, 2026-07-18. Number confirmed directly by `docs/DECISIONS.md`'s "Phase 1 task sequencing" entry (2026-07-18), which describes inserting "Phase 1 Task 5" for this work.

| File(s) | Purpose |
|---|---|
| `src/proxy/upstream_client.py` | Injected `httpx.AsyncClient` factory |
| `src/proxy/routes.py` | Composes `SSEEventParser`, `SlidingWindow`, and `chat_stream` (Tasks 2 and 4) into a working streaming and non-streaming route |

That same `docs/DECISIONS.md` entry records why this task exists at all: the original Phase 1 task breakdown bundled the upstream client and route handler into what became Task 4, and when Task 4's scope narrowed to SSE parsing only, "the remainder of that bundle ... was not re-assigned to any task, leaving a silent gap in front of the SDK compatibility task" — caught, per the entry, "before any code was written for the compatibility test, by checking `app/main.py`'s actual state."

The commit message also records the connection-failure/timeout status-code design later audited and extended in Phase 7 (`docs/DECISIONS.md`, 2026-07-23): failures are handled before `StreamingResponse` commits its status, "so they still become real 502/504s; failures discovered mid-stream fall through to flush-and-terminate-honestly instead, since the 200 status can no longer change by then" — and confirms `UpstreamError`'s fixed status-code mapping, not `fail_mode.resolve_failure()`, was "the correct architectural boundary before implementation," per that day's `docs/DECISIONS.md` entry on `FAIL_MODE`'s scope.

### Task 6 — OpenAI SDK compatibility tests

Commit `202267a`, 2026-07-18 (tagged `v0.2.0`). Number confirmed directly by the `docs/DECISIONS.md` "Phase 1 task sequencing" entry ("the OpenAI SDK compatibility test (now Task 6)").

| File(s) | Purpose |
|---|---|
| `tests/integration/test_openai_sdk_compatibility.py` | `AsyncOpenAI` + `httpx.ASGITransport` drives the real, unmodified SDK against the real gateway in-process — non-streaming, streaming, and streaming under forced pathological upstream chunking via the SDK's own `extra_body` |

This test is `BUILD.md`'s own Phase 1 gate ("I run the OpenAI SDK against `localhost:8080` in mock mode, stream a response, and it is byte-identical to what the mock sent") encoded as an automated, repeatable test rather than a manual step. It is part of the current test suite and passes as of this document.

## Defects found and fixed during this phase

Directly quoted or closely paraphrased from the commits that found and fixed each one — not reconstructed from any other source:

- **Commit `27cdefa`**: "Fixes a real FastAPI startup crash (`response_model` inference on a `Union[StreamingResponse, dict]` return type) and two mypy Optional-indexing errors caught by full validation, not just style checks."
- **Commit `3b7fc03`**: "Fixes a real data-loss bug found by the test suite: the carrier envelope for window-released text was tracked as 'the last event seen' rather than 'the last event whose envelope can hold content' — since the mock's final pre-`[DONE]` event is always the content-less `finish_reason` chunk, every response shorter than the window's lookahead was silently emptied. Also closes an unguarded `parse_event()` call on the mid-stream-drop fallback path that could have crashed the generator on a malformed trailing fragment."
- **Commit `202267a`**: "Fixes a real bug the SDK test caught immediately: the `finish_reason` chunk has no content key, so Task 5's carrier-envelope fix correctly excluded it from carrying text — but as a side effect it was never forwarded to the client at all, silently dropping `finish_reason` for every response shorter than the window's lookahead. Now held separately and forwarded, unmodified, after the final content flush and before `[DONE]` — late enough to preserve ordering, but no longer dropped."

## Key design decisions and why

Sourced directly from `docs/DECISIONS.md` entries dated within Phase 1's timeframe and from the commit messages above — not reconstructed narrative:

- **`FAIL_MODE` has no default value** (`docs/DECISIONS.md`, 2026-07-18, "FAIL_MODE: closed is the defensible default, but has no configured default"). `open` fails safe for availability but unsafe for privacy; `closed` fails safe for privacy but unsafe for availability; a coded default either way would still be "making the choice silently, on the operator's behalf." The same entry states the mechanism (`resolve_failure()`) is not consumed for real until Phase 2, since no detector exists yet.
- **`resolve_failure()` lives in `src/core/fail_mode.py`, not `src/pipeline/`** (commit `45f7b98`): "ARCHITECTURE.md's own failure taxonomy calls FAIL_MODE a Tier 2 (detect-layer) concern, and CLAUDE.md files it as a system-wide security invariant alongside the logger, not a pipeline behavior — placing it in pipeline would force `detect/` to import upward across the frozen layering boundary once Tier 2 needs it."
- **`UPSTREAM_BASE_URL` is required in both mock and live modes, with no code-level default** (commit `3b7fc03`): "the mock-mode value is documented explicitly in `.env.example` instead, per earlier correction against hidden defaults."
- **Upstream connection failures/timeouts are mapped to fixed status codes via `UpstreamError`, not routed through `FAIL_MODE`** (commit `3b7fc03`, and `docs/DECISIONS.md`, 2026-07-18): confirmed as the correct architectural boundary before implementation, on the reasoning that `FAIL_MODE` governs detector failures specifically, and upstream failures have their own separate, fixed handling.
- **A dedicated Task 5 was inserted for the gateway route and upstream client** (`docs/DECISIONS.md`, 2026-07-18, "Phase 1 task sequencing"), correcting a gap in the original task breakdown rather than any change to `BUILD.md`, `ARCHITECTURE.md`, or `CLAUDE.md` — the entry states directly that those three source documents were checked and found "mutually consistent," and that none of them subdivide Phase 1 into the numbered tasks used for tracking.
- **`split_into_n_chunks` lives in `src/core/chunking.py`, not duplicated in the mock upstream** (commit `8f7bc22`): "so the mock upstream (Task 3) can reuse the identical splitting logic instead of a second implementation."

## Definition of Done — cross-checked against `BUILD.md`'s Phase 1 checklist

`BUILD.md` (lines 142-148) lists six Phase 1 Definition-of-Done items. Checked against the current repository state, not a historical record of what was verified at the time:

- [x] `openai` Python SDK pointed at the proxy works unmodified, streaming and non-streaming — `tests/integration/test_openai_sdk_compatibility.py` (Task 6), currently passing.
- [x] Mock upstream runs offline with zero keys — `src/mock_upstream/main.py` makes no outbound network call of any kind.
- [x] Chunk-boundary tests pass, including a string split across 3+ chunks — `tests/unit/test_sliding_window.py`, `tests/unit/test_chunking.py`, `tests/unit/test_mock_chunking.py`, currently passing.
- [x] Upstream errors and timeouts propagate with sane status codes — `src/proxy/routes.py`'s `httpx` translation (extended in the Phase 7 failure-path audit, `docs/DECISIONS.md`, 2026-07-23); covered today by `tests/integration/test_chat_completions_route.py`.
- [x] `FAIL_MODE` implemented and its behaviour documented in `docs/DECISIONS.md` — `src/core/fail_mode.py`; `docs/DECISIONS.md`, 2026-07-18, "FAIL_MODE: closed is the defensible default, but has no configured default."
- [ ] Summary + state updated — **not done at the time** (this document is the retroactive substitute; `PROJECT_STATE.md` itself was never created at all, per the Phase 0 decision documented in `docs/PHASE_0_SUMMARY.md` and `docs/DECISIONS.md`).

## How to verify

Present-tense — these commands exercise Phase 1's surviving code today, through the current test suite, not a historical verification transcript:

```powershell
.\tasks.ps1 test          # full suite, includes every test file listed above
pytest tests/integration/test_openai_sdk_compatibility.py -v
pytest tests/unit/test_sliding_window.py tests/unit/test_chunking.py tests/unit/test_mock_chunking.py -v
```

## What you must do manually

Not reconstructable. No record survives of what manual verification, if any, was performed at the time, and inventing a plausible-looking list would misrepresent it as historical fact.

## Known limitations / deliberately deferred

- **No detection of any kind** — `BUILD.md`'s own Phase 1 title states this directly ("NO DETECTION"). Bytes pass through unmodified; Phase 2 adds Tier 1.
- **Carrier-envelope selection for re-buffered text is a named Phase 1 simplification**, not the general span-attribution problem — stated directly in commit `f01696e`'s message, deferred explicitly to Phase 3.
- Everything Phase 0 had already deferred and not touched by Phase 1's own scope (see `docs/PHASE_0_SUMMARY.md`'s own list) remained open through this phase too.

## What Phase 2 did

Tier 1 detection (checksum-validated Aadhaar/PAN/IFSC/UPI/vehicle-registration/card/email/phone) and FF1 format-preserving surrogates over the request path — documented in full in `docs/PHASE_2_SUMMARY.md`, tagged `v0.3.0`.
