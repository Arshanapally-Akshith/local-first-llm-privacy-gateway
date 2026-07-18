"""Unit tests for the mock's chunking-strategy selection."""

from src.mock_upstream.chunking import default_token_split, resolve_chunks


def test_default_token_split_preserves_content() -> None:
    text = "Hello world, this is a test."
    assert "".join(default_token_split(text)) == text


def test_default_token_split_empty_content_returns_no_pieces() -> None:
    assert default_token_split("") == []


def test_default_token_split_keeps_whitespace_runs_intact() -> None:
    text = "a  b\tc"
    assert "".join(default_token_split(text)) == text


def test_resolve_chunks_without_directive_uses_default_split() -> None:
    text = "Hello world"
    assert resolve_chunks(text, None) == default_token_split(text)


def test_resolve_chunks_with_directive_uses_n_way_split() -> None:
    text = "Hello world"

    pieces = resolve_chunks(text, 4)

    assert len(pieces) == 4
    assert "".join(pieces) == text


def test_resolve_chunks_with_directive_can_produce_zero_content_pieces() -> None:
    pieces = resolve_chunks("ab", 5)

    assert "".join(pieces) == "ab"
    assert "" in pieces
