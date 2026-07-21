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

---

## 2026-07-20 — FF1 domain resolution: vehicle registration is FF1-eligible; UPI ID and email are not, and wait for Phase 3

**Decision.** Phase 2 Task 5 implements six FF1 surrogate domains:
Aadhaar, PAN, Card, IFSC, Phone, and Vehicle Registration. UPI ID and
email get no surrogate domain in Phase 2 at all —
`src/surrogate/registry.py` raises `SurrogateDomainError` for both,
loudly, rather than silently passing them through or forcing a
technically-dubious fit. Their surrogate generation is deferred to
Phase 3, when the session-scoped name map exists.

**Alternatives considered** (raised originally before Phase 0, parked
explicitly for "right before Task 5"):
- Force all three (vehicle reg, UPI, email) into FF1 now, via a
  padded/canonicalized fixed-length domain: rejected for UPI and
  email specifically — NPCI allows a VPA local part 2-256 characters,
  and email has no length bound at all. A fixed-length pad either
  truncates longer values (data loss) or reveals the original value's
  approximate length through the surrogate's padding pattern (a
  privacy leak in the surrogate mechanism itself). Vehicle
  registration, by contrast, has exactly two known, bounded formats
  (state-code and BH-series) — no different in kind from IFSC's
  two-segment structure — so it does not have this problem.
- Defer all three, including vehicle registration, to keep this
  task strictly to ARCHITECTURE.md's diagram-named FF1 types:
  rejected — vehicle registration has no unbounded-length problem, so
  deferring it anyway would be conservatism without a reason tied to
  the actual constraint.

**Why.** ARCHITECTURE.md's own criterion for the FF1 branch is "fixed
and finite"; for the map branch it is "arbitrary Unicode... unbounded
domain." UPI ID and email match the map criterion, not FF1's — forcing
them into FF1 anyway would be bending the mechanism past what NIST SP
800-38G is meant for, for a privacy property (format preservation)
that a padded surrogate would then partially undermine on its own.
Structurally, the map doesn't exist until Phase 3 either, so deferring
UPI/email isn't purely a preference — implementing them properly
before then isn't possible regardless.

See `src/surrogate/registry.py` and `src/surrogate/domains/` for the
implementation.

---

## 2026-07-20 — Aadhaar reserved-range enforcement deferred: real values are never reserved-range members, which breaks the cycle-walking technique used elsewhere

**Decision.** `src/surrogate/domains/aadhaar.py` FF1-permutes the
11-digit payload and re-derives the Verhoeff check digit, producing a
checksum-valid, correctly round-tripping surrogate — but does **not**
yet guarantee the surrogate falls in UIDAI's documented never-issued
reserved range. `src/surrogate/reserved_ranges.py` was not written
this phase. BUILD.md's Phase 2 DoD item "Reserved-range compliance
test for generated Aadhaar" is therefore not met yet — a known,
stated gap, not an oversight.

**Why this isn't just "add a retry loop."** PAN, IFSC, and vehicle
registration all need their own kind of retry (`mixed_radix_ff1.py`'s
cycle-walking, permuting a value's own output repeatedly under a
*fixed* key/tweak until it lands inside the true domain). That
technique is provably correctly invertible **only because the real
input is always itself a member of the valid-output set** — any real
PAN's own mixed-radix encoding is, by construction, already inside
its true domain. Aadhaar's reserved range breaks this precondition
outright: a *real* Aadhaar number is, by definition, never in the
"never-issued" range — that is the entire meaning of the range. Cycle
walking's forward/backward symmetry (walk forward from `x` until
valid; invert by walking backward from the surrogate until valid)
relies on `x` itself being a valid-set member so that the backward
walk provably lands back on `x` and not on some other, unrelated
reserved-range value earlier in the same permutation cycle. Without
that property, a naive port of the same technique would silently
decrypt to the wrong Aadhaar number for some fraction of inputs —
exactly the class of invisible, silent correctness bug this project's
testing philosophy is built to catch, not one to ship provisionally.

**Alternatives considered** for a correct mechanism (not chosen; needs
design before implementation, not a decision to make silently now):
- Vary the tweak per retry attempt instead of re-permuting the output:
  requires decrypt to know which attempt's tweak was used, which
  nothing currently records or can safely infer without either
  encoding the attempt count somewhere in the (format-preserving,
  fixed-length) surrogate itself, or risking an ambiguous decrypt.
- Freeze a reserved-range-identifying prefix in the surrogate output
  (mirroring IFSC's frozen `'0'`): rejected on inspection — freezing
  digits that would otherwise carry real input information destroys
  bijectivity unless the reserved range's own size is at least as
  large as the real-payload space it needs to represent, which is not
  yet known and plausibly false for a genuinely small reserved block.
- Choose the FF1 domain to be exactly the reserved range's size:
  requires knowing that size precisely, which requires the research
  below regardless.

**Also still required, not done this phase:** verified, citable
research into UIDAI's actual documented reserved/never-issued Aadhaar
ranges. Confident only that Aadhaar numbers never start with `0` or
`1`; no verified source for a specific reserved subrange beyond that
was found or asserted. CLAUDE.md requires this be verified *before*
the generator exists, cited in code — not reconstructed from memory.
If no clean official published range is found when this is picked up,
the fallback is a conservative, clearly-labeled synthetic reserved
subrange of this project's own choosing, stated as such here and in
the code, never presented as UIDAI's own.

**Current behavior:** every Aadhaar surrogate is Verhoeff-valid and
round-trips correctly (`tests/property/test_ff1_roundtrip.py`); none
are yet guaranteed to avoid the issuable range.

---

## 2026-07-20 — Mixed-radix domains (PAN, IFSC, vehicle registration): frozen positions and cycle-walking over a binary covering domain

**Decision.** Where a domain has a position constrained to a small set
of structurally-valid values (PAN's holder-category letter, one of 10
documented codes; phone's leading digit, one of 4) rather than
permuting over that constrained set, the position is frozen — copied
verbatim from input to surrogate, never passed to FF1 at all. Every
other free position across a domain's letters and digits is combined
into one integer via `src/surrogate/mixed_radix.py`'s place-value
encoding, then FF1-permuted over the smallest binary domain
(`2**bits`) covering that integer's true range, via
`src/surrogate/mixed_radix_ff1.py`'s cycle-walking.

**Alternatives considered.**
- Permute frozen positions too, over their true small value set (e.g.
  PAN's category letter as its own radix-10 "digit" representing one
  of the 10 valid codes): more thorough — a surrogate's category
  letter would no longer always match the real value's — but adds
  real mixed-radix complexity for what CLAUDE.md would call a
  negligible privacy gain, since both the real and any permuted
  category value are drawn from the same 10 (or 4, for phone)
  publicly-documented options either way.
- Run FF1 separately per same-radix segment (e.g. PAN's 5 letters as
  one call, its 4 digits as a separate call) rather than combining
  all free positions into one domain: rejected — PAN's 4 free digit
  positions alone are only `10**4`, and IFSC's 4 free bank-code
  letters alone are only `26**4` ≈ 456,976, both below NIST SP
  800-38G's recommended `10**6` domain-size minimum (ARCHITECTURE.md
  already names this exact caveat). Combining across letter/digit
  type boundaries is what gets PAN and IFSC's smallest segments above
  that minimum at all.
- A non-uniform-radix FF1 variant (permuting a mixed-radix digit
  sequence directly, without first collapsing it to one integer):
  more "native," but NIST SP 800-38G's FF1 is specified over a single
  fixed radix; building and trusting a novel mixed-radix variant of a
  cryptographic primitive is a materially bigger correctness risk than
  composing the standard algorithm with a separately-verified,
  independent positional-encoding step.

**Why cycle-walking over binary specifically.** Any uniform radix
works for the covering domain; binary gives the tightest possible
covering (`2**bits` for the smallest `bits` with `2**bits >=
true_size`), minimizing the covering-to-true-size ratio and therefore
the expected number of cycle-walk attempts — empirically ~1 attempt
for PAN/IFSC/vehicle registration's actual domain sizes (`tests/unit/test_mixed_radix_ff1.py`,
`tests/property/test_ff1_roundtrip.py`, 100+ generated examples each,
zero observed failures).

**Also decided in this pass, smaller:** `src/surrogate/key_provider.py`
derives a 32-byte AES-256 key via a plain SHA-256 digest of the
operator-supplied `FPE_KEY` secret, not a password-hardening KDF
(PBKDF2/scrypt/Argon2). `FPE_KEY` is meant to be an operator-chosen
strong secret, not a human-memorable password needing brute-force
resistance, so a hardening KDF's extra iteration cost buys nothing
here.

---

## 2026-07-20 — Aadhaar reserved-range requirement retired as mathematically unsatisfiable; supersedes the entry above

**Decision.** BUILD.md's Phase 2 requirement that FF1-generated Aadhaar
surrogates always fall inside UIDAI's reserved/never-issued number
space is retired. It cannot be satisfied by any deterministic,
stateless, invertible construction — not just the cycle-walking
technique the entry above ruled out, but *any* function at all.
`src/surrogate/domains/aadhaar.py` ships as already implemented:
full-11-digit-payload FF1 permutation, Verhoeff-repaired check digit,
deterministic, stateless, invertible for every input it accepts.
BUILD.md's Phase 2 bullet and DoD item now reflect this; this entry is
the record of why.

**Formal argument (pigeonhole).** Let `U` be the 11-digit payload
space FF1 permutes over (`10^11`). Let `R ⊂ U` be whatever is defined
as the reserved/never-issued range, and `A = U \ R` the issuable
space — by definition of "reserved," every real Aadhaar's payload is a
member of `A`, never `R`. A surrogate generator satisfying the
requirement is a function `E_k : A → R`; invertibility requires `E_k`
be injective. An injective function `A → R` can exist only if `|A| ≤
|R|` — pigeonhole, true of *any* function, not something specific to
FF1 or cycle-walking. Because a reserved/never-issued range is, by its
own definition, a minority carve-out from a space UIDAI needs mostly
intact to issue numbers to 1.4B+ residents, `|A| > |R|` holds for any
legitimate reserved range, official or hypothetical. The requirement
is unsatisfiable independent of implementation technique — no cleverer
construction than cycle-walking was going to fix this.

**Research performed before retiring the requirement** (CLAUDE.md:
verify a UIDAI fact before asserting it, don't reconstruct one from
memory):
- No primary UIDAI document was found stating Aadhaar numbers never
  start with `0` or `1`. It's widely repeated (Medium, state
  IT-department pages, third-party validators) but every trail
  dead-ends in secondary sources restating each other, never a UIDAI
  circular, RTI reply, or spec page. Not usable as a cited UIDAI fact.
- One genuine, citable, official reserved range *does* exist: UIDAI's
  own developer/testing page publishes five test UIDs, all sharing the
  prefix `9999` (e.g. `999941057058`), explicitly reserved for
  sandbox/integration testing —
  https://uidai.gov.in/en/916-developer-section/data-and-downloads-section/11350-testing-data-and-license-keys.html.
  Fixing a 4-digit prefix over the 11-digit payload gives `|R| = 10^8`.
- Applying the pigeonhole argument to this *actual, official* range:
  `|A| ≈ 10^11 - 10^8 ≈ 9.999×10^10`, `|R| = 10^8` — a ~1000:1 gap. The
  requirement is not just theoretically unsatisfiable, it fails by
  three orders of magnitude against the one reserved range UIDAI has
  actually published. No undiscovered UIDAI document changes this
  conclusion: even a range 10x or 100x larger than the one found would
  still be short by 1-2 orders of magnitude.

**Alternatives considered** (see the entry above for the original
three; one more considered now):
- Add a session-scoped or persistent map from real Aadhaar →
  reserved-range surrogate, sized to guarantee injectivity: rejected.
  Directly contradicts the frozen architecture table ("Structured
  surrogates: FF1 FPE, keyed, stateless, invertible. No map") and
  CLAUDE.md's forbidden-action list (no persistence for PII or the
  session map beyond names). Would also mean Tier-1 structured PII
  needs the same collision/TTL/durability machinery Phase 3 built for
  names, for one entity type only — reintroducing the vault CLAUDE.md
  says was deliberately deleted.
- Restrict `encrypt()`'s accepted input domain to a subset of `A` no
  larger than `R`, raising `SurrogateDomainError` on the rest:
  rejected. Technically satisfies the letter of the old requirement
  but means ~99.9% of real Aadhaar values throw on ingress — unusable
  under `FAIL_MODE=closed`, a plaintext leak under `FAIL_MODE=open`.
  Worse than the problem it would solve.
- Retire the requirement, keep the guarantees that are actually
  satisfiable (determinism, statelessness, invertibility), and report
  the residual honestly (**chosen**).

**Why.** CLAUDE.md's own hierarchy is explicit: "Honest measurement
over favourable measurement." Structured entities are supposed to be
checksum-*guaranteed* — but reserved-range membership was never a
property a checksum can deliver, and it turns out no stateless
mechanism can, not just the one this project tried first. Treating an
unsatisfiable requirement as a still-open implementation gap (as the
entry above provisionally did, pending research) would eventually
produce either silently-wrong cryptography — exactly the failure class
this project's testing philosophy exists to catch — or a stealth
architecture violation (a map). Retiring the requirement, with the
proof and the research trail attached, extends the same honesty this
project already applies to names ("best-effort with a measured
residual") to a second entity type that turns out to need it too.

**Residual, stated plainly.** An Aadhaar surrogate produced by
`AadhaarDomain` is Verhoeff-valid, format-preserving, deterministic,
and invertible — but is not guaranteed to avoid coinciding with a real
UIDAI-issuable number pattern. Against an issuable space on the order
of `10^11` and public reporting of roughly a billion enrolled
Aadhaars, the a priori chance any single surrogate's *shape* coincides
with an actually-issued number is low-single-digit percent — stated
here as an illustrative order-of-magnitude estimate only, not a cited
UIDAI figure, and not to be presented as one. This belongs in
`docs/LIMITATIONS.md` and the README's residual-leak statement
alongside the existing name-surrogate residual, not hidden — not yet
added; the next piece of work this decision unblocks, not part of
retiring the requirement itself.

**Supersedes:** the "Aadhaar reserved-range enforcement deferred"
entry immediately above (2026-07-20). That entry correctly identified
cycle-walking's precondition failure; this entry establishes the
requirement itself was unsatisfiable by any technique, closing the
"still required" research item it left open.

---

## 2026-07-21 — Span precedence: Tier 1 always wins, same-tier ties by longest-match then registration order

**Decision.** `src/detect/precedence.py`'s `resolve()` implements one
deterministic rule for overlapping spans from different detectors,
matching ARCHITECTURE.md's Span Precedence section exactly: Tier 1
always wins over Tier 2 on any overlap ("deterministic evidence beats
probabilistic evidence, always"); among spans of the same tier, the
longest match wins; remaining ties are broken by detector registration
order — the position of that detector's span sequence in
`get_tier1_detectors()`'s output, threaded through `resolve()`'s
`Sequence[Sequence[Span]]` argument shape rather than inferred from a
flattened list. The winner of an overlap claims its entire conflict
neighborhood — eliminating every span it directly or transitively
overlaps — rather than maximizing the count of surviving spans.

**Alternatives considered.**
- Maximize surviving span coverage (keep two lower-priority spans A
  and C if a higher-priority span B is eliminated and A/C don't
  overlap each other): rejected. "Deterministic evidence beats
  probabilistic evidence, always" is an unconditional priority rule,
  not an optimization target — a resolver that kept more text covered
  by second-guessing the priority order would reintroduce exactly the
  judgment call precedence exists to remove. See
  `test_chain_overlap_highest_priority_span_eliminates_both_neighbors`
  and its converse in `tests/unit/test_precedence.py`.
- Let a higher-confidence or longer Tier-2 span override a shorter
  Tier-1 span: rejected. A checksum has no false-positive rate; a
  model's confidence score is not comparable evidence. Reversing the
  rule would let probabilistic evidence override arithmetic, which
  ARCHITECTURE.md rules out explicitly ("A checksum-validated PAN
  inside a GLiNER `ORG` span is a PAN").
- Break same-tier ties by scan position in one flattened span list,
  rather than by which detector's own sequence a span came from:
  rejected. Flattening first would make "registration order" depend on
  how a caller happened to concatenate detector outputs — an
  unenforced calling convention a caller could silently violate.
  Instead, `resolve()`'s signature takes one span sequence *per
  detector*, so registration order is a property of the input's shape,
  not caller discipline.
- Treat abutting spans (`a.end == b.start`) as overlapping, to be
  conservative: rejected. Half-open interval semantics (`a.start <
  b.end and b.start < a.end`) match the convention `Span`'s own
  offsets already use elsewhere in the codebase, and treating adjacency
  as overlap would falsely eliminate two genuinely distinct,
  back-to-back entities (e.g. two PANs directly separated by nothing)
  for no correctness benefit.

**Why.** Overlap resolution happens immediately before offset-based
substitution — an incorrect resolution doesn't just mis-attribute an
entity type, it corrupts the request body at the character level
(CLAUDE.md: "Off-by-one on overlapping spans corrupts the JSON body").
A rule with a judgment call anywhere in it (confidence weighting,
coverage maximization) is a rule a reviewer has to re-derive by
testing; a rule that is a strict, three-level priority tuple (`tier`,
`-length`, `detector_index`), sorted once, is fully determined by its
inputs and requires no runtime heuristics. Tested with a deliberate
three-detector overlap (`tests/unit/test_precedence.py`) and exercised
end-to-end through the full sanitize pipeline (Phase 2 Task 6,
`tests/unit/test_cascade.py`, `tests/unit/test_sanitize.py`).

---

## 2026-07-21 — Session store: two-level locking, lazy-only eviction, sliding TTL, and the memory-growth trade-off this implies

**Decision.** `src/session/store.py`'s `SessionStore` and
`src/session/session.py`'s `Session` use two independent locks that
are never held simultaneously: a short-lived `SessionStore` lock
protecting only the `dict[SessionId, Session]` (insert / lookup /
replace — O(1) dict operations, nothing else), and a private,
per-`Session` lock protecting that session's own state (currently: the
known-surrogate registry — see the entry below). `get_or_create()`
always releases the store lock before calling into a `Session`'s own
locked methods, so a burst of concurrent requests on *different*
sessions never serialises behind one session's work — proven directly
by `test_get_or_create_does_not_serialize_across_different_sessions`
(`tests/unit/test_session_store.py`), which blocks one session mid-
operation and asserts a different session's `get_or_create()` still
returns in well under a second.

Eviction is **lazy only** — no background sweeper, timer, or cleanup
thread exists or is planned. A session is checked for expiry, and
replaced if expired, only at the moment `get_or_create()` is next
called for its id. TTL is **sliding**: each successful access refreshes
`last_accessed_at` to the current time, so an actively-used
conversation is never evicted mid-way purely because total elapsed
time since creation exceeds `SESSION_TTL` — see
`test_sliding_ttl_repeated_access_before_expiry_keeps_a_session_alive_past_fixed_ttl`.

**Memory-growth policy, stated explicitly (per this task's own
instruction not to leave it implicit).** A session's memory footprint
grows only while it is active — new known-surrogate entries (and, once
Task 2 lands, new name mappings) accumulate for the lifetime of that
conversation. `SESSION_TTL` bounds how long a session's *data remains
trusted and reachable through normal use*, refreshed on every access —
but lazy eviction means it does **not** bound how long an *abandoned*
session's dict entry survives in memory. A session that is created and
then never looked up again (its `session_id` never reappears in a
future request) sits in `SessionStore._sessions` for the remaining
lifetime of the process, because nothing ever revisits it to trigger
the lazy check that would evict it. Under Task 1's scope alone this
residual is low-severity — a `Session` today holds only
`KnownSurrogate` records, which are fake values by construction, never
real PII. **It stops being low-severity once Task 2 adds the real
name map**: an abandoned session's forward map (real name -> surrogate)
would then hold actual PII in memory indefinitely, unbounded by
`SESSION_TTL`, for as long as the process runs. This is accepted for
this project's stated scope — a local, single-developer-machine tool,
not a long-running multi-tenant service (see ARCHITECTURE.md's
Technology Decisions, "In-memory session map" trade-offs) — and is
recorded here, not buried, per CLAUDE.md's "honest measurement over
favourable measurement." A future deployment model change (long-running
shared instance, high session churn) would need to revisit this, most
likely by bounding total store size or adding real eviction — explicitly
out of scope for Phase 3.

**Alternatives considered.**
- A background sweeper thread evicting expired sessions on a timer:
  rejected on direct instruction for this task — adds a lifecycle
  component (start/stop, thread safety of the sweep itself racing
  `get_or_create`) for a benefit (bounding memory for *abandoned*
  sessions) that a single-developer-machine deployment does not need
  urgently enough to justify the complexity now.
- A single global lock covering both the store dict and every
  session's state: rejected — would serialise all concurrent requests
  across every session in the process, failing "do not serialize
  requests across different sessions" outright, and would make the
  50-parallel-requests DoD item (Task 6) measure lock contention rather
  than the mechanism's correctness.
- Fixed TTL from creation instead of sliding: rejected — would cap
  total conversation length regardless of activity, which is not the
  security property `SESSION_TTL` is meant to bound (how long *idle*
  PII sits in memory), and would make a long but actively-used
  conversation fail mid-way for no security benefit.

**Why.** BUILD.md calls this "the hard phase... do not rush it." The
two-lock split is what makes the concurrency and TTL properties
independently provable: `SessionStore`'s tests only need to reason
about dict operations; `Session`'s tests only need to reason about one
session's own state, never about locking across sessions at all.

---

## 2026-07-21 — Known-surrogate registry: typed metadata, not a bare type map — and why Tier-1 needs session state at all now

**Decision.** `src/session/known_surrogate.py`'s `KnownSurrogate` is a
frozen dataclass (`entity_type`, `created_at`), not a bare
`dict[str, EntityType]` mapping a surrogate string directly to its
type. `Session.record_surrogate()` / `Session.lookup_surrogate()`
store and return this typed record, keyed by the surrogate string
itself — never by, or containing, the real value the surrogate was
derived from.

This is the first piece of **session state for structured (Tier-1)
entities**, which were, until now, 100% stateless — FF1 needs no map
to encrypt or decrypt (ARCHITECTURE.md, Surrogate Architecture: "No
map. No vault. No state."). The registry exists to make Phase 3 Task
3's ingress-surrogate recognition possible at all: a Tier-1 surrogate
is, by design, indistinguishable in shape from a real value (that is
the entire point of format preservation), so there is no way to
recognise "this 12-digit string is a surrogate we minted two turns
ago" versus "this is a genuinely new real Aadhaar" without *some*
per-session record of what this session has already minted.

**Why this does not reintroduce "no map for Tier 1."** The frozen
architecture table's "No map. No vault. No state" line is about
*encryption* — FF1 remains fully stateless for that purpose; no key
material, real value, or forward/reverse mapping from a real value is
ever stored here. The registry's key is always a surrogate (fake by
construction, and already treated as safe to hold and log elsewhere in
this codebase — ARCHITECTURE.md, Logging Architecture: "the surrogate
is safe to log because it's fake by construction"). Its value carries
no information recoverable except via the same stateless FF1 key every
caller already holds. Decrypting `AadhaarDomain` still requires nothing
but the key; this registry only ever answers "have I minted this exact
string before," never "what real value does this correspond to" — that
second question is still answered by `engine.decrypt()`, statelessly,
exactly as before.

**Alternatives considered.**
- Store only `dict[str, EntityType]` (surrogate -> type, no record
  type): rejected — the task's own instructions ask for something
  "easily extensible later," and a bare `EntityType` value gives a
  future caller (the rehydration-fidelity harness; parity with
  `Span`'s `tier` field) nowhere to add a field without changing every
  call site's return-type handling from a scalar to a struct at that
  point, instead of now, once, while the type is still new.
- Recognise ingress surrogates by re-deriving each Tier-1 domain's
  format at query time and calling `engine.decrypt()` speculatively,
  with no registry at all (checking "does this round-trip to something
  checksum-valid" as the recognition signal): rejected — FF1 is a
  permutation over the full domain, so an *arbitrary* real value the
  user pastes in would often also decrypt to *some* checksum-valid
  output, indistinguishable from a genuine surrogate this session
  minted. This would misclassify real, new PII as "already ours" and
  pass it through unsanitised — the single most dangerous failure
  direction in the whole phase (a leak, not merely a correctness bug).
  A registry recording only what this session has actually,
  provably minted has no such false-positive path.
- Give `Session` a `Clock` reference so `record_surrogate()` can read
  its own timestamp: rejected — see `session.py`'s module docstring;
  `Session` takes `now` as a parameter everywhere, keeping it a pure,
  deterministic class with no hidden dependency, and keeping clock
  injection centralised at `SessionStore`.

**Why.** CLAUDE.md: "no duplicated logic" and "domain types over
primitives" both apply here — a typed record is one field's worth more
code than a bare dict today, and saves a breaking signature change
later. Recorded now, explicitly, because this is a genuinely new kind
of session state (Tier-1 previously had none at all), not an extension
of the name map's already-established shape.

---

## 2026-07-21 — SessionExpiredError removed pending a real caller; supersedes the "defined now" call in the entry above

**Decision.** `SessionExpiredError` (added in Phase 3 Task 1's first
pass, alongside the locking/TTL entry above) is removed from
`src/core/exceptions.py`. It remains named in CLAUDE.md's exception
hierarchy and ARCHITECTURE.md's Rehydration Engine failure modes as an
anticipated type, but is not defined in code until something actually
raises it.

**Why the reversal.** On review, `SessionStore`'s lazy eviction always
transparently returns a valid session — `get_or_create()` cannot
distinguish "this id has never been seen" from "this id existed and
expired," by design, and nothing in Task 1 or Task 2 needs that
distinction. Defining the type ahead of a real call site was flagged,
correctly, as contradicting CLAUDE.md's own stated rule: "Children are
added only once a phase actually raises them, not ahead of need." The
original entry called this "the one deliberate exception to that
rule" — on reflection, that reasoning does not hold: choosing an HTTP
status now, for an exception with no caller, is not a case the rule
needed an exception carved out for; it is exactly the case the rule
exists to prevent.

**Where it most likely belongs.** ARCHITECTURE.md's own failure-mode
table: "Expiry mid-conversation → surrogates arrive back with no
mapping → `SessionExpiredError`" — a rehydration-time concern (Phase 3
Task 4), not a session-store concern. Whether Task 4 genuinely needs to
raise it (as opposed to treating an unresolvable surrogate as an
ordinary, expected miss under conservative matching — see the
rehydration-oracle reasoning elsewhere in this file) is a design
question for that task, not decided here. If it turns out Task 4 has
no need for the distinction either, this type should stay absent
rather than be added defensively a second time.

**Alternatives considered.**
- Keep the type but leave it genuinely unused indefinitely, as
  documented "ready infrastructure": rejected — dead code with no
  caller and no test exercising a real raise site is exactly the kind
  of thing that silently drifts wrong (e.g. its HTTP mapping) without
  anything ever failing to reveal the drift.
- Keep it and add a synthetic call site just to justify its existence:
  rejected outright — explicitly what this task's review instructed
  against ("do not force an artificial use of this exception simply
  because it exists").

**HTTP status, if and when it is reintroduced.** `410 Gone` was chosen
in the removed docstring and is worth preserving here rather than
re-deriving later: the session genuinely existed and no longer does,
which is what `410` means, distinguishing it from an ordinary `400`
validation failure. Not binding on whichever task actually adds it
back — a real call site may reveal a better fit.

---

## 2026-07-21 — Bounding session-store growth: a deterministic LRU capacity cap, not a documented-only limitation

**Decision.** `SessionStore` (`src/session/store.py`) now takes a
`max_sessions` parameter (default `DEFAULT_MAX_SESSIONS = 10_000`, a
guess, stated as such). Once that many distinct sessions exist,
creating one more evicts the least-recently-used entry first — tracked
via an `OrderedDict` with `move_to_end()` on every access and
`popitem(last=False)` to evict, all under the existing store lock, with
no new locking primitive or background component. This narrows and
partially supersedes the memory-growth entry above: that entry
correctly identified the risk but left it as a documented-only
limitation; this entry closes the specific, worse half of it.

**The distinction that matters.** Two different growth patterns were
conflated in the original memory-growth entry, and they are not
equally bad:
- **Reused session ids** (the common case: the same conversation
  making repeated requests) were already handled correctly — lazy TTL
  eviction replaces a stale entry the next time that same id is
  accessed, and the store's size tracks the number of *distinct*
  sessions, not the number of requests.
- **Unique, never-revisited session ids** — an attacker (or simply
  many legitimate one-shot callers) creating a fresh id every request
  — are the real unbounded case: lazy eviction, by definition, never
  fires for an id nothing ever asks about again. Every prior test and
  the original entry's own reasoning already showed this; what changed
  is treating it as something to bound now rather than something to
  merely disclose.

**Why a hard cap, not a smarter TTL sweep.** A cap bounds *worst-case*
memory directly and exactly, regardless of access pattern or how fast
new ids are created — it is the only mechanism in the space of
"deterministic, no background thread" options that gives that
guarantee. Any TTL-driven amortized sweep (checking a few other entries
opportunistically on each `get_or_create()` call) still allows
unbounded growth if new unique ids are created faster than the sweep
can retire old ones; a hard cap cannot be outrun that way.

**Residual, stated plainly.** A capacity cap does not make the
attack-shaped scenario free — it converts "unbounded memory growth,
eventually a crash" into "bounded memory, but sustained creation of new
unique ids can now evict *legitimate*, actively-used sessions early,"
i.e. an availability/correctness cost instead of a memory-exhaustion
one. For this project's stated deployment target — one developer's
machine, not a shared multi-tenant service (ARCHITECTURE.md,
Performance Architecture: "Target: one developer's machine... Not a
fleet") — a bounded, recoverable degradation is clearly preferable to
an unbounded one, but it is not a complete defense against a
sufficiently determined flood of unique session ids, and is not
presented as one.

**Alternatives considered.**
- Leave it as a documented-only limitation (the original entry's
  conclusion): rejected on review — the task's own framing correctly
  distinguished "the common case is already fine" from "the actual
  worst case is a certain failure, not a rare one," and a certain
  eventual-OOM failure mode with a known, cheap, deterministic
  mitigation available is not a residual worth merely disclosing.
- Amortized opportunistic sweeping (check/evict a few stale entries on
  every `get_or_create()` call, no hard cap): rejected — does not
  bound worst-case memory (see above); also adds a second eviction
  reason (staleness-probability) alongside TTL and capacity, for a
  weaker guarantee than the cap alone already provides.
- A true background sweeper thread: rejected outright — explicitly
  forbidden by this project's Phase 3 architectural decision ("no
  background sweepers, timers, cleanup threads, lifecycle workers").
- Make `max_sessions` required, no default (matching `FAIL_MODE`/
  `SESSION_TTL`/`FPE_KEY`'s "no silent security defaults" pattern):
  rejected — this constant is an operational/reliability tuning value
  in the same family as `sliding_window.py`'s `DEFAULT_LOOKAHEAD`
  (guessed, documented, revisit once measured), not a security posture
  choice like `FAIL_MODE` where a default would silently pick a side
  of an open/closed trade-off. A missing cap has one obvious safe
  behavior (a large, generous default); a missing `FAIL_MODE` does not.

**Why.** CLAUDE.md: "Silent-failure-hostile... if a defect can hide,
assume it is hiding, and go write the test that would catch it" —
unbounded growth under a specific, plausible, adversarial access
pattern is exactly that class of defect, and it does not require a
background component to close, only a cap already implementable with
the same lock and the same data structure already in place.

---

## 2026-07-21 — Name allocator: one atomic Session method, a shared known-surrogate registry across tiers, and a real (not speculative) exhaustion exception

**Decision.** `Session.allocate_or_lookup_name()` (Phase 3 Task 2,
`src/session/session.py`) implements the entire check-existing /
shuffle / probe-for-unused / commit sequence as **one method acquiring
`self._lock` once** — not a separate `NameAllocator` class or free
function making multiple separately-locked calls into `Session`. A
successful new allocation also writes into `_known_surrogates` (Task
1's registry) directly, inline, rather than calling
`record_surrogate()` — `threading.Lock` is not reentrant, so a locked
method calling another locked method on the same object would
deadlock. The RNG is `random.Random` itself, injected, not a bespoke
protocol. Exhaustion (every candidate already assigned to a different
real value) raises `NameListExhaustedError`, newly added to
`src/core/exceptions.py`.

**Why one atomic method, not a free function over Session's
internals.** Splitting "check if a candidate is free" and "claim it"
into two separately-locked operations reopens exactly the race BUILD.md's
DoD forbids: two concurrent callers could both observe the same
candidate as free between the two calls and both claim it, producing
two real values sharing one surrogate. Collision-avoidance is only a
real guarantee if the whole probe-and-commit sequence is indivisible
from the perspective of every other caller — which requires it to be
one critical section, which requires it to live on `Session` itself
(the only place already holding the right lock), not layered on top
from outside.

**Why the known-surrogate registry is shared across Tier-1 and
Tier-2, not duplicated.** A name allocation records a `KnownSurrogate`
entry the same way Task 1's Aadhaar/PAN example would. This means
Phase 3 Task 3's ingress-surrogate recognition can check one registry
(`lookup_surrogate()`) regardless of whether the candidate substring
turns out to be a structured (FF1) surrogate or a name surrogate,
instead of needing two parallel recognition mechanisms. CLAUDE.md: "no
duplicated logic" — the alternative (a second, Tier-2-only known-value
set) would duplicate exactly the same bookkeeping Task 1 already built
for a different reason.

**Why `random.Random`, not a custom `RNG` protocol.** Unlike `Clock`
(where a test needs manually-controllable, non-realtime advancement
that no real clock implementation provides — hence `FakeClock`),
`random.Random` is already fully deterministic and substitutable when
constructed with a fixed seed; a bespoke protocol would add an
abstraction layer over something the standard library already makes
injectable and testable on its own. `_IdentityShuffleRandom` in
`tests/unit/test_session_names.py` (a `random.Random` subclass whose
`shuffle()` is a no-op) is what actually proves the collision-retry
*code path* runs, rather than merely hoping a real shuffle never picks
the same candidate twice by chance.

**Why `NameListExhaustedError` is not the same mistake as
`SessionExpiredError`** (see the entry above, same day). This
exception has an immediate, real call site inside
`allocate_or_lookup_name()` itself, and a test
(`test_exhaustion_raises_once_every_candidate_is_assigned_to_a_different_value`)
that genuinely exhausts a forced-tiny candidate list to trigger it —
not a type defined ahead of any caller. ARCHITECTURE.md's Name
Allocator component already names exhaustion as a real failure mode
("more distinct entities in a session than names in the list"); this
task is the first one with a concrete mechanism that failure mode
applies to.

**Alternatives considered.**
- A separate `names.py`-level `NameAllocator` class holding its own
  lock, composed with `Session`: rejected — a second lock guarding
  state that must be checked jointly-atomically with `Session`'s
  existing forward/reverse maps would either need cross-lock
  coordination (reintroducing exactly the race this design avoids) or
  duplicate state, neither of which is simpler than one more method on
  the class that already owns the relevant locking.
- Silently returning `None` (or an empty string) on exhaustion instead
  of raising: rejected — CLAUDE.md's error-handling philosophy is
  explicit that an exceptional state (no representable output for
  valid input) must raise, not be modelled as a sentinel a caller could
  forget to check; a swallowed exhaustion would silently forward a
  request with a missing/wrong-shaped surrogate, or worse, an
  un-substituted real value.

**Why.** BUILD.md's Phase 3 DoD is explicit and testable on this exact
point: "two in-flight requests assigning a surrogate to the same new
name must not produce two mappings," and "no two entities share a
surrogate" under a forced-tiny list. Both are proven directly in
`tests/unit/test_session_names.py`, including under real thread
concurrency (`ThreadPoolExecutor`, 50 workers), not merely asserted by
code inspection.

---

## 2026-07-21 — Two Session objects for one SessionId: an accepted, intentional invariant, not an oversight

**Decision.** `SessionStore` does not guarantee that every caller
holding a `session_id` is looking at the same `Session` object at every
point in time. Both lazy TTL expiry-and-replacement (Task 1) and LRU
capacity eviction (the "Bounding session-store growth" entry above)
can cause `_sessions[session_id]` to move on to a *different* `Session`
object while some other caller, having already fetched the *previous*
object via an earlier `get_or_create()` call, is still holding and
using it. `get_or_create()` never invalidates a reference a caller
already has — an in-flight request's `Session` reference stays valid
and usable for the caller's entire lifetime, it simply may no longer be
the one a *new* `get_or_create("s1")` call from someone else returns.

**Why this is safe — no data race.** Each `Session` object is
independently, correctly thread-safe on its own terms (its own lock
protects its own state — see `session.py`'s module docstring). Two
objects existing for one conceptual "conversation" at once means two
independently-consistent pieces of state exist momentarily, not one
inconsistent piece of shared, racily-accessed state. Nothing about
holding a reference to an object no longer reachable via the store's
dict makes that object unsafe to keep using — Python's garbage
collector keeps it alive exactly as long as something references it,
and its own lock keeps protecting it exactly as before.

**Why this is not a new risk introduced by the capacity cap.** The
capacity cap adds a *second trigger* for the same pre-existing
category of behaviour — it does not create a new one. Even with no
`max_sessions` cap at all (Task 1's original design), a caller that
fetched a `Session` moments before it expired would already face the
identical situation: the store lazily replaces the expired entry on
the next `get_or_create()` call from anyone else, while the original
caller's reference stays exactly as valid and exactly as orphaned as
under capacity eviction. The consequence is also identical either way:
work committed to the orphaned object (a name allocation, a recorded
surrogate) becomes invisible to whatever the store considers "the"
session for that id going forward — which is the same "the session
moved on, prior mappings are gone" outcome `SESSION_TTL` already
promises will eventually happen by design, not a new failure mode.

**Practical bound, for this project's stated scale.** For this window
to matter, either a single in-flight request would need to outlive the
entire configured `SESSION_TTL` (minutes, for a request that normally
completes in seconds), or — for the capacity-eviction trigger
specifically — `max_sessions` other distinct sessions would need to be
created and processed during that one request's lifetime. Both are far
outside ARCHITECTURE.md's stated deployment target ("one developer's
machine... not a fleet"), though neither is impossible, which is why
this is documented as an accepted trade-off rather than asserted to be
unreachable.

**What this does not affect.** Within one request's own processing,
`sanitize()` (and, later, rehydration) holds one `Session` reference
throughout and is fully self-consistent — this invariant is about
visibility *across* separate `get_or_create()` calls, never about
correctness *within* a single call's use of the object it was handed.

**Why.** Documented explicitly, per this task's own review instruction,
so a future contributor encountering two live `Session` objects for one
`SessionId` in a debugger or a log trace recognises it as expected
behaviour with a known cause, rather than investigating it as a bug.

---

## 2026-07-21 — Ingress recognition lives in the detection cascade, not a pipeline-level wrapper

**Decision.** `src/detect/cascade.py::detect()` (Phase 3 Task 3) takes
a `session: Session` parameter and returns `list[ResolvedSpan]`
(`Span` plus `is_ingress_surrogate: bool`) instead of `list[Span]`.
Ingress recognition — checking each precedence-resolved span's text
against `session.lookup_surrogate()` — runs as the cascade's own last
step, inside `detect/`, rather than in a separate pipeline-level
function that would call the old `detect(text) -> list[Span]` and wrap
its output with session awareness from outside.

**Alternatives considered.**
- Keep `cascade.detect()` unchanged (session-free) and do the
  `ResolvedSpan` wrapping in `pipeline/sanitize.py` instead: seriously
  considered, since it avoids `detect/` depending on `session/` at all
  and reads as a stricter interpretation of "detectors remain
  session-unaware." Rejected on rereading ARCHITECTURE.md's own
  Component 4 ("Detection Pipeline") table, which lists "recognise
  ingress surrogates and mark them pass-through" as one of that
  component's *own* stated responsibilities, alongside running Tier 1,
  running Tier 2, and resolving overlaps — the same component
  `cascade.py` already implements end to end. Moving recognition up a
  layer would be deviating from what ARCHITECTURE.md already
  describes, not a stricter reading of it.
- A new `EntityType`-keyed session parameter passed to each individual
  `Detector.detect()`: rejected outright — "detectors remain
  session-unaware" is explicit and unambiguous; recognition depends on
  a *resolved*, non-overlapping span's exact text, which does not
  exist until *after* precedence resolution, and no single detector
  ever sees that.

**Why `detect` depending on `session` is not a layering violation.**
The frozen layering diagram draws `pipeline -> detect/surrogate/session
-> core` — a rule about `core` (imports nothing internal) and about
`pipeline`'s position above the three siblings. It draws no arrow
*between* `detect`, `surrogate`, and `session`, so a sibling depending
on a sibling is unconstrained by the diagram, not forbidden by it. This
is the one place in the codebase that dependency is actually needed;
`surrogate/` still depends on nothing (FF1 stays fully stateless), and
`session/` still depends on nothing but `core`.

**Why recognition runs last, after precedence resolution, not before.**
Precedence resolution operates on raw, possibly-overlapping candidate
spans from every detector and is entirely about *which entity type
wins* when detectors disagree — a question unrelated to whether a span
happens to already be a known surrogate. Running recognition first
would mean checking candidate spans that might not even survive
precedence resolution, for no benefit; running it last means every
`ResolvedSpan` this function returns has already been fully decided on
type and boundaries, and recognition is the one remaining question left
to answer about it.

**Why.** BUILD.md, Phase 3: "Ingress surrogate recognition... Detect
and pass through — do not re-encrypt." Proven end-to-end, not just at
the cascade level, by `tests/unit/test_sanitize.py`'s
`test_a_surrogate_already_known_to_the_session_is_passed_through_unchanged`
and the multi-request integration test in
`tests/integration/test_sanitize_integration.py`
(`test_a_surrogate_replayed_in_a_later_request_on_the_same_session_is_not_re_encrypted`),
which sends a real value on turn 1, captures the surrogate the gateway
actually produced, then sends that surrogate back inside turn 2's
history and confirms it survives byte-for-byte unchanged.

---

## 2026-07-21 — The session header: `X-Session-Id`, required, fail-closed, and why SessionStore's DI caching is load-bearing here

**Decision.** `src/proxy/routes.py` requires an `X-Session-Id` header
on every `/v1/chat/completions` request, checked before the body is
even parsed. A missing or empty value raises `HTTPException(400)`
immediately — no derived, generated, or otherwise implicit session
identity exists anywhere in this codebase. `get_session_store()`
(`src/session/store.py`) is `@lru_cache`d, same as
`get_upstream_client()`/`get_key_provider()`, but for a different and
stronger reason: those two are cached purely for connection/computation
reuse and would still be *correct* (if wasteful) if constructed fresh
per request; `SessionStore` would be *actively wrong* if uncached —
every request would get a brand-new, empty store, and no session
could ever persist across two requests, defeating Phase 3 entirely.

**Why `X-Session-Id` specifically, not the OpenAI SDK's `user` field.**
OpenAI's chat-completion request schema has an optional, free-text
`user` field, already present in the wire format this project must
preserve exactly. It was considered and rejected as the session
identity source: it is optional (no fail-closed story — what happens
when it's merely absent, as it usually is in real traffic?), it is
documented for *the provider's own* abuse-tracking purposes, not
proxy-session-scoping, and overloading it would conflate two unrelated
concerns behind one field a caller might set for either reason, or
neither. A dedicated header names its purpose unambiguously and costs
callers one line, matching this project's own "one-line integration"
standard.

**Why fail-closed (400) rather than a derived fallback (e.g. hashing
the client's connection or the request body).** A derived identity
would silently violate "consistent surrogate within a session" the
moment two logically-separate conversations happened to hash to the
same derived value, or the moment one conversation's derived value
changed between requests — a correctness failure with no error message
anywhere pointing at its cause. An explicit, required header makes the
one hard requirement of using this gateway's session features visible
and enforced, not discovered later as mysteriously inconsistent
surrogates.

**Why.** Matches this project's established "no silent security
defaults" pattern (`FAIL_MODE`, `SESSION_TTL`, `FPE_KEY` all already
require explicit configuration, never an inherited default) applied to
the one piece of required *request*-level configuration Phase 3
introduces. Tested directly: `test_missing_session_id_header_returns_400`
and `test_empty_session_id_header_returns_400`
(`tests/integration/test_chat_completions_route.py`).

---

## 2026-07-21 - Rehydration engine: transform-in-place on the sliding window's own buffer, not a fragment-level substitution

**Decision.** `src/pipeline/rehydrate.py` (Phase 3 Task 4) implements
rehydration as exact-substring matching against a session's own
known-surrogate registry - one alternation regex over every surrogate
`Session.known_surrogate_snapshot()` reports, longest-first (mirroring
`precedence.py`'s own same-kind tie-break), resolving each match via
`engine.decrypt()` for structured (Tier-1) entity types or
`Session.lookup_real_name()` for name-map (Tier-2) types. `SlidingWindow`
(`src/pipeline/sliding_window.py`) gained one new constructor parameter,
`transform: Callable[[str], str] | None`, applied to the *entire
retained buffer* - before the lookahead length check that decides what
is safe to release - on every `feed()` and on `flush()`. The route
handler (`src/proxy/routes.py::_generate_sse`) constructs the window
with `transform=rehydrate` (closed over the request's session, key
provider, and correlation id) instead of the bare pass-through Phase 1
used.

**Why transform must run on the retained buffer, not on the fragment
`feed()` is about to return.** Worked through in full in
`sliding_window.py`'s own module docstring, but the core of it: a
surrogate is only guaranteed to be fully, contiguously present in the
window's buffer for the interval between "its last character just
arrived" and "its first character is about to age out of the retention
margin" - and that interval only exists at all if `lookahead >=` the
longest possible match length. If a caller instead substituted against
whatever `feed()` returns (which can be as short as one character, fed
incrementally), the first character of a still-forming match would be
released - unsubstituted - before the rest of the match ever arrives,
leaking it one character at a time. This is exactly ARCHITECTURE.md's
own named failure mode ("Naive: substitute per chunk... Result:
surrogate leaks to user"), and it is not a corner case:
`tests/unit/test_sliding_window.py::test_transform_receiving_one_character_at_a_time_never_leaks_a_partial_match`
feeds one character per call specifically to force it.

**Alternatives considered.**
- A separate `RehydratingWindow` class wrapping or duplicating
  `SlidingWindow`'s buffering/slicing logic, with matching built in:
  rejected - would duplicate the retention-margin arithmetic
  `SlidingWindow` already implements and already has full test coverage
  for (CLAUDE.md: "no duplicated logic"), for no benefit over a single
  injected callable.
- Matching inside `SlidingWindow` directly, importing `session`/
  `surrogate`: rejected - `SlidingWindow` lives in `src/pipeline/`,
  which is *allowed* to depend on `session`/`surrogate` per the
  layering diagram, so this wasn't a hard layering violation, but it
  would hard-wire one specific privacy mechanism into a class Phase 1
  built and tested as generic buffering mechanics, and CLAUDE.md's
  dependency-injection rule already names the correct alternative:
  "Anything with a clock, a key, a model... is injected." `transform`
  is exactly that injection point - literally the seam Phase 1's own
  docstring said would exist ("the seam exists and is tested").
- Applying `transform` only at release time, to the fragment about to
  be returned: rejected for the reason above - provably insufficient
  once matches can be shorter than a single `feed()` call's chunk size.

**Why the response body is rehydrated on the non-streaming path too, not
just SSE.** BUILD.md and ARCHITECTURE.md both frame Phase 3's
rehydration work almost entirely around the SSE/streaming case (it is
the hard engineering problem), but nothing scopes rehydration itself to
streaming only - the product goal ("the user sees their real PAN") does
not distinguish `stream: true` from `stream: false`. Before this task,
`_forward_non_streaming` returned the upstream's raw body unmodified;
had detection ever substituted an entity in that request, the caller
would have received the *surrogate* back in a non-streaming response,
never rehydrated - a real, if narrow, gap left unclosed. `rehydrate_body()`
reuses `field_walker.walk()`/`rebuild()` exactly as `sanitize()` does,
rather than special-casing `choices[].message.content`, for the same
"no duplicated logic" reason the request path already established.

**A real bug caught while wiring the non-streaming path: stale
`Content-Length`.** Re-serializing a parsed-and-rehydrated JSON body via
`json.dumps` is not guaranteed byte-identical to whatever the upstream
originally sent - even with zero actual substitutions, `ensure_ascii`
handling, key ordering, and whitespace can all differ. Forwarding the
upstream's original `Content-Length` header verbatim (as
`_forwardable_headers` already did, since it is not a hop-by-hop header)
would hand the client a length that doesn't match the real body - a
client either truncates its read or hangs waiting for bytes that never
arrive. Fixed by dropping `content-length` from the forwarded header set
whenever the body has been re-serialized, letting Starlette compute a
correct one from the actual bytes
(`tests/integration/test_rehydrate_integration.py::test_non_streaming_response_content_length_matches_the_rehydrated_body`).

**Window lookahead: derived from real domain/name data, not a guess,
superseding Phase 1's placeholder.** `SlidingWindow.DEFAULT_LOOKAHEAD`
(64, Phase 1) was an admitted guess, pending "the longest entity in the
surrogate domain plus the longest decoration handled" (ARCHITECTURE.md)
- neither existed yet at the time. Both now do. `SurrogateDomain`
(`src/surrogate/domain.py`) gained a `max_surrogate_length: int` field,
populated by each of the six FF1 domains from their own already-fixed,
cited format length (Aadhaar 12, PAN 10, IFSC 11, Card 19 per ISO/IEC
7812-1, Phone 13 with its longest accepted prefix, Vehicle Registration
11 for its longest accepted shape); `registry.max_registered_surrogate_length()`
takes the max across whichever domains are actually registered.
`rehydrate.py::REQUIRED_WINDOW_LOOKAHEAD` combines that with the longest
name in `src/session/names.py`'s candidate list, and the real route
(`_generate_sse`) constructs its window with this value, not
`SlidingWindow`'s own default. Because both source values are read live
at import time rather than hand-copied, a future change to either (a
new, longer FF1 domain; a differently-sized production name list in
Phase 4) updates the required lookahead automatically, with no second
number to remember to update in step.

**Why no extra margin for "decoration," despite ARCHITECTURE.md's
literal phrasing.** That phrasing is written for a matcher that must
tolerate decoration characters appearing *between* an entity's own
characters. Exact-substring matching does not have this problem:
decoration (`**ABCDE1234F**`) wraps *around* a surrogate's contiguous
span, never interleaving inside it, so the window only ever needs to
hold one complete surrogate's own characters at once - the entity
length alone is the correct, tight bound, not the entity length plus
some additional decoration allowance.
`tests/unit/test_rehydrate.py::test_rehydrates_a_surrogate_wrapped_in_markdown_decoration`
proves decorated forms are caught with no decoration-specific code.

**`RehydrationError`: a second real, immediate caller, not a
speculative addition.** Added to `src/core/exceptions.py` for exactly
one condition: a known-surrogate registry entry claims a name-map
entity type, but the session's reverse name map has no value for it -
an invariant violation, since `Session.allocate_or_lookup_name()`
always writes both structures in the same locked operation (see the
"Name allocator" entry above). Unlike `SessionExpiredError` (removed
the same day, above, for having no real caller), this type has an
immediate call site in `rehydrate.py::_resolve_real_value()` and a test
that genuinely constructs the drifted state through the session's own
public API (`record_surrogate()` without a matching
`allocate_or_lookup_name()` call) -
`tests/unit/test_rehydrate.py::test_name_map_entry_with_no_reverse_mapping_raises_rehydration_error`.

**Longest-match-first tie-break for overlapping known surrogates.**
`_pattern_for()` sorts known surrogate strings by descending length
before building the alternation regex, so that if one known surrogate
happened to be an exact substring of another *within the same
session* - not expected in practice: FF1 outputs are effectively random
within their domain, and no name in the current placeholder list is a
prefix of another - the longer, more specific one wins, mirroring
`precedence.py`'s same-kind tie-break rather than leaving the case
undefined. Proven with a deliberately constructed collision:
`tests/unit/test_rehydrate.py::test_longest_known_surrogate_wins_when_one_is_a_substring_of_another`.

---

## 2026-07-21 - Rehydration-fidelity harness: a new top-level directory, not scripts/ or a pytest test

**Decision.** The rehydration-fidelity harness (BUILD.md, Phase 3 Task
5) lives in a new top-level `rehydration_fidelity/` directory
(`runner/taxonomy.py`, `runner/run.py`, `results/latest.json`),
mirroring the structure BUILD.md's Repository Conventions tree already
gives `benchmarks/` (Phase 5) and `adversarial/` (Phase 6) — a
`runner/` that produces a `results/` artifact stamped with the commit
that produced it. Invoked via `python -m rehydration_fidelity.runner.run`,
or `.\tasks.ps1 rehydration-fidelity`.

**Why this needed a decision at all.** BUILD.md's Repository
Conventions tree enumerates `benchmarks/` and `adversarial/`
explicitly, for the two evaluation deliverables Phases 5 and 6
introduce, but names nothing for a Phase 3 harness — a real gap in the
enumerated structure, not an oversight safe to resolve silently
(CLAUDE.md: "No feature additions unless explicitly requested... Not
small ones"; a new top-level directory is exactly the kind of
structural choice that section has in mind).

**Alternatives considered.**
- Under `scripts/` (CLAUDE.md: "dev-only. Never imported by `src/`."):
  rejected — this harness is a first-class, committed measurement
  artifact BUILD.md explicitly asks to be "measured and reported," in
  the same spirit as the benchmark and adversarial suites, not a
  throwaway dev convenience. Treating it as `scripts/`-tier tooling
  would understate that it produces a real, citable number
  (`docs/LIMITATIONS.md` now points at its committed output).
- Inside `benchmarks/`, since it is not yet built: rejected — the
  Phase 5 benchmark and this harness measure two different things
  (structured/unstructured entity *detection* recall vs. *rehydration*
  fidelity of an already-detected surrogate); nesting one inside the
  other's directory ahead of Phase 5 existing would conflate them for
  whoever builds Phase 5 next.
- A pytest test asserting fixed expected rates: rejected outright —
  BUILD.md's own framing is explicit ("Measure, don't fix"); a test
  encodes an assertion about what *should* happen, which is the wrong
  shape for a tool whose entire purpose is reporting what *does*
  happen. Two specific rates *are* asserted in
  `tests/unit/test_rehydration_fidelity.py` ("exact" and "decorated"
  always fully round-trip; "reasoned_about" never does) — but only
  because those are guaranteed by the rehydration engine's own
  construction (proven separately in `tests/unit/test_rehydrate.py`),
  not empirical findings. Every other category's rate is measured, not
  asserted.

**Taxonomy: BUILD.md's own seven categories, not ARCHITECTURE.md's
example table verbatim.** ARCHITECTURE.md's Response Lifecycle section
illustrates the same idea with an eight-row table that includes
"possessive" and "slugified" forms and omits "case-shifted." BUILD.md's
Phase 3 section is the more specific, DoD-bearing source ("Build the
taxonomy now: exact, partial... decorated... case-shifted,
abbreviated... transliterated, reasoned-about"), so
`rehydration_fidelity/runner/taxonomy.py`'s `TAXONOMY` tuple follows it
literally, in its listed order. Possessive forms (`Arjun's report`) and
slugified forms (`arjun-reddy`) are not separate categories here, but
the harness's exact-substring matching already resolves the possessive
case for free (a possessive suffix doesn't break the surrogate's own
contiguous characters) — a property `tests/unit/test_rehydrate.py`
covers directly, not something this harness needed its own category to
confirm.

**Why every sample is a `PERSON`-type entity, not a mix of Tier-1 and
Tier-2.** ARCHITECTURE.md's own framing draws the fidelity/measurement
line exactly here: "Structured entities are checksum-guaranteed...
Names are best-effort with a measured residual." The taxonomy's
categories (partial, abbreviated, transliterated) only make sense for
multi-word free text in the first place — a 12-digit Aadhaar has no
"first name only" form. Structured-entity round-trip correctness is
already proven exhaustively by property-based testing
(`tests/property/test_ff1_roundtrip.py`); this harness exists
specifically to quantify the *different*, harder question Tier-2
raises, and scoping it to `PERSON` keeps that distinction visible
rather than diluting the name-specific finding across an
entity-type-mixed sample.

**Why `PERSON` surrogates are minted directly via
`Session.allocate_or_lookup_name()`, not through real Tier-2
detection.** Tier 2 (GLiNER) doesn't exist until Phase 4 — there is no
detector yet to hand this harness a real span. Calling the session's
own allocation API directly is the same technique
`tests/unit/test_session_names.py` and `tests/unit/test_rehydrate.py`
already use to exercise name-map behaviour ahead of Phase 4, and it
means this harness needs no changes when Phase 4 lands; only the
*source* of `PERSON` spans changes, not how they're rehydrated.

**Reproducibility: a fixed allocation seed, and no assertion the exact
surrogate strings matter.** `_ALLOCATION_SEED = 0` (not system entropy)
so re-running the harness with unchanged code reproduces byte-identical
output — the same "delete the numbers, regenerate, get the same
numbers back" property ARCHITECTURE.md requires of the Phase 5
benchmark, applied here first, and verified directly (ran the harness
twice across an unrelated refactor in this same task with identical
`results/latest.json` output both times). Which specific surrogate
string each sample real name happens to land on does not affect any
category's rate: every sample name and every candidate surrogate shares
the same "First Last" shape, so the taxonomy's transforms behave
uniformly regardless of which pairing the RNG produces.

**The `transliterated` category uses a hand-written per-letter stand-in
table, not a real transliteration engine.** Stated plainly in
`taxonomy.py`'s own docstring and repeated here: this project has no
transliteration engine or linguistic data, and building one is out of
scope for a Phase 3 harness. The stand-in table exists only to give
this category the *property* it needs to test — output sharing no
substring with the Latin surrogate it was derived from — not to
produce a linguistically accurate rendering. A real transliteration
model would be Tier-2/Phase-4-adjacent scope creep for a measurement
tool.

**Result, measured today (`rehydration_fidelity/results/latest.json`,
commit `6796edc`): "exact" and "decorated" round-trip at 100%;
"case_shifted," "partial," "abbreviated," "transliterated," and
"reasoned_about" round-trip at 0%.** This is the expected, honest shape
of a conservative, exact-substring-only matcher (ARCHITECTURE.md,
Response Lifecycle) — not a defect to fix in this task. Reported
plainly in `docs/LIMITATIONS.md` rather than only in this committed
artifact, per CLAUDE.md's "honest measurement over favourable
measurement."

**Why.** BUILD.md's Phase 3 DoD item is explicit and now met: "Rehydration-fidelity
harness runs and emits per-category numbers to an artifact." The
harness's own code is tested (`tests/unit/test_rehydration_fidelity.py`),
per CLAUDE.md's "benchmark and adversarial runners are code, and they
get tested too," applied one phase early to this smaller, structurally
identical kind of tool.

---

## 2026-07-21 - The rehydration-oracle tradeoff: conservative exact-match matching, chosen explicitly, recorded as its own decision

**Decision.** Response-path rehydration (`src/pipeline/rehydrate.py`,
Phase 3 Task 4) matches only exact, complete, unmodified surrogate
substrings against a session's own known-surrogate registry — never a
fuzzy, partial, or heuristic match. This was already ARCHITECTURE.md's
stated position before Phase 3 began (Response Lifecycle: "the
architecture chooses conservative matching: misses are visible... rather
than dangerous"); this entry is the explicit Phase 3 decision record
BUILD.md's own Phase 3 DoD asks for by name ("Oracle tradeoff written
into DECISIONS.md"), not a new position — recorded now, directly,
rather than left implicit across Task 4's own entry and
ARCHITECTURE.md's prior framing.

**Alternatives considered.**
- Fuzzy/partial matching (e.g., match on the surrogate's first token
  alone, or a normalized/lowercased/Levenshtein-distance comparison):
  rejected. Once matching tolerates *any* transformation of the
  surrogate short of an exact copy, an attacker who can influence what
  the model repeats back (a prompt-injection payload, or simply asking
  the model "please repeat the name you were given") can induce the
  gateway to treat attacker-supplied or attacker-observed text as a
  match and rehydrate a *real* value into attacker-readable output —
  turning the privacy layer itself into the exfiltration primitive
  (ARCHITECTURE.md calls this "the sharpest attack on this design").
  Exact matching has no such path: the only text that ever rehydrates
  is a byte-for-byte copy of a string this specific session already
  minted, which an attacker who does not already control the real
  value has no way to produce.
- Fuzzy matching gated behind a confidence threshold or an allow-list of
  "safe" transformations (case-folding only, say): rejected — it moves
  the oracle risk rather than removing it. Any tolerated transformation
  is a transformation an attacker can also produce; "only case-folding"
  is still an oracle for case-folded attacker input, just a narrower
  one. There is no threshold at which fuzzy matching is safe *and*
  meaningfully more permissive than exact matching, because the
  property that makes exact matching safe (only a session's own minted
  string, verbatim, ever matches) is binary, not a matter of degree.
- Ship fuzzy matching now and measure the residual with the fidelity
  harness, deciding later whether the false-positive rehydration risk
  is "worth it": rejected — CLAUDE.md's Decision Making section is
  explicit that a security-relevant tradeoff is not something to
  implement first and evaluate after ("do not resolve it by
  implementing"), and ARCHITECTURE.md already settled this exact
  question before Phase 3 began. Re-opening it here would be relitigating
  frozen architecture, not extending it.

**What this costs, stated plainly (the other half of the tradeoff, not
just its justification).** The rehydration-fidelity harness
(`rehydration_fidelity/`, Task 5) measures the cost directly: of
BUILD.md's seven named response-form categories, only "exact" and
"decorated" round-trip (100% each); "case_shifted," "partial,"
"abbreviated," "transliterated," and "reasoned_about" all measure at
0%, today. Every one of those is a real, visible surrogate leaking into
the user-facing response rather than silently vanishing — the correct
failure direction (a bug the user can see and report) rather than the
dangerous one (a leak an attacker engineered and the user never
notices), but a real, non-trivial fraction of realistic model output
nonetheless. This cost is not hidden in `docs/LIMITATIONS.md`'s own
entry for it, alongside the measured numbers.

**Why.** ARCHITECTURE.md, Response Lifecycle: "So the architecture
chooses conservative matching: misses are visible... rather than
dangerous... The miss rate is measured per category by the
rehydration-fidelity harness and published in `docs/LIMITATIONS.md`.
Owning this limit is the second-most-honest thing in the project,
after the adversarial suite." Phase 3 Tasks 4 and 5 are what make that
sentence, written before either task existed, actually true rather than
aspirational.
