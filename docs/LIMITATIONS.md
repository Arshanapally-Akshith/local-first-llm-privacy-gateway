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

**Phase 2. Resolved in Phase 3.**

`UpiDetector` and `EmailDetector` are registered and active — a UPI ID
or email address in a request **is detected**. No surrogate domain is
registered for either type yet (`src/surrogate/registry.py`): FF1
doesn't fit an unbounded-length domain (NPCI allows a 2–256 character
VPA local part; email has no length bound at all), and the
session-scoped map that would handle them correctly doesn't exist
until Phase 3. See `docs/DECISIONS.md`, 2026-07-20, "FF1 domain
resolution."

Detecting one today raises `SurrogateDomainError`, which the gateway
turns into a `500` **before any upstream call is made**
(`app/main.py`'s exception handler; `src/pipeline/sanitize.py` never
calls `field_walker.rebuild()` until every region has succeeded). This
is a hard-fail, not a silent leak — the request is refused rather than
partially sanitized — but it does mean **a request containing a UPI ID
or email address cannot be sanitized and forwarded at all in Phase 2.**

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

---

## No unstructured-entity detection yet (names, organizations, addresses)

**Phase 2. Tier 2 is Phase 4.**

Only the 8 structured Tier-1 entity types are detected. A person's
name, an organization, or a street address in free text is not
detected or sanitized at all — Tier 2 (GLiNER-class NER) doesn't exist
until Phase 4. Any PII that isn't Aadhaar, PAN, IFSC, UPI, Vehicle
Registration, Card, Email, or Phone currently passes through the
gateway completely unsanitized.

---

## No response-path sanitization (rehydration) yet

**Phase 2. Phase 3.**

Everything in this phase operates on the request path only, per
BUILD.md's explicit Phase 2 scope ("REQUEST PATH ONLY"). The response
stream from the upstream passes through the sliding window unmodified
— there is no detection or rehydration on the way back. This is not a
live risk today (the mock upstream only ever receives sanitized
surrogates, by construction), but nothing in this phase would catch a
real value if a live upstream ever echoed one. Phase 3 builds the
session map and rehydration engine that closes this loop for
Tier-2-class entities; Tier-1 structured entities rehydrate by FF1
decryption, which Phase 3 also wires in.

---

## Ingress-surrogate re-encryption is not yet prevented

**Phase 2. Must be closed in Phase 3.**

Tier-1 detection re-runs from scratch on every request, with no
awareness of session state. If a structured surrogate FF1 produced on
an earlier turn were ever echoed back inside a later turn's request
body (e.g. the assistant's own prior message, replayed by a
multi-turn client), today's pipeline would detect it as a "new" real
entity and re-encrypt it — a surrogate-of-a-surrogate. This is
invisible in every test in this phase, since nothing in Phase 2
exercises multi-turn conversations — exactly the class of silent,
only-visible-in-long-conversations bug BUILD.md warns about. Phase 3's
explicit multi-turn DoD item ("5-turn conversation, no
double-encryption, no corruption") is what proves this is fixed; it is
not fixed today.
