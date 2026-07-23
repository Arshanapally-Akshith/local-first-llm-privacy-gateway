"""Spawns the real gateway and mock-upstream `uvicorn` processes the
Phase 7 harness measures against, health-checks both before handing
control back, and tears both down afterward.

This is the one deliberate departure from the in-process
`TestClient`/`ASGITransport` pattern `benchmarks/`, `adversarial/`, and
`rehydration_fidelity/` all share: those three measure *what* the
gateway decides, where an in-process transport is not just adequate
but preferable (faster, simpler, no port/process management). This
harness measures *how long it takes under real concurrent load* —
exactly the property an in-process, single-event-loop ASGI transport
risks distorting (no real socket, no real chunked-transfer framing).
See `docs/DECISIONS.md` for the full reasoning and the alternative
considered (an in-process capturing-log-handler harness, rejected for
this specific measurement).

Neither spawned process uses `--reload`: the file-watcher `tasks.ps1
run`/`mock` enable for development adds overhead and a source of
non-determinism this harness's own noise-minimization discipline
(Phase 7 design) explicitly rules out.
"""

import os
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import IO

import httpx

_HEALTH_PATH: str = "/health"
_READINESS_POLL_INTERVAL_S: float = 0.2
_READINESS_POLL_TIMEOUT_S: float = 60.0
"""Generous, not a measurement: the gateway's own startup, with
NER_WARMUP enabled, loads and warms the real Tier-2 model (seconds,
Phase 4) before `/health` ever answers 200. 60s sits comfortably above
that so the harness fails loudly if a process never comes up at all,
rather than hanging forever."""

_MOCK_READINESS_PROBE_BODY: dict[str, object] = {
    "model": "readiness-probe",
    "messages": [{"role": "user", "content": "ping"}],
    "stream": False,
}
"""The mock upstream (`src/mock_upstream/main.py`) has no `/health`
endpoint — unlike the gateway, it was never given one (BUILD.md's Phase
1 scope was streaming-correctness, not a liveness probe for a process
nothing but this harness ever spawns standalone). A minimal, valid,
non-streaming chat-completion request is the cheapest real readiness
check available: a 200 response means the ASGI app is up and routing,
which is all this harness needs to know before pointing the gateway at
it."""

_PROCESS_TERMINATE_TIMEOUT_S: float = 10.0

GATEWAY_PORT: int = 8180
MOCK_PORT: int = 8181
"""Deliberately distinct from `tasks.ps1 run`/`mock`'s 8080/8081 — this
harness spawns and owns its own processes end to end, and must never
collide with a developer's already-running dev-convenience instances
on the default ports."""


@dataclass(frozen=True, slots=True)
class ManagedProcess:
    """A spawned `uvicorn` process this harness owns end to end."""

    base_url: str
    stderr_log_path: Path
    process: subprocess.Popen[bytes]
    _stdout_file: IO[bytes]
    _stderr_file: IO[bytes]
    """The open file objects backing `process`'s `stdout`/`stderr` —
    held here only so `_terminate()` can close them once the process
    exits. Nothing else in this module reads through them; the log is
    read back later by re-opening `stderr_log_path` for reading, in
    `log_capture.py`. Without this, every spawned process (ten fresh
    ones per cold-start section alone) would leak two open file
    descriptors in this harness's own process for as long as it keeps
    running."""


def _gateway_ready(client: httpx.Client) -> bool:
    return client.get(_HEALTH_PATH).status_code == 200


def _mock_ready(client: httpx.Client) -> bool:
    return client.post("/v1/chat/completions", json=_MOCK_READINESS_PROBE_BODY).status_code == 200


def _wait_until_ready(
    base_url: str, is_ready: Callable[[httpx.Client], bool], timeout_s: float
) -> None:
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    with httpx.Client(base_url=base_url, timeout=2.0) as client:
        while time.monotonic() < deadline:
            try:
                if is_ready(client):
                    return
            except httpx.TransportError as exc:
                last_error = exc
            time.sleep(_READINESS_POLL_INTERVAL_S)
    raise RuntimeError(
        f"{base_url} did not become ready within {timeout_s}s"
        + (f" (last connection error: {last_error})" if last_error is not None else "")
    )


def _spawn_uvicorn(
    app_import_path: str,
    port: int,
    *,
    env: dict[str, str],
    log_dir: Path,
    label: str,
    is_ready: Callable[[httpx.Client], bool],
) -> ManagedProcess:
    """Start one `uvicorn` server as a real subprocess, on real sockets,
    with its stderr (where `PiiSafeFormatter`'s `StreamHandler` writes —
    `logging.StreamHandler()`'s default stream, unchanged by
    `src/core/logging.py`) captured to a file `log_capture.py` reads
    back afterward. Stdout is captured too, to a sibling file, purely
    for a human to inspect if a process fails to come up — nothing in
    this package ever parses it.
    """
    stderr_path = log_dir / f"{label}_stderr.log"
    stdout_path = log_dir / f"{label}_stdout.log"
    stdout_file = stdout_path.open("wb")
    stderr_file = stderr_path.open("wb")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            app_import_path,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=stdout_file,
        stderr=stderr_file,
    )
    base_url = f"http://127.0.0.1:{port}"
    _wait_until_ready(base_url, is_ready, _READINESS_POLL_TIMEOUT_S)
    return ManagedProcess(
        base_url=base_url,
        stderr_log_path=stderr_path,
        process=process,
        _stdout_file=stdout_file,
        _stderr_file=stderr_file,
    )


def _terminate(managed: ManagedProcess) -> None:
    """Best-effort graceful shutdown, falling back to a hard kill.

    A benchmark harness that leaves an orphaned `uvicorn` process
    holding a port is a worse failure mode than one that occasionally
    has to kill -9 it — the next run would otherwise fail at the
    health-check stage with a confusing "port already in use", not at
    this line where the actual cause is visible.
    """
    managed.process.terminate()
    try:
        managed.process.wait(timeout=_PROCESS_TERMINATE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        managed.process.kill()
        managed.process.wait(timeout=_PROCESS_TERMINATE_TIMEOUT_S)
    finally:
        managed._stdout_file.close()
        managed._stderr_file.close()


def _base_env(*, extra: dict[str, str] | None = None) -> dict[str, str]:
    """The environment every spawned gateway process gets.

    Starts from a *copy* of this process's own environment (so a
    developer's real `.env`-derived values, if already exported, still
    apply) and fills in synthetic placeholders for whichever required
    settings are absent — the identical `setdefault` pattern
    `tests/conftest.py` already uses for the same four fields, for the
    same reason: these are not secrets, only syntactically-valid
    placeholders satisfying `Settings()`'s required-field validation.
    """
    env = dict(os.environ)
    env.setdefault("FPE_KEY", "latency-harness-fpe-key-not-a-real-secret")
    env.setdefault("SESSION_TTL", "1800")
    env.setdefault("FAIL_MODE", "closed")
    env.setdefault("UPSTREAM_BASE_URL", f"http://127.0.0.1:{MOCK_PORT}")
    env.setdefault("NER_WARMUP", "true")
    if extra is not None:
        env.update(extra)
    return env


@contextmanager
def running_gateway_and_mock(log_dir: Path) -> Iterator[tuple[ManagedProcess, ManagedProcess]]:
    """Spawn the mock upstream and the gateway (in that order — the
    gateway's own startup never calls the upstream, but every real
    request it serves afterward will), health-check both, yield them,
    and always tear both down on exit — even if the caller raises.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    mock = _spawn_uvicorn(
        "src.mock_upstream.main:app",
        MOCK_PORT,
        env=dict(os.environ),
        log_dir=log_dir,
        label="mock_upstream",
        is_ready=_mock_ready,
    )
    try:
        gateway = _spawn_uvicorn(
            "app.main:app",
            GATEWAY_PORT,
            env=_base_env(),
            log_dir=log_dir,
            label="gateway",
            is_ready=_gateway_ready,
        )
        try:
            yield gateway, mock
        finally:
            _terminate(gateway)
    finally:
        _terminate(mock)


@contextmanager
def running_gateway_alone(log_dir: Path) -> Iterator[ManagedProcess]:
    """Spawn only the gateway, with no mock upstream running at all.

    Used exclusively for cold-start measurement (`run.py`): the Tier-2
    model warm-up `app/main.py`'s own lifespan performs at startup
    (`_warm_tier2_model()`, already logging `startup.tier2_model_warmed`
    with `latency_ms`) makes no upstream call — `UPSTREAM_BASE_URL` is
    validated for shape only at startup, never reachability (see
    `src/core/config.py`), so no mock needs to be listening on the
    other end for `/health` to come up.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    gateway = _spawn_uvicorn(
        "app.main:app",
        GATEWAY_PORT,
        env=_base_env(),
        log_dir=log_dir,
        label="gateway_cold_start",
        is_ready=_gateway_ready,
    )
    try:
        yield gateway
    finally:
        _terminate(gateway)
