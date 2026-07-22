"""Translates raw Presidio `RecognizerResult`s into this project's own
`Prediction` type — shared by every arm that runs a Presidio
`AnalyzerEngine` (arms 1, 2, and 3; arm 4 has no Presidio involvement at
all).

Factored out once three call sites needed the identical shape (arm 1:
stock labels only; arm 2: stock labels + 5 custom-recognizer labels; arm
3: stock labels + 8) — CLAUDE.md's own threshold for when repetition
becomes a refactor ("twice is a coincidence, three times is a
refactor"), applied here the same way `Tier2Detector` already applies it
to this project's own detection code.
"""

from collections.abc import Iterable
from typing import cast

from presidio_analyzer import RecognizerResult

from src.core.types import EntityType, Offset

from benchmarks.arms.arm import Prediction
from benchmarks.arms.presidio_label_map import PRESIDIO_LABEL_TO_ENTITY_TYPE


def translate_results(
    results: Iterable[RecognizerResult], own_vocabulary_entity_types: frozenset[str]
) -> list[Prediction]:
    """Convert `results` into `Prediction`s.

    A result's Presidio label is resolved in one of two ways:

    - it is a stock Presidio label with an entry in
      `PRESIDIO_LABEL_TO_ENTITY_TYPE` (e.g. `CREDIT_CARD` -> `CARD`); or
    - it is already one of this project's own `EntityType` strings,
      because it came from one of *this arm's own* custom recognizers
      (`DetectorBackedRecognizer` emits `Span.entity_type` directly as
      its Presidio label — see `presidio_custom/recognizers.py`) —
      `own_vocabulary_entity_types` is exactly the set of types this
      specific arm's own custom recognizers were registered for, so a
      label landing here could only have come from one of them.

    A label matching neither is a stock Presidio type with no
    correspondence in this project's vocabulary (e.g. `LOCATION`,
    `IBAN_CODE`) and is dropped — correctly excluded, not a bug.
    """
    predictions: list[Prediction] = []
    for result in results:
        if result.entity_type in PRESIDIO_LABEL_TO_ENTITY_TYPE:
            entity_type = PRESIDIO_LABEL_TO_ENTITY_TYPE[result.entity_type]
        elif result.entity_type in own_vocabulary_entity_types:
            entity_type = cast(EntityType, result.entity_type)
        else:
            continue
        predictions.append(
            Prediction(start=Offset(result.start), end=Offset(result.end), entity_type=entity_type)
        )
    return predictions
