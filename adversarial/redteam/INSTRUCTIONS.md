# Blind Red-Team Session — Instructions

BUILD.md, Phase 6: "Get one person with no stake to spend an hour
attacking it blind." ARCHITECTURE.md: "The author writing the attacks
and then fixing them means the measured adversarial recall is *an
upper bound on a lower bound*, and any reviewer knows it." This session
is the one available mitigation in scope — it does not eliminate
selection bias, it bounds it, and the bound is stated alongside the
result.

This is a **real, manual exercise**. Nothing in `adversarial/cases/`
or `adversarial/runner/` runs it automatically, and no result may be
recorded in `adversarial/results/redteam.md` that a real person did not
actually produce.

## Who should run this

One person who:

- did **not** write any of the code in `src/`, `adversarial/`, or
  `benchmarks/`,
- has **not** read `ARCHITECTURE.md`'s Adversarial Evaluation section,
  `docs/LIMITATIONS.md`, or this suite's own case modules beforehand,
- can spend **about one hour**.

If no second person is available, the project owner may run the
session personally, but must record that fact plainly in the results
file rather than implying independence that didn't happen —
`docs/DECISIONS.md`'s own standard: state the limitation, don't hide
it.

## Setup

```powershell
# Terminal 1
.\tasks.ps1 mock

# Terminal 2
.\tasks.ps1 run
```

The gateway listens on `http://localhost:8080`. The mock upstream logs
every request body it receives, at INFO level, in Terminal 1 — this is
the tester's window into "what actually left the gateway." No other
tooling is required; `curl` or the `openai` Python SDK pointed at
`http://localhost:8080/v1` both work, per the project's own one-line
integration pitch.

## The task

Try, for one hour, to get a piece of sensitive information you invent
yourself (a fake Aadhaar, PAN, phone number, name — synthetic only,
per this repo's own rule: no real PII, ever) to appear **unmodified**
in Terminal 1's "mock upstream received body" log line, by any means:
rewording, formatting tricks, splitting it across messages, hiding it
in a tool call, anything. You do not need to know how the detectors
work — guessing from the outside is the point.

For each attempt, note:

- what you tried (the literal request or curl command),
- what you expected to happen,
- what Terminal 1 actually logged,
- whether your synthetic value survived unmodified (a "hit" for you,
  a miss for the gateway) or was replaced (a "miss" for you).

## Recording results

Fill in `adversarial/results/redteam.md` directly — it has a fixed
format for exactly this. Report your **own** hit rate (successful
bypasses ÷ total attempts) separately from anything in
`adversarial/results/latest.md`; the two are not the same measurement
and must never be combined or averaged.
