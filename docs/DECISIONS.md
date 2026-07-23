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

---

## 2026-07-21 - Tier 2 seam: one parameterized Tier2Detector, not three classes or a second interface; Tier2Model is request-stateless with no cache

**Decision.** Phase 4 Task 1 adds `src/detect/tier2/model.py`
(`Tier2Model` Protocol, `ModelEntityMatch`) and
`src/detect/tier2/detector.py` (`Tier2Detector`), plus
`registry.get_tier2_detectors(model) -> Sequence[Detector]`. `Detector`
itself is unchanged. `PersonDetector`/`ORG`/`ADDRESS` (BUILD.md's own
naming) are three *instances* of one `Tier2Detector` class,
parameterized by `entity_type`, all sharing one injected `Tier2Model`
reference — not three separate class definitions, and not a second,
Tier-2-specific detector interface running alongside `Detector`.
`Tier2Model.find_entities(text)` returns every match across all types
in one call, undifferentiated; each `Tier2Detector` instance filters to
its own type. No caching or call-batching exists anywhere in this
seam: three detectors each independently call the shared model once
per text region, and nothing remembers a result between calls.

**Why one parameterized class, not three (`PersonDetector`,
`OrgDetector`, `AddressDetector` as separate definitions).** Reviewed
and changed during Phase 4 planning, before this task began: an
earlier draft of this plan considered a distinct `MultiTypeDetector`
interface for Tier 2 (Option B, below); the reviewer's explicit
instruction was to preserve the existing `Detector` abstraction and
avoid "two parallel detector ecosystems." Three separate class bodies
whose only real content is a single constant (`entity_type`) is exactly
the repetition CLAUDE.md's own refactor threshold names ("twice is a
coincidence, three times is a refactor") — one class, three
registrations, is the version of "detector-oriented" that doesn't
duplicate that constant three times.

**Alternatives considered (from the planning review).**
- A distinct `MultiTypeDetector` interface, called directly by
  `cascade.py` alongside the `Detector` registry rather than forced
  through the single-type `Detector` Protocol: rejected on explicit
  instruction — introduces a second detector-shaped abstraction
  `cascade.py` and any future contributor would need to understand,
  for a problem (one model, three types) that a shared internal
  reference already solves without touching the outward interface at
  all.
- Three separate `PersonDetector`/`OrgDetector`/`AddressDetector`
  class definitions, each independently calling a shared model
  reference: considered and rejected in favour of one parameterized
  class — functionally equivalent from `cascade.py`'s point of view,
  but three class bodies for one real difference (a constant) is
  duplicated logic without a duplicated *reason* to duplicate it.
- Caching/batching the shared model's per-text result across the three
  detectors' independent calls (so identical text isn't re-processed
  three times): explicitly not built now. CLAUDE.md's own performance
  rule applies directly ("no optimization without a before-number") —
  no real model exists yet to measure the actual cost of three calls
  against, so there is nothing yet to optimise. Deferred to Phase 4
  Task 2, to be revisited only if a real measurement shows a genuine
  cost.

**`Tier2Model` must be request-stateless — an explicit architectural
constraint, not a style note.** Per direct instruction during plan
review: `find_entities(text)` must not retain `text`, any derived
value, or any per-call state beyond the call's own execution. If a
future optimisation (the caching considered and deferred above)
introduces memoisation, it must either be scoped to one request's own
lifetime, or be demonstrably thread-safe with a bounded, explicitly-
reviewed retention policy — never a silently-added, long-lived cache
holding request text. Written directly into `Tier2Model`'s own
docstring so the constraint travels with the seam, not just this entry.

**`DetectionError` (`src/core/exceptions.py`): a new, immediate-caller
exception, not a speculative addition.** `Tier2Detector.detect()` is
the first place in this codebase that must validate offsets against a
text's actual length before trusting them: Tier-1 detectors' offsets
come from Python's own regex engine over the same string and are
always valid by construction; a model's offsets carry no such
guarantee. `Span.__post_init__` already rejects `start >= end` or
`start < 0`, but has no way to check `end <= len(text)` since a bare
`Span` never sees the source text — `DetectionError` closes that gap
at the one place text and offsets are both in scope together, named in
CLAUDE.md's own exception hierarchy in advance, given its first real
caller here rather than added ahead of need.

**Known open item, deliberately not resolved in this task.** If a real
model ever returns two *overlapping* matches of the *same* entity type
in one `find_entities()` call, `Tier2Detector.detect()` currently
returns both, unfiltered — `precedence.resolve()`'s documented
precondition (no overlap within one detector's own output) would then
not hold for that detector's contribution. Whether this is a real
behaviour any actual model exhibits is unknown without one to observe
(Phase 4 Task 2 hasn't chosen one yet); resolving it against a fake
model that can only behave however a test tells it to would be solving
an imagined problem, not an observed one. Carried forward explicitly to
Phase 4 Task 3 (cascade wiring), where real model output will actually
be available to check this against — not silently ignored, and not
pre-emptively "fixed" against a guess.

**Why.** BUILD.md, Phase 4: "Wire into the cascade behind Tier 1" and
"no fine-tuning in this phase" both presuppose a detector seam exists
to wire *into* — this task builds exactly that seam, fully tested
(`tests/unit/test_tier2_detector.py`) against a fake model, with zero
dependency on which real model Task 2 eventually chooses.

---

## 2026-07-21 - Tier 2 model selection: gliner_multi_pii-v1, chosen by measurement across two rounds of evaluation, with a real end-to-end RAM finding disclosed rather than assumed away

**Decision.** Phase 4 Task 2 integrates `urchade/gliner_multi_pii-v1`
as the real `Tier2Model` (`src/detect/tier2/gliner_model.py`), behind
Task 1's seam without any change to `Tier2Detector`, `registry.py`, or
`cascade.py`. Chosen over `gliner_small-v2.1`, `gliner_medium-v2.1`,
and `gliner_large-v2.1` after two separate, increasingly rigorous
rounds of measurement, not intuition — first a single-sentence,
five-way comparison across model sizes; then a focused, 27-sentence
synthetic corpus (slot-and-inject, gold offsets exact by construction)
comparing only the two strongest candidates head to head; then a
final, real end-to-end process-memory measurement of the actual
gateway running under `uvicorn`, not the model in isolation.

**Round 1 (five candidates, one sentence each), summary.** Measured
RAM, cold-start load time, and warm inference latency for
`gliner_small-v2.1`, `gliner_medium-v2.1`, `gliner_large-v2.1`, and
`gliner_multi_pii-v1` in an isolated scratch venv (outside the repo).
`gliner_large-v2.1` was ruled out outright: slowest (940ms-1.9s warm
latency, itself showing large run-to-run variance), heaviest to
materialize (its weights load lazily at first inference, not at
`from_pretrained()`, understating its RAM cost until measured *after*
inference), and — the deciding factor — *not* measurably better at
ADDRESS extraction than the smaller checkpoints on the one test
sentence tried. `gliner_multi_pii-v1` stood out for the opposite
reason: the only candidate that captured a full, multi-component
address ("14 MG Road, Bengaluru, Karnataka") as one span, at
medium-like latency (~200ms), though with the heaviest isolated RAM
footprint (~1.7GB).

**Round 2 (27-sentence synthetic corpus, `gliner_small-v2.1` vs.
`gliner_multi_pii-v1` only), summary.** Built to cover English,
Hinglish, Indian naming conventions (honorifics, initials,
patronymic-style), literal multi-line addresses, and abbreviation/
punctuation variation — 38 gold entities (15 PERSON, 12 ORG, 11
ADDRESS), gold offsets computed by construction (piece-by-piece
concatenation), never hand-counted. Exact-span match was fixed as the
primary criterion before running, with overlap-match reported
alongside for transparency (ARCHITECTURE.md's own "the matching
criterion changes recall by 10+ points" caveat, taken seriously here
too). Result, broken down by type - the number that actually mattered:

| Type | `gliner_small-v2.1` exact | `gliner_multi_pii-v1` exact |
|---|---|---|
| PERSON | 15/15 (100%) | 15/15 (100%) — identical |
| ORG | 9/12 (75%) | 11/12 (92%) |
| ADDRESS | **0/11 (0%)** | **5/11 (45%)** |

`gliner_small-v2.1` never once produced an exact match on a
multi-component address in this corpus — it reliably fragments them
("14 MG Road, Bengaluru, Karnataka 560001" comes back as three separate
spans) and drops trailing periods on org abbreviations. Aggregate exact
precision more than doubled (0.369 -> 0.775) and exact recall improved
materially (0.632 -> 0.816) for `multi_pii`, entirely because of this
concentrated ADDRESS/ORG gap — PERSON detection was already identical
between the two. `multi_pii`'s own honestly-disclosed residual: it
missed addresses embedded in Hinglish carrier sentences and all three
literal multi-line addresses in the corpus more often than `small` did
under overlap-matching — a real, measured weakness, not hidden.
Isolated-process cost of the improvement: +78ms warm latency (93ms ->
171ms), +491.7MB peak RSS (1186.7MB -> 1678.4MB).

**Round 3 (real end-to-end gateway process memory), summary — the
measurement that actually decided this.** Both rounds above measured
the model *in isolation* (a bare Python process running just
`torch`+`gliner`, no FastAPI/uvicorn/httpx overhead). Per direct
instruction, before Task 2 could be considered complete, the *real*
gateway (`uvicorn app.main:app`, full startup, real warmup) was
measured end-to-end for both candidates via Windows' own
`Get-Process -Id <pid>` (`WorkingSet64`, `PeakWorkingSet64`), not a
script-reported number:

| | `gliner_small-v2.1` (real gateway) | `gliner_multi_pii-v1` (real gateway) |
|---|---|---|
| Current (settled) WorkingSet | 1279.8 MB | 1533.3 MB |
| **Peak WorkingSet** (transient, during startup) | 1638.2 MB | 2216.3 MB |
| Private (committed) memory | 1597.0 MB | 2459.3 MB |
| Startup warmup latency (this run) | 15.5 s | 24.1 s |

Two things this round revealed that the isolated measurements alone
could not: first, the *full gateway's* peak RAM (2216.3MB for
`multi_pii`) is meaningfully higher than the *model alone's* isolated
peak (1678.4MB) — FastAPI/uvicorn/pydantic/httpx overhead is not
negligible on top of the model. Second, and more importantly: the
**peak** figure is a one-time transient during model loading/warmup,
not the sustained cost — the process's *current* (settled) WorkingSet
after warmup completes is 1533.3MB, only ~253MB above `small`'s own
1279.8MB. The steady-state delta (what matters while the gateway is
actually serving requests) is modest; the transient startup-only delta
(~578MB peak-to-peak) is the larger, real cost.

**System-context finding, disclosed rather than smoothed over.**
Measured on the actual target machine (7.68GB total RAM, matching
BUILD.md's stated dev environment), with a realistic *concurrent*
session state — VS Code, a browser, Windows Defender, and this
assistant's own CLI all running, exactly the "one developer's machine"
BUILD.md describes, not an idle/pristine box — only **0.91GB was free**
system-wide while the smaller model's gateway was running. Under this
real, measured condition, either candidate's startup transient is
genuinely tight against available headroom; `gliner_small`'s own peak
(1638.2MB) is already large relative to 0.91GB free. This is a property
of running any current CPU NER model in this build alongside a full
development session on a 7.68GB machine, not something uniquely
disqualifying about `multi_pii` specifically.

**Alternatives considered at this final gate.**
- Revert to `gliner_small-v2.1` given the tight measured headroom:
  rejected. The concerning number (the transient startup peak) is
  large but one-time and does not recur while serving traffic; the
  number that matters for sustained operation (steady-state RSS) shows
  only a ~253MB difference between the two candidates. Reverting over
  a one-time, ~15-25-second startup spike would discard a measured,
  concentrated, and substantial ADDRESS/ORG recall improvement
  (Round 2) for a cost that is real but smaller than the isolated
  numbers alone suggested.
- Treat the low system-wide free-RAM reading as disqualifying on its
  own: rejected — it reflects this measurement session's own crowded
  state (IDE, browser, this assistant) more than a property of the
  model choice; both candidates are tight under it, and `small` is not
  meaningfully safer by this measure than `multi_pii` is unsafe.
- Hide or soften the RAM finding to avoid relitigating an already-
  approved model choice: rejected outright — CLAUDE.md's "honest
  measurement over favourable measurement" applies with equal force to
  this project's own tooling choices, not only to the benchmark and
  adversarial suite the phrase was originally written for.

**Why.** BUILD.md, Phase 4: "Runs on CPU within my RAM budget —
measured, not assumed." All three rounds above exist because "probably
fine" was never an acceptable basis for this decision — and the third
round specifically exists because the first two, while real
measurements, were not yet the *right* measurement (the model alone,
not the system that actually ships). Recorded here in full, including
the uncomfortable transient-peak number and the crowded-machine
context, per the same discipline this project applies to its own
detector's residual weaknesses.

**Supporting artifacts (not committed — produced in an isolated scratch
venv outside the repository, per instruction not to modify the
repository during evaluation):** the 27-sentence corpus and evaluation
scripts, and the raw JSON results from all three measurement rounds.

---

## 2026-07-21 - Tier 2 wired into the cascade: detection only, name-surrogate allocation stays out of scope until Task 5

**Decision.** Phase 4 Task 3 makes `src/detect/cascade.py::detect()`
take a required `tier2_model: Tier2Model` parameter and run
`get_tier2_detectors(tier2_model)` alongside `get_tier1_detectors()`,
feeding both into the same, unmodified `precedence.resolve()` call
(Tier-1 detectors' sequences first, Tier-2's second — this only affects
the same-tier tie-break among PERSON/ORG/ADDRESS, never a cross-tier
outcome, since tier rank alone already decides those). `tier2_model` is
threaded down through `sanitize()`/`_sanitize_region()` exactly like
`key_provider`/`clock` already are, and `routes.py::chat_completions()`
supplies it via `Depends(get_tier2_model)` — the same `@lru_cache`d
singleton `app/main.py`'s startup warmup already constructs, not a
fresh construction per request. No change to `precedence.py` itself:
tracing the algorithm showed its documented "no overlap within one
detector's own output" precondition is not actually load-bearing for
correctness — it eliminates overlaps from a flat
`(span, detector_index)` list regardless of whether both spans came
from the same detector — so Task 1's "known open item" in
`Tier2Detector`'s own docstring (a model returning two overlapping
same-type matches) is closed by a test
(`test_same_type_tier2_overlap_resolves_to_the_longest_span`), not a
code change.

**Scope boundary, decided explicitly, not discovered by accident.**
This task does **not** wire real detected `PERSON`/`ORG`/`ADDRESS`
spans to `Session.allocate_or_lookup_name()` — that remains Phase 4
Task 5's scope (see `docs/PHASE_4_SUMMARY.md`'s own "known limitations"
list, written before this task began: "Phase 4 Task 5 replaces
[the placeholder name list] with a production-sized, synthetic list
before real name allocation is wired to detected PERSON spans"). The
consequence, surfaced to the product owner before implementing rather
than discovered afterward (CLAUDE.md, Decision Making: "do not resolve
it by implementing"): once Tier 2 is live in the cascade, **any request
containing a detectable name, organisation, or address now raises
`SurrogateDomainError`** via `sanitize()` — `src/surrogate/registry.py`
has no FF1 domain for those three types, exactly as it already has none
for UPI/email. `app/main.py`'s existing `SurrogateDomainError` handler
turns this into a clean, documented 500, not a crash and not a silent
pass-through of the real value — the same failure shape UPI/email
requests already produce today, extended to three more types until
Task 5 lands.

**Alternatives considered.**
- Pull part of Task 5 forward: also wire `sanitize()` to call
  `Session.allocate_or_lookup_name()` for Tier-2 spans now, using the
  existing Phase-3 *placeholder* 40-name list, so name-bearing requests
  succeed end-to-end sooner. Presented to the product owner as a real
  option, not assumed — rejected in favour of the detection-only scope:
  it would mean shipping name substitution against a list explicitly
  documented as "nowhere near enough for real Tier-2 traffic"
  (`src/session/names.py`), blurring which task actually delivered
  production-ready name allocation, and mixing a Task 3 concern
  (detection wiring) with a Task 5 concern (surrogate allocation) in
  one change.
- Silently swallow `SurrogateDomainError` for Tier-2 types specifically
  and pass the real value through unsanitised until Task 5: rejected
  outright — this is exactly the "half-sanitized request is a leak"
  case CLAUDE.md's Error Handling section rules out; crashing loudly is
  strictly better, and is already this project's established behaviour
  for UPI/email.
- Gate Tier-2 detection itself behind a settings flag so it can be
  "turned on" only once Task 5 lands: rejected — an inactive
  feature flag with no current caller is exactly the kind of
  speculative, ahead-of-need addition CLAUDE.md's exception-hierarchy
  rule (and this project's general anti-scope-creep posture) argues
  against elsewhere; the existing `SurrogateDomainError` failure path
  already provides a correct, loud, non-leaking behaviour with no new
  configuration surface.

**Test-suite side effect, found and fixed in this same task.** Adding
`Depends(get_tier2_model)` to the real route meant every existing
integration test that POSTs to `/v1/chat/completions` through the real
`app` without overriding it (`test_chat_completions_route.py`,
`test_sanitize_integration.py`, `test_rehydrate_integration.py`,
`test_phase_3_gate.py`, `test_openai_sdk_compatibility.py` — none of
them `real_model`-marked or Tier-2-related) would have started loading
the real, multi-second, ~1.5GB+ GLiNER model on first request,
defeating `pytest.ini`'s entire `-m "not real_model"` split. Fixed with
one shared, autouse fixture in `tests/conftest.py`
(`_no_real_tier2_model_over_http`) overriding
`app.dependency_overrides[get_tier2_model]` with a zero-cost fake for
every test, mirroring how `get_upstream_client` is already overridden
per-file — centralised here instead, since this override is correct
for the entire suite, not specific to any one test module.
`tests/integration/test_tier2_real_model.py` is unaffected: it
constructs `GLiNERTier2Model`/calls `get_tier2_model()` directly,
bypassing FastAPI's dependency system entirely, so the override never
shadows it.

**Why.** BUILD.md, Phase 4: "Wire into the cascade behind Tier 1. Tier
1 wins on overlap per the Phase-2 precedence rule" and "Cascade
precedence tested: a PAN inside a span Tier 2 calls ORG resolves per
the documented rule" are both proven directly —
`tests/unit/test_cascade.py::test_tier1_wins_over_an_overlapping_tier2_span_the_build_md_gate_scenario`
against a fake model (deterministic, fast) and
`tests/integration/test_tier2_real_model.py::test_cascade_resolves_a_real_tier1_tier2_overlap_tier1_wins`
against the real one (slow, `real_model`-marked, written to hold
regardless of GLiNER's actual labelling choice on the test sentence).
Tier-hit instrumentation (the DoD's third bullet) needed no new code:
`sanitize.py`'s existing `log_event("pipeline.span_sanitized", ...,
tier=span.tier, ...)` already logs which tier resolved a span, for any
tier value, and now genuinely observes `tier=2` for the first time.

---

## 2026-07-21 - FAIL_MODE gates the Tier-2 stage: caught inside cascade.detect(), broadly by type but narrowly by scope

**Decision.** Phase 4 Task 4 wraps only the Tier-2 detection step
inside `src/detect/cascade.py::detect()` —
`[detector.detect(text) for detector in get_tier2_detectors(tier2_model)]`
— in a `try`/`except Exception`, handing any failure to
`src/core/fail_mode.py::resolve_failure()`. Tier-1 detection,
`precedence.resolve()`, and ingress recognition are not wrapped at all
— they have no failure mode to guard (`re.finditer` over a `str` cannot
raise for any input). `detect()` gains two new required parameters,
`fail_mode: FailMode` and `correlation_id: CorrelationId` (the latter
because `resolve_failure()` needs one to log against), threaded down
from `routes.py` through `sanitize()`/`_sanitize_region()` exactly like
`tier2_model` already is. `get_fail_mode()` (new, in `fail_mode.py`) is
a thin `get_settings().fail_mode` factory, injected in `routes.py` via
`Depends(get_fail_mode)` — mirroring `get_key_provider()`'s/
`get_session_store()`'s own shape, not a new pattern. `app/main.py`
gains a `FailClosedError` → 503 handler, fulfilling the mapping
`fail_mode.py`'s own docstring already named in advance ("The proxy
layer, not this module, maps this to a 503").

**On `open`:** `resolve_failure()` logs a WARNING
(`detection.tier2_failed`) and returns; `detect()` then treats Tier-2 as
having contributed zero spans for that text region — Tier-1's own spans
(already computed *before* Tier-2 was attempted) are entirely
unaffected, since they're collected into a separate list before the
Tier-2 `try` block ever runs.

**On `closed`:** `resolve_failure()` raises `FailClosedError`, chained
from the original cause, aborting `detect()` (and therefore
`sanitize()`, and therefore the whole request) before any Tier-1
substitution is lost — `sanitize()`'s no-partial-body invariant already
guaranteed this for `SurrogateDomainError`; this is the same guarantee,
now proven for a Tier-2 failure too
(`tests/unit/test_sanitize.py::test_tier2_failure_with_fail_mode_closed_raises_fail_closed_error_and_body_untouched`).

**Why `except Exception`, not a named type — the one deliberate
exception to "catch the narrowest type you can name."** Two distinct
failure shapes are gated identically here: `DetectionError` (this
codebase's own typed exception, raised by `Tier2Detector.detect()` for
a bad model offset) and an arbitrary exception from the model call
itself (`Tier2Model.find_entities()` — the "model unavailable" case
ARCHITECTURE.md names separately). The second cannot be named
specifically the way `upstream_client.py` names `httpx.TimeoutException`/
`httpx.ConnectError`: httpx is a well-typed library with a documented
exception hierarchy for exactly this boundary; a CPU NER model
(`gliner`/`torch`) has no equivalent contract this codebase can cite,
and enumerating "every exception type gliner or torch might raise" is
both incomplete today and liable to silently stop matching after a
dependency upgrade. The catch is kept narrow in the one dimension that
is actually controllable: *scope*. Only the single `get_tier2_detectors()`
call is wrapped — not Tier-1 detection, not precedence resolution, not
ingress recognition, not any other line in the function — so a bug
anywhere else in `detect()` still propagates unguarded, exactly as
CLAUDE.md's error-handling philosophy requires. This is never a silent
swallow either way: `resolve_failure()` always either logs at WARNING
(`open`) or raises loudly (`closed`) — there is no path where the
caught exception simply vanishes.

**Alternatives considered.**
- Catch only `DetectionError`, leave a raw model exception unguarded:
  rejected — ARCHITECTURE.md names "model unavailable" as its own
  failure mode requiring `FAIL_MODE`, distinct from a bad-offset
  `DetectionError`; leaving it unguarded would mean the one failure
  mode BUILD.md's Task 4 description opens with ("model unavailable, or
  a `DetectionError`...") is the one left unhandled.
- Gate the whole `detect()` call (Tier 1 included), on the theory that
  "the detection stage" is one unit: rejected — Tier 1 has no failure
  mode to guard, so wrapping it would either never trigger (dead code
  the tests can't meaningfully exercise) or mask a real Tier-1 bug
  (e.g. a checksum module regression) behind `FAIL_MODE=open`'s
  swallow-and-continue path, which is a correctness regression wearing
  a resilience costume.
- Push the try/except one layer up, into `sanitize.py`, wrapping the
  call to `cascade.detect()` itself: rejected — `fail_mode.py`'s own
  Phase 1 docstring already anticipated this exact call site
  ("the real call site lives *below* pipeline... a detector-level
  concern"), and catching at `sanitize.py` would mean a Tier-1-only
  bug raised from inside `detect()` (there is none today, but nothing
  stops one existing later) gets caught by the same broad handler
  meant only for Tier-2 - conflating two different guarantees behind
  one catch site.

**Why.** BUILD.md, Phase 4 Task 4 (this document's own prior entry's
"what's next"): "consume `FAIL_MODE` for a Tier-2 detection failure
(model unavailable, or a `DetectionError` from an out-of-bounds model
offset) — currently both propagate unhandled past `sanitize()`."
Both are now proven gated, at the cascade level
(`tests/unit/test_cascade.py`, four tests spanning both failure shapes
and both `FAIL_MODE` values), the sanitize level
(`tests/unit/test_sanitize.py`, two tests), and the real HTTP route
(`tests/integration/test_chat_completions_route.py`, two tests proving
the actual 503/200 status codes a caller would see).

---

## 2026-07-21 - Phase 4 Task 5: all three Tier-2 types get name-map surrogates, via generated (not hand-typed) candidate pools

**Decision.** Task 5's scope, decided explicitly before implementing
(the product owner's call, not this document's to make alone): all
three Tier-2 entity types — `PERSON`, `ORG`, `ADDRESS` — are wired to
`Session.allocate_or_lookup_name()`, not `PERSON` alone. This closes
Task 3's disclosed `SurrogateDomainError` gap for all three, fully
satisfying BUILD.md's Phase 4 gate text ("a name, an org, an address,
and a PAN... surrogates consistent across turns") rather than leaving
two of the three types permanently unsanitizable.

Three new candidate-pool modules replace Phase 3's 40-entry `PERSON`
placeholder: `src/session/names.py` (`PERSON`, expanded), `org_names.py`
(`ORG`, new), `addresses.py` (`ADDRESS`, new). Each is generated from
two small seed pools combined by cartesian product (~70 x ~70 ≈
4,900-5,100 candidates each) rather than hand-typed — the same
"programmatic generation over manual authoring" methodology BUILD.md's
benchmark section already mandates ("slot carriers... entities injected
programmatically"), applied here to a candidate *pool* instead of a
labeled dataset. `src/session/candidates.py` is a new registry —
`NAME_MAP_ENTITY_TYPES` (the shared source of truth for "which entity
types use the map", replacing a set `rehydrate.py` used to hardcode on
its own) and `get_candidates(entity_type)` (mirrors
`src/surrogate/registry.py::get_surrogate_domain()`'s shape for the FF1
side). `src/session/rng.py` adds `get_rng()`, injected into
`sanitize()`/`routes.py` for `allocate_or_lookup_name()`'s required
`rng` parameter.

**Why generated pools, not real company/street names.** `org_names.py`'s
root-word pool deliberately excludes real, identifiable companies (no
"Tata", "Infosys", "Reliance", etc.) — a surrogate that *is* a specific
real company is a materially worse residual than a low-probability
shape coincidence (unlike Aadhaar's reserved-range residual, this would
be a guaranteed, obvious collision with one particular real entity, not
a statistical one). `addresses.py`'s street-name pool uses generic
patterns reused across hundreds of real Indian cities (`Gandhi Road`,
`Station Road`, figure-named roads) rather than a single uniquely
identifying real street, for the same reason. City/state names in
`addresses.py` are necessarily real (a fixed, public set) — no
different from a benchmark carrier sentence naming a real city.

**Why a fresh `random.Random()` per request, not a cached singleton
(`get_rng()`, unlike `get_key_provider()`/`get_session_store()`/
`get_tier2_model()`).** `Session.allocate_or_lookup_name()`'s own lock
only serialises access to *that one session's* state — it says nothing
about a shared RNG object two *different* sessions' concurrent calls
might both be mutating at once. `random.Random`'s methods are not
thread-safe against concurrent callers, so a single cached instance
reused across concurrent requests on different sessions would be a real
bug: two threads calling `.shuffle()` on the same `Random` object
simultaneously, unsynchronised. A fresh, unseeded instance per call
sidesteps the question entirely, at effectively zero construction cost,
rather than adding a lock this project's threading model doesn't
otherwise need.

**`REQUIRED_WINDOW_LOOKAHEAD` widened from `PERSON`-only to all three
pools — a real correctness fix, not a refactor.** Before this task,
`rehydrate.py` derived the response-path sliding window's lookahead
margin from `max(len(name) for name in DEFAULT_NAME_CANDIDATES)` —
correct while only `PERSON` used the name map, silently wrong the
moment `ADDRESS` surrogates (structurally much longer than "First
Last" names) could also appear. `src/session/candidates.py::max_candidate_length()`
now spans all three pools; `rehydrate.py` imports it instead of
reaching into `names.py` directly, and imports the shared
`NAME_MAP_ENTITY_TYPES` instead of hardcoding its own copy of the same
three-element set (CLAUDE.md: "no duplicated logic") — this was a real,
if latent, duplication: `rehydrate.py`'s own `_NAME_MAP_ENTITY_TYPES`
was defined independently of wherever `sanitize.py` would eventually
need the identical set, and Task 5 is precisely that "eventually."

**A real substring-collision case now exists in the name-map pools,
where the old docstring claimed none did — documented, not fixed.**
`rehydrate.py`'s module docstring previously claimed "no name in
`src/session/names.py`'s placeholder list is a prefix of another." That
claim is false for the new list: last names `"Khan"`/`"Khanna"` mean
`"Priya Khan"` is a literal substring of `"Priya Khanna"` if a session
ever mints both. This is not a new bug — `_pattern_for()`'s existing
longest-first alternation (built in Phase 3 Task 4, tested by
`test_longest_known_surrogate_wins_when_one_is_a_substring_of_another`)
already resolves it correctly, exactly as it already does for the
FF1 side. Confirmed by re-reading `_pattern_for()` and Python's `re`
alternation semantics rather than assumed: case sensitivity means a
*shorter* name can never accidentally match as a substring starting
mid-word inside a *longer* one (a mid-word position is lowercase; every
candidate's own leading letter is capitalised), so the only real
collision shape is one candidate being an exact *prefix* of another
sharing the same leading token — which `"Khan"`/`"Khanna"` is, and which
the existing mechanism already handles. The module docstring is
corrected to state this as a real, present case rather than a
theoretical one ruled out by inspection.

**Alternatives considered.**
- Hand-type ~5,000 individual names/orgs/addresses: rejected outright —
  exactly the "classic time sink" BUILD.md's benchmark section already
  names as a reason to generate programmatically instead, applied here
  to a candidate pool for the same reason.
- Scope this task to `PERSON` only, per the narrower framing a prior
  session had already written into `PHASE_4_SUMMARY.md`'s "known
  limitations"/"what's next": presented to the product owner as a real
  option (not assumed away) — rejected in favour of all three types,
  since BUILD.md's own Phase 4 gate text names org/address surrogate
  consistency explicitly, and leaving two of three Tier-2 types
  permanently unsanitizable is a worse "Phase 4 complete" story than
  building two more (mechanically identical) candidate pools.
- A single shared `random.Random()` singleton for `get_rng()`, matching
  the other factories' `@lru_cache` shape: rejected — see the
  concurrency reasoning above; this is the one factory in this family
  where caching is actively wrong, not merely unnecessary.
- Keep `rehydrate.py`'s own hardcoded `_NAME_MAP_ENTITY_TYPES` rather
  than centralising it in `session/candidates.py`: rejected — the
  moment `sanitize.py` needed the identical set (this task), keeping
  two independent copies in sync by hand is exactly the drift
  CLAUDE.md's "no duplicated logic" rule exists to prevent.

**Why.** BUILD.md, Phase 4: "Name surrogates from the finite name list
via the Phase-3 map" — now genuinely true for all three Tier-2 types,
proven end-to-end at the cascade-adjacent sanitize level
(`tests/unit/test_sanitize.py`, including a same-session
consistency test) and over the real HTTP request/response cycle
(`tests/integration/test_chat_completions_route.py::test_person_span_round_trips_through_the_full_http_request_response_cycle`),
mirroring the FF1 side's existing round-trip proof
(`test_rehydrate_integration.py`).

---

## 2026-07-21 - Phase 4 closeout: a committed gate test, two stale-documentation fixes, one stale-comment fix

**Decision.** Before writing the Phase 4 closeout summary, the
repository was reviewed for the same things every phase closeout in
this project checks: temporary code, stale comments, duplicated logic,
and documentation that no longer matches what the code actually does.
Three real findings, all fixed as part of closing this phase rather
than carried forward silently:

1. **BUILD.md's own Phase 4 gate line had no single committed,
   reproducible test proving it**, verbatim: "Hinglish sentence with a
   name, an org, an address, and a PAN -> correct spans, correct tier
   attribution, surrogates consistent across turns." The capability
   existed (Tasks 3-5), but the specific, literal gate scenario was
   only ever demonstrated piecemeal across several narrower tests, none
   of which used genuinely Hinglish/code-switched text. Closed with a
   new `real_model`-marked test,
   `tests/integration/test_phase_4_gate.py::test_phase_4_gate_hinglish_name_org_address_and_pan`,
   mirroring `test_phase_3_gate.py`'s own closeout-task pattern (Phase
   3, Task 6). The sentence used was not invented and hoped for — it
   was run directly against `get_tier2_model()` first (a throwaway
   probe script, not committed) to confirm the real model actually
   resolves `PERSON`, `ORG`, and `ADDRESS` in it before the test's
   assertions were written around that observed behaviour, the same
   "measure, don't guess" discipline Task 2's own three-round model
   evaluation already established. "Consistent across turns" is proven
   by sending the identical real-value content twice on one session and
   asserting the two sanitized bodies that crossed to "upstream" are
   byte-identical — a single, robust assertion covering all four
   entities' consistency at once, rather than parsing individual
   surrogate spans out of a Hindi-English-mixed sentence.
2. **`docs/LIMITATIONS.md`'s UPI/email entry claimed "Resolved in Phase
   3."** It was never resolved — the entry's own body already said so
   ("no surrogate domain is registered... the session-scoped map...
   doesn't exist until Phase 3," which reads correctly only as "not yet
   resolved, pending Phase 3," not "resolved by Phase 3"). Phase 3 built
   the map; nothing in Phase 3 or Phase 4 ever registered UPI/email
   against it (`src/session/candidates.py`'s `NAME_MAP_ENTITY_TYPES` is
   `PERSON`/`ORG`/`ADDRESS` only — the three types BUILD.md's Phase 4
   scope actually names). Corrected in place, with the correction
   itself stated in the entry rather than silently fixed — a wrong
   "resolved" claim sitting in a limitations file is a worse failure
   than the original gap, since a reader trusts this specific file to
   be current.
3. **`docs/LIMITATIONS.md`'s "no unstructured-entity detection yet"
   entry was stale** — Phase 4 resolves exactly what it describes. Kept
   (not deleted) and marked resolved, per this file's own established
   convention for entries later phases close (see the ingress-surrogate
   and UPI/email entries already using this pattern).
4. **A comment in `src/session/session.py`
   (`allocate_or_lookup_name()`) said "no Tier-2 detector exists yet to
   produce this [a same real_value, two different entity_types
   collision]."** False as of this same phase's Task 5 — real
   detectors now call this method for all three name-map types.
   Corrected to state the case is now reachable in principle (not
   merely hypothetical), while keeping the same underlying engineering
   call: this remains an accepted Phase 3 simplification, not something
   to fix speculatively without an observed failure.

**Why fix these now rather than note them and move on.** CLAUDE.md:
"if a comment is wrong, fix it" (comments), and this project's own
standard for `docs/LIMITATIONS.md` specifically is that it "states,
plainly, what this system does not yet guarantee" — a limitations file
containing an incorrect "resolved" claim is actively worse than an
honestly-stated open gap, because a future reader (or a reviewer
checking "did you configure things fairly," CLAUDE.md's own recurring
example question) has no way to tell the difference between "resolved"
and "claimed resolved, actually still broken" without independently
re-verifying every claim — exactly the trust the rest of this project's
documentation discipline is built to avoid requiring.

**What was checked and found clean, not requiring changes.** No
TODO/FIXME/XXX markers, no `print()`/`breakpoint()` calls, no skipped or
`xfail`-marked tests, no commented-out code, anywhere under `src/`,
`app/`, or `tests/`. `mypy.ini`/`pytest.ini`/`.env.example`/
`requirements.txt` all already reflect Phase 4's additions (`gliner`
type-stub scoping, the `real_model` marker, `NER_MODEL`/`NER_WARMUP`,
the CPU-only torch wheel index) with no drift found. `PROJECT_STATE.md`
remains, correctly, absent — a Phase 0 decision (see
`docs/PHASE_0_SUMMARY.md`), reaffirmed at every phase closeout since
(Phase 2, Phase 3), not an oversight of this phase.

**Why.** BUILD.md's Phase Protocol requires closing each phase with a
verified DoD and updated documentation before the next phase begins;
this is that verification, performed directly against the repository's
actual current state rather than assumed from the summary documents
already on file.

---

## 2026-07-22 - Phase 5 Task 1: span-matching criterion fixed as exact-span, exact-type, before any benchmark code exists

**Decision.** The benchmark's scoring criterion for "did an arm detect
this entity" is **exact-span match**: a predicted detection counts as a
true positive for a gold entity if and only if `predicted.start ==
gold.start`, `predicted.end == gold.end` (character offsets into the
example's raw text, half-open interval, matching `src/core/types.py`'s
existing `Span` convention exactly), **and** the predicted entity type
maps, under a canonical cross-arm type table (built in the scorer task,
not this one), to the gold entity type. No partial credit, no
overlap-fraction threshold, no tokenizer of any kind is used anywhere
in scoring.

Matching is one-to-one per gold span: at most one predicted span may be
credited against a given gold span. Where a single arm emits more than
one prediction with the offsets and type that would match one gold
span, only one counts as the true positive; any others are counted as
false positives against that arm's own precision. This prevents an arm
from inflating recall by over-predicting. Full assignment mechanics
(how ties among multiple *distinct* overlapping predictions are broken,
if that case arises in practice) are an implementation detail of the
scorer task, not a methodological choice this entry needs to fix in
advance — the *matching rule itself* (exact offsets, exact type,
one-to-one) is what must be fixed now, per BUILD.md, and is.

This entry exists and is written *before* `benchmarks/` contains a
single line of scoring code, and before the dataset generator (Task 2)
or any arm integration (Tasks 4-6) exists — deliberately, per BUILD.md's
own instruction for this exact decision ("Span-matching criterion fixed
**before measuring**") and CLAUDE.md's forbidden-actions list ("Change
the span-matching criterion after seeing results").

### 1. What BUILD.md actually requires here

Two passages constrain this decision, and neither is optional:

- Phase 5's bullet list: *"Span-matching criterion fixed before
  measuring. Exact-span vs token-level vs partial credit differ by 10+
  points. Pick one, justify it in `docs/DECISIONS.md`, apply it
  identically to all four arms."*
- Phase 5's Definition of Done: *"Span-matching criterion documented and
  applied uniformly."*

ARCHITECTURE.md's Benchmark Architecture section restates the same
three named options and adds one fact this decision must engage with
directly: *"Presidio's own evaluator uses token-level."* CLAUDE.md's
forbidden-actions list adds the enforcement mechanism: the criterion,
once fixed, may not move after results exist, for any reason, including
an unfavourable result.

Nothing in BUILD.md or ARCHITECTURE.md names a fourth criterion beyond
the three above (exact-span, token-level, partial-overlap) — those are
the only ones "explicitly discussed," so those are the three compared
below.

### 2. The three options, compared on this project's own terms

**Exact-span matching.** A prediction matches only if its `(start, end,
entity_type)` is identical to the gold span's.

- *Advantage — it is the only criterion that measures the actual
  operational property this system claims.* CLAUDE.md: *"Off-by-one on
  overlapping spans corrupts the JSON body."* Substitution happens at
  exact character offsets — a detector that finds "roughly the right
  entity" with the wrong boundary does not produce a correct FF1
  surrogate (wrong domain length) or a correct name-map substitution
  (wrong text sliced out) in the real pipeline. A benchmark criterion
  more forgiving than the pipeline's own correctness requirement would
  report a recall number the pipeline cannot actually deliver in
  production.
- *Advantage — no external tokenizer, so no hidden per-arm bias.* The
  four arms tokenize completely differently on the inside: Tier 1's
  regex/checksum detectors emit raw character offsets tied to no
  tokenizer at all; Presidio's default backend uses spaCy's tokenizer;
  GLiNER uses its own subword tokenizer. Any token-level or
  overlap-based criterion requires picking *one* tokenizer to score all
  four arms with — a choice with no principled answer here — and
  whichever arm's natural span boundaries happen to align best with
  that scorer's tokenizer boundaries would be favoured for reasons
  unrelated to whether it actually got the entity right. Exact
  character-offset comparison needs no such choice and is identical
  regardless of what any arm's internals do.
- *Advantage — zero free parameters.* No threshold, no weighting scheme,
  nothing to tune. Consistent with CLAUDE.md's "no magic constants" and
  "boring is a feature" — and, more specifically here, nothing left for
  a future session to be tempted to adjust once real numbers exist.
- *Advantage — the gold labels have no legitimate ambiguity to be lenient
  about.* This is the point of slot-and-inject (BUILD.md, Phase 5):
  entities are injected programmatically into carrier templates at
  known slot boundaries, so gold offsets are exact by construction, not
  a human annotator's judgment call about where a name "really" starts.
  Token-level and partial-overlap criteria exist mainly to absorb
  *annotator* disagreement in human-labeled corpora (e.g. CoNLL-style
  NER benchmarks) — a problem this dataset does not have, because
  nobody is annotating it. Being lenient about an ambiguity that does
  not exist here would only be absorbing *detector* imprecision, which
  is exactly the thing being measured.
- *Disadvantage — it is harsh on genuinely-partial detections.* A
  detector that returns `"Arjun"` for a gold `"Arjun Reddy"` PERSON
  span, or that includes/excludes a leading title (`"Mr. Arjun Reddy"`
  vs. `"Arjun Reddy"`), scores as a complete miss, not partial credit,
  even though something about the entity's location was found. This is
  a real cost, addressed below (why it is accepted rather than
  designed around).
- *Disadvantage — diverges from Presidio's own convention*, discussed
  in its own section below rather than folded in here, because it is
  the one point ARCHITECTURE.md itself flags and deserves a direct
  answer.

**Token-level matching.** Text is tokenized; each token is scored
independently (present in a gold span of type X → should be predicted
as type X), and P/R/F1 are computed over tokens rather than whole
spans.

- *Advantage — more forgiving of boundary imprecision*, and it is the
  scheme `presidio-evaluator` (Presidio's own measurement tool) uses by
  default, so it has a ready-made, well-precedented implementation to
  point at.
- *Disadvantage — requires choosing a tokenizer, and that choice is not
  neutral here.* As above: this project's own differentiator is
  Hinglish/Telugu-English code-switched and transliterated text —
  exactly the text where tokenization is least standardized and most
  tokenizer-dependent. A token-level score computed with, say, spaCy's
  tokenizer would be silently measuring "how well did each arm's
  entity match spaCy's idea of a token boundary," which is a different
  question from "did this system correctly protect this entity," and
  is a question this project has no principled way to prefer one
  tokenizer's answer to over another's.
- *Disadvantage — decouples the score from the pipeline's real failure
  mode.* A system can score high token-level recall while producing
  zero spans whose exact offsets would actually round-trip correctly
  through substitution — the metric would say "mostly protected" about
  requests the real pipeline would corrupt or leave partially
  sanitized. For a benchmark whose entire purpose is to be trustworthy
  about a privacy property (CLAUDE.md: "Honest measurement over
  favourable measurement"), a metric that can read well while the
  underlying security property fails is the wrong metric, independent
  of whether it happens to make any particular arm look better or
  worse.

**Partial-overlap / partial-credit matching** (e.g. any predicted span
overlapping a gold span of the same type counts as at least a partial
match, optionally weighted by overlap fraction or a MUC-style scheme).

- *Advantage — most forgiving; captures "detected roughly the right
  entity."*
- *Disadvantage — introduces at least one more arbitrary parameter*
  (an overlap threshold, or a weighting function) with no principled
  value for this project, which is precisely the kind of knob CLAUDE.md
  warns against turning after seeing results ("Do not tune until arm 4
  wins"). A parameter that does not exist cannot be tuned, consciously
  or not; a parameter that does exist eventually will be, even if only
  by omission of scrutiny.
- *Disadvantage — the weakest correspondence to any real privacy
  outcome.* Substitution is binary in the real pipeline: an entity is
  either correctly replaced by a surrogate or it is not. "70% span
  overlap" is not a state a real request can be in. Reporting a recall
  number under this criterion risks implying a graduated privacy
  outcome (partially protected) where none exists (the un-substituted
  remainder of a partially-matched entity still fully identifies the
  person). This is the sharpest mismatch of the three options against
  ARCHITECTURE.md's own stated privacy claim: *"Structured entities are
  checksum-guaranteed... Names... are best-effort... This system
  provides risk reduction with a measured residual. It does not provide
  a privacy guarantee."* A partial-credit recall number is closer to
  overclaiming that guarantee than exact-match recall is.

### 3. Why Presidio's own token-level convention is not adopted here

ARCHITECTURE.md names this specifically, so it gets a direct answer
rather than an implicit one. Adopting Presidio's own evaluator
convention would have one real advantage — it is Presidio's own
yardstick, so a Presidio maintainer could not object to being measured
by their own tool's logic. But it does not survive the two reasons
above: it still requires choosing a tokenizer applied uniformly to all
four arms (Presidio's evaluator ships with its own default, which is
not obligated to be neutral toward the other three arms' internals),
and it still decouples the reported number from whether the request
would actually be correctly sanitized in this project's real pipeline.
"Score everyone the way the baseline scores itself" is a fairness
argument about the *baseline comparison*, not about which number best
answers this project's own question ("would this have leaked?"), and
CLAUDE.md's hierarchy is explicit that evaluation honesty about *this
project's own claim* outranks matching a competitor's convention for
its own sake.

### 4. Recommendation, stated from first principles only

**Exact-span, exact-type matching, one-to-one per gold span, no
tokenizer, no partial credit.** This follows from three facts about
this specific project, not from any expectation about which arm the
criterion will favour:

1. The system's own domain type is already `(start, end, entity_type)`
   (`src/core/types.py::Span`), and the system's own correctness
   contract already depends on exact offsets (offset-based substitution,
   `precedence.py`'s existing half-open-interval overlap semantics).
   Scoring against anything looser than the type the rest of the
   codebase already uses to define correctness would be measuring a
   different, easier question than the one that matters.
2. The dataset's gold labels have no annotation ambiguity to accommodate
   — they are exact by construction (slot-and-inject), which is the one
   precondition that makes strict exact-match scoring *fair* rather than
   merely strict. A benchmark with human-annotated, inherently-fuzzy
   gold labels would have a real argument for token-level or
   partial-overlap leniency; this one does not.
3. A harsher, more honest number is the correct trade for a project
   whose stated goal is "honest measurement over favourable measurement"
   and whose own privacy claim is explicitly a "measured residual," not
   a guarantee. Exact-match will report a lower number than the other
   two options on the same system — that is a feature of this criterion
   for this project, not a defect to be designed around, and it must not
   be revisited once arm 4's number is known.

This recommendation is made before the dataset exists, before any arm
is wired up, and before any P/R/F1 number of any kind has been computed
for any arm — consistent with the requirement it is enforcing.

### 5. Why changing this after benchmark generation would invalidate the comparison

The criterion is not a presentation choice made after the fact; it is
part of the *definition* of what "detected" means, and that definition
must be identical and fixed across all four arms for the comparison to
mean anything at all:

- **Changing it after seeing results turns methodology into a knob.**
  BUILD.md is explicit that arm 3 ≈ arm 4 is an acceptable, even good,
  finding ("the cascade buys latency, not accuracy"). If the criterion
  could still move at that point, there would be no way to distinguish
  "we found an honest result" from "we adjusted the ruler until our arm
  won" — and a reviewer cannot tell the difference from the outside
  either, which is exactly the credibility failure CLAUDE.md's
  forbidden-actions list names directly ("Tune the detector against the
  benchmark until our arm wins" / "Change the span-matching criterion
  after seeing results").
- **A criterion swap after generation silently changes which detections
  count, per arm, unevenly.** Because the three criteria diverge by
  10+ points on the *same* system (BUILD.md's own stated fact) and
  the four arms have structurally different span-boundary behaviour
  (regex/checksum vs. spaCy-tokenized vs. GLiNER-subword-tokenized),
  a switch from exact-span to token-level after the fact would not move
  every arm's score by the same amount — it would asymmetrically help
  whichever arm's boundary behaviour happens to align best with
  whatever tokenizer got chosen at that later point. That asymmetry is
  invisible in the final table; only the process discipline of fixing
  the criterion first prevents it from ever being introduced.
- **The committed artifact's reproducibility guarantee depends on it.**
  BUILD.md's gate for this phase is deleting the README numbers, running
  `make bench`, and getting the same numbers back. A scoring criterion
  that could plausibly have been different is not a fixed part of the
  measurement process — it is an unrecorded input, and the reproduced
  numbers would only be reproducible *given* a methodology choice that
  itself was never pinned down in advance, which does not satisfy the
  gate in spirit even if it satisfies it mechanically.

**Not decided by this entry, deliberately deferred to the scorer task
(Task 7):** the canonical entity-type mapping table across arms (e.g.
how Presidio's default type names map onto this project's
`EntityType`s), and the exact one-to-one assignment algorithm when more
than one distinct predicted span could plausibly match one gold span.
Those are implementation mechanics of *applying* this criterion, not
part of the criterion itself, and do not need to be fixed before the
dataset or any arm exists — only the matching rule does, per BUILD.md's
own phrasing ("pick one... apply it identically"), and that is what
this entry fixes.

---

## 2026-07-22 - Phase 5 Task 7: a coincidental cross-type Tier-1 checksum
collision, discovered by the scorer's own test suite, not a bug

**Decision.** No code changes at the time of this entry. This entry
records a real, reproducible phenomenon
`tests/integration/test_scoring_real_arm.py` discovered while proving
the scorer (`benchmarks/scoring/`) against the real, committed Phase 5
dataset and a real arm: a small fraction of generated `PHONE` values are,
by pure coincidence, also Verhoeff-valid (or Luhn-valid), making them
indistinguishable in shape and checksum validity from a genuine
`AADHAAR` (or `CARD`) candidate at the exact same span. When this
happens, `precedence.resolve()`'s already-approved (Phase 2) same-tier
tie-break — longest match, then detector registration order — correctly
and deterministically attributes the span to whichever detector is
registered first (`AadhaarDetector`, then `CardDetector`, ...,
`PhoneDetector` last — `src/detect/registry.py`). The gold label says
`PHONE`; the cascade reports `AADHAAR`. Scored under the exact-span,
exact-type criterion, this is a genuine false negative for `PHONE` (and
a genuine false positive for `AADHAAR`) — not a scorer bug, not a
cascade bug, and not a dataset-generator bug in the sense of doing
anything the generator wasn't supposed to do at the time.

**Mechanism, confirmed directly, not inferred.** `benchmarks/generate/entity_values.py::_generate_phone()`
produces a `"91"`-prefixed value with probability 1/4 (one of four
equally-likely prefixes: `""`, `"+91"`, `"91"`, `"0"`); a `"91"`-prefixed
value is exactly 12 digits — identical in length to `AadhaarDetector`'s
`\b\d{12}\b` candidate pattern. Whether the resulting 12-digit string
also happens to be Verhoeff-valid is then a roughly 1-in-10 event (one
valid check digit out of ten possible trailing digits), independent of
how the leading digits were chosen. A `"+91"`-prefixed value (13 digits)
sits inside `CardDetector`'s `\d{12,19}` range and has an independent
~1-in-10 chance of being Luhn-valid. Verified against two real examples
produced by the actual generator during this investigation:
`918298529155` (Verhoeff-valid — confirmed via `verhoeff_is_valid()`)
and `917818830734` (Luhn-valid — confirmed via `luhn_is_valid()`); both
were confirmed, by calling `cascade.detect()` directly, to resolve to
`AADHAAR`/`CARD` respectively, never `PHONE`, in the full cascade.

**Why `PHONE` is the only type with this exposure.** `PAN`/`IFSC`/`UPI`/
`VEHICLE_REG`/`EMAIL` are never pure-digit, so they can never match
`AADHAAR`'s or `CARD`'s all-digit patterns at all. `AADHAAR` itself is
registered *before* `CardDetector`, so a coincidentally-Luhn-valid
Aadhaar value still wins its own tie and is never mis-attributed.
`CARD`'s own generated values are 16 digits with a fixed leading `4`,
and `AadhaarDetector`'s `\b\d{12}\b` pattern requires a word boundary on
both sides — a 12-digit substring in the middle of a 16-digit run has no
such boundary, so a Card value can never be mistaken for an Aadhaar
candidate. Only `PhoneDetector`, registered last, with two of its four
possible prefixes landing inside another Tier-1 detector's exact length
range, has a real, identified collision surface.

**Alternatives considered, at the time this entry was first written.**
- **Fix `precedence.py`**: rejected — the tie-break rule is already
  correctly, deterministically doing exactly what `docs/DECISIONS.md`
  (2026-07-21, "Span precedence: Tier 1 always wins...") specifies.
  Changing it to somehow prefer `PHONE` in this specific case would be
  an arbitrary, undocumented special case with no principled
  justification over any other same-tier collision.
- **Fix the dataset generator (Task 2, at the time already approved and
  closed)**: identified as a real design question, deliberately *not*
  decided unilaterally in this entry — flagged to the product owner in
  Task 7's own completion report instead. See the follow-up entry below
  for the outcome.
- **Fix only the test suite**: done regardless of the above — the test
  that discovered this asserted a blanket "recall must be 1.0 for every
  Tier-1 type," which was wrong once this collision surface was known to
  exist, independent of whether the generator itself was ever changed.

**Residual, stated plainly, at the time this entry was first written.**
`ARCHITECTURE.md`'s claim "Tier 1 outputs are the only ones this system
calls guaranteed... if the entity is present in a canonical,
unobfuscated form, it is detected with certainty" remains true *per
detector, per isolated span*. It does not guarantee *which* entity type
a span is attributed to when two different Tier-1 detectors' value
spaces coincidentally overlap in both shape and checksum validity at the
identical span — a narrow, low-probability (order of a few percent of
`PHONE` examples) residual. See the follow-up entry below: this residual
no longer applies to the committed Phase 5 dataset specifically, though
the underlying cascade behaviour it describes is unchanged and still
real.

**Why.** CLAUDE.md: "if a defect can hide, assume it is hiding, and go
write the test that would catch it" — this is that defect (in the
original test's assumption, not in the system), caught by exactly the
kind of real-data, real-arm test this task's own scope called for
(`tests/integration/test_scoring_real_arm.py`, not a synthetic fixture
that would never have exercised the actual generator's output
distribution).

---

## 2026-07-22 - Phase 5 Task 7 follow-up: `_generate_phone()` now rejects any candidate the real cascade precedence rule would reclassify

**Decision.** Supersedes the "why this is not being fixed... in the
dataset generator" position of the entry immediately above, on explicit
product-owner approval (the entry above deliberately did not decide this
unilaterally). `benchmarks/generate/entity_values.py::_generate_phone()`
now regenerates a candidate — consuming more of the same injected
`random.Random`'s stream, never reseeding it — whenever
`_phone_candidate_wins_precedence()` reports that the real cascade
precedence rule would resolve it to something other than `PHONE`. That
helper builds `[detector.detect(candidate) for detector in
get_tier1_detectors()]` and calls the real `precedence.resolve()`
directly — the same functions the live cascade calls — rather than
re-deriving "does any other detector also match this string" from a
hand-reasoned rule about lengths and registration order. The committed
dataset (`benchmarks/data/dataset.jsonl`) was regenerated with the fixed
generator; all 385 `PHONE` gold values were confirmed, by running this
same check against every one of them, to now resolve as `PHONE` with
zero collisions remaining.

**Why reuse `precedence.resolve()` rather than hand-code the specific
collision rule identified above.** The entry above's own "why `PHONE` is
the only type with this exposure" analysis is a hand-derived argument
about lengths and registration order — useful for understanding *why*
the bug happened, but exactly the kind of manual re-derivation that
produced the original blanket "recall must be 1.0" assumption this
task's test suite disproved. A validation function built the same
hand-reasoned way would only be as trustworthy as that reasoning, and
would silently stop protecting against a collision shape nobody thought
to enumerate by hand. Calling the actual `get_tier1_detectors()` +
`precedence.resolve()` pipeline means the check can never itself drift
out of sync with what the cascade actually does — it *is* what the
cascade does, run once at generation time instead of once at detection
time.

**Why this preserves determinism.** The retry loop only ever calls
`rng.choice()`/`rng.randint()` again on the *same* `random.Random`
instance passed into `_generate_phone()` — it never reseeds, never
touches global `random` state, and never depends on wall-clock time or
iteration order. The same seed therefore still always produces the same
final dataset, byte-for-byte — reverified directly (two independent
`build_dataset()` calls produced identical output; `write_jsonl()`
called twice produced identical files) after this change, the same
proof `benchmarks/generate/build_dataset.py`'s own tests already
required before this fix.

**Why the dataset's total example count and per-type entity counts are
unchanged.** The fix only changes *which* string `_generate_phone()`
returns for a given `random.Random` draw sequence, never how many times
it is called or which templates/slots invoke it — every template still
instantiates the same number of times, with the same entity-type slots.
Reverified directly: 2,860 examples, 4,235 entity occurrences, and the
identical per-type breakdown (`PHONE`: 385) before and after
regeneration.

**What this means for the entry above's residual.** The specific
residual described there — a `PHONE` gold value in *this benchmark's
dataset* occasionally resolving as `AADHAAR`/`CARD` — no longer applies:
every committed `PHONE` value is now guaranteed, by construction, to
resolve as `PHONE`. The *underlying cascade mechanism* the residual
described (two Tier-1 detectors validating an identical span, resolved
by registration order) is unchanged, still real, still correct, and now
has a direct regression test of its own
(`tests/integration/test_scoring_real_arm.py::test_cascade_precedence_still_resolves_a_deliberately_colliding_value_correctly`)
independent of what the dataset happens to contain.

**Alternatives considered.**
- **Leave the dataset as-is, document the collision as a permanent,
  disclosed residual** (the entry above's default position pending
  product-owner input): rejected on explicit instruction — "the
  benchmark should measure detector quality rather than accidental
  generator ambiguity."
- **Fix `precedence.py` instead of the generator**: rejected for the
  same reason the entry above rejected it — the precedence rule is
  correct, general-purpose production behaviour that many other things
  depend on (the live gateway's own request path, not just this
  benchmark); the ambiguity belongs to one generator's output
  distribution, not to the rule that resolves ambiguity when it exists.
- **A fixed retry cap with an exhaustion exception**, mirroring
  `NameListExhaustedError`'s pattern for the (genuinely finite) name-map
  candidate pools: rejected — phone-number generation draws from an
  effectively unbounded space (`10^10` core values), so unlike a finite
  candidate list, exhaustion is not a realistic failure mode to guard
  against; adding one would be validating a scenario that cannot
  practically occur (CLAUDE.md: don't add error handling for scenarios
  that can't happen).

**Why.** The product owner's own framing is the complete justification:
a benchmark whose `PHONE` recall number partly reflects "did the
generator happen to produce an ambiguous value" rather than "did the
detector find the phone number" is not measuring what BUILD.md's Phase 5
exists to measure. CLAUDE.md's "preserve the architecture unless a
genuine issue is discovered" instruction is exactly why this required
explicit approval before touching Task 2's already-closed output, rather
than being silently decided inside Task 7's own scope.

---

## 2026-07-22 - Phase 5 Task 8 closeout: the ~13 residual AADHAAR false
positives in arms 2 and 3 are Presidio's own overlap resolution, not a
bug anywhere

**Decision.** No code changes. A bounded investigation (per the product
owner's explicit request, after the full benchmark run showed AADHAAR
precision at .974 rather than 1.000 in arms 2, 3, and 4) identified the
exact cause: 13 examples where a `PHONE` value's `"+91"` prefix means
`AadhaarDetector`'s `\b\d{12}\b` pattern independently, correctly
matches the 12 digits *after* the `+` — and that 12-digit substring is,
by the same coincidental-checksum mechanism already documented in the
Phase 5 Task 7 entries above, independently Verhoeff-valid roughly 1 in
10 times. Confirmed directly for three of the 13:
`verhoeff_is_valid("918113076941")`,
`verhoeff_is_valid("918586220629")`, and
`verhoeff_is_valid("917605996149")` all return `True`.

**Why this is not the Task 7 collision recurring, and not something the
generator fix should have caught.** `_generate_phone()`'s guard
(`_phone_candidate_wins_precedence()`) checks whether *this project's
own* `precedence.resolve()` — the function `benchmarks/arms/ours.py`
and the live gateway both actually call — would attribute the span to
something other than `PHONE`. Re-run directly against all 13 offending
examples through `get_tier1_detectors()` + `precedence.resolve()` (the
exact mechanism the guard checks): **zero** false positives survive.
`PhoneDetector`'s own span (`"+91..."`, 13 characters, including the
`+`) is one character longer than `AadhaarDetector`'s overlapping
candidate span (12 digits, starting just after the `+`), so this
project's own tie-break (`(tier, -length, detector_index)`, longest
match first) correctly picks `PHONE` every time. The generator's fix is
working exactly as designed, for the one thing it was ever designed to
guarantee — this project's own cascade.

**The actual mechanism, confirmed by direct comparison.** Arms 2 and 3
register `DetectorBackedRecognizer(AadhaarDetector())` as one Presidio
`EntityRecognizer` and rely on Presidio's own stock `PhoneRecognizer`
for `PHONE` (Task 4's own scope decision: "CARD/EMAIL/PHONE/PERSON...
Presidio already ships recognizers for all four out of the box"). Each
recognizer's `analyze()` call is independent and returns its own
genuine, correct candidate spans directly — `DetectorBackedRecognizer`
never calls `precedence.resolve()` itself (it wraps exactly one
detector; there is nothing to resolve *within* one recognizer's own
output). Combining *across* recognizers is `AnalyzerEngine`'s own job,
and Presidio's internal conflict resolution is not the same function,
does not know about this project's "tier" concept, and — demonstrated
directly for `ex-02823`'s text (`"Siddharth Subramaniam ka Aadhaar
999926628123 aur phone +918113076941 dono form mein daal dijiye."`) —
does not eliminate the overlapping, lower-priority `AADHAAR` candidate
the way this project's own `precedence.resolve()` does:

```
Arm 2 (Presidio + custom) predictions:
  AADHAAR (33, 45) '999926628123'   <- correct
  AADHAAR (57, 69) '918113076941'   <- spurious; overlaps the PHONE span below
  PERSON  (0, 21)  'Siddharth Subramaniam'
  PHONE   (56, 69) '+918113076941'  <- correct

Arm 4 (ours) predictions:
  PERSON  (0, 21)  'Siddharth Subramaniam'
  AADHAAR (33, 45) '999926628123'   <- correct
  PHONE   (56, 69) '+918113076941'  <- correct, AADHAAR candidate eliminated
```

**Why this is not a bug in any single component.** `AadhaarDetector`
correctly found a genuinely Verhoeff-valid 12-digit run — that is
exactly its job, and it has no way to know a different entity's value
happens to contain it. Presidio's `PhoneRecognizer` correctly found the
phone number. `precedence.resolve()` correctly resolves the overlap
when it is actually given both candidates — proven directly above. The
only place these three correct pieces fail to compose correctly is
*inside Presidio's own engine*, which was never built to know about
this project's tier concept, and was never supposed to. This is a real,
structural, disclosed property of arms 2 and 3 specifically, not a
project bug to fix.

**Why this is not being "fixed."** The three options considered mirror
the Task 7 entries' own reasoning exactly:
- **Patch `DetectorBackedRecognizer` to run `precedence.resolve()`
  itself, across recognizers**: rejected — a single recognizer cannot
  see what *other* recognizers will independently find; the only way to
  apply this project's own precedence rule inside Presidio's engine
  would be to replace Presidio's own conflict resolution wholesale,
  which stops arms 2/3 from being a fair measurement of *Presidio
  configured with custom recognizers* and starts measuring "Presidio's
  detection primitives wearing this project's own precedence logic" —
  a different, uninteresting arm.
- **Regenerate the dataset to avoid `"+91"`-prefixed phone numbers
  whose trailing digits are coincidentally Verhoeff-valid**: rejected —
  this residual is not a property of the dataset in isolation (the
  Task 7 fix already proved these exact 13 examples score perfectly
  under this project's own cascade); it is a property of how *Presidio
  itself* combines independent recognizer results. Removing it from the
  dataset would hide a real, measurable difference between the arms
  behind a dataset choice, which is a worse kind of dishonesty than
  reporting a slightly-below-1.000 precision number with its cause
  documented.
- **Document it and leave the measured numbers as they are**
  (**chosen**): the .974 AADHAAR precision in arms 2 and 3 is a real,
  reproducible, now-fully-explained measurement of a genuine
  architectural difference between Presidio's own conflict resolution
  and this project's own precedence rule — exactly the kind of honest,
  attributable delta BUILD.md's ablation design exists to surface, not
  a defect to launder away.

**Likely connection to a second observed pattern, not separately
investigated.** The full benchmark run also showed arm 3 with lower
`PERSON`/`ORG` precision than arm 4 at identical recall. The mechanism
here is the same shape: arm 3's GLiNER-backed `PERSON`/`ORG`/`ADDRESS`
recognizers (`presidio_gliner/engine.py`, also built on
`DetectorBackedRecognizer`) are combined with arm 3's Tier-1 custom
recognizers by the same Presidio-internal conflict resolution, not this
project's own `precedence.resolve()`. Plausible, not confirmed — this
entry documents only what was actually investigated (the AADHAAR case,
per the bounded scope of this task), and does not extend the claim
further than what was directly verified.

**Why.** The product owner's own instruction is the complete
justification for stopping here rather than changing anything: "if the
cause is a dataset artifact or an expected checksum collision, document
it... if it reveals a genuine detector issue, stop and report before
making any code changes." This is neither a dataset artifact nor a
detector issue — every component involved behaved correctly in
isolation — so the disposition is the third, unnamed-but-implied case:
document a real, correctly-behaving-components-composing-imperfectly
finding, and change nothing.

---

## 2026-07-22 - Phase 6: adversarial suite runs against the live gateway, not `cascade.detect()` — and its success criterion requires proof of substitution, not mere disappearance

**Decision.** Unlike `benchmarks/arms/ours.py` (Phase 5's arm 4, which
calls `src/detect/cascade.py::detect()` directly), every case in
`adversarial/` sends a real HTTP request through the real `app` and
inspects what the mock upstream actually received, via a shared
`CapturingTransport` (see the separate entry below on promoting it out
of three duplicated test-local copies). A case is scored `caught` only
if all three hold, computed by `adversarial/cases/verify.py`'s three
verifier builders:

1. the captured upstream body is still valid JSON,
2. the original sensitive value is absent from it, and
3. something demonstrably *replaced* it — for the seven slot-based
   bypass classes, proven by requiring the text immediately
   surrounding the entity's known position to be byte-identical to
   what was sent, while the text between those two anchors changed to
   something that is not the value that was actually sent.

**Alternatives considered.**
- **"Needle disappeared" alone** (the suite's own first draft): reusing
  `benchmarks/arms/ours.py`'s in-process pattern and simply asserting
  the real value is absent from the captured body. Rejected on
  independent Staff Engineer review: disappearance alone cannot
  distinguish a real substitution from a truncation, a blanket
  redaction, or any other corruption that also happens to remove the
  literal substring — none of which is evidence that sanitization, specifically,
  occurred.
- **Hardcode the expected surrogate value or format and compare
  directly**: rejected — CLAUDE.md's own domain-type philosophy and
  ARCHITECTURE.md's frozen FF1/candidate-pool design mean the surrogate
  *scheme* could change; a check that assumes today's exact surrogate
  shape would silently stop meaning anything the day that scheme
  evolves, and would also require this suite to duplicate knowledge of
  the surrogate engine it has no business knowing.
- **In-process `cascade.detect()` calls, mirroring the benchmark's own
  arm 4** (chosen approach, rejected for this suite specifically):
  ARCHITECTURE.md's Adversarial Evaluation section states plainly that
  bypasses like split-across-turns and PII-as-a-JSON-key "only exist at
  the system level" — `field_walker.py`'s per-message, per-field
  traversal and the OpenAI wire format's full-history-per-request shape
  are properties of the *proxy*, not of any single call to `detect()`.
  An in-process call cannot exercise either mechanism at all.

**Why the chosen design (both parts) is correct.** The prefix/suffix
invariance check is a generic, surrogate-implementation-agnostic proof
of *targeted substitution* — it says nothing about what replaced the
value, only that the known carrier text on both sides is untouched and
the middle changed to something new. This is the same "do not hardcode
specific surrogate values" requirement the Staff Engineer review stated
explicitly. The two structural-isolation classes
(`split_across_turns`, `pii_in_json_key`) cannot use this check at all
— there is no single slot to anchor around, because the entity was
never assembled contiguously by construction — so their own
verifiers (`fragment_reconstruction()`, `key_presence()`) measure the
only honest signal available: whether the mechanism that should have
prevented reconstruction (or key-visibility) actually did.

**A real, contained bug this design caught before any case ran for
real.** An earlier draft of `verify.slot_replacement()` compared the
surviving middle text against `real_value` (the always-plaintext
canonical entity) rather than `sent_value` (the literal text actually
embedded — obfuscated, for most adversarial cases). Since
`sent_value != real_value` by construction for an obfuscated case, an
*untouched* obfuscated value would have read as "changed" purely
because it doesn't equal `real_value`, silently inverting the very
success criterion this entry describes. Caught by reasoning through the
first live-gateway run before trusting its output, not discovered by
accident; fixed in `verify.slot_replacement()` and `carrier.build_slot_case()`
before any case's result was recorded, with a regression test
(`tests/unit/test_adversarial_carrier.py::test_build_slot_case_verifier_uses_sent_value_not_real_value_for_replacement_check`).

---

## 2026-07-22 - Phase 6: bypass-class discovery via a `build_cases()` convention, not an import list

**Decision.** `adversarial/cases/discovery.py::discover_cases()` walks
`adversarial/cases/` at runtime (`pkgutil.iter_modules`) and calls
`build_cases()` on every module that defines it. Infrastructure modules
(`case_types`, `verify`, `carrier`, `discovery` itself) are skipped
because they simply have no `build_cases()` — there is no separate
allowlist/denylist of module names to maintain.

**Alternatives considered.**
- **A growing import list in the runner** (this suite's own first
  draft, and `benchmarks/runner/run.py::_ARM_FACTORIES`'s actual
  pattern for its four, fixed, hand-designed arms): rejected on
  independent Staff Engineer review specifically for this suite — nine
  bypass classes today, with BUILD.md's own framing ("8-10 bypass
  classes") anticipating more, is exactly the shape where a manually
  maintained list becomes the thing every new class's PR has to
  remember to touch. The benchmark's four arms are a fixed, permanent
  ablation design (BUILD.md names all four explicitly); this suite's
  bypass classes are the opposite — an intentionally open-ended,
  growing catalogue — so the two runners' own registration mechanisms
  are allowed to differ.
- **A decorator-based explicit registry** (`@register_bypass_class`):
  rejected — still requires every module to be *imported* somewhere for
  the decorator to run, which either reintroduces an import list in
  `adversarial/cases/__init__.py` or requires the same `pkgutil`-based
  walk anyway, at which point the decorator adds ceremony without
  removing the growing-list problem it was meant to solve.

**Why.** Mirrors `src/detect/registry.py`'s own justification, quoted
directly in `discovery.py`'s docstring: "adding an entity type is a new
detector registered in a registry, not an `if` branch in the pipeline."
Applied here: adding a bypass class is a new module with a
`build_cases()` function, not a new line anywhere else.

---

## 2026-07-22 - Phase 6: single-bypass scope; combined obfuscations are out of scope

**Decision.** Every case in this suite applies exactly one obfuscation
technique. Combinations (base64 + zero-width, split-across-turns +
homoglyph, or any other pairing of two classes in this suite) are not
measured, are stated as out of scope in the runner's own rendered
output (`adversarial/runner/run.py::_SCOPE_NOTE`, present in every
generated `latest.md`), and in this entry, so a future contributor
cannot mistake this suite's coverage for something broader than what
was actually measured.

**Alternatives considered.**
- **Also measure a handful of hand-picked combinations**: rejected for
  this phase — BUILD.md's own Phase 6 scope names nine specific,
  independent bypass classes, not a combinatorial matrix over them;
  attempting even a "representative sample" of combinations would be
  unbounded scope creep with no natural stopping point (2^9 possible
  subsets), and CLAUDE.md's Forbidden Actions list rules out adding
  unrequested scope mid-phase.
- **Say nothing and let the single-bypass table speak for itself**:
  rejected — ARCHITECTURE.md's own reasoning for the blind red-team
  step applies equally here: an unstated assumption a future reader
  could reasonably make ("this covers combined attacks too") is exactly
  the kind of gap this project's own honesty standard exists to close
  before a reviewer finds it.

**Why.** Single-bypass measurement is the honest, in-scope claim; a
combined-attack suite is real future work with its own design
questions (which pairings are representative? does a combination need
its own verifier shape?) that this phase does not have room to answer
without compressing the nine classes BUILD.md actually asked for.

---

## 2026-07-22 - Phase 6: `CapturingTransport` promoted out of three duplicated test-local copies

**Decision.** `tests/integration/test_sanitize_integration.py`,
`test_phase_3_gate.py`, and `test_phase_4_gate.py` each defined their
own private `_CapturingTransport` class and
`_override_with_capturing_mock_upstream()` helper before this phase —
`test_phase_3_gate.py`'s own comment on the class read "duplicated
locally rather than imported: it is test plumbing... each integration
test module already keeps its own copy." Promoted now to
`adversarial/runner/gateway_client.py` (public `CapturingTransport`,
`override_with_capturing_mock_upstream()`, and a context-manager form
`capturing_mock_upstream()` for non-pytest callers), and all three
existing test modules now import it from there instead.

**Why now, reversing an explicit prior decision.** CLAUDE.md's own
refactor policy: "duplication has actually appeared (twice is a
coincidence; three times is a refactor)." Three copies already existed
before this phase touched anything. More importantly, this phase's own
runner (`adversarial/runner/run.py`, invoked standalone via
`python -m adversarial.runner.run`, never through pytest) needs the
identical mechanism as its *core execution strategy* — ARCHITECTURE.md
requires every case to run "against the live gateway" and inspect "what
the upstream actually received," which is exactly what
`CapturingTransport` gives a caller. A fourth private copy inside
`adversarial/` would have been the same duplication the prior decision
already flagged as acceptable at three, now grown to four for no
reason other than habit.

**Why it lives under `adversarial/runner/`, not `tests/support/`.** The
runner is not a test — it is production-quality evaluation code
(CLAUDE.md: "benchmark and adversarial runners are code, and they get
tested too") invoked directly by `tasks.ps1 adversarial`. Placing the
shared module under `tests/` would invert this codebase's own layering
convention (tests import production code; production code is never
imported from `tests/`). Tests continue to import it from
`adversarial.runner.gateway_client`, the same way they already import
from `benchmarks.arms.arm` and other sibling top-level packages.

**Verified non-regressive.** All three refactored test modules were
re-run immediately after the change (`test_sanitize_integration.py`,
`test_phase_3_gate.py` in the fast suite; `test_phase_4_gate.py` under
`-m real_model`) and passed unchanged, before any new Phase 6 code was
written on top of the shared module.

---

## 2026-07-22 - Phase 6: discovered — Tier-2 can misclassify a message's literal `role` value as `PERSON`, corrupting the OpenAI role enum; documented, not fixed this phase

**What was found.** Running many varied real-`GLiNER` requests through
the live gateway for the first time with the *entire* captured upstream
body scrutinized (not just `message.content`, which is all any earlier
real-model test asserted on) surfaced a real, reproducible defect in
already-shipped Phase 4 code: `get_tier2_model().find_entities("user")`
returns a `PERSON` match spanning the whole 4-character string, with no
surrounding context. `src/pipeline/field_walker.py::_walk()` treats
every string-valued field generically, including a message's `"role"`
field — nothing special-cases it — so `sanitize()` can replace a
message's literal `"role": "user"` with a fabricated person-name
surrogate (observed directly, e.g. `{"role": "Krishna Chowdhury",
"content": "..."}` forwarded to the mock upstream). This corrupts a
value the OpenAI wire format requires to be one of a fixed enum
(`system`/`user`/`assistant`/`tool`), independent of anything this
project's own adversarial or benchmark work is trying to measure.

**Why this is not a Phase 6 finding, and not fixed here.** This is a
real correctness defect in the ordinary, non-adversarial request path
— any request through this gateway with Tier-2 enabled has a nonzero
chance of a corrupted `role` field, entirely independent of whether the
request contains a deliberate bypass attempt. It is out of Phase 6's
scope (the adversarial suite) to fix a Phase 4 pipeline bug, and
CLAUDE.md's Forbidden Actions list rules out unrequested architecture
or pipeline changes mid-phase. Surfaced to the product owner directly
before continuing Phase 6 work (per this project's own decision-making
protocol: "root-cause every unexpected result before changing code");
the product owner's explicit choice was to document and continue,
deferring a fix to its own future task.

**Why it does not invalidate any Phase 6 measurement.** Every verifier
in `adversarial/cases/verify.py` checks specific, known field paths
(`content`, an `arguments` sub-key) directly via `_get_at_path()` —
never a fuzzy whole-body substring search for an unrelated field's
corruption to interfere with. The corrupted `role` field was observed
in the same captured bodies this suite's own cases used, and confirmed
by direct inspection not to change any case's `caught` verdict.

**Residual, for `docs/LIMITATIONS.md`.** See that file's own new entry
for the user-facing statement of this gap.

---

## 2026-07-22 - Phase 6: a genuine, measured contradiction in `transliterated_names` — GLiNER recognises Devanagari-script names in this suite's own test pairs, against this module's own a priori prediction

**What was measured.** `adversarial/cases/transliterated_names.py`
predicted `expected_outcome="leaked"` for both Devanagari name pairs,
reasoning from `docs/LIMITATIONS.md`'s already-disclosed GLiNER
weakness on *romanized* Hinglish carrier sentences. The actual measured
result (`adversarial/results/latest.md`, "Prediction mismatches"): both
pairs were in fact caught — `urchade/gliner_multi_pii-v1`'s
multilingual training recognises native Devanagari script well enough,
at least for these two examples, to contradict the prediction.

**Disposition: left as a reported mismatch, not corrected.**
`expected_outcome` was not changed to `"caught"` after seeing this
result. The entire point of recording a prediction before measuring is
that the runner's own "Prediction mismatches" section
(`adversarial/runner/run.py::render_markdown()`) stays honest about
what was predicted versus what was found — retroactively editing the
prediction to match the outcome would be indistinguishable from "tuning
until the result looks good," which CLAUDE.md rules out even implicitly
("Never... change the span-matching criterion after seeing results" —
the same principle applied here to a bypass-class prediction instead of
a scoring criterion).

**A separate, unrelated bug this same investigation caught and fixed.**
The first real-model run also showed the module's own *clean* cases
mismatching (`expected_outcome="caught"`, measured `caught=False`) for
a reason that turned out to be unrelated to transliteration at all: the
original carrier suffix ("... regarding their account.") gave GLiNER a
separate, ordinary word ("account") it sometimes misread as an `ORG`,
which broke this case's own prefix/suffix invariance check
(`verify.slot_replacement()`) for a reason having nothing to do with
the name being tested. Root-caused by direct inspection of the captured
body, confirmed against the real model with an alternative suffix
before committing to it, and fixed by choosing carrier text verified
not to trigger a false positive — a test-design fix, not a change to
what is being measured or predicted.

---

## 2026-07-22 - Phase 6 release-readiness pass: deterministic discovery order, and removing the one real source of non-reproducibility in the committed artifact

**What an independent release-readiness review required.** Two checks
before tagging: that `discover_cases()` executes in a deterministic
order (so `adversarial/results/latest.json`/`latest.md` are
reproducible across operating systems and CI runs), and that
re-running the committed runner actually reproduces those two files.

**Finding 1 — module iteration order was never guaranteed.**
`pkgutil.iter_modules()` reflects whatever order the underlying
filesystem finder enumerates directory entries in, which is not
guaranteed identical across operating systems (observed, not assumed:
Windows and Linux directory listings are not required to agree) or
across Python versions. Fixed in `discovery.py::discover_cases()` with
two independent guards, not one: modules are imported in
sorted-by-name order, and — the guard that actually matters for the
artifact's own byte-reproducibility, since `json.dumps(...,
sort_keys=True)` sorts dict keys but never reorders a JSON list — the
final case list is sorted by `case_id` before being returned,
regardless of which module or what order produced it.

**Finding 2 (more significant) — the report was never actually
reproducible, for a reason unrelated to discovery order at all.** Two
back-to-back runs of `python -m adversarial.runner.run` were diffed
directly (not assumed identical) and found to differ: every
`transliterated_names` case's `detail` field reported a different
`substituted span length=N`. Root cause: `src/session/rng.py::get_rng()`
deliberately returns a fresh, **unseeded** `random.Random()` per
request (a Phase 4 decision, documented in that module's own docstring,
made for a real reason — a single shared RNG object across concurrent
sessions would be a genuine thread-safety bug). `PERSON` surrogates are
drawn from a candidate pool using this RNG
(`Session.allocate_or_lookup_name()`), so which candidate name gets
chosen — and therefore its length — genuinely varies run to run. This
is the only place in the entire suite where a case's outcome touches
anything non-deterministic: every Tier-1 (FF1) surrogate is
format-preserving and same-length by construction, so only the one
Tier-2/PERSON bypass class was ever affected.

**Alternatives considered.**
- **Override `get_rng()` in the runner with a seeded instance**:
  rejected — `get_rng()`'s own unseeded-per-request design is a frozen,
  already-decided Phase 4 concurrency property (CLAUDE.md: "never
  change architecture for optimisation" applies equally to changing it
  for a Phase 6 convenience); overriding it would mean this suite's
  "live gateway" runs are no longer actually exercising the same
  dependency-injection path the real gateway uses, undermining
  ARCHITECTURE.md's own reason for requiring live-gateway execution in
  the first place.
- **Accept the non-reproducibility as a known, disclosed limitation**:
  rejected — the variation was in a field this suite's own code writes
  (`detail`), not a property of the gateway being measured; the
  gateway's own actual behaviour (name-map allocation) is exactly as
  non-deterministic as Phase 4 already decided it should be, but
  nothing about *that* required this suite's own diagnostic text to
  encode a length that inherits the variation.
- **Stop embedding the substituted span's length in `detail` at all**
  (chosen): `verify.slot_replacement()`'s success-path message changed
  from `f"substituted span length={len(middle)}"` to a fixed string
  ("prefix/suffix invariant held; sent value replaced" /
  "... unchanged") — evidence of *whether* a targeted substitution
  occurred, with no dependency on what the substitute happens to look
  like. This is consistent with the criterion's own design intent
  (`docs/DECISIONS.md`, the "needle disappeared" entry above): the
  proof is structural (prefix/suffix invariance), never a property of
  the surrogate's own shape.

**Verified, not assumed.** `python -m adversarial.runner.run` was run
three consecutive times after the fix; `latest.json` and `latest.md`
were byte-identical across all three (`diff` exit 0). Fast and
`real_model` suites re-run in full afterward with no regressions.

---

## 2026-07-23 - Phase 7: protocol-aware field walking — closes the deferred `messages[].role` misclassification, via a value-checked protocol-enum registry, not a key-name exclusion

**What this closes.** The defect deferred on 2026-07-22 (this file, and
`docs/LIMITATIONS.md`): Tier-2 misclassifying a message's literal
`role` value (e.g. `"user"`) as `PERSON`, which `sanitize()` then
substituted with a fabricated name surrogate, corrupting a value the
OpenAI wire format requires to be one of a fixed enum.

**The issue, precisely.** `field_walker.walk()` finds every
text-bearing field in a request body generically, with no notion of
which fields are natural-language content versus wire-protocol
metadata. `sanitize()` fed every region unconditionally to `detect()`,
so a Tier-2 false positive on a short, context-free token like `"user"`
had no way to be distinguished from a genuine detection in ordinary
content.

**Alternatives considered.**
- **Key-name exclusion** (`if key == "role": skip`), inline in
  `field_walker.py` or `sanitize.py`: rejected. This is unsound, not
  merely inelegant — it would skip detection under that key
  unconditionally, regardless of content, which opens exactly the leak
  channel this proxy exists to close: a malformed client, or an
  attacker deliberately placing real PII in a field expected to be
  skipped, would have it forwarded to the upstream provider completely
  unscanned. It also doesn't generalize safely: `"type"` appears at
  several positions in this schema with different meanings (`tools[].type`,
  and — recursively, at arbitrary depth — a JSON-Schema `"type"`
  keyword inside `tools[].function.parameters`, which can collide with
  a user-defined property literally named `type`), and a name-only rule
  can't distinguish these without scattering more special-casing through
  the traversal or detection code (CLAUDE.md: "No duplicated logic").
- **A typed request model** (Pydantic/dataclass) with `role: Literal[...]`,
  replacing the raw-dict body: rejected as out of scope for this defect.
  The gateway's request path is deliberately schema-agnostic
  (`field_walker.py`'s own docstring: "the field you forget is the
  leak" — a field this project's authors didn't anticipate is still
  found, not silently skipped); introducing a typed schema is a larger
  architectural change than a value-checked exemption requires, and
  wasn't asked for.
- **A value-checked protocol-enum registry** (chosen): a new module,
  `src/pipeline/protocol_fields.py`, declares — as one small, citation-bearing
  data table — the wire-protocol positions whose values are drawn from
  a finite, spec-defined vocabulary, together with that vocabulary.
  `is_protocol_enum_value(path, text)` is a two-part test: the region's
  path must match a declared position, *and* its value must actually be
  one of that field's legal members. A path match with a non-member
  value returns `False` and falls through to ordinary detection — the
  value check, not the path check alone, is what keeps this from
  becoming a new leak channel. `sanitize()` is the only caller, in the
  existing `walk()` loop, before `detect()` is invoked; `field_walker.py`
  itself is unchanged, so `walk()`/`rebuild()` still reach and
  round-trip every field, `role` included.

**Scope of the initial table: `messages[].role` only.** The design
supports adding further protocol-enum positions later (e.g.
`tool_calls[].type`, `tools[].type` — both are also closed
single-value enums at fixed, non-recursive paths, the same failure
class as `role`), but none were added in this phase. Per explicit
product-owner instruction: extending the table requires a demonstrated
failing test or a real observed bug, the same bar `role` itself met —
not speculative coverage of every closed-enum-shaped field this schema
could ever contain.

**Explicit non-goal.** The recursive JSON-Schema `"type"` keyword
inside `tools[].function.parameters` is not handled and is not
planned to be via this mechanism: its path is not fixed-depth or
unambiguous (arbitrary nesting, and collides with a user-defined
property that could itself be named `type`). It remains ordinary
scanned text, exactly as it is today.

**Verified.** `tests/unit/test_protocol_fields.py` proves the predicate
in isolation (position match, value match, and — the fail-safe case —
a non-enum value at the `role` position still returns `False`).
`tests/unit/test_sanitize.py` and
`tests/regression/test_role_field_pii_misclassification.py` reproduce
the original defect with a stub `Tier2Model` that deterministically
misfires on `"user"`/`"assistant"` (no real GLiNER weights required)
and prove both halves of the invariant end-to-end: a legal role value
survives the misfire unchanged, and a non-conforming value at the role
position is still fully detected and substituted. Full fast suite
(`pytest`), `ruff`, and `mypy --strict src` all pass with no
regressions.

---

## 2026-07-23 - Phase 7 Task 2: configuration hardening — two Settings-level validators close two "passes startup, crashes at first request" gaps; no cross-field invariants found to enforce

**What this closes.** A full audit of every field on `Settings`
(`src/core/config.py`) against how each is actually consumed, cross-
checked against `ARCHITECTURE.md`'s own claim ("Every variable is
validated before the server binds... a configuration error must never
be discovered at first request") — which turned out to be false for
two fields:

1. **`SESSION_TTL` overflow.** `session_ttl: int = Field(gt=0)` accepted
   any positive int, including one too large for `datetime.timedelta`
   to represent. `get_session_store()` (`src/session/store.py`)
   unconditionally builds `timedelta(seconds=settings.session_ttl)` —
   an absurdly large value passed `Settings()` construction cleanly and
   only raised a bare, uncaught `OverflowError` on the first request.
2. **`UPSTREAM_BASE_URL` shape.** `Field(min_length=1)` only checked
   non-emptiness. Neither `Settings()` nor `httpx.AsyncClient(base_url=...)`
   (`build_upstream_client()`, `src/proxy/upstream_client.py`) validate
   URL shape at construction — a malformed value passed both silently,
   surfacing only as a generic connection failure deep inside a real
   request.

**Fix.** Two `@field_validator`s added directly to `Settings`:
`_session_ttl_must_fit_a_timedelta` (attempts `timedelta(seconds=value)`,
converts an `OverflowError` into a clean, actionable `ValueError`) and
`_upstream_base_url_must_be_an_absolute_http_url` (`urllib.parse.urlsplit`,
requires `scheme in {"http","https"}` and a non-empty host). Both live
in the one file that already owns every other constraint on these nine
fields — no new validation module, no change to `get_session_store()`,
`build_upstream_client()`, or any route. The `upstream_base_url` check
is shape-only, deliberately: validating reachability would mean dialing
the URL at startup, which requires the upstream to already be running —
an assumption this project doesn't make (the mock upstream is a
separate process, started independently).

**Cross-field invariants — explicitly evaluated, none found to enforce.**
Before implementing, every pair of the nine `Settings` fields was
checked against actual consumer code for a real "mutually exclusive,"
"one requires another," or "mode implies required/forbidden config"
relationship:

- `upstream_mode` × `upstream_base_url` (and the documented-but-
  nonexistent `UPSTREAM_API_KEY`) is the only pairing shaped like a
  genuine cross-field invariant — `live` mode *should*, in principle,
  require a credential `mock` mode forbids. But `UPSTREAM_API_KEY` does
  not exist anywhere in code (only in `ARCHITECTURE.md`'s now-corrected
  Configuration Architecture table), and `upstream_mode` itself is read
  nowhere in application code — confirmed by grep, and stated directly
  in `upstream_client.py`'s own docstring ("`base_url` is
  `settings.upstream_base_url` regardless of whether `UPSTREAM_MODE` is
  mock or live"). Explicitly decided (product owner, this task):
  `upstream_mode` stays informational-only; fix the documentation to
  stop overclaiming, do not add live-provider authentication as a
  side effect of a hardening task. Adding a `model_validator` coupling
  these two fields today would have nothing real behind it — both
  modes already require exactly the same thing (a shape-valid URL).
- `fail_mode` × anything: no coupling exists anywhere — scoped to
  Tier-2 detector failures only (confirmed by grep; upstream errors and
  stream drops use a separate, fixed code path per this file's own
  2026-07-21 entries on FAIL_MODE's scope).
- `ner_warmup` × `ner_model`: a real behavioral coupling (disabling
  warmup defers `ner_model`'s validity check to first use), but not a
  contradiction to reject — there is no cheaper way to validate a
  HuggingFace model id is loadable than loading it, which is exactly
  the cost `NER_WARMUP=false` exists to defer. Documented as an
  accepted trade-off, not fixed.
- Every remaining pairing (`session_ttl`×`upstream_timeout`,
  `fpe_key`×`session_ttl`, `log_level`×anything, `upstream_base_url`×
  `upstream_timeout`) governs an independent subsystem with no shared
  code path — no plausible operator error looks like "these two
  disagree."

**Why no `@model_validator` was added.** CLAUDE.md: "Don't apply SOLID
ceremonially" and "don't design for hypothetical future requirements"
apply here in spirit — a cross-field validator with no real invariant
behind it is validation theater, not hardening. All fixes in this task
stay at the single-field level.

**Verified.** New `tests/unit/test_config.py` (did not exist before this
task) covers every required-field-missing case, every existing
constraint (`gt=0`, `min_length`, `Literal` membership including case
sensitivity, `extra="forbid"`), `get_settings()` singleton caching,
`fpe_key`'s repr-safety, and both new validators (rejection cases, a
just-under-the-boundary acceptance case, and valid-URL acceptance,
parametrized). Two named regression tests
(`tests/regression/test_session_ttl_overflow_fails_at_startup.py`,
`tests/regression/test_upstream_base_url_shape_fails_at_startup.py`)
reproduce each original symptom directly. All `Settings()` construction
in the new test file passes pydantic-settings' own `_env_file=None`
override, discovered to be necessary mid-task: this developer's local,
untracked `.env` file (present, `.gitignore`d) would otherwise leak
into test outcomes for any defaulted field the test doesn't explicitly
override — a real test-isolation hazard, not hypothetical, fixed before
it could cause a flaky suite. Full fast suite, `ruff`, and
`mypy --strict src` all pass with no regressions.
