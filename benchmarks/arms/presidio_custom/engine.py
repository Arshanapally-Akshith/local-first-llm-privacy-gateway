"""Arm 2 — Presidio + custom recognizers: a fully-default
`AnalyzerEngine` (arm 1's own construction, `presidio_stock.py`) with
`recognizers.py`'s five `DetectorBackedRecognizer`s added on top.

Additive, not a replacement engine: `AnalyzerEngine()`'s registry
auto-loads Presidio's own predefined recognizers at construction
(`CreditCardRecognizer`, `EmailRecognizer`, `PhoneRecognizer`, the
spaCy-backed `PERSON` recognizer, and everything else stock Presidio
ships) — this module only calls `registry.add_recognizer()` five times
on top of that, never removes or overrides anything Presidio already
had. This is what makes arm 2 a genuine extension of arm 1, not a
differently-configured engine that happens to share a name.
"""

from collections.abc import Sequence

from presidio_analyzer import AnalyzerEngine, EntityRecognizer

from benchmarks.arms.arm import Prediction
from benchmarks.arms.presidio_custom.recognizers import build_custom_recognizers
from benchmarks.arms.presidio_results import translate_results


def own_vocabulary(recognizers: Sequence[EntityRecognizer]) -> frozenset[str]:
    """The set of entity types `recognizers` were registered for -
    derived from the recognizer objects themselves, not a separately
    hand-maintained tuple of type-name strings that could silently drift
    out of sync with what is actually registered (e.g. if a future
    recognizer were added to or removed from `build_custom_recognizers()`
    without remembering to update a parallel literal here)."""
    return frozenset(entity_type for r in recognizers for entity_type in r.supported_entities)


class PresidioCustomArm:
    """Wraps an `AnalyzerEngine` extended with `recognizers.py`'s five
    custom recognizers. See module docstring for why this is additive
    to, not a replacement of, arm 1's engine."""

    def __init__(self) -> None:
        custom_recognizers = build_custom_recognizers()
        self._own_vocabulary = own_vocabulary(custom_recognizers)
        self._engine = AnalyzerEngine()
        for recognizer in custom_recognizers:
            self._engine.registry.add_recognizer(recognizer)

    def predict(self, text: str) -> list[Prediction]:
        results = self._engine.analyze(text=text, language="en")
        return translate_results(results, own_vocabulary_entity_types=self._own_vocabulary)
