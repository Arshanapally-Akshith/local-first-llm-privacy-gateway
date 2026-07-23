"""The Phase 7 latency harness: measures the gateway's own overhead —
cold start, TTFT (with and without the sliding window), total latency,
and per-tier tier-hit distribution — across a fixed workload matrix and
concurrency levels 1/2/4/8/16.

Unlike `benchmarks/`, `adversarial/`, and `rehydration_fidelity/`, this
harness drives the gateway as a real `uvicorn` subprocess over real
sockets rather than in-process via `TestClient`/`ASGITransport`
(`latency/runner/process_harness.py`) — the concurrency/GIL effect and
the TTFT numbers this phase exists to measure are exactly the things an
in-process ASGI transport risks distorting. See `docs/DECISIONS.md` for
the full reasoning and the alternatives considered.
"""
