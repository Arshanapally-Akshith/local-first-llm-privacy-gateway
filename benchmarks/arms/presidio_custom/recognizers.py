"""Custom Presidio recognizers for the five entity types Presidio ships
no recognizer for by default: AADHAAR, PAN, IFSC, UPI, VEHICLE_REG
(BUILD.md, Phase 5: "Presidio ships no Aadhaar/PAN/IFSC/UPI recognizers
by default"; vehicle registration has no Western equivalent either).

`DetectorBackedRecognizer` reuses the real, existing `Detector` classes
from `src/detect/tier1/` directly — it is a translation layer, not a
second implementation. This is deliberately stronger reuse than
re-deriving a Presidio `Pattern` from each detector's regex and
overriding `validate_result()` with a checksum call (Presidio's own
`PatternRecognizer` extension point, and the more obvious first
instinct): that approach would still need to export five private
`_CANDIDATE_PATTERN` regexes from Phase 2 modules never designed to
share them, and would leave two independent copies of "how do I
recognize this entity" — the regex, wrapped in Presidio's own matching
engine, and the checksum, called from validation — where this module has
zero. `Detector.detect(text)` runs exactly once, inside the class that
already owns the whole recognition rule (regex candidate extraction
*and* checksum/structural validation), and this file only ever converts
its output type.

One consequence worth stating plainly, not discovering later: this
means arm 2's recall on these five types is mathematically identical to
whatever this project's own cascade (arm 4, not yet built) achieves for
the same types — both call the same detector instance. That is the
correct shape for this ablation, not an accident: any arm-2-vs-arm-4
delta this benchmark eventually reports will be attributable entirely
to unstructured entity detection (PERSON/ORG/ADDRESS), never to these
five, isolating exactly the variable ARCHITECTURE.md's "arm 3 ≈ arm 4"
framing is built to measure.

`score=1.0` for every result — not a Presidio confidence heuristic, a
direct restatement of this project's own language: "Tier 1 outputs are
the only ones this system calls guaranteed" (ARCHITECTURE.md, Tier 1 —
deterministic).

CARD, EMAIL, PHONE, and PERSON deliberately have no recognizer here.
Presidio already ships recognizers for all four out of the box — the
fairness gap BUILD.md names is specifically about entities it "does not
attempt," which does not describe these. `presidio_stock.py`'s
`presidio_label_map.py` is what arm 2 relies on for them instead (see
`engine.py`).
"""

from presidio_analyzer import EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts

from src.detect.detector import Detector
from src.detect.tier1.aadhaar import AadhaarDetector
from src.detect.tier1.ifsc import IfscDetector
from src.detect.tier1.pan import PanDetector
from src.detect.tier1.upi import UpiDetector
from src.detect.tier1.vehicle_registration import VehicleRegistrationDetector


class DetectorBackedRecognizer(EntityRecognizer):
    """One class, parameterized by which `Detector` it wraps — not five
    near-identical subclasses (mirroring `src/detect/tier2/detector.py`
    ::`Tier2Detector`'s own "one class, parameterized by entity_type"
    precedent, Phase 4 Task 1)."""

    def __init__(self, detector: Detector) -> None:
        super().__init__(supported_entities=[detector.entity_type], supported_language="en")
        self._detector = detector

    def load(self) -> None:
        """Nothing to load: every wrapped detector is regex + checksum
        (or regex + structural check), already cheap and stateless —
        unlike Presidio's own NLP-model-backed recognizers, there is no
        asset here to warm."""

    def analyze(
        self, text: str, entities: list[str], nlp_artifacts: NlpArtifacts
    ) -> list[RecognizerResult]:
        """Delegate entirely to the wrapped `Detector`. `entities` and
        `nlp_artifacts` are unused: this recognizer supports exactly
        one entity type (fixed at construction) and needs no NLP
        pre-processing — the same reason `src/detect/tier1/*.py`'s own
        detectors take nothing but raw text.
        """
        return [
            RecognizerResult(
                entity_type=span.entity_type,
                start=span.start,
                end=span.end,
                score=1.0,
            )
            for span in self._detector.detect(text)
        ]


def build_custom_recognizers() -> list[DetectorBackedRecognizer]:
    """One `DetectorBackedRecognizer` per entity type Presidio ships no
    recognizer for by default. See module docstring for why CARD,
    EMAIL, PHONE, and PERSON are not included here."""
    return [
        DetectorBackedRecognizer(AadhaarDetector()),
        DetectorBackedRecognizer(PanDetector()),
        DetectorBackedRecognizer(IfscDetector()),
        DetectorBackedRecognizer(UpiDetector()),
        DetectorBackedRecognizer(VehicleRegistrationDetector()),
    ]
