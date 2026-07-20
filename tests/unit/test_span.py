"""Span is a domain type, not a tuple: immutable, and rejects an
arithmetically impossible offset pair at construction (CLAUDE.md:
"The off-by-one that corrupts a JSON body is prevented by the type
system or it is not prevented")."""

import dataclasses

import pytest

from src.core.types import Offset, Span


def test_span_equality_is_by_value() -> None:
    a = Span(start=Offset(0), end=Offset(5), entity_type="AADHAAR", tier=1)
    b = Span(start=Offset(0), end=Offset(5), entity_type="AADHAAR", tier=1)

    assert a == b


def test_span_is_frozen() -> None:
    span = Span(start=Offset(0), end=Offset(5), entity_type="AADHAAR", tier=1)

    with pytest.raises(dataclasses.FrozenInstanceError):
        span.start = Offset(1)  # type: ignore[misc]


@pytest.mark.parametrize(
    "start,end",
    [(-1, 5), (5, 5), (10, 5)],
)
def test_span_rejects_invalid_offsets(start: int, end: int) -> None:
    with pytest.raises(ValueError, match="invalid span"):
        Span(start=Offset(start), end=Offset(end), entity_type="AADHAAR", tier=1)
