<#
.SYNOPSIS
    PowerShell-native task runner for local-first-llm-privacy-gateway.

    Chosen over a Makefile because the target development machine is native
    Windows 11 PowerShell with no assumed bash/WSL/make installation
    (see BUILD.md — "MY ENVIRONMENT"). Revisit for a Makefile-inside-Docker
    setup at the Phase 8 one-command demo, not before.

.EXAMPLE
    .\tasks.ps1 install
    .\tasks.ps1 run
    .\tasks.ps1 mock
    .\tasks.ps1 test
    .\tasks.ps1 lint
    .\tasks.ps1 typecheck
    .\tasks.ps1 check
#>

param(
    [Parameter(Position = 0)]
    [ValidateSet("install", "run", "mock", "test", "lint", "typecheck", "check", "rehydration-fidelity", "bench")]
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
    "test" {
        pytest
    }
    "lint" {
        ruff check --line-length 100 .
    }
    "typecheck" {
        mypy --strict src
    }
    "check" {
        ruff check --line-length 100 .
        mypy --strict src
        pytest
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
}
