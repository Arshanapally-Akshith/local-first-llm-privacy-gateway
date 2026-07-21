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
