"""Public entry point: registry lookup + orchestration.

`encrypt`/`decrypt` are deliberately thin — registry lookup, fetch the
key, delegate to the domain. Every retry a domain needs (the
mixed-radix cycle-walk in `mixed_radix_ff1.py`) is self-contained
inside that domain using a single fixed `(key, tweak)`, not something
this module orchestrates: see that module's docstring for why that
technique is correctly invertible without the engine needing to track
which attempt succeeded. Aadhaar's UIDAI reserved-range requirement
was the one case that would have needed engine-level retry — tracking
which attempt succeeded so decrypt could agree — but it is proven
mathematically unsatisfiable by any construction (see
`docs/DECISIONS.md`, 2026-07-20) and permanently retired, not
deferred. This module has no retry loop of its own, and none is
expected to be added for Aadhaar.
"""

from src.core.types import EntityType
from src.surrogate.key_provider import KeyProvider
from src.surrogate.registry import get_surrogate_domain


def encrypt(entity_type: EntityType, value: str, key_provider: KeyProvider) -> str:
    domain = get_surrogate_domain(entity_type)
    return domain.encrypt(value, key_provider.get_key())


def decrypt(entity_type: EntityType, surrogate: str, key_provider: KeyProvider) -> str:
    domain = get_surrogate_domain(entity_type)
    return domain.decrypt(surrogate, key_provider.get_key())
