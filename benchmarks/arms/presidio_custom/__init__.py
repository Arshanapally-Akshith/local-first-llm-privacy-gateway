"""Arm 2 — Presidio + custom recognizers (BUILD.md, Phase 5 ablation
arm 2).

`recognizers.py` wraps this project's own, real Tier-1 `Detector`
classes as Presidio `EntityRecognizer`s — see that module's docstring
for why this is the strongest available form of reuse (not a second
regex, not a second checksum, the literal production class). `engine.py`
assembles the `AnalyzerEngine` these recognizers are registered into.
"""
