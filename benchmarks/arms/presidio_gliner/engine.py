"""Arm 3's `AnalyzerEngine` construction: arm 2's five Tier-1 custom
recognizers, `SpacyRecognizer` removed, three GLiNER-backed recognizers
added for `PERSON`/`ORG`/`ADDRESS`.

No new recognizer class exists here. `DetectorBackedRecognizer`
(`presidio_custom/recognizers.py`, Task 4) is generic over any
`Detector` — it was never Tier-1-specific, only ever
`Detector`-Protocol-shaped — and `Tier2Detector`
(`src/detect/tier2/detector.py`, Phase 4) already satisfies that exact
Protocol. Wrapping three `Tier2Detector` instances in the same adapter
that already wraps five Tier-1 ones needed no new code, which is itself
evidence the Task 4 "one class, parameterized" design was the right
call, not merely convenient in hindsight.

`get_tier2_detectors()` (`src/detect/registry.py`, Phase 4) already
builds exactly the three `Tier2Detector` instances needed — reused
directly, not reconstructed by hand. `get_tier2_model()`
(`src/detect/tier2/gliner_model.py`) is the same `@lru_cache`d factory
the live gateway uses; calling it here loads the real
`gliner_multi_pii-v1` weights once, shared with any other part of this
process that also calls it (there is no other part, in a benchmark
process, but the property holds regardless).
"""

from typing import Final

from presidio_analyzer import AnalyzerEngine

from src.detect.registry import get_tier2_detectors
from src.detect.tier2.gliner_model import get_tier2_model

from benchmarks.arms.arm import Prediction
from benchmarks.arms.presidio_custom.engine import own_vocabulary
from benchmarks.arms.presidio_custom.recognizers import (
    DetectorBackedRecognizer,
    build_custom_recognizers,
)
from benchmarks.arms.presidio_results import translate_results

_SPACY_RECOGNIZER_NAME: Final[str] = "SpacyRecognizer"
"""Presidio's own name for its default NLP-backed recognizer
(confirmed against the installed package: `AnalyzerEngine().registry
.recognizers` lists an instance with `.name == "SpacyRecognizer"`,
`.supported_entities == ["DATE_TIME", "LOCATION", "NRP", "PERSON"]`).
It is the *only* source of `PERSON` in a stock engine — removing it
entirely, rather than filtering its `PERSON` output after the fact, is
possible because none of its other three labels
(`DATE_TIME`/`LOCATION`/`NRP`) have an entry in
`presidio_label_map.py` either; losing them changes nothing this
project ever observes.
"""


class PresidioGlinerArm:
    """Wraps an `AnalyzerEngine` built from arm 2's five custom
    recognizers, with `SpacyRecognizer` removed and three GLiNER-backed
    `PERSON`/`ORG`/`ADDRESS` recognizers added. See module and package
    docstrings for why this is a backend swap, not an addition.
    """

    def __init__(self) -> None:
        tier1_recognizers = build_custom_recognizers()
        tier2_recognizers = [
            DetectorBackedRecognizer(detector) for detector in get_tier2_detectors(get_tier2_model())
        ]
        all_recognizers = [*tier1_recognizers, *tier2_recognizers]
        self._own_vocabulary = own_vocabulary(all_recognizers)

        self._engine = AnalyzerEngine()
        self._engine.registry.remove_recognizer(_SPACY_RECOGNIZER_NAME)
        for recognizer in all_recognizers:
            self._engine.registry.add_recognizer(recognizer)

    def predict(self, text: str) -> list[Prediction]:
        results = self._engine.analyze(text=text, language="en")
        return translate_results(results, own_vocabulary_entity_types=self._own_vocabulary)
