# Decisions

Append-only. One entry per non-obvious call: decision, alternatives
considered, why, date. Never edit a past entry — supersede it with a
new one that links back.

---

## 2026-07-18 — FAIL_MODE: closed is the defensible default, but has no configured default

**Decision.** `Settings.fail_mode` (`open` | `closed`) has no default
value in code; the operator must set it explicitly in `.env`, or the
gateway refuses to start (`src/core/config.py`).

**Alternatives considered.**
- Default to `open` (forward unsanitised on any detector failure):
  fails safe for availability, fails unsafe for privacy — a detector
  timeout under load would silently leak PII at exactly the moment of
  stress, which is the one moment this system exists to guard against.
- Default to `closed` (503 on any detector failure): fails safe for
  privacy, fails unsafe for availability — the gateway becomes a
  single point of failure for the caller's LLM access, silently,
  without the operator having consciously chosen that trade-off.
- No default; require explicit configuration (chosen).

**Why.** A privacy product that silently degrades its core guarantee
under load is not a control — ARCHITECTURE.md states the position
plainly: "a silent leak is worse than a loud outage, and ... a
security control that degrades quietly under load is not a control."
But codifying `closed` as *the* default would still be making the
choice silently, on the operator's behalf — the exact failure mode
CLAUDE.md's Configuration Architecture forbids ("No silent security
defaults"). Requiring an explicit choice — with `closed` recommended,
not assumed — keeps the trade-off conscious rather than inherited.

See `src/core/fail_mode.py` for the dispatch mechanism this decision is
implemented by (`resolve_failure()`), including why that mechanism
lives in `core` rather than `pipeline`. **Scope note:** per
ARCHITECTURE.md's Error Handling flowchart, FAIL_MODE governs detector
failures specifically ("Detector fails/times out → FAIL_MODE"). Upstream
failures (4xx/5xx, mid-stream drops) have their own separate, fixed
handling — "propagate verbatim" and "flush and terminate honestly",
respectively — and are not gated by FAIL_MODE. No detector exists yet
in Phase 1, so this mechanism is not consumed for real until Phase 2.

---

## 2026-07-18 — Phase 1 task sequencing: the gateway route was an omitted prerequisite, not an architecture change

**Decision.** Insert a dedicated task (Phase 1 Task 5) to build the
gateway's `/v1/chat/completions` route and upstream client, before the
OpenAI SDK compatibility test (now Task 6). No change to the
architecture, ARCHITECTURE.md, BUILD.md, or CLAUDE.md.

**Alternatives considered.**
- Fold the route/upstream-client work into the SDK compatibility task:
  rejected — bundles two independently-reviewable pieces of work
  (transport wiring; SDK-level verification of that wiring) into one
  commit, against the project's small-commit discipline, and risks
  conflating a route bug with a test bug in the same diff.
- Point the SDK compatibility test at the mock upstream instead of the
  gateway: rejected — would prove SDK-to-mock compatibility while being
  described as gateway compatibility, misrepresenting what the test
  actually establishes.
- Treat the gap as a documentation inconsistency requiring a doc
  change: investigated and ruled out — BUILD.md, ARCHITECTURE.md, and
  CLAUDE.md are mutually consistent; none of them subdivide Phase 1
  into the numbered tasks used for tracking in this build. The gap
  originated entirely in that task breakdown, not in the source
  documents.

**Why.** The original Phase 1 plan bundled the upstream client and
route handler into "Task 4," alongside SSE parsing/re-serialization.
When Task 4's scope was later narrowed to SSE parsing/re-serialization
only, the remainder of that bundle (upstream client, route wiring) was
not re-assigned to any task, leaving a silent gap in front of the SDK
compatibility task, which depends on a working route to test against.
Caught before any code was written for the compatibility test, by
checking `app/main.py`'s actual state rather than assuming the task
breakdown's sequencing was still valid.
