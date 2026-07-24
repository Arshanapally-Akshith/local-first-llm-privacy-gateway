# Local-First LLM Privacy Gateway

A local-first egress proxy that sits between your application and a cloud LLM
provider. It exposes an OpenAI-compatible `/v1/chat/completions` surface,
inspects every outbound request body, replaces sensitive entities (Aadhaar,
PAN, card numbers, names, addresses, and more) with realistic,
format-preserving surrogates before anything leaves the machine, and
rehydrates the streaming response so your application sees the real values.
The provider sees `ABCDE1234F`. Your application sees the real PAN. Neither
side notices the proxy.

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8080/v1", api_key="not-needed")
```

That's the entire integration — one line changes, prompts stop leaking. This
is a competent reimplementation of a pattern already shipped in production by
Skyflow, Google Cloud DLP, and others (full list and framing in
[Competitor comparison](#competitor-comparison)) — not a novel gateway
architecture. What this repository contributes instead is two evaluation
artifacts that don't otherwise exist: a fairly-baselined Indian-PII detection
benchmark, and an adversarial bypass suite that reports the bypasses that
still work. Every number below is regenerated from a committed artifact by a
runner in this repository — nothing here is hand-typed.

## Demo

![Demo: starting the gateway with one command, sending a request with a synthetic Aadhaar and name, and watching the mock upstream receive only surrogates while the client gets the real values back](docs/assets/demo.gif)

Every command, log line, and response above is real — captured from an
actual `docker compose up --build` run and an actual request against the
running gateway (a synthetic, Verhoeff-valid Aadhaar from the UIDAI
reserved test range, `999910433219`, and a synthetic name, "Zara Arora,"
neither belonging to a real person). It is **not** a raw screen recording:
it's a small script that renders the real, verbatim captured text (the
container startup, the request, the gateway's own detection/substitution
log lines, what the mock upstream actually received, and the rehydrated
response) as a paced terminal-style animation. The content is 100% real;
only the animation's pacing was authored, the same way any edited demo
recording is trimmed. It shows the four things this gateway's whole value
proposition rests on, sequentially rather than in a literal split-screen:
the one-command startup, the request leaving with real PII in it, the
provider-facing side seeing surrogates only, and the caller getting the
real values back.

No screenshots beyond the terminal capture above — this is a CLI/API tool
with no graphical interface to screenshot.

Want to run this yourself instead of watching it? Skip to
[Try it yourself](#try-it-yourself).

## Key features

- **Drop-in OpenAI-compatible proxy** — one `base_url` change, no SDK, no
  wrapper.
- **Two-tier detection cascade** — deterministic checksum/regex (Aadhaar,
  PAN, IFSC, UPI, vehicle registration, card, email, phone) plus a
  GLiNER-class NER model for names, organisations, and addresses.
- **Format-preserving surrogates, not redaction** — FF1 (NIST SP 800-38G)
  keyed encryption for structured entities; a session-scoped name map for
  everything else. The model reasons over realistic-looking data instead of
  `[REDACTED]`.
- **Streaming-safe rehydration** — real values are restored in the response
  correctly across arbitrary SSE chunk boundaries.
- **Zero persistence** — no vault, no database. The one unavoidable piece of
  state (the name map) is in-memory and session-scoped, and dies with the
  session.
- **Runs with zero API key** — a mock upstream is the default and only
  upstream this repository's tests, benchmarks, and demo ever use.
- **Every number reproducible** — detection accuracy, adversarial
  robustness, and latency are each measured by a committed runner, never
  hand-typed into this document.

See [Architecture](#architecture) for how these pieces fit together, or
skip straight to [Try it yourself](#try-it-yourself) to run it.

## Architecture

One OpenAI-compatible surface, a config/flag-driven upstream (mock by
default, a real provider optionally — never hardcoded), a two-tier detection
cascade (Tier 1 wins any overlap with Tier 2; there is no Tier 3), FF1
surrogates for structured entities, and a session-scoped in-memory name map
for everything else. Layering is one-directional: `proxy` → `pipeline` →
`detect`/`surrogate`/`session` → `core`. No database, no policy engine, no
frontend. Full component diagrams, request/response lifecycles, and the
reasoning behind every frozen decision are in
[`ARCHITECTURE.md`](ARCHITECTURE.md).

## Try it yourself

No API key or account is required anywhere below — the mock upstream is
the default and only upstream this repository's tests, benchmarks, and
demo ever use. Run every command from a terminal, in the root of a
cloned copy of this repository:

```powershell
git clone https://github.com/Arshanapally-Akshith/local-first-llm-privacy-gateway.git
cd local-first-llm-privacy-gateway
```

### Step 1: start the gateway — pick one path

| | Docker (recommended) | Native |
|---|---|---|
| **Best for** | Trying it out, any OS | Editing the code |
| **Requires** | [Docker Desktop](https://www.docker.com/products/docker-desktop/) with Compose v2 | Windows + PowerShell + Python 3.11+ |
| **Steps** | 1 command | 2 terminals, a few commands |

**Docker** — works on Windows, macOS, or Linux (make sure Docker Desktop
is actually running first — a common first-try error is `docker: cannot
connect to the Docker daemon`, which just means Docker Desktop itself
hasn't started yet):

```powershell
.\tasks.ps1 demo
# equivalent on any OS:
docker compose up --build
```

Wait until `docker compose ps` shows both containers as `healthy`, then
go to [Step 2](#step-2-verify-its-actually-sanitizing-pii). First run
takes roughly 3–4 minutes (image build, plus a one-time Tier-2 model
download into a cached Docker volume); later runs take about 90 seconds.
`docker-compose.yml` fills in the three settings that have no default in
the app itself (`FPE_KEY`, `SESSION_TTL`, `FAIL_MODE`) with clearly-labeled
placeholder values, the same non-secret-placeholder pattern
`tests/conftest.py` uses — see that file's own comments for why each has
no default.

**Native** — Windows + PowerShell only; use this if you plan to edit the
code (on macOS/Linux, use Docker instead — `tasks.ps1` is PowerShell-only):

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
.\tasks.ps1 install
copy .env.example .env
```

Then start two long-running processes, each in its own terminal (both
must stay open):

```powershell
# Terminal 1
.\tasks.ps1 mock

# Terminal 2 — activate the venv again first (.\venv\Scripts\Activate.ps1)
.\tasks.ps1 run
```

Once both print `Uvicorn running on http://...`, go to
[Step 2](#step-2-verify-its-actually-sanitizing-pii).

This native setup is also the one to use for actually developing against
this codebase (`run`/`mock` both use `uvicorn --reload`, so edits apply
immediately) — it's a separate concern from the evaluation runners
further down this README (`bench`, `adversarial`, `latency-bench`,
`test`, `check`): each of those starts and stops its own gateway/mock
process internally and does **not** need `run`/`mock` already running.
Only `tasks.ps1 install` is a shared prerequisite for those.

### Step 2: verify it's actually sanitizing PII

Either path above leaves the gateway reachable at
`http://localhost:8080`. Send a request containing a synthetic Aadhaar
number and confirm the gateway substitutes it before forwarding, then
restores it in the response:

```powershell
$body = @{
    model    = "gpt-4"
    stream   = $false
    messages = @(@{ role = "user"; content = "My Aadhaar is 999910433219." })
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://localhost:8080/v1/chat/completions" -Method Post `
  -Headers @{ "X-Session-Id" = "quickstart-check" } -ContentType "application/json" -Body $body
```

Use `Invoke-RestMethod`, not `curl`/`curl.exe` — PowerShell's argument
quoting mangles inline JSON passed to a native executable's `-d` flag
(tested; it produces a malformed request the gateway rejects).
`999910433219` is a synthetic, Verhoeff-valid Aadhaar from UIDAI's
documented reserved test range — not a real one, safe to reuse anywhere.

**What you should see:**

1. **The command above prints a response** whose `choices[0].message.content`
   contains `999910433219` — your real input, unchanged from the caller's
   point of view.
2. **That alone isn't proof** — the mock upstream just echoes content back,
   so step 1 would look identical whether or not sanitization happened.
   The actual proof is in what the mock upstream logged as *received*.
   Check its terminal (running `tasks.ps1 mock`), or run
   `docker compose logs mock-upstream` for the Docker path, and look for
   a line shaped like:

   ```
   mock upstream received body: {'messages': [{'content': 'My Aadhaar is <a different 12-digit number>.', ...
   ```

3. **If that number is different from `999910433219`**, the gateway
   detected the real Aadhaar, replaced it with a format-preserving
   surrogate before the request ever left the machine, and rehydrated the
   real value back into the response you saw in step 1. That substitute-
   then-restore round trip is this repository's entire reason for
   existing. The [Demo](#demo) GIF above shows the same thing, with a
   name added to the request too.

If the numbers matched (no substitution happened), something's
misconfigured — check `docker compose logs gateway` (Docker) or the
gateway's own terminal (native) for a startup error, most likely a
missing or invalid `.env` value (native path only — the Docker path sets
these for you).

## Performance / benchmarks

### Detection accuracy (Phase 5)

Full per-entity precision/recall/F1 for all four ablation arms — stock
Presidio, Presidio with custom Indian-entity recognizers, Presidio+custom+our
GLiNER backend, and our full cascade — is committed at
[`benchmarks/results/latest.md`](benchmarks/results/latest.md), regenerated
by `.\tasks.ps1 bench` from [`benchmarks/data/dataset.jsonl`](benchmarks/data/DATASET_CARD.md)
(2,860 synthetic examples, gold offsets exact by construction). Rows where a
baseline beats our own cascade are not removed.

Headline, quoted directly from that artifact (commit `cb0e7f2`): our full
cascade reaches **1.000 F1 on 8 of 11 entity types** (AADHAAR, CARD, EMAIL,
IFSC, PAN, PHONE, UPI, VEHICLE_REG) and 0.995 on ADDRESS. The two hardest
categories — ORG (0.670 F1) and PERSON (0.828 F1) — are also the hardest for
the *fairly configured* Presidio+GLiNER baseline (arm 3: ORG 0.617, PERSON
0.747): free-text entity recognition in Hinglish/code-switched carrier text is
a genuinely hard problem for both approaches, not something either solves
outright. Stock Presidio (arm 1), which ships no Aadhaar/PAN/IFSC/UPI/vehicle
recognizers at all, scores 0.000 F1 on every one of those five types —
included in the table specifically so beating it isn't mistaken for a fair
comparison; arm 2 (Presidio + our committed custom recognizer config) is the
fair baseline, committed at
[`benchmarks/arms/presidio_custom/`](benchmarks/arms/presidio_custom/).

**Read this as an optimistic bound, not a real-world guarantee**: carrier
sentence phrasing is LLM-generated and diverse, but entity surface forms come
from our own generator — see the
[dataset card](benchmarks/data/DATASET_CARD.md) for the full caveat.

### Latency (Phase 7)

Full per-workload, per-concurrency results (TTFT with and without the
sliding window, total latency, per-tier percentiles, cold start) are
committed at [`latency/results/latest.md`](latency/results/latest.md),
regenerated by `.\tasks.ps1 latency-bench` — a real subprocess gateway and
mock upstream over real sockets, at concurrency levels 1/2/4/8/16, 200
requests per cell, every number stating its own concurrency level.

Headline, quoted directly from that artifact (commit `ab7222a`): **38 of the
40 cells completed with zero timeouts or errors.** Cold start (loading the
Tier-2 model) measured 14.6s–21.8s across 10 independent fresh process
starts. One systematic, disclosed finding, not a bug fixed to look better:
concurrent requests currently serialize on the gateway's single event loop
(`sanitize()` runs synchronously with no thread offload) — visible directly
in the numbers, e.g. the zero-PII baseline workload's mean TTFT goes from
~1.06s at concurrency=1 to ~12.0s at concurrency=16, and at the extreme this
pushed the gateway's own upstream-client timeout past its limit for one
workload (`multiturn_5`, the two non-clean cells, at concurrency 8 and 16).
Reported as measured; not optimized away — see
[`docs/PHASE_7_SUMMARY.md`](docs/PHASE_7_SUMMARY.md) for the full
investigation.

## Security & privacy guarantees

> **Structured entities are checksum-guaranteed**: if an Aadhaar, PAN, IFSC,
> UPI ID, vehicle registration, or payment card is present in canonical form,
> it is detected and replaced with certainty.
>
> **Names, organisations, and addresses are best-effort**, at the measured
> rate in the [detection accuracy](#detection-accuracy-phase-5) table above.
>
> **This system provides risk reduction with a measured residual. It does
> not provide a privacy guarantee.** A recall figure below 100% is a leak at
> that rate, and marketing "privacy" on top of a statistical detector would
> be dishonest. Full statement in
> [`ARCHITECTURE.md`](ARCHITECTURE.md#privacy-guarantees--stated-precisely).

### Adversarial bypass suite (Phase 6)

Full results, per bypass class, are committed at
[`adversarial/results/latest.md`](adversarial/results/latest.md),
regenerated by `.\tasks.ps1 adversarial` against the real, running gateway —
not against the detector in isolation. Clean and adversarial recall are
reported separately per class and never averaged.

Headline, quoted directly from that artifact (commit `e47a030`, 42 cases
across 9 bypass classes): **8 of 9 classes measured 0% adversarial recall**
(100% leak rate) on every entity type they were tested against — base64
encoding, number-words, spaced digits, Unicode homoglyphs, zero-width
characters, PII embedded in code, PII used as a JSON key, and PII split
across conversation turns. **19 specific bypasses are still unfixed today**,
named individually — case id and entity type — in the "Bypasses that still
work" section of the artifact above; none are hidden or removed. The ninth
class, transliterated Devanagari-script names, measured 100% recall — a
result that *contradicted* this project's own prediction (a Hinglish/
romanization weakness was expected to leak), reported here as a genuine
prediction mismatch rather than adjusted after the fact.

A blind red-team exercise (a person with no stake in the design, attacking
the running gateway for about an hour) has a harness and recording template
at [`adversarial/redteam/INSTRUCTIONS.md`](adversarial/redteam/INSTRUCTIONS.md)
but **has not been run yet** — see
[`adversarial/results/redteam.md`](adversarial/results/redteam.md), marked
"NOT YET RUN."

## Threat model

Full trust-boundary diagram, threat table, and reasoning in
[`ARCHITECTURE.md`](ARCHITECTURE.md#security-architecture). Summarized here:

**Why isn't the proxy the new juiciest target?** It holds no persistent
store. Real PII exists only in gateway process memory, only for the duration
of a request or an active session (bounded by `SESSION_TTL`). There is
nothing on disk to steal, and nothing to steal after the process exits.

**Fail-open vs. fail-closed.** `FAIL_MODE` has no default — the operator
must choose explicitly. This project's own position: **fail-closed is the
defensible default for a privacy product.** A detector failure under `open`
silently forwards unsanitised data — the privacy property evaporates exactly
when the system is under stress. A security control that degrades quietly is
not a control. `closed` returns a 503 instead: a loud outage, not a silent
leak.

**The rehydration-oracle tradeoff.** Rehydration only ever matches an exact,
contiguous surrogate string — never fuzzy, never partial. Aggressive fuzzy
matching would let an attacker who learns the surrogate distribution (or who
simply asks the model to repeat a name) induce the gateway into reinserting
*real* PII into attacker-readable output, turning the privacy layer into an
exfiltration primitive. This project accepts the alternative cost instead:
visible misses, where an unrehydrated surrogate leaks to the legitimate user
and looks like a bug. Measured per category in
[`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).

**Why there's no vault, and why the Tier-2 session map is unavoidable.** A
persistent map of real-to-surrogate values would concentrate every sensitive
value a user ever sent into one indexed, plaintext-recoverable store — a
threat-model inversion, building the exact database this project exists to
avoid creating. Structured entities (Aadhaar, PAN, card numbers, ...) use
keyed FF1 encryption and need no map at all: the same key that encrypted a
value can decrypt it, statelessly. Names, organisations, and addresses are
arbitrary Unicode with no fixed domain FF1 can permute over — producing a
*realistic* surrogate (not an opaque token) requires mapping into a finite
candidate list, and that map is the one piece of state this system cannot
avoid. It is in-memory, session-scoped, and dies at `SESSION_TTL` or process
exit — never written to disk, never logged.

## Competitor comparison

The gateway pattern — reversible, format-preserving pseudonymisation between
an application and an LLM — is solved and shipped in production today:

- **Skyflow** (LLM Privacy Vault)
- **Google Cloud DLP** (FF1-based deterministic surrogates, reversible,
  production since ~2019)
- **LiteLLM guardrails**
- **Cloudflare AI Gateway**
- **Portkey**
- **Microsoft Presidio** (the detection library this project's own benchmark
  baselines against, fairly configured)

This system is a competent reimplementation of that solved pattern. It does
not claim otherwise anywhere in this repository. Its contribution is the two
evaluation artifacts above: the Indian-entity benchmark (with a fair,
committed Presidio baseline) and the adversarial bypass suite — neither of
which a public comparison against these tools currently exists for.

## Limitations

Every currently-known gap — what's measured, what's deferred, and why — is
tracked in [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md). Highlights already
referenced above: UPI IDs and email addresses are detected but cannot be
sanitized yet (hard-fail, not a silent leak); detection is canonical-form
only, measured per bypass class in the adversarial suite; rehydration is
exact-match only, measured per category; session continuity holds only
within a single gateway process.

## Project status

| Phase | What it built | Status |
|---|---|---|
| 0 | Skeleton, config, safety rails | Done |
| 1 | Mock provider, streaming-correct passthrough | Done |
| 2 | Tier 1 detection + FF1 surrogates | Done |
| 3 | Session map, rehydration, multi-turn integrity | Done |
| 4 | Tier 2 detection (GLiNER) | Done |
| 5 | Detection benchmark | Done |
| 6 | Adversarial bypass suite | Done |
| 7 | Latency harness | Done |
| 8 | Demo, README, release | Done |

Per-phase detail, decisions, and manual-verification steps:
[`docs/PHASE_0_SUMMARY.md`](docs/PHASE_0_SUMMARY.md) through
[`docs/PHASE_7_SUMMARY.md`](docs/PHASE_7_SUMMARY.md). Every non-obvious
engineering decision, with alternatives considered:
[`docs/DECISIONS.md`](docs/DECISIONS.md) (append-only).

This repository is feature-complete. Future changes will focus on bug fixes,
benchmark updates, and maintenance rather than expanding scope.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
