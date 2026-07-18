"""Chunking-strategy selection for the mock's streamed responses.

Default (no directive): a word-ish split approximating real
token-by-token streaming. Directive present: the exact N-way
pathological split from src.core.chunking (BUILD.md, Phase 1 — "split a
configured string across N chunks... emit zero-content chunks").
"""

import re

from src.core.chunking import split_into_n_chunks


def default_token_split(content: str) -> list[str]:
    """Split on whitespace boundaries, keeping whitespace runs as their
    own pieces, so concatenation reconstructs `content` exactly.

    Not a real tokenizer — a rough approximation good enough to look
    like token-by-token streaming for the default (undirected) case. A
    real provider's actual tokenization is not something this mock
    needs to reproduce; only its SSE framing and chunk shape matter.
    """
    if not content:
        return []
    return re.findall(r"\S+|\s+", content)


def resolve_chunks(content: str, directive_n: int | None) -> list[str]:
    """Decide how to split `content` for one streamed response.

    `directive_n` comes from the request's optional `chunking.n` field
    — present only when a test deliberately asks for pathological
    splitting. Absent for any real OpenAI-SDK-shaped request, which
    gets the default word-ish split instead.
    """
    if directive_n is not None:
        return split_into_n_chunks(content, directive_n)
    return default_token_split(content)
