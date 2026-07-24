<#
.SYNOPSIS
    PowerShell-native task runner for local-first-llm-privacy-gateway.

    Chosen over a Makefile because the target development machine is native
    Windows 11 PowerShell with no assumed bash/WSL/make installation
    (see BUILD.md — "MY ENVIRONMENT"). The Phase 8 one-command demo
    (`demo`, below) wraps `docker compose`, not a Makefile -- this file
    remains the one task runner for everything, native or containerized;
    see docker-compose.yml's own docstring and README.md's Quick Start
    for what `demo` does and does not change (the native
    install/run/mock workflow below is unchanged and still the
    documented development path).

.EXAMPLE
    .\tasks.ps1 install
    .\tasks.ps1 run
    .\tasks.ps1 mock
    .\tasks.ps1 demo
    .\tasks.ps1 test
    .\tasks.ps1 lint
    .\tasks.ps1 typecheck
    .\tasks.ps1 check
#>

param(
    [Parameter(Position = 0)]
    [ValidateSet("install", "run", "mock", "demo", "test", "lint", "typecheck", "check", "rehydration-fidelity", "bench", "adversarial", "latency-pilot", "latency-bench")]
    [string]$Task = "check"
)

$ErrorActionPreference = "Stop"

switch ($Task) {
    "install" {
        pip install -r requirements.txt -r requirements-dev.txt
    }
    "run" {
        uvicorn app.main:app --reload --port 8080
    }
    "mock" {
        # The mock upstream must be running for the gateway to have
        # anything to forward to in mock mode (UPSTREAM_BASE_URL
        # defaults, in .env.example, to this port). Run in a second
        # terminal alongside `run`.
        uvicorn src.mock_upstream.main:app --reload --port 8081
    }
    "demo" {
        # BUILD.md, Phase 8: "One-command run... if setup has more than
        # one step, it has zero users." Builds and starts both
        # containers (docker-compose.yml) -- the mock upstream and the
        # gateway, wired together with no manual .env step required.
        # Does not touch, replace, or require the native
        # install/run/mock workflow above; this is an additional path,
        # not a replacement. First run builds the image (torch + GLiNER
        # weights download on first start) and can take several minutes;
        # subsequent runs reuse Docker's layer cache.
        docker compose up --build
    }
    "test" {
        pytest tests
    }
    "lint" {
        ruff check --line-length 100 .
    }
    "typecheck" {
        # Matches .github/workflows/ci.yml exactly: strict on every
        # first-party package, non-strict on tests/ (tests/ has never
        # been held to --strict — see docs/DECISIONS.md, 2026-07-23,
        # "Phase 7 Task 5").
        mypy --strict src
        mypy --strict app
        mypy --strict benchmarks
        mypy --strict adversarial
        mypy --strict latency
        mypy tests
    }
    "check" {
        # Runs the identical command sequence CI does (.github/workflows/ci.yml),
        # so this local target and CI can never silently diverge on what
        # counts as "passing" (docs/DECISIONS.md, 2026-07-23, "Phase 7 Task 5").
        ruff check --line-length 100 .
        mypy --strict src
        mypy --strict app
        mypy --strict benchmarks
        mypy --strict adversarial
        mypy --strict latency
        mypy tests
        pytest tests
    }
    "rehydration-fidelity" {
        # Regenerates rehydration_fidelity/results/latest.json — BUILD.md,
        # Phase 3: "Rehydration-fidelity harness runs and emits
        # per-category numbers to an artifact." Measures, does not
        # assert; re-run after committing code changes to re-stamp the
        # artifact with the commit that actually produced its numbers.
        python -m rehydration_fidelity.runner.run
    }
    "bench" {
        # Regenerates benchmarks/results/latest.json and latest.md -
        # BUILD.md, Phase 5: "make bench regenerates every number in
        # the README." Runs all four ablation arms (two GLiNER-backed)
        # over the full committed dataset - real models, real
        # inference, multi-hour runtime; deliberately not part of
        # `check`, which must stay fast enough to run on every change.
        python -m benchmarks.runner.run
    }
    "adversarial" {
        # Regenerates adversarial/results/latest.json and latest.md -
        # BUILD.md, Phase 6: every discovered bypass case run against
        # the real, running gateway (ARCHITECTURE.md's Adversarial
        # Evaluation section) - real Tier-2 inference for the
        # transliterated_names class; deliberately not part of `check`
        # for the same reason `bench` isn't.
        python -m adversarial.runner.run
    }
    "latency-pilot" {
        # BUILD.md, Phase 7: a small calibration pass (20 reps/cell)
        # across all 8 workloads x 5 concurrency levels (1/2/4/8/16),
        # spawning the real gateway + mock upstream as uvicorn
        # subprocesses over real sockets (latency/runner/process_harness.py -
        # deliberately not the in-process TestClient pattern `bench`/
        # `adversarial` use; see latency/__init__.py). Prints each
        # cell's mean latency and a projected full-run wall-clock
        # estimate; writes no artifact. Run this before `latency-bench`
        # to decide whether --repetitions needs adjusting on this
        # machine - some workloads (e.g. field_walker_heavy, which
        # makes 5 separate Tier-2 calls per request) have been observed
        # to take tens of seconds per request at concurrency 4+.
        python -m latency.runner.run --pilot-only
    }
    "latency-bench" {
        # Regenerates latency/results/latest.json and latest.md -
        # BUILD.md, Phase 7: cold start (10 fresh processes) plus the
        # full 40-cell matrix at 200 reps/cell by default. Real model
        # inference, real concurrent load against real subprocesses -
        # can take a long time (see `latency-pilot` above); deliberately
        # not part of `check` for the same reason `bench`/`adversarial`
        # aren't. Pass -Repetitions via the underlying module directly
        # if 200/cell is impractical on this machine, e.g.:
        #   python -m latency.runner.run --repetitions 50
        python -m latency.runner.run
    }
}
