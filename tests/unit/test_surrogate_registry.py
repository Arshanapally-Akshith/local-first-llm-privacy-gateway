"""get_surrogate_domain: returns the registered domain for each of the
six FF1-eligible types, and raises loudly (never a silent no-op) for
UPI/email — deferred to Phase 3's map — and for Tier-2 types."""

import pytest

from src.core.exceptions import SurrogateDomainError
from src.surrogate.registry import get_surrogate_domain, max_registered_surrogate_length


@pytest.mark.parametrize(
    "entity_type",
    ["AADHAAR", "PAN", "CARD", "IFSC", "PHONE", "VEHICLE_REG"],
)
def test_returns_a_domain_for_every_ff1_eligible_type(entity_type: str) -> None:
    domain = get_surrogate_domain(entity_type)  # type: ignore[arg-type]

    assert domain.entity_type == entity_type


@pytest.mark.parametrize("entity_type", ["UPI", "EMAIL", "PERSON", "ORG", "ADDRESS"])
def test_raises_for_types_with_no_registered_domain(entity_type: str) -> None:
    with pytest.raises(SurrogateDomainError, match="no surrogate domain registered"):
        get_surrogate_domain(entity_type)  # type: ignore[arg-type]


def test_max_registered_surrogate_length_matches_every_domains_own_claim() -> None:
    """Guards against exactly the staleness `max_surrogate_length`
    exists to prevent: if a domain's own claimed maximum ever silently
    drifted from what it can actually produce, this is the test that
    would need updating alongside it — a hand-copied constant
    elsewhere in `src/pipeline/rehydrate.py` could not drift unnoticed
    the way a second, independent number could."""
    for entity_type in ["AADHAAR", "PAN", "CARD", "IFSC", "PHONE", "VEHICLE_REG"]:
        domain = get_surrogate_domain(entity_type)  # type: ignore[arg-type]
        assert domain.max_surrogate_length <= max_registered_surrogate_length()

    assert max_registered_surrogate_length() == 19  # CardDomain's own maximum, today
