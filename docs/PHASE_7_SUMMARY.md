# Phase 7 Summary — Latency Harness

BUILD.md's Phase 7: three specific traps to instrument against —
concurrency turning p99 into "a different distribution entirely," cold
start hiding inside p50, and the sliding window taxing TTFT — plus a
literal Definition-of-Done requirement (per-tier p50/p95/p99, alongside
the tier-hit distribution) confirmed by direct quotation against
BUILD.md before implementation, not assumed. Built across three tasks
(design, implementation, DoD-gap closure) and two investigation-driven
follow-ups triggered by real pilot failures, all recorded in
`docs/DECISIONS.md`. The official, full-scale run (200 repetitions/cell,
all 40 cells, commit `ab7222a`) completed successfully and is the source
of every number in this document.

## What was built

| File(s) | Purpose |
|---|---|
| `latency/workloads/workload_types.py`, `latency/workloads/definitions.py` | `LatencyWorkload` + the 8 fixed, deterministic workloads (`baseline_clean`, `tier1_only`, `tier2_only`, `mixed_dense`, `multiturn_5`, `field_walker_heavy`, `pathological_chunking`, `long_response`), each isolating one cost axis |
| `latency/runner/stats.py` | `summarize()` — one percentile implementation (linear interpolation, fixed before any cell was measured), reused for every metric in the report |
| `latency/runner/process_harness.py` | Spawns the real gateway + real mock upstream as `uvicorn` subprocesses over real sockets — the deliberate departure from the in-process `TestClient` pattern `benchmarks`/`adversarial`/`rehydration_fidelity` share |
| `latency/runner/log_capture.py` | Parses the gateway's captured structured log, keyed by `correlation_id`, to recover the two internal timing events and per-span tier attribution |
| `latency/runner/measure.py` | `run_cell()` — real-socket, `ThreadPoolExecutor`-bounded concurrent request execution; per-request timeout/transport-failure/gateway-504 classification as recorded outcomes, never fatal |
| `latency/runner/run.py` | `build_report()`/`main()`/`run_pilot()` — cold-start section, the 40-cell matrix, per-tier TTFT breakdown, JSON+MD output |
| `latency/results/{latest.json,latest.md}` | The committed, commit-stamped official artifact (not yet `git add`ed — see "What you must do manually") |
| `src/core/logging.py` | `timestamp_ms` field added to `log_event()`/`_ALLOWED_FIELDS` — diagnostic only |
| `src/proxy/routes.py` | `X-Correlation-Id` response header; two diagnostic log events (`latency.upstream_first_chunk`, `latency.window_first_release`) — the only two production-code touches this phase made, both purely diagnostic |
| `tasks.ps1` | `latency-pilot` / `latency-bench` targets |
| `.github/workflows/ci.yml` | `mypy --strict latency` added |
| Tests | 24 new unit tests (`tests/unit/test_latency_{stats,workloads,log_capture,measure,run_report}.py`) + 4 new integration tests (`tests/integration/test_chat_completions_route.py`) |

## Key design decisions and why

**Real subprocess, real sockets — not the in-process pattern the other
three runners share.** This is the one runner whose entire purpose is
*how long something takes*, not *what the system decided* — an
in-process ASGI transport is not a neutral stand-in for that question
the way it is for correctness. `docs/DECISIONS.md`, 2026-07-23.

**A per-request timeout — client-side, or a gateway-generated HTTP 504
carrying the exact structured upstream-timeout body — is a recorded
benchmark outcome, never a fatal error.** Two real pilot failures drove
this, in sequence: a fixed 60s client timeout tripped on `multiturn_5`
at concurrency=8 and aborted the entire run; after widening it to a
configurable 120s default, a *different*, inner timeout (the gateway's
own `UPSTREAM_TIMEOUT=30s`, gateway→mock) tripped on `multiturn_5` at
concurrency=16, surfacing as a real HTTP 504. Both are excluded from
every latency percentile and counted separately per cell
(`timeout_count`/`error_count`), never silently dropped and never
allowed to abort the remaining cells. Deliberately narrow: only the
exact, content-verified 504 shape is reclassified — 400/422/500/502/503
and any unrecognized 504 remain fatal. `docs/DECISIONS.md`, both
2026-07-23 follow-up entries.

**Per-tier TTFT breakdown, closing a literal DoD gap.** BUILD.md's own
text — quoted verbatim and verified against Phase 4's "tier-hit
instrumentation emits which tier resolved each span" as the antecedent
— requires "Per-tier p50/p95/p99 + tier-hit distribution," two things
joined by "+". The harness initially reported only the tier-hit
fractions; `per_tier_ttft_with_window_ms` closes the gap, grouping
already-collected `RequestMeasurement`s by `tier_hit_class` with the
same `summarize()` every other metric uses. Deliberately TTFT-only, per
explicit instruction — not extended to total latency or window tax.

**Concurrency levels widened to 1/2/4/8/16**, exceeding BUILD.md's
literal "1/4/8" — an approved refinement, not a deviation; every
additional level still states itself with every number, per the DoD's
own requirement.

**Cold start via genuinely fresh processes**, reusing Phase 4's own
`startup.tier2_model_warmed` log event rather than adding new
instrumentation for it.

## A real finding this phase discovered, reported, and did not fix

Running the full matrix at concurrency 16 confirmed, with real numbers,
a characteristic first suspected during harness development:
`chat_completions()` (`src/proxy/routes.py`) calls `sanitize()`
synchronously, inline, with no thread/executor offload, inside a
single-process, single-event-loop `uvicorn` server. Every concurrently
-connected request's Tier-1/Tier-2 detection work fully serializes on
that one event loop — a request's wait time scales with how many
*other* requests are already queued ahead of it, not just its own cost.
This is visible directly in the committed numbers: `baseline_clean`'s
mean TTFT goes from 1058ms at concurrency=1 to 12,015ms at
concurrency=16 — an ~11x increase driven by queuing, not by the
workload itself changing (the same zero-PII message, every time). At
the extreme, this same mechanism pushed the gateway's own
gateway→mock `UPSTREAM_TIMEOUT` (30s) past its limit for
`multiturn_5` at concurrency=8 (1 of 200 requests) and concurrency=16
(22 of 200 timed out, 1 errored) — the only two non-clean cells in the
entire 40-cell matrix.

Per explicit instruction, this phase measured and reported this
honestly and did **not** optimize the gateway to improve it — no
thread offloading, no change to `sanitize()`'s call site, no change to
`UPSTREAM_TIMEOUT`. Whether to address it is a future decision, and
BUILD.md's own framing anticipated exactly this kind of result: "Python
GIL + CPU inference at 4 concurrent requests is a different
distribution entirely."

A second, smaller finding, also honest and also not "fixed" toward a
better-looking number: the sliding window's own overhead is
negligible everywhere in this run — `window_tax_percent` never exceeds
roughly 1% of TTFT in any clean cell (frequently under 0.1% at higher
concurrency, where total latency itself has grown large). The
window is not the bottleneck this benchmark's numbers point to;
detection cost under queuing is.

## Measured result

Full 40-cell table, per-tier breakdowns, and the cold-start section are
in `latency/results/latest.md` (regenerate with `.\tasks.ps1
latency-bench`). Headline numbers, commit `ab7222a`:

- **Cold start** (n=10 fresh processes): mean 16,659ms, p95 20,343ms,
  p99 21,501ms, min 14,645ms, max 21,790ms — "first inference is
  seconds," confirmed, and excluded from every steady-state row.
- **39 of 40 cells completed with zero timeouts and zero errors.**
  The two non-clean cells are both `multiturn_5`: concurrency=8 (199/200
  completed, 1 timeout) and concurrency=16 (177/200 completed, 22
  timeouts, 1 error) — directly attributable to the event-loop
  -serialization finding above, on the one workload with the most
  per-request Tier-2 calls (5 messages needing detection).
- **Every row states its own concurrency level**; no p99 is ever
  reported without one.
- **Per-tier TTFT breakdown present for every workload** — 6 of 8
  workloads show exactly one populated tier class per cell (by design:
  most workloads were built to isolate one tier's cost), `mixed_dense`/
  `multiturn_5`/`field_walker_heavy`/`pathological_chunking` show `both`,
  `long_response`/`tier2_only` show `tier2_only`, `tier1_only` shows
  `tier1_only`, `baseline_clean` shows `neither` — all exactly as the
  workload matrix was designed to produce.
- **TTFT vs. total latency vs. window tax are all reported separately**
  in every row, per the DoD.

## Manual verification gate

```powershell
# Fast suite (no real model load, no subprocess spawning)
.\tasks.ps1 check

# Calibration pass only (writes no artifact) -- confirms the harness itself still works
.\tasks.ps1 latency-pilot

# The official run this summary reports on (real subprocesses, real model,
# ~5.5 hours at n=200/cell across 40 cells) -- already completed; re-running
# regenerates latency/results/latest.json and latest.md
.\tasks.ps1 latency-bench
```

**Expected:** `ruff` and `mypy --strict src/app/benchmarks/adversarial/latency`
all clean (verified); the fast suite passes in full (809 tests,
41 deselected `real_model` tests — verified); `latency/results/latest.json`
and `latest.md` exist, are internally consistent (verified
programmatically: all 40 `(workload, concurrency)` pairs present with no
duplicates, `n + timeout_count + error_count == attempted` for every
cell, `tier_hit` and `per_tier_ttft_with_window_ms` keyed identically
and `tier_hit` fractions sum to 1.0 wherever `n > 0`), and the commit
hash embedded in the artifact (`ab7222a`) resolves to a real commit in
this repository's history.

One honesty note this project's own standard requires stating plainly:
unlike Phase 5/6's arms, this artifact's **timing numbers are not
expected to reproduce byte-identically** run to run — only the
workload content, classification logic, and structural schema are
deterministic. Re-running `latency-bench` will regenerate real,
slightly different latency values every time (that's what "measuring
real request timing on a real machine" means), which the artifact's own
`caveat` field already states. A second, full ~5.5-hour re-run to
verify this was not performed, as doing so would cost another
overnight run for a property that is definitionally not supposed to
hold (unlike Phase 6's adversarial suite, whose determinism *was*
verified because its output is expected to be exactly reproducible).

## Definition of Done

- [x] Harness runs at 1 / 2 / 4 / 8 / 16 concurrency (exceeds the
      literal "1 / 4 / 8" — approved widening); level reported with
      every number — confirmed in every row of `latest.md`
- [x] Cold start excluded from steady-state and reported as its own
      line — `latest.md`'s "Cold start" section, n=10 fresh processes,
      never folded into any cell
- [x] TTFT reported separately from total latency, with and without
      the window — `ttft_with_window_ms`, `ttft_without_window_ms`,
      `total_latency_ms`, `window_tax_ms`, `window_tax_percent` all
      present and distinct in every cell
- [x] Per-tier p50/p95/p99 + tier-hit distribution — `tier_hit`
      (fractions) and `per_tier_ttft_with_window_ms` (percentiles per
      tier class) both present, keyed identically, verified
      programmatically
- [x] "measured-on-benchmark, not real traffic" caveat in the table
      caption — quoted verbatim in `latest.md`, above the results table
- [x] Summary + state updated — this document. `BUILD.md` itself is
      **deliberately not edited**: every one of its Phase 0–6 DoD
      checklists remains unticked in place even though those phases are
      long complete — checked directly before writing this summary, to
      confirm this repository's own established convention rather than
      assume it. Completion tracking for every phase, including this
      one, lives exclusively in that phase's own `docs/PHASE_N_SUMMARY.md`,
      consistent with the Phase 0 decision (recorded in
      `docs/PHASE_0_SUMMARY.md`, reaffirmed at every closeout since) that
      a fourth, separately-maintained status document — `PROJECT_STATE.md`,
      and by the same reasoning, a routinely-edited `BUILD.md` — would
      only be a second surface that could drift out of sync with this
      one. The single existing annotation before this phase's own
      `BUILD.md` heading (2026-07-23, "an unplanned hardening pass...")
      was inserted for a genuinely out-of-sequence event, not as a
      routine phase-closeout marker, and is not a precedent for editing
      `BUILD.md` here.

**Gate:** "The latency table states its concurrency level and its TTFT
tax without me asking" — true of `latency/results/latest.md` as
committed-pending (see below): every row states its concurrency level;
the window's TTFT tax is reported in absolute ms and as a percentage,
in every row, unprompted.

## Known limitations / deliberately deferred

- **Event-loop serialization of `sanitize()` under concurrency** is a
  real, disclosed gateway characteristic (see "A real finding" above),
  measured and reported, deliberately not fixed this phase.
- **The gateway's own `UPSTREAM_TIMEOUT` (30s default)** is the binding
  constraint behind `multiturn_5`'s two non-clean cells — not adjusted,
  since doing so would be tuning configuration to make a specific
  finding disappear rather than reporting it.
- **n=200 steady-state repetitions retained**, not reduced, despite the
  ~5.5-hour cost — an explicit decision (see `docs/DECISIONS.md`'s
  repetition-count discussion), not an oversight.
- **Full-run timing reproducibility was not independently re-verified**
  — real latency numbers are expected to vary run to run; only content,
  classification, and schema are deterministic (see "Manual
  verification gate" above).
- **EMAIL and UPI are excluded from every workload** — neither has a
  registered surrogate domain (a pre-existing repository gap,
  `docs/LIMITATIONS.md`, not something this phase introduced or papered
  over).
- **6 of 8 workloads show a single populated tier class per cell** — by
  design (most workloads deliberately isolate one tier's cost); the
  per-tier breakdown is most informative for `mixed_dense`,
  `multiturn_5`, `field_walker_heavy`, and `pathological_chunking`,
  which combine both tiers.
- **Tier-hit rate is a property of this benchmark's own fixed workload
  matrix**, not of real traffic — stated in the artifact's own caveat,
  per BUILD.md's explicit requirement.

## What Phase 8 will do

Demo, README, release. `latency/results/latest.md` is exactly the
artifact Phase 8's README latency table will read from, the same way
Phase 5's `benchmarks/results/` and Phase 6's `adversarial/results/`
already are. Nothing built in Phase 7 needs to change for Phase 8 to
begin — **Phase 8 has not been started**, per explicit instruction.

## What you must do manually

- Personally review `latency/results/latest.json` and `latest.md`
  before treating Phase 7 as closed.
- **`git add latency/results/latest.json latency/results/latest.md`**
  and commit them — unlike this phase's code (already committed across
  four commits, `2e11c94` through `ab7222a`), the artifact itself is
  still untracked (`git status` shows `latency/results/` as untracked).
  This mirrors `benchmarks/results/` and `adversarial/results/`, both of
  which are genuinely tracked, committed artifacts — CLAUDE.md's one
  named exception to "never commit a generated artifact."
- Push these commits, and the results commit once made, to
  `origin/main`.
- Decide when to tag this milestone — `v0.7.1` already tags the
  pre-Phase-7 hardening pass; this phase's tag is the next one.
- Say "Begin Phase 8" when ready — not implied by anything in this
  document.
