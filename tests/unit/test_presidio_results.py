"""benchmarks.arms.presidio_results: `translate_results()` — the shared
logic now behind all three Presidio arms' `predict()` methods. Fast,
independent of any real `AnalyzerEngine`: constructs raw
`RecognizerResult`s by hand."""

from presidio_analyzer import RecognizerResult

from benchmarks.arms.presidio_results import translate_results


def test_stock_label_is_translated_via_the_shared_map() -> None:
    results = [RecognizerResult(entity_type="CREDIT_CARD", start=0, end=5, score=0.9)]
    predictions = translate_results(results, own_vocabulary_entity_types=frozenset())
    assert len(predictions) == 1
    assert predictions[0].entity_type == "CARD"
    assert predictions[0].start == 0
    assert predictions[0].end == 5


def test_own_vocabulary_label_passes_through_unchanged() -> None:
    results = [RecognizerResult(entity_type="AADHAAR", start=2, end=14, score=1.0)]
    predictions = translate_results(results, own_vocabulary_entity_types=frozenset({"AADHAAR"}))
    assert len(predictions) == 1
    assert predictions[0].entity_type == "AADHAAR"


def test_label_in_neither_the_map_nor_own_vocabulary_is_dropped() -> None:
    results = [RecognizerResult(entity_type="LOCATION", start=0, end=5, score=0.9)]
    assert translate_results(results, own_vocabulary_entity_types=frozenset()) == []


def test_person_resolves_identically_whether_via_the_map_or_own_vocabulary() -> None:
    # PERSON is both a stock Presidio label (SpacyRecognizer, arms 1/2)
    # and a possible custom-recognizer label (a GLiNER-backed
    # Tier2Detector, arm 3) - both branches must resolve it to the same
    # EntityType, since a caller may hit either depending on which arm
    # is asking.
    results = [RecognizerResult(entity_type="PERSON", start=0, end=5, score=1.0)]
    via_map = translate_results(results, own_vocabulary_entity_types=frozenset())
    via_own_vocabulary = translate_results(results, own_vocabulary_entity_types=frozenset({"PERSON"}))
    assert via_map == via_own_vocabulary
    assert via_map[0].entity_type == "PERSON"


def test_empty_results_returns_empty_list() -> None:
    assert translate_results([], own_vocabulary_entity_types=frozenset()) == []


def test_multiple_results_are_all_translated_independently() -> None:
    results = [
        RecognizerResult(entity_type="CREDIT_CARD", start=0, end=5, score=0.9),
        RecognizerResult(entity_type="PAN", start=10, end=20, score=1.0),
        RecognizerResult(entity_type="IBAN_CODE", start=25, end=30, score=0.8),
    ]
    predictions = translate_results(results, own_vocabulary_entity_types=frozenset({"PAN"}))
    assert {p.entity_type for p in predictions} == {"CARD", "PAN"}
    assert len(predictions) == 2
