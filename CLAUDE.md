# CLAUDE.md — Engineering Handbook

> **Scope of this file.** These are the permanent engineering rules for this repository. They apply to every task, every phase, every session, forever.
>
> **`BUILD.md` owns the workflow** — phases, gates, Definitions of Done, what gets built when. **This file owns the standards** — how anything gets built at all. When they overlap, BUILD.md wins on *what*, this file wins on *how*. Neither overrides the other; they are read together.
>
> Read this file at the start of every session. If a task seems to require breaking a rule here, that is a signal to stop and ask — not a signal that the rule is stale.

---

## Project Overview

**What it is.** A local-first **egress proxy** that sits between an application and a cloud LLM provider. It exposes an OpenAI-compatible `/v1/chat/completions` surface. Outbound request bodies are inspected; sensitive entities are replaced with realistic, format-preserving surrogates before anything leaves the machine. The streaming response is rehydrated locally so the caller sees real values. The provider never sees real data.

The integration surface is one line:

```python
client = OpenAI(base_url="http://localhost:8080/v1", api_key="...")
```

**Primary objective.** Not the proxy. The proxy is table stakes — Skyflow, Google Cloud DLP, LiteLLM, Cloudflare AI Gateway, and Portkey all ship this pattern in production. The objective is **two evaluation artifacts that do not currently exist**:

1. A **fairly-baselined Indian-PII benchmark** — Presidio configured *with* custom recognizers, with ablation arms so any delta is attributable to a named cause.
2. An **adversarial bypass suite** that reports the bypasses that still work.

Everything else in the repo exists to make those two artifacts meaningful. **The evaluation is the project.**

**What the project is NOT.**

- Not a novel gateway. Any language in this repo implying novelty for the gateway pattern is a bug. Remove it on sight.
- Not a privacy *guarantee*. Structured entities are checksum-guaranteed. Names are best-effort with a measured residual. The claim is **risk reduction with a measured residual**, phrased exactly that plainly.
- Not an MCP proxy, browser extension, SaaS product, dashboard, or policy engine.
- Not a research project on inference risk or k-anonymity. Tier 3 was cut. It does not come back.
- Not a place where a real API key, real PII, or a persistent datastore is ever required or permitted.

---

## Engineering Philosophy

**Correctness over speed.** A proxy that is fast and silently drops a surrogate at a chunk boundary is worse than no proxy — it manufactures false confidence about a privacy property. Correctness here has a security meaning, not just an aesthetic one.

**Evaluation over feature count.** If the schedule slips, we ship a **worse detector, never a worse benchmark**. A competent detector with a rigorous benchmark is the project. A great detector with a self-serving benchmark is a rejection. This is the single most important sentence in this file.

**Honest measurement over favourable measurement.** Every number is reproducible from a committed artifact by a runner. Results where a baseline beats us stay in the table. Bypasses we cannot fix stay in the README. A finding of *"the cascade buys latency, not accuracy"* is a **good result** and gets reported as-is. Do not tune until our arm wins.

**Simplicity over cleverness.** The interesting parts of this system (FF1 domains, sliding-window rehydration, span precedence, concurrent session maps) are hard enough on their own merits. Every unit of cleverness spent elsewhere is a unit unavailable where it's needed. If a reviewer needs to reconstruct your reasoning to read the code, rewrite the code.

**Benchmark before optimization.** No optimization lands without a before-number and an after-number from the same harness at the same concurrency level. "This felt slow" is not a measurement.

**Small, reviewable commits.** A commit should be explainable in one sentence without the word "and."

**Boring is a feature.** This is a security-adjacent system. Predictable, obvious, well-tested code is the goal state, not a compromise.

---

## Frozen Architecture

**The architecture is frozen.** It was frozen after review. It is not a starting point for discussion.

| Decision | Frozen value |
|---|---|
| Layer | Egress proxy (OpenAI-compatible reverse proxy). Not MCP. Not a browser plugin. |
| Provider surface | One OpenAI-compatible interface. Upstream is config/flag driven, never hardcoded. |
| Default upstream | Mock provider. No paid key is required to run, test, benchmark, or demo. |
| Detection | Tier 1 (checksum/regex, deterministic) + Tier 2 (GLiNER-class NER). **No Tier 3.** |
| Structured surrogates | FF1 FPE (NIST SP 800-38G), keyed, stateless, invertible. No map. |
| Name surrogates | Finite name list + in-memory, session-scoped map. Unavoidable: names are not a fixed domain. |
| Persistence | None. No vault, no DB, no cross-session state, no PII on disk. |
| Policy engine | Cut. |
| Frontend | Cut. CLI + curl + logs. |
| MCP shim | Deferred out of this build. |

**Rules.**

- Claude Code **may and should** point out architectural problems. Raise them in the plan step, with reasoning.
- Claude Code **must never act on an architectural objection**. Argue, then stop. Do not implement the objection, do not implement a "compromise," do not leave a hook for it.
- **No feature additions unless explicitly requested.** Not small ones. Not helpful ones. Not "while I was in there."
- Nothing that looks like a deleted feature comes back through a side door: no policy YAML, no persistence layer, no dashboard, no Tier 3, no second provider.
- If a task appears to require an architecture change to complete, that means the task is wrong or the architecture concern is real. Either way: **stop and ask**.

---

## Coding Standards

**Style.** Python 3.11+. `ruff` for lint and format, `mypy --strict` on `src/`. CI enforces both. Line length 100. Formatter output is not a matter of opinion — do not hand-format around it.

**Type hints everywhere.** Every function signature, every module-level constant, every dataclass field. No bare `Any` without an inline comment explaining why it is unavoidable. Prefer `Protocol` over ABCs for seams. Prefer `NewType` for identifiers that must not be interchangeable — `SessionId`, `SurrogateToken`, `EntityType`. Passing a raw `str` where a `SurrogateToken` belongs is exactly the class of bug that corrupts rehydration silently.

**Domain types over primitives.** Spans are a type, not a tuple. Offsets are a type, not an int. A detected entity is a type, not a dict. The off-by-one that corrupts a JSON body is prevented by the type system or it is not prevented.

**Docstrings.** Every public function, class, and module. Google style. Document *why*, plus preconditions and failure modes — not a restatement of the signature. For anything touching FPE domains, span arithmetic, chunk buffering, or concurrency, the docstring must state the invariant the code maintains.

```
Bad:   """Encrypts the value."""
Good:  """FF1-encrypt a 12-digit Aadhaar to another Verhoeff-valid Aadhaar.

       Domain is fixed (radix 10, length 12), so this is invertible with
       the session key and requires no map. Output is checked against the
       UIDAI reserved range: a surrogate must never collide with an
       issuable ID.
       """
```

**Modular architecture.** Clear layers, one direction of dependency: `proxy` (HTTP/SSE) → `pipeline` (orchestration) → `detect` / `surrogate` / `session` (domain) → `core` (types, config, logging). Domain modules never import the proxy layer. Detectors never know about HTTP. The pipeline never knows which detector fired.

**SOLID, where it pays.** Specifically:
- **Single responsibility:** a detector detects; it does not substitute, log, or decide precedence.
- **Open/closed:** adding an entity type is a new detector registered in a registry, not an `if` branch in the pipeline.
- **Liskov:** every detector is substitutable behind the same `Detector` protocol — including the mock ones the tests use.
- **Interface segregation / dependency inversion:** see below.

Do not apply SOLID ceremonially. A factory for a thing with one implementation is bloat.

**Dependency injection where useful.** Anything with a clock, a key, a model, a network call, or randomness is injected, never reached for globally. Non-negotiable for: the upstream client, the FPE key provider, the NER model, the session store, the clock, the RNG. This is what makes the pathological-chunk tests, the forced-collision tests, and the TTL tests possible at all. `datetime.now()` or `random.choice()` called inline in domain code is a test you cannot write.

**No duplicated logic.** Checksum validation, span arithmetic, and surrogate formatting exist **once**. If a detector and a benchmark generator both need Verhoeff, they import the same function — a benchmark that validates with a second implementation is measuring the second implementation.

**Consistent naming.** Fixed vocabulary across code, tests, docs, and logs — do not invent synonyms:
- `entity` — a real sensitive value found in input
- `span` — `(start, end, entity_type)` over a specific string
- `surrogate` — the fake value substituted outbound
- `sanitize` — request path, real → surrogate
- `rehydrate` — response path, surrogate → real
- `tier` — which detection stage resolved a span
- `session` — the scope of the in-memory name map

Modules and functions: `snake_case`. Classes: `PascalCase`. Constants: `UPPER_SNAKE`. Private: leading underscore. Booleans read as assertions: `is_reserved_range`, `has_valid_checksum`. Never `data`, `info`, `handle`, `process`, `manager`, `util`.

**Clear error handling.** See the Error Handling section. Summary: typed, loud, actionable.

**Structured logging.** Every log line goes through the PII-safe formatter. Entity type, span offsets, tier, surrogate, session id, request id — **never plaintext**. `print()` is banned outside `scripts/`. f-string log messages are banned; pass structured fields. Every request carries a correlation id from ingress through rehydration.

**No magic constants.** Max lookahead window, session TTL, name-list size, retrieval thresholds, confidence cutoffs, chunk sizes, timeouts — named constants in one module, or config, with a comment stating where the value came from. If the value was chosen by measurement, cite the artifact. If it was a guess, say "guess" in the comment so it can be found later.

---

## Repository Conventions

```
.
├── CLAUDE.md                  # this file — permanent rules
├── BUILD.md                   # phase workflow — the plan
├── PROJECT_STATE.md           # current reality — updated every phase
├── README.md                  # the 90-second artifact; all numbers generated
├── Makefile / tasks.ps1       # bench, adversarial, test, lint — PowerShell-friendly
├── .env.example
├── src/
│   ├── core/                  # types, config, logging, exceptions. Imports nothing internal.
│   ├── detect/
│   │   ├── tier1/             # one module per entity type; checksums live here
│   │   ├── tier2/             # GLiNER wrapper
│   │   ├── registry.py        # detectors register; pipeline never branches on type
│   │   └── precedence.py      # span overlap resolution — the documented rule, once
│   ├── surrogate/             # FF1 domains, name list, format preservation
│   ├── session/               # in-memory map, TTL, collision handling, locking
│   ├── pipeline/              # sanitize / rehydrate orchestration, sliding window
│   ├── proxy/                 # FastAPI app, SSE framing, upstream client, fail-mode
│   └── mock_upstream/         # the test harness and the demo. Not an afterthought.
├── benchmarks/
│   ├── generate/              # slot carriers + programmatic injection
│   ├── data/                  # generated dataset + dataset card
│   ├── arms/                  # presidio_stock, presidio_custom, presidio_gliner, ours
│   ├── configs/               # committed Presidio recognizer configs — the fairness proof
│   ├── runner/                # make bench entrypoint; emits artifacts
│   └── results/               # committed artifacts, each stamped with producing commit
├── adversarial/
│   ├── cases/                 # one module per bypass class
│   ├── runner/
│   └── results/               # includes the bypasses that still work
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── property/              # FF1 round-trip, span arithmetic
│   └── regression/            # one file per fixed bug, named for it
├── docs/
│   ├── DECISIONS.md           # append-only
│   ├── LIMITATIONS.md
│   ├── THREAT_MODEL.md
│   └── PHASE_N_SUMMARY.md
└── scripts/                   # dev-only. Never imported by src/.
```

**Module organization.** One concept per module. A module over ~300 lines is a smell; over ~500 it is a defect. `src/core/` imports nothing internal — if it needs to, the dependency is inverted.

**File organization within a module.** Imports → module constants → types → public API → private helpers. Public function first: a reader should learn what the module is for in the first thirty lines.

**Import style.** Absolute imports from `src` only. No relative imports beyond `.`. No wildcard imports. No conditional imports for optional deps — if it's needed, it's in `requirements.txt`. Import modules, not symbols, when the module name adds meaning at the call site (`precedence.resolve(spans)` reads better than a bare `resolve(spans)`). Runtime-unneeded imports go under `if TYPE_CHECKING:`.

**Test naming.** `test_<unit>_<condition>_<expected>`. `test_verhoeff_rejects_transposed_digits` — not `test_aadhaar_2`.

---

## Testing Philosophy

**Every feature requires tests.** A phase with no tests is not done, regardless of what the code does. This is a Definition-of-Done item in BUILD.md and it is not negotiable here either.

**Unit before integration.** Detectors, checksums, FF1 domains, span arithmetic, and collision logic are unit-tested in isolation with injected dependencies. Integration tests exercise the proxy end-to-end against the mock upstream. If a bug can be caught by a unit test, an integration test catching it is a design failure — the seam is in the wrong place.

**Property tests where the property is the point.** FF1 round-trip (`decrypt(encrypt(x)) == x` for all valid inputs), span non-overlap after precedence resolution, surrogate format validity. These are invariants; sampled examples do not prove invariants.

**Adversarial-by-construction tests.** This system's failures are almost all invisible under happy-path testing. Tests must be hostile by default:
- Chunk boundaries: split every surrogate across 1/2/3/N chunks. The pathological chunker exists for this; use it everywhere on the response path.
- Collisions: force a 3-name list so collisions are certain, not probable.
- Concurrency: parallel requests on one session, asserting no duplicate or lost mapping.
- Multi-turn: surrogates arriving on ingress must not be re-encrypted. This never fires in single-turn tests, which is exactly why it needs its own test.
- Near-misses: bad checksums must **not** detect. A detector with no negative tests is a regex with good PR.

**Never merge untested code.** No exceptions for "just plumbing" or "just the mock."

**Regression test for every fixed bug.** Before the fix, write the failing test. It goes in `tests/regression/`, named for the bug, with a one-line comment stating the symptom. The test proving the bug existed is more valuable than the fix.

**Test the logger.** There is a test asserting the formatter cannot emit plaintext entity values. It is a security control, not a convenience.

**Benchmark and adversarial runners are code, and they get tested too.** Offset integrity on generated data must be asserted on 100% of examples. A benchmark with unverified labels is not a measurement.

---

## Documentation Rules

**`docs/DECISIONS.md` — append-only.** One entry per non-obvious call. Format: decision / alternatives considered / why / date. Never edit a past entry; supersede it with a new one that links back.

This file is not a chore. It is the interview. "Why is there a session map for names but not for Aadhaar?" and "why conservative matching instead of fuzzy?" are questions with excellent answers, and this is where they live. Entries required, at minimum, for: fail-open vs fail-closed, span precedence rule, span-matching criterion, the rehydration-oracle tradeoff, name-list size, window lookahead length.

**`PROJECT_STATE.md` must always reflect reality.** Architecture, module map, every env var, every endpoint, every config flag, current entity coverage, current metrics **with the commit hash that produced them**. Updated every phase. If it disagrees with the code, it is a defect — fix it in the same commit that caused the drift.

**Phase summaries stay concise.** One page. What was built, decisions and why, manual steps, how to verify, DoD checklist ticked, known limits, what's next. A summary that reads like a changelog has failed; a reader wants to know what the phase *cost* and what it *left broken*.

**README never contains a manually written number.** Every metric is regenerated by `make bench` / `make adversarial` from a committed artifact. If a number cannot be reproduced by a runner, it does not appear. Deleting the tables and regenerating them must produce identical output — this is a test, and it is the reason the claim is credible at all.

**Comments explain why, never what.** Any comment stating an invariant, a security rationale, a spec reference (NIST SP 800-38G, Verhoeff, UIDAI reserved ranges), or the origin of a constant is **load-bearing and must never be deleted during refactoring**. If a comment is wrong, fix it. Never silently drop it.

---

## Git Philosophy

**Small commits.** One logical change. If the message needs "and," split it.

**Meaningful messages.** Conventional-commit prefix, imperative mood, and a body explaining *why* whenever the why isn't obvious:

```
fix(pipeline): buffer surrogate spans across SSE chunk boundaries

A surrogate split across chunks was substituted on the first fragment,
emitting a partial rehydration. Window now holds max-surrogate-length
lookahead before flushing.

Costs TTFT; measured at +Xms p50 (see benchmarks/results/<hash>).
Regression test: tests/regression/test_split_surrogate_partial_flush.py
```

**Never combine unrelated work.** No drive-by reformatting inside a logic commit. No "also fixed a typo." A formatting-only commit is fine and should say so.

**Never commit:** `.env`, real PII of any kind, model weights, generated artifacts that a runner produces (except committed results, which are stamped), or commented-out code.

**Suggest commit messages after each phase** — a proposed sequence of small commits, not one giant squash. I decide what lands.

**Never `git push --force`, never rewrite shared history, never commit on my behalf without asking.**

---

## Performance Rules

**Measure first.** No optimization without a before-number from the harness. "This looks slow" is a hypothesis, not a finding.

**Profile before optimizing.** `cProfile` / `py-spy` on a real path, not intuition. The intuitive answer here is usually wrong: on this system, the cost is almost always the NER model or the buffer, and almost never the code you were tempted to rewrite.

**Never change architecture for optimization.** No caching layer, no persistence, no batching service, no second process. If a real bottleneck genuinely requires an architectural change, that is a **stop-and-ask**, not a refactor.

**Report honestly.** Every latency number carries its concurrency level. Cold start is reported as its own line, never folded into p50. TTFT is reported separately from total — it is the only latency a human perceives, and the sliding window taxes it. Tier-hit rates are stated as *measured-on-benchmark*, never as a property of real traffic.

**Correctness is not tradeable for latency.** Shrinking the lookahead window to improve TTFT is a correctness change wearing a performance costume. It requires a decision entry and approval.

---

## Security Rules

This is a security product. These rules are the product.

- **No PII in logs. Ever.** Not at DEBUG, not behind a flag, not temporarily, not "just while I debug this." Everything goes through the PII-safe formatter. Log types, offsets, tiers, surrogates.
- **Never persist sensitive values.** No disk, no DB, no cache, no temp file, no crash dump, no exception message containing a detected value. Exception payloads carry span offsets and entity type — never the value.
- **Secrets only in `.env`.** Never in code, never in tests, never in a fixture, never in a committed config. `.env.example` documents the shape.
- **Synthetic PII only in this repo.** Generated Aadhaars must be Verhoeff-valid **and** from never-issued reserved ranges. Verify against UIDAI's documented reserved space *before* writing the generator. A public repo shipping issuable national ID numbers is a legal problem, not a bug.
- **The session map is in-memory and session-scoped.** Making it durable "for reliability" would recreate the vault we deliberately deleted and invert the threat model. It is not an optimization opportunity.
- **No unsafe debugging.** No dumping request bodies, no `breakpoint()` in committed code, no logging the map, no test that prints a mapping.
- **No temporary bypasses.** No `if DEBUG: skip_detection`, no `# TODO: re-enable`, no disabled test left red. A bypass merged is a bypass shipped.
- **Conservative matching on rehydration is a security decision, not a quality shortfall.** Aggressive fuzzy matching turns the proxy into a rehydration oracle — an attacker who learns the surrogate distribution induces us to reinsert real PII into attacker-readable output. Visible misses are the correct trade. They get measured and reported.
- **Fail-mode is explicit and configured**, never implicit. A detector timeout has a defined outcome. Silently proceeding is fail-open with extra steps.

---

## Error Handling

**Fail loudly during development.** Config errors fail at startup, not at first request. An unexpected state in the pipeline raises; it does not shrug and continue. A half-sanitized request is a leak — crashing is strictly better.

**Never silently ignore exceptions.** Banned: bare `except:`, `except Exception: pass`, and `try/except` used for control flow around a preventable condition. Catch the narrowest type you can name. If you must swallow, log at WARNING with the reason and a correlation id, and write down why in the code.

**Typed exceptions.** A hierarchy rooted at `GatewayError`, with meaningful children: `DetectionError`, `SurrogateDomainError`, `RehydrationError`, `NameListExhaustedError`, `UpstreamError`, and `FailClosedError` (defined in `src/core/fail_mode.py`, not `exceptions.py`, since `core` must not depend on the proxy layer — see that module's own docstring). `SessionExpiredError` and `ConfigError` were considered and never implemented — the former was added ahead of a real caller and removed on review (`docs/DECISIONS.md`, 2026-07-21: "children are added only once a phase actually raises them, not ahead of need"), the latter because config failures already fail loud as `pydantic.ValidationError` at startup, with no gap a bespoke wrapper type would close. Every subclass has exactly one handler in `app/main.py` — either its own (`UpstreamError`, `SurrogateDomainError`, `FailClosedError`) or the shared `GatewayError` catch-all — never zero, never duplicated (`docs/DECISIONS.md`, Phase 7 failure-path audit). Callers catch categories, not strings. Never raise bare `Exception`.

**Actionable messages.** State what failed, what was expected, and what to do — with **no sensitive values in the message**.

```
Bad:   ValueError("bad input")
Bad:   SurrogateDomainError(f"cannot encrypt {value}")     # leaks PII
Good:  SurrogateDomainError(
           "FF1 domain mismatch for entity_type=AADHAAR: expected radix 10 "
           "length 12, got length 11 at span (140,151). Detector emitted a "
           "span the surrogate domain cannot represent — check tier1/aadhaar.py "
           "span boundaries."
       )
```

**Distinguish expected from exceptional.** A detector finding nothing is normal — return an empty result. A detector handed a span it cannot represent is exceptional — raise. Do not model the first as an error or the second as a `None`.

---

## Refactoring Policy

Refactor only when **all** of the following hold:

- Duplication has actually appeared (twice is a coincidence; three times is a refactor), **or** readability measurably improves for a specific reader task;
- The architecture is unchanged;
- Tests exist before the refactor and pass unchanged after — a refactor that requires editing tests is a redesign.

**Never refactor because another style looks nicer.** Not to fashion, not to a pattern you prefer, not to "clean up while I'm here." A refactor is its own commit, never mixed with behaviour change.

**Never delete a comment explaining complex logic during a refactor.** The comment is usually the only artifact of the reasoning.

Refactors touching FPE domains, span precedence, the sliding window, or the session map are **stop-and-ask**, regardless of how mechanical they look. That code is load-bearing and its failure modes are silent.

---

## Forbidden Actions

Claude Code must **never**, in any phase, for any reason, without explicit approval in the current turn:

**Architecture & scope**
- Redesign the architecture, or implement an architectural objection it raised
- Change the layer (MCP proxy, browser extension, sidecar, SDK wrapper)
- Add a second provider, or hardcode an upstream
- Reintroduce a cut feature: Tier 3 / inference risk, YAML policy engine, dashboard, UI, browser extension, MCP shim
- Add a database, cache, queue, vault, or **any persistence for PII or the session map**
- Add a phase, split a phase, merge phases, or work ahead of the current phase
- Add a feature, flag, or "small extra" that wasn't requested

**Evaluation integrity**
- Write a metric into the README by hand
- Report a number that `make bench` / `make adversarial` cannot regenerate
- Remove a benchmark row where a baseline beats us
- Remove or hide an unfixed bypass
- Benchmark against stock Presidio without the custom recognizers and call it fair
- Generate benchmark labels by asking an LLM for spans (slot-and-inject only)
- Tune the detector against the benchmark until our arm wins
- Change the span-matching criterion after seeing results
- Average clean and adversarial recall

**Craft**
- Skip tests, skip documentation, skip the DoD checklist
- Optimize without a measurement
- Introduce a dependency without justification, a version pin, and my approval
- Delete a comment explaining complex logic
- Leave a temporary bypass, a disabled test, a `TODO: re-enable`, or commented-out code
- Log plaintext PII, or persist a sensitive value anywhere
- Commit a secret, or a real PII value
- `git push --force`, rewrite history, or commit without being asked
- Claim novelty for the gateway pattern anywhere in the repo

---

## Decision Making

When uncertain — about an approach, a tradeoff, a spec ambiguity, or whether something is in scope — **do not resolve it by implementing**. A guess in code is indistinguishable from a decision, and it is what turns a frozen scope into drift.

Follow this, exactly:

1. **State the issue.** What's ambiguous, and what breaks either way.
2. **Give alternatives.** At least two, real ones, with their actual costs — including whichever one you don't like.
3. **Recommend one**, with reasoning.
4. **Wait for approval.** Then implement — and only what was approved.
5. **Record it** in `docs/DECISIONS.md` if it was non-obvious.

**Always stop and ask when:** an architecture change looks necessary; a new dependency is tempting; a measurement contradicts a plan; a benchmark result is unfavourable and you're inclined to adjust the method; a phase's DoD looks unachievable in scope; the frozen scope appears wrong.

"I wasn't sure, so I did both / I picked one / I added a flag" is the failure mode. Uncertainty is information — surface it.

---

## Code Review Checklist

Before considering **any** task complete, walk this. All of it, every time.

**Scope**
- [ ] This is the current phase's work, and nothing else
- [ ] No feature, flag, or extra crept in unrequested
- [ ] No architecture change, and no hook left for one
- [ ] Nothing implemented that I flagged as uncertain but wasn't approved

**Security**
- [ ] No plaintext PII in any log, exception message, test output, or artifact
- [ ] Nothing sensitive persisted anywhere — disk, DB, cache, temp
- [ ] No secret in code, test, or fixture
- [ ] All test PII is synthetic; Aadhaars Verhoeff-valid *and* reserved-range
- [ ] No debug bypass, no disabled test, no commented-out code
- [ ] Session-scoped state is still session-scoped

**Correctness**
- [ ] Chunk-boundary behaviour tested for anything on the response path
- [ ] Multi-turn: surrogates on ingress are not re-encrypted
- [ ] Span overlaps resolve per the documented precedence rule
- [ ] Concurrent access to the session map is safe, and there's a test proving it
- [ ] Collisions handled at assignment; forced-collision test present
- [ ] Negative and near-miss cases tested — bad checksum does not detect

**Craft**
- [ ] Types on every signature; `mypy --strict` clean; `ruff` clean
- [ ] Docstrings state *why*, plus invariants for anything hard
- [ ] No duplicated logic — one Verhoeff, one FF1, one span module
- [ ] No magic constants; each named value has a documented origin
- [ ] Errors are typed, loud, and actionable, with no values in messages
- [ ] Dependencies injected — clock, key, model, upstream, RNG
- [ ] Names use the fixed vocabulary

**Evidence**
- [ ] Tests exist and pass; a bug fix has a regression test that failed first
- [ ] Any performance claim has a before/after from the harness at a stated concurrency
- [ ] Any number in a doc traces to a committed artifact with a commit hash

**Documentation**
- [ ] Non-obvious decisions in `DECISIONS.md`
- [ ] `PROJECT_STATE.md` matches reality
- [ ] Load-bearing comments intact
- [ ] Phase summary written, DoD ticked, limitations stated

**Then stop.** Do not begin the next phase.

---

## Definition of High-Quality Code

"Production quality" here does not mean polished. It means **trustworthy** — the properties this system claims are actually true, and the numbers describing them are actually earned.

Concretely, high-quality code in this repo is:

**Honest.** It does what its docstring says, its numbers are reproducible from artifacts, and its failures are reported rather than smoothed. A benchmark row where we lose is high-quality. A bypass in the README that we cannot fix is high-quality. A hand-written metric is not, no matter how good the code underneath it is.

**Silent-failure-hostile.** Every failure mode in this system is quiet by nature — a surrogate split across a chunk, a re-encrypted surrogate on turn three, a collided name, a partially sanitized tool definition. None of these throw. None are visible in a demo. High-quality code here means the hostile test existed *before* the bug did. If a defect can hide, assume it is hiding, and go write the test that would catch it.

**Boring where it can be, careful where it can't.** The FF1 domain logic, the span arithmetic, the sliding window, and the session map deserve real thought and heavy invariants. Everything else should be so obvious it's dull. Cleverness distributed evenly across a codebase is cleverness wasted where it mattered.

**Explicable under pressure.** A reviewer will ask *why* — why no vault for Tier 1 but a map for Tier 2, why conservative matching, why fail-closed, why this precedence rule, why this window length. Every one of those has a good answer. High-quality code is code where the answer is already written down, in a comment or a decision entry, before the question is asked.

**Modest about its own guarantees.** Structured entities are checksum-guaranteed. Names are best-effort with a measured residual. The gateway pattern is not novel and we name the companies that shipped it first. Code and docs that overclaim are defects, and they are the most expensive defects in this project — because they are the ones that get caught in the room.

The bar, stated once: **could a Staff engineer read any file in this repo, reconstruct why it is the way it is, and find nothing that flatters us?**
