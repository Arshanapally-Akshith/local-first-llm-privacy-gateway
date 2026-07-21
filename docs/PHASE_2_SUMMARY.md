# Phase 2 Summary — Tier 1 Detection + FF1 Surrogates (Request Path Only)

Six tasks, one phase. Tasks 1–5 built detection, precedence, and
surrogate generation in isolation; Task 6 wired them into an actual
`sanitize()` pipeline running on the live proxy route.

## What was built

### Task 1 — Core detection infrastructure

| File(s) | Purpose |
|---|---|
| `src/core/types.py` (`Offset`, `Span`, `EntityType`, `Tier`) | Domain types for detection — an offset is not a bare `int`, a span is not a tuple |
| `src/detect/detector.py` | `Detector` protocol every Tier-1 (and future Tier-2) detector implements |
| `src/detect/registry.py` | Explicit, ordered Tier-1 detector registry — not import-time self-registration |
| `src/detect/tier1/checksum.py` | Single shared Verhoeff + Luhn implementation |
| `src/detect/tier1/aadhaar.py`, `card.py` | First two Tier-1 detectors, checksum-gated |

### Task 2 — Remaining Tier-1 detectors

| File(s) | Purpose |
|---|---|
| `src/detect/tier1/pan.py`, `ifsc.py`, `upi.py`, `vehicle_registration.py`, `email.py`, `phone.py` | The remaining six entity types, each candidate-regex + structural/checksum-gated |

### Task 3 — Span precedence

| File(s) | Purpose |
|---|---|
| `src/detect/precedence.py` | The one documented overlap-resolution rule — Tier 1 wins, then longest match, then registration order (see `docs/DECISIONS.md`, 2026-07-21) |

### Task 4 — Structural JSON field walker

| File(s) | Purpose |
|---|---|
| `src/pipeline/field_walker.py` | Generic recursive body traversal (`walk`) + offset-safe rebuild (`rebuild`); the only schema-specific behavior is a JSON-string unwrap for fields literally named `arguments` |

### Task 5 — FF1 surrogate engine

| File(s) | Purpose |
|---|---|
| `src/surrogate/ff1.py` | Literal NIST SP 800-38G FF1, verified against official test vectors |
| `src/surrogate/mixed_radix.py`, `mixed_radix_ff1.py` | Mixed-radix place-value encoding + cycle-walking over a binary covering domain, for entities with mixed letter/digit positions |
| `src/surrogate/domains/aadhaar.py`, `card.py`, `pan.py`, `ifsc.py`, `phone.py`, `vehicle_registration.py` | Six FF1 domains — the six FF1-eligible Tier-1 types |
| `src/surrogate/key_provider.py`, `engine.py`, `registry.py` | Injected key derivation, encrypt/decrypt orchestration, domain lookup by entity type |

### Task 6 — Sanitize wiring + request-path integration

| File(s) | Purpose |
|---|---|
| `src/detect/cascade.py` | Runs the full Tier-1 cascade + precedence for one text region |
| `src/pipeline/sanitize.py` | The request-path orchestrator: walk → detect → encrypt → rebuild |
| `src/proxy/routes.py`, `app/main.py` | Wires `sanitize()` into the live route; adds correlation-id generation, `KeyProvider` DI, a `SurrogateDomainError → 500` handler, and a non-object-body → 400 guard |
| `src/mock_upstream/main.py` | Logs the raw received body, so the acceptance gate is manually demonstrable |

**Scale at the end of Phase 2:** 50 source files under `src/` and
`app/`, 44 test files, 366 tests passing.

## Key design decisions and why

Full reasoning for each lives in `docs/DECISIONS.md`; this is the
index.

- **Regex candidate, then checksum/structural gate — never regex
  alone.** Every Tier-1 detector follows this shape (Task 1–2): a
  12-digit run is a *candidate* Aadhaar, not a detected one, until
  Verhoeff says so. This is what keeps false-positive rate near zero
  on any isolated digit run.
- **Mixed-radix cycle-walking for non-uniform domains** (Task 5): PAN,
  IFSC, Vehicle Registration, and Phone mix letter and digit
  positions at different radixes; each is combined into one integer
  via place-value encoding, then FF1-permuted over the smallest binary
  domain covering it. Aadhaar and Card, both uniform-radix, use plain
  FF1 directly.
- **Aadhaar reserved-range requirement retired as mathematically
  unsatisfiable** (`docs/DECISIONS.md`, 2026-07-20): proven by
  pigeonhole that no stateless, deterministic, invertible construction
  can satisfy it, for any reserved range large or small. The residual
  is documented in `docs/LIMITATIONS.md`, not hidden.
- **UPI ID and email deferred to Phase 3's session map**
  (`docs/DECISIONS.md`, 2026-07-20): neither has a fixed, finite
  domain FF1 requires, and forcing one into a padded fixed-length
  domain would leak the original value's approximate length through
  the padding pattern. Detected today, but hard-fail (`500`) on
  substitution rather than a forced-fit surrogate or a silent
  pass-through.
- **Span precedence is a strict, judgment-free priority tuple**
  (`docs/DECISIONS.md`, 2026-07-21): `(tier, -length,
  detector_registration_index)`, sorted once. No confidence weighting,
  no coverage maximization — those would each reintroduce exactly the
  kind of runtime judgment call precedence exists to remove.
- **`sanitize()` calls `rebuild()` exactly once, after every region
  succeeds.** A request body is either fully sanitized or never
  forwarded — there is no code path where a partially-sanitized body
  reaches the upstream client, because a `SurrogateDomainError`
  anywhere in the walk propagates before `rebuild()` ever runs.
- **FAIL_MODE deliberately not wired into Tier-1 calls this phase.**
  Tier 1 is pure regex + checksum — no I/O, no model, no declared
  failure exception. Wrapping it in a broad `except Exception` to
  route through FAIL_MODE would mean catching an unnamed type, which
  CLAUDE.md's error-handling rule forbids. Real consumption is
  deferred to Phase 4, where Tier 2 (GLiNER) has an actual failure
  mode (timeout, model unavailable).
- **Correlation ID generation has one owner:** `new_correlation_id()`
  in `src/core/types.py`, called once at ingress in the route handler
  — not generated inline, so the scheme has a single place to change.
- **A non-object JSON body is rejected with `400` before `sanitize()`
  ever sees it.** Caught during Task 6's own review: a syntactically
  valid but non-object body (a JSON array, string, or number) used to
  reach the detection/FF1 pipeline unvalidated and crash on an
  internal assertion instead of failing cleanly.

## Interview takeaways

- **Verhoeff and Luhn were each verified against externally-published
  reference vectors before being trusted for detector tests** — not
  just tested for internal self-consistency. Trusting your own code's
  output as proof of itself is exactly the failure mode CLAUDE.md
  warns the Phase 5 benchmark generator against; the same discipline
  applied here, one phase earlier.
- **`Detector` is a structural `Protocol`, not an `ABC`.** A test's
  mock detector doesn't need to inherit from anything defined in
  `src/detect/detector.py` — consistent with CLAUDE.md's SOLID
  guidance to prefer `Protocol` over ABCs for seams.
- **`\b\d{12}\b` rejecting a match inside a longer digit run is a
  deliberate, testable property**, not an accident of the regex
  engine — worth being able to explain why a 25-digit blob produces
  zero Aadhaar candidates rather than one truncated one.
- **The Aadhaar test fixture (`234567890124`) is Verhoeff-valid but
  never claimed to be UIDAI reserved-range-compliant** — that
  requirement turned out to be unsatisfiable entirely (see Key design
  decisions above), so the distinction became moot, but the fixture's
  own docstring said so from Task 1, before that was known.

## Field coverage

BUILD.md's Phase 2 requirement is to sanitize the *whole* request
body, not just `messages[].content`, and to record the field list
deliberately (originally specified as "write the list into
`PROJECT_STATE.md`" — that file doesn't exist by design, per
`docs/PHASE_0_SUMMARY.md`; this section is its replacement for this
requirement, per that same decision).

`field_walker.walk()` (`src/pipeline/field_walker.py`) does not
enumerate a fixed field list at all — it recursively walks **every**
`dict`/`list` node in the body and yields **every** string-valued
leaf, with exactly one schema-specific exception: a field whose path's
last segment is literally `arguments` gets one transparent JSON-string
unwrap attempt (OpenAI encodes function-call arguments as a JSON
string, not a nested object). This is a stronger guarantee than a
fixed enumerated list: a field this project's authors didn't
anticipate is still found, not silently skipped.

Proven by test, not just asserted, against every field category
BUILD.md names:

- **System prompt** — `test_entity_in_system_prompt_is_caught`
  (`tests/unit/test_sanitize.py`)
- **Message content, all roles** — covered throughout
  `tests/unit/test_sanitize.py` and `tests/integration/test_sanitize_integration.py`
- **Tool/function definitions** —
  `test_pan_and_aadhaar_in_a_tool_definition_never_reach_upstream_plaintext`
  (`tests/integration/test_sanitize_integration.py`) — the literal
  Phase 2 gate scenario
- **Function-call arguments (JSON-string-encoded)** —
  `test_entity_inside_tool_call_arguments_json_string_is_caught`
  (`tests/unit/test_sanitize.py`)
- **Consistency across locations** —
  `test_the_same_identifier_gets_the_same_surrogate_in_every_json_location`
  proves the same real value produces the *same* surrogate wherever it
  appears in one request (message content, tool description, and
  tool-call arguments simultaneously) — the practical payoff of FF1
  being a stateless, keyed permutation rather than a per-occurrence
  substitution.

`tool-result` messages and `name` fields are not schema-special-cased
either — they fall under the same generic string-leaf traversal and
are covered by construction, not by a dedicated test per field name.

## Manual verification gate

BUILD.md's Phase 2 gate: curl a real-format Aadhaar and PAN inside a
**tool definition** (not the user message); the mock upstream's log
must show valid-format surrogates, never the real values.

```powershell
# Terminal 1 — mock upstream
copy .env.example .env
# edit .env: set FPE_KEY, SESSION_TTL, FAIL_MODE (FAIL_MODE=closed recommended)
.\tasks.ps1 mock

# Terminal 2 — gateway
.\tasks.ps1 run

# Terminal 3 — the gate
$body = @'
{
  "model": "gpt-4",
  "messages": [{"role": "system", "content": "You are a helpful assistant."}],
  "tools": [{"type":"function","function":{"name":"lookup_customer","description":"Look up a customer by Aadhaar 234567890124 or PAN AAAPL1234C.","parameters":{"type":"object","properties":{}}}}],
  "stream": false
}
'@
Invoke-RestMethod -Uri http://127.0.0.1:8080/v1/chat/completions -Method Post -ContentType "application/json" -Body $body
```

**Expected:** Terminal 1 prints a line starting `mock upstream
received body: ...` whose `tools[0].function.description` contains a
different 12-digit value and a different 10-character PAN-shaped value
than the ones sent — never `234567890124` or `AAAPL1234C` verbatim
anywhere in that line. Both surrogates are format/checksum-valid for
their type (a Verhoeff-valid 12-digit Aadhaar shape; a
5-letter/4-digit/1-letter PAN shape).

This was run and verified during Task 6's implementation. Re-running
it yourself before tagging is the actual sign-off BUILD.md's phase
protocol calls for — this document reports that it passed, not that
you don't need to check.

## Definition of Done

- [x] Each entity type has positive + negative + near-miss tests (bad
      checksum → not detected) — all 8 detectors, verified
- [x] FF1 round-trips: `decrypt(encrypt(x)) == x` for every Tier-1
      type, property-tested — all 6 FF1 domains
      (`tests/property/test_ff1_roundtrip.py`)
- [x] Surrogates are format-valid and checksum-valid for their type
- [x] Span precedence rule implemented, tested with a deliberate
      overlap, **documented** — `docs/DECISIONS.md`, 2026-07-21
- [x] Field-coverage test: PII planted in a tool definition and a
      system prompt is caught
- [x] Aadhaar reserved-range requirement retired per `DECISIONS.md`
      (proven unsatisfiable); residual documented in
      `docs/LIMITATIONS.md` in its place
- [x] Summary + state updated — this document; `PROJECT_STATE.md`
      remains intentionally absent per the Phase 0 decision, replaced
      by this file plus `docs/DECISIONS.md` and git history

**Gate:** verified — see Manual verification gate above.

## Known limitations / deliberately deferred

Full detail in `docs/LIMITATIONS.md`. Summary:

- Aadhaar surrogates may coincide with an issuable number's shape
  (mathematically unavoidable, low-single-digit-percent residual)
- UPI ID and email addresses are detected but hard-fail (`500`) rather
  than being sanitized — no surrogate domain until Phase 3
- Detection is canonical-form only — no obfuscation resistance yet
  (Phase 6)
- No unstructured-entity detection — names, organizations, addresses
  pass through completely unsanitized (Tier 2 is Phase 4)
- No response-path sanitization/rehydration yet — request path only,
  per Phase 2's explicit scope (Phase 3)
- Ingress-surrogate re-encryption is not yet prevented — invisible in
  every single-turn test this phase, must be closed by Phase 3's
  multi-turn DoD

## What Phase 3 will do

Session Map, Rehydration, Multi-Turn Integrity — "the hard phase":

- A session-scoped in-memory map for Tier-2-class entities (built now,
  populated in Phase 4), TTL-bounded, thread-safe under concurrent
  requests on the same session
- Collision handling at assignment time, forced-tiny-list tested
- Rehydration through the sliding window, including surrogates split
  across chunk boundaries
- Ingress-surrogate recognition — closing the gap named above
- A rehydration-fidelity harness measuring, per category, what
  fraction of surrogates come back in a matchable form
- Conservative matching, by design — documented as a deliberate
  rehydration-oracle tradeoff, not a quality shortfall

## What you must do manually

- Personally re-run the Manual verification gate above before treating
  Phase 2 as closed — this document reports that it passed once, it
  isn't a substitute for your own sign-off
- Push these commits to `origin/main`
- Decide when to tag `v0.3.0`
