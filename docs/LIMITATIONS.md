# Limitations

States, plainly, what this system does not yet guarantee — CLAUDE.md's
"modest about its own guarantees" standard applied as a living
document. Each entry names the phase that introduced the gap and,
where known, the phase expected to close it. This is not a duplicate
of ARCHITECTURE.md's Security Architecture → Residual risks section
(the frozen, project-wide threat-model list); this file tracks
concrete, currently-true implementation gaps as the phases land.

---

## Aadhaar surrogates may coincide with an issuable number's shape

**Phase 2.**

An Aadhaar surrogate produced by `AadhaarDomain`
(`src/surrogate/domains/aadhaar.py`) is Verhoeff-valid,
format-preserving, deterministic, and invertible — but is not
guaranteed to avoid coinciding with a real UIDAI-issuable number's
*shape*. This was originally a Phase 2 requirement (BUILD.md); it was
retired as mathematically unsatisfiable by **any** stateless,
deterministic, invertible construction — a pigeonhole argument
independent of implementation technique, not a gap specific to this
project's approach. See `docs/DECISIONS.md`, 2026-07-20, "Aadhaar
reserved-range requirement retired as mathematically unsatisfiable,"
for the full proof.

**Residual, stated plainly.** Against an issuable payload space on the
order of 10^11 and public reporting of roughly a billion enrolled
Aadhaars, the a priori chance any single surrogate's shape coincides
with an actually-issued number is low-single-digit percent — an
illustrative order-of-magnitude estimate only, not a cited UIDAI
figure.

**Why this doesn't undermine the privacy property.** The surrogate is
never the real Aadhaar belonging to the person whose data was
sanitized — it is a different, algorithmically-derived value that
happens to share Aadhaar's shape. The residual is a small chance the
surrogate resembles *someone else's* real, valid Aadhaar, not a chance
of leaking the original value.

---

## UPI IDs and email addresses cannot be sanitized yet — they hard-fail instead

**Phase 2. Still open as of Phase 4.** (An earlier version of this
entry said "Resolved in Phase 3" — that was wrong. The session-scoped
map Phase 3 built, and Phase 4 Task 5 wired PERSON/ORG/ADDRESS into, was
never extended to UPI or email. Corrected here, not silently.)

`UpiDetector` and `EmailDetector` are registered and active — a UPI ID
or email address in a request **is detected**. No surrogate domain is
registered for either type in `src/surrogate/registry.py` (FF1 doesn't
fit an unbounded-length domain: NPCI allows a 2–256 character VPA local
part; email has no length bound at all), and neither is registered in
`src/session/candidates.py` either (Phase 4 Task 5's name-map registry
covers only `PERSON`/`ORG`/`ADDRESS` — the three types BUILD.md's Phase
4 scope actually named). See `docs/DECISIONS.md`, 2026-07-20, "FF1
domain resolution," for why UPI/email don't fit FF1, and 2026-07-21,
"Phase 4 Task 5," for why the name-map registry wasn't widened to cover
them too (out of BUILD.md's stated Phase 4 scope).

Detecting one today raises `SurrogateDomainError`, which the gateway
turns into a `500` **before any upstream call is made**
(`app/main.py`'s exception handler; `src/pipeline/sanitize.py` never
calls `field_walker.rebuild()` until every region has succeeded). This
is a hard-fail, not a silent leak — the request is refused rather than
partially sanitized — but it does mean **a request containing a UPI ID
or email address cannot be sanitized and forwarded at all, in any phase
through Phase 4.**

---

## Detection is canonical-form only

**Phase 2. Adversarial robustness is Phase 6.**

Every Tier-1 detector matches exact, unobfuscated, canonical-form text
— `\b\d{12}\b` for Aadhaar, `[A-Z]{5}\d{4}[A-Z]` for PAN, and so on.
Spaced digits (`1234 5678 9012`), dashed digits, number-words,
transliteration, or homoglyphs defeat detection entirely, not
partially — these are regex candidate patterns with no fuzzy fallback.
This is deliberate, per ARCHITECTURE.md: "Tier 1 outputs are the only
ones this system calls guaranteed — with a precise meaning: *if the
entity is present in a canonical, unobfuscated form, it is detected
with certainty*." Measuring which obfuscations bypass detection is
explicitly Phase 6's job (the adversarial suite); Phase 2 does not
attempt to close this gap.

**Measured in Phase 6** (`adversarial/results/latest.md`, regenerate
with `.\tasks.ps1 adversarial`): 8 of the suite's 9 bypass classes —
spaced digits, number-words, base64, PII embedded in code, PII as a
JSON key, split-across-turns, Unicode homoglyphs, zero-width
characters — measured at 100% adversarial leak rate (0% recall) against
every entity type they were tested on, exactly as this entry predicted.
The ninth class, transliterated names, is Tier-2/GLiNER-based rather
than a Tier-1 regex property, and its measured result contradicted this
suite's own prediction: `urchade/gliner_multi_pii-v1` recognised both
tested Devanagari-script name pairs, where a leak was expected based on
this project's already-documented Hinglish-romanization weakness (see
`docs/DECISIONS.md`, 2026-07-22, "a genuine, measured contradiction in
`transliterated_names`"). Every unfixed bypass, per class and per
entity type, is listed in `adversarial/results/latest.md`'s "Bypasses
that still work" section — none are hidden or removed.

**Scope of this measurement, stated plainly.** Every case above applies
exactly one obfuscation technique. Combinations (e.g. base64 together
with zero-width characters, or split-across-turns together with a
homoglyph) have not been measured and must not be assumed to behave the
same as either technique alone — see `docs/DECISIONS.md`, 2026-07-22,
"single-bypass scope."

---

## Tier-2 can misclassify a message's literal `role` field as `PERSON`, corrupting the OpenAI role enum — resolved

**Phase 4 (gap present since Tier-2 was wired in). Discovered in Phase
6, documented, not fixed. Resolved in Phase 7.**

`get_tier2_model().find_entities("user")` returns a `PERSON` match
spanning the entire string — a context-free, 4-character token is
exactly the input zero-shot NER is least reliable on.
`src/pipeline/field_walker.py::_walk()` treats every string-valued
field the same way, including a chat message's `"role"` field (nothing
special-cases it), so `sanitize()` could replace a message's literal
`"role": "user"` with a fabricated person-name surrogate — observed
directly during Phase 6's own live-gateway test runs, e.g. a captured
upstream body containing `{"role": "Krishna Chowdhury", "content":
"..."}`. This corrupted a value the OpenAI wire format requires to be
one of a fixed enum (`system`/`user`/`assistant`/`tool`), and was
unrelated to any deliberate bypass attempt — it could occur on an
entirely ordinary request whenever Tier-2 happened to misfire on the
bare role string.

**Why this was disclosed rather than fixed immediately.** This is a
real defect in the already-shipped, non-adversarial request path,
discovered incidentally by Phase 6's methodology (the first test work
to scrutinize an entire captured request body against real Tier-2
inference, rather than only a message's `content`). Fixing it was out
of Phase 6's own scope (the adversarial suite, not a Phase 4 pipeline
change), and was explicitly deferred by the product owner on being
reported — see `docs/DECISIONS.md`, 2026-07-22, for the full
root-cause, and 2026-07-23 for the fix.

**Did not invalidate any Phase 6 measurement.** Every verifier in
`adversarial/cases/verify.py` checks specific, known field paths
directly, never a fuzzy whole-body search that this corruption could
interfere with — confirmed by direct inspection that no case's `caught`
verdict was affected by it.

**Resolution (Phase 7).** `src/pipeline/protocol_fields.py` declares
the OpenAI wire protocol's closed-vocabulary field positions —
`messages[].role` is the only entry so far — and `sanitize()` skips
detection entirely on a region whose path and value both match a
declared entry, before that region is ever handed to `detect()`. The
exemption is a value-membership check, not a field-name exclusion: a
`role` field holding anything other than one of its five legal values
(`system`/`user`/`assistant`/`tool`/`function`) still gets full
detection, exactly like any other field — so this cannot become a new
channel for smuggling real PII past the gateway through the `role`
position. See `docs/DECISIONS.md`, 2026-07-23, for the alternatives
considered (a key-name exclusion was rejected as unsound) and
`tests/regression/test_role_field_pii_misclassification.py` for the
end-to-end reproduction and fix proof.

---

## No unstructured-entity detection yet (names, organizations, addresses) — resolved

**Phase 2 (gap opened). Resolved in Phase 4.**

Tier 2 (`urchade/gliner_multi_pii-v1`, CPU) now detects `PERSON`,
`ORG`, and `ADDRESS` in free text, wired into the same cascade as Tier
1 (Tier 1 wins any overlap, per the Phase 2 precedence rule — Phase 4
Task 3), gated by `FAIL_MODE` (Task 4), and sanitized via a
production-sized session-map candidate pool for all three types (Task
5) — see `docs/PHASE_4_SUMMARY.md` and `docs/DECISIONS.md` for full
detail. Proven end-to-end, including a genuinely Hinglish/code-switched
sentence, by
`tests/integration/test_phase_4_gate.py::test_phase_4_gate_hinglish_name_org_address_and_pan`.

**Residual, carried forward, not closed by this phase:** GLiNER's own
measured weakness on Hinglish carrier sentences and literal multi-line
addresses (see `docs/DECISIONS.md`, Phase 4 Task 2's three-round
evaluation) — a *quality* residual within Tier 2, not an absence of
Tier 2 detection itself. Rigorous, dataset-scale measurement of exactly
how much is Phase 5's job (the benchmark), not this phase's.

---

## Rehydration is exact-match only; measured at 100% for exact/decorated forms and 0% for every other taxonomy category

**Phase 2 (gap opened). Closed for exact matches in Phase 3 Task 4.
Measured per-category in Phase 3 Task 5.**

Response-path rehydration exists (`src/pipeline/rehydrate.py`, wired
into both the streaming and non-streaming paths in
`src/proxy/routes.py`): every surrogate a session has minted, echoed
back by the upstream in any form that preserves the surrogate's own
characters contiguously — exact, embedded in a larger sentence, or
wrapped in markdown decoration — is rehydrated to its real value, even
when the upstream splits it across an arbitrary number of SSE chunks
(`tests/integration/test_rehydrate_integration.py`).

Matching is exact-substring only — a deliberate, conservative choice,
not an oversight (ARCHITECTURE.md's rehydration-oracle reasoning:
aggressive fuzzy matching would let an attacker induce the gateway into
reinserting real PII into attacker-readable output). The
rehydration-fidelity harness (`rehydration_fidelity/`, BUILD.md's Phase
3 taxonomy: exact, decorated, case-shifted, partial, abbreviated,
transliterated, reasoned-about) measures, per category, what fraction
of a name surrogate round-trips correctly. Current measured result
(`rehydration_fidelity/results/latest.json`, regenerate with
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

This is the expected shape of a conservative, exact-substring matcher,
not a bug: only forms that preserve the surrogate's own characters
contiguously and unmodified are ever caught. A surrogate returned as a
first-name-only fragment, an abbreviation, a case-shifted variant, a
transliteration, or reasoned-about text ("the name starts with A") is
left as a visible surrogate in the response — a measured miss, and the
correct trade per ARCHITECTURE.md, not a defect scheduled to be fixed.

---

## Ingress-surrogate re-encryption — closed

**Phase 2 (gap opened). Closed in Phase 3 Task 3.**

Tier-1 detection previously re-ran from scratch on every request, with
no awareness of session state — a structured surrogate FF1 produced on
an earlier turn, echoed back inside a later turn's request body (e.g.
the assistant's own prior message, replayed by a multi-turn client),
would have been detected as a "new" real entity and re-encrypted into a
surrogate-of-a-surrogate. `src/detect/cascade.py::detect()` now takes
the session and marks any span whose text is already a known surrogate
as `is_ingress_surrogate`; `src/pipeline/sanitize.py` never re-encrypts
those. Proven end-to-end by
`tests/integration/test_sanitize_integration.py::test_a_surrogate_replayed_in_a_later_request_on_the_same_session_is_not_re_encrypted`.
See `docs/DECISIONS.md`, 2026-07-21, "Ingress recognition lives in the
detection cascade, not a pipeline-level wrapper."

---

## Session continuity exists only within a single gateway process

**Phase 3.**

`SessionStore` (`src/session/store.py`) is an in-memory
`dict`-backed singleton, one per running gateway process
(`get_session_store()`'s `@lru_cache`). A session's name map and
known-surrogate registry live only in that process's RAM, for exactly
as long as `SESSION_TTL` and the process itself both allow.

This means session continuity — a surrogate minted on turn 1 being
recognisable on turn 5 — holds only as long as every request in that
conversation reaches the *same* running gateway process. A
multi-worker or horizontally-scaled deployment (multiple `uvicorn`
workers, a process manager restarting the gateway, a load balancer
routing requests to different instances) would route two requests in
one logical conversation to two different processes, each with its own
empty `SessionStore` — the second process has never seen the first
turn's mapping, and Task 3's ingress recognition, Task 4's rehydration,
and Task 2's name allocation would all silently start over as if it
were a brand-new session.

**This is intentional, and out of scope, not an oversight.** A shared
session backend across processes would mean either a shared in-memory
store (defeating "one developer's machine," ARCHITECTURE.md's stated
deployment target) or a networked store — which reintroduces exactly
the "no persistence for PII or the session map" line CLAUDE.md and
ARCHITECTURE.md both draw deliberately (a networked session store is,
functionally, the vault this project's threat model refuses to build).
Multi-worker/distributed deployment is real future work, requiring its
own design (a shared, still-non-persistent backend, e.g. an in-memory
cache with its own TTL semantics) and its own threat-model review — not
a Phase 3 concern, and not something to design speculatively here.

**Practical implication today.** `uvicorn app.main:app` (the documented
single-process run command, `tasks.ps1 run`) is the only deployment
shape this project's session guarantees hold for. Running multiple
gateway worker processes (`--workers N`) or behind a load balancer with
more than one backend instance would silently break session continuity
per-conversation, with no error — a caller would simply see surrogates
that never rehydrate, indistinguishable from an ordinary miss, which is
precisely why this is worth stating rather than discovering later.

---

## Session identifiers are routing keys, not authentication credentials

**Phase 3.**

`X-Session-Id` (`src/proxy/routes.py`) exists to give two requests in
one conversation a shared surrogate map — it is a **correlation key**,
scoping which `Session` object a request's detection and rehydration
read and write. It is not, and was never designed to be, an
authentication or authorization mechanism. Nothing in this gateway
verifies that the caller presenting a given `X-Session-Id` is the same
caller who first created it; nothing rate-limits or signs it; nothing
prevents a second, unrelated caller from supplying the same string.

**Why this matters.** A caller who can guess or observe another
caller's session id (it is sent as a plain, unauthenticated request
header) could read that session's rehydration behaviour indirectly —
e.g. sending a surrogate string back and observing whether it comes
back rehydrated reveals *that this session has a mapping for it*,
though never the surrogate's own reverse-mapped value directly (the
gateway never echoes a bare lookup result; it only ever rehydrates
inline within a full model response). This is a narrower version of
the same rehydration-oracle concern ARCHITECTURE.md already names for
a different attacker position (the upstream model itself); a shared
or guessable session id widens who could attempt it.

**Why this is not being fixed in Phase 3.** Authenticating the *session
id* would only make sense once the gateway authenticates the *caller*
at all — today, per ARCHITECTURE.md's Configuration Architecture, the
gateway accepts any request bearing a syntactically valid
`X-Session-Id` and performs no caller identity check whatsoever
(`UPSTREAM_API_KEY`, when `live` mode is used, authenticates the
*gateway* to the *upstream provider* — the opposite direction).
Binding session ids to a caller identity that doesn't yet exist in this
system's model would be speculative scope, not a fix for something
broken today. Deployments should treat `X-Session-Id` as they would any
other unauthenticated request metadata: generated per-conversation by
a trusted client, not accepted from, or forwarded on behalf of,
untrusted parties.
