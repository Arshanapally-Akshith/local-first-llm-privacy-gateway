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
    .\tasks.ps1 test
    .\tasks.ps1 lint
    .\tasks.ps1 typecheck
    .\tasks.ps1 check
#>

param(
    [Parameter(Position = 0)]
    [ValidateSet("install", "run", "test", "lint", "typecheck", "check")]
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
}
