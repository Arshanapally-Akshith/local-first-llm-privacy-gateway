# Fixture provenance

`openai_stream_capture.jsonl` is **hand-built from OpenAI's publicly
documented chat-completions streaming format** — the
`chat.completion.chunk` object shape (`id`, `object`, `created`,
`model`, `choices[].index`, `choices[].delta`,
`choices[].finish_reason`).

This is **not a live capture**. No paid API key has been used anywhere
in this repository, at any point (BUILD.md, ABSOLUTE CONSTRAINTS #2).

It exists so the mock upstream's SSE chunk shape can be validated
against a stable, documented reference instead of being trusted by
construction (ARCHITECTURE.md, Mock Provider: "Its framing must be
validated once against a real provider capture, and that capture
committed as a fixture").

If a real captured transcript becomes available later, it should
replace this file — the tests that consume it only assert on key
structure (`set(dict.keys())`), not on the exact IDs, timestamps, or
content, so no test changes should be needed.
