"""Span precedence: the documented overlap-resolution rule, tested
against hand-constructed `Span` objects only — no real detectors.
Detector integration is deferred to pipeline-level tests (later).
"""

import pytest

from src.core.types import EntityType, Offset, Span, Tier
from src.detect.precedence import _spans_overlap, resolve


def _span(start: int, end: int, entity_type: EntityType = "PAN", tier: Tier = 1) -> Span:
    return Span(start=Offset(start), end=Offset(end), entity_type=entity_type, tier=tier)


def test_no_overlap_keeps_all_spans() -> None:
    a = _span(0, 5)
    b = _span(10, 15)

    assert resolve([[a], [b]]) == [a, b]


def test_tier1_wins_over_longer_overlapping_tier2_span() -> None:
    tier1_span = _span(5, 10, tier=1)
    tier2_span = _span(0, 20, entity_type="ORG", tier=2)  # longer, fully contains tier1_span

    assert resolve([[tier1_span], [tier2_span]]) == [tier1_span]


def test_tier1_wins_over_tier2_even_when_tier2_registered_first() -> None:
    # Tier alone must decide, regardless of registration order.
    tier1_span = _span(5, 10, tier=1)
    tier2_span = _span(0, 20, entity_type="ORG", tier=2)

    assert resolve([[tier2_span], [tier1_span]]) == [tier1_span]


def test_longest_match_wins_within_same_tier_even_when_registered_second() -> None:
    short = _span(0, 5)
    long = _span(0, 10, entity_type="CARD")

    # `long` is detector index 1 (registered after `short`) and still
    # wins: length outranks registration order within the same tier.
    assert resolve([[short], [long]]) == [long]


def test_full_containment_same_tier_longest_wins() -> None:
    inner = _span(5, 8)
    outer = _span(0, 10, entity_type="CARD")

    assert resolve([[inner], [outer]]) == [outer]


def test_registration_order_breaks_tie_on_equal_tier_and_length() -> None:
    span_a = _span(0, 5)
    span_b = _span(2, 7, entity_type="CARD")  # same length as span_a, overlaps it

    assert resolve([[span_a], [span_b]]) == [span_a]
    # Swapping which detector index each span occupies swaps the winner
    # — proving the tie-break follows the explicit index, not incidental
    # Python list position or object identity.
    assert resolve([[span_b], [span_a]]) == [span_b]


def test_adjacent_spans_do_not_overlap_and_both_survive() -> None:
    a = _span(0, 5)
    b = _span(5, 10, entity_type="CARD")

    assert resolve([[a], [b]]) == [a, b]


def test_exact_duplicate_spans_deduplicate_to_one() -> None:
    a = _span(0, 5)
    b = _span(0, 5)

    result = resolve([[a], [b]])

    assert result == [a]
    assert len(result) == 1


def test_chain_overlap_highest_priority_span_eliminates_both_neighbors() -> None:
    # A overlaps B, B overlaps C, A and C do not overlap each other.
    # B is strictly longest (highest priority) and claims the whole
    # contested region, even though A and C don't conflict with each
    # other — this is the "winner takes its whole neighborhood"
    # semantics, not "maximize surviving span count".
    a = _span(0, 10)
    b = _span(8, 20, entity_type="CARD")  # length 12, longest
    c = _span(15, 25, entity_type="EMAIL")

    assert not _spans_overlap(a, c)  # sanity check on the fixture itself
    assert resolve([[a], [b], [c]]) == [b]


def test_chain_overlap_low_priority_middle_span_dropped_both_outer_spans_survive() -> None:
    # Same overlap shape as above, but this time the middle span (b)
    # is the *shortest* — lowest priority — so it is the one dropped,
    # and the two non-conflicting outer spans both survive together.
    a = _span(0, 10)
    b = _span(9, 16, entity_type="CARD")  # length 7, shortest
    c = _span(15, 25, entity_type="EMAIL")

    assert not _spans_overlap(a, c)  # sanity check on the fixture itself
    assert resolve([[a], [b], [c]]) == [a, c]


def test_output_sorted_by_start_offset_regardless_of_input_order() -> None:
    late = _span(20, 25)
    early = _span(0, 5, entity_type="CARD")
    middle = _span(10, 15, entity_type="EMAIL")

    assert resolve([[late], [early], [middle]]) == [early, middle, late]


def test_empty_outer_sequence_returns_empty_list() -> None:
    assert resolve([]) == []


def test_outer_sequence_of_empty_detector_results_returns_empty_list() -> None:
    assert resolve([[], []]) == []


def test_single_span_returns_unchanged() -> None:
    a = _span(0, 5)

    assert resolve([[a]]) == [a]


def test_resolve_output_is_pairwise_non_overlapping() -> None:
    spans_by_detector = [
        [_span(0, 10), _span(30, 40)],
        [_span(5, 15, entity_type="CARD", tier=2)],
        [_span(8, 12, entity_type="EMAIL")],
        [_span(35, 45, entity_type="IFSC")],
    ]

    result = resolve(spans_by_detector)

    for i, span_i in enumerate(result):
        for span_j in result[i + 1 :]:
            assert not _spans_overlap(span_i, span_j)


def test_resolve_is_deterministic_across_repeated_calls() -> None:
    spans_by_detector = [
        [_span(0, 10), _span(30, 40)],
        [_span(5, 15, entity_type="CARD", tier=2)],
        [_span(8, 12, entity_type="EMAIL")],
    ]

    first = resolve(spans_by_detector)
    second = resolve(spans_by_detector)

    assert first == second


@pytest.mark.parametrize(
    "a_start,a_end,b_start,b_end,expected",
    [
        (0, 10, 0, 10, True),  # identical
        (0, 10, 5, 15, True),  # partial, b shifted right
        (5, 15, 0, 10, True),  # partial, b shifted left (symmetry)
        (0, 10, 2, 5, True),  # b fully contained in a
        (2, 5, 0, 10, True),  # a fully contained in b (symmetry)
        (0, 5, 5, 10, False),  # adjacent, not overlapping
        (5, 10, 0, 5, False),  # adjacent, reversed (symmetry)
        (0, 5, 10, 15, False),  # disjoint with a gap
        (0, 5, 4, 9, True),  # single-character overlap at position 4
    ],
)
def test_spans_overlap_boundary_matrix(
    a_start: int, a_end: int, b_start: int, b_end: int, expected: bool
) -> None:
    a = _span(a_start, a_end)
    b = _span(b_start, b_end)

    assert _spans_overlap(a, b) is expected
