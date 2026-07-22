# Phase 6 Summary — Adversarial Suite (Second Differentiator)

BUILD.md's Phase 6: "the bypasses that still work stay in the results
file... this is the single strongest artifact in the repo." Approved
with four mandatory architectural refinements from an independent Staff
Engineer review (recorded below and in `docs/DECISIONS.md`) before
implementation began: a three-part success criterion instead of
"needle disappeared," a `build_cases()`-discovery mechanism instead of
a growing import list, explicit per-class coverage documentation, and
an explicit single-bypass scope statement.

## What was built

| File(s) | Purpose |
|---|---|
| `adversarial/runner/gateway_client.py` | `CapturingTransport` + helpers, promoted out of three duplicated test-local copies (`test_sanitize_integration.py`, `test_phase_3_gate.py`, `test_phase_4_gate.py`, all repointed to import from here) |
| `adversarial/cases/case_types.py` | `AdversarialCase`, `VerificationOutcome` (the three-part `caught` criterion), `CaseLabel`, `ExpectedOutcome` |
| `adversarial/cases/verify.py` | `slot_replacement()`, `fragment_reconstruction()`, `key_presence()` — three verifier builders, none of which hardcode a surrogate value or format |
| `adversarial/cases/carrier.py` | `build_slot_case()` — shared request-body builder used by 7 of the 9 bypass classes |
| `adversarial/cases/discovery.py` | `discover_cases()` — `pkgutil`-based auto-discovery; adding a bypass class requires only a new module |
| `adversarial/cases/{spaced_digits,number_words,transliterated_names,split_across_turns,base64_encoding,pii_in_code,pii_in_json_key,homoglyphs,zero_width}.py` | The nine bypass classes, each with an explicit Coverage section (entity types exercised, entity types intentionally omitted, and why) |
| `adversarial/runner/run.py` | `run_case()`, `build_report()`, `render_markdown()`, `main()` — executes every discovered case against the real, running gateway |
| `adversarial/results/{latest.json,latest.md}` | The committed, commit-stamped artifact |
| `adversarial/redteam/INSTRUCTIONS.md`, `adversarial/results/redteam.md` | Blind red-team harness instructions and recording template — **not run**; see "What you must do manually" |
| `tasks.ps1` | New `adversarial` task |
| `.github/workflows/ci.yml` | `mypy --strict adversarial` added |
| Tests | 60 fast (`tests/unit/test_adversarial_*.py`, `tests/integration/test_adversarial_gate.py`) + 5 `real_model` (`tests/integration/test_adversarial_runner_real_run.py`) |

## Key design decisions and why

**Executes against the live gateway, not `cascade.detect()`.** Unlike
Phase 5's benchmark arms, every case sends a real HTTP request through
the real `app` and inspects what the mock upstream actually received.
ARCHITECTURE.md is explicit that bypasses like split-across-turns and
PII-as-a-JSON-key "only exist at the system level" — an in-process
detector call cannot exercise either mechanism. See
`docs/DECISIONS.md`, 2026-07-22.

**The three-part success criterion.** A case is `caught` only if the
captured body is still valid JSON, the original value is absent, *and*
something demonstrably replaced it (proven via prefix/suffix
invariance around the entity's known position, or — for the two
structural-isolation classes — whether the mechanism that should have
prevented reconstruction actually did). Never compares against a
hardcoded surrogate value or format. A real bug in an early draft
(comparing against `real_value` instead of `sent_value`, which would
have misread an untouched obfuscated value as "replaced") was caught
and fixed before any case result was recorded — `docs/DECISIONS.md`.

**Auto-discovery, not a growing import list.** `discover_cases()` finds
every module exposing `build_cases()`; there is no allowlist to keep in
sync and no runner edit required to add a class.

**Every bypass mechanism verified empirically before being coded**, not
assumed from regex inspection alone — including two non-obvious,
codebase-specific findings: `\b` is Unicode-aware, so a homoglyph
merges two would-be tokens into one unmatched compound (a *clean* miss)
for `\b`-anchored detectors (PAN, IFSC), but the *same* substitution
against `EmailDetector`'s lookaround-anchored pattern produces a
*partial, wrong-span* match instead — a different, more concerning
failure mode this suite's binary model can't characterize, so EMAIL is
disclosed as omitted from `homoglyphs.py` rather than silently included
with a misleading result. And: `_` counts as a word character for
`\b`, so a value glued to a `snake_case` identifier defeats AADHAAR/PAN
detection but *not* PHONE/EMAIL/UPI, which anchor on an explicit
alphanumeric-only lookaround instead.

**Single-bypass scope, stated in three places** (the runner's own
rendered output, `docs/LIMITATIONS.md`, `docs/DECISIONS.md`) so a
future contributor cannot assume combined obfuscations (base64 +
zero-width, split-across-turns + homoglyph, ...) were measured. They
were not.

**Blind red-team: harness and template only, not run.** BUILD.md
requires a real person, with no stake and no prior exposure to the
internals, spending about an hour attacking the running gateway. This
cannot be simulated or fabricated — `adversarial/redteam/INSTRUCTIONS.md`
and `adversarial/results/redteam.md` (marked "NOT YET RUN") exist so the
session can happen, but did not happen as part of this implementation
pass.

## Release-readiness pass: determinism and reproducibility

An independent release-readiness review required two things verified,
not assumed, before tagging:

**Deterministic discovery order.** `pkgutil.iter_modules()` does not
guarantee iteration order — it reflects the filesystem finder's own
directory-listing order, which is not required to agree across
operating systems. `discovery.py::discover_cases()` now imports modules
in sorted-by-name order and, more importantly, returns the final case
list sorted by `case_id` regardless of discovery order — the guard that
actually matters for `latest.json`'s `"cases"` array, since
`json.dumps(..., sort_keys=True)` sorts dict keys but never reorders a
JSON list.

**A real, non-cosmetic non-reproducibility this check caught.** Two
consecutive runs of `python -m adversarial.runner.run` were diffed
directly and found to differ — every `transliterated_names` case's
`detail` field reported a different `substituted span length=N`. Root
cause: `src/session/rng.py::get_rng()` deliberately returns a fresh,
unseeded RNG per request (a frozen Phase 4 concurrency decision, not
touched), so which `PERSON` candidate name gets chosen — and its length
— genuinely varies run to run. Fixed at the source of the variation,
not by touching the RNG: `verify.slot_replacement()`'s success message
no longer embeds the substituted text's length, only whether a targeted
substitution occurred. **Verified, not assumed**: three consecutive
runs after the fix produced byte-identical `latest.json`/`latest.md`
(`diff` exit 0 each time). Full root cause and alternatives considered
in `docs/DECISIONS.md`, 2026-07-22, "release-readiness pass."

## A real defect this phase discovered, reported, and did not fix

Running many varied real-`GLiNER` requests through the live gateway for
the first time with the *entire* captured body scrutinized (not just
`message.content`) surfaced a genuine, reproducible bug in already-shipped
Phase 4 code: `get_tier2_model().find_entities("user")` returns a
`PERSON` match for the bare 4-character string, and `field_walker.py`
walks a message's `"role"` field like any other text — so `sanitize()`
can replace `"role": "user"` with a fabricated person-name surrogate,
corrupting the OpenAI wire format's required role enum. This is a real
defect in the ordinary, non-adversarial request path, unrelated to any
deliberate bypass. Reported to the product owner before continuing
(per this project's own "root-cause every unexpected result before
changing code" standard); explicit decision was **document, fix
later** — `docs/DECISIONS.md` and `docs/LIMITATIONS.md` both carry the
full entry. Confirmed not to affect any Phase 6 measurement: every
verifier checks specific, known field paths directly, never a fuzzy
whole-body search this corruption could interfere with.

A second, honest finding, not a bug: `transliterated_names.py`
predicted GLiNER would not recognise Devanagari-script names (based on
the already-documented Hinglish-romanization weakness); the actual
measured result was that it did, for both tested pairs. Left as a
reported "prediction mismatch" rather than retroactively corrected —
`docs/DECISIONS.md`.

## Measured result

Full table, "bypasses that still work," and prediction mismatches in
`adversarial/results/latest.md` (regenerate with `.\tasks.ps1
adversarial`). Headline: 8 of 9 classes measured 100% clean recall /
0% adversarial recall on every entity type tested — every predicted
bypass genuinely works, none were fixed to make the number look better.
The ninth class (`transliterated_names`) measured 100%/100%, a real
finding disclosed as a prediction mismatch rather than hidden.

## Manual verification gate

```powershell
# Fast suite (no real model load)
.\tasks.ps1 check

# Real-model suite (adversarial's transliterated_names class + everything else)
.\venv\Scripts\python.exe -m pytest -m real_model -v

# The adversarial suite itself (real Tier-2 inference for one class; a few minutes)
.\tasks.ps1 adversarial
```

**Expected:** `ruff` and `mypy --strict src/app/benchmarks/adversarial`
all clean; `mypy tests` clean; the fast suite passes in full (660
tests); the `real_model` suite passes in full (41 tests, including the
5-test, ~7-minute adversarial runner integration test); `.\tasks.ps1
adversarial` regenerates `adversarial/results/latest.json` and
`latest.md` — verified byte-identical across three consecutive runs.

## Definition of Done

- [x] Each bypass class is a runnable case with an expected-outcome
      record — `AdversarialCase.expected_outcome`, one `build_cases()`
      per module
- [x] `make adversarial` produces clean vs adversarial recall, per
      class, never averaged — `.\tasks.ps1 adversarial` →
      `adversarial/results/latest.md`. Regeneration verified
      byte-identical across three consecutive runs (see
      "Release-readiness pass" above) — no manually edited generated
      file exists
- [x] Unfixed bypasses listed in the results file — "Bypasses that
      still work" section, 19 entries in the current measured run.
      **And the README** — deferred to Phase 8 per the approved plan
      (no `README.md` exists yet; BUILD.md's Phase 8 owns assembling
      it, and this artifact is what it will read from — see "What you
      must do manually")
- [x] Blind red-team results recorded separately with the tester's
      methodology — template and harness built; **session not run**,
      see below
- [ ] Residual-leak statement in the README, above the fold — deferred
      to Phase 8 with the rest of the README (see above); the
      statement itself is fully supported by this phase's committed
      artifact
- [x] Summary + state updated — this document; `PROJECT_STATE.md`
      remains intentionally absent, per the Phase 0 decision reaffirmed
      at every phase closeout since (see `docs/PHASE_5_SUMMARY.md`)

**Gate:** BUILD.md's own phrasing — "I read the README and can
immediately name three ways to beat this system" — cannot be verified
literally until Phase 8 builds the README; the underlying claim is
already true of the committed artifact: `adversarial/results/latest.md`
names 19 specific, still-working bypasses by case id and entity type.

## Known limitations / deliberately deferred

- **The blind red-team session itself has not been run.** The harness
  and recording template exist; running it is a manual step, listed
  below.
- **The `role`-field Tier-2 misclassification bug** is disclosed,
  root-caused, and deliberately not fixed this phase (product owner's
  explicit choice — `docs/DECISIONS.md`).
- **Combined obfuscations are out of scope** — every case applies
  exactly one bypass technique; nothing about multi-technique
  combinations has been measured (`docs/DECISIONS.md`,
  `docs/LIMITATIONS.md`).
- Coverage within each class is deliberately partial, not exhaustive
  over all 11 entity types — each module's own docstring states which
  types are covered, which are omitted, and why, per the Staff Engineer
  review's required change.
- Everything already carried over from Phases 2-5 that Phase 6 didn't
  touch: the Aadhaar reserved-range residual, rehydration's
  exact-match-only fidelity, session continuity being process-local,
  UPI/email still having no surrogate mechanism.

## What Phase 7 will do

The latency harness: TTFT vs total, per-tier p50/p95/p99, cold start
reported separately, all at stated 1/4/8 concurrency levels. Nothing
built in Phase 6 needs to change for Phase 7 to begin.

## What you must do manually

- Personally re-run the Manual verification gate above before treating
  Phase 6 as closed.
- **Run the blind red-team session** — `adversarial/redteam/INSTRUCTIONS.md`
  has the full protocol; find one person with no stake in the design
  and no prior exposure to this repo's internals, give them about an
  hour, and record their results directly in
  `adversarial/results/redteam.md`. This cannot be done on your behalf.
- Decide when and how to address the discovered `role`-field
  misclassification bug (`docs/DECISIONS.md`, `docs/LIMITATIONS.md`) —
  it was deliberately left open per your own explicit instruction, not
  forgotten.
- Push these commits to `origin/main`.
- Decide when to tag this milestone — `v0.6.0` already tags Phase 5's
  closeout; this phase's tag is the next one.
