"""Arm 1 — stock Presidio (BUILD.md, Phase 5 ablation arm 1).

`AnalyzerEngine()` is constructed with zero modification: no custom
recognizers registered, no region configuration, no NLP engine override.
This is deliberate, not an oversight — the entire point of this arm is
to report whatever a genuinely out-of-the-box Presidio installation does
with Indian PII, including where that is weak or silent. Tuning anything
here would blur it into arm 2, and BUILD.md is explicit that beating an
unfairly-configured baseline is a credibility failure this project
refuses (ARCHITECTURE.md, Benchmark Architecture: "Presidio ships no
Aadhaar/PAN/IFSC/UPI recognizers by default... beating stock Presidio
means beating a tool at a task it does not attempt").
"""

from presidio_analyzer import AnalyzerEngine

from benchmarks.arms.arm import Prediction
from benchmarks.arms.presidio_results import translate_results


class PresidioStockArm:
    """Wraps a fully-default `AnalyzerEngine`. See module docstring for
    why nothing here is configured."""

    def __init__(self) -> None:
        self._engine = AnalyzerEngine()

    def predict(self, text: str) -> list[Prediction]:
        results = self._engine.analyze(text=text, language="en")
        # No custom recognizers exist on this arm's engine at all, so
        # there is no "own vocabulary" set to pass through - every
        # result is necessarily a stock Presidio label.
        return translate_results(results, own_vocabulary_entity_types=frozenset())
