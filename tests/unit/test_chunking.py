"""Proves split_into_n_chunks preserves content exactly under any split."""

import pytest

from src.core.chunking import split_into_n_chunks


@pytest.mark.parametrize("n", [1, 2, 3, 5, 10, 50])
def test_split_into_n_chunks_preserves_content(n: int) -> None:
    text = "The PAN ABCDE1234F was approved for Ramesh Kumar."

    pieces = split_into_n_chunks(text, n)

    assert len(pieces) == n
    assert "".join(pieces) == text


def test_split_into_n_chunks_n_equals_1_returns_whole_string() -> None:
    assert split_into_n_chunks("hello", 1) == ["hello"]


def test_split_into_n_chunks_more_pieces_than_characters_produces_empty_chunks() -> None:
    pieces = split_into_n_chunks("ab", 5)

    assert len(pieces) == 5
    assert "".join(pieces) == "ab"
    assert pieces.count("") == 3


def test_split_into_n_chunks_handles_empty_string() -> None:
    pieces = split_into_n_chunks("", 4)

    assert pieces == ["", "", "", ""]


def test_split_into_n_chunks_rejects_n_less_than_1() -> None:
    with pytest.raises(ValueError, match="n must be >= 1"):
        split_into_n_chunks("hello", 0)
