# Blind Red-Team Results

**Status: NOT YET RUN.**

This file is a template, not a report — no session has been conducted
yet. See `adversarial/redteam/INSTRUCTIONS.md` for how to run one. Do
not read the fields below as data; every value is a placeholder showing
the expected shape, not a measurement. This file must be filled in by
whoever actually ran the session, by hand — no runner regenerates it,
unlike `adversarial/results/latest.md`.

---

## Session record

| Field | Value |
|---|---|
| Tester | *(name or role, e.g. "colleague, no repo access" — or "project owner, no independent tester available" if that's genuinely the case; do not imply independence that didn't happen)* |
| Date | *(YYYY-MM-DD)* |
| Duration | *(actual time spent, e.g. "55 minutes")* |
| Prior exposure to this repo | *(e.g. "none" / "had read the README only" — state plainly)* |
| Gateway version / commit | *(`git rev-parse HEAD` at session time)* |

## Methodology

*(Describe in the tester's own words: what tools were used — curl,
`openai` SDK, browser, Postman; what strategy was tried; anything
prepared in advance vs improvised live.)*

## Attempts

One row per distinct thing tried. Add rows as needed.

| # | What was tried | Expected | What Terminal 1 actually logged | Hit (bypass worked) or Miss (gateway caught it) |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |

## Result

- Total attempts: *(n)*
- Hits (bypasses that worked): *(n)*
- **Hit rate: n/n** — reported on its own, never averaged with
  `adversarial/results/latest.md`'s clean/adversarial recall numbers;
  those measure this suite's own pre-written cases, this measures a
  blind tester's independent attempts, and the two answer different
  questions.

## Notes

*(Anything surprising, anything the tester wants recorded but that
didn't fit the table above — including bypasses that *didn't* occur to
this suite's own authored cases.)*
